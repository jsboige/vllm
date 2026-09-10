#!/usr/bin/env python3
"""Build a small, reviewable identity map from privileged vLLM traffic logs.

The operator report may contain short redacted conversation clues for human
qualification. The shared report never contains conversation text, credentials,
or arbitrary headers. This tool observes only; it never authorizes or blocks.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import ipaddress
import json
import math
import os
import re
import sys
import zlib
from collections import Counter
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_LIVE = ROOT / "logs" / "error_sources.jsonl"
DEFAULT_ARCHIVES = ROOT / "logs" / "archive"
DEFAULT_REGISTRY = ROOT / "configs" / "monitoring" / "traffic_identity_registry.json"
DEFAULT_OPERATOR = ROOT / "logs" / "traffic_identity.review.json"
DEFAULT_SHARED = ROOT / "logs" / "traffic_identity.summary.json"
DEFAULT_MARKDOWN = ROOT / "logs" / "traffic_identity.summary.md"

SECRET_PATTERNS = (
    re.compile(r'(?i)\bbearer\s+[^\s,;"\']+'),
    re.compile(
        r'(?i)["\']?(api[_ -]?key|token|password|secret)["\']?\s*[:=]\s*"[^"]*"'
    ),
    re.compile(
        r'(?i)["\']?(api[_ -]?key|token|password|secret)["\']?\s*[:=]\s*\'[^\']*\''
    ),
    re.compile(
        r'(?i)["\']?(api[_ -]?key|token|password|secret)["\']?\s*[:=]\s*[^\s,;"\']+'
    ),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{40,}\b"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
)
FORBIDDEN_SHARED_KEYS = {
    "conversation_clues",
    "auth_prefix",
    "body_head",
    "body_tail",
    "referer",
    "user_agent",
}
VALID_SUBJECT_TYPES = {"machine", "service", "team", "person", "location", "network"}
VALID_STATES = {"ACTIVE", "HISTORICAL", "PENDING_DEPLOYMENT", "CONDITIONAL", "DISPUTED"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> float | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.timestamp()


def redact(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:limit]


def conversation_clue(record: dict[str, Any]) -> str | None:
    """Return a short local-only clue, preferring user text from JSON bodies."""
    raw = f"{record.get('body_head') or ''}\n{record.get('body_tail') or ''}".strip()
    if not raw:
        return None
    candidate = raw
    try:
        body = json.loads(raw)
        messages = body.get("messages") if isinstance(body, dict) else None
        if isinstance(messages, list):
            user_parts = []
            for message in messages:
                if not isinstance(message, dict) or message.get("role") != "user":
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    user_parts.append(content)
                elif isinstance(content, list):
                    user_parts.extend(
                        str(part.get("text"))
                        for part in content
                        if isinstance(part, dict)
                        and part.get("type") == "text"
                        and part.get("text")
                    )
            if user_parts:
                candidate = user_parts[-1]
    except (ValueError, TypeError):
        pass
    clue = redact(candidate)
    return clue or None


def categorize_ua(raw: Any) -> str:
    ua = str(raw or "").strip().lower()
    if not ua:
        return "empty"
    if "ai engine" in ua:
        return "ai_engine"
    if "openai/js" in ua:
        return "openai_js"
    if "curl/" in ua:
        return "curl"
    if "claude" in ua and "desktop" in ua:
        return "claude_desktop_candidate"
    if "safari/" in ua:
        return "browser_safari"
    return "other"


def categorize_conversation(record: dict[str, Any], clue: str | None) -> str:
    # Classification sees both privileged capture fragments in memory. The clue is
    # only a redacted review aid and can be incomplete when the original JSON was
    # truncated, so it must not be the classifier's sole instrument.
    folded = " ".join(
        (
            str(record.get("body_head") or ""),
            str(record.get("body_tail") or ""),
            clue or "",
        )
    ).casefold()
    if "liveness" in folded:
        return "liveness_probe"
    if "ascenseur" in folded and "safari" in folded:
        return "safari_business"
    if (
        "maison d’édition" in folded
        or "maison d'édition" in folded
        or "maison d'edition" in folded
    ):
        return "publishing_business"
    return "unclassified"


def parse_ip(raw: Any) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    elif text.count(":") == 1 and "." in text:
        text = text.rsplit(":", 1)[0]
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def client_ip(record: dict[str, Any]) -> str | None:
    xff = str(record.get("x_forwarded_for") or "")
    for hop in xff.split(","):
        parsed = parse_ip(hop)
        if parsed:
            return parsed
    return parse_ip(record.get("x_real_ip")) or parse_ip(record.get("client"))


def ip_scope(value: str) -> str:
    address = ipaddress.ip_address(value)
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link_local"
    if address.is_private:
        return "private"
    if address.is_reserved:
        return "reserved"
    return "global"


def safe_model(raw: Any) -> str:
    model = str(raw or "unknown")[:80]
    return model if re.fullmatch(r"[A-Za-z0-9_.:/+-]+", model) else "other"


def endpoint(raw: Any) -> str:
    path = str(raw or "")
    if path.endswith("/chat/completions"):
        return "chat_completions"
    if path.endswith("/embeddings"):
        return "embeddings"
    if path.endswith("/models"):
        return "models"
    return "other"


def discover_sources(live: Path, archive_dir: Path) -> list[Path]:
    result: list[Path] = []
    if archive_dir.exists():
        result.extend(sorted(archive_dir.glob("error_sources-*.jsonl.gz")))
        result.extend(sorted(archive_dir.glob("error_sources-*.jsonl")))
    if live.exists():
        result.append(live)
    return result


def iter_complete_lines(path: Path) -> Iterator[bytes]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        for line in stream:
            if line.endswith(b"\n") or path.name != DEFAULT_LIVE.name:
                yield line


def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    subjects = registry.get("subjects") or []
    rules = registry.get("rules") or []
    subject_ids: set[str] = set()
    for subject in subjects:
        sid = subject.get("id")
        if not sid or sid in subject_ids:
            errors.append(f"duplicate or missing subject id: {sid}")
        subject_ids.add(sid)
        if subject.get("type") not in VALID_SUBJECT_TYPES:
            errors.append(f"invalid subject type: {sid}")
        if subject.get("state") not in VALID_STATES:
            errors.append(f"invalid subject state: {sid}")
    rule_ids: set[str] = set()
    for rule in rules:
        rid = rule.get("id")
        if not rid or rid in rule_ids:
            errors.append(f"duplicate or missing rule id: {rid}")
        rule_ids.add(rid)
        if rule.get("subject_id") not in subject_ids:
            errors.append(f"unknown subject in rule: {rid}")
        if not rule.get("evidence"):
            errors.append(f"missing evidence: {rid}")
        if rule.get("state") and rule["state"] not in VALID_STATES:
            errors.append(f"invalid rule state: {rid}")
        match = rule.get("match") or {}
        allowed_match_keys = {"networks", "ua", "conversation", "endpoint", "model"}
        unknown_match_keys = set(match) - allowed_match_keys
        if unknown_match_keys:
            errors.append(f"unknown match fields {sorted(unknown_match_keys)}: {rid}")
        if not any(match.get(key) for key in allowed_match_keys):
            errors.append(f"empty match: {rid}")
        for network in match.get("networks", []):
            try:
                ipaddress.ip_network(network, strict=False)
            except ValueError:
                errors.append(f"invalid network {network}: {rid}")
        parsed_times = {}
        for key in ("from", "until"):
            try:
                parsed_times[key] = parse_time(rule.get(key))
            except ValueError:
                errors.append(f"invalid {key}: {rid}")
        if rule.get("state") == "HISTORICAL" and parsed_times.get("until") is None:
            errors.append(f"historical rule requires until: {rid}")
        if (
            all(parsed_times.get(key) is not None for key in ("from", "until"))
            and parsed_times["from"] > parsed_times["until"]
        ):
            errors.append(f"from is after until: {rid}")
        subject = next(
            (item for item in subjects if item.get("id") == rule.get("subject_id")), {}
        )
        if subject.get("type") == "person":
            if rule.get("requires_confirmation") is not True:
                errors.append(f"person rule requires explicit confirmation: {rid}")
            if match.get("networks"):
                application_keys = {"ua", "conversation", "endpoint", "model"}
                if not any(match.get(key) for key in application_keys):
                    errors.append(f"person rule cannot match only a network: {rid}")
        if subject.get("state") in {"CONDITIONAL", "PENDING_DEPLOYMENT"} and rule.get(
            "auto_activate"
        ):
            errors.append(f"conditional rule cannot auto-activate: {rid}")
    return errors


def rule_matches(rule: dict[str, Any], observation: dict[str, Any]) -> bool:
    match = rule.get("match") or {}
    networks = match.get("networks") or []
    if networks:
        address = ipaddress.ip_address(observation["ip"])
        if not any(
            address in ipaddress.ip_network(network, strict=False)
            for network in networks
        ):
            return False
    for key in ("ua", "conversation", "endpoint", "model"):
        expected = match.get(key)
        if expected and observation[key] != expected:
            return False
    start, end = parse_time(rule.get("from")), parse_time(rule.get("until"))
    if start is not None and observation["ts"] < start:
        return False
    return not (end is not None and observation["ts"] > end)


def scan(sources: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    parse_errors = 0
    source_errors: list[dict[str, str]] = []
    first = last = None
    for source in sources:
        try:
            for raw in iter_complete_lines(source):
                digest = hashlib.sha256(raw).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                try:
                    record = json.loads(raw)
                    address = client_ip(record)
                    if not address:
                        continue
                    clue = conversation_clue(record)
                    ts = float(record.get("ts") or 0)
                    if not math.isfinite(ts) or ts <= 0:
                        raise ValueError("timestamp must be finite and positive")
                    observation = {
                        "ip": address,
                        "scope": ip_scope(address),
                        "ts": ts,
                        "status": int(record.get("status") or 0),
                        "ua": categorize_ua(record.get("user_agent")),
                        "conversation": categorize_conversation(record, clue),
                        "endpoint": endpoint(record.get("path")),
                        "model": safe_model(record.get("model")),
                        "clue": clue,
                    }
                    observations.append(observation)
                    first = ts if first is None else min(first, ts)
                    last = ts if last is None else max(last, ts)
                except (ValueError, TypeError, json.JSONDecodeError):
                    parse_errors += 1
        except (OSError, EOFError, gzip.BadGzipFile, zlib.error) as exc:
            source_errors.append({"source": source.name, "error": type(exc).__name__})
    coverage = {
        "verdict": "NO_CORPUS"
        if not sources
        else ("INCOMPLETE" if source_errors or parse_errors else "COMPLETE"),
        "sources": [path.name for path in sources],
        "source_count": len(sources),
        "unique_lines": len(seen),
        "observations": len(observations),
        "parse_errors": parse_errors,
        "source_errors": source_errors,
        "first_observed": timestamp_iso(first),
        "last_observed": timestamp_iso(last),
    }
    return observations, coverage


def group_observations(
    observations: list[dict[str, Any]], registry: dict[str, Any]
) -> list[dict[str, Any]]:
    subjects = {subject["id"]: subject for subject in registry["subjects"]}
    rules = {rule["id"]: rule for rule in registry["rules"]}
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for observation in observations:
        matched_rule_ids = tuple(
            sorted(
                rule["id"]
                for rule in registry["rules"]
                if rule_matches(rule, observation)
            )
        )
        # Include the applicable rule set in the grouping key. A historical match
        # must not label later traffic from the same IP and coarse signature.
        key = (
            observation["ip"],
            observation["ua"],
            observation["conversation"],
            observation["endpoint"],
            matched_rule_ids,
        )
        group = groups.setdefault(
            key,
            {
                "ip": observation["ip"],
                "scope": observation["scope"],
                "ua": observation["ua"],
                "conversation": observation["conversation"],
                "endpoint": observation["endpoint"],
                "count": 0,
                "first": observation["ts"],
                "last": observation["ts"],
                "statuses": Counter(),
                "models": Counter(),
                "conversation_clues": [],
                "rule_ids": matched_rule_ids,
            },
        )
        group["count"] += 1
        group["first"] = min(group["first"], observation["ts"])
        group["last"] = max(group["last"], observation["ts"])
        group["statuses"][str(observation["status"])] += 1
        group["models"][observation["model"]] += 1
        if (
            observation["clue"]
            and observation["clue"] not in group["conversation_clues"]
        ):
            group["conversation_clues"].append(observation["clue"])
            group["conversation_clues"] = group["conversation_clues"][:3]
    result = []
    for group in groups.values():
        matches = []
        for rid in group["rule_ids"]:
            rule = rules[rid]
            subject = subjects[rule["subject_id"]]
            matches.append(
                {
                    "rule_id": rid,
                    "subject_id": subject["id"],
                    "label": subject["label"],
                    "subject_type": subject["type"],
                    "state": rule.get("state", subject["state"]),
                    "evidence": rule["evidence"],
                    "requires_confirmation": bool(rule.get("requires_confirmation")),
                }
            )
        states = {match["state"] for match in matches}
        if "DISPUTED" in states:
            verdict = "DISPUTED"
        elif "CONDITIONAL" in states:
            verdict = "CONDITIONAL"
        elif "PENDING_DEPLOYMENT" in states:
            verdict = "PENDING_DEPLOYMENT"
        elif matches:
            verdict = "KNOWN"
        else:
            verdict = "UNKNOWN"
        identity = "|".join(
            map(
                str,
                (
                    group["ip"],
                    group["ua"],
                    group["conversation"],
                    group["endpoint"],
                    ",".join(group["rule_ids"]),
                ),
            )
        )
        result.append(
            {
                "group_id": hashlib.sha256(identity.encode()).hexdigest()[:12],
                "ip": group["ip"],
                "scope": group["scope"],
                "count": group["count"],
                "first_observed": timestamp_iso(group["first"]),
                "last_observed": timestamp_iso(group["last"]),
                "signature": {
                    "ua": group["ua"],
                    "conversation": group["conversation"],
                    "endpoint": group["endpoint"],
                },
                "statuses": dict(group["statuses"]),
                "models": dict(group["models"]),
                "verdict": verdict,
                "matches": matches,
                "conversation_clues": group["conversation_clues"],
            }
        )
    return sorted(
        result, key=lambda row: (row["verdict"] != "UNKNOWN", -row["count"], row["ip"])
    )


def shared_rows(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for group in groups:
        known = bool(group["matches"])
        if not known:
            continue
        result.append(
            {
                "group_id": group["group_id"],
                "ip": group["ip"],
                "ip_masked": False,
                "scope": group["scope"],
                "count": group["count"],
                "first_observed": group["first_observed"],
                "last_observed": group["last_observed"],
                "signature": group["signature"],
                "verdict": group["verdict"],
                "subjects": [
                    {
                        key: match[key]
                        for key in ("subject_id", "label", "state", "rule_id")
                    }
                    for match in group["matches"]
                ],
            }
        )
    return result


def assert_shared_safe(value: Any) -> None:
    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in FORBIDDEN_SHARED_KEYS:
                    raise ValueError(f"forbidden shared field: {key}")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, str):
            if "bearer " in item.casefold():
                raise ValueError("authorization material reached shared output")
            canary = os.environ.get("TRAFFIC_IDENTITY_PRIVACY_CANARY")
            if canary and canary in item:
                raise ValueError("privacy canary reached shared output")

    walk(value)


def atomic_json(path: Path, value: dict[str, Any], shared: bool = False) -> None:
    if shared:
        assert_shared_safe(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temp, path)


def atomic_text(path: Path, text: str) -> None:
    assert_shared_safe(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def render_markdown(shared: dict[str, Any]) -> str:
    coverage = shared["coverage"]
    coverage_line = (
        f"- Coverage: **{coverage['verdict']}** "
        f"({coverage['observations']} observations; {coverage['source_count']} sources)"
    )
    observed_line = (
        f"- Observed: {coverage['first_observed'] or '?'} "
        f"→ {coverage['last_observed'] or '?'}"
    )
    unknown_line = (
        f"- Public unknowns: {shared['unknown_public']['group_count']} groups / "
        f"{shared['unknown_public']['event_count']} events "
        "(details remain operator-only)"
    )
    lines = [
        "# Traffic identity summary",
        "",
        f"- Generated: {shared['generated_at']}",
        coverage_line,
        observed_line,
        unknown_line,
        "",
        "| Group | IP/CIDR | Signature | Verdict | Subject | Count | Last seen |",
        "|---|---|---|---|---|---:|---|",
    ]
    for group in shared["groups"]:
        signature = "/".join(group["signature"].values())
        subject = (
            ", ".join(item["label"] for item in group["subjects"])
            or "needs human qualification"
        )
        lines.append(
            f"| {group['group_id']} | {group['ip']} | {signature} | "
            f"{group['verdict']} | {subject} | {group['count']} | "
            f"{group['last_observed']} |"
        )
    if shared["pending_subjects"]:
        lines.extend(["", "## Pending / conditional"])
        for subject in shared["pending_subjects"]:
            lines.append(f"- **{subject['state']}** — {subject['label']}")
    text = "\n".join(lines) + "\n"
    assert_shared_safe(text)
    return text


def inventory(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.registry))
    errors = validate_registry(registry)
    if errors:
        print("REGISTRY INVALID: " + "; ".join(errors), file=sys.stderr)
        return 1
    observations, coverage = scan(
        discover_sources(Path(args.live), Path(args.archive_dir))
    )
    groups = group_observations(observations, registry)
    pending = [
        {"id": subject["id"], "label": subject["label"], "state": subject["state"]}
        for subject in registry["subjects"]
        if subject["type"] != "person"
        and subject["state"] in {"PENDING_DEPLOYMENT", "CONDITIONAL", "DISPUTED"}
    ]
    common = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "coverage": coverage,
        "pending_subjects": pending,
    }
    operator = {**common, "privacy_profile": "operator-local", "groups": groups}
    public_unknown = [
        group
        for group in groups
        if group["scope"] == "global" and group["verdict"] == "UNKNOWN"
    ]
    shared = {
        **common,
        "privacy_profile": "shared-no-conversation",
        "unknown_public": {
            "group_count": len(public_unknown),
            "event_count": sum(group["count"] for group in public_unknown),
            "groups_with_local_clues": sum(
                bool(group["conversation_clues"]) for group in public_unknown
            ),
            "latest_observed": max(
                (group["last_observed"] for group in public_unknown), default=None
            ),
            "review_command": "traffic_identity.py review --since <ISO-8601>",
        },
        "suppressed_internal_unknown_groups": sum(
            group["scope"] != "global" and group["verdict"] == "UNKNOWN"
            for group in groups
        ),
        "groups": shared_rows(groups),
    }
    atomic_json(Path(args.operator_output), operator)
    atomic_json(Path(args.shared_output), shared, shared=True)
    atomic_text(Path(args.markdown_output), render_markdown(shared))
    print(
        json.dumps(
            {
                "coverage": coverage["verdict"],
                "observations": coverage["observations"],
                "groups": len(groups),
                "unknown_groups": sum(
                    group["verdict"] == "UNKNOWN" for group in groups
                ),
                "review_file": str(Path(args.operator_output)),
            }
        )
    )
    if coverage["verdict"] == "NO_CORPUS":
        return 4
    return 3 if coverage["verdict"] == "INCOMPLETE" else 0


def explain(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.operator_output).read_text(encoding="utf-8"))
    groups = report.get("groups", [])
    if args.group:
        groups = [group for group in groups if group["group_id"] == args.group]
    elif args.ip:
        groups = [group for group in groups if group["ip"] == args.ip]
    explained = []
    for group in groups:
        explained.append(
            {key: value for key, value in group.items() if key != "conversation_clues"}
        )
    print(
        json.dumps(
            {
                "coverage": report.get("coverage", {}).get("verdict"),
                "groups": explained,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def review(args: argparse.Namespace) -> int:
    """Render public unknown/disputed groups for local human qualification."""
    report = json.loads(Path(args.operator_output).read_text(encoding="utf-8"))
    since = parse_time(args.since) if args.since else None
    groups = [
        group
        for group in report.get("groups", [])
        if group.get("scope") == "global"
        and (args.include_known or group.get("verdict") in {"UNKNOWN", "DISPUTED"})
        and (since is None or (parse_time(group.get("last_observed")) or 0) >= since)
    ]
    groups.sort(
        key=lambda group: (group.get("last_observed") or "", group.get("count", 0)),
        reverse=True,
    )
    groups = groups[: args.limit]
    lines = [
        "# Local traffic qualification queue",
        "",
        f"Coverage: {report.get('coverage', {}).get('verdict', 'UNKNOWN')}",
        "",
    ]
    if not groups:
        lines.append("No matching groups.")
    for group in groups:
        signature = "/".join(group["signature"].values())
        labels = (
            ", ".join(match["label"] for match in group.get("matches", []))
            or "unattributed"
        )
        lines.extend(
            [
                f"## {group['group_id']} — {group['ip']}",
                f"- Verdict: {group['verdict']} · signature: {signature}",
                f"- Activity: {group['count']} requests · "
                f"{group['first_observed']} → {group['last_observed']}",
                f"- Current labels: {labels}",
            ]
        )
        clues = group.get("conversation_clues") or []
        if clues:
            lines.append("- Redacted conversation clues:")
            lines.extend(f"  - {clue}" for clue in clues)
        else:
            lines.append("- Redacted conversation clues: none captured")
        lines.append("")
    output = "\n".join(lines)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
        print(json.dumps({"groups": len(groups), "review_file": str(target)}))
    else:
        print(output)
    return 0


def migrate(args: argparse.Namespace) -> int:
    source = Path(args.from_state)
    if not source.exists():
        result = {"status": "ABSENT", "seen": 0, "allowlisted": 0, "review_items": []}
    else:
        state = json.loads(source.read_text(encoding="utf-8-sig"))
        review = sorted(
            set(state.get("ip_identities") or {})
            | set(state.get("reviewed_not_allowlisted") or {})
        )
        result = {
            "status": "DRY_RUN",
            "seen": len(state.get("seen_ips") or {}),
            "allowlisted": len(state.get("allowlist") or []),
            "review_items": [
                {"ip": ip, "action": "compare-with-versioned-registry"} for ip in review
            ],
        }
    print(json.dumps(result, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    scan_cmd = commands.add_parser("inventory", parents=[common])
    scan_cmd.add_argument("--live", default=str(DEFAULT_LIVE))
    scan_cmd.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVES))
    scan_cmd.add_argument("--operator-output", default=str(DEFAULT_OPERATOR))
    scan_cmd.add_argument("--shared-output", default=str(DEFAULT_SHARED))
    scan_cmd.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN))
    explain_cmd = commands.add_parser("explain")
    explain_cmd.add_argument("--operator-output", default=str(DEFAULT_OPERATOR))
    selector = explain_cmd.add_mutually_exclusive_group(required=True)
    selector.add_argument("--group")
    selector.add_argument("--ip")
    review_cmd = commands.add_parser("review")
    review_cmd.add_argument("--operator-output", default=str(DEFAULT_OPERATOR))
    review_cmd.add_argument("--since", help="ISO-8601 lower bound on last activity")
    review_cmd.add_argument("--limit", type=int, default=30)
    review_cmd.add_argument("--include-known", action="store_true")
    review_cmd.add_argument(
        "--output", help="Write the local privileged review to this path"
    )
    commands.add_parser("validate-registry", parents=[common])
    migrate_cmd = commands.add_parser("migrate-state")
    migrate_cmd.add_argument(
        "--from-state", default=str(ROOT / "logs" / "leaked_key_monitor_state.json")
    )
    migrate_cmd.add_argument("--dry-run", action="store_true", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inventory":
            return inventory(args)
        if args.command == "explain":
            return explain(args)
        if args.command == "review":
            return review(args)
        if args.command == "migrate-state":
            return migrate(args)
        errors = validate_registry(load_registry(Path(args.registry)))
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print("registry valid")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, zlib.error) as exc:
        print(f"traffic identity error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
leaked_key_monitor.py — Monitor usage of the leaked vLLM "medium" API key.

Context (2026-05): a student leaked the medium API key (7711C3D0...). Rotating it
is impractical (a whole class + many services depend on it), so the decision is
MONITORING ONLY — no rotation. The error_source_capture ASGI middleware already
logs every /v1/* request (incl. real client IP via X-Forwarded-For) to
error_sources.jsonl. This script turns that raw log into an actionable signal:
which *unknown* public IPs are using the leaked key.

What it does
------------
1. Parse error_sources.jsonl, keep only requests authenticated with the leaked key
   (matched by the key prefix derived from VLLM_API_KEY_MEDIUM in .env — the secret
   itself is never written into this file).
2. Resolve the real client IP (left-most X-Forwarded-For hop, else X-Real-IP),
   stripping ports. Internal traffic (watchdog / localhost, no XFF) is ignored.
3. Diff each public IP against an allowlist of known-good IPs AND a persisted
   "already seen / acknowledged" state, so a given IP alerts only ONCE.
4. Detect anomalies: new unauthorized public IP, volume spike, off-hours activity.
5. Emit a French markdown summary (dashboard-ready) on stdout, append structured
   alerts to leaked_key_alerts.jsonl, and update the state file.

Exit codes:  0 = no new alert   2 = new alert(s) raised   1 = error
(So a scheduled task can branch on the exit code to decide whether to escalate.)

Usage
-----
  python leaked_key_monitor.py                 # incremental hourly scan
  python leaked_key_monitor.py --full          # rescan whole file (ignore high-water)
  python leaked_key_monitor.py --baseline      # record current IPs as acknowledged, no alert
  python leaked_key_monitor.py --report        # full-history human report, no state change
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# --- Paths (resolved relative to this script: myia_vllm/scripts/monitoring/) ---
HERE = os.path.dirname(os.path.abspath(__file__))
MYIA_VLLM = os.path.normpath(os.path.join(HERE, "..", ".."))
LOG_PATH = os.path.join(MYIA_VLLM, "logs", "error_sources.jsonl")
STATE_PATH = os.path.join(MYIA_VLLM, "logs", "leaked_key_monitor_state.json")
ALERT_PATH = os.path.join(MYIA_VLLM, "logs", "leaked_key_alerts.jsonl")
# Dashboard-ready markdown of the LAST alert batch (overwritten each alerting run).
# The headless-Claude relay reads this file verbatim to post to the dashboards,
# which keeps the French/accented content out of PowerShell's console encoding.
LAST_ALERT_PATH = os.path.join(MYIA_VLLM, "logs", "leaked_key_last_alert.md")
ENV_PATH = os.path.join(MYIA_VLLM, ".env")

# --- Allowlist: known-good public/LAN IPs of legitimate users/services. ---
# Editable here OR via the state file's "allowlist" array (state takes precedence
# when present, so you can acknowledge a new legit IP without touching code).
DEFAULT_ALLOWLIST = {
    "37.187.180.135",   # OVH (po-2023 / infra)
    "212.222.31.210",
    "92.150.81.115",
    "86.246.3.30",
    "163.5.3.41",
    "192.168.0.254",    # LAN reverse proxy
}

# --- Anomaly thresholds ---
VOLUME_SPIKE_PER_HOUR = 300   # >N reqs/h from a single non-allowlist IP -> spike alert
OFF_HOURS = range(0, 6)       # local hours considered "off-hours" (00:00-05:59)


def load_medium_key_prefix() -> str | None:
    """Derive the leaked-key match prefix from .env, without storing the secret here.

    The middleware records auth_prefix as 'Bearer ' + first 17 chars of the token
    + '...'. We match on 'Bearer ' + key[:17].
    """
    key = os.environ.get("VLLM_API_KEY_MEDIUM")
    if not key and os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VLLM_API_KEY_MEDIUM"):
                    _, _, val = line.partition("=")
                    key = val.strip().strip('"').strip("'")
                    break
    if not key:
        return None
    return "Bearer " + key[:17]


def real_client_ip(d: dict) -> str | None:
    """Left-most X-Forwarded-For hop (the original client), else X-Real-IP.

    Returns None for internal traffic (no XFF/XRI = watchdog/localhost).
    """
    xff = (d.get("x_forwarded_for") or "").strip()
    if xff:
        hop = xff.split(",")[0].strip().strip("[]")
        # strip ":port" only when it's a single colon (IPv4:port), not IPv6
        if hop.count(":") == 1:
            hop = hop.rsplit(":", 1)[0]
        if hop:
            return hop
    xri = (d.get("x_real_ip") or "").strip().strip("[]")
    if xri:
        if xri.count(":") == 1:
            xri = xri.rsplit(":", 1)[0]
        return xri or None
    return None


def is_public(ip: str) -> bool:
    return not ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.",
                              "172.19.", "172.2", "172.3", "127.", "169.254."))


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"high_water_ts": 0.0, "seen_ips": {}, "allowlist": []}


def save_state(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def scan(key_prefix: str, since_ts: float):
    """Aggregate leaked-key requests with ts > since_ts, grouped by real public IP."""
    agg = defaultdict(lambda: {"count": 0, "first": 9e18, "last": 0.0,
                               "status": defaultdict(int), "off_hours": 0,
                               "user_agents": defaultdict(int)})
    max_ts = since_ts
    total = internal = 0
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not (d.get("auth_prefix") or "").startswith(key_prefix):
                continue
            ts = float(d.get("ts", 0) or 0)
            if ts <= since_ts:
                continue
            max_ts = max(max_ts, ts)
            ip = real_client_ip(d)
            if ip is None:
                internal += 1
                continue
            if not is_public(ip):
                continue  # LAN proxy etc. handled via allowlist if needed
            total += 1
            a = agg[ip]
            a["count"] += 1
            a["first"] = min(a["first"], ts)
            a["last"] = max(a["last"], ts)
            a["status"][int(d.get("status", 0) or 0)] += 1
            a["user_agents"][(d.get("user_agent") or "?")[:60]] += 1
            if datetime.fromtimestamp(ts).hour in OFF_HOURS:
                a["off_hours"] += 1
    return agg, max_ts, total, internal


def fmt_ts(t: float) -> str:
    if not t or t > 9e17:
        return "?"
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    ap = argparse.ArgumentParser(description="Monitor leaked medium API key usage.")
    ap.add_argument("--full", action="store_true", help="rescan whole file")
    ap.add_argument("--baseline", action="store_true",
                    help="record current public IPs as acknowledged, raise no alert")
    ap.add_argument("--report", action="store_true",
                    help="full-history human report, no state change")
    args = ap.parse_args()

    if not os.path.exists(LOG_PATH):
        print(f"ERROR: log not found: {LOG_PATH}", file=sys.stderr)
        return 1

    key_prefix = load_medium_key_prefix()
    if not key_prefix:
        print("ERROR: could not derive medium key prefix (set VLLM_API_KEY_MEDIUM "
              "or check .env)", file=sys.stderr)
        return 1

    state = load_state()
    allowlist = set(DEFAULT_ALLOWLIST) | set(state.get("allowlist", []))
    seen = state.get("seen_ips", {})

    since = 0.0 if (args.full or args.baseline or args.report) else state.get("high_water_ts", 0.0)
    agg, max_ts, total, internal = scan(key_prefix, since)

    # Classify
    new_alerts = []
    for ip, a in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
        if ip in allowlist:
            continue
        known = ip in seen
        spike = a["count"] >= VOLUME_SPIKE_PER_HOUR
        if not known:
            new_alerts.append(("NEW_IP", ip, a))
        elif spike:
            new_alerts.append(("VOLUME_SPIKE", ip, a))
        # update/record seen state
        rec = seen.get(ip, {"first": a["first"], "count": 0})
        rec["last"] = a["last"]
        rec["count"] = rec.get("count", 0) + a["count"]
        rec["first"] = min(rec.get("first", a["first"]), a["first"])
        seen[ip] = rec

    # --- REPORT mode: print everything, change nothing ---
    if args.report:
        print(f"# Rapport monitoring clé leakée (full history)\n")
        print(f"- Log: {LOG_PATH}")
        print(f"- Requêtes clé leakée (publiques): {total} | interne (watchdog): {internal}")
        print(f"- IP publiques distinctes: {len(agg)}\n")
        print("| IP réelle | statut | requêtes | première | dernière | off-h |")
        print("|---|---|---|---|---|---|")
        for ip, a in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
            tag = "✅ allow" if ip in allowlist else "⚠️ INCONNUE"
            print(f"| `{ip}` | {tag} | {a['count']} | {fmt_ts(a['first'])} | "
                  f"{fmt_ts(a['last'])} | {a['off_hours']} |")
        return 0

    # --- BASELINE mode: acknowledge current IPs, no alert ---
    if args.baseline:
        state["seen_ips"] = seen
        state["high_water_ts"] = max_ts
        if "allowlist" not in state:
            state["allowlist"] = []
        save_state(state)
        print(f"BASELINE recorded: {len(seen)} public IP(s) acknowledged, "
              f"high_water={fmt_ts(max_ts)}. No alert raised.")
        return 0

    # --- Normal scan: persist state, emit alerts ---
    state["seen_ips"] = seen
    state["high_water_ts"] = max_ts
    state.setdefault("allowlist", [])
    save_state(state)

    now = datetime.now(timezone.utc).isoformat()
    if not new_alerts:
        print(f"[{now}] RAS — {total} requête(s) clé leakée depuis {fmt_ts(since)}, "
              f"aucune nouvelle IP non autorisée.")
        return 0

    # Build dashboard-ready French markdown + structured alert records
    lines = [f"🚨 **Alerte clé leakée (medium)** — {len(new_alerts)} événement(s) "
             f"nouveau(x) — {now}", ""]
    for kind, ip, a in new_alerts:
        label = "Nouvelle IP non autorisée" if kind == "NEW_IP" else "Pic de volume"
        sts = ", ".join(f"{k}:{v}" for k, v in sorted(a["status"].items()))
        ua = max(a["user_agents"].items(), key=lambda kv: kv[1])[0] if a["user_agents"] else "?"
        lines.append(f"- **{label}** `{ip}` — {a['count']} req "
                     f"({fmt_ts(a['first'])} → {fmt_ts(a['last'])}), statuts [{sts}], "
                     f"UA `{ua}`, off-hours: {a['off_hours']}")
        with open(ALERT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(), "iso": now, "kind": kind, "ip": ip,
                "count": a["count"], "first": a["first"], "last": a["last"],
                "status": dict(a["status"]), "off_hours": a["off_hours"],
                "top_user_agent": ua,
            }) + "\n")
    lines.append("")
    lines.append("_Décision en vigueur : monitoring seulement, pas de rotation de clé. "
                 "Si l'IP est légitime, l'ajouter à l'allowlist du state._")
    alert_md = "\n".join(lines)
    # Persist the dashboard-ready markdown so the relay can post it verbatim.
    with open(LAST_ALERT_PATH, "w", encoding="utf-8") as f:
        f.write(alert_md + "\n")
    print(alert_md)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""nb-coder model matrix — run the same grain across several models and line the results up.

WHY THIS EXISTS
    The harness takes `--agent` and `--verifier-agent`; what it did not have is a way to
    answer "which hub-served model should build this grain?" without hand-running the driver
    N times and hand-copying numbers out of N traces. This runner is that layer, and nothing
    more: it never decides, never merges, never opens a PR on its own.

WHAT IT MEASURES (mechanical, per model)
    verdict · per-stage seconds · total seconds · number of model calls and how many failed ·
    which model actually served each call (`model_used`, the sk-agent envelope's own proof) ·
    execution cells ok/total · built bytes and `changed` · structure ok · gates · verify
    verdict. Token counts are deliberately NOT invented here: sk-agent's usage log carries no
    tokens (ts/tool/ok/dur_s/pid/agent/model only, sk_agent.py `log_usage`). Consumption is
    read from the proxy captures over the run window, not guessed by the runner.

DESIGN NOTES THAT COST A MEASUREMENT TO LEARN
    * `--out-dir` is ALWAYS resolved to an absolute path before it reaches the driver. The
      papermill MCP server is spawned with `cwd=PM_CWD`, so a relative out-dir makes stage 2
      execute a notebook path that does not exist from where the server stands — measured
      16/11 on CoursIA#26804: build fine, then 11/11 cells "Notebook file not found",
      verdict `built-execution-failed`. Absolute here, once, for every model.
    * Each model gets its OWN out-dir and its OWN worktree. Two models sharing a worktree
      would edit the same checkout and the second would read the first's leftovers.
    * Default `--max-stage 2`: a sweep is a comparison, not a delivery. Stage 5 writes to
      GitHub (branch, commit, push, PR) and is opt-in per run with `--max-stage 5`.
    * The runner reports what the traces say. It does not rank, score, or pick a winner —
      a model that fails structurally and a model that fails on a timeout are not the same
      fact, and only the operator reading the table knows which one the grain needed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "nb_coder_driver.py"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(agent: str) -> str:
    """A filesystem-safe directory name for an agent id (never a path fragment of it)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", agent).strip("-") or "agent"


def run_one(agent: str, model: str, args, out_root: Path) -> dict:
    """Run the driver once for one (agent, model) pair and read back what the trace says.

    `agent` carries the PROMPT (the notebook-builder conventions); `model` is what actually
    serves it. Keeping the prompt fixed across rows is the whole point of the matrix: vary one
    thing, or the table compares prompts and calls them models.
    """
    label = f"{agent}@{model}" if model else agent
    out_dir = (out_root / slug(label)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(DRIVER),
           "--issue", str(args.issue),
           "--notebook", args.notebook,
           "--repo", args.repo,
           "--agent", agent,
           "--verifier-agent", args.verifier_agent,
           "--max-stage", str(args.max_stage),
           "--max-tokens", str(args.max_tokens),
           "--timeout", str(args.timeout),
           "--verify-timeout", str(args.verify_timeout),
           "--out-dir", str(out_dir),
           "--worktree", str(out_dir / "wt"),
           "--gate-mode", args.gate_mode,
           "--exec-mode", args.exec_mode,
           "--write-mode", args.write_mode,
           "--fresh-worktree"]
    if args.lane:
        cmd += ["--lane", args.lane]
    if args.conventions:
        cmd += ["--conventions", args.conventions]
    if model:
        cmd += ["--model-override", model]
    row = {"agent": agent, "model": model or None, "label": label, "started": utcnow(),
           "out_dir": str(out_dir), "cmd": cmd if args.dry else None}
    if args.dry:
        row["verdict"] = "dry:not-run"
        return row
    t0 = time.time()
    log = out_dir / "driver.log"
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                           cwd=str(HERE.parents[3]), env=os.environ.copy())
    row["exit_code"] = p.returncode
    row["wall_s"] = round(time.time() - t0, 1)
    trace = out_dir / f"issue-{args.issue}.json"
    if not trace.is_file():
        row["verdict"] = f"no-trace (exit {p.returncode}; see {log})"
        return row
    rec = json.loads(trace.read_text(encoding="utf-8"))
    calls = rec.get("calls") or []
    row.update({
        "verdict": rec.get("verdict"),
        "stage0_s": rec.get("stage0_s"), "stage1_s": rec.get("stage1_s"),
        "stage2_s": rec.get("stage2_s"), "stage4_s": rec.get("stage4_s"),
        "stage5_s": rec.get("stage5_s"),
        "calls": len(calls),
        "calls_failed": sum(1 for c in calls if c.get("error")),
        "calls_retry": sum(1 for c in calls if str(c.get("stage", "")).endswith("-retry")),
        "model_used": sorted({c.get("model_used") for c in calls if c.get("model_used")}),
        "agent_used": sorted({c.get("agent_used") for c in calls if c.get("agent_used")}),
        "response_chars": sum(int(c.get("response_chars") or 0) for c in calls),
        "build_bytes": (rec.get("built_notebook") or {}).get("bytes"),
        "build_changed": (rec.get("built_notebook") or {}).get("changed"),
        "structure_ok": (rec.get("structure") or {}).get("ok"),
        "gate": (rec.get("gate") or {}).get("verdict"),
        "verify": (rec.get("verify") or {}).get("verdict"),
        "pr": (rec.get("pr") or {}).get("number"),
        "crash": (rec.get("crash") or {}).get("message"),
    })
    ex = rec.get("execution") or []
    row["exec_ok"] = sum(1 for e in ex if e.get("ok"))
    row["exec_n"] = len(ex)
    # The first failing cell's status is the operator-readable cause, not the verdict code.
    bad = next((e for e in ex if not e.get("ok")), None)
    if bad:
        row["exec_fail"] = {"cell": bad.get("cell"),
                            "status": str(bad.get("status"))[:200]}
    return row


def money_rows(rows: list[dict]) -> list[str]:
    """A markdown table an operator can read at a glance — one line per model."""
    head = ("| modèle | verdict | s0 | s1 | s2 | s4 | s5 | mur | appels | échecs | exéc | "
            "octets | struct | gate | verify | PR |")
    sep = "|" + "---|" * 17
    out = [head, sep]
    for r in rows:
        def s(k):
            v = r.get(k)
            return f"{v:g}" if isinstance(v, (int, float)) else ("" if v is None else str(v))
        out.append("| " + " | ".join([
            r.get("label") or r["agent"], s("verdict"), s("stage0_s"), s("stage1_s"), s("stage2_s"),
            s("stage4_s"), s("stage5_s"), s("wall_s"),
            f"{r.get('calls', '')}" + (f" (+{r['calls_retry']}r)" if r.get("calls_retry") else ""),
            s("calls_failed"),
            f"{r.get('exec_ok', '')}/{r.get('exec_n', '')}" if r.get("exec_n") else "",
            s("build_bytes"), s("structure_ok"), s("gate"), s("verify"), s("pr"),
        ]) + " |")
    return out


def main() -> int:
    # Console encoding: the table carries accents and the em dash; cp1252 renders them as '?'
    # and the operator reads a mangled header (measured 16/11 on the first dry run).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--notebook", required=True, help="repo-relative target notebook")
    ap.add_argument("--repo", required=True, help="CoursIA checkout (claim guard + worktree source)")
    ap.add_argument("--agents", required=True,
                    help="comma-separated `agent[@model]` entries, one build each. Bare agent = its own "
                         "model; `@model` holds the agent's prompt and serves another model — "
                         "hub ids glm-5.3 / glm-5.3-flash / swift-1.5-27b / frognano-4b, "
                         "sidecar ids nb-minimax / nb-luna / nb-haiku. "
                         "e.g. notebook-coder-minimax,notebook-coder-minimax@glm-5.3")
    ap.add_argument("--verifier-agent", default="analyst-fast")
    ap.add_argument("--max-stage", type=int, choices=[0, 1, 2, 3, 4, 5], default=2,
                    help="default 2 (build+exec): a sweep compares, it does not deliver. "
                         "5 writes to GitHub and must be asked for explicitly")
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--verify-timeout", type=int, default=900)
    ap.add_argument("--gate-mode", choices=["warn", "block", "off"], default="off",
                    help="off by default: a sweep reports, the gates belong to a delivery run")
    ap.add_argument("--exec-mode", choices=["auto", "all", "plan"], default="auto")
    ap.add_argument("--write-mode", choices=["json", "mcp"], default="json")
    ap.add_argument("--lane", default="")
    ap.add_argument("--conventions", default="")
    ap.add_argument("--out-root", default="")
    ap.add_argument("--dry", action="store_true", help="print each driver command, run nothing")
    args = ap.parse_args()

    out_root = Path(args.out_root or (HERE.parents[3] / ".tmp/nbcoder-matrix")).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    # `agent`, or `agent@model` to hold that agent's prompt and serve another model.
    pairs: list[tuple[str, str]] = []
    for piece in args.agents.split(","):
        piece = piece.strip()
        if not piece:
            continue
        agent, _, model = piece.partition("@")
        pairs.append((agent.strip(), model.strip()))
    if not pairs:
        ap.error("--agents is empty")

    print(f"# nb-coder matrix — issue {args.issue} — {len(pairs)} modèle(s) — "
          f"max-stage {args.max_stage} — {utcnow()}")
    print(f"# carnet : {args.notebook}")
    print(f"# sorties : {out_root}")
    rows = []
    for agent, model in pairs:
        print(f"\n== {agent}{'@' + model if model else ''} ==", flush=True)
        row = run_one(agent, model, args, out_root)
        rows.append(row)
        if not args.dry:
            print(f"   verdict={row.get('verdict')} wall={row.get('wall_s')}s "
                  f"calls={row.get('calls')}", flush=True)
    if args.dry:
        for r in rows:
            print(" ".join(r["cmd"]))
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"issue": args.issue, "notebook": args.notebook, "started": utcnow(),
               "max_stage": args.max_stage, "verifier_agent": args.verifier_agent,
               "max_tokens": args.max_tokens, "rows": rows}
    report = out_root / f"matrix-{args.issue}-{stamp}.json"
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    for line in money_rows(rows):
        print(line)
    print(f"\nRapport JSON : {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""nb-coder driver — stages 0-2 of the issue -> notebook -> PR harness (jsboige/vllm#431).

Stage 0 CLAIM : check_lane_claim.py on the CoursIA checkout (read), optional [CLAIMED] comment.
Stage 1 PLAN  : sk-agent model turn -> cell plan JSON (kernel, edits, expected outputs).
Stage 2 BUILD : the model writes cells via its papermill tools; the HARNESS runs every
                planned cell with execute_on_kernel on the series kernel and decides
                success alone, from the real outputs (never from the model's claims).

Dry by default: no branch, no commit, no push, no PR. The spec's stages 3-5 (gates,
verify, PR) are deliberately absent from this file for now (dispatch 14/11 15:34Z asks 0-2).

Run with the sk-agent venv python (it carries the ``mcp`` client package):
    d:/roo-extensions/mcps/internal/servers/sk-agent/venv/Scripts/python.exe \
        nb_coder_driver.py --issue 20250 --notebook IIT/ICT-Series/ICT-40b-...ipynb \
        --out-dir d:/vllm/.tmp/nbcoder --worktree d:/vllm/.tmp/nbcoder/wt-20250
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
VLLM_ROOT = HERE.parents[3]
SK_DIR = Path("d:/roo-extensions/mcps/internal/servers/sk-agent")
SK_PY = SK_DIR / "venv/Scripts/python.exe"
SK_CONFIG = SK_DIR / "sk_agent_config.json"
PM_PY = Path(r"C:\Users\MYIA\miniconda3\envs\mcp-jupyter\python.exe")
PM_CWD = Path(r"D:\roo-extensions\mcps\internal\servers\jupyter-papermill-mcp-server")
GATE = VLLM_ROOT / "myia_vllm/scripts/adoption/swift_capacity_gate.py"
LANE = "myia-ai-01:nb-coder"

# requirement #3: canonical kernel per series, version read from the neighbours on main
KERNEL_MAP = {
    "Audio": "coursia-genai-audio",
    "GameTheory": "python3",
    "IIT": "python3",
    "Complexity": "python3",
    "Image": "python3",
    "Video": "python3",
}
DEFAULT_KERNEL = "python3"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(x) -> str:
    return "".join(x) if isinstance(x, list) else (x or "")


def gh(args: list[str], token: str | None = None, timeout: int = 60) -> tuple[int, str]:
    """REST-only GitHub calls (GraphQL bucket is fleet-shared)."""
    env = {**os.environ}
    if token:
        env["GH_TOKEN"] = token
    p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env)
    return p.returncode, (p.stdout or p.stderr).strip()


def app_token(repo_dir: Path) -> str | None:
    """Requirement #5: 1-hour installation token, never persisted, never in the model context."""
    app_id = os.environ.get("NBCODER_GH_APP_ID")
    key = os.environ.get("NBCODER_GH_KEY")
    if not app_id or not key:
        return None
    script = repo_dir / "scripts/secrets/github_app_token.py"
    if not script.is_file():
        return None
    p = subprocess.run([sys.executable, str(script), "--app-id", app_id, "--key", key,
                        "--repo", "jsboige/CoursIA", "--quiet"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    tok = (p.stdout or "").strip().splitlines()[-1] if p.returncode == 0 else ""
    return tok or None


# ---------------------------------------------------------------- stage 0
def fetch_issue(slug: str, n: int, token: str | None) -> dict:
    rc, out = gh(["api", f"repos/{slug}/issues/{n}",
                  "--jq", '{"title":.title,"state":.state,"body":(.body // ""),"labels":[.labels[].name]}'],
                 token)
    if rc != 0:
        raise RuntimeError(f"issue fetch failed rc={rc}: {out[:300]}")
    issue = json.loads(out)
    rc, out = gh(["api", f"repos/{slug}/issues/{n}/comments", "--paginate",
                  "--jq", r'.[] | "--- \(.user.login) \(.created_at)\n\(.body)"'], token)
    issue["comments"] = out if rc == 0 else f"(comments fetch failed rc={rc})"
    return issue


def check_claim(repo: Path, n: int, lane: str) -> dict:
    script = repo / "scripts/check_lane_claim.py"
    if not script.is_file():
        return {"ok": None, "error": "check_lane_claim.py absent"}
    p = subprocess.run([sys.executable, str(script), str(n), "--lane", lane],
                       cwd=repo, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    return {"ok": p.returncode == 0, "rc": p.returncode,
            "out": (p.stdout or p.stderr).strip()[:2000]}


def post_claim(repo: Path, n: int, lane: str, intention: str) -> dict:
    script = repo / "scripts/check_lane_claim.py"
    p = subprocess.run([sys.executable, str(script), str(n), "--lane", lane,
                        "--claim", intention], cwd=repo, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return {"rc": p.returncode, "out": (p.stdout or p.stderr).strip()[:1000]}


def prepare_worktree(repo: Path, dest: Path, fresh: bool) -> dict:
    """Detached worktree of origin/main: the dirty checkout is never read or touched."""
    if dest.exists() and (dest / ".git").exists() and not fresh:
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        return {"path": str(dest), "reused": True, "head": head}
    subprocess.run(["git", "-C", str(repo), "fetch", "origin", "main"],
                   capture_output=True, text=True, timeout=300)
    if dest.exists():
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(dest)],
                       capture_output=True, text=True)
    p = subprocess.run(["git", "-C", str(repo), "worktree", "add", str(dest), "--detach", "origin/main"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return {"path": str(dest), "reused": False, "head": head,
            "ok": p.returncode == 0, "err": (p.stderr or "").strip()[:500]}


def gate_call(mode: str) -> dict:
    """Requirement: capacity gate before every notebook. warn = non-blocking (24 h window)."""
    p = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    try:
        verdict = json.loads((p.stdout or "").strip().splitlines()[-1])
    except Exception:
        verdict = {"verdict": "unknown", "raw": (p.stdout or p.stderr)[:500]}
    verdict["exit"] = p.returncode
    verdict["mode"] = mode
    verdict["blocking_refusal"] = mode == "block" and p.returncode != 0
    return verdict


# ---------------------------------------------------------------- notebook view
def series_kernel(repo: Path, rel: str) -> dict:
    """Kernel name from the series map + canonical python version from the neighbours."""
    d = Path(rel).parent
    segs = rel.replace("\\", "/").split("/")[:-1]
    name = next((KERNEL_MAP[s] for s in segs if s in KERNEL_MAP), DEFAULT_KERNEL)
    versions = {}
    for sib in sorted((repo / d).glob("*.ipynb")):
        if sib.name == Path(rel).name:
            continue
        try:
            meta = json.loads(sib.read_text(encoding="utf-8")).get("metadata", {})
            v = (meta.get("language_info") or {}).get("version")
            if v:
                versions[v] = versions.get(v, 0) + 1
        except Exception:
            continue
    canon = max(versions, key=versions.get) if versions else None
    return {"kernel_name": name, "canonical_version": canon,
            "neighbour_versions": versions}


def build_view(nb_path: Path, max_cells: int = 200) -> str:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    parts = []
    for i, cell in enumerate(nb.get("cells", [])[:max_cells]):
        ctype, src = cell.get("cell_type"), _text(cell.get("source"))
        parts.append(f"=== cellule {i} | {ctype} ===\n{src}")
    return "\n\n".join(parts)


def series_context(repo: Path, rel: str, max_headers: int = 10) -> str:
    d = str(Path(rel).parent).replace("\\", "/")
    names = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", f"{d}/*.ipynb"],
                           capture_output=True, text=True, encoding="utf-8").stdout.split("\0")
    names = sorted(n for n in names if n and "/" not in n[len(d) + 1:])
    me = rel.replace("\\", "/")
    lines = [f"Série {d} — {len(names)} carnets ; celui-ci en position "
             f"{names.index(me) + 1 if me in names else '?'}."]
    for n in names:
        if n >= me:
            break
        try:
            nb = json.loads((repo / n).read_text(encoding="utf-8"))
        except Exception:
            continue
        heads = [ln.strip() for c in nb.get("cells", []) if c.get("cell_type") == "markdown"
                 for ln in _text(c.get("source")).splitlines() if ln.startswith("#")]
        lines.append(f"- {Path(n).name} : " + " | ".join(heads[:max_headers]))
    return "\n".join(lines)


def parse_json_block(text: str) -> dict | None:
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    for cand in reversed(m or [text]):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- prompts
def plan_prompt(issue_n: int, issue: dict, rel: str, kernel: dict, ctx: str, view: str) -> str:
    return (
        f"MODE CONSTRUCTION — tu n'audites pas, tu prépares une modification de carnet pour l'issue "
        f"jsboige/CoursIA#{issue_n}.\n\n"
        f"## Issue\nTITRE : {issue['title']}\n\nCORPS :\n{issue['body'][:6000]}\n\n"
        f"## Fil (extrait)\n{issue['comments'][-3000:]}\n\n"
        f"## Carnet cible : {rel} (branche origin/main)\n"
        f"Noyau canonique de la série : {kernel['kernel_name']} "
        f"(version des voisins : {kernel['canonical_version']} — {kernel['neighbour_versions']})\n\n"
        f"## Contexte de série\n{ctx}\n\n"
        f"## Carnet actuel\n{view[:20000]}\n\n"
        "Rends UNIQUEMENT un bloc ```json :\n"
        '{"plan":[{"cell":<index>,"geste":"edit|insert_after|delete","but":"..."}],'
        '"execute_cells":[<index des cellules code à ré-exécuter>],'
        '"expectations":["..."],"risques":["..."]}\n'
        "`execute_cells` vide si le geste est markdown seul."
    )


def build_prompt(scratch_nb: str, plan: dict, execute_ids: list) -> str:
    return (
        "TOUR 2 — écris le carnet. Tu disposes des outils papermill : `create_notebook` puis "
        "`add_cell`/`update_cell` (n'utilise JAMAIS les outils legacy : `execute_on_kernel` seul côté "
        "exécution, et c'est le harnais qui exécute, pas toi).\n\n"
        f"Chemin de travail ABSOLU à créer : {scratch_nb}\n"
        f"Plan validé : {json.dumps(plan, ensure_ascii=False)[:6000]}\n\n"
        "Écris l'intégralité du carnet visé (cells existantes pertinentes + modifications du plan), "
        "sources exactes, sans outputs. Puis rends UNIQUEMENT un bloc ```json :\n"
        '{"cells_written":<n>,"code_cell_indexes":[...],"notes":"..."}\n'
        f"Cellules que le harnais exécutera ensuite : {execute_ids or 'aucune'}."
    )


# ---------------------------------------------------------------- sk-agent / papermill calls
async def sk_call(session: ClientSession, args, prompt: str, conv: str | None) -> tuple[dict, float]:
    spec = {"extends": args.agent, "sampling": {"max_tokens": args.max_tokens, "temperature": 0.4}}
    payload = {"prompt": prompt, "agent": args.agent, "timeout": args.timeout,
               "include_steps": True, "agent_spec": json.dumps(spec)}
    if conv:
        payload["conversation_id"] = conv
    t0 = time.time()
    try:
        res = await session.call_tool("call_agent", payload,
                                      read_timeout_seconds=timedelta(seconds=args.timeout + 120))
        raw = "\n".join(getattr(c, "text", "") for c in res.content)
    except Exception as exc:
        raw = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    try:
        env = json.loads(raw)
    except Exception:
        env = {"response": raw}
    return env, round(time.time() - t0, 1)


async def pm_call(session: ClientSession, tool: str, payload: dict) -> dict:
    try:
        res = await session.call_tool(tool, payload, read_timeout_seconds=timedelta(seconds=300))
        raw = "\n".join(getattr(c, "text", "") for c in res.content)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


async def execute_cells(pm: ClientSession, nb_path: Path, kernel_id: str,
                        indexes: list[int]) -> list[dict]:
    """The harness owns execution and the verdict: real outputs, never the model's word."""
    results = []
    for idx in indexes:
        r = await pm_call(pm, "execute_on_kernel", {"kernel_id": kernel_id, "mode": "notebook_cell",
                                                    "path": str(nb_path), "cell_index": idx,
                                                    "timeout": 300})
        status = r.get("status") or r.get("error") or "?"
        outs = r.get("outputs") or []
        err_txt = " ".join(str(o.get("text") or o.get("ename") or "") for o in outs
                           if isinstance(o, dict) and o.get("output_type") == "error")
        results.append({"cell": idx, "status": status, "ok": status == "ok" and not err_txt,
                        "elapsed_s": r.get("execution_time") or r.get("elapsed_s"),
                        "outputs_tail": str(outs)[-800:], "error": err_txt[:500] or None})
    return results


async def start_kernel(pm: ClientSession, kernel_name: str) -> str | None:
    r = await pm_call(pm, "manage_kernel", {"action": "start", "kernel_name": kernel_name})
    return r.get("kernel_id")


# ---------------------------------------------------------------- main flow
async def run(args) -> dict:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo = Path(args.repo)
    rec = {"issue": args.issue, "notebook": args.notebook, "started": utcnow(),
           "lane": LANE, "dry": True, "stages": {}, "calls": []}
    token = app_token(repo)

    # ---- stage 0
    t0 = time.time()
    rec["stages"]["claim_check"] = check_claim(repo, args.issue, LANE)
    if rec["stages"]["claim_check"]["rc"] == 1:
        rec["verdict"] = "refused-claim-held-by-another-lane"
        return rec
    issue = fetch_issue("jsboige/CoursIA", args.issue, token)
    rec["stages"]["issue"] = {"title": issue["title"], "state": issue["state"],
                              "labels": issue["labels"], "body_chars": len(issue["body"])}
    if args.claim:
        rec["stages"]["claim_posted"] = post_claim(repo, args.issue, LANE, args.intention)
    wt = prepare_worktree(repo, Path(args.worktree), args.fresh_worktree)
    rec["stages"]["worktree"] = wt
    rec["stage0_s"] = round(time.time() - t0, 1)
    if args.max_stage < 1:
        rec["verdict"] = "stage0-only"
        return rec

    src_nb = Path(wt["path"]) / args.notebook
    if not src_nb.is_file():
        rec["verdict"] = f"notebook-not-found:{src_nb}"
        return rec
    kernel = series_kernel(Path(wt["path"]), args.notebook)
    rec["kernel"] = kernel
    gate = gate_call(args.gate_mode)
    rec["gate"] = gate
    if gate["blocking_refusal"]:
        rec["verdict"] = "deferred-by-capacity-gate"
        return rec

    scratch_nb = (out_dir / f"nb_{args.issue}_built.ipynb").as_posix()
    sk_params = StdioServerParameters(command=str(SK_PY), args=[str(SK_DIR / "sk_agent.py")],
                                      env={**os.environ, "SK_AGENT_CONFIG": str(SK_CONFIG)},
                                      cwd=str(out_dir))
    pm_params = StdioServerParameters(command=str(PM_PY), args=["-u", "-m", "papermill_mcp.main"],
                                      env={**os.environ, "PYTHONUNBUFFERED": "1"},
                                      cwd=str(PM_CWD))
    async with stdio_client(sk_params) as (r1, w1), stdio_client(pm_params) as (r2, w2):
        async with ClientSession(r1, w1) as sk, ClientSession(r2, w2) as pm:
            await sk.initialize()
            await pm.initialize()
            # ---- stage 1 PLAN
            t1 = time.time()
            prompt = plan_prompt(args.issue, issue, args.notebook, kernel,
                                 series_context(Path(wt["path"]), args.notebook),
                                 build_view(src_nb))
            env, dt = await sk_call(sk, args, prompt, None)
            conv = env.get("conversation_id")
            rec["calls"].append({"stage": "1-plan", "elapsed_s": dt, "error": env.get("error"),
                                 "response_chars": len(env.get("response") or "")})
            plan = parse_json_block(env.get("response") or "")
            rec["plan"] = plan
            rec["stage1_s"] = round(time.time() - t1, 1)
            if args.max_stage < 2:
                rec["verdict"] = "stage1-only" if plan else "stage1-unparsed"
                return rec
            if not plan:
                rec["verdict"] = "stage1-unparsed"
                return rec
            exec_idx = plan.get("execute_cells") or []

            # ---- stage 2 BUILD (model writes via its papermill tools, same conversation)
            t2 = time.time()
            env2, dt2 = await sk_call(sk, args, build_prompt(scratch_nb, plan, exec_idx), conv)
            rec["calls"].append({"stage": "2-build", "elapsed_s": dt2, "error": env2.get("error"),
                                 "response_chars": len(env2.get("response") or "")})
            built = parse_json_block(env2.get("response") or "")
            rec["build_model_answer"] = {"parsed": built, "chars": len(env2.get("response") or "")}
            rec["stage2_s"] = round(time.time() - t2, 1)

            # ---- harness: verify the notebook exists, execute the planned cells, judge
            t3 = time.time()
            exists = Path(scratch_nb).is_file()
            rec["built_notebook"] = {"path": scratch_nb, "exists": exists,
                                     "bytes": Path(scratch_nb).stat().st_size if exists else 0}
            if exists:
                kid = await start_kernel(pm, args.kernel_override or kernel["kernel_name"])
                rec["kernel_id"] = kid
                if kid and exec_idx:
                    rec["execution"] = await execute_cells(pm, Path(scratch_nb), kid,
                                                           [int(i) for i in exec_idx])
                elif kid:
                    rec["execution"] = []
                rec["verdict"] = ("built-executed-ok"
                                  if all(e["ok"] for e in rec.get("execution") or [{}])
                                  else "built-execution-failed")
            else:
                rec["verdict"] = "build-no-notebook"
            rec["stage3_s"] = round(time.time() - t3, 1)
    rec["finished"] = utcnow()
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--issue", type=int, required=True, help="CoursIA issue number")
    ap.add_argument("--notebook", required=True, help="repo-relative target notebook")
    ap.add_argument("--repo", default="d:/CoursIA", help="CoursIA checkout (claim guard + worktree source)")
    ap.add_argument("--worktree", default=str(VLLM_ROOT / ".tmp/nbcoder/wt"))
    ap.add_argument("--fresh-worktree", action="store_true")
    ap.add_argument("--out-dir", default=str(VLLM_ROOT / ".tmp/nbcoder"))
    ap.add_argument("--agent", default="notebook-auditor", help="sk-agent agent id")
    ap.add_argument("--intention", default="volet vllm du harnais nb-coder (passe a blanc)")
    ap.add_argument("--claim", action="store_true", help="post the [CLAIMED] comment (off in dry)")
    ap.add_argument("--gate-mode", choices=["warn", "block"], default="warn")
    ap.add_argument("--kernel-override", default=None)
    ap.add_argument("--max-stage", type=int, choices=[0, 1, 2], default=2)
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--max-tokens", type=int, default=16384)
    args = ap.parse_args()
    rec = asyncio.run(run(args))
    out = Path(args.out_dir) / f"issue-{args.issue}.json"
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(Path(args.out_dir) / "ledger.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({k: rec.get(k) for k in
                             ("issue", "notebook", "started", "finished", "verdict", "lane")}
                            | {"stage0_s": rec.get("stage0_s"), "stage1_s": rec.get("stage1_s"),
                               "stage2_s": rec.get("stage2_s"),
                               "gate": (rec.get("gate") or {}).get("verdict"),
                               "calls": len(rec.get("calls") or [])}, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec.get(k) for k in
                      ("issue", "verdict", "stage0_s", "stage1_s", "stage2_s", "kernel_id")},
                     ensure_ascii=False))
    return 0 if rec.get("verdict", "").endswith(("ok", "stage0-only", "stage1-only")) else 1


if __name__ == "__main__":
    sys.exit(main())
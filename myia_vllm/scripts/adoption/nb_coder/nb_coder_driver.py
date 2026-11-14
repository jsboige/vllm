#!/usr/bin/env python3
"""nb-coder driver — stages 0-2 of the issue -> notebook -> PR harness (jsboige/vllm#431).

Stage 0 CLAIM : check_lane_claim.py on the CoursIA checkout (read), optional [CLAIMED] comment.
Stage 1 PLAN  : sk-agent model turn -> cell plan JSON (kernel, edits, expected outputs).
Stage 2 BUILD : the HARNESS copies the source notebook (outputs preserved) and the model
                edits ONLY the planned cells on that copy (update_cell/add_cell/remove_cell);
                the harness then proves the result is a minimal edit (structure diff) and runs
                every planned cell with execute_on_kernel, deciding success alone.

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
import hashlib
import json
import os
import re
import shutil
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


def engine_tokens() -> dict:
    """Engine-side prompt/generation counters, for a per-pass token delta (CR CoursIA#26534)."""
    try:
        p = subprocess.run(["curl", "-s", "--max-time", "5", "http://localhost:5002/metrics"],
                           capture_output=True, text=True, timeout=10)
        vals = {}
        for ln in (p.stdout or "").splitlines():
            for key in ("prompt_tokens_total", "generation_tokens_total"):
                if ln.startswith(f"vllm:{key}"):
                    vals[key] = float(ln.rsplit(" ", 1)[-1])
        return vals
    except Exception:
        return {}


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


def build_view(nb_path: Path, max_chars: int = 120_000) -> str:
    """Whole-notebook view. Overflow is DECLARED, never silent: a cut view makes the model
    plan against a notebook whose footer it cannot see (measured 14/11: 37-cell notebook,
    view cut at 20 000 chars -> plan said "insert a footer after cell 19", 17 cells lost)."""
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    cells = nb.get("cells", [])
    parts, used, shown = [], 0, 0
    for i, cell in enumerate(cells):
        block = f"=== cellule {i} | {cell.get('cell_type')} ===\n{_text(cell.get('source'))}"
        if used + len(block) > max_chars and shown:
            break
        parts.append(block)
        used += len(block)
        shown += 1
    head = f"[Vue : {len(cells)} cellules au total ; {shown} affichées en entier.]"
    if shown < len(cells):
        rest = [f"ATTENTION — vue TRONQUÉE : les cellules {shown}..{len(cells) - 1} ne sont pas "
                "affichées ; le carnet CONTINUE après la dernière cellule montrée "
                "(ce n'est pas le pied de carnet). Index du reste :"]
        for j in range(shown, len(cells)):
            first = next((ln.strip() for ln in _text(cells[j].get("source")).splitlines()
                          if ln.strip()), "")
            rest.append(f"- {j} | {cells[j].get('cell_type')} | {first[:120]}")
        rest.append("Si ton plan touche une cellule non affichée, dis-le explicitement et "
                    "n'invente pas son contenu.")
        parts.append("\n".join(rest))
    return head + "\n\n" + "\n\n".join(parts)


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
def _cut(text: str, limit: int, label: str, tail: bool = False) -> str:
    """Cut with a DECLARED marker: a silent cut makes the model invent what it cannot see
    (measured 14/11: Epic body 20 245 chars cut at 6 000 -> the canonical footer wording,
    which lives at char ~16 700, was never shown and the plan invented a `## Provenance`)."""
    text = text or ""
    if len(text) <= limit:
        return text
    body = text[-limit:] if tail else text[:limit]
    where = f"les {limit} derniers" if tail else f"les {limit} premiers"
    return (f"{body}\n\n[ATTENTION — {label} TRONQUÉ : {len(text)} caractères au total, "
            f"{where} seulement sont affichés.]")


def read_conventions(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8").strip() if p.is_file() else ""
    except Exception:
        return ""


def plan_prompt(issue_n: int, issue: dict, rel: str, kernel: dict, ctx: str, view: str,
                conventions: str = "") -> str:
    return (
        f"MODE CONSTRUCTION — tu n'audites pas, tu prépares une modification de carnet pour l'issue "
        f"jsboige/CoursIA#{issue_n}.\n\n"
        f"## Issue\nTITRE : {issue['title']}\n\n"
        f"CORPS :\n{_cut(issue['body'], 30000, 'corps de l issue')}\n\n"
        f"## Fil (extrait récent)\n{_cut(issue['comments'], 8000, 'fil de l issue', tail=True)}\n\n"
        + (f"## Conventions de livraison (imposées)\n{conventions}\n\n" if conventions else "")
        + f"## Carnet cible : {rel} (branche origin/main)\n"
        f"Noyau canonique de la série : {kernel['kernel_name']} "
        f"(version des voisins : {kernel['canonical_version']} — {kernel['neighbour_versions']})\n\n"
        f"## Contexte de série\n{ctx}\n\n"
        f"## Carnet actuel\n{view}\n\n"
        "Rends UNIQUEMENT un bloc ```json :\n"
        '{"plan":[{"cell":<index>,"geste":"edit|insert_after|delete",'
        '"to":"<code|markdown — uniquement si le geste convertit le type de la cellule>",'
        '"but":"..."}],'
        '"execute_cells":[<index des cellules code concernées, carnet d ORIGINE>],'
        '"expectations":["..."],"risques":["..."]}\n'
        "`execute_cells` vide si le geste est markdown seul. Tout index (`cell`, `after`, "
        "`execute_cells`) est un index du carnet d'ORIGINE ; le harnais remappe après "
        "suppressions/insertions."
    )


def build_prompt(scratch_nb: str, plan: dict, execute_ids: list, src_cells: list,
                 n_cells: int, conventions: str = "") -> str:
    """Edit prompt: the harness already made the copy, the model only applies the plan.

    Measured 14/11 (attempt 2): asking for "the entirety of the notebook, exact sources, no
    outputs" made the model re-emit what it had seen and drop everything past the view."""
    current = []
    for p in plan.get("plan") or []:
        if p.get("geste") != "edit":
            continue
        try:
            i = int(p["cell"])
            current.append(f"=== cellule {i} — source ACTUELLE (à remplacer intégralement) ===\n"
                           f"{_text(src_cells[i].get('source'))}")
        except Exception:
            continue
    return (
        "TOUR 2 — applique le plan sur le carnet de travail. "
        f"Le fichier EXISTE DÉJÀ à {scratch_nb} : c'est une copie exacte du carnet cible "
        f"({n_cells} cellules, outputs inclus). N'utilise PAS create_notebook — il écraserait "
        "la copie.\n\n"
        "Outils papermill autorisés, rien d'autre :\n"
        "- `update_cell` {path, index, source} pour un geste `edit` ;\n"
        "- `add_cell` {path, cell_type, source, index} pour un geste `insert_after` "
        "(index = position d'insertion 0-based = cellule_ancre + 1) ;\n"
        "- `remove_cell` {path, index} pour un geste `delete`.\n"
        "N'ÉCRIS QUE les cellules du plan ; toute autre cellule doit rester intacte — le harnais "
        "compare le résultat à la source et rejette tout écart (nombre de cellules, cellules non "
        "prévues modifiées, outputs perdus).\n\n"
        f"Plan validé : {json.dumps(plan, ensure_ascii=False)[:6000]}\n\n"
        + (f"Conventions de livraison (imposées) :\n{conventions}\n\n" if conventions else "")
        + ("\n\n".join(current) + "\n\n" if current else "")
        + "Puis rends UNIQUEMENT un bloc ```json :\n"
        '{"cells_written":<n>,"gestures_done":[{"cell":<index>,"tool":"update_cell|add_cell|remove_cell"}],'
        '"notes":"..."}\n'
        f"Cellules que le harnais exécutera ensuite : {execute_ids or 'aucune'}."
    )


# ---------------------------------------------------------------- structural verdict
def build_json_prompt(plan: dict, execute_ids: list, src_cells: list, n_cells: int,
                      conventions: str = "") -> str:
    """JSON write mode: the model returns the new cell sources, the harness applies them with
    ONE write. Measured 14/11: three parallel MCP write calls -> two silent lost updates."""
    current = []
    for p in plan.get("plan") or []:
        if p.get("geste") != "edit":
            continue
        try:
            i = int(p["cell"])
            current.append(f"=== cellule {i} — source ACTUELLE (à remplacer intégralement) ===\n"
                           f"{_text(src_cells[i].get('source'))}")
        except Exception:
            continue
    return (
        "TOUR 2 — rends les cellules à écrire. Le harnais les appliquera lui-même sur une copie "
        f"exacte du carnet ({n_cells} cellules, outputs inclus) ; tu n'écris aucun fichier et tu "
        "n'appelles aucun outil d'écriture.\n\n"
        f"Plan validé : {json.dumps(plan, ensure_ascii=False)[:6000]}\n\n"
        + (f"Conventions de livraison (imposées) :\n{conventions}\n\n" if conventions else "")
        + ("\n\n".join(current) + "\n\n" if current else "")
        + "Rends UNIQUEMENT un bloc ```json :\n"
        '{"edits":[{"cell":<index>,"source":"<source COMPLET de remplacement>",'
        '"cell_type":"<code|markdown — UNIQUEMENT si le plan déclare une conversion de type>"}],'
        '"deletes":[<index du carnet d ORIGINE>...],'
        '"inserts":[{"after":<index>,"cell_type":"markdown|code","source":"<source complet>"}],'
        '"notes":"..."}\n'
        "Règles : source COMPLET (pas un diff), aucune cellule hors plan, `after` = index de "
        "l'ancre dans le carnet d'origine, une seule entrée par geste du plan ; `deletes` "
        "reprend les gestes delete du plan (tableau vide s'il n'y en a pas)."
    )


def apply_edits(nb_path: Path, payload: dict) -> dict:
    """Deterministic applier: one read-modify-write, indexes taken on the ORIGINAL notebook.

    Order (must stay consistent with verify_structure's shift): edits on original indexes,
    then deletes (desc), then inserts (anchor desc, anchor = ORIGINAL index). A delete
    shifts every later cell by -1, so an insert anchored at `a` lands at
    a - #(deletes < a) + 1 in the post-delete array."""
    raw = nb_path.read_text(encoding="utf-8")
    nb = json.loads(raw)
    cells = nb["cells"]
    rep = {"roundtrip_ok": json.dumps(nb, ensure_ascii=False, indent=1) + "\n" == raw,
           "edits": [], "deletes": [], "inserts": [], "errors": []}
    for e in payload.get("edits") or []:
        try:
            i, new = int(e["cell"]), e["source"]
            if not 0 <= i < len(cells):
                raise IndexError(f"cell {i} hors bornes (0..{len(cells) - 1})")
            old = _text(cells[i].get("source"))
            cells[i]["source"] = new
            entry = {"cell": i, "changed": new != old, "chars": len(new)}
            if e.get("cell_type") in ("code", "markdown"):
                ct = e["cell_type"]
                if ct != cells[i].get("cell_type"):          # declared type conversion
                    entry["type"] = f"{cells[i].get('cell_type')}->{ct}"
                    cells[i]["cell_type"] = ct
                    if ct == "markdown":
                        cells[i].pop("execution_count", None)
                        cells[i].pop("outputs", None)
                    else:
                        cells[i]["execution_count"] = None
                        cells[i]["outputs"] = []
            rep["edits"].append(entry)
        except Exception as exc:
            rep["errors"].append(f"edit: {exc}")
    deletes = sorted({int(k) for k in payload.get("deletes") or []}, reverse=True)
    n_src = len(cells)
    for k in deletes:
        try:
            if not 0 <= k < len(cells):
                raise IndexError(f"delete {k} hors bornes (0..{n_src - 1})")
            cells.pop(k)                                     # desc: earlier indexes stay valid
            rep["deletes"].append(k)
        except Exception as exc:
            rep["errors"].append(f"delete: {exc}")
    taken = {c.get("id") for c in cells}
    for x in sorted(payload.get("inserts") or [],
                    key=lambda v: int(v.get("after", -1)), reverse=True):
        try:
            a, src = int(x["after"]), x["source"]
            below = sum(1 for k in rep["deletes"] if k < a)
            if not 0 <= a < n_src:
                raise IndexError(f"ancre {a} hors bornes")
            pos = a - below + 1
            if any(d == a for d in rep["deletes"]):
                raise ValueError(f"ancre {a} supprimée — ancre le prédécesseur")
            cid = hashlib.sha1((str(a) + src).encode("utf-8")).hexdigest()[:8]
            while cid in taken:
                cid = hashlib.sha1((cid + src).encode("utf-8")).hexdigest()[:8]
            taken.add(cid)
            ct = x.get("cell_type") or "markdown"
            new_cell = {"cell_type": ct, "id": cid, "metadata": {}, "source": src}
            if ct == "code":
                new_cell |= {"execution_count": None, "outputs": []}
            cells.insert(pos, new_cell)
            rep["inserts"].append({"after": a, "built_pos": pos, "type": ct,
                                   "chars": len(src), "id": cid})
        except Exception as exc:
            rep["errors"].append(f"insert: {exc}")
    nb_path.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rep["wrote"] = True
    return rep


def _cells(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8")).get("cells", [])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def verify_structure(src_path: Path, built_path: Path, plan: dict) -> dict:
    """Mechanical proof the deliverable is a MINIMAL EDIT of the source, not a rewrite.

    The first dry pass (14/11) produced a 21-cell notebook from a 37-cell source and the
    "file exists" verdict accepted it: that is the hole this closes."""
    src, built = _cells(src_path), _cells(built_path)
    gestures = plan.get("plan") or []
    edits = {int(p["cell"]) for p in gestures
             if p.get("geste") == "edit" and str(p.get("cell", "")).isdigit()}
    deletes = {int(p["cell"]) for p in gestures
               if p.get("geste") == "delete" and str(p.get("cell", "")).isdigit()}
    anchors = [int(p["cell"]) for p in gestures
               if p.get("geste") == "insert_after" and str(p.get("cell", "")).isdigit()]
    convert = {int(p["cell"]): p["to"] for p in gestures
               if p.get("geste") == "edit" and str(p.get("cell", "")).isdigit()
               and p.get("to") in ("code", "markdown")}
    s_src = [_text(c.get("source")) for c in src]
    s_b = [_text(c.get("source")) for c in built]

    def shift(i: int) -> int:
        return i + sum(1 for a in anchors if a < i) - sum(1 for k in deletes if k < i)

    d = {"src_cells": len(src), "built_cells": len(built),
         "edits": sorted(edits), "deletes": sorted(deletes), "inserts": len(anchors),
         "type_conversions": sorted(convert)}
    d["count_ok"] = len(built) == len(src) - len(deletes) + len(anchors)
    d["anchors_on_deleted"] = sorted(set(anchors) & deletes)

    untouched = [i for i in range(len(src)) if i not in edits | deletes]
    j, missing = 0, None
    for i in untouched:                      # verbatim, in order (index-agnostic)
        while j < len(s_b) and s_b[j] != s_src[i]:
            j += 1
        if j >= len(s_b):
            missing = i
            break
        j += 1
    d["untouched_ok"] = missing is None
    d["missing_cell"] = missing

    detail, edits_ok = [], True
    for i in sorted(edits):
        pos = shift(i)
        want_type = convert.get(i) or src[i].get("cell_type")
        detail.append({"cell": i, "built_pos": pos,
                       "type_ok": 0 <= pos < len(built)
                                  and built[pos].get("cell_type") == want_type,
                       "changed": 0 <= pos < len(s_b) and s_b[pos] != s_src[i]})
        edits_ok = edits_ok and detail[-1]["type_ok"] and detail[-1]["changed"]
    d["edits_detail"] = detail
    d["edits_ok"] = edits_ok

    lost = []
    for i in untouched:
        if src[i].get("cell_type") == "code" and (src[i].get("outputs") or []):
            pos = shift(i)
            if pos >= len(built) or not (built[pos].get("outputs") or []):
                lost.append(i)
    d["outputs_lost"] = lost
    d["outputs_ok"] = not lost

    # an insert_after must actually land right after its anchor: a Provenance block dropped in
    # the middle of a 37-cell notebook passes count/order checks but is not the intended footer
    ins_detail, ins_ok = [], True
    for a in anchors:
        pos_a = shift(a)
        nxt = pos_a + 1
        if a + 1 >= len(src):
            # insert after the LAST source cell: it must really be the tail of the notebook
            landed = nxt < len(built) and s_b[len(built) - 1] != s_src[len(src) - 1]
        else:
            landed = nxt < len(built) and s_b[nxt] != s_src[a + 1]
        ins_detail.append({"anchor": a, "built_pos": pos_a + 1, "landed": landed})
        ins_ok = ins_ok and landed
    d["inserts_detail"] = ins_detail
    d["inserts_ok"] = ins_ok
    d["ok"] = (all(d[k] for k in ("count_ok", "untouched_ok", "edits_ok", "outputs_ok", "inserts_ok"))
               and not d["anchors_on_deleted"])
    return d


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


# empty answers: nbaudit pilots 2/11 and 1/11 — one retry asking for shorter reasoning
# recovered the pilot-2 case; measured again here on stage 2 (14/11 dry pass, 482 s, 0 char)
RETRY_NOTE = ("\n\nNB : une tentative précédente n'a rien rendu. "
              "Réfléchis plus court (quelques centaines de mots), puis rends directement ta sortie.")


async def sk_call_retry(session: ClientSession, args, rec: dict, stage: str, prompt: str,
                        conv: str | None) -> dict:
    for attempt in range(2):
        tob = engine_tokens()
        env, dt = await sk_call(session, args, prompt + (RETRY_NOTE if attempt else ""), conv)
        toa = engine_tokens()
        rec["calls"].append({"stage": stage if not attempt else f"{stage}-retry",
                             "elapsed_s": dt, "error": env.get("error"),
                             "response_chars": len(env.get("response") or ""),
                             "engine_delta": ({k: round(toa[k] - tob[k]) for k in toa if k in tob}
                                              or None)})
        if not (env.get("error") or "").startswith("empty model response"):
            break
    return env


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
           "lane": LANE, "dry": True, "stages": {}, "calls": [],
           "engine_tokens_before": engine_tokens()}
    # refuse a --repo whose origin is not jsboige/CoursIA: the claim guard infers its slug from
    # the remote of ITS cwd (check_lane_claim.py), and a wrong --repo silently serves another
    # repo's issue numbers (measured 14/11: a manual claim check run from d:/vllm queried
    # jsboige/vllm#20250 — right number, wrong repo; multi-remote checkouts also hide this,
    # `git remote -v | head` shows only the alphabetically first remote).
    origin = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                            capture_output=True, text=True).stdout.strip()
    rec["repo_origin"] = origin
    if "jsboige/CoursIA" not in origin and not args.allow_foreign_origin:
        rec["verdict"] = f"refused-foreign-origin:{origin or 'no-origin'}"
        return rec
    token = app_token(repo)
    conventions = read_conventions(args.conventions)
    rec["conventions"] = {"path": args.conventions, "chars": len(conventions)}

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
                                 build_view(src_nb), conventions)
            env = await sk_call_retry(sk, args, rec, "1-plan", prompt, None)
            conv = env.get("conversation_id")
            rec["conversation_id"] = conv      # the agentic trace the PR body must carry
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

            # ---- stage 2 BUILD (model edits a harness-made copy, same conversation)
            t2 = time.time()
            scratch = Path(scratch_nb)
            if scratch.exists():
                scratch.unlink()
            shutil.copy2(src_nb, scratch)     # outputs preserved: nothing to re-create
            sha_before = _sha(scratch)
            src_cells = _cells(src_nb)
            rec["write_mode"] = args.write_mode
            prompt2 = (build_json_prompt(plan, exec_idx, src_cells, len(src_cells), conventions)
                       if args.write_mode == "json"
                       else build_prompt(scratch_nb, plan, exec_idx, src_cells,
                                         len(src_cells), conventions))
            env2 = await sk_call_retry(sk, args, rec, "2-build", prompt2, conv)
            built = parse_json_block(env2.get("response") or "")
            rec["build_model_answer"] = {"parsed": built, "chars": len(env2.get("response") or "")}
            if args.write_mode == "json" and built:
                rec["apply"] = apply_edits(scratch, built)
            rec["stage2_s"] = round(time.time() - t2, 1)

            # ---- harness: structural diff first, then execution; the harness judges alone
            t3 = time.time()
            exists = scratch.is_file()
            rec["built_notebook"] = {"path": scratch_nb, "exists": exists,
                                     "bytes": scratch.stat().st_size if exists else 0,
                                     "changed": exists and _sha(scratch) != sha_before}
            if not exists:
                rec["verdict"] = "build-no-notebook"
            elif not rec["built_notebook"]["changed"]:
                rec["verdict"] = "build-no-change"
            else:
                rec["structure"] = verify_structure(src_nb, scratch, plan)
                if not rec["structure"]["ok"]:
                    rec["verdict"] = "built-structure-mismatch"
                else:
                    kid = await start_kernel(pm, args.kernel_override or kernel["kernel_name"])
                    rec["kernel_id"] = kid
                    # exec policy: plan indexes are SOURCE-space and shift with deletes/inserts.
                    # auto = run ALL built code cells in order when the plan touches code
                    # (state-safe: dependencies run first, execution_count sequential 1..N —
                    # the C.2 proof), none for a markdown-only gesture.
                    exec_targets: list[int] = []
                    if kid:
                        code_idx = [i for i, c in enumerate(_cells(scratch))
                                    if c.get("cell_type") == "code"]
                        touches_code = (
                            any(src_cells[int(p["cell"])].get("cell_type") == "code"
                                for p in plan.get("plan") or []
                                if p.get("geste") in ("edit", "delete")
                                and str(p.get("cell", "")).isdigit()
                                and int(p["cell"]) < len(src_cells))
                            or any(x.get("type") == "code"
                                   for x in (rec.get("apply") or {}).get("inserts") or []))
                        mode = "all" if (args.exec_mode == "auto" and touches_code) \
                            else ("none" if args.exec_mode == "auto" else args.exec_mode)
                        rec["exec_mode"] = f"{args.exec_mode}->{mode}"
                        rec["exec_planned_idx"] = exec_idx
                        if mode == "all":
                            exec_targets = code_idx
                        elif mode == "plan":
                            exec_targets = [int(i) for i in exec_idx if int(i) in code_idx]
                        rec["execution"] = (await execute_cells(pm, scratch, kid, exec_targets)
                                            if exec_targets else [])
                    counts = [c.get("execution_count") for c in _cells(scratch)
                              if c.get("cell_type") == "code"
                              and _text(c.get("source")).strip()]
                    rec["c2"] = {"counts": counts,
                                 "sequential": counts == list(range(1, len(counts) + 1))}
                    exec_ok = all(e.get("ok") for e in (rec.get("execution") or []))
                    if not exec_ok:
                        rec["verdict"] = "built-execution-failed"
                    elif not rec.get("execution") or rec["c2"]["sequential"]:
                        rec["verdict"] = "built-executed-ok"
                    else:
                        rec["verdict"] = "built-executed-counts-broken"
            rec["stage3_s"] = round(time.time() - t3, 1)
    rec["finished"] = utcnow()
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--issue", type=int, required=True, help="CoursIA issue number")
    ap.add_argument("--notebook", required=True, help="repo-relative target notebook")
    ap.add_argument("--repo", default="d:/CoursIA", help="CoursIA checkout (claim guard + worktree source)")
    ap.add_argument("--allow-foreign-origin", action="store_true",
                    help="accept a --repo checkout whose origin is not jsboige/CoursIA (default: "
                         "refuse — the claim guard infers its slug from its cwd's origin, so a "
                         "wrong --repo silently serves another repo's issue numbers)")
    ap.add_argument("--worktree", default=str(VLLM_ROOT / ".tmp/nbcoder/wt"))
    ap.add_argument("--fresh-worktree", action="store_true")
    ap.add_argument("--out-dir", default=str(VLLM_ROOT / ".tmp/nbcoder"))
    ap.add_argument("--agent", default="notebook-auditor", help="sk-agent agent id")
    ap.add_argument("--conventions",
                    default=str(VLLM_ROOT / "myia_vllm/docs/adoption/nb-coder-conventions.md"),
                    help="house rules injected into the prompts ('' disables)")
    ap.add_argument("--intention", default="volet vllm du harnais nb-coder (passe a blanc)")
    ap.add_argument("--claim", action="store_true", help="post the [CLAIMED] comment (off in dry)")
    ap.add_argument("--gate-mode", choices=["warn", "block"], default="warn")
    ap.add_argument("--write-mode", choices=["json", "mcp"], default="json",
                    help="json = harness applies the model's cell sources in one write; "
                         "mcp = the model calls the papermill write tools (lost-update hazard "
                         "when it parallelises its calls, measured 14/11)")
    ap.add_argument("--kernel-override", default=None)
    ap.add_argument("--exec-mode", choices=["auto", "all", "plan"], default="auto",
                    help="auto: run ALL built code cells in order when the plan touches code "
                         "(state-safe, execution_count sequential — C.2 proof), none for "
                         "markdown-only; all: always; plan: the plan's execute_cells "
                         "(SOURCE indexes, shift hazard with deletes/inserts)")
    ap.add_argument("--max-stage", type=int, choices=[0, 1, 2], default=2)
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--max-tokens", type=int, default=16384)
    args = ap.parse_args()
    try:
        rec = asyncio.run(run(args))
    except Exception as exc:  # a trace is always written: a dead harness must not look like a quiet one
        rec = {"issue": args.issue, "notebook": args.notebook, "started": utcnow(),
               "lane": LANE, "dry": True, "verdict": f"crashed:{type(exc).__name__}: {exc}"}
    rec["engine_tokens_after"] = engine_tokens()
    b, a = rec.get("engine_tokens_before") or {}, rec.get("engine_tokens_after") or {}
    rec["engine_tokens_delta"] = {k: round(a[k] - b[k]) for k in a if k in b} or None
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
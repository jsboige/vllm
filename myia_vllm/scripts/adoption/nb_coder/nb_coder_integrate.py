#!/usr/bin/env python3
"""nb-coder repo integration — the CI guards a NEW port notebook trips, fixed
deterministically before the PR is pushed (jsboige/vllm, 21/11).

Measured (CoursIA#27829 head 05541d13, #27835 head 7ddca46e, lot-1 fixes
#27803/#27804/#27805, and po-2028:claudish's 14 C# port PRs of the 18/11):
every nb_coder port PR failed blocking guards and waited one Hermes review
cycle (~1 h) for remedies a deterministic pass applies itself:

  1. ``readme-notebook-coverage`` — the new notebook has no row in its folder's
     README (folder convention in force). Fix: a twin link appended on the
     source twin's own README line, mirroring that line's label convention
     (measured shapes: bare `[C#] · [Python]` -> `[Rust]`; `· [jumeau C#]` ->
     `· [jumeau Rust]`; inside a `(+ ...)` group -> bare; po-2028 folders use
     `[Version C#]` -> `[Version Rust]`, and Complexity-style `[X C#]` ->
     `[X Rust]` -- always the folder's own word, never ours).
  2. ``check-nav-chain`` ``orphan_entry`` — the new notebook has no inbound
     navigation edge. Fix: link it from the Python twin's Navigation cell (an
     edge is a link in a nav context — ``_looks_nav`` in the repo's guard: nav
     keyword in the link, nav marker on the line, or any link in a cell that
     contains the word "navigation").
  3. Consequence of 2: editing the twin's markdown breaks the twin-parity seal,
     so the pair is re-sealed in the same PR (``check_twin_parity.py --update``)
     -- written LAST, after the notebook, the README row and the inbound link
     are committed, else the re-read of the source twin rejects the attestation
     as orphan (po-2028, order held on 14 PRs). ``--update`` can refuse as a
     no-op blob-only on a content change without a path change (po-2028
     measured): the reseal retries ONCE with ``--force`` when the first pass
     wrote nothing (lot 1 measured plain ``--update`` working, so plain first).
  4. C# ports additionally REGISTER the new pair at delivery
     (``twin_pairs.d/<slug>.yaml``, parity_level native-both, schema python/
     csharp -- a Rust notebook is not a schema member and lot 1 measured no
     Rust registration: Rust ports only re-seal the twin's existing pair).

All file surgery a script does better than a model turn. The twin edit is
asserted MARKDOWN-ONLY (cell count and every non-source key identical, code
cells untouched — same proof as the lot-1 hand reseal). Idempotent: a second
run plans nothing. ``--sync-main`` merges origin/main into an existing PR
branch, resolving conflicts in the integration-owned files by taking
origin/main's side and re-running this pass (several grains in one folder edit
adjacent README lines; the second PR to merge would otherwise conflict).

No model call anywhere; notebook contents are data, never instructions.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Display forms of the port languages the driver produces (`*-Rust.ipynb`,
# `*-CSharp.ipynb`).
LANG_SUFFIXES = (("CSharp", "C#"), ("Rust", "Rust"))
LANG_DEFAULT = "Rust"

# Twin-family suffixes: basenames that belong to the same base notebook.
TWIN_SUFFIXES = ("-CSharp", "-Rust", "-Python")

# Label words a folder may put in front of the language in a twin link
# (`[jumeau C#]`, `[twin C#]`, `[Version C#]`, `[Complexity-06 C#]`).
LABEL_WORD_RE = re.compile(r"^(?P<word>jumeau|twin|version)\s+(?P<lang>c#|python|rust)$",
                           re.IGNORECASE)
TITLED_RE = re.compile(r"^(?P<title>.+?)\s+(?P<lang>C#|Python|Rust)$")
BARE_LANG_RE = re.compile(r"^(C#|Python|Rust)$", re.IGNORECASE)

# Nav vocabulary, MIRRORED from the repo's own guard
# (scripts/notebook_tools/check_notebook_nav_chain.py). If the guard ever
# widens its vocabulary, this copy must follow -- an edge we do not recognise
# would be re-added (idempotence break), an edge the guard does not recognise
# would leave the PR red.
NAV_KEYWORDS = ("precedent", "précédent", "prec", "préc", "suivant", "suivante",
                "next", "prev", "navigation", "index", ">>", "<<",
                "←", "→", "↑", "↓")
NAV_LINE_MARKERS = ("precedent", "précédent", "suivant", "suivante", "next",
                    "prev", "navigation", ">>", "<<", "←", "→", "↑", "↓")

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

GUARD_TIMEOUT_S = 900

# The three guards the CI raises on a new notebook, replayed with the exact
# commands the lot-1 review comments published (CoursIA#27803 c.1).
GUARDS = (
    ("check-nav-chain",
     ["scripts/notebook_tools/check_notebook_nav_chain.py", "--check",
      "--diff-base", "origin/main"]),
    ("readme-notebook-coverage",
     ["scripts/ci/check_readme_notebook_coverage.py", "--diff-base",
      "origin/main"]),
    ("twin-parity-changed",
     ["scripts/translation/check_twin_parity_changed.py", "--diff",
      "origin/main...HEAD"]),
)

TWIN_PAIRS_DIR = Path("scripts/notebook_tools/twin_pairs.d")

GIT_IDENTITY = ("-c", "user.name=nb-coder",
                "-c", "user.email=nb-coder@nb-coder.invalid")


def _git(wt: Path, *args: str, timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(wt), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    return p.returncode, (p.stdout or p.stderr or "").strip()


# ---------------------------------------------------------------- notebook io

def detect_nb_format(raw: str) -> dict:
    """Byte-faithful dump format of a repo notebook, measured from the file.

    The repo's notebooks are ``ensure_ascii=False, indent=1`` with no trailing
    newline (verified byte-exact on ``Search-03d-WeightedAstar.ipynb`` at
    origin/main); the detection keeps the module honest if another series
    formats differently, and ``apply_nb`` refuses to write when a round-trip
    of the UNCHANGED notebook does not reproduce the original bytes.
    """
    m = re.search(r"^\{[\r\n]+( +)\"cells\"", raw, re.MULTILINE)
    indent = len(m.group(1)) if m else 1
    return {"indent": indent,
            "ensure_ascii": ("\\u" in raw),
            "trailing_nl": raw.endswith("\n")}


def load_nb(path: Path) -> tuple[dict, dict, str]:
    raw = path.read_bytes().decode("utf-8")
    return json.loads(raw), detect_nb_format(raw), raw


def dump_nb(nb: dict, fmt: dict) -> str:
    return json.dumps(nb, ensure_ascii=fmt["ensure_ascii"],
                      indent=fmt["indent"]) + ("\n" if fmt["trailing_nl"] else "")


def apply_nb(path: Path, nb: dict, fmt: dict, original_raw: str) -> None:
    """Write a notebook only if the format round-trips: the unchanged parse must
    reproduce the original bytes, else the edit would silently reformat the
    whole file (a whole-file diff a reviewer cannot inspect)."""
    if dump_nb(json.loads(original_raw), fmt) != original_raw:
        raise ValueError(f"{path.name}: byte-faithful round-trip failed -- "
                         "unknown notebook formatting, refusing to write")
    path.write_bytes(dump_nb(nb, fmt).encode("utf-8"))


def cell_text(cell: dict) -> str:
    src = cell.get("source", "")
    return src if isinstance(src, str) else "".join(src)


def set_cell_text(cell: dict, text: str) -> None:
    """Replace a cell's source preserving its representation (list of lines vs
    string) — the repo's notebooks carry lists with per-line newlines."""
    if isinstance(cell.get("source"), list):
        cell["source"] = text.splitlines(keepends=True)
    else:
        cell["source"] = text


def assert_markdown_only(before: list[dict], after: list[dict], name: str) -> None:
    """Same proof as the lot-1 hand reseal: cell count identical, only markdown
    cells change, and only their 'source' key. Code cells and outputs are never
    touched — a port PR's twin edit is navigation prose, nothing else."""
    if len(before) != len(after):
        raise AssertionError(f"{name}: cell count changed {len(before)} -> {len(after)}")
    for i, (cb, ca) in enumerate(zip(before, after)):
        if cb == ca:
            continue
        if cb.get("cell_type") != "markdown" or ca.get("cell_type") != "markdown":
            raise AssertionError(f"{name}: cell {i} is not markdown on both sides")
        if {k: v for k, v in cb.items() if k != "source"} != \
           {k: v for k, v in ca.items() if k != "source"}:
            raise AssertionError(f"{name}: non-source change in cell {i}")


# ------------------------------------------------------------------ language

def split_port_name(nb_rel: str) -> tuple[str, str]:
    """`Serie-07-Norvig-Rust.ipynb` -> (`Serie-07-Norvig`, `Rust`).

    Returns (base_stem, display_language) for a `*-Rust.ipynb` / `*-CSharp.ipynb`
    port name. The base stem is what the twin family shares; the language is
    what the README label and nav segment name.
    """
    stem = Path(nb_rel).stem
    for suffix, display in LANG_SUFFIXES:
        if stem.endswith("-" + suffix):
            return stem[: -(len(suffix) + 1)], display
    return stem, LANG_DEFAULT


def twin_family_names(base_stem: str) -> set[str]:
    """Basenames of the base notebook and its language twins (base itself,
    -Python, -CSharp, -Rust -- whatever exists on the edited line)."""
    names = {f"{base_stem}.ipynb"}
    for suffix in TWIN_SUFFIXES:
        names.add(f"{base_stem}{suffix}.ipynb")
    return names


def mirror_label(sibling_text: str, lang: str, in_plus_group: bool) -> str:
    """README/nav label for the new twin, MIRRORING the sibling link it sits
    next to — the folder's own convention, never a house word.

    Measured shapes (lot 1 + po-2028 folders): `[Python]` -> `Rust`;
    `[jumeau C#]` -> `jumeau Rust`; `[Version C#]` -> `Version Rust`;
    `[Complexity-06 C#]` -> `Complexity-06 Rust`; a sibling inside a `(+ ...)`
    group takes the bare language (Part1-Foundations' `(+ [jumeau C#](...) ·
    [Rust](...))`). Default `jumeau <Lang>` (the repo's dominant twin word).
    """
    if in_plus_group:
        return lang
    text = sibling_text.strip()
    if BARE_LANG_RE.match(text):
        return lang
    m = LABEL_WORD_RE.match(text)
    if m:
        return f"{m.group('word')} {lang}"
    m = TITLED_RE.match(text)
    if m:
        return f"{m.group('title')} {lang}"
    return f"jumeau {lang}"


# ------------------------------------------------------------------ README row

def plan_readme_row(repo: Path, nb_rel: str, source_rel: str) -> dict:
    """Plan the README twin-link the coverage guard requires.

    The link is appended right after the LAST twin-family link of the source
    twin's own README line, as ` · [label](new.ipynb)` (all lot-1 fixes).
    """
    nb_rel = nb_rel.replace("\\", "/")
    new_name = nb_rel.rsplit("/", 1)[-1]
    base_stem, lang = split_port_name(nb_rel)
    folder = repo / Path(nb_rel).parent
    readmes = sorted(p for p in folder.glob("README*.md") if p.is_file())
    if not readmes:
        return {"todo": False, "why": "no-dir-readme (advisory, guard does not block)"}
    for readme in readmes:
        raw = readme.read_bytes().decode("utf-8")
        if new_name in raw:
            return {"todo": False, "why": f"{new_name} already in {readme.name}",
                    "file": _rel(repo, readme)}
        lines = raw.splitlines(keepends=True)
        family = twin_family_names(base_stem)
        for idx, line in enumerate(lines):
            links = [(m.start(), m.end(), m.group(1), m.group(2))
                     for m in LINK_RE.finditer(line)
                     if m.group(2).rsplit("/", 1)[-1] in family]
            if not links:
                continue
            start, end, text, _ = links[-1]
            in_plus_group = bool(re.search(r"\(\+\s*$", line[:start]))
            label = mirror_label(text, lang, in_plus_group)
            return {"todo": True, "file": _rel(repo, readme), "line": idx,
                    "insert": f" · [{label}]({new_name})", "insert_at": end,
                    "label": label, "path": str(readme)}
    return {"todo": False,
            "why": "no README line links the source twin -- row placement needs "
                   "the folder's own convention (guard will stay red, reported)"}


def apply_readme_row(action: dict) -> bool:
    if not action.get("todo"):
        return False
    path = Path(action["path"])
    raw = path.read_bytes().decode("utf-8")
    lines = raw.splitlines(keepends=True)
    line = lines[action["line"]]
    at = action["insert_at"]
    lines[action["line"]] = line[:at] + action["insert"] + line[at:]
    path.write_bytes("".join(lines).encode("utf-8"))
    return True


# ------------------------------------------------------------------ nav link

def _nav_edge_exists(cells: list[dict], new_name: str) -> bool:
    """True when the twin already links the new notebook in a NAV context —
    same three scopes as the guard's ``_looks_nav`` (link text, line, cell)."""
    for cell in cells:
        if cell.get("cell_type") != "markdown":
            continue
        text = cell_text(cell)
        cell_is_nav = "navigation" in text.lower()
        for line in text.splitlines():
            for m in LINK_RE.finditer(line):
                if m.group(2).rsplit("/", 1)[-1] != new_name:
                    continue
                low = f"{m.group(1)} {m.group(2)}".lower()
                if any(k in low for k in NAV_KEYWORDS):
                    return True
                if any(k in line.lower() for k in NAV_LINE_MARKERS):
                    return True
                if cell_is_nav:
                    return True
    return False


def _nav_bar_cells(cells: list[dict]) -> dict[int, int]:
    """{cell index: line index} of the LAST nav-bar line of every markdown cell
    that carries one — a bar is a line with a .ipynb link and a nav marker
    (`**Navigation** :`, `<<`, `>>`, arrows...). Series that duplicate the bar
    at the end of the notebook (ChoixSocial cells 0 and 27) get every copy
    extended, matching the lot-1 hand fix."""
    out: dict[int, int] = {}
    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "markdown":
            continue
        last = None
        for j, line in enumerate(cell_text(cell).splitlines()):
            if not any(m in line.lower() for m in NAV_LINE_MARKERS):
                continue
            if not any(m.group(2).lower().endswith(".ipynb")
                       for m in LINK_RE.finditer(line)):
                continue
            last = j
        if last is not None:
            out[i] = last
    return out


def _nav_label(bar_line: str, cell_text_: str, lang: str) -> str:
    """Twin segment of the nav bar, mirroring the bar's own twin link
    (`| [twin C#](...)` -> `twin Rust`, `[jumeau C#]` -> `jumeau Rust`);
    default `jumeau <Lang>` (lot-1 cell-0 bars)."""
    for m in LINK_RE.finditer(bar_line):
        text = m.group(1).strip()
        if BARE_LANG_RE.match(text):
            return lang
        mm = LABEL_WORD_RE.match(text) or TITLED_RE.match(text)
        if mm:
            return mirror_label(text, lang, False)
    low = cell_text_.lower()
    if re.search(r"\btwin\b", low):
        return f"twin {lang}"
    return f"jumeau {lang}"


def plan_nav_link(twin_path: Path, nb_rel: str) -> dict:
    """Plan the inbound nav edge in the Python twin.

    Shapes, all measured on the lot-1 fixes: extend every existing nav bar with
    ` | [label](new.ipynb)` (Search-03d cell 0, ChoixSocial cells 0+27); when
    no bar exists but a cell is a Navigation cell, append a
    `**Jumeau <Lang>** : [stem](new.ipynb)` line to it (Sudoku-07 cell 0 under
    its `## Navigation` table); when the twin has no navigation at all, prepend
    a minimal `**Navigation** : [jumeau <Lang>](new.ipynb)` bar to its first
    markdown cell and REPORT it — the smallest change the guard accepts, less
    than the series' full prev|index|next bar a reviewer may want.
    """
    nb_rel = nb_rel.replace("\\", "/")
    new_name = nb_rel.rsplit("/", 1)[-1]
    _, lang = split_port_name(nb_rel)
    nb, fmt, raw = load_nb(twin_path)
    cells = nb["cells"]
    if _nav_edge_exists(cells, new_name):
        return {"todo": False, "why": "nav edge already present"}
    bars = _nav_bar_cells(cells)
    if bars:
        changed, labels = [], []
        for i, j in bars.items():
            text = cell_text(cells[i])
            lines = text.splitlines(keepends=True)
            bar = lines[j]
            label = _nav_label(bar, text, lang)
            labels.append(label)
            body, tail = bar.rstrip("\r\n"), bar[len(bar.rstrip("\r\n")):]
            lines[j] = f"{body} | [{label}]({new_name}){tail}"
            set_cell_text(cells[i], "".join(lines))
            changed.append(i)
        return _finish_plan(twin_path, nb, fmt, raw,
                            {"todo": True, "how": "extended-nav-bar",
                             "cells": changed, "label": labels[0]})
    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "markdown":
            continue
        text = cell_text(cell)
        if "navigation" not in text.lower():
            continue
        addition = f"**Jumeau {lang}** : [{Path(nb_rel).stem}]({new_name})"
        set_cell_text(cell, text.rstrip("\n") + "\n\n" + addition + "\n")
        return _finish_plan(twin_path, nb, fmt, raw,
                            {"todo": True, "how": "appended-under-navigation-cell",
                             "cells": [i], "label": f"Jumeau {lang}"})
    first_md = next((i for i, c in enumerate(cells)
                     if c.get("cell_type") == "markdown"), None)
    if first_md is None:
        return {"todo": False, "why": "twin has no markdown cell to host a nav bar"}
    bar = f"**Navigation** : [jumeau {lang}]({new_name})\n\n"
    set_cell_text(cells[first_md], bar + cell_text(cells[first_md]))
    return _finish_plan(twin_path, nb, fmt, raw,
                        {"todo": True, "how": "added-minimal-nav-bar",
                         "cells": [first_md], "label": f"jumeau {lang}",
                         "note": "twin had no Navigation cell -- minimal bar "
                                 "added, series may want prev|index|next"})


def _finish_plan(path: Path, nb: dict, fmt: dict, raw: str, plan: dict) -> dict:
    assert_markdown_only(json.loads(raw)["cells"], nb["cells"], path.name)
    plan["file"] = str(path)
    plan["_nb"], plan["_fmt"], plan["_raw"] = nb, fmt, raw
    return plan


def apply_nav_link(action: dict) -> bool:
    if not action.get("todo"):
        return False
    apply_nb(Path(action["file"]), action["_nb"], action["_fmt"], action["_raw"])
    return True


# ------------------------------------------------------------------ registry

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def pair_member(worktree: Path, rel_path: str, key: str) -> str | None:
    """Value of `key:` of the registry pair whose PYTHON member is `rel_path`.
    Flat scan, no yaml import (pair files are flat mappings; the name line is
    the list dash form `- name:`)."""
    rel_path = rel_path.replace("\\", "/")
    d = worktree / TWIN_PAIRS_DIR
    if not d.is_dir():
        return None
    for f in sorted(d.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m_py = re.search(r"^\s+python:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                         text, re.MULTILINE)
        if not m_py or m_py.group(1).replace("\\", "/") != rel_path:
            continue
        for pat in (rf"^-\s+{key}:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                    rf"^\s+{key}:\s*['\"]?([^'\"\n]+?)['\"]?\s*$"):
            m = re.search(pat, text, re.MULTILINE)
            if m:
                return m.group(1).strip()
    return None


def find_twin_pair(worktree: Path, source_rel: str) -> str | None:
    """Name of the registry pair whose python member is the source twin, or
    None (twin not registered -- the parity guard has no seal to break, but a
    C# delivery must then REGISTER the pair, cf register_pair)."""
    return pair_member(worktree, source_rel, "name")


def _csharp_member_exists(worktree: Path, nb_rel: str) -> bool:
    """True when `nb_rel` is already the csharp member of some registered pair."""
    nb_rel = nb_rel.replace("\\", "/")
    d = worktree / TWIN_PAIRS_DIR
    if not d.is_dir():
        return False
    for f in sorted(d.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^\s+csharp:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                      text, re.MULTILINE)
        if m and m.group(1).replace("\\", "/") == nb_rel:
            return True
    return False


def register_pair(worktree: Path, source_rel: str, nb_rel: str, lane: str,
                  facts: dict | None = None) -> dict:
    """Register the NEW pair (source twin + new C# notebook) at delivery —
    parity_level native-both, schema python/csharp, attestation written LAST
    by reseal_pair (po-2028 order, held on 14 PRs). Rust notebooks are NOT
    registered: the registry schema has no rust member and lot 1 measured no
    Rust registration on review-accepted branches.

    The entry states DELIVERY facts only (harness, verifier verdict, execution
    count) -- no `bridge_verdict` (optional in the schema; a SOTA verdict is a
    firsthand judgment the harness does not make) and no 'verified firsthand'
    claim. """
    source_rel = source_rel.replace("\\", "/")
    nb_rel = nb_rel.replace("\\", "/")
    base_stem, lang = split_port_name(nb_rel)
    if lang != "C#":
        return {"registered": False,
                "why": f"language {lang!r} is not a registry member (python/csharp)"}
    if pair_member(worktree, source_rel, "name"):
        return {"registered": False, "why": "source twin already in a pair"}
    if _csharp_member_exists(worktree, nb_rel):
        return {"registered": False, "why": "notebook already in a pair"}
    family = Path(nb_rel).parent.relative_to("MyIA.AI.Notebooks").as_posix() \
        if nb_rel.startswith("MyIA.AI.Notebooks/") else Path(nb_rel).parent.as_posix()
    name = f"{base_stem} C#"
    facts = facts or {}
    entry = (
        f"- name: \"{name}\"\n"
        f"  family: {family}\n"
        f"  python: {source_rel}\n"
        f"  csharp: {nb_rel}\n"
        f"  parity_level: native-both\n"
        f"  known_differences:\n"
        f"    - \"Enregistrement de livraison ({lane}, harnais nb_coder stages 0-5) : "
        f"portage C# de {Path(source_rel).name}. Execution reelle sur kernel "
        f"{facts.get('kernel', 'n/a')} : {facts.get('executed_cells', 'n/a')} cellules, "
        f"0 erreur. Verification independente : {facts.get('verdict', 'n/a')}. "
        f"Premiere attestation ecrite par l'integration de livraison (check_twin_parity "
        f"--update), en DERNIERE operation (cf #8957).\"\n")
    dest = worktree / TWIN_PAIRS_DIR / f"{_slug(name)}.yaml"
    if dest.exists():
        return {"registered": False, "why": f"{dest.name} already exists"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(entry, encoding="utf-8", newline="")
    return {"registered": True, "file": (TWIN_PAIRS_DIR / dest.name).as_posix(),
            "pair": name}


def reseal_pair(worktree: Path, pair_name: str, lane: str) -> dict:
    """Re-seal a pair with the repo's own tool (``check_twin_parity.py
    --update``), like the lot-1 hand reseal. Records the git blob SHAs AT
    HEAD, so the notebook, README row and inbound link must already be
    COMMITTED (po-2028: attestation LAST). ``--update`` can refuse as a no-op
    blob-only on a content change (measured po-2028): before retrying with
    ``--force``, the pair's OWN check decides whether a seal is actually
    missing -- a forced duplicate attestation on an already-sealed pair would
    be exactly the false audit the registry's design gate forbids (#9399)."""
    out = {"pair": pair_name, "forced": False}

    def _run(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "scripts/notebook_tools/check_twin_parity.py",
             *extra, "--pair", pair_name]
            + (["--by", lane] if "--update" in extra else []),
            cwd=str(worktree), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=GUARD_TIMEOUT_S)

    proc = _run("--update")
    audit = _status(worktree, TWIN_PAIRS_DIR.as_posix())
    if proc.returncode == 0 and audit:
        return out | {"ok": True, "rc": proc.returncode, "audit_files": audit,
                      "tail": (proc.stdout or proc.stderr or "")[-400:]}
    chk = _run("--check")
    if chk.returncode == 0:  # pair already sealed at HEAD: nothing to attest
        return out | {"ok": True, "rc": proc.returncode, "audit_files": [],
                      "skipped": "already sealed at HEAD",
                      "tail": (chk.stdout or chk.stderr or "")[-400:]}
    proc = _run("--update", "--force")  # drift present, --update refused
    audit = _status(worktree, TWIN_PAIRS_DIR.as_posix())
    out |= {"forced": True, "rc": proc.returncode, "audit_files": audit,
            "tail": (proc.stdout or proc.stderr or "")[-400:]}
    out["ok"] = proc.returncode == 0 and bool(audit)
    return out


def _status(worktree: Path, path: str) -> list[str]:
    rc, out = _git(worktree, "status", "--porcelain", "--", path)
    return [l[3:].strip() for l in out.splitlines() if l.strip()]


def _rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ------------------------------------------------------------------ guards

def replay_guards(worktree: Path) -> list[dict]:
    """Replay the three guards with the exact commands the lot-1 review
    comments published. Read-only against git; run AFTER the integration
    commits so `--diff-base origin/main` sees them."""
    out = []
    for name, cmd in GUARDS:
        try:
            proc = subprocess.run([sys.executable, *cmd], cwd=str(worktree),
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=GUARD_TIMEOUT_S)
            out.append({"guard": name, "cmd": " ".join(["python", *cmd]),
                        "rc": proc.returncode,
                        "tail": (proc.stdout or proc.stderr or "")[-400:]})
        except (subprocess.TimeoutExpired, OSError) as e:
            out.append({"guard": name, "cmd": " ".join(["python", *cmd]),
                        "rc": None, "tail": f"{type(e).__name__}: {e}"[:400]})
    return out


# ------------------------------------------------------------------ integrate

def integrate(worktree: Path, notebook: str, source_nb: str) -> dict:
    """Apply the two file edits (README row + inbound nav link). Returns the
    plan for each plus the touched repo-relative files. Idempotent: on an
    already-integrated branch both plans report todo=False and nothing moves."""
    worktree = Path(worktree)
    notebook = notebook.replace("\\", "/")
    source_nb = source_nb.replace("\\", "/")
    twin = worktree / source_nb
    if not twin.is_file():
        return {"error": f"source notebook not found: {source_nb}"}
    nav = plan_nav_link(twin, notebook)
    apply_nav_link(nav)
    readme = plan_readme_row(worktree, notebook, source_nb)
    apply_readme_row(readme)
    touched = ([source_nb] if nav.get("todo") else []) + \
              ([readme["file"]] if readme.get("todo") else [])
    return {"notebook": notebook, "source_nb": source_nb,
            "nav": {k: v for k, v in nav.items() if not k.startswith("_")},
            "readme": {k: v for k, v in readme.items() if k != "path"},
            "pair": find_twin_pair(worktree, source_nb),
            "touched": touched}


def plan_only(worktree: Path, notebook: str, source_nb: str) -> dict:
    """--check-only: the same plans, zero writes."""
    worktree = Path(worktree)
    notebook = notebook.replace("\\", "/")
    source_nb = source_nb.replace("\\", "/")
    twin = worktree / source_nb
    if not twin.is_file():
        return {"error": f"source notebook not found: {source_nb}"}
    nav = plan_nav_link(twin, notebook)
    readme = plan_readme_row(worktree, notebook, source_nb)
    return {"notebook": notebook, "source_nb": source_nb,
            "nav": {k: v for k, v in nav.items()
                    if not k.startswith("_") and k != "file"},
            "readme": {k: v for k, v in readme.items() if k != "path"},
            "pair": find_twin_pair(worktree, source_nb),
            "todo": bool(nav.get("todo") or readme.get("todo"))}


# ------------------------------------------------------------------ sync-main

def owned_files(worktree: Path, notebook: str, source_nb: str) -> list[str]:
    """Paths whose conflicts --sync-main may resolve itself: the notebook
    folder's README(s), the source twin, the twin-pairs registry. Invariant:
    on an nb_coder branch those files carry ONLY this integration's edits,
    so taking origin/main's side then re-running it loses nothing."""
    notebook = notebook.replace("\\", "/")
    source_nb = source_nb.replace("\\", "/")
    folder = worktree / Path(notebook).parent
    owned = sorted(_rel(worktree, p) for p in folder.glob("README*.md"))
    owned.append(source_nb)
    owned.append(TWIN_PAIRS_DIR.as_posix())
    return owned


def merge_owned_conflicts(worktree: Path, owned: list[str]) -> dict:
    """`git merge origin/main` (no rebase, no force-push). Conflicts confined
    to `owned` paths are resolved by taking origin/main's version (the caller
    re-runs the integration on top, idempotently); ANY other conflict aborts
    the merge and reports. Testable without the guards."""
    rc, out = _git(worktree, "merge", "origin/main", "--no-edit")
    if rc == 0:
        return {"merged": True, "already_up_to_date": "Already up to date" in out,
                "output": out[-300:]}
    rc_u, conflicted = _git(worktree, "diff", "--name-only", "--diff-filter=U")
    paths = [p for p in conflicted.splitlines() if p.strip()]
    owned_ok = all(any(p == o or p.startswith(o.rstrip("/") + "/") for o in owned)
                   for p in paths)
    if not paths or not owned_ok:
        _git(worktree, "merge", "--abort")
        return {"merged": False, "aborted": True, "conflicts": paths,
                "output": out[-300:]}
    for p in paths:  # take origin/main's side, then the caller re-integrates
        _git(worktree, "restore", "--source=origin/main", "--staged",
             "--worktree", "--", p)
    return {"merged": True, "resolved_theirs": paths, "output": out[-300:]}


def sync_main(worktree: Path, notebook: str, source_nb: str, lane: str,
              facts: dict | None = None) -> dict:
    """--sync-main: fold origin/main into an existing PR branch, re-apply the
    integration (idempotent), re-seal LAST, replay the guards. Several grains
    in one folder edit adjacent README lines: the second PR to merge would
    otherwise conflict -- measured risk on the 4 Complexity grains queued by
    po-2028."""
    worktree = Path(worktree)
    merge = merge_owned_conflicts(worktree, owned_files(worktree, notebook, source_nb))
    if not merge.get("merged"):
        return {"merge": merge, "guards": replay_guards(worktree)}
    result = integrate(worktree, notebook, source_nb)
    for f in result.get("touched", []):
        _git(worktree, "add", "--", f)
    _git(worktree, *GIT_IDENTITY, "commit", "--no-edit")
    return {"merge": merge, "integration": result,
            "reseal": _reseal_after(worktree, notebook, source_nb, lane, facts),
            "guards": replay_guards(worktree)}


def _reseal_after(worktree: Path, notebook: str, source_nb: str, lane: str,
                  facts: dict | None) -> dict | None:
    """Register (C# first delivery) then re-seal, and commit the registry
    writes so the guards read them at HEAD."""
    reg = register_pair(worktree, source_nb, notebook, lane, facts)
    pair = find_twin_pair(worktree, source_nb)
    if not pair:
        return {"registered": reg, "why": "no pair to seal"}
    reseal = reseal_pair(worktree, pair, lane)
    if reg.get("registered") or reseal.get("audit_files"):
        _git(worktree, "add", "--", TWIN_PAIRS_DIR.as_posix())
        msg = (f"Chore(twin-parity): rescelle « {pair} » après intégration "
               f"({Path(notebook).stem})\n\nAttestation écrite en DERNIÈRE "
               "opération, après carnet, ligne README et lien de navigation.\n\n"
               f"Lane: {lane}\n"
               "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n")
        _git(worktree, *GIT_IDENTITY, "commit", "-m", msg)
    return {"registered": reg, "reseal": reseal}


# ------------------------------------------------------------------ cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Integrate an nb_coder port notebook into the repo's "
                    "guards (README row, inbound nav link, twin-parity reseal).")
    ap.add_argument("--worktree", required=True, help="CoursIA worktree root")
    ap.add_argument("--notebook", required=True,
                    help="repo-relative path of the NEW notebook")
    ap.add_argument("--source-nb", required=True, dest="source_nb",
                    help="repo-relative path of its Python source twin")
    ap.add_argument("--check-only", action="store_true",
                    help="plan only: report what would change, write nothing")
    ap.add_argument("--sync-main", action="store_true", dest="sync_main",
                    help="existing PR branch: merge origin/main (no rebase), "
                         "resolve integration-owned conflicts from origin/main, "
                         "re-apply, re-seal, replay guards")
    ap.add_argument("--by", default="myia-ai-01:vllm",
                    help="lane identity for the twin-parity reseal")
    ap.add_argument("--facts", default=None,
                    help="JSON delivery facts for the C# pair registration "
                         "(kernel, executed_cells, verdict)")
    args = ap.parse_args(argv)
    wt = Path(args.worktree)
    facts = json.loads(args.facts) if args.facts else None

    if args.check_only:
        result = plan_only(wt, args.notebook, args.source_nb)
        result["guards"] = replay_guards(wt)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if not result.get("todo") else 1

    if args.sync_main:
        result = sync_main(wt, args.notebook, args.source_nb, args.by, facts)
        result["guards"] = result.get("guards") or replay_guards(wt)
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
        return 0 if (result.get("merge", {}).get("merged")
                     and all(g["rc"] == 0 for g in result["guards"])) else 1

    result = integrate(wt, args.notebook, args.source_nb)
    if result.get("error"):
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 2
    for f in result["touched"]:
        _git(wt, "add", "--", f)
    msg = (f"Chore(integration): ligne README + arête nav pour "
           f"{Path(args.notebook).stem}\n\n"
           "Le jumeau Python ne change qu'en markdown (barre/section Navigation) : "
           "arête entrante exigée par check-nav-chain ; ligne README exigée par "
           "readme-notebook-coverage.\n\n"
           f"Lane: {args.by}\n"
           "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n")
    if result["touched"]:
        _git(wt, *GIT_IDENTITY, "commit", "-m", msg)
    result["reseal"] = _reseal_after(wt, args.notebook, args.source_nb,
                                     args.by, facts)
    result["guards"] = replay_guards(wt)
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 0 if all(g["rc"] == 0 for g in result["guards"]) else 1


if __name__ == "__main__":
    sys.exit(main())

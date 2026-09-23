"""Run the CoursIA multi-agent Lean prover on a sorry that has no DEMOS entry (#1453).

The harness only targets entries of ``prover/config.py:DEMOS``, and its files are under a
po-2024:CoursIA claim, so they are read, never edited. This launcher registers a transient
DEMOS entry in memory (built from the target file itself: import block, statement) and then
runs the unmodified ``run_prover_bg.main``. Nothing is written to the harness.

Usage (from run_prover_local.sh, which pins every role to the local provider):
    run_prover_target.py --file <abs .lean> --theorem <name> [--note <text>] -- <run_prover_bg args>
"""
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

AGENT_TESTS = Path(os.environ.get(
    "PROVER_AGENT_TESTS", "d:/dev/CoursIA-prover/MyIA.AI.Notebooks/SymbolicAI/Lean/agent_tests"))
ADHOC_ID = 9001  # far above the harness's own ids


def statement_colon(header: str) -> int:
    """Index just past the ':' that opens the statement: the first one outside binders."""
    depth = 0
    for i, ch in enumerate(header):
        if ch in "([{⦃":
            depth += 1
        elif ch in ")]}⦄":
            depth -= 1
        elif ch == ":" and depth == 0 and header[i + 1:i + 2] != "=":
            return i + 1
    raise ValueError("no statement colon in theorem header")


def target_demo(path: Path, theorem: str, note: str) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if re.match(rf"\s*(theorem|lemma)\s+{re.escape(theorem)}\b", l))
    end = next(i for i in range(start, len(lines)) if ":= by" in lines[i])
    sorry = next(i for i in range(end + 1, len(lines)) if lines[i].strip() == "sorry")
    header = "\n".join(lines[start:end + 1])
    goal = re.sub(r"\s*:=\s*by\s*$", "", header[statement_colon(header):]).strip()
    imports = "".join(l + "\n" for l in lines if l.startswith("import "))
    return {
        "name": f"ADHOC_{theorem.upper()}",
        "file": str(path),
        "line": sorry + 1,
        "sorry_type": "sorry_replacement",
        "theorem_name": theorem,
        "theorem": theorem,
        "imports": imports,
        "goal": goal,
        "description": (f"Target from count_code_sorry.py (non-INTRINSIC), #1453 pass on the local MoE.\n"
                        f"Statement:\n{header}\n{note}\n"
                        f"Replace the sorry at L{sorry + 1} of {path.name}."),
        "difficulty": "hard",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True)
    ap.add_argument("--theorem", required=True)
    ap.add_argument("--note", default="", help="extra context for the agents, taken from the file's own docstring")
    ap.add_argument("rest", nargs=argparse.REMAINDER, help="run_prover_bg options after --")
    args = ap.parse_args()

    os.chdir(AGENT_TESTS)
    sys.path.insert(0, str(AGENT_TESTS))
    import run_prover_bg as bg  # noqa: E402  (sets LEAN_PROJECT, imports the harness)

    demo = target_demo(Path(args.file).resolve(), args.theorem, args.note)
    bg.DEMOS[ADHOC_ID] = demo
    bg._bg(f"ADHOC_TARGET {demo['name']} file={demo['file']} line={demo['line']}")
    rest = [a for a in args.rest if a != "--"]
    sys.argv = [str(AGENT_TESTS / "run_prover_bg.py"), str(ADHOC_ID), *rest]
    rc = 130  # same sentinel as run_prover_bg: a log never ends without an EXIT marker
    try:
        rc = asyncio.run(bg.main(bg.parse_args()))
    finally:
        bg._bg(f"EXIT code={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())

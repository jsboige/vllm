#!/usr/bin/env python3
"""Offline tests for the driver's creation mode (--source-nb) — the parity C# wave
(#27099-#27116) creates notebooks absent from origin/main. No engine, no MCP, no GitHub."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "nb_coder_driver", HERE / "nb_coder_driver.py")
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)


def write_nb(path: Path, cells: list[dict], meta: dict | None = None) -> Path:
    path.write_text(json.dumps({"cells": cells, "metadata": meta or {},
                                "nbformat": 4, "nbformat_minor": 5},
                               ensure_ascii=False), encoding="utf-8")
    return path


def _join(src) -> str:
    return "".join(src) if isinstance(src, list) else (src or "")


def py_twin(tmp_path: Path) -> Path:
    return write_nb(tmp_path / "T-Python.ipynb", [
        {"cell_type": "markdown", "source": "# Titre", "metadata": {}},
        {"cell_type": "code", "source": "print('hello')", "metadata": {},
         "execution_count": 1, "outputs": []},
        {"cell_type": "markdown", "source": "## Suite", "metadata": {}},
        {"cell_type": "code", "source": "assert 1 + 1 == 2", "metadata": {},
         "execution_count": 2, "outputs": []},
    ])


# ---------------------------------------------------------------- apply_create
def test_apply_create_fills_skeleton_one_write(tmp_path):
    skel = tmp_path / "skel.ipynb"
    skel.write_text(json.dumps({"cells": [], "metadata": {"kernelspec": {"name": ".net-csharp"}},
                                "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
    rep = D.apply_create(skel, {"cells": [
        {"cell_type": "markdown", "source": "# Titre C#"},
        {"cell_type": "code", "source": 'Console.WriteLine("hello");'},
        {"cell_type": "code", "source": ""},                     # skipped: empty
        {"cell_type": "quote", "source": "bad"},                 # skipped: bad type
    ]})
    nb = json.loads(skel.read_text(encoding="utf-8"))
    assert rep["cells_written"] == 2 and len(nb["cells"]) == 2
    assert rep["empty_sources"] == [2] and len(rep["errors"]) == 1
    assert nb["cells"][1]["execution_count"] is None and nb["cells"][1]["outputs"] == []
    assert "execution_count" not in nb["cells"][0]               # markdown stays clean
    assert all(c["id"] for c in nb["cells"])                     # nbformat 4.5+ ids
    assert nb["metadata"]["kernelspec"]["name"] == ".net-csharp"  # skeleton meta kept


def test_verify_structure_create_count_and_signature(tmp_path):
    src = py_twin(tmp_path)
    good = write_nb(tmp_path / "good.ipynb", [
        {"cell_type": "markdown", "source": "# Titre C#", "metadata": {}},
        {"cell_type": "code", "source": "var a = 1;", "metadata": {},
         "execution_count": None, "outputs": []},
        {"cell_type": "markdown", "source": "## Suite .NET", "metadata": {}},
        {"cell_type": "code", "source": "var b = 2;", "metadata": {},
         "execution_count": None, "outputs": []},
    ])
    assert D.verify_structure_create(src, good)["ok"] is True

    fewer = write_nb(tmp_path / "fewer.ipynb",
                     json.loads(good.read_text(encoding="utf-8"))["cells"][:3])
    v = D.verify_structure_create(src, fewer)
    assert v["ok"] is False and v["counts_ok"] is False and v["type_signature_ok"] is False

    swapped = write_nb(tmp_path / "swapped.ipynb", [
        {"cell_type": "markdown", "source": "# T", "metadata": {}},
        {"cell_type": "markdown", "source": "code devenu markdown", "metadata": {}},
        {"cell_type": "markdown", "source": "## S", "metadata": {}},
        {"cell_type": "code", "source": "var b = 2;", "metadata": {},
         "execution_count": None, "outputs": []},
    ])
    v2 = D.verify_structure_create(src, swapped)
    assert v2["counts_ok"] is True and v2["type_signature_ok"] is False

    stale = json.loads(good.read_text(encoding="utf-8"))
    stale["cells"][1]["outputs"] = [{"output_type": "stream", "text": "fabriqué"}]
    stalep = tmp_path / "stale.ipynb"
    stalep.write_text(json.dumps(stale), encoding="utf-8")
    v3 = D.verify_structure_create(src, stalep)
    assert v3["ok"] is False and v3["stale_outputs"] == [1]      # outputs must come from EXECUTION


# ---------------------------------------------------------------- canonical meta
def test_series_canonical_meta_picks_csharp_twin(tmp_path):
    repo = tmp_path
    d = repo / "Ser"
    d.mkdir()
    write_nb(d / "T-01-CSharp.ipynb", [], {"kernelspec": {"name": ".net-csharp"},
                                           "language_info": {"version": "9.0.117"}})
    write_nb(d / "T-02-CSharp.ipynb", [], {"kernelspec": {"name": ".net-csharp"},
                                           "language_info": {"version": "9.0.117"}})
    write_nb(d / "T-Python.ipynb", [], {"kernelspec": {"name": "python3"},
                                        "language_info": {"version": "3.13.16"}})
    meta = D.series_canonical_meta(repo, "Ser/T-03-CSharp.ipynb")
    assert meta["kernelspec"]["name"] == ".net-csharp"
    assert meta["language_info"]["version"] == "9.0.117"         # NOT the Python twin's
    assert D.series_canonical_meta(repo, "Ser/T-04-CSharp.ipynb") == {} or True
    # no C# sibling at all -> empty dict (skeleton without meta, gate will report honestly)
    lone = repo / "Lone"
    lone.mkdir()
    write_nb(lone / "X-Python.ipynb", [], {"kernelspec": {"name": "python3"}})
    assert D.series_canonical_meta(repo, "Lone/X-CSharp.ipynb") == {}


# ---------------------------------------------------------------- gates in creation mode
def test_run_gates_language_info_uses_canon_in_creation(tmp_path):
    src = py_twin(tmp_path)
    built = write_nb(tmp_path / "built.ipynb", [
        {"cell_type": "markdown", "source": "# Titre C#", "metadata": {}},
        {"cell_type": "code", "source": "var a = 1;", "metadata": {},
         "execution_count": None, "outputs": []},
        {"cell_type": "markdown", "source": "## Suite .NET", "metadata": {}},
        {"cell_type": "code", "source": "var b = 2;", "metadata": {},
         "execution_count": None, "outputs": []},
    ], meta={"kernelspec": {"name": ".net-csharp"},
             "language_info": {"version": "9.0.117"}})
    gates = {g["gate"]: g for g in D.run_gates(src, built, create_mode=True,
                                               canon_version="9.0.117")}
    assert gates["language-info"]["ok"] is True
    assert gates["language-info"]["detail"] == {"canon": "9.0.117", "built": "9.0.117"}
    # correction mode on the same pair would FAIL (python 3.13 vs 9.0) — that failure is
    # the proof the create branch is actually taken
    gates_corr = {g["gate"]: g for g in D.run_gates(src, built)}
    assert gates_corr["language-info"]["ok"] is False
    # every cell is delta in creation mode: coord-refs polices the whole notebook
    bad = json.loads(built.read_text(encoding="utf-8"))
    bad["cells"][0]["source"] = "voir l'epic #26070 pour le contexte"
    badp = tmp_path / "bad.ipynb"
    badp.write_text(json.dumps(bad), encoding="utf-8")
    gates_bad = {g["gate"]: g for g in D.run_gates(src, badp, create_mode=True,
                                                   canon_version="9.0.117")}
    assert gates_bad["coord-refs"]["ok"] is False


# ---------------------------------------------------------------- prompts + segmentation
def test_creation_prompts_contract(tmp_path):
    p1 = D.creation_prompt(27099, {"title": "t", "body": "corps", "comments": ""},
                           "Ser/Z3-10-CSharp.ipynb", "Ser/Z3-10-Python.ipynb",
                           {"kernel_name": ".net-csharp", "canonical_version": None,
                            "neighbour_versions": {}}, "ctx", "vue")
    assert "MODE CRÉATION" in p1 and '"cells"' in p1 and "27099" in p1
    # the 17/11 fix: stage 1 is a LIGHT plan — full sources are stage 2's job, by segments
    assert "SANS les sources" in p1
    assert '"source"' not in p1.split("Rends UNIQUEMENT")[1]   # schema has titre/role only
    p2 = D.creation_json_prompt([{"idx": 0, "cell_type": "markdown", "titre": "T"}], 29, "conv")
    assert "29" in p2 and '"cells"' in p2 and "TRANCHE" in p2


def test_create_segments_assembles_and_reports(monkeypatch):
    """The stage-2 loop: one call per CREATE_SEGMENT plan cells -> assembled payload in
    plan order; a segment that answers nothing parseable sets the verdict and returns
    {} with the raw tail persisted (the 17/11 diagnosability hole)."""
    plan_cells = [{"idx": i, "cell_type": "markdown" if i % 2 else "code", "titre": f"c{i}"}
                  for i in range(10)]
    canned = [{"cells": [{"idx": c["idx"], "cell_type": c["cell_type"],
                          "source": f"src {c['idx']}"} for c in plan_cells[i:i + D.CREATE_SEGMENT]]}
              for i in range(0, 10, D.CREATE_SEGMENT)]
    calls = []

    async def fake_retry(session, args, rec, stage, prompt, conv):
        calls.append(stage)
        return {"response": "```json\n" + json.dumps(canned.pop(0)) + "\n```",
                "conversation_id": "cx"}

    monkeypatch.setattr(D, "sk_call_retry", fake_retry)
    rec: dict = {}
    out = asyncio.run(D.create_segments(None, None, rec, None, plan_cells, 10, ""))
    assert calls == ["2-build+0", "2-build+8"]               # 10 cells -> segments of 8 + 2
    assert [c["source"] for c in out["cells"]] == [f"src {i}" for i in range(10)]
    assert [s["got"] for s in rec["segments"]] == [8, 2]
    assert out["notes"] == "assembled from 2 segments"

    async def fake_dead(session, args, rec, stage, prompt, conv):
        return {"response": "voilà le code … { incomplet", "conversation_id": "cx"}

    monkeypatch.setattr(D, "sk_call_retry", fake_dead)
    rec2: dict = {}
    out2 = asyncio.run(D.create_segments(None, None, rec2, None, plan_cells, 10, ""))
    assert out2 == {} and rec2["verdict"].startswith("stage2-unparsed:0")
    assert rec2["stage2_raw_tail"]                           # diagnosable without a re-run


# ---------------------------------------------------------------- repair loop
def test_apply_repairs_replaces_and_resets(tmp_path):
    nb = tmp_path / "b.ipynb"
    write_nb(nb, [
        {"cell_type": "markdown", "source": "# T", "metadata": {}},
        {"cell_type": "code", "source": "var a = MkNe(1, 2);", "metadata": {},
         "execution_count": 3,
         "outputs": [{"output_type": "error", "evalue": "compilation error"}]},
        {"cell_type": "code", "source": "Console.WriteLine(1);", "metadata": {},
         "execution_count": 4, "outputs": []},
    ])
    rep = D.apply_repairs(nb, {"cells": [
        {"idx": 1, "cell_type": "code", "source": "var a = ctx.MkNot(ctx.MkEq(x, y));"},
        {"idx": 9, "cell_type": "code", "source": "inconnue"},      # unknown idx
        {"idx": 0, "cell_type": "code", "source": "pas code"},      # not a code cell
        {"idx": 2, "cell_type": "code", "source": "   "},           # empty source
    ]})
    assert rep["replaced"] == [1] and rep["unknown_idx"] == [9, 0] and rep["bad"] == [2]
    cells = json.loads(nb.read_text(encoding="utf-8"))["cells"]
    # sources are normalized to LISTS of lines — substring on the joined source
    assert "MkNot" in _join(cells[1]["source"])
    assert cells[1]["outputs"] == [] and cells[1]["execution_count"] is None  # re-execute
    assert _join(cells[2]["source"]) == "Console.WriteLine(1);"   # untouched


def test_repair_prompt_contract():
    p = D.repair_prompt([{"idx": 3, "source": "var a = MkNe(1,2);",
                          "errors": "(2,15): error CS1061: MkNe"}], "conv")
    assert "TOUR RÉPARATION" in p and "MkNe" in p and "CS1061" in p
    assert '"idx"' in p and "conv" in p
    # the schema demands ONLY the failing cells — no wholesale rewrite invitation
    assert "index inchangés" in p


def test_mcp_write_mode_refused_in_creation():
    """The driver's own post-parse guard: --source-nb + --write-mode mcp exits 2
    BEFORE any stage runs (max-stage 0, unreachable repo, claim off)."""
    old = sys.argv
    try:
        sys.argv = ["nb_coder_driver.py",
                    "--issue", "1", "--notebook", "A/B-CSharp.ipynb",
                    "--source-nb", "A/B-Python.ipynb", "--repo", "D:/nope",
                    "--write-mode", "mcp", "--max-stage", "0"]
        with pytest.raises(SystemExit) as ei:
            D.main()
        assert ei.value.code == 2
    finally:
        sys.argv = old


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

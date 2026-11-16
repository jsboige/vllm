"""Regression pins for the per-cell outputs fingerprint (vllm#440, merged in #445).

The gate that rejected a correct deliverable was the INSTRUMENT, not the notebook: the
old `outputs_digest` hashed the raw outputs list, so a stream payload re-chunked by the
kernel (['a','b'] vs ['ab']) read as a content change. A verifier told "same sha =
untouched" then rejected an unedited cell. Measured on the 26789 pair (po-2028, 16/11):
the old digest flagged cells 14, 20 and 22 — 20 was purely a buffer split.

These pins also FIX the deliberate design choice of #445: the signed zero is NOT
normalised in the instrument. `+0.000000` and `-0.000000` stay different on purpose —
both texts are handed to the verifier so it can arbitrate, rather than being masked by
a normaliser. `test_signed_zero_is_deliberately_not_normalised` exists so nobody
"fixes" that silently.

Skipped when `mcp` is not importable (the module imports the MCP client at load).
"""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nb_coder_verify as v  # noqa: E402


def _nb(tmp_path: Path, cells: list, name: str) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps({"cells": cells, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
    return p


def _code(outputs: list, source: str = "x") -> dict:
    return {"cell_type": "code", "source": source, "outputs": outputs, "metadata": {},
            "execution_count": 1}


def _stream(text, name: str = "stdout") -> dict:
    return {"output_type": "stream", "name": name, "text": text}


# --------------------------------------------------------------- digest


def test_stream_chunking_is_not_a_change(tmp_path):
    """A stdout payload split differently by the kernel is the same text (cell 20 of 26789)."""
    a = _nb(tmp_path, [_code([_stream("abc\ndef\n")])], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream("abc\ndef\n")])], "b.ipynb")
    b_cells = json.loads(b.read_text(encoding="utf-8"))
    b_cells["cells"][0]["outputs"] = [_stream("ab"), _stream("c\nde"), _stream("f\n")]
    b.write_text(json.dumps(b_cells), encoding="utf-8")
    da, db = v.outputs_digest(a)[0], v.outputs_digest(b)[0]
    assert da["sha"] == db["sha"], "the fingerprint must not move on a buffer boundary"
    assert da["bytes"] == db["bytes"]
    # `n` is the RAW block count, kept for information only — it legitimately differs, and
    # nothing may key a verdict on it (the sha is the fingerprint).
    assert (da["n"], db["n"]) == (1, 3)


def test_a_real_change_is_still_seen(tmp_path):
    """The fingerprint must never be constant."""
    a = _nb(tmp_path, [_code([_stream("value 0.100000\n")])], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream("value 0.200000\n")])], "b.ipynb")
    assert v.outputs_digest(a) != v.outputs_digest(b)


def test_signed_zero_is_deliberately_not_normalised(tmp_path):
    """DECISION PIN (#445 comment: "ca se decide, ca ne se glisse pas").

    numpy prints +0.0 or -0.0 depending on the rounding path. The instrument keeps them
    DIFFERENT on purpose: the verifier receives both texts and arbitrates. If someone
    later normalises it, this test must fail so the choice is re-argued, not slipped in.
    """
    a = _nb(tmp_path, [_code([_stream("x  +0.000000\n")])], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream("x  -0.000000\n")])], "b.ipynb")
    assert v.outputs_digest(a) != v.outputs_digest(b)


def test_digest_row_shape_is_stable(tmp_path):
    """The prompt annex and any consumer key on these four fields."""
    nb = _nb(tmp_path, [_code([_stream("a\n")])], "a.ipynb")
    row = v.outputs_digest(nb)[0]
    assert set(row) == {"cell", "n", "types", "bytes", "sha"}
    assert row["types"] == ["stream"]


# --------------------------------------------------------------- cell_diffs


def test_edited_cell_is_labelled_edited(tmp_path):
    """Cell 22 of 26789: the issue asked for the edit, so its output MUST change."""
    a = _nb(tmp_path, [_code([_stream("old\n")], source="print(1)")], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream("new\n")], source="print(2)")], "b.ipynb")
    d = v.cell_diffs(a, b)
    assert [x["kind"] for x in d] == ["edited"]


def test_unchanged_code_with_changed_output_is_labelled_outputs_changed(tmp_path):
    """Cell 2 of 26820: same code, only `python 3.13.15` -> `3.13.16`. The verifier must
    see the text to judge it as an interpreter drift, not as an alteration."""
    a = _nb(tmp_path, [_code([_stream("python     : 3.13.15\n")], source="import sys")], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream("python     : 3.13.16\n")], source="import sys")], "b.ipynb")
    d = v.cell_diffs(a, b)
    assert [x["kind"] for x in d] == ["outputs-changed"]
    assert "3.13.15" in d[0]["src_text"] and "3.13.16" in d[0]["built_text"]


def test_identical_cells_produce_no_diff(tmp_path):
    a = _nb(tmp_path, [_code([_stream("same\n")])], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream("sa"), _stream("me\n")])], "b.ipynb")
    assert v.cell_diffs(a, b) == []


def test_added_and_removed_cells_are_labelled(tmp_path):
    keep = _code([_stream("k\n")])
    extra = _code([_stream("e\n")])
    a = _nb(tmp_path, [keep], "a.ipynb")
    b = _nb(tmp_path, [keep, extra], "b.ipynb")
    assert [x["kind"] for x in v.cell_diffs(a, b)] == ["added"]
    assert [x["kind"] for x in v.cell_diffs(b, a)] == ["removed"]


def test_diff_text_is_bounded(tmp_path):
    """A divergent cell must not inflate the verifier prompt without limit."""
    big = "x" * 5000
    a = _nb(tmp_path, [_code([_stream(big)])], "a.ipynb")
    b = _nb(tmp_path, [_code([_stream(big[:-1] + "y")])], "b.ipynb")
    d = v.cell_diffs(a, b)
    assert all(len(x["src_text"]) <= v.CELL_TEXT_CAP + 1 for x in d)
    assert all(len(x["built_text"]) <= v.CELL_TEXT_CAP + 1 for x in d)


# ------------------------------------------------- worktree organ (vllm#455 review)


def _git_repo(p: Path) -> Path:
    """A real one-commit repo — no mock: the organ shells out to `git` and that IS the code."""
    import subprocess
    p.mkdir(parents=True, exist_ok=True)
    for cmd in (["init", "-q"], ["-c", "user.name=nb", "-c", "user.email=nb@x",
                                 "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    return p


def test_reused_worktree_reports_ok_true(tmp_path):
    """The branch that used to omit `ok` entirely: a healthy reuse must say so, or the
    call-site guard refuses it (a false positive, and a guard that cries wolf gets removed)."""
    dest = _git_repo(tmp_path / "wt")
    wt = v.nbcd.prepare_worktree(tmp_path / "unused", dest, fresh=False)
    assert wt["reused"] is True
    assert wt["ok"] is True and wt["err"] is None
    assert v.nbcd.worktree_refusal(wt) is None


def test_failed_worktree_reports_ok_false_with_the_error(tmp_path):
    """No origin/main in a bare tmp repo: `worktree add` fails, and the reason must survive."""
    repo = _git_repo(tmp_path / "repo")          # has HEAD, has no origin/main
    wt = v.nbcd.prepare_worktree(repo, tmp_path / "wt", fresh=True)
    assert wt["ok"] is False
    assert wt["err"]
    ref = v.nbcd.worktree_refusal(wt)
    assert ref and ref.startswith("worktree-failed:")


def test_absent_ok_is_not_a_refusal(tmp_path):
    """Tri-state: `is False` fails, absent passes. This is the exact dict the pre-contract
    organ returned for a HEALTHY reuse — refusing it is the bug being pinned."""
    assert v.nbcd.worktree_refusal({"path": "x", "reused": True, "head": "abc"}) is None


# ------------------------------------------------- agent wiring (vllm#455 review)


def _cfg(tmp_path: Path, ids: list) -> Path:
    p = tmp_path / "sk-agent.config.json"
    p.write_text(json.dumps({"agents": [{"id": i, "model": "m"} for i in ids],
                             "models": [{"id": "m", "api_key_env": None}]}), encoding="utf-8")
    return p


def test_a_known_agent_is_not_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(v.nbcd, "SK_CONFIG", _cfg(tmp_path, ["fast-local", "notebook-coder-minimax"]))
    assert v.nbcd.unknown_agent("fast-local") is None


def test_a_typo_is_refused_and_lists_the_real_ids(tmp_path, monkeypatch):
    """sk-agent falls back to `get_default_agent()` on an unknown id — a DIFFERENT model
    runs after the claim is paid (ai-01:vllm, 16/11). The refusal must name the typo and
    show what exists, or the operator keeps guessing."""
    monkeypatch.setattr(v.nbcd, "SK_CONFIG", _cfg(tmp_path, ["fast-local", "notebook-coder-minimax"]))
    ref = v.nbcd.unknown_agent("notebook-coder-minmax")
    assert ref and "notebook-coder-minmax" in ref
    assert "notebook-coder-minimax" in ref


def test_a_model_suffix_does_not_look_like_a_typo(tmp_path, monkeypatch):
    """`agent[model]` is legal; only the base id is looked up — a false refusal here would
    block a working invocation."""
    monkeypatch.setattr(v.nbcd, "SK_CONFIG", _cfg(tmp_path, ["fast-local"]))
    assert v.nbcd.unknown_agent("fast-local[glm-5.3]") is None


def test_an_unreadable_config_accuses_nobody(tmp_path, monkeypatch):
    """The path check owns that failure; a second, less precise refusal would only muddy it."""
    missing = tmp_path / "absent.json"
    monkeypatch.setattr(v.nbcd, "SK_CONFIG", missing)
    assert v.nbcd.unknown_agent("whatever") is None


def test_the_preflight_actually_calls_it():
    """A correct refusal that `_preflight` never calls protects nothing.

    `_preflight` is not reachable from a unit test without argparse + a full seat, so the
    pin reads the CALL SITE in the source — the same pattern the grain tag uses.
    """
    src = Path(v.nbcd.__file__).read_text(encoding="utf-8")
    assert "unknown_agent(args.agent)" in src, "the preflight no longer refuses a ghost agent"

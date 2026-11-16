"""Regression pins for the per-cell outputs fingerprint (vllm#440).

The gate that rejected a correct deliverable was the INSTRUMENT, not the notebook:
`outputs_digest` hashed the raw outputs list, so a stream payload re-chunked by the
kernel (['a','b'] vs ['ab']) and a printed zero carrying the other sign (+0.000000 vs
-0.000000) both read as content drift. A verifier told "same sha = untouched" then
rejected an unedited cell.

Measured on the 26789 pair (po-2028, 16/11): the old digest flagged cells 14, 20 and
22; the canonical one flags only 22 — the cell the plan actually edited.

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


def _code(outputs: list) -> dict:
    return {"cell_type": "code", "source": "x", "outputs": outputs, "metadata": {},
            "execution_count": 1}


def test_stream_chunking_is_not_a_change(tmp_path):
    """A stdout payload split differently by the kernel is the same text."""
    a = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "abc\ndef\n"}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": ["ab", "c\nde", "f\n"]}])], "b.ipynb")
    assert v.outputs_digest(a) == v.outputs_digest(b)


def test_signed_zero_is_not_a_change(tmp_path):
    """+0.000000 and -0.000000 print the same value; numpy picks the sign."""
    a = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "x  +0.000000\n"}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "x  -0.000000\n"}])], "b.ipynb")
    assert v.outputs_digest(a) == v.outputs_digest(b)


def test_a_real_change_is_still_seen(tmp_path):
    """The normalisation must never turn the fingerprint constant."""
    a = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "value 0.100000\n"}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "value 0.200000\n"}])], "b.ipynb")
    assert v.outputs_digest(a) != v.outputs_digest(b)


def test_nonzero_numbers_keep_their_sign():
    """`-0.5` is negative, `4012` is a number: neither may be rewritten."""
    assert v._norm_text("-0.5") == "-0.5"
    assert v._norm_text("4012") == "4012"
    assert v._norm_text("took 1401 ms") == "took 1401 ms"
    assert v._norm_text("-0.000000") == "0.000000"
    assert v._norm_text("+0.") == "0."


def test_image_payload_is_hashed_raw(tmp_path):
    """A non-text payload still counts: an image that changed must be seen."""
    a = _nb(tmp_path, [_code([{"output_type": "display_data", "data": {"image/png": "AAA"}, "metadata": {}}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "display_data", "data": {"image/png": "BBB"}, "metadata": {}}])], "b.ipynb")
    assert v.outputs_digest(a) != v.outputs_digest(b)


def test_diff_is_empty_when_only_the_chunking_differs(tmp_path):
    """No divergence to judge → no block in the prompt."""
    a = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "abc\n"}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": ["a", "bc\n"]}])], "b.ipynb")
    assert v.outputs_diff(a, b) == ""


def test_diff_shows_both_sides_so_the_model_can_judge(tmp_path):
    """The measured 26820 case: an unedited cell whose only change is the interpreter
    version. The digest can only say 'different'; this text lets the verifier see that
    nothing computed changed."""
    a = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "python     : 3.13.15\nnumpy      : 2.5.2\n"}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": "python     : 3.13.16\nnumpy      : 2.5.2\n"}])], "b.ipynb")
    assert v.outputs_digest(a) != v.outputs_digest(b)
    d = v.outputs_diff(a, b)
    assert "cell 0" in d
    assert "3.13.15" in d and "3.13.16" in d


def test_diff_is_bounded(tmp_path):
    """A huge divergent cell must not inflate the verifier prompt."""
    big = "x" * 5000
    a = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": big}])], "a.ipynb")
    b = _nb(tmp_path, [_code([{"output_type": "stream", "name": "stdout", "text": big[:-1] + "y"}])], "b.ipynb")
    d = v.outputs_diff(a, b, max_chars=200)
    assert "car.)" in d and len(d) < 1200

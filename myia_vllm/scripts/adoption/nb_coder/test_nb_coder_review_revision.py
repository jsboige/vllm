"""Offline tests: only the model, Papermill transport and Git boundary are replaced."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nb_coder_driver as d  # noqa: E402


@pytest.mark.parametrize("case", ["approve", "reject", "scope", "mixed", "no-op",
                                  "gate", "stale", "verify-error", "write-error", "tamper"])
def test_review_revision(tmp_path, monkeypatch, case):
    before = {"metadata": {"language_info": {"version": "3"}}, "cells": [
        {"cell_type": "markdown", "source": "first draft"},
        {"cell_type": "code", "source": "print(1)", "execution_count": 1,
         "outputs": [{"output_type": "stream", "name": "stdout", "text": "1\n"}]}]}
    src, built = tmp_path / "source.ipynb", tmp_path / "built.ipynb"
    src.write_text(json.dumps({**before, "cells": [
        {"cell_type": "markdown", "source": "original"}, before["cells"][1]]}))
    built.write_text(json.dumps(before))
    initial = built.read_bytes()
    args = SimpleNamespace(issue=99, verifier_agent="verifier", verify_timeout=1, review_rounds=1,
                           notebook="delivery.ipynb", pr_branch="test")
    rec = {"built_notebook": {"path": str(built)}}
    events = []
    findings = [{"kind": "prose", "severity": "major", "cell": 0, "detail": "Clarify wording"}]
    if case == "mixed":
        findings.append({"kind": "output", "severity": "major", "cell": 1, "detail": "Wrong output"})
    (tmp_path / "verify-99.json").write_text('{"verdict":"approve"}')

    def verify(cmd, **kwargs):
        assert cmd[1].endswith("nb_coder_verify.py")
        draft = Path(cmd[cmd.index("--built-nb") + 1])
        log = Path(cmd[cmd.index("--out-dir") + 1])
        events.append("verify-first" if draft == built else "verify-new")
        assert log != tmp_path
        if (case == "verify-error" and draft == built) or (case == "stale" and draft != built):
            return subprocess.CompletedProcess(cmd, 0, "", "")
        approve = draft != built and case != "reject"
        (log / "verify-99.json").write_text(json.dumps({
            "verdict": "approve" if approve else "reject", "answer": {"findings": findings}}))
        return subprocess.CompletedProcess(cmd, 0 if approve else 1, "", "")

    async def propose(args, rec, prompt):
        events.append("propose")
        assert "Clarify wording" in prompt and "first draft" in prompt
        return {"response": json.dumps({"cells": [{
            "idx": 1 if case == "scope" else 0,
            "source": "first draft" if case == "no-op" else "revised wording"}]})}

    async def write(params, path, patch):
        events.append("write")
        assert path != built and path.read_bytes() == initial
        nb = json.loads(path.read_bytes())
        nb["cells"][0]["source"] = [patch[0]]
        if case == "write-error":
            nb["cells"][1]["outputs"] = []
        path.write_text(json.dumps(nb))  # simulator for the Papermill writer
        return True

    real_gates = d.run_gates

    def gates(*a, **kw):
        events.append("gates")
        return real_gates(*a, **kw) + [{"gate": "fixture", "ok": case != "gate"}]

    monkeypatch.setattr(d.subprocess, "run", verify)
    monkeypatch.setattr(d, "propose_review_prose", propose)
    monkeypatch.setattr(d, "write_review_prose", write)
    monkeypatch.setattr(d, "run_gates", gates)
    final = asyncio.run(d.review_and_revise(args, rec, src, built, tmp_path, None,
                                           {"title": "clarify"}, False))
    assert built.read_bytes() == initial
    assert events[0] == "verify-first"
    if case in {"approve", "reject", "stale", "tamper"}:
        assert events == ["verify-first", "propose", "write", "gates", "verify-new"]
        assert len({r["sha256"] for r in rec["review_history"]}) == 2
        assert len({r["out_dir"] for r in rec["review_history"]}) == 2
        assert json.loads(final.read_bytes())["cells"][1] == before["cells"][1]
    elif case == "gate":
        assert events[-1] == "gates"
    else:
        assert "gates" not in events
    if case in {"mixed", "verify-error"}:
        assert events == ["verify-first"]
    if case in {"scope", "no-op"}:
        assert "write" not in events
    if case == "tamper":
        final.write_bytes(initial)
    git_calls = []
    monkeypatch.setattr(d, "_git", lambda *a: (git_calls.append(a), (-1, "stop here"))[1])
    verdict = rec["verdict"]
    d.stage5_pr(args, rec, tmp_path, final, {}, None)
    assert bool(git_calls) == (case == "approve")
    if case in {"tamper", "verify-error", "stale"}:
        assert rec["verdict"] == "verify-error"
    elif case != "approve":
        assert rec["verdict"] == verdict
    if case in {"reject", "mixed", "scope", "no-op", "gate"}:
        assert rec["verdict"] == "verify-reject"

#!/usr/bin/env python3
"""Offline tests for halving a repair round whose answer was cut — #27134 (2.3d), 2026-11-21.

The repair of 2.3d asked six cells at once. The call ran 644.7 s, past the model's 600 s
request budget, and the answer stopped in the middle of a cell source (31,654 chars, no
error raised): nothing parsed, the loop broke and the grain was lost. The build stage
already halves a tranche on exactly these two failures (#517); a repair round now does
the same, once, and keeps whatever half parses."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("nb_coder_driver", HERE / "nb_coder_driver.py")
d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d)

ERR = "\x1b[31m[E0308] Error:\x1b[0m mismatched types\n"
CUT = '```json\n{"cells": [{"idx": 1, "cell_type": "code", "source": "let k: u16 = 3'


def _code(src: str, err: str | None = None) -> dict:
    c = {"cell_type": "code", "metadata": {}, "source": src, "execution_count": None,
         "outputs": []}
    if err is not None:
        c["outputs"] = [{"output_type": "stream", "name": "stderr", "text": err},
                        {"output_type": "error", "ename": "Error",
                         "evalue": "compilation error", "traceback": []}]
    return c


def _notebook(n_failing: int = 4) -> list[dict]:
    cells = [{"cell_type": "markdown", "metadata": {}, "source": "# Titre"}]
    cells += [_code(f"let k{i}: u8 = 300u16;", ERR) for i in range(n_failing)]
    cells.append(_code("let ok = 1;"))
    return cells


def _fix(i: int) -> dict:
    return {"idx": i, "cell_type": "code", "source": f"let k{i - 1}: u16 = 300u16;"}


def _run_round(tmp_path, monkeypatch, cells, answers):
    """`answers` maps the stage suffix ('', '+h0', '+h1') to (response, parsed cells)."""
    nb = tmp_path / "nb.ipynb"
    nb.write_text(json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                              "nbformat_minor": 5}), encoding="utf-8")
    calls, executed = [], []

    def key(stage):
        return stage.split("+0", 1)[1]

    async def fake_retry(sk, args, rec, stage, prompt, conv, max_tokens=None):
        calls.append((key(stage), prompt))
        resp, _ = answers[key(stage)]
        return {"conversation_id": "c1", "response": resp, "error": None}

    async def fake_parse(sk, args, rec, stage, env, conv, max_tokens=None):
        _, parsed = answers[key(stage)]
        return ({"cells": parsed} if parsed else None), env

    async def fake_pm(pm, name, payload):
        return {}

    async def fake_start(pm, kname, exec_dir):
        return "k2"

    async def fake_exec(pm, path, kid, targets):
        executed.append(list(targets))
        return [{"cell": i, "ok": True} for i in targets]

    monkeypatch.setattr(d, "sk_call_retry", fake_retry)
    monkeypatch.setattr(d, "parse_or_repair", fake_parse)
    monkeypatch.setattr(d, "pm_call", fake_pm)
    monkeypatch.setattr(d, "start_kernel", fake_start)
    monkeypatch.setattr(d, "execute_cells", fake_exec)
    targets = [i for i, c in enumerate(cells) if c["cell_type"] == "code"]
    rec = {"execution": [{"cell": i, "ok": not cells[i]["outputs"]} for i in targets]}
    asyncio.run(d.repair_kernel_errors(None, None, SimpleNamespace(repair_rounds=1), rec, nb,
                                       "csharp", tmp_path, "k1", targets, None, ""))
    return calls, rec["repairs"][0], executed, json.loads(nb.read_text(encoding="utf-8"))


# ---- repair_bisect_cause ---------------------------------------------------------------
def test_cause_names_the_two_failures_a_smaller_request_cures():
    assert d.repair_bisect_cause({"response": CUT, "error": None}) == "truncated"
    assert d.repair_bisect_cause({"response": "", "error": "APITimeoutError: x"}) == "timeout"
    assert d.repair_bisect_cause({"response": "```json\n{}\n```", "error": None}) == ""
    assert d.repair_bisect_cause({"response": "", "error": "401 invalid proxy "
                                  "authentication"}) == ""
    assert d.repair_bisect_cause({"response": "", "error": "capacity gate refused "
                                  "dispatch (verdict red); retry after 60s"}) == ""


# ---- a repair round --------------------------------------------------------------------
def test_a_cut_answer_is_asked_again_in_two_halves_and_both_apply(tmp_path, monkeypatch):
    answers = {"": (CUT, None), "+h0": ("ok}", [_fix(1), _fix(2)]),
               "+h1": ("ok}", [_fix(3), _fix(4)])}
    calls, r, executed, nb = _run_round(tmp_path, monkeypatch, _notebook(), answers)
    assert [c[0] for c in calls] == ["", "+h0", "+h1"]
    h0, h1 = calls[1][1], calls[2][1]
    assert "### Cellule 1 (code)" in h0 and "### Cellule 2 (code)" in h0
    assert "### Cellule 3 (code)" not in h0 and "### Cellule 4 (code)" in h1
    assert "### Cellule 1 (code)" not in h1
    assert r["asked"] == 4 and r["replaced"] == [1, 2, 3, 4]
    assert r["bisect"]["cause"] == "truncated"
    assert [h["asked"] for h in r["bisect"]["halves"]] == [[1, 2], [3, 4]]
    assert all("verdict" not in h for h in r["bisect"]["halves"])
    assert executed == [[1, 2, 3, 4, 5]]
    assert "".join(nb["cells"][1]["source"]) == "let k0: u16 = 300u16;"


def test_a_half_that_fails_does_not_lose_the_other(tmp_path, monkeypatch):
    answers = {"": ("", None), "+h0": (CUT, None), "+h1": ("ok}", [_fix(3), _fix(4)])}
    monkeypatch.setattr(d, "call_timed_out", lambda env: not env.get("response"))
    calls, r, executed, _ = _run_round(tmp_path, monkeypatch, _notebook(), answers)
    assert r["bisect"]["cause"] == "timeout"
    assert r["replaced"] == [3, 4]
    assert r["bisect"]["halves"][0]["verdict"] == "truncated"
    assert executed == [[1, 2, 3, 4, 5]]


def test_both_halves_failing_ends_the_loop_named(tmp_path, monkeypatch):
    answers = {"": (CUT, None), "+h0": (CUT, None), "+h1": (CUT, None)}
    calls, r, executed, _ = _run_round(tmp_path, monkeypatch, _notebook(), answers)
    assert r["verdict"] == "bisect-truncated"
    assert [h["verdict"] for h in r["bisect"]["halves"]] == ["truncated", "truncated"]
    assert executed == []


def test_a_single_cell_is_never_halved(tmp_path, monkeypatch):
    answers = {"": (CUT, None)}
    calls, r, executed, _ = _run_round(tmp_path, monkeypatch, _notebook(1), answers)
    assert [c[0] for c in calls] == [""]
    assert r["verdict"] == "unparsed" and "bisect" not in r


def test_a_wrong_but_complete_answer_is_not_halved(tmp_path, monkeypatch):
    """A fenced answer that does not parse is the format repair's business, not ours."""
    answers = {"": ("```json\n{nope}\n```", None)}
    calls, r, _, _ = _run_round(tmp_path, monkeypatch, _notebook(), answers)
    assert [c[0] for c in calls] == [""] and "bisect" not in r


def test_held_cells_follow_the_half_that_asks_their_root(tmp_path, monkeypatch):
    halves = d._repair_halves
    seen = {}

    async def spy(sk, args, rec, stage, detail, conventions, upstream, deferred,
                  crate_api, conv):
        seen["deferred"] = deferred
        return await halves(sk, args, rec, stage, detail, conventions, upstream, deferred,
                            crate_api, conv)

    async def fake_retry(sk, args, rec, stage, prompt, conv, max_tokens=None):
        seen.setdefault("prompts", []).append(prompt)
        return {"conversation_id": "c1", "response": "ok}", "error": None}

    async def fake_parse(sk, args, rec, stage, env, conv, max_tokens=None):
        return {"cells": [{"idx": 1, "cell_type": "code", "source": "x"}]}, env

    monkeypatch.setattr(d, "sk_call_retry", fake_retry)
    monkeypatch.setattr(d, "parse_or_repair", fake_parse)
    detail = [{"idx": 1, "source": "a", "errors": ERR, "cited": []},
              {"idx": 4, "source": "b", "errors": ERR, "cited": []}]
    deferred = [{"idx": 2, "roots": [1], "names": ["f"], "crates": []},
                {"idx": 5, "roots": [4], "names": ["g"], "crates": []}]
    upstream = [{"idx": 0, "names": ["h"], "for": 4, "via": "use", "source": "fn h() {}"}]
    part, conv, rec = asyncio.run(d._repair_halves(None, None, {}, "s", detail, "", upstream,
                                                   deferred, "", None))
    assert [h["deferred"] for h in rec["halves"]] == [[2], [5]]
    assert [h["upstream"] for h in rec["halves"]] == [[], [0]]
    p0, p1 = seen["prompts"]
    assert "CELLULES EN ATTENTE (2)" in p0 and "CELLULES EN ATTENTE (5)" in p1
    assert len(part["cells"]) == 2

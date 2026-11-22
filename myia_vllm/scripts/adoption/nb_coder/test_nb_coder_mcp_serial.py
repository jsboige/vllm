"""--write-mode mcp-serial: every harness write through the papermill MCP, serialized, each
one proved (CoursIA ASK 22/11 11:18Z: "un flux de création via MCP sérialisé, avec test de
concurrence et preuve qu'aucune cellule ni sortie n'est perdue").

Two layers:
  * unit (always run when `mcp` imports): the readback comparison `nb_diff`, the
    compare-and-swap of `McpNbStore.write` on a fake server, the unwrapping of
    `NbWriteError` out of the ExceptionGroups the MCP task groups add, and the json mode
    left byte-identical;
  * live (NBCODER_MCP_SERIAL_LIVE=1 + the papermill interpreter present): the REAL server.
    (i) 6 writers on 6 distinct notebooks, through one session and through 6 sessions
    (6 grains) at once, 0 cell and 0 output lost; (ii) a second writer provoked on purpose
    between the read and the write, refused and never merged; a markdown attachment the
    server drops, caught by the readback; (iii) the same applier sequence in json mode and
    in mcp-serial mode, same notebook once parsed, byte differences recorded.
    NBCODER_MCP_SERIAL_LOG=<file> appends one JSON line per live proof (the PR's evidence).
"""
import difflib
import importlib.util
import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")

_DRV = Path(__file__).resolve().parent / "nb_coder_driver.py"
_spec = importlib.util.spec_from_file_location("nbcd_mcp_serial", _DRV)
nbcd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nbcd)

CRLF = bytes([13, 10])
LIVE = (os.environ.get("NBCODER_MCP_SERIAL_LIVE") == "1" and Path(nbcd.PM_PY).is_file()
        and Path(nbcd.PM_CWD).is_dir())
live = pytest.mark.skipif(not LIVE, reason="NBCODER_MCP_SERIAL_LIVE=1 and the papermill "
                                           "interpreter are needed for the real server")


def _evidence(name: str, **facts) -> None:
    log = os.environ.get("NBCODER_MCP_SERIAL_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"proof": name, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                    time.gmtime()), **facts},
                               ensure_ascii=False) + "\n")


def _fixture_nb() -> dict:
    """A notebook with every field the harness must never lose: code with stream,
    execute_result (multiline data as a list), display_data (image), error
    outputs; markdown; raw; ids; cell and notebook metadata; one cell without an id."""
    return {
        "cells": [
            {"cell_type": "markdown", "id": "md000001", "metadata": {"tags": ["intro"]},
             "source": ["# Titre\n", "\n", "Texte avec accents : é à ç — ✓\n"]},
            {"cell_type": "code", "execution_count": 1, "id": "code0001",
             "metadata": {"trusted": True, "collapsed": False},
             "outputs": [{"name": "stdout", "output_type": "stream",
                          "text": ["ligne 1\n", "ligne 2\n"]}],
             "source": ["x = 40 + 2\n", "print('ligne 1'); print('ligne 2')"]},
            {"cell_type": "code", "execution_count": 2, "id": "code0002", "metadata": {},
             "outputs": [{"data": {"text/plain": ["42\n", "suite"]}, "execution_count": 2,
                          "metadata": {}, "output_type": "execute_result"},
                         {"data": {"image/png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAA"
                                                 "fFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                                   "text/plain": ["<Figure>"]},
                          "metadata": {"image/png": {"width": 1}},
                          "output_type": "display_data"}],
             "source": "x"},
            {"cell_type": "code", "execution_count": 3, "id": "code0003", "metadata": {},
             "outputs": [{"ename": "ZeroDivisionError", "evalue": "division by zero",
                          "output_type": "error",
                          "traceback": ["Traceback...", "ZeroDivisionError: division by zero"]}],
             "source": ["1/0"]},
            {"cell_type": "raw", "id": "raw00001", "metadata": {}, "source": ["brut"]},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
             "source": ["# a cell written without an id"]},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                    "name": "python3"},
                     "language_info": {"name": "python", "version": "3.12.0"}},
        "nbformat": 4, "nbformat_minor": 5,
    }


def _dump_json(p: Path, nb: dict) -> None:
    p.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ unit: the readback check
def _as_nbformat_writes(nb: dict) -> dict:
    """What nbformat's writer does to a notebook, by hand: str sources, transient and
    `trusted` dropped, an id added where none was, minor raised."""
    out = json.loads(json.dumps(nb))
    for i, c in enumerate(out["cells"]):
        c["source"] = "".join(c["source"]) if isinstance(c["source"], list) else c["source"]
        c.setdefault("id", f"added{i:03d}")
        c["metadata"].pop("trusted", None)
        for o in c.get("outputs") or []:
            o.pop("transient", None)
            if isinstance(o.get("text"), list):
                o["text"] = "".join(o["text"])
            for m, v in list((o.get("data") or {}).items()):
                if isinstance(v, list):
                    o["data"][m] = "".join(v)
    out["nbformat_minor"] = max(out.get("nbformat_minor", 0), 5)
    return out


def test_nb_diff_tolerates_only_what_nbformat_writes():
    sent = _fixture_nb()
    sent["nbformat_minor"] = 4
    sent["cells"][2]["outputs"][1]["transient"] = {"display_id": "abc"}   # a message key
    diffs, notes = nbcd.nb_diff(sent, _as_nbformat_writes(sent))
    assert diffs == []
    assert "cell 5 id added" in notes and "nbformat_minor 4->5" in notes


@pytest.mark.parametrize("damage, expected", [
    (lambda d: d["cells"].pop(), "cells 6->5"),
    (lambda d: d["cells"][1].__setitem__("source", "x = 0"), "cell 1 source"),
    (lambda d: d["cells"][1].__setitem__("outputs", []), "cell 1 outputs"),
    (lambda d: d["cells"][2]["outputs"][1]["data"].pop("image/png"), "cell 2 outputs"),
    (lambda d: d["cells"][2].__setitem__("execution_count", None), "cell 2 execution_count"),
    (lambda d: d["cells"][0].__setitem__("metadata", {}), "cell 0 metadata"),
    (lambda d: d["cells"][0].__setitem__("id", "other"), "cell 0 id"),
    (lambda d: d["cells"][4].__setitem__("cell_type", "markdown"), "cell 4 cell_type"),
    (lambda d: d["metadata"].pop("kernelspec"), "notebook metadata"),
    (lambda d: d.__setitem__("nbformat_minor", 4), "nbformat_minor 5->4"),
])
def test_nb_diff_catches_every_loss(damage, expected):
    sent = _fixture_nb()
    disk = _as_nbformat_writes(sent)
    damage(disk)
    diffs, _ = nbcd.nb_diff(sent, disk)
    assert expected in diffs


def test_nb_diff_catches_a_dropped_attachment():
    sent = _fixture_nb()
    sent["cells"][0]["attachments"] = {"a.png": {"image/png": "iVBORw0KGgo="}}
    disk = _as_nbformat_writes(sent)
    disk["cells"][0].pop("attachments")
    assert "cell 0 attachments" in nbcd.nb_diff(sent, disk)[0]


# ------------------------------------------------------------------ unit: compare-and-swap
class _FakeServer:
    """write_notebook as nbformat would persist it (sorted keys, str sources), or damaged."""

    def __init__(self, damage=None, answer=None):
        self.damage, self.answer, self.calls = damage, answer, 0

    def __call__(self, tool, payload):
        self.calls += 1
        if self.answer is not None:
            return self.answer
        disk = _as_nbformat_writes(payload["content"])
        if self.damage:
            self.damage(disk)
        Path(payload["path"]).write_text(json.dumps(disk, sort_keys=True, indent=1,
                                                    ensure_ascii=False) + "\n",
                                         encoding="utf-8")
        return {"path": payload["path"], "success": True}


def _store(monkeypatch, server):
    st = object.__new__(nbcd.McpNbStore)
    st._lock, st._seen, st.writes, st.log = threading.Lock(), {}, 0, []
    st.call = server
    monkeypatch.setattr(nbcd, "_NB_STORE", st)
    return st


def test_json_mode_writes_the_bytes_it_always_wrote(tmp_path, monkeypatch):
    monkeypatch.setattr(nbcd, "_NB_STORE", None)
    p = tmp_path / "a.ipynb"
    nb = _fixture_nb()
    nbcd.nb_dump(p, nb)
    ref = tmp_path / "ref.ipynb"                # the pre-mcp-serial write, CRLF on Windows
    ref.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert p.read_bytes() == ref.read_bytes()


def test_a_proved_write_passes_and_is_logged(tmp_path, monkeypatch):
    p = tmp_path / "a.ipynb"
    _dump_json(p, _fixture_nb())
    st = _store(monkeypatch, _FakeServer())
    nb = nbcd.nb_load(p)
    nb["cells"][1]["source"] = ["x = 1\n"]
    nbcd.nb_dump(p, nb)
    assert st.writes == 1 and st.log[0]["cells"] == 6
    assert "cell 5 id added" in st.log[0]["normalized"]
    nb2 = nbcd.nb_load(p)                       # the next RMW starts from the proved bytes
    nbcd.nb_dump(p, nb2)
    assert st.writes == 2


def test_second_writer_between_read_and_write_is_refused_never_merged(tmp_path, monkeypatch):
    p = tmp_path / "a.ipynb"
    _dump_json(p, _fixture_nb())
    srv = _FakeServer()
    st = _store(monkeypatch, srv)
    nb = nbcd.nb_load(p)
    other = _fixture_nb()
    other["cells"].append({"cell_type": "markdown", "id": "second01", "metadata": {},
                           "source": ["written by someone else"]})
    _dump_json(p, other)                        # the second writer
    theirs = p.read_bytes()
    nb["cells"][1]["source"] = ["mine\n"]
    with pytest.raises(nbcd.NbWriteError) as ei:
        nbcd.nb_dump(p, nb)
    assert ei.value.kind == "conflict"
    assert p.read_bytes() == theirs and srv.calls == 0 and st.writes == 0


def test_writing_a_notebook_never_read_is_refused(tmp_path, monkeypatch):
    p = tmp_path / "a.ipynb"
    _dump_json(p, _fixture_nb())
    _store(monkeypatch, _FakeServer())
    with pytest.raises(nbcd.NbWriteError) as ei:
        nbcd.nb_dump(p, _fixture_nb())
    assert ei.value.kind == "unseen"


def test_a_new_notebook_needs_no_base(tmp_path, monkeypatch):
    st = _store(monkeypatch, _FakeServer())
    nbcd.nb_dump(tmp_path / "new.ipynb", {"cells": [], "metadata": {}, "nbformat": 4,
                                          "nbformat_minor": 5})
    assert st.writes == 1


def test_a_server_that_loses_a_cell_is_caught_by_the_readback(tmp_path, monkeypatch):
    p = tmp_path / "a.ipynb"
    _dump_json(p, _fixture_nb())
    _store(monkeypatch, _FakeServer(damage=lambda d: d["cells"].pop(2)))
    nb = nbcd.nb_load(p)
    with pytest.raises(nbcd.NbWriteError) as ei:
        nbcd.nb_dump(p, nb)
    assert ei.value.kind == "readback" and "cells 6->5" in ei.value.detail


def test_a_server_refusal_stops_the_write(tmp_path, monkeypatch):
    p = tmp_path / "a.ipynb"
    _dump_json(p, _fixture_nb())
    _store(monkeypatch, _FakeServer(answer={"error": "boom", "success": False}))
    nb = nbcd.nb_load(p)
    with pytest.raises(nbcd.NbWriteError) as ei:
        nbcd.nb_dump(p, nb)
    assert ei.value.kind == "server"


def test_the_appliers_go_through_the_choke_point(tmp_path, monkeypatch):
    """apply_repairs + normalize_sources, unmodified, under mcp-serial: proved writes."""
    p = tmp_path / "a.ipynb"
    _dump_json(p, _fixture_nb())
    st = _store(monkeypatch, _FakeServer())
    rep = nbcd.apply_repairs(p, {"cells": [{"idx": 1, "source": "y = 2\n"}]})
    assert rep["replaced"] == [1] and st.writes == 1
    assert nbcd.normalize_sources(p) > 0 and st.writes == 2    # nbformat stored str sources
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["cells"][1]["outputs"] == [] and on_disk["cells"][2]["outputs"]


def test_the_write_error_is_found_inside_exception_groups():
    e = nbcd.NbWriteError("conflict", "x")
    assert nbcd.find_nb_write_error(e) is e
    g = ExceptionGroup("tg", [ValueError("a"), ExceptionGroup("inner", [e])])
    assert nbcd.find_nb_write_error(g) is e
    try:
        try:
            raise e
        except nbcd.NbWriteError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert nbcd.find_nb_write_error(outer) is e
    assert nbcd.find_nb_write_error(ValueError("plain")) is None


# ------------------------------------------------------------------ live: the real server
@pytest.fixture
def live_store():
    st = nbcd.McpNbStore()
    yield st
    st.close()


def _rmw_rounds(store_owner_set, p: Path, rounds: int, tag: str) -> None:
    """`rounds` read-modify-writes, each appending one executed-looking code cell."""
    for r in range(rounds):
        nb = nbcd.nb_load(p)
        nb["cells"].append({"cell_type": "code", "execution_count": r + 1,
                            "id": f"{tag}{r:04d}", "metadata": {},
                            "outputs": [{"name": "stdout", "output_type": "stream",
                                         "text": [f"{tag} round {r}\n"]}],
                            "source": [f"print('{tag} round {r}')"]})
        nbcd.nb_dump(p, nb)


def _check_rounds(p: Path, rounds: int, tag: str) -> dict:
    nb = json.loads(p.read_text(encoding="utf-8"))
    mine = [c for c in nb["cells"] if str(c.get("id", "")).startswith(tag)]
    assert [c["id"] for c in mine] == [f"{tag}{r:04d}" for r in range(rounds)]
    for r, c in enumerate(mine):
        assert "".join(c["outputs"][0]["text"]) == f"{tag} round {r}\n"
        assert c["execution_count"] == r + 1
    assert len(nb["cells"]) == len(_fixture_nb()["cells"]) + rounds
    return {"cells": len(nb["cells"]), "outputs": sum(len(c.get("outputs") or [])
                                                      for c in nb["cells"])}


@live
def test_live_i_six_writers_one_session_lose_nothing(tmp_path, monkeypatch, live_store):
    monkeypatch.setattr(nbcd, "_NB_STORE", live_store)
    rounds, paths = 8, [tmp_path / f"w{k}.ipynb" for k in range(6)]
    for p in paths:
        _dump_json(p, _fixture_nb())
    errors: list = []

    def worker(k):
        try:
            _rmw_rounds(None, paths[k], rounds, f"w{k}r")
        except BaseException as exc:            # surfaced below, never swallowed
            errors.append(exc)

    t0 = time.time()
    ts = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == []
    facts = [_check_rounds(p, rounds, f"w{k}r") for k, p in enumerate(paths)]
    assert live_store.writes == 6 * rounds
    _evidence("i-six-writers-one-session", notebooks=6, rounds=rounds,
              writes=live_store.writes, lost_cells=0, lost_outputs=0, per_nb=facts,
              seconds=round(time.time() - t0, 1),
              ms_max=max(e["ms"] for e in live_store.log))


@live
def test_live_i_six_grains_six_sessions_lose_nothing(tmp_path, monkeypatch):
    """Six grains = six driver processes, each with its own session, at the same time.
    `_NB_STORE` is process-global, so each grain is simulated by a thread that drives its
    own store directly through the same nb_load/nb_dump code."""
    rounds, paths = 6, [tmp_path / f"g{k}.ipynb" for k in range(6)]
    for p in paths:
        _dump_json(p, _fixture_nb())
    stores = [nbcd.McpNbStore() for _ in range(6)]
    errors: list = []

    def grain(k):
        st = stores[k]
        try:
            for r in range(rounds):
                b = paths[k].read_bytes()
                st.seen(paths[k], nbcd._nb_sha(b))
                nb = json.loads(b.decode("utf-8"))
                nb["cells"].append({"cell_type": "code", "execution_count": r + 1,
                                    "id": f"g{k}r{r:04d}", "metadata": {},
                                    "outputs": [{"name": "stdout", "output_type": "stream",
                                                 "text": [f"g{k}r round {r}\n"]}],
                                    "source": [f"print('g{k}r round {r}')"]})
                st.write(paths[k], nb)
        except BaseException as exc:
            errors.append(exc)

    t0 = time.time()
    try:
        ts = [threading.Thread(target=grain, args=(k,)) for k in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    finally:
        for st in stores:
            st.close()
    assert errors == []
    facts = [_check_rounds(p, rounds, f"g{k}r") for k, p in enumerate(paths)]
    assert [st.writes for st in stores] == [rounds] * 6
    _evidence("i-six-grains-six-sessions", notebooks=6, sessions=6, rounds=rounds,
              writes=sum(st.writes for st in stores), lost_cells=0, lost_outputs=0,
              per_nb=facts, seconds=round(time.time() - t0, 1))


@live
def test_live_ii_second_writer_is_refused_never_merged(tmp_path, monkeypatch, live_store):
    monkeypatch.setattr(nbcd, "_NB_STORE", live_store)
    p = tmp_path / "shared.ipynb"
    _dump_json(p, _fixture_nb())
    mine = nbcd.nb_load(p)
    other = nbcd.McpNbStore()                   # a second session: another grain, or a
    try:                                        # timed-out call still persisting
        b = p.read_bytes()
        other.seen(p, nbcd._nb_sha(b))
        theirs = json.loads(b.decode("utf-8"))
        theirs["cells"].append({"cell_type": "markdown", "id": "second01", "metadata": {},
                                "source": ["written by the second writer"]})
        other.write(p, theirs)
    finally:
        other.close()
    after_second = p.read_bytes()
    mine["cells"][1]["source"] = ["x = 'mine'\n"]
    with pytest.raises(nbcd.NbWriteError) as ei:
        nbcd.nb_dump(p, mine)
    assert ei.value.kind == "conflict"
    assert p.read_bytes() == after_second       # the second writer's cell is still there
    assert any(c.get("id") == "second01"
               for c in json.loads(after_second.decode("utf-8"))["cells"])
    _evidence("ii-second-writer", refused=ei.value.kind, second_writer_kept=True,
              detail=ei.value.detail)


@live
def test_live_ii_a_markdown_attachment_is_kept_or_the_write_refused(tmp_path, monkeypatch,
                                                                    live_store):
    """The server rebuilt every cell with new_markdown_cell, which drops a markdown cell's
    `attachments` (jupyter-papermill write_notebook, as of mcp-servers 2f890b0d7). Whatever
    the server does, the attachment is never lost silently: either it is on disk after the
    write, or the readback refuses the write and the file keeps its last proved bytes."""
    monkeypatch.setattr(nbcd, "_NB_STORE", live_store)
    p = tmp_path / "att.ipynb"
    nb = _fixture_nb()
    nb["cells"][0]["attachments"] = {"a.png": {"image/png": "iVBORw0KGgo="}}
    _dump_json(p, nb)
    nb = nbcd.nb_load(p)
    try:
        nbcd.nb_dump(p, nb)
    except nbcd.NbWriteError as exc:
        assert exc.kind == "readback" and "cell 0 attachments" in exc.detail
        _evidence("ii-attachment", outcome="refused-by-readback", detail=exc.detail)
        return
    disk = json.loads(p.read_text(encoding="utf-8"))
    assert disk["cells"][0]["attachments"] == {"a.png": {"image/png": "iVBORw0KGgo="}}
    _evidence("ii-attachment", outcome="kept-by-server")


@live
def test_live_ii_schema_invalid_notebook_is_refused_by_the_server(tmp_path, monkeypatch,
                                                                  live_store):
    """`transient` is a message key, never valid on disk: the server's nbformat validation
    refuses the write, the store reports it, and the file keeps its last proved bytes."""
    monkeypatch.setattr(nbcd, "_NB_STORE", live_store)
    p = tmp_path / "invalid.ipynb"
    _dump_json(p, _fixture_nb())
    before = p.read_bytes()
    nb = nbcd.nb_load(p)
    nb["cells"][2]["outputs"][1]["transient"] = {"display_id": "abc"}
    with pytest.raises(nbcd.NbWriteError) as ei:
        nbcd.nb_dump(p, nb)
    assert ei.value.kind == "server" and "transient" in ei.value.detail
    assert p.read_bytes() == before
    _evidence("ii-server-schema-refusal", refused=ei.value.kind, file_unchanged=True)


@live
def test_live_iii_json_and_mcp_serial_give_the_same_notebook(tmp_path, monkeypatch,
                                                             live_store):
    """Same applier sequence (repair a code cell, re-normalize, repair a markdown cell)
    in both modes: identical once parsed; the byte differences are only nbformat's."""
    seq = [
        lambda p: nbcd.apply_repairs(p, {"cells": [{"idx": 1, "source": "y = 2\nprint(y)\n"}]}),
        lambda p: nbcd.normalize_sources(p),
        lambda p: nbcd.apply_repairs(p, {"cells": [{"idx": 0, "source": "# Titre corrigé\n"}]},
                                     allow_markdown=True),
        lambda p: nbcd.normalize_sources(p),
    ]
    pj, pm = tmp_path / "json.ipynb", tmp_path / "mcp.ipynb"
    _dump_json(pj, _fixture_nb())
    shutil.copyfile(pj, pm)
    monkeypatch.setattr(nbcd, "_NB_STORE", None)
    for step in seq:
        step(pj)
    monkeypatch.setattr(nbcd, "_NB_STORE", live_store)
    for step in seq:
        step(pm)
    nj = json.loads(pj.read_text(encoding="utf-8"))
    nm = json.loads(pm.read_text(encoding="utf-8"))
    diffs, notes = nbcd.nb_diff(nj, nm)
    assert diffs == []
    bj, bm = pj.read_bytes(), pm.read_bytes()
    lines_j, lines_m = bj.decode().splitlines(), bm.decode().splitlines()
    udiff = list(difflib.unified_diff(lines_j, lines_m, "json", "mcp-serial", n=1,
                                      lineterm=""))
    _evidence("iii-json-vs-mcp-serial", semantic_diffs=0, normalized=notes,
              bytes_json=len(bj), bytes_mcp=len(bm), identical_bytes=bj == bm,
              crlf_json=bj.count(CRLF), crlf_mcp=bm.count(CRLF),
              keys_sorted_on_disk=list(nm["cells"][1]) == sorted(nm["cells"][1]),
              writes=live_store.writes, byte_diff=udiff[:60])

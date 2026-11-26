#!/usr/bin/env python3
"""Tests de l'attribution des appels du harnais voltron (26/11).

SANS engine : mêmes gardes que test_voltron_facade.py (module chargé hors
main(), `run_task` factice, `engine_healthy` vrai, aucun Docker).

Couvre :
  1. `caller_id` : normalisation (minuscules, caractères sûrs) et refus d'un
     en-tête vide ou entièrement illisible ;
  2. `by_caller` dans le compteur : chaque appelant déclaré a sa ligne, un
     appel sans en-tête tombe sous « anonymous », une sonde (`X-Voltron-Probe`)
     n'entre pas dans le compteur ;
  3. la borne : au-delà de CALLER_MAX noms, les nouveaux vont sous « _others »
     (un nom forgé à chaque appel ne peut pas gonfler le fichier) ;
  4. un job conserve l'appelant déclaré au POST et l'attribue à ses tâches,
     y compris après relecture depuis le disque (clé persistée) ;
  5. le journal d'accès porte l'appelant, sonde/adoption et le User-Agent sur
     les routes d'exécution — et reste sobre sur /health.

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_attribution.py -v
Preuve rouge : VOLTRON_SERVER_SRC=<serveur d'avant l'attribution, à côté de
real_task_bench.py> python test_voltron_attribution.py
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_voltron_facade import TASK, call, load_module, read_usage, serve  # noqa: E402

OK_RES = {"ok": True, "stage": "a", "answer": "{}", "detail": "", "turns": 1, "dt_s": 0.0}


def _post_task(port, headers=None):
    return call(port, "POST", "/v1/task", TASK, headers=headers)


def test_caller_id_normalise():
    scratch = tempfile.mkdtemp(prefix="vha_id_")
    try:
        mod = load_module(scratch)
        assert mod.caller_id({"X-Voltron-Caller": "  Po-2028/VLLM "}) == "po-2028vllm"
        assert mod.caller_id({"X-Voltron-Caller": "lane a\tb\r\nx"}) == "laneabx"
        assert mod.caller_id({"X-Voltron-Caller": "x" * 80}) == "x" * 40
        assert mod.caller_id({}) is None
        assert mod.caller_id(None) is None
        assert mod.caller_id({"X-Voltron-Caller": "  ///  "}) is None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_usage_par_appelant_et_sonde():
    scratch = tempfile.mkdtemp(prefix="vha_usage_")
    srv = None
    try:
        mod = load_module(scratch, run_task=lambda t: dict(OK_RES))
        srv, port = serve(mod)
        for _ in range(2):
            assert _post_task(port, {"X-Voltron-Caller": "lane-a"})[0] == 200
        assert _post_task(port, {"X-Voltron-Caller": "Lane-B"})[0] == 200
        assert _post_task(port)[0] == 200
        # une sonde s'exécute mais ne compte pas, même avec un appelant déclaré
        assert _post_task(port, {"X-Voltron-Caller": "lane-a",
                                 "X-Voltron-Probe": "1"})[0] == 200

        u = read_usage(mod)
        assert u["tasks_total"] == 4, u
        assert u["by_caller"]["lane-a"] == {"n": 2, "ok": 2, "jobs": 0}, u["by_caller"]
        assert u["by_caller"]["lane-b"] == {"n": 1, "ok": 1, "jobs": 0}, u["by_caller"]
        assert u["by_caller"]["anonymous"] == {"n": 1, "ok": 1, "jobs": 0}, u["by_caller"]

        status, _, raw = call(port, "GET", "/v1/usage")
        assert status == 200 and json.loads(raw)["by_caller"]["lane-a"]["n"] == 2
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_by_caller_borne():
    scratch = tempfile.mkdtemp(prefix="vha_bound_")
    srv = None
    try:
        mod = load_module(scratch, run_task=lambda t: dict(OK_RES))
        srv, port = serve(mod)
        total = mod.CALLER_MAX + 8
        for i in range(total):
            assert _post_task(port, {"X-Voltron-Caller": f"caller-{i}"})[0] == 200
        bc = read_usage(mod)["by_caller"]
        assert len(bc) == mod.CALLER_MAX + 1, sorted(bc)
        assert bc["_others"]["n"] == 8, bc["_others"]
        assert "caller-0" in bc and f"caller-{total - 1}" not in bc
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_job_conserve_l_appelant():
    scratch = tempfile.mkdtemp(prefix="vha_job_")
    srv = None
    try:
        mod = load_module(scratch, run_task=lambda t: dict(OK_RES))
        srv, port = serve(mod)
        status, _, raw = call(port, "POST", "/v1/jobs",
                              {"tasks": [dict(TASK), dict(TASK)], "name": "lot"},
                              headers={"X-Voltron-Caller": "lot-a"})
        assert status == 200, (status, raw)
        jid = json.loads(raw)["job_id"]
        assert mod._jobs[jid]["caller"] == "lot-a", mod._jobs[jid]
        # la clé est persistée avec la charge : une reprise garde l'attribution
        with open(os.path.join(mod.JOBS_DIR, f"{jid}.json"), encoding="utf-8") as f:
            assert json.load(f)["caller"] == "lot-a"

        deadline = time.time() + 15
        while time.time() < deadline:
            _, _, raw = call(port, "GET", f"/v1/jobs/{jid}")
            if json.loads(raw).get("status") == "done":
                break
            time.sleep(0.05)
        u = read_usage(mod)
        assert u["by_caller"]["lot-a"] == {"n": 2, "ok": 2, "jobs": 1}, u["by_caller"]
        assert u["jobs_total"] == 1 and u["job_tasks"] == 2, u
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_journal_accredite_l_appelant():
    scratch = tempfile.mkdtemp(prefix="vha_log_")
    srv = None
    try:
        mod = load_module(scratch, run_task=lambda t: dict(OK_RES))
        srv, port = serve(mod)
        # serve() coupe le journal : le rétablir vers stdout pour l'observer
        mod.Handler.log_message = lambda self, fmt, *args: print(fmt % args, flush=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _post_task(port, {"X-Voltron-Caller": "veille-sister",
                              "X-Voltron-Probe": "1",
                              "User-Agent": "python-requests/2.32 probe"})
            _post_task(port, {"User-Agent": "OpenAI/Python 2.54.0"})
            call(port, "GET", "/health")
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        probe_line = next(ln for ln in lines if "kind=probe" in ln)
        assert "caller=veille-sister" in probe_line, probe_line
        assert "ua='python-requests/2.32 probe'" in probe_line, probe_line
        adopt_line = next(ln for ln in lines if "kind=adoption" in ln)
        assert "caller=-" in adopt_line and "ua='OpenAI/Python 2.54.0'" in adopt_line, adopt_line
        health_line = next(ln for ln in lines if "/health" in ln)
        assert "caller=" not in health_line and "ua=" not in health_line, health_line
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS: {fn.__name__}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"FAIL: {fn.__name__}: {exc!r}", flush=True)
    print(f"{len(fns) - failed}/{len(fns)} tests OK", flush=True)
    sys.exit(1 if failed else 0)

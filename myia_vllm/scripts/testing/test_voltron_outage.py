#!/usr/bin/env python3
"""Tests de résilience aux coupures d'engine du service harnais voltron.

SANS engine : le module est chargé hors main(), les appels moteur sont factices.
Les tests HTTP utilisent un serveur éphémère sur un port libre (jamais :5029).

Couvre (coupures mesurées 20-23/11 : la garde anti-famine du commit hôte
recycle la VM WSL, le moteur revient 2 à 9 min plus tard) :

  1. classification d'une exception : coupure de transport (rejouable) vs refus
     du moteur (HTTPError — à ne pas rejouer) ;
  2. une tâche coupée est ATTENDUE puis REJOUEE, et comptée UNE fois ;
  3. un échec non transitoire n'est PAS rejoué ;
  4. une longue coupure : attente épuisée -> `engine_outage` sur le job, les
     tâches restantes ne sont plus lancées tant que le moteur est muet, job
     finalisé, résultats étiquetés `transient` ; moteur revenu -> reprise ;
  5. `ensure_engine` ne renonce plus quand `docker start` lève TimeoutExpired
     (CLI bloquée pendant le recyclage de la VM) ;
  6. classify : une coupure à l'étape preuve remonte en transitoire au lieu de
     brûler les tours de réparation puis de payer le coordinateur hub ;
  7. la réparation dirigée des autres contrats est gardée (avant : l'exception
     traversait -> `stage: error` en job, connexion fermée en synchrone) ;
  8. `/openapi.json` et `OPTIONS` sont servis, SANS en-tête CORS ni adresse ;
  9. l'en-tête `X-Voltron-Probe: 1` retire la sonde du compteur d'adoption ;
 10. `GET /v1/jobs/<id>` est un instantané pris sous le verrou (une clé ajoutée
     pendant la réponse ne casse pas la connexion du consommateur) ;
 11. moteur muet : l'attente RELANCE son conteneur, puis le relance toutes les
     30 s (un conteneur tué ne revient pas par sa politique de restart).

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_outage.py -v
            (ou directement : python test_voltron_outage.py)
Preuve rouge : VOLTRON_SERVER_SRC=<serveur sans correctif, à côté de
real_task_bench.py> python test_voltron_outage.py
"""
import http.client
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("VOLTRON_SERVER_SRC") or os.path.join(HERE, "voltron_harness_server.py")

OK = {"ok": True, "stage": "a", "answer": "x", "detail": "", "turns": 1, "dt_s": 0.01}
CUT = {"ok": False, "stage": "engine-error", "answer": "", "detail": "connexion coupée",
       "turns": 1, "dt_s": 0.1, "transient": True}


class DockerInterdit(BaseException):
    """Un test ne lance jamais Docker. Hérite de BaseException exprès : le
    serveur attrape `Exception` autour de `docker start` (CLI bloquée), un job
    attrape `Exception` par tâche — un appel Docker involontaire ne doit être
    avalé par aucun des deux."""


def _no_docker(*args, **kwargs):
    raise DockerInterdit("un test ne lance jamais Docker : poser un faux subprocess.run")


@contextmanager
def patched(obj, name, value):
    """Patch un attribut et le RESTAURE. `obj` peut être le vrai module time
    (sans restauration, le patch fuit sur les autres tests) ou le garde
    subprocess propre au module chargé (voir load_module)."""
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def load_module(scratch, run_task=None):
    """Charge le serveur SANS main() et le pointe sur un scratch dir. Aucune
    sonde ne touche l'engine réel : engine_healthy est factice, et la seule
    commande Docker du serveur (subprocess.run) est remplacée par un garde
    qui lève — mesuré 24/11 : sans ce garde, la suite de reprise a lancé le
    VRAI conteneur du siège. La boucle d'attente (_wait_engine) reste la
    vraie : elle n'a d'autre frontière que ces deux-là."""
    spec = importlib.util.spec_from_file_location(
        "vho_test_%d" % id(scratch), SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __name__ != __main__ -> pas de serveur
    mod.JOBS_DIR = os.path.join(scratch, "jobs")
    mod.USAGE_PATH = os.path.join(scratch, "usage.json")
    mod.engine_healthy = lambda timeout=2: True
    mod.subprocess = types.SimpleNamespace(run=_no_docker)
    mod.HUB_KEY = None
    if run_task is not None:
        mod.run_task = run_task
    return mod


def new_job(mod, tasks):
    jid = "job-20260101T000000Z-abc123"
    with mod._jobs_lock:
        mod._jobs[jid] = {"status": "running", "name": "t", "total": len(tasks),
                          "done": 0, "results": [], "tasks": tasks}
    return jid


def read_usage(mod):
    if not os.path.exists(mod.USAGE_PATH):
        return {"tasks_total": 0, "jobs_total": 0}
    with open(mod.USAGE_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_blip_classification():
    scratch = tempfile.mkdtemp(prefix="vho_blip_")
    try:
        mod = load_module(scratch)
        req = urllib.request.Request("http://127.0.0.1/x")
        blips = [urllib.error.URLError("connexion refusée"), ConnectionResetError(104, "reset"),
                 TimeoutError("timed out"), http.client.RemoteDisconnected("closed"),
                 http.client.BadStatusLine("junk")]
        for exc in blips:
            assert mod._is_engine_blip(exc) is True, repr(exc)
        non_blips = [urllib.error.HTTPError(req.full_url, 500, "boom", {}, io.BytesIO(b"")),
                     urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"")),
                     ValueError("mauvais contrat"), KeyError("choices"),
                     json.JSONDecodeError("doc", "x", 0)]
        for exc in non_blips:
            assert mod._is_engine_blip(exc) is False, repr(exc)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_coupure_rejouee_comptee_une_fois():
    """1re tentative coupée, moteur revenu -> rejeu, résultat ok, 1 seul bump."""
    scratch = tempfile.mkdtemp(prefix="vho_replay_")
    calls, waits = [], []

    def fake(t):
        calls.append(t["text"])
        return dict(CUT) if len(calls) == 1 else dict(OK)
    try:
        mod = load_module(scratch, run_task=fake)
        mod._wait_engine = lambda timeout_s=300: waits.append(timeout_s) or True
        jid = new_job(mod, [{"type": "classify", "text": "t0"}])
        mod._run_tasks(jid, [(0, mod._jobs[jid]["tasks"][0])])
        job = mod._jobs[jid]
        assert calls == ["t0", "t0"], calls
        assert waits == [mod.ENGINE_WAIT_JOB_S], waits
        assert job["results"][0]["ok"] is True, job["results"]
        assert not job.get("engine_outage"), job
        u = read_usage(mod)
        assert u["tasks_total"] == 1 and u["ok"] == 1, u
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_echec_non_transitoire_pas_rejoue():
    scratch = tempfile.mkdtemp(prefix="vho_noreplay_")
    calls = []

    def fake(t):
        calls.append(t["text"])
        return {"ok": False, "stage": "engine-error", "answer": "",
                "detail": "HTTPError 500", "turns": 1, "dt_s": 0.1,
                "transient": False}
    try:
        mod = load_module(scratch, run_task=fake)
        jid = new_job(mod, [{"type": "classify", "text": "t0"}])
        mod._run_tasks(jid, [(0, mod._jobs[jid]["tasks"][0])])
        assert calls == ["t0"], calls
        assert mod._jobs[jid]["results"][0]["ok"] is False
        assert not mod._jobs[jid].get("engine_outage")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_longue_coupure_echec_rapide_puis_reprise():
    """Attente épuisée : les tâches restantes ne sont PLUS LANÇÉES (ni run_task,
    ni attente) tant que le moteur est muet ; résultats transitoires. Moteur
    revenu -> le drapeau tombe et le job reprend."""
    scratch = tempfile.mkdtemp(prefix="vho_outage_")
    calls, waits = [], []

    def fake(t):
        calls.append(t["text"])
        return dict(CUT) if t["text"] == "t0" else dict(OK)
    healthy = [True]
    try:
        mod = load_module(scratch, run_task=fake)
        mod.engine_healthy = lambda timeout=2: healthy[0]
        mod._wait_engine = lambda timeout_s=300: waits.append(timeout_s) or False
        tasks = [{"type": "classify", "text": f"t{i}"} for i in range(5)]
        jid = new_job(mod, tasks)
        mod._run_tasks(jid, [(0, tasks[0])])  # coupée, attente épuisée
        healthy[0] = False
        mod._run_tasks(jid, [(1, tasks[1]), (2, tasks[2])])
        job = mod._jobs[jid]
        assert calls == ["t0"], f"les tâches 1 et 2 ne devaient pas être lancées: {calls}"
        assert waits == [mod.ENGINE_WAIT_JOB_S], waits
        assert job["engine_outage"] is True and job["engine_outages"] == 1, job
        assert job["status"] == "running" and job["done"] == 3, job
        by_task = {r["task"]: r for r in job["results"]}
        for i in (0, 1, 2):
            assert by_task[i]["ok"] is False and by_task[i]["transient"] is True, by_task[i]
        assert by_task[1]["stage"] == "engine-down", by_task[1]

        healthy[0] = True  # moteur revenu : le job reprend
        mod._run_tasks(jid, [(3, tasks[3]), (4, tasks[4])])
        job = mod._jobs[jid]
        assert "engine_outage" not in job, job
        assert calls == ["t0", "t3", "t4"], calls
        assert job["status"] == "done" and job["done"] == 5, job
        u = read_usage(mod)
        assert u["tasks_total"] == 5 and u["ok"] == 2, u
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_ensure_engine_survit_au_timeout_docker_start():
    """docker start qui bloque (TimeoutExpired) ne doit PAS faire renoncer :
    la politique de restart du conteneur le ramène, l'attente le voit revenir.
    docker absent (FileNotFoundError) : échec immédiat, sans boucle."""
    scratch = tempfile.mkdtemp(prefix="vho_ensure_")
    try:
        mod = load_module(scratch)
        states = iter([False, False, True])  # muet, boot, servi
        mod.engine_healthy = lambda timeout=2: next(states, True)

        def blocked(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="docker start", timeout=30)
        with patched(mod.subprocess, "run", blocked), patched(mod.time, "sleep", lambda s: None):
            ok, msg = mod.ensure_engine()
        assert ok is True, (ok, msg)

        probes = []
        mod.engine_healthy = lambda timeout=2: probes.append(1) or False

        def absent(*a, **kw):
            raise FileNotFoundError("docker")
        with patched(mod.subprocess, "run", absent):
            ok, msg = mod.ensure_engine()
        assert ok is False and "docker start échoué" in msg, (ok, msg)
        assert len(probes) == 1, "aucune boucle de sondes après un docker absent"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_attente_relance_le_conteneur_arrete():
    """Moteur muet : l'attente RELANCE son conteneur, puis le relance toutes
    les 30 s tant qu'il reste muet (mesuré 24/11 : après un `docker kill`, la
    politique de restart n'a rien fait pendant 20 min ; un start émis pendant
    l'agonie du conteneur est un no-op — un seul start ne suffit pas). Moteur
    servi d'emblée : aucune commande Docker. Horloge factice : le test ne
    touche ni Docker ni l'engine."""
    scratch = tempfile.mkdtemp(prefix="vho_nudge_")
    try:
        mod = load_module(scratch)
        clock, base = [1000.0], [1000.0]  # base = départ de la phase en cours
        mod.time = types.SimpleNamespace(
            time=time.time, monotonic=lambda: clock[0],
            sleep=lambda s: clock.__setitem__(0, clock[0] + s))
        starts = []
        mod.engine_healthy = lambda timeout=2: clock[0] >= 1040.0  # servi à +40 s
        mod._docker_start = lambda: starts.append(clock[0] - base[0]) or (True, "")
        assert mod._wait_engine(300) is True
        assert starts == [0.0, 30.0], f"un docker start à 0 s puis toutes les 30 s: {starts}"

        clock[0] = base[0] = 2000.0
        mod.engine_healthy = lambda timeout=2: True
        assert mod._wait_engine(300) is True
        assert starts == [0.0, 30.0], "moteur servi : aucun docker start"

        clock[0] = base[0] = 3000.0  # reste muet : borné par le budget de l'appelant
        mod.engine_healthy = lambda timeout=2: False
        assert mod._wait_engine(70) is False
        assert starts == [0.0, 30.0, 0.0, 30.0, 60.0], starts
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_classify_coupure_preuve_transitoire_sans_reparation():
    """Coupure à l'étape preuve : transitoire, 2 tours, AUCUN tour de réparation
    (avant : preuve vide -> 2 tours brûlés -> escalade au coordinateur hub)."""
    scratch = tempfile.mkdtemp(prefix="vho_cls_")
    calls = []

    def fake_chat(url, model, messages, **kw):
        calls.append(kw.get("prefill"))
        if len(calls) == 1:
            return 'classeA"}'
        raise urllib.error.URLError("moteur tué")
    try:
        mod = load_module(scratch)
        mod.chat = fake_chat
        res = mod.run_classify({"type": "classify", "data": "une ligne de preuve assez longue",
                                "classes": ["classeA", "classeB"]})
        assert res["stage"] == "engine-error" and res["transient"] is True, res
        assert res["turns"] == 2 and "étape preuve" in res["detail"], res
        assert len(calls) == 2, calls
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_reparation_gardee_contre_la_coupure():
    """extract : 1re réponse hors contrat, la réparation est coupée -> résultat
    transitoire (avant : l'exception traversait run_task)."""
    scratch = tempfile.mkdtemp(prefix="vho_rep_")
    calls = []

    def fake_chat(url, model, messages, **kw):
        calls.append(1)
        if len(calls) == 1:
            return "pas du json du tout"
        raise ConnectionResetError(104, "reset")
    try:
        mod = load_module(scratch)
        mod.chat = fake_chat
        try:
            res = mod.run_task({"type": "extract", "data": "score=42", "fields": ["score"]})
        except Exception as exc:  # c'est le défaut visé (ancienne tête)
            raise AssertionError(f"la coupure a traversé run_task: {exc!r}")
        assert res["stage"] == "engine-error" and res["transient"] is True, res
        assert len(calls) == 2, calls
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _serve(mod):
    mod.Handler.log_message = lambda self, fmt, *args: None
    srv = mod.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_openapi_et_options_sans_cors_ni_adresse():
    scratch = tempfile.mkdtemp(prefix="vho_http_")
    srv = None
    try:
        mod = load_module(scratch)
        srv, port = _serve(mod)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=5) as r:
            raw = r.read().decode("utf-8")
        doc = json.loads(raw)
        assert doc["openapi"].startswith("3."), doc.get("openapi")
        for p in ("/v1/task", "/v1/jobs", "/v1/jobs/{id}", "/v1/usage", "/health"):
            assert p in doc["paths"], p
        assert "servers" not in doc, "aucune adresse ne vit dans le code"
        assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", raw), "adresse IP dans le contrat"
        task = doc["paths"]["/v1/task"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert {"extract", "classify", "numbers", "diff"} == set(
            task["properties"]["type"]["enum"]), task
        result = doc["paths"]["/v1/task"]["post"]["responses"]["200"]["content"][
            "application/json"]["schema"]
        assert {"a", "c", "reject", "error", "engine-down", "engine-error"} == set(
            result["properties"]["stage"]["enum"]), result

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("OPTIONS", "/v1/task")
            r = conn.getresponse()
            r.read()
            assert r.status == 204, r.status
            assert "POST" in (r.getheader("Allow") or ""), r.getheader("Allow")
            assert r.getheader("Access-Control-Allow-Origin") is None, \
                "service sans clé qui dépense des tokens hub : pas de CORS"
        finally:
            conn.close()
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_sonde_hors_compteur_adoption():
    scratch = tempfile.mkdtemp(prefix="vho_probe_")
    srv = None
    try:
        mod = load_module(scratch, run_task=lambda t: dict(OK))
        srv, port = _serve(mod)

        def post(path, payload, probe):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            if probe:
                req.add_header("X-Voltron-Probe", "1")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)

        post("/v1/task", {"type": "classify", "data": "x"}, probe=True)
        assert read_usage(mod)["tasks_total"] == 0, "une sonde n'est pas de l'adoption"
        post("/v1/task", {"type": "classify", "data": "x"}, probe=False)
        assert read_usage(mod)["tasks_total"] == 1

        job = post("/v1/jobs", {"name": "sonde", "tasks": [{"type": "classify", "data": "x"}]},
                   probe=True)
        assert read_usage(mod)["jobs_total"] == 0, read_usage(mod)
        t0 = time.monotonic()
        while mod._jobs[job["job_id"]]["status"] != "done" and time.monotonic() - t0 < 15:
            time.sleep(0.1)
        done = mod._jobs[job["job_id"]]
        assert done["status"] == "done" and done["probe"] is True, done
        u = read_usage(mod)
        assert u["jobs_total"] == 0 and u["tasks_total"] == 1, u
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_statut_job_instantane_sous_verrou():
    """GET /v1/jobs/<id> pendant que le job GAGNE une clé (waiting_engine,
    engine_outage) : la vue est un instantané pris sous _jobs_lock. Sans le
    verrou, itérer le dict live lève « dictionary changed size during
    iteration » — la connexion du consommateur se ferme au lieu de répondre."""
    scratch = tempfile.mkdtemp(prefix="vho_view_")
    srv = None

    class SlowDict(dict):
        def items(self):
            for kv in super().items():
                time.sleep(0.02)
                yield kv
    try:
        mod = load_module(scratch)
        jid = "job-20260101T000000Z-abc123"
        job = SlowDict({"status": "running", "name": "t", "total": 1, "done": 0,
                        "results": [], "tasks": [{"type": "classify"}]})
        mod._jobs[jid] = job
        srv, port = _serve(mod)
        out = {}

        def get():
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/v1/jobs/{jid}", timeout=10) as r:
                    out["status"] = r.status
                    out["body"] = json.load(r)
            except Exception as exc:
                out["status"] = None
                out["err"] = repr(exc)
        t = threading.Thread(target=get)
        t.start()
        time.sleep(0.05)  # la réponse est en train d'être construite
        with mod._jobs_lock:
            job["engine_outage"] = True  # une tâche épuise son attente ici
        t.join(10)
        assert not t.is_alive(), "GET bloqué"
        assert out.get("status") == 200, out
        assert "engine_outage" not in out["body"], "l'instantané a été pris après"
        assert "tasks" not in out["body"], "la charge ne voyage pas dans le statut"
        assert job["engine_outage"] is True
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

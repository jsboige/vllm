#!/usr/bin/env python3
"""Tests de la machine à états de reprise du service harnais voltron.

SANS engine, SANS serveur et SANS Docker : le module est chargé hors main(), ses
constantes sont repatchées vers un répertoire scratch, les appels réseau sont
factices et la seule commande Docker du serveur est remplacée par un garde.
Couvre (CHANGES_REQUESTED ai-01 §2) :

  1. la reprise d'un job interrompu SANS doublon d'exécution ;
  2. la finalisation malgré une tâche en erreur (str dans le lot), et l'effacement
     du drapeau `engine_outage` d'avant restart (sinon la reprise renonçait) ;
  3. N threads qui persistent le MÊME job en parallèle — rouge sur une
     implémentation à tmp partagé (JSON entrelacé / PermissionError Windows),
     vert dès que l'écriture est sérialisée à tmp unique ;
  4. le compteur d'usage REFUSE d'écrire sur un fichier illisible (l'historique
     d'adoption ne repart pas de zéro), JSON non-objet compris (#599 D1) ;
  5. la reprise ne re-compte pas les tâches relancées ;
  6. un os.replace REFUSÉ (WinError 5) ne tue ni le job, ni le boot, ni un
     résultat, ni la réponse à POST /v1/jobs — reproduit 24/11 (~1 passage
     sur 12) : la dernière écriture du job n'était pas protégée, le thread
     mourait à la finalisation et `done` ne touchait jamais le disque.

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_recovery.py -v
            (ou directement : python test_voltron_recovery.py)
Preuve rouge : VOLTRON_SERVER_SRC=<serveur sans correctif> python test_voltron_recovery.py
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import urllib.request
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("VOLTRON_SERVER_SRC") or os.path.join(HERE, "voltron_harness_server.py")

_calls_lock = threading.Lock()
CALLS = []


class DockerInterdit(BaseException):
    """Un test ne lance jamais Docker. Hérite de BaseException exprès : le
    serveur attrape `Exception` autour de `docker start`, la reprise attrape
    `Exception` par tâche — un appel involontaire ne doit être avalé."""


def _no_docker(*args, **kwargs):
    raise DockerInterdit("un test ne lance jamais Docker : poser un faux subprocess.run")


@contextmanager
def patched(obj, name, value):
    """Patch un attribut et le RESTAURE (obj est souvent le vrai module
    os/time : sans restauration, le patch fuit sur les autres tests)."""
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


class ReplaceRefusals:
    """os.replace factice : sert `left` refus (PermissionError WinError 5) sur
    les destinations acceptées par `want`, à partir de la `skip`-ième écriture
    concernée ; laisse passer tout le reste."""

    def __init__(self, want, left, skip=1):
        self.want, self.left, self.skip = want, left, skip
        self.n = self.calls = 0
        self.real = os.replace

    def __call__(self, src, dst, *a, **kw):
        if self.want(dst):
            self.calls += 1
            if self.calls >= self.skip and self.left > 0:
                self.left -= 1
                self.n += 1
                raise PermissionError(13, "Accès refusé")
        return self.real(src, dst, *a, **kw)


def load_module(scratch):
    """Charge le serveur SANS main() et le pointe sur un scratch dir. Frontières
    moteur/Docker factices : la reprise au boot RELANCE un conteneur arrêté
    (24/11) — mesuré ce jour-là, sans ces gardes la suite a lancé le VRAI
    conteneur du siège quand il était arrêté."""
    spec = importlib.util.spec_from_file_location(
        "vhs_test_%d" % id(scratch), SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __name__ != __main__ -> pas de serveur
    mod.JOBS_DIR = os.path.join(scratch, "jobs")
    mod.USAGE_PATH = os.path.join(scratch, "usage.json")
    mod.engine_healthy = lambda timeout=2: True  # pas d'engine : la vraie
    # _wait_engine ne touche que cette frontière et subprocess.run, gardés tous deux
    mod.subprocess = types.SimpleNamespace(run=_no_docker)  # jamais de docker start
    mod.HUB_KEY = None  # couper la phase C des fausses tâches
    with _calls_lock:
        CALLS.clear()

    def fake_run_task(t):
        with _calls_lock:
            CALLS.append(t.get("text", t.get("type", "?")))
        return {"ok": True, "stage": "a", "answer": "x", "detail": "",
                "turns": 1, "dt_s": 0.01}
    mod.run_task = fake_run_task
    return mod


def wjob(mod, name, obj):
    with open(os.path.join(mod.JOBS_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def rjob(mod, name):
    """Lit un job sur disque. Une lecture peut tomber PENDANT le remplacement
    atomique du fichier : Windows la refuse alors (mesuré 24/11, ~1 lecture
    refusée sur 20 sous écriture continue). C'est la course du sondeur du test
    avec l'écrivain, pas un défaut du service — on relit."""
    path = os.path.join(mod.JOBS_DIR, name)
    t0 = time.monotonic()
    while True:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except PermissionError:
            if time.monotonic() - t0 > 5:
                raise
            time.sleep(0.05)


def wait_status(mod, name, want, timeout_s=30, missing_ok=False):
    """Attend le statut `want` sur disque. missing_ok : le fichier n'est pas
    encore écrit (le thread d'un job POSTé peut démarrer après la réponse)."""
    t0 = time.time()
    j = {}
    while j.get("status") != want and time.time() - t0 < timeout_s:
        try:
            j = rjob(mod, name)
        except FileNotFoundError:
            if not missing_ok:
                raise
            time.sleep(0.2)
    return j


def serve(mod):
    """Serveur éphémère du module chargé, sur un port libre (jamais :5029)."""
    mod.Handler.log_message = lambda self, fmt, *args: None
    srv = mod.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_orphaned_finalise_corrupt_done():
    """legacy sans charge -> orphaned ; complet -> finalisé ; illisible ->
    ignoré (fichier gardé) ; done -> intact."""
    scratch = tempfile.mkdtemp(prefix="vhs_t1_")
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        wjob(mod, "job-legacy.json",
             {"status": "running", "total": 10, "done": 3, "results": []})
        wjob(mod, "job-complete.json",
             {"status": "running", "total": 2, "done": 2,
              "results": [{"task": 0}, {"task": 1}],
              "tasks": [{"type": "classify"}, {"type": "classify"}]})
        with open(os.path.join(mod.JOBS_DIR, "job-corrupt.json"), "w") as f:
            f.write('{"status": "run')
        wjob(mod, "job-done.json",
             {"status": "done", "total": 1, "done": 1, "results": [{"task": 0}]})

        mod._recover_orphans()

        a = rjob(mod, "job-legacy.json")
        assert a["status"] == "orphaned" and "orphaned_at" in a, a
        c = rjob(mod, "job-complete.json")
        assert c["status"] == "done", c
        e = rjob(mod, "job-done.json")
        assert e["status"] == "done" and e["done"] == 1, e
        assert os.path.exists(os.path.join(mod.JOBS_DIR, "job-corrupt.json")), \
            "un fichier illisible doit rester en place, jamais supprimé"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_reprise_sans_doublon_et_avec_tache_erreur():
    """running avec charge, 1 résultat sur 3 (dont une tâche malformée dans
    le lot restant) -> seules les manquantes tournent, la malformée devient un
    résultat d'erreur, le job FINALISE done, index 0-2 sans doublon."""
    scratch = tempfile.mkdtemp(prefix="vhs_t2_")
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        # tâche 1 = str malformé : l'ancien défaut gelait le pool entier
        wjob(mod, "job-partial.json",
             {"status": "running", "total": 3, "done": 1,
              "engine_outage": True, "waiting_engine": 1,
              "results": [{"task": 0, "ok": True}],
              "tasks": [{"type": "classify", "text": "t0"},
                        "t1-malformee",
                        {"type": "classify", "text": "t2"}]})

        mod._recover_orphans()
        b = wait_status(mod, "job-partial.json", "done")

        assert b["done"] == 3 and len(b["results"]) == 3, b
        assert b.get("recovered") == 1, b
        assert "engine_outage" not in b and "waiting_engine" not in b, \
            "un drapeau d'avant restart ne doit pas geler la nouvelle tentative"
        assert sorted(x["task"] for x in b["results"]) == [0, 1, 2], b
        err = [x for x in b["results"] if x["task"] == 1][0]
        assert err["ok"] is False and err["stage"] == "error", err
        with _calls_lock:
            relance = sorted(CALLS)
        # tâche 0 JAMAIS re-exécutée ; la malformée ne passe pas run_task
        assert relance == ["t2"], relance
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_reprise_ne_recompte_pas():
    """count_usage=False sur la reprise : tasks_total ne bouge pas."""
    scratch = tempfile.mkdtemp(prefix="vhs_t3_")
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        wjob(mod, "job-a.json",
             {"status": "running", "total": 2, "done": 0, "results": [],
              "tasks": [{"type": "classify", "text": "r1"},
                        {"type": "classify", "text": "r2"}]})
        mod._recover_orphans()
        wait_status(mod, "job-a.json", "done")
        if os.path.exists(mod.USAGE_PATH):
            with open(mod.USAGE_PATH, encoding="utf-8") as f:
                assert json.load(f)["tasks_total"] == 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_persist_parallel_n_threads():
    """N threads persistent le MÊME job en parallèle (CHANGES_REQUESTED §1) :
    aucune exception, le fichier final est un JSON valide dont l'état est
    cohérent avec la mémoire. Rouge sur un tmp partagé sans verrou."""
    scratch = tempfile.mkdtemp(prefix="vhs_t4_")
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        jid = "job-20260101T000000Z-abc123"
        with mod._jobs_lock:
            mod._jobs[jid] = {"status": "running", "name": "hammer", "total": 0,
                              "done": 0, "results": [], "tasks": []}
        errors = []
        N, ITERS = 8, 25

        def hammer():
            try:
                for k in range(ITERS):
                    with mod._jobs_lock:
                        mod._jobs[jid]["results"].append({"task": k, "ok": True})
                        mod._jobs[jid]["done"] += 1
                    mod._persist(jid)
            except Exception as exc:  # pragma: no cover - c'est le défaut visé
                errors.append(repr(exc))

        threads = [threading.Thread(target=hammer) for _ in range(N)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert not errors, f"persistance concurrente cassée: {errors[:3]}"
        final = rjob(mod, jid + ".json")
        assert final["status"] == "running", final
        assert len(final["results"]) == N * ITERS, \
            (len(final["results"]), N * ITERS)
        # aucun tmp orphelin ne reste
        leftovers = [f for f in os.listdir(mod.JOBS_DIR) if f.endswith(".tmp")]
        assert not leftovers, leftovers
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_usage_illisible_refuse_ecriture():
    """Un usage.json illisible ne doit PAS être écrasé par un dict à zéro
    (CHANGES_REQUESTED §3) : le bump refuse, les octets d'origine restent."""
    scratch = tempfile.mkdtemp(prefix="vhs_t5_")
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        corrupt = '{"tasks_total": 999, "ok": 99'  # JSON tronqué
        with open(mod.USAGE_PATH, "w", encoding="utf-8") as f:
            f.write(corrupt)
        r = mod._bump_usage("classify", True)
        assert r is None, "le bump doit refuser sur fichier illisible"
        with open(os.path.join(mod.USAGE_PATH), encoding="utf-8") as f:
            assert f.read() == corrupt, "l'historique a été écrasé !"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_usage_non_objet_ne_tue_pas_le_job():
    """#599 D1 : un usage.json valide en JSON mais non-objet ([]) est ILLEGIBLE
    pour l'instrument, comme un JSON tronqué. Le job finalise et le compteur
    reste intact — l'ancien code levait AttributeError avant la finalisation."""
    scratch = tempfile.mkdtemp(prefix="vhs_usage_shape_")
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        with open(mod.USAGE_PATH, "w", encoding="utf-8") as f:
            f.write("[]")
        task = {"type": "classify", "text": "t0"}
        jid = "job-20260101T000003Z-abc123"
        with mod._jobs_lock:
            mod._jobs[jid] = {"status": "running", "name": "usage-shape",
                              "total": 1, "done": 0, "results": [], "tasks": [task]}
        mod._run_tasks(jid, [(0, task)])
        done = rjob(mod, jid + ".json")
        assert done["status"] == "done" and done["done"] == 1, done
        assert done["results"][0]["ok"] is True, done
        with open(mod.USAGE_PATH, encoding="utf-8") as f:
            assert f.read() == "[]", "le compteur non-objet a été écrasé"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_ecriture_refusee_ne_tue_rien():
    """os.replace REFUSÉ (WinError 5 : la destination est tenue par un lecteur
    ou un antivirus). Quatre chemins où l'exception arrêtait autrefois le
    service — le premier est le rouge intermittent des passes précédentes :
      (1) finalisation d'un job : thread mort, `done` jamais sur disque, et la
          reprise au boot relançait un job fini ;
      (2) reprise au boot : _recover_orphans levait avant serve_forever ;
      (3) compteur d'usage : une tâche RÉUSSIE devenait « stage: error » ;
      (4) POST /v1/jobs : la connexion se fermait sans réponse."""
    scratch = tempfile.mkdtemp(prefix="vhs_t6_")
    srv = None
    try:
        mod = load_module(scratch)
        os.makedirs(mod.JOBS_DIR)
        two = {"type": "classify", "text": "t"}

        # (1) 2 tâches = 3 écritures ; 4 refus à partir de la 3e (finalisation)
        # -> réessayée, le job survit et son `done` finit sur disque
        fin = ReplaceRefusals(lambda d: d.endswith(".json") and "usage" not in d,
                              left=4, skip=3)
        jid = "job-20260101T000001Z-abc123"
        with mod._jobs_lock:
            mod._jobs[jid] = {"status": "running", "total": 2, "done": 0,
                              "results": [], "tasks": [two, two]}
        with patched(os, "replace", fin), patched(mod.time, "sleep", lambda s: None):
            mod._run_tasks(jid, [(0, two), (1, two)], count_usage=False)
        assert fin.n == 4, (fin.n, fin.calls)
        done = rjob(mod, jid + ".json")
        assert done["status"] == "done" and done["done"] == 2, done

        # refus permanent : rien ne lève, l'état juste reste en mémoire
        always = ReplaceRefusals(lambda d: True, left=10 ** 9)
        wjob(mod, "job-legacy.json",
             {"status": "running", "total": 1, "done": 0, "results": []})
        jid2 = "job-20260101T000002Z-abc123"
        with mod._jobs_lock:
            mod._jobs[jid2] = {"status": "running", "total": 1, "done": 0,
                               "results": [], "tasks": [two]}
        with patched(os, "replace", always), patched(mod.time, "sleep", lambda s: None):
            mod._run_tasks(jid2, [(0, two)])  # (3) compteur d'usage compris
            mod._recover_orphans()            # (2) boot
            assert mod._bump_usage("x", True) is None
        assert mod._jobs[jid2]["status"] == "done", mod._jobs[jid2]
        assert mod._jobs[jid2]["results"][0]["ok"] is True, \
            "un compteur muet a changé le résultat d'une tâche réussie"
        assert mod._jobs["job-legacy"]["status"] == "orphaned"
        assert rjob(mod, "job-legacy.json")["status"] == "running", \
            "l'écriture refusée ne doit quand même pas altérer le fichier"

        # (4) POST /v1/jobs : les 6 essais de la première écriture sont refusés
        # — la réponse part quand même (avant : _persist levait dans le
        # handler, connexion fermée sans réponse) et la persistance suivante
        # reprend tout l'état du job
        srv, port = serve(mod)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/jobs",
            data=json.dumps({"name": "x", "tasks": [two]}).encode(),
            headers={"Content-Type": "application/json"})
        first = ReplaceRefusals(lambda d: d.endswith(".json") and "usage" not in d, left=6)
        with patched(os, "replace", first), patched(mod.time, "sleep", lambda s: None):
            with urllib.request.urlopen(req, timeout=10) as r:
                created = json.load(r)
        assert created["total"] == 1 and first.n == 6, (created, first.n)
        c = wait_status(mod, created["job_id"] + ".json", "done", missing_ok=True)
        assert c["status"] == "done" and c["done"] == 1, c

        leftovers = [f for f in os.listdir(mod.JOBS_DIR) if f.endswith(".tmp")]
        assert not leftovers, f"essais ratés non nettoyés: {leftovers}"
        assert not [f for f in os.listdir(scratch) if f.endswith(".tmp")], \
            "un compteur qui ne peut pas écrire ne laisse pas de fichier à côté de lui"
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

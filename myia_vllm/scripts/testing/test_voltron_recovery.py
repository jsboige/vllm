#!/usr/bin/env python3
"""Tests de la machine à états de reprise du service harnais voltron.

SANS engine et SANS serveur : le module est chargé hors main(), ses constantes
sont repatchées vers un répertoire scratch, les appels réseau sont factices.
Couvre (CHANGES_REQUESTED ai-01 §2) :

  1. la reprise d'un job interrompu SANS doublon d'exécution ;
  2. la finalisation malgré une tâche en erreur (str dans le lot) ;
  3. N threads qui persistent le MÊME job en parallèle — rouge sur une
     implémentation à tmp partagé (JSON entrelacé / PermissionError Windows),
     vert dès que l'écriture est sérialisée à tmp unique ;
  4. le compteur d'usage REFUSE d'écrire sur un fichier illisible (l'historique
     d'adoption ne repart pas de zéro) ;
  5. la reprise ne re-compte pas les tâches relancées.

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_recovery.py -v
            (ou directement : python test_voltron_recovery.py)
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "voltron_harness_server.py")

_calls_lock = threading.Lock()
CALLS = []


def load_module(scratch):
    """Charge le serveur SANS main() et le pointe sur un scratch dir."""
    spec = importlib.util.spec_from_file_location(
        "vhs_test_%d" % id(scratch), SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __name__ != __main__ -> pas de serveur
    mod.JOBS_DIR = os.path.join(scratch, "jobs")
    mod.USAGE_PATH = os.path.join(scratch, "usage.json")
    mod._wait_engine = lambda timeout_s=300: True  # pas d'engine ici
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
    with open(os.path.join(mod.JOBS_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def wait_status(mod, name, want, timeout_s=30):
    t0 = time.time()
    j = rjob(mod, name)
    while j["status"] != want and time.time() - t0 < timeout_s:
        time.sleep(0.2)
        j = rjob(mod, name)
    return j


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
              "results": [{"task": 0, "ok": True}],
              "tasks": [{"type": "classify", "text": "t0"},
                        "t1-malformee",
                        {"type": "classify", "text": "t2"}]})

        mod._recover_orphans()
        b = wait_status(mod, "job-partial.json", "done")

        assert b["done"] == 3 and len(b["results"]) == 3, b
        assert b.get("recovered") == 1, b
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
        with open(mod.USAGE_PATH, encoding="utf-8") as f:
            assert f.read() == corrupt, "l'historique a été écrasé !"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS: {fn.__name__}", flush=True)
    print(f"{len(fns)}/{len(fns)} tests OK", flush=True)

#!/usr/bin/env python3
"""Harnais voltron — étage « b », le second lecteur (duo voltron + mini de la flotte).

Mandat user 28/11 : « s'il est trop faible pour être utile, essayer de caler un
harnais sk-agent avec le modèle de po-2025, peut-être qu'à deux ils seront
meilleurs ». Mesuré sur les deux bancs gelés (duo_bench.py / duo_analyze.py) :
la cascade gâtée a→b vaut le plafond de l'union — socle 93/120 (voltron 87,
frog 82), pack réel 32/40 (18, 28). Ces tests fixent la MÉCANIQUE du service :

  1. étage absent tant que VOLTRON_DUO_MODEL est vide (chaîne a→c d'avant) ;
  2. a passe → b n'est JAMAIS appelé, pas plus que le coordinateur ;
  3. a échoue, b passe → stage "b", coordinateur jamais appelé ;
  4. b refuse par le gate → on retombe sur c, l'échec de b reste lisible ;
  5. b lève (hub muet) → on retombe sur c, et l'échec n'est JAMAIS transitoire
     (le rejeu d'un refus de hub redonnerait le même résultat) ;
  6. chemin classify : UN seul prompt à b, même gate (classe ∈ taxonomie,
     ligne_cle verbatim), définitions du consommant APRÈS la taxonomie ;
  7. la requête de b : prompt SEC (ni brouillon de a, ni note de coordinateur),
     thinking coupé, clé hub, budget de jetons mesuré ;
  8. contrat : "b" dans l'énumération de `stage` ; compteur d'usage par étage.

Aucun moteur, aucun hub, aucun Docker : `chat` est remplacé par un routeur
qui journalise chaque appel.

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_duo.py -v
Preuve rouge : VOLTRON_SERVER_SRC=<serveur d'avant l'étage, à côté de
real_task_bench.py> python test_voltron_duo.py
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
import urllib.error
import urllib.request
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("VOLTRON_SERVER_SRC") or os.path.join(HERE, "voltron_harness_server.py")

DATA = "Le siège po-2028 sert le modèle voltron-1.1-mini depuis le 27 novembre 2026."
GOOD = '{"modele": "voltron-1.1-mini", "date": "27 novembre 2026"}'
LOG = "Traceback:\n  FileNotFoundError: le disque est plein\n  code 28"
CLASSES = ["panne", "réseau"]
CLS_GOOD = '{"classe": "panne", "ligne_cle": "FileNotFoundError: le disque est plein"}'
DUO = "frognano-test"
COORD = "coordonnateur-test"
KEY = "cle-de-test"


class DockerInterdit(BaseException):
    pass


def _no_docker(*args, **kwargs):
    raise DockerInterdit("un test ne lance jamais Docker")


@contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def load_module(scratch):
    spec = importlib.util.spec_from_file_location("vd_test_%d" % id(scratch), SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __name__ != __main__ -> pas de serveur
    mod.JOBS_DIR = os.path.join(scratch, "jobs")
    mod.USAGE_PATH = os.path.join(scratch, "usage.json")
    mod.engine_healthy = lambda timeout=2: True
    mod.subprocess = types.SimpleNamespace(run=_no_docker)
    mod.HUB_URL = "http://hub-test"
    mod.HUB_MODEL = COORD
    return mod


class Router:
    """`chat` factice : route par modèle et journalise chaque appel. Un script
    est callable(numero_d_appel, appel) -> texte, ou lève l'exception reçue."""

    def __init__(self, mod, engine, duo, coord):
        self.mod, self.script, self.calls, self.n = mod, {"engine": engine, "duo": duo,
                                                          "coord": coord}, [], {}
        self.kinds = {mod.ENGINE_MODEL: "engine", DUO: "duo", COORD: "coord"}

    def __call__(self, url, model, messages, max_tokens=400, timeout=120,
                 api_key=None, prefill=None, extra_body=None):
        call = dict(url=url, model=model, messages=messages, max_tokens=max_tokens,
                    timeout=timeout, api_key=api_key, prefill=prefill,
                    extra_body=extra_body)
        self.calls.append(call)
        kind = self.kinds[model]
        self.n[kind] = self.n.get(kind, 0) + 1
        out = self.script[kind](self.n[kind], call)
        if isinstance(out, BaseException):
            raise out
        return out

    def of(self, kind):
        return [c for c in self.calls if self.kinds[c["model"]] == kind]


def static(text):
    return lambda n, call: text


def always_fail(n, call):
    if call["prefill"] == '{"classe": "':  # étape classe de run_classify
        return 'hors_taxonomie"}'
    return "je ne sais pas du tout"


def arm(mod, engine, duo, coord, key=KEY):
    mod.DUO_MODEL = DUO
    mod.HUB_KEY = key
    router = Router(mod, engine, duo, coord)
    mod.chat = router
    return router


def extract_task():
    return {"type": "extract", "data": DATA, "fields": ["modele", "date"]}


def classify_task(**extra):
    return dict({"type": "classify", "data": LOG, "classes": CLASSES}, **extra)


def read_usage(mod):
    with open(mod.USAGE_PATH, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 1, 2, 3

def test_etage_absent_par_defaut():
    """Sans VOLTRON_DUO_MODEL, ni b ni trace de b : la chaîne a→c d'avant."""
    scratch = tempfile.mkdtemp(prefix="vd_off_")
    try:
        mod = load_module(scratch)
        with patched(mod, "DUO_MODEL", ""):
            assert mod.duo_ready() is False
            router = Router(mod, always_fail, static(GOOD), static(GOOD))
            mod.HUB_KEY, mod.chat = KEY, router
            res = mod.run_task(extract_task())
        assert res["ok"] is True and res["stage"] == "c", res
        assert res["turns"] == 4 and router.n == {"engine": 3, "coord": 1}, (res, router.n)
        assert "second lecteur" not in res["detail"], res
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_a_passe_b_jamais_appele():
    scratch = tempfile.mkdtemp(prefix="vd_a_")
    try:
        mod = load_module(scratch)
        router = arm(mod, static('"modele": "voltron-1.1-mini", "date": "27 novembre 2026"}'),
                     static(GOOD), static(GOOD))
        res = mod.run_task(extract_task())
        assert res["ok"] is True and res["stage"] == "a" and res["turns"] == 1, res
        assert router.n == {"engine": 1}, router.n

        # classify : classe + preuve du premier coup, b reste muet
        router = arm(mod, lambda n, c: 'panne"}' if n == 1 else
                     "FileNotFoundError: le disque est plein\n  code 28",
                     static(CLS_GOOD), static(CLS_GOOD))
        res = mod.run_task(classify_task())
        assert res["ok"] is True and res["stage"] == "a" and res["turns"] == 2, res
        assert router.n == {"engine": 2}, router.n
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_a_echoue_b_passe_sans_coordinateur():
    scratch = tempfile.mkdtemp(prefix="vd_b_")
    try:
        mod = load_module(scratch)
        router = arm(mod, always_fail, static(GOOD), static(GOOD))
        res = mod.run_task(extract_task())
        assert res["ok"] is True and res["stage"] == "b" and res["detail"] == "", res
        assert res["turns"] == 4 and router.n == {"engine": 3, "duo": 1}, (res, router.n)
        # le livrable est le JSON parsé, comme en a
        assert json.loads(res["answer"]) == json.loads(GOOD), res
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 4, 5

def test_b_refuse_retombe_sur_c():
    scratch = tempfile.mkdtemp(prefix="vd_c_")
    try:
        mod = load_module(scratch)
        router = arm(mod, always_fail, static("aucun JSON ici"), static(GOOD))
        res = mod.run_task(extract_task())
        assert res["ok"] is True and res["stage"] == "c", res
        assert res["turns"] == 5 and router.n == {"engine": 3, "duo": 1, "coord": 1}, (res, router.n)
        # c refuse aussi : le détail nomme l'échec de a ET celui de b
        router = arm(mod, always_fail, static("aucun JSON ici"), static("toujours rien"))
        res = mod.run_task(extract_task())
        assert res["ok"] is False and res["stage"] == "c", res
        assert "aucun objet JSON" in res["detail"] and "second lecteur" in res["detail"], res
        assert DUO in res["detail"], res
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_b_leve_retombe_sur_c_et_n_est_jamais_transitoire():
    scratch = tempfile.mkdtemp(prefix="vd_leve_")
    try:
        mod = load_module(scratch)
        down = static(urllib.error.URLError("hub muet"))
        router = arm(mod, always_fail, down, static(GOOD))
        res = mod.run_task(extract_task())
        assert res["ok"] is True and res["stage"] == "c" and res["turns"] == 5, res
        assert router.n == {"engine": 3, "duo": 1, "coord": 1}, router.n

        # c lève aussi : ni rejeu (pas transitoire), ni étiquette d'engine
        router = arm(mod, always_fail, down, static(urllib.error.URLError("hub muet")))
        res = mod.run_task(extract_task())
        assert res["ok"] is False and res["stage"] == "c", res
        assert res.get("transient") is None and mod._is_transient(res) is False, res
        assert "second lecteur" in res["detail"] and "coordinateur hub échoué" in res["detail"], res
        assert "aucun objet JSON" in res["detail"], ("l'échec de a reste lisible", res)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_sans_cle_hub_b_reste_inactif():
    """b exige la même clé que c : sans elle, ni l'un ni l'autre."""
    scratch = tempfile.mkdtemp(prefix="vd_cle_")
    try:
        mod = load_module(scratch)
        router = arm(mod, always_fail, static(GOOD), static(GOOD), key=None)
        assert mod.duo_ready() is False
        res = mod.run_task(extract_task())
        assert res["ok"] is False and res["stage"] == "a", res
        assert router.n == {"engine": 3} and "coordinateur indisponible" in res["detail"], (
            router.n, res)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 6, 7

def test_classify_un_seul_prompt_meme_gate():
    scratch = tempfile.mkdtemp(prefix="vd_cls_")
    try:
        mod = load_module(scratch)
        router = arm(mod, always_fail, static(CLS_GOOD), static(CLS_GOOD))
        res = mod.run_task(classify_task())
        assert res["ok"] is True and res["stage"] == "b" and res["turns"] == 5, res
        assert router.n == {"engine": 4, "duo": 1}, router.n  # classe + preuve + 2 réparations
        duo = router.of("duo")[0]
        prompt = duo["messages"][0]["content"]
        assert len(duo["messages"]) == 1 and duo["messages"][0]["role"] == "user", duo["messages"]
        assert prompt.startswith(f"Texte :\n{LOG}"), prompt
        assert f"classes : {CLASSES}." in prompt and '"classe"' in prompt, prompt
        assert mod.COORD_NOTE not in prompt and "je ne sais pas" not in prompt, \
            "prompt SEC : ni note de coordinateur ni brouillon de a"

        # le gate de b est le même : une ligne qui n'est pas dans le texte est refusée
        forged = '{"classe": "panne", "ligne_cle": "une ligne inventée de toutes pièces"}'
        router = arm(mod, always_fail, static(forged), static(CLS_GOOD))
        res = mod.run_task(classify_task())
        assert res["ok"] is True and res["stage"] == "c", res
        assert router.n == {"engine": 4, "duo": 1, "coord": 1}, router.n
        assert "ligne_cle introuvable" in res["detail"], res
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_classify_definitions_apres_taxonomie():
    scratch = tempfile.mkdtemp(prefix="vd_def_")
    try:
        mod = load_module(scratch)
        defs = {"panne": "définition de la panne", "réseau": "définition du réseau"}
        router = arm(mod, always_fail, static(CLS_GOOD), static(CLS_GOOD))
        res = mod.run_task(classify_task(class_definitions=defs))
        assert res["stage"] == "b", res
        prompt = router.of("duo")[0]["messages"][0]["content"]
        i_cls, i_def, i_ask = prompt.index(f"{CLASSES}."), prompt.index("- panne : "), \
            prompt.index("Renvoie UNIQUEMENT")
        assert i_cls < i_def < i_ask, prompt
        assert prompt.index("Texte :") < i_cls, ("jamais au-dessus du Texte", prompt)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_requete_du_second_lecteur():
    scratch = tempfile.mkdtemp(prefix="vd_req_")
    try:
        mod = load_module(scratch)
        router = arm(mod, always_fail, static(GOOD), static(GOOD))
        mod.run_task(extract_task())
        duo, coord = router.of("duo")[0], router.of("coord")
        assert duo["url"] == mod.HUB_URL and duo["model"] == DUO, duo
        assert duo["api_key"] == KEY, "la clé client du hub part en Bearer"
        assert duo["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}, duo
        assert duo["max_tokens"] == mod.DUO_MAX_TOKENS == 400, duo
        assert duo["prefill"] is None, ("jamais prérempli", duo)
        assert duo["timeout"] == mod.DUO_TIMEOUT_S, duo
        assert coord == [], "a→b→c : le coordinateur n'est pas payé"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 8

def test_contrat_schema_et_compteur_par_etage():
    scratch = tempfile.mkdtemp(prefix="vd_cpt_")
    try:
        mod = load_module(scratch)
        enum = mod._RESULT_SCHEMA["properties"]["stage"]["enum"]
        assert enum == ["a", "b", "c", "reject", "error", "engine-down", "engine-error"], enum
        assert "b" in mod.CAPABILITIES["chain"], mod.CAPABILITIES["chain"]

        mod._bump_usage("extract", True, stage="a")
        mod._bump_usage("extract", True, stage="b")
        mod._bump_usage("extract", True, stage="b")
        mod._bump_usage("extract", False, stage="c")
        mod._bump_usage("extract", True)  # sans étage : compté, non rangé
        u = read_usage(mod)
        assert u["tasks_total"] == 5 and u["ok"] == 4, u
        assert u["by_stage"] == {"a": {"n": 1, "ok": 1}, "b": {"n": 2, "ok": 2},
                                 "c": {"n": 1, "ok": 0}}, u
        assert u["by_type"]["extract"] == {"n": 5, "ok": 4}, u
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _post(port, path, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def test_http_et_job_portent_le_stage_b():
    """Le compte par étage tient sur les trois chemins réels : /v1/task,
    façade chat, job en fond."""
    scratch = tempfile.mkdtemp(prefix="vd_http_")
    srv = None
    try:
        mod = load_module(scratch)
        arm(mod, always_fail, static(GOOD), static(GOOD))
        mod.Handler.log_message = lambda self, fmt, *args: None
        srv = mod.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]

        res = _post(port, "/v1/task", extract_task())
        assert res["stage"] == "b" and res["ok"] is True, res
        chat = {"model": mod.ENGINE_MODEL, "messages": [
            {"role": "user", "content": json.dumps(extract_task())}]}
        res = _post(port, "/v1/chat/completions", chat)
        assert json.loads(res["choices"][0]["message"]["content"])["stage"] == "b", res
        job = _post(port, "/v1/jobs", {"name": "duo", "tasks": [extract_task(),
                                                                extract_task()]})
        for _ in range(200):
            if mod._jobs[job["job_id"]]["status"] == "done":
                break
            time.sleep(0.05)
        done = mod._jobs[job["job_id"]]
        assert [r["stage"] for r in done["results"]] == ["b", "b"], done["results"]

        u = read_usage(mod)
        assert u["by_stage"] == {"b": {"n": 4, "ok": 4}} and u["job_tasks"] == 2, u
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/usage", timeout=10) as r:
            assert json.load(r)["by_stage"] == u["by_stage"]
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))

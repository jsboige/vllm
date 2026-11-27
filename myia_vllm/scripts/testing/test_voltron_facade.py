#!/usr/bin/env python3
"""Tests de la façade OpenAI du harnais voltron (26/11).

SANS engine : le module est chargé hors main(), `run_task` est factice et
`engine_healthy` toujours vrai ; les tests HTTP utilisent un serveur éphémère
sur un port libre (jamais :5029). Aucun test ne lance Docker.

Couvre :
  1. GET /v1/models : un seul modèle (`voltron-harness`), sa fiche, 404 OpenAI
     pour un autre id ;
  2. POST /v1/chat/completions : le contenu du dernier message user porte la
     tâche, `choices[0].message.content` est le JSON du résultat ;
  3. la tâche se lit aussi dans un bloc ```json entouré de prose, ou dans des
     parties de contenu `{type: text}` ; system et historique sont ignorés ;
  4. un message sans tâche reçoit la carte d'emploi — aucune tâche exécutée,
     compteur d'adoption inchangé (le service ne fait pas de chat libre) ;
  5. `messages` absent ou sans message user : 400 au format OpenAI ;
  6. `stream: true` : SSE (rôle, contenu, fin, [DONE]), contenu identique au
     mode JSON, aucun en-tête CORS ;
  7. le compteur d'adoption compte une tâche par appel, sauf en-tête
     `X-Voltron-Probe: 1` ;
  8. un tableau JSON (lot) et un JSON cassé donnent un `reject` actionnable —
     aucune tâche lancée ;
  9. un corps non objet sur /v1/task est un 400, et une tâche malformée
     (`data` numérique) devient un résultat `stage: error` au lieu d'une
     connexion fermée sans réponse ;
 10. /openapi.json publie les routes de la façade, sans adresse ni `servers`.

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_facade.py -v
            (ou directement : python test_voltron_facade.py)
Preuve rouge : VOLTRON_SERVER_SRC=<serveur sans la façade, à côté de
real_task_bench.py> python test_voltron_facade.py
"""
import http.client
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("VOLTRON_SERVER_SRC") or os.path.join(HERE, "voltron_harness_server.py")

TASK = {"type": "extract", "data": "Rapport : temp 42, score 97",
        "fields": ["temp", "score"], "verbatim": False}


class DockerInterdit(BaseException):
    """Un test ne lance jamais Docker (même garde que test_voltron_outage.py)."""


def _no_docker(*args, **kwargs):
    raise DockerInterdit("un test ne lance jamais Docker : poser un faux subprocess.run")


def load_module(scratch, run_task=None):
    spec = importlib.util.spec_from_file_location("vhf_test_%d" % id(scratch), SRC)
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


def serve(mod):
    mod.Handler.log_message = lambda self, fmt, *args: None
    srv = mod.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def call(port, method, path, payload=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        body = None if payload is None else json.dumps(payload).encode()
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        raw = r.read()
        return r.status, dict(r.getheaders()), raw
    finally:
        conn.close()


def chat(port, payload, headers=None):
    status, hdrs, raw = call(port, "POST", "/v1/chat/completions", payload, headers)
    return status, hdrs, json.loads(raw)


def sse_events(raw):
    events = []
    for block in raw.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data: "), block[:80]
        data = block[len("data: "):]
        events.append(None if data == "[DONE]" else json.loads(data))
    return events


def read_usage(mod):
    if not os.path.exists(mod.USAGE_PATH):
        return {"tasks_total": 0, "jobs_total": 0}
    with open(mod.USAGE_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_models_un_seul_modele():
    scratch = tempfile.mkdtemp(prefix="vhf_models_")
    srv = None
    try:
        mod = load_module(scratch)
        srv, port = serve(mod)
        status, hdrs, raw = call(port, "GET", "/v1/models")
        assert status == 200, status
        doc = json.loads(raw)
        assert doc["object"] == "list", doc
        assert [m["id"] for m in doc["data"]] == ["voltron-harness"], doc
        assert doc["data"][0]["object"] == "model", doc
        assert hdrs.get("Access-Control-Allow-Origin") is None, "pas de CORS"

        status, _, raw = call(port, "GET", "/v1/models/voltron-harness")
        assert status == 200 and json.loads(raw)["id"] == "voltron-harness"

        status, _, raw = call(port, "GET", "/v1/models/qwen3.6-35b-a3b")
        assert status == 404, status
        err = json.loads(raw)["error"]
        assert err["code"] == "model_not_found" and err["type"] == "invalid_request_error", err
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_chat_transporte_la_tache_et_rend_le_resultat():
    scratch = tempfile.mkdtemp(prefix="vhf_task_")
    srv = None
    try:
        seen = []

        def fake(t):
            seen.append(t)
            return {"ok": True, "stage": "a", "answer": json.dumps({"temp": 42, "score": 97}),
                    "detail": "", "turns": 1, "dt_s": 0.01}

        mod = load_module(scratch, run_task=fake)
        srv, port = serve(mod)
        status, _, doc = chat(port, {"model": "voltron-harness", "temperature": 0.7,
                                     "messages": [{"role": "system", "content": "ignore-moi"},
                                                  {"role": "user", "content": json.dumps(TASK)}]})
        assert status == 200, status
        assert seen == [TASK], seen
        assert doc["object"] == "chat.completion", doc
        assert doc["model"] == "voltron-harness"
        choice = doc["choices"][0]
        assert choice["finish_reason"] == "stop" and choice["index"] == 0, choice
        assert choice["message"]["role"] == "assistant", choice
        res = json.loads(choice["message"]["content"])
        assert res["ok"] is True and json.loads(res["answer"]) == {"temp": 42, "score": 97}, res
        assert doc["usage"]["total_tokens"] == 0, doc["usage"]
        assert doc["x_voltron"]["kind"] == "task", doc["x_voltron"]
        assert doc["x_voltron"]["ignored_params"] == ["temperature"], doc["x_voltron"]
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_chat_bloc_json_et_parties_de_contenu():
    scratch = tempfile.mkdtemp(prefix="vhf_parse_")
    srv = None
    try:
        seen = []
        mod = load_module(scratch, run_task=lambda t: seen.append(t) or
                          {"ok": True, "stage": "a", "answer": "{}", "detail": "",
                           "turns": 1, "dt_s": 0.0})
        srv, port = serve(mod)
        prose = "Voici la tâche :\n```json\n" + json.dumps(TASK) + "\n```\nmerci"
        status, _, doc = chat(port, {"messages": [{"role": "user", "content": prose}]})
        assert status == 200 and doc["x_voltron"]["kind"] == "task", doc
        assert seen == [TASK], seen

        parts = [{"type": "text", "text": "prélude"},
                 {"type": "text", "text": json.dumps({"type": "classify", "data": "x",
                                                      "classes": ["a", "b"]})}]
        status, _, doc = chat(port, {"messages": [{"role": "user", "content": parts}]})
        assert status == 200 and doc["x_voltron"]["kind"] == "task", doc
        assert seen[-1]["type"] == "classify", seen
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_chat_sans_tache_rend_la_carte():
    scratch = tempfile.mkdtemp(prefix="vhf_help_")
    srv = None
    try:
        seen = []
        mod = load_module(scratch, run_task=lambda t: seen.append(t) or {})
        srv, port = serve(mod)
        status, _, doc = chat(port, {"messages": [
            {"role": "user", "content": "bonjour, peux-tu me résumer ce document ?"}]})
        assert status == 200, status
        assert seen == [], "le service ne fait pas de chat libre"
        assert doc["x_voltron"]["kind"] == "help", doc["x_voltron"]
        card = json.loads(doc["choices"][0]["message"]["content"])
        assert "service" in card and "howto" in card and "example" in card, card
        assert read_usage(mod).get("tasks_total", 0) == 0, read_usage(mod)
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_chat_messages_invalides_400():
    scratch = tempfile.mkdtemp(prefix="vhf_400_")
    srv = None
    try:
        mod = load_module(scratch)
        srv, port = serve(mod)
        status, _, doc = chat(port, {"model": "voltron-harness"})
        assert status == 400 and doc["error"]["param"] == "messages", doc
        assert doc["error"]["type"] == "invalid_request_error", doc
        status, _, doc = chat(port, {"messages": [{"role": "system", "content": "s"}]})
        assert status == 400 and "role=user" in doc["error"]["message"], doc
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_chat_stream_sse():
    scratch = tempfile.mkdtemp(prefix="vhf_sse_")
    srv = None
    try:
        res = {"ok": True, "stage": "a", "answer": "{\"temp\": 42}", "detail": "",
               "turns": 1, "dt_s": 0.01}
        mod = load_module(scratch, run_task=lambda t: dict(res))
        srv, port = serve(mod)
        status, hdrs, raw = call(port, "POST", "/v1/chat/completions",
                                 {"messages": [{"role": "user", "content": json.dumps(TASK)}],
                                  "stream": True})
        assert status == 200, status
        assert (hdrs.get("Content-Type") or "").startswith("text/event-stream"), hdrs
        assert hdrs.get("Access-Control-Allow-Origin") is None, "pas de CORS"
        events = sse_events(raw)
        assert events[-1] is None, "le flux se termine par data: [DONE]"
        chunks = events[:-1]
        assert [c["object"] for c in chunks] == ["chat.completion.chunk"] * 3, chunks
        assert chunks[0]["choices"][0]["delta"]["role"] == "assistant", chunks[0]
        text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
        assert json.loads(text) == res, text
        final = chunks[-1]["choices"][0]
        assert final["finish_reason"] == "stop" and final["delta"] == {}, final
        assert chunks[-1]["usage"]["total_tokens"] == 0, chunks[-1]
        assert chunks[-1]["x_voltron"]["kind"] == "task", chunks[-1]
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_compteur_et_sonde_sur_la_facade():
    scratch = tempfile.mkdtemp(prefix="vhf_usage_")
    srv = None
    try:
        ok = {"ok": True, "stage": "a", "answer": "{}", "detail": "", "turns": 1, "dt_s": 0.0}
        mod = load_module(scratch, run_task=lambda t: dict(ok))
        srv, port = serve(mod)
        body = {"messages": [{"role": "user", "content": json.dumps(TASK)}]}
        chat(port, body, headers={"X-Voltron-Probe": "1"})
        assert read_usage(mod)["tasks_total"] == 0, "une sonde n'est pas de l'adoption"
        chat(port, body)
        u = read_usage(mod)
        assert u["tasks_total"] == 1 and u["ok"] == 1, u
        assert u["by_type"]["extract"] == {"n": 1, "ok": 1}, u
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_lot_et_json_casse_sont_des_rejects():
    scratch = tempfile.mkdtemp(prefix="vhf_reject_")
    srv = None
    try:
        seen = []
        mod = load_module(scratch, run_task=lambda t: seen.append(t) or {})
        srv, port = serve(mod)
        status, _, doc = chat(port, {"messages": [
            {"role": "user", "content": json.dumps([TASK, TASK])}]})
        assert status == 200 and doc["x_voltron"]["kind"] == "batch", doc
        res = json.loads(doc["choices"][0]["message"]["content"])
        assert res["stage"] == "reject" and "/v1/jobs" in res["detail"], res
        status, _, doc = chat(port, {"messages": [
            {"role": "user", "content": '{"type": "extract", '}]})
        assert doc["x_voltron"]["kind"] == "invalid", doc
        res = json.loads(doc["choices"][0]["message"]["content"])
        assert res["stage"] == "reject" and "JSON invalide" in res["detail"], res
        assert seen == [], "un reject n'exécute aucune tâche"
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_tache_malformee_rend_une_erreur_pas_une_connexion_morte():
    scratch = tempfile.mkdtemp(prefix="vhf_sync_")
    srv = None
    try:
        mod = load_module(scratch)  # run_task réel : data numérique -> TypeError
        srv, port = serve(mod)
        status, _, raw = call(port, "POST", "/v1/task", [1, 2])
        assert status == 400 and "objet JSON attendu" in json.loads(raw)["error"], raw
        status, _, raw = call(port, "POST", "/v1/task",
                              {"type": "extract", "data": 123, "fields": ["a"]})
        assert status == 200, "la connexion doit répondre, pas se fermer"
        res = json.loads(raw)
        assert res["stage"] == "error" and "TypeError" in res["detail"], res
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_openapi_publie_la_facade():
    scratch = tempfile.mkdtemp(prefix="vhf_openapi_")
    srv = None
    try:
        mod = load_module(scratch)
        srv, port = serve(mod)
        status, _, raw = call(port, "GET", "/openapi.json")
        assert status == 200
        doc = json.loads(raw)
        for p in ("/v1/chat/completions", "/v1/models"):
            assert p in doc["paths"], p
        assert "servers" not in doc, "aucune adresse ne vit dans le code"
        text = raw.decode("utf-8")
        assert not __import__("re").search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text), "IP dans le contrat"
        schema = doc["paths"]["/v1/chat/completions"]["post"]["responses"]["200"][
            "content"]["application/json"]["schema"]
        assert "choices" in schema["required"] and "x_voltron" in schema["properties"], schema
        caps = mod.FACADE_HELP
        assert "POST /v1/jobs" in caps["more"], caps
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

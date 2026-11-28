#!/usr/bin/env python3
"""Harnais voltron — écoute LAN gardée par clé entrante (28/11).

Prérequis nommé par le propriétaire du hub claudish (DM 28/11) pour qu'une
entrée d'endpoint au hub ait un sens : le hub `192.168.0.50` ne peut pas
joindre le loopback d'une autre machine. Ce que ces tests fixent, dans l'ordre
où le siège s'y est engagé — **la garde d'abord, l'écoute ensuite** :

  1. le défaut reste le loopback sans clé (les sondes de vigie ne changent pas) ;
  2. un bind non-loopback SANS clé refuse le démarrage (jamais d'écoute nue) ;
  3. loopback = toujours servi ; distant = clé exigée, en `Authorization:
     Bearer` (ce que le hub sait déjà envoyer) ou en `X-Voltron-Key` ;
  4. câblage HTTP réel : `/health` ouvert, le reste à 401 sans clé, et un
     POST refusé n'atteint JAMAIS le moteur (le corps n'est même pas lu) ;
  5. l'empreinte `sha256[:12]` de la clé peut être publiée — la bannière ne
     contient jamais la valeur.

Aucun moteur, aucun hub, aucun Docker : `engine_healthy` et `_run_sync` sont
remplacés, la clé des tests est une valeur jetable.

Exécution : python -m pytest myia_vllm/scripts/testing/test_voltron_inbound.py -v
Preuve rouge : VOLTRON_SERVER_SRC=<serveur d'avant le 28/11> python test_voltron_inbound.py
"""
import contextlib
import http.client
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import types
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("VOLTRON_SERVER_SRC") or os.path.join(HERE, "voltron_harness_server.py")

KEY = "cle-entrante-de-test-0123456789"


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
    spec = importlib.util.spec_from_file_location("vi_test_%d" % id(scratch), SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.JOBS_DIR = os.path.join(scratch, "jobs")
    mod.USAGE_PATH = os.path.join(scratch, "usage.json")
    mod.engine_healthy = lambda timeout=2: True
    mod.subprocess = types.SimpleNamespace(run=_no_docker)
    return mod


# ------------------------------------------------------------------ 1, 2

def test_defaut_loopback_sans_cle():
    """Rien de configuré : le service reste sur le loopback, sans clé."""
    scratch = tempfile.mkdtemp(prefix="vi_def_")
    try:
        mod = load_module(scratch)
        if "VOLTRON_BIND" not in os.environ:
            assert mod.BIND == "127.0.0.1", mod.BIND
        if "VOLTRON_INBOUND_KEY" not in os.environ:
            assert mod.INBOUND_KEY == "", mod.INBOUND_KEY
        assert mod.validate_bind("127.0.0.1", "") is None
        assert mod.validate_bind("::1", "") is None
        assert mod.validate_bind("::ffff:127.0.0.1", "") is None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_bind_lan_sans_cle_refuse():
    """La garde passe avant l'écoute : 0.0.0.0 sans clé = refus explicite."""
    scratch = tempfile.mkdtemp(prefix="vi_refus_")
    try:
        mod = load_module(scratch)
        for bind in ("0.0.0.0", "192.168.0.28", "::"):
            msg = mod.validate_bind(bind, "")
            assert msg and "VOLTRON_INBOUND_KEY" in msg, (bind, msg)
            assert mod.validate_bind(bind, KEY) is None, bind

        # chemin réel : main() sort AVANT de créer le serveur
        def pas_de_serveur(*a, **k):
            raise DockerInterdit("le serveur n'aurait pas dû être créé")

        with patched(mod, "BIND", "0.0.0.0"), patched(mod, "INBOUND_KEY", ""), \
                patched(mod, "ThreadingHTTPServer", pas_de_serveur), \
                patched(mod, "_recover_orphans", lambda: None):
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    mod.main()
            except SystemExit as exc:
                assert exc.code == 1, exc.code
            else:
                raise AssertionError("main() aurait dû refuser de démarrer")
        assert "REFUS DE DEMARRAGE" in out.getvalue(), out.getvalue()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 3

def test_matrice_autorisation():
    """Loopback toujours servi ; distant = clé, Bearer ou en-tête, à temps constant."""
    scratch = tempfile.mkdtemp(prefix="vi_auth_")
    try:
        mod = load_module(scratch)
        h = {"X-Voltron-Key": KEY, "Authorization": "Bearer " + KEY}
        # loopback : servi même sans aucun en-tête, clé configurée ou non
        for ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "127.5.6.7"):
            assert mod.inbound_authorized(ip, {}, key=KEY) is True, ip
            assert mod.inbound_authorized(ip, {}, key="") is True, ip
        # distant, clé configurée : refus sans en-tête, refus si fausse
        assert mod.inbound_authorized("192.168.0.50", {}, key=KEY) is False
        assert mod.inbound_authorized("192.168.0.50", {"X-Voltron-Key": "fausse"},
                                      key=KEY) is False
        assert mod.inbound_authorized("192.168.0.50",
                                      {"Authorization": "Bearer fausse"}, key=KEY) is False
        # accepté : en-tête dédié, ou Bearer (ce que le hub sait déjà envoyer)
        assert mod.inbound_authorized("192.168.0.50", {"X-Voltron-Key": KEY},
                                      key=KEY) is True
        assert mod.inbound_authorized("192.168.0.50",
                                      {"Authorization": "Bearer " + KEY}, key=KEY) is True
        assert mod.inbound_authorized("192.168.0.50",
                                      {"Authorization": "bearer " + KEY}, key=KEY) is True
        # aucun schéma = refus (une clé nue dans Authorization n'est pas un contrat)
        assert mod.inbound_authorized("192.168.0.50",
                                      {"Authorization": KEY}, key=KEY) is False
        assert mod.inbound_authorized("192.168.0.50", h, key=KEY) is True
        # clé vide côté serveur : distant servi (le service ne peut alors
        # écouter qu'en loopback, validate_bind l'impose)
        assert mod.inbound_authorized("192.168.0.50", {}, key="") is True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 4

def serve(mod):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        data = None if body is None else json.dumps(body).encode()
        c.request(method, path, body=data,
                  headers=dict({"Content-Type": "application/json"}, **(headers or {})))
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")
    finally:
        c.close()


def test_cablage_http():
    """Distant simulé (`_is_loopback` forcé à False) : /health ouvert, le reste gardé."""
    scratch = tempfile.mkdtemp(prefix="vi_http_")
    srv = None
    try:
        mod = load_module(scratch)
        touched = []

        def run_sync(task, prefix=""):
            touched.append(task)
            return {"ok": True, "stage": "a"}

        mod._run_sync = run_sync
        with patched(mod, "_is_loopback", lambda ip: False), \
                patched(mod, "INBOUND_KEY", KEY):
            srv, port = serve(mod)
            # 1. /health reste ouvert : une sonde de vivacité sans identifiant
            st, body = call(port, "GET", "/health")
            assert st == 200 and body["server"] == "up", (st, body)
            # 2. tout le reste exige la clé
            st, body = call(port, "GET", "/v1/models")
            assert st == 401 and body["error"]["code"] == "unauthorized", (st, body)
            st, body = call(port, "GET", "/v1/models", headers={"X-Voltron-Key": "fausse"})
            assert st == 401, (st, body)
            # 3. en-tête dédié ou Bearer : servi
            st, body = call(port, "GET", "/v1/models", headers={"X-Voltron-Key": KEY})
            assert st == 200 and body["data"], (st, body)
            st, body = call(port, "GET", "/v1/usage", headers={"Authorization": "Bearer " + KEY})
            assert st == 200, (st, body)
            # 4. un POST refusé n'atteint jamais le moteur
            task = {"type": "extract", "data": "Le siège sert voltron depuis 27/11.",
                    "fields": ["x"]}
            st, _ = call(port, "POST", "/v1/task", task)
            assert st == 401, st
            assert touched == [], "le moteur a été appelé malgré le 401"
            # 5. avec la clé, le POST passe le garde puis la tâche
            st, body = call(port, "POST", "/v1/task", task,
                            headers={"Authorization": "Bearer " + KEY,
                                     "X-Voltron-Probe": "1"})
            assert st == 200 and body["ok"] is True, (st, body)
            assert len(touched) == 1, touched
            # 6. OPTIONS (pré-vol d'un chargeur) inchangé, sans CORS
            st, _ = call(port, "OPTIONS", "/v1/task")
            assert st == 204, st
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


def test_loopback_reel_sans_cle_configuree():
    """Le trafic du siège lui-même reste servi sans clé (vigie inchangée)."""
    scratch = tempfile.mkdtemp(prefix="vi_local_")
    srv = None
    try:
        mod = load_module(scratch)
        with patched(mod, "INBOUND_KEY", ""):
            srv, port = serve(mod)
            st, body = call(port, "GET", "/v1/models")
            assert st == 200 and body["data"], (st, body)
            st, body = call(port, "GET", "/v1/capabilities")
            assert st == 200, st
    finally:
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ 5

def test_banniere_empreinte_pas_la_cle():
    """main() peut démarrer sur le LAN avec clé ; la bannière n'imprime qu'une empreinte."""
    import hashlib
    scratch = tempfile.mkdtemp(prefix="vi_banner_")
    try:
        mod = load_module(scratch)
        seen = {}

        class FauxServeur:
            def __init__(self, addr, handler):
                seen["addr"] = addr

            def serve_forever(self):
                raise DockerInterdit("on ne sert pas pendant un test")

        with patched(mod, "BIND", "0.0.0.0"), patched(mod, "INBOUND_KEY", KEY), \
                patched(mod, "ThreadingHTTPServer", FauxServeur), \
                patched(mod, "_recover_orphans", lambda: None):
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    mod.main()
            except DockerInterdit:
                pass
        banner = out.getvalue()
        fp = hashlib.sha256(KEY.encode()).hexdigest()[:12]
        assert seen["addr"] == ("0.0.0.0", mod.PORT), seen["addr"]
        assert "empreinte " + fp in banner, banner
        assert KEY not in banner, "la bannière contient la clé en clair"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except BaseException as exc:  # noqa: BLE001 - rapport de test
                failed += 1
                print("FAIL %s : %r" % (name, exc))
    sys.exit(1 if failed else 0)

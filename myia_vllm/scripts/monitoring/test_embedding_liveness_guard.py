#!/usr/bin/env python3
"""Unit tests for the `docker desktop restart` rails of the liveness guard.

Context (2026-11-26, cycle 182): under host memory pressure `docker version`
timed out six times while the engine was answering real requests. Each timeout
produced a `docker desktop restart`, with neither rail nor cap, and one of those
restarts opened a 32-minute outage. The rails added on top of the 2026-10-24
mandate are locked here:

  * the SERVICE decides whether the engine is mute, not the CLI (a CLI timeout
    with a POST that honours the contract restarts nothing, and no docker-driven
    gesture runs for the rest of the pass);
  * a real Desktop restart is spaced by DESKTOP_RESTART_MIN_GAP and capped at
    DESKTOP_RESTART_CAP_PER_HOUR;
  * the pass returns at once instead of blocking on the restart;
  * a deliberately stopped Docker Desktop is still a SKIP.

Every probe and every subprocess is replaced: nothing here touches Docker, the
network or a GPU.

    python -m unittest discover -s myia_vllm/scripts/monitoring -p "test_embedding_liveness_guard.py"
"""
import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

GUARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embedding_liveness_guard.py")
_spec = importlib.util.spec_from_file_location("embedding_liveness_guard_under_test", GUARD_PATH)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def emb_ok(path="sidecar"):
    return {"check": "embeddings", "path": path, "status": 200, "ok": True,
            "model": "qwen3-4b-awq-embedding", "dims": 2560}


def emb_fail(path="sidecar", status=502):
    return {"check": "embeddings", "path": path, "status": status, "ok": False,
            "error": "HTTP %s" % status}


def whisper_ok():
    return {"check": "whisper", "health_status": 200, "models_status": 200,
            "ok": True, "deep": False}


def whisper_down():
    return {"check": "whisper", "health_status": 502, "models_status": 502,
            "ok": False, "error": "HTTP 502", "deep": False}


class OnePassRailTests(unittest.TestCase):
    def run_pass(self, *, engine=("29.9.3", None), service=None, service_sequence=None,
                 direct=None, desktop_running=True, dry_run=False, budget_state=None,
                 whisper=None):
        """Drive one_pass with everything replaced.

        Returns (result, desktop_calls, all_docker_calls, saved_state).
        """
        service = emb_ok() if service is None else service
        whisper = whisper_ok() if whisper is None else whisper
        direct = emb_fail("engine") if direct is None else direct
        docker_calls = []

        def fake_run(cmd, **kwargs):
            docker_calls.append((list(cmd), kwargs.get("timeout")))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        seq = list(service_sequence) if service_sequence else None

        def fake_probe(url, key, tag):
            if tag == "engine":
                return direct
            if seq:
                return seq.pop(0)
            return service

        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state.json")
            if budget_state is not None:
                with open(state, "w", encoding="utf-8") as fh:
                    json.dump(budget_state, fh)
            args = argparse.Namespace(
                env=os.path.join(tmp, "absent.env"),
                log=os.path.join(tmp, "log.jsonl"),
                state=state,
                dry_run=dry_run,
                deep_whisper=False,
                budget=guard.RestartBudget(state),
            )
            with mock.patch.object(guard, "read_key", return_value="test-key"), \
                 mock.patch.object(guard, "engine_status", return_value=engine), \
                 mock.patch.object(guard, "probe_embeddings", side_effect=fake_probe), \
                 mock.patch.object(guard, "probe_whisper", return_value=whisper), \
                 mock.patch.object(guard, "docker_desktop_running", return_value=desktop_running), \
                 mock.patch.object(guard, "container_state", return_value=("running", "healthy")), \
                 mock.patch.object(guard, "age_seconds", return_value=3600.0), \
                 mock.patch.object(guard, "wait_healthy", return_value=True), \
                 mock.patch.object(guard.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(guard.time, "sleep", lambda _s: None):
                result = guard.one_pass(args)
            saved = {}
            if os.path.exists(state):
                with open(state, encoding="utf-8") as fh:
                    saved = json.load(fh)
        desktop_calls = [c for c in docker_calls if c[0][:3] == ["docker", "desktop", "restart"]]
        return result, desktop_calls, docker_calls, saved

    # -- the healthy pass stays silent and gesture-free --------------------
    def test_healthy_path_makes_no_docker_gesture(self):
        result, desktop, docker_calls, _ = self.run_pass()
        self.assertEqual(result["verdict"], "OK")
        self.assertEqual(docker_calls, [])
        self.assertEqual(desktop, [])

    # -- 2026-11-26: a CLI timeout with a live service is NOT an outage ----
    def test_cli_timeout_with_service_answering_never_restarts(self):
        result, desktop, docker_calls, saved = self.run_pass(
            engine=(None, "TimeoutExpired: 45"), service=emb_ok())
        self.assertEqual(result["verdict"], "OK")
        self.assertEqual(desktop, [])
        self.assertEqual(docker_calls, [])
        self.assertEqual(saved, {})
        engine_check = [c for c in result["checks"] if c["check"] == "engine"][0]
        self.assertTrue(engine_check["ok"])
        self.assertIn("docker CLI mute", engine_check["note"])

    def test_cli_timeout_also_skips_container_restarts(self):
        # Whisper is down AND the CLI is mute: no docker gesture at all.
        result, desktop, docker_calls, _ = self.run_pass(
            engine=(None, "TimeoutExpired: 45"), service=emb_ok(), whisper=whisper_down())
        self.assertEqual(result["verdict"], "DEGRADED")
        self.assertEqual(docker_calls, [])
        self.assertTrue(any("SKIP restart of whisper-webui: docker CLI mute" in a
                            for a in result["actions"]), result["actions"])

    def test_one_transient_post_failure_is_absorbed_by_the_retry(self):
        result, desktop, docker_calls, _ = self.run_pass(
            engine=(None, "TimeoutExpired: 45"),
            service_sequence=[emb_fail(), emb_ok()])
        self.assertEqual(result["verdict"], "OK")
        self.assertEqual(docker_calls, [])
        self.assertEqual(desktop, [])

    # -- engine down + service silent + Desktop running: the mandate ------
    def test_service_silent_issues_exactly_one_restart(self):
        result, desktop, docker_calls, saved = self.run_pass(
            engine=(None, "rc=1"), service=emb_fail())
        self.assertEqual(result["verdict"], "ENGINE_DOWN")
        self.assertEqual(len(desktop), 1)
        self.assertEqual(desktop[0][0], ["docker", "desktop", "restart"])
        self.assertEqual(desktop[0][1], guard.DESKTOP_RESTART_CLI_TIMEOUT)
        self.assertEqual(len(saved[guard.DESKTOP_RESTART_KEY]), 1)
        # no blocking wait: the only docker call is the restart itself
        self.assertEqual(len(docker_calls), 1)

    def test_second_restart_blocked_by_spacing(self):
        recent = {"__docker_desktop__": [time.time() - 60]}
        result, desktop, _, _ = self.run_pass(
            engine=(None, "rc=1"), service=emb_fail(), budget_state=recent)
        self.assertEqual(result["verdict"], "ENGINE_DOWN")
        self.assertEqual(desktop, [])
        self.assertTrue(any("SKIP docker desktop restart" in a for a in result["actions"]),
                        result["actions"])

    def test_cap_blocks_a_restart_older_than_the_spacing(self):
        hist = {"__docker_desktop__": [time.time() - 1700, time.time() - 1000]}
        result, desktop, _, saved = self.run_pass(
            engine=(None, "rc=1"), service=emb_fail(), budget_state=hist)
        self.assertEqual(desktop, [])
        self.assertTrue(any("cap reached" in a for a in result["actions"]),
                        result["actions"])
        self.assertEqual(len(saved["__docker_desktop__"]), 2)  # unchanged

    def test_dry_run_never_calls_docker(self):
        result, desktop, docker_calls, saved = self.run_pass(
            engine=(None, "rc=1"), service=emb_fail(), dry_run=True)
        self.assertEqual(result["verdict"], "ENGINE_DOWN")
        self.assertEqual(docker_calls, [])
        self.assertTrue(any("would docker desktop restart" in a for a in result["actions"]),
                        result["actions"])
        self.assertNotIn(guard.DESKTOP_RESTART_KEY, saved)

    def test_stopped_docker_desktop_is_a_skip(self):
        result, desktop, docker_calls, _ = self.run_pass(
            engine=(None, "rc=1"), service=emb_fail(), desktop_running=False)
        self.assertEqual(result["verdict"], "SKIP_ENGINE_STOPPED")
        self.assertEqual(docker_calls, [])


class RestartBudgetTests(unittest.TestCase):
    def test_elapsed_is_none_then_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = guard.RestartBudget(os.path.join(tmp, "state.json"))
            self.assertIsNone(b.elapsed("x"))
            b.record("x")
            self.assertGreater(b.elapsed("x"), 0)
            self.assertLess(b.elapsed("x"), 5)

    def test_allow_honours_an_explicit_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = guard.RestartBudget(os.path.join(tmp, "state.json"))
            now = time.time()
            b.data["x"] = [now - 3000, now - 2000]  # inside the hour, both
            self.assertFalse(b.allow("x"))
            self.assertFalse(b.allow("x", cap=2))
            self.assertTrue(b.allow("x", cap=3))


if __name__ == "__main__":
    unittest.main(verbosity=2)

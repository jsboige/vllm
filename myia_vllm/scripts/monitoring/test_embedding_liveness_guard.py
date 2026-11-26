#!/usr/bin/env python3
"""Unit tests for the rails of the liveness guard.

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

Context (2026-11-26, Maintenance `docker-desktop-orphan-stacking-po2023`): the
task runs a pass under `ExecutionTimeLimit = PT10M`; a pass killed there
survives as a detached orphan. The wall-clock budget of one pass is locked in
`PassBudgetTests`, on a faked clock.

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
from datetime import datetime, timezone
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


class PassBudgetTests(unittest.TestCase):
    """One pass must end well before the launcher's PT10M.

    The task runs the pass through a hidden `wscript` launcher under
    `ExecutionTimeLimit = PT10M`. Past that limit the launcher is killed and the
    Python process survives as a detached orphan, which `IgnoreNew` no longer
    covers: the next tick starts a second pass on top. The summed timeouts of
    the "everything is down" path were ~22 minutes (1 315 s).

    Everything runs on a faked clock: each docker CLI call and each HTTP probe
    costs the time written in `costs`. `age_seconds`, `container_state`,
    `wait_healthy` and `engine_status` run for real against the fake CLI.
    """

    # What `docker inspect` answers: Go emits nanosecond precision.
    STARTED = "2026-11-26T12:00:00.000000000Z"
    # The fake clock starts one hour after STARTED, i.e. past the boot rail.
    T0 = datetime(2026, 11, 26, 13, 0, 0, tzinfo=timezone.utc).timestamp()

    def run_timed(self, *, costs, probe, states, version="29.9.3", sidecar_capped=False,
                  desktop_running=True):
        """Drive one_pass on a faked clock.

        `probe(tag, restarted)` returns the probe result, `states(name)` the
        `docker inspect` answer "status|health". Returns (result, elapsed_s, cmds).
        """
        clock = {"t": self.T0}
        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(list(cmd))
            if cmd[:2] == ["docker", "version"]:
                clock["t"] += costs["version"]
                if version is None:
                    raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
                return subprocess.CompletedProcess(cmd, 0, stdout=version + "\n", stderr="")
            if cmd[:2] == ["docker", "inspect"]:
                clock["t"] += costs["inspect"]
                out = self.STARTED if "StartedAt" in cmd[-1] else states(cmd[2])
                return subprocess.CompletedProcess(cmd, 0, stdout=out + "\n", stderr="")
            if cmd[:2] == ["docker", "restart"]:
                clock["t"] += costs["restart"]
                return subprocess.CompletedProcess(cmd, 0, stdout=cmd[2] + "\n", stderr="")
            if cmd[:3] == ["docker", "desktop", "restart"]:
                clock["t"] += costs["desktop"]
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            raise AssertionError("unexpected command %r" % (cmd,))

        def restarted():
            return [c[2] for c in cmds if c[:2] == ["docker", "restart"]]

        def fake_probe(url, key, tag):
            clock["t"] += costs["probe"]
            return probe(tag, restarted())

        def fake_whisper(deep, key=None):
            clock["t"] += 30
            return whisper_ok()

        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state.json")
            if sidecar_capped:
                with open(state, "w", encoding="utf-8") as fh:
                    json.dump({guard.SIDECAR_CONTAINER: [self.T0 - 60, self.T0 - 120]}, fh)
            args = argparse.Namespace(
                env=os.path.join(tmp, "absent.env"),
                log=os.path.join(tmp, "log.jsonl"),
                state=state,
                dry_run=False,
                deep_whisper=False,
                budget=guard.RestartBudget(state),
            )
            with mock.patch.object(guard, "read_key", return_value="test-key"), \
                 mock.patch.object(guard, "probe_embeddings", side_effect=fake_probe), \
                 mock.patch.object(guard, "probe_whisper", side_effect=fake_whisper), \
                 mock.patch.object(guard, "docker_desktop_running", return_value=desktop_running), \
                 mock.patch.object(guard.time, "time", lambda: clock["t"]), \
                 mock.patch.object(guard.time, "sleep",
                                   lambda s: clock.__setitem__("t", clock["t"] + s)), \
                 mock.patch.object(guard.subprocess, "run", side_effect=fake_run):
                result = guard.one_pass(args)
        return result, round(clock["t"] - self.T0), cmds

    @staticmethod
    def restarts(result):
        return [a for a in result["actions"] if "left in this pass" in a]

    # -- the usual "everything is down" case is left untouched --------------
    def test_fast_failures_still_walk_the_whole_ladder(self):
        def probe(tag, restarted):
            # the fake service comes back once the engine has been restarted
            return emb_ok(tag) if guard.ENGINE_CONTAINER in restarted else emb_fail(tag, None)

        def states(name):
            return "running|none" if name == guard.SIDECAR_CONTAINER else "running|healthy"

        result, elapsed, cmds = self.run_timed(
            costs={"version": 1, "inspect": 1, "restart": 10, "probe": 1},
            probe=probe, states=states)
        self.assertEqual([c[2] for c in cmds if c[:2] == ["docker", "restart"]],
                         [guard.SIDECAR_CONTAINER, guard.ENGINE_CONTAINER])
        self.assertEqual(result["verdict"], "OK")
        # the engine probe taken before the restart is history, not a failure
        self.assertTrue(result["checks"][-2]["before_escalation"])
        self.assertFalse(result["checks"][-2]["ok"])
        self.assertTrue([c for c in result["checks"] if c.get("path") == "sidecar"][0]["ok_after_escalation"])
        self.assertEqual(self.restarts(result), [])
        self.assertFalse(any(c.get("skipped") for c in result["checks"]), result["checks"])
        self.assertEqual(elapsed, 69)

    # -- the rule: a restart starts only if its worst case fits -------------
    def test_restart_is_refused_while_budget_remains(self):
        # Slow host: every probe times out. The relay restart takes 40 s and
        # turns healthy; 167 s then remain, less than the 230 s an engine
        # restart can cost, so it is left to the next pass.
        def states(name):
            return "running|none" if name == guard.SIDECAR_CONTAINER else "running|healthy"

        result, elapsed, cmds = self.run_timed(
            costs={"version": 45, "inspect": 25, "restart": 40, "probe": 30},
            probe=lambda tag, restarted: emb_fail(tag, None), states=states)
        self.assertEqual([c[2] for c in cmds if c[:2] == ["docker", "restart"]],
                         [guard.SIDECAR_CONTAINER])
        self.assertEqual(self.restarts(result), [
            "SKIP restart of %s: 167s left in this pass (< 230s) - the next pass decides"
            % guard.ENGINE_CONTAINER])
        # 132 s remain: that covers the whisper check, which is evaluated
        self.assertFalse(any(c.get("skipped") for c in result["checks"]), result["checks"])
        self.assertEqual(elapsed, 318)
        self.assertEqual(result["verdict"], "DEGRADED")

    def test_health_wait_is_clipped_to_the_budget(self):
        # Relay capped for the hour (no restart call), engine restart slow and
        # never healthy: the wait stops at the budget, not 90 s later (552 s).
        result, elapsed, cmds = self.run_timed(
            costs={"version": 45, "inspect": 25, "restart": 170, "probe": 30},
            probe=lambda tag, restarted: emb_fail(tag, None),
            states=lambda name: "running|starting", sidecar_capped=True)
        self.assertEqual([c[2] for c in cmds if c[:2] == ["docker", "restart"]],
                         [guard.ENGINE_CONTAINER])
        self.assertTrue(any("restart cap reached for %s this hour" % guard.SIDECAR_CONTAINER in a
                            for a in result["actions"]), result["actions"])
        self.assertTrue(any("%s restarted (NOT healthy yet)" % guard.ENGINE_CONTAINER in a
                            for a in result["actions"]), result["actions"])
        self.assertLessEqual(elapsed, 480)
        # an unchecked whisper is neither a failure nor healthy
        skipped = [c for c in result["checks"] if c.get("check") == "whisper"]
        self.assertEqual(len(skipped), 1)
        self.assertTrue(skipped[0]["skipped"])
        self.assertIsNone(skipped[0]["ok"])
        self.assertEqual(result["verdict"], "DEGRADED")
        self.assertEqual([f.split(":")[0] for f in result["failures"]], ["embeddings"])

    def test_engine_mute_path_returns_well_within_the_task_limit(self):
        result, elapsed, cmds = self.run_timed(
            costs={"version": 45, "inspect": 25, "restart": 170, "probe": 30, "desktop": 120},
            version=None, probe=lambda tag, restarted: emb_fail(tag, None),
            states=lambda name: "running|none")
        self.assertEqual(result["verdict"], "ENGINE_DOWN")
        self.assertEqual([c[:2] for c in cmds], [["docker", "version"], ["docker", "desktop"]])
        self.assertEqual(elapsed, 45 + 30 + 3 + 30 + 120)

    def test_budget_leaves_margin_under_the_task_limit(self):
        # Worst case, every call at its timeout: a restart started at the last
        # second that allows it, the health wait clipped to the budget (plus
        # one inspect and one sleep of overhang), the settle and the closing
        # probe. The whisper check is skipped by then.
        worst = guard.PASS_BUDGET_S + guard.INSPECT_TIMEOUT + 3 + 5 + 30
        self.assertLess(worst, 600)
        self.assertEqual(guard.RESTART_MIN_BUDGET_S, 2 * guard.INSPECT_TIMEOUT + guard.RESTART_CLI_TIMEOUT)

    # -- the boot rail reads a Go timestamp: lock the template --------------
    def test_age_reads_the_timestamp_docker_emits(self):
        # A broken format template makes `docker inspect` fail, `age_seconds`
        # return None and the boot rail vanish - silently (caught in diff,
        # 2026-11-26: one missing brace).
        out = subprocess.CompletedProcess([], 0, stdout=self.STARTED + "\n", stderr="")
        with mock.patch.object(guard.subprocess, "run", return_value=out) as run:
            age = guard.age_seconds("x")
        self.assertGreater(age, guard.BOOT_RAIL)
        self.assertEqual(run.call_args[0][0][-1], "{{.State.StartedAt}}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

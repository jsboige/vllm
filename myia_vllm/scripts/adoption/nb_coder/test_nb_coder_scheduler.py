#!/usr/bin/env python3
"""Offline tests for nb_coder_scheduler.py — fake gate, fake driver, no engine,
no GitHub writes (#468). Run: python -m pytest test_nb_coder_scheduler.py -q
from this directory."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "nb_coder_scheduler", HERE / "nb_coder_scheduler.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

GREEN = {"verdict": "green", "running": 0, "waiting": 0, "preemptions": 0}


def write_queue(tmp_path: Path, lines: list[dict]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    q = tmp_path / "queue.jsonl"
    q.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return q


def make_sched(tmp_path, items, gate=None, spawn=None, ramp=None,
               max_active=2, **arg_overrides):
    queue = write_queue(tmp_path, items)
    args = S.parse_args([
        "--queue", str(queue), "--state-dir", str(tmp_path / "state"),
        "--repo", "D:/CoursIA", "--max-active", str(max_active)])
    if ramp:
        args.ramp = ramp
        args.max_active = 0
    for k, v in arg_overrides.items():
        setattr(args, k, v)
    sched = S.Scheduler(args, spawn=spawn, gate=gate or (lambda: dict(GREEN)),
                        sleep=lambda s=0: None, clock=lambda: 1000.0)
    loaded, digest = S.load_queue(queue)
    sched.merge_queue(loaded, digest)
    sched._save_state()      # a reborn instance must see this queue in state.json
    return sched


class SpawnRecorder:
    def __init__(self, verdict="built-executed-ok", rc=0, done_after=2):
        self.calls = []
        self.verdict, self.rc, self.done_after = verdict, rc, done_after

    def __call__(self, cmd):
        self.calls.append(cmd)
        return S.FakeProc(self.verdict, self.rc, self.done_after)


def item(n):
    return {"issue": n, "notebook": f"Dir/N{n}.ipynb"}


# ---------------------------------------------------------------- queue validation
def test_queue_rejects_unknown_field(tmp_path):
    q = tmp_path / "q.jsonl"
    q.write_text(json.dumps({"issue": 1, "notebook": "A.ipynb",
                             "notebok": "typo.ipynb"}) + "\n")
    with pytest.raises(S.QueueError, match="unknown field"):
        S.load_queue(q)


def test_queue_rejects_duplicate_and_bad_paths(tmp_path):
    q = tmp_path / "q.jsonl"
    q.write_text(json.dumps(item(1)) + "\n" + json.dumps(item(1)) + "\n")
    with pytest.raises(S.QueueError, match="duplicate"):
        S.load_queue(q)
    q.write_text(json.dumps({"issue": 2, "notebook": "../escape.ipynb"}) + "\n")
    with pytest.raises(S.QueueError, match="repo-relative"):
        S.load_queue(q)
    q.write_text(json.dumps({"issue": 3, "notebook": "A.ipynb",
                             "claim": "yes"}) + "\n")
    with pytest.raises(S.QueueError, match="must be bool"):
        S.load_queue(q)


# ---------------------------------------------------------------- admission
def test_green_launches_only_up_to_target(tmp_path):
    spawn = SpawnRecorder(done_after=99)     # stays in flight
    sched = make_sched(tmp_path, [item(i) for i in (1, 2, 3)], spawn=spawn,
                       max_active=2)
    r = sched.tick()
    assert r["launched"] == 2 and len(spawn.calls) == 2 and r["active"] == 2
    assert r["held"] == "capacity-target"
    # budget also honours the engine gauge, not just our own children
    sched2 = make_sched(tmp_path / "g", [item(i) for i in (1, 2)], spawn=spawn,
                        gate=lambda: {**GREEN, "running": 2}, max_active=2)
    assert sched2.tick()["launched"] == 0


def test_yellow_red_unknown_hold_new_launches(tmp_path):
    for verdict in ("yellow", "red", "unknown"):
        spawn = SpawnRecorder()
        sched = make_sched(tmp_path / verdict, [item(1)], spawn=spawn,
                           gate=lambda: {"verdict": verdict, "running": 0})
        r = sched.tick()
        assert r["launched"] == 0 and r["held"] == f"gate-{verdict}"
    assert spawn.calls == []


def test_yellow_never_touches_in_flight(tmp_path):
    gate = {"verdict": "green", "running": 0}
    spawn = SpawnRecorder(done_after=99)
    sched = make_sched(tmp_path, [item(1), item(2)], spawn=spawn,
                       gate=lambda: dict(gate), max_active=2)
    sched.tick()
    assert len(sched.active) == 2
    gate["verdict"] = "yellow"
    r = sched.tick()
    assert r["launched"] == 0 and len(sched.active) == 2  # still alive
    for entry in sched.active.values():
        assert entry["proc"].poll() is None


def test_stop_file_freezes_new_launches(tmp_path):
    spawn = SpawnRecorder()
    sched = make_sched(tmp_path, [item(1)], spawn=spawn)
    Path(sched.args.stop_file).write_text("pause\n")
    r = sched.tick()
    assert r["launched"] == 0 and r["held"] == "stop-file"
    Path(sched.args.stop_file).unlink()
    assert sched.tick()["launched"] == 1


# ---------------------------------------------------------------- deferred / retry
def test_capacity_deferred_is_retried_after_backoff(tmp_path):
    clock = {"t": 1000.0}
    spawn = SpawnRecorder(verdict="deferred-by-capacity-gate", rc=1,
                          done_after=0)
    sched = make_sched(tmp_path, [item(1)], spawn=spawn)
    sched.clock = lambda: clock["t"]
    sched.tick()                                  # launch
    clock["t"] += 10
    sched.tick()                                  # reap -> deferred
    g = sched.state["grains"]["#1:Dir/N1.ipynb"]
    assert g["status"] == "deferred" and g["attempts"] == 1
    assert g["not_before"] > clock["t"]
    clock["t"] += 5                               # still inside backoff
    assert sched.tick()["launched"] == 0
    clock["t"] = g["not_before"] + 1
    assert sched.tick()["launched"] == 1 and g["attempts"] == 2


def test_attempts_exhausted_becomes_terminal(tmp_path):
    clock = {"t": 1000.0}
    spawn = SpawnRecorder(verdict="deferred-by-capacity-gate", rc=1,
                          done_after=0)
    sched = make_sched(tmp_path, [item(1)], spawn=spawn, max_attempts=1)
    sched.clock = lambda: clock["t"]
    sched.tick()
    clock["t"] += 10
    sched.tick()
    key = "#1:Dir/N1.ipynb"
    assert sched.state["grains"][key]["status"] == "deferred"
    clock["t"] = sched.state["grains"][key]["not_before"] + 1
    sched.tick()                                  # exhausted -> failed, no relaunch
    assert sched.state["grains"][key]["status"] == "failed"
    events = [json.loads(l) for l in
              (sched.state_dir / "scheduler.jsonl").read_text().splitlines()]
    assert any(e["kind"] == "attempts-exhausted" for e in events)


# ---------------------------------------------------------------- ramp
def test_ramp_promotion_measured(tmp_path):
    clock = {"t": 1000.0}
    spawn = SpawnRecorder(done_after=0)
    sched = make_sched(tmp_path, [item(i) for i in (1, 2, 3)], spawn=spawn,
                       ramp=[1, 2], ramp_min_done=2, ramp_green_s=0)
    sched.clock = lambda: clock["t"]
    sched.tick()                                  # launch #1 (step max 1)
    clock["t"] += 1
    sched.tick()                                  # reap #1 done, launch #2
    clock["t"] += 1
    sched.tick()                                  # reap #2 -> promote -> launch #3 at target 2
    assert sched.state["ramp"]["max_active"] == 2
    assert sched.state["ramp"]["done"] == 0        # counters reset for step 2
    assert sched.state["ramp_history"][-1]["promoted_to"] == 2
    assert len(spawn.calls) == 3
    clock["t"] += 1
    sched.tick()                                  # step 2 holds until re-proven
    assert sched.state["ramp"]["max_active"] == 2


def test_red_gates_block_promotion_and_demote(tmp_path):
    clock = {"t": 1000.0}
    gate = {"verdict": "green", "running": 0}
    spawn = SpawnRecorder(done_after=0)
    sched = make_sched(tmp_path, [item(i) for i in (1, 2, 3)], spawn=spawn,
                       gate=lambda: dict(gate), ramp=[1, 2], ramp_min_done=1,
                       ramp_green_s=1, ramp_demote=True)
    sched.clock = lambda: clock["t"]
    sched.tick()
    clock["t"] += 1
    sched.tick()                                  # done=1, green 1s -> promoted to 2
    assert sched.state["ramp"]["max_active"] == 2
    gate["verdict"] = "red"
    clock["t"] += 1
    sched.tick()                                  # demotion one step down
    assert sched.state["ramp"]["max_active"] == 1
    assert sched.state["ramp"]["dirty"] is False   # reset with the demotion
    gate["verdict"] = "green"
    clock["t"] += 1
    sched.tick()
    assert sched.state["ramp"]["max_active"] == 1  # green clock restarted at demotion


# ---------------------------------------------------------------- persistence
def test_previous_run_running_grain_marked_orphaned(tmp_path):
    sched = make_sched(tmp_path, [item(1)], spawn=SpawnRecorder(done_after=0))
    sched.run()                                   # queue drains cleanly
    # simulate a scheduler that died mid-grain
    key = "#1:Dir/N1.ipynb"
    sched.state["grains"][key].update({"status": "running", "pid": 123})
    sched._save_state()
    # reborn instance: gate forced red so the offline test never touches /metrics
    reborn = S.Scheduler(sched.args, gate=lambda: {"verdict": "red"},
                         sleep=lambda: None, clock=lambda: 2000.0)
    reborn.merge_queue(*S.load_queue(sched.args.queue))
    reborn.run()
    assert reborn.state["grains"][key]["status"] == "orphaned"
    assert reborn.state["grains"][key]["status"] != "pending"  # never auto-relaunched


def test_withdrawn_then_readded_is_requeued(tmp_path):
    sched = make_sched(tmp_path, [item(1), item(2)])   # no run: merge only
    args = sched.args
    q1 = write_queue(tmp_path, [item(1)])              # N2 disappears
    args.queue = q1
    sched2 = S.Scheduler(args, gate=lambda: {"verdict": "red"},
                         sleep=lambda: None, clock=lambda: 1.0)
    sched2.merge_queue(*S.load_queue(q1))
    assert sched2.state["grains"]["#2:Dir/N2.ipynb"]["status"] == "withdrawn"
    q2 = write_queue(tmp_path, [item(1), item(2)])     # N2 comes back
    args.queue = q2
    sched3 = S.Scheduler(args, gate=lambda: {"verdict": "red"},
                         sleep=lambda: None, clock=lambda: 1.0)
    sched3.merge_queue(*S.load_queue(q2))
    assert sched3.state["grains"]["#2:Dir/N2.ipynb"]["status"] == "pending"


def test_dry_run_logs_command_without_spawning(tmp_path):
    spawn = SpawnRecorder()
    sched = make_sched(tmp_path, [item(1)], spawn=spawn, dry_run=True)
    r = sched.tick()
    assert r["launched"] == 0 and spawn.calls == []
    events = [json.loads(l) for l in
              (sched.state_dir / "scheduler.jsonl").read_text().splitlines()]
    dry = [e for e in events if e["kind"] == "dry-launch"]
    assert dry and "--gate-mode" in dry[0]["cmd"] and "--issue" in dry[0]["cmd"]
    assert sched.state["grains"]["#1:Dir/N1.ipynb"]["status"] == "pending"


def test_driver_command_carries_known_fields_only(tmp_path):
    sched = make_sched(tmp_path, [{
        "issue": 42, "notebook": "A/B.ipynb", "max_stage": 2, "claim": True,
        "agent": "notebook-coder", "intention": "test"}],
        lane="myia-ai-01:nb-coder", claim=True)
    cmd = sched.driver_command(sched.items_by_key["#42:A/B.ipynb"])
    joined = " ".join(cmd)
    assert "--issue 42" in joined and "--notebook A/B.ipynb" in joined
    assert "--claim" in joined and "--lane myia-ai-01:nb-coder" in joined
    assert "--gate-mode block" in joined
    assert "--max-stage 2" in joined


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

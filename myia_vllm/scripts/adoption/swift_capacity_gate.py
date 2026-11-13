#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""swift_capacity_gate.py — real-time capacity verdict for the Swift engine (:5002).

Read-only probe over /metrics. Classifies the engine as green / yellow / red so
opportunistic consumers (light sk-agent agents, sweeps, pre-audits) can decide
whether to START a new conversation turn. Designed as the future pre-dispatch
gate inside sk-agent (proposal posted to roo-extensions 2026-11-13).

Contract:
  exit 0 = green   (safe to start a new light turn)
  exit 1 = yellow  (start only if the work is deferrable-cheap; prefer waiting)
  exit 2 = red     (do not start anything; let pilot traffic have the engine)
  exit 3 = unknown (metrics unreachable — instrument failure, NOT a verdict;
                    consumers should treat it as "don't run" and report)

Output: single-line JSON on stdout, e.g.
  {"verdict":"green","running":2,"waiting":0,"preemptions":0,"preempt_delta":0,
   "kv_gpu_perc":0.31,"age_s":12}

Classifier (thresholds from measured prod behaviour, 2026-11):
  RED   if running >= 12 (KV knee for long-context sessions — preemptions climb,
                          hit drops to ~74%, decode/streams falls to ~34 t/s)
        OR preempt_delta > 0 within the last window (saturation in progress)
        OR waiting > 0 on two consecutive probes (queue is sustained)
  YELLOW if waiting > 0 (transient) OR running >= 8
  GREEN  otherwise
  kv_gpu_perc is reported for information only: with the RAM/fs tiers active a
  high GPU-KV gauge means spilling, not failure — it does not classify.

State: %LOCALAPPDATA%/vllm-capacity-gate/state.json (last probe, 10-min window).
Overrides: SWIFT_GATE_URL, SWIFT_GATE_RED_RUNNING, SWIFT_GATE_YELLOW_RUNNING,
           SWIFT_GATE_STATE, SWIFT_GATE_WINDOW_S.

Self-test: python swift_capacity_gate.py --selftest   (offline, no engine call)
"""

import json
import os
import re
import sys
import time
import urllib.request

DEFAULT_URL = os.environ.get("SWIFT_GATE_URL", "http://localhost:5002/metrics")
RED_RUNNING = float(os.environ.get("SWIFT_GATE_RED_RUNNING", "12"))
YELLOW_RUNNING = float(os.environ.get("SWIFT_GATE_YELLOW_RUNNING", "8"))
WINDOW_S = float(os.environ.get("SWIFT_GATE_WINDOW_S", "600"))
DEFAULT_STATE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", "/tmp")),
    "vllm-capacity-gate", "state.json")


def _metric(text, name):
    """Return the float value of a vLLM gauge/counter, or None if absent."""
    m = re.search(r"^%s\{[^}]*\}\s+([0-9.eE+-]+)" % re.escape(name), text, re.M)
    return float(m.group(1)) if m else None


def read_metrics(url, timeout=5.0):
    req = urllib.request.Request(url, headers={"User-Agent": "swift-capacity-gate/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(path, snapshot):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)
    except Exception:
        pass  # state is an optimisation, not a requirement


def classify(running, waiting, preempt_delta, waiting_prev, age_s):
    """Pure classifier — unit-testable, no IO. Returns 'green'|'yellow'|'red'."""
    if running >= RED_RUNNING:
        return "red"
    if preempt_delta is not None and preempt_delta > 0:
        return "red"
    if waiting > 0 and waiting_prev is not None and age_s <= WINDOW_S and waiting_prev > 0:
        return "red"  # queue sustained across two probes
    if waiting > 0 or running >= YELLOW_RUNNING:
        return "yellow"
    return "green"


def probe(url=DEFAULT_URL, state_path=None):
    state_path = state_path or os.environ.get("SWIFT_GATE_STATE", DEFAULT_STATE)
    text = read_metrics(url)
    running = _metric(text, "vllm:num_requests_running")
    waiting = _metric(text, "vllm:num_requests_waiting")
    preempt = _metric(text, "vllm:num_preemptions_total")
    # v0.32 exposes vllm:kv_cache_usage_perc (older name gpu_cache_usage_perc kept as fallback)
    kv = _metric(text, "vllm:kv_cache_usage_perc")
    if kv is None:
        kv = _metric(text, "vllm:gpu_cache_usage_perc")
    if running is None or waiting is None or preempt is None:
        return {"verdict": "unknown",
                "error": "required gauges missing from /metrics"}, 3

    now = time.time()
    prev = load_state(state_path)
    preempt_delta = None
    waiting_prev = None
    age_s = None
    if prev and now - prev.get("ts", 0) <= WINDOW_S:
        preempt_delta = preempt - prev.get("preemptions", preempt)
        waiting_prev = prev.get("waiting")
        age_s = now - prev.get("ts", 0)

    verdict = classify(running, waiting, preempt_delta, waiting_prev, age_s or 0)
    out = {"verdict": verdict, "running": running, "waiting": waiting,
           "preemptions": preempt,
           "preempt_delta": preempt_delta, "kv_gpu_perc": kv,
           "age_s": round(age_s, 1) if age_s else None}
    save_state(state_path, {"ts": now, "preemptions": preempt, "waiting": waiting})
    return out, {"green": 0, "yellow": 1, "red": 2}[verdict]


def selftest():
    cases = [
        # (running, waiting, preempt_delta, waiting_prev, age, expected)
        (2, 0, 0, 0, 60, "green"),      # calm trough
        (7, 0, 0, 0, 60, "green"),      # busy but under yellow line
        (9, 0, 0, 0, 60, "yellow"),     # running band 8-11
        (12, 0, 0, 0, 60, "red"),       # KV knee
        (3, 0, 5, 0, 60, "red"),        # preemptions climbing
        (3, 2, 0, 1, 60, "red"),        # sustained queue (two probes)
        (3, 2, 0, 0, 60, "yellow"),     # first queue observation
        (3, 1, 0, 2, 3600, "yellow"),   # stale prev (> window): queue not sustained
        (2, 0, 0, 0, None, "green"),    # no state at all
    ]
    ok = True
    for i, (r, w, pd, wp, age, exp) in enumerate(cases):
        got = classify(r, w, pd, wp, age if age is not None else 0)
        # case 9: emulate "no state" by preempt_delta None
        if i == 8:
            got = classify(r, w, None, None, 0)
        status = "ok" if got == exp else "FAIL"
        ok = ok and got == exp
        print("case %d: running=%d waiting=%d preempt_delta=%s prev_wait=%s -> %s (%s)"
              % (i + 1, r, w, pd, wp, got, status))
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    try:
        out, code = probe()
    except Exception as e:
        print(json.dumps({"verdict": "unknown", "error": str(e)[:200]}))
        return 3
    print(json.dumps(out))
    return code


if __name__ == "__main__":
    sys.exit(main())

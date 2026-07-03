#!/usr/bin/env python3
"""
Passive wedge telemetry for the vLLM prod engine (read-only).

Samples vLLM /metrics + nvidia-smi at a fixed interval and appends one compact
JSONL line per sample, capturing the "wedge" signature conditions so the NEXT
wedge onset leaves a diagnostic trace (traffic / concurrency / KV / GPU-power
in the minutes leading up to it). This turns the mitigation decision in
project-engine-wedge (accept churn / preventive restart / root-cause) into a
data-driven one, and tests the load-correlation hypothesis WITHOUT touching
prod config, the model, or throughput.

Wedge tell (see MEMORY.md project-engine-wedge):
  gen_rate < 1 tok/s WHILE running > 0            -> WEDGE
  GPU util >=90%% at LOW power (e.g. 112 W) + KV low -> corroborating signature
  (gen ~0 with running == 0 is just IDLE, healthy)

/metrics is unauthenticated (the same endpoint the watchdog and the cron ops
checks already read); NO API key is used, read, or logged. Fully read-only.

Usage:
  python wedge_telemetry.py                 # loop forever, 60s interval
  python wedge_telemetry.py --interval 30
  python wedge_telemetry.py --once          # one sample (2x with interval gap), exit
Output: --out PATH or WEDGE_TELEMETRY_OUT env
        (default: myia_vllm/_iteration_log/wedge_telemetry.jsonl)

Read it back with: python -m json.tool, or:
  tail -50 wedge_telemetry.jsonl | python -c "import json,sys; [print(l.strip()) for l in sys.stdin]"
"""
import argparse
import json
import os
import subprocess
import time
import urllib.request

METRICS_URL = os.environ.get("WEDGE_METRICS_URL", "http://127.0.0.1:5002/metrics")
DEFAULT_OUT = os.environ.get(
    "WEDGE_TELEMETRY_OUT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "_iteration_log", "wedge_telemetry.jsonl"),
)

COUNTERS = ("vllm:generation_tokens_total", "vllm:prompt_tokens_total")
GAUGES = ("vllm:num_requests_running", "vllm:num_requests_waiting",
          "vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc")


def fetch_metrics():
    """Sum of matched metric values across label sets, or None if endpoint down."""
    try:
        with urllib.request.urlopen(METRICS_URL, timeout=5) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    vals = {}
    for line in body.splitlines():
        if not line or line[0] == "#" or " " not in line:
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        if name in COUNTERS or name in GAUGES:
            try:
                v = float(line.rsplit(" ", 1)[1])
            except ValueError:
                continue
            vals[name] = vals.get(name, 0.0) + v
    return vals


def fetch_gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,utilization.gpu,power.draw,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return []
    gpus = []
    for ln in out.splitlines():
        p = [x.strip() for x in ln.split(",")]
        if len(p) >= 4:
            try:
                gpus.append({"i": int(p[0]), "util": float(p[1]),
                             "pw": float(p[2]), "mem": int(float(p[3]))})
            except ValueError:
                pass
    return gpus


def _rate(now, prev, key, dt):
    if prev is None or dt <= 0:
        return None
    d = now.get(key, 0.0) - prev.get(key, 0.0)
    if d < 0:            # counter reset => engine restarted; rate undefined this window
        return None
    return d / dt


def sample(prev, dt):
    """Return (record, now_counters_or_None)."""
    now = fetch_metrics()
    gpus = fetch_gpu()
    ts = int(time.time())
    gpu01 = [{"i": g["i"], "util": g["util"], "pw": g["pw"]}
             for g in gpus if g["i"] in (0, 1)]
    if now is None:
        return {"ts": ts, "endpoint": "down", "gpu": gpu01}, None
    gen_rate = _rate(now, prev, "vllm:generation_tokens_total", dt)
    prm_rate = _rate(now, prev, "vllm:prompt_tokens_total", dt)
    running = int(now.get("vllm:num_requests_running", 0))
    waiting = int(now.get("vllm:num_requests_waiting", 0))
    kv = now.get("vllm:gpu_cache_usage_perc",
                 now.get("vllm:kv_cache_usage_perc", 0.0))
    kv_pct = round(kv * 100, 1) if kv <= 1.0 else round(kv, 1)
    tell = any(g["util"] >= 90 and g["pw"] < 200 for g in gpu01)
    wedge = gen_rate is not None and gen_rate < 1 and running > 0
    rec = {"ts": ts, "endpoint": "up",
           "gen_rate": None if gen_rate is None else round(gen_rate, 2),
           "prompt_rate": None if prm_rate is None else round(prm_rate, 1),
           "running": running, "waiting": waiting, "kv_pct": kv_pct,
           "gpu_lowpower_pegged": tell, "wedge": bool(wedge), "gpu": gpu01}
    return rec, now


def emit(rec, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    hhmm = time.strftime("%H:%M:%SZ", time.gmtime(rec["ts"]))
    if rec.get("endpoint") == "down":
        print(f"[{hhmm}] endpoint DOWN (booting/crashed)", flush=True)
        return
    flag = ""
    if rec["wedge"]:
        flag = "  *** WEDGE ***"
    elif rec["gpu_lowpower_pegged"]:
        flag = "  (pegged@lowpower)"
    elif rec["running"] == 0 and (rec["gen_rate"] or 0) < 1:
        flag = "  idle"
    print(f"[{hhmm}] gen={rec['gen_rate']} prm={rec['prompt_rate']} "
          f"run={rec['running']} wait={rec['waiting']} kv={rec['kv_pct']}%{flag}",
          flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="seconds between samples")
    ap.add_argument("--once", action="store_true", help="one sample then exit")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    out = os.path.abspath(a.out)

    prev = fetch_metrics()
    t_prev = time.time()
    if a.once:
        time.sleep(a.interval)
        rec, _ = sample(prev, time.time() - t_prev)
        emit(rec, out)
        return

    print(f"wedge_telemetry -> {out} (interval {a.interval}s) — Ctrl-C to stop",
          flush=True)
    while True:
        time.sleep(a.interval)
        rec, now = sample(prev, time.time() - t_prev)
        emit(rec, out)
        if now is not None:          # keep prev on endpoint-down so rate resumes cleanly
            prev, t_prev = now, time.time()


if __name__ == "__main__":
    main()

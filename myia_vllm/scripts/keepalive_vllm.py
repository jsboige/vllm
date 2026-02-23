#!/usr/bin/env python3
"""
Keepalive for vLLM services — prevents idle crash (TimeoutError / SystemError).

GLM-4.7-Flash crashes after idle periods due to:
  - SystemError: attempting to create PyCFunction (CPython/pybind11 bug)
  - TimeoutError: RPC call to sample_tokens timed out (10s timeout)

The /health endpoint does NOT trigger inference, so it doesn't prevent the crash.
This script sends a minimal completion request every N minutes to keep the
engine warm and detect failures early.

Pattern observed (02-18 to 02-23): 16 crashes in 5 days, shortest idle before
crash was 10 minutes. Keepalive interval of 5 minutes should prevent most crashes.

Usage:
    python keepalive_vllm.py                    # Default: both models, 5min interval
    python keepalive_vllm.py --interval 300     # Custom interval (seconds)
    python keepalive_vllm.py --models glm       # Only GLM
    python keepalive_vllm.py --models zwz       # Only ZwZ
    python keepalive_vllm.py --once             # Single check, then exit (for cron)

Deployment as Windows Scheduled Task:
    schtasks /create /tn "vLLM Keepalive" /tr "python d:\\vllm\\myia_vllm\\scripts\\keepalive_vllm.py --once" /sc minute /mo 5 /ru SYSTEM
"""

import argparse
import os
import sys
import time
from datetime import datetime

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# Model configurations
MODELS = {
    "glm": {
        "name": "GLM-4.7-Flash",
        "url": "http://localhost:5002/v1/chat/completions",
        "model": "glm-4.7-flash",
        "api_key_env": "VLLM_API_KEY_MEDIUM",
        "api_key_fallback": "Y7PSM158SR952HCAARSLQ344RRPJTDI3",
    },
    "zwz": {
        "name": "ZwZ-8B",
        "url": "http://localhost:5001/v1/chat/completions",
        "model": "zwz-8b",
        "api_key_env": "VLLM_API_KEY_MINI",
        "api_key_fallback": "Y7PSM158SR952HCAARSLQ344RRPJTDI3",
    },
}

# Minimal request: 1 token output, tiny prompt
KEEPALIVE_PAYLOAD = {
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 1,
    "temperature": 0,
}


def get_api_key(model_cfg: dict) -> str:
    """Get API key from env or fallback."""
    key = os.environ.get(model_cfg["api_key_env"], "")
    if not key:
        # Try loading from .env file
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{model_cfg['api_key_env']}="):
                        key = line.split("=", 1)[1].strip()
                        break
    return key or model_cfg["api_key_fallback"]


def ping_model(model_key: str, timeout: float = 30.0) -> tuple[bool, float, str]:
    """Send a minimal inference request. Returns (success, latency_s, detail)."""
    cfg = MODELS[model_key]
    api_key = get_api_key(cfg)
    payload = {**KEEPALIVE_PAYLOAD, "model": cfg["model"]}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    start = time.monotonic()
    try:
        r = httpx.post(cfg["url"], json=payload, headers=headers, timeout=timeout)
        elapsed = time.monotonic() - start
        if r.status_code == 200:
            return True, elapsed, "OK"
        else:
            return False, elapsed, f"HTTP {r.status_code}: {r.text[:200]}"
    except httpx.ConnectError:
        elapsed = time.monotonic() - start
        return False, elapsed, "Connection refused (container down?)"
    except httpx.ReadTimeout:
        elapsed = time.monotonic() - start
        return False, elapsed, f"Timeout after {elapsed:.1f}s (engine likely dead)"
    except Exception as e:
        elapsed = time.monotonic() - start
        return False, elapsed, f"Error: {type(e).__name__}: {e}"


def log(msg: str):
    """Print with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_once(model_keys: list[str]) -> int:
    """Run a single keepalive check. Returns number of failures."""
    failures = 0
    for key in model_keys:
        cfg = MODELS[key]
        ok, latency, detail = ping_model(key)
        status = "OK" if ok else "FAIL"
        log(f"{cfg['name']:20s} | {status} | {latency:.2f}s | {detail}")
        if not ok:
            failures += 1
    return failures


def run_loop(model_keys: list[str], interval: int):
    """Run keepalive in a loop."""
    log(f"Starting keepalive loop: models={model_keys}, interval={interval}s")
    log(f"Press Ctrl+C to stop")

    consecutive_failures = {k: 0 for k in model_keys}

    while True:
        for key in model_keys:
            cfg = MODELS[key]
            ok, latency, detail = ping_model(key)
            status = "OK" if ok else "FAIL"
            log(f"{cfg['name']:20s} | {status} | {latency:.2f}s | {detail}")

            if ok:
                consecutive_failures[key] = 0
            else:
                consecutive_failures[key] += 1
                if consecutive_failures[key] >= 3:
                    log(f"  WARNING: {cfg['name']} has failed {consecutive_failures[key]} consecutive checks!")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("Stopped by user")
            break


def main():
    parser = argparse.ArgumentParser(description="vLLM keepalive to prevent idle crashes")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(MODELS.keys()),
        default=list(MODELS.keys()),
        help="Models to monitor (default: all)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between keepalive pings (default: 300 = 5min)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for cron/scheduled task)",
    )
    args = parser.parse_args()

    if args.once:
        failures = run_once(args.models)
        sys.exit(1 if failures > 0 else 0)
    else:
        run_loop(args.models, args.interval)


if __name__ == "__main__":
    main()

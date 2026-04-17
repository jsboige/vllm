#!/usr/bin/env python3
"""
Keepalive + Watchdog for vLLM services.

Two failure modes are monitored:
  1. IDLE CRASH: Engine dies after idle periods (CPython/pybind11 bug).
     Fixed by PR #28053 on Mar 05 nightly, but keepalive remains as safety net.
  2. PORT FORWARDING LOSS: Docker Desktop Windows silently loses port mapping.
     Container stays "healthy" internally but localhost:PORT returns nothing.
     This was undetected for 12+ hours on 2026-03-09, blocking 7 agents.

The script pings from the HOST side (localhost) to detect BOTH failure modes.
On consecutive failures, it restarts the container via docker compose.

Usage:
    python keepalive_vllm.py                    # Default: both models, 2min interval
    python keepalive_vllm.py --interval 120     # Custom interval (seconds)
    python keepalive_vllm.py --models qwen      # Only Qwen3.5
    python keepalive_vllm.py --models zwz       # Only ZwZ
    python keepalive_vllm.py --once             # Single check, then exit (for cron)
    python keepalive_vllm.py --auto-restart     # Enable automatic container restart

Deployment as Windows Scheduled Task:
    schtasks /create /tn "vLLM Watchdog" /tr "python d:\\vllm\\myia_vllm\\scripts\\keepalive_vllm.py --auto-restart" /sc minute /mo 2 /ru SYSTEM
"""

import argparse
import os
import subprocess
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
    "qwen": {
        "name": "Qwen3.6-35B-A3B",
        "url": "http://localhost:5002/v1/chat/completions",
        "model": "qwen3.6-35b-a3b",
        "api_key_env": "VLLM_API_KEY_MEDIUM",
        "container": "myia_vllm-medium-qwen36-moe",
        "compose_file": "d:/vllm/myia_vllm/configs/docker/profiles/medium-qwen36-moe.yml",
        "service": "vllm-medium-qwen36-moe",
    },
    "zwz": {
        "name": "ZwZ-8B",
        "url": "http://localhost:5001/v1/chat/completions",
        "model": "zwz-8b",
        "api_key_env": "VLLM_API_KEY_MINI",
        "container": "myia_vllm-mini-zwz",
        "compose_file": "d:/vllm/myia_vllm/configs/docker/profiles/mini-zwz.yml",
        "service": "vllm-mini-zwz",
    },
}

ENV_FILE = "d:/vllm/myia_vllm/.env"
MAX_RESTART_FAILURES = 3  # restart after N consecutive ping failures

# Minimal request: 1 token output, tiny prompt
KEEPALIVE_PAYLOAD = {
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 1,
    "temperature": 0,
}


def get_api_key(model_cfg: dict) -> str:
    """Get API key from env or .env file."""
    key = os.environ.get(model_cfg["api_key_env"], "")
    if not key:
        env_path = ENV_FILE
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{model_cfg['api_key_env']}="):
                        key = line.split("=", 1)[1].strip()
                        break
    return key or "no-key"


def restart_container(model_key: str) -> bool:
    """Restart a container via docker compose. Returns True on success."""
    cfg = MODELS[model_key]
    compose_file = cfg.get("compose_file")
    service = cfg.get("service")
    container = cfg.get("container")

    if not compose_file or not service:
        log(f"  No compose_file/service configured for {model_key}, cannot restart")
        return False

    log(f"  RESTARTING {cfg['name']} ({container})...")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", compose_file,
             "--env-file", ENV_FILE, "restart", service],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log(f"  Restart command succeeded. Waiting for healthy...")
        else:
            log(f"  Restart command failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"  Restart error: {e}")
        return False

    # Wait for container to become healthy + port accessible (up to 10 min)
    for i in range(40):  # 40 * 15s = 10 min
        time.sleep(15)
        ok, _, detail = ping_model(model_key, timeout=10.0)
        if ok:
            log(f"  Recovery successful after {(i+1)*15}s")
            return True
        if (i + 1) % 4 == 0:
            log(f"  Still waiting... {(i+1)*15}s elapsed ({detail})")

    log(f"  Recovery FAILED after 600s. Manual intervention needed.")
    return False


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


def run_loop(model_keys: list[str], interval: int, auto_restart: bool = False):
    """Run keepalive in a loop with optional auto-restart."""
    mode = "watchdog+restart" if auto_restart else "monitor-only"
    log(f"Starting keepalive loop: models={model_keys}, interval={interval}s, mode={mode}")
    log(f"Press Ctrl+C to stop")

    consecutive_failures = {k: 0 for k in model_keys}

    while True:
        for key in model_keys:
            cfg = MODELS[key]
            ok, latency, detail = ping_model(key)
            status = "OK" if ok else "FAIL"
            log(f"{cfg['name']:20s} | {status} | {latency:.2f}s | {detail}")

            if ok:
                if consecutive_failures[key] > 0:
                    log(f"  {cfg['name']} recovered (was failing for {consecutive_failures[key]} checks)")
                consecutive_failures[key] = 0
            else:
                consecutive_failures[key] += 1
                if consecutive_failures[key] >= MAX_RESTART_FAILURES:
                    log(f"  ALERT: {cfg['name']} has failed {consecutive_failures[key]} consecutive checks!")
                    if auto_restart:
                        recovered = restart_container(key)
                        consecutive_failures[key] = 0
                        if not recovered:
                            log(f"  CRITICAL: {cfg['name']} could not be recovered. Will retry next cycle.")

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
        default=120,
        help="Seconds between keepalive pings (default: 120 = 2min)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for cron/scheduled task)",
    )
    parser.add_argument(
        "--auto-restart",
        action="store_true",
        help="Automatically restart container on consecutive failures",
    )
    args = parser.parse_args()

    if args.once:
        failures = run_once(args.models)
        sys.exit(1 if failures > 0 else 0)
    else:
        run_loop(args.models, args.interval, args.auto_restart)


if __name__ == "__main__":
    main()

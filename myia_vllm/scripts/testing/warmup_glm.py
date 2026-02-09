#!/usr/bin/env python3
"""
Post-startup warmup for GLM-4.7-Flash vLLM service.

Sends progressively larger prompts to pre-trigger CUDA graph captures
and torch.compile optimizations. Run this after container startup
before real users connect.

Without warmup: first 2-3 user requests suffer 10-14s TTFT spikes.
With warmup: all TTFT consistently ~3.5s for 30K token prompts.

Usage:
    python warmup_glm.py                # Default: localhost:5002
    python warmup_glm.py --port 5002    # Specify port
    python warmup_glm.py --wait         # Wait for service to be ready first
"""

import argparse
import sys
import time

import httpx

API_KEY = "Y7PSM158SR952HCAARSLQ344RRPJTDI3"


def wait_for_service(base_url: str, timeout: int = 600):
    """Wait for vLLM service to be healthy."""
    print(f"Waiting for {base_url} to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"{base_url}/health", timeout=5)
            if r.status_code == 200:
                elapsed = time.time() - start
                print(f"  Service ready after {elapsed:.0f}s")
                return True
        except Exception:
            pass
        time.sleep(5)
    print(f"  Timeout after {timeout}s")
    return False


def warmup_request(base_url: str, system_tokens: int, label: str):
    """Send a warmup request with a specific system prompt size."""
    # ~7 tokens per repetition of "You are a helpful assistant. "
    reps = max(1, system_tokens // 7)
    system_prompt = "You are a helpful assistant. " * reps

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    start = time.time()
    try:
        r = httpx.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": "glm-4.7-flash",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Say OK."},
                ],
                "max_tokens": 5,
                "temperature": 0.1,
            },
            timeout=120,
        )
        elapsed = time.time() - start
        data = r.json()
        prompt_tok = data.get("usage", {}).get("prompt_tokens", "?")
        comp_tok = data.get("usage", {}).get("completion_tokens", "?")
        print(f"  {label}: {prompt_tok} prompt + {comp_tok} gen in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"  {label}: ERROR after {elapsed:.1f}s - {e}")


def main():
    parser = argparse.ArgumentParser(description="Warmup GLM-4.7-Flash service")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--wait", action="store_true", help="Wait for service first")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    if args.wait:
        if not wait_for_service(base_url):
            sys.exit(1)

    print(f"Warming up {base_url} with progressive prompt sizes...")
    print(f"This pre-triggers CUDA graph captures for realistic workloads.")
    print()

    # Phase 1: Small prompt (triggers basic graph captures)
    warmup_request(base_url, 50, "Phase 1 - small (50 tok)")

    # Phase 2: Medium prompt (triggers chunked prefill paths)
    warmup_request(base_url, 5000, "Phase 2 - medium (5K tok)")

    # Phase 3: Large prompt (simulates Roo system prompt ~30K tokens)
    warmup_request(base_url, 30000, "Phase 3 - large (30K tok)")

    # Phase 4: Repeat large with slight variation (tests graph reuse)
    warmup_request(base_url, 30000, "Phase 4 - large repeat (30K tok)")

    # Phase 5: Extra large (tests upper range, ~50K tokens)
    warmup_request(base_url, 50000, "Phase 5 - XL (50K tok)")

    print()
    print("Warmup complete. CUDA graphs should be captured for all common sizes.")
    print("Subsequent requests should have consistent TTFT (~3.5s for 30K tokens).")


if __name__ == "__main__":
    main()

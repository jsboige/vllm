#!/usr/bin/env python3
"""TTFT (time-to-first-token) benchmark for vLLM prefill performance.

Measures prefill cost across prompt sizes, cold vs warm (prefix cache).
Created 2026-05-14 to compare --max-num-batched-tokens 32768 vs 65536
for the claudish/Claude Code long-prompt use case.

Usage:
  python ttft_benchmark.py <API_KEY> [label]

Each size is tested:
  - COLD: unique prefix, no prefix-cache hit possible
  - WARM: exact same prompt resent immediately (should hit prefix cache)
"""
import json
import random
import sys
import time
import urllib.request
import uuid

URL = "http://localhost:5002/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
KEY = sys.argv[1]
LABEL = sys.argv[2] if len(sys.argv) > 2 else "run"

SIZES = [20_000, 40_000, 80_000]  # approx prompt tokens

WORDS = (
    "function return value data process system compute result input output "
    "model token cache memory layer attention vector matrix kernel buffer "
    "thread context window prefill decode throughput latency batch sequence "
    "tensor parallel expert routing quantization inference engine scheduler"
).split()


def make_prompt(approx_tokens: int, unique: str) -> str:
    """Deterministic pseudo-text of ~approx_tokens, prefixed with a unique marker."""
    rng = random.Random(approx_tokens)  # deterministic per size
    n_words = int(approx_tokens / 1.3)
    body = " ".join(rng.choice(WORDS) for _ in range(n_words))
    return f"[req-{unique}] Summarize the following log in one word:\n{body}"


def measure(prompt: str):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    ttft = None
    prompt_tokens = None
    cached_tokens = None
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.strip()
            if not line or not line.startswith(b"data: "):
                continue
            chunk = line[6:]
            if chunk == b"[DONE]":
                break
            data = json.loads(chunk)
            if data.get("choices"):
                delta = data["choices"][0].get("delta", {})
                if (delta.get("content") or delta.get("reasoning")) and ttft is None:
                    ttft = time.time() - t0
            if data.get("usage"):
                prompt_tokens = data["usage"].get("prompt_tokens")
                details = data["usage"].get("prompt_tokens_details") or {}
                cached_tokens = details.get("cached_tokens")
    total = time.time() - t0
    return ttft, total, prompt_tokens, cached_tokens


def main():
    print(f"\n=== TTFT benchmark [{LABEL}] ===")
    print(f"{'size':>8} {'phase':>6} {'prompt_tok':>11} {'cached':>8} "
          f"{'TTFT(s)':>9} {'total(s)':>9}")
    results = []
    for size in SIZES:
        uniq = uuid.uuid4().hex[:8]
        prompt = make_prompt(size, uniq)
        # COLD
        ttft, total, ptok, ctok = measure(prompt)
        print(f"{size:>8} {'COLD':>6} {ptok:>11} {ctok if ctok is not None else '-':>8} "
              f"{ttft:>9.3f} {total:>9.3f}")
        results.append((size, "COLD", ptok, ctok, ttft, total))
        time.sleep(1)
        # WARM (same prompt)
        ttft, total, ptok, ctok = measure(prompt)
        print(f"{size:>8} {'WARM':>6} {ptok:>11} {ctok if ctok is not None else '-':>8} "
              f"{ttft:>9.3f} {total:>9.3f}")
        results.append((size, "WARM", ptok, ctok, ttft, total))
        time.sleep(1)
    return results


if __name__ == "__main__":
    main()

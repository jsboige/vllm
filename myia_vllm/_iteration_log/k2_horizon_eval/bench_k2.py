#!/usr/bin/env python3
"""K2-Horizon perf bench on the GPU-2 eval server (localhost:5022, keyless).

Single-GPU TP=1 indicative numbers only — the real A/B vs prod Qwen3.6 (TP=2,
GPUs 0,1) happens in the dedicated eval window. Machine noise dominates; run
prod's bench in the same window if comparing.

Usage: python bench_k2.py [--port 5022] [--model k2-horizon-36b]
"""
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request

PROMPTS = [
    "Write a haiku about caching.",
    "Explain prefix caching in 2 sentences.",
    "List 5 LLM inference optimizations.",
    "What is paged attention?",
    "Define KV cache in 1 sentence.",
    "What's the difference between MoE and dense models?",
    "Briefly: what is speculative decoding?",
    "Name 3 quantization formats for LLMs.",
    "What's beam search? 1 sentence.",
    "Explain top-k sampling briefly.",
    "What is grouped-query attention?",
    "List 3 reasons to use FP8.",
    "Define TTFT.",
    "What is rope scaling?",
    "Explain flash attention v3.",
    "What's tensor parallelism vs pipeline parallelism?",
]


def chat(api, model, prompt, max_tokens=256):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    req = urllib.request.Request(
        api,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    t1 = time.monotonic()
    content = data["choices"][0]["message"].get("content") or ""
    reasoning = data["choices"][0]["message"].get("reasoning") or ""
    return t1 - t0, data["usage"]["completion_tokens"], len(reasoning)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="5022")
    p.add_argument("--model", default="k2-horizon-36b")
    p.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8])
    args = p.parse_args()
    api = f"http://localhost:{args.port}/v1/chat/completions"

    print("== warmup ==")
    wall, toks, rlen = chat(api, args.model, PROMPTS[0], max_tokens=48)
    print(f"  {wall:.2f}s, {toks} completion tokens, reasoning_len={rlen}")

    print(f"{'N':>3} {'wall':>7} {'tot_tok':>8} {'agg_tps':>9} {'per_min':>8} {'per_med':>8} {'per_max':>8}")
    for n in args.levels:
        prompts = [PROMPTS[i % len(PROMPTS)] for i in range(n)]
        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            results = list(ex.map(lambda pr: chat(api, args.model, pr), prompts))
        wall = time.monotonic() - t0
        tot = sum(r[1] for r in results)
        per = [r[0] for r in results]
        print(f"{n:>3} {wall:>6.1f}s {tot:>8} {tot/wall:>9.1f} {min(per):>7.2f}s {statistics.median(per):>7.2f}s {max(per):>7.2f}s")


if __name__ == "__main__":
    main()

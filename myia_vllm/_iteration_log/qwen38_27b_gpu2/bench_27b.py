#!/usr/bin/env python3
"""Throughput bench for the Qwen3.8-27B GPU-2 re-test (#35).

Same prompts/measurement as k2_horizon_eval/bench_k2.py, plus optional Bearer
auth so the SAME script runs against both endpoints:
  - :5022 qwen38-eval (keyless, GPU 2)
  - :5002 prod 3.6 (VLLM_API_KEY_MEDIUM from env)
Run interleaved A/B/A/B (machine-noise lesson from the 08-20 eval).

Usage (from d:/vllm):
  python myia_vllm/_iteration_log/qwen38_27b_gpu2/bench_27b.py --levels 1 2 4 8 12 16
  export VLLM_API_KEY_MEDIUM=$(grep -m1 '^VLLM_API_KEY_MEDIUM=' myia_vllm/.env | cut -d= -f2)
  python myia_vllm/_iteration_log/qwen38_27b_gpu2/bench_27b.py --port 5002 --model qwen3.6-35b-a3b --levels 1 2 4 8 12 16
"""
import argparse
import concurrent.futures
import json
import os
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

API_KEY = os.environ.get("VLLM_API_KEY_MEDIUM", "dummy")


def chat(api, model, prompt, max_tokens=256):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"), headers=headers)
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
    p.add_argument("--model", default="qwen3.8-27b")
    p.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8])
    args = p.parse_args()
    api = f"http://localhost:{args.port}/v1/chat/completions"

    print(f"== warmup ({args.model} :{args.port}) ==")
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

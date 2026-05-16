"""Quick bench: single-user decode tok/s + 5-concurrent aggregate tok/s.

Comparing to baseline FP8 (2026-04-17 numbers):
  single-user no-thinking: 107 tok/s
  5-concurrent aggregate:  369 tok/s
  thinking decode:         116.5 tok/s
"""
import concurrent.futures
import json
import statistics
import time
import urllib.request

API = "http://localhost:5002/v1/chat/completions"
KEY = None
for line in open("d:/vllm/myia_vllm/.env"):
    if line.startswith("VLLM_API_KEY_MEDIUM="):
        KEY = line.split("=", 1)[1].strip()


def chat(prompt, max_tokens=256, thinking=False):
    body = {
        "model": "qwen3.6-35b-a3b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        },
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    t1 = time.monotonic()
    comp = data["usage"]["completion_tokens"]
    return t1 - t0, comp


PROMPT_SHORT = "Write 5 lines of professional Python code that defines a binary search function."
PROMPT_THINK = "Step by step: what is the smallest prime number greater than 1000?"

# Warmup
chat(PROMPT_SHORT, max_tokens=32)

# Single-user no-thinking
print("=== Single-user no-thinking (3 runs) ===")
single_results = []
for i in range(3):
    dt, comp = chat(PROMPT_SHORT, max_tokens=256, thinking=False)
    tps = comp / dt
    print(f"  run {i+1}: {comp} tokens in {dt:.2f}s = {tps:.1f} tok/s")
    single_results.append(tps)
print(f"  MEDIAN: {statistics.median(single_results):.1f} tok/s "
      f"(baseline FP8: 107)")

# Single-user thinking
print("\n=== Single-user thinking (3 runs) ===")
think_results = []
for i in range(3):
    dt, comp = chat(PROMPT_THINK, max_tokens=256, thinking=True)
    tps = comp / dt
    print(f"  run {i+1}: {comp} tokens in {dt:.2f}s = {tps:.1f} tok/s")
    think_results.append(tps)
print(f"  MEDIAN: {statistics.median(think_results):.1f} tok/s "
      f"(baseline FP8: 116.5)")

# 5-concurrent
print("\n=== 5-concurrent users (1 run) ===")
prompts = [
    "Write a haiku about caching.",
    "Explain prefix caching in 2 sentences.",
    "List 5 LLM inference optimizations.",
    "What is paged attention?",
    "Define KV cache in 1 sentence.",
]
t0 = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    futures = [ex.submit(chat, p, 256, False) for p in prompts]
    results = [f.result() for f in futures]
t_total = time.monotonic() - t0
total_tokens = sum(r[1] for r in results)
agg_tps = total_tokens / t_total
per_user = [r[1] / r[0] for r in results]
print(f"  Total tokens: {total_tokens}")
print(f"  Wall time:    {t_total:.2f}s")
print(f"  Aggregate:    {agg_tps:.1f} tok/s (baseline FP8: 369)")
print(f"  Per-user:     min={min(per_user):.1f} med={statistics.median(per_user):.1f} max={max(per_user):.1f}")

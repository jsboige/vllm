"""Concurrent scaling bench: 1..48 users at once (distinct prompts -- no prefix-cache inflation)."""
import concurrent.futures
import json
import os
import statistics
import time
import urllib.request

API = "http://localhost:5002/v1/chat/completions"
MODEL = os.environ.get("BENCH_MODEL", "qwen3.6-35b-a3b")
KEY = None
for line in open("d:/vllm/myia_vllm/.env"):
    if line.startswith("VLLM_API_KEY_MEDIUM="):
        KEY = line.split("=", 1)[1].strip()

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
    "Summarize the attention mechanism in 3 bullet points.",
    "What does temperature do in sampling?",
    "Give 2 pros and 2 cons of quantization.",
    "Explain what a tokenizer does.",
    "What is an embedding space?",
    "Define batch inference in one sentence.",
    "Why do LLMs hallucinate? 2 reasons.",
    "What is KV cache eviction?",
    "Explain chunked prefill briefly.",
    "What is a CUDA graph, 1 sentence?",
    "Name 2 LLM serving frameworks other than vLLM.",
    "What does context length mean?",
    "Explain speculative decoding acceptance rate.",
    "What is continuous batching?",
    "Define TTFT vs TPOT.",
    "Why is memory bandwidth the decode bottleneck?",
    "What is a CUDA graph replay?",
    "Explain async scheduling in one sentence.",
    "Define prefix cache hit rate.",
    "Why does FP8 halve KV memory?",
    "What is a page table in paged attention?",
    "Name 2 ways to reduce TTFT.",
    "What does preemption mean for LLM serving?",
    "Explain weight quantization vs KV quantization.",
    "What is a continuous batching head-of-line block?",
    "Define tokens per second per stream.",
    "What is speculative verification cost?",
    "Explain tensor-core utilization briefly.",
    "What is a scheduler step?",
    "Name 2 KV eviction policies.",
    "What is chunked prefill continuation?",
    "Why shard experts across GPUs?",
]


def chat(prompt, max_tokens=256, thinking=False):
    body = {
        "model": MODEL,
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
    return t1 - t0, data["usage"]["completion_tokens"]


# Warmup
chat(PROMPTS[0], max_tokens=32)

print(f"{'N':>3} {'wall':>7} {'tot_tok':>8} {'agg_tps':>9} {'per_min':>8} {'per_med':>8} {'per_max':>8}")
for n_users in [1, 2, 4, 8, 16, 24, 32, 48]:
    prompts = PROMPTS[:n_users]
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_users) as ex:
        futures = [ex.submit(chat, p, 256, False) for p in prompts]
        results = [f.result() for f in futures]
    t_total = time.monotonic() - t0
    total_tokens = sum(r[1] for r in results)
    agg_tps = total_tokens / t_total
    per_user = [r[1] / r[0] for r in results]
    print(f"{n_users:>3} {t_total:>7.2f} {total_tokens:>8} {agg_tps:>9.1f} "
          f"{min(per_user):>8.1f} {statistics.median(per_user):>8.1f} {max(per_user):>8.1f}")

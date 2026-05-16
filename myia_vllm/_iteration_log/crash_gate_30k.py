"""30K-prefix crash gate for Genesis TQ.

The 2026-05-06 MoE+TQ attempt crashed on the first chunked-prefill continuation
with `AssertionError: Workspace is locked` at turboquant_attn.py:720:_continuation_prefill
requiring 29.73 MB / has 16.31 MB. Genesis P22+P38 should fix it.

This script sends one ~30K-token prompt that forces chunked-prefill continuation
(prompt length > --max-num-batched-tokens 4096 = ~7 chunks).
"""
import json
import os
import time
import urllib.request

API = "http://localhost:5002/v1/chat/completions"
KEY = None
for line in open("d:/vllm/myia_vllm/.env"):
    if line.startswith("VLLM_API_KEY_MEDIUM="):
        KEY = line.split("=", 1)[1].strip()

# Build a ~30K-token prefix (~120K chars) of realistic content
# (so vLLM has to chunk it through multiple _continuation_prefill calls).
chunk = (
    "In the field of large language model serving, prefix caching is a "
    "critical optimization. By detecting common prefixes across requests, "
    "the inference engine can skip the prefill computation for the cached "
    "tokens and serve them with near-zero compute, dramatically reducing "
    "time-to-first-token for chatbots, agents, and tool-using workflows. "
    "vLLM's prefix caching implementation uses block-level hashing where "
    "each contiguous block of tokens is hashed with its position, and the "
    "resulting hash is used to look up the KV cache. "
)
# ~480 chars per chunk × 250 = ~120K chars ≈ 30K tokens
prompt_text = chunk * 250 + "\n\nIn one sentence, what is prefix caching?"

print(f"Prompt char length: {len(prompt_text)}")
print(f"Estimated tokens: ~{len(prompt_text) // 4}")

body = {
    "model": "qwen3.6-35b-a3b",
    "messages": [{"role": "user", "content": prompt_text}],
    "max_tokens": 80,
    "temperature": 0,
    "chat_template_kwargs": {"enable_thinking": False},
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
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    t1 = time.monotonic()
    print(f"\nHTTP 200 in {t1 - t0:.2f}s")
    print(f"prompt_tokens: {data['usage'].get('prompt_tokens')}")
    print(f"completion_tokens: {data['usage'].get('completion_tokens')}")
    print(f"finish_reason: {data['choices'][0]['finish_reason']}")
    print(f"content[:200]: {(data['choices'][0]['message'].get('content') or '')[:200]}")
    print("\n=== CRASH GATE: PASS ===")
except Exception as e:
    t1 = time.monotonic()
    print(f"\nFAILED after {t1 - t0:.2f}s: {type(e).__name__}: {e}")
    print("\n=== CRASH GATE: FAIL ===")
    raise

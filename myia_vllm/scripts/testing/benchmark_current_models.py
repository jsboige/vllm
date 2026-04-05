#!/usr/bin/env python3
"""
Benchmark suite for current deployed models.

Tests both deployed vLLM models:
  - Qwen3.5-35B-A3B MoE (GPUs 0,1, port 5002)
  - OmniCoder-9B (GPU 2, port 5001)

Measures: decode speed, TTFT, tool calling, concurrent throughput, vision.

Usage:
    python benchmark_current_models.py
    python benchmark_current_models.py --model medium   # Only Qwen3.5 MoE
    python benchmark_current_models.py --model mini     # Only OmniCoder-9B
    python benchmark_current_models.py --concurrent 10  # 10 concurrent users
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx


@dataclass
class ModelConfig:
    name: str
    url: str
    model_id: str
    api_key: str
    supports_vision: bool = False
    supports_thinking: bool = False


@dataclass
class Result:
    model: str
    test: str
    success: bool
    latency_s: float = 0.0
    ttft_s: float = 0.0
    tokens: int = 0
    tok_per_s: float = 0.0
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


MODELS = {
    "medium": ModelConfig(
        name="Qwen3.5-35B-A3B MoE",
        url=f"http://localhost:{os.environ.get('VLLM_PORT_MEDIUM', '5002')}",
        model_id="qwen3.5-35b-a3b",
        api_key=os.environ.get("VLLM_API_KEY_MEDIUM", ""),
        supports_vision=True,
        supports_thinking=True,
    ),
    "mini": ModelConfig(
        name="OmniCoder-9B",
        url=f"http://localhost:{os.environ.get('VLLM_PORT_MINI', '5001')}",
        model_id="omnicoder-9b",
        api_key=os.environ.get("VLLM_API_KEY_MINI", ""),
        supports_vision=True,
        supports_thinking=True,
    ),
}

# Test prompts
DECODE_PROMPT = "Write a detailed Python implementation of a binary search tree with insert, delete, search, and in-order traversal. Include type hints and docstrings."
SHORT_PROMPT = "What is 2+2?"
TOOL_PROMPT = "What's the weather in Paris today?"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        },
    }
]


async def test_health(client: httpx.AsyncClient, model: ModelConfig) -> Result:
    """Health endpoint check."""
    t0 = time.perf_counter()
    try:
        r = await client.get(f"{model.url}/health", timeout=10)
        lat = time.perf_counter() - t0
        return Result(model.name, "health", r.status_code == 200, latency_s=lat)
    except Exception as e:
        return Result(model.name, "health", False, error=str(e))


async def test_decode(client: httpx.AsyncClient, model: ModelConfig, max_tokens: int = 512) -> Result:
    """Measure decode speed with streaming."""
    headers = {"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"}
    body = {
        "model": model.model_id,
        "messages": [{"role": "user", "content": DECODE_PROMPT}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "stream": True,
    }
    if model.supports_thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}

    tokens = 0
    ttft = None
    t0 = time.perf_counter()

    try:
        async with client.stream("POST", f"{model.url}/v1/chat/completions", json=body, headers=headers, timeout=120) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    tokens += 1

        elapsed = time.perf_counter() - t0
        tps = tokens / elapsed if elapsed > 0 else 0
        return Result(model.name, f"decode_{max_tokens}", True, latency_s=elapsed, ttft_s=ttft or 0, tokens=tokens, tok_per_s=tps)
    except Exception as e:
        return Result(model.name, f"decode_{max_tokens}", False, error=str(e))


async def test_tool_calling(client: httpx.AsyncClient, model: ModelConfig) -> Result:
    """Tool calling latency."""
    headers = {"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"}
    body = {
        "model": model.model_id,
        "messages": [{"role": "user", "content": TOOL_PROMPT}],
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 256,
        "temperature": 0.1,
    }
    if model.supports_thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}

    t0 = time.perf_counter()
    try:
        r = await client.post(f"{model.url}/v1/chat/completions", json=body, headers=headers, timeout=30)
        lat = time.perf_counter() - t0
        data = r.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        has_tool = len(tool_calls) > 0
        fn_name = tool_calls[0]["function"]["name"] if has_tool else None
        return Result(model.name, "tool_call", has_tool, latency_s=lat,
                      details={"function": fn_name, "tool_calls_count": len(tool_calls)})
    except Exception as e:
        return Result(model.name, "tool_call", False, error=str(e))


async def test_thinking(client: httpx.AsyncClient, model: ModelConfig) -> Result:
    """Thinking mode (reasoning extraction)."""
    if not model.supports_thinking:
        return Result(model.name, "thinking", False, error="not supported")

    headers = {"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"}
    body = {
        "model": model.model_id,
        "messages": [{"role": "user", "content": "What is the derivative of x^3 * sin(x)?"}],
        "max_tokens": 1024,
        "temperature": 0.6,
        "stream": True,
    }
    # enable_thinking=True (default, don't set to False)

    tokens = 0
    reasoning_tokens = 0
    content_tokens = 0
    ttft = None
    t0 = time.perf_counter()

    try:
        async with client.stream("POST", f"{model.url}/v1/chat/completions", json=body, headers=headers, timeout=60) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("reasoning"):
                    reasoning_tokens += 1
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                if delta.get("content"):
                    content_tokens += 1
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                tokens = reasoning_tokens + content_tokens

        elapsed = time.perf_counter() - t0
        tps = tokens / elapsed if elapsed > 0 else 0
        return Result(model.name, "thinking", reasoning_tokens > 0, latency_s=elapsed, ttft_s=ttft or 0,
                      tokens=tokens, tok_per_s=tps,
                      details={"reasoning_tokens": reasoning_tokens, "content_tokens": content_tokens})
    except Exception as e:
        return Result(model.name, "thinking", False, error=str(e))


async def test_concurrent(client: httpx.AsyncClient, model: ModelConfig, n_users: int = 5) -> Result:
    """Concurrent throughput test."""
    headers = {"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"}

    prompts = [
        "Explain the difference between TCP and UDP in networking.",
        "Write a Python function to find the longest common subsequence.",
        "What are the SOLID principles in software engineering?",
        "Describe how a hash table works internally.",
        "Explain the CAP theorem in distributed systems.",
        "Write a recursive Fibonacci function with memoization in Python.",
        "What is the difference between a mutex and a semaphore?",
        "Explain how garbage collection works in Java.",
        "Write a Python implementation of quicksort.",
        "Describe the observer design pattern with an example.",
    ]

    async def single_request(prompt: str) -> tuple:
        body = {
            "model": model.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256,
            "temperature": 0.6,
            "stream": True,
        }
        if model.supports_thinking:
            body["chat_template_kwargs"] = {"enable_thinking": False}

        tokens = 0
        t0 = time.perf_counter()
        try:
            async with client.stream("POST", f"{model.url}/v1/chat/completions", json=body, headers=headers, timeout=120) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if delta.get("content"):
                        tokens += 1
            return tokens, time.perf_counter() - t0, None
        except Exception as e:
            return 0, time.perf_counter() - t0, str(e)

    t0 = time.perf_counter()
    tasks = [single_request(prompts[i % len(prompts)]) for i in range(n_users)]
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - t0

    total_tokens = sum(r[0] for r in results)
    errors = [r[2] for r in results if r[2]]
    agg_tps = total_tokens / total_time if total_time > 0 else 0
    per_user = [r[0] / r[1] if r[1] > 0 else 0 for r in results if r[2] is None]
    avg_per_user = sum(per_user) / len(per_user) if per_user else 0

    return Result(model.name, f"concurrent_{n_users}", len(errors) == 0,
                  latency_s=total_time, tokens=total_tokens, tok_per_s=agg_tps,
                  details={
                      "n_users": n_users,
                      "total_tokens": total_tokens,
                      "aggregate_tok_s": round(agg_tps, 1),
                      "avg_per_user_tok_s": round(avg_per_user, 1),
                      "errors": len(errors),
                  })


def print_result(r: Result):
    status = "PASS" if r.success else "FAIL"
    line = f"  [{status}] {r.test:<20s}"
    if r.tok_per_s > 0:
        line += f"  {r.tok_per_s:>7.1f} tok/s"
    if r.tokens > 0:
        line += f"  ({r.tokens} tokens)"
    if r.ttft_s > 0:
        line += f"  TTFT={r.ttft_s:.3f}s"
    if r.latency_s > 0:
        line += f"  total={r.latency_s:.2f}s"
    if r.error:
        line += f"  ERROR: {r.error}"
    if r.details:
        for k, v in r.details.items():
            if k not in ("n_users", "total_tokens"):
                line += f"  {k}={v}"
    print(line)


async def run_benchmarks(model_filter: Optional[str] = None, n_concurrent: int = 5):
    models_to_test = {k: v for k, v in MODELS.items() if model_filter is None or k == model_filter}

    print(f"\n{'='*70}")
    print(f"  vLLM Benchmark — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Models: {', '.join(m.name for m in models_to_test.values())}")
    print(f"  Concurrent users: {n_concurrent}")
    print(f"{'='*70}\n")

    async with httpx.AsyncClient() as client:
        all_results = []

        for key, model in models_to_test.items():
            print(f"\n--- {model.name} ({model.url}) ---")

            # Health
            r = await test_health(client, model)
            print_result(r)
            all_results.append(r)
            if not r.success:
                print(f"  Skipping {model.name} (unhealthy)")
                continue

            # Decode 512
            r = await test_decode(client, model, 512)
            print_result(r)
            all_results.append(r)

            # Tool calling
            r = await test_tool_calling(client, model)
            print_result(r)
            all_results.append(r)

            # Thinking
            r = await test_thinking(client, model)
            print_result(r)
            all_results.append(r)

            # Concurrent
            r = await test_concurrent(client, model, n_concurrent)
            print_result(r)
            all_results.append(r)

        # Summary
        print(f"\n{'='*70}")
        print("  SUMMARY")
        print(f"{'='*70}")
        print(f"  {'Model':<25s} {'Decode tok/s':>12s} {'Tool call':>10s} {'Think tok/s':>12s} {'Conc agg':>10s}")
        print(f"  {'-'*25} {'-'*12} {'-'*10} {'-'*12} {'-'*10}")

        for key, model in models_to_test.items():
            model_results = {r.test: r for r in all_results if r.model == model.name}
            decode = model_results.get("decode_512")
            tool = model_results.get("tool_call")
            think = model_results.get("thinking")
            conc = model_results.get(f"concurrent_{n_concurrent}")

            decode_s = f"{decode.tok_per_s:.1f}" if decode and decode.success else "N/A"
            tool_s = f"{tool.latency_s:.2f}s" if tool and tool.success else "FAIL"
            think_s = f"{think.tok_per_s:.1f}" if think and think.success else "N/A"
            conc_s = f"{conc.tok_per_s:.1f}" if conc and conc.success else "N/A"

            print(f"  {model.name:<25s} {decode_s:>12s} {tool_s:>10s} {think_s:>12s} {conc_s:>10s}")

        print()

        # Save results
        out_dir = os.path.join(os.path.dirname(__file__), "../../benchmark_results")
        os.makedirs(out_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"benchmark_{ts}.json")
        with open(out_path, "w") as f:
            json.dump([{
                "model": r.model, "test": r.test, "success": r.success,
                "latency_s": round(r.latency_s, 4), "ttft_s": round(r.ttft_s, 4),
                "tokens": r.tokens, "tok_per_s": round(r.tok_per_s, 2),
                "error": r.error, "details": r.details,
            } for r in all_results], f, indent=2)
        print(f"  Results saved to: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark current vLLM models")
    parser.add_argument("--model", choices=["medium", "mini"], help="Test only one model")
    parser.add_argument("--concurrent", type=int, default=5, help="Number of concurrent users (default: 5)")
    args = parser.parse_args()

    asyncio.run(run_benchmarks(model_filter=args.model, n_concurrent=args.concurrent))


if __name__ == "__main__":
    main()

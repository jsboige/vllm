#!/usr/bin/env python3
"""
Multi-Model Benchmark Suite.

Tests all 3 deployed models sequentially and concurrently:
  - medium (GLM-4.7-Flash) on port 5002
  - mini (Qwen3-VL-8B-Thinking) on port 5001
  - micro (Qwen3-4B-Thinking) on port 5000

Usage:
    python benchmark_all_models.py
    python benchmark_all_models.py --sequential-only
    python benchmark_all_models.py --concurrent-only
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class ModelConfig:
    name: str
    url: str
    port: int
    api_key: str
    model_id: str
    supports_vision: bool = False
    supports_reasoning: bool = False


@dataclass
class BenchResult:
    model: str
    test: str
    success: bool
    latency_s: float = 0.0
    tokens: int = 0
    tok_per_s: float = 0.0
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


# Model configurations
MODELS = [
    ModelConfig(
        name="medium (GLM-4.7-Flash)",
        url="http://localhost:5002",
        port=5002,
        api_key="Y7PSM158SR952HCAARSLQ344RRPJTDI3",
        model_id="glm-4.7-flash",
        supports_vision=False,
        supports_reasoning=True,
    ),
    ModelConfig(
        name="mini (Qwen3-VL-8B-Thinking)",
        url="http://localhost:5001",
        port=5001,
        api_key="9OYJNTEAAANJF6F17FMHR51Y0532O9QY",
        model_id="qwen3-vl-8b-thinking",
        supports_vision=True,
        supports_reasoning=True,
    ),
    ModelConfig(
        name="micro (Qwen3-4B-Thinking)",
        url="http://localhost:5000",
        port=5000,
        api_key="4S985NRGNN0FZ1P6ZZWNHPJOSAJIMD7M",
        model_id="qwen3-4b-thinking",
        supports_vision=False,
        supports_reasoning=True,
    ),
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"],
            },
        },
    },
]


def extract_content(message: dict) -> str:
    """Extract content from a message, handling Thinking models.

    Thinking models may return content=null with reasoning_content instead.
    """
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    # Return content if available, otherwise use reasoning
    return content if content else reasoning


async def test_health(model: ModelConfig) -> BenchResult:
    """Test health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            start = time.perf_counter()
            resp = await client.get(f"{model.url}/health")
            latency = time.perf_counter() - start
            return BenchResult(
                model=model.name,
                test="health",
                success=resp.status_code == 200,
                latency_s=latency,
            )
    except Exception as e:
        return BenchResult(model=model.name, test="health", success=False, error=str(e))


async def test_inference(model: ModelConfig) -> BenchResult:
    """Test basic chat completion."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{model.url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {model.api_key}"},
                json={
                    "model": model.model_id,
                    "messages": [
                        {"role": "user", "content": "Write a Python function to check if a string is a palindrome. Be concise."}
                    ],
                    "max_tokens": 1000 if model.supports_reasoning else 300,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    model=model.name, test="inference", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            return BenchResult(
                model=model.name, test="inference", success=len(content) > 0,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={
                    "preview": (msg.get("content") or "")[:200],
                    "has_reasoning": len(reasoning) > 0,
                    "reasoning_tokens": len(reasoning.split()) if reasoning else 0,
                },
            )
    except Exception as e:
        return BenchResult(model=model.name, test="inference", success=False, error=str(e))


async def test_tool_calling(model: ModelConfig) -> BenchResult:
    """Test tool/function calling."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{model.url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {model.api_key}"},
                json={
                    "model": model.model_id,
                    "messages": [
                        {"role": "user", "content": "Read the file at /tmp/config.json"}
                    ],
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "max_tokens": 500 if model.supports_reasoning else 200,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    model=model.name, test="tool_calling", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            # Filter out empty tool calls
            tool_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name")]
            has_tool = len(tool_calls) > 0
            correct_tool = has_tool and tool_calls[0]["function"]["name"] == "read_file"

            return BenchResult(
                model=model.name, test="tool_calling",
                success=correct_tool,
                latency_s=latency,
                details={
                    "has_tool_call": has_tool,
                    "tool_name": tool_calls[0]["function"]["name"] if has_tool else None,
                    "num_calls": len(tool_calls),
                    "has_reasoning": bool(msg.get("reasoning_content") or msg.get("reasoning")),
                },
            )
    except Exception as e:
        return BenchResult(model=model.name, test="tool_calling", success=False, error=str(e))


async def test_reasoning(model: ModelConfig) -> BenchResult:
    """Test reasoning/chain-of-thought."""
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{model.url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {model.api_key}"},
                json={
                    "model": model.model_id,
                    "messages": [
                        {"role": "user", "content": "If a train travels 120km in 2 hours, then 180km in 3 hours, what is its average speed for the entire journey? Show your reasoning."}
                    ],
                    "max_tokens": 1500 if model.supports_reasoning else 500,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    model=model.name, test="reasoning", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            # Check both content and reasoning for the answer
            full_text = (content or "") + " " + (reasoning or "")
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            # Check for correct answer (60 km/h)
            has_correct = "60" in full_text
            mentions_reasoning = any(w in full_text.lower() for w in ["300", "total", "5 hour", "average"])

            return BenchResult(
                model=model.name, test="reasoning",
                success=has_correct and mentions_reasoning,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={
                    "preview": (msg.get("content") or "")[:200],
                    "has_correct_answer": has_correct,
                    "has_reasoning": len(reasoning) > 0,
                },
            )
    except Exception as e:
        return BenchResult(model=model.name, test="reasoning", success=False, error=str(e))


async def test_concurrent(models: list[ModelConfig], requests_per_model: int = 3) -> list[BenchResult]:
    """Test all 3 models concurrently."""
    prompts = [
        "Write a function to calculate factorial.",
        "Explain what a binary tree is in 2 sentences.",
        "Write a list comprehension that filters even numbers.",
    ]

    async def single_request(model: ModelConfig, prompt: str) -> BenchResult:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                start = time.perf_counter()
                resp = await client.post(
                    f"{model.url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {model.api_key}"},
                    json={
                        "model": model.model_id,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200,
                        "temperature": 0.7,
                    },
                )
                latency = time.perf_counter() - start

                if resp.status_code != 200:
                    return BenchResult(
                        model=model.name, test="concurrent", success=False,
                        latency_s=latency, error=f"HTTP {resp.status_code}",
                    )

                data = resp.json()
                tokens = data.get("usage", {}).get("completion_tokens", 0)
                tps = tokens / latency if latency > 0 else 0

                return BenchResult(
                    model=model.name, test="concurrent", success=True,
                    latency_s=latency, tokens=tokens, tok_per_s=tps,
                )
        except Exception as e:
            return BenchResult(model=model.name, test="concurrent", success=False, error=str(e))

    # Launch all requests concurrently
    tasks = []
    for model in models:
        for i in range(requests_per_model):
            tasks.append(single_request(model, prompts[i % len(prompts)]))

    start = time.perf_counter()
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start

    # Calculate aggregate metrics per model
    summary_results = []
    for model in models:
        model_results = [r for r in results if r.model == model.name]
        successes = [r for r in model_results if r.success]
        if successes:
            avg_latency = sum(r.latency_s for r in successes) / len(successes)
            total_tokens = sum(r.tokens for r in successes)
            aggregate_tps = total_tokens / total_time
            avg_tps = sum(r.tok_per_s for r in successes) / len(successes)
        else:
            avg_latency = 0
            total_tokens = 0
            aggregate_tps = 0
            avg_tps = 0

        summary_results.append(BenchResult(
            model=model.name, test="concurrent_summary",
            success=len(successes) == len(model_results),
            latency_s=avg_latency, tokens=total_tokens, tok_per_s=aggregate_tps,
            details={
                "requests": len(model_results),
                "successes": len(successes),
                "avg_per_request_tps": round(avg_tps, 1),
                "aggregate_tps": round(aggregate_tps, 1),
                "total_time_s": round(total_time, 2),
            },
        ))

    return summary_results


def print_result(result: BenchResult):
    """Print a single benchmark result."""
    status = "\033[92m✓ PASS\033[0m" if result.success else "\033[91m✗ FAIL\033[0m"
    metrics = ""
    if result.tokens > 0:
        metrics = f" | {result.tokens} tokens, {result.tok_per_s:.1f} tok/s"
    if result.latency_s > 0:
        metrics += f" | {result.latency_s:.2f}s"
    error_msg = f" | ERROR: {result.error}" if result.error else ""
    print(f"  {status} {result.test}{metrics}{error_msg}")


async def main():
    parser = argparse.ArgumentParser(description="Multi-model benchmark suite")
    parser.add_argument("--sequential-only", action="store_true", help="Skip concurrent tests")
    parser.add_argument("--concurrent-only", action="store_true", help="Skip sequential tests")
    parser.add_argument("--requests", type=int, default=3, help="Requests per model in concurrent test")
    args = parser.parse_args()

    print("=" * 70)
    print("MULTI-MODEL BENCHMARK SUITE")
    print("=" * 70)
    print(f"Models: {len(MODELS)}")
    for m in MODELS:
        print(f"  - {m.name}: {m.model_id} (port {m.port})")
    print()

    all_results = []

    # Sequential tests per model
    if not args.concurrent_only:
        for model in MODELS:
            print(f"\n{'─' * 50}")
            print(f"Testing: {model.name}")
            print(f"{'─' * 50}")

            # Health
            result = await test_health(model)
            all_results.append(result)
            print_result(result)

            if not result.success:
                print(f"  ⚠ Skipping remaining tests for {model.name}")
                continue

            # Inference
            result = await test_inference(model)
            all_results.append(result)
            print_result(result)

            # Tool calling
            result = await test_tool_calling(model)
            all_results.append(result)
            print_result(result)

            # Reasoning
            result = await test_reasoning(model)
            all_results.append(result)
            print_result(result)

    # Concurrent test
    if not args.sequential_only:
        print(f"\n{'─' * 50}")
        print(f"Concurrent Load Test ({args.requests} requests × {len(MODELS)} models)")
        print(f"{'─' * 50}")

        concurrent_results = await test_concurrent(MODELS, args.requests)
        all_results.extend(concurrent_results)
        for r in concurrent_results:
            print_result(r)
            if r.details:
                print(f"    Requests: {r.details.get('requests', '?')}, "
                      f"Aggregate: {r.details.get('aggregate_tps', '?')} tok/s, "
                      f"Per-request avg: {r.details.get('avg_per_request_tps', '?')} tok/s, "
                      f"Total time: {r.details.get('total_time_s', '?')}s")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    passed = sum(1 for r in all_results if r.success)
    total = len(all_results)
    print(f"Total: {passed}/{total} tests passed")

    # Per-model summary
    for model in MODELS:
        model_results = [r for r in all_results if r.model == model.name]
        model_passed = sum(1 for r in model_results if r.success)
        inference_results = [r for r in model_results if r.test == "inference" and r.success]
        if inference_results:
            avg_tps = sum(r.tok_per_s for r in inference_results) / len(inference_results)
            print(f"  {model.name}: {model_passed}/{len(model_results)} passed, {avg_tps:.1f} tok/s")
        else:
            print(f"  {model.name}: {model_passed}/{len(model_results)} passed")

    print(f"\n{'=' * 70}")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())

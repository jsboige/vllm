#!/usr/bin/env python3
"""
A/B Benchmark: llama.cpp vs vLLM for GLM-4.7-Flash.

Runs identical tests against an OpenAI-compatible endpoint and saves
results to JSON. Run once with vLLM, once with llama.cpp, then compare.

Usage:
    # Step 1: Benchmark vLLM (already running)
    python benchmark_llamacpp_vs_vllm.py --backend vllm

    # Step 2: Stop vLLM, start llama.cpp, then:
    python benchmark_llamacpp_vs_vllm.py --backend llamacpp

    # Step 3: Compare results
    python benchmark_llamacpp_vs_vllm.py --compare
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

RESULTS_DIR = Path(__file__).parent / "benchmark_results"

AGENTIC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the specified path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return the output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute"},
                },
                "required": ["command"],
            },
        },
    },
]


@dataclass
class TestResult:
    test_name: str
    success: bool
    latency_s: float = 0.0
    ttft_s: float = 0.0
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    prompt_tokens: int = 0
    error: str = ""
    details: dict = field(default_factory=dict)


async def wait_for_service(base_url: str, timeout: int = 120) -> bool:
    """Wait for service to be healthy."""
    print(f"  Waiting for {base_url}/health ...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{base_url}/health")
                if r.status_code == 200:
                    print(f"  Service ready after {time.time() - start:.0f}s")
                    return True
        except Exception:
            pass
        await asyncio.sleep(2)
    print(f"  Timeout after {timeout}s")
    return False


async def streaming_request(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    max_tokens: int = 200,
    timeout: float = 300.0,
    tools: list | None = None,
) -> TestResult:
    """Send a streaming request and measure TTFT + decode speed."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": True,
    }
    if tools:
        body["tools"] = tools

    start = time.perf_counter()
    ttft = 0.0
    tokens = 0
    content_parts = []
    has_tool_call = False

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=body,
            ) as response:
                if response.status_code != 200:
                    body_text = ""
                    async for chunk in response.aiter_text():
                        body_text += chunk
                    return TestResult(
                        test_name="",
                        success=False,
                        error=f"HTTP {response.status_code}: {body_text[:200]}",
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        delta = chunk_data["choices"][0].get("delta", {})

                        # Count content tokens (regular content)
                        if delta.get("content"):
                            if ttft == 0.0:
                                ttft = time.perf_counter() - start
                            tokens += 1
                            content_parts.append(delta["content"])

                        # Count reasoning tokens (GLM-4.7 sends these via reasoning parser)
                        if delta.get("reasoning") or delta.get("reasoning_content"):
                            if ttft == 0.0:
                                ttft = time.perf_counter() - start
                            tokens += 1

                        # Detect tool calls
                        if delta.get("tool_calls"):
                            has_tool_call = True
                            if ttft == 0.0:
                                ttft = time.perf_counter() - start
                            tokens += 1
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        elapsed = time.perf_counter() - start
        decode_time = elapsed - ttft if ttft > 0 else elapsed
        tps = tokens / decode_time if decode_time > 0 and tokens > 0 else 0.0

        return TestResult(
            test_name="",
            success=True,
            latency_s=elapsed,
            ttft_s=ttft,
            tokens_generated=tokens,
            tokens_per_second=tps,
            details={
                "content_preview": "".join(content_parts)[:100],
                "has_tool_call": has_tool_call,
            },
        )

    except Exception as e:
        elapsed = time.perf_counter() - start
        return TestResult(
            test_name="",
            success=False,
            latency_s=elapsed,
            error=str(e),
        )


async def non_streaming_request(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    max_tokens: int = 200,
    timeout: float = 300.0,
    tools: list | None = None,
) -> TestResult:
    """Send a non-streaming request (for usage stats)."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    if tools:
        body["tools"] = tools

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=body,
            )
            elapsed = time.perf_counter() - start

            if r.status_code != 200:
                return TestResult(
                    test_name="",
                    success=False,
                    latency_s=elapsed,
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                )

            data = r.json()
            usage = data.get("usage", {})
            comp_tok = usage.get("completion_tokens", 0)
            prompt_tok = usage.get("prompt_tokens", 0)
            tps = comp_tok / elapsed if elapsed > 0 and comp_tok > 0 else 0.0

            content = ""
            tool_calls = None
            if data.get("choices"):
                msg = data["choices"][0].get("message", {})
                content = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls")

            return TestResult(
                test_name="",
                success=True,
                latency_s=elapsed,
                tokens_generated=comp_tok,
                prompt_tokens=prompt_tok,
                tokens_per_second=tps,
                details={
                    "content_preview": content[:100],
                    "has_tool_call": tool_calls is not None,
                },
            )
    except Exception as e:
        elapsed = time.perf_counter() - start
        return TestResult(
            test_name="",
            success=False,
            latency_s=elapsed,
            error=str(e),
        )


async def run_benchmark(base_url: str, api_key: str, model: str, backend: str) -> list[dict]:
    """Run the full benchmark suite."""
    results = []

    # Check health
    print("\n[1/7] Health check...")
    healthy = await wait_for_service(base_url, timeout=30)
    results.append(asdict(TestResult(
        test_name="health_check",
        success=healthy,
    )))
    if not healthy:
        print("  FAILED - service not reachable")
        return results

    # Test 1: Short prompt (decode speed)
    print("\n[2/7] Short prompt (decode speed)...")
    r = await streaming_request(
        base_url, api_key, model,
        messages=[{"role": "user", "content": "Write a Python function to check if a number is prime. Include docstring and type hints."}],
        max_tokens=500,
    )
    r.test_name = "short_prompt"
    print(f"  {r.tokens_generated} tokens in {r.latency_s:.2f}s = {r.tokens_per_second:.1f} tok/s (TTFT: {r.ttft_s:.3f}s)")
    results.append(asdict(r))

    # Test 2: Medium prompt (5K tokens)
    print("\n[3/7] Medium prompt (~5K tokens)...")
    system_5k = "You are a helpful coding assistant. " * 700  # ~5K tokens
    r = await streaming_request(
        base_url, api_key, model,
        messages=[
            {"role": "system", "content": system_5k},
            {"role": "user", "content": "Say OK."},
        ],
        max_tokens=10,
    )
    r.test_name = "medium_prompt_5k"
    print(f"  {r.tokens_generated} tokens in {r.latency_s:.2f}s (TTFT: {r.ttft_s:.3f}s)")
    results.append(asdict(r))

    # Test 3: Long prompt (30K tokens) - cold
    print("\n[4/7] Long prompt (~30K tokens, cold)...")
    system_30k = "You are a helpful assistant. " * 4300  # ~30K tokens
    r = await streaming_request(
        base_url, api_key, model,
        messages=[
            {"role": "system", "content": system_30k},
            {"role": "user", "content": "Say OK."},
        ],
        max_tokens=10,
        timeout=300.0,
    )
    r.test_name = "long_prompt_30k_cold"
    print(f"  {r.tokens_generated} tokens in {r.latency_s:.2f}s (TTFT: {r.ttft_s:.3f}s)")
    results.append(asdict(r))

    # Test 4: Long prompt repeat (cache test)
    print("\n[5/7] Long prompt repeat (cache test)...")
    r = await streaming_request(
        base_url, api_key, model,
        messages=[
            {"role": "system", "content": system_30k},
            {"role": "user", "content": "Say hello."},
        ],
        max_tokens=10,
        timeout=300.0,
    )
    r.test_name = "long_prompt_30k_cached"
    print(f"  {r.tokens_generated} tokens in {r.latency_s:.2f}s (TTFT: {r.ttft_s:.3f}s)")
    results.append(asdict(r))

    # Test 5: Tool calling
    print("\n[6/7] Tool calling...")
    r = await non_streaming_request(
        base_url, api_key, model,
        messages=[{"role": "user", "content": "Read the file at /etc/hostname"}],
        max_tokens=100,
        tools=AGENTIC_TOOLS,
    )
    r.test_name = "tool_calling"
    has_tc = r.details.get("has_tool_call", False)
    print(f"  {'OK - tool call detected' if has_tc else 'No tool call'} in {r.latency_s:.2f}s")
    results.append(asdict(r))

    # Test 6: Concurrent users (5)
    print("\n[7/7] Concurrent users (5 simultaneous requests)...")
    concurrent_start = time.perf_counter()
    tasks = []
    for i in range(5):
        tasks.append(streaming_request(
            base_url, api_key, model,
            messages=[{"role": "user", "content": f"Write a Python function #{i+1}: implement a binary search algorithm with type hints."}],
            max_tokens=300,
        ))
    concurrent_results = await asyncio.gather(*tasks)
    concurrent_elapsed = time.perf_counter() - concurrent_start

    total_tokens = sum(r.tokens_generated for r in concurrent_results)
    successful = sum(1 for r in concurrent_results if r.success)
    aggregate_tps = total_tokens / concurrent_elapsed if concurrent_elapsed > 0 else 0.0
    avg_tps = sum(r.tokens_per_second for r in concurrent_results if r.success) / max(successful, 1)
    avg_ttft = sum(r.ttft_s for r in concurrent_results if r.success) / max(successful, 1)

    print(f"  {successful}/5 succeeded, {total_tokens} total tokens in {concurrent_elapsed:.2f}s")
    print(f"  Aggregate: {aggregate_tps:.1f} tok/s, Avg per-user: {avg_tps:.1f} tok/s, Avg TTFT: {avg_ttft:.3f}s")

    results.append(asdict(TestResult(
        test_name="concurrent_5_users",
        success=successful == 5,
        latency_s=concurrent_elapsed,
        tokens_generated=total_tokens,
        tokens_per_second=aggregate_tps,
        details={
            "successful": successful,
            "avg_tps_per_user": avg_tps,
            "avg_ttft": avg_ttft,
            "individual_tps": [r.tokens_per_second for r in concurrent_results],
            "individual_ttft": [r.ttft_s for r in concurrent_results],
        },
    )))

    return results


def save_results(results: list[dict], backend: str):
    """Save benchmark results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "backend": backend,
        "timestamp": datetime.now().isoformat(),
        "results": results,
    }
    path = RESULTS_DIR / f"benchmark_{backend}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {path}")


def compare_results():
    """Load and compare vLLM vs llama.cpp results."""
    vllm_path = RESULTS_DIR / "benchmark_vllm.json"
    llamacpp_path = RESULTS_DIR / "benchmark_llamacpp.json"

    if not vllm_path.exists():
        print(f"Missing {vllm_path} - run with --backend vllm first")
        return
    if not llamacpp_path.exists():
        print(f"Missing {llamacpp_path} - run with --backend llamacpp first")
        return

    with open(vllm_path, encoding="utf-8") as f:
        vllm_data = json.load(f)
    with open(llamacpp_path, encoding="utf-8") as f:
        llama_data = json.load(f)

    vllm_results = {r["test_name"]: r for r in vllm_data["results"]}
    llama_results = {r["test_name"]: r for r in llama_data["results"]}

    print("\n" + "=" * 90)
    print("  BENCHMARK COMPARISON: vLLM vs llama.cpp (GLM-4.7-Flash)")
    print("=" * 90)
    print(f"  vLLM run:     {vllm_data['timestamp']}")
    print(f"  llama.cpp run: {llama_data['timestamp']}")
    print("-" * 90)

    header = f"{'Test':<25} | {'Metric':<12} | {'vLLM':>12} | {'llama.cpp':>12} | {'Winner':>10}"
    print(header)
    print("-" * 90)

    tests_to_compare = [
        ("short_prompt", "tok/s", "tokens_per_second", "{:.1f}"),
        ("short_prompt", "TTFT (s)", "ttft_s", "{:.3f}"),
        ("medium_prompt_5k", "TTFT (s)", "ttft_s", "{:.3f}"),
        ("long_prompt_30k_cold", "TTFT (s)", "ttft_s", "{:.3f}"),
        ("long_prompt_30k_cold", "Total (s)", "latency_s", "{:.2f}"),
        ("long_prompt_30k_cached", "TTFT (s)", "ttft_s", "{:.3f}"),
        ("tool_calling", "Latency (s)", "latency_s", "{:.2f}"),
        ("concurrent_5_users", "Agg tok/s", "tokens_per_second", "{:.1f}"),
        ("concurrent_5_users", "Total (s)", "latency_s", "{:.2f}"),
    ]

    for test_name, metric_label, field_name, fmt in tests_to_compare:
        v = vllm_results.get(test_name, {})
        l = llama_results.get(test_name, {})

        v_val = v.get(field_name, 0)
        l_val = l.get(field_name, 0)

        # For tok/s: higher is better. For latency/TTFT: lower is better.
        higher_is_better = "tok/s" in metric_label
        if higher_is_better:
            winner = "vLLM" if v_val >= l_val else "llama.cpp"
        else:
            if v_val == 0 and l_val == 0:
                winner = "tie"
            elif v_val == 0:
                winner = "vLLM"  # 0 means test didn't run
            elif l_val == 0:
                winner = "llama.cpp"
            else:
                winner = "vLLM" if v_val <= l_val else "llama.cpp"

        v_str = fmt.format(v_val) if v_val else "N/A"
        l_str = fmt.format(l_val) if l_val else "N/A"

        # Color indicator
        if winner == "vLLM":
            indicator = "<<<"
        elif winner == "llama.cpp":
            indicator = ">>>"
        else:
            indicator = "==="

        print(f"{test_name:<25} | {metric_label:<12} | {v_str:>12} | {l_str:>12} | {indicator:>10}")

    print("-" * 90)

    # Tool calling comparison
    v_tc = vllm_results.get("tool_calling", {}).get("details", {}).get("has_tool_call", False)
    l_tc = llama_results.get("tool_calling", {}).get("details", {}).get("has_tool_call", False)
    print(f"\nTool calling support: vLLM={'Yes' if v_tc else 'No'}, llama.cpp={'Yes' if l_tc else 'No'}")

    # Concurrent details
    v_conc = vllm_results.get("concurrent_5_users", {}).get("details", {})
    l_conc = llama_results.get("concurrent_5_users", {}).get("details", {})
    if v_conc and l_conc:
        print(f"\nConcurrent details:")
        print(f"  vLLM:     avg {v_conc.get('avg_tps_per_user', 0):.1f} tok/s/user, TTFT {v_conc.get('avg_ttft', 0):.3f}s")
        print(f"  llama.cpp: avg {l_conc.get('avg_tps_per_user', 0):.1f} tok/s/user, TTFT {l_conc.get('avg_ttft', 0):.3f}s")

    print("\n" + "=" * 90)
    print("  <<< = vLLM wins   >>> = llama.cpp wins   === = tie")
    print("=" * 90)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark vLLM vs llama.cpp for GLM-4.7-Flash")
    parser.add_argument("--backend", type=str, help="Backend to benchmark (e.g. vllm, llamacpp, vllm_autotune)")
    parser.add_argument("--compare", action="store_true", help="Compare saved results")
    parser.add_argument("--port", type=int, default=5002, help="API port (default: 5002)")
    parser.add_argument("--host", type=str, default="localhost", help="API host")
    parser.add_argument("--model", type=str, default="glm-4.7-flash", help="Model name")
    parser.add_argument("--api-key", type=str, default=None, help="API key")
    args = parser.parse_args()

    if args.compare:
        compare_results()
        return

    if not args.backend:
        parser.error("--backend or --compare required")

    api_key = args.api_key or os.environ.get("VLLM_API_KEY_MEDIUM", "")
    base_url = f"http://{args.host}:{args.port}"

    print(f"{'=' * 60}")
    print(f"  Benchmarking: {args.backend.upper()}")
    print(f"  Endpoint: {base_url}")
    print(f"  Model: {args.model}")
    print(f"{'=' * 60}")

    results = await run_benchmark(base_url, api_key, args.model, args.backend)
    save_results(results, args.backend)

    print("\nDone! Run with --compare after benchmarking both backends.")


if __name__ == "__main__":
    asyncio.run(main())

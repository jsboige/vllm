#!/usr/bin/env python3
"""
Comprehensive vLLM Benchmark and Performance Monitoring Tool.

This reusable agent tests all deployed models, compares with reference benchmarks,
and generates detailed reports for performance tracking.

Usage:
    # Quick benchmark (single-user only)
    python benchmark_report.py --quick

    # Full benchmark with concurrent tests
    python benchmark_report.py

    # Benchmark specific model only
    python benchmark_report.py --model glm

    # Generate markdown report
    python benchmark_report.py --output report.md

    # Compare with reference (Internet benchmarks)
    python benchmark_report.py --compare-reference

Example cron/scheduled task:
    # Run daily at 6 AM
    0 6 * * * cd /path/to/vllm && python myia_vllm/scripts/testing/benchmark_report.py --output reports/$(date +%Y%m%d).md
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class ModelConfig:
    """Configuration for a model endpoint."""
    name: str
    short_name: str
    url: str
    port: int
    api_key: str
    model_id: str
    expected_single_user_tps: tuple[float, float]  # (min, max) expected range
    expected_concurrent_tps: float  # Expected aggregate tps with 5 concurrent
    supports_vision: bool = False
    is_moe: bool = False
    context_len: int = 32768
    notes: str = ""


# Reference benchmarks from Internet research (February 2026)
# These are used for comparison and to detect regressions
REFERENCE_BENCHMARKS = {
    "glm-4.7-flash": {
        "single_user": (45, 58),  # RTX 4090 TP=2, 128K context, AWQ
        "concurrent_5": 227,
        "source": "Internal optimized config",
        "notes": "128K context limits throughput vs 4K benchmarks (120-220 tok/s)",
    },
    "qwen3-4b-thinking": {
        "single_user": (100, 210),  # RTX 4090, solo, CUDA graphs
        "concurrent_5": 508,
        "source": "Internal benchmark, solo mode",
        "notes": "Shared GPU mode: 64-66 tok/s (enforce-eager penalty)",
    },
    "qwen3-vl-8b-thinking": {
        "single_user": (80, 130),  # RTX 4090, solo, CUDA graphs
        "concurrent_5": 364,
        "source": "Internal benchmark, solo mode",
        "notes": "Vision model, text-only tests. Shared GPU: 53-54 tok/s",
    },
}


# Load API keys from environment or use defaults (for development)
def get_api_key(service: str) -> str:
    """Get API key from environment variable."""
    env_var = f"VLLM_API_KEY_{service.upper()}"
    key = os.environ.get(env_var)
    if key:
        return key
    # Fallback to hardcoded keys (development only)
    defaults = {
        "MEDIUM": "Y7PSM158SR952HCAARSLQ344RRPJTDI3",
        "MINI": "9OYJNTEAAANJF6F17FMHR51Y0532O9QY",
        "MICRO": "4S985NRGNN0FZ1P6ZZWNHPJOSAJIMD7M",
    }
    return defaults.get(service.upper(), "")


# Model configurations - update as deployment changes
MODELS = {
    "glm": ModelConfig(
        name="GLM-4.7-Flash (31B MoE)",
        short_name="glm",
        url="http://localhost:5002",
        port=5002,
        api_key=get_api_key("MEDIUM"),
        model_id="glm-4.7-flash",
        expected_single_user_tps=(45, 60),
        expected_concurrent_tps=220,
        is_moe=True,
        context_len=131072,
        notes="2x RTX 4090, TP=2, AWQ 4-bit, 128K context",
    ),
    "mini": ModelConfig(
        name="Qwen3-VL-8B-Thinking",
        short_name="mini",
        url="http://localhost:5001",
        port=5001,
        api_key=get_api_key("MINI"),
        model_id="qwen3-vl-8b-thinking",
        expected_single_user_tps=(50, 130),  # Range covers shared/solo
        expected_concurrent_tps=100,  # Conservative for shared mode
        supports_vision=True,
        context_len=16384,
        notes="GPU 2, AWQ 4-bit, vision capable",
    ),
    "micro": ModelConfig(
        name="Qwen3-4B-Thinking",
        short_name="micro",
        url="http://localhost:5000",
        port=5000,
        api_key=get_api_key("MICRO"),
        model_id="qwen3-4b-thinking",
        expected_single_user_tps=(60, 210),  # Range covers shared/solo
        expected_concurrent_tps=100,  # Conservative for shared mode
        context_len=65536,
        notes="GPU 2, AWQ 4-bit, Thinking model",
    ),
}


# ============================================================================
# BENCHMARK FUNCTIONS
# ============================================================================

@dataclass
class BenchResult:
    """Result from a single benchmark test."""
    model: str
    test_name: str
    success: bool
    tokens: int = 0
    latency_s: float = 0.0
    tps: float = 0.0
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


async def check_health(model: ModelConfig) -> BenchResult:
    """Check if model endpoint is healthy."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            start = time.perf_counter()
            resp = await client.get(f"{model.url}/health")
            latency = time.perf_counter() - start
            return BenchResult(
                model=model.short_name,
                test_name="health",
                success=resp.status_code == 200,
                latency_s=latency,
            )
    except Exception as e:
        return BenchResult(
            model=model.short_name,
            test_name="health",
            success=False,
            error=str(e),
        )


async def run_inference(
    model: ModelConfig,
    prompt: str,
    max_tokens: int = 500,
    test_name: str = "inference",
) -> BenchResult:
    """Run a single inference request."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{model.url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {model.api_key}"},
                json={
                    "model": model.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    model=model.short_name,
                    test_name=test_name,
                    success=False,
                    latency_s=latency,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            tokens = data.get("usage", {}).get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            return BenchResult(
                model=model.short_name,
                test_name=test_name,
                success=True,
                tokens=tokens,
                latency_s=latency,
                tps=tps,
            )
    except Exception as e:
        return BenchResult(
            model=model.short_name,
            test_name=test_name,
            success=False,
            error=str(e),
        )


async def benchmark_single_user(model: ModelConfig) -> list[BenchResult]:
    """Run single-user benchmark (3 sequential requests)."""
    prompts = [
        "Write a Python function to check if a number is prime.",
        "Explain recursion in 3 sentences.",
        "Write a list comprehension to filter odd numbers from 1 to 100.",
    ]

    results = []
    for i, prompt in enumerate(prompts):
        result = await run_inference(model, prompt, test_name=f"single_{i+1}")
        results.append(result)

    return results


async def benchmark_concurrent(
    model: ModelConfig,
    num_requests: int = 5,
) -> BenchResult:
    """Run concurrent benchmark."""
    prompts = [
        "Write a Python function to calculate factorial.",
        "Explain what a binary tree is in 2 sentences.",
        "Write a list comprehension that filters even numbers.",
        "What is the difference between a list and a tuple in Python?",
        "Write a function to reverse a string.",
    ]

    async def single_req(idx: int) -> tuple[int, float]:
        prompt = prompts[idx % len(prompts)]
        result = await run_inference(model, prompt, max_tokens=300, test_name="concurrent")
        return result.tokens if result.success else 0, result.latency_s

    start = time.perf_counter()
    tasks = [single_req(i) for i in range(num_requests)]
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start

    total_tokens = sum(r[0] for r in results)
    aggregate_tps = total_tokens / total_time if total_time > 0 else 0
    successes = sum(1 for r in results if r[0] > 0)

    return BenchResult(
        model=model.short_name,
        test_name=f"concurrent_{num_requests}",
        success=successes == num_requests,
        tokens=total_tokens,
        latency_s=total_time,
        tps=aggregate_tps,
        details={
            "requests": num_requests,
            "successes": successes,
            "total_time_s": round(total_time, 2),
        },
    )


# ============================================================================
# REPORTING
# ============================================================================

def format_tps(tps: float, expected: tuple[float, float]) -> str:
    """Format TPS with comparison to expected range."""
    min_exp, max_exp = expected
    if tps < min_exp * 0.8:
        status = "LOW"
    elif tps > max_exp * 1.1:
        status = "HIGH"
    else:
        status = "OK"
    return f"{tps:.1f} tok/s ({status} vs {min_exp}-{max_exp})"


def generate_report(
    results: dict[str, list[BenchResult]],
    compare_reference: bool = False,
) -> str:
    """Generate markdown report from benchmark results."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# vLLM Performance Benchmark Report",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
        "| Model | Single-user (tok/s) | Concurrent (5 req) | Status |",
        "|-------|---------------------|-------------------|--------|",
    ]

    for model_key, model_results in results.items():
        model = MODELS.get(model_key)
        if not model:
            continue

        # Calculate averages
        single_results = [r for r in model_results if r.test_name.startswith("single_") and r.success]
        concurrent_results = [r for r in model_results if r.test_name.startswith("concurrent_") and r.success]

        if single_results:
            avg_single_tps = sum(r.tps for r in single_results) / len(single_results)
            single_str = format_tps(avg_single_tps, model.expected_single_user_tps)
        else:
            single_str = "FAILED"

        if concurrent_results:
            concurrent_tps = concurrent_results[0].tps
            status = "OK" if concurrent_tps >= model.expected_concurrent_tps * 0.8 else "LOW"
            concurrent_str = f"{concurrent_tps:.1f} tok/s ({status})"
        else:
            concurrent_str = "N/A"

        health = [r for r in model_results if r.test_name == "health"]
        status = "Healthy" if health and health[0].success else "DOWN"

        lines.append(f"| {model.name} | {single_str} | {concurrent_str} | {status} |")

    lines.extend([
        "",
        "## Detailed Results",
        "",
    ])

    for model_key, model_results in results.items():
        model = MODELS.get(model_key)
        if not model:
            continue

        lines.extend([
            f"### {model.name}",
            f"- Endpoint: `{model.url}`",
            f"- Model ID: `{model.model_id}`",
            f"- Context: {model.context_len:,} tokens",
            f"- Notes: {model.notes}",
            "",
        ])

        for result in model_results:
            status = "PASS" if result.success else "FAIL"
            metrics = ""
            if result.tokens > 0:
                metrics = f" | {result.tokens} tokens, {result.tps:.1f} tok/s"
            if result.latency_s > 0:
                metrics += f" | {result.latency_s:.2f}s"
            error = f" | ERROR: {result.error}" if result.error else ""
            lines.append(f"- [{status}] {result.test_name}{metrics}{error}")

        lines.append("")

    if compare_reference:
        lines.extend([
            "## Reference Comparison",
            "",
            "| Model | Our Results | Reference (Internet) | Source |",
            "|-------|-------------|---------------------|--------|",
        ])

        for model_key, model_results in results.items():
            model = MODELS.get(model_key)
            ref = REFERENCE_BENCHMARKS.get(model.model_id if model else "")
            if not model or not ref:
                continue

            single_results = [r for r in model_results if r.test_name.startswith("single_") and r.success]
            if single_results:
                avg = sum(r.tps for r in single_results) / len(single_results)
                ref_range = ref["single_user"]
                lines.append(
                    f"| {model.short_name} | {avg:.1f} tok/s | {ref_range[0]}-{ref_range[1]} tok/s | {ref['source']} |"
                )

        lines.append("")

    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="vLLM Benchmark and Performance Monitoring Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()),
        help="Benchmark specific model only",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick benchmark (single-user only, skip concurrent)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output markdown report to file",
    )
    parser.add_argument(
        "--compare-reference",
        action="store_true",
        help="Compare results with Internet reference benchmarks",
    )
    parser.add_argument(
        "--concurrent-requests",
        type=int,
        default=5,
        help="Number of concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    # Select models to benchmark
    if args.model:
        models_to_test = {args.model: MODELS[args.model]}
    else:
        models_to_test = MODELS

    print("=" * 70)
    print("vLLM PERFORMANCE BENCHMARK")
    print("=" * 70)
    print(f"Models: {', '.join(models_to_test.keys())}")
    print(f"Mode: {'Quick' if args.quick else 'Full'}")
    print()

    all_results: dict[str, list[BenchResult]] = {}

    for model_key, model in models_to_test.items():
        print(f"\n{'─' * 50}")
        print(f"Testing: {model.name}")
        print(f"{'─' * 50}")

        results = []

        # Health check
        health = await check_health(model)
        results.append(health)
        status = "OK" if health.success else f"FAIL ({health.error})"
        print(f"  Health: {status} ({health.latency_s*1000:.0f}ms)")

        if not health.success:
            print(f"  Skipping remaining tests for {model.name}")
            all_results[model_key] = results
            continue

        # Single-user benchmark
        print("  Single-user tests:")
        single_results = await benchmark_single_user(model)
        results.extend(single_results)
        for r in single_results:
            if r.success:
                print(f"    {r.test_name}: {r.tokens} tokens, {r.tps:.1f} tok/s ({r.latency_s:.2f}s)")
            else:
                print(f"    {r.test_name}: FAILED - {r.error}")

        # Concurrent benchmark
        if not args.quick:
            print(f"  Concurrent test ({args.concurrent_requests} requests):")
            concurrent = await benchmark_concurrent(model, args.concurrent_requests)
            results.append(concurrent)
            if concurrent.success:
                print(f"    Aggregate: {concurrent.tps:.1f} tok/s ({concurrent.tokens} tokens in {concurrent.latency_s:.2f}s)")
            else:
                print(f"    FAILED - {concurrent.error}")

        all_results[model_key] = results

    # Generate report
    print(f"\n{'=' * 70}")
    print("BENCHMARK COMPLETE")
    print(f"{'=' * 70}")

    if args.json:
        # JSON output
        json_results = {}
        for model_key, results in all_results.items():
            json_results[model_key] = [
                {
                    "test": r.test_name,
                    "success": r.success,
                    "tokens": r.tokens,
                    "latency_s": r.latency_s,
                    "tps": r.tps,
                    "error": r.error,
                }
                for r in results
            ]
        output = json.dumps(json_results, indent=2)
    else:
        # Markdown report
        output = generate_report(all_results, args.compare_reference)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report saved to: {args.output}")
    else:
        print()
        print(output)


if __name__ == "__main__":
    asyncio.run(main())

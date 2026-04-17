#!/usr/bin/env python3
"""
Benchmark script for measuring repetition in Qwen3.5-35B-A3B responses.

Tests different sampling parameter combinations to find optimal settings
for reducing repetition while maintaining quality. Designed for AWQ 4-bit
quantized models which may need different params than BF16 originals.

Metrics:
- N-gram repetition rate (4-gram, 8-gram)
- Type-token ratio (lexical diversity)
- Tokens per second (performance impact)
- Output length (penalty impact on verbosity)

Usage:
    python benchmark_repetition.py --api-url http://localhost:5002/v1
    python benchmark_repetition.py --preset qwen-think-general
    python benchmark_repetition.py --grid-search  # Full matrix (~60 combos)
"""

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Test prompts designed to provoke repetition
# ---------------------------------------------------------------------------

PROMPTS = {
    "list_long": {
        "category": "list",
        "messages": [
            {"role": "user", "content": "List 50 different creative ways to use a paperclip. Number each one and make each suggestion unique and specific."}
        ],
        "max_tokens": 2048,
    },
    "list_technical": {
        "category": "list",
        "messages": [
            {"role": "user", "content": "List 30 distinct Python design patterns with a one-sentence description for each. Avoid repeating similar patterns."}
        ],
        "max_tokens": 2048,
    },
    "explanation": {
        "category": "explanation",
        "messages": [
            {"role": "user", "content": "Explain in great detail the history and evolution of version control systems, from RCS to Git. Cover at least 5 major milestones."}
        ],
        "max_tokens": 2048,
    },
    "explanation_technical": {
        "category": "explanation",
        "messages": [
            {"role": "user", "content": "Provide a detailed technical explanation of how transformer attention mechanisms work, including multi-head attention, positional encoding, and the differences between encoder and decoder attention."}
        ],
        "max_tokens": 2048,
    },
    "code_crud": {
        "category": "code",
        "messages": [
            {"role": "user", "content": "Write a complete Python FastAPI application with CRUD endpoints for 5 different entities: Users, Products, Orders, Reviews, and Categories. Each entity should have different fields and validation rules."}
        ],
        "max_tokens": 4096,
    },
    "code_algorithms": {
        "category": "code",
        "messages": [
            {"role": "user", "content": "Implement 8 different sorting algorithms in Python (bubble, selection, insertion, merge, quick, heap, radix, counting) with docstrings and complexity analysis for each."}
        ],
        "max_tokens": 4096,
    },
    "multiturn_debate": {
        "category": "multiturn",
        "messages": [
            {"role": "user", "content": "What are the pros and cons of microservices vs monolithic architecture?"},
            {"role": "assistant", "content": "Microservices offer independent scaling, technology diversity, and fault isolation, but add complexity in deployment, data consistency, and inter-service communication. Monoliths are simpler to develop and deploy but harder to scale and maintain as they grow."},
            {"role": "user", "content": "Can you elaborate more on the data consistency challenges with microservices?"},
            {"role": "assistant", "content": "The main challenge is maintaining data consistency across services that each own their own database. You need patterns like Saga (choreography or orchestration), event sourcing, or CQRS. Distributed transactions (2PC) are generally avoided due to performance and availability concerns."},
            {"role": "user", "content": "Now explain in detail how the Saga pattern works with a concrete e-commerce example, covering both the happy path and compensation/rollback scenarios."},
        ],
        "max_tokens": 2048,
    },
    "multiturn_refine": {
        "category": "multiturn",
        "messages": [
            {"role": "user", "content": "Write a Python function to validate email addresses."},
            {"role": "assistant", "content": "```python\nimport re\n\ndef validate_email(email: str) -> bool:\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email))\n```"},
            {"role": "user", "content": "Good, but now make it more robust: handle edge cases like consecutive dots, leading/trailing spaces, international domains, and add detailed error messages explaining why validation failed."},
        ],
        "max_tokens": 2048,
    },
    "instruction_following": {
        "category": "instruction",
        "messages": [
            {"role": "user", "content": "Write a response that follows ALL of these rules:\n1. Use exactly 5 paragraphs\n2. Each paragraph must start with a different letter of the word HELLO\n3. Include at least one metaphor in each paragraph\n4. The topic is climate change\n5. Each paragraph must be between 3-5 sentences\n6. Do not use the word 'the' more than twice per paragraph"}
        ],
        "max_tokens": 1024,
    },
    "instruction_format": {
        "category": "instruction",
        "messages": [
            {"role": "user", "content": "Create a structured comparison table of 5 programming languages (Python, Rust, Go, TypeScript, Java) across these dimensions: typing system, concurrency model, memory management, ecosystem maturity, learning curve, and primary use cases. Format as a markdown table with clear headers. After the table, write one paragraph summarizing which language you'd recommend for a new backend project and why."}
        ],
        "max_tokens": 1024,
    },
}


# ---------------------------------------------------------------------------
# Qwen-recommended parameter presets
# ---------------------------------------------------------------------------

PRESETS = {
    # --- Calibrated for AWQ Q4 (2026-03-21) ---
    # Adjusted from official Qwen BF16 recommendations:
    # temp 1.0→0.7 (Q4 stability), pp 2.0→1.5 (language mixing), rp 1.05-1.1 (anti-bleed)
    "qwen-think-general": {
        "temperature": 0.7, "top_p": 0.95, "presence_penalty": 1.5,
        "extra_body": {"top_k": 20, "chat_template_kwargs": {"enable_thinking": True}},
    },
    "qwen-think-code": {
        "temperature": 0.6, "top_p": 0.95, "presence_penalty": 0.0,
        "extra_body": {"top_k": 20, "chat_template_kwargs": {"enable_thinking": True}},
    },
    "qwen-think-reason": {
        "temperature": 1.0, "top_p": 1.0, "presence_penalty": 1.5,
        "extra_body": {"top_k": 40, "chat_template_kwargs": {"enable_thinking": True}},
    },
    "qwen-instruct": {
        "temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5,
        "extra_body": {"top_k": 20, "repetition_penalty": 1.1, "min_p": 0.01,
                       "chat_template_kwargs": {"enable_thinking": False}},
    },
    "qwen-fast": {
        "temperature": 0.6, "top_p": 0.85, "presence_penalty": 0.5,
        "extra_body": {"top_k": 20, "repetition_penalty": 1.1, "min_p": 0.01,
                       "chat_template_kwargs": {"enable_thinking": False}},
    },
    # --- Baselines for comparison ---
    "baseline-low-temp": {
        "temperature": 0.1, "top_p": 1.0, "presence_penalty": 0.0,
        "extra_body": {},
    },
    "baseline-server-defaults": {
        "temperature": 0.6, "top_p": 0.95, "presence_penalty": 0.0,
        "extra_body": {"top_k": 20},
    },
}

# Grid search parameter space
GRID_TEMPERATURES = [0.3, 0.6, 0.7, 1.0]
GRID_PRESENCE_PENALTIES = [0.0, 0.5, 1.0, 1.5, 2.0]
GRID_TOP_P = [0.8, 0.95, 1.0]


# ---------------------------------------------------------------------------
# Repetition metrics
# ---------------------------------------------------------------------------

def ngram_repetition_rate(text: str, n: int) -> float:
    """Compute fraction of repeated n-grams in text."""
    words = text.lower().split()
    if len(words) < n:
        return 0.0
    ngrams = [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]
    total = len(ngrams)
    unique = len(set(ngrams))
    if total == 0:
        return 0.0
    return 1.0 - (unique / total)


def type_token_ratio(text: str) -> float:
    """Compute type-token ratio (lexical diversity). Higher = more diverse."""
    words = text.lower().split()
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def longest_repeated_substring_ratio(text: str, min_len: int = 30) -> float:
    """Estimate ratio of text that is exact repeated content (char-level).

    Simple approach: find repeated lines/sentences.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return 0.0
    counts = Counter(lines)
    repeated_chars = sum(len(line) * (count - 1) for line, count in counts.items()
                        if count > 1 and len(line) >= min_len)
    total_chars = sum(len(line) for line in lines)
    return repeated_chars / total_chars if total_chars > 0 else 0.0


@dataclass
class RepetitionMetrics:
    """Container for repetition analysis results."""
    ngram_4_rate: float = 0.0
    ngram_8_rate: float = 0.0
    type_token: float = 0.0
    repeated_line_ratio: float = 0.0
    word_count: int = 0
    char_count: int = 0

    def summary(self) -> str:
        return (f"4gram={self.ngram_4_rate:.3f} 8gram={self.ngram_8_rate:.3f} "
                f"TTR={self.type_token:.3f} RepLines={self.repeated_line_ratio:.3f} "
                f"words={self.word_count}")


def analyze_repetition(text: str) -> RepetitionMetrics:
    """Compute all repetition metrics for a text."""
    if not text:
        return RepetitionMetrics()
    return RepetitionMetrics(
        ngram_4_rate=ngram_repetition_rate(text, 4),
        ngram_8_rate=ngram_repetition_rate(text, 8),
        type_token=type_token_ratio(text),
        repeated_line_ratio=longest_repeated_substring_ratio(text),
        word_count=len(text.split()),
        char_count=len(text),
    )


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    prompt_name: str
    category: str
    preset_name: str
    temperature: float
    top_p: float
    presence_penalty: float
    top_k: Optional[int] = None
    thinking: Optional[bool] = None
    # Performance
    tokens_per_second: float = 0.0
    ttft_s: float = 0.0
    e2e_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Repetition metrics
    ngram_4_rate: float = 0.0
    ngram_8_rate: float = 0.0
    type_token_ratio: float = 0.0
    repeated_line_ratio: float = 0.0
    word_count: int = 0
    # Status
    success: bool = True
    error: Optional[str] = None
    # Content preview
    response_preview: str = ""


async def run_single_test(
    client: httpx.AsyncClient,
    api_url: str,
    model: str,
    api_key: str,
    prompt_name: str,
    prompt_config: dict,
    params: dict,
    preset_name: str = "custom",
) -> BenchmarkResult:
    """Run a single test with given prompt and parameters."""
    temperature = params.get("temperature", 1.0)
    top_p = params.get("top_p", 1.0)
    presence_penalty = params.get("presence_penalty", 0.0)
    extra_body = params.get("extra_body", {})
    top_k = extra_body.get("top_k")
    thinking = extra_body.get("chat_template_kwargs", {}).get("enable_thinking")

    result = BenchmarkResult(
        prompt_name=prompt_name,
        category=prompt_config["category"],
        preset_name=preset_name,
        temperature=temperature,
        top_p=top_p,
        presence_penalty=presence_penalty,
        top_k=top_k,
        thinking=thinking,
    )

    body = {
        "model": model,
        "messages": prompt_config["messages"],
        "max_tokens": prompt_config.get("max_tokens", 2048),
        "temperature": temperature,
        "top_p": top_p,
        "presence_penalty": presence_penalty,
        "stream": False,
    }
    # Merge extra_body params at top level (vLLM expects top_k and
    # chat_template_kwargs at top level, not inside extra_body)
    body.update(extra_body)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        t_start = time.monotonic()
        resp = await client.post(f"{api_url}/chat/completions", json=body, headers=headers, timeout=120)
        t_end = time.monotonic()

        if resp.status_code != 200:
            result.success = False
            result.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return result

        data = resp.json()
        result.e2e_s = round(t_end - t_start, 3)

        usage = data.get("usage", {})
        result.prompt_tokens = usage.get("prompt_tokens", 0)
        result.completion_tokens = usage.get("completion_tokens", 0)
        if result.e2e_s > 0 and result.completion_tokens > 0:
            result.tokens_per_second = round(result.completion_tokens / result.e2e_s, 1)

        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content") or ""
            # Analyze repetition on the actual content (exclude thinking)
            metrics = analyze_repetition(content)
            result.ngram_4_rate = metrics.ngram_4_rate
            result.ngram_8_rate = metrics.ngram_8_rate
            result.type_token_ratio = metrics.type_token
            result.repeated_line_ratio = metrics.repeated_line_ratio
            result.word_count = metrics.word_count
            result.response_preview = content[:150].replace('\n', ' ')

    except Exception as e:
        result.success = False
        result.error = str(e)[:200]

    return result


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------

async def run_preset_benchmark(
    api_url: str, model: str, api_key: str,
    preset_name: str, prompts: Optional[list] = None,
) -> list[BenchmarkResult]:
    """Run all prompts with a specific preset."""
    params = PRESETS[preset_name]
    prompt_items = [(k, v) for k, v in PROMPTS.items()
                    if prompts is None or k in prompts]

    results = []
    async with httpx.AsyncClient() as client:
        for prompt_name, prompt_config in prompt_items:
            print(f"  [{preset_name}] {prompt_name}...", end=" ", flush=True)
            result = await run_single_test(
                client, api_url, model, api_key,
                prompt_name, prompt_config, params, preset_name,
            )
            if result.success:
                print(f"✓ {result.tokens_per_second} tok/s | "
                      f"4gram={result.ngram_4_rate:.3f} TTR={result.type_token_ratio:.3f} "
                      f"RepLines={result.repeated_line_ratio:.3f}")
            else:
                print(f"✗ {result.error}")
            results.append(result)
    return results


async def run_grid_search(
    api_url: str, model: str, api_key: str,
    prompts: Optional[list] = None,
) -> list[BenchmarkResult]:
    """Run full grid search over parameter space."""
    prompt_items = [(k, v) for k, v in PROMPTS.items()
                    if prompts is None or k in prompts]

    combos = list(product(GRID_TEMPERATURES, GRID_PRESENCE_PENALTIES, GRID_TOP_P))
    total = len(combos) * len(prompt_items)
    print(f"\nGrid search: {len(combos)} param combos × {len(prompt_items)} prompts = {total} tests")

    results = []
    done = 0
    async with httpx.AsyncClient() as client:
        for temp, pp, top_p in combos:
            params = {
                "temperature": temp,
                "top_p": top_p,
                "presence_penalty": pp,
                "extra_body": {},
            }
            preset_label = f"T{temp}_PP{pp}_P{top_p}"

            for prompt_name, prompt_config in prompt_items:
                done += 1
                print(f"  [{done}/{total}] {preset_label} | {prompt_name}...",
                      end=" ", flush=True)
                result = await run_single_test(
                    client, api_url, model, api_key,
                    prompt_name, prompt_config, params, preset_label,
                )
                if result.success:
                    print(f"✓ 4g={result.ngram_4_rate:.3f} TTR={result.type_token_ratio:.3f}")
                else:
                    print(f"✗ {result.error}")
                results.append(result)
    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results_csv(results: list[BenchmarkResult], output_path: str):
    """Save results to CSV."""
    fieldnames = [
        "prompt_name", "category", "preset_name",
        "temperature", "top_p", "presence_penalty", "top_k", "thinking",
        "tokens_per_second", "ttft_s", "e2e_s",
        "prompt_tokens", "completion_tokens",
        "ngram_4_rate", "ngram_8_rate", "type_token_ratio",
        "repeated_line_ratio", "word_count",
        "success", "error", "response_preview",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({fn: getattr(r, fn, "") for fn in fieldnames})
    print(f"\nResults saved to {output_path}")


def print_summary(results: list[BenchmarkResult]):
    """Print summary statistics grouped by preset."""
    from collections import defaultdict
    by_preset = defaultdict(list)
    for r in results:
        if r.success:
            by_preset[r.preset_name].append(r)

    print("\n" + "=" * 100)
    print(f"{'Preset':<25} {'Avg 4gram':>10} {'Avg 8gram':>10} {'Avg TTR':>10} "
          f"{'Avg RepLine':>12} {'Avg tok/s':>10} {'Avg Words':>10}")
    print("-" * 100)

    for preset, rs in sorted(by_preset.items()):
        n = len(rs)
        avg_4g = sum(r.ngram_4_rate for r in rs) / n
        avg_8g = sum(r.ngram_8_rate for r in rs) / n
        avg_ttr = sum(r.type_token_ratio for r in rs) / n
        avg_rep = sum(r.repeated_line_ratio for r in rs) / n
        avg_tps = sum(r.tokens_per_second for r in rs) / n
        avg_words = sum(r.word_count for r in rs) / n
        print(f"{preset:<25} {avg_4g:>10.4f} {avg_8g:>10.4f} {avg_ttr:>10.4f} "
              f"{avg_rep:>12.4f} {avg_tps:>10.1f} {avg_words:>10.0f}")

    print("=" * 100)
    print("\nLower 4gram/8gram/RepLine = less repetition. Higher TTR = more diverse.")
    print("Optimal: low repetition rates + high TTR + reasonable tok/s")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Benchmark repetition in LLM responses")
    parser.add_argument("--api-url", default=os.environ.get("VLLM_API_URL", "http://localhost:5002/v1"),
                        help="vLLM API base URL")
    parser.add_argument("--model", default="qwen3.6-35b-a3b", help="Model name")
    parser.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY_MEDIUM", ""),
                        help="API key")
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        help="Run single preset")
    parser.add_argument("--all-presets", action="store_true",
                        help="Run all presets")
    parser.add_argument("--grid-search", action="store_true",
                        help="Run full grid search (~60 param combos)")
    parser.add_argument("--prompts", nargs="+", choices=list(PROMPTS.keys()),
                        help="Specific prompts to test (default: all)")
    parser.add_argument("--output", default=None,
                        help="Output CSV path (auto-generated if not set)")
    args = parser.parse_args()

    if not args.api_key:
        print("WARNING: No API key set. Use --api-key or VLLM_API_KEY_MEDIUM env var.")

    results = []

    if args.grid_search:
        print("=== Grid Search Benchmark ===")
        results = asyncio.run(run_grid_search(
            args.api_url, args.model, args.api_key, args.prompts))
    elif args.all_presets:
        print("=== All Presets Benchmark ===")
        for preset_name in PRESETS:
            print(f"\n--- Preset: {preset_name} ---")
            r = asyncio.run(run_preset_benchmark(
                args.api_url, args.model, args.api_key, preset_name, args.prompts))
            results.extend(r)
    elif args.preset:
        print(f"=== Preset: {args.preset} ===")
        results = asyncio.run(run_preset_benchmark(
            args.api_url, args.model, args.api_key, args.preset, args.prompts))
    else:
        # Default: run baselines + Qwen recommended
        print("=== Baseline + Qwen Recommended Presets ===")
        for preset_name in ["baseline-low-temp", "baseline-roo-current",
                            "qwen-think-general", "qwen-instruct-general"]:
            print(f"\n--- Preset: {preset_name} ---")
            r = asyncio.run(run_preset_benchmark(
                args.api_url, args.model, args.api_key, preset_name, args.prompts))
            results.extend(r)

    if results:
        print_summary(results)
        output = args.output or f"benchmark_repetition_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        save_results_csv(results, output)


if __name__ == "__main__":
    main()

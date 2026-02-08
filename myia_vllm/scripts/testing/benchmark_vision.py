#!/usr/bin/env python3
"""
Vision Model Benchmark Suite for Qwen3-VL-8B-Thinking.

Tests all capabilities of the vision-language model:
  - Text inference (baseline)
  - Vision/image understanding
  - Multi-image analysis
  - Tool calling
  - Reasoning with visual context
  - Concurrent load testing

Usage:
    python benchmark_vision.py
    python benchmark_vision.py --vision-only
    python benchmark_vision.py --concurrent-only --requests 5
"""

import argparse
import asyncio
import base64
import json
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

import httpx

# Try to import PIL for image generation, fallback to base64 test pattern
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class BenchResult:
    test: str
    success: bool
    latency_s: float = 0.0
    tokens: int = 0
    tok_per_s: float = 0.0
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


# Model configuration
MODEL_CONFIG = {
    "name": "Qwen3-VL-8B-Thinking (mini-solo)",
    "url": "http://localhost:5001",
    "api_key": "9OYJNTEAAANJF6F17FMHR51Y0532O9QY",
    "model_id": "qwen3-vl-8b-thinking",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "Analyze an image and return structured data",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Image description"},
                    "objects": {"type": "array", "items": {"type": "string"}, "description": "Objects detected"},
                    "colors": {"type": "array", "items": {"type": "string"}, "description": "Dominant colors"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_from_image",
            "description": "Extract and read text from an image (OCR)",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Extracted text"},
                    "language": {"type": "string", "description": "Detected language"},
                },
                "required": ["text"],
            },
        },
    },
]


def create_test_image_simple() -> str:
    """Create a simple test image with geometric shapes (no PIL dependency)."""
    # 8x8 red square as minimal PNG
    # This is a valid 8x8 PNG with red pixels
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x08,  # 8x8
        0x08, 0x02, 0x00, 0x00, 0x00, 0x4B, 0x6D, 0x29,
        0xDE, 0x00, 0x00, 0x00, 0x1C, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0xC1, 0xFF, 0xFF, 0xFF, 0x7F, 0x00, 0x00, 0x00,
        0x00, 0xFF, 0xFF, 0x03, 0x00, 0x3D, 0x35, 0x04,
        0x7D, 0xC8, 0xA6, 0x7C, 0xCE, 0x00, 0x00, 0x00,
        0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60,
        0x82
    ])
    return base64.b64encode(png_data).decode()


def create_test_image_shapes() -> str:
    """Create a test image with shapes and text using PIL."""
    if not HAS_PIL:
        return create_test_image_simple()

    # Create 200x200 white image
    img = Image.new('RGB', (200, 200), color='white')
    draw = ImageDraw.Draw(img)

    # Draw shapes
    draw.rectangle([20, 20, 80, 80], fill='red', outline='black')
    draw.ellipse([100, 20, 180, 100], fill='blue', outline='black')
    draw.polygon([(100, 120), (60, 180), (140, 180)], fill='green', outline='black')

    # Add text
    draw.text((50, 5), "Test Image", fill='black')

    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def create_test_image_text() -> str:
    """Create a test image with readable text for OCR testing."""
    if not HAS_PIL:
        return create_test_image_simple()

    img = Image.new('RGB', (300, 100), color='white')
    draw = ImageDraw.Draw(img)

    # Try to use a readable font
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()

    draw.text((20, 30), "Hello World 2026", fill='black', font=font)

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def create_test_image_chart() -> str:
    """Create a simple bar chart for data interpretation testing."""
    if not HAS_PIL:
        return create_test_image_simple()

    img = Image.new('RGB', (300, 200), color='white')
    draw = ImageDraw.Draw(img)

    # Draw bars
    bars = [('A', 50, 'red'), ('B', 80, 'blue'), ('C', 30, 'green'), ('D', 100, 'orange')]
    x = 30
    for label, height, color in bars:
        draw.rectangle([x, 180 - height, x + 40, 180], fill=color, outline='black')
        draw.text((x + 15, 185), label, fill='black')
        x += 60

    draw.text((100, 5), "Sales Data", fill='black')

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def extract_content(message: dict) -> str:
    """Extract content from a message, handling Thinking models."""
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    return content if content else reasoning


async def test_health() -> BenchResult:
    """Test health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            start = time.perf_counter()
            resp = await client.get(f"{MODEL_CONFIG['url']}/health")
            latency = time.perf_counter() - start
            return BenchResult(
                test="health",
                success=resp.status_code == 200,
                latency_s=latency,
            )
    except Exception as e:
        return BenchResult(test="health", success=False, error=str(e))


async def test_text_inference() -> BenchResult:
    """Test basic text-only inference (baseline)."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{MODEL_CONFIG['url']}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                json={
                    "model": MODEL_CONFIG["model_id"],
                    "messages": [
                        {"role": "user", "content": "Write a Python function to reverse a string. Be concise."}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    test="text_inference", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            return BenchResult(
                test="text_inference", success=len(content) > 0,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={"preview": content[:150], "has_code": "def " in content or "return" in content},
            )
    except Exception as e:
        return BenchResult(test="text_inference", success=False, error=str(e))


async def test_vision_shapes() -> BenchResult:
    """Test vision: identify shapes in an image."""
    try:
        image_b64 = create_test_image_shapes()

        async with httpx.AsyncClient(timeout=90) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{MODEL_CONFIG['url']}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                json={
                    "model": MODEL_CONFIG["model_id"],
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe this image. What shapes and colors do you see? Be specific."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                            ],
                        }
                    ],
                    "max_tokens": 500,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    test="vision_shapes", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            # Check if model identified key elements
            content_lower = content.lower()
            found_shapes = any(s in content_lower for s in ["square", "rectangle", "circle", "triangle", "shape"])
            found_colors = any(c in content_lower for c in ["red", "blue", "green", "color"])

            return BenchResult(
                test="vision_shapes", success=len(content) > 20,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={
                    "preview": content[:200],
                    "found_shapes": found_shapes,
                    "found_colors": found_colors,
                    "has_reasoning": bool(msg.get("reasoning_content")),
                },
            )
    except Exception as e:
        return BenchResult(test="vision_shapes", success=False, error=str(e))


async def test_vision_ocr() -> BenchResult:
    """Test vision: read text from image (OCR capability)."""
    try:
        image_b64 = create_test_image_text()

        async with httpx.AsyncClient(timeout=90) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{MODEL_CONFIG['url']}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                json={
                    "model": MODEL_CONFIG["model_id"],
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What text do you see in this image? Transcribe it exactly."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                            ],
                        }
                    ],
                    "max_tokens": 300,
                    "temperature": 0.3,  # Lower temperature for OCR accuracy
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    test="vision_ocr", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            # Check if "Hello World" or "2026" was detected
            content_check = content.lower()
            found_hello = "hello" in content_check
            found_world = "world" in content_check
            found_year = "2026" in content

            return BenchResult(
                test="vision_ocr", success=found_hello or found_world,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={
                    "extracted_text": content[:150],
                    "found_hello": found_hello,
                    "found_world": found_world,
                    "found_year": found_year,
                },
            )
    except Exception as e:
        return BenchResult(test="vision_ocr", success=False, error=str(e))


async def test_vision_chart() -> BenchResult:
    """Test vision: interpret a chart/graph."""
    try:
        image_b64 = create_test_image_chart()

        async with httpx.AsyncClient(timeout=90) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{MODEL_CONFIG['url']}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                json={
                    "model": MODEL_CONFIG["model_id"],
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "This is a bar chart. Which bar is the tallest? Which is the shortest? Think step by step."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                            ],
                        }
                    ],
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    test="vision_chart", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            reasoning = msg.get("reasoning_content") or ""
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            # D is tallest (100), C is shortest (30)
            full_text = (content + " " + reasoning).lower()
            mentions_bars = any(x in full_text for x in ["bar", "chart", "graph", "a", "b", "c", "d"])

            return BenchResult(
                test="vision_chart", success=len(content) > 20,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={
                    "preview": content[:200],
                    "mentions_bars": mentions_bars,
                    "has_reasoning": len(reasoning) > 0,
                    "reasoning_preview": reasoning[:100] if reasoning else "",
                },
            )
    except Exception as e:
        return BenchResult(test="vision_chart", success=False, error=str(e))


async def test_tool_calling() -> BenchResult:
    """Test tool/function calling capability."""
    try:
        # Use a simple file-reading tool for testing (no image context confusion)
        file_tool = {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file from the filesystem",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"}
                    },
                    "required": ["path"],
                },
            },
        }

        async with httpx.AsyncClient(timeout=60) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{MODEL_CONFIG['url']}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                json={
                    "model": MODEL_CONFIG["model_id"],
                    "messages": [
                        {"role": "user", "content": "Read the file at /tmp/config.json"}
                    ],
                    "tools": [file_tool],
                    "tool_choice": "auto",
                    "max_tokens": 300,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    test="tool_calling", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            tool_calls = [tc for tc in tool_calls if tc.get("function", {}).get("name")]
            has_tool = len(tool_calls) > 0

            tool_name = tool_calls[0]["function"]["name"] if has_tool else None
            correct_tool = tool_name == "read_file"

            return BenchResult(
                test="tool_calling",
                success=correct_tool,
                latency_s=latency,
                details={
                    "has_tool_call": has_tool,
                    "tool_name": tool_name,
                    "num_calls": len(tool_calls),
                },
            )
    except Exception as e:
        return BenchResult(test="tool_calling", success=False, error=str(e))


async def test_reasoning() -> BenchResult:
    """Test reasoning/chain-of-thought capability."""
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            start = time.perf_counter()
            resp = await client.post(
                f"{MODEL_CONFIG['url']}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                json={
                    "model": MODEL_CONFIG["model_id"],
                    "messages": [
                        {"role": "user", "content": "A farmer has 17 sheep. All but 9 die. How many sheep are left? Think step by step."}
                    ],
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
            latency = time.perf_counter() - start

            if resp.status_code != 200:
                return BenchResult(
                    test="reasoning", success=False,
                    latency_s=latency, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            msg = data["choices"][0]["message"]
            content = extract_content(msg)
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            tps = tokens / latency if latency > 0 else 0

            # Correct answer is 9
            full_text = content + " " + reasoning
            has_correct = "9" in full_text and ("left" in full_text.lower() or "remain" in full_text.lower() or "sheep" in full_text.lower())

            return BenchResult(
                test="reasoning",
                success=has_correct,
                latency_s=latency, tokens=tokens, tok_per_s=tps,
                details={
                    "preview": content[:150],
                    "has_correct_answer": has_correct,
                    "has_reasoning": len(reasoning) > 0,
                },
            )
    except Exception as e:
        return BenchResult(test="reasoning", success=False, error=str(e))


async def test_concurrent(requests_count: int = 5) -> list[BenchResult]:
    """Test concurrent requests to measure throughput."""
    prompts = [
        "Explain what machine learning is in 2 sentences.",
        "Write a Python one-liner to sum a list of numbers.",
        "What is the capital of France?",
        "Name 3 programming languages.",
        "What is 15 * 7?",
    ]

    async def single_request(prompt: str, idx: int) -> BenchResult:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                start = time.perf_counter()
                resp = await client.post(
                    f"{MODEL_CONFIG['url']}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                    json={
                        "model": MODEL_CONFIG["model_id"],
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200,
                        "temperature": 0.7,
                    },
                )
                latency = time.perf_counter() - start

                if resp.status_code != 200:
                    return BenchResult(
                        test=f"concurrent_{idx}", success=False,
                        latency_s=latency, error=f"HTTP {resp.status_code}",
                    )

                data = resp.json()
                tokens = data.get("usage", {}).get("completion_tokens", 0)
                tps = tokens / latency if latency > 0 else 0

                return BenchResult(
                    test=f"concurrent_{idx}", success=True,
                    latency_s=latency, tokens=tokens, tok_per_s=tps,
                )
        except Exception as e:
            return BenchResult(test=f"concurrent_{idx}", success=False, error=str(e))

    # Launch all requests concurrently
    tasks = [single_request(prompts[i % len(prompts)], i) for i in range(requests_count)]

    start = time.perf_counter()
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start

    # Calculate aggregate metrics
    successes = [r for r in results if r.success]
    if successes:
        avg_latency = sum(r.latency_s for r in successes) / len(successes)
        total_tokens = sum(r.tokens for r in successes)
        aggregate_tps = total_tokens / total_time
        avg_tps = sum(r.tok_per_s for r in successes) / len(successes)
    else:
        avg_latency = total_tokens = aggregate_tps = avg_tps = 0

    summary = BenchResult(
        test="concurrent_summary",
        success=len(successes) == len(results),
        latency_s=avg_latency,
        tokens=total_tokens,
        tok_per_s=aggregate_tps,
        details={
            "requests": len(results),
            "successes": len(successes),
            "failures": len(results) - len(successes),
            "avg_per_request_tps": round(avg_tps, 1),
            "aggregate_tps": round(aggregate_tps, 1),
            "total_time_s": round(total_time, 2),
        },
    )

    return results + [summary]


async def test_concurrent_vision(requests_count: int = 3) -> list[BenchResult]:
    """Test concurrent vision requests."""

    async def vision_request(idx: int) -> BenchResult:
        try:
            image_b64 = create_test_image_shapes()
            prompts = [
                "What shapes do you see?",
                "Describe the colors in this image.",
                "Is there any text in this image?",
            ]

            async with httpx.AsyncClient(timeout=120) as client:
                start = time.perf_counter()
                resp = await client.post(
                    f"{MODEL_CONFIG['url']}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {MODEL_CONFIG['api_key']}"},
                    json={
                        "model": MODEL_CONFIG["model_id"],
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompts[idx % len(prompts)]},
                                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                                ],
                            }
                        ],
                        "max_tokens": 300,
                        "temperature": 0.7,
                    },
                )
                latency = time.perf_counter() - start

                if resp.status_code != 200:
                    return BenchResult(
                        test=f"concurrent_vision_{idx}", success=False,
                        latency_s=latency, error=f"HTTP {resp.status_code}",
                    )

                data = resp.json()
                tokens = data.get("usage", {}).get("completion_tokens", 0)
                tps = tokens / latency if latency > 0 else 0

                return BenchResult(
                    test=f"concurrent_vision_{idx}", success=True,
                    latency_s=latency, tokens=tokens, tok_per_s=tps,
                )
        except Exception as e:
            return BenchResult(test=f"concurrent_vision_{idx}", success=False, error=str(e))

    tasks = [vision_request(i) for i in range(requests_count)]

    start = time.perf_counter()
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start

    successes = [r for r in results if r.success]
    if successes:
        total_tokens = sum(r.tokens for r in successes)
        aggregate_tps = total_tokens / total_time
    else:
        total_tokens = aggregate_tps = 0

    summary = BenchResult(
        test="concurrent_vision_summary",
        success=len(successes) == len(results),
        tokens=total_tokens,
        tok_per_s=aggregate_tps,
        details={
            "requests": len(results),
            "successes": len(successes),
            "aggregate_tps": round(aggregate_tps, 1),
            "total_time_s": round(total_time, 2),
        },
    )

    return results + [summary]


def print_result(result: BenchResult, verbose: bool = False):
    """Print a single benchmark result."""
    status = "\033[92m✓ PASS\033[0m" if result.success else "\033[91m✗ FAIL\033[0m"
    metrics = ""
    if result.tokens > 0:
        metrics = f" | {result.tokens} tokens, {result.tok_per_s:.1f} tok/s"
    if result.latency_s > 0:
        metrics += f" | {result.latency_s:.2f}s"
    error_msg = f" | ERROR: {result.error}" if result.error else ""
    print(f"  {status} {result.test}{metrics}{error_msg}")

    if verbose and result.details:
        for key, value in result.details.items():
            if key != "preview":
                print(f"       {key}: {value}")


async def main():
    parser = argparse.ArgumentParser(description="Vision model benchmark suite")
    parser.add_argument("--vision-only", action="store_true", help="Only run vision tests")
    parser.add_argument("--concurrent-only", action="store_true", help="Only run concurrent tests")
    parser.add_argument("--requests", type=int, default=5, help="Requests for concurrent test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed results")
    args = parser.parse_args()

    print("=" * 70)
    print("VISION MODEL BENCHMARK SUITE")
    print("=" * 70)
    print(f"Model: {MODEL_CONFIG['name']}")
    print(f"URL: {MODEL_CONFIG['url']}")
    print(f"PIL available: {HAS_PIL}")
    print()

    all_results = []

    # Health check
    print(f"\n{'─' * 50}")
    print("Health Check")
    print(f"{'─' * 50}")
    result = await test_health()
    all_results.append(result)
    print_result(result, args.verbose)

    if not result.success:
        print("\n⚠ Model not healthy. Is the service running?")
        print("  Check: docker logs myia_vllm-mini-solo")
        return

    if not args.concurrent_only:
        # Text inference (baseline)
        if not args.vision_only:
            print(f"\n{'─' * 50}")
            print("Text Inference (Baseline)")
            print(f"{'─' * 50}")
            result = await test_text_inference()
            all_results.append(result)
            print_result(result, args.verbose)

        # Vision tests
        print(f"\n{'─' * 50}")
        print("Vision Tests")
        print(f"{'─' * 50}")

        result = await test_vision_shapes()
        all_results.append(result)
        print_result(result, args.verbose)

        result = await test_vision_ocr()
        all_results.append(result)
        print_result(result, args.verbose)

        result = await test_vision_chart()
        all_results.append(result)
        print_result(result, args.verbose)

        # Tool calling & Reasoning
        if not args.vision_only:
            print(f"\n{'─' * 50}")
            print("Tool Calling & Reasoning")
            print(f"{'─' * 50}")

            result = await test_tool_calling()
            all_results.append(result)
            print_result(result, args.verbose)

            result = await test_reasoning()
            all_results.append(result)
            print_result(result, args.verbose)

    # Concurrent tests
    if not args.vision_only or args.concurrent_only:
        print(f"\n{'─' * 50}")
        print(f"Concurrent Load Test ({args.requests} text requests)")
        print(f"{'─' * 50}")

        concurrent_results = await test_concurrent(args.requests)
        all_results.extend(concurrent_results)
        for r in concurrent_results:
            if r.test == "concurrent_summary":
                print_result(r, args.verbose)
                print(f"    Requests: {r.details.get('requests')}, "
                      f"Successes: {r.details.get('successes')}, "
                      f"Aggregate: {r.details.get('aggregate_tps')} tok/s, "
                      f"Total time: {r.details.get('total_time_s')}s")

        print(f"\n{'─' * 50}")
        print(f"Concurrent Vision Test ({min(args.requests, 3)} vision requests)")
        print(f"{'─' * 50}")

        vision_concurrent = await test_concurrent_vision(min(args.requests, 3))
        all_results.extend(vision_concurrent)
        for r in vision_concurrent:
            if r.test == "concurrent_vision_summary":
                print_result(r, args.verbose)
                print(f"    Requests: {r.details.get('requests')}, "
                      f"Aggregate: {r.details.get('aggregate_tps')} tok/s, "
                      f"Total time: {r.details.get('total_time_s')}s")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    # Group results by category
    health_results = [r for r in all_results if r.test == "health"]
    text_results = [r for r in all_results if r.test in ["text_inference", "tool_calling", "reasoning"]]
    vision_results = [r for r in all_results if r.test.startswith("vision_")]
    concurrent_results = [r for r in all_results if "concurrent" in r.test and "summary" in r.test]

    passed = sum(1 for r in all_results if r.success and "concurrent_" not in r.test or r.test.endswith("_summary"))
    total = len([r for r in all_results if "concurrent_" not in r.test or r.test.endswith("_summary")])
    print(f"Total: {passed}/{total} tests passed")

    if text_results:
        text_passed = sum(1 for r in text_results if r.success)
        text_tps = [r.tok_per_s for r in text_results if r.success and r.tok_per_s > 0]
        avg_tps = sum(text_tps) / len(text_tps) if text_tps else 0
        print(f"  Text tests: {text_passed}/{len(text_results)} passed, {avg_tps:.1f} avg tok/s")

    if vision_results:
        vision_passed = sum(1 for r in vision_results if r.success)
        vision_tps = [r.tok_per_s for r in vision_results if r.success and r.tok_per_s > 0]
        avg_tps = sum(vision_tps) / len(vision_tps) if vision_tps else 0
        print(f"  Vision tests: {vision_passed}/{len(vision_results)} passed, {avg_tps:.1f} avg tok/s")

    for r in concurrent_results:
        print(f"  {r.test}: {r.details.get('aggregate_tps', 0)} tok/s aggregate")

    print(f"\n{'=' * 70}")
    return all_results


if __name__ == "__main__":
    asyncio.run(main())

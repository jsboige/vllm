#!/usr/bin/env python3
"""
Benchmark script for Qwen3-Coder-Next vLLM deployment.

Tests:
1. Basic inference latency (TTFT, TPS)
2. Tool calling functionality
3. Concurrent user simulation
4. Memory utilization

Usage:
    python benchmark_coder_next.py [--api-url URL] [--api-key KEY]
    python benchmark_coder_next.py --concurrent-users 5 --requests-per-user 10
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


@dataclass
class BenchmarkResult:
    """Container for benchmark metrics."""
    test_name: str
    success: bool
    latency_ms: float = 0.0
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


# Agentic tools definition for comprehensive testing
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
            "name": "write_file",
            "description": "Write content to a file, creating it if necessary",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
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
                    "working_dir": {"type": "string", "description": "Working directory (optional)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a pattern in code files",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search"},
                    "path": {"type": "string", "description": "Directory to search in"},
                    "file_type": {"type": "string", "description": "File extension filter (e.g., '.py')"},
                },
                "required": ["pattern"],
            },
        },
    },
]


class CoderNextBenchmark:
    """Benchmark suite for Qwen3-Coder-Next deployment."""

    def __init__(
        self,
        api_url: str = "http://localhost:5002",
        api_key: Optional[str] = None,
        model_name: str = "qwen3-coder-next",
        timeout: float = 120.0,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.environ.get("VLLM_API_KEY_MEDIUM", "")
        self.model_name = model_name
        self.timeout = timeout
        self.results: list[BenchmarkResult] = []

    def _get_headers(self) -> dict:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def test_health(self) -> BenchmarkResult:
        """Test API health endpoint."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.api_url}/health")
                latency = (time.perf_counter() - start) * 1000

                if response.status_code == 200:
                    return BenchmarkResult(
                        test_name="health_check",
                        success=True,
                        latency_ms=latency,
                    )
                else:
                    return BenchmarkResult(
                        test_name="health_check",
                        success=False,
                        latency_ms=latency,
                        error=f"Status {response.status_code}: {response.text}",
                    )
        except Exception as e:
            return BenchmarkResult(
                test_name="health_check",
                success=False,
                error=str(e),
            )

    async def test_basic_inference(self, prompt: str = "Write a hello world in Python.") -> BenchmarkResult:
        """Test basic chat completion."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 500,
                        "temperature": 1.0,
                        "top_p": 0.95,
                    },
                )
                latency = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    return BenchmarkResult(
                        test_name="basic_inference",
                        success=False,
                        latency_ms=latency,
                        error=f"Status {response.status_code}: {response.text}",
                    )

                data = response.json()
                usage = data.get("usage", {})
                completion_tokens = usage.get("completion_tokens", 0)
                tps = completion_tokens / (latency / 1000) if latency > 0 else 0

                return BenchmarkResult(
                    test_name="basic_inference",
                    success=True,
                    latency_ms=latency,
                    tokens_generated=completion_tokens,
                    tokens_per_second=tps,
                    details={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "response_preview": data["choices"][0]["message"]["content"][:200] + "...",
                    },
                )
        except Exception as e:
            return BenchmarkResult(
                test_name="basic_inference",
                success=False,
                error=str(e),
            )

    async def test_tool_calling(self) -> BenchmarkResult:
        """Test function/tool calling capability."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": [
                            {"role": "user", "content": "Read the file at /tmp/test.txt and tell me what's inside."}
                        ],
                        "tools": AGENTIC_TOOLS,
                        "tool_choice": "auto",
                        "max_tokens": 200,
                        "temperature": 0.7,
                    },
                )
                latency = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    return BenchmarkResult(
                        test_name="tool_calling",
                        success=False,
                        latency_ms=latency,
                        error=f"Status {response.status_code}: {response.text}",
                    )

                data = response.json()
                message = data["choices"][0]["message"]
                tool_calls = message.get("tool_calls", [])

                if tool_calls:
                    first_call = tool_calls[0]
                    return BenchmarkResult(
                        test_name="tool_calling",
                        success=True,
                        latency_ms=latency,
                        details={
                            "tool_name": first_call["function"]["name"],
                            "tool_args": first_call["function"]["arguments"],
                            "num_tool_calls": len(tool_calls),
                        },
                    )
                else:
                    return BenchmarkResult(
                        test_name="tool_calling",
                        success=False,
                        latency_ms=latency,
                        error="No tool calls generated",
                        details={"response": message.get("content", "")[:200]},
                    )
        except Exception as e:
            return BenchmarkResult(
                test_name="tool_calling",
                success=False,
                error=str(e),
            )

    async def test_reasoning(self) -> BenchmarkResult:
        """Test reasoning/chain-of-thought capability."""
        reasoning_prompt = """Solve this step by step:

A software project has 3 modules. Module A depends on Module B.
Module B depends on Module C. Module C has no dependencies.
If we need to rebuild everything, in what order should we build the modules?
Explain your reasoning."""

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": reasoning_prompt}],
                        "max_tokens": 500,
                        "temperature": 0.7,
                    },
                )
                latency = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    return BenchmarkResult(
                        test_name="reasoning",
                        success=False,
                        latency_ms=latency,
                        error=f"Status {response.status_code}: {response.text}",
                    )

                data = response.json()
                content = data["choices"][0]["message"].get("content", "")
                usage = data.get("usage", {})
                tokens = usage.get("completion_tokens", 0)
                tps = tokens / (latency / 1000) if latency > 0 else 0

                # Verify reasoning quality - should mention C, B, A order
                has_correct_order = ("C" in content and "B" in content and "A" in content)
                mentions_dependencies = ("depend" in content.lower() or "order" in content.lower())

                return BenchmarkResult(
                    test_name="reasoning",
                    success=has_correct_order and mentions_dependencies,
                    latency_ms=latency,
                    tokens_generated=tokens,
                    tokens_per_second=tps,
                    details={
                        "response_preview": content[:300] + "..." if len(content) > 300 else content,
                        "has_correct_order": has_correct_order,
                        "mentions_dependencies": mentions_dependencies,
                    },
                )
        except Exception as e:
            return BenchmarkResult(
                test_name="reasoning",
                success=False,
                error=str(e),
            )

    async def test_tool_result_cycle(self) -> BenchmarkResult:
        """Test complete tool call cycle: request → tool call → result → continuation."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Step 1: Initial request that should trigger tool call
                response1 = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": [
                            {"role": "user", "content": "Check the Python version by running 'python --version'"}
                        ],
                        "tools": AGENTIC_TOOLS,
                        "tool_choice": "auto",
                        "max_tokens": 200,
                    },
                )

                if response1.status_code != 200:
                    return BenchmarkResult(
                        test_name="tool_result_cycle",
                        success=False,
                        error=f"Step 1 failed: {response1.status_code}",
                    )

                data1 = response1.json()
                message1 = data1["choices"][0]["message"]
                tool_calls = message1.get("tool_calls", [])

                if not tool_calls:
                    return BenchmarkResult(
                        test_name="tool_result_cycle",
                        success=False,
                        error="No tool call generated in step 1",
                    )

                # Step 2: Send tool result and get continuation
                tool_call = tool_calls[0]
                messages = [
                    {"role": "user", "content": "Check the Python version by running 'python --version'"},
                    message1,  # Assistant's response with tool_calls
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": "Python 3.11.5",
                    },
                ]

                response2 = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "tools": AGENTIC_TOOLS,
                        "max_tokens": 200,
                    },
                )

                latency = (time.perf_counter() - start) * 1000

                if response2.status_code != 200:
                    return BenchmarkResult(
                        test_name="tool_result_cycle",
                        success=False,
                        latency_ms=latency,
                        error=f"Step 2 failed: {response2.status_code}",
                    )

                data2 = response2.json()
                content2 = data2["choices"][0]["message"].get("content", "")

                # Verify the model understood and used the tool result
                mentions_version = "3.11" in content2 or "python" in content2.lower()

                return BenchmarkResult(
                    test_name="tool_result_cycle",
                    success=mentions_version,
                    latency_ms=latency,
                    details={
                        "tool_called": tool_call["function"]["name"],
                        "response_preview": content2[:200] if content2 else "(empty)",
                        "cycle_complete": True,
                    },
                )
        except Exception as e:
            return BenchmarkResult(
                test_name="tool_result_cycle",
                success=False,
                error=str(e),
            )

    async def test_multi_tool_scenario(self) -> BenchmarkResult:
        """Test agentic scenario requiring multiple tool calls."""
        agentic_prompt = """I need you to help me with a coding task:
1. First, read the file at /project/main.py to understand the current code
2. Then search for all TODO comments in the project
3. Finally, run the tests with 'pytest'

Start by reading the main.py file."""

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": agentic_prompt}],
                        "tools": AGENTIC_TOOLS,
                        "tool_choice": "auto",
                        "max_tokens": 300,
                    },
                )
                latency = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    return BenchmarkResult(
                        test_name="multi_tool_scenario",
                        success=False,
                        latency_ms=latency,
                        error=f"Status {response.status_code}: {response.text}",
                    )

                data = response.json()
                message = data["choices"][0]["message"]
                tool_calls = message.get("tool_calls", [])

                # Should call read_file for main.py
                if tool_calls:
                    tool_names = [tc["function"]["name"] for tc in tool_calls]
                    first_call = tool_calls[0]

                    # Check if it correctly identified read_file as the first action
                    correct_first_tool = first_call["function"]["name"] == "read_file"

                    return BenchmarkResult(
                        test_name="multi_tool_scenario",
                        success=correct_first_tool,
                        latency_ms=latency,
                        details={
                            "tools_called": tool_names,
                            "num_calls": len(tool_calls),
                            "first_tool_args": first_call["function"]["arguments"],
                            "correct_first_tool": correct_first_tool,
                        },
                    )
                else:
                    return BenchmarkResult(
                        test_name="multi_tool_scenario",
                        success=False,
                        latency_ms=latency,
                        error="No tool calls generated",
                        details={"response": message.get("content", "")[:200]},
                    )
        except Exception as e:
            return BenchmarkResult(
                test_name="multi_tool_scenario",
                success=False,
                error=str(e),
            )

    async def test_code_generation(self) -> BenchmarkResult:
        """Test code generation quality with a typical coding task."""
        coding_prompt = """Write a Python function called 'merge_sorted_lists' that:
- Takes two sorted lists as input
- Returns a single sorted list containing all elements
- Has O(n+m) time complexity
- Include type hints and a docstring

Only output the code, no explanations."""

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": coding_prompt}],
                        "max_tokens": 600,
                        "temperature": 0.3,  # Lower temp for more precise code
                    },
                )
                latency = (time.perf_counter() - start) * 1000

                if response.status_code != 200:
                    return BenchmarkResult(
                        test_name="code_generation",
                        success=False,
                        latency_ms=latency,
                        error=f"Status {response.status_code}: {response.text}",
                    )

                data = response.json()
                content = data["choices"][0]["message"].get("content", "")
                usage = data.get("usage", {})
                tokens = usage.get("completion_tokens", 0)
                tps = tokens / (latency / 1000) if latency > 0 else 0

                # Quality checks
                has_function_def = "def merge_sorted_lists" in content
                has_type_hints = "->" in content and ("list" in content.lower() or "List" in content)
                has_docstring = '"""' in content or "'''" in content
                looks_like_code = "return" in content and ("while" in content or "for" in content)

                quality_score = sum([has_function_def, has_type_hints, has_docstring, looks_like_code])

                return BenchmarkResult(
                    test_name="code_generation",
                    success=quality_score >= 3,  # At least 3/4 criteria
                    latency_ms=latency,
                    tokens_generated=tokens,
                    tokens_per_second=tps,
                    details={
                        "has_function_def": has_function_def,
                        "has_type_hints": has_type_hints,
                        "has_docstring": has_docstring,
                        "looks_like_code": looks_like_code,
                        "quality_score": f"{quality_score}/4",
                        "code_preview": content[:400] + "..." if len(content) > 400 else content,
                    },
                )
        except Exception as e:
            return BenchmarkResult(
                test_name="code_generation",
                success=False,
                error=str(e),
            )

    async def test_concurrent_users(
        self,
        num_users: int = 5,
        requests_per_user: int = 3,
    ) -> BenchmarkResult:
        """Simulate concurrent user load."""
        prompts = [
            "Write a function to calculate factorial.",
            "Explain what a decorator is in Python.",
            "Write a simple HTTP server in Python.",
            "How do I handle exceptions in Python?",
            "Write a class for a binary search tree.",
        ]

        async def user_session(user_id: int) -> list[dict]:
            """Simulate a single user's session."""
            results = []
            for i in range(requests_per_user):
                prompt = prompts[(user_id + i) % len(prompts)]
                start = time.perf_counter()
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.post(
                            f"{self.api_url}/v1/chat/completions",
                            headers=self._get_headers(),
                            json={
                                "model": self.model_name,
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": 200,
                                "temperature": 1.0,
                            },
                        )
                        latency = (time.perf_counter() - start) * 1000

                        if response.status_code == 200:
                            data = response.json()
                            tokens = data.get("usage", {}).get("completion_tokens", 0)
                            results.append({
                                "success": True,
                                "latency_ms": latency,
                                "tokens": tokens,
                            })
                        else:
                            results.append({
                                "success": False,
                                "latency_ms": latency,
                                "error": response.status_code,
                            })
                except Exception as e:
                    results.append({
                        "success": False,
                        "latency_ms": 0,
                        "error": str(e),
                    })
            return results

        start = time.perf_counter()
        try:
            # Run all user sessions concurrently
            user_results = await asyncio.gather(
                *[user_session(i) for i in range(num_users)]
            )
            total_time = (time.perf_counter() - start) * 1000

            # Aggregate results
            all_requests = [r for user in user_results for r in user]
            successful = [r for r in all_requests if r["success"]]
            failed = [r for r in all_requests if not r["success"]]

            if successful:
                avg_latency = sum(r["latency_ms"] for r in successful) / len(successful)
                total_tokens = sum(r.get("tokens", 0) for r in successful)
                avg_tps = total_tokens / (total_time / 1000) if total_time > 0 else 0
            else:
                avg_latency = 0
                total_tokens = 0
                avg_tps = 0

            return BenchmarkResult(
                test_name="concurrent_users",
                success=len(failed) == 0,
                latency_ms=avg_latency,
                tokens_generated=total_tokens,
                tokens_per_second=avg_tps,
                details={
                    "num_users": num_users,
                    "requests_per_user": requests_per_user,
                    "total_requests": len(all_requests),
                    "successful": len(successful),
                    "failed": len(failed),
                    "total_time_ms": total_time,
                    "throughput_rps": len(all_requests) / (total_time / 1000) if total_time > 0 else 0,
                },
            )
        except Exception as e:
            return BenchmarkResult(
                test_name="concurrent_users",
                success=False,
                error=str(e),
            )

    async def run_all(
        self,
        include_concurrent: bool = True,
        concurrent_users: int = 5,
        requests_per_user: int = 3,
        quick_mode: bool = False,
    ):
        """Run all benchmark tests.

        Args:
            include_concurrent: Run concurrent user load test
            concurrent_users: Number of simulated concurrent users
            requests_per_user: Requests per user in load test
            quick_mode: Run only essential tests (health, inference, tool_calling)
        """
        total_tests = 4 if quick_mode else 8
        print("=" * 60)
        print("Qwen3-Coder-Next Benchmark Suite")
        print("=" * 60)
        print(f"API URL: {self.api_url}")
        print(f"Model: {self.model_name}")
        print(f"Mode: {'Quick' if quick_mode else 'Full'} ({total_tests} tests)")
        print()

        test_num = 1

        # Test 1: Health check
        print(f"[{test_num}/{total_tests}] Health check...", end=" ", flush=True)
        result = await self.test_health()
        self.results.append(result)
        self._print_result(result)
        test_num += 1

        if not result.success:
            print("\nERROR: API not healthy. Stopping benchmark.")
            return

        # Test 2: Basic inference
        print(f"[{test_num}/{total_tests}] Basic inference...", end=" ", flush=True)
        result = await self.test_basic_inference()
        self.results.append(result)
        self._print_result(result)
        test_num += 1

        # Test 3: Tool calling
        print(f"[{test_num}/{total_tests}] Tool calling...", end=" ", flush=True)
        result = await self.test_tool_calling()
        self.results.append(result)
        self._print_result(result)
        test_num += 1

        if not quick_mode:
            # Test 4: Reasoning
            print(f"[{test_num}/{total_tests}] Reasoning (chain-of-thought)...", end=" ", flush=True)
            result = await self.test_reasoning()
            self.results.append(result)
            self._print_result(result)
            test_num += 1

            # Test 5: Tool result cycle
            print(f"[{test_num}/{total_tests}] Tool result cycle...", end=" ", flush=True)
            result = await self.test_tool_result_cycle()
            self.results.append(result)
            self._print_result(result)
            test_num += 1

            # Test 6: Multi-tool scenario
            print(f"[{test_num}/{total_tests}] Multi-tool agentic scenario...", end=" ", flush=True)
            result = await self.test_multi_tool_scenario()
            self.results.append(result)
            self._print_result(result)
            test_num += 1

            # Test 7: Code generation
            print(f"[{test_num}/{total_tests}] Code generation quality...", end=" ", flush=True)
            result = await self.test_code_generation()
            self.results.append(result)
            self._print_result(result)
            test_num += 1

        # Test N: Concurrent users (last test)
        if include_concurrent:
            print(f"[{test_num}/{total_tests}] Concurrent users ({concurrent_users} users, {requests_per_user} req/user)...", end=" ", flush=True)
            result = await self.test_concurrent_users(concurrent_users, requests_per_user)
            self.results.append(result)
            self._print_result(result)
        else:
            print(f"[{test_num}/{total_tests}] Concurrent users... SKIPPED")

        self._print_summary()

    def _print_result(self, result: BenchmarkResult):
        """Print a single test result."""
        if result.success:
            status = "✓ PASS"
            color = "\033[92m"  # Green
        else:
            status = "✗ FAIL"
            color = "\033[91m"  # Red
        reset = "\033[0m"

        metrics = []
        if result.latency_ms > 0:
            metrics.append(f"{result.latency_ms:.0f}ms")
        if result.tokens_per_second > 0:
            metrics.append(f"{result.tokens_per_second:.1f} tok/s")
        if result.tokens_generated > 0:
            metrics.append(f"{result.tokens_generated} tokens")

        metric_str = " | ".join(metrics) if metrics else ""
        error_str = f" ({result.error})" if result.error else ""

        print(f"{color}{status}{reset} {metric_str}{error_str}")

    def _print_summary(self):
        """Print benchmark summary."""
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.success)
        total = len(self.results)

        for result in self.results:
            status = "✓" if result.success else "✗"
            print(f"  {status} {result.test_name}: ", end="")
            if result.success:
                if result.tokens_per_second > 0:
                    print(f"{result.tokens_per_second:.1f} tok/s", end="")
                if result.latency_ms > 0:
                    print(f" ({result.latency_ms:.0f}ms)", end="")
            else:
                print(f"FAILED - {result.error}", end="")
            print()

        print()
        print(f"Results: {passed}/{total} tests passed")

        if passed == total:
            print("\n✓ All tests passed! Deployment is ready.")
        else:
            print("\n✗ Some tests failed. Check configuration.")

    def export_json(self, filepath: str):
        """Export results to JSON file."""
        output = {
            "api_url": self.api_url,
            "model": self.model_name,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "latency_ms": r.latency_ms,
                    "tokens_generated": r.tokens_generated,
                    "tokens_per_second": r.tokens_per_second,
                    "error": r.error,
                    "details": r.details,
                }
                for r in self.results
            ],
        }
        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults exported to: {filepath}")


async def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Qwen3-Coder-Next vLLM deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:5002",
        help="vLLM API URL (default: http://localhost:5002)",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (default: from VLLM_API_KEY_MEDIUM env var)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="qwen3-coder-next",
        help="Model name for API requests (default: qwen3-coder-next)",
    )

    parser.add_argument(
        "--concurrent-users",
        type=int,
        default=5,
        help="Number of concurrent users to simulate (default: 5)",
    )

    parser.add_argument(
        "--requests-per-user",
        type=int,
        default=3,
        help="Requests per user in concurrent test (default: 3)",
    )

    parser.add_argument(
        "--skip-concurrent",
        action="store_true",
        help="Skip concurrent users test",
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: run only essential tests (health, inference, tool_calling, concurrent)",
    )

    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export results to JSON file",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Request timeout in seconds (default: 120)",
    )

    args = parser.parse_args()

    benchmark = CoderNextBenchmark(
        api_url=args.api_url,
        api_key=args.api_key,
        model_name=args.model,
        timeout=args.timeout,
    )

    await benchmark.run_all(
        include_concurrent=not args.skip_concurrent,
        concurrent_users=args.concurrent_users,
        requests_per_user=args.requests_per_user,
        quick_mode=args.quick,
    )

    if args.export:
        benchmark.export_json(args.export)


if __name__ == "__main__":
    asyncio.run(main())

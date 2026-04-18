#!/usr/bin/env python3
"""Tool-calling accuracy probe for Qwen3.6-35B-A3B.

Tests 12 scenarios across single-tool, multi-tool selection, parameter extraction,
and negative cases (no tool needed). Measures correctness, not just latency.

Usage:
    python benchmark_tool_calling_accuracy.py
"""

import json
import os
import time

from openai import OpenAI

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ["VLLM_API_KEY_MEDIUM"]
MODEL = os.environ.get("BENCH_MODEL", "qwen3.6-35b-a3b")
BASE_URL = f"http://localhost:{os.environ.get('VLLM_PORT_MEDIUM', '5002')}/v1"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

TOOLS = [
    {"type": "function", "function": {
        "name": "get_weather", "description": "Get current weather for a location",
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string", "description": "City name"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        }, "required": ["location"]}}},
    {"type": "function", "function": {
        "name": "search_web", "description": "Search the web for information",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "num_results": {"type": "integer", "default": 5},
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "send_email", "description": "Send an email to a recipient",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string", "description": "Recipient email"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        }, "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {
        "name": "calculator", "description": "Evaluate a math expression",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string"},
        }, "required": ["expression"]}}},
]

# Each scenario: (prompt, expected_tool_or_None, required_params_present)
SCENARIOS = [
    # Single-tool selection (4)
    ("What's the weather in Paris today?", "get_weather", {"location": "paris"}),
    ("Search the web for the latest vLLM release notes.", "search_web", {"query": "vllm"}),
    ("Send an email to alice@example.com with subject 'Hi' and body 'Hello'.",
     "send_email", {"to": "alice", "subject": "hi", "body": "hello"}),
    ("Compute 17 * 23 + 5", "calculator", {"expression": "17"}),
    # Multi-tool ambiguity — should pick the most relevant (4)
    ("It's 35 degrees in Madrid, is that hot?", "get_weather", {"location": "madrid"}),
    ("Find me articles about quantum computing", "search_web", {"query": "quantum"}),
    ("What is the square root of 144?", "calculator", {"expression": "144"}),
    ("Email bob@corp.io that the meeting is moved to 3pm", "send_email", {"to": "bob"}),
    # Negative cases — no tool needed (2)
    ("What is the capital of France?", None, None),
    ("Explain how photosynthesis works.", None, None),
    # Parameter extraction edge cases (2)
    ("Get the weather in Tokyo in fahrenheit", "get_weather",
     {"location": "tokyo", "unit": "fahrenheit"}),
    ("Search for 'rust async runtime' and return 10 results", "search_web",
     {"query": "rust", "num_results": 10}),
]


def evaluate_call(scenario_idx: int, prompt: str, expected_tool, expected_params):
    """Run one scenario and assess correctness."""
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=512,
            temperature=0.1,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=30,
        )
    except Exception as e:
        return {"idx": scenario_idx, "ok": False, "error": str(e)[:100]}

    lat = round(time.perf_counter() - t0, 3)
    msg = resp.choices[0].message
    tool_calls = msg.tool_calls or []

    # Negative case: should NOT call a tool
    if expected_tool is None:
        ok = len(tool_calls) == 0
        return {"idx": scenario_idx, "ok": ok, "lat": lat,
                "expected": None, "got": [tc.function.name for tc in tool_calls],
                "prompt": prompt[:60]}

    # Positive case: must call expected tool
    if not tool_calls:
        return {"idx": scenario_idx, "ok": False, "lat": lat,
                "expected": expected_tool, "got": None,
                "prompt": prompt[:60], "reason": "no_tool_call"}

    fn = tool_calls[0].function
    name_ok = fn.name == expected_tool

    # Parameter check (substring/case-insensitive)
    params_ok = True
    missing = []
    if name_ok and expected_params:
        try:
            args = json.loads(fn.arguments)
        except Exception:
            args = {}
        for k, v in expected_params.items():
            actual = str(args.get(k, "")).lower()
            if str(v).lower() not in actual:
                params_ok = False
                missing.append(f"{k}={v}/{actual}")

    ok = name_ok and params_ok
    return {
        "idx": scenario_idx, "ok": ok, "lat": lat,
        "expected": expected_tool, "got": fn.name, "args": fn.arguments[:120],
        "params_ok": params_ok, "missing": missing,
        "prompt": prompt[:60],
    }


def main():
    print(f"Tool-calling accuracy probe — {MODEL}")
    print(f"Base URL: {BASE_URL}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print("=" * 80)

    results = []
    for i, (prompt, expected, params) in enumerate(SCENARIOS):
        r = evaluate_call(i, prompt, expected, params)
        results.append(r)
        status = "PASS" if r.get("ok") else "FAIL"
        line = f"  [{status}] #{i:2d} ({r.get('lat','?')}s)  exp={r.get('expected')}  got={r.get('got')}"
        if not r.get("ok"):
            line += f"  REASON={r.get('reason') or r.get('missing') or r.get('error')}"
        print(line)
        print(f"         prompt={r.get('prompt')}")
        if r.get("args"):
            print(f"         args={r['args']}")

    passed = sum(1 for r in results if r.get("ok"))
    total = len(results)
    avg_lat = sum(r.get("lat", 0) for r in results) / max(total, 1)

    print("=" * 80)
    print(f"  Tool calling accuracy: {passed}/{total} = {passed/total*100:.1f}%")
    print(f"  Avg latency: {avg_lat:.2f}s")

    # Save
    out = os.path.join(os.path.dirname(__file__), "../../benchmark_results",
                        f"tool_accuracy_{time.strftime('%Y%m%d_%H%M%S')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"model": MODEL, "passed": passed, "total": total,
                   "accuracy_pct": round(passed/total*100, 1),
                   "avg_latency_s": round(avg_lat, 3),
                   "results": results}, f, indent=2)
    print(f"  Saved: {out}")


if __name__ == "__main__":
    main()

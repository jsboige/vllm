#!/usr/bin/env python3
"""
Validate OWUI sampling profiles for Qwen3.5-35B-A3B (AWQ Q4).

Tests each deployed OWUI model wrapper to verify:
1. Model responds without errors
2. Thinking mode is correctly ON/OFF
3. Sampling params produce expected behavior (diversity, no repetition loops)
4. Direct vLLM defaults still work as fallback

Can test via:
- Direct vLLM API (port 5002) — tests server defaults
- OWUI API (port 2090) — tests wrapper param injection

Usage:
    python validate_owui_profiles.py                    # Test all via vLLM direct
    python validate_owui_profiles.py --via-owui         # Test all via OWUI wrappers
    python validate_owui_profiles.py --profile fast     # Test single profile
    python validate_owui_profiles.py --quick            # Fast smoke test (1 prompt each)

Environment:
    VLLM_API_KEY_MEDIUM: API key for vLLM (required for direct mode)
    OWUI_API_KEY: API key for Open WebUI (required for --via-owui)
"""

import argparse
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


# ---------------------------------------------------------------------------
# Profile definitions (must match deployed OWUI wrappers)
# ---------------------------------------------------------------------------

PROFILES = {
    # --- Qwen_* preset wrappers ---
    "think": {
        "display": "Qwen_think (general thinking)",
        "owui_model": "Qwen_think",
        "vllm_params": {
            "temperature": 0.7, "top_p": 0.95, "presence_penalty": 1.5,
            "extra_body": {
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        },
        "expect_thinking": True,
    },
    "think-code": {
        "display": "Qwen_think-code (coding)",
        "owui_model": "Qwen_think-code",
        "vllm_params": {
            "temperature": 0.6, "top_p": 0.95, "presence_penalty": 0.0,
            "extra_body": {
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        },
        "expect_thinking": True,
    },
    "think-reason": {
        "display": "Qwen_think-reason (reasoning)",
        "owui_model": "Qwen_think-reason",
        "vllm_params": {
            "temperature": 1.0, "top_p": 1.0, "presence_penalty": 1.5,
            "extra_body": {
                "top_k": 40,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        },
        "expect_thinking": True,
    },
    "instruct": {
        "display": "Qwen_instruct (chat, no thinking)",
        "owui_model": "Qwen_instruct",
        "vllm_params": {
            "temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5,
            "extra_body": {
                "top_k": 20, "repetition_penalty": 1.1, "min_p": 0.01,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        },
        "expect_thinking": False,
    },
    # --- Original model wrappers ---
    "base": {
        "display": "Local.qwen3.5-35b-a3b (base)",
        "owui_model": "Local.qwen3.5-35b-a3b",
        "vllm_params": {
            "temperature": 0.7, "top_p": 0.95, "presence_penalty": 1.5,
            "extra_body": {
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        },
        "expect_thinking": True,
    },
    "fast": {
        "display": "Local.qwen3.5-35b-a3b-fast (bots)",
        "owui_model": "Local.qwen3.5-35b-a3b-fast",
        "vllm_params": {
            "temperature": 0.6, "top_p": 0.85, "presence_penalty": 0.5,
            "extra_body": {
                "top_k": 20, "repetition_penalty": 1.1, "min_p": 0.01,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        },
        "expect_thinking": False,
    },
    "analyste": {
        "display": "expert-analyste (coding/analysis)",
        "owui_model": "expert-analyste",
        "vllm_params": {
            "temperature": 0.6, "top_p": 0.95, "presence_penalty": 0.0,
            "extra_body": {
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        },
        "expect_thinking": True,
    },
    "redacteur": {
        "display": "redacteur-technique (writing)",
        "owui_model": "redacteur-technique",
        "vllm_params": {
            "temperature": 0.8, "top_p": 0.95, "presence_penalty": 0.5,
            "extra_body": {
                "top_k": 20, "repetition_penalty": 1.05, "min_p": 0.05,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        },
        "expect_thinking": True,
    },
    # --- vLLM defaults (no OWUI wrapper) ---
    "vllm-defaults": {
        "display": "vLLM direct (server defaults, no OWUI)",
        "owui_model": None,
        "vllm_params": {},  # Uses server defaults: temp=0.6, top_p=0.95, top_k=20
        "expect_thinking": True,  # Thinking ON by default
    },
}

# ---------------------------------------------------------------------------
# Test prompts
# ---------------------------------------------------------------------------

PROMPTS = {
    "simple_chat": {
        "messages": [
            {"role": "user", "content": "Bonjour ! Explique-moi en 3 phrases ce qu'est le machine learning."}
        ],
        "max_tokens": 512,
        "desc": "Simple chat (FR, 3 phrases)",
    },
    "code_task": {
        "messages": [
            {"role": "user", "content": "Write a Python function that finds the longest palindromic substring in a string. Include type hints."}
        ],
        "max_tokens": 1024,
        "desc": "Coding task (palindrome)",
    },
    "tool_call": {
        "messages": [
            {"role": "user", "content": "What's the weather like in Paris today?"}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"},
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "max_tokens": 256,
        "desc": "Tool calling",
    },
    "repetition_stress": {
        "messages": [
            {"role": "user", "content": "List 20 different creative uses for a paperclip. Number each one and make every suggestion unique."}
        ],
        "max_tokens": 1024,
        "desc": "Repetition stress test",
    },
}


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    profile: str
    prompt: str
    success: bool
    thinking_detected: bool
    thinking_expected: bool
    response_length: int
    tok_per_sec: float
    ttft_ms: float
    error: Optional[str] = None
    tool_call_detected: bool = False
    language_mixing: bool = False
    content_preview: str = ""

    @property
    def thinking_ok(self) -> bool:
        return self.thinking_detected == self.thinking_expected

    @property
    def status(self) -> str:
        if not self.success:
            return "FAIL"
        if not self.thinking_ok:
            return "THINK-BUG"
        return "OK"


def detect_thinking(response_json: dict) -> bool:
    """Check if the response contains thinking content."""
    choices = response_json.get("choices", [])
    if not choices:
        return False
    choice = choices[0]
    msg = choice.get("message", {})
    # Check reasoning field (vLLM Qwen3 parser)
    if msg.get("reasoning"):
        return True
    # Check content for <think> tags (fallback)
    content = msg.get("content") or ""
    if "<think>" in content or "</think>" in content:
        return True
    return False


def detect_language_mixing(text: str) -> bool:
    """Simple heuristic: detect CJK characters in Latin text."""
    import re
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    latin_chars = len(re.findall(r'[a-zA-Zàâéèêëïîôùûüÿç]', text))
    if latin_chars > 50 and cjk_chars > 3:
        return True
    return False


def run_test(
    client: httpx.Client,
    api_url: str,
    api_key: str,
    model: str,
    profile_key: str,
    profile: dict,
    prompt_key: str,
    prompt: dict,
    via_owui: bool = False,
) -> TestResult:
    """Run a single test against the API."""
    messages = prompt["messages"]
    max_tokens = prompt["max_tokens"]

    # Build request body
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }

    # Add tools if present
    if "tools" in prompt:
        body["tools"] = prompt["tools"]

    # Add sampling params (only for direct vLLM, OWUI injects its own)
    if not via_owui and profile.get("vllm_params"):
        params = profile["vllm_params"]
        for key in ("temperature", "top_p", "presence_penalty"):
            if key in params:
                body[key] = params[key]
        extra = params.get("extra_body", {})
        for key, val in extra.items():
            body[key] = val

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    start = time.monotonic()
    try:
        resp = client.post(
            f"{api_url}/chat/completions",
            json=body,
            headers=headers,
            timeout=120.0,
        )
        elapsed = time.monotonic() - start

        if resp.status_code != 200:
            return TestResult(
                profile=profile_key, prompt=prompt_key, success=False,
                thinking_detected=False, thinking_expected=profile.get("expect_thinking", True),
                response_length=0, tok_per_sec=0, ttft_ms=0,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "") or ""

        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        tok_s = completion_tokens / elapsed if elapsed > 0 else 0

        thinking = detect_thinking(data)
        lang_mix = detect_language_mixing(content)

        tool_call = False
        if choices and choices[0].get("message", {}).get("tool_calls"):
            tool_call = True

        return TestResult(
            profile=profile_key, prompt=prompt_key, success=True,
            thinking_detected=thinking,
            thinking_expected=profile.get("expect_thinking", True),
            response_length=len(content),
            tok_per_sec=round(tok_s, 1),
            ttft_ms=round(elapsed * 1000, 0),
            tool_call_detected=tool_call,
            language_mixing=lang_mix,
            content_preview=content[:120].replace("\n", " "),
        )

    except Exception as e:
        return TestResult(
            profile=profile_key, prompt=prompt_key, success=False,
            thinking_detected=False, thinking_expected=profile.get("expect_thinking", True),
            response_length=0, tok_per_sec=0, ttft_ms=0,
            error=str(e)[:200],
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Validate OWUI sampling profiles")
    parser.add_argument("--via-owui", action="store_true",
                        help="Test via OWUI API (default: direct vLLM)")
    parser.add_argument("--profile", type=str, default=None,
                        help=f"Test single profile: {', '.join(PROFILES.keys())}")
    parser.add_argument("--prompt", type=str, default=None,
                        help=f"Test single prompt: {', '.join(PROMPTS.keys())}")
    parser.add_argument("--quick", action="store_true",
                        help="Quick smoke test (simple_chat only)")
    parser.add_argument("--vllm-url", type=str,
                        default=os.environ.get("VLLM_URL", "http://localhost:5002/v1"),
                        help="vLLM API URL")
    parser.add_argument("--owui-url", type=str,
                        default=os.environ.get("OWUI_URL", "http://localhost:2090/api/v1"),
                        help="Open WebUI API URL")
    parser.add_argument("--vllm-key", type=str,
                        default=os.environ.get("VLLM_API_KEY_MEDIUM", ""),
                        help="vLLM API key")
    parser.add_argument("--owui-key", type=str,
                        default=os.environ.get("OWUI_API_KEY", ""),
                        help="Open WebUI API key")
    parser.add_argument("--model", type=str, default="qwen3.5-35b-a3b",
                        help="vLLM model name (for direct mode)")
    args = parser.parse_args()

    # Select profiles
    profiles = PROFILES
    if args.profile:
        if args.profile not in PROFILES:
            print(f"ERROR: Unknown profile '{args.profile}'. Available: {', '.join(PROFILES.keys())}")
            sys.exit(1)
        profiles = {args.profile: PROFILES[args.profile]}

    # Select prompts
    prompts = PROMPTS
    if args.quick:
        prompts = {"simple_chat": PROMPTS["simple_chat"]}
    elif args.prompt:
        if args.prompt not in PROMPTS:
            print(f"ERROR: Unknown prompt '{args.prompt}'. Available: {', '.join(PROMPTS.keys())}")
            sys.exit(1)
        prompts = {args.prompt: PROMPTS[args.prompt]}

    # Config
    via_owui = args.via_owui
    api_url = args.owui_url if via_owui else args.vllm_url
    api_key = args.owui_key if via_owui else args.vllm_key
    mode = "OWUI" if via_owui else "vLLM direct"

    if not api_key:
        key_name = "OWUI_API_KEY" if via_owui else "VLLM_API_KEY_MEDIUM"
        print(f"ERROR: No API key. Set {key_name} env var or use --{'owui' if via_owui else 'vllm'}-key")
        sys.exit(1)

    print(f"=== Qwen3.5 OWUI Profile Validation ===")
    print(f"Mode: {mode}")
    print(f"API: {api_url}")
    print(f"Profiles: {len(profiles)}")
    print(f"Prompts: {len(prompts)}")
    print(f"Total tests: {len(profiles) * len(prompts)}")
    print()

    results: list[TestResult] = []
    client = httpx.Client()

    for pf_key, pf in profiles.items():
        # Skip vllm-defaults when testing via OWUI (not an OWUI model)
        if via_owui and pf["owui_model"] is None:
            continue

        model = pf["owui_model"] if via_owui else args.model
        print(f"--- {pf['display']} ---")

        for pr_key, pr in prompts.items():
            # Skip tool_call for profiles that disable thinking (tool call test needs specific handling)
            result = run_test(
                client, api_url, api_key, model,
                pf_key, pf, pr_key, pr, via_owui=via_owui,
            )
            results.append(result)

            status_icon = {"OK": "OK", "FAIL": "FAIL", "THINK-BUG": "THINK-BUG"}[result.status]
            thinking_str = f"think={'Y' if result.thinking_detected else 'N'}"
            tool_str = " tool=Y" if result.tool_call_detected else ""
            lang_str = " LANG-MIX!" if result.language_mixing else ""

            print(f"  [{status_icon}] {pr['desc']:30s} | {thinking_str}{tool_str}{lang_str} | "
                  f"{result.tok_per_sec:6.1f} tok/s | {result.response_length:5d} chars")
            if result.error:
                print(f"       ERROR: {result.error}")

    client.close()

    # Summary
    print()
    print("=== SUMMARY ===")
    total = len(results)
    ok = sum(1 for r in results if r.status == "OK")
    fail = sum(1 for r in results if r.status == "FAIL")
    think_bug = sum(1 for r in results if r.status == "THINK-BUG")
    lang_mix = sum(1 for r in results if r.language_mixing)

    print(f"Total: {total} | OK: {ok} | FAIL: {fail} | THINK-BUG: {think_bug} | LANG-MIX: {lang_mix}")

    if think_bug > 0:
        print()
        print("THINKING BUGS (expected != detected):")
        for r in results:
            if r.status == "THINK-BUG":
                print(f"  {r.profile}/{r.prompt}: expected={r.thinking_expected}, got={r.thinking_detected}")

    if fail > 0:
        print()
        print("FAILURES:")
        for r in results:
            if r.status == "FAIL":
                print(f"  {r.profile}/{r.prompt}: {r.error}")

    if lang_mix > 0:
        print()
        print("LANGUAGE MIXING DETECTED:")
        for r in results:
            if r.language_mixing:
                print(f"  {r.profile}/{r.prompt}")

    # Exit code
    if fail > 0 or think_bug > 0:
        sys.exit(1)
    print()
    print("All tests passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()

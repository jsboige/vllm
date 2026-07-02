# Ornith-1.0-35B Genesis-TQ smoke tests (S3 gate) — run against localhost:5002
# Usage: python smoke_test.py [--base-url http://localhost:5002/v1]
# Reads VLLM_API_KEY_MEDIUM from myia_vllm/.env. Prints PASS/FAIL per gate.
import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # myia_vllm/


def load_key():
    env_path = os.path.join(ROOT, ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("VLLM_API_KEY_MEDIUM="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("VLLM_API_KEY_MEDIUM not found in .env")


def post(base, key, path, payload, timeout=300):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r), time.time() - t0


def get(base, key, path):
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def red_png_b64():
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (256, 256), (220, 30, 30)).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return None


results = []


def gate(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:5002/v1")
    ap.add_argument("--model", default="qwen3.6-35b-a3b", help="alias by default = the client path")
    args = ap.parse_args()
    base, key = args.base_url, load_key()

    # 1. both served names present
    models = [m["id"] for m in get(base, key, "/models")["data"]]
    gate("models: ornith-1.0-35b + alias qwen3.6-35b-a3b",
         "ornith-1.0-35b" in models and "qwen3.6-35b-a3b" in models, str(models))

    # 2. simple completion, no thinking
    r, dt = post(base, key, "/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 512, "chat_template_kwargs": {"enable_thinking": False}})
    msg = r["choices"][0]["message"]
    gate("simple completion (thinking off)", "OK" in (msg.get("content") or ""),
         f"{dt:.1f}s content={((msg.get('content') or '')[:60])!r}")

    # 3. thinking on -> reasoning field populated
    r, dt = post(base, key, "/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "What is 17*23? Answer with the number."}],
        "max_tokens": 2048})
    msg = r["choices"][0]["message"]
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    gate("thinking: reasoning field + correct answer",
         len(reasoning) > 20 and "391" in (msg.get("content") or ""),
         f"{dt:.1f}s reasoning_len={len(reasoning)} content={((msg.get('content') or '')[:40])!r}")

    # 4. tool calling (qwen3_coder XML parse)
    r, dt = post(base, key, "/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "Quelle est la meteo a Paris ?"}],
        "tools": [{"type": "function", "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                           "required": ["city"]}}}],
        "max_tokens": 2048})
    tc = r["choices"][0]["message"].get("tool_calls") or []
    ok = bool(tc) and tc[0]["function"]["name"] == "get_weather" and \
        "paris" in tc[0]["function"]["arguments"].lower()
    gate("tool call parsed (qwen3_coder)", ok, f"{dt:.1f}s tool_calls={tc[:1]}")

    # 5. vision
    img = red_png_b64()
    if img:
        r, dt = post(base, key, "/chat/completions", {
            "model": args.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
                {"type": "text", "text": "What single dominant color is this image? One word."}]}],
            "max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}})
        content = (r["choices"][0]["message"].get("content") or "").lower()
        gate("vision: red square identified", "red" in content or "rouge" in content,
             f"{dt:.1f}s content={content[:60]!r}")
    else:
        gate("vision", False, "SKIPPED — PIL not installed")

    # 6. CRASH TEST: ~30K-token prompt -> chunked continuation prefill (the 2026-05-06 TQ killer)
    lines = [f"Line {i}: the quick brown fox jumps over the lazy dog number {i*7%1000}." for i in range(2600)]
    lines[1600] = "Line 1600: THE SECRET CODE IS BLUE-7742."
    long_prompt = "\n".join(lines) + "\n\nWhat is the secret code mentioned in the text above? Answer with the code only."
    r, dt = post(base, key, "/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": long_prompt}],
        "max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}, timeout=600)
    content = r["choices"][0]["message"].get("content") or ""
    ptok = r.get("usage", {}).get("prompt_tokens", 0)
    gate(f"30K continuation-prefill + needle ({ptok} prompt tokens)",
         "BLUE-7742" in content and ptok > 25000, f"{dt:.1f}s content={content[:50]!r}")

    # 7. decode speed (single user, thinking off)
    r, dt = post(base, key, "/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "Write a 300-word essay about GPUs."}],
        "max_tokens": 400, "chat_template_kwargs": {"enable_thinking": False}})
    ctok = r.get("usage", {}).get("completion_tokens", 0)
    tps = ctok / dt if dt else 0
    gate("decode speed (informational)", tps > 60, f"{ctok} tok in {dt:.1f}s = {tps:.1f} tok/s (v2g baseline ~120)")

    print("\n" + ("ALL GATES PASSED" if all(ok for _, ok, _ in results) else "SOME GATES FAILED"))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)


if __name__ == "__main__":
    main()

"""Quick test: streaming thinking on Qwen3.6 with reasoning parser."""
import os, sys, requests, json

# Load env
env = {}
with open("d:/vllm/myia_vllm/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")

API_KEY = env.get("VLLM_API_KEY_MEDIUM", "")
PORT = env.get("VLLM_PORT_GLM", "5002")

url = f"http://localhost:{PORT}/v1/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

# Test 1: Streaming with thinking enabled (default)
print("=" * 60)
print("TEST 1: Streaming, thinking ENABLED (default)")
print("=" * 60)
data = {
    "model": "qwen3.6-35b-a3b",
    "messages": [{"role": "user", "content": "What is 15 + 27?"}],
    "max_tokens": 300,
    "temperature": 0.7,
    "stream": True,
}

resp = requests.post(url, json=data, headers=headers, stream=True)
reasoning_chunks = []
content_chunks = []
for line in resp.iter_lines():
    line = line.decode()
    if line.startswith("data: ") and line != "data: [DONE]":
        chunk = json.loads(line[6:])
        delta = chunk["choices"][0]["delta"]
        if delta.get("reasoning"):
            reasoning_chunks.append(delta["reasoning"])
        if delta.get("reasoning_content"):
            reasoning_chunks.append("[RC]" + delta["reasoning_content"])
        if delta.get("content"):
            content_chunks.append(delta["content"])

reasoning_text = "".join(reasoning_chunks)
content_text = "".join(content_chunks)
print(f"REASONING ({len(reasoning_chunks)} chunks, {len(reasoning_text)} chars):")
print(reasoning_text[:500] if reasoning_text else "(empty)")
print(f"\nCONTENT ({len(content_chunks)} chunks, {len(content_text)} chars):")
print(content_text[:500] if content_text else "(empty)")

# Test 2: Streaming with thinking disabled
print("\n" + "=" * 60)
print("TEST 2: Streaming, thinking DISABLED")
print("=" * 60)
data2 = {
    "model": "qwen3.6-35b-a3b",
    "messages": [{"role": "user", "content": "What is 15 + 27?"}],
    "max_tokens": 100,
    "temperature": 0.7,
    "stream": True,
    "chat_template_kwargs": {"enable_thinking": False},
}

resp2 = requests.post(url, json=data2, headers=headers, stream=True)
reasoning2 = []
content2 = []
for line in resp2.iter_lines():
    line = line.decode()
    if line.startswith("data: ") and line != "data: [DONE]":
        chunk = json.loads(line[6:])
        delta = chunk["choices"][0]["delta"]
        if delta.get("reasoning"):
            reasoning2.append(delta["reasoning"])
        if delta.get("content"):
            content2.append(delta["content"])

r2_text = "".join(reasoning2)
c2_text = "".join(content2)
print(f"REASONING ({len(reasoning2)} chunks): {r2_text[:200] if r2_text else '(empty)'}")
print(f"CONTENT ({len(content2)} chunks): {c2_text[:200] if c2_text else '(empty)'}")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Thinking enabled  → reasoning: {'YES' if reasoning_text else 'NO'}, content: {'YES' if content_text else 'NO'}")
print(f"Thinking disabled → reasoning: {'YES' if r2_text else 'NO'}, content: {'YES' if c2_text else 'NO'}")

"""v2f vision smoke: send 1 image + question, verify the model reads it."""
import base64
import json
import time
import urllib.request

API = "http://localhost:5002/v1/chat/completions"
KEY = None
for line in open("d:/vllm/myia_vllm/.env"):
    if line.startswith("VLLM_API_KEY_MEDIUM="):
        KEY = line.split("=", 1)[1].strip()

# Generate a 64x64 solid red PNG in-process (PIL guaranteed to produce valid bytes).
import io
from PIL import Image
img = Image.new("RGB", (64, 64), (220, 20, 20))
buf = io.BytesIO()
img.save(buf, format="PNG")
RED_PNG_B64 = base64.b64encode(buf.getvalue()).decode("ascii")
data_url = f"data:image/png;base64,{RED_PNG_B64}"

body = {
    "model": "qwen3.6-35b-a3b",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What single color dominates this image? Answer in one word."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ],
    "max_tokens": 32,
    "temperature": 0,
    "chat_template_kwargs": {"enable_thinking": False},
}

req = urllib.request.Request(
    API,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
)

t0 = time.monotonic()
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    dt = time.monotonic() - t0
    content = (out["choices"][0]["message"].get("content") or "").strip()
    print(f"HTTP 200 in {dt:.2f}s")
    print(f"prompt_tokens: {out['usage']['prompt_tokens']}")
    print(f"completion_tokens: {out['usage']['completion_tokens']}")
    print(f"finish_reason: {out['choices'][0]['finish_reason']}")
    print(f"answer: {content!r}")
    if "red" in content.lower() or "rouge" in content.lower():
        print("=== VISION SMOKE: PASS ===")
    else:
        print("=== VISION SMOKE: SUSPECT (answer doesn't mention red) ===")
except Exception as e:
    dt = time.monotonic() - t0
    print(f"FAILED after {dt:.2f}s: {type(e).__name__}: {e}")
    print("=== VISION SMOKE: FAIL ===")
    raise

"""
Sidecar proxy to log embedding requests and forward to vLLM.

Listens on LISTEN_PORT (default 8004), forwards to TARGET_PORT (default 8005).
Logs POST /v1/embeddings request bodies to embedding_requests.jsonl.

Usage:
    python scripts/embedding-proxy-logger.py
    LISTEN_PORT=8004 TARGET_PORT=8005 MAX_LOG=200 python scripts/embedding-proxy-logger.py
"""

import asyncio
import hashlib
import json
import os
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from aiohttp import web, ClientSession, ClientTimeout

LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8004"))
TARGET = os.environ.get("TARGET_URL") or f"http://localhost:{os.environ.get('TARGET_PORT', '8005')}"
MAX_LOG = int(os.environ.get("MAX_LOG", "200"))
LOG_FILE = Path("embedding_requests.jsonl")
TARGET_TIMEOUT = ClientTimeout(total=120)


class RequestTracker:
    def __init__(self):
        self.count = 0
        self.logged = 0

    def should_log(self):
        return self.logged < MAX_LOG


tracker = RequestTracker()
session: ClientSession = None


async def handle(request: web.Request):
    path = request.path
    method = request.method

    # Forward all requests to vLLM
    target_url = f"{TARGET}{path}"
    headers = dict(request.headers)
    headers.pop("Host", None)

    body = await request.read()

    # Log embedding requests
    if method == "POST" and "/v1/embeddings" in path and tracker.should_log():
        tracker.logged += 1
        try:
            payload = json.loads(body)
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "seq": tracker.logged,
                "size_bytes": len(body),
                "model": payload.get("model", ""),
                "input_count": 0,
                "input_preview": None,
                "input_lengths": [],
            }

            inp = payload.get("input", "")
            if isinstance(inp, list):
                entry["input_count"] = len(inp)
                entry["input_lengths"] = [len(str(s)) for s in inp[:20]]
                entry["input_preview"] = [
                    str(s)[:300] for s in inp[:3]
                ]
                entry["input_hashes"] = [
                    hashlib.sha256(str(s).encode("utf-8", "replace")).hexdigest()[:16]
                    for s in inp[:64]
                ]
            elif isinstance(inp, str):
                entry["input_count"] = 1
                entry["input_lengths"] = [len(inp)]
                entry["input_preview"] = inp[:300]
                entry["input_hashes"] = [
                    hashlib.sha256(inp.encode("utf-8", "replace")).hexdigest()[:16]
                ]

            extra_keys = [k for k in payload if k not in ("input", "model")]
            if extra_keys:
                entry["extra_params"] = {k: payload[k] for k in extra_keys}

            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            print(
                f"[{tracker.logged}/{MAX_LOG}] {entry['input_count']} input(s), "
                f"model={entry['model']}, sizes={entry['input_lengths'][:5]}, "
                f"total={len(body)} bytes"
            )
        except Exception as e:
            print(f"[LOG ERROR] {e}")

    tracker.count += 1

    # Forward to vLLM
    async with session.request(
        method, target_url, headers=headers, data=body, timeout=TARGET_TIMEOUT
    ) as resp:
        response_headers = dict(resp.headers)
        response_headers.pop("Transfer-Encoding", None)
        response_body = await resp.read()
        return web.Response(
            status=resp.status,
            headers=response_headers,
            body=response_body,
        )


async def stats(request: web.Request):
    return web.json_response({
        "total_requests": tracker.count,
        "logged": tracker.logged,
        "max_log": MAX_LOG,
        "target": TARGET,
    })


async def on_startup(app):
    global session
    session = ClientSession()
    print(f"Proxy started: :{LISTEN_PORT} -> {TARGET}")
    print(f"Logging up to {MAX_LOG} embedding requests to {LOG_FILE}")
    if LOG_FILE.exists():
        LOG_FILE.unlink()
        print(f"Cleared previous {LOG_FILE}")


async def on_cleanup(app):
    if session:
        await session.close()


app = web.Application()
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)
app.router.add_route("*", "/{path:.*}", handle)
app.router.add_get("/_proxy_stats", stats)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=LISTEN_PORT, print=None)

"""Minimal ASGI middleware: dump raw /v1/chat/completions request bodies.

DIAGNOSTIC ONLY — created 2026-05-14 to investigate why claudish/Claude Code
gets poor prefix-cache hits (slow TTFT on turns 2-3). Captures each request
body verbatim so consecutive turns can be diffed to find where the prompt
prefix diverges (timestamps, system-reminders, reordered tools, etc.).

Far lighter than logging_middleware.RequestResponseLogger: no response
parsing, no streaming buffering — one async file write per request.

Usage (add to docker profile command, PYTHONPATH=/middleware already set):
    --middleware prefix_capture.PrefixCapture

Output: /logs/capture/req_<seq>_<epoch_ms>.json  (one file per request)
Disable: remove the --middleware flag and restart. Then delete /logs/capture/.
"""

import asyncio
import itertools
import os
import time
from pathlib import Path

_seq = itertools.count(1)


class PrefixCapture:
    def __init__(self, app):
        self.app = app
        self.out_dir = Path(os.environ.get("VLLM_LOG_DIR", "/logs")) / "capture"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return self.app(scope, receive, send)
        if not scope.get("path", "").endswith("/v1/chat/completions"):
            return self.app(scope, receive, send)
        return self._intercept(scope, receive, send)

    async def _intercept(self, scope, receive, send):
        body = bytearray()

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    seq = next(_seq)
                    ts = int(time.time() * 1000)
                    path = self.out_dir / f"req_{seq:04d}_{ts}.json"
                    asyncio.get_running_loop().run_in_executor(
                        None, _write, path, bytes(body)
                    )
            return message

        await self.app(scope, receive_wrapper, send)


def _write(path, data):
    try:
        with open(path, "wb") as f:
            f.write(data)
    except Exception:
        pass

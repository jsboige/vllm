"""Capture source identity of /v1/* requests (good AND bad traffic).

Diagnostic — created 2026-05-16 after we saw ~50 stale `qwen3.5-35b-a3b`
404s/hour from `172.27.0.1` (Docker gateway) with no way to tell whether the
caller was a host-side process, an OWUI instance, or external traffic reverse-
proxied via IIS. Captures source IP + key forwarding headers + User-Agent +
requested model on every chat-completions request, regardless of status.

User explicitly asked (2026-05-16) to log both the good AND the bad traffic,
so we can characterize the legitimate sources too — not only the 4xx noise.

Filter after the fact with `jq 'select(.status >= 400)' /logs/error_sources.jsonl`
or `jq -s 'group_by(.user_agent) | map({ua: .[0].user_agent, n: length})'`.

Output: /logs/error_sources.jsonl (one JSON line per request).

Body capture: first N + last N bytes of request body (default N=1500, env override
ERROR_SOURCE_BODY_BYTES). Head shows model/system prompt/messages start; tail shows
the latest user turn + sampling params. NOTE: bodies may contain user prompts,
chat history, and (rarely) secrets embedded by clients. Reading /logs/error_sources.jsonl
is privileged.

Wire-up: profile must mount middleware/ and set PYTHONPATH=/middleware, then
  --middleware error_source_capture.ErrorSourceCapture

Disable: remove the --middleware flag and restart.
"""

import asyncio
import json
import os
import time
from pathlib import Path

_BODY_BYTES = int(os.environ.get("ERROR_SOURCE_BODY_BYTES", "1500"))


class ErrorSourceCapture:
    def __init__(self, app):
        self.app = app
        out_dir = Path(os.environ.get("VLLM_LOG_DIR", "/logs"))
        out_dir.mkdir(parents=True, exist_ok=True)
        self.out_path = out_dir / "error_sources.jsonl"
        self._lock = asyncio.Lock()

    def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return self.app(scope, receive, send)
        path = scope.get("path", "")
        if not (path.startswith("/v1/") or path.startswith("/openai/v1/")):
            return self.app(scope, receive, send)
        return self._intercept(scope, receive, send)

    async def _intercept(self, scope, receive, send):
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        client = scope.get("client") or ("-", 0)
        body_chunks = bytearray()
        captured_model = None

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    nonlocal captured_model
                    try:
                        captured_model = json.loads(bytes(body_chunks)).get("model")
                    except Exception:
                        captured_model = None
            return message

        status_holder = {"status": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 0)
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)

        # Log every request — good AND bad. Filter with jq after the fact.
        if status_holder["status"] > 0:
            body_bytes = bytes(body_chunks)
            body_len = len(body_bytes)
            if body_len <= 2 * _BODY_BYTES:
                body_head = body_bytes.decode("utf-8", errors="replace")
                body_tail = ""
                body_truncated = 0
            else:
                body_head = body_bytes[:_BODY_BYTES].decode("utf-8", errors="replace")
                body_tail = body_bytes[-_BODY_BYTES:].decode("utf-8", errors="replace")
                body_truncated = body_len - 2 * _BODY_BYTES
            entry = {
                "ts": time.time(),
                "status": status_holder["status"],
                "path": scope.get("path", ""),
                "client": f"{client[0]}:{client[1]}",
                "model": captured_model,
                "user_agent": headers.get("user-agent", ""),
                "x_forwarded_for": headers.get("x-forwarded-for", ""),
                "x_real_ip": headers.get("x-real-ip", ""),
                "x_forwarded_host": headers.get("x-forwarded-host", ""),
                "host": headers.get("host", ""),
                "referer": headers.get("referer", ""),
                "auth_prefix": (headers.get("authorization", "")[:24] + "...")
                if headers.get("authorization") else "",
                "body_bytes": body_len,
                "body_truncated_bytes": body_truncated,
                "body_head": body_head,
                "body_tail": body_tail,
            }
            asyncio.get_running_loop().run_in_executor(
                None, _append_line, self.out_path, entry
            )


def _append_line(path, entry):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

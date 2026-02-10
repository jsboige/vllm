"""
ASGI middleware for logging vLLM chat completion requests and responses.

Intercepts /v1/chat/completions, captures full request/response content
with timing (TTFT, E2E), and writes JSONL log entries asynchronously.

Handles both streaming (SSE) and non-streaming responses. Streaming chunks
are forwarded to the client in real-time -- only the log entry is buffered.

Configuration via environment variables:
    VLLM_LOG_DIR: Directory for log files (default: /logs)
    VLLM_LOG_REQUESTS_CONTENT: Set to "0" to disable (default: "1")

Usage with vLLM --middleware flag:
    --middleware logging_middleware.RequestResponseLogger

The module must be importable (e.g. via PYTHONPATH=/middleware mount).
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class RequestResponseLogger:
    """Pure ASGI middleware logging chat completion requests/responses as JSONL.

    Follows vLLM's middleware pattern (see XRequestIdMiddleware in api_server.py).
    Constructor signature: __init__(self, app) -- compatible with
    app.add_middleware(cls) loading at api_server.py:1596.
    """

    def __init__(self, app):
        self.app = app
        self.log_dir = Path(os.environ.get("VLLM_LOG_DIR", "/logs"))
        self.enabled = os.environ.get("VLLM_LOG_REQUESTS_CONTENT", "1") != "0"
        self.log_file = self.log_dir / "chat_completions.jsonl"
        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.enabled:
            return self.app(scope, receive, send)

        path = scope.get("path", "")
        if not path.endswith("/v1/chat/completions"):
            return self.app(scope, receive, send)

        return self._intercept(scope, receive, send)

    async def _intercept(self, scope, receive, send):
        request_body = bytearray()

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request":
                request_body.extend(message.get("body", b""))
            return message

        response_status = 0
        content_type = ""
        request_id = None
        response_chunks = []
        t_start = time.monotonic()
        t_first_body = None

        async def send_wrapper(message):
            nonlocal response_status, content_type, request_id, t_first_body

            if message["type"] == "http.response.start":
                response_status = message.get("status", 200)
                for name, value in message.get("headers", []):
                    n = name.lower() if isinstance(name, bytes) else name
                    v = (value.decode("latin-1")
                         if isinstance(value, bytes) else value)
                    if n == b"content-type":
                        content_type = v
                    elif n == b"x-request-id":
                        request_id = v

            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    if t_first_body is None:
                        t_first_body = time.monotonic()
                    response_chunks.append(body)

                if not message.get("more_body", False):
                    t_end = time.monotonic()
                    try:
                        entry = _build_entry(
                            request_body=bytes(request_body),
                            response_chunks=response_chunks,
                            is_streaming="text/event-stream" in content_type,
                            status=response_status,
                            request_id=request_id or uuid.uuid4().hex,
                            t_start=t_start,
                            t_first_body=t_first_body or t_end,
                            t_end=t_end,
                        )
                        asyncio.create_task(
                            _async_write(self.log_file, entry))
                    except Exception:
                        pass

            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)


# ---------------------------------------------------------------------------
# Log entry construction (module-level functions, no state)
# ---------------------------------------------------------------------------

def _build_entry(*, request_body, response_chunks, is_streaming,
                 status, request_id, t_start, t_first_body, t_end):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "status": status,
        "stream": is_streaming,
        "ttft_s": round(t_first_body - t_start, 4),
        "e2e_s": round(t_end - t_start, 4),
    }
    _parse_request(request_body, entry)
    if is_streaming:
        _parse_streaming_response(response_chunks, entry)
    else:
        _parse_non_streaming_response(response_chunks, entry)
    return entry


def _parse_request(body, entry):
    try:
        req = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return
    entry["model"] = req.get("model", "")
    messages = req.get("messages", [])
    entry["messages_count"] = len(messages)
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                entry["last_user_message"] = content[:500]
            elif isinstance(content, list):
                texts = [p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text"]
                entry["last_user_message"] = " ".join(texts)[:500]
            break
    entry["tools_count"] = len(req.get("tools", []))
    entry["temperature"] = req.get("temperature")
    entry["max_tokens"] = (req.get("max_tokens")
                           or req.get("max_completion_tokens"))


def _parse_non_streaming_response(chunks, entry):
    try:
        resp = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, ValueError):
        return
    choices = resp.get("choices", [])
    if choices:
        choice = choices[0]
        msg = choice.get("message", {})
        entry["response_text"] = msg.get("content")
        tc = msg.get("tool_calls")
        if tc:
            entry["tool_calls"] = tc
        entry["finish_reason"] = choice.get("finish_reason")
    usage = resp.get("usage", {})
    if usage:
        entry["prompt_tokens"] = usage.get("prompt_tokens")
        entry["completion_tokens"] = usage.get("completion_tokens")


def _parse_streaming_response(chunks, entry):
    try:
        raw = b"".join(chunks).decode("utf-8", errors="replace")
    except Exception:
        return

    content_parts = []
    reasoning_parts = []
    tool_calls_acc = {}
    finish_reason = None
    usage = None

    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        try:
            chunk = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content") or delta.get("reasoning"):
                reasoning_parts.append(
                    delta.get("reasoning_content") or delta["reasoning"])
            for tc in delta.get("tool_calls", []):
                idx = tc.get("index", 0)
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {"id": tc.get("id", ""),
                                           "name": "", "arguments": ""}
                fn = tc.get("function", {})
                if fn.get("name"):
                    tool_calls_acc[idx]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls_acc[idx]["arguments"] += fn["arguments"]
            fr = choices[0].get("finish_reason")
            if fr:
                finish_reason = fr

        if chunk.get("usage"):
            usage = chunk["usage"]

    entry["response_text"] = "".join(content_parts) or None
    if reasoning_parts:
        entry["reasoning_text"] = "".join(reasoning_parts)
    if tool_calls_acc:
        entry["tool_calls"] = [
            {"id": v["id"],
             "function": {"name": v["name"], "arguments": v["arguments"]}}
            for v in tool_calls_acc.values()
        ]
    entry["finish_reason"] = finish_reason
    if usage:
        entry["prompt_tokens"] = usage.get("prompt_tokens")
        entry["completion_tokens"] = usage.get("completion_tokens")


# ---------------------------------------------------------------------------
# Async file I/O (fire-and-forget from send_wrapper)
# ---------------------------------------------------------------------------

async def _async_write(log_file, entry):
    try:
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_append, log_file, line)
    except Exception:
        pass


def _sync_append(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)

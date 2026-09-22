#!/usr/bin/env python3
"""One-shot sk-agent call_agent from the command line (smoke tests of agents/tools).

Usage: <sk-agent venv python> sk_call.py AGENT "prompt" [timeout_s]
"""
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SK_DIR = Path("d:/roo-extensions/mcps/internal/servers/sk-agent")


async def main() -> None:
    agent, prompt = sys.argv[1], sys.argv[2]
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 600
    params = StdioServerParameters(command=str(SK_DIR / "venv/Scripts/python.exe"),
                                   args=[str(SK_DIR / "sk_agent.py")],
                                   env={**os.environ, "SK_AGENT_CONFIG": str(SK_DIR / "sk_agent_config.json")})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("call_agent", {"prompt": prompt, "agent": agent, "timeout": timeout,
                                                   "include_steps": True},
                                    read_timeout_seconds=timedelta(seconds=timeout + 60))
            print("\n".join(getattr(c, "text", "") for c in res.content))


asyncio.run(main())

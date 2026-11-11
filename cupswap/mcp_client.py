"""MCP client used by the buyer agent: discover tools and call them over stdio."""
from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from mcp import ClientSession, StdioServerParameters, stdio_client

from .config import ROOT

_PARAMS = StdioServerParameters(command=sys.executable, args=["-m", "cupswap.mcp_server"], cwd=str(ROOT))
_POOL = ThreadPoolExecutor(max_workers=1)


async def _list_tools() -> list[dict]:
    async with stdio_client(_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.list_tools()
            return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
                    for t in res.tools]


async def _call(name: str, args: dict) -> dict:
    async with stdio_client(_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(name, args)
            text = "".join(getattr(c, "text", "") for c in res.content)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}


def _run(coro):
    # Streamlit already owns a thread; run the coroutine on a private loop in a worker thread.
    return _POOL.submit(asyncio.run, coro).result(timeout=30)


def list_tools() -> list[dict]:
    return _run(_list_tools())


def call_tool(name: str, args: dict) -> dict:
    return _run(_call(name, args))


def openai_schema_from_mcp(tool: dict) -> dict:
    """Convert a discovered MCP tool into an OpenAI function schema, adding the agent-side
    'thought' field our ReAct trace requires (it is stripped before the MCP call)."""
    schema = json.loads(json.dumps(tool["input_schema"]))
    props = {"thought": {"type": "string", "description": "One sentence: why you are calling this tool now."}}
    props.update(schema.get("properties", {}))
    for p in props.values():
        p.pop("title", None)
    return {"type": "function", "function": {
        "name": tool["name"], "description": "[via MCP server] " + tool["description"],
        "parameters": {"type": "object", "properties": props,
                       "required": ["thought"] + list(schema.get("required", [])),
                       "additionalProperties": False},
        "strict": True}}

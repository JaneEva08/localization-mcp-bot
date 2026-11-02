"""MCP SDK выполняет initialize, tools/list и tools/call по HTTP."""
import json
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from settings import MCP_URL


@asynccontextmanager
async def session(url=MCP_URL):
    async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client


async def list_tools():
    async with session() as client:
        tools = (await client.list_tools()).tools
        return [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.inputSchema
        }} for t in tools]


async def call_tool(name, arguments):
    async with session() as client:
        response = await client.call_tool(name, arguments)
    return decode(response)


def decode(response):
    content = "\n".join(c.text for c in response.content if c.type == "text")
    if response.isError:
        raise ValueError(content)
    if response.structuredContent is not None:
        return response.structuredContent
    return json.loads(content)

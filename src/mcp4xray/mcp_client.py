from __future__ import annotations

from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def serialize_tool(tool: Any) -> dict[str, Any]:
    if isinstance(tool, dict):
        return tool
    if hasattr(tool, "model_dump"):
        return tool.model_dump(mode="json")
    return {
        "name": getattr(tool, "name", None),
        "description": getattr(tool, "description", None),
        "inputSchema": getattr(tool, "inputSchema", None),
    }


def normalize_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return {
            "is_error": result.get("isError", False),
            "content": result.get("content", []),
        }
    content = []
    for item in getattr(result, "content", []):
        if hasattr(item, "model_dump"):
            content.append(item.model_dump(mode="json"))
        else:
            content.append(str(item))
    return {
        "is_error": getattr(result, "isError", False),
        "content": content,
    }


class MCPClient:
    def __init__(self, url: str):
        self.url = url
        self.session: ClientSession | None = None
        self.tools: list[dict[str, Any]] = []
        self.instructions: str = ""
        self._client_cm = None
        self._session_cm = None

    async def connect(self):
        self._client_cm = streamablehttp_client(self.url)
        streams = await self._client_cm.__aenter__()
        read_stream, write_stream, _ = streams
        self._session_cm = ClientSession(read_stream, write_stream)
        self.session = await self._session_cm.__aenter__()
        init_result = await self.session.initialize()
        self.instructions = getattr(init_result, "instructions", "") or ""
        tools_result = await self.session.list_tools()
        self.tools = [serialize_tool(t) for t in tools_result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        result = await self.session.call_tool(name, arguments)
        return normalize_tool_result(result)

    async def disconnect(self):
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._client_cm:
            await self._client_cm.__aexit__(None, None, None)
        self.session = None
        self.tools = []
        self.instructions = ""

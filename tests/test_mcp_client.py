from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from mcp4xray.mcp_client import MCPClient, normalize_tool_result, serialize_tool


class TestSerializeTool:
    """Tests for serialize_tool()."""

    def test_dict_input_returned_as_is(self) -> None:
        tool = {"name": "search", "description": "Search the archive", "inputSchema": {}}
        result = serialize_tool(tool)
        assert result is tool  # exact same dict object

    def test_object_with_model_dump(self) -> None:
        class FakeTool:
            def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
                return {
                    "name": "cone_search",
                    "description": "Cone search",
                    "inputSchema": {"type": "object"},
                }

        result = serialize_tool(FakeTool())
        assert result == {
            "name": "cone_search",
            "description": "Cone search",
            "inputSchema": {"type": "object"},
        }

    def test_fallback_uses_getattr(self) -> None:
        tool = SimpleNamespace(
            name="lookup",
            description="Look up an observation",
            inputSchema={"type": "object", "properties": {}},
        )
        result = serialize_tool(tool)
        assert result == {
            "name": "lookup",
            "description": "Look up an observation",
            "inputSchema": {"type": "object", "properties": {}},
        }


class TestNormalizeToolResult:
    """Tests for normalize_tool_result()."""

    def test_dict_input(self) -> None:
        raw = {
            "isError": False,
            "content": [{"type": "text", "text": "hello"}],
        }
        result = normalize_tool_result(raw)
        assert result == {
            "is_error": False,
            "content": [{"type": "text", "text": "hello"}],
        }

    def test_dict_input_defaults(self) -> None:
        result = normalize_tool_result({})
        assert result == {"is_error": False, "content": []}

    def test_object_with_model_dump_content(self) -> None:
        class FakeContent:
            def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
                return {"type": "text", "text": "data"}

        raw = SimpleNamespace(isError=True, content=[FakeContent()])
        result = normalize_tool_result(raw)
        assert result == {
            "is_error": True,
            "content": [{"type": "text", "text": "data"}],
        }

    def test_object_content_without_model_dump(self) -> None:
        raw = SimpleNamespace(isError=False, content=["plain text"])
        result = normalize_tool_result(raw)
        assert result == {
            "is_error": False,
            "content": ["plain text"],
        }


class TestMCPClientInit:
    """Tests for MCPClient initial state."""

    def test_initial_state(self) -> None:
        client = MCPClient("http://localhost:9000/mcp")
        assert client.url == "http://localhost:9000/mcp"
        assert client.session is None
        assert client.tools == []
        assert client.instructions == ""

    def test_call_tool_raises_when_not_connected(self) -> None:
        import pytest

        client = MCPClient("http://localhost:9000/mcp")
        with pytest.raises(RuntimeError, match="Not connected"):
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                client.call_tool("search", {"ra": 0.0})
            )

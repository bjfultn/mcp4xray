"""Tests for the agentic chat loop in mcp4xray.chat."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp4xray.chat import ChatEvent, run_chat_turn
from mcp4xray.llm import LLMResponse, ToolCall


def _make_mock_llm(
    responses: list[LLMResponse],
) -> AsyncMock:
    """Create a mock LLMBackend that returns *responses* in order."""
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=responses)

    def _append(messages, tool_name, arguments, result):
        new = list(messages)
        new.append({"role": "assistant", "content": f"called {tool_name}"})
        new.append({"role": "tool", "content": json.dumps(result)})
        return new

    llm.append_tool_interaction = _append
    return llm


def _make_mock_mcp(
    tools: list[dict[str, Any]] | None = None,
    instructions: str = "",
    call_tool_results: list[dict[str, Any]] | None = None,
) -> AsyncMock:
    """Create a mock MCPClient with configurable tools and call_tool results."""
    mcp = AsyncMock()
    mcp.tools = tools or []
    mcp.instructions = instructions
    if call_tool_results is not None:
        mcp.call_tool = AsyncMock(side_effect=call_tool_results)
    else:
        mcp.call_tool = AsyncMock(
            return_value={"is_error": False, "content": [{"type": "text", "text": "ok"}]}
        )
    return mcp


async def _collect_events(llm, mcp, messages, **kwargs) -> list[ChatEvent]:
    """Helper to collect all ChatEvent objects from run_chat_turn."""
    events: list[ChatEvent] = []
    async for event in run_chat_turn(llm, mcp, messages, **kwargs):
        events.append(event)
    return events


class TestChatTurnTextOnly:
    """LLM responds with text and no tool calls."""

    @pytest.mark.asyncio
    async def test_yields_text_and_done(self) -> None:
        llm = _make_mock_llm([LLMResponse(text="Hello, researcher!")])
        mcp = _make_mock_mcp(instructions="You are an X-ray assistant.")
        messages = [{"role": "user", "content": "Hi"}]

        events = await _collect_events(llm, mcp, messages)

        assert len(events) == 2
        assert events[0].type == "text"
        assert events[0].content == "Hello, researcher!"
        assert events[1].type == "done"

    @pytest.mark.asyncio
    async def test_passes_system_prompt_and_tools(self) -> None:
        llm = _make_mock_llm([LLMResponse(text="Done")])
        tools = [{"name": "search", "description": "Search", "inputSchema": {}}]
        mcp = _make_mock_mcp(tools=tools, instructions="System prompt here")
        messages = [{"role": "user", "content": "test"}]

        await _collect_events(llm, mcp, messages)

        llm.complete.assert_called_once_with(messages, tools, "System prompt here")

    @pytest.mark.asyncio
    async def test_does_not_call_tool(self) -> None:
        llm = _make_mock_llm([LLMResponse(text="No tools needed")])
        mcp = _make_mock_mcp()
        messages = [{"role": "user", "content": "Just a question"}]

        await _collect_events(llm, mcp, messages)

        mcp.call_tool.assert_not_called()


class TestChatTurnWithToolCall:
    """LLM makes a tool call, gets a result, then responds with text."""

    @pytest.mark.asyncio
    async def test_yields_tool_call_result_text_done(self) -> None:
        responses = [
            LLMResponse(
                text="",
                tool_calls=[ToolCall(name="cone_search", arguments={"ra": 83.6, "dec": -5.4})],
            ),
            LLMResponse(text="Found 3 sources near Orion."),
        ]
        llm = _make_mock_llm(responses)
        tool_result = {
            "is_error": False,
            "content": [{"type": "text", "text": "3 sources"}],
        }
        mcp = _make_mock_mcp(call_tool_results=[tool_result])
        messages = [{"role": "user", "content": "Search near Orion"}]

        events = await _collect_events(llm, mcp, messages)

        types = [e.type for e in events]
        assert types == ["tool_call", "tool_result", "text", "done"]

    @pytest.mark.asyncio
    async def test_tool_call_event_has_correct_fields(self) -> None:
        responses = [
            LLMResponse(
                text="",
                tool_calls=[ToolCall(name="cone_search", arguments={"ra": 10.0})],
            ),
            LLMResponse(text="Done"),
        ]
        llm = _make_mock_llm(responses)
        mcp = _make_mock_mcp()
        messages = [{"role": "user", "content": "search"}]

        events = await _collect_events(llm, mcp, messages)

        tc_event = events[0]
        assert tc_event.type == "tool_call"
        assert tc_event.tool_name == "cone_search"
        assert tc_event.tool_args == {"ra": 10.0}
        parsed = json.loads(tc_event.content)
        assert parsed["name"] == "cone_search"

    @pytest.mark.asyncio
    async def test_tool_result_event_has_content(self) -> None:
        responses = [
            LLMResponse(
                text="",
                tool_calls=[ToolCall(name="get_obs", arguments={"obsid": 1234})],
            ),
            LLMResponse(text="Observation details"),
        ]
        llm = _make_mock_llm(responses)
        tool_result = {"is_error": False, "content": [{"type": "text", "text": "obs data"}]}
        mcp = _make_mock_mcp(call_tool_results=[tool_result])
        messages = [{"role": "user", "content": "Get obs 1234"}]

        events = await _collect_events(llm, mcp, messages)

        result_event = events[1]
        assert result_event.type == "tool_result"
        assert result_event.tool_name == "get_obs"
        parsed = json.loads(result_event.content)
        assert parsed["is_error"] is False

    @pytest.mark.asyncio
    async def test_tool_call_exception_yields_error_result(self) -> None:
        responses = [
            LLMResponse(
                text="",
                tool_calls=[ToolCall(name="broken_tool", arguments={})],
            ),
            LLMResponse(text="Handled the error"),
        ]
        llm = _make_mock_llm(responses)
        mcp = _make_mock_mcp()
        mcp.call_tool = AsyncMock(side_effect=RuntimeError("Connection lost"))
        messages = [{"role": "user", "content": "do it"}]

        events = await _collect_events(llm, mcp, messages)

        types = [e.type for e in events]
        assert types == ["tool_call", "tool_result", "text", "done"]
        result_event = events[1]
        parsed = json.loads(result_event.content)
        assert parsed["is_error"] is True
        assert "Connection lost" in parsed["content"][0]["text"]


class TestChatTurnLLMError:
    """LLM raises an exception during complete()."""

    @pytest.mark.asyncio
    async def test_yields_error_and_done(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("API timeout"))
        mcp = _make_mock_mcp()
        messages = [{"role": "user", "content": "Hello"}]

        events = await _collect_events(llm, mcp, messages)

        assert len(events) == 2
        assert events[0].type == "error"
        assert "API timeout" in events[0].content
        assert events[1].type == "done"

    @pytest.mark.asyncio
    async def test_no_tool_calls_after_error(self) -> None:
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=ValueError("Bad request"))
        mcp = _make_mock_mcp()
        messages = [{"role": "user", "content": "Hello"}]

        await _collect_events(llm, mcp, messages)

        mcp.call_tool.assert_not_called()


class TestChatTurnMaxIterations:
    """LLM always returns tool calls, hitting the iteration limit."""

    @pytest.mark.asyncio
    async def test_yields_error_after_max_iterations(self) -> None:
        # LLM always returns a tool call, never a final text-only response
        always_tool = LLMResponse(
            text="",
            tool_calls=[ToolCall(name="loop_tool", arguments={"x": 1})],
        )
        llm = _make_mock_llm([always_tool, always_tool, always_tool])
        mcp = _make_mock_mcp()
        messages = [{"role": "user", "content": "infinite loop"}]

        events = await _collect_events(llm, mcp, messages, max_iterations=2)

        types = [e.type for e in events]
        # Each iteration: tool_call + tool_result = 2 events, x2 iterations = 4
        # Then error + done = 2 more
        assert types == [
            "tool_call", "tool_result",
            "tool_call", "tool_result",
            "error", "done",
        ]
        error_event = [e for e in events if e.type == "error"][0]
        assert "Max tool iterations reached" in error_event.content

    @pytest.mark.asyncio
    async def test_llm_called_max_iterations_times(self) -> None:
        always_tool = LLMResponse(
            text="",
            tool_calls=[ToolCall(name="loop_tool", arguments={})],
        )
        llm = _make_mock_llm([always_tool, always_tool])
        mcp = _make_mock_mcp()
        messages = [{"role": "user", "content": "loop"}]

        await _collect_events(llm, mcp, messages, max_iterations=2)

        assert llm.complete.call_count == 2

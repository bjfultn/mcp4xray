"""Agentic chat loop with tool-call cycling.

Orchestrates multi-turn conversations between an LLM backend and MCP tools,
yielding structured ChatEvent objects for each step in the interaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

from mcp4xray.llm import LLMBackend, LLMResponse

MAX_TOOL_ITERATIONS = 10


@dataclass
class ChatEvent:
    """A single event emitted during a chat turn.

    *type* is one of ``"text"``, ``"tool_call"``, ``"tool_result"``,
    ``"error"``, or ``"done"``.
    """

    type: str  # "text", "tool_call", "tool_result", "error", "done"
    content: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] | None = None


async def run_chat_turn(
    llm: LLMBackend,
    mcp: Any,  # MCPClient
    messages: list[dict[str, str]],
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> AsyncIterator[ChatEvent]:
    """Run a single chat turn, cycling through tool calls until the LLM
    produces a final text response or the iteration limit is reached.

    Yields :class:`ChatEvent` objects for each step so the caller can
    stream progress to a UI.
    """
    system_prompt = getattr(mcp, "instructions", "") or ""
    tools = getattr(mcp, "tools", []) or []
    working_messages = list(messages)

    for _ in range(max_iterations):
        try:
            response: LLMResponse = await llm.complete(working_messages, tools, system_prompt)
        except Exception as exc:
            yield ChatEvent(type="error", content=str(exc))
            yield ChatEvent(type="done")
            return

        if response.text:
            yield ChatEvent(type="text", content=response.text)

        if not response.tool_calls:
            yield ChatEvent(type="done")
            return

        for tc in response.tool_calls:
            yield ChatEvent(
                type="tool_call",
                tool_name=tc.name,
                tool_args=tc.arguments,
                content=json.dumps({"name": tc.name, "arguments": tc.arguments}),
            )
            try:
                result = await mcp.call_tool(tc.name, tc.arguments)
            except Exception as exc:
                result = {"is_error": True, "content": [{"type": "text", "text": str(exc)}]}

            result_text = json.dumps(result)
            yield ChatEvent(type="tool_result", tool_name=tc.name, content=result_text)

            working_messages = llm.append_tool_interaction(
                working_messages, tc.name, tc.arguments, result
            )

    yield ChatEvent(type="error", content="Max tool iterations reached")
    yield ChatEvent(type="done")

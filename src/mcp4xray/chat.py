"""Agentic chat loop with tool-call cycling.

Orchestrates multi-turn conversations between an LLM backend and MCP tools,
yielding structured ChatEvent objects for each step in the interaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

from mcp4xray.llm import LLMBackend, LLMResponse

MAX_TOOL_ITERATIONS = 20
# Max chars of a tool result to feed back to the LLM. Large results (e.g.
# 10k-row tables) are truncated for the LLM but sent in full to the UI.
_TOOL_RESULT_LLM_CAP = 4000

BASE_SYSTEM_PROMPT = """\
You are an expert X-ray astronomy archive assistant with deep knowledge of \
the Chandra and XMM-Newton observatories. You help researchers query mission \
archives, interpret observation metadata, find relevant sources, and navigate \
mission documentation. When working across missions, you understand the \
differences in instrument capabilities, coordinate conventions, and archive \
interfaces. You prefer precise, scientifically accurate responses and flag \
ambiguities when archive queries could be interpreted multiple ways.

Formatting rules:
- Do not use emojis. This is a professional research tool.
- Use plain markdown: headers, bold, lists, code blocks, and tables.
- When presenting tabular data, use markdown pipe tables so the UI can render \
them as sortable, downloadable tables.
- Be concise. Lead with the answer, not the reasoning.
"""


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


def _truncate_for_llm(result_text: str) -> str:
    """Truncate a tool result for the LLM's working context.

    For tabular MCP results, produces a compact summary with column names,
    row count, and a few sample rows. For other results, plain truncation.
    """
    if len(result_text) <= _TOOL_RESULT_LLM_CAP:
        return result_text

    try:
        parsed = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return result_text[:_TOOL_RESULT_LLM_CAP] + f"... [{len(result_text)} chars truncated]"

    # Structured MCP result: {"content": [{"type": "text", "text": "..."}]}
    if isinstance(parsed, dict) and isinstance(parsed.get("content"), list):
        for item in parsed["content"]:
            if item.get("type") == "text":
                try:
                    inner = json.loads(item["text"])
                except (json.JSONDecodeError, TypeError):
                    break
                if isinstance(inner, dict) and "columns" in inner and "rows" in inner:
                    cols = inner["columns"]
                    rows = inner["rows"]
                    total = inner.get("row_count", len(rows))
                    summary = {
                        "columns": cols,
                        "row_count": total,
                        "preview_rows": rows[:5],
                        "note": f"Showing 5 of {total} rows. Full data was sent to the user.",
                    }
                    return json.dumps({"content": [{"type": "text", "text": json.dumps(summary)}]})

    return result_text[:_TOOL_RESULT_LLM_CAP] + f"... [{len(result_text)} chars truncated]"


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
    mcp_instructions = getattr(mcp, "instructions", "") or ""
    system_prompt = BASE_SYSTEM_PROMPT
    if mcp_instructions:
        system_prompt += "\nMission server context:\n" + mcp_instructions
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

            # Send truncated result to LLM to avoid blowing context on large tables
            llm_result = _truncate_for_llm(result_text)
            working_messages = llm.append_tool_interaction(
                working_messages, tc.name, tc.arguments, llm_result, response
            )

    yield ChatEvent(type="error", content="Max tool iterations reached")
    yield ChatEvent(type="done")

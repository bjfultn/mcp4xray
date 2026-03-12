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
# Approximate token budget for conversation history. ~4 chars per token.
_MAX_HISTORY_TOKENS = 100_000
_CHARS_PER_TOKEN = 4


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: ~4 chars per token."""
    return sum(len(m.get("content", "")) for m in messages) // _CHARS_PER_TOKEN


def trim_messages(
    messages: list[dict[str, Any]],
    max_tokens: int = _MAX_HISTORY_TOKENS,
) -> list[dict[str, Any]]:
    """Trim conversation history to fit within a token budget.

    Keeps the first user message (establishes the topic) and the most
    recent messages. Drops messages from the middle when over budget,
    inserting a note so the LLM knows context was trimmed.
    """
    if _estimate_tokens(messages) <= max_tokens:
        return messages

    if len(messages) <= 2:
        return messages

    # Always keep the first message (original user query)
    first = messages[0]
    rest = messages[1:]

    # Budget remaining after the first message
    first_tokens = len(first.get("content", "")) // _CHARS_PER_TOKEN
    budget = max_tokens - first_tokens

    # Walk backwards from the end, accumulating messages that fit
    kept_tail: list[dict[str, Any]] = []
    used = 0
    for msg in reversed(rest):
        msg_tokens = len(msg.get("content", "")) // _CHARS_PER_TOKEN
        if used + msg_tokens > budget:
            break
        kept_tail.append(msg)
        used += msg_tokens

    kept_tail.reverse()

    # If we couldn't even keep one recent message, keep just the last one
    if not kept_tail:
        kept_tail = [rest[-1]]

    trimmed_count = len(rest) - len(kept_tail)
    if trimmed_count > 0:
        note = {
            "role": "user",
            "content": f"[{trimmed_count} earlier messages trimmed to fit context window]",
        }
        return [first, note] + kept_tail

    return [first] + kept_tail


BASE_SYSTEM_PROMPT = """\
You are an expert X-ray astronomy archive assistant with deep knowledge of \
the Chandra and XMM-Newton observatories. You help researchers query mission \
archives, interpret observation metadata, find relevant sources, and navigate \
mission documentation. When working across missions, you understand the \
differences in instrument capabilities, coordinate conventions, and archive \
interfaces. You prefer precise, scientifically accurate responses and flag \
ambiguities when archive queries could be interpreted multiple ways.

Tool-calling rules:
- You have a MAXIMUM of {max_iterations} tool calls per response. Plan ahead.
- Be efficient: do not call the same tool twice with the same arguments.
- Combine what you need: if you need column metadata to write a query, get \
the metadata first, then write the query. Do not re-fetch metadata you \
already have.
- If you need to explore a table schema, one call to get_table_columns or \
get_table_column_metadata is enough — do not call both for the same table.
- Prefer to construct a well-formed ADQL query in one shot rather than \
running exploratory queries. You are an expert — use your knowledge.
- If a tool call fails, do not retry with the same arguments. Adjust your \
approach or explain the issue to the user.

Formatting rules:
- Do not use emojis. This is a professional research tool.
- Use plain markdown: headers, bold, lists, code blocks, and tables.
- When presenting tabular data, use markdown pipe tables so the UI can render \
them as sortable, downloadable tables.
- When a tool already returned a large table, do NOT repeat the full table in \
your response. The UI already displays the tool result as a sortable, \
downloadable table. Instead, summarize key findings or highlight interesting \
rows. You may include a small illustrative table (5-10 rows) if useful.
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

    Only truncates results that have a ``rows`` key (query results).
    Schema/metadata results (column lists, table lists, examples) are
    kept in full since the LLM needs them to build correct queries.
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
                # Only truncate if it has "rows" — that's a query result.
                # Metadata results (columns, table_names, examples) have no
                # "rows" key and are kept verbatim.
                if isinstance(inner, dict) and "rows" in inner:
                    truncated = dict(inner)
                    rows = truncated.pop("rows")
                    total = truncated.get("row_count", len(rows))
                    truncated["preview_rows"] = rows[:5]
                    truncated["note"] = (
                        f"Showing 5 of {total} rows. The full table is already "
                        f"displayed to the user as a sortable, downloadable table. "
                        f"Do not repeat it — summarize findings instead."
                    )
                    return json.dumps({"content": [{"type": "text", "text": json.dumps(truncated)}]})

    # No rows key found — keep in full (metadata, schemas, etc.)
    # Only fall back to hard truncation for truly huge non-structured results
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
    system_prompt = BASE_SYSTEM_PROMPT.format(max_iterations=max_iterations)
    if mcp_instructions:
        system_prompt += "\nMission server context:\n" + mcp_instructions
    tools = getattr(mcp, "tools", []) or []
    working_messages = trim_messages(list(messages))

    for _ in range(max_iterations):
        working_messages = trim_messages(working_messages)
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

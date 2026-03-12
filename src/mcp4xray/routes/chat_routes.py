from __future__ import annotations

import json

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mcp4xray.auth import require_auth
from mcp4xray.chat import trim_messages
from mcp4xray.llm import create_llm_backend
from mcp4xray.mcp_client import MCPClient
from mcp4xray.chat import run_chat_turn

router = APIRouter()

# Max chars to keep from a tool result when replaying history.
# Enough to show column names, a few sample rows, and row counts.
_TOOL_RESULT_CAP = 800


def _truncate_tool_result(content: str) -> str:
    """Produce a short summary of a tool result for conversation history.

    Only truncates results with a ``rows`` key (query results).
    Schema/metadata results (column lists, table lists, examples) are
    kept in full so the LLM can reference them for building queries.
    """
    if len(content) <= _TOOL_RESULT_CAP:
        return content

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content[:_TOOL_RESULT_CAP] + f"... [{len(content)} chars total]"

    # Structured MCP result
    if isinstance(parsed, dict) and isinstance(parsed.get("content"), list):
        for item in parsed["content"]:
            if item.get("type") == "text":
                try:
                    inner = json.loads(item["text"])
                except (json.JSONDecodeError, TypeError):
                    break
                # Only truncate if it has "rows" — query results.
                # Metadata (columns, table_names, examples) kept verbatim.
                if isinstance(inner, dict) and "rows" in inner:
                    truncated = dict(inner)
                    rows = truncated.pop("rows")
                    total = truncated.get("row_count", len(rows))
                    truncated["preview_rows"] = rows[:3]
                    truncated["note"] = f"3 of {total} rows shown"
                    return json.dumps(truncated)

    # No rows — keep in full (metadata, schemas, etc.)
    return content


def _build_history(prev_messages: list[dict]) -> list[dict]:
    """Build LLM message history from stored messages.

    Keeps user/assistant messages verbatim. Includes tool_call and
    tool_result as assistant notes so the LLM knows what tools were
    used and roughly what came back, without replaying huge payloads.
    """
    messages: list[dict] = []
    for m in prev_messages:
        role = m["role"]
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": m["content"]})
        elif role == "tool_call":
            # Summarise as an assistant note
            try:
                tc = json.loads(m["content"])
                note = f"[Called tool: {tc.get('name', '?')}({json.dumps(tc.get('arguments', {}))})]"
            except (json.JSONDecodeError, TypeError):
                note = f"[Called tool: {m['content'][:200]}]"
            messages.append({"role": "assistant", "content": note})
        elif role == "tool_result":
            truncated = _truncate_tool_result(m["content"])
            messages.append({"role": "user", "content": f"[Tool result: {truncated}]"})
    return trim_messages(messages)


class ChatRequest(BaseModel):
    message: str
    server_name: str
    model_id: str
    conversation_id: int | None = None


@router.post("/chat")
async def chat(req: ChatRequest, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    servers_config = request.app.state.servers_config

    server = next((s for s in servers_config.servers if s.name == req.server_name), None)
    if not server:
        raise HTTPException(status_code=400, detail=f"Unknown server: {req.server_name}")

    model_entry = next((m for m in servers_config.models if m.id == req.model_id), None)
    if not model_entry:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model_id}")

    # Get user's API key for this provider
    user_settings = await db.get_user_provider_settings(user["user_id"], model_entry.provider)
    api_key = (user_settings["api_key"] if user_settings else "") or ""
    base_url = (user_settings["base_url"] if user_settings else "") or getattr(model_entry, "base_url", "") or ""

    # Ollama doesn't need a key; all other providers do
    if not api_key and model_entry.provider != "ollama":
        raise HTTPException(
            status_code=400,
            detail=f"No API key configured for {model_entry.provider}. Add one in Settings.",
        )

    if req.conversation_id:
        conv_id = req.conversation_id
        prev_messages = await db.get_messages(conv_id)
        messages = _build_history(prev_messages)
    else:
        conv_id = await db.create_conversation(user["user_id"], req.server_name, req.model_id)
        messages = []

    messages.append({"role": "user", "content": req.message})
    await db.add_message(conv_id, "user", req.message)

    llm = create_llm_backend(model_entry.provider, model_entry.id, api_key=api_key, base_url=base_url)

    async def event_stream():
        mcp = MCPClient(server.url)
        full_text = ""
        try:
            # Send conversation_id immediately so the UI can update the sidebar
            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conv_id})}\n\n"

            try:
                await mcp.connect()
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'content': f'MCP connection failed: {exc}'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"
                return

            async for event in run_chat_turn(llm=llm, mcp=mcp, messages=messages):
                payload = {"type": event.type, "content": event.content}
                if event.tool_name:
                    payload["tool_name"] = event.tool_name
                if event.tool_args is not None:
                    payload["tool_args"] = event.tool_args
                if event.type == "done":
                    payload["conversation_id"] = conv_id
                yield f"data: {json.dumps(payload)}\n\n"

                if event.type == "text":
                    full_text += event.content
                elif event.type == "tool_call":
                    await db.add_message(conv_id, "tool_call", event.content)
                elif event.type == "tool_result":
                    await db.add_message(conv_id, "tool_result", event.content)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"
        finally:
            if full_text:
                await db.add_message(conv_id, "assistant", full_text)
            await mcp.disconnect()

    return StreamingResponse(event_stream(), media_type="text/event-stream")

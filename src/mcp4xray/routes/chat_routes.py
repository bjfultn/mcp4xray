from __future__ import annotations

import json

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mcp4xray.auth import require_auth
from mcp4xray.llm import create_llm_backend
from mcp4xray.mcp_client import MCPClient
from mcp4xray.chat import run_chat_turn

router = APIRouter()

# Max chars to keep from a tool result when replaying history.
# Enough to show column names, a few sample rows, and row counts.
_TOOL_RESULT_CAP = 800


def _truncate_tool_result(content: str) -> str:
    """Produce a short summary of a tool result for conversation history."""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content[:_TOOL_RESULT_CAP]

    # Structured MCP result with tabular data inside
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
                    preview_rows = rows[:3]
                    summary = {
                        "columns": cols,
                        "row_count": total,
                        "preview_rows": preview_rows,
                    }
                    return json.dumps(summary)

    # Generic: just truncate
    short = content[:_TOOL_RESULT_CAP]
    if len(content) > _TOOL_RESULT_CAP:
        short += f"... [{len(content)} chars total]"
    return short


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
    return messages


class ChatRequest(BaseModel):
    message: str
    server_name: str
    model_id: str
    conversation_id: int | None = None


@router.post("/chat")
async def chat(req: ChatRequest, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    app_config = request.app.state.app_config
    servers_config = request.app.state.servers_config

    server = next((s for s in servers_config.servers if s.name == req.server_name), None)
    if not server:
        raise HTTPException(status_code=400, detail=f"Unknown server: {req.server_name}")

    model_entry = next((m for m in servers_config.models if m.id == req.model_id), None)
    if not model_entry:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model_id}")

    # User settings override server-level keys and base_url
    user_settings = await db.get_user_provider_settings(user["user_id"], model_entry.provider)
    if user_settings and user_settings["api_key"]:
        api_key = user_settings["api_key"]
    else:
        api_key_map = {
            "anthropic": app_config.anthropic_api_key,
            "openai": app_config.openai_api_key,
            "gemini": app_config.gemini_api_key,
            "ollama": "",
        }
        api_key = api_key_map.get(model_entry.provider, "")

    if user_settings and user_settings["base_url"]:
        base_url = user_settings["base_url"]
    else:
        base_url = getattr(model_entry, "base_url", "") or ""

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

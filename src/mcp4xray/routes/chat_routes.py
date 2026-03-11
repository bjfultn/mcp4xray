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

    api_key_map = {
        "anthropic": app_config.anthropic_api_key,
        "openai": app_config.openai_api_key,
        "gemini": app_config.gemini_api_key,
        "ollama": "",
    }
    api_key = api_key_map.get(model_entry.provider, "")
    base_url = getattr(model_entry, "base_url", "") or ""

    if req.conversation_id:
        conv_id = req.conversation_id
        prev_messages = await db.get_messages(conv_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in prev_messages]
    else:
        conv_id = await db.create_conversation(user["user_id"], req.server_name, req.model_id)
        messages = []

    messages.append({"role": "user", "content": req.message})
    await db.add_message(conv_id, "user", req.message)

    llm = create_llm_backend(model_entry.provider, model_entry.id, api_key=api_key, base_url=base_url)

    async def event_stream():
        mcp = MCPClient(server.url)
        try:
            await mcp.connect()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': f'MCP connection failed: {exc}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"
            return

        full_text = ""
        try:
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
        finally:
            if full_text:
                await db.add_message(conv_id, "assistant", full_text)
            await mcp.disconnect()

    return StreamingResponse(event_stream(), media_type="text/event-stream")

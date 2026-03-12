from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, Depends

from mcp4xray.auth import require_auth
from mcp4xray.llm import create_llm_backend

router = APIRouter()


@router.get("/conversations")
async def list_conversations(
    request: Request,
    user: dict = Depends(require_auth),
    server_name: str | None = None,
    model: str | None = None,
):
    db = request.app.state.db
    convs = await db.get_conversations(user["user_id"], server_name=server_name, model=model)
    return {"conversations": convs}


@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: int, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    messages = await db.get_messages(conv_id)
    return {"messages": messages}


_TITLE_MODELS = [
    ("anthropic", "claude-haiku-4-5-20251001"),
    ("openai", "gpt-4o-mini"),
    ("gemini", "gemini-2.5-flash"),
]


@router.post("/conversations/{conv_id}/generate-title")
async def generate_title(conv_id: int, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db

    messages = await db.get_messages(conv_id)
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), None)
    asst_msg = next((m["content"] for m in messages if m["role"] == "assistant"), None)
    if not user_msg:
        raise HTTPException(status_code=400, detail="No user message found")

    # Try the user's available API keys in preference order
    user_keys = await db.get_user_api_keys(user["user_id"])
    keys_by_provider = {k["provider"]: k["api_key"] for k in user_keys if k["api_key"]}

    provider = None
    model_id = None
    api_key = None
    for p, m in _TITLE_MODELS:
        if p in keys_by_provider:
            provider, model_id, api_key = p, m, keys_by_provider[p]
            break

    if not api_key:
        # No usable key — fall back to truncated user message
        title = user_msg[:30].strip()
        if len(user_msg) > 30:
            title += "..."
        await db.set_conversation_title(conv_id, title)
        return {"title": title}

    prompt = "Title this chat in 2-3 words. No quotes, no punctuation.\n\n"
    prompt += f"User: {user_msg[:200]}\n"
    if asst_msg:
        prompt += f"Assistant: {asst_msg[:200]}"

    llm = create_llm_backend(provider, model_id, api_key=api_key)
    try:
        response = await llm.complete(
            [{"role": "user", "content": prompt}],
            tools=None,
            system_prompt="",
        )
        title = response.text.strip().strip('"\'').split('\n')[0][:30]
    except Exception:
        title = user_msg[:30].strip()
        if len(user_msg) > 30:
            title += "..."

    await db.set_conversation_title(conv_id, title)
    return {"title": title}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    deleted = await db.delete_conversation(conv_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}

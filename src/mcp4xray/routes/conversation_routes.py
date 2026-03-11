from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, Depends

from mcp4xray.auth import require_auth

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


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    deleted = await db.delete_conversation(conv_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}

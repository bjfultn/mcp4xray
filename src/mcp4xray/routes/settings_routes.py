from __future__ import annotations

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from mcp4xray.auth import require_auth

router = APIRouter()

VALID_PROVIDERS = {"anthropic", "openai", "gemini", "ollama"}


def _mask_key(key: str) -> str:
    """Return a masked version of an API key for display."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


class SetKeyRequest(BaseModel):
    provider: str
    api_key: str = ""
    base_url: str = ""


@router.get("/settings/api-keys")
async def get_api_keys(request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    rows = await db.get_user_api_keys(user["user_id"])
    keys = {}
    for row in rows:
        entry = {}
        if row["api_key"]:
            entry["masked_key"] = _mask_key(row["api_key"])
        if row["base_url"]:
            entry["base_url"] = row["base_url"]
        if entry:
            keys[row["provider"]] = entry
    return {"keys": keys}


@router.put("/settings/api-keys")
async def set_api_key(req: SetKeyRequest, request: Request, user: dict = Depends(require_auth)):
    if req.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")
    db = request.app.state.db
    api_key = req.api_key.strip()
    base_url = req.base_url.strip()
    if not api_key and not base_url:
        await db.delete_user_api_key(user["user_id"], req.provider)
    else:
        # If only base_url is set (e.g., ollama), preserve existing api_key
        existing = await db.get_user_provider_settings(user["user_id"], req.provider)
        if existing:
            if not api_key:
                api_key = existing["api_key"]
            if not base_url:
                base_url = existing["base_url"]
        await db.set_user_api_key(user["user_id"], req.provider, api_key, base_url)
    return {"ok": True}


@router.delete("/settings/api-keys/{provider}")
async def delete_api_key(provider: str, request: Request, user: dict = Depends(require_auth)):
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")
    db = request.app.state.db
    await db.delete_user_api_key(user["user_id"], provider)
    return {"ok": True}

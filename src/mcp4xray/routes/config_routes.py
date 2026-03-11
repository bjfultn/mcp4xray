from __future__ import annotations

from fastapi import APIRouter, Request, Depends

from mcp4xray.auth import require_auth

router = APIRouter()


@router.get("/config")
async def get_config(request: Request, user: dict = Depends(require_auth)):
    sc = request.app.state.servers_config
    return {
        "servers": [{"name": s.name, "url": s.url} for s in sc.servers],
        "models": [{"id": m.id, "name": m.name, "provider": m.provider} for m in sc.models],
    }

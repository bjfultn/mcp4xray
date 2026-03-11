from __future__ import annotations

from fastapi import APIRouter, Request, Depends, HTTPException

from mcp4xray.auth import require_auth
from mcp4xray.mcp_client import MCPClient

router = APIRouter()


@router.get("/config")
async def get_config(request: Request, user: dict = Depends(require_auth)):
    sc = request.app.state.servers_config
    return {
        "servers": [{"name": s.name, "url": s.url} for s in sc.servers],
        "models": [{"id": m.id, "name": m.name, "provider": m.provider} for m in sc.models],
    }


@router.get("/server-info")
async def get_server_info(server_name: str, request: Request, user: dict = Depends(require_auth)):
    sc = request.app.state.servers_config
    server = next((s for s in sc.servers if s.name == server_name), None)
    if not server:
        raise HTTPException(status_code=404, detail=f"Unknown server: {server_name}")

    mcp = MCPClient(server.url)
    try:
        await mcp.connect()
        return {
            "name": server.name,
            "url": server.url,
            "instructions": mcp.instructions,
            "tools": mcp.tools,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not connect to {server.name}: {exc}")
    finally:
        await mcp.disconnect()

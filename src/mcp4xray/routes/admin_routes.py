from __future__ import annotations

from fastapi import APIRouter, Request, Depends

from mcp4xray.auth import require_admin

router = APIRouter()


@router.post("/invite")
async def create_invite(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    code = await db.create_invite_code(admin["user_id"])
    return {"code": code}


@router.get("/invites")
async def list_invites(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    codes = await db.list_invite_codes(admin["user_id"])
    return {"invites": codes}


@router.get("/users")
async def list_users(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    users = await db.get_all_users()
    return {"users": users}

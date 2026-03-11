from __future__ import annotations

from fastapi import APIRouter, Request, Depends, HTTPException

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


@router.patch("/users/{user_id}")
async def update_user(request: Request, user_id: int, admin: dict = Depends(require_admin)):
    body = await request.json()
    is_admin = body.get("is_admin")
    if is_admin is None:
        raise HTTPException(status_code=400, detail="Missing is_admin field")
    db = request.app.state.db
    role = "admin" if is_admin else "user"
    updated = await db.update_user_role(user_id, role)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from mcp4xray.auth import verify_password, hash_password, create_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    db = request.app.state.db
    config = request.app.state.app_config
    user = await db.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["id"], user["username"], user["role"], config.jwt_secret)
    return {"token": token, "username": user["username"], "role": user["role"]}


@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    db = request.app.state.db
    config = request.app.state.app_config
    invite = await db.get_invite_code(req.invite_code)
    if not invite or invite["used_by"] is not None:
        raise HTTPException(status_code=400, detail="Invalid or already used invite code")
    existing = await db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    pw_hash = hash_password(req.password)
    user_id = await db.create_user(req.username, pw_hash, "user")
    await db.use_invite_code(req.invite_code, user_id)
    token = create_token(user_id, req.username, "user", config.jwt_secret)
    return {"token": token, "username": req.username, "role": "user"}

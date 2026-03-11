from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from mcp4xray.config import AppConfig, load_config
from mcp4xray.db import Database
from mcp4xray.auth import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_config = AppConfig.from_env()
    servers_config = load_config(os.environ.get("MCP_SERVERS_CONFIG", "servers.json"))
    db = Database(app_config.database_url.replace("sqlite:///", ""))
    await db.initialize()
    existing = await db.get_user_by_username(app_config.admin_username)
    if not existing:
        await db.create_user(
            app_config.admin_username,
            hash_password(app_config.admin_password),
            "admin",
        )
    app.state.db = db
    app.state.app_config = app_config
    app.state.servers_config = servers_config
    yield
    await db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="mcp4xray", lifespan=lifespan)
    from mcp4xray.routes.auth_routes import router as auth_router
    from mcp4xray.routes.admin_routes import router as admin_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api/admin")

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app

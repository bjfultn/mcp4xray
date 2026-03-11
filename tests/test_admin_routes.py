from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from mcp4xray.config import AppConfig, ServersConfig
from mcp4xray.db import Database
from mcp4xray.auth import hash_password


def _build_test_app(db: Database) -> FastAPI:
    """Create a FastAPI app wired to the given Database (no lifespan)."""
    from mcp4xray.routes.auth_routes import router as auth_router
    from mcp4xray.routes.admin_routes import router as admin_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api/admin")

    app.state.db = db
    app.state.app_config = AppConfig(
        jwt_secret="test-secret",
        admin_username="admin",
        admin_password="adminpass",
    )
    app.state.servers_config = ServersConfig(servers=[], models=[])
    return app


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def client(db):
    app = _build_test_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user(db):
    """Create an admin user and return (user_id, username, password)."""
    pw = "adminpass"
    user_id = await db.create_user("admin", hash_password(pw), "admin")
    return user_id, "admin", pw


@pytest_asyncio.fixture
async def admin_token(client, admin_user):
    """Log in as admin and return the JWT token."""
    _, username, password = admin_user
    resp = await client.post("/api/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest_asyncio.fixture
async def admin_headers(admin_token):
    """Return Authorization headers for the admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


class TestListInvites:
    @pytest.mark.asyncio
    async def test_list_invites(self, client, admin_headers, admin_token):
        # Create an invite
        resp = await client.post(
            "/api/admin/invite",
            headers=admin_headers,
        )
        assert resp.status_code == 200

        # List invites and verify count >= 1
        resp = await client.get("/api/admin/invites", headers=admin_headers)
        assert resp.status_code == 200
        invites = resp.json()["invites"]
        assert len(invites) >= 1


class TestListUsers:
    @pytest.mark.asyncio
    async def test_list_users(self, client, admin_headers):
        resp = await client.get("/api/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        users = resp.json()["users"]
        assert len(users) >= 1
        usernames = {u["username"] for u in users}
        assert "admin" in usernames


class TestAdminRequiresAdminRole:
    @pytest.mark.asyncio
    async def test_admin_requires_admin_role(self, client, db, admin_user, admin_headers):
        # Register a normal user via invite code
        admin_id, _, _ = admin_user
        code = await db.create_invite_code(admin_id)
        reg_resp = await client.post(
            "/api/register",
            json={"username": "regular", "password": "pass123", "invite_code": code},
        )
        assert reg_resp.status_code == 200
        user_token = reg_resp.json()["token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # Try to access admin endpoints with regular user token -> 403
        resp = await client.get("/api/admin/invites", headers=user_headers)
        assert resp.status_code == 403

        resp = await client.get("/api/admin/users", headers=user_headers)
        assert resp.status_code == 403

        resp = await client.post("/api/admin/invite", headers=user_headers)
        assert resp.status_code == 403

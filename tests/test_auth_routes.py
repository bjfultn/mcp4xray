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


class TestLogin:
    @pytest.mark.asyncio
    async def test_admin_login_success(self, client, admin_user):
        _, username, password = admin_user
        resp = await client.post("/api/login", json={"username": username, "password": password})
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"
        assert "token" in body

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(self, client, admin_user):
        resp = await client.post("/api/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_401(self, client):
        resp = await client.post("/api/login", json={"username": "nobody", "password": "pass"})
        assert resp.status_code == 401


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_with_valid_invite(self, client, admin_token, db, admin_user):
        admin_id, _, _ = admin_user
        code = await db.create_invite_code(admin_id)

        resp = await client.post(
            "/api/register",
            json={"username": "newuser", "password": "newpass", "invite_code": code},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "newuser"
        assert body["role"] == "user"
        assert "token" in body

        # Invite code should now be marked as used
        invite = await db.get_invite_code(code)
        assert invite["used_by"] is not None

    @pytest.mark.asyncio
    async def test_register_with_invalid_invite_returns_400(self, client):
        resp = await client.post(
            "/api/register",
            json={"username": "newuser", "password": "newpass", "invite_code": "bogus"},
        )
        assert resp.status_code == 400
        assert "Invalid" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_with_used_invite_returns_400(self, client, db, admin_user):
        admin_id, _, _ = admin_user
        code = await db.create_invite_code(admin_id)

        # Register first user with this code
        resp = await client.post(
            "/api/register",
            json={"username": "user1", "password": "pass1", "invite_code": code},
        )
        assert resp.status_code == 200

        # Attempt to reuse the same invite code
        resp = await client.post(
            "/api/register",
            json={"username": "user2", "password": "pass2", "invite_code": code},
        )
        assert resp.status_code == 400
        assert "Invalid or already used" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_duplicate_username_returns_400(self, client, db, admin_user):
        admin_id, _, _ = admin_user
        code1 = await db.create_invite_code(admin_id)
        code2 = await db.create_invite_code(admin_id)

        resp = await client.post(
            "/api/register",
            json={"username": "dup", "password": "pass", "invite_code": code1},
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/register",
            json={"username": "dup", "password": "pass2", "invite_code": code2},
        )
        assert resp.status_code == 400
        assert "Username already taken" in resp.json()["detail"]


class TestAdminRoutes:
    @pytest.mark.asyncio
    async def test_create_invite_requires_admin(self, client):
        resp = await client.post("/api/admin/invite")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_invite_success(self, client, admin_token):
        resp = await client.post(
            "/api/admin/invite",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "code" in resp.json()

    @pytest.mark.asyncio
    async def test_list_invites(self, client, admin_token):
        # Create two invites
        await client.post(
            "/api/admin/invite",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        await client.post(
            "/api/admin/invite",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        resp = await client.get(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["invites"]) == 2

    @pytest.mark.asyncio
    async def test_list_users(self, client, admin_token):
        resp = await client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        users = resp.json()["users"]
        assert len(users) >= 1
        usernames = {u["username"] for u in users}
        assert "admin" in usernames

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client, db, admin_user):
        # Create a regular user
        admin_id, _, _ = admin_user
        code = await db.create_invite_code(admin_id)
        reg_resp = await client.post(
            "/api/register",
            json={"username": "regular", "password": "pass", "invite_code": code},
        )
        user_token = reg_resp.json()["token"]

        resp = await client.post(
            "/api/admin/invite",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

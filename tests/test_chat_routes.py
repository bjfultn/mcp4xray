from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from mcp4xray.config import AppConfig, ServersConfig, ServerEntry, ModelEntry
from mcp4xray.db import Database
from mcp4xray.auth import hash_password, create_token


def _build_test_app(db: Database) -> FastAPI:
    """Create a FastAPI app wired to the given Database (no lifespan)."""
    from mcp4xray.routes.auth_routes import router as auth_router
    from mcp4xray.routes.admin_routes import router as admin_router
    from mcp4xray.routes.config_routes import router as config_router
    from mcp4xray.routes.chat_routes import router as chat_router
    from mcp4xray.routes.conversation_routes import router as conv_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(config_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(conv_router, prefix="/api")

    app.state.db = db
    app.state.app_config = AppConfig(
        jwt_secret="test-secret",
        admin_username="admin",
        admin_password="adminpass",
    )
    app.state.servers_config = ServersConfig(
        servers=[
            ServerEntry(name="chandra", url="http://localhost:9100/mcp"),
            ServerEntry(name="xmm", url="http://localhost:9101/mcp"),
        ],
        models=[
            ModelEntry(id="claude-sonnet", name="Claude Sonnet", provider="anthropic"),
            ModelEntry(id="gpt-4o", name="GPT-4o", provider="openai"),
        ],
    )
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
async def auth_headers(client, admin_user):
    """Log in as admin and return Authorization headers dict."""
    _, username, password = admin_user
    resp = await client.post("/api/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestConfigRoute:
    @pytest.mark.asyncio
    async def test_get_config_requires_auth(self, client):
        resp = await client.get("/api/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_config_returns_servers_and_models(self, client, auth_headers):
        resp = await client.get("/api/config", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["servers"]) == 2
        server_names = {s["name"] for s in body["servers"]}
        assert server_names == {"chandra", "xmm"}

        assert len(body["models"]) == 2
        model_ids = {m["id"] for m in body["models"]}
        assert model_ids == {"claude-sonnet", "gpt-4o"}
        # Each model should have provider info
        for m in body["models"]:
            assert "provider" in m


class TestConversationRoutes:
    @pytest.mark.asyncio
    async def test_get_conversations_empty(self, client, auth_headers):
        resp = await client.get("/api/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []

    @pytest.mark.asyncio
    async def test_get_conversations_after_create(self, client, auth_headers, db, admin_user):
        user_id, _, _ = admin_user
        await db.create_conversation(user_id, "chandra", "claude-sonnet")
        resp = await client.get("/api/conversations", headers=auth_headers)
        assert resp.status_code == 200
        convs = resp.json()["conversations"]
        assert len(convs) == 1
        assert convs[0]["server_name"] == "chandra"

    @pytest.mark.asyncio
    async def test_get_messages(self, client, auth_headers, db, admin_user):
        user_id, _, _ = admin_user
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.add_message(conv_id, "user", "Hello")
        await db.add_message(conv_id, "assistant", "Hi there")

        resp = await client.get(f"/api/conversations/{conv_id}/messages", headers=auth_headers)
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, client, auth_headers, db, admin_user):
        user_id, _, _ = admin_user
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        resp = await client.delete(f"/api/conversations/{conv_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Should be gone now
        resp = await client.get("/api/conversations", headers=auth_headers)
        assert resp.json()["conversations"] == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent_conversation_returns_404(self, client, auth_headers):
        resp = await client.delete("/api/conversations/9999", headers=auth_headers)
        assert resp.status_code == 404


class TestChatRoute:
    @pytest.mark.asyncio
    async def test_chat_requires_auth(self, client):
        resp = await client.post("/api/chat", json={
            "message": "hello",
            "server_name": "chandra",
            "model_id": "claude-sonnet",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_chat_unknown_server_returns_400(self, client, auth_headers):
        resp = await client.post(
            "/api/chat",
            json={
                "message": "hello",
                "server_name": "nonexistent",
                "model_id": "claude-sonnet",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Unknown server" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_chat_unknown_model_returns_400(self, client, auth_headers):
        resp = await client.post(
            "/api/chat",
            json={
                "message": "hello",
                "server_name": "chandra",
                "model_id": "nonexistent-model",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Unknown model" in resp.json()["detail"]

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from mcp4xray.config import AppConfig, ServersConfig, ServerEntry, ModelEntry
from mcp4xray.db import Database
from mcp4xray.auth import hash_password


def _build_test_app(db: Database) -> FastAPI:
    """Create a FastAPI app wired to the given Database (no lifespan)."""
    from mcp4xray.routes.auth_routes import router as auth_router
    from mcp4xray.routes.conversation_routes import router as conv_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
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


class TestListConversationsEmpty:
    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, client, auth_headers):
        resp = await client.get("/api/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []


class TestListConversationsWithFilter:
    @pytest.mark.asyncio
    async def test_list_conversations_with_filter(self, client, auth_headers, db, admin_user):
        user_id, _, _ = admin_user
        await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.create_conversation(user_id, "xmm", "claude-sonnet")
        await db.create_conversation(user_id, "chandra", "claude-sonnet")

        # Filter by server_name=chandra
        resp = await client.get(
            "/api/conversations",
            params={"server_name": "chandra"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        convs = resp.json()["conversations"]
        assert len(convs) == 2
        assert all(c["server_name"] == "chandra" for c in convs)

        # Filter by server_name=xmm
        resp = await client.get(
            "/api/conversations",
            params={"server_name": "xmm"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        convs = resp.json()["conversations"]
        assert len(convs) == 1
        assert convs[0]["server_name"] == "xmm"


class TestDeleteConversation:
    @pytest.mark.asyncio
    async def test_delete_conversation(self, client, auth_headers, db, admin_user):
        user_id, _, _ = admin_user
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        # Delete the conversation
        resp = await client.delete(f"/api/conversations/{conv_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify it is gone
        resp = await client.get("/api/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []


class TestGetMessages:
    @pytest.mark.asyncio
    async def test_get_messages(self, client, auth_headers, db, admin_user):
        user_id, _, _ = admin_user
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.add_message(conv_id, "user", "What is Cas A?")
        await db.add_message(conv_id, "assistant", "Cas A is a supernova remnant.")
        await db.add_message(conv_id, "user", "Tell me more.")

        resp = await client.get(
            f"/api/conversations/{conv_id}/messages",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert len(msgs) == 3
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "What is Cas A?"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["role"] == "user"

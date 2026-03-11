# mcp4xray Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web-based chat UI that connects to remote X-ray astronomy MCP servers, supports multiple LLM providers, and persists conversations per user.

**Architecture:** FastAPI backend serves a vanilla HTML/JS frontend. The backend connects to one remote MCP server at a time (streamable-http transport), discovers tools dynamically, and runs an agentic loop (LLM → tool call → tool result → LLM) streaming each step to the browser via SSE. SQLite stores users, invite codes, and chat history. JWT handles auth.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, httpx, mcp (Python SDK), PyJWT, bcrypt, aiosqlite, SQLite, Docker Compose

---

## File Structure

```
mcp4xray/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── servers.json                     # MCP server registry
├── .env.example                     # Template for env vars
├── src/
│   └── mcp4xray/
│       ├── __init__.py
│       ├── main.py                  # Entrypoint: uvicorn app
│       ├── app.py                   # FastAPI app factory, lifespan
│       ├── config.py                # Load servers.json + env vars
│       ├── db.py                    # SQLite schema, connection, queries
│       ├── auth.py                  # Password hashing, JWT, FastAPI deps
│       ├── llm.py                   # Multi-provider LLM abstraction
│       ├── mcp_client.py            # MCP streamable-http client wrapper
│       ├── chat.py                  # Agentic loop: LLM + MCP tool calls
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── auth_routes.py       # POST /api/login, POST /api/register
│       │   ├── config_routes.py     # GET /api/config (servers, models)
│       │   ├── chat_routes.py       # POST /api/chat (SSE stream)
│       │   ├── conversation_routes.py # GET/DELETE /api/conversations
│       │   └── admin_routes.py      # POST /api/invite, GET /api/users
│       └── static/
│           ├── index.html           # Chat page (redirects to login if unauthed)
│           ├── login.html           # Login + register forms
│           ├── admin.html           # Admin panel
│           ├── app.js               # Chat UI logic + SSE handling
│           ├── auth.js              # Login/register logic
│           ├── admin.js             # Admin panel logic
│           └── style.css            # All styles
├── tests/
│   ├── conftest.py                  # Fixtures: test db, test client, auth helpers
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_auth.py
│   ├── test_llm.py
│   ├── test_mcp_client.py
│   ├── test_chat.py
│   ├── test_auth_routes.py
│   ├── test_chat_routes.py
│   ├── test_admin_routes.py
│   └── test_conversation_routes.py
└── laiss_hack/                      # Reference code (not part of build)
```

Each source file has one clear responsibility. The `routes/` package keeps endpoint definitions separate from business logic in the top-level modules.

---

## Chunk 1: Project Scaffolding, Config, and Database

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/mcp4xray/__init__.py`
- Create: `src/mcp4xray/main.py`
- Create: `.env.example`
- Create: `servers.json`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "mcp4xray"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "httpx>=0.28",
    "mcp>=1.0",
    "PyJWT>=2.9",
    "bcrypt>=4.2",
    "aiosqlite>=0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx",  # for TestClient
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create `src/mcp4xray/__init__.py`**

Empty file.

- [ ] **Step 3: Create `src/mcp4xray/main.py`**

```python
import uvicorn

def main():
    uvicorn.run("mcp4xray.app:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `.env.example`**

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
JWT_SECRET=change-this-to-a-random-string
DATABASE_URL=sqlite:///./mcp4xray.db
MCP_SERVERS_CONFIG=servers.json
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
```

- [ ] **Step 5: Create `servers.json`**

```json
{
  "servers": [
    {
      "name": "Chandra",
      "url": "https://chandra-mcp.example.com/mcp"
    },
    {
      "name": "XMM-Newton",
      "url": "https://xmm-mcp.example.com/mcp"
    }
  ],
  "models": [
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet", "provider": "anthropic"},
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "gemini"},
    {"id": "llama3", "name": "Llama 3 (local)", "provider": "ollama"}
  ]
}
```

- [ ] **Step 6: Install dependencies**

Run: `cd /path/to/mcp4xray && pip install -e ".[dev]"`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/mcp4xray/__init__.py src/mcp4xray/main.py .env.example servers.json
git commit -m "feat: project scaffolding with dependencies and config template"
```

---

### Task 2: Configuration module

**Files:**
- Create: `src/mcp4xray/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

```python
# tests/test_config.py
import json
import os
import tempfile
import pytest
from mcp4xray.config import load_config, AppConfig

def test_load_config_from_file():
    data = {
        "servers": [{"name": "TestMission", "url": "http://localhost:9000/mcp"}],
        "models": [{"id": "test-model", "name": "Test", "provider": "openai"}],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        config = load_config(f.name)
    os.unlink(f.name)
    assert len(config.servers) == 1
    assert config.servers[0].name == "TestMission"
    assert len(config.models) == 1

def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path.json")

def test_app_config_env_vars(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "testadmin")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    config = AppConfig.from_env()
    assert config.jwt_secret == "test-secret"
    assert config.admin_username == "testadmin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — module does not exist yet

- [ ] **Step 3: Implement config module**

```python
# src/mcp4xray/config.py
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ServerEntry:
    name: str
    url: str

@dataclass
class ModelEntry:
    id: str
    name: str
    provider: str  # "anthropic", "openai", "gemini", "ollama"

@dataclass
class ServersConfig:
    servers: list[ServerEntry]
    models: list[ModelEntry]

@dataclass
class AppConfig:
    jwt_secret: str
    admin_username: str
    admin_password: str
    database_url: str = "sqlite:///./mcp4xray.db"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            jwt_secret=os.environ.get("JWT_SECRET", "dev-secret-change-me"),
            admin_username=os.environ.get("ADMIN_USERNAME", "admin"),
            admin_password=os.environ.get("ADMIN_PASSWORD", "changeme"),
            database_url=os.environ.get("DATABASE_URL", "sqlite:///./mcp4xray.db"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        )

def load_config(path: str) -> ServersConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = json.loads(config_path.read_text())
    servers = [ServerEntry(**s) for s in data.get("servers", [])]
    models = [ModelEntry(**m) for m in data.get("models", [])]
    return ServersConfig(servers=servers, models=models)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp4xray/config.py tests/test_config.py
git commit -m "feat: config module for servers.json and env vars"
```

---

### Task 3: Database module

**Files:**
- Create: `src/mcp4xray/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for database operations**

```python
# tests/test_db.py
import pytest
from mcp4xray.db import Database

@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()

@pytest.mark.asyncio
async def test_create_user(db):
    user_id = await db.create_user("alice", "hashed_pw", "user")
    assert user_id is not None
    user = await db.get_user_by_username("alice")
    assert user["username"] == "alice"
    assert user["role"] == "user"

@pytest.mark.asyncio
async def test_create_duplicate_user(db):
    await db.create_user("alice", "hashed_pw", "user")
    with pytest.raises(Exception):
        await db.create_user("alice", "hashed_pw2", "user")

@pytest.mark.asyncio
async def test_create_and_use_invite_code(db):
    admin_id = await db.create_user("admin", "hashed_pw", "admin")
    code = await db.create_invite_code(admin_id)
    assert len(code) > 0
    invite = await db.get_invite_code(code)
    assert invite is not None
    assert invite["used_by"] is None
    user_id = await db.create_user("bob", "hashed_pw", "user")
    await db.use_invite_code(code, user_id)
    invite = await db.get_invite_code(code)
    assert invite["used_by"] == user_id

@pytest.mark.asyncio
async def test_conversations_and_messages(db):
    user_id = await db.create_user("alice", "hashed_pw", "user")
    conv_id = await db.create_conversation(user_id, "Chandra", "gpt-4o")
    await db.add_message(conv_id, "user", "Hello")
    await db.add_message(conv_id, "assistant", "Hi there")
    messages = await db.get_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    convs = await db.get_conversations(user_id)
    assert len(convs) == 1
```

- [ ] **Step 2: Create test conftest**

```python
# tests/conftest.py
import pytest

pytest_plugins = []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 4: Implement database module**

```python
# src/mcp4xray/db.py
from __future__ import annotations
import secrets
import time
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS invite_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    used_by INTEGER REFERENCES users(id),
    created_at REAL NOT NULL,
    used_at REAL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    server_name TEXT NOT NULL,
    model TEXT NOT NULL,
    title TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL
);
"""

class Database:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self):
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def create_user(self, username: str, password_hash: str, role: str) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, time.time()),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_user_by_username(self, username: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_invite_code(self, created_by: int) -> str:
        code = secrets.token_urlsafe(16)
        await self._conn.execute(
            "INSERT INTO invite_codes (code, created_by, created_at) VALUES (?, ?, ?)",
            (code, created_by, time.time()),
        )
        await self._conn.commit()
        return code

    async def get_invite_code(self, code: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def use_invite_code(self, code: str, user_id: int):
        await self._conn.execute(
            "UPDATE invite_codes SET used_by = ?, used_at = ? WHERE code = ?",
            (user_id, time.time(), code),
        )
        await self._conn.commit()

    async def list_invite_codes(self, created_by: int) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT * FROM invite_codes WHERE created_by = ? ORDER BY created_at DESC",
            (created_by,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def create_conversation(self, user_id: int, server_name: str, model: str) -> int:
        now = time.time()
        cursor = await self._conn.execute(
            "INSERT INTO conversations (user_id, server_name, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, server_name, model, now, now),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_conversations(
        self, user_id: int, server_name: str | None = None, model: str | None = None
    ) -> list[dict]:
        query = "SELECT * FROM conversations WHERE user_id = ?"
        params: list = [user_id]
        if server_name:
            query += " AND server_name = ?"
            params.append(server_name)
        if model:
            query += " AND model = ?"
            params.append(model)
        query += " ORDER BY updated_at DESC"
        cursor = await self._conn.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def add_message(self, conversation_id: int, role: str, content: str) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, time.time()),
        )
        await self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.time(), conversation_id),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_messages(self, conversation_id: int) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
            (conversation_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_all_users(self) -> list[dict]:
        cursor = await self._conn.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at")
        return [dict(row) for row in await cursor.fetchall()]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/mcp4xray/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: database module with users, invite codes, conversations, messages"
```

---

## Chunk 2: Authentication

### Task 4: Auth module

**Files:**
- Create: `src/mcp4xray/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import pytest
from mcp4xray.auth import hash_password, verify_password, create_token, decode_token

def test_password_hash_and_verify():
    pw_hash = hash_password("mysecret")
    assert verify_password("mysecret", pw_hash)
    assert not verify_password("wrong", pw_hash)

def test_create_and_decode_token():
    token = create_token(user_id=1, username="alice", role="user", secret="test-secret")
    payload = decode_token(token, secret="test-secret")
    assert payload["user_id"] == 1
    assert payload["username"] == "alice"
    assert payload["role"] == "user"

def test_decode_invalid_token():
    with pytest.raises(Exception):
        decode_token("garbage", secret="test-secret")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement auth module**

```python
# src/mcp4xray/auth.py
from __future__ import annotations
import time
import bcrypt
import jwt

TOKEN_EXPIRY_SECONDS = 86400  # 24 hours

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_token(user_id: int, username: str, role: str, secret: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": time.time() + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])

# --- FastAPI dependencies (used by route modules) ---

from fastapi import Request, HTTPException

async def require_auth(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return decode_token(auth[7:], request.app.state.app_config.jwt_secret)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(request: Request) -> dict:
    user = await require_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp4xray/auth.py tests/test_auth.py
git commit -m "feat: auth module with password hashing and JWT tokens"
```

---

### Task 5: Auth routes (login + register)

**Files:**
- Create: `src/mcp4xray/routes/__init__.py`
- Create: `src/mcp4xray/routes/auth_routes.py`
- Create: `tests/test_auth_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from mcp4xray.app import create_app

@pytest.fixture
async def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("MCP_SERVERS_CONFIG", "servers.json")
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_login_admin(client):
    resp = await client.post("/api/login", json={"username": "admin", "password": "adminpass"})
    assert resp.status_code == 200
    assert "token" in resp.json()

@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_register_with_invite_code(client):
    # Login as admin, create invite code, register new user
    login = await client.post("/api/login", json={"username": "admin", "password": "adminpass"})
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    invite_resp = await client.post("/api/admin/invite", headers=headers)
    assert invite_resp.status_code == 200
    code = invite_resp.json()["code"]
    reg_resp = await client.post("/api/register", json={
        "username": "researcher1",
        "password": "secret123",
        "invite_code": code,
    })
    assert reg_resp.status_code == 200
    assert "token" in reg_resp.json()

@pytest.mark.asyncio
async def test_register_invalid_invite_code(client):
    resp = await client.post("/api/register", json={
        "username": "hacker",
        "password": "password",
        "invite_code": "invalid-code",
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_routes.py -v`
Expected: FAIL — app module not ready

- [ ] **Step 3: Create the FastAPI app factory**

```python
# src/mcp4xray/app.py
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
    # Bootstrap admin user
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
```

- [ ] **Step 4: Implement auth routes**

```python
# src/mcp4xray/routes/__init__.py
# empty

# src/mcp4xray/routes/auth_routes.py
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
```

- [ ] **Step 5: Implement admin routes (invite code generation)**

```python
# src/mcp4xray/routes/admin_routes.py
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_auth_routes.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/mcp4xray/app.py src/mcp4xray/routes/ tests/test_auth_routes.py
git commit -m "feat: auth routes with login, registration, and admin invite codes"
```

---

## Chunk 3: LLM Backends and MCP Client

### Task 6: LLM backend abstraction

**Files:**
- Create: `src/mcp4xray/llm.py`
- Create: `tests/test_llm.py`

The key improvement over `laiss_hack/client.py`: use each provider's **native tool/function calling** API instead of prompting the LLM to output JSON manually. This is more reliable and supports streaming.

- [ ] **Step 1: Write failing tests for tool schema conversion and LLM backend construction**

```python
# tests/test_llm.py
import pytest
from mcp4xray.llm import (
    mcp_tools_to_openai,
    mcp_tools_to_anthropic,
    mcp_tools_to_gemini,
    create_llm_backend,
)

SAMPLE_MCP_TOOL = {
    "name": "query_tap",
    "description": "Run an ADQL query",
    "inputSchema": {
        "type": "object",
        "properties": {
            "adql": {"type": "string", "description": "The ADQL query"},
            "max_rows": {"type": "integer", "default": 100},
        },
        "required": ["adql"],
    },
}

def test_mcp_tools_to_openai():
    result = mcp_tools_to_openai([SAMPLE_MCP_TOOL])
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "query_tap"
    assert "adql" in result[0]["function"]["parameters"]["properties"]

def test_mcp_tools_to_anthropic():
    result = mcp_tools_to_anthropic([SAMPLE_MCP_TOOL])
    assert len(result) == 1
    assert result[0]["name"] == "query_tap"
    assert result[0]["input_schema"]["type"] == "object"

def test_mcp_tools_to_gemini():
    result = mcp_tools_to_gemini([SAMPLE_MCP_TOOL])
    assert len(result) == 1
    assert result[0]["name"] == "query_tap"
    assert "parameters" in result[0]

def test_create_llm_backend_openai():
    backend = create_llm_backend("openai", "gpt-4o", api_key="test-key")
    assert backend.provider == "openai"

def test_create_llm_backend_ollama():
    backend = create_llm_backend("ollama", "llama3")
    assert backend.provider == "ollama"
    assert "11434" in backend.base_url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL

- [ ] **Step 3: Implement LLM module**

The module provides:
- Tool schema converters (MCP → provider-native format)
- `LLMBackend` class with async `complete()` that accepts messages + tools, returns a standardized response containing either text content or tool calls
- Streaming support via async `stream()` method

```python
# src/mcp4xray/llm.py
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
import httpx

# --- Tool schema converters ---

def mcp_tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]

def mcp_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]

def mcp_tools_to_gemini(tools: list[dict]) -> list[dict]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]

# --- Standardized response types ---

@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]

@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

@dataclass
class StreamEvent:
    type: str  # "text", "tool_call", "done"
    text: str = ""
    tool_call: ToolCall | None = None

# --- Backend ---

PROVIDER_DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1"},
}

class LLMBackend:
    def __init__(self, provider: str, model: str, api_key: str = "", base_url: str = ""):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")

    async def complete(
        self, messages: list[dict], tools: list[dict], system_prompt: str = ""
    ) -> LLMResponse:
        if self.provider in ("openai", "ollama"):
            return await self._complete_openai(messages, tools, system_prompt)
        if self.provider == "anthropic":
            return await self._complete_anthropic(messages, tools, system_prompt)
        if self.provider == "gemini":
            return await self._complete_gemini(messages, tools, system_prompt)
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def _complete_openai(
        self, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> LLMResponse:
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)
        payload: dict[str, Any] = {"model": self.model, "messages": api_messages}
        openai_tools = mcp_tools_to_openai(tools)
        if openai_tools:
            payload["tools"] = openai_tools
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]["message"]
        result = LLMResponse(text=choice.get("content") or "")
        for tc in choice.get("tool_calls") or []:
            fn = tc["function"]
            result.tool_calls.append(
                ToolCall(name=fn["name"], arguments=json.loads(fn["arguments"]))
            )
        return result

    async def _complete_anthropic(
        self, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        anthropic_tools = mcp_tools_to_anthropic(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url.rstrip('/')}/messages", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        result = LLMResponse()
        for block in data.get("content", []):
            if block["type"] == "text":
                result.text += block["text"]
            elif block["type"] == "tool_use":
                result.tool_calls.append(
                    ToolCall(name=block["name"], arguments=block["input"])
                )
        return result

    async def _complete_gemini(
        self, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> LLMResponse:
        contents = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        payload: dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        gemini_tools = mcp_tools_to_gemini(tools)
        if gemini_tools:
            payload["tools"] = [{"functionDeclarations": gemini_tools}]
        url = (
            f"{self.base_url.rstrip('/')}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        result = LLMResponse()
        candidate = data.get("candidates", [{}])[0]
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                result.text += part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                result.tool_calls.append(
                    ToolCall(name=fc["name"], arguments=fc.get("args", {}))
                )
        return result

    def append_tool_interaction(
        self, messages: list[dict], tool_name: str, arguments: dict, result: dict
    ) -> list[dict]:
        """Append a tool call + result to the message list in provider-native format."""
        result_text = json.dumps(result)
        if self.provider in ("openai", "ollama"):
            # OpenAI: assistant with tool_calls + role:tool with tool_call_id
            call_id = f"call_{tool_name}_{len(messages)}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": call_id, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(arguments)}}],
            })
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result_text})
        elif self.provider == "anthropic":
            # Anthropic: assistant with tool_use block + user with tool_result block
            tool_use_id = f"toolu_{tool_name}_{len(messages)}"
            messages.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": arguments}],
            })
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result_text}],
            })
        elif self.provider == "gemini":
            # Gemini: model with functionCall + user with functionResponse
            messages.append({
                "role": "assistant",
                "content": json.dumps({"functionCall": {"name": tool_name, "args": arguments}}),
            })
            messages.append({
                "role": "user",
                "content": json.dumps({"functionResponse": {"name": tool_name, "response": result}}),
            })
        return messages

def create_llm_backend(provider: str, model: str, api_key: str = "", base_url: str = "") -> LLMBackend:
    return LLMBackend(provider=provider, model=model, api_key=api_key, base_url=base_url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp4xray/llm.py tests/test_llm.py
git commit -m "feat: multi-provider LLM backend with native tool calling"
```

---

### Task 7: MCP client wrapper

**Files:**
- Create: `src/mcp4xray/mcp_client.py`
- Create: `tests/test_mcp_client.py`

Wraps the MCP Python SDK's `streamable-http` client transport. Provides connect/disconnect/list_tools/call_tool.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_mcp_client.py
import pytest
from mcp4xray.mcp_client import MCPClient, serialize_tool, normalize_tool_result

def test_serialize_tool_from_dict():
    tool = {"name": "foo", "description": "does foo", "inputSchema": {"type": "object"}}
    result = serialize_tool(tool)
    assert result["name"] == "foo"

def test_normalize_tool_result_text():
    # Test with a simple dict simulating a text content block
    result = normalize_tool_result({"content": [{"type": "text", "text": "hello"}], "isError": False})
    assert result["is_error"] is False
    assert "hello" in str(result["content"])

def test_mcp_client_init():
    client = MCPClient("http://localhost:9000/mcp")
    assert client.url == "http://localhost:9000/mcp"
    assert client.session is None
    assert client.tools == []
    assert client.instructions == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MCP client wrapper**

```python
# src/mcp4xray/mcp_client.py
from __future__ import annotations
import json
from typing import Any
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

def serialize_tool(tool: Any) -> dict[str, Any]:
    if isinstance(tool, dict):
        return tool
    if hasattr(tool, "model_dump"):
        return tool.model_dump(mode="json")
    return {
        "name": getattr(tool, "name", None),
        "description": getattr(tool, "description", None),
        "inputSchema": getattr(tool, "inputSchema", None),
    }

def normalize_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return {
            "is_error": result.get("isError", False),
            "content": result.get("content", []),
        }
    content = []
    for item in getattr(result, "content", []):
        if hasattr(item, "model_dump"):
            content.append(item.model_dump(mode="json"))
        else:
            content.append(str(item))
    return {
        "is_error": getattr(result, "isError", False),
        "content": content,
    }

class MCPClient:
    def __init__(self, url: str):
        self.url = url
        self.session: ClientSession | None = None
        self.tools: list[dict[str, Any]] = []
        self.instructions: str = ""
        self._client_cm = None
        self._session_cm = None

    async def connect(self):
        self._client_cm = streamablehttp_client(self.url)
        streams = await self._client_cm.__aenter__()
        read_stream, write_stream, _ = streams
        self._session_cm = ClientSession(read_stream, write_stream)
        self.session = await self._session_cm.__aenter__()
        init_result = await self.session.initialize()
        self.instructions = getattr(init_result, "instructions", "") or ""
        tools_result = await self.session.list_tools()
        self.tools = [serialize_tool(t) for t in tools_result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        result = await self.session.call_tool(name, arguments)
        return normalize_tool_result(result)

    async def disconnect(self):
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._client_cm:
            await self._client_cm.__aexit__(None, None, None)
        self.session = None
        self.tools = []
        self.instructions = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp4xray/mcp_client.py tests/test_mcp_client.py
git commit -m "feat: MCP client wrapper for streamable-http transport"
```

---

## Chunk 4: Chat Loop and API Routes

### Task 8: Agentic chat loop

**Files:**
- Create: `src/mcp4xray/chat.py`
- Create: `tests/test_chat.py`

The chat loop: takes user message + conversation history, runs the agentic cycle (LLM → tool call → MCP → LLM → ...), yields streaming events for each step.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_chat.py
import pytest
from unittest.mock import AsyncMock
from mcp4xray.chat import run_chat_turn, ChatEvent
from mcp4xray.llm import LLMResponse, ToolCall

@pytest.mark.asyncio
async def test_chat_turn_text_only():
    """LLM responds with text, no tool calls."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = LLMResponse(text="The answer is 42.")
    mock_mcp = AsyncMock()
    mock_mcp.tools = []
    mock_mcp.instructions = "You are helpful."

    events = []
    async for event in run_chat_turn(
        llm=mock_llm,
        mcp=mock_mcp,
        messages=[{"role": "user", "content": "What is the answer?"}],
    ):
        events.append(event)

    assert any(e.type == "text" and "42" in e.content for e in events)
    assert events[-1].type == "done"

@pytest.mark.asyncio
async def test_chat_turn_with_tool_call():
    """LLM makes a tool call, then responds with text."""
    mock_llm = AsyncMock()
    mock_llm.complete.side_effect = [
        LLMResponse(tool_calls=[ToolCall(name="query_tap", arguments={"adql": "SELECT *"})]),
        LLMResponse(text="Found 5 sources."),
    ]
    mock_mcp = AsyncMock()
    mock_mcp.tools = [{"name": "query_tap", "description": "Run query", "inputSchema": {}}]
    mock_mcp.instructions = ""
    mock_mcp.call_tool.return_value = {"is_error": False, "content": [{"type": "text", "text": "5 rows"}]}

    events = []
    async for event in run_chat_turn(
        llm=mock_llm, mcp=mock_mcp,
        messages=[{"role": "user", "content": "Find sources"}],
    ):
        events.append(event)

    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "text" in types
    assert events[-1].type == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat.py -v`
Expected: FAIL

- [ ] **Step 3: Implement chat loop**

```python
# src/mcp4xray/chat.py
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator
from mcp4xray.llm import LLMBackend, LLMResponse

MAX_TOOL_ITERATIONS = 10

@dataclass
class ChatEvent:
    type: str  # "text", "tool_call", "tool_result", "error", "done"
    content: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] | None = None

async def run_chat_turn(
    llm: LLMBackend,
    mcp: Any,  # MCPClient
    messages: list[dict[str, str]],
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> AsyncIterator[ChatEvent]:
    system_prompt = getattr(mcp, "instructions", "") or ""
    tools = getattr(mcp, "tools", []) or []
    working_messages = list(messages)

    for _ in range(max_iterations):
        try:
            response: LLMResponse = await llm.complete(working_messages, tools, system_prompt)
        except Exception as exc:
            yield ChatEvent(type="error", content=str(exc))
            yield ChatEvent(type="done")
            return

        if response.text:
            yield ChatEvent(type="text", content=response.text)

        if not response.tool_calls:
            yield ChatEvent(type="done")
            return

        for tc in response.tool_calls:
            yield ChatEvent(
                type="tool_call",
                tool_name=tc.name,
                tool_args=tc.arguments,
                content=json.dumps({"name": tc.name, "arguments": tc.arguments}),
            )
            try:
                result = await mcp.call_tool(tc.name, tc.arguments)
            except Exception as exc:
                result = {"is_error": True, "content": [{"type": "text", "text": str(exc)}]}

            result_text = json.dumps(result)
            yield ChatEvent(type="tool_result", tool_name=tc.name, content=result_text)

            # Append tool interaction to working messages using the LLM backend's
            # provider-native format (see llm.py format_tool_messages).
            working_messages = llm.append_tool_interaction(
                working_messages, tc.name, tc.arguments, result
            )

    yield ChatEvent(type="error", content="Max tool iterations reached")
    yield ChatEvent(type="done")
```

**Important:** The `LLMBackend.append_tool_interaction()` method formats tool call/result
messages in the provider-native format:
- **OpenAI/Ollama:** assistant message with `tool_calls` array + `role: "tool"` message with `tool_call_id`
- **Anthropic:** assistant message with `tool_use` content block + user message with `tool_result` content block
- **Gemini:** model message with `functionCall` part + user message with `functionResponse` part

This must be added to `llm.py` alongside `complete()`. The `complete()` method already
knows how to send provider-native tool definitions; `append_tool_interaction()` handles
the response-side formatting so multi-turn tool calling works correctly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp4xray/chat.py tests/test_chat.py
git commit -m "feat: agentic chat loop with tool call cycling"
```

---

### Task 9: Chat and config API routes

**Files:**
- Create: `src/mcp4xray/routes/config_routes.py`
- Create: `src/mcp4xray/routes/chat_routes.py`
- Create: `src/mcp4xray/routes/conversation_routes.py`
- Create: `tests/test_chat_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_chat_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from mcp4xray.app import create_app

@pytest.fixture
async def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("MCP_SERVERS_CONFIG", "servers.json")
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/api/login", json={"username": "admin", "password": "adminpass"})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_get_config(client, auth_headers):
    resp = await client.get("/api/config", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "servers" in data
    assert "models" in data

@pytest.mark.asyncio
async def test_get_conversations_empty(client, auth_headers):
    resp = await client.get("/api/conversations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["conversations"] == []

@pytest.mark.asyncio
async def test_chat_requires_auth(client):
    resp = await client.post("/api/chat", json={"message": "hello", "server_name": "Chandra", "model_id": "gpt-4o"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config routes**

```python
# src/mcp4xray/routes/config_routes.py
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
```

- [ ] **Step 4: Implement conversation routes**

```python
# src/mcp4xray/routes/conversation_routes.py
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException, Depends
from mcp4xray.auth import require_auth

router = APIRouter()

@router.get("/conversations")
async def list_conversations(
    request: Request,
    user: dict = Depends(require_auth),
    server_name: str | None = None,
    model: str | None = None,
):
    db = request.app.state.db
    convs = await db.get_conversations(user["user_id"], server_name=server_name, model=model)
    return {"conversations": convs}

@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: int, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    messages = await db.get_messages(conv_id)
    return {"messages": messages}

@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    deleted = await db.delete_conversation(conv_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}
```

- [ ] **Step 5: Implement chat route (SSE streaming)**

```python
# src/mcp4xray/routes/chat_routes.py
from __future__ import annotations
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from mcp4xray.auth import require_auth
from mcp4xray.llm import create_llm_backend
from mcp4xray.mcp_client import MCPClient
from mcp4xray.chat import run_chat_turn

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    server_name: str
    model_id: str
    provider: str = ""
    conversation_id: int | None = None

@router.post("/chat")
async def chat(req: ChatRequest, request: Request, user: dict = Depends(require_auth)):
    db = request.app.state.db
    app_config = request.app.state.app_config
    servers_config = request.app.state.servers_config

    # Find server URL
    server = next((s for s in servers_config.servers if s.name == req.server_name), None)
    if not server:
        raise HTTPException(status_code=400, detail=f"Unknown server: {req.server_name}")

    # Find model config
    model_entry = next((m for m in servers_config.models if m.id == req.model_id), None)
    if not model_entry:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model_id}")

    # Resolve API key
    api_key_map = {
        "anthropic": app_config.anthropic_api_key,
        "openai": app_config.openai_api_key,
        "gemini": app_config.gemini_api_key,
        "ollama": "",
    }
    api_key = api_key_map.get(model_entry.provider, "")

    # Create or load conversation
    # NOTE: When resuming, we load all message roles including tool_call/tool_result
    # so the LLM sees the full interaction history. The LLM backend's complete()
    # method must handle these roles in its provider-native format.
    if req.conversation_id:
        conv_id = req.conversation_id
        prev_messages = await db.get_messages(conv_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in prev_messages]
    else:
        conv_id = await db.create_conversation(user["user_id"], req.server_name, req.model_id)
        messages = []

    # Add new user message
    messages.append({"role": "user", "content": req.message})
    await db.add_message(conv_id, "user", req.message)

    llm = create_llm_backend(model_entry.provider, model_entry.id, api_key=api_key)

    async def event_stream():
        mcp = MCPClient(server.url)
        try:
            await mcp.connect()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': f'MCP connection failed: {exc}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"
            return

        full_text = ""
        try:
            async for event in run_chat_turn(llm=llm, mcp=mcp, messages=messages):
                payload = {"type": event.type, "content": event.content}
                if event.tool_name:
                    payload["tool_name"] = event.tool_name
                if event.tool_args is not None:
                    payload["tool_args"] = event.tool_args
                if event.type == "done":
                    payload["conversation_id"] = conv_id
                yield f"data: {json.dumps(payload)}\n\n"

                if event.type == "text":
                    full_text += event.content
                elif event.type == "tool_call":
                    await db.add_message(conv_id, "tool_call", event.content)
                elif event.type == "tool_result":
                    await db.add_message(conv_id, "tool_result", event.content)
        finally:
            if full_text:
                await db.add_message(conv_id, "assistant", full_text)
            await mcp.disconnect()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 6: Wire new routes into app.py**

Update `create_app()` in `src/mcp4xray/app.py` to include the new routers:

```python
from mcp4xray.routes.config_routes import router as config_router
from mcp4xray.routes.chat_routes import router as chat_router
from mcp4xray.routes.conversation_routes import router as conv_router
app.include_router(config_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(conv_router, prefix="/api")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_chat_routes.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/mcp4xray/routes/config_routes.py src/mcp4xray/routes/chat_routes.py \
    src/mcp4xray/routes/conversation_routes.py src/mcp4xray/app.py tests/test_chat_routes.py
git commit -m "feat: chat, config, and conversation API routes with SSE streaming"
```

---

### Task 9b: Admin route tests

**Files:**
- Create: `tests/test_admin_routes.py`

- [ ] **Step 1: Write tests for admin endpoints**

```python
# tests/test_admin_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from mcp4xray.app import create_app

@pytest.fixture
async def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("MCP_SERVERS_CONFIG", "servers.json")
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def admin_headers(client):
    resp = await client.post("/api/login", json={"username": "admin", "password": "adminpass"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}

@pytest.mark.asyncio
async def test_list_invites(client, admin_headers):
    await client.post("/api/admin/invite", headers=admin_headers)
    resp = await client.get("/api/admin/invites", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()["invites"]) >= 1

@pytest.mark.asyncio
async def test_list_users(client, admin_headers):
    resp = await client.get("/api/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    assert any(u["username"] == "admin" for u in resp.json()["users"])

@pytest.mark.asyncio
async def test_admin_requires_admin_role(client, admin_headers):
    # Register a normal user
    invite_resp = await client.post("/api/admin/invite", headers=admin_headers)
    code = invite_resp.json()["code"]
    await client.post("/api/register", json={"username": "user1", "password": "pass", "invite_code": code})
    login_resp = await client.post("/api/login", json={"username": "user1", "password": "pass"})
    user_headers = {"Authorization": f"Bearer {login_resp.json()['token']}"}
    # Normal user cannot access admin endpoints
    resp = await client.get("/api/admin/users", headers=user_headers)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_admin_routes.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_routes.py
git commit -m "test: add admin route tests"
```

---

### Task 9c: Conversation route tests

**Files:**
- Create: `tests/test_conversation_routes.py`

- [ ] **Step 1: Write tests for conversation endpoints**

```python
# tests/test_conversation_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from mcp4xray.app import create_app

@pytest.fixture
async def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("MCP_SERVERS_CONFIG", "servers.json")
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/api/login", json={"username": "admin", "password": "adminpass"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}

@pytest.mark.asyncio
async def test_list_conversations_empty(client, auth_headers):
    resp = await client.get("/api/conversations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["conversations"] == []

@pytest.mark.asyncio
async def test_list_conversations_with_filter(client, auth_headers, app):
    # Create conversations directly via DB for testing
    db = app.state.db
    user = await db.get_user_by_username("admin")
    await db.create_conversation(user["id"], "Chandra", "gpt-4o")
    await db.create_conversation(user["id"], "XMM-Newton", "gpt-4o")
    resp = await client.get("/api/conversations?server_name=Chandra", headers=auth_headers)
    assert len(resp.json()["conversations"]) == 1

@pytest.mark.asyncio
async def test_delete_conversation(client, auth_headers, app):
    db = app.state.db
    user = await db.get_user_by_username("admin")
    conv_id = await db.create_conversation(user["id"], "Chandra", "gpt-4o")
    resp = await client.delete(f"/api/conversations/{conv_id}", headers=auth_headers)
    assert resp.status_code == 200
    resp = await client.get("/api/conversations", headers=auth_headers)
    assert len(resp.json()["conversations"]) == 0

@pytest.mark.asyncio
async def test_get_messages(client, auth_headers, app):
    db = app.state.db
    user = await db.get_user_by_username("admin")
    conv_id = await db.create_conversation(user["id"], "Chandra", "gpt-4o")
    await db.add_message(conv_id, "user", "Hello")
    await db.add_message(conv_id, "assistant", "Hi there")
    resp = await client.get(f"/api/conversations/{conv_id}/messages", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_conversation_routes.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_conversation_routes.py
git commit -m "test: add conversation route tests"
```

---

## Chunk 5: Frontend

### Task 10: Login page

**Files:**
- Create: `src/mcp4xray/static/login.html`
- Create: `src/mcp4xray/static/auth.js`
- Create: `src/mcp4xray/static/style.css`

- [ ] **Step 1: Create `login.html`**

Minimal login/register page with two forms. Login form shown by default, register form toggled via link. On success, stores JWT in localStorage and redirects to `/`.

- [ ] **Step 2: Create `auth.js`**

Handles:
- POST `/api/login` with username/password
- POST `/api/register` with username/password/invite_code
- Store token in `localStorage`
- Redirect to `/` on success
- Show error messages on failure

- [ ] **Step 3: Create `style.css`**

Clean, minimal styling. Dark theme suitable for a research tool. Key elements:
- Centered auth forms
- Chat layout with sidebar + main panel
- Distinct styling for user, assistant, tool_call, tool_result messages
- Collapsible tool call/result blocks

- [ ] **Step 4: Test manually**

Run: `cd /path/to/mcp4xray && python -m mcp4xray.main`
Visit: `http://localhost:8000/login.html`
Expected: Login form renders, admin login works, redirects to `/`

- [ ] **Step 5: Commit**

```bash
git add src/mcp4xray/static/login.html src/mcp4xray/static/auth.js src/mcp4xray/static/style.css
git commit -m "feat: login and registration page"
```

---

### Task 11: Chat page

**Files:**
- Create: `src/mcp4xray/static/index.html`
- Create: `src/mcp4xray/static/app.js`

- [ ] **Step 1: Create `index.html`**

Layout:
- Left sidebar: conversation list, "New Chat" button
- Top bar: mission dropdown, model dropdown, username, logout button
- Main area: message list + input box

If no token in localStorage, redirect to `/login.html`.

- [ ] **Step 2: Create `app.js`**

Handles:
- On load: fetch `/api/config` to populate dropdowns, fetch `/api/conversations` for sidebar
- New chat: POST `/api/chat` with `message`, `server_name`, `model_id`
- SSE streaming: use `fetch()` with `ReadableStream` reader (NOT `EventSource`, which only supports GET). Parse SSE `data:` lines from the stream.
  - `text` events: append to assistant message bubble incrementally
  - `tool_call` events: render as a distinct block showing tool name + arguments
  - `tool_result` events: render as a collapsible block showing the result JSON
  - `done` event: finalize, update conversation list
- Load conversation: GET `/api/conversations/{id}/messages`, render all messages
- Delete conversation: DELETE `/api/conversations/{id}`
- Mission switch: clear chat, update dropdown
- Model switch: update for next message (doesn't reset conversation)

- [ ] **Step 3: Test manually**

Run the server, login, verify:
- Dropdowns populate from config
- Sending a message shows SSE stream (will fail to connect to MCP, which is expected)
- Conversation appears in sidebar

- [ ] **Step 4: Commit**

```bash
git add src/mcp4xray/static/index.html src/mcp4xray/static/app.js
git commit -m "feat: chat page with streaming, tool call display, and conversation sidebar"
```

---

### Task 12: Admin page

**Files:**
- Create: `src/mcp4xray/static/admin.html`
- Create: `src/mcp4xray/static/admin.js`

- [ ] **Step 1: Create `admin.html`**

Simple panel with:
- "Generate Invite Code" button, displays generated codes
- List of existing invite codes with status (used/unused)
- User list table (username, role, created date)
- Link back to chat

- [ ] **Step 2: Create `admin.js`**

Handles:
- POST `/api/admin/invite` → display new code (copyable)
- GET `/api/admin/invites` → list codes
- GET `/api/admin/users` → list users

- [ ] **Step 3: Test manually**

Login as admin, visit `/admin.html`, generate an invite code, verify it appears in the list. Use it to register a new user in an incognito window.

- [ ] **Step 4: Commit**

```bash
git add src/mcp4xray/static/admin.html src/mcp4xray/static/admin.js
git commit -m "feat: admin panel for invite codes and user management"
```

---

## Chunk 6: Integration and Dev Tooling

### Task 13: Mock MCP server for development

**Files:**
- Create: `dev/mock_server.py`

A simple FastMCP server with a couple of stub tools, runnable locally with `streamable-http` transport, so the full stack can be tested end-to-end without real archive servers.

- [ ] **Step 1: Create mock server**

```python
# dev/mock_server.py
from __future__ import annotations
from typing import Any
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="mock-xray-archive",
    instructions=(
        "You are a mock X-ray astronomy archive assistant. "
        "You have access to simulated observation data for testing."
    ),
)

@mcp.tool(name="search_observations", description="Search for X-ray observations by target name or coordinates.")
def search_observations(target: str, radius_arcmin: float = 5.0) -> dict[str, Any]:
    return {
        "target": target,
        "radius_arcmin": radius_arcmin,
        "results": [
            {"obsid": "12345", "target": target, "exposure_ks": 50.0, "instrument": "ACIS-S", "date": "2024-01-15"},
            {"obsid": "67890", "target": target, "exposure_ks": 30.0, "instrument": "ACIS-I", "date": "2023-06-22"},
        ],
    }

@mcp.tool(name="get_observation_details", description="Get detailed metadata for a specific observation by ObsID.")
def get_observation_details(obsid: str) -> dict[str, Any]:
    return {
        "obsid": obsid,
        "target": "Cas A",
        "ra": 350.866,
        "dec": 58.815,
        "exposure_ks": 50.0,
        "instrument": "ACIS-S",
        "grating": "NONE",
        "date": "2024-01-15",
        "pi": "Dr. Example",
        "status": "archived",
    }

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=9000)
```

- [ ] **Step 2: Update `servers.json` to include a local dev entry**

```json
{
  "servers": [
    {"name": "Mock Archive (dev)", "url": "http://127.0.0.1:9000/mcp"},
    {"name": "Chandra", "url": "https://chandra-mcp.example.com/mcp"},
    {"name": "XMM-Newton", "url": "https://xmm-mcp.example.com/mcp"}
  ],
  "models": [
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet", "provider": "anthropic"},
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "gemini"},
    {"id": "llama3", "name": "Llama 3 (local)", "provider": "ollama"}
  ]
}
```

- [ ] **Step 3: Test end-to-end**

Terminal 1: `python dev/mock_server.py`
Terminal 2: `python -m mcp4xray.main`
Browser: Login, select "Mock Archive (dev)" + any model with a valid API key, send "Search for Cas A observations"
Expected: See tool_call event (search_observations), tool_result event (JSON results), then assistant text summarizing.

- [ ] **Step 4: Commit**

```bash
git add dev/mock_server.py servers.json
git commit -m "feat: mock MCP server for end-to-end development testing"
```

---

### Task 14: Docker Compose containerization

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY servers.json .

EXPOSE 8000

CMD ["python", "-m", "mcp4xray.main"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./servers.json:/app/servers.json:ro
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite:///./data/mcp4xray.db
    restart: unless-stopped

  # Optional: mock MCP server for development
  mock-mcp:
    build: .
    command: python /app/dev/mock_server.py
    ports:
      - "9000:9000"
    profiles:
      - dev
    volumes:
      - ./dev:/app/dev:ro
```

- [ ] **Step 3: Create `.dockerignore`**

```
__pycache__
*.pyc
.git
.env
data/
laiss_hack/
tests/
docs/
*.egg-info
.pytest_cache
```

- [ ] **Step 4: Update `src/mcp4xray/main.py` to bind to 0.0.0.0**

Verify `main.py` uses `host="0.0.0.0"` (already set in Task 1).

- [ ] **Step 5: Test Docker build and run**

Run: `docker compose build`
Expected: Image builds successfully

Run: `docker compose up`
Expected: App starts on port 8000, accessible at http://localhost:8000

Run (with mock server): `docker compose --profile dev up`
Expected: Both app and mock MCP server start

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker Compose for containerized deployment"
```

---

### Task 15: Run all tests and final cleanup

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Verify the app starts cleanly**

Run: `python -m mcp4xray.main`
Expected: Uvicorn starts on port 8000, no errors

- [ ] **Step 3: Verify Docker build**

Run: `docker compose build`
Expected: Builds without errors

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and verify all tests pass"
```

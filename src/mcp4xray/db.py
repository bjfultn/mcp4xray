"""Database module for mcp4xray — async SQLite via aiosqlite."""

from __future__ import annotations

import time
import uuid

import aiosqlite

_SCHEMA = """\
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
CREATE TABLE IF NOT EXISTS user_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    provider TEXT NOT NULL,
    api_key TEXT NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(user_id, provider)
);
"""


def _row_to_dict(cursor: aiosqlite.Cursor, row: aiosqlite.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class Database:
    """Async wrapper around an SQLite database for the mcp4xray application."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the database connection and create tables if needed."""
        self._conn = await aiosqlite.connect(self._db_path)
        # Enable foreign keys
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(_SCHEMA)
        # Migrate: add base_url column if missing
        cursor = await self._conn.execute("PRAGMA table_info(user_api_keys)")
        cols = {row[1] for row in await cursor.fetchall()}
        if "base_url" not in cols:
            await self._conn.execute(
                "ALTER TABLE user_api_keys ADD COLUMN base_url TEXT NOT NULL DEFAULT ''"
            )
        await self._conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def create_user(self, username: str, password_hash: str, role: str) -> int:
        """Insert a new user and return the user id."""
        now = time.time()
        cursor = await self._conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, now),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_user_by_username(self, username: str) -> dict | None:
        """Look up a user by username. Returns a dict or None."""
        cursor = await self._conn.execute(
            "SELECT id, username, password_hash, role, created_at FROM users WHERE username = ?",
            (username,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(cursor, row)

    async def get_all_users(self) -> list[dict]:
        """Return a list of all users (id, username, role, created_at)."""
        cursor = await self._conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(cursor, row) for row in rows]

    async def update_user_role(self, user_id: int, role: str) -> bool:
        """Update a user's role. Returns True if the user was found and updated."""
        cursor = await self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (role, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Invite codes
    # ------------------------------------------------------------------

    async def create_invite_code(self, created_by: int) -> str:
        """Generate a unique invite code and return it."""
        code = uuid.uuid4().hex
        now = time.time()
        await self._conn.execute(
            "INSERT INTO invite_codes (code, created_by, created_at) VALUES (?, ?, ?)",
            (code, created_by, now),
        )
        await self._conn.commit()
        return code

    async def get_invite_code(self, code: str) -> dict | None:
        """Look up an invite code. Returns a dict or None."""
        cursor = await self._conn.execute(
            "SELECT id, code, created_by, used_by, created_at, used_at "
            "FROM invite_codes WHERE code = ?",
            (code,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(cursor, row)

    async def use_invite_code(self, code: str, user_id: int) -> None:
        """Mark an invite code as used by the given user."""
        now = time.time()
        await self._conn.execute(
            "UPDATE invite_codes SET used_by = ?, used_at = ? WHERE code = ?",
            (user_id, now, code),
        )
        await self._conn.commit()

    async def list_invite_codes(self, created_by: int) -> list[dict]:
        """Return all invite codes created by the given user."""
        cursor = await self._conn.execute(
            "SELECT id, code, created_by, used_by, created_at, used_at "
            "FROM invite_codes WHERE created_by = ? ORDER BY id",
            (created_by,),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(cursor, row) for row in rows]

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    async def create_conversation(
        self, user_id: int, server_name: str, model: str
    ) -> int:
        """Create a new conversation and return its id."""
        now = time.time()
        cursor = await self._conn.execute(
            "INSERT INTO conversations (user_id, server_name, model, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, server_name, model, now, now),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_conversations(
        self,
        user_id: int,
        server_name: str | None = None,
        model: str | None = None,
    ) -> list[dict]:
        """Return conversations for a user, with optional filtering."""
        query = (
            "SELECT id, user_id, server_name, model, title, created_at, updated_at "
            "FROM conversations WHERE user_id = ?"
        )
        params: list = [user_id]

        if server_name is not None:
            query += " AND server_name = ?"
            params.append(server_name)
        if model is not None:
            query += " AND model = ?"
            params.append(model)

        query += " ORDER BY updated_at DESC"

        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_dict(cursor, row) for row in rows]

    async def set_conversation_title(self, conversation_id: int, title: str):
        await self._conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id),
        )
        await self._conn.commit()

    async def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        """Delete a conversation owned by user_id. Returns True if deleted."""
        cursor = await self._conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(self, conversation_id: int, role: str, content: str) -> int:
        """Add a message to a conversation and return the message id."""
        now = time.time()
        cursor = await self._conn.execute(
            "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        # Also bump updated_at on the parent conversation
        await self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_messages(self, conversation_id: int) -> list[dict]:
        """Return all messages for a conversation, ordered by timestamp."""
        cursor = await self._conn.execute(
            "SELECT id, conversation_id, role, content, timestamp "
            "FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC, id ASC",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(cursor, row) for row in rows]

    # ------------------------------------------------------------------
    # User API keys
    # ------------------------------------------------------------------

    async def set_user_api_key(
        self, user_id: int, provider: str, api_key: str, base_url: str = "",
    ) -> None:
        """Set or update an API key (and optional base_url) for a user/provider."""
        now = time.time()
        await self._conn.execute(
            "INSERT INTO user_api_keys (user_id, provider, api_key, base_url, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, provider) DO UPDATE SET api_key = ?, base_url = ?, updated_at = ?",
            (user_id, provider, api_key, base_url, now, api_key, base_url, now),
        )
        await self._conn.commit()

    async def delete_user_api_key(self, user_id: int, provider: str) -> bool:
        """Remove a user's API key for a provider. Returns True if deleted."""
        cursor = await self._conn.execute(
            "DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_user_api_keys(self, user_id: int) -> list[dict]:
        """Return a list of {provider, api_key, base_url} dicts for a user."""
        cursor = await self._conn.execute(
            "SELECT provider, api_key, base_url FROM user_api_keys WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [{"provider": r[0], "api_key": r[1], "base_url": r[2] or ""} for r in rows]

    async def get_user_provider_settings(self, user_id: int, provider: str) -> dict | None:
        """Return {api_key, base_url} for a user/provider, or None."""
        cursor = await self._conn.execute(
            "SELECT api_key, base_url FROM user_api_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {"api_key": row[0], "base_url": row[1] or ""}

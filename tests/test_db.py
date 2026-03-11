from __future__ import annotations

import pytest
import pytest_asyncio

from mcp4xray.db import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create an in-memory Database instance for each test."""
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


class TestCreateAndGetUser:
    @pytest.mark.asyncio
    async def test_create_user_returns_id(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hashed_pw", "user")
        assert isinstance(user_id, int)
        assert user_id > 0

    @pytest.mark.asyncio
    async def test_get_user_by_username_returns_dict(self, db: Database) -> None:
        await db.create_user("astro", "hashed_pw", "user")
        user = await db.get_user_by_username("astro")

        assert user is not None
        assert user["username"] == "astro"
        assert user["password_hash"] == "hashed_pw"
        assert user["role"] == "user"
        assert "id" in user
        assert "created_at" in user

    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(self, db: Database) -> None:
        result = await db.get_user_by_username("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_username_raises(self, db: Database) -> None:
        await db.create_user("astro", "hash1", "user")
        with pytest.raises(Exception):
            await db.create_user("astro", "hash2", "user")


class TestInviteCodes:
    @pytest.mark.asyncio
    async def test_create_invite_code_returns_string(self, db: Database) -> None:
        user_id = await db.create_user("admin", "hash", "admin")
        code = await db.create_invite_code(user_id)
        assert isinstance(code, str)
        assert len(code) > 0

    @pytest.mark.asyncio
    async def test_get_invite_code(self, db: Database) -> None:
        user_id = await db.create_user("admin", "hash", "admin")
        code = await db.create_invite_code(user_id)

        invite = await db.get_invite_code(code)
        assert invite is not None
        assert invite["code"] == code
        assert invite["created_by"] == user_id
        assert invite["used_by"] is None
        assert invite["used_at"] is None

    @pytest.mark.asyncio
    async def test_get_invite_code_not_found(self, db: Database) -> None:
        result = await db.get_invite_code("nonexistent-code")
        assert result is None

    @pytest.mark.asyncio
    async def test_use_invite_code(self, db: Database) -> None:
        admin_id = await db.create_user("admin", "hash", "admin")
        code = await db.create_invite_code(admin_id)

        new_user_id = await db.create_user("newuser", "hash", "user")
        await db.use_invite_code(code, new_user_id)

        invite = await db.get_invite_code(code)
        assert invite is not None
        assert invite["used_by"] == new_user_id
        assert invite["used_at"] is not None

    @pytest.mark.asyncio
    async def test_list_invite_codes(self, db: Database) -> None:
        admin_id = await db.create_user("admin", "hash", "admin")
        code1 = await db.create_invite_code(admin_id)
        code2 = await db.create_invite_code(admin_id)

        codes = await db.list_invite_codes(admin_id)
        assert len(codes) == 2
        returned_codes = {c["code"] for c in codes}
        assert code1 in returned_codes
        assert code2 in returned_codes

    @pytest.mark.asyncio
    async def test_list_invite_codes_only_own(self, db: Database) -> None:
        admin1 = await db.create_user("admin1", "hash", "admin")
        admin2 = await db.create_user("admin2", "hash", "admin")
        await db.create_invite_code(admin1)
        await db.create_invite_code(admin2)

        codes1 = await db.list_invite_codes(admin1)
        codes2 = await db.list_invite_codes(admin2)
        assert len(codes1) == 1
        assert len(codes2) == 1


class TestConversations:
    @pytest.mark.asyncio
    async def test_create_conversation_returns_id(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")
        assert isinstance(conv_id, int)
        assert conv_id > 0

    @pytest.mark.asyncio
    async def test_get_conversations(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.create_conversation(user_id, "xmm", "gpt-4o")

        convs = await db.get_conversations(user_id)
        assert len(convs) == 2

    @pytest.mark.asyncio
    async def test_get_conversations_filter_by_server(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.create_conversation(user_id, "xmm", "gpt-4o")

        convs = await db.get_conversations(user_id, server_name="chandra")
        assert len(convs) == 1
        assert convs[0]["server_name"] == "chandra"

    @pytest.mark.asyncio
    async def test_get_conversations_filter_by_model(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.create_conversation(user_id, "xmm", "gpt-4o")

        convs = await db.get_conversations(user_id, model="gpt-4o")
        assert len(convs) == 1
        assert convs[0]["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_get_conversations_filter_by_both(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        await db.create_conversation(user_id, "chandra", "claude-sonnet")
        await db.create_conversation(user_id, "chandra", "gpt-4o")
        await db.create_conversation(user_id, "xmm", "claude-sonnet")

        convs = await db.get_conversations(
            user_id, server_name="chandra", model="claude-sonnet"
        )
        assert len(convs) == 1
        assert convs[0]["server_name"] == "chandra"
        assert convs[0]["model"] == "claude-sonnet"

    @pytest.mark.asyncio
    async def test_get_conversations_other_user(self, db: Database) -> None:
        user1 = await db.create_user("astro1", "hash", "user")
        user2 = await db.create_user("astro2", "hash", "user")
        await db.create_conversation(user1, "chandra", "claude-sonnet")

        convs = await db.get_conversations(user2)
        assert len(convs) == 0

    @pytest.mark.asyncio
    async def test_delete_conversation(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        result = await db.delete_conversation(conv_id, user_id)
        assert result is True

        convs = await db.get_conversations(user_id)
        assert len(convs) == 0

    @pytest.mark.asyncio
    async def test_delete_conversation_wrong_user(self, db: Database) -> None:
        user1 = await db.create_user("astro1", "hash", "user")
        user2 = await db.create_user("astro2", "hash", "user")
        conv_id = await db.create_conversation(user1, "chandra", "claude-sonnet")

        result = await db.delete_conversation(conv_id, user2)
        assert result is False

        # Original user's conversation should still exist
        convs = await db.get_conversations(user1)
        assert len(convs) == 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent_conversation(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        result = await db.delete_conversation(9999, user_id)
        assert result is False


class TestMessages:
    @pytest.mark.asyncio
    async def test_add_message_returns_id(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        msg_id = await db.add_message(conv_id, "user", "Hello!")
        assert isinstance(msg_id, int)
        assert msg_id > 0

    @pytest.mark.asyncio
    async def test_get_messages(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        await db.add_message(conv_id, "user", "What is Cas A?")
        await db.add_message(conv_id, "assistant", "Cas A is a supernova remnant.")

        messages = await db.get_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is Cas A?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Cas A is a supernova remnant."

    @pytest.mark.asyncio
    async def test_get_messages_empty_conversation(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        messages = await db.get_messages(conv_id)
        assert messages == []

    @pytest.mark.asyncio
    async def test_messages_ordered_by_timestamp(self, db: Database) -> None:
        user_id = await db.create_user("astro", "hash", "user")
        conv_id = await db.create_conversation(user_id, "chandra", "claude-sonnet")

        await db.add_message(conv_id, "user", "First")
        await db.add_message(conv_id, "assistant", "Second")
        await db.add_message(conv_id, "user", "Third")

        messages = await db.get_messages(conv_id)
        assert len(messages) == 3
        assert messages[0]["content"] == "First"
        assert messages[1]["content"] == "Second"
        assert messages[2]["content"] == "Third"
        # Timestamps should be non-decreasing
        assert messages[0]["timestamp"] <= messages[1]["timestamp"]
        assert messages[1]["timestamp"] <= messages[2]["timestamp"]


class TestGetAllUsers:
    @pytest.mark.asyncio
    async def test_get_all_users(self, db: Database) -> None:
        await db.create_user("alice", "hash1", "admin")
        await db.create_user("bob", "hash2", "user")

        users = await db.get_all_users()
        assert len(users) == 2
        usernames = {u["username"] for u in users}
        assert usernames == {"alice", "bob"}

    @pytest.mark.asyncio
    async def test_get_all_users_empty(self, db: Database) -> None:
        users = await db.get_all_users()
        assert users == []

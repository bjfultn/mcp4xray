from __future__ import annotations

import pytest

from mcp4xray.auth import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

SECRET = "test-secret-key"


class TestPasswordHashing:
    def test_hash_and_verify_correct_password(self):
        hashed = hash_password("s3cret")
        assert verify_password("s3cret", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("s3cret")
        assert verify_password("wrong", hashed) is False

    def test_hash_produces_different_salts(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # different salts each time


class TestJWT:
    def test_create_and_decode_roundtrip(self):
        token = create_token(
            user_id=42, username="astro", role="user", secret=SECRET
        )
        payload = decode_token(token, SECRET)
        assert payload["user_id"] == 42
        assert payload["username"] == "astro"
        assert payload["role"] == "user"
        assert "exp" in payload

    def test_decode_garbage_raises(self):
        with pytest.raises(Exception):
            decode_token("not.a.valid.token", SECRET)

    def test_decode_wrong_secret_raises(self):
        token = create_token(
            user_id=1, username="x", role="user", secret=SECRET
        )
        with pytest.raises(Exception):
            decode_token(token, "wrong-secret")

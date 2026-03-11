from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mcp4xray.config import (
    AppConfig,
    ModelEntry,
    ServerEntry,
    ServersConfig,
    load_config,
)


@pytest.fixture
def sample_config_file(tmp_path: Path) -> Path:
    """Write a minimal servers.json and return its path."""
    data = {
        "servers": [
            {"name": "Mock Archive", "url": "http://127.0.0.1:9000/mcp"},
            {"name": "Chandra", "url": "https://chandra-mcp.example.com/mcp"},
        ],
        "models": [
            {
                "id": "claude-sonnet-4-20250514",
                "name": "Claude Sonnet",
                "provider": "anthropic",
            },
            {
                "id": "qwen3:14b",
                "name": "Qwen3 14B",
                "provider": "ollama",
                "base_url": "http://localhost:11434/v1",
            },
        ],
    }
    config_path = tmp_path / "servers.json"
    config_path.write_text(json.dumps(data))
    return config_path


class TestLoadConfig:
    """Tests for load_config()."""

    def test_loads_servers_from_valid_json(self, sample_config_file: Path) -> None:
        cfg = load_config(str(sample_config_file))

        assert isinstance(cfg, ServersConfig)
        assert len(cfg.servers) == 2
        assert cfg.servers[0] == ServerEntry(
            name="Mock Archive", url="http://127.0.0.1:9000/mcp"
        )
        assert cfg.servers[1].name == "Chandra"

    def test_loads_models_from_valid_json(self, sample_config_file: Path) -> None:
        cfg = load_config(str(sample_config_file))

        assert len(cfg.models) == 2
        assert cfg.models[0].id == "claude-sonnet-4-20250514"
        assert cfg.models[0].provider == "anthropic"

    def test_model_with_optional_base_url(self, sample_config_file: Path) -> None:
        cfg = load_config(str(sample_config_file))

        # Model without base_url should default to ""
        assert cfg.models[0].base_url == ""
        # Model with explicit base_url should keep it
        assert cfg.models[1].base_url == "http://localhost:11434/v1"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config(str(missing))

    def test_empty_servers_and_models(self, tmp_path: Path) -> None:
        config_path = tmp_path / "empty.json"
        config_path.write_text(json.dumps({"servers": [], "models": []}))

        cfg = load_config(str(config_path))

        assert cfg.servers == []
        assert cfg.models == []


class TestAppConfig:
    """Tests for AppConfig.from_env()."""

    def test_from_env_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_SECRET", "super-secret")
        monkeypatch.setenv("ADMIN_USERNAME", "astro")
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/xray")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-xxx")
        monkeypatch.setenv("GEMINI_API_KEY", "gem-xxx")

        cfg = AppConfig.from_env()

        assert cfg.jwt_secret == "super-secret"
        assert cfg.admin_username == "astro"
        assert cfg.admin_password == "hunter2"
        assert cfg.database_url == "postgresql://localhost/xray"
        assert cfg.anthropic_api_key == "sk-ant-xxx"
        assert cfg.openai_api_key == "sk-oai-xxx"
        assert cfg.gemini_api_key == "gem-xxx"

    def test_from_env_uses_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear any existing env vars that might interfere
        for var in [
            "JWT_SECRET",
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
            "DATABASE_URL",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ]:
            monkeypatch.delenv(var, raising=False)

        cfg = AppConfig.from_env()

        assert cfg.jwt_secret == "dev-secret-change-me"
        assert cfg.admin_username == "admin"
        assert cfg.admin_password == "changeme"
        assert cfg.database_url == "sqlite:///./mcp4xray.db"
        assert cfg.anthropic_api_key == ""
        assert cfg.openai_api_key == ""
        assert cfg.gemini_api_key == ""


class TestModelEntry:
    """Tests for ModelEntry dataclass."""

    def test_base_url_defaults_to_empty(self) -> None:
        m = ModelEntry(id="gpt-4o", name="GPT-4o", provider="openai")
        assert m.base_url == ""

    def test_base_url_can_be_set(self) -> None:
        m = ModelEntry(
            id="qwen3:14b",
            name="Qwen3 14B",
            provider="ollama",
            base_url="http://localhost:11434/v1",
        )
        assert m.base_url == "http://localhost:11434/v1"

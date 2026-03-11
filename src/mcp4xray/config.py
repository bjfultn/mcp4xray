from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
    base_url: str = ""  # optional override


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
    models = [ModelEntry(**{k: v for k, v in m.items()}) for m in data.get("models", [])]
    return ServersConfig(servers=servers, models=models)

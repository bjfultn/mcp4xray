"""Multi-provider LLM backend with native tool-calling support.

Supports OpenAI, Anthropic, Gemini, and Ollama (OpenAI-compatible) providers.
Converts MCP tool definitions to each provider's native format and handles
tool interaction message formatting.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Provider base-URL defaults
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "ollama": "http://127.0.0.1:11434/v1",
}

# ---------------------------------------------------------------------------
# Tool-schema converters
# ---------------------------------------------------------------------------


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip fields from an MCP inputSchema that LLM providers reject."""
    cleaned = {k: v for k, v in schema.items() if k != "title"}
    if "properties" in cleaned:
        cleaned["properties"] = {
            k: {pk: pv for pk, pv in v.items() if pk != "title"}
            for k, v in cleaned["properties"].items()
        }
    return cleaned


def mcp_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool definitions to OpenAI's native function-calling format.

    Each tool is wrapped in ``{"type": "function", "function": {...}}``.
    """
    result: list[dict[str, Any]] = []
    for tool in tools:
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": _clean_schema(tool["inputSchema"]),
                },
            }
        )
    return result


def mcp_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool definitions to Anthropic's native format.

    Uses the ``input_schema`` key instead of ``inputSchema``.
    """
    result: list[dict[str, Any]] = []
    for tool in tools:
        result.append(
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": _clean_schema(tool["inputSchema"]),
            }
        )
    return result


def mcp_tools_to_gemini(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool definitions to Gemini's function-declaration format.

    Uses the ``parameters`` key for the JSON schema.
    """
    result: list[dict[str, Any]] = []
    for tool in tools:
        result.append(
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": _clean_schema(tool["inputSchema"]),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""

    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLMBackend
# ---------------------------------------------------------------------------


class LLMBackend:
    """Async LLM client supporting multiple providers with native tool calling."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str = "",
        base_url: str = "",
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or _PROVIDER_DEFAULTS.get(provider, "")

    # -- public API ---------------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
    ) -> LLMResponse:
        """Send a chat-completion request and return a unified *LLMResponse*.

        *tools* should be in MCP format; they are converted to the provider's
        native format automatically.
        """
        if self.provider in ("openai", "ollama"):
            native_tools = mcp_tools_to_openai(tools) if tools else None
            return await self._complete_openai(messages, native_tools, system_prompt)
        elif self.provider == "anthropic":
            native_tools = mcp_tools_to_anthropic(tools) if tools else None
            return await self._complete_anthropic(messages, native_tools, system_prompt)
        elif self.provider == "gemini":
            native_tools = mcp_tools_to_gemini(tools) if tools else None
            return await self._complete_gemini(messages, native_tools, system_prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider!r}")

    def append_tool_interaction(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
    ) -> list[dict[str, Any]]:
        """Return a *new* message list with the tool call and its result appended.

        The format matches the provider's native message convention so the
        resulting list can be fed straight back into :meth:`complete`.
        """
        if self.provider in ("openai", "ollama"):
            return self._append_openai(messages, tool_name, arguments, result)
        elif self.provider == "anthropic":
            return self._append_anthropic(messages, tool_name, arguments, result)
        elif self.provider == "gemini":
            # Gemini uses a similar structure; for now fall back to OpenAI style
            return self._append_openai(messages, tool_name, arguments, result)
        else:
            raise ValueError(f"Unknown provider: {self.provider!r}")

    # -- OpenAI / Ollama ----------------------------------------------------

    async def _complete_openai(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_prompt: str,
    ) -> LLMResponse:
        all_messages = list(messages)
        if system_prompt:
            all_messages = [{"role": "system", "content": system_prompt}, *all_messages]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
        }
        if tools:
            payload["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=120.0,
            )
            if not resp.is_success:
                detail = resp.text[:500]
                raise RuntimeError(
                    f"{self.provider} API error {resp.status_code}: {detail}"
                )
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        text = msg.get("content") or ""
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments", "{}")
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(name=tc["function"]["name"], arguments=args))

        return LLMResponse(text=text, tool_calls=tool_calls)

    def _append_openai(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
    ) -> list[dict[str, Any]]:
        tool_call_id = f"call_{uuid.uuid4().hex[:24]}"
        new_messages = list(messages)
        new_messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(arguments),
                        },
                    }
                ],
            }
        )
        new_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result,
            }
        )
        return new_messages

    # -- Anthropic ----------------------------------------------------------

    async def _complete_anthropic(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_prompt: str,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "max_tokens": 4096,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
                timeout=120.0,
            )
            if not resp.is_success:
                detail = resp.text[:500]
                raise RuntimeError(
                    f"Anthropic API error {resp.status_code}: {detail}"
                )
            data = resp.json()

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in data.get("content", []):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(name=block["name"], arguments=block["input"])
                )

        return LLMResponse(text="\n".join(text_parts), tool_calls=tool_calls)

    def _append_anthropic(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
    ) -> list[dict[str, Any]]:
        tool_use_id = f"toolu_{uuid.uuid4().hex[:24]}"
        new_messages = list(messages)
        new_messages.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": tool_name,
                        "input": arguments,
                    }
                ],
            }
        )
        new_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result,
                    }
                ],
            }
        )
        return new_messages

    # -- Gemini -------------------------------------------------------------

    async def _complete_gemini(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_prompt: str,
    ) -> LLMResponse:
        # Build Gemini contents from messages
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                {"role": role, "parts": [{"text": msg.get("content", "")}]}
            )

        payload: dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        if tools:
            payload["tools"] = [{"function_declarations": tools}]

        url = (
            f"{self.base_url}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120.0,
            )
            if not resp.is_success:
                detail = resp.text[:500]
                raise RuntimeError(
                    f"Gemini API error {resp.status_code}: {detail}"
                )
            data = resp.json()

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    text_parts.append(part["text"])
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append(
                        ToolCall(name=fc["name"], arguments=fc.get("args", {}))
                    )

        return LLMResponse(text="\n".join(text_parts), tool_calls=tool_calls)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_backend(
    provider: str,
    model: str,
    api_key: str = "",
    base_url: str = "",
) -> LLMBackend:
    """Create an :class:`LLMBackend` with sensible defaults per provider.

    Raises :class:`ValueError` for unrecognised providers.
    """
    if provider not in _PROVIDER_DEFAULTS:
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            f"Supported: {', '.join(sorted(_PROVIDER_DEFAULTS))}"
        )
    return LLMBackend(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

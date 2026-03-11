from __future__ import annotations

import pytest

from mcp4xray.llm import (
    LLMBackend,
    LLMResponse,
    ToolCall,
    create_llm_backend,
    mcp_tools_to_anthropic,
    mcp_tools_to_gemini,
    mcp_tools_to_openai,
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


class TestMcpToolsToOpenai:
    def test_wraps_in_function_type(self):
        result = mcp_tools_to_openai([SAMPLE_MCP_TOOL])

        assert len(result) == 1
        tool = result[0]
        assert tool["type"] == "function"
        assert "function" in tool

    def test_function_name_and_description(self):
        result = mcp_tools_to_openai([SAMPLE_MCP_TOOL])

        func = result[0]["function"]
        assert func["name"] == "query_tap"
        assert func["description"] == "Run an ADQL query"

    def test_function_parameters(self):
        result = mcp_tools_to_openai([SAMPLE_MCP_TOOL])

        params = result[0]["function"]["parameters"]
        assert params["type"] == "object"
        assert "adql" in params["properties"]
        assert params["required"] == ["adql"]

    def test_multiple_tools(self):
        second_tool = {
            "name": "get_obs",
            "description": "Get observation",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        }
        result = mcp_tools_to_openai([SAMPLE_MCP_TOOL, second_tool])

        assert len(result) == 2
        assert result[0]["function"]["name"] == "query_tap"
        assert result[1]["function"]["name"] == "get_obs"

    def test_empty_list(self):
        result = mcp_tools_to_openai([])
        assert result == []


class TestMcpToolsToAnthropic:
    def test_uses_input_schema_key(self):
        result = mcp_tools_to_anthropic([SAMPLE_MCP_TOOL])

        assert len(result) == 1
        tool = result[0]
        assert "input_schema" in tool

    def test_name_and_description(self):
        result = mcp_tools_to_anthropic([SAMPLE_MCP_TOOL])

        tool = result[0]
        assert tool["name"] == "query_tap"
        assert tool["description"] == "Run an ADQL query"

    def test_input_schema_content(self):
        result = mcp_tools_to_anthropic([SAMPLE_MCP_TOOL])

        schema = result[0]["input_schema"]
        assert schema["type"] == "object"
        assert "adql" in schema["properties"]
        assert schema["required"] == ["adql"]

    def test_empty_list(self):
        result = mcp_tools_to_anthropic([])
        assert result == []


class TestMcpToolsToGemini:
    def test_uses_parameters_key(self):
        result = mcp_tools_to_gemini([SAMPLE_MCP_TOOL])

        assert len(result) == 1
        decl = result[0]
        assert "parameters" in decl

    def test_name_and_description(self):
        result = mcp_tools_to_gemini([SAMPLE_MCP_TOOL])

        decl = result[0]
        assert decl["name"] == "query_tap"
        assert decl["description"] == "Run an ADQL query"

    def test_parameters_content(self):
        result = mcp_tools_to_gemini([SAMPLE_MCP_TOOL])

        params = result[0]["parameters"]
        assert params["type"] == "object"
        assert "adql" in params["properties"]
        assert params["required"] == ["adql"]

    def test_empty_list(self):
        result = mcp_tools_to_gemini([])
        assert result == []


class TestCreateLlmBackend:
    def test_creates_openai_backend(self):
        backend = create_llm_backend(
            provider="openai", model="gpt-4o", api_key="sk-test"
        )

        assert isinstance(backend, LLMBackend)
        assert backend.provider == "openai"
        assert backend.model == "gpt-4o"
        assert backend.api_key == "sk-test"
        assert backend.base_url == "https://api.openai.com/v1"

    def test_creates_ollama_backend(self):
        backend = create_llm_backend(
            provider="ollama", model="qwen3:14b"
        )

        assert isinstance(backend, LLMBackend)
        assert backend.provider == "ollama"
        assert backend.model == "qwen3:14b"
        assert backend.base_url == "http://127.0.0.1:11434/v1"

    def test_creates_anthropic_backend(self):
        backend = create_llm_backend(
            provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-ant-test"
        )

        assert backend.provider == "anthropic"
        assert backend.base_url == "https://api.anthropic.com/v1"

    def test_creates_gemini_backend(self):
        backend = create_llm_backend(
            provider="gemini", model="gemini-2.0-flash", api_key="gem-test"
        )

        assert backend.provider == "gemini"
        assert backend.base_url == "https://generativelanguage.googleapis.com/v1beta"

    def test_custom_base_url_overrides_default(self):
        backend = create_llm_backend(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url="https://custom.api.com/v1",
        )

        assert backend.base_url == "https://custom.api.com/v1"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_llm_backend(provider="unknown", model="x")


class TestAppendToolInteractionOpenai:
    def test_appends_assistant_and_tool_messages(self):
        backend = create_llm_backend(
            provider="openai", model="gpt-4o", api_key="sk-test"
        )
        messages: list[dict] = [{"role": "user", "content": "Run a query"}]

        result = backend.append_tool_interaction(
            messages=messages,
            tool_name="query_tap",
            arguments={"adql": "SELECT * FROM obs"},
            result="Found 42 rows",
        )

        # Should have 3 messages: original user + assistant tool_calls + tool result
        assert len(result) == 3

        # Assistant message with tool_calls
        assistant_msg = result[1]
        assert assistant_msg["role"] == "assistant"
        assert "tool_calls" in assistant_msg
        assert len(assistant_msg["tool_calls"]) == 1

        tc = assistant_msg["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "query_tap"
        assert "id" in tc  # must have a tool_call_id

        # Tool result message
        tool_msg = result[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == tc["id"]
        assert tool_msg["content"] == "Found 42 rows"

    def test_does_not_mutate_original_messages(self):
        backend = create_llm_backend(
            provider="openai", model="gpt-4o", api_key="sk-test"
        )
        messages: list[dict] = [{"role": "user", "content": "Hello"}]
        original_len = len(messages)

        backend.append_tool_interaction(
            messages=messages,
            tool_name="query_tap",
            arguments={"adql": "SELECT 1"},
            result="ok",
        )

        assert len(messages) == original_len

    def test_ollama_uses_openai_format(self):
        backend = create_llm_backend(provider="ollama", model="qwen3:14b")
        messages: list[dict] = [{"role": "user", "content": "test"}]

        result = backend.append_tool_interaction(
            messages=messages,
            tool_name="query_tap",
            arguments={"adql": "SELECT 1"},
            result="ok",
        )

        # Ollama uses OpenAI-compatible format
        assert result[1]["role"] == "assistant"
        assert "tool_calls" in result[1]
        assert result[2]["role"] == "tool"


class TestAppendToolInteractionAnthropic:
    def test_appends_tool_use_and_tool_result(self):
        backend = create_llm_backend(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key="sk-ant-test",
        )
        messages: list[dict] = [{"role": "user", "content": "Run a query"}]

        result = backend.append_tool_interaction(
            messages=messages,
            tool_name="query_tap",
            arguments={"adql": "SELECT * FROM obs"},
            result="Found 42 rows",
        )

        # Should have 3 messages: original user + assistant tool_use + user tool_result
        assert len(result) == 3

        # Assistant message with tool_use content block
        assistant_msg = result[1]
        assert assistant_msg["role"] == "assistant"
        assert isinstance(assistant_msg["content"], list)

        tool_use_block = assistant_msg["content"][0]
        assert tool_use_block["type"] == "tool_use"
        assert tool_use_block["name"] == "query_tap"
        assert tool_use_block["input"] == {"adql": "SELECT * FROM obs"}
        assert "id" in tool_use_block

        # Tool result message (role: user with tool_result content)
        tool_result_msg = result[2]
        assert tool_result_msg["role"] == "user"
        assert isinstance(tool_result_msg["content"], list)

        tool_result_block = tool_result_msg["content"][0]
        assert tool_result_block["type"] == "tool_result"
        assert tool_result_block["tool_use_id"] == tool_use_block["id"]
        assert tool_result_block["content"] == "Found 42 rows"

    def test_does_not_mutate_original_messages(self):
        backend = create_llm_backend(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key="sk-ant-test",
        )
        messages: list[dict] = [{"role": "user", "content": "Hello"}]
        original_len = len(messages)

        backend.append_tool_interaction(
            messages=messages,
            tool_name="query_tap",
            arguments={"adql": "SELECT 1"},
            result="ok",
        )

        assert len(messages) == original_len


class TestResponseTypes:
    def test_tool_call_dataclass(self):
        tc = ToolCall(name="query_tap", arguments={"adql": "SELECT 1"})
        assert tc.name == "query_tap"
        assert tc.arguments == {"adql": "SELECT 1"}

    def test_llm_response_defaults(self):
        resp = LLMResponse()
        assert resp.text == ""
        assert resp.tool_calls == []

    def test_llm_response_with_values(self):
        tc = ToolCall(name="query_tap", arguments={"adql": "SELECT 1"})
        resp = LLMResponse(text="Here are results", tool_calls=[tc])
        assert resp.text == "Here are results"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "query_tap"

# mcp4xray Web Frontend Design

## Overview

A web-based chat UI for querying X-ray astronomy archives via MCP servers. Connects to one remote MCP server at a time (Chandra, XMM-Newton, or future missions), supports multiple LLM providers, and shows tool calls transparently.

## Architecture

```
Browser (HTML/JS)  <-->  FastAPI Backend  <-->  Remote MCP Server (HTTP/SSE)
                                          <-->  LLM Provider APIs
                                          <-->  SQLite Database
```

## Backend (Python / FastAPI)

### MCP Client
- Connects to remote MCP servers using the `streamable-http` transport
- One connection at a time, switchable by mission
- System prompt sourced from the MCP server's `instructions` field at connection time
- Tool definitions discovered dynamically via `list_tools`

### LLM Backend
- Supports Anthropic, OpenAI, Gemini, and Ollama (local)
- Reuses the multi-provider pattern from `laiss_hack/client.py`
- Translates MCP tool definitions into each provider's tool-calling format
- API keys configured server-side via environment variables

### Chat Endpoint
- Streaming SSE endpoint
- Receives user message, runs the agentic loop (LLM -> tool call -> tool result -> LLM -> ...)
- Streams each step back to the browser as it happens: assistant text chunks, tool call requests, tool results

### Config Endpoint
- Returns available missions and models to populate UI dropdowns
- Missions defined in a JSON config file:

```json
{
  "servers": [
    {"name": "Chandra", "url": "https://chandra-mcp.example.com/mcp"},
    {"name": "XMM-Newton", "url": "https://xmm-mcp.example.com/mcp"}
  ]
}
```

Adding a new mission requires only a config file entry, no code changes.

### Authentication
- JWT-based session management
- Login endpoint (username/password -> JWT token)
- Two roles: `admin` and `user`
- Initial admin created on first startup via env vars (`ADMIN_USERNAME`, `ADMIN_PASSWORD`) or CLI command
- Admin generates single-use invite codes from an admin panel
- New users self-register with a valid invite code, choosing their own username/password

## Frontend (HTML + Vanilla JS)

### Chat View
- Message list showing user messages, assistant responses, and tool call/result blocks (visually distinct)
- Streaming responses rendered incrementally
- Dropdowns for mission and model selection
- Switching mission disconnects from current MCP server and connects to the new one (resets conversation)

### Conversation Sidebar
- List of past conversations, filterable by mission/model
- Ability to resume or review past conversations

### Admin Panel
- Generate invite codes
- View/manage users

## Database (SQLite)

### Tables

**users**
- id, username, password_hash, role (admin/user), created_at

**invite_codes**
- id, code, created_by (user_id), used_by (user_id, nullable), created_at, used_at (nullable)

**conversations**
- id, user_id, server_name, model, title, created_at, updated_at

**messages**
- id, conversation_id, role (user/assistant/tool_call/tool_result), content, timestamp

## Configuration (Environment Variables)

- `ADMIN_USERNAME`, `ADMIN_PASSWORD` — initial admin account (first startup)
- `ANTHROPIC_API_KEY` — Anthropic API key
- `OPENAI_API_KEY` — OpenAI API key
- `GEMINI_API_KEY` — Gemini API key
- `DATABASE_URL` — SQLite path (default: `./mcp4xray.db`)
- `JWT_SECRET` — secret for signing JWT tokens
- `MCP_SERVERS_CONFIG` — path to the servers JSON config file

## Key Decisions

- No simultaneous multi-server connections; one mission at a time
- Chat history persisted in database per user
- System prompt owned by MCP server, not hardcoded in client
- Server-side API keys only; users never handle keys
- SQLite to start; schema simple enough to swap to Postgres later if needed
- Containerized with Docker Compose; `docker compose up` runs the app
- Python 3.12+

# StudyPulse backend agent

FastAPI HTTP entrypoint (`server.py`) for the Vite/React frontend in
`codebase/FE`. `/api/v1/chat` runs `studypulse/`'s LangGraph pipeline
(extraction → validation → confidence gate → SQLite/FAISS, RAG chat) — see
`studypulse/graph.py`. Mail/Discord ingestion is triggered right after a
connect (`studypulse/mail_ingest.py`, `studypulse/discord_ingest.py`) and its
progress is exposed via `GET /api/v1/connections/ingest-status`.

Wired to the MCP integrations in `codebase/mcp/`: **Gmail** (`gmail_mcp`),
**Discord** (`discord_mcp`), **Google Calendar** (`google_calendar_mcp`), and
**Outlook** (`codebase/mcp/outlook_mcp`, via `mcp_bridge/outlook_client.py`).

## How the MCPs are reached

- **Gmail**, **Discord**, **Google Calendar**: local MCP servers, reached over streamable-HTTP (`mcp_bridge/http_mcp_client.py`).
- **Outlook**: `outlook-local-mcp`'s Docker container, reached via `mcp_bridge/outlook_client.py` (device-code sign-in — see `outlook_connection.py`).

## Setup

```bash
cd codebase/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
test -f .env || cp .env.example .env
```

Fill in `OPENAI_API_KEY` (all LLM calls, including studypulse/, go through
OpenAI) and Google OAuth client credentials in `codebase/backend/.env`.
Discord/Calendar/Gmail credentials go in `codebase/mcp/.env` (see
`codebase/mcp/discord_mcp/README.md`, `codebase/mcp/google_calendar_mcp/README.md`,
`codebase/mcp/gmail_mcp/README.md` for how to obtain each).

In other terminals (same `codebase/mcp/.venv`), start the MCP servers:

```bash
cd codebase/mcp && source .venv/bin/activate
python -m discord_mcp            # http://localhost:8085/mcp
```

```bash
cd codebase/mcp && source .venv/bin/activate
python -m google_calendar_mcp    # http://localhost:8086/mcp
```

```bash
cd codebase/mcp && source .venv/bin/activate
python -m gmail_mcp              # http://localhost:8087/mcp
```

Outlook runs as a Docker container instead — see `codebase/mcp/outlook_mcp/README.md`.

## Run

```bash
cd codebase/backend
uvicorn server:app --reload --port 8000
```

The FE (`codebase/FE`) talks to this at `http://localhost:8000/api/v1` by
default (`VITE_API_BASE_URL`).

Tools with no server/credentials configured yet fail closed with a plain
`{"tool": ..., "error": ..., "message": ...}` dict instead of crashing.

# Build context must be the repo root (this image needs both codebase/backend
# and three of the codebase/mcp/* servers). In Railway: Root Directory = repo
# root, Dockerfile Path = codebase/backend/Dockerfile.
FROM python:3.11-slim

WORKDIR /app

COPY codebase/backend/requirements.txt /app/backend-requirements.txt
COPY codebase/mcp/requirements.txt /app/mcp-requirements.txt
RUN pip install --no-cache-dir -r /app/backend-requirements.txt -r /app/mcp-requirements.txt

COPY codebase/backend /app/backend
COPY codebase/mcp/discord_mcp /app/mcp/discord_mcp
COPY codebase/mcp/gmail_mcp /app/mcp/gmail_mcp
COPY codebase/mcp/google_calendar_mcp /app/mcp/google_calendar_mcp

RUN chmod +x /app/backend/start.sh

ENTRYPOINT ["/app/backend/start.sh"]

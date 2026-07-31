#!/usr/bin/env bash
# Container entrypoint: brings up discord_mcp/gmail_mcp/google_calendar_mcp
# (codebase/mcp, HTTP servers on their usual localhost ports) as background
# processes, then execs the FastAPI backend in the foreground. One container
# so all four processes share one filesystem/volume — see
# codebase/backend/Dockerfile and the deploy plan for why.
set -euo pipefail

if [ -n "${GOOGLE_OAUTH_CLIENT_SECRETS_FILE:-}" ]; then
  mkdir -p "$(dirname "$GOOGLE_OAUTH_CLIENT_SECRETS_FILE")"
  if [ -n "${GOOGLE_CLIENT_SECRET_JSON:-}" ] && [ ! -f "$GOOGLE_OAUTH_CLIENT_SECRETS_FILE" ]; then
    echo "Writing GOOGLE_CLIENT_SECRET_JSON to $GOOGLE_OAUTH_CLIENT_SECRETS_FILE"
    printf '%s' "$GOOGLE_CLIENT_SECRET_JSON" > "$GOOGLE_OAUTH_CLIENT_SECRETS_FILE"
  fi
fi

if [ -n "${GOOGLE_CALENDAR_TOKEN_FILE:-}" ]; then
  mkdir -p "$(dirname "$GOOGLE_CALENDAR_TOKEN_FILE")"
fi

if [ -n "${DISCORD_TOKEN:-}" ]; then
  echo "Starting discord_mcp..."
  (cd /app/mcp && exec python -m discord_mcp) &
else
  echo "DISCORD_TOKEN not set — skipping discord_mcp."
fi

if [ -n "${GOOGLE_CLIENT_SECRETS_FILE:-}" ] && [ -f "$GOOGLE_CLIENT_SECRETS_FILE" ]; then
  echo "Starting google_calendar_mcp..."
  (cd /app/mcp && exec python -m google_calendar_mcp) &
else
  echo "GOOGLE_CLIENT_SECRETS_FILE missing — skipping google_calendar_mcp."
fi

echo "Starting gmail_mcp..."
(cd /app/mcp && exec python -m gmail_mcp) &

cd /app/backend
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"

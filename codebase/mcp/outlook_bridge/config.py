import os
import sys

from dotenv import load_dotenv

load_dotenv()

# outlook-local-mcp's own docker-run args (image, volume, client id, etc.) are
# defined once in outlook_mcp/config.py — reused here rather than duplicated,
# since both packages need the exact same invocation for the cached token to
# be readable (see that module's docker_run_args() docstring re: --hostname
# and HOME).
from outlook_mcp import config as outlook_mcp_config  # noqa: E402

docker_run_args = outlook_mcp_config.docker_run_args

BRIDGE_HOST = os.environ.get("OUTLOOK_BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.environ.get("OUTLOOK_BRIDGE_PORT", "8088"))

AUTH_TOKEN = os.environ.get("OUTLOOK_BRIDGE_AUTH_TOKEN", "").strip()
if not AUTH_TOKEN:
    print(
        "ERROR: OUTLOOK_BRIDGE_AUTH_TOKEN is not set. This server is reachable from the "
        "public internet via a Cloudflare Tunnel, so it must not run without a shared-secret "
        "token — generate one (e.g. `openssl rand -hex 32`) and set it here and as "
        "OUTLOOK_MCP_AUTH_TOKEN on the Railway backend.",
        file=sys.stderr,
    )
    sys.exit(1)

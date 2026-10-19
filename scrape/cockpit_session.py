"""A requests session for social-cockpit that carries its access token.

With COCKPIT_AUTH on, the cockpit refuses any request without an `x-cockpit-token`
header. The token is COCKPIT_TOKEN (env or .env), else the cockpit checkout's
data/auth-token — the checkout found from .mcp.json, as {SOCIAL_COCKPIT_DIR} is in
glossary.md. With neither, requests go out bare, which a cockpit with auth off accepts.
"""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _token() -> str:
    if os.environ.get("COCKPIT_TOKEN"):
        return os.environ["COCKPIT_TOKEN"]
    cockpit = ROOT.parent / "social-cockpit"
    mcp = ROOT / ".mcp.json"
    if mcp.exists():
        for server in json.loads(mcp.read_text()).get("mcpServers", {}).values():
            for arg in server.get("args", []):
                if arg.endswith("mcp/dist/index.js"):
                    cockpit = Path(arg).parents[2]
    path = cockpit / "data" / "auth-token"
    return path.read_text().strip() if path.exists() else ""


session = requests.Session()
if token := _token():
    session.headers["x-cockpit-token"] = token

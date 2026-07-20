"""HTTP auth helpers for the Silex MCP server."""

from __future__ import annotations

import hmac
import os




def mcp_client_id() -> str:
    return os.getenv("KINTHIC_MCP_CLIENT_ID", "default").strip() or "default"


def verify_api_key(provided: str) -> bool:
    if not provided:
        return False
    expected = os.getenv("KINTHIC_API_KEY")
    return hmac.compare_digest(provided, expected)


def extract_api_key(headers: dict[str, str]) -> str:
    direct = headers.get("x-kinthic-api-key") or headers.get("X-Kinthic-Api-Key") or ""
    if direct:
        return direct
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


# Phase 5: OAuth 2.1 + PKCE for remote MCP deployments.
# See docs/mcp-server-rfc.md — not implemented in single-user local-first v1.

OAUTH_PHASE = 5
OAUTH_WELL_KNOWN = "/.well-known/oauth-authorization-server"

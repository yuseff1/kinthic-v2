"""Paste-ready MCP client configuration snippets."""

from __future__ import annotations

import json


def claude_desktop_config() -> dict:
    return {
        "mcpServers": {
            "kinthic-memory": {
                "command": "kinthic",
                "args": ["mcp", "serve", "--stdio"],
            }
        }
    }


def cursor_config() -> dict:
    return claude_desktop_config()


def print_config(client: str = "claude") -> None:
    client = (client or "claude").lower()
    if client == "cursor":
        payload = cursor_config()
    else:
        payload = claude_desktop_config()
    print(json.dumps(payload, indent=2))
    print("\n# HTTP endpoint (daemon running): http://127.0.0.1:8000/mcp")
    print("# Auth header: x-kinthic-api-key (see ~/.kinthic/runtime/settings.json)")

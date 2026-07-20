"""Bundled MCP server presets."""

from __future__ import annotations

from silex_core.utils.config import WORKSPACE_DIR


def get_preset(name: str) -> dict | None:
    """Return server config dict for a named preset."""
    presets = {
        "filesystem": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(WORKSPACE_DIR),
            ],
            "enabled": False,
            "allowed_tools": ["read_file", "list_directory", "get_file_info"],
            "requires_approval": ["write_file"],
            "description": "Read-only workspace filesystem (write requires approval)",
        },
        "fetch": {
            "command": "uvx",
            "args": ["mcp-server-fetch"],
            "enabled": False,
            "allowed_tools": [],
            "requires_approval": ["fetch"],
            "description": "Fetch URL content via MCP",
        },
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "enabled": False,
            "allowed_tools": [],
            "requires_approval": [],
            "description": "GitHub MCP (requires GITHUB_PERSONAL_ACCESS_TOKEN env var)",
        },
    }
    return presets.get(name)


def list_presets() -> list[str]:
    return ["filesystem", "fetch", "github"]

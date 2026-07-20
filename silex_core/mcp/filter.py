"""Per-server MCP tool allow/deny filtering."""

from __future__ import annotations

from typing import Any


class ToolsetFilter:
    """Filter MCP tools by allow/deny lists and max cap."""

    def __init__(
        self,
        allowed_tools: list[str] | None = None,
        denied_tools: list[str] | None = None,
        max_tools: int = 50,
    ) -> None:
        self.allowed_tools = [t.lower() for t in (allowed_tools or [])]
        self.denied_tools = [t.lower() for t in (denied_tools or [])]
        self.max_tools = max_tools

    def filter_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for tool in tools:
            name = str(tool.get("name", "")).lower()
            if self.denied_tools and name in self.denied_tools:
                continue
            if self.allowed_tools and name not in self.allowed_tools:
                continue
            filtered.append(tool)
            if len(filtered) >= self.max_tools:
                break
        return filtered

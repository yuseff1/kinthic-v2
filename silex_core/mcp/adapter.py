"""Wrap MCP tools as Kinthic BaseTool instances."""

from __future__ import annotations

import json
from typing import Any

from silex_core.tools.base import BaseTool


class McpToolAdapter(BaseTool):
    """Adapter that delegates execution to an MCP server session."""

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        call_fn,
        requires_approval: bool = False,
        risk_level: str = "read_only",
    ) -> None:
        self.server_name = server_name
        self.mcp_tool_name = tool_name
        self.name = f"mcp__{server_name}__{tool_name}"
        self.description = f"[MCP:{server_name}] {description}"
        self.schema = input_schema or {"type": "object", "properties": {}}
        self._call_fn = call_fn
        self.requires_approval = requires_approval
        self.risk_level = risk_level

    async def execute(self, **kwargs) -> str:
        try:
            result = await self._call_fn(self.mcp_tool_name, kwargs)
            if isinstance(result, str):
                return result
            return json.dumps(result, default=str)[:8000]
        except Exception as exc:
            return f"MCP tool error ({self.server_name}/{self.mcp_tool_name}): {exc}"

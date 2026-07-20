"""Start/stop stdio MCP servers and discover tools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from silex_core.mcp.adapter import McpToolAdapter
from silex_core.mcp.config import load_mcp_config
from silex_core.mcp.filter import ToolsetFilter

log = logging.getLogger("silex.mcp.manager")

_manager: "McpServerManager | None" = None


class McpServerManager:
    """Lazy-connect MCP servers and expose adapted tools."""

    def __init__(self) -> None:
        self._tools: list[McpToolAdapter] = []
        self._last_errors: dict[str, str] = {}
        self._server_configs: dict[str, dict[str, Any]] = {}

    def _mcp_available(self) -> bool:
        try:
            import mcp  # noqa: F401

            return True
        except ImportError:
            return False

    async def _run_with_session(
        self, name: str, cfg: dict[str, Any], fn: Callable[..., Awaitable[Any]]
    ) -> Any:
        if not self._mcp_available():
            raise RuntimeError("MCP extra not installed (pip install '.[mcp]')")

        command = cfg.get("command", "")
        args = list(cfg.get("args") or [])
        if not command:
            raise RuntimeError("Missing command in MCP config")

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=command, args=args)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        cfg = (
            self._server_configs.get(server_name)
            or load_mcp_config().get_server(server_name)
            or {}
        )
        if not cfg:
            raise RuntimeError(f"Unknown MCP server: {server_name}")

        async def _invoke(session) -> str:
            res = await session.call_tool(tool_name, arguments=arguments)
            parts = []
            for block in res.content or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts) if parts else str(res)

        return await self._run_with_session(server_name, cfg, _invoke)

    async def _discover_server_tools(
        self, name: str, cfg: dict[str, Any]
    ) -> list[McpToolAdapter]:
        if not self._mcp_available():
            self._last_errors[name] = "MCP extra not installed (pip install '.[mcp]')"
            return []

        approval_list = [t.lower() for t in cfg.get("requires_approval") or []]
        tool_filter = ToolsetFilter(
            allowed_tools=cfg.get("allowed_tools"),
            denied_tools=cfg.get("denied_tools"),
            max_tools=int(cfg.get("max_tools", 50)),
        )

        try:

            async def _list(session) -> list[dict[str, Any]]:
                listed = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema or {},
                    }
                    for t in listed.tools
                ]

            raw_tools = await self._run_with_session(name, cfg, _list)
            self._last_errors.pop(name, None)
        except Exception as exc:
            self._last_errors[name] = str(exc)
            log.warning("MCP server %s failed: %s", name, exc)
            return []

        adapted: list[McpToolAdapter] = []
        manager = self
        for tool_def in tool_filter.filter_tools(raw_tools):
            tname = tool_def["name"]

            async def _call(
                _tool: str, args: dict, _srv: str = name, _tname: str = tname
            ) -> str:
                return await manager.call_tool(_srv, _tname, args)

            adapted.append(
                McpToolAdapter(
                    server_name=name,
                    tool_name=tname,
                    description=tool_def.get("description", tname),
                    input_schema=tool_def.get("inputSchema") or {},
                    call_fn=_call,
                    requires_approval=tname.lower() in approval_list,
                    risk_level="repo_write"
                    if tname.lower() in approval_list
                    else "read_only",
                )
            )
        return adapted

    async def discover_tools(self) -> list[McpToolAdapter]:
        """Discover tools from all enabled MCP servers."""
        self._tools.clear()
        cfg = load_mcp_config()
        self._server_configs = dict(cfg.enabled_servers())
        for name, server_cfg in self._server_configs.items():
            tools = await self._discover_server_tools(name, server_cfg)
            self._tools.extend(tools)
        return self._tools

    def discover_tools_sync(self) -> list[McpToolAdapter]:
        """Synchronous wrapper for CLI/doctor."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return list(self._tools)
            return loop.run_until_complete(self.discover_tools())
        except RuntimeError:
            return asyncio.run(self.discover_tools())

    def get_adapted_tools(self) -> list[McpToolAdapter]:
        return list(self._tools)

    async def test_server(self, name: str) -> tuple[bool, str]:
        cfg = load_mcp_config()
        server = cfg.get_server(name)
        if not server:
            return False, f"Server '{name}' not found in mcp.yaml"
        tools = await self._discover_server_tools(name, server)
        if name in self._last_errors:
            return False, self._last_errors[name]
        return True, f"OK — {len(tools)} tool(s) available"

    def status_report(self) -> list[str]:
        cfg = load_mcp_config()
        lines: list[str] = []
        if not cfg.servers:
            lines.append("No MCP servers configured (~/.kinthic/config/mcp.yaml)")
            return lines
        if not self._mcp_available():
            lines.append("MCP Python package not installed — run: pip install '.[mcp]'")
        for name, server in cfg.servers.items():
            enabled = server.get("enabled", True)
            state = "enabled" if enabled else "disabled"
            err = self._last_errors.get(name)
            suffix = f" — ERROR: {err}" if err else ""
            approval = server.get("requires_approval") or []
            if approval:
                suffix += f" (approval: {', '.join(approval)})"
            lines.append(f"  {name}: {state}{suffix}")
        return lines


def get_mcp_manager() -> McpServerManager:
    global _manager
    if _manager is None:
        _manager = McpServerManager()
    return _manager


class MCPManager:
    """Wrapper to satisfy KinthicFacade expectations in silex_core/facade.py"""
    def __init__(self, tool_registry: Any):
        self.tool_registry = tool_registry
        
    async def start_all(self) -> None:
        try:
            adapted = await get_mcp_manager().discover_tools()
            for tool in adapted:
                self.tool_registry.register(tool)
        except Exception as exc:
            log.warning("MCP start_all failed: %s", exc)

    async def stop_all(self) -> None:
        pass


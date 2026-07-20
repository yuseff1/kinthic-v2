"""stdio MCP bridge — proxies to gateway Streamable HTTP when daemon is running."""

from __future__ import annotations

import asyncio

from silex_engine.mcp.server.app import create_mcp_stdio, set_mcp_context
from silex_engine.mcp.server.lifecycle import create_standalone_context
from silex_engine.config import KINTHIC_DAEMON_LOCK, gateway_host, gateway_port
from silex_engine.logger import setup_logger

log = setup_logger("silex.mcp.server.stdio_bridge")


async def gateway_reachable() -> bool:
    """True when the daemon lock exists and the gateway health probe responds."""
    if not KINTHIC_DAEMON_LOCK.exists():
        return False
    try:
        import httpx

        url = f"http://{gateway_host()}:{gateway_port()}/api/health"
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception as exc:
        log.warning("Daemon lock present but gateway unreachable (%s)", exc)
        return False


async def _run_stdio_proxy() -> None:
    """When daemon is up, proxy stdio MCP to gateway HTTP. Otherwise run standalone stdio."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import os

    if not await gateway_reachable():
        if KINTHIC_DAEMON_LOCK.exists():
            log.warning(
                "Stale daemon lock or gateway down — standalone MCP stdio "
                "(do not run alongside a live daemon on the same database)"
            )
        else:
            log.warning("Daemon not running — standalone MCP stdio")
        ctx = await create_standalone_context()
        set_mcp_context(ctx)
        mcp = create_mcp_stdio(ctx)
        await mcp.run_stdio_async()
        return

    url = f"http://{gateway_host()}:{gateway_port()}/mcp"
    api_key = os.getenv("KINTHIC_API_KEY")
    headers = {"x-kinthic-api-key": api_key}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            upstream_tools = listed.tools

            server = Server("silex-memory-proxy")

            @server.list_tools()
            async def list_tools_handler():
                return upstream_tools

            @server.call_tool()
            async def call_tool_handler(name: str, arguments: dict):
                result = await session.call_tool(name, arguments=arguments)
                return result.content

            @server.list_resources()
            async def list_resources_handler():
                res = await session.list_resources()
                return res.resources

            @server.read_resource()
            async def read_resource_handler(uri: str):
                res = await session.read_resource(uri)
                return res.contents

            @server.list_prompts()
            async def list_prompts_handler():
                res = await session.list_prompts()
                return res.prompts

            @server.get_prompt()
            async def get_prompt_handler(name: str, arguments: dict | None = None):
                res = await session.get_prompt(name, arguments=arguments or {})
                return res

            async with stdio_server() as (read_stdio, write_stdio):
                await server.run(
                    read_stdio, write_stdio, server.create_initialization_options()
                )


def run_stdio_bridge() -> None:
    if KINTHIC_DAEMON_LOCK.exists():
        log.info(
            "Daemon lock present — will proxy stdio MCP to %s:%s/mcp if gateway is up",
            gateway_host(),
            gateway_port(),
        )
    else:
        log.warning("Daemon not running — standalone MCP stdio")
    asyncio.run(_run_stdio_proxy())


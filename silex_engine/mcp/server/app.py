"""FastMCP application factory and gateway mount helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from silex_engine.mcp.server.lifecycle import McpServerContext
from silex_engine.mcp.server.schemas import (
    ForgetRequest,
    GraphRecallRequest,
    ListMemoriesRequest,
    RecallRequest,
    RememberExplicitRequest,
    RememberRequest,
    SearchRequest,
)
from silex_engine.mcp.server import service as svc
from silex_engine.logger import setup_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from mcp.server.fastmcp import FastMCP

log = setup_logger("silex.mcp.server.app")

_mcp_context: McpServerContext | None = None
_mcp_fastmcp: "FastMCP | None" = None


def get_mcp_context() -> McpServerContext | None:
    return _mcp_context


def get_mcp_fastmcp() -> "FastMCP | None":
    return _mcp_fastmcp


def set_mcp_context(ctx: McpServerContext | None) -> None:
    global _mcp_context
    _mcp_context = ctx


def register_tools(mcp: "FastMCP", ctx: McpServerContext) -> None:
    """Register all Silex memory tools, resources, and prompts on a FastMCP instance."""

    @mcp.tool()
    async def silex_recall(query: str, limit: int = 12) -> str:
        """Hybrid memory recall (recent + important + keyword + semantic RRF)."""
        return await svc.recall(ctx, RecallRequest(query=query, limit=limit))

    @mcp.tool()
    async def silex_search(query: str, limit: int = 20) -> str:
        """Keyword FTS search across stored memories."""
        return await svc.search(ctx, SearchRequest(query=query, limit=limit))

    @mcp.tool()
    async def silex_remember(
        content: str,
        memory_type: str = "semantic",
        importance: float = 0.6,
        tags: list[str] | None = None,
    ) -> str:
        """Store memory through full A-MAC admission pipeline; returns admission metadata."""
        return await svc.remember(
            ctx,
            RememberRequest(
                content=content,
                memory_type=memory_type,
                importance=importance,
                tags=tags or [],
            ),
        )

    @mcp.tool()
    async def silex_remember_explicit(
        content: str,
        importance: float = 0.7,
        tags: list[str] | None = None,
    ) -> str:
        """Store a user/agent fact directly (bypasses A-MAC; injection guard still applies)."""
        return await svc.remember_explicit(
            ctx,
            RememberExplicitRequest(
                content=content, importance=importance, tags=tags or []
            ),
        )

    @mcp.tool()
    async def silex_forget(memory_id: str, confirm: bool = False) -> str:
        """Delete a memory by ID. Requires confirm=true."""
        return await svc.forget(
            ctx, ForgetRequest(memory_id=memory_id, confirm=confirm)
        )

    @mcp.tool()
    async def silex_get_memory(memory_id: str) -> str:
        """Retrieve a single memory by UUID."""
        return await svc.get_memory(ctx, memory_id)

    @mcp.tool()
    async def silex_list_memories(
        offset: int = 0,
        limit: int = 20,
        tag: str | None = None,
    ) -> str:
        """List memories with pagination and optional tag filter."""
        return await svc.list_memories(
            ctx, ListMemoriesRequest(offset=offset, limit=limit, tag=tag)
        )

    @mcp.tool()
    async def silex_graph_recall(query: str, max_nodes: int = 15) -> str:
        """Graph-aware causal context retrieval from the knowledge graph."""
        return await svc.graph_recall(
            ctx, GraphRecallRequest(query=query, max_nodes=max_nodes)
        )

    @mcp.tool()
    async def silex_memory_health() -> str:
        """Memory engine health: counts, vector drift, FTS availability."""
        return await svc.memory_health(ctx)



    @mcp.resource("memory://catalog/recent")
    async def recent_memories() -> str:
        return await svc.list_memories(ctx, ListMemoriesRequest(offset=0, limit=10))

    @mcp.resource("memory://item/{memory_id}")
    async def memory_item(memory_id: str) -> str:
        return await svc.get_memory(ctx, memory_id)

    @mcp.resource("graph://beliefs/summary")
    async def graph_summary() -> str:
        return await svc.graph_summary(ctx)

    @mcp.prompt()
    async def silex_augmented_turn(user_message: str) -> str:
        recalled = await svc.recall(ctx, RecallRequest(query=user_message, limit=8))
        return (
            "Use the following recalled Silex memories as grounding. "
            "Do not invent facts not present in memory.\n\n"
            f"User message: {user_message}\n\n"
            f"Recalled context:\n{recalled}"
        )


def build_mcp_http(ctx: McpServerContext) -> "FastMCP":
    """FastMCP instance for Streamable HTTP (gateway mount at /mcp)."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    mcp = FastMCP(
        "silex-memory",
        instructions=(
            "Silex persistent memory engine for Kinthic. "
            "Use silex_recall for hybrid retrieval, silex_remember_explicit for reliable facts, "
            "and silex_graph_recall for causal knowledge graph context."
        ),
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1",
                "127.0.0.1:*",
                "localhost",
                "localhost:*",
                "[::1]",
                "[::1]:*",
            ],
            allowed_origins=[
                "http://127.0.0.1",
                "http://127.0.0.1:*",
                "http://localhost",
                "http://localhost:*",
                "http://[::1]",
                "http://[::1]:*",
            ],
        ),
    )
    register_tools(mcp, ctx)
    return mcp


def create_mcp_app(ctx: McpServerContext):
    return build_mcp_http(ctx).streamable_http_app()


def create_mcp_stdio(ctx: McpServerContext):
    """FastMCP instance for stdio transport (standalone mode)."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "silex-memory",
        instructions="Silex persistent memory engine for Kinthic.",
        stateless_http=True,
        json_response=True,
    )
    register_tools(mcp, ctx)
    return mcp


def mount_mcp_server(app: "FastAPI", cognitive_loop) -> "FastMCP":
    """Mount Streamable HTTP MCP on the gateway at /mcp.

    Returns the FastMCP instance so the gateway lifespan can run
    ``session_manager.run()`` (required for Streamable HTTP).
    """
    from silex_engine.mcp.server.lifecycle import context_from_loop

    global _mcp_fastmcp

    ctx = context_from_loop(cognitive_loop)
    set_mcp_context(ctx)
    _mcp_fastmcp = build_mcp_http(ctx)
    app.mount("/mcp", _mcp_fastmcp.streamable_http_app())
    log.info("Silex MCP server mounted at /mcp (Streamable HTTP)")
    return _mcp_fastmcp


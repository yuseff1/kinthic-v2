"""Attach MCP server to shared CognitiveLoop memory or standalone bootstrap."""

from __future__ import annotations

from dataclasses import dataclass

from silex_engine.memory.memory_store import MemoryStore
from silex_engine.mcp.server.auth import mcp_client_id
from silex_engine.mcp.server.audit import McpAuditLog, get_audit_log
from silex_engine.storage.database import Database
from silex_engine.config import SILEX_DB
from silex_engine.logger import setup_logger
from silex_engine.world.graph import KnowledgeGraph

log = setup_logger("silex.mcp.server.lifecycle")


@dataclass
class McpServerContext:
    memory: MemoryStore
    kg: KnowledgeGraph
    client_id: str
    audit: McpAuditLog
    standalone: bool = False
    skill_loader: object | None = None


async def create_standalone_context(db_path: str | None = None) -> McpServerContext:
    """Bootstrap MemoryStore when daemon is not running (demo / dev only)."""
    db = Database(db_path or str(SILEX_DB))
    await db.connect()
    memory = MemoryStore(db)
    kg = KnowledgeGraph(db)
    await kg.load()
    log.warning(
        "MCP standalone mode: not sharing daemon CognitiveLoop. "
        "Do not run concurrently with kinthic daemon."
    )
    return McpServerContext(
        memory=memory,
        kg=kg,
        client_id=mcp_client_id(),
        audit=get_audit_log(),
        standalone=True,
    )


def context_from_loop(cognitive_loop) -> McpServerContext:
    """Build context from a running CognitiveLoop (gateway lifespan)."""
    return McpServerContext(
        memory=cognitive_loop.memory,
        kg=cognitive_loop.kg,
        client_id=mcp_client_id(),
        audit=get_audit_log(),
        standalone=False,
        skill_loader=getattr(cognitive_loop, "skill_loader", None),
    )


def tag_for_client(client_id: str) -> str:
    return f"mcp_client:{client_id}"


def apply_client_tags(tags: list[str] | None, client_id: str) -> list[str]:
    base = list(tags or [])
    marker = tag_for_client(client_id)
    if marker not in base:
        base.append(marker)
    return base


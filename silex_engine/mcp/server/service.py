"""MCP tool business logic — thin wrapper over MemoryStore / KnowledgeGraph."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import ValidationError

from silex_engine.mcp.server.audit import get_audit_log
from silex_engine.mcp.server.lifecycle import McpServerContext, apply_client_tags
from silex_engine.mcp.server.schemas import (
    AdmissionInfo,
    ForgetRequest,
    ForgetResponse,
    GraphRecallRequest,
    GraphRecallResponse,
    ListMemoriesRequest,
    ListMemoriesResponse,
    MemoryHealthResponse,
    McpErrorCode,
    RecallRequest,
    RecallResponse,
    RememberExplicitRequest,
    RememberRequest,
    RememberResponse,
    SearchRequest,
    ToolError,
    memory_to_record,
)
from silex_engine.models.schemas import Memory, MemorySource, MemoryType
from silex_engine.logger import setup_logger

log = setup_logger("silex.mcp.server.service")


class McpToolError(Exception):
    def __init__(self, code: McpErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _tool_error(code: McpErrorCode, message: str) -> str:
    return json.dumps(ToolError(code=code, message=message).model_dump())


async def _guarded(ctx: McpServerContext, tool: str, arguments: dict[str, Any], fn):
    from silex_engine.utils import mcp_http_write_ctx

    audit = ctx.audit
    if not audit.check_rate_limit(ctx.client_id, tool):
        audit.record(
            tool=tool,
            client_id=ctx.client_id,
            arguments=arguments,
            outcome="error",
            latency_ms=0,
            error="rate limited",
        )
        return _tool_error(McpErrorCode.RATE_LIMITED, f"Rate limit exceeded for {tool}")
    start = time.perf_counter()
    outcome = "ok"
    error_msg: str | None = None
    token = mcp_http_write_ctx.set(True)
    try:
        result = await fn()
        return result
    except McpToolError as exc:
        outcome = "error"
        error_msg = exc.message
        return _tool_error(exc.code, exc.message)
    except ValidationError as exc:
        outcome = "error"
        error_msg = str(exc)
        return _tool_error(McpErrorCode.INVALID_ARGUMENT, error_msg)
    except Exception as exc:
        outcome = "error"
        error_msg = str(exc)
        log.exception("MCP tool %s failed", tool)
        return _tool_error(McpErrorCode.INTERNAL, str(exc))
    finally:
        mcp_http_write_ctx.reset(token)
        audit.record(
            tool=tool,
            client_id=ctx.client_id,
            arguments=arguments,
            outcome=outcome,
            latency_ms=(time.perf_counter() - start) * 1000,
            error=error_msg,
        )


async def recall(ctx: McpServerContext, req: RecallRequest) -> str:
    async def _run():
        memories = await ctx.memory.retrieve_context(req.query)
        records = [memory_to_record(m) for m in memories[: req.limit]]
        return RecallResponse(
            query=req.query, count=len(records), memories=records
        ).model_dump_json()

    return await _guarded(ctx, "silex_recall", req.model_dump(), _run)


async def search(ctx: McpServerContext, req: SearchRequest) -> str:
    async def _run():
        memories = await ctx.memory.search(req.query)
        records = [memory_to_record(m) for m in memories[: req.limit]]
        return RecallResponse(
            query=req.query, count=len(records), memories=records
        ).model_dump_json()

    return await _guarded(ctx, "silex_search", req.model_dump(), _run)


async def remember(ctx: McpServerContext, req: RememberRequest) -> str:
    async def _run():
        try:
            mtype = MemoryType(req.memory_type)
        except ValueError as exc:
            raise McpToolError(
                McpErrorCode.INVALID_ARGUMENT,
                f"Invalid memory_type: {req.memory_type}",
            ) from exc

        memory = Memory(
            content=req.content,
            source=MemorySource.USER,
            memory_type=mtype,
            importance=req.importance,
            tags=apply_client_tags(req.tags, ctx.client_id),
            provenance={"context": "mcp", "client_id": ctx.client_id},
        )
        result = await ctx.memory.add_with_result(memory)
        admission = AdmissionInfo(
            accepted=result["accepted"],
            reason=result["reason"],
            amac_score=result.get("amac_score"),
        )
        stored = result.get("memory")
        record = memory_to_record(stored, admission=admission) if stored else None
        return RememberResponse(admission=admission, memory=record).model_dump_json()

    return await _guarded(ctx, "silex_remember", req.model_dump(), _run)


async def remember_explicit(ctx: McpServerContext, req: RememberExplicitRequest) -> str:
    async def _run():
        stored = await ctx.memory.add_manual(
            req.content,
            importance=req.importance,
            tags=apply_client_tags(req.tags, ctx.client_id),
        )
        if stored is None:
            admission = AdmissionInfo(
                accepted=False, reason="guard_blocked", amac_score=None
            )
            return RememberResponse(admission=admission, memory=None).model_dump_json()
        admission = AdmissionInfo(accepted=True, reason="explicit", amac_score=None)
        return RememberResponse(
            admission=admission,
            memory=memory_to_record(stored, admission=admission),
        ).model_dump_json()

    return await _guarded(ctx, "silex_remember_explicit", req.model_dump(), _run)


async def forget(ctx: McpServerContext, req: ForgetRequest) -> str:
    async def _run():
        if not req.confirm:
            raise McpToolError(
                McpErrorCode.CONFIRMATION_REQUIRED,
                "Set confirm=true to delete a memory",
            )
        deleted = await ctx.memory.delete(req.memory_id)
        msg = "deleted" if deleted else "not found"
        log.warning("MCP forget %s: %s (client=%s)", req.memory_id, msg, ctx.client_id)
        return ForgetResponse(
            deleted=deleted, memory_id=req.memory_id, message=msg
        ).model_dump_json()

    return await _guarded(ctx, "silex_forget", req.model_dump(), _run)


async def get_memory(ctx: McpServerContext, memory_id: str) -> str:
    async def _run():
        mem = await ctx.memory.get(memory_id)
        if not mem:
            raise McpToolError(McpErrorCode.NOT_FOUND, f"Memory not found: {memory_id}")
        return memory_to_record(mem).model_dump_json()

    return await _guarded(ctx, "silex_get_memory", {"memory_id": memory_id}, _run)


async def list_memories(ctx: McpServerContext, req: ListMemoriesRequest) -> str:
    async def _run():
        page, total = await ctx.memory.list_page(req.offset, req.limit, tag=req.tag)
        records = [memory_to_record(m) for m in page]
        return ListMemoriesResponse(
            total=total,
            offset=req.offset,
            limit=req.limit,
            memories=records,
        ).model_dump_json()

    return await _guarded(ctx, "silex_list_memories", req.model_dump(), _run)


async def graph_summary(ctx: McpServerContext) -> str:
    async def _run():
        nodes = await ctx.kg.retrieve_relevant_context("memory knowledge", max_nodes=5)
        return json.dumps({"node_count": len(nodes), "sample": nodes[:5]})

    return await _guarded(ctx, "silex_graph_summary", {}, _run)


async def graph_recall(ctx: McpServerContext, req: GraphRecallRequest) -> str:
    async def _run():
        nodes = await ctx.kg.retrieve_relevant_context(
            req.query, max_nodes=req.max_nodes
        )
        return GraphRecallResponse(query=req.query, nodes=nodes).model_dump_json()

    return await _guarded(ctx, "silex_graph_recall", req.model_dump(), _run)


async def memory_health(ctx: McpServerContext) -> str:
    async def _run():
        count = await ctx.memory.count()
        drift = await ctx.memory.get_vector_drift_count()
        fts5 = await ctx.memory.fts5_available()
        audit = get_audit_log()
        return MemoryHealthResponse(
            memory_count=count,
            vector_active=ctx.memory.vs.is_active,
            vector_drift_count=drift,
            fts5_available=fts5,
            mcp_client_id=ctx.client_id,
            audit_log_path=str(audit.path),
        ).model_dump_json()

    return await _guarded(ctx, "silex_memory_health", {}, _run)


"""
Single emission API for Kinthic turn visibility (Python → Ink NDJSON bus).
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from silex_core.ui.turn_events import TurnEvent, TurnPhase, new_turn_id

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


class TurnEmitter:
    """Emits monotonic turn_event records and optional legacy mirror events."""

    def __init__(
        self,
        emit_fn: EmitFn,
        turn_id: str | None = None,
        *,
        mirror_legacy: bool = True,
    ) -> None:
        self._emit = emit_fn
        self.turn_id = turn_id or new_turn_id()
        self._seq = 0
        self._mirror_legacy = mirror_legacy
        self._workers_seen: set[str] = set()

    async def _next(
        self,
        phase: TurnPhase,
        title: str,
        detail: str = "",
        payload: dict[str, Any] | None = None,
    ) -> TurnEvent:
        self._seq += 1
        event = TurnEvent(
            turn_id=self.turn_id,
            seq=self._seq,
            phase=phase,
            title=title,
            detail=detail,
            payload=payload or {},
        )
        await self._emit(event.to_wire())
        if self._mirror_legacy:
            await self._mirror(event)
        return event

    async def _mirror(self, event: TurnEvent) -> None:
        """Keep legacy Ink reducers working during migration."""
        if event.phase in (
            TurnPhase.ROUTING,
            TurnPhase.CONTEXT,
            TurnPhase.TOOL,
            TurnPhase.RESPONSE,
        ):
            status = event.title or event.phase.value
            detail = event.detail or None
            await self._emit(
                {
                    "type": "thinking",
                    "data": {"status": status, "detail": detail},
                }
            )
        elif event.phase == TurnPhase.SUBAGENT:
            p = event.payload
            await self._emit(
                {
                    "type": "worker",
                    "data": {
                        "worker_id": p.get("worker_id", "unknown"),
                        "lifecycle": p.get("lifecycle", "running"),
                        "objective": p.get("objective", event.detail),
                        "parent_id": p.get("parent_id"),
                        "ancestry_chain": p.get("ancestry_chain", []),
                        "worker_class": p.get("worker_class", "worker"),
                        "detail": p.get("detail", ""),
                        "exit_code": p.get("exit_code"),
                        "turns_used": p.get("turns_used"),
                        "tokens_used": p.get("tokens_used"),
                        "timestamp": p.get("timestamp", time.time()),
                        "event_id": p.get("event_id", f"evt_{event.seq}"),
                    },
                }
            )
        elif event.phase == TurnPhase.APPROVAL:
            p = event.payload
            if p.get("resolved"):
                await self._emit(
                    {
                        "type": "approval_resolved",
                        "data": {
                            "approval_id": p.get("approval_id", ""),
                            "approved": bool(p.get("approved")),
                        },
                    }
                )
            else:
                await self._emit(
                    {
                        "type": "approval_requested",
                        "data": {
                            "approval_id": p.get("approval_id", ""),
                            "tool_name": p.get("tool_name", event.title),
                            "risk_level": p.get("risk_level", "unknown"),
                            "reason": p.get("reason", event.detail),
                            "arguments_preview": p.get("arguments_preview", {}),
                            "requested_at": p.get("requested_at", time.time()),
                        },
                    }
                )
        elif event.phase == TurnPhase.MEMORY:
            p = event.payload
            await self._emit(
                {
                    "type": "memory_write",
                    "data": {
                        "count": int(p.get("count", 0)),
                        "items": list(p.get("items") or []),
                    },
                }
            )
        elif event.phase == TurnPhase.SUMMARY:
            p = event.payload
            await self._emit(
                {
                    "type": "telemetry",
                    "data": {
                        "latencyMs": int(p.get("latencyMs", 0)),
                        "tokens": int(p.get("tokens", 0)),
                        "memoriesWritten": int(p.get("memoriesWritten", 0)),
                        "toolsExecuted": int(p.get("toolsExecuted", 0)),
                    },
                }
            )
        elif event.phase == TurnPhase.ERROR:
            await self._emit(
                {
                    "type": "error",
                    "data": {"message": event.detail or event.title},
                }
            )

    async def emit_raw(self, msg: dict[str, Any]) -> None:
        await self._emit(msg)

    async def user_message(self, text: str) -> TurnEvent:
        return await self._next(
            TurnPhase.USER, "You", detail=text, payload={"text": text}
        )

    async def routing(self, detail: str) -> TurnEvent:
        return await self._next(TurnPhase.ROUTING, "routing", detail=detail)

    async def context(self, detail: str) -> TurnEvent:
        return await self._next(TurnPhase.CONTEXT, "context", detail=detail)

    async def tool_start(self, tool_name: str, detail: str = "") -> TurnEvent:
        return await self._next(
            TurnPhase.TOOL, tool_name, detail=detail or f"{tool_name} started"
        )

    async def tool_progress(self, tool_name: str, detail: str) -> TurnEvent:
        return await self._next(TurnPhase.TOOL, tool_name, detail=detail)

    async def tool_done(self, tool_name: str, detail: str = "") -> TurnEvent:
        return await self._next(
            TurnPhase.TOOL, tool_name, detail=detail or f"{tool_name} done"
        )

    async def subagent(
        self,
        worker_id: str,
        lifecycle: str,
        *,
        objective: str = "",
        worker_class: str = "worker",
        detail: str = "",
        parent_id: str | None = None,
        ancestry_chain: list[str] | None = None,
        exit_code: int | None = None,
        turns_used: int | None = None,
        tokens_used: int | None = None,
    ) -> TurnEvent:
        if worker_id:
            self._workers_seen.add(worker_id)
        return await self._next(
            TurnPhase.SUBAGENT,
            worker_class,
            detail=objective or detail,
            payload={
                "worker_id": worker_id,
                "lifecycle": lifecycle,
                "objective": objective,
                "worker_class": worker_class,
                "detail": detail,
                "parent_id": parent_id,
                "ancestry_chain": ancestry_chain or [],
                "exit_code": exit_code,
                "turns_used": turns_used,
                "tokens_used": tokens_used,
                "event_id": f"evt_{worker_id}_{lifecycle}_{self._seq}",
                "timestamp": time.time(),
            },
        )

    async def approval_request(
        self,
        approval_id: str,
        tool_name: str,
        risk_level: str,
        reason: str,
        arguments_preview: dict | None = None,
    ) -> TurnEvent:
        return await self._next(
            TurnPhase.APPROVAL,
            tool_name,
            detail=reason,
            payload={
                "approval_id": approval_id,
                "tool_name": tool_name,
                "risk_level": risk_level,
                "reason": reason,
                "arguments_preview": arguments_preview or {},
                "requested_at": time.time(),
                "resolved": False,
            },
        )

    async def approval_result(
        self,
        approval_id: str,
        tool_name: str,
        risk_level: str,
        approved: bool,
    ) -> TurnEvent:
        return await self._next(
            TurnPhase.APPROVAL,
            tool_name,
            detail="allowed" if approved else "denied",
            payload={
                "approval_id": approval_id,
                "tool_name": tool_name,
                "risk_level": risk_level,
                "reason": "",
                "approved": approved,
                "resolved": True,
            },
        )

    async def response_phase(self, detail: str) -> TurnEvent:
        return await self._next(TurnPhase.RESPONSE, "response", detail=detail)

    async def assistant_done(self, text: str) -> TurnEvent:
        await self._emit({"type": "stream", "data": {"text": text}})
        return await self._next(
            TurnPhase.RESPONSE,
            "Kinthic",
            detail=text[:120],
            payload={"text": text},
        )

    async def memory(self, count: int, items: list[str]) -> TurnEvent:
        return await self._next(
            TurnPhase.MEMORY,
            "memory",
            detail=f"wrote {count} item(s)",
            payload={"count": count, "items": items},
        )

    async def error(self, message: str) -> TurnEvent:
        return await self._next(TurnPhase.ERROR, "error", detail=message)

    async def turn_summary(
        self,
        *,
        latency_ms: int,
        tokens: int,
        memories_written: int,
        tools_executed: int,
        workers_used: int | None = None,
    ) -> TurnEvent:
        workers = workers_used if workers_used is not None else len(self._workers_seen)
        return await self._next(
            TurnPhase.SUMMARY,
            "summary",
            detail=f"{latency_ms / 1000:.2f}s · {tools_executed} tool(s) · {memories_written} memory",
            payload={
                "latencyMs": latency_ms,
                "tokens": tokens,
                "memoriesWritten": memories_written,
                "toolsExecuted": tools_executed,
                "workersUsed": workers,
            },
        )

    @property
    def workers_used(self) -> int:
        return len(self._workers_seen)


def worker_aware_emit(turn_emitter: TurnEmitter) -> EmitFn:
    """Route orchestrator worker events through TurnEmitter.subagent()."""

    async def emit(msg: dict[str, Any]) -> None:
        if msg.get("type") == "worker":
            d = msg.get("data") or {}
            await turn_emitter.subagent(
                str(d.get("worker_id", "")),
                str(d.get("lifecycle", "running")),
                objective=str(d.get("objective", "")),
                worker_class=str(d.get("worker_class", "worker")),
                detail=str(d.get("detail", "")),
                parent_id=d.get("parent_id"),
                ancestry_chain=list(d.get("ancestry_chain") or []),
                exit_code=d.get("exit_code"),
                turns_used=d.get("turns_used"),
                tokens_used=d.get("tokens_used"),
            )
        else:
            await turn_emitter.emit_raw(msg)

    return emit

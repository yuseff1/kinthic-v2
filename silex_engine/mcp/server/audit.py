"""NDJSON audit logging and per-tool rate limits for MCP calls."""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from silex_engine.config import KINTHIC_HOME
from silex_engine.logger import setup_logger

log = setup_logger("silex.mcp.server.audit")

AUDIT_PATH = KINTHIC_HOME / "logs" / "mcp-audit.ndjson"

# Per-tool limits: (max_calls, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "silex_recall": (60, 60),
    "silex_search": (60, 60),
    "silex_remember": (20, 60),
    "silex_remember_explicit": (30, 60),
    "silex_forget": (10, 60),
    "silex_get_memory": (60, 60),
    "silex_list_memories": (30, 60),
    "silex_graph_recall": (30, 60),
    "silex_graph_summary": (30, 60),
    "silex_memory_health": (30, 60),
}


@dataclass
class _Bucket:
    timestamps: list[float] = field(default_factory=list)


class McpAuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or AUDIT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self.last_error: str | None = None

    def _client_key(self, client_id: str, tool: str) -> str:
        return f"{client_id}:{tool}"

    def check_rate_limit(self, client_id: str, tool: str) -> bool:
        limit, window = RATE_LIMITS.get(tool, (120, 60))
        key = self._client_key(client_id, tool)
        bucket = self._buckets[key]
        now = time.time()
        bucket.timestamps = [t for t in bucket.timestamps if now - t < window]
        if len(bucket.timestamps) >= limit:
            return False
        bucket.timestamps.append(now)
        return True

    def _hash_args(self, arguments: dict[str, Any]) -> str:
        raw = json.dumps(arguments, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def record(
        self,
        *,
        tool: str,
        client_id: str,
        arguments: dict[str, Any],
        outcome: str,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        entry = {
            "ts": time.time(),
            "tool": tool,
            "client_id": client_id,
            "args_hash": self._hash_args(arguments),
            "outcome": outcome,
            "latency_ms": round(latency_ms, 2),
        }
        if error:
            entry["error"] = error
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            self.last_error = str(exc)
            log.warning("Failed to write MCP audit log: %s", exc)


_audit: McpAuditLog | None = None


def get_audit_log() -> McpAuditLog:
    global _audit
    if _audit is None:
        _audit = McpAuditLog()
    return _audit


"""
Stable MCP tool contracts for the Silex memory server.

RFC: docs/mcp-server-rfc.md
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class McpErrorCode(str, Enum):
    """Machine-readable error codes returned in tool payloads."""

    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    GUARD_BLOCKED = "guard_blocked"
    ADMISSION_REJECTED = "admission_rejected"
    DUPLICATE = "duplicate"
    CONFIRMATION_REQUIRED = "confirmation_required"
    INTERNAL = "internal"


class AdmissionInfo(BaseModel):
    accepted: bool
    reason: str = Field(
        description="duplicate | guard_blocked | amac_rejected | accepted | explicit"
    )
    amac_score: float | None = None


class MemoryRecord(BaseModel):
    memory_id: str
    content: str
    source: str
    memory_type: str
    importance: float
    confidence: float
    tags: list[str] = Field(default_factory=list)
    created_at: str
    last_accessed: str = ""
    admission: AdmissionInfo | None = None


class RecallRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=12, ge=1, le=50)


class RecallResponse(BaseModel):
    query: str
    count: int
    memories: list[MemoryRecord]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=20, ge=1, le=100)


class RememberRequest(BaseModel):
    content: str = Field(min_length=5, max_length=1000)
    memory_type: str = Field(default="semantic")
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class RememberExplicitRequest(BaseModel):
    content: str = Field(min_length=5, max_length=1000)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class RememberResponse(BaseModel):
    admission: AdmissionInfo
    memory: MemoryRecord | None = None


class ForgetRequest(BaseModel):
    memory_id: str
    confirm: bool = False


class ForgetResponse(BaseModel):
    deleted: bool
    memory_id: str
    message: str


class ListMemoriesRequest(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    tag: str | None = None


class ListMemoriesResponse(BaseModel):
    total: int
    offset: int
    limit: int
    memories: list[MemoryRecord]


class GraphRecallRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    max_nodes: int = Field(default=15, ge=1, le=50)


class GraphRecallResponse(BaseModel):
    query: str
    nodes: list[dict[str, Any]]


class MemoryHealthResponse(BaseModel):
    memory_count: int
    vector_active: bool
    vector_drift_count: int
    fts5_available: bool
    mcp_client_id: str
    audit_log_path: str


class ToolError(BaseModel):
    code: McpErrorCode
    message: str


def memory_to_record(memory, *, admission: AdmissionInfo | None = None) -> MemoryRecord:
    """Convert a Memory ORM model to a stable MCP record."""
    mtype = (
        memory.memory_type.value
        if hasattr(memory.memory_type, "value")
        else str(memory.memory_type)
    )
    src = memory.source.value if hasattr(memory.source, "value") else str(memory.source)
    return MemoryRecord(
        memory_id=memory.id,
        content=memory.content,
        source=src,
        memory_type=mtype,
        importance=float(memory.importance),
        confidence=float(memory.confidence),
        tags=list(memory.tags or []),
        created_at=memory.created_at,
        last_accessed=getattr(memory, "last_accessed", "") or "",
        admission=admission,
    )

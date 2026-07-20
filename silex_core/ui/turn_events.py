"""
Canonical turn event schema for Kinthic operator UI.

All Python surfaces emit TurnEvent records through TurnEmitter so the Ink
ledger can render a trustworthy chronological stream without string guessing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TurnPhase(str, Enum):
    USER = "user"
    ROUTING = "routing"
    CONTEXT = "context"
    TOOL = "tool"
    SUBAGENT = "subagent"
    APPROVAL = "approval"
    RESPONSE = "response"
    MEMORY = "memory"
    ERROR = "error"
    SUMMARY = "summary"


@dataclass
class TurnEvent:
    turn_id: str
    seq: int
    phase: TurnPhase
    title: str
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": "turn_event",
            "data": {
                "turn_id": self.turn_id,
                "seq": self.seq,
                "phase": self.phase.value,
                "title": self.title,
                "detail": self.detail,
                "payload": self.payload,
            },
        }

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> TurnEvent:
        return cls(
            turn_id=str(data["turn_id"]),
            seq=int(data["seq"]),
            phase=TurnPhase(str(data["phase"])),
            title=str(data.get("title", "")),
            detail=str(data.get("detail", "")),
            payload=dict(data.get("payload") or {}),
        )


def new_turn_id() -> str:
    return f"turn_{uuid.uuid4().hex[:12]}"

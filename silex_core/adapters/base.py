"""Base class for messaging platform adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    Any


class MessageAdapter(ABC):
    """
    Bridge between an external chat platform and V2 loop.

    Each adapter owns platform I/O (polling/webhooks) and routes inbound
    messages through loop.process(), respecting tool approval gates.
    """

    name: str = "base"

    def __init__(self) -> None:
        self._loop: Any | None = None

    @property
    def loop(self) -> Any:
        if self._loop is None:
            raise RuntimeError(f"{self.name} adapter: loop not initialized")
        return self._loop

    async def startup(self) -> None:
        """Initialize the shared cognitive engine."""
        from silex_core.harness.wrapper import LoopWrapper
        self._loop = LoopWrapper()
        await self._loop.startup()

    async def shutdown(self) -> None:
        if self._loop is not None:
            await self._loop.shutdown()
            self._loop = None

    async def process_text(
        self,
        text: str,
        *,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        """Route a user message through CognitiveLoop and return the reply."""
        result = await self.loop.process(text, images=images)
        return getattr(result, "response", str(result))

    @classmethod
    @abstractmethod
    def is_configured(cls) -> bool:
        """Return True when required env vars / settings are present."""

    @abstractmethod
    def run(self) -> None:
        """Blocking entry point — start polling / webhook server."""

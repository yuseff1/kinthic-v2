"""
Telegram bot entry point — delegates to silex.adapters.telegram.

Kept for backward compatibility with `kinthic telegram run` and daemon worker.
"""

from __future__ import annotations

from silex_core.adapters.telegram import TelegramAdapter, get_active_loop


class _LoopProxy:
    """Backward-compatible alias used by older imports and tests."""

    def __getattr__(self, name: str):
        loop = get_active_loop()
        if loop is None:
            raise AttributeError(name)
        return getattr(loop, name)


kinthic_loop = _LoopProxy()


def main() -> None:
    TelegramAdapter().run()


if __name__ == "__main__":
    main()

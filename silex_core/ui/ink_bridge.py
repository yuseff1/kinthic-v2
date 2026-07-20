"""
silex/ui/ink_bridge.py — Kinthic Ink UI subprocess bridge.  (v3 — file-pipe architecture)

Pipe Architecture
─────────────────
  Python → Ink  :  localhost TCP push (KINTHIC_EVENTS_PORT) when Ink connects
                   ~/.kinthic/ink_events.ndjson  (50ms poll fallback / debug)
  Ink → terminal:  proc.stdout = None            (inherits TTY; Ink renders)
  Ink keyboard  :  proc.stdin  = None            (inherits TTY; Ink owns keyboard)
  Ink → Python  :  proc.stderr = PIPE            (JSON packets: user_input + auth_response)

Why NOT stdin=PIPE for Python→Ink?
  ink-text-input and useInput() read from process.stdin. If stdin is PIPE,
  those hooks read Python's JSON events as keyboard bytes — completely broken.
  stdin must be None (TTY) so Ink exclusively owns the keyboard.

Why a file instead of stdin for Python→Ink events?
  With stdin=None (TTY), Python has no pipe handle into Ink's process at all.
  A polled NDJSON file is the simplest cross-platform alternative. Node's
  fs.watchFile / setInterval is perfectly adequate for event rates ≤ 30 Hz.

Fallback
────────
  If Node/npx is not found, the bridge silently no-ops and Rich takes over.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from silex_core.utils.tasks import safe_create_task

log = logging.getLogger("silex.ui.ink_bridge")

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_INK_ROOT = _REPO_ROOT / "kinthic-ink-ui"
_INK_DIST = _INK_ROOT / "dist" / "index.js"
_INK_SRC = _INK_ROOT / "src" / "index.tsx"

_KINTHIC_DIR = Path.home() / ".kinthic"
_EVENTS_FILE = _KINTHIC_DIR / "ink_events.ndjson"  # Python → Ink event bus
_COMPILED_UI = _KINTHIC_DIR / "bin" / "kinthic-ui"


# ── Capability detection ──────────────────────────────────────────────────────


def _build_launch_cmd() -> list[str] | None:
    import shutil

    # 1. Check for pre-compiled binary in ~/.kinthic/bin/
    if _COMPILED_UI.exists() and os.access(str(_COMPILED_UI), os.X_OK):
        return [str(_COMPILED_UI)]

    # 2. Fall back to local developer environment
    node = shutil.which("node")
    if node and _INK_DIST.exists():
        return [node, str(_INK_DIST)]
    npx = shutil.which("npx")
    if npx and _INK_SRC.exists():
        return [npx, "tsx", str(_INK_SRC)]
    return None


def _diagnose_launch_unavailable() -> str:
    """Return a human-readable reason the production Ink UI cannot launch."""
    import shutil

    if not _INK_ROOT.exists():
        return f"Missing Ink UI directory: {_INK_ROOT}"
    if _COMPILED_UI.exists() and not os.access(str(_COMPILED_UI), os.X_OK):
        return f"Compiled UI exists but is not executable: {_COMPILED_UI}"
    if not shutil.which("node") and not shutil.which("npx"):
        return "Node.js/npx not found on PATH. Install Node 18+ or run `npm install` in kinthic-ink-ui."
    if shutil.which("node") and not _INK_DIST.exists() and not shutil.which("npx"):
        return f"Ink build missing: {_INK_DIST}. Run `cd kinthic-ink-ui && npm install && npm run build`."
    if shutil.which("npx") and not _INK_SRC.exists():
        return f"Ink source entry missing: {_INK_SRC}"
    return (
        "Ink UI not launchable. Run `cd kinthic-ink-ui && npm install && npm run build`, "
        "then restart Kinthic."
    )


# ── Bridge ────────────────────────────────────────────────────────────────────


class KinthicInkBridge:
    """
    Async bridge between the Python cognitive loop and the Ink terminal UI.

    Message flow
    ────────────
    Python → Ink:  self.emit()   appends JSON line to _EVENTS_FILE
    Ink → Python:  _stderr_reader() drains proc.stderr, routes to queues:
                     type=user_input   → _user_input_queue
                     type=auth_response → _auth_queue
    """

    def __init__(self, header_metadata: dict[str, Any] | None = None) -> None:
        self._metadata: dict[str, Any] = header_metadata or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._user_input_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=100)
        self._auth_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._cancel_queue: asyncio.Queue[bool] = asyncio.Queue(maxsize=100)
        self._approval_response_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._enabled: bool = False
        self._use_tcp: bool = False
        self._event_server: asyncio.Server | None = None
        self._event_writers: list[asyncio.StreamWriter] = []
        self._pending_event_lines: list[str] = []
        self._events_port: int = 0
        self._cmd: list[str] | None = _build_launch_cmd()
        self._fallback_reason: str = "" if self._cmd else _diagnose_launch_unavailable()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the Ink subprocess, clear the event bus, emit the header."""
        if self._cmd is None:
            log.warning(
                "kinthic-ink-ui: not available — falling back to Rich. %s",
                self._fallback_reason,
            )
            return

        # Prepare the event file: truncate to signal a fresh session start (fallback / debug)
        _KINTHIC_DIR.mkdir(parents=True, exist_ok=True)
        _EVENTS_FILE.write_text("", encoding="utf-8")

        # Phase B: localhost TCP push (Hermes-style instant delivery vs 50ms file poll)
        self._event_server = await asyncio.start_server(
            self._handle_event_client,
            "127.0.0.1",
            0,
        )
        self._events_port = int(self._event_server.sockets[0].getsockname()[1])
        self._use_tcp = True

        env = {
            **os.environ,
            "FORCE_COLOR": "3",
            "KINTHIC_EVENTS_FILE": str(_EVENTS_FILE),
            "KINTHIC_EVENTS_PORT": str(self._events_port),
        }

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._cmd,
                # stdin=None → Ink inherits the real TTY → keyboard works
                stdin=None,
                # stdout=None → Ink renders directly into the user's terminal
                stdout=None,
                # stderr=PIPE → Python reads user_input + auth_response JSON
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(_INK_ROOT) if _INK_ROOT.is_dir() else None,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            self._fallback_reason = (
                f"Failed to spawn Ink UI command `{self._cmd}`: {exc}"
            )
            log.warning("kinthic-ink-ui: spawn failed: %s", exc)
            return

        self._enabled = True

        # Close Python's own stdin was removed because it is redundant and causes terminal freezes on subprocess crashes.

        # Background reader for Ink → Python packets
        self._reader_task = safe_create_task(
            self._stderr_reader(), name="ink-stderr-reader"
        )

        # Brief pause so Ink renders its first frame before header arrives
        await asyncio.sleep(0.15)
        await self._send_header()
        await self._send_commands()

    async def stop(self) -> None:
        """Emit the done event, drain, and wait for clean exit."""
        if not self._enabled or self._proc is None:
            return

        await self.emit({"type": "done"})
        # Signal the user_input reader to unblock any waiting call
        await self._user_input_queue.put(None)

        try:
            await asyncio.wait_for(self._proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            self._proc.kill()

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        for writer in self._event_writers:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._event_writers.clear()

        if self._event_server is not None:
            self._event_server.close()
            await self._event_server.wait_closed()
            self._event_server = None

        self._enabled = False
        self._use_tcp = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def emit(self, msg: dict[str, Any]) -> None:
        """Push a JSON event to Ink (TCP when connected, else buffer or file fallback)."""
        if not self._enabled:
            return
        try:
            line = json.dumps(msg, ensure_ascii=False) + "\n"
            if self._use_tcp:
                if self._event_writers:
                    await self._push_event_line(line)
                else:
                    self._pending_event_lines.append(line)
                return
            with open(_EVENTS_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as exc:
            log.warning("kinthic-ink-ui: event write failed: %s", exc)
            self._enabled = False

    async def _push_event_line(self, line: str) -> None:
        dead: list[asyncio.StreamWriter] = []
        data = line.encode("utf-8")
        for writer in self._event_writers:
            try:
                writer.write(data)
                await writer.drain()
            except (ConnectionError, OSError, asyncio.CancelledError):
                dead.append(writer)
        for writer in dead:
            if writer in self._event_writers:
                self._event_writers.remove(writer)

    async def _handle_event_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._event_writers.append(writer)
        try:
            if self._pending_event_lines:
                for line in self._pending_event_lines:
                    writer.write(line.encode("utf-8"))
                await writer.drain()
                self._pending_event_lines.clear()
            await reader.read()
        except Exception:
            pass
        finally:
            if writer in self._event_writers:
                self._event_writers.remove(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def emit_error(self, message: str) -> None:
        """Return Ink UI to prompt state and surface an operator-visible error."""
        await self.emit({"type": "error", "data": {"message": message}})
        await self.emit({"type": "response", "data": {"text": f"Error: {message}"}})

    async def emit_cancel(self, message: str = "Thinking cancelled.") -> None:
        """Return Ink UI to prompt state after an interrupted turn."""
        await self.emit({"type": "cancel", "data": {"message": message}})
        await self.emit({"type": "response", "data": {"text": message}})

    async def emit_approval_requested(
        self,
        approval_id: str,
        tool_name: str,
        risk_level: str,
        reason: str,
        arguments_preview: dict | None = None,
    ) -> None:
        """Surface a pending tool approval in the operator UI."""
        import time

        await self.emit(
            {
                "type": "approval_requested",
                "data": {
                    "approval_id": approval_id,
                    "tool_name": tool_name,
                    "risk_level": risk_level,
                    "reason": reason,
                    "arguments_preview": arguments_preview or {},
                    "requested_at": time.time(),
                },
            }
        )

    async def emit_approval_resolved(self, approval_id: str, approved: bool) -> None:
        """Dismiss a resolved approval from the queue."""
        await self.emit(
            {
                "type": "approval_resolved",
                "data": {"approval_id": approval_id, "approved": approved},
            }
        )

    async def emit_active_goal(
        self, goal_id: str, description: str, status: str, run_id: str = ""
    ) -> None:
        """Push the current background goal status to the operator bar."""
        import time

        await self.emit(
            {
                "type": "active_goal",
                "data": {
                    "goal_id": goal_id,
                    "description": description,
                    "status": status,
                    "run_id": run_id,
                    "last_heartbeat": time.time(),
                },
            }
        )

    async def emit_cost_update(
        self,
        total_cost_usd: float,
        total_tokens: int,
        turns: int,
        model: str = "",
    ) -> None:
        """Push accumulated cost/usage metrics to the operator bar."""
        await self.emit(
            {
                "type": "cost_update",
                "data": {
                    "total_cost_usd": total_cost_usd,
                    "total_tokens": total_tokens,
                    "turns": turns,
                    "model": model,
                },
            }
        )

    async def read_user_input(self, timeout: float | None = None) -> str | None:
        """
        Block until Ink sends a user_input packet via stderr.
        Returns the text string, or None if the bridge closed / timed out.
        """
        if not self._enabled:
            return None
        try:
            coro = self._user_input_queue.get()
            result = (
                await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
            )
            return result  # None signals bridge shutdown
        except asyncio.TimeoutError:
            return None

    async def read_auth_response(self, timeout: float = 120.0) -> dict | None:
        """Block until Ink sends an auth_response packet."""
        if not self._enabled:
            return None
        try:
            return await asyncio.wait_for(self._auth_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            log.warning("kinthic-ink-ui: auth timeout after %ss", timeout)
            return None

    async def read_cancel_request(self) -> bool:
        """Block until the user presses Escape in Ink (cancel_request packet)."""
        if not self._enabled:
            # Never cancel in non-Ink mode (keyboard is handled differently)
            await asyncio.sleep(3600)
            return False
        return await self._cancel_queue.get()

    async def read_approval_response(self, timeout: float = 120.0) -> dict | None:
        """Block until Ink sends an approval_response packet."""
        if not self._enabled:
            return None
        try:
            return await asyncio.wait_for(
                self._approval_response_queue.get(), timeout=timeout
            )
        except asyncio.TimeoutError:
            log.warning("kinthic-ink-ui: approval_response timeout after %ss", timeout)
            return None

    @property
    def is_active(self) -> bool:
        return self._enabled and self._proc is not None

    @property
    def fallback_reason(self) -> str:
        return self._fallback_reason or "Ink UI unavailable; using Rich fallback."

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _send_header(self) -> None:
        try:
            from silex import __version__

            version = __version__
        except Exception:
            version = "1.0.0"

        skill_count = 0
        try:
            from silex_core.utils.config import KINTHIC_HOME

            d = KINTHIC_HOME / "skills"
            if d.is_dir():
                skill_count = len(list(d.glob("*.md")))
        except Exception:
            pass

        import os as _os

        try:
            cwd = _os.getcwd()
        except Exception:
            cwd = "~"

        await self.emit(
            {
                "type": "header",
                "data": {
                    "platform": self._metadata.get("platform", "OpenYF (λ) Enterprise"),
                    "core": self._metadata.get("core", "SILEX Reasoning Engine"),
                    "version": self._metadata.get("version", version),
                    "skillCount": skill_count,
                    "storageMode": self._metadata.get(
                        "storageMode", "SQLite + ChromaDB"
                    ),
                    "cwd": self._metadata.get("cwd", cwd),
                },
            }
        )

    async def _send_commands(self) -> None:
        from silex_core.ui.commands import SLASH_COMMANDS

        await self.emit({"type": "init_commands", "data": {"commands": SLASH_COMMANDS}})

    async def _stderr_reader(self) -> None:
        """
        Drain proc.stderr line-by-line.
        Routes user_input → _user_input_queue
                auth_response → _auth_queue
        Discards non-JSON lines (Node warnings, stack traces).
        """
        assert self._proc and self._proc.stderr

        while True:
            try:
                raw = await self._proc.stderr.readline()
            except (asyncio.IncompleteReadError, OSError):
                break
            if not raw:
                break

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                packet = json.loads(line)
            except json.JSONDecodeError:
                log.debug("ink stderr (non-JSON): %.120s", line)
                continue

            ptype = packet.get("type", "")
            if ptype == "user_input":
                text = packet.get("params", {}).get("text", "")
                await self._user_input_queue.put(text)
            elif ptype == "auth_response":
                await self._auth_queue.put(packet)
            elif ptype == "cancel_request":
                await self._cancel_queue.put(True)
            elif ptype == "approval_response":
                await self._approval_response_queue.put(packet)
            else:
                log.debug("ink stderr packet: %s", packet)

        # Unblock any waiting read_user_input() when Ink exits
        await self._user_input_queue.put(None)


def create_bridge(**kwargs: Any) -> KinthicInkBridge:
    return KinthicInkBridge(header_metadata=kwargs)

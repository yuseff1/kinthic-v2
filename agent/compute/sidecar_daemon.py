"""
Sidecar Daemon for Kinthic Sandboxes.

Listens on a Unix domain socket for host-orchestrator payloads.
Lease HMAC verification happens on the host; the sidecar validates a
per-worker session secret passed at container spawn (fail-closed).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("sidecar")

_worker_id = os.environ.get("KINTHIC_WORKER_ID")
_default_timeout = float(os.environ.get("KINTHIC_SIDECAR_DEFAULT_TIMEOUT", "600"))
if _worker_id:
    SOCKET_PATH = f"/run/kinthic_sockets/kinthic_{_worker_id}.sock"
else:
    SOCKET_PATH = "/workspace/kinthic.sock"
SOCKET_MODE = 0o660


def _validate_payload(payload: dict) -> tuple[str | None, float | None, str | None]:
    """Validate session key and extract command. Returns (command, timeout, error)."""
    session_key = payload.get("session_key")
    expected_key = os.environ.get("KINTHIC_WORKER_SESSION_KEY", "")
    if not expected_key or not session_key:
        return None, None, "Missing session_key — unauthenticated execution denied"
    if not isinstance(session_key, str) or not isinstance(expected_key, str):
        return None, None, "Invalid session_key format"
    if len(session_key) != len(expected_key):
        return None, None, "Invalid session_key"
    # Constant-time compare without importing hmac for minimal deps in sidecar
    mismatch = 0
    for a, b in zip(session_key.encode(), expected_key.encode()):
        mismatch |= a ^ b
    if mismatch:
        return None, None, "Invalid session_key"

    command = payload.get("command")
    if not command or not isinstance(command, str):
        return None, None, "No command provided"

    timeout_raw = payload.get("timeout_seconds", _default_timeout)
    try:
        timeout = max(1.0, min(float(timeout_raw), 3600.0))
    except (TypeError, ValueError):
        timeout = _default_timeout

    return command, timeout, None


def _preexec_setsid() -> None:
    os.setsid()


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        process.kill()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass


async def handle_client(reader, writer) -> None:
    process: asyncio.subprocess.Process | None = None
    try:
        data = await reader.read()
        if not data:
            return

        payload = json.loads(data.decode("utf-8"))
        command, timeout, error = _validate_payload(payload)
        if error:
            writer.write(json.dumps({"error": error, "exit_code": -1}).encode("utf-8"))
            await writer.drain()
            return

        log.info("Executing authenticated command: %s...", command[:50])

        workspace_cwd = os.environ.get("WORKSPACE_DIR", "/workspace")
        if not os.path.exists(workspace_cwd):
            workspace_cwd = os.getcwd()

        shell_kwargs: dict = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": workspace_cwd,
        }
        if os.name != "nt":
            shell_kwargs["preexec_fn"] = _preexec_setsid

        process = await asyncio.create_subprocess_shell(
            command,
            **shell_kwargs,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            exit_code = process.returncode
        except asyncio.TimeoutError:
            log.warning("Command timed out after %.0fs; killing process group", timeout)
            await _kill_process_tree(process)
            writer.write(
                json.dumps(
                    {
                        "error": f"Command timed out after {timeout:.0f} seconds",
                        "exit_code": -1,
                        "output": "",
                    }
                ).encode("utf-8")
            )
            await writer.drain()
            return

        output = (stdout + stderr).decode("utf-8", errors="replace")
        response = {
            "output": output,
            "exit_code": exit_code if exit_code is not None else -1,
        }
        writer.write(json.dumps(response).encode("utf-8"))
        await writer.drain()
    except Exception as e:
        log.error("Error handling request: %s", e)
        if process is not None:
            await _kill_process_tree(process)
        error_resp = {
            "output": f"Sidecar Error: {type(e).__name__}",
            "exit_code": -1,
        }
        writer.write(json.dumps(error_resp).encode("utf-8"))
        await writer.drain()
    finally:
        writer.close()


async def main() -> None:
    parent_dir = os.path.dirname(SOCKET_PATH)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server = await asyncio.start_unix_server(handle_client, path=SOCKET_PATH)
    os.chmod(SOCKET_PATH, SOCKET_MODE)
    log.info("Sidecar listening on %s (mode %o)", SOCKET_PATH, SOCKET_MODE)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

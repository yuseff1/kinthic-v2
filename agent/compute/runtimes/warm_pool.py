"""
Warm pool manager for Docker containers.
Maintains a pool of pre-initialized containers for low-latency sandboxing.
Containers are claimed per-task and destroyed after completion (replenished async).
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from pathlib import Path
from typing import Any, Optional

from agent.compute.isolation_provider import IsolationProvider, SandboxInstance

try:
    import docker
except ImportError:
    docker = None

log = logging.getLogger("agent.warm_pool")


def _local_fallback_allowed() -> bool:
    return os.environ.get("KINTHIC_ALLOW_LOCAL_FALLBACK", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ) or os.environ.get("KINTHIC_DEV_MODE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class WarmDockerSandbox(SandboxInstance):
    def __init__(
        self,
        client: Any,
        container: Any,
        worker_id: str,
        workspace_dir: Path,
        project_root: Path,
        session_key: str,
        socket_path: Path,
        default_timeout: float = 600.0,
    ):
        self.client = client
        self.container = container
        self._worker_id = worker_id
        self._workspace_dir = workspace_dir
        self.project_root = project_root
        self._session_key = session_key
        self._socket_path = socket_path
        self._default_timeout = default_timeout

        from agent.security.path_guardian import FilesystemPathGuardian

        self._guardian = FilesystemPathGuardian(workspace_dir)
        self._project_guardian = FilesystemPathGuardian(project_root)

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    @property
    def worker_id(self) -> str:
        return self._worker_id

    async def execute(self, command: str, lease: Any) -> str:
        try:
            self._guardian.verify_and_canonicalize(self.workspace_dir)
            self._project_guardian.verify_and_canonicalize(self.project_root)
        except PermissionError as e:
            return f"Security Violation: {e}"

        if lease is None:
            return "Security Violation: Missing actuation lease"
        if not lease.validate("run_terminal_command"):
            return "Security Violation: Invalid or expired actuation lease"

        lease.write_egress_policy(self.workspace_dir)

        timeout_seconds = self._default_timeout
        if hasattr(lease, "expires_at") and hasattr(lease, "issued_at"):
            ttl = max(1.0, float(lease.expires_at) - __import__("time").time())
            timeout_seconds = min(timeout_seconds, ttl)

        if not self._socket_path.exists():
            return (
                "Security Violation: Sidecar socket unavailable. "
                "Execution denied (no fail-open fallback)."
            )

        import json

        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self._socket_path)),
                timeout=2.0,
            )
            payload = {
                "command": command,
                "session_key": self._session_key,
                "timeout_seconds": timeout_seconds,
            }
            writer.write(json.dumps(payload).encode("utf-8"))
            await writer.drain()
            writer.write_eof()

            read_timeout = timeout_seconds + 10.0
            response_data = await asyncio.wait_for(reader.read(), timeout=read_timeout)
            response = json.loads(response_data.decode("utf-8"))
            if "error" in response:
                return f"Security Violation: {response['error']}"
            output = response.get("output", "")
            exit_code = response.get("exit_code", -1)
            return f"--- SANDBOX OUTPUT (Warm UDS) ---\n{output}\n--- END OUTPUT ---\nExit Code: {exit_code}"
        except asyncio.TimeoutError:
            return (
                f"Error: Sidecar command timed out after {timeout_seconds:.0f} seconds."
            )
        except Exception as e:
            log.error("UDS execution failed for worker %s: %s", self._worker_id, e)
            return (
                "Security Violation: Sidecar execution failed. "
                "Execution denied (no fail-open fallback)."
            )
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

    async def kill(self) -> None:
        try:
            await asyncio.to_thread(self.container.kill)
        except Exception:
            pass
        try:
            await asyncio.to_thread(self.container.remove, force=True)
        except Exception:
            pass
        try:
            if self._socket_path.exists():
                self._socket_path.unlink()
        except Exception:
            pass
        try:
            socket_dir = self._socket_path.parent
            if socket_dir.exists() and not any(socket_dir.iterdir()):
                socket_dir.rmdir()
        except Exception:
            pass


class LocalFallbackSandbox(SandboxInstance):
    """Dev-only fallback when Docker is unavailable. Not for production."""

    def __init__(self, worker_id: str, workspace_dir: Path, project_root: Path):
        self._worker_id = worker_id
        self._workspace_dir = workspace_dir
        self.project_root = project_root
        self._active_process: Optional[asyncio.subprocess.Process] = None

        from agent.security.path_guardian import FilesystemPathGuardian

        self._guardian = FilesystemPathGuardian(workspace_dir)
        self._project_guardian = FilesystemPathGuardian(project_root)

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    @property
    def worker_id(self) -> str:
        return self._worker_id

    async def execute(self, command: str, lease: Any) -> str:
        if not _local_fallback_allowed():
            return (
                "Security Violation: Docker unavailable and local fallback is disabled. "
                "Set KINTHIC_ALLOW_LOCAL_FALLBACK=1 for dev mode only."
            )

        try:
            self._guardian.verify_and_canonicalize(self.workspace_dir)
            self._project_guardian.verify_and_canonicalize(self.project_root)
        except PermissionError as e:
            return f"Security Violation: {e}"

        if not lease.validate("run_terminal_command"):
            return "Security Violation: Invalid or expired actuation lease."

        # Enforce strict safety validation for local command execution fallback
        import shlex
        argv = shlex.split(command)
        if not argv:
            return "Error: Command is empty."

        from silex_core.tools.system import RunTerminalCommandTool
        try:
            temp_tool = RunTerminalCommandTool()
            temp_tool._check_safety(command, argv, sandboxed=False)
        except PermissionError as e:
            return f"Security Violation: {e}"

        timeout_seconds = 60.0
        if hasattr(lease, "expires_at"):
            ttl = max(1.0, float(lease.expires_at) - __import__("time").time())
            timeout_seconds = min(timeout_seconds, ttl)

        try:
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
            proc = await asyncio.create_subprocess_shell(
                command if os.name != "nt" else command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace_dir),
            )
            self._active_process = proc
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_seconds,
                )
                output = (stdout + stderr).decode("utf-8", errors="replace")
                return (
                    f"--- SANDBOX OUTPUT (Local Fallback) ---\n{output}\n"
                    f"--- END OUTPUT ---\nExit Code: {proc.returncode}"
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return f"Error: Local fallback command timed out after {timeout_seconds:.0f} seconds."
            finally:
                self._active_process = None
        except Exception as e:
            return f"Error: Local fallback execution failed: {e}"

    async def kill(self) -> None:
        proc = self._active_process
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (ProcessLookupError, asyncio.TimeoutError, OSError):
                pass
            finally:
                self._active_process = None


class DockerWarmPoolManager(IsolationProvider):
    def __init__(self, workspace_root: Path, project_root: Path, pool_size: int = 4):
        self.workspace_root = workspace_root
        self.project_root = project_root
        self.pool_size = pool_size
        self._pool: asyncio.Queue[WarmDockerSandbox] = asyncio.Queue()
        self._spawn_meta: dict[str, tuple[str, Path, float]] = {}

        self.client = None
        if docker:
            try:
                self.client = docker.from_env()
                try:
                    existing = self.client.containers.list(
                        all=True, filters={"label": "kinthic.managed=true"}
                    )
                    for c in existing:
                        log.info("Scavenging leaked container: %s", c.name)
                        try:
                            c.kill()
                        except Exception:
                            pass
                        try:
                            c.remove(force=True)
                        except Exception:
                            pass
                except Exception as scavenger_error:
                    log.warning(
                        "Scavenger failed to clean up containers: %s", scavenger_error
                    )
            except Exception as e:
                log.warning("Docker not available for Warm Pool: %s", e)

        self._replenish_task: Optional[asyncio.Task] = None

        if self.client:
            try:
                self.client.images.get("python:3.11-alpine")
            except Exception:
                self.client.images.pull("python:3.11-alpine")

            try:
                self.client.networks.get("kinthic_sandbox")
            except Exception:
                self.client.networks.create("kinthic_sandbox", internal=True)

            try:
                proxy = self.client.containers.get("kinthic_egress_proxy")
                if proxy.status != "running":
                    proxy.start()
            except Exception:
                self.client.containers.run(
                    image="python:3.11-alpine",
                    name="kinthic_egress_proxy",
                    command=[
                        "python",
                        "-u",
                        "/project/agent/security/network_proxy.py",
                    ],
                    volumes={
                        str(self.project_root.resolve()): {
                            "bind": "/project",
                            "mode": "ro",
                        },
                        str(Path.home() / ".kinthic" / "workers"): {
                            "bind": "/kinthic/workers",
                            "mode": "ro",
                        },
                    },
                    environment={
                        # Safe here only because kinthic_sandbox is an internal
                        # (no host route, no internet) network with no published
                        # host port for this container — see network_proxy.py.
                        "KINTHIC_EGRESS_PROXY_IN_SANDBOX_NETWORK": "true",
                    },
                    detach=True,
                )
                self.client.networks.get("kinthic_sandbox").connect(
                    self.client.containers.get("kinthic_egress_proxy")
                )

            self._replenish_task = asyncio.create_task(self._replenish_loop())

    async def _spawn_container(
        self,
        network_disabled: bool = True,
        timeout_seconds: float = 600.0,
    ) -> Optional[WarmDockerSandbox]:
        if not self.client:
            return None

        worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        workspace_dir = self.workspace_root / worker_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        run_dir = Path.home() / ".kinthic" / "run" / worker_id
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            run_dir.chmod(0o700)
        except OSError:
            pass

        session_key = secrets.token_hex(32)
        self._spawn_meta[worker_id] = (session_key, run_dir, timeout_seconds)

        env = {
            "GIT_DIR": "/workspace/.git",
            "GIT_WORK_TREE": "/workspace",
            "WORKSPACE_DIR": "/workspace",
            "PYTHONPATH": "/project",
            "KINTHIC_WORKER_ID": worker_id,
            "KINTHIC_WORKER_SESSION_KEY": session_key,
            "KINTHIC_SIDECAR_DEFAULT_TIMEOUT": str(int(timeout_seconds)),
        }
        if not network_disabled:
            env.update(
                {
                    "HTTP_PROXY": "http://kinthic_egress_proxy:8080",
                    "HTTPS_PROXY": "http://kinthic_egress_proxy:8080",
                    "http_proxy": "http://kinthic_egress_proxy:8080",
                    "https_proxy": "http://kinthic_egress_proxy:8080",
                }
            )

        try:
            container = await asyncio.to_thread(
                self.client.containers.run,
                image="python:3.11-alpine",
                command=["python", "-u", "/project/agent/compute/sidecar_daemon.py"],
                volumes={
                    str(self.project_root.resolve()): {
                        "bind": "/project",
                        "mode": "ro",
                    },
                    str(workspace_dir.resolve()): {"bind": "/workspace", "mode": "rw"},
                    str(run_dir.resolve()): {
                        "bind": "/run/kinthic_sockets",
                        "mode": "rw",
                    },
                },
                environment=env,
                working_dir="/workspace",
                detach=True,
                remove=False,
                mem_limit="256m",
                pids_limit=128,
                labels={
                    "kinthic.managed": "true",
                    "kinthic.worker_id": worker_id,
                },
                network="kinthic_sandbox",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                network_disabled=network_disabled,
            )
            socket_path = run_dir / f"kinthic_{worker_id}.sock"
            return WarmDockerSandbox(
                self.client,
                container,
                worker_id,
                workspace_dir,
                self.project_root,
                session_key,
                socket_path,
                default_timeout=timeout_seconds,
            )
        except Exception as e:
            log.error("Failed to spawn warm container: %s", e)
            self._spawn_meta.pop(worker_id, None)
            return None

    async def _replenish_loop(self) -> None:
        while True:
            try:
                if self._pool.qsize() < self.pool_size:
                    sandbox = await self._spawn_container(network_disabled=True)
                    if sandbox:
                        await self._pool.put(sandbox)
                        log.debug(
                            "Replenished warm pool. Pool size: %d", self._pool.qsize()
                        )
                    else:
                        await asyncio.sleep(5)
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Error in replenish loop: %s", e)
                await asyncio.sleep(5)

    async def provision_sandbox(self, lease: Any = None) -> SandboxInstance:
        if not self.client:
            if not _local_fallback_allowed():
                raise RuntimeError(
                    "Docker unavailable and local fallback is disabled (fail-closed). "
                    "Install Docker or set KINTHIC_ALLOW_LOCAL_FALLBACK=1 for dev only."
                )
            log.warning("Docker not available, using LocalFallbackSandbox (dev mode).")
            worker_id = f"worker_{uuid.uuid4().hex[:8]}"
            workspace_dir = self.workspace_root / worker_id
            workspace_dir.mkdir(parents=True, exist_ok=True)
            return LocalFallbackSandbox(worker_id, workspace_dir, self.project_root)

        network_disabled = not (lease and getattr(lease, "network_allowed", False))
        timeout_seconds = 600.0
        if lease and hasattr(lease, "expires_at") and hasattr(lease, "issued_at"):
            timeout_seconds = max(1.0, float(lease.expires_at) - float(lease.issued_at))

        log.debug("Claiming warm sandbox (network_disabled=%s)...", network_disabled)

        try:
            sandbox = self._pool.get_nowait()
        except asyncio.QueueEmpty:
            sandbox = await self._spawn_container(
                network_disabled=network_disabled,
                timeout_seconds=timeout_seconds,
            )
            if sandbox is None:
                raise RuntimeError("Failed to provision sandbox from warm pool")

        if lease:
            lease.write_egress_policy(sandbox.workspace_dir)
            sandbox._default_timeout = timeout_seconds
        return sandbox

    async def teardown_sandbox(self, sandbox: SandboxInstance) -> None:
        log.debug("Tearing down sandbox %s...", sandbox.worker_id)
        await sandbox.kill()

    async def shutdown(self) -> None:
        if self._replenish_task:
            self._replenish_task.cancel()
            try:
                await self._replenish_task
            except asyncio.CancelledError:
                pass

        while not self._pool.empty():
            sandbox = self._pool.get_nowait()
            await sandbox.kill()

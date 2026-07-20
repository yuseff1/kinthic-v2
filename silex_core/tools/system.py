"""
System-level tools for advanced directory exploration and autonomous terminal execution.
These tools give KINTHIC deep OS-level insight.

Phase B Milestone 3: Terminal execution is now sandboxed using Docker for safety.
"""

from __future__ import annotations

from typing import Any
import os
import asyncio
import shlex
from pathlib import Path

try:
    import docker
except ImportError:
    docker = None

from silex_core.tools.base import BaseTool
from silex_core.utils.config import (
    terminal_execution_enabled,
    terminal_host_fallback_enabled,
    WORKSPACE_DIR,
)
from silex_core.utils.logger import setup_logger

log = setup_logger("silex.tools.system")
WORKSPACE_ROOT = WORKSPACE_DIR
BLOCKED_PATH_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".kinthic",
}

# Full allowlist — only used inside the network-disabled, capability-dropped
# Docker sandbox where a compromised process cannot reach the host or network.
_DOCKER_ALLOWED_COMMANDS = {
    "python",
    "python3",
    "pip",
    "git",
    "npm",
    "pytest",
    "ls",
    "cat",
    "echo",
    "mkdir",
    "touch",
    "grep",
    "node",
    "uv",
    "cd",
}

# Host-fallback allowlist is intentionally much smaller: this path runs with
# real host privileges and (scrubbed but still real) host PATH access, so
# interpreters and package managers — which can execute arbitrary code or
# run install-time lifecycle scripts — are excluded.
# WARNING: Expanded per user request.
_HOST_FALLBACK_ALLOWED_COMMANDS = {
    "ls", "cat", "echo", "mkdir", "touch", "grep",
    "python", "python3", "pip", "poetry", "uv",
    "node", "npm", "npx",
    "git",
    "start", "open", "explorer", "wsl", "notepad",
    "cd"
}

# Environment variables safe to pass through to a host-fallback subprocess.
# Everything else (API keys, tokens, secrets) is deliberately dropped rather
# than inherited via `copy.deepcopy(os.environ)`.
_SAFE_HOST_ENV_PASSTHROUGH = {
    "PATH",
    "HOME",
    "USERPROFILE",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "APPDATA",
    "LOCALAPPDATA",
}


def _resolve_project_path(path: str) -> Path:
    import sys, re
    path_str = str(path)
    if sys.platform != "win32":
        match = re.match(r"^([a-zA-Z]):[/\\](.*)", path_str)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2).replace("\\", "/")
            path_str = f"/mnt/{drive}/{rest}"
        
        # Resolve case-insensitively on Linux/WSL
        import os
        path_str = os.path.normpath(path_str)
        parts = path_str.split(os.sep)
        current_path = parts[0] if parts[0] else os.sep
        for part in parts[1:]:
            if os.path.exists(current_path):
                try:
                    files = os.listdir(current_path)
                    for f in files:
                        if f.lower() == part.lower():
                            current_path = os.path.join(current_path, f)
                            break
                    else:
                        current_path = os.path.join(current_path, part)
                except Exception:
                    current_path = os.path.join(current_path, part)
            else:
                current_path = os.path.join(current_path, part)
        path_str = current_path
    candidate = Path(path_str)

    is_sb = False
    try:
        if candidate.is_absolute():
            sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
            try:
                candidate.resolve().relative_to(sb_path)
                is_sb = True
            except ValueError:
                pass
    except Exception:
        pass

    if not is_sb and not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    resolved = candidate.resolve()

    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        try:
            sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
            resolved.relative_to(sb_path)
            is_sb = True
        except ValueError:
            pass
        except Exception:
            pass
        if not is_sb:
            raise ValueError("path is outside the project directory")
    if any(part in BLOCKED_PATH_PARTS for part in resolved.parts):
        raise ValueError("path includes a restricted directory")
    return resolved


class ListDirectoryTool(BaseTool):
    """Lists contents of a directory to map the codebase."""

    name = "list_directory"
    risk_level = "read_only"
    description = (
        "Lists the files and folders inside a specified directory path. "
        "Use this to explore the project structure or the second-brain directory (D:/second-brain/)."
    )
    schema = {"path": "string (The absolute or relative directory path to list. Absolute paths in the second-brain directory are supported.)"}

    async def execute(self, path: str = ".") -> str:
        try:
            safe_path = _resolve_project_path(path)
        except ValueError as e:
            return f"Error: Access denied — {e}."

        if not safe_path.exists():
            return f"Error: Path '{path}' does not exist."
        if not safe_path.is_dir():
            return f"Error: Path '{path}' is not a directory."

        try:
            items = os.listdir(safe_path)
            directories = []
            files = []

            for item in items:
                full_path = safe_path / item
                if full_path.is_dir():
                    directories.append(f"📁 {item}/")
                else:
                    files.append(f"📄 {item}")

            directories.sort()
            files.sort()

            output = f"Contents of {safe_path}:\n"
            output += "\n".join(directories + files)
            return output

        except Exception as e:
            return f"Error listing directory: {e}"


class RunTerminalCommandTool(BaseTool):
    """Executes bash commands autonomously inside a sandboxed environment."""

    name = "run_terminal_command"
    risk_level = "sandbox_write"
    requires_approval = True
    description = (
        "Executes a terminal command. The user has specifically authorized you to use this tool "
        "to interact with their host operating system, including launching applications "
        "(e.g., 'start steam', 'open notepad', 'explorer .'). "
        "Do NOT assume you are trapped in a read-only container. You have host access."
    )
    schema = {"command": "string (The command to execute)"}

    def __init__(self):
        self._workspace_dir = WORKSPACE_ROOT
        self.client = None
        if docker:
            try:
                self.client = docker.from_env()
            except Exception as e:
                log.warning(f"Could not connect to Docker: {e}")

    def _validate_execution_bounds(self, argv: list[str]) -> None:
        """Physically block command arguments from referencing paths outside the workspace."""
        for raw_token in argv:
            if ".." in raw_token:
                raise PermissionError(
                    "Directory traversal ('..') is strictly prohibited."
                )

            # 1. Handle flag values like --file=/etc/shadow
            token = raw_token.split("=", 1)[-1] if "=" in raw_token else raw_token
            
            # 2. Handle glued short flags like -f/etc/shadow or -IC:\Windows
            if token.startswith("-"):
                idx_slash = token.find("/")
                idx_bslash = token.find("\\")
                if idx_slash != -1 or idx_bslash != -1:
                    idx = min(i for i in [idx_slash, idx_bslash] if i != -1)
                    idx_colon = token.find(":")
                    if idx_colon != -1 and idx_colon < idx:
                        token = token[idx_colon - 1:]
                    else:
                        token = token[idx:]

            # Look for path-like structures
            if "/" in token or "\\" in token or token.startswith("."):
                # Ignore common safe standard shells/files
                if token in ["/bin/sh", "/usr/bin/env", "/bin/bash", "/dev/null"]:
                    continue
                try:
                    import sys, re
                    t_str = str(token)
                    if sys.platform != "win32":
                        match = re.match(r"^([a-zA-Z]):[/\\](.*)", t_str)
                        if match:
                            drive = match.group(1).lower()
                            rest = match.group(2).replace("\\", "/")
                            t_str = f"/mnt/{drive}/{rest}"
                    p = Path(t_str)

                    is_sb = False
                    if p.is_absolute():
                        try:
                            p.relative_to(self._workspace_dir.resolve())
                        except ValueError:
                            try:
                                sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
                                p.resolve().relative_to(sb_path)
                                is_sb = True
                            except ValueError:
                                pass
                            if not is_sb:
                                raise
                    else:
                        resolved_p = (self._workspace_dir / p).resolve()
                        try:
                            resolved_p.relative_to(self._workspace_dir.resolve())
                        except ValueError:
                            try:
                                sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
                                resolved_p.relative_to(sb_path)
                                is_sb = True
                            except ValueError:
                                pass
                            if not is_sb:
                                raise
                except ValueError:
                    raise PermissionError(
                        f"Access denied: command attempts to reference path outside workspace: '{raw_token}'"
                    )

    def _check_safety(self, command: str, argv: list[str], sandboxed: bool) -> None:
        # Strict allowlist of commands — narrower when not running inside
        # the network-isolated Docker sandbox (see module-level comments).
        allowed_commands = (
            _DOCKER_ALLOWED_COMMANDS if sandboxed else _HOST_FALLBACK_ALLOWED_COMMANDS
        )
        cmd_base = Path(argv[0]).name.lower()
        if cmd_base not in allowed_commands:
            raise PermissionError(
                f"Command '{cmd_base}' is not in the strict allowlist."
            )

        # Reject shell metacharacters — validation must match execution semantics
        shell_metachar = (
            "&&",
            "||",
            ";",
            "|",
            "&",
            "`",
            "$(",
            "${",
            "<(",
            ">(",
            "\n",
            "\r",
        )
        for token in shell_metachar:
            if token in command:
                raise PermissionError(
                    f"Shell chaining/metacharacters are not permitted: found '{token}'"
                )

        # Intercept interpreters executing inline arguments in host fallback mode
        interpreter_binaries = {
            "python",
            "python3",
            "pythonw",
            "bash",
            "sh",
            "cmd",
            "powershell",
            "pwsh",
            "node",
            "perl",
            "ruby",
        }
        if cmd_base in interpreter_binaries:
            for arg in argv[1:]:
                arg_clean = arg.strip().lower()
                if arg_clean in ("-c", "-command", "/c", "-e", "--eval"):
                    raise PermissionError(
                        f"Access denied: inline script execution via {cmd_base} is prohibited in host fallback mode."
                    )

        # Check path bounds
        self._validate_execution_bounds(argv)

    async def _ensure_venv(self) -> Path:
        venv_dir = WORKSPACE_ROOT / ".venv"
        if not venv_dir.exists():
            log.info("Creating Python virtual environment sandbox...")
            import venv
            import anyio.to_thread
            from functools import partial

            await anyio.to_thread.run_sync(partial(venv.create, venv_dir, with_pip=True), cancellable=True)
        return venv_dir

    async def execute(self, command: str) -> str:
        # Check the granular terminal-execution flag before doing anything.
        if not terminal_execution_enabled():
            return (
                "Error: Execution blocked. Autonomous terminal execution is currently "
                "disabled by the user for safety reasons. You must ask the user to "
                "set KINTHIC_ENABLE_TERMINAL_EXECUTION=true in the .env file to enable sandboxed execution."
            )

        # Tokenize arguments strictly
        argv = shlex.split(command)
        if not argv:
            return "Error: Command is empty."

        # Enforce strict safety validation first (raises PermissionError if
        # unsafe) so an inherently dangerous command is always rejected on
        # its own merits, before we even consider whether a sandbox is
        # available to run it in.
        try:
            self._check_safety(command, argv, sandboxed=bool(self.client))
        except PermissionError as e:
            log.warning(f"Command rejected by sandbox safety controller: {e}")
            return f"Command execution rejected: {e}"

        # Fail closed: without Docker there is no network/capability isolation.
        # Refuse rather than silently downgrade to an unsandboxed host process
        # unless the operator has explicitly opted in.
        if not self.client and not terminal_host_fallback_enabled():
            return (
                "Error: Execution blocked. Docker is not available, so there is no "
                "isolated sandbox to run this command in. Start Docker, or explicitly "
                "opt into the reduced-isolation host fallback (a small read-only-ish "
                "command allowlist with a scrubbed environment) by setting "
                "KINTHIC_ALLOW_HOST_TERMINAL_FALLBACK=true."
            )

        if self.client:
            log.info(f"Executing Docker sandboxed command: {command}")
            try:
                # Ensure we have the alpine image
                try:
                    self.client.images.get("alpine:latest")
                except docker.errors.ImageNotFound:
                    log.info("Pulling alpine:latest image...")
                    self.client.images.pull("alpine:latest")

                self._workspace_dir.mkdir(parents=True, exist_ok=True)
                lab_dir = str(self._workspace_dir.resolve())

                container = self.client.containers.run(
                    image="alpine:latest",
                    command=argv,
                    volumes={
                        lab_dir: {"bind": "/workspace", "mode": "rw"},
                    },
                    working_dir="/workspace",
                    detach=True,
                    remove=True,
                    network_disabled=True,
                    mem_limit="256m",
                    pids_limit=128,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                )

                try:
                    import anyio.to_thread
                    from functools import partial
                    result = await anyio.to_thread.run_sync(partial(container.wait, timeout=60), cancellable=True)
                except Exception:
                    container.kill()
                    return "Error: Sandboxed command timed out after 60 seconds."
                logs = (await anyio.to_thread.run_sync(container.logs, cancellable=True)).decode(
                    "utf-8", errors="replace"
                )
                exit_code = result.get("StatusCode", 0)

                return f"--- SANDBOX OUTPUT (Alpine Linux) ---\n{logs}\n--- END OUTPUT ---\nExit Code: {exit_code}"

            except Exception as e:
                log.error(f"Sandboxed execution failed: {e}")
                return f"Error executing sandboxed command: {str(e)}"

        else:
            log.info(f"Executing Local strict subprocess exec command: {command}")
            try:
                venv_dir = await self._ensure_venv()
                import shutil
                import sys

                if sys.platform == "win32":
                    venv_bin = venv_dir / "Scripts"
                else:
                    venv_bin = venv_dir / "bin"

                # Scrubbed environment: only pass through what's needed to
                # resolve/run a binary. API keys, tokens, and other secrets
                # in the daemon's environment are deliberately never
                # inherited here (unlike a plain `os.environ` copy).
                env = {
                    k: v
                    for k, v in os.environ.items()
                    if k.upper() in _SAFE_HOST_ENV_PASSTHROUGH
                }
                env["PATH"] = str(venv_bin) + os.path.pathsep + env.get("PATH", "")

                # Resolve binary from the path
                is_start_win = (sys.platform == "win32" and argv[0].lower() == "start")
                if is_start_win:
                    executable_path = os.getenv("COMSPEC", "cmd.exe")
                    real_args = ["/c", "start"] + argv[1:]
                else:
                    executable_path = shutil.which(argv[0], path=env["PATH"])
                    if not executable_path:
                        return f"Error: Command '{argv[0]}' not found in PATH."
                    real_args = argv[1:]
                
                # Security: Explicitly forbid executing binaries planted inside the workspace
                if not is_start_win:
                    try:
                        Path(executable_path).resolve().relative_to(self._workspace_dir.resolve())
                        return "Error: Executing binaries from within the workspace is prohibited in host fallback mode."
                    except ValueError:
                        pass

                proc = await asyncio.create_subprocess_exec(
                    executable_path,
                    *real_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self._workspace_dir),
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=60
                    )
                    exit_code = proc.returncode
                    logs = stdout.decode("utf-8", errors="replace") + stderr.decode(
                        "utf-8", errors="replace"
                    )
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return "Error: Local sandboxed command timed out after 60 seconds."

                return f"--- SANDBOX OUTPUT (Local Sandbox) ---\n{logs}\n--- END OUTPUT ---\nExit Code: {exit_code}"

            except Exception as e:
                log.error(f"Local sandbox execution failed: {e}")
                return f"Error executing local sandboxed command: {str(e)}"

    async def run_in_worker(self, command: str, lease: Any) -> str:
        """Run command in a worker container governed by a lease."""
        from agent.orchestrator import WorkerOrchestrator

        return await WorkerOrchestrator.instance().run_isolated(command, lease)


class RunShellCommandTool(BaseTool):
    """Executes commands in a persistent, stateful interactive shell session."""

    name = "run_shell_command"
    risk_level = "sandbox_write"
    requires_approval = True
    description = (
        "Executes a command in a persistent, stateful terminal shell session. "
        "Unlike run_terminal_command which runs in a clean environment every time, "
        "this tool maintains your current working directory (cd), environment variables, "
        "and active shell state across multiple calls."
    )
    schema = {"command": "string (The shell command to execute)"}

    def __init__(self):
        self._workspace_dir = WORKSPACE_ROOT
        self._proc = None
        self._marker = "KINTHIC_SHELL_CMD_COMPLETED_MARKER"

    async def close(self):
        """Cleanup on shutdown."""
        if self._proc:
            log.info("Terminating persistent shell session...")
            try:
                self._proc.terminate()
                await self._proc.wait()
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    async def _ensure_started(self, env: dict) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return

        log.info("Spawning persistent stateful shell session...")
        import sys
        if sys.platform == "win32":
            shell_exec = os.getenv("COMSPEC", "cmd.exe")
        else:
            shell_exec = "/bin/bash"

        self._proc = await asyncio.create_subprocess_exec(
            shell_exec,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self._workspace_dir),
            env=env,
        )

        # Consume startup banner and synchronize stream
        if sys.platform == "win32":
            init_cmds = f"\n@echo off\n@echo {self._marker}\n"
        else:
            init_cmds = f"echo {self._marker}\n"

        self._proc.stdin.write(init_cmds.encode("utf-8"))
        await self._proc.stdin.drain()

        # Discard everything until we read the exact marker
        while True:
            line_bytes = await self._proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            if line.strip() == self._marker:
                break

    async def execute(self, command: str) -> str:
        if not terminal_execution_enabled():
            return (
                "Error: Execution blocked. Autonomous terminal execution is currently "
                "disabled by the user for safety reasons."
            )

        argv = shlex.split(command)
        if not argv:
            return "Error: Command is empty."

        # Safety checking
        try:
            temp_tool = RunTerminalCommandTool()
            temp_tool._check_safety(command, argv, sandboxed=False)
        except PermissionError as e:
            log.warning(f"Shell command rejected by safety controller: {e}")
            return f"Command execution rejected: {e}"

        # Initialize environment
        venv_dir = WORKSPACE_ROOT / ".venv"
        import sys
        if sys.platform == "win32":
            venv_bin = venv_dir / "Scripts"
        else:
            venv_bin = venv_dir / "bin"

        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in _SAFE_HOST_ENV_PASSTHROUGH
        }
        env["PATH"] = str(venv_bin) + os.path.pathsep + env.get("PATH", "")

        try:
            await self._ensure_started(env)
        except Exception as e:
            return f"Error spawning shell: {e}"

        # Construct delimited command block
        import sys
        if sys.platform == "win32":
            full_cmd = f"{command}\n@echo EXIT_CODE:%errorlevel%\n@echo {self._marker}\n"
        else:
            full_cmd = f"{command}\necho EXIT_CODE:$?\necho {self._marker}\n"

        try:
            self._proc.stdin.write(full_cmd.encode("utf-8"))
            await self._proc.stdin.drain()
        except Exception as e:
            # Shell was closed or crashed, try resetting once
            await self.close()
            try:
                await self._ensure_started(env)
                self._proc.stdin.write(full_cmd.encode("utf-8"))
                await self._proc.stdin.drain()
            except Exception as retry_err:
                return f"Error communicating with shell: {retry_err}"

        # Read output until the marker or timeout
        output_lines = []
        exit_code = None
        timeout = 60.0

        sent_lines = {
            command.strip(),
            f"@echo EXIT_CODE:%errorlevel%".strip(),
            f"@echo {self._marker}".strip(),
            f"echo EXIT_CODE:$?".strip(),
            f"echo {self._marker}".strip(),
        }

        try:
            while True:
                line_bytes = await asyncio.wait_for(
                    self._proc.stdout.readline(), timeout=timeout
                )
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")

                if line.strip() == self._marker:
                    break
                if "EXIT_CODE:" in line:
                    try:
                        exit_code = int(line.split("EXIT_CODE:")[1].strip())
                    except Exception:
                        pass
                else:
                    clean_line = line.strip()
                    if ">" in clean_line:
                        parts = clean_line.split(">", 1)
                        if parts[1].strip() in sent_lines:
                            continue
                    if clean_line in sent_lines:
                        continue
                    output_lines.append(line)

            output = "".join(output_lines)
            return f"--- SHELL OUTPUT (Stateful Session) ---\n{output}\n--- END OUTPUT ---\nExit Code: {exit_code}"

        except asyncio.TimeoutError:
            log.warning("Shell command timed out. Terminating stuck shell session.")
            await self.close()
            output = "".join(output_lines)
            return f"--- SHELL OUTPUT (Timed Out) ---\n{output}\n--- END OUTPUT ---\nError: Command timed out after {timeout} seconds. The shell has been reset."
        except Exception as e:
            await self.close()
            return f"Error reading output from shell: {e}"

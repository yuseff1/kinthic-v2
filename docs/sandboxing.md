---
title: "Sandboxing"
description: "How Kinthic isolates code execution and filesystem access."
---

Kinthic is designed to be **paranoid by default**. Giving an AI agent autonomous access to your terminal is dangerous, so Kinthic wraps execution in a strict two-pronged sandbox.

## 1. Terminal Execution Sandboxing

When Kinthic decides to run a shell command (via the `run_terminal_command` tool), it does **not** execute it directly on your host machine.

### Docker Sandbox (Default if available)
If Docker is installed and running on your host:
- Commands are intercepted by Kinthic's safety controller.
- The controller checks the command against `_DOCKER_ALLOWED_COMMANDS` (a whitelist of safe tools like `git`, `python`, `npm`, `ls`).
- The command is executed entirely inside an isolated **Alpine Linux** container.
- **Network Isolation:** By default, the container's network access is disabled so malicious payloads cannot phone home.

### Host Fallback
If Docker is not available:
- Kinthic falls back to a highly restricted local Python Virtual Environment.
- It uses a much stricter `_HOST_FALLBACK_ALLOWED_COMMANDS` whitelist (stripping out tools that could execute arbitrary binaries outside the virtual environment).
- All sensitive environment variables (API keys, tokens, SSH keys) are stripped from the environment before the subprocess spawns, preventing credential harvesting.

## 2. Filesystem Boundaries

When Kinthic tries to read or write files (via the `code_editor` or `file_reader` tools):
- All paths must be relative to the `KINTHIC_WORKSPACE` (your active project directory).
- Kinthic enforces strict path resolution. If an agent attempts to perform a directory traversal attack (e.g., `../../../../etc/passwd`), the operation is instantly rejected.
- Write operations (`sandbox_write` risk level) explicitly require your human approval before proceeding.

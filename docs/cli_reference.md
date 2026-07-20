---
title: "CLI Reference"
description: "A complete list of Kinthic CLI commands."
---

Kinthic ships with a powerful CLI to manage your local agent, memory daemon, and integrations.

### Interactive Agent

- `kinthic`
Starts the interactive agent chat session directly in your terminal.

- `kinthic init`
Runs the onboarding setup wizard to configure your LLM providers, skills, and channels.

### Web & Observability

- `kinthic web`
Starts the local dashboard and backend API. Automatically opens the Epistemic Graph visualization and metrics tracking.

- `kinthic observe`
An alternative command to quickly visualize the active Silex memory graph.

### Daemon Management

- `kinthic daemon start`
Starts the Kinthic background supervisor. This daemon handles persistent background tasks like Telegram/Discord adapters and proactive goals.

- `kinthic daemon logs`
View the live logs of the running daemon.

- `kinthic daemon stop`
Stops the background supervisor.

### MCP (Model Context Protocol)

- `kinthic mcp serve --stdio`
Exposes the Silex memory engine to external tools (like Claude Desktop or Cursor) via the Model Context Protocol over standard input/output.

- `kinthic mcp print-config`
Generates the paste-ready JSON configuration to add Kinthic to your Claude Desktop config.

### Skills

- `kinthic skills install <name>`
Installs a new workflow skill from KinthicHub.

- `kinthic skills list`
Lists all your active installed skills located in `~/.kinthic/skills`.

### Data & Memory

- `kinthic data migrate --from [openclaw|hermes]`
Imports legacy agent state, memory, and settings from OpenClaw or Hermes formats.

- `kinthic data backup`
Exports your entire `~/.kinthic` brain to an archive file.

- `kinthic data restore <archive>`
Restores your brain from a backup archive.

- `kinthic benchmark recall`
Runs a comprehensive needle-in-a-haystack memory benchmark against the Silex Engine.

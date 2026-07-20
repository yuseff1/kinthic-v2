---
title: "Quickstart"
description: "Get started with Kinthic in under 60 seconds."
---

Kinthic is a local-first AI agent built on the **Silex memory engine**. It persists facts in a local database and builds an epistemic graph so it remembers *what* it learned and *how* things connect across sessions.

## Prerequisites

- macOS, Linux, or WSL2 on Windows
- Python 3.10+
- (Optional) Docker (for execution sandboxing)

## Installation

The easiest way to install Kinthic is via the one-line installer:

```bash
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
```

Alternatively, you can install from source:

```bash
git clone https://github.com/openyfai/kinthic.git
cd kinthic
pip install -e .
```

## Setup Wizard

After installation, run the initial interactive wizard to connect your LLM providers:

```bash
kinthic init
```

The wizard will guide you through:
1. Selecting your primary LLM provider (OpenAI, Anthropic, Gemini, OpenRouter, or local models via Ollama/LM Studio).
2. Authenticating your API key.
3. Enabling workflows and skills.
4. Setting up optional MCP connections and Telegram/Discord channels.

> **Note on Local Models:** If you select Ollama or LM Studio, Kinthic will automatically detect your installed models.

## Your First Session

Start an interactive chat session:

```bash
kinthic
```

Try asking it to remember something across sessions:
1. **You:** "My favorite framework is Next.js."
2. *Close the session (Ctrl+C).*
3. *Start a new session:* `kinthic`
4. **You:** "What's my favorite framework?"
5. **Kinthic:** "Your favorite framework is Next.js."

## Exploring Memory

You can visualize Kinthic's memory graph by running the dashboard:

```bash
kinthic web
```

This opens a local backend and a beautiful 2D Force Graph on your browser where you can see all your agent's epistemic nodes and reasoning links!

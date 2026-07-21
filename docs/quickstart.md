# Kinthic Quickstart Guide

Get up and running with **Kinthic v2** in under 5 minutes.

---

## 1. Installation

Clone Kinthic repository:

```bash
git clone https://github.com/openyfai/kinthic.git
cd kinthic
```

Install Python dependencies:

```bash
pip install -e .
```

---

## 2. One-Command VM Setup

For VM / VPS deployments, run the interactive setup wizard:

```bash
bash scripts/setup_vps.sh
```

Follow the prompts to enter your **Telegram Bot Token**, **LLM API Keys** (OpenAI, Anthropic, Gemini, OpenRouter), and preferred model defaults.

---

## 3. Registered Tool Plugins

Kinthic comes equipped with core tool plugins out-of-the-box:

* **X Social Suite (`x_social`)**: `post_x_status`, `x_interactive_login`, `x_auto_engage` (topic search, reply generator, growth stats).
* **Stealth Multi-Platform Session Manager (`browser_session_manager`)**: `list_sessions`, `interactive_login`, `check_session`, `fetch_page` (LinkedIn, Reddit, GitHub, X).
* **Proactive Daily Briefings**: `/briefing` command & 24h cron push notifications.
* **VM Watchdog & Auto-Healing**: Background supervisor monitoring API gateway & SQLite health.

---

## 4. Basic CLI Usage

Start Kinthic interactively:
```bash
kinthic start
```

Query memory:
```bash
kinthic memory search "project goals"
```

Check health & loaded skills:
```bash
kinthic status
```

# Kinthic VPS & Telegram Deployment Guide

This guide explains how to deploy Kinthic on a standard Ubuntu/Debian Linux VPS (Virtual Private Server) using the **One-Command Setup Wizard**, Systemd supervisor, or Docker Compose.

---

## 1. One-Command Setup Wizard (Recommended)

Kinthic provides an interactive setup script (`scripts/setup_vps.sh`) that installs dependencies, interactively prompts for model API keys and Telegram credentials, and sets up systemd auto-healing services.

SSH into your VPS and run:

```bash
git clone https://github.com/openyfai/kinthic.git
cd kinthic
bash scripts/setup_vps.sh
```

### What the Setup Script Configures:
1. **Interactive Key Prompts**:
   * Telegram Bot Token (`TELEGRAM_BOT_TOKEN`) & User ID (`ALLOWED_TELEGRAM_USERS`).
   * LLM API Keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`).
   * Preferred Default Model (`KINTHIC_DEFAULT_MODEL`) & Provider (`KINTHIC_LLM_PROVIDER`).
   * Optional X/Twitter Credentials.
2. **Secure Environment Storage**: Saves configuration safely to `/etc/kinthic/kinthic.env` and `~/.kinthic/.env` (`chmod 600`).
3. **Playwright & System Dependencies**: Installs Python 3.11 and Playwright Chromium headless dependencies.
4. **Auto-Healing Supervisor**: Configures `/etc/systemd/system/kinthic-supervisor.service`.

### Start & Monitor Service:

```bash
# Start service
sudo systemctl start kinthic-supervisor

# Check live status & logs
sudo systemctl status kinthic-supervisor
journalctl -u kinthic-supervisor -f
```

---

## 2. Docker Compose Deployment

Alternatively, you can launch Kinthic using Docker Compose with built-in healthchecks:

```bash
# Launch container in detached mode
docker compose up -d --build

# View container logs
docker compose logs -f
```

---

## 3. Pairing via Telegram

1. Open Telegram on your phone and search for your bot.
2. Send `/start`.
3. Send `/pair CODE` if pairing is active, or message `/start CODE`.
4. You are now connected to Kinthic from your mobile device!

---

## 4. Watchdog & Auto-Healing Recovery

Kinthic runs a background supervisor watchdog (`scripts/watchdog.py`) that monitors:
* **Gateway API status**: `http://localhost:8000/health`
* **Silex SQLite DB connectivity**: SQL probe

If an un-responsive state is detected (3 consecutive failures), the watchdog automatically restarts the service and sends a high-priority alert notification directly to your Telegram chat!

---

## 5. Maintenance Commands

To backup your Kinthic data:
```bash
kinthic data backup --output /home/ubuntu/kinthic-backup.zip
```

To restore from a backup:
```bash
kinthic stop
kinthic data restore ./kinthic-backup.zip --apply
kinthic start
```

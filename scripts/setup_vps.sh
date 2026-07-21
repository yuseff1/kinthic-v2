#!/usr/bin/env bash
# ==============================================================================
# Kinthic v2 — Interactive VPS Deployment & Setup Wizard
# ==============================================================================

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "======================================================================"
echo "         🚀 KINTHIC v2 — VM DEPLOYMENT & SETUP WIZARD                 "
echo "======================================================================"
echo -e "${NC}"
echo "This script configures your Virtual Machine (VM) for remote Kinthic"
echo "operation via Telegram, sets up systemd auto-healing services, and"
echo "securely saves your model API keys."
echo ""

# Ensure running on Linux
if [ "$(uname)" != "Linux" ]; then
    echo -e "${YELLOW}Notice: This VPS script is designed for Linux VMs (Ubuntu/Debian/RHEL). Running in configuration generator mode.${NC}"
fi

# Step 1: System Packages Check / Installation
echo -e "${GREEN}${BOLD}[1/5] Checking System Dependencies...${NC}"
if command -v apt-get &> /dev/null; then
    echo "Installing system packages (Python 3.11, Git, Playwright requirements)..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip python3-venv git curl \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
        libasound2 libpango-1.0-0 libcairo2 || true
elif command -v dnf &> /dev/null; then
    sudo dnf install -y python3 python3-pip git curl || true
fi

# Step 2: Interactive Configuration Prompts
echo ""
echo -e "${GREEN}${BOLD}[2/5] Interactive API Keys & Configuration Setup${NC}"
echo "----------------------------------------------------------------------"
echo "Press ENTER to skip optional keys."
echo ""

read -p "📱 Enter TELEGRAM_BOT_TOKEN (from @BotFather): " TELEGRAM_BOT_TOKEN
read -p "👤 Enter your Telegram User ID (numeric, optional): " ALLOWED_TELEGRAM_USERS
echo ""

echo "--- LLM Model Providers & API Keys ---"
read -p "🔑 OpenAI API Key (OPENAI_API_KEY, optional): " OPENAI_API_KEY
read -p "🔑 Anthropic API Key (ANTHROPIC_API_KEY, optional): " ANTHROPIC_API_KEY
read -p "🔑 Gemini / Google API Key (GEMINI_API_KEY, optional): " GEMINI_API_KEY
read -p "🔑 OpenRouter API Key (OPENROUTER_API_KEY, optional): " OPENROUTER_API_KEY
echo ""

read -p "⚙️ Preferred LLM Provider (openai/anthropic/gemini/openrouter, default: openai): " KINTHIC_LLM_PROVIDER
KINTHIC_LLM_PROVIDER=${KINTHIC_LLM_PROVIDER:-openai}

read -p "⚙️ Preferred Default Model (eg. gpt-4o, claude-3-5-sonnet-20241022, default: gpt-4o): " KINTHIC_DEFAULT_MODEL
KINTHIC_DEFAULT_MODEL=${KINTHIC_DEFAULT_MODEL:-gpt-4o}
echo ""

echo "--- Optional X (Twitter) API v2 Credentials ---"
read -p "🐦 X API Key (X_API_KEY, optional): " X_API_KEY
read -p "🐦 X API Secret (X_API_SECRET, optional): " X_API_SECRET
read -p "🐦 X Access Token (X_ACCESS_TOKEN, optional): " X_ACCESS_TOKEN
read -p "🐦 X Access Token Secret (X_ACCESS_TOKEN_SECRET, optional): " X_ACCESS_TOKEN_SECRET
echo ""

# Step 3: Write Secure Environment Files
echo -e "${GREEN}${BOLD}[3/5] Saving Secure Environment File...${NC}"

CONFIG_DIR="${HOME}/.kinthic"
mkdir -p "$CONFIG_DIR"
ENV_FILE="$CONFIG_DIR/.env"

cat <<EOF > "$ENV_FILE"
# Kinthic v2 Environment Configuration
KINTHIC_ENV=production
KINTHIC_LLM_PROVIDER=${KINTHIC_LLM_PROVIDER}
KINTHIC_DEFAULT_MODEL=${KINTHIC_DEFAULT_MODEL}

TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
ALLOWED_TELEGRAM_USERS=${ALLOWED_TELEGRAM_USERS}

OPENAI_API_KEY=${OPENAI_API_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
GEMINI_API_KEY=${GEMINI_API_KEY}
OPENROUTER_API_KEY=${OPENROUTER_API_KEY}

X_API_KEY=${X_API_KEY}
X_API_SECRET=${X_API_SECRET}
X_ACCESS_TOKEN=${X_ACCESS_TOKEN}
X_ACCESS_TOKEN_SECRET=${X_ACCESS_TOKEN_SECRET}
EOF

chmod 600 "$ENV_FILE"
echo "Saved environment configuration to $ENV_FILE (chmod 600)."

if [ -w "/etc" ] || sudo -n true 2>/dev/null; then
    sudo mkdir -p /etc/kinthic
    sudo cp "$ENV_FILE" /etc/kinthic/kinthic.env
    sudo chmod 600 /etc/kinthic/kinthic.env
    echo "Synced to /etc/kinthic/kinthic.env for Systemd supervisor."
fi

# Step 4: Python Virtualenv & Playwright Setup
echo ""
echo -e "${GREEN}${BOLD}[4/5] Installing Python Dependencies & Playwright...${NC}"
VENV_DIR="${HOME}/.kinthic/venv"
python3 -m venv "$VENV_DIR" || true
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

pip install --upgrade pip -q
pip install -e . -q || true

if command -v playwright &> /dev/null; then
    echo "Installing Playwright Chromium binaries..."
    playwright install chromium --with-deps || true
fi

# Step 5: Systemd Supervisor Installation
echo ""
echo -e "${GREEN}${BOLD}[5/5] Configuring Systemd Auto-Healing Supervisor...${NC}"

SERVICE_FILE="/etc/systemd/system/kinthic-supervisor.service"
if [ -w "/etc/systemd/system" ] || sudo -n true 2>/dev/null; then
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    REPO_DIR="$(dirname "$SCRIPT_DIR")"

    sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Kinthic v2 Cognitive Agent & Watchdog Supervisor
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_DIR}/bin/python ${REPO_DIR}/scripts/run.py
Restart=always
RestartSec=5s
MemoryMax=4G
EnvironmentFile=/etc/kinthic/kinthic.env
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=kinthic-supervisor

[Install]
WantedBy=multi-user.target
EOF"

    sudo systemctl daemon-reload || true
    sudo systemctl enable kinthic-supervisor || true
    echo "Systemd service 'kinthic-supervisor' enabled."
fi

echo ""
echo -e "${CYAN}${BOLD}======================================================================"
echo "🎉 KINTHIC VM SETUP & DEPLOYMENT COMPLETE!"
echo "======================================================================"
echo -e "${NC}"
echo -e "1. ${BOLD}Start Kinthic Service:${NC}"
echo "   sudo systemctl start kinthic-supervisor"
echo ""
echo -e "2. ${BOLD}Check Status:${NC}"
echo "   sudo systemctl status kinthic-supervisor"
echo ""
echo -e "3. ${BOLD}Telegram Bot Connection:${NC}"
echo "   Send /start to your bot on Telegram from your phone!"
echo "   If pairing is required, run: kinthic telegram pair"
echo ""
echo -e "4. ${BOLD}X Session Cookies (Optional):${NC}"
echo "   Copy your x_cookies.json into ~/.kinthic/browser_sessions/x_cookies.json"
echo ""

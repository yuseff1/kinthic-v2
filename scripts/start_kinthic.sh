#!/usr/bin/env bash
# scripts/start_kinthic.sh — Startup script for Kinthic Telegram Adapter daemon.

set -eo pipefail

# Locate script and project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

echo "Starting Kinthic v2 daemon setup..."

# Activate python virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment (.venv)..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "Activating virtual environment (venv)..."
    source venv/bin/activate
fi

# Run the Kinthic Telegram channel listener
echo "Launching Telegram bot adapter..."
exec python scripts/cli.py channels telegram run

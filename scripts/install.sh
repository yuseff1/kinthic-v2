#!/usr/bin/env bash

# ─────────────────────────────────────────────────────────────────────────────
# OpenYF Kinthic — Zero-Dependency Installer
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ── 1. Guard check for native Windows shells ──────────────────────────────────
# WSL2 is required for Windows users to prevent UAC/SmartScreen execution blocks
if [ -n "${WINDIR:-}" ] || [ -n "${COMSPEC:-}" ] || [ -d "/cygdrive" ] || [ "${OSTYPE:-}" = "msys" ]; then
    echo -e "${RED}❌ Error: This installer must be executed inside a WSL2 Linux terminal.${NC}"
    echo -e "${YELLOW}Windows detected (Command Prompt / PowerShell / Git Bash).${NC}"
    echo -e "Open Ubuntu (or your WSL distro) from the Start menu, then run:"
    echo -e "  ${GREEN}curl -fsSL https://kinthic.openyf.dev/install.sh | bash${NC}"
    echo -e "Native Windows is not supported — WSL2 is required."
    exit 1
fi

# Friendly WSL banner when running inside Linux-on-Windows
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo -e "${GREEN}✓ WSL2 environment detected${NC}"
fi

echo -e "${BLUE}"
echo "  ██╗  ██╗██╗███╗   ██╗████████╗██╗  ██╗██╗ ██████╗ "
echo "  ██║ ██╔╝██║████╗  ██║╚══██╔══╝██║  ██║██║██╔════╝ "
echo "  █████╔╝ ██║██╔██╗ ██║   ██║   ███████║██║██║      "
echo "  ██╔═██╗ ██║██║╚██╗██║   ██║   ██╔══██║██║██║      "
echo "  ██║  ██╗██║██║ ╚████║   ██║   ██║  ██║██║╚██████╗ "
echo "  ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝ "
echo -e "${NC}"
echo -e "         ${YELLOW}[ OpenYF Kinthic Local Operator Installer ]${NC}"
echo -e "──────────────────────────────────────────────────────────"

# ── 2. Environment and Architecture Detection ─────────────────────────────────
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

echo -e "Checking host environment..."
echo -e "  - OS:   ${GREEN}$OS${NC}"
echo -e "  - Arch: ${GREEN}$ARCH${NC}"

# Define UI binary suffix based on detected OS/Arch
UI_SUFFIX=""
if [ "$OS" = "linux" ]; then
    UI_SUFFIX="linux-x64"
elif [ "$OS" = "darwin" ]; then
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
        UI_SUFFIX="darwin-arm64"
    else
        UI_SUFFIX="darwin-x64"
    fi
else
    echo -e "${RED}❌ Error: Operating system '$OS' is not supported.${NC}"
    exit 1
fi

# Define path constants
KINTHIC_DIR="$HOME/.kinthic"
KINTHIC_BIN="$KINTHIC_DIR/bin"
KINTHIC_VENV="$KINTHIC_DIR/runtime/venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_VERSION="3.12"
REPO="openyfai/kinthic"

echo -e "Initializing installer paths..."
mkdir -p "$KINTHIC_BIN"
mkdir -p "$KINTHIC_DIR/workspace/exports"
mkdir -p "$KINTHIC_DIR/workspace/backups"
mkdir -p "$KINTHIC_DIR/runtime/engine_cache"
mkdir -p "$KINTHIC_DIR/storage/vector_db"
mkdir -p "$KINTHIC_DIR/config/plugins/model-providers"
mkdir -p "$KINTHIC_DIR/skills"
mkdir -p "$KINTHIC_DIR/plugins/tools"
mkdir -p "$KINTHIC_DIR/plugins/skills"
mkdir -p "$KINTHIC_DIR/registry"
mkdir -p "$KINTHIC_DIR/logs/traces"

# ── 3. Minimal host requirements & system package setup ───────────────────────
if command -v apt-get &>/dev/null; then
    echo -e "Installing system dependencies..."
    sudo apt-get update -qq || true
    sudo apt-get install -y -qq python3 python3-pip python3-venv python3-full python3-dev git curl \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
        libpango-1.0-0 libcairo2 || true
    sudo apt-get install -y -qq libasound2t64 || sudo apt-get install -y -qq libasound2 || true
fi

MISSING=()
if ! command -v curl &>/dev/null; then
    MISSING+=("curl")
fi
if ! command -v git &>/dev/null; then
    MISSING+=("git")
fi
if [ ${#MISSING[@]} -ne 0 ]; then
    echo -e "${RED}❌ Missing required tools: ${MISSING[*]}${NC}"
    echo -e "Install them with your package manager, then rerun this script."
    exit 1
fi

# ── 4. Retrieve Standalone Assets (parallel) ─────────────────────────────────
echo -e "${BLUE}Downloading uv and TUI binary in parallel...${NC}"
export INSTALL_DIR="$KINTHIC_BIN"
export CARGO_DIST_FORCE_INSTALL_DIR="$KINTHIC_BIN"

UI_URL="https://github.com/$REPO/releases/latest/download/kinthic-ui-$UI_SUFFIX"

(
    curl -LsSf https://astral.sh/uv/install.sh | sh
) &
UV_PID=$!

(
    if curl -L -sSf -o "$KINTHIC_BIN/kinthic-ui" "$UI_URL"; then
        echo "ui_ok" > "$KINTHIC_BIN/.ui_download_status"
    else
        echo "ui_fail" > "$KINTHIC_BIN/.ui_download_status"
    fi
) &
UI_PID=$!

wait "$UV_PID"
wait "$UI_PID"

if [ ! -x "$KINTHIC_BIN/uv" ]; then
    echo -e "${RED}❌ Error: uv installation failed.${NC}"
    exit 1
fi

if [ -f "$KINTHIC_BIN/.ui_download_status" ] && [ "$(cat "$KINTHIC_BIN/.ui_download_status")" = "ui_fail" ]; then
    echo -e "${YELLOW}⚠️ Release UI download failed. Using dev fallback stub.${NC}"
    cat << 'EOF' > "$KINTHIC_BIN/kinthic-ui"
#!/usr/bin/env bash
echo "❌ Precompiled UI missing. From a dev checkout run: cd kinthic-ink-ui && npm run build"
exit 1
EOF
fi
rm -f "$KINTHIC_BIN/.ui_download_status"
chmod +x "$KINTHIC_BIN/kinthic-ui"

# ── 5. Setup Python Sandboxed Virtual Environment ────────────────────────────
echo -e "${BLUE}Installing managed Python ${PYTHON_VERSION} via uv...${NC}"
"$KINTHIC_BIN/uv" python install "$PYTHON_VERSION"

echo -e "${BLUE}Configuring isolated Python virtual environment...${NC}"
"$KINTHIC_BIN/uv" venv "$KINTHIC_VENV" --python "$PYTHON_VERSION"

# uv pip does not auto-detect a venv created at a custom path — target it explicitly.
UV_PIP=( "$KINTHIC_BIN/uv" pip install --python "$KINTHIC_VENV/bin/python" --compile-bytecode )

echo -e "${BLUE}Installing Silex Engine and Core harness (v2 architecture)...${NC}"
if [ -f "$REPO_ROOT/pyproject.toml" ] && [ -f "$REPO_ROOT/scripts/install.sh" ]; then
    cd "$REPO_ROOT"
    "${UV_PIP[@]}" -e .
else
    "${UV_PIP[@]}" "git+https://github.com/$REPO.git"
fi

# Verify kinthic entrypoint
if [ ! -x "$KINTHIC_VENV/bin/kinthic" ]; then
    echo -e "${RED}❌ Error: kinthic CLI not found after install. Check pip output above.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ kinthic CLI installed${NC}"

# ── 6. Bootstrap local config & seed bundled skills ─────────────────────────────
echo -e "${BLUE}Bootstrapping ~/.kinthic configuration...${NC}"

if [ ! -f "$KINTHIC_DIR/.env" ]; then
    if [ -f "$REPO_ROOT/.env.example" ]; then
        cp "$REPO_ROOT/.env.example" "$KINTHIC_DIR/.env"
    else
        cat > "$KINTHIC_DIR/.env" << 'ENVEOF'
# Kinthic runtime configuration
# Add your provider API keys here, then run: kinthic init

GEMINI_API_KEY=
# TELEGRAM_BOT_TOKEN=
# ALLOWED_TELEGRAM_USERS=
# DISCORD_BOT_TOKEN=
# ALLOWED_DISCORD_USERS=
ENVEOF
    fi
    echo -e "  Created ${GREEN}$KINTHIC_DIR/.env${NC} — run ${GREEN}kinthic init${NC} next"
fi

# Bundled catalog fallback (offline KinthicHub)
if [ -f "$REPO_ROOT/registry/catalog.yaml" ]; then
    cp "$REPO_ROOT/registry/catalog.yaml" "$KINTHIC_DIR/registry/catalog.yaml"
    echo -e "  Copied bundled ${GREEN}registry/catalog.yaml${NC}"
fi

# Seed bundled skills from checkout
SKILLS_SRC="$REPO_ROOT/skills"
if [ -d "$SKILLS_SRC" ]; then
    for skill_file in "$SKILLS_SRC"/*.md; do
        [ -f "$skill_file" ] || continue
        base="$(basename "$skill_file")"
        if [ "$base" = "README.md" ]; then
            continue
        fi
        if [ ! -f "$KINTHIC_DIR/skills/$base" ]; then
            cp "$skill_file" "$KINTHIC_DIR/skills/$base"
        fi
        stem="${base%.md}"
        sidecar="$SKILLS_SRC/${stem}.yaml"
        if [ -f "$sidecar" ] && [ ! -f "$KINTHIC_DIR/skills/${stem}.yaml" ]; then
            cp "$sidecar" "$KINTHIC_DIR/skills/${stem}.yaml"
        fi
    done
    echo -e "  Seeded bundled skills into ${GREEN}$KINTHIC_DIR/skills/${NC}"
fi

# Initialize KinthicHub catalog (remote seed with bundled fallback)
"$KINTHIC_VENV/bin/python" - << PYEOF || true
from silex_core.utils.config import ensure_kinthic_home
from silex_core.plugins.registry import get_registry

ensure_kinthic_home()
reg = get_registry()
if not reg.catalog_path.exists():
    reg.seed_builtin_catalog()
else:
    reg.load_catalog()
print("  KinthicHub catalog ready.")
PYEOF

# Non-fatal smoke test
echo -e "${BLUE}Running install smoke check (kinthic doctor)...${NC}"
if "$KINTHIC_VENV/bin/kinthic" doctor; then
    :
else
    echo -e "${YELLOW}⚠️ doctor reported issues — run ${GREEN}kinthic init${NC}${YELLOW} to fix${NC}"
fi
echo -e "${GREEN}→ Run ${YELLOW}kinthic init${NC}${GREEN} next to configure your provider.${NC}"

# ── 7. Create Binary Command Wrapper & Link PATH ──────────────────────────────
echo -e "${BLUE}Registering CLI path endpoints...${NC}"
cat << 'EOF' > "$KINTHIC_BIN/kinthic"
#!/usr/bin/env bash
set -e
exec "$HOME/.kinthic/runtime/venv/bin/kinthic" "$@"
EOF
chmod +x "$KINTHIC_BIN/kinthic"

add_to_path() {
    local profile_file="$1"
    if [ -f "$profile_file" ]; then
        if ! grep -q '\.kinthic/bin' "$profile_file"; then
            echo -e "\n# OpenYF Kinthic path registration\nexport PATH=\"\$HOME/.kinthic/bin:\$PATH\"" >> "$profile_file"
            echo -e "Registered path inside ${GREEN}$profile_file${NC}"
        fi
    fi
}

add_to_path "$HOME/.zshrc"
add_to_path "$HOME/.bashrc"
add_to_path "$HOME/.profile"

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo -e "\n──────────────────────────────────────────────────────────"
echo -e "${GREEN}🎉 OpenYF Kinthic Installed Successfully!${NC}"
echo -e ""
echo -e "Install method: ${YELLOW}curl -fsSL https://kinthic.openyf.dev/install.sh | bash${NC}"
echo -e ""
echo -e "Next steps:"
echo -e "  ${GREEN}kinthic init${NC}                    — first-run wizard (provider + models)"
echo -e "  ${GREEN}kinthic daemon install${NC}          — 24/7 service (survives reboot)"
echo -e "  ${GREEN}kinthic channels telegram run${NC}   — messaging bot (after init)"
echo -e "  ${GREEN}kinthic skills list${NC}             — installed skills"
echo -e "──────────────────────────────────────────────────────────\n"

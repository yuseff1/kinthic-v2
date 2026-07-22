#!/usr/bin/env bash
# Redirection script pointing to canonical installer
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
exec bash "$SCRIPT_DIR/install.sh" "$@"

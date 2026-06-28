#!/bin/bash
# Linux Mint XFCE POS Launcher (thin wrapper — delegates to root start.sh)
# Usage: ./mint/start.sh [--dev]
#
# Note: This file mirrors ubuntu/start.sh. Both ultimately call the same
# root start.sh so behavior is identical; the launcher (.desktop) is what
# dispatches to mint/desktop.py vs ubuntu/desktop.py.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"
exec ./start.sh "$@"

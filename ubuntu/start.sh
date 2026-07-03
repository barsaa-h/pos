#!/bin/bash
# Ubuntu POS Launcher (thin wrapper — delegates to root start.sh)
# Usage: ./ubuntu/start.sh [--dev]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"
exec ./start.sh "$@"

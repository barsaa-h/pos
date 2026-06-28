#!/bin/bash
# POS Launcher — double-click this or run: ./start.sh
# Usage: ./start.sh [--dev]

set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Find Python 3
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    if [ -f "venv/bin/python3" ]; then
        PYTHON="venv/bin/python3"
    else
        echo "❌ Python 3 олдсонгүй. sudo apt install python3"
        exit 1
    fi
fi

exec "$PYTHON" desktop.py "$@"

#!/bin/bash
# POS Development Mode Launcher
# Usage: ./dev.sh

set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
elif [ -f "venv/bin/python3" ]; then
    PYTHON="venv/bin/python3"
else
    echo "❌ Python 3 олдсонгүй. sudo apt install python3"
    exit 1
fi

exec "$PYTHON" dev.py "$@"

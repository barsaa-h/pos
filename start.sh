#!/bin/bash
# POS Launcher — double-click this or run: ./start.sh
# Usage: ./start.sh [PORT]

set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PORT="${1:-5000}"

# Find Python 3
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

# Use venv if available
if [ -f "$ROOT_DIR/venv/bin/activate" ]; then
    source "$ROOT_DIR/venv/bin/activate"
fi

mkdir -p "$ROOT_DIR/logs" "$ROOT_DIR/backups" "$ROOT_DIR/static/uploads"

echo "=== POS Web Server ==="
echo "Open http://localhost:$PORT in your browser"
echo "Press Ctrl+C to stop"
echo ""

export POS_PORT="$PORT"
exec "$PYTHON" app.py

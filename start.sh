#!/bin/bash
# start.sh — Quick launcher for the POS system
# Auto-detects platform and launches the correct desktop

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$(uname -s)" = "Linux" ]; then
    exec "$SCRIPT_DIR/ubuntu/start.sh" "$@"
else
    echo "Error: This script is for Ubuntu. On Windows use: start.bat"
    exit 1
fi

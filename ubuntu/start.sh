#!/bin/bash
# Ubuntu POS Launcher
# Double-click .desktop icon or run: ./ubuntu/start.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "============================================"
echo "  Миний дэлгүүр — Ubuntu"
echo "============================================"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 олдсонгүй. sudo apt install python3"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "📦 Virtual environment үүсгэж байна..."
    python3 -m venv venv
fi

source venv/bin/activate

if ! python3 -c "import flask, webview" 2>/dev/null; then
    echo "📦 Хамаарлууд суулгаж байна..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
fi

mkdir -p logs backups static/uploads

echo "🚀 Миний дэлгүүр ажиллаж эхэллээ..."
python3 ubuntu/desktop.py "$@"

#!/bin/bash
# POS System — One-Click Installer for Linux Mint XFCE
# Usage:  ./install.sh
# Copies itself to ~/.local/share/pos-app first if not already there.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Check if running from a removable / transient location ──
# If running from /run/media, /media, or /tmp, copy to ~/.local/share/pos-app
TARGET_DIR="$HOME/.local/share/pos-app"
if [[ "$SCRIPT_DIR" == /run/media/* ]] || [[ "$SCRIPT_DIR" == /media/* ]] || [[ "$SCRIPT_DIR" == /tmp/* ]]; then
    echo "📁 USB / түр сангаас илэрсэн. $TARGET_DIR руу хуулж байна..."
    mkdir -p "$TARGET_DIR"
    rsync -a --delete "$SCRIPT_DIR"/ "$TARGET_DIR"/
    echo "✅ Хуулагдлаа: $TARGET_DIR"
    cd "$TARGET_DIR"
    exec "$TARGET_DIR/install.sh"
    exit 0
fi

ROOT_DIR="$SCRIPT_DIR"
cd "$ROOT_DIR"

echo "============================================"
echo "  Моност POS — Linux Mint XFCE суулгагч"
echo "============================================"
echo ""

# ── System dependencies ──
echo "🔍 Системийн хамаарлууд шалгаж байна..."

if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 олдсонгүй. Суулгах:"
    echo "   sudo apt install python3 python3-venv python3-pip python3-tk"
    exit 1
fi
echo "  ✅ Python $(python3 --version)"

MISSING_DEPS=""
if ! python3 -c "import tkinter" &>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS python3-tk"
fi
if ! dpkg -l libwebkit2gtk-4.1-0 &>/dev/null && ! dpkg -l libwebkit2gtk-4.0-37 &>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS libwebkit2gtk-4.1-dev"
fi

if [ -n "$MISSING_DEPS" ]; then
    echo "  ⚠️  Дараах системийн хамаарлууд суулгагдаагүй байна:"
    echo "     sudo apt install$MISSING_DEPS"
    echo "  Суулгасны дараа ./install.sh дахин ажиллуулна уу."
    exit 1
fi
echo "  ✅ Бүх системийн хамаарлууд бэлэн"

# ── Virtual environment ──
echo ""
echo "📦 Виртуал орчин үүсгэж байна..."
VENV_DIR="$ROOT_DIR/venv"
if [ ! -f "$VENV_DIR/bin/python3" ]; then
    python3 -m venv "$VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python3"

echo "📦 Хамаарлууд суулгаж байна..."
"$VENV_PYTHON" -m pip install --upgrade pip -q
"$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt" -q

# Mint launcher uses waitress — add it
"$VENV_PYTHON" -m pip install waitress -q 2>/dev/null || true

echo "  ✅ Python хамаарлууд бэлэн"

# ── Database ──
echo ""
echo "🗄️  Өгөгдлийн сан бэлдэж байна..."
"$VENV_PYTHON" -c "
import sys, os
sys.path.insert(0, '$ROOT_DIR')
import database as db
db.init_db()
print('  ✅ Өгөгдлийн сан бэлэн')
"

# ── Directories ──
mkdir -p "$ROOT_DIR/logs" "$ROOT_DIR/backups" "$ROOT_DIR/static/uploads"
chmod +x "$ROOT_DIR/start.sh" "$ROOT_DIR/mint/desktop.py" 2>/dev/null || true

# ── Admin password setup ──
echo ""
echo "🔒 Админ нууц үг тохируулах"
echo "----------------------------------------"
$VENV_PYTHON -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from database import hash_password, get_db, get_setting

existing = get_setting('admin_password_hash')
if existing:
    print('  Админ нууц үг аль хэдийн тохируулагдсан.')
    print('  Өөрчлөх: python3 -c \"from database import hash_password, get_db; conn=get_db(); conn.execute(\\\"UPDATE settings SET value=? WHERE key=\\\\\"admin_password_hash\\\\\\\"\\\", (hash_password(\\\"шинэ_нууц_үг\\\"),)); conn.commit(); conn.close()\"')
    sys.exit(0)

import getpass
password = getpass.getpass('  Шинэ админ нууц үг оруулна уу (Enter = 1234): ') or '1234'
pw_hash = hash_password(password)
conn = None
try:
    conn = __import__('sqlite3').connect(os.path.join('$ROOT_DIR', 'pos.db'))
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('admin_password_hash', pw_hash))
    conn.commit()
    print('  ✅ Админ нууц үг тохируулагдлаа')
finally:
    if conn:
        conn.close()
"

# ── XFCE compositor optimization (Mint-specific) ──
echo ""
echo "🎨 XFCE дэлгэцийн тохиргоо оновчтой болгож байна..."
# Set XFCE compositor off for i5 2nd gen hardware
if command -v xfconf-query &>/dev/null; then
    xfconf-query -c xfwm4 -p /general/use_compositing -s false 2>/dev/null && \
    echo "  ✅ XFCE compositor унтраагдлаа (хуучин комп-д илүү хурдтай)" || true
else
    echo "  ℹ️  xfconf-query олдсонгүй (XFCE биш байж магадгүй)"
fi
# XFCE screensaver off via xset
xset s off -dpms 2>/dev/null || true

# ── Desktop shortcut ──
echo ""
echo "📋 Desktop товч үүсгэж байна..."
DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
mkdir -p "$DESKTOP_DIR" 2>/dev/null || DESKTOP_DIR="$HOME"
DESKTOP_FILE="$DESKTOP_DIR/Моност_POS.desktop"

cat > "$DESKTOP_FILE" << DESKTOPEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Моност POS
Comment=Кассын систем — Борлуулалт, бараа, тайлан
Exec=$ROOT_DIR/start.sh
Path=$ROOT_DIR
Icon=$ROOT_DIR/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
StartupWMClass=Моност POS
Keywords=pos;касс;sale;store;point of sale;борлуулалт;дэлгүүр
DESKTOPEOF
chmod +x "$DESKTOP_FILE"
echo "  ✅ Desktop товч: $DESKTOP_FILE"

# ── Autostart ──
read -p $'\n🚀 Компьютер асахад автоматаар эхлэх үү? (y/N): ' -r AUTOSTART
if [[ "$AUTOSTART" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/autostart"
    cp "$DESKTOP_FILE" "$HOME/.config/autostart/"
    echo "  ✅ Автоматаар эхлэхээр тохируулагдлаа"
fi

# ── Done ──
echo ""
echo "============================================"
echo "  ✅ Суулгалт дууслаа!"
echo "============================================"
echo ""
echo "  Эхлүүлэх:"
echo "    • Desktop дээрх 'Моност POS' товч дээр дарна уу"
echo "    • Эсвэл:  ./start.sh"
echo ""
echo "  Админ хуудас:  http://localhost:8765/settings"
echo "  Нууц үг:        Таны тохируулсан нууц үг (эсвэл 1234)"
echo ""
echo "  Бараа нэмэх:    Бараа -> + Шинэ бараа"
echo "  Тайлан:         Тайлан"
echo ""
read -p $'  Одоо эхлүүлэх үү? (y/N): ' -r LAUNCH
if [[ "$LAUNCH" =~ ^[Yy]$ ]]; then
    "$ROOT_DIR/start.sh" &
fi

#!/bin/bash
# Ubuntu POS Installer — one-click setup
# Run: ./ubuntu/install.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "============================================"
echo "  Миний дэлгүүр — Ubuntu суулгах"
echo "============================================"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 олдсонгүй. sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
echo "✅ Python $(python3 --version)"

if ! dpkg -l libwebkit2gtk-4.1-0 &>/dev/null && ! dpkg -l libwebkit2gtk-4.0-37 &>/dev/null; then
    echo "⚠️  WebKit2GTK суулгаагүй байна. pywebview-д шаардлагатай."
    echo "   Суулгах: sudo apt install libwebkit2gtk-4.1-dev"
fi

# Bootstrap via root launcher
python3 -c "
import sys, os, subprocess
PROJECT_DIR = '$ROOT_DIR'
sys.path.insert(0, PROJECT_DIR)

vp = os.path.join(PROJECT_DIR, 'venv', 'bin', 'python3')
if not os.path.exists(vp):
    print('📦 Virtual environment үүсгэж байна...')
    subprocess.run([sys.executable, '-m', 'venv', os.path.join(PROJECT_DIR, 'venv')], check=True)

subprocess.run([vp, '-m', 'pip', 'install', '--upgrade', 'pip', '-q'], check=True)
subprocess.run([vp, '-m', 'pip', 'install', '-r', os.path.join(PROJECT_DIR, 'requirements.txt'), '-q'], check=True)

import database as db
db.init_db()
print('✅ Database бэлэн')
"

mkdir -p logs backups static/uploads

# Desktop shortcut
DESKTOP_FILE="$HOME/Desktop/Миний_дэлгүүр.desktop"
cat > "$DESKTOP_FILE" << 'DESKTOPEOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Миний дэлгүүр
Name[en]=My Store POS
Comment=POS систем — Борлуулалт, нөөц, тайлан
Comment[en]=Point of Sale — Sales, inventory, reports
Exec=ROOT_DIR_PLACEHOLDER/start.sh
Path=ROOT_DIR_PLACEHOLDER
Icon=ROOT_DIR_PLACEHOLDER/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
StartupWMClass=Миний дэлгүүр
Keywords=pos;sale;store;point of sale;борлуулалт;дэлгүүр;касс
MimeType=
DESKTOPEOF
sed -i "s|ROOT_DIR_PLACEHOLDER|$ROOT_DIR|g" "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

# Autostart
mkdir -p "$HOME/.config/autostart"
cp "$DESKTOP_FILE" "$HOME/.config/autostart/"

chmod +x start.sh ubuntu/start.sh ubuntu/desktop.py

echo ""
echo "✅ Суулгалт дууслаа!"
echo "   Desktop дээрх 'Миний дэлгүүр' дүрс дээр давхар дарж эхлүүлнэ үү."
echo "   Эсвэл: ./start.sh"

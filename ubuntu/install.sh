#!/bin/bash
# Ubuntu POS Installer
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "============================================"
echo "  Миний дэлгүүр — Ubuntu суулгах"
echo "============================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 олдсонгүй. sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
echo "✅ Python $(python3 --version)"

# Check GTK/WebKit dependency
if ! dpkg -l libwebkit2gtk-4.1-0 &>/dev/null && ! dpkg -l libwebkit2gtk-4.0-37 &>/dev/null; then
    echo "⚠️  WebKit2GTK суулгаагүй байна. pywebview-д шаардлагатай."
    echo "   Суулгах: sudo apt install libwebkit2gtk-4.1-dev"
fi

# Venv
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Initialize DB
python3 -c "import database as db; db.init_db(); print('✅ Database бэлэн')"

# Create directories
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
Exec=ROOT_DIR_PLACEHOLDER/ubuntu/start.sh
Path=ROOT_DIR_PLACEHOLDER
Icon=ROOT_DIR_PLACEHOLDER/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
Keywords=pos;sale;store;point of sale;борлуулалт;дэлгүүр;касс
MimeType=
DESKTOPEOF
sed -i "s|ROOT_DIR_PLACEHOLDER|$ROOT_DIR|g" "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

# Autostart
mkdir -p "$HOME/.config/autostart"
cp "$DESKTOP_FILE" "$HOME/.config/autostart/"

chmod +x ubuntu/start.sh ubuntu/desktop.py

echo ""
echo "✅ Суулгалт дууслаа!"
echo "   Desktop дээрх 'Миний дэлгүүр' дүрс дээр давхар дарж эхлүүлнэ үү."
echo "   Эсвэл: ./ubuntu/start.sh"

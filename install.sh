#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Миний дэлгүүр — POS систем суулгах"
echo "============================================"
echo ""

# ─── Check Python ───
echo "🔍 Python 3 шалгаж байна..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 олдсонгүй. Суулгана уу:"
    echo "   sudo apt update && sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo "❌ Python >= 3.10 шаардлагатай (одоогийн: $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION"

# ─── Create virtual environment ───
echo ""
echo "📦 Virtual environment үүсгэж байна..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
echo "✅ venv бэлэн"

# ─── Install dependencies ───
echo ""
echo "📦 Python хамаарлууд суулгаж байна..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Хамаарлууд суулгагдлаа"

# ─── Initialize database ───
echo ""
echo "🗄️ Database бэлдэж байна..."
python3 -c "
import database as db
db.init_db()
print('✅ Database бэлэн')
"

# ─── Create directories ───
mkdir -p backups

# ─── Create desktop shortcut ───
echo ""
echo "🖥️ Desktop shortcut үүсгэж байна..."
DESKTOP_FILE="$HOME/Desktop/Миний_дэлгүүр.desktop"
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Миний дэлгүүр
Comment=POS систем — Борлуулалт, нөөц, тайлан
Exec=/bin/bash -c 'cd $SCRIPT_DIR && ./ubuntu/start.sh'
Path=$SCRIPT_DIR
Icon=$SCRIPT_DIR/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
Name[mn]=Миний дэлгүүр
Comment[mn]=Борлуулалтын систем
EOF
chmod +x "$DESKTOP_FILE"
chmod +x "$SCRIPT_DIR/ubuntu/start.sh"
chmod +x "$SCRIPT_DIR/ubuntu/desktop.py"
echo "✅ Desktop shortcut: $DESKTOP_FILE"

# ─── Auto-start on login ───
echo ""
echo "🔄 Авто асаалт тохируулж байна..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_FILE" "$AUTOSTART_DIR/Миний_дэлгүүр.desktop"
echo "✅ Login үед автоматаар асна"

# ─── Create desktop shortcut on all users' desktops ───
for user_dir in /home/*; do
    if [ -d "$user_dir/Desktop" ] && [ "$user_dir" != "$HOME" ]; then
        cp "$DESKTOP_FILE" "$user_dir/Desktop/Миний_дэлгүүр.desktop" 2>/dev/null || true
    fi
done

# ─── Install systemd service (optional) ───
if command -v systemctl &> /dev/null; then
    echo ""
    echo "🔧 Системийн үйлчилгээ (systemd) суулгах уу? [y/N]"
    read -r INSTALL_SERVICE
    if [ "$INSTALL_SERVICE" = "y" ] || [ "$INSTALL_SERVICE" = "Y" ]; then
        sudo cp pos.service /etc/systemd/system/minii-delguur.service
        sudo sed -i "s|/opt/minii-delguur|$SCRIPT_DIR|g" /etc/systemd/system/minii-delguur.service
        sudo systemctl daemon-reload
        sudo systemctl enable minii-delguur.service
        echo "✅ systemd үйлчилгээ суулаа: sudo systemctl start minii-delguur"
    fi
fi

# ─── Done ───
echo ""
echo "============================================"
echo "  ✅ Суулгалт амжилттай дууслаа!"
echo "============================================"
echo ""
echo "🚀 Эхлүүлэх:"
echo "   ./ubuntu/start.sh       # Desktop горим (кассчин + үйлчлүүлэгч цонх)"
echo "   source venv/bin/activate && python3 app.py   # Вэб горим (http://localhost:8765)"
echo ""
echo "⚙️ Эхний тохируулга:"
echo "   1. Админ нууц үг тохируулах (баруун дээд булан)"
echo "   2. eBarimt тохиргоо (Мерчант TIN, API URL, TTD код)"
echo "   3. Хэвлэгчийн порт (ихэвчлэн /dev/usb/lp0)"
echo ""
echo "📖 Дэлгэрэнгүй: POS_SYSTEM_DOCS.txt"
echo "============================================"
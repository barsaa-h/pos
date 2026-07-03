#!/bin/bash
# POS App — Chroot Installer (runs during autoinstall, no sudo needed)
set -e

ROOT_DIR="/opt/minii-delguur"
cd "$ROOT_DIR"

# ─── Check Python ───
PYTHON=$(command -v python3)
PYTHON_VERSION=$($PYTHON --version 2>&1)
echo "➜ $PYTHON_VERSION"

# ─── Virtual environment ───
echo "➜ Virtual environment үүсгэж байна..."
$PYTHON -m venv venv
source venv/bin/activate
echo " ✅ venv бэлэн"

# ─── Install Python deps ───
echo "➜ Python хамаарлууд суулгаж байна..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo " ✅ Python хамаарлууд суулгагдлаа"

# ─── Init database ───
echo "➜ Database бэлтгэж байна..."
$PYTHON -c "
import database as db
db.init_db()
print(' ✅ Database бэлэн')
"

mkdir -p logs backups
chmod +x start.sh ubuntu/start.sh ubuntu/desktop.py 2>/dev/null || true

# ─── Generate icon ───
if [ -f generate_icon.py ]; then
    $PYTHON generate_icon.py 2>/dev/null || true
fi

# ─── Desktop shortcut ───
echo "➜ Desktop shortcut үүсгэж байна..."
USER_HOME=$(eval echo ~delguur)
mkdir -p "$USER_HOME/Desktop" "$USER_HOME/.config/autostart"

DESKTOP_FILE="$USER_HOME/Desktop/Миний_дэлгүүр.desktop"
cat > "$DESKTOP_FILE" << DESKTOPEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Миний дэлгүүр
Comment=POS систем — Борлуулалт, нөөц, тайлан
Exec=$ROOT_DIR/start.sh
Path=$ROOT_DIR
Icon=$ROOT_DIR/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
Name[mn]=Миний дэлгүүр
DESKTOPEOF
chmod +x "$DESKTOP_FILE"
cp "$DESKTOP_FILE" "$USER_HOME/.config/autostart/"
chown -R delguur:delguur "$USER_HOME/Desktop" "$USER_HOME/.config"
echo " ✅ Desktop shortcut + auto-start"

# ─── Systemd service ───
echo "➜ Systemd үйлчилгээ суулгаж байна..."
cp pos.service /etc/systemd/system/minii-delguur.service
sed -i "s|/opt/minii-delguur|$ROOT_DIR|g" /etc/systemd/system/minii-delguur.service
systemctl daemon-reload
systemctl enable minii-delguur.service
echo " ✅ Systemd үйлчилгээ суулаа"

# ─── Auto-login for delguur user ───
echo "➜ Автомат нэвтрэлт тохируулж байна..."
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-autologin.conf << LIGHTDMEOF
[Seat:*]
autologin-user=delguur
autologin-user-timeout=0
LIGHTDMEOF
echo " ✅ Login үед автоматаар нэвтрэнэ"

# ─── Done ───
echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║  ✅ POS Систем амжилттай суулаа!          ║"
echo "╚═══════════════════════════════════════════╝"
echo ""
echo "  Программ хаяг: $ROOT_DIR"
echo "  Хэрэглэгч: delguur"
echo "  Нууц үг: delguur123"
echo ""

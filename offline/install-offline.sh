#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  Миний дэлгүүр — Офлайн суулгагч (internet шаардлагагүй)       ║
# ║  Linux Mint XFCE 22.04 дээр ажиллуулах                         ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# Ажиллуулах: cd /media/*/POS-APP && sudo bash offline/install-offline.sh
# ──────────────────────────────────────────────────────────────────

set -e

# ─── Colors ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${CYAN}➜${NC} $1"; }
ok()    { echo -e " ${GREEN}✅${NC} $1"; }
warn()  { echo -e " ${YELLOW}⚠️${NC} $1"; }
fail()  { echo -e "${RED}❌${NC} $1"; exit 1; }

USB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OFFLINE_DIR="$USB_DIR/offline"
INSTALL_DIR="/opt/minii-delguur"
REAL_USER="${SUDO_USER:-$USER}"

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║   Миний дэлгүүр — POS Систем (Офлайн суулгац)        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# ─── Root шалгах ───
if [ "$EUID" -ne 0 ]; then
    exec sudo bash "$0" "$@"
    exit 0
fi

# ──────────────────────────────────────────────────────────────
step="1"; info "$step. Системийн хамаарлууд суулгаж байна..."
# ──────────────────────────────────────────────────────────────
dpkg -i $OFFLINE_DIR/debs/*.deb 2>/dev/null || true
apt-get install -f -y -qq 2>&1 | tail -2
ok "Системийн хамаарлууд суулгагдлаа"

# ──────────────────────────────────────────────────────────────
step="2"; info "$step. Файлуудыг $INSTALL_DIR руу хуулж байна..."
# ──────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
rsync -a --info=progress2 "$USB_DIR/" "$INSTALL_DIR/" \
    --exclude=offline --exclude=venv --exclude=.git \
    --exclude='__pycache__' --exclude='*.pyc' \
    --exclude=.pytest_cache --exclude=tests \
    --exclude='*~' --exclude=pos.db --exclude=backups --exclude=logs 2>&1 | tail -1
ok "Файлууд хуулагдлаа"

# ──────────────────────────────────────────────────────────────
step="3"; info "$step. Виртуал орчин ба Python хамаарлууд..."
# ──────────────────────────────────────────────────────────────
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --no-index --find-links=$OFFLINE_DIR/wheels -r requirements.txt -q
ok "Python хамаарлууд суулгагдлаа"

# ──────────────────────────────────────────────────────────────
step="4"; info "$step. Өгөгдлийн сан үүсгэж байна..."
# ──────────────────────────────────────────────────────────────
python3 -c "import database as db; db.init_db()"
ok "Өгөгдлийн сан бэлэн"

# ──────────────────────────────────────────────────────────────
step="5"; info "$step. Зөвшөөрөл тохируулж байна..."
# ──────────────────────────────────────────────────────────────
chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR" 2>/dev/null || true
chmod +x "$INSTALL_DIR/start.sh" "$INSTALL_DIR/mint/desktop.py" \
        "$INSTALL_DIR/mint/start.sh" 2>/dev/null || true
ok "Зөвшөөрөл тохируулагдлаа"

# ──────────────────────────────────────────────────────────────
step="6"; info "$step. Desktop shortcut + Autostart..."
# ──────────────────────────────────────────────────────────────
DESKTOP_FILE="$INSTALL_DIR/mint/Миний_дэлгүүр.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    mkdir -p "$HOME/Desktop" "$HOME/.config/autostart"
    cp "$DESKTOP_FILE" "$HOME/Desktop/"
    cp "$DESKTOP_FILE" "$HOME/.config/autostart/"
    ok "Desktop shortcut + autostart тохируулагдлаа"
else
    warn "Desktop shortcut олдсонгүй (алгасав)"
fi

# ──────────────────────────────────────────────────────────────
step="7"; info "$step. Принтер зөвшөөрөл..."
# ──────────────────────────────────────────────────────────────
usermod -aG lp,dialout,plugdev "$REAL_USER" 2>/dev/null || true
ok "Принтер port зөвшөөрөгдлөө"

echo ""
echo " ${GREEN}══════════════════════════════════════════════════${NC}"
echo " ${GREEN}✅ Суулгалт амжилттай дууслаа!${NC}"
echo " ${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo "   Системийг эхлүүлэх:"
echo "     • Desktop дээрх 'Миний дэлгүүр' дүрс дээр дарна уу"
echo "     • Эсвэл терминалд: $INSTALL_DIR/start.sh"
echo "     • Web browser: http://localhost:8765"
echo ""

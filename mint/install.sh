#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  Миний дэлгүүр — Linux Mint XFCE нэг товшилтоор суулгагч        ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# Hardware target: i5 2nd gen, 4GB RAM, Intel HD Graphics
# Optimized for Linux Mint XFCE 22 on slow store computers.
#
# Ажиллуулах: ./mint/install.sh
# эсвэл:      bash mint/install.sh
# ──────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# ─── Colors ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}➜${NC} $1"; }
ok()    { echo -e " ${GREEN}✅${NC} $1"; }
warn()  { echo -e " ${YELLOW}⚠️${NC} $1"; }
fail()  { echo -e "${RED}❌${NC} $1"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     Миний дэлгүүр — Linux Mint XFCE суулгах                     ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ─── Check Python3 ───
if ! command -v python3 &> /dev/null; then
    fail "Python 3 олдсонгүй. Суулгах: sudo apt install python3 python3-venv python3-pip"
fi
ok "Python $(python3 --version 2>&1)"

# ─── Check WebKit2GTK ───
if ! dpkg -l libwebkit2gtk-4.1-0 &>/dev/null && ! dpkg -l libwebkit2gtk-4.0-37 &>/dev/null; then
    warn "WebKit2GTK суулгаагүй байна. pywebview-д шаардлагатай."
    warn "Суулгах: sudo apt install libwebkit2gtk-4.1-dev"
fi

# ─── Create venv + install deps ───
info "Virtual environment үүсгэж байна..."
python3 -c "
import sys, os, subprocess
PROJECT_DIR = '$ROOT_DIR'
sys.path.insert(0, PROJECT_DIR)

vp = os.path.join(PROJECT_DIR, 'venv', 'bin', 'python3')
if not os.path.exists(vp):
    subprocess.run([sys.executable, '-m', 'venv', os.path.join(PROJECT_DIR, 'venv')], check=True)

subprocess.run([vp, '-m', 'pip', 'install', '--upgrade', 'pip', '-q'], check=True)
subprocess.run([vp, '-m', 'pip', 'install', '-r', os.path.join(PROJECT_DIR, 'requirements.txt'), '-q'], check=True)
subprocess.run([vp, '-m', 'pip', 'install', 'waitress', '-q'], check=False)

import database as db
db.init_db()
print('OK')
" 2>&1 | tail -3

ok "Python орчин бэлэн"

# ─── Create directories ───
mkdir -p logs backups static/uploads
chmod 777 logs backups

# ─── Desktop shortcut ───
info "Desktop shortcut үүсгэж байна..."
mkdir -p "$HOME/Desktop" "$HOME/.config/autostart"

DESKTOP_FILE="$HOME/Desktop/Миний_дэлгүүр.desktop"
cat > "$DESKTOP_FILE" << DESKTOPEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Миний дэлгүүр
Name[en]=My Store POS
Comment=POS систем — Борлуулалт, нөөц, тайлан
Comment[en]=Point of Sale — Sales, inventory, reports
Exec=${ROOT_DIR}/start.sh
Path=${ROOT_DIR}
Icon=${ROOT_DIR}/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
StartupWMClass=Миний дэлгүүр
Keywords=pos;sale;store;point of sale;борлуулалт;дэлгүүр;касс
MimeType=
DESKTOP_FILE_EOF
chmod +x "$DESKTOP_FILE"
cp "$DESKTOP_FILE" "$HOME/.config/autostart/"

chmod +x start.sh mint/start.sh mint/desktop.py

ok "Desktop shortcut + auto-start тохируулагдлаа"

# ─── XFCE optimizations (quick version) ───
info "XFCE оновчлол хийж байна..."

# Compositor off (critical for i5 2nd gen)
XFWM4_XML="$HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml"
mkdir -p "$(dirname "$XFWM4_XML")"
if [ ! -f "$XFWM4_XML" ]; then
    cat > "$XFWM4_XML" << 'XFWM4EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="use_compositing" type="bool" value="false"/>
    <property name="workspace_count" type="int" value="1"/>
    <property name="borderless_maximize" type="bool" value="true"/>
  </property>
</channel>
XFWM4EOF
fi

# Disable screensaver
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true

ok "XFCE оновчлол дууслаа"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  ✅ Суулгалт дууслаа!                                          ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  🚀 Эхлүүлэх:"
echo "     • Desktop дээрх 'Миний дэлгүүр' дүрс дээр дарна уу"
echo "     • Эсвэл терминалд: ${ROOT_DIR}/start.sh"
echo ""

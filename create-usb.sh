#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  Миний дэлгүүр — POS офлайн USB үүсгэгч                         ║
# ║  Хөгжүүлэгч компьютер дээр ажиллуулна (internet заавартай)       ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# Энэ скрипт USB флаш диск бэлтгэж, POS системийн файлууд,
# системийн .deb багцууд, Python wheels-ийг хуулж, офлайн
# суулгагч скрипт үүсгэнэ.
#
# Ашиглах: sudo bash create-usb.sh /dev/sdX
# (X-ийг USB төхөөрөмжийн үсгээр солино)
#
# Нарийвчилсан заавар: AGENTS.md → "Store PC Deployment" хэсгийг үзнэ үү.

set -e

# ─── Colors ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}➜${NC} $1"; }
ok()    { echo -e " ${GREEN}✅${NC} $1"; }
warn()  { echo -e " ${YELLOW}⚠️${NC} $1"; }

DEVICE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$DEVICE" ]; then
    echo -e "${RED}❌ USB төхөөрөмж зааж өгнө үү: sudo bash create-usb.sh /dev/sdX${NC}"
    echo ""
    echo "Боломжтой төхөөрөмжүүд:"
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL | grep -E 'disk|part'
    exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  POS Офлайн USB үүсгэгч                               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

PART="${DEVICE}1"

# ─── Аюулгүй байдлын шалгалт ───
if [[ "$DEVICE" == *"nvme"*"n"* ]]; then PART="${DEVICE}p1"; fi
if [[ "$DEVICE" == "/dev/sda" ]]; then
    warn "$DEVICE дээр системийн диск шиг байна. Үргэлжлүүлэх үү?"
    read -p "   Enter дарж үргэлжлүүлэх, Ctrl+C цуцлах: " _
fi

# ─── 1. Формат ───
info "1. $DEVICE холбоосыг салгаж байна..."
for m in $(mount | grep "^$DEVICE" | awk '{print $1}'); do umount "$m" 2>/dev/null || true; done
ok "Салгагдлаа"

info "2. $PART форматлаж байна (ext4, label: POS-APP)..."
mkfs.ext4 -F -L POS-APP "$PART" 2>&1 | tail -1
ok "Форматлагдлаа"

# ─── 2. Холбох ───
MNT=$(mktemp -d)
mount "$PART" "$MNT"
ok "$PART → $MNT холбогдлоа"

# ─── 3. POS файлууд хуулах ───
info "3. POS файлууд хуулж байна..."
rsync -a "$SCRIPT_DIR/" "$MNT/" \
    --exclude=venv --exclude=.git --exclude='__pycache__' \
    --exclude='*.pyc' --exclude=.pytest_cache --exclude=tests \
    --exclude=requirements-dev.txt --exclude='*~' \
    --exclude=pos.db --exclude=backups --exclude=logs \
    --exclude=.coverage --exclude=.coveragerc --info=progress2 2>&1 | tail -1
ok "POS файлууд хуулагдлаа"

# ─── 4. .deb багцууд татах ───
info "4. Системийн .deb багцууд татаж байна (internet)..."
mkdir -p "$MNT/offline/debs"

apt-get install --download-only -y \
    python3 python3-pip python3-venv python3-dev build-essential \
    libwebkit2gtk-4.1-0 pkg-config libcairo2-dev gir1.2-gtk-3.0 \
    git curl wget rsync sqlite3 2>&1 | tail -2

cp /var/cache/apt/archives/*.deb "$MNT/offline/debs/" 2>/dev/null
ok "${#MNT_DEBS[@]} .deb багц хуулагдлаа"

# ─── 5. Python wheels татах ───
info "5. Python wheels татаж байна (internet)..."
mkdir -p "$MNT/offline/wheels"

# venv байгаа эсэхийг шалгах
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    info "venv үүсгэж байна..."
    python3 -m venv "$SCRIPT_DIR/venv"
    "$SCRIPT_DIR/venv/bin/pip" install --upgrade pip -q
fi

"$SCRIPT_DIR/venv/bin/pip" download -r "$SCRIPT_DIR/requirements.txt" \
    -d "$MNT/offline/wheels" 2>&1 | tail -1
ok "Python wheels татагдлаа"

# ─── 6. Зөвшөөрөл ───
CHOWN_USER="${SUDO_USER:-$USER}"
chown -R "$CHOWN_USER:$CHOWN_USER" "$MNT/offline"
chmod +x "$MNT/offline/install-offline.sh" \
        "$MNT/start.sh" "$MNT/mint/desktop.py" 2>/dev/null || true

# ─── 7. Салгах ───
sync
umount "$MNT"
rmdir "$MNT"
echo ""
ok "✅ USB бэлэн! Хэмжээ: $(du -sh /dev/$PART 2>/dev/null | awk '{print $1}')"
echo "   Одоо store PC дээр залгаад ажиллуулна:"
echo "   cd /media/*/POS-APP && sudo bash offline/install-offline.sh"
echo ""

#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  Моност POS USB Builder — Fully Automated Linux Mint + POS USB  ║
# ║                                                                  ║
# ║  Creates a bootable USB that:                                    ║
# ║    1. Auto-installs Linux Mint XFCE 22                           ║
# ║    2. Auto-installs Моност POS app on first boot                 ║
# ║                                                                  ║
# ║  Usage:                                                          ║
# ║    sudo bash build-pos-usb.sh /path/to/linuxmint.iso /dev/sdX    ║
# ║                                                                  ║
# ║  Example:                                                        ║
# ║    sudo bash build-pos-usb.sh ~/Downloads/linuxmint-22-xfce.iso /dev/sdb
# ╚══════════════════════════════════════════════════════════════════╝

set -e

# ─── Colors ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}➜${NC} $1"; }
ok()    { echo -e " ${GREEN}✅${NC} $1"; }
warn()  { echo -e " ${YELLOW}⚠️${NC} $1"; }
fail()  { echo -e "${RED}❌${NC} $1"; exit 1; }

cat << "WELCOME"

╔══════════════════════════════════════════════════════════════════╗
║      Моност POS — Автомат USB суулгагч бэлтгэх                  ║
║      Linux Mint XFCE + POS систем нэг USB-наас                  ║
╚══════════════════════════════════════════════════════════════════╝
WELCOME

# ─── Root check ───
if [ "$EUID" -ne 0 ]; then
    warn "Root эрх шаардлагатай. sudo ашиглаж байна..."
    exec sudo bash "$0" "$@"
fi

# ─── Args ───
ISO="$1"
USB_DEV="$2"

if [ -z "$ISO" ] || [ -z "$USB_DEV" ]; then
    echo ""
    echo "Хэрэглээ: sudo bash build-pos-usb.sh <linuxmint.iso> <usb_device>"
    echo ""
    echo "Жишээ:   sudo bash build-pos-usb.sh linuxmint-22-xfce.iso /dev/sdb"
    echo ""
    echo "Боломжтой төхөөрөмжүүд:"
    lsblk -d -o NAME,SIZE,MODEL | grep -v loop
    exit 1
fi

if [ ! -f "$ISO" ]; then
    fail "ISO файл олдсонгүй: $ISO"
fi

if [ ! -b "$USB_DEV" ]; then
    fail "USB төхөөрөмж олдсонгүй: $USB_DEV"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POS_DIR="$SCRIPT_DIR"
WORK_DIR="/tmp/pos-usb-build-$$"
ISO_EXTRACT="$WORK_DIR/iso"
PRESEED_DIR="$ISO_EXTRACT/preseed"
POS_ISO_DIR="$ISO_EXTRACT/pos-app"
FIRSTBOOT_SCRIPT="$ISO_EXTRACT/firstboot-pos.sh"

# ─── Config ───
POS_USER="delguur"
POS_PASSWORD="delguur123"
STORE_NAME="Моност"
TIMEZONE="Asia/Ulaanbaatar"
KEYBOARD="us"
HOSTNAME="monost-pos"

# ─── Step 1: Check prerequisites ───
info "Шаардлагатай програмуудыг шалгаж байна..."
MISSING=""
for cmd in xorriso 7z dd lsblk; do
    command -v $cmd &>/dev/null || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
    fail "Дараах програмууд олдсонгүй:$MISSING. Суулгах: sudo apt install xorriso p7zip-full"
fi
ok "Бүх програм бэлэн"

# ─── Step 2: Extract ISO ───
info "ISO файлыг задалж байна..."
rm -rf "$WORK_DIR"
mkdir -p "$ISO_EXTRACT"

xorriso -osirrox on -indev "$ISO" -extract / "$ISO_EXTRACT" 2>&1 | tail -3
chmod -R u+w "$ISO_EXTRACT"
ok "ISO задалгаа дууслаа"

# ─── Step 3: Create preseed file ───
info "Автомат суулгах тохиргоо (preseed) үүсгэж байна..."
mkdir -p "$PRESEED_DIR"

# Escape paths for preseed late_command
PRESEED_LATE="\
    cp -a /cdrom/pos-app /target/opt/monost-pos; \
    mkdir -p /target/etc/systemd/system; \
    cp /cdrom/monost-pos-firstboot/monost-pos-firstboot.service /target/etc/systemd/system/; \
    cp /cdrom/firstboot-pos.sh /target/usr/local/bin/monost-pos-firstboot.sh; \
    in-target chmod +x /usr/local/bin/monost-pos-firstboot.sh; \
    in-target systemctl enable monost-pos-firstboot.service; \
    mkdir -p /target/etc/lightdm/lightdm.conf.d; \
    printf '[Seat:*]\\\\nautologin-user=${POS_USER}\\\\nautologin-user-timeout=0\\\\nautologin-session=xfce\\\\n' > /target/etc/lightdm/lightdm.conf.d/50-pos-autologin.conf; \
"

cat > "$PRESEED_DIR/auto.seed" << PRESEEDEOF
# ─── Моност POS — Linux Mint Autoinstall Preseed ───

# Language
d-i debian-installer/locale string en_US.UTF-8

# Keyboard
d-i console-setup/ask_detect boolean false
d-i keyboard-configuration/xkb-keymap select ${KEYBOARD}

# Network
d-i netcfg/choose_interface select auto
d-i netcfg/dhcp_timeout string 60
d-i netcfg/get_hostname string ${HOSTNAME}
d-i netcfg/get_domain string unassigned-domain

# Time
d-i time/zone string ${TIMEZONE}
d-i clock-setup/utc boolean true
d-i clock-setup/ntp boolean true

# Partitioning — use entire disk
d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/confirm_nooverwrite boolean true
d-i partman/confirm boolean true
d-i partman/default_filesystem string ext4

# User account
d-i passwd/root-login boolean false
d-i passwd/make-user boolean true
d-i passwd/user-fullname string ${POS_USER}
d-i passwd/username string ${POS_USER}
d-i passwd/user-password password ${POS_PASSWORD}
d-i passwd/user-password-again password ${POS_PASSWORD}
d-i user-setup/allow-password-weak boolean true
d-i user-setup/encrypt-home boolean false

# Skip slow updates during install
d-i pkgsel/update-policy select none
d-i pkgsel/upgrade select none

# GRUB to main drive
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true

# ─── Post-install: copy POS app, install first-boot service ───
d-i preseed/late_command string ${PRESEED_LATE}

# Finish — reboot automatically
d-i finish-install/reboot_in_progress note
PRESEEDEOF
ok "Preseed файл үүслээ"

# ─── Step 4: Copy POS app to ISO ───
info "Моност POS програмыг ISO руу хуулж байна..."
mkdir -p "$POS_ISO_DIR"

rsync -a \
    --exclude=venv \
    --exclude=.git \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude=.pytest_cache \
    --exclude='*~' \
    --exclude=backups \
    --exclude=logs \
    --exclude=pos.db \
    --exclude=tests \
    --exclude=requirements-dev.txt \
    --exclude=.coverage \
    --exclude=.coveragerc \
    --exclude=.ruff_cache \
    --info=progress2 \
    "$POS_DIR/" "$POS_ISO_DIR/" 2>&1 | tail -1
ok "POS файлууд хуулагдлаа"

# ─── Step 5: First-boot script ───
info "Эхний ачаалал дээр ажиллах скрипт үүсгэж байна..."
cat > "$FIRSTBOOT_SCRIPT" << 'SCRIPTEOF'
#!/bin/bash
# ─── Моност POS — First Boot Setup ───
# Runs automatically right after Linux Mint is installed
# Copies POS app from /cdrom to /opt and runs complete setup

set -e
exec 2>/var/log/monost-pos-firstboot.log
set -x

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ─── Wait for system to settle ───
sleep 5

# ─── Only run once ───
if [ -f /opt/monost-pos/.installed ]; then
    log "POS already installed, skipping first-boot."
    exit 0
fi

log "Starting Моност POS auto-install..."

# ─── Locate POS app (from live CD or already copied) ───
if [ -d /cdrom/pos-app ]; then
    SOURCE="/cdrom/pos-app"
elif [ -d /run/live/medium/pos-app ]; then
    SOURCE="/run/live/medium/pos-app"
else
    log "POS source not found! Trying mount..."
    mkdir -p /tmp/pos-source
    mount /dev/disk/by-label/"MINT_POS" /tmp/pos-source 2>/dev/null || \
    mount /dev/sr0 /tmp/pos-source 2>/dev/null || true
    if [ -d /tmp/pos-source/pos-app ]; then
        SOURCE="/tmp/pos-source/pos-app"
    else
        log "ERROR: POS app source not found. Manual install needed."
        exit 1
    fi
fi

log "Source: $SOURCE"
TARGET="/opt/monost-pos"

# ─── Copy POS app ───
log "Copying POS app to $TARGET..."
mkdir -p "$TARGET"
rsync -a --info=progress2 "$SOURCE/" "$TARGET/" 2>&1 | tail -1

# ─── Install deps & setup ───
export DEBIAN_FRONTEND=noninteractive

log "Updating package lists..."
apt-get update -qq 2>/dev/null | tail -1

log "Installing system requirements..."
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    build-essential libwebkit2gtk-4.1-0 \
    pkg-config libcairo2-dev gir1.2-gtk-3.0 \
    git curl wget rsync sqlite3 \
    2>&1 | tail -3

# ─── Run mint-setup.sh if available ───
if [ -f "$TARGET/mint-setup.sh" ]; then
    log "Running mint-setup.sh..."
    cd "$TARGET"
    export POS_USER="delguur"
    export POS_PASSWORD="delguur123"
    export SETUP_AUTOLOGIN="yes"
    export DISABLE_POWER_SAVE="yes"
    export OPTIMIZE_XFCE="yes"
    bash "$TARGET/mint-setup.sh" --no-rsync 2>&1
fi

# ─── Create desktop shortcut for delguur user ───
USER_HOME=$(eval echo ~delguur)
if [ -d "$USER_HOME/Desktop" ]; then
    DESKTOP_FILE="$USER_HOME/Desktop/Моност.desktop"
    cat > "$DESKTOP_FILE" << DESKTOPEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Моност
Comment=POS систем — Борлуулалт, нөөц, тайлан
Exec=${TARGET}/start.sh
Path=${TARGET}
Icon=${TARGET}/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
StartupWMClass=Моност
Name[mn]=Моност
Keywords=pos;sale;store;борлуулалт;дэлгүүр;касс
DESKTOPEOF
    chmod +x "$DESKTOP_FILE"
    cp "$DESKTOP_FILE" "$USER_HOME/.config/autostart/" 2>/dev/null || true
    chown delguur:delguur "$DESKTOP_FILE" 2>/dev/null || true
fi

# ─── Mark installed ───
touch /opt/monost-pos/.installed

# ─── Disable this oneshot service so it never runs again ───
systemctl disable monost-pos-firstboot.service 2>/dev/null || true

log "Моност POS installation complete! Rebooting in 10 seconds..."
sleep 10
reboot
SCRIPTEOF
chmod +x "$FIRSTBOOT_SCRIPT"

ok "First-boot скрипт үүслээ"

# ─── Step 6: Create systemd oneshot service ───
info "Systemd үйлчилгээ үүсгэж байна..."

mkdir -p "$ISO_EXTRACT/monost-pos-firstboot"
cat > "$ISO_EXTRACT/monost-pos-firstboot/monost-pos-firstboot.service" << SERVICEEOF
[Unit]
Description=Моност POS First Boot Setup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/monost-pos-firstboot.sh
RemainAfterExit=true
StandardOutput=journal
StandardError=journal
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
SERVICEEOF

# ─── Step 7: Create installer script for the target system ───
cat > "$ISO_EXTRACT/monost-pos-firstboot/install.sh" << INSTALLEOF
#!/bin/bash
# Called by /cdrom/casper/initrd or post-install script
# Copies first-boot service into the installed system

set -e

SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
TARGET_DEST="/opt/monost-pos"

# Mount the installed system's root
if [ -n "\$1" ]; then
    ROOT_MOUNT="\$1"
else
    ROOT_MOUNT="/target"
fi

# Copy POS app
mkdir -p "\${ROOT_MOUNT}\${TARGET_DEST}"
rsync -a /cdrom/pos-app/ "\${ROOT_MOUNT}\${TARGET_DEST}/" \
    --exclude=venv --exclude=.git --exclude=__pycache__ --exclude='*.pyc'

# Install first-boot service
cp /cdrom/monost-pos-firstboot/monost-pos-firstboot.service "\${ROOT_MOUNT}/etc/systemd/system/"
cp /cdrom/firstboot-pos.sh "\${ROOT_MOUNT}/usr/local/bin/monost-pos-firstboot.sh"
chmod +x "\${ROOT_MOUNT}/usr/local/bin/monost-pos-firstboot.sh"

# Create the .installed marker directory
mkdir -p "\${ROOT_MOUNT}\${TARGET_DEST}"

# Enable the service
chroot "\${ROOT_MOUNT}" systemctl enable monost-pos-firstboot.service 2>/dev/null || true

echo "POS first-boot service installed."
INSTALLEOF
chmod +x "$ISO_EXTRACT/monost-pos-firstboot/install.sh"

ok "Systemd үйлчилгээ бэлэн"

# ─── Step 8: Modify bootloader for autoinstall ───
info "Ачаалагчийн тохиргоог өөрчилж байна..."

# ── GRUB config (UEFI boot) ──
GRUB_CFG="$ISO_EXTRACT/boot/grub/grub.cfg"
if [ -f "$GRUB_CFG" ]; then
    # Add preseed parameter to the default boot entry
    sed -i 's|linux	/casper/vmlinuz|linux	/casper/vmlinuz preseed/file=/cdrom/preseed/auto.seed auto=true priority=critical|' "$GRUB_CFG"
    sed -i 's|linux	/vmlinuz|linux	/vmlinuz preseed/file=/cdrom/preseed/auto.seed auto=true priority=critical|' "$GRUB_CFG" 2>/dev/null || true
    # Set default timeout to 0
    sed -i 's/^set timeout=[0-9]*/set timeout=0/' "$GRUB_CFG" 2>/dev/null || true
    # Hide menu
    sed -i 's/^set menu_auto_hide=0/set menu_auto_hide=1/' "$GRUB_CFG" 2>/dev/null || true
    ok "GRUB config modified"
else
    warn "GRUB config not found at $GRUB_CFG"
fi

# ── ISOLINUX config (BIOS boot) ──
ISOLINUX_CFG="$ISO_EXTRACT/isolinux/txt.cfg"
if [ -f "$ISOLINUX_CFG" ]; then
    # Modify all boot entries to use preseed
    sed -i '/^append/ s/$/ preseed\/file=\/cdrom\/preseed\/auto.seed auto=true priority=critical/' "$ISOLINUX_CFG"
    ok "ISOLINUX config modified"
else
    # Try alternate location
    for f in "$ISO_EXTRACT/isolinux/isolinux.cfg" "$ISO_EXTRACT/syslinux/live.cfg" "$ISO_EXTRACT/syslinux/syslinux.cfg"; do
        if [ -f "$f" ]; then
            sed -i '/^append/ s/$/ preseed\/file=\/cdrom\/preseed\/auto.seed auto=true priority=critical/' "$f" 2>/dev/null || true
            ok "Modified: $f"
        fi
    done
fi

# Change ISO volume label to be identifiable
LABEL="MINT_POS"

# ─── Step 10: Rebuild ISO ───
info "ISO файлыг дахин бүтээж байна..."
OUTPUT_ISO="$WORK_DIR/monost-pos-linuxmint.iso"

# Find the MBR template
MBR_FILE="/usr/lib/ISOLINUX/isohdpfx.bin"
if [ ! -f "$MBR_FILE" ]; then
    MBR_FILE="/usr/lib/syslinux/isohdpfx.bin"
fi
if [ ! -f "$MBR_FILE" ]; then
    MBR_FILE=""
fi

XORRISO_OPTS=(
    -as mkisofs
    -r -V "$LABEL" -J -joliet-long
    -cache-inodes
    -iso-level 3
    -no-emul-boot -boot-load-size 4 -boot-info-table
    -b isolinux/isolinux.bin -c isolinux/boot.cat
)

if [ -n "$MBR_FILE" ] && [ -f "$MBR_FILE" ]; then
    XORRISO_OPTS+=(-isohybrid-mbr "$MBR_FILE")
fi

XORRISO_OPTS+=(
    -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot
    -isohybrid-gpt-basdat
    -o "$OUTPUT_ISO"
    "$ISO_EXTRACT"
)

xorriso "${XORRISO_OPTS[@]}" 2>&1 | grep -E 'Written|Total|ISO image'
ok "ISO дахин бүтээгдлээ: $OUTPUT_ISO"
ok "ISO хэмжээ: $(du -h "$OUTPUT_ISO" | cut -f1)"

# ─── Step 11: Flash to USB ───
info "USB төхөөрөмж рүү бичиж байна: $USB_DEV"
warn "БҮХ ӨГӨГДӨЛ $USB_DEV УСТГАГДАНА!"
echo ""
echo -n "Үргэлжлүүлэх үү? (yes/no): "
read CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    warn "Цуцлагдлаа. ISO файл: $OUTPUT_ISO"
    info "Та дараах командаар гараар бичиж болно: sudo dd if=$OUTPUT_ISO of=$USB_DEV bs=4M status=progress oflag=sync"
    exit 1
fi

# Unmount any mounted partitions
for part in $(lsblk -n -o NAME "$USB_DEV" | tail -n +2); do
    umount "/dev/$part" 2>/dev/null || true
done

# Flash the ISO
info "ISO-г USB руу бичиж байна..."
dd if="$OUTPUT_ISO" of="$USB_DEV" bs=4M status=progress oflag=sync 2>&1
sync

ok "USB төхөөрөмж бэлэн боллоо!"
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  🎉 Моност POS USB амжилттай бэлэн боллоо!                     ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  📌 USB төхөөрөмж: $USB_DEV"
echo "  📋 ISO файл: $OUTPUT_ISO"
echo ""
echo "  ⚡ Ашиглах заавар:"
echo "     1. USB-г дэлгүүрийн компьютерт залгаад"
echo "     2. Компьютерээ асаагаад BIOS-оос USB-р ачаална (F12 / F2 / ESC)"
echo "     3. Linux Mint автоматаар сууна"
echo "     4. Суулгаж дууссаны дараа компьютер дахин асах ба"
echo "     5. Моност POS програм автоматаар суугаад бэлэн болно"
echo ""
echo "  👤 Нэвтрэх нэр: $POS_USER"
echo "  🔑 Нууц үг: $POS_PASSWORD"
echo ""
echo "  ⏱️  Нийт хугацаа: ~15-20 минут (татаж авах + суулгах)"
echo ""

# ─── Cleanup ───
rm -rf "$WORK_DIR" 2>/dev/null || true

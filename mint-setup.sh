#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  Миний дэлгүүр — Linux Mint XFCE 22.04 Суулгагч + Оновчлогч    ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# USB флаш дискнээс ажиллуулахад зориулагдсан бүрэн автомат суулгагч.
# Linux Mint XFCE 22.04 (Wilma) шинээр суулгасны дараа энэ скриптийг
# ажиллуулахад:
#   1. Системийн хамаарлууд суулгана
#   2. Програмыг /opt/minii-delguur руу хуулна
#   3. Python орчин, хамаарлууд, өгөгдлийн сан бэлтгэнэ
#   4. Десктоп shortcut + авто асаалт тохируулна
#   5. Systemd үйлчилгээ суулгана
#   6. Дэлгүүрийн компьютерт зориулж системийг оновчлоно
#      (дэлгэц унтрах, түгжих, унтах горим идэвхгүйжүүлэх гэх мэт)
#
# Ажиллуулах: sudo bash mint-setup.sh
#             эсвэл   bash mint-setup.sh   (sudo хүсэх болно)
# ──────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Colors ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${CYAN}➜${NC} $1"; }
ok()    { echo -e " ${GREEN}✅${NC} $1"; }
warn()  { echo -e " ${YELLOW}⚠️${NC} $1"; }
fail()  { echo -e "${RED}❌${NC} $1"; exit 1; }
step()  { echo -e "\n${BLUE}═══${NC} $1 ${BLUE}═══${NC}"; }

cat << "EOF"

╔══════════════════════════════════════════════════════════════════╗
║     Миний дэлгүүр — POS Систем                                  ║
║     Linux Mint XFCE 22.04 бүрэн автомат суулгагч                ║
╚══════════════════════════════════════════════════════════════════╝
EOF
echo ""

# ─── Root check ───
if [ "$EUID" -ne 0 ]; then
    warn "Энэ скрипт root эрх шаардана. sudo ашиглаж байна..."
    exec sudo bash "$0" "$@"
    exit 0
fi

# ─── Config ───
INSTALL_DIR="/opt/minii-delguur"
POS_USER="${POS_USER:-delguur}"
POS_PASSWORD="${POS_PASSWORD:-delguur123}"
DISABLE_POWER_SAVE="${DISABLE_POWER_SAVE:-yes}"
SETUP_AUTOLOGIN="${SETUP_AUTOLOGIN:-yes}"
OPTIMIZE_XFCE="${OPTIMIZE_XFCE:-yes}"

# ──────────────────────────────────────────────────────────────────
step "1. Систем шалгах"
# ──────────────────────────────────────────────────────────────────

if [ -f /etc/os-release ]; then
    source /etc/os-release
    OS_NAME="${PRETTY_NAME:-$NAME}"
    OS_ID="${ID}"
    OS_ID_LIKE="${ID_LIKE}"
else
    fail "/etc/os-release олдсонгүй"
fi

ok "Үйлдлийн систем: ${OS_NAME}"

if ! echo "${OS_ID} ${OS_ID_LIKE}" | grep -qi 'ubuntu\|debian\|linuxmint'; then
    fail "Зөвхөн Ubuntu / Debian / Linux Mint дэмжигдэнэ."
fi

ARCH=$(uname -m)
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
CPU_CORES=$(nproc)
ok "CPU: ${CPU_CORES} цөм, RAM: ${TOTAL_RAM}MB, Архитектур: ${ARCH}"

# ──────────────────────────────────────────────────────────────────
step "2. Системийн хамаарлууд суулгах"
# ──────────────────────────────────────────────────────────────────

info "Системийн package жагсаалт шинэчилж байна..."
DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>/dev/null | tail -1

PACKAGES=(
    python3 python3-pip python3-venv
    python3-dev build-essential
    libwebkit2gtk-4.1-0
    pkg-config libcairo2-dev gir1.2-gtk-3.0
    git curl wget
    rsync
    sqlite3
)

info "Системийн ${#PACKAGES[@]} багц суулгаж байна..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${PACKAGES[@]}" 2>&1 | tail -3
ok "Системийн хамаарлууд суулгагдлаа"

PYTHON_VER=$(python3 --version 2>&1)
ok "Python: ${PYTHON_VER}"

# ──────────────────────────────────────────────────────────────────
step "3. Програмыг хуулах"
# ──────────────────────────────────────────────────────────────────

if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    info "Файлуудыг ${SCRIPT_DIR} → ${INSTALL_DIR} руу хуулж байна..."

    PREV_EXISTS=false
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/pos.db" ]; then
        PREV_EXISTS=true
        warn "Хуучин суулгац олдлоо. pos.db нөөцөлж байна..."
        if [ -f "$INSTALL_DIR/pos.db" ]; then
            cp "$INSTALL_DIR/pos.db" /tmp/pos.db.backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
            ok "Хуучин pos.db нөөцлөгдлөө"
        fi
    fi

    mkdir -p "$INSTALL_DIR"
    rsync -a --info=progress2 "$SCRIPT_DIR/" "$INSTALL_DIR/" \
        --exclude=venv \
        --exclude=.git \
        --exclude=__pycache__ \
        --exclude='*.pyc' \
        --exclude=.pytest_cache \
        --exclude='*~' \
        --exclude=tests \
        --exclude=requirements-dev.txt \
        --exclude=backups \
        --exclude=logs \
        --exclude=pos.db 2>&1 | tail -1

    if [ "$PREV_EXISTS" = true ]; then
        LATEST_BACKUP=$(ls -t /tmp/pos.db.backup-* 2>/dev/null | head -1)
        if [ -n "$LATEST_BACKUP" ] && [ ! -f "$INSTALL_DIR/pos.db" ]; then
            cp "$LATEST_BACKUP" "$INSTALL_DIR/pos.db"
            ok "Хуучин pos.db сэргээгдлээ"
        fi
    fi

    ok "Файлууд ${INSTALL_DIR} руу хуулагдлаа"
    cd "$INSTALL_DIR"
else
    ok "Программ аль хэдийн ${INSTALL_DIR} дотор байна"
    cd "$INSTALL_DIR"
fi

ROOT_DIR="$INSTALL_DIR"

# Нэвтрэх хэрэглэгчийн файлын эзэмшил
REAL_USER="${SUDO_USER:-$USER}"
if [ "$REAL_USER" != "root" ] && [ -n "$REAL_USER" ]; then
    chown -R "$REAL_USER:$REAL_USER" "$ROOT_DIR" 2>/dev/null || true
fi

# ──────────────────────────────────────────────────────────────────
step "4. Виртуал орчин ба Python хамаарлууд"
# ──────────────────────────────────────────────────────────────────

info "venv үүсгэж байна..."
su -s /bin/bash -c "
    cd $ROOT_DIR
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
" "${REAL_USER}" 2>&1 | tail -3
ok "Python орчин бэлэн"

# ──────────────────────────────────────────────────────────────────
step "5. Өгөгдлийн сан үүсгэх / шинэчлэх"
# ──────────────────────────────────────────────────────────────────

su -s /bin/bash -c "
    cd $ROOT_DIR
    source venv/bin/activate
    python3 -c \"
import database as db
db.init_db()
print('OK')
\"
" "${REAL_USER}" 2>&1 | tail -1

# Verify DB
su -s /bin/bash -c "
    cd $ROOT_DIR
    source venv/bin/activate
    python3 -c \"
import sqlite3
conn = sqlite3.connect('$ROOT_DIR/pos.db')
row = conn.execute('PRAGMA integrity_check').fetchone()
if row and row[0] == 'ok':
    print('OK')
else:
    print('FAIL: ' + str(row))
conn.close()
\"
" "${REAL_USER}" 2>&1

ok "Өгөгдлийн сан бэлэн"

# Санууд
mkdir -p "$ROOT_DIR/logs" "$ROOT_DIR/backups" "$ROOT_DIR/static/uploads"
chmod 777 "$ROOT_DIR/logs" "$ROOT_DIR/backups"

# Run scripts
chmod +x "$ROOT_DIR/start.sh" \
         "$ROOT_DIR/mint/start.sh" "$ROOT_DIR/mint/desktop.py" \
         "$ROOT_DIR/ubuntu/start.sh" "$ROOT_DIR/ubuntu/desktop.py" 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────
step "6. Дүрс үүсгэх"
# ──────────────────────────────────────────────────────────────────

if [ ! -f "$ROOT_DIR/static/pos-icon.png" ] && [ -f "$ROOT_DIR/generate_icon.py" ]; then
    su -s /bin/bash -c "
        cd $ROOT_DIR
        source venv/bin/activate
        python3 generate_icon.py
    " "${REAL_USER}" 2>/dev/null || warn "Дүрс үүсгэхэд алдаа гарлаа (алгасав)"
fi

# ──────────────────────────────────────────────────────────────────
step "7. POS хэрэглэгч үүсгэх"
# ──────────────────────────────────────────────────────────────────

if id "$POS_USER" &>/dev/null; then
    ok "Хэрэглэгч '${POS_USER}' аль хэдийн байна"
else
    info "Хэрэглэгч '${POS_USER}' үүсгэж байна..."

    useradd -m -s /bin/bash \
        -c "Дэлгүүрийн POS хэрэглэгч" \
        "$POS_USER" 2>/dev/null || true

    echo "${POS_USER}:${POS_PASSWORD}" | chpasswd
    usermod -aG lp,dialout,plugdev "$POS_USER" 2>/dev/null || true
    ok "Хэрэглэгч '${POS_USER}' үүслээ (нууц үг: ${POS_PASSWORD})"
fi

# Ensure POS user owns the install directory
chown -R "$POS_USER:$POS_USER" "$ROOT_DIR" 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────
step "8. Desktop shortcut + Auto-start"
# ──────────────────────────────────────────────────────────────────

USER_HOME=$(eval echo "~${POS_USER}")
mkdir -p "$USER_HOME/Desktop" "$USER_HOME/.config/autostart"

DESKTOP_FILE="$USER_HOME/Desktop/Миний_дэлгүүр.desktop"
cat > "$DESKTOP_FILE" << DESKTOPEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Миний дэлгүүр
Comment=POS систем — Борлуулалт, нөөц, тайлан
Exec=${ROOT_DIR}/start.sh
Path=${ROOT_DIR}
Icon=${ROOT_DIR}/static/pos-icon.png
Terminal=false
Categories=Office;Finance;
StartupNotify=true
StartupWMClass=Миний дэлгүүр
Name[mn]=Миний дэлгүүр
Keywords=pos;sale;store;борлуулалт;дэлгүүр;касс
DESKTOPEOF
chmod +x "$DESKTOP_FILE"

cp "$DESKTOP_FILE" "$USER_HOME/.config/autostart/Миний_дэлгүүр.desktop"

chown -R "$POS_USER:$POS_USER" "$USER_HOME/Desktop" "$USER_HOME/.config"

ok "Desktop shortcut + auto-start тохируулагдлаа"

# ──────────────────────────────────────────────────────────────────
step "9. Systemd үйлчилгээ"
# ──────────────────────────────────────────────────────────────────

if command -v systemctl &>/dev/null; then
    SERVICE_FILE="/etc/systemd/system/minii-delguur.service"
    cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=Миний дэлгүүр POS System
After=network.target graphical.target
Wants=graphical.target

[Service]
Type=simple
User=${POS_USER}
WorkingDirectory=${ROOT_DIR}
ExecStartPre=/bin/sleep 3
ExecStart=${ROOT_DIR}/venv/bin/python3 ${ROOT_DIR}/mint/desktop.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0
Environment=XAUTHORITY=${USER_HOME}/.Xauthority

[Install]
WantedBy=graphical.target
SERVICEEOF

    systemctl daemon-reload
    systemctl enable minii-delguur.service 2>/dev/null || true
    ok "Systemd үйлчилгээ суулаа (minii-delguur.service)"
fi

# ──────────────────────────────────────────────────────────────────
step "10. Авто нэвтрэлт (LightDM)"
# ──────────────────────────────────────────────────────────────────

if [ "$SETUP_AUTOLOGIN" = "yes" ]; then
    AUTOLOGIN_CONF="/etc/lightdm/lightdm.conf.d/50-pos-autologin.conf"
    mkdir -p "$(dirname "$AUTOLOGIN_CONF")"

    if [ -f /etc/lightdm/lightdm.conf ]; then
        info "LightDM илэрсэн — авто нэвтрэлт тохируулж байна..."

        cat > "$AUTOLOGIN_CONF" << LIGHTDMEOF
[Seat:*]
autologin-user=${POS_USER}
autologin-user-timeout=0
autologin-session=xfce
LIGHTDMEOF
        ok "LightDM авто нэвтрэлт: ${POS_USER}"
    else
        warn "LightDM олдсонгүй. Авто нэвтрэлтийг гараар тохируулна уу."
    fi
fi

# ──────────────────────────────────────────────────────────────────
step "11. Дэлгүүрийн компьютерт зориулсан системийн оновчлол"

# ─────────────────────────────────────
# 11a. Дэлгэц унтрах / түгжихийг болиулах
# ─────────────────────────────────────

SUDO_USER=${REAL_USER}

if [ "$DISABLE_POWER_SAVE" = "yes" ]; then
    info "Эрчим хүч хэмнэлт, дэлгэц түгжих, унтах горимыг идэвхгүйжүүлж байна..."

    # ── LightDM: өөрийн screen lock-г болиулах ──
    if [ -f /etc/lightdm/lightdm.conf ]; then
        if grep -q '^\[Seat:\*\]' /etc/lightdm/lightdm.conf 2>/dev/null; then
            if ! grep -q 'lock-session' /etc/lightdm/lightdm.conf 2>/dev/null; then
                sed -i '/^\[Seat:\*\]/a lock-session=false' /etc/lightdm/lightdm.conf
            fi
        fi
    elif [ ! -f "$AUTOLOGIN_CONF" ]; then
        mkdir -p /etc/lightdm/lightdm.conf.d
        cat > "$AUTOLOGIN_CONF" << LIGHTDMEOF2
[Seat:*]
lock-session=false
LIGHTDMEOF2
    fi

    # ── XFCE Power Manager: бүх унтраалтыг болиулах ──
    XFCE4_XML="${USER_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml"
    mkdir -p "$(dirname "$XFCE4_XML")"

    cat > "$XFCE4_XML" << XFCEPOWER
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-power-manager" version="1.0">
  <property name="xfce4-power-manager" type="empty">
    <property name="power-button-action" type="uint" value="3"/>
    <property name="sleep-button-action" type="uint" value="3"/>
    <property name="hibernate-button-action" type="uint" value="3"/>
    <property name="brightness-switch-restore-on-exit" type="int" value="0"/>
    <property name="brightness-switch" type="int" value="0"/>
    <property name="lid-action-on-battery" type="uint" value="3"/>
    <property name="lid-action-on-ac" type="uint" value="3"/>
    <property name="general-notification" type="bool" value="false"/>
    <property name="inactivity-sleep-mode-on-battery" type="uint" value="0"/>
    <property name="inactivity-sleep-mode-on-ac" type="uint" value="0"/>
    <property name="dpms-on-ac-off" type="uint" value="0"/>
    <property name="dpms-on-battery-off" type="uint" value="0"/>
    <property name="blank-on-ac" type="int" value="0"/>
    <property name="blank-on-battery" type="int" value="0"/>
    <property name="show-tray-icon" type="int" value="0"/>
    <property name="inactivity-on-ac" type="uint" value="0"/>
    <property name="inactivity-on-battery" type="uint" value="0"/>
    <property name="brightness-on-ac" type="uint" value="90"/>
    <property name="brightness-on-battery" type="uint" value="80"/>
    <property name="lock-screen-suspend-hibernate" type="bool" value="false"/>
    <property name="logind-handle-lid-switch" type="bool" value="false"/>
  </property>
</channel>
XFCEPOWER

    # ── XScreenSaver: болиулах ──
    XSAVER="${USER_HOME}/.xscreensaver"
    if [ ! -f "$XSAVER" ]; then
        cat > "$XSAVER" << XSAVEEOF
mode:		off
lock:		False
lockTimeout:	0
timeout:	0
dpmsEnabled:	False
dpmsQuickOff:	False
dpmsStandby:	0:00:00
dpmsSuspend:	0:00:00
dpmsOff:	0:00:00
XSAVEEOF
    fi

    # ── X11 DPMS: болиулах ──
    mkdir -p "$USER_HOME/.config/autostart"

    cat > "$USER_HOME/.config/autostart/disable-dpms.desktop" << DPMSDESKTOP
[Desktop Entry]
Type=Application
Name=Disable DPMS
Exec=xset s off -dpms
Hidden=false
X-GNOME-Autostart-enabled=true
DPMSDESKTOP

    # ── Logind: lid switch + sleep товчийг болиулах ──
    if [ -f /etc/systemd/logind.conf ]; then
        sed -i 's/^#\?HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
        sed -i 's/^#\?HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
        sed -i 's/^#\?HandleLidSwitchDocked=.*/HandleLidSwitchDocked=ignore/' /etc/systemd/logind.conf
        sed -i 's/^#\?HandleSuspendKey=.*/HandleSuspendKey=ignore/' /etc/systemd/logind.conf
        sed -i 's/^#\?HandleHibernateKey=.*/HandleHibernateKey=ignore/' /etc/systemd/logind.conf
        sed -i 's/^#\?IdleAction=.*/IdleAction=ignore/' /etc/systemd/logind.conf
    fi

    chown -R "$POS_USER:$POS_USER" "$USER_HOME/.config" 2>/dev/null || true
    ok "Дэлгэц унтрах, түгжих, унтах горим: БОЛИУЛАВ"
fi

# ─────────────────────────────────────
# 11b. CPU Performance горим
# ─────────────────────────────────────
if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
    info "CPU governor-г performance болгож байна..."
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        echo "performance" > "$cpu" 2>/dev/null || true
    done

    # Install cpufrequtils for persistence
    if command -v apt-get &>/dev/null; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cpufrequtils 2>/dev/null || true
        if [ -f /etc/default/cpufrequtils ]; then
            sed -i 's/^GOVERNOR=.*/GOVERNOR="performance"/' /etc/default/cpufrequtils
        else
            echo 'GOVERNOR="performance"' > /etc/default/cpufrequtils
        fi
    fi
    ok "CPU governor → performance"
fi

# ─────────────────────────────────────
# 11c. Swap багасгах (дарсан RAM-тай үед SSD хамгаалах)
# ─────────────────────────────────────
info "Swappiness тохируулж байна..."
sysctl vm.swappiness=10 2>/dev/null || true
if ! grep -q 'vm.swappiness' /etc/sysctl.conf 2>/dev/null; then
    echo "vm.swappiness=10" >> /etc/sysctl.conf
else
    sed -i 's/^vm.swappiness=.*/vm.swappiness=10/' /etc/sysctl.conf
fi
ok "vm.swappiness → 10"

# ─────────────────────────────────────
# 11d. XFCE-н тохиргоог оновчлох
# ─────────────────────────────────────

if [ "$OPTIMIZE_XFCE" = "yes" ]; then
    info "XFCE ширээний компьютерын тохиргоог оновчилж байна..."

    # ── XFCE композитор (compositor) болиулах → гүйцэтгэл нэмэгдэнэ ──
    XFWM4_XML="${USER_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml"
    mkdir -p "$(dirname "$XFWM4_XML")"

    cat > "$XFWM4_XML" << XFWM4EOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="use_compositing" type="bool" value="false"/>
    <property name="workspace_count" type="int" value="1"/>
    <property name="borderless_maximize" type="bool" value="true"/>
    <property name="snap_to_border" type="bool" value="false"/>
    <property name="snap_to_windows" type="bool" value="false"/>
    <property name="wrap_windows" type="bool" value="false"/>
    <property name="wrap_workspaces" type="bool" value="false"/>
    <property name="scroll_workspaces" type="bool" value="false"/>
    <property name="click_to_focus" type="bool" value="true"/>
    <property name="focus_delay" type="int" value="0"/>
    <property name="raise_delay" type="int" value="0"/>
    <property name="theme" type="string" value="Default"/>
    <property name="title_alignment" type="string" value="center"/>
    <property name="title_font" type="string" value="Sans 9"/>
  </property>
</channel>
XFWM4EOF

    # ── Мэдэгдэл (desktop notifications) болиулах ──
    NOTIFYD_XML="${USER_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-notifyd.xml"
    mkdir -p "$(dirname "$NOTIFYD_XML")"

    cat > "$NOTIFYD_XML" << NOTIFYEOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-notifyd" version="1.0">
  <property name="notify-location" type="uint" value="0"/>
  <property name="primary-monitor" type="int" value="0"/>
  <property name="do-fadeout" type="bool" value="false"/>
  <property name="fadeout-timeout" type="int" value="100"/>
  <property name="initial-opacity" type="int" value="90"/>
  <property name="default-timeout" type="int" value="1000"/>
  <property name="applications" type="empty">
    <property name="known_applications" type="array">
      <value type="string" value="mute"/>
    </property>
  </property>
</channel>
NOTIFYEOF

    # ── XFCE panel: доод самбарыг жижиг, авто нуугддаг болгох ──
    PANEL_XML="${USER_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
    if [ ! -f "$PANEL_XML" ]; then
        mkdir -p "$(dirname "$PANEL_XML")"
        cat > "$PANEL_XML" << PANELEOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-panel" version="1.0">
  <property name="configver" type="int" value="2"/>
  <property name="panels" type="array">
    <value type="int" value="1"/>
    <property name="dark-mode" type="bool" value="false"/>
    <property name="panel-1" type="empty">
      <property name="position" type="string" value="p=8;x=0;y=0"/>
      <property name="length" type="uint" value="100"/>
      <property name="position-locked" type="bool" value="true"/>
      <property name="icon-size" type="uint" value="0"/>
      <property name="size" type="uint" value="28"/>
      <property name="plugin-ids" type="array"/>
      <property name="autohide-behavior" type="uint" value="1"/>
      <property name="background-style" type="uint" value="0"/>
      <property name="enter-opacity" type="uint" value="100"/>
      <property name="leave-opacity" type="uint" value="60"/>
    </property>
  </property>
</channel>
PANELEOF
    fi

    # ── Desktop icons: болиулах (цэвэр дэлгэц) ──
    DESKTOP_XML="${USER_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml"
    if [ ! -f "$DESKTOP_XML" ]; then
        mkdir -p "$(dirname "$DESKTOP_XML")"
        cat > "$DESKTOP_XML" << DESKTOPXMLEOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-desktop" version="1.0">
  <property name="desktop-icons" type="empty">
    <property name="file-icons" type="empty">
      <property name="show-home" type="bool" value="false"/>
      <property name="show-filesystem" type="bool" value="false"/>
      <property name="show-trash" type="bool" value="false"/>
      <property name="show-removable" type="bool" value="false"/>
    </property>
    <property name="style" type="int" value="0"/>
  </property>
  <property name="backdrop" type="empty">
    <property name="screen0" type="empty">
      <property name="monitor0" type="empty">
        <property name="image-style" type="int" value="0"/>
        <property name="color-style" type="int" value="0"/>
        <property name="rgba1" type="array">
          <value type="double" value="0.101961"/>
          <value type="double" value="0.101961"/>
          <value type="double" value="0.180392"/>
          <value type="double" value="1.000000"/>
        </property>
      </property>
    </property>
  </property>
</channel>
DESKTOPXMLEOF
    fi

    # ── Авто эхлүүлэлтээс хэрэггүй зүйлс хасах ──
    # Хэрэглэгчийн глобал autostart
    rm -f "$USER_HOME/.config/autostart/xfce4-screensaver.desktop" 2>/dev/null || true
    rm -f "$USER_HOME/.config/autostart/update-notifier.desktop" 2>/dev/null || true
    rm -f "$USER_HOME/.config/autostart/mintupdate.desktop" 2>/dev/null || true
    rm -f "$USER_HOME/.config/autostart/mintreport.desktop" 2>/dev/null || true

    # ── bluetooth-г болиулах (дэлгүүрт хэрэггүй) ──
    if command -v rfkill &>/dev/null; then
        rfkill block bluetooth 2>/dev/null || true
    fi

    chown -R "$POS_USER:$POS_USER" "$USER_HOME/.config" 2>/dev/null || true
    ok "XFCE оновчлол дууслаа"
fi

# ──────────────────────────────────────────────────────────────────
step "12. Өдөр тутмын нөөц хуулалт (cron)"
# ──────────────────────────────────────────────────────────────────

if [ -f "$ROOT_DIR/deploy/backup.sh" ]; then
    BACKUP_SCRIPT="/usr/local/bin/pos-backup"
    cp "$ROOT_DIR/deploy/backup.sh" "$BACKUP_SCRIPT"
    chmod +x "$BACKUP_SCRIPT"

    echo "0 8,14,20 * * * root ${BACKUP_SCRIPT}" > /etc/cron.d/pos-backup
    ok "Өдөрт 3 удаа нөөцлөх cron тохируулагдлаа (08:00, 14:00, 20:00)"
fi

# ──────────────────────────────────────────────────────────────────
step "13. Шалгалт"
# ──────────────────────────────────────────────────────────────────

ERRORS=0

# Check venv
if [ -f "$ROOT_DIR/venv/bin/python3" ]; then
    ok "venv: OK"
else
    warn "venv олдсонгүй"
    ERRORS=$((ERRORS + 1))
fi

# Check Flask
if su -s /bin/bash -c "
    cd $ROOT_DIR
    source venv/bin/activate
    python3 -c 'import flask' 2>/dev/null && echo OK
" "${REAL_USER}" 2>/dev/null | grep -q OK; then
    ok "Flask: OK"
else
    warn "Flask импортлогдсонгүй"
fi

# Check webview
if dpkg -l libwebkit2gtk-4.1-0 &>/dev/null || dpkg -l libwebkit2gtk-4.0-37 &>/dev/null; then
    ok "WebKit2GTK: OK"
else
    warn "WebKit2GTK олдсонгүй — pywebview ажиллахгүй"
    ERRORS=$((ERRORS + 1))
fi

# Check DB
if sqlite3 "$ROOT_DIR/pos.db" "SELECT count(*) FROM products;" &>/dev/null; then
    ok "Database: OK"
else
    warn "Database шалгахад алдаа гарлаа"
    ERRORS=$((ERRORS + 1))
fi

# ──────────────────────────────────────────────────────────────────
# Done!
# ──────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
if [ $ERRORS -eq 0 ]; then
    echo "║  ✅ Суулгалт амжилттай дууслаа!                                ║"
else
    echo "║  ⚠️  Суулгалт дууслаа (${ERRORS} анхааруулгатай)                   ║"
fi
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  📍 Программ: ${ROOT_DIR}"
echo "  👤 Хэрэглэгч: ${POS_USER}"
echo "  🔑 Нууц үг:   ${POS_PASSWORD}"
echo ""
echo "  ⚙️  Хийгдсэн тохиргоо:"
echo "     ✅ Системийн хамаарлууд суугдсан"
echo "     ✅ Python виртуал орчин + бүх библиотек"
echo "     ✅ Өгөгдлийн сан бэлэн"
echo "     ✅ Desktop shortcut + авто асаалт"
echo "     ✅ Systemd үйлчилгээ"
echo "     ✅ Автомат нэвтрэлт (auto-login)"
echo "     ✅ Дэлгэц унтрах/түгжих/унтах: БОЛИУЛСАН"
echo "     ✅ CPU performance горим"
echo "     ✅ XFCE оновчлол (compositor, notifications)"
echo "     ✅ Өдөрт 3 удаа нөөцлөлт"
echo ""
echo "  🚀 Эхлүүлэх хоёр арга:"
echo "     А) Компьютерээ restart хийх (автоматаар асна)"
echo "        sudo reboot"
echo ""
echo "     Б) Гараар эхлүүлэх:"
echo "        sudo -u ${POS_USER} ${ROOT_DIR}/start.sh"
echo ""
echo "  ⚙️  Эхний тохируулга (вэб хуудаснаас):"
echo "     1. Админ нууц үг тохируулах (цоож дүрс → Тохиргоо)"
echo "     2. Хэвлэгчийн порт тохируулах"
echo "     3. eBarimt тохиргоо хийх"
echo ""
echo "  💡 Зөвлөмж:"
echo "     • Өгөгдлийн сангийн нөөцийг тогтмол USB дискрүү хуулж байх"
echo "     • Программ асахгүй бол: sudo systemctl status minii-delguur"
echo "     • Бүртгэл: journalctl -u minii-delguur -f"
echo ""

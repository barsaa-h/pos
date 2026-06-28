# AGENTS.md — POS System Project Guide

## Quick Commands
```bash
# Run tests
cd /home/barsaa/pos && source venv/bin/activate && python -m pytest tests/ -x -q

# Coverage
cd /home/barsaa/pos && source venv/bin/activate && coverage run -m pytest && coverage report

# Compile check (Python syntax)
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['app.py','database.py','config.py','printer.py','desktop.py','windows/desktop.py','ubuntu/desktop.py']]"

# Run desktop app (auto-bootstraps: venv + deps + DB)
./start.sh                   # Shell launcher (double-click or .desktop target)
python3 desktop.py           # Same, directly via Python
python3 desktop.py --dev     # Dev mode (Flask auto-reload)

# Run web-only (browser access)
source venv/bin/activate && python3 app.py   # http://localhost:8765

# Build Docker
docker build -t pos .
docker run -p 8765:8765 -v $(pwd)/data:/app/data pos

# Prometheus metrics
curl http://localhost:8765/api/metrics
```

## Architecture
- **Backend**: Flask on port 8765 (or `FLASK_PORT` env var)
- **Database**: SQLite with WAL mode at `pos.db` (or `POS_DB_PATH`)
- **Desktop**: pywebview — WinForms on Windows, GTK on Linux
- **Platform-specific launchers**: `windows/desktop.py`, `ubuntu/desktop.py`
- **Root dispatcher**: `desktop.py` — self-bootstrapping launcher (auto-creates venv, installs deps, inits DB), then delegates to platform script
- **Entry point**: `start.sh` (shell wrapper) or `python3 desktop.py` directly
- **Security**: Admin session with configurable timeout, login/logout with brute-force lockout, rate limiting on mutation routes, CSRF tokens, HSTS, security headers
- **Monitoring**: `/api/metrics` Prometheus endpoint, background health check (DB integrity, disk space, eBarimt queue), diagnostics with process memory

## Code Conventions
- **Language**: Mongolian UI strings, English code identifiers
- **DB**: parameterized queries only, no string concatenation
- **CSRF**: all mutating POST routes require `validate_csrf_token()`
- **Session**: admin auth via `session["admin"]` flag + configurable timeout; `/login` route for password-protected access
- **Rate Limiting**: `@rate_limit(max_requests, window_seconds)` decorator on all mutation routes
- **Admin Routes**: `@admin_required` decorator on all admin mutation routes (product/supplier/category CRUD, settings, cash drawer, returns)
- **Error handling**: no route should 500 on bad input; return JSON `{"success": false, "error": "..."}`
- **Imports**: database and config imported lazily where needed to avoid circular imports
- **Test fixtures**: `conftest.py` provides temp DB, test client, CSRF token

## Key Files
| File | Purpose |
|------|---------|
| `app.py` | Flask routes, CSRF, rate limiting, auth, file logging |
| `database.py` | SQLite schema, migrations, CRUD, backups (1766 lines) |
| `config.py` | Config defaults, secret key generation, DB-backed settings |
| `printer.py` | Cross-platform ESC/POS: COM port on Win, `/dev/usb/lp*` on Linux |
| `ebarimt.py` | Mongolian eBarimt API integration via `ebarimt-pos-sdk` |
| `i18n.py` | Translation helper; locales in `locales/mn.json`, `locales/en.json` |
| `desktop.py` | Self-bootstrapping launcher → `windows/desktop.py` or `ubuntu/desktop.py` |
| `start.sh` | Shell wrapper for .desktop files and double-click launch |
| `windows/desktop.py` | Windows launcher: WinForms, COM port, named mutex lock |
| `windows/start.bat` | Windows double-click launcher (Python detect + venv + deps) |
| `windows/start.ps1` | PowerShell launcher (Unicode-friendly) |
| `ubuntu/desktop.py` | Ubuntu launcher: GTK, flock, `/dev/usb/lp*` |
| `ubuntu/start.sh` | Thin wrapper — delegates to root `start.sh` |
| `ubuntu/install.sh` | One-click setup: venv, deps, desktop shortcut, autostart |
| `pos.spec` | PyInstaller spec (optional build) |
| `VERSION` | Single-line version string used by `/api/version` |
| `static/pos.js` | POS screen: cart, checkout, barcode, shortcuts |
| `static/customer.js` | Customer display: SSE with reconnect + polling fallback |
| `static/style.css` | Full stylesheet: categories, dark/light mode, responsive |
| `templates/pos.html` | Main POS screen |
| `templates/login.html` | Admin login page with password form |
| `templates/customer_display.html` | Customer-facing second screen |

## Database Tables
- `products` — barcode (UNIQUE), name, price, category, stock_qty, unit, cost_price, expiry_date, image_url, supplier_id
- `sales` — payment_type (cash/card/split/return/qr), amounts, ebarimt fields, return_of_sale_id
- `sale_items` — per-item quantity, unit_price, subtotal
- `settings` — key/value config store
- `stock_adjustments` — audit trail for stock changes
- `suppliers` — supplier CRUD
- `cash_drawer_log` — drawer open/close/float events
- `idempotency_keys` — prevents duplicate sales on network retry
- `held_orders` — suspend/resume cart

## Critical Context
- WAL mode + `synchronous=NORMAL`: crash-safe reads, slight write risk on power loss. Consider `FULL` for high-value stores.
- Admin auth: `session["admin"]` + `session["admin_login_time"]` with configurable timeout (default 8 hours). `/login` and `/logout` routes provide password protection (default PIN: `0000`). Brute-force lockout: 5 failures locks IP for 15 minutes.
- `auto_admin_session` auto-grants admin on first visit for single-terminal desktop UX even without login.
- Rate limiting: `@rate_limit(20, 60)` on admin mutation routes (product/supplier/category CRUD, settings, cash drawer). Sensitive ops (returns, eBarimt retry, printer test, backup) use stricter limits (5-10/60).
- Prometheus metrics: `/api/metrics` exposes uptime, DB size, sales counts, disk free, request count, eBarimt pending. Backward-compatible — no prometheus_client library needed.
- Background health check: runs every 5 minutes, checks DB integrity, disk space (<100 MB = warning), eBarimt queue length (>5 = warning), backup directory presence.
- Printer auto-detect runs once at startup, falls back to configured port, then OS default
- eBarimt failed receipts retried on next startup via background thread
- Customer display uses SSE with exponential backoff (1s→2s→4s→8s) then 500ms polling fallback
- Weight items (unit `кг`/`л`/`хайрцаг`) show quantity prompt with preset buttons + custom input
- Theme toggle stored in `settings` table (`auto`/`light`/`dark`), applied via `data-theme` on `<html>`

## Store PC Deployment (Linux Mint XFCE)

The target is a store computer with Linux Mint XFCE installed. The store PC may have NO internet — all dependencies must be pre-downloaded on a dev machine and bundled on the USB.

### Creating the offline USB installer

The fastest way — on a dev machine WITH internet, run the bundled script:

```bash
sudo bash /path/to/pos/create-usb.sh /dev/sdX   # X = your USB device letter
```

It automates everything: format, copy POS files, download `.deb` + pip wheels.

Or manually step by step:

```bash
# 1. Wipe and format USB (adjust /dev/sdX to your USB device)
sudo umount /dev/sdX1
sudo mkfs.ext4 -F -L POS-APP /dev/sdX1
sudo mkdir -p /mnt/usb-pos
sudo mount /dev/sdX1 /mnt/usb-pos

# 2. Copy POS source files
cd /home/barsaa/pos
sudo rsync -a --delete . /mnt/usb-pos/ \
  --exclude=venv --exclude=.git --exclude='__pycache__' \
  --exclude='*.pyc' --exclude=.pytest_cache --exclude=tests \
  --exclude=requirements-dev.txt --exclude='*~' \
  --exclude=pos.db --exclude=backups --exclude=logs \
  --exclude=.coverage --exclude=.coveragerc

# 3. Pre-download system .deb packages
sudo apt-get install --download-only -y \
  python3 python3-pip python3-venv python3-dev build-essential \
  libwebkit2gtk-4.1-0 pkg-config libcairo2-dev gir1.2-gtk-3.0 \
  git curl wget rsync sqlite3 2>&1
mkdir -p /mnt/usb-pos/offline/debs
sudo cp /var/cache/apt/archives/*.deb /mnt/usb-pos/offline/debs/
sudo dpkg-scanpackages /mnt/usb-pos/offline/debs /dev/null \
  | gzip > /mnt/usb-pos/offline/debs/Packages.gz

# 4. Pre-download Python packages (wheels)
pip download -r requirements.txt -d /mnt/usb-pos/offline/wheels

# 5. Create offline installer script
cat > /mnt/usb-pos/offline/install-offline.sh << 'OFFLINE'
#!/bin/bash
# Offline installer — run on store PC (no internet needed)
set -e
ROOT_DIR="/opt/minii-delguur"
OFFLINE_DIR="$(dirname "$0")"

# Install system debs from local cache
echo "📦 Системийн хамаарлууд суулгаж байна..."
sudo dpkg -i $OFFLINE_DIR/debs/*.deb 2>/dev/null || true
sudo apt-get install -f -y 2>&1 | tail -3

# Copy POS files
echo "📂 Файлуудыг хуулж байна..."
sudo mkdir -p $ROOT_DIR
sudo rsync -a $(dirname "$OFFLINE_DIR")/ $ROOT_DIR/ \
  --exclude=offline --exclude=venv --exclude=.git --exclude='__pycache__' \
  --exclude='*.pyc' --exclude=.pytest_cache --exclude=tests

# Setup venv + install wheels offline
cd $ROOT_DIR
python3 -m venv venv
source venv/bin/activate
pip install --no-index --find-links=$OFFLINE_DIR/wheels -r requirements.txt

# Init DB
python3 -c "import database as db; db.init_db()"

# Set up desktop shortcut + autostart
REAL_USER=${SUDO_USER:-$USER}
sudo chown -R $REAL_USER:$REAL_USER $ROOT_DIR
mkdir -p $HOME/Desktop $HOME/.config/autostart
cp $ROOT_DIR/mint/Миний_дэлгүүр.desktop $HOME/Desktop/
cp $ROOT_DIR/mint/Миний_дэлгүүр.desktop $HOME/.config/autostart/
chmod +x $ROOT_DIR/start.sh $ROOT_DIR/mint/desktop.py

echo "✅ Суулгалт дууслаа! Desktop дээрх дүрс дээр дарна уу."
OFFLINE
chmod +x /mnt/usb-pos/offline/install-offline.sh

# 6. Fix permissions
sudo chown -R 1000:1000 /mnt/usb-pos/
sudo chmod +x /mnt/usb-pos/start.sh /mnt/usb-pos/mint-setup.sh \
  /mnt/usb-pos/mint/desktop.py /mnt/usb-pos/mint/start.sh \
  /mnt/usb-pos/ubuntu/start.sh /mnt/usb-pos/ubuntu/desktop.py \
  /mnt/usb-pos/desktop.py

# 7. Unmount
sync
sudo umount /mnt/usb-pos
echo "✅ USB бэлэн! Одоо store PC дээр залгаад offline/install-offline.sh ажиллуулна."
```

### USB structure after creation

```
USB (POS-APP)/
├── app.py, database.py, templates/, static/, ...
├── mint/desktop.py, mint-setup.sh
├── start.sh, desktop.py
├── offline/
│   ├── debs/          # Pre-downloaded .deb packages
│   │   ├── packages.gz
│   │   └── *.deb
│   ├── wheels/        # Pre-downloaded pip wheels
│   │   └── *.whl
│   └── install-offline.sh  # One-shot installer for store PC
└── ...
```

### On the store PC (offline)

```bash
# Plug in USB, open terminal
cd /media/*/POS-APP/offline
sudo bash install-offline.sh
```

### On the store PC (with internet)

```bash
cd /media/*/POS-APP
sudo bash mint-setup.sh
```

### What mint-setup.sh does
1. Installs system packages: Python, WebKit2GTK, GTK dev, build tools
2. Copies POS files to `/opt/minii-delguur`
3. Creates Python venv + installs pip dependencies
4. Initializes SQLite database
5. Creates POS user account
6. Sets up desktop shortcut + XFCE autostart
7. Installs systemd service
8. Optimizes XFCE: disables screensaver, sleep, screen lock, DPMS
9. Configures auto-login
10. Sets up printer permissions (lp,dialout groups)
11. Installs firewall rules (only port 8765 open)

## Testing
```bash
source venv/bin/activate
python -m pytest tests/ -v    # Full verbose run
python -m pytest tests/ -x    # Stop on first failure
coverage run -m pytest && coverage report  # Coverage report (fail_under=50%)
```
116 tests: database CRUD (product, sale, return, held orders), API (pages, CSRF, checkout, login, security), eBarimt adapter.

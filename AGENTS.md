# AGENTS.md — POS System Project Guide

## Quick Commands
```bash
# Run tests
cd /home/barsaa/pos && source venv/bin/activate && python -m pytest tests/ -x -q

# Compile check (Python syntax)
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['app.py','database.py','config.py','printer.py','desktop.py','windows/desktop.py','ubuntu/desktop.py']]"

# Run desktop app
./ubuntu/start.sh           # Ubuntu
windows\start.bat           # Windows
python3 desktop.py          # Auto-detects OS

# Run web-only (browser access)
source venv/bin/activate && python3 app.py   # http://localhost:8765

# Build Docker
docker build -t pos .
docker run -p 8765:8765 -v $(pwd)/data:/app/data pos
```

## Architecture
- **Backend**: Flask on port 8765 (or `FLASK_PORT` env var)
- **Database**: SQLite with WAL mode at `pos.db` (or `POS_DB_PATH`)
- **Desktop**: pywebview — WinForms on Windows, GTK on Linux
- **Platform-specific launchers**: `windows/desktop.py`, `ubuntu/desktop.py`
- **Root dispatcher**: `desktop.py` auto-detects OS and delegates (uses `runpy.run_path`)

## Code Conventions
- **Language**: Mongolian UI strings, English code identifiers
- **DB**: parameterized queries only, no string concatenation
- **CSRF**: all mutating POST routes require `validate_csrf_token()`
- **Session**: admin auth via `session["admin"]` flag + timeout
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
| `desktop.py` | OS-detecting dispatcher → `windows/desktop.py` or `ubuntu/desktop.py` |
| `windows/desktop.py` | Windows launcher: WinForms, COM port, named mutex lock |
| `windows/start.bat` | Windows double-click launcher (Python detect + venv + deps) |
| `windows/start.ps1` | PowerShell launcher (Unicode-friendly) |
| `ubuntu/desktop.py` | Ubuntu launcher: GTK, flock, `/dev/usb/lp*` |
| `ubuntu/start.sh` | Ubuntu double-click launcher |
| `ubuntu/install.sh` | One-click setup: venv, deps, desktop shortcut, autostart |
| `pos.spec` | PyInstaller spec (optional build) |
| `VERSION` | Single-line version string used by `/api/version` |
| `static/pos.js` | POS screen: cart, checkout, barcode, shortcuts |
| `static/customer.js` | Customer display: SSE with reconnect + polling fallback |
| `static/style.css` | Full stylesheet: categories, dark/light mode, responsive |
| `templates/pos.html` | Main POS screen |
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
- Admin auth: `session["admin"]` + `session["admin_login_time"]` with configurable timeout (default 8 hours)
- Printer auto-detect runs once at startup, falls back to configured port, then OS default
- eBarimt failed receipts retried on next startup via background thread
- Customer display uses SSE with exponential backoff (1s→2s→4s→8s) then 500ms polling fallback
- Weight items (unit `кг`/`л`/`хайрцаг`) show quantity prompt with preset buttons + custom input
- Theme toggle stored in `settings` table (`auto`/`light`/`dark`), applied via `data-theme` on `<html>`

## Testing
```bash
source venv/bin/activate
python -m pytest tests/ -v    # Full verbose run
python -m pytest tests/ -x    # Stop on first failure
```
36 tests: database CRUD (product, sale, return, held orders), API (pages, CSRF, checkout), eBarimt adapter.

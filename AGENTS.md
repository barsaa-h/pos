# AGENTS.md — POS System Project Guide

## Quick Commands
```bash
# Run tests
cd /home/barsaa/pos && source venv/bin/activate && python -m pytest tests/ -x -q

# Compile check (Python syntax)
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['database.py','config.py','printer.py','ebarimt.py']]"

# Launch GTK desktop app
./posgtk-dev.sh
```

## Architecture
- **UI**: GTK 3 native (Gtk.Application, Gtk.Stack, Gi)
- **Database**: SQLite with WAL mode, `synchronous=FULL`, at path from `POS_DB_PATH` env var
- **Printer**: ESC/POS via python-escpos — auto-detects `/dev/usb/lp*` (Linux) or COM ports (Windows)
- **eBarimt**: Mongolian tax receipt API via `ebarimt-pos-sdk`
- **Async**: 4-worker thread pool (WorkQueue) for DB writes, printing, eBarimt, terminal

## Code Conventions
- **Language**: Mongolian UI strings, English code identifiers
- **DB**: parameterized queries only, no string concatenation
- **Error handling**: functions return `(result, error)` tuples, never raise on bad input
- **Imports**: database and config imported lazily where needed to avoid circular imports
- **Screen lazy-loading**: only POS screen is eagerly loaded; all others load on first click

## Key Files
| File | Purpose |
|------|---------|
| `database.py` | SQLite schema, migrations, CRUD, backups, audit log (2000+ lines) |
| `config.py` | Config defaults, DB-backed settings with cache |
| `printer.py` | ESC/POS auto-detect + receipt printing |
| `ebarimt.py` | Mongolian eBarimt API integration |
| `posgtk/main.py` | App entry, sidebar+stack layout, single keyboard dispatcher |
| `posgtk/pos.py` | POS screen: cart, barcode, split payment, held orders, eBarimt |
| `posgtk/sales.py` | Sales history with pagination, detail view, return processing |
| `posgtk/products.py` | Product CRUD with search, cache invalidation |
| `posgtk/categories.py` | Category CRUD with icon + color picker |
| `posgtk/suppliers.py` | Supplier CRUD |
| `posgtk/stock.py` | Stock adjustments with barcode scan + history |
| `posgtk/reports.py` | Sales/profit reports with date filter |
| `posgtk/settings.py` | 7-tab settings (store, printer, payment, tax, security, display, system) |
| `posgtk/widgets.py` | ProductCard, CartItem, make_cart_item_row() |
| `posgtk/cache.py` | In-memory product cache, prefix search index, category CSS gen |
| `posgtk/theme.py` | CSS file loader + scaler, dark/light themes |
| `posgtk/customer_display.py` | Second-monitor customer window (Gtk native) |
| `posgtk/login.py` | Admin PIN login with brute-force lockout |
| `posgtk/workqueue.py` | Thread pool for async operations |

## Database Tables
- `products` — barcode (UNIQUE), name, price, category, stock_qty, unit, cost_price, expiry_date, image_url, supplier_id
- `sales` — payment_type (cash/card/split/return/qr), amounts, ebarimt fields, return_of_sale_id
- `sale_items` — per-item quantity, unit_price, subtotal
- `settings` — key/value config store
- `categories` — name (UNIQUE), icon (emoji), color (hex), sort_order
- `suppliers` — name, contact_person, phone, email, address
- `stock_adjustments` — audit trail for stock changes
- `cash_drawer_log` — drawer open/close/float events
- `shifts` — shift open/close + Z-report data
- `idempotency_keys` — prevents duplicate sales on network retry
- `held_orders` — suspend/resume cart
- `audit_log` — CRUD audit trail (product create/update/delete)

## Critical Context
- WAL mode + `synchronous=FULL`: crash-safe. Can be set to NORMAL for performance on slow disks.
- Admin auth: PIN-based login with bcrypt, 5-failure lockout (15 min)
- Printer auto-detects at startup; falls back to configured port, then OS default
- eBarimt failed receipts retried on next startup via background workqueue task
- Customer display uses direct GObject signals (same process, no SSE/polling needed)
- Weight items (unit `кг`/`л`/`хайрцаг`) show quantity prompt with preset + custom input
- Theme stores in `settings` table (`auto`/`light`/`dark`), applied via GTK CSS provider
- Product grid uses FlowBox with `set_visible_func` — virtual rendering, no 2500-widget DOM

## Testing
```bash
source venv/bin/activate
python -m pytest tests/ -v    # Full verbose run
python -m pytest tests/ -x    # Stop on first failure
```
28 tests: database CRUD (product, sale, return, held orders, audit, cashiers), eBarimt adapter, scaling.

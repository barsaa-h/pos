# POS System — Монгол Кассын Систем

Mongolian point-of-sale system with barcode scanning, thermal receipt printing, eBarimt integration, and customer display.

## Quick Start

```bash
# Install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run the server
python3 app.py
# Open http://localhost:8765
```

## Docker

```bash
docker compose up -d
# http://localhost:8765
```

## Features

- Barcode scanner support (keyboard wedge / serial)
- Touch-friendly product grid with category filtering
- Weighted item support (kg, liter, box)
- Cash / Card / Split / QR payment types
- Thermal receipt printing (ESC/POS — USB)
- eBarimt integration (Mongolian e-receipt API)
- Sales history, reports with charts
- Inventory management with stock adjustments
- Low stock alerts and expiry tracking
- Held orders (suspend/resume carts)
- Shift management (open/close with Z-report)
- Customer-facing second display (SSE + polling fallback)
- CSV import/export for products and sales
- Admin authentication with 4-digit PIN
- Dark/light/auto theme support

## Configuration

Set via the Settings page (admin) or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POS_PORT` | `8765` | Server port |
| `POS_DB_PATH` | `./pos.db` | Database path |
| `POS_SECRET_KEY` | (auto-generated) | Flask secret key |
| `POS_SECURE_COOKIES` | `false` | Enable Secure flag (behind HTTPS proxy) |
| `POS_DEBUG` | `0` | Debug mode |

## API Endpoints

All mutating endpoints require a CSRF token (`X-CSRF-Token` header or `csrf_token` form field).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | - | POS screen |
| GET | `/api/health` | - | Health check |
| GET | `/api/health/deep` | - | Deep health check (DB, printer, disk) |
| GET | `/api/products/search` | - | Product search/pagination |
| POST | `/api/barcode` | - | Barcode lookup |
| POST | `/api/checkout` | CSRF | Process sale |
| POST | `/api/product/create` | CSRF | Quick product create |
| GET/POST | `/api/customer-state` | - | Customer display state |
| GET | `/api/customer-stream` | - | SSE for customer display |
| POST | `/api/hold-order` | CSRF | Suspend cart |
| GET | `/api/held-orders` | - | List held orders |
| POST | `/api/recall-order/<id>` | CSRF | Resume cart |
| POST | `/api/reprint/<id>` | CSRF | Re-print receipt |
| GET | `/api/diagnostics` | Admin | System diagnostics |
| POST | `/api/printer/test` | Admin | Printer test |
| GET | `/reports/export` | Admin | CSV export |

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
ruff check .
ruff format --check .
```

## License

Proprietary. All rights reserved.

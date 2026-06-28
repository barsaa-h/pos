#!/bin/bash
# check.sh — local production-readiness smoke check for the POS system.
set -euo pipefail

cd "$(dirname "$0")"

if [ -x "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
elif [ -x "venv/bin/python3" ]; then
    PYTHON="venv/bin/python3"
else
    PYTHON="python3"
fi

echo "============================================"
echo "  POS System — Safety Check"
echo "============================================"

echo ""
echo "1. Compile check..."
"$PYTHON" - <<'PY'
import py_compile

files = [
    "app.py", "database.py", "config.py", "printer.py", "ebarimt.py",
    "qpay.py", "terminal.py", "i18n.py", "desktop.py",
    "windows/desktop.py", "ubuntu/desktop.py", "mint/desktop.py",
]
for path in files:
    py_compile.compile(path, doraise=True)
print(f"  OK: {len(files)} files compiled")
PY

echo ""
echo "2. Running tests..."
"$PYTHON" -m pytest tests/ -x -q

echo ""
echo "3. Flask page/API smoke..."
POS_DB_PATH="$(mktemp /tmp/pos-check-XXXXXX.db)" \
POS_SECRET_KEY="check-script-local-secret-key-1234567890" \
POS_FORCE_HTTPS=0 \
POS_SKIP_MODULE_INIT=1 \
"$PYTHON" - <<'PY'
import time

from app import create_app

app = create_app()
app.config["TESTING"] = True

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
        sess["csrf_token"] = "check-csrf"

    paths = [
        "/", "/customer", "/products", "/suppliers", "/categories",
        "/reports", "/settings", "/sales",
        "/api/health", "/api/health/deep", "/api/version",
        "/api/categories", "/api/products/search?q=",
    ]
    for path in paths:
        resp = client.get(path)
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert "Internal Server Error" not in body, path

    resp = client.post("/products/create", data={
        "csrf_token": "check-csrf",
        "barcode": "CHECK-001",
        "name": "Check Product",
        "price": "1234",
        "category": "Бусад",
        "unit": "ш",
        "cost_price": "1000",
    }, follow_redirects=False)
    assert resp.status_code in (200, 302), resp.status_code

    with client.session_transaction() as sess:
        csrf = sess["csrf_token"]

    resp = client.post("/api/checkout", json={
        "items": [{
            "barcode": "CHECK-001",
            "product_name": "Check Product",
            "quantity": 1,
            "unit_price": 1234,
            "subtotal": 1234,
        }],
        "payment_type": "cash",
        "cash_given": 1500,
        "idempotency_key": "check-sale-001",
    }, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

print("  OK: pages, APIs, product create, checkout")
PY

echo ""
echo "============================================"
echo "  ALL CHECKS PASSED"
echo "============================================"

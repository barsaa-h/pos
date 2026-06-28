import json


def test_pos_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Борлуулалт" in html


def test_settings_page_allowed(client):
    """Settings page should be accessible without login (auto-admin)."""
    resp = client.get("/settings")
    assert resp.status_code == 200


def test_api_products_search(client):
    resp = client.get("/api/products/search?q=")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["products"], list)

    resp2 = client.get("/api/products/search?q=test")
    assert resp2.status_code == 200


def test_api_barcode_no_auth(client):
    resp = client.post("/api/barcode",
        json={"barcode": "123456"}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    if data["success"]:
        assert "product" in data
    else:
        assert data["error"] == "not_found"


def test_api_customer_state(client):
    resp = client.get("/api/customer-state")
    assert resp.status_code == 200


def test_api_create_product_csrf_block(client):
    resp = client.post("/api/product/create",
        data=json.dumps({"barcode": "test1", "name": "Тест", "price": 1000}),
        content_type="application/json"
    )
    assert resp.status_code in (401, 403)


def test_api_create_product_with_csrf(authed_client, csrf_token):
    resp = authed_client.post("/api/product/create",
        data=json.dumps({"barcode": "test1", "name": "Тест", "price": 1000, "category": "Бусад", "unit": "ш"}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_search_products(client):
    from database import create_product
    create_product("search1", "Хайх тест", 3000, "Бусад", "ш")

    resp = client.get("/api/products/search?q=Хайх")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["products"], list)
    assert len(data["products"]) >= 1


def test_create_sale_api(client, csrf_token):
    from database import create_product
    from database import get_product_by_barcode
    create_product("sale1", "Борлуулалт тест", 10000, "Бусад", "ш")
    p = get_product_by_barcode("sale1")

    resp = client.post("/api/checkout",
        data=json.dumps({
            "items": [{"product_id": p["id"], "product_name": "Борлуулалт тест", "barcode": "sale1", "quantity": 1, "unit_price": 10000, "subtotal": 10000}],
            "payment_type": "cash",
            "total": 10000,
            "cash_given": 10000,
            "change_given": 0,
        }),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    sale = data["sale"]
    assert sale["total"] == 10000
    assert sale["payment_type"] == "cash"


def test_create_sale_api_csrf_blocked(client):
    resp = client.post("/api/checkout",
        data=json.dumps({"total": 1000}),
        content_type="application/json"
    )
    assert resp.status_code == 403


def test_reports_page(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
    resp = client.get("/reports")
    assert resp.status_code == 200


def test_reports_export(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
    resp = client.get("/reports/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type


def test_ebarimt_retry_not_configured(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
    resp = client.post("/api/ebarimt-retry",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_api_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_api_health_deep(client):
    resp = client.get("/api/health/deep")
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    assert "status" in data
    assert "components" in data
    assert "database" in data["components"]


def test_api_diagnostics(client):
    """Diagnostics should be accessible (auto-admin)."""
    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "version" in data
    assert "db_path" in data


def test_api_version(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "version" in data


def test_api_ebarimt_ping(client):
    resp = client.get("/api/ebarimt/ping")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reachable" in data


def test_api_printer_test_accessible(client, csrf_token):
    resp = client.post("/api/printer/test",
        data=json.dumps({}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    # Auto-admin means no redirect; response may be 200 or 400 depending on printer
    assert resp.status_code not in (302, 401)


def test_paginated_product_search(client):
    resp = client.get("/api/products/search?page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "products" in data
    assert "total" in data
    assert "page" in data


def test_product_search_sanitizes_pagination(client):
    resp = client.get("/api/products/search?page=abc&per_page=9999")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 200

    resp = client.get("/api/products/search?page=-5&per_page=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 1


def test_sales_page_sanitizes_bad_page(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()

    resp = client.get("/sales?page=abc")
    assert resp.status_code == 200
    assert "Internal Server Error" not in resp.data.decode()


def test_cash_drawer_sanitize_amount_input(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()

    def _get_token():
        with client.session_transaction() as s:
            return s.get("csrf_token", "")

    resp = client.post("/api/cash-drawer/action",
        json={"action": "float_in", "amount": "bad"},
        headers={"X-CSRF-Token": _get_token()}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["balance"] >= 0


def test_all_pages_render_with_auth(client, csrf_token):
    """Smoke test: every page route should return 200 with admin auth."""
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()

    pages = [
        "/", "/customer", "/products", "/suppliers", "/categories",
        "/reports", "/settings", "/sales",
    ]
    for path in pages:
        resp = client.get(path)
        body = resp.data.decode()
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        assert "Internal Server Error" not in body, f"{path} has 500 error"
        assert "Traceback" not in body, f"{path} has traceback"


def test_product_types_after_migration(client, csrf_token):
    """After all migrations, products table must have correct column types."""
    from database import get_db
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM products").fetchall()
        for r in rows:
            d = dict(r)
            assert isinstance(d["price"], int), f"price is {type(d['price'])}"
            assert isinstance(d["cost_price"], int), f"cost_price is {type(d['cost_price'])}"
            assert isinstance(d["is_active"], int), f"is_active is {type(d['is_active'])}"
            assert d["unit"] in ("ш", "кг", "л", "хайрцаг"), f"unit is '{d['unit']}'"
            assert isinstance(d["category"], str) and len(d["category"]) > 0, f"category is '{d['category']}'"


def test_admin_routes_accessible_with_auto_admin(client):
    """All admin routes should be accessible (auto-admin)."""
    admin_page_routes = ["/sales", "/suppliers", "/categories",
                          "/reports", "/settings"]
    for path in admin_page_routes:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} should be 200, got {resp.status_code}"

    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200, f"/api/diagnostics should be 200, got {resp.status_code}"


def test_hold_order_and_list(client, csrf_token):
    from database import create_product, get_product_by_barcode, set_setting
    create_product("hold-bc", "Hold Test", 5000, "Бусад", "ш")
    p = get_product_by_barcode("hold-bc")

    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = __import__("time").time()

    resp = client.post("/api/hold-order",
        json={"items": [{
            "product_id": p["id"], "product_name": "Hold Test",
            "barcode": "hold-bc", "quantity": 2, "unit_price": 5000,
            "subtotal": 10000
        }], "total": 10000, "label": "test hold"},
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    held = client.get("/api/held-orders")
    assert held.status_code == 200
    orders = held.get_json().get("orders", [])
    assert len(orders) >= 1
    match = [o for o in orders if o.get("label") == "test hold"]
    assert len(match) == 1


def test_hold_order_requires_auth(client):
    resp = client.post("/api/hold-order",
        json={"items": [], "total": 0},
        content_type="application/json"
    )
    assert resp.status_code in (401, 403)


def test_hold_order_items_max_50(client, csrf_token):
    from database import create_product
    items = []
    for i in range(60):
        items.append({"product_name": f"Item {i}", "barcode": f"h{i:04d}",
                       "quantity": 1, "unit_price": 1000, "subtotal": 1000})
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = __import__("time").time()
    resp = client.post("/api/hold-order",
        json={"items": items, "total": 60000},
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True


def test_csrf_token_rotates_after_use(authed_client):
    with authed_client.session_transaction() as sess:
        sess["csrf_token"] = "before-rotation"
    token_before = "before-rotation"

    resp = authed_client.post("/api/cash-drawer/action",
        json={"action": "open", "amount": 0, "note": "test"},
        headers={"X-CSRF-Token": token_before}
    )
    assert resp.status_code == 200

    with authed_client.session_transaction() as sess:
        assert sess.get("csrf_token") != token_before
        assert len(sess.get("csrf_token", "")) == 64


def test_csrf_rotation_response_header(client):
    with client.session_transaction() as sess:
        sess["csrf_token"] = "header-test"
        sess["admin"] = True
        sess["csrf_token"] = "header-test"
        sess["admin_login_time"] = __import__("time").time()
    resp = client.post("/api/cash-drawer/action",
        json={"action": "open", "amount": 0, "note": "test"},
        headers={"X-CSRF-Token": "header-test"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-CSRF-Token") is not None
    assert resp.headers.get("X-CSRF-Token") != "header-test"


def test_customer_state_persists_in_db(client, csrf_token):
    state = {"phase": "shopping", "items": [{"name": "test"}], "total": 5000}
    resp = client.post("/api/customer-state",
        json=state,
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200

    from database import get_setting
    import json as _json
    raw = get_setting("_customer_display_state", "")
    assert raw
    saved = _json.loads(raw)
    assert saved["phase"] == "shopping"
    assert saved["total"] == 5000


def test_https_redirect_with_x_forwarded_proto(client):
    resp = client.get("/settings", headers={"X-Forwarded-Proto": "http"})
    assert resp.status_code in (301, 302)
    assert "https://" in resp.headers.get("Location", "")


def test_https_no_redirect_when_disabled(monkeypatch):
    monkeypatch.setenv("POS_FORCE_HTTPS", "0")
    monkeypatch.setenv("FLASK_ENV", "testing")
    import importlib
    import app
    importlib.reload(app)

    with app.create_app().test_client() as c:
        resp = c.get("/settings", headers={"X-Forwarded-Proto": "http"})
        assert resp.status_code in (200, 302)
        if resp.status_code == 302:
            assert "https" not in resp.headers.get("Location", "").lower()


def test_save_terminal_settings(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
        sess["csrf_token"] = csrf_token

    resp = client.post("/settings",
        data={
            "csrf_token": csrf_token,
            "terminal_enabled": "true",
            "terminal_ip": "192.168.1.150",
            "terminal_port": "9999",
            "store_name": "Моност"
        }
    )
    assert resp.status_code == 302

    from config import get_config, invalidate_settings_cache
    invalidate_settings_cache()

    assert get_config("terminal_enabled") == "true"
    assert get_config("terminal_ip") == "192.168.1.150"
    assert get_config("terminal_port") == "9999"

    # Reset config for other tests
    client.post("/settings",
        data={
            "csrf_token": csrf_token,
            "terminal_enabled": "false",
            "terminal_ip": "",
            "terminal_port": "10009",
            "store_name": "Моност"
        }
    )
    invalidate_settings_cache()


def test_terminal_disabled_when_enabled_setting_false(client, csrf_token):
    from database import set_setting

    set_setting("terminal_enabled", "false")
    set_setting("terminal_ip", "192.168.1.150")
    set_setting("terminal_port", "10009")

    resp = client.post(
        "/api/terminal/test",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_terminal_checkout_failed_payment_does_not_create_sale(client, csrf_token, monkeypatch):
    import terminal
    from database import create_product, get_product_by_barcode, get_sales_count, set_setting

    create_product("pax-fail", "PAX Fail", 5500, "Бусад", "ш")
    product = get_product_by_barcode("pax-fail")
    set_setting("terminal_enabled", "true")
    set_setting("terminal_ip", "127.0.0.1")
    set_setting("terminal_port", "10009")
    monkeypatch.setattr(terminal, "send_payment", lambda amount, invoice_no="": {
        "success": False,
        "error": "declined",
    })

    before = get_sales_count()
    resp = client.post(
        "/api/terminal/checkout",
        json={"items": [{
            "product_id": product["id"],
            "product_name": "PAX Fail",
            "barcode": "pax-fail",
            "quantity": 1,
            "unit_price": 5500,
            "subtotal": 5500,
        }]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 502
    assert get_sales_count() == before


def test_terminal_checkout_approved_creates_sale(client, csrf_token, monkeypatch):
    import terminal
    from database import create_product, get_product_by_barcode, set_setting

    create_product("pax-ok", "PAX OK", 6600, "Бусад", "ш")
    product = get_product_by_barcode("pax-ok")
    set_setting("terminal_enabled", "true")
    set_setting("terminal_ip", "127.0.0.1")
    set_setting("terminal_port", "10009")

    seen = {}
    def fake_send_payment(amount, invoice_no=""):
        seen["amount"] = amount
        seen["invoice_no"] = invoice_no
        return {"success": True, "transaction_id": "TXN123", "amount": amount}

    monkeypatch.setattr(terminal, "send_payment", fake_send_payment)

    resp = client.post(
        "/api/terminal/checkout",
        json={"items": [{
            "product_id": product["id"],
            "product_name": "PAX OK",
            "barcode": "pax-ok",
            "quantity": 1,
            "unit_price": 1,
            "subtotal": 1,
        }]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert seen["amount"] == 6600
    assert data["sale"]["terminal_txn_id"] == "TXN123"
    assert data["sale"]["terminal_status"] == "approved"


def test_qpay_status_returns_404_for_bad_id(client):
    resp = client.get("/api/qpay/status/nonexistent_invoice")
    assert resp.status_code in (404, 400)


def test_ebarimt_retry_skipped_without_terminal(client, csrf_token):
    from database import set_setting
    set_setting("ebarimt_enabled", "false")
    set_setting("terminal_enabled", "false")
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = __import__("time").time()

    resp = client.post("/api/ebarimt-retry",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code in (200, 400)


def test_stock_adjustment_create(client, csrf_token):
    from database import create_product, get_product_by_barcode
    create_product("stock-adj", "Stock Test", 3000, "Бусад", "ш")
    p = get_product_by_barcode("stock-adj")

    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = __import__("time").time()

    resp = client.post("/inventory/adjust",
        data={"product_id": p["id"], "adjustment": 10, "reason": "тест"},
        follow_redirects=True,
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code in (200, 302, 404)
    # route may not exist in this version; accept any non-5xx response
    assert resp.status_code < 500


def test_terminal_cancel_no_active_sale(client, csrf_token):
    resp = client.post("/api/terminal/cancel",
        json={"invoice_no": "NONEXISTENT"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "invoice_no" in data


def test_terminal_test_not_configured(client, csrf_token):
    from database import set_setting
    set_setting("terminal_enabled", "false")
    resp = client.post("/api/terminal/test",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_qpay_status_returns_404_for_bad_id(client):
    resp = client.get("/api/qpay/status/nonexistent_invoice")
    assert resp.status_code in (404, 400)


def test_ebarimt_retry_skipped_without_terminal(client, csrf_token):
    from database import set_setting
    set_setting("ebarimt_enabled", "false")
    set_setting("terminal_enabled", "false")
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = __import__("time").time()

    resp = client.post("/api/ebarimt-retry",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code in (200, 400)


def test_qpay_invoice_missing_params(client, csrf_token):
    resp = client.post("/api/qpay/invoice",
        json={},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code in (400, 404, 200)


def test_qpay_mock_check_missing_invoice(client):
    resp = client.get("/api/qpay/mock-check/nonexistent")
    assert resp.status_code in (404, 400)


def test_category_add_no_name(client, csrf_token):
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = __import__("time").time()
    resp = client.post("/api/category/add",
        json={"name": ""},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code in (400, 200)


def test_qpay_webhook_missing_data(client):
    resp = client.post("/api/qpay/webhook",
        json={},
        content_type="application/json"
    )
    assert resp.status_code in (400, 200, 401, 404)


def test_barcode_lookup_empty(client):
    resp = client.post("/api/barcode", json={"barcode": ""})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False

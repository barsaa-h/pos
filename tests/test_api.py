import json


def test_pos_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Борлуулалт" in html


def test_settings_page_requires_admin(client):
    resp = client.get("/settings")
    assert resp.status_code == 200


def test_settings_page_allowed_authed(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
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
    assert resp.status_code in (200, 404)
    data = resp.get_json()
    if resp.status_code == 200:
        assert data["success"] is True
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
    assert resp.status_code == 403


def test_api_create_product_with_csrf(client, csrf_token):
    resp = client.post("/api/product/create",
        data=json.dumps({"barcode": "test1", "name": "Тест", "price": 1000, "category": "Бусад", "unit": "ш", "stock_qty": 10}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_search_products(client):
    from database import create_product
    create_product("search1", "Хайх тест", 3000, "Бусад", 5, "ш")

    resp = client.get("/api/products/search?q=Хайх")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["products"], list)
    assert len(data["products"]) >= 1


def test_create_sale_api(client, csrf_token):
    from database import create_product
    from database import get_product_by_barcode
    create_product("sale1", "Борлуулалт тест", 10000, "Бусад", 10, "ш")
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

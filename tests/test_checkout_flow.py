"""Integration tests for full checkout flow."""

import json


def test_checkout_cash_success(client, csrf_token, app):
    with app.app_context():
        from database import create_product
        pid, err = create_product("test123", "Test Product", 5000, "Бусад")
    assert pid is not None

    cart = [{"product_id": pid, "product_name": "Test Product",
             "barcode": "test123", "quantity": 2, "unit_price": 5000}]
    resp = client.post("/api/checkout", json={
        "items": cart,
        "payment_type": "cash",
        "cash_given": 10000,
        "csrf_token": csrf_token,
    }, headers={"X-CSRF-Token": csrf_token})
    data = resp.get_json()
    assert data["success"] is True
    assert data["sale"]["id"] > 0
    assert data["sale"]["total"] == 10000
    assert data["sale"]["payment_type"] == "cash"


def test_checkout_printer_offline(client, csrf_token, app, monkeypatch):
    def mock_print(*args, **kwargs):
        raise FileNotFoundError("No such device")
    monkeypatch.setattr("printer.print_receipt", mock_print)

    with app.app_context():
        from database import create_product
        pid, err = create_product("test456", "Test Product 2", 3000, "Бусад")
    assert pid is not None

    cart = [{"product_id": pid, "product_name": "Test Product 2",
             "barcode": "test456", "quantity": 1, "unit_price": 3000}]
    resp = client.post("/api/checkout", json={
        "items": cart,
        "payment_type": "cash",
        "cash_given": 3000,
        "csrf_token": csrf_token,
    }, headers={"X-CSRF-Token": csrf_token})
    data = resp.get_json()
    assert data["success"] is True
    assert data["sale"]["id"] > 0

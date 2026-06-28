def test_create_held_order(db, request):
    from database import create_held_order, get_held_order
    bc = f"ho_{request.node.name}"
    from database import create_product
    create_product(bc, "Хүлээлгэсэн бараа", 1000, "Бусад", "ш")
    items = [{"product_name": "Хүлээлгэсэн бараа", "quantity": 2, "unit_price": 1000, "subtotal": 2000}]
    order_id = create_held_order("Test order", items, 2000)
    assert order_id is not None
    order = get_held_order(order_id)
    assert order is not None
    assert order["label"] == "Test order"
    assert order["total"] == 2000
    assert len(order["items"]) == 1


def test_get_held_orders(db, request):
    from database import create_held_order, get_held_orders, delete_held_order
    items1 = [{"product_name": "A", "quantity": 1, "unit_price": 500, "subtotal": 500}]
    items2 = [{"product_name": "B", "quantity": 2, "unit_price": 1000, "subtotal": 2000}]
    id1 = create_held_order("Order 1", items1, 500)
    id2 = create_held_order("Order 2", items2, 2000)
    orders = get_held_orders()
    assert len(orders) >= 2

    delete_held_order(id1)
    orders_after = get_held_orders()
    remaining_ids = [o["id"] for o in orders_after]
    assert id1 not in remaining_ids
    assert id2 in remaining_ids


def test_delete_held_order(db, request):
    from database import create_held_order, get_held_order, delete_held_order
    items = [{"product_name": "X", "quantity": 1, "unit_price": 100, "subtotal": 100}]
    order_id = create_held_order("To delete", items, 100)
    assert get_held_order(order_id) is not None
    delete_held_order(order_id)
    assert get_held_order(order_id) is None


def test_held_orders_api(client, csrf_token):
    import json
    resp = client.post("/api/hold-order",
        data=json.dumps({
            "label": "API test",
            "items": [{"product_name": "Test", "quantity": 1, "unit_price": 500, "subtotal": 500}],
            "total": 500
        }),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["id"] is not None

    resp2 = client.get("/api/held-orders")
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["success"] is True
    assert len(data2["orders"]) >= 1
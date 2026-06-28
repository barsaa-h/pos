import json
import time


def test_customer_display_idle_state(client):
    resp = client.get("/api/customer-state")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data.get("phase"), str)
    assert isinstance(data.get("items"), list)


def test_customer_display_shopping_state(client, csrf_token):
    state = {"phase": "shopping", "items": [{"name": "Test", "quantity": 1, "unit_price": 5000, "subtotal": 5000}], "total": 5000}
    resp = client.post("/api/customer-state", json=state, headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    resp = client.get("/api/customer-state")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["phase"] == "shopping"
    assert len(data["items"]) == 1
    assert data["total"] == 5000


def test_customer_display_paying_to_complete(client, csrf_token):
    from database import set_setting

    state = {"phase": "paying", "items": [], "total": 10000, "payment_type": "cash", "cash_given": 10000, "change_given": 0}
    resp = client.post("/api/customer-state", json=state, headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 200

    state2 = {"phase": "complete", "items": [], "total": 10000, "payment_type": "cash", "lottery": "LOT999"}
    resp = client.post("/api/customer-state", json=state2, headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 200

    resp = client.get("/api/customer-state")
    data = resp.get_json()
    assert data["phase"] == "complete"
    assert data["lottery"] == "LOT999"


def test_customer_display_qr_state(client, csrf_token):
    state = {"phase": "paying", "items": [], "total": 5000, "qr_image": "base64_qr_data"}
    resp = client.post("/api/customer-state", json=state, headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 200

    resp = client.get("/api/customer-state")
    data = resp.get_json()
    assert data["qr_image"] == "base64_qr_data"


def test_sse_stream(client):
    resp = client.get("/api/customer-stream")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"


def test_customer_display_round_trip(client, csrf_token):
    from database import set_setting
    set_setting("_customer_display_state", "")
    transitions = [
        {"phase": "idle", "items": [], "total": 0},
        {"phase": "shopping", "items": [{"name": "A"}], "total": 1000},
        {"phase": "paying", "items": [{"name": "A"}], "total": 1000, "payment_type": "cash", "cash_given": 1000},
        {"phase": "complete", "items": [{"name": "A"}], "total": 1000, "lottery": "WIN"},
        {"phase": "idle", "items": [], "total": 0},
    ]
    for state in transitions:
        resp = client.post("/api/customer-state", json=state, headers={"X-CSRF-Token": csrf_token})
        assert resp.status_code == 200

        resp = client.get("/api/customer-state")
        data = resp.get_json()
        assert data["phase"] == state["phase"]

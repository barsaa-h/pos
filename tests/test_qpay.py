from qpay import QPayClient


def test_qpay_check_payment_accepts_string_amount(monkeypatch):
    client = QPayClient("client", "secret", "https://example.test")
    monkeypatch.setattr(client, "_ensure_token", lambda: "token")
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: {
        "rows": [],
        "count": 1,
        "total_amount": "1234",
    })

    result = client.check_payment("invoice-1")

    assert result["payment_status"] == "paid"
    assert result["paid_amount"] == 1234

import pytest


def test_print_receipt_no_escpos(monkeypatch):
    """print_receipt should return error when python-escpos not installed."""
    monkeypatch.setattr("printer.ESCPOS_AVAILABLE", False)
    from printer import print_receipt
    result = print_receipt({"id": 1, "total": 1000, "payment_type": "cash", "items": []}, {"name": "Store"})
    assert result["success"] is False
    assert "суулгаагүй" in result["error"]


def test_print_receipt_card_skip(monkeypatch):
    """Card payments should be skipped (PAX prints its own receipt)."""
    monkeypatch.setattr("printer.ESCPOS_AVAILABLE", True)
    from printer import print_receipt
    result = print_receipt({"id": 1, "total": 1000, "payment_type": "card", "items": []}, {"name": "Store"})
    assert result["success"] is True
    assert result.get("note") == "pax_printed"


def test_get_printer_port_fallback(monkeypatch):
    """get_effective_printer_port should fallback gracefully."""
    monkeypatch.setattr("printer.IS_WINDOWS", False)
    monkeypatch.setattr("printer.os.path.exists", lambda p: False)
    from printer import get_effective_printer_port, detect_printer_port

    port = get_effective_printer_port()
    assert port == "/dev/usb/lp0" or port is not None


def test_detect_printer_port_linux(monkeypatch):
    """Detect Linux printer port."""
    monkeypatch.setattr("printer.IS_WINDOWS", False)
    existing_paths = set()

    def mock_exists(path):
        return path in existing_paths

    monkeypatch.setattr("printer.os.path.exists", mock_exists)

    from printer import detect_printer_port

    # No printer found: fallback
    port = detect_printer_port()
    assert port == "/dev/usb/lp0"

    # Printer at /dev/usb/lp1
    existing_paths.add("/dev/usb/lp1")
    port = detect_printer_port()
    assert port == "/dev/usb/lp1"


@pytest.fixture
def sale_with_items():
    return {
        "id": 99,
        "payment_type": "cash",
        "total": 12340,
        "subtotal": 12340,
        "cash_given": 15000,
        "change_given": 2660,
        "cash_amount": 15000,
        "card_amount": 0,
        "ebarimt_status": "sent",
        "ebarimt_qr": "test_qr_data",
        "ebarimt_lottery": "LOT123",
        "items": [
            {"product_name": "Test Item", "category": "Бусад",
             "quantity": 2, "unit_price": 5000, "subtotal": 10000},
            {"product_name": "Milk", "category": "Сүүн бүтээгдэхүүн",
             "quantity": 1, "unit_price": 2340, "subtotal": 2340},
        ]
    }


def test_print_formatting_functions(sale_with_items):
    """Test the formatting helper functions."""
    from printer import _fmt, _rpad, _rfmt
    assert _fmt(1000) == "1,000 ₮"
    assert _fmt(0) == "0 ₮"
    assert _fmt(None) == "0 ₮"
    assert _rpad("test", 10) == "      test"
    assert _rfmt(5000, 10) == "   5,000 ₮"
    assert len(_rfmt(5000, 32)) == 32


def test_printer_get_effective_port_from_config(monkeypatch):
    """get_effective_printer_port should use configured port when set."""
    monkeypatch.setattr("printer.IS_WINDOWS", False)

    def mock_get_config(key, default=""):
        if key == "printer_port":
            return "/dev/usb/lp2"
        return default

    monkeypatch.setattr("config.get_config", mock_get_config)

    from printer import get_effective_printer_port
    port = get_effective_printer_port()
    assert port == "/dev/usb/lp2"

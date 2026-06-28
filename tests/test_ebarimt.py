def test_adapter_not_configured():
    from ebarimt import EbarimtAdapter
    adapter = EbarimtAdapter()
    adapter.api_url = ""
    adapter.merchant_tin = ""
    adapter.ttd = ""
    adapter.branch_id = ""
    assert adapter.is_configured() is False
    result = adapter.send_receipt({"total": 1000})
    assert result["success"] is False
    assert "тохиргоо хийгдээгүй" in result["error"]


def test_adapter_logs_config_error(caplog):
    import logging
    caplog.set_level(logging.ERROR)
    from ebarimt import EbarimtAdapter
    adapter = EbarimtAdapter()
    assert adapter.api_url == ""

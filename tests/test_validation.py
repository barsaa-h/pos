"""Tests for input validation."""


def _post(authed_client, csrf_token, data):
    import json as _json
    return authed_client.post('/api/product/create',
        data=_json.dumps(data),
        content_type='application/json',
        headers={'X-CSRF-Token': csrf_token}
    )


def test_create_product_no_name(authed_client, csrf_token):
    resp = _post(authed_client, csrf_token, {
        'name': '', 'price': 100
    })
    assert resp.json['success'] is False


def test_create_product_negative_price(authed_client, csrf_token):
    resp = _post(authed_client, csrf_token, {
        'name': 'Test', 'price': -100
    })
    assert resp.json['success'] is False


def test_create_product_zero_price(authed_client, csrf_token):
    resp = _post(authed_client, csrf_token, {
        'name': 'Test Product', 'price': 0
    })
    assert resp.json['success'] is True


def test_barcode_lookup_empty(client):
    resp = client.post('/api/barcode', json={'barcode': ''})
    assert resp.status_code == 400
    assert resp.json['success'] is False


def test_barcode_lookup_special_chars(client):
    resp = client.post('/api/barcode', json={'barcode': '<script>'})
    assert resp.status_code == 400


def test_checkout_empty_cart(client, csrf_token):
    resp = client.post('/api/checkout',
        json={'items': []},
        headers={'X-CSRF-Token': csrf_token}
    )
    assert resp.json is not None


def test_health_endpoint(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    assert resp.json['status'] == 'ok'


def test_health_deep_endpoint(client):
    resp = client.get('/api/health/deep')
    assert resp.status_code in (200, 503)
    assert 'status' in resp.json

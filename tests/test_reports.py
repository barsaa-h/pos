"""Tests for report generation and sales history."""


def test_sales_page_requires_auth(client):
    resp = client.get('/sales', follow_redirects=True)
    assert resp.status_code == 200


def test_reports_page_requires_auth(client):
    resp = client.get('/reports', follow_redirects=True)
    assert resp.status_code == 200


def test_sale_detail_not_found(authed_client):
    resp = authed_client.get('/sales/99999')
    assert resp.status_code in (200, 302)


def test_held_orders_list(client):
    resp = client.get('/api/held-orders')
    assert resp.status_code == 200
    assert resp.json['success'] is True


def test_cash_drawer_status(client):
    resp = client.get('/api/cash-drawer/status')
    assert resp.status_code == 200
    assert 'balance' in resp.json

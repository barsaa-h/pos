"""
qpay.py — QPay v2 payment gateway integration.

QPay v2 API: https://qpay.mn/
- Auth: POST /auth/token (Basic Auth) → access_token (3600s TTL)
- Invoice: POST /invoice → invoice_id, qr_image (base64), qr_text, urls, expires_at
- Payment check: POST /payment/check → rows[paid_amount, status...]
- Webhook: HMAC-SHA256 signature verification
"""

import logging
import time
import hmac
import hashlib
import base64
import json
import threading
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

TOKEN_REFRESH_MARGIN = 300  # refresh 5 min before expiry


def _get_timeout():
    try:
        from config import get_config
        return int(get_config("qpay_timeout") or 15)
    except Exception:
        return 15


class QPayError(Exception):
    pass


class QPayAuthError(QPayError):
    pass


class QPayAPIError(QPayError):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"QPay API error {status}: {body}")


class QPayClient:
    def __init__(self, client_id, client_secret, base_url):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self._token = None
        self._token_expiry = 0.0
        self._token_lock = threading.Lock()

    def _basic_auth_header(self):
        raw = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(raw.encode()).decode()
        return f"Basic {encoded}"

    def _request(self, method, path, body=None, auth_basic=False, auth_bearer=False):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if auth_basic:
            req.add_header("Authorization", self._basic_auth_header())
        elif auth_bearer:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=_get_timeout()) as resp:
                raw = resp.read().decode()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 401:
                raise QPayAuthError(f"Auth failed: {body}")
            raise QPayAPIError(e.code, body)
        except urllib.error.URLError as e:
            raise QPayError(f"Connection failed: {e.reason}")

    def _get_token(self):
        with self._token_lock:
            now = time.monotonic()
            if self._token and now < self._token_expiry - TOKEN_REFRESH_MARGIN:
                return self._token
            resp = self._request("POST", "/auth/token", auth_basic=True)
            self._token = resp.get("access_token")
            expires_in = resp.get("expires_in", 3600)
            self._token_expiry = now + expires_in
            logger.info("QPay token acquired (expires in %ss)", expires_in)
            return self._token

    def _ensure_token(self):
        if not self._token:
            self._get_token()
        return self._token

    def create_invoice(self, amount, description="",
                       allow_partial=False, allow_exceed=False,
                       callback_url=None, sender_invoice_no=""):
        self._ensure_token()
        body = {
            "invoice_code": "",
            "sender_invoice_no": sender_invoice_no or f"POS{int(time.time())}",
            "amount": int(amount),
            "allow_partial": allow_partial,
            "allow_exceed": allow_exceed,
            "description": description,
            "callback_url": callback_url or "",
        }
        resp = self._request("POST", "/invoice", body=body, auth_bearer=True)
        return {
            "invoice_id": resp.get("invoice_id", ""),
            "qr_image": resp.get("qr_image", ""),
            "qr_text": resp.get("qr_text", ""),
            "urls": resp.get("urls", []),
            "expires_at": resp.get("expires_at", ""),
            "amount": int(amount),
        }

    def check_payment(self, invoice_id):
        self._ensure_token()
        body = {"object_type": "INVOICE", "object_id": invoice_id}
        resp = self._request("POST", "/payment/check", body=body, auth_bearer=True)
        rows = resp.get("rows", [])
        count = resp.get("count", 0)
        try:
            total_paid = int(resp.get("total_amount", 0) or 0)
        except (TypeError, ValueError):
            total_paid = 0
        payment_status = "pending"
        if total_paid > 0:
            payment_status = "paid"
        return {
            "invoice_id": invoice_id,
            "paid_amount": int(total_paid),
            "count": count,
            "rows": rows,
            "payment_status": payment_status,
        }

    @staticmethod
    def verify_webhook(body_bytes, signature, client_secret):
        if not signature:
            return False
        expected = hmac.new(
            client_secret.encode(),
            body_bytes,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower())

    @staticmethod
    def is_configured():
        try:
            from config import get_config
            cid = get_config("qpay_client_id")
            secret = get_config("qpay_client_secret")
            url = get_config("qpay_base_url")
            enabled = get_config("qpay_enabled")
            return bool(enabled == "true" and cid and secret and url)
        except Exception:
            return False

    @classmethod
    def from_config(cls):
        from config import get_config
        return cls(
            client_id=get_config("qpay_client_id"),
            client_secret=get_config("qpay_client_secret"),
            base_url=get_config("qpay_base_url"),
        )

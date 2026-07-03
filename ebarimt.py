"""
ebarimt.py — eBarimt (Mongolian national e-receipt) adapter.

Uses ebarimt-pos-sdk (EbarimtRestClient) to talk to the local POS device
REST API. Falls back gracefully for older setups.
"""

import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


def _get_timeout():
    try:
        from config import get_config
        return int(get_config("ebarimt_timeout") or 5)
    except Exception:
        return 5

BILL_ID_SUFFIXES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _make_bill_id_suffix(sale_id):
    now = datetime.now()
    day_char = BILL_ID_SUFFIXES[now.timetuple().tm_yday % len(BILL_ID_SUFFIXES)]
    sale_char = BILL_ID_SUFFIXES[sale_id % len(BILL_ID_SUFFIXES)]
    return day_char + sale_char


def _mnt_to_decimal(amount):
    return Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class EbarimtAdapter:
    def __init__(self):
        self.api_url = ""
        self.merchant_tin = ""
        self.ttd = ""
        self.branch_id = ""
        self._load_config()

    def _load_config(self):
        try:
            from config import get_config
            self.api_url = get_config("ebarimt_api_url")
            self.merchant_tin = get_config("ebarimt_merchant_tin")
            self.ttd = get_config("ebarimt_ttd")
            self.branch_id = get_config("ebarimt_branch_id")
        except (ImportError, KeyError, ValueError) as e:
            logger.error(f"Failed to load eBarimt config: {e}")

    def is_configured(self):
        return bool(self.api_url and self.merchant_tin and self.ttd and self.branch_id)

    def send_receipt(self, sale_data):
        if not self.is_configured():
            logger.warning("eBarimt not configured — skipping receipt submission.")
            return {
                "success": False,
                "ebarimt_id": "",
                "qr_data": "",
                "lottery": "",
                "error": "eBarimt тохиргоо хийгдээгүй байна"
            }

        try:
            from ebarimt_pos_sdk.clients.rest_client import EbarimtRestClient
            from ebarimt_pos_sdk.settings.rest_client_settings import RestClientSettings
            from ebarimt_pos_sdk.resources.rest.receipt.schema import (
                CreateReceiptRequest, SubReceipt, Item, Payment
            )
            from ebarimt_pos_sdk.resources.enum import (
                PaymentCode, TaxType, ReceiptType, PaymentStatus
            )
        except ImportError:
            logger.error("ebarimt-pos-sdk not installed.")
            return {
                "success": False,
                "ebarimt_id": "",
                "qr_data": "",
                "lottery": "",
                "error": "ebarimt-pos-sdk суулгагдаагүй байна"
            }

        customer_tin = sale_data.get("customer_tin", "").strip()

        total = _mnt_to_decimal(sale_data.get("total", 0))
        total_vat = (total * Decimal("10") / Decimal("110")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) if total > 0 else Decimal("0")

        items = []
        for item in sale_data.get("items", []):
            qty = _mnt_to_decimal(item.get("quantity", 1))
            unit_price = _mnt_to_decimal(item.get("unit_price", 0))
            subtotal = _mnt_to_decimal(item.get("subtotal", 0))
            items.append(Item(
                name=item.get("product_name", ""),
                measure_unit=item.get("unit", "ш"),
                qty=qty,
                unit_price=unit_price,
                total_amount=subtotal,
                bar_code=str(item.get("barcode") or ""),
            ))

        sub_receipt = SubReceipt(
            total_amount=total,
            tax_type=TaxType.VAT_ABLE,
            merchant_tin=self.merchant_tin,
            items=items,
            total_vat=total_vat,
        )

        if customer_tin:
            sub_receipt.customer_tin = customer_tin

        payment_type = sale_data.get("payment_type", "cash")
        payments = []
        if payment_type == "cash":
            payments.append(Payment(
                code=PaymentCode.CASH,
                status=PaymentStatus.PAID,
                paid_amount=total,
            ))
        elif payment_type in ("card", "qr"):
            payments.append(Payment(
                code=PaymentCode.PAYMENT_CARD,
                status=PaymentStatus.PAID,
                paid_amount=total,
            ))
        elif payment_type == "split":
            cash_amt = _mnt_to_decimal(sale_data.get("cash_amount", 0))
            card_amt = _mnt_to_decimal(sale_data.get("card_amount", 0))
            if cash_amt > 0:
                payments.append(Payment(
                    code=PaymentCode.CASH,
                    status=PaymentStatus.PAID,
                    paid_amount=cash_amt,
                ))
            if card_amt > 0:
                payments.append(Payment(
                    code=PaymentCode.PAYMENT_CARD,
                    status=PaymentStatus.PAID,
                    paid_amount=card_amt,
                ))

        bill_id_suffix = _make_bill_id_suffix(sale_data.get("id", 0))
        idempotency_key = f"pos-{sale_data.get('id', 0)}"

        receipt_type = ReceiptType.B2B_RECEIPT if customer_tin else ReceiptType.B2C_RECEIPT

        request = CreateReceiptRequest(
            branch_no=self.branch_id,
            total_amount=total,
            merchant_tin=self.merchant_tin,
            pos_no=self.ttd,
            type=receipt_type,
            total_vat=total_vat,
            bill_id_suffix=bill_id_suffix,
            receipts=[sub_receipt],
            payments=payments,
            data={"idempotency_key": idempotency_key},
        )

        if customer_tin:
            request.customer_tin = customer_tin

        client_settings = RestClientSettings(base_url=self.api_url, timeout_s=_get_timeout())
        client = EbarimtRestClient(settings=client_settings)
        try:
            response = client.receipt.create_receipt(request)

            if response.status == "SUCCESS":
                return {
                    "success": True,
                    "ebarimt_id": response.id,
                    "qr_data": response.qr_data,
                    "lottery": response.lottery,
                    "error": ""
                }
            else:
                return {
                    "success": False,
                    "ebarimt_id": response.id or "",
                    "qr_data": response.qr_data or "",
                    "lottery": response.lottery or "",
                    "error": f"eBarimt статус: {response.status}"
                }
        except Exception as e:
            logger.error(f"eBarimt API error: {e}")
            return {
                "success": False,
                "ebarimt_id": "",
                "qr_data": "",
                "lottery": "",
                "error": f"eBarimt API алдаа: {e}"
            }

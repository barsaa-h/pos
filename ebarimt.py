"""
ebarimt.py — eBarimt (Mongolian national e-receipt) adapter.

Uses ebarimt-pos-sdk (EbarimtRestClient) to talk to the local POS device
REST API. Falls back gracefully for older setups.
"""

import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5

BILL_ID_SUFFIXES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _get_bill_id_suffix():
    day = datetime.now().timetuple().tm_yday
    return BILL_ID_SUFFIXES[day % len(BILL_ID_SUFFIXES)]


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
        except Exception as e:
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

        total = _mnt_to_decimal(sale_data.get("total", 0))
        total_vat = _mnt_to_decimal(total // 11) if total > 0 else Decimal("0")

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
                bar_code=str(item.get("barcode", "")),
            ))

        sub_receipt = SubReceipt(
            total_amount=total,
            tax_type=TaxType.VAT_ABLE,
            merchant_tin=self.merchant_tin,
            items=items,
            total_vat=total_vat,
        )

        payment_type = sale_data.get("payment_type", "cash")
        payments = []
        if payment_type == "cash":
            payments.append(Payment(
                code=PaymentCode.CASH,
                status=PaymentStatus.PAID,
                paid_amount=total,
            ))
        elif payment_type == "card":
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

        bill_id_suffix = _get_bill_id_suffix()

        request = CreateReceiptRequest(
            branch_no=self.branch_id,
            total_amount=total,
            merchant_tin=self.merchant_tin,
            pos_no=self.ttd,
            type=ReceiptType.B2C_RECEIPT,
            total_vat=total_vat,
            bill_id_suffix=bill_id_suffix,
            receipts=[sub_receipt],
            payments=payments,
        )

        client_settings = RestClientSettings(base_url=self.api_url, timeout_s=REQUEST_TIMEOUT)
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

    def retry_pending(self, sale_ids=None):
        if not self.is_configured():
            logger.warning("eBarimt not configured — skipping retry.")
            return []

        try:
            from database import get_pending_ebarimt_sales, update_sale_ebarimt
        except ImportError:
            logger.error("Cannot import database module for eBarimt retry.")
            return []

        if sale_ids:
            all_pending = get_pending_ebarimt_sales()
            pending = [s for s in all_pending if s["id"] in sale_ids]
        else:
            pending = get_pending_ebarimt_sales()

        if not pending:
            logger.info("No pending eBarimt sales to retry.")
            return []

        results = []
        for sale in pending:
            try:
                result = self.send_receipt(sale)
                if result["success"]:
                    update_sale_ebarimt(
                        sale["id"],
                        ebarimt_id=result.get("ebarimt_id", ""),
                        ebarimt_qr=result.get("qr_data", ""),
                        lottery=result.get("lottery", ""),
                        status="sent"
                    )
                results.append({
                    "sale_id": sale["id"],
                    "success": result["success"],
                    "ebarimt_id": result.get("ebarimt_id", ""),
                    "lottery": result.get("lottery", ""),
                    "error": result.get("error", "")
                })
            except Exception as e:
                logger.error(f"eBarimt retry error for sale #{sale['id']}: {e}")
                results.append({
                    "sale_id": sale["id"],
                    "success": False,
                    "ebarimt_id": "",
                    "lottery": "",
                    "error": str(e)
                })

        return results

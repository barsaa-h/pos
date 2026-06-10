"""
printer.py — Cross-platform thermal receipt printer (ESC/POS).

Supports:
  - Linux:   /dev/usb/lp0, /dev/usb/lp1... (auto-detect)
  - Windows: COM1, COM2... (auto-detect via serial.tools.list_ports)

Falls back gracefully when printer is unavailable.
"""

import logging
import os
import platform
from datetime import datetime

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"

try:
    from escpos.printer import File
    ESCPOS_AVAILABLE = True
except ImportError:
    ESCPOS_AVAILABLE = False
    logger.warning("python-escpos not installed. Receipt printing disabled.")

SERIAL_AVAILABLE = False
if IS_WINDOWS:
    try:
        import serial.tools.list_ports
        SERIAL_AVAILABLE = True
    except ImportError:
        logger.warning("pyserial not installed. Windows COM port detection disabled.")


def detect_printer_port():
    """Auto-detect the most likely thermal printer port for the current OS."""
    if IS_WINDOWS:
        return _detect_windows_port()
    return _detect_linux_port()


def _detect_windows_port():
    if not SERIAL_AVAILABLE:
        return "COM3"
    try:
        ports = list(serial.tools.list_ports.comports())
        # Look for common thermal printer USB VID/PID or descriptions
        for p in ports:
            desc = (p.description or "").lower()
            if any(kw in desc for kw in ("thermal", "receipt", "esc/pos", "pos", "epson", "tm-", "print")):
                logger.info(f"Windows printer detected: {p.device} ({p.description})")
                return p.device
        # Fallback: pick the last available COM port (often USB printer)
        if ports:
            last = ports[-1].device
            logger.info(f"Windows printer fallback: {last}")
            return last
    except Exception as e:
        logger.warning(f"Windows COM port scan failed: {e}")
    return "COM3"


def _detect_linux_port():
    """Scan /dev for USB printer device files."""
    for i in range(10):
        path = f"/dev/usb/lp{i}"
        if os.path.exists(path):
            logger.info(f"Linux printer detected: {path}")
            return path
    # Fallback: check common serial paths
    for path in ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0"]:
        if os.path.exists(path):
            logger.info(f"Linux printer serial fallback: {path}")
            return path
    return "/dev/usb/lp0"


def get_effective_printer_port():
    """Get printer port from config, falling back to auto-detect, then OS default."""
    try:
        from config import get_config
        configured = get_config("printer_port")
        if configured and configured.strip() and configured != "/dev/usb/lp0":
            return configured.strip()
    except Exception:
        pass
    try:
        return detect_printer_port()
    except Exception:
        return "COM3" if IS_WINDOWS else "/dev/usb/lp0"


def print_receipt(sale_data, store_info):
    if not ESCPOS_AVAILABLE:
        return {"success": False, "error": "python-escpos суулгаагүй байна."}

    try:
        from config import get_config
        printer_port = get_effective_printer_port()
        receipt_width = int(get_config("receipt_width") or 32)
    except Exception:
        printer_port = "COM3" if IS_WINDOWS else "/dev/usb/lp0"
        receipt_width = 32

    try:
        printer = File(printer_port)

        _print_header(printer, store_info, sale_data, receipt_width)
        _print_items(printer, sale_data, receipt_width)
        _print_totals(printer, sale_data, receipt_width)
        _print_payment(printer, sale_data, receipt_width)
        _print_ebarimt(printer, sale_data)
        _print_lottery(printer, sale_data)
        _print_footer(printer, receipt_width)

        printer.cut()

        payment_type = sale_data.get("payment_type", "")
        if payment_type in ("cash", "split"):
            _cash_drawer_kick(printer)

        logger.info(f"Receipt printed for sale #{sale_data.get('id')} on {printer_port}")
        return {"success": True, "error": ""}

    except FileNotFoundError:
        error_msg = f"Хэвлэгч олдсонгүй: {printer_port}"
        logger.warning(error_msg)
        return {"success": False, "error": error_msg}

    except PermissionError:
        error_msg = f"Хэвлэгчид хандах эрх байхгүй: {printer_port}"
        logger.warning(error_msg)
        return {"success": False, "error": error_msg}

    except OSError as e:
        error_msg = f"Хэвлэгчийн холболтын алдаа: {printer_port} — {e}"
        logger.warning(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Хэвлэх алдаа: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def _print_header(printer, store_info, sale_data, width):
    printer.set(align="center", bold=True, width=2, height=2)
    printer.text(store_info.get("name", "Дэлгүүр") + "\n")
    printer.set(align="center", bold=False, width=1, height=1)
    address = store_info.get("address", "")
    if address:
        printer.text(address + "\n")
    phone = store_info.get("phone", "")
    if phone:
        printer.text("Утас: " + phone + "\n")
    now = datetime.now()
    printer.text(now.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    cashier_name = sale_data.get("cashier_name", "")
    if cashier_name:
        printer.text("Кассчин: " + cashier_name + "\n")
    payment_type = sale_data.get("payment_type", "cash")
    if payment_type == "return":
        printer.set(bold=True)
        printer.text("!!! БУЦААЛТ !!!\n")
        printer.set(bold=False)
    printer.text("Борлуулалт #:" + str(sale_data.get("id", "")) + "\n")
    printer.text("-" * width + "\n")


def _print_items(printer, sale_data, width):
    items = sale_data.get("items", [])
    for item in items:
        name = item.get("product_name", "Бараа")
        qty = item.get("quantity", 1)
        unit_price = item.get("unit_price", 0)
        subtotal = item.get("subtotal", 0)
        name_width = width - 14
        if len(name) > name_width:
            name = name[:name_width - 3] + "..."
        printer.text(name + "\n")
        qty_str = str(int(qty)) if qty == int(qty) else str(qty)
        line = f"  {qty_str} x {_fmt(unit_price)} = {_fmt(subtotal)}"
        printer.text(line + "\n")
    printer.text("-" * width + "\n")


def _print_totals(printer, sale_data, width):
    try:
        from config import get_config
        show_vat = get_config("show_vat_on_receipt") == "true"
    except Exception:
        show_vat = False
    total = sale_data.get("total", 0)
    printer.text(f"Нийт дүн: {_rpad(_fmt(total), width)}\n")
    if show_vat:
        vat = total // 11 if total > 0 else 0
        printer.text(f"НӨАТ (10%): {_rpad(_fmt(vat), width)}\n")
    printer.set(bold=True)
    printer.text(f"НИЙТ: {_rpad(_fmt(total), width)}\n")
    printer.set(bold=False)


def _print_payment(printer, sale_data, width):
    payment_type = sale_data.get("payment_type", "cash")
    if payment_type == "return":
        printer.text(f"БУЦААЛТ: {_rpad(_fmt(abs(sale_data.get('total', 0))), width)}\n")
    elif payment_type == "cash":
        printer.text(f"Төлбөр: Бэлэн\n")
        cash_given = sale_data.get("cash_given", 0)
        change_given = sale_data.get("change_given", 0)
        printer.text(f"  Өгсөн: {_rpad(_fmt(cash_given), width)}\n")
        if change_given > 0:
            printer.text(f"  Буцаалт: {_rpad(_fmt(change_given), width)}\n")
    elif payment_type == "card":
        printer.text(f"Төлбөр: Карт\n")
        printer.text(f"  Карт: {_rpad(_fmt(sale_data.get('card_amount', 0)), width)}\n")
    elif payment_type == "qr":
        printer.text(f"Төлбөр: QR\n")
        printer.text(f"  QR: {_rpad(_fmt(sale_data.get('card_amount', total if 'total' in sale_data else 0)), width)}\n")
    elif payment_type == "split":
        printer.text(f"Төлбөр: Холимог\n")
        printer.text(f"  Карт: {_rpad(_fmt(sale_data.get('card_amount', 0)), width)}\n")
        printer.text(f"  Бэлэн: {_rpad(_fmt(sale_data.get('cash_amount', 0)), width)}\n")
    printer.text("-" * width + "\n")


def _print_ebarimt(printer, sale_data):
    ebarimt_status = sale_data.get("ebarimt_status", "pending")
    ebarimt_qr = sale_data.get("ebarimt_qr", "")
    if ebarimt_status == "sent" and ebarimt_qr:
        try:
            printer.qr(ebarimt_qr, size=4)
            printer.text("eBarimt: Илгээгдлээ\n")
        except Exception:
            printer.text("eBarimt: Илгээгдлээ\n")
            printer.text(f"ID: {sale_data.get('ebarimt_id', '')}\n")
    elif ebarimt_status == "skipped":
        printer.text("eBarimt: Тохиргоо хийгдээгүй\n")
    elif ebarimt_status == "failed":
        printer.text("eBarimt: Алдаа — Дахин оролдоно\n")
    else:
        printer.text("eBarimt: Дахин оролдоно\n")


def _print_lottery(printer, sale_data):
    lottery = sale_data.get("ebarimt_lottery", "")
    if lottery:
        printer.set(align="center")
        printer.text("\nСугалаа: " + lottery + "\n")


def _cash_drawer_kick(printer):
    try:
        printer.pulse()
        logger.info("Cash drawer kicked")
    except Exception as e:
        logger.warning(f"Cash drawer kick failed (non-fatal): {e}")


def _print_footer(printer, width):
    try:
        from config import get_config
        footer = get_config("receipt_footer")
    except Exception:
        footer = "Баярлалаа! Дахин үйлчлүүлнэ үү."
    if not footer:
        footer = "Баярлалаа!"
    printer.set(align="center")
    printer.text("\n" + footer + "\n\n")
    printer.text("\n\n\n")


def _fmt(amount):
    return f"{int(amount):,} ₮"


def _rpad(text, width=32):
    return text.rjust(width)

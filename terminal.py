"""
terminal.py — PAX A930 TCP/IP terminal integration.

The PAX A930 is an Android payment terminal. It must be on the same LAN
as the POS computer. Enable TCP Server mode on the PAX (usually through
the bank's payment app or QuickPOS settings). Default port: 10009.

Supported protocols:
  1. PAX native TCP (STX/ETX/LRC framing, FS-delimited fields) — default
  2. PosLink text key=value — fallback for some bank apps
"""

import logging
import socket
import time
import threading

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 90            # customer needs time to tap card
CONNECT_TIMEOUT = 5             # just for the TCP handshake
RECONNECT_DELAY = 2
MAX_RECONNECT_ATTEMPTS = 3

STX = 0x02
ETX = 0x03
FS = 0x1C

# Active payment tracking for cancellation support
_active_sockets: dict = {}
_active_sockets_lock = threading.Lock()


def _register_socket(invoice_no: str, sock) -> None:
    with _active_sockets_lock:
        _active_sockets[invoice_no] = sock


def _unregister_socket(invoice_no: str) -> None:
    with _active_sockets_lock:
        _active_sockets.pop(invoice_no, None)


def cancel_payment(invoice_no: str) -> bool:
    with _active_sockets_lock:
        sock = _active_sockets.pop(invoice_no, None)
        if sock:
            try:
                sock.close()
                logger.info(f"Payment cancelled: {invoice_no}")
                return True
            except Exception as e:
                logger.warning(f"Error closing socket for {invoice_no}: {e}")
    return False


def is_terminal_configured():
    try:
        from config import get_config
        return get_config("terminal_enabled") == "true" and bool(get_config("terminal_ip"))
    except Exception:
        return False


def _calc_lrc(data: bytes) -> int:
    lrc = 0
    for b in data:
        lrc ^= b
    return lrc


def _build_pax_request(amount: int, invoice_no: str = "") -> bytes:
    ref = invoice_no or f"POS{int(time.time())}"
    body = f"\x1c00\x1cSALE\x1c{amount}\x1c{ref}\x1c"
    msg = bytes([STX]) + body.encode("ascii", errors="replace") + bytes([ETX])
    lrc = _calc_lrc(body.encode("ascii", errors="replace"))
    msg += bytes([lrc])
    return msg


def _parse_pax_response(data: bytes, amount: int) -> dict:
    if not data or data[0] != STX:
        return None

    etx_pos = data.find(bytes([ETX]))
    if etx_pos == -1:
        return None

    body = data[1:etx_pos]
    received_lrc = data[etx_pos + 1] if len(data) > etx_pos + 1 else None

    expected_lrc = _calc_lrc(body)
    if received_lrc is not None and received_lrc != expected_lrc:
        logger.warning("PAX LRC mismatch: got %d, expected %d", received_lrc, expected_lrc)

    raw = body.decode("ascii", errors="replace")
    fields = raw.split("\x1c") if "\x1c" in raw else raw.split("|")

    result = {
        "success": False,
        "transaction_id": "",
        "error": "Хариултын формат тохирохгүй",
    }

    if len(fields) >= 3:
        cmd = fields[1].upper() if len(fields) > 1 else ""
        resp_code = fields[3].strip() if len(fields) > 3 else ""
        txn_id = fields[4].strip() if len(fields) > 4 else fields[2].strip()

        approved = resp_code in ("00", "0", "OK", "APPROVED", "TRUE", "SUCCESS")
        if cmd == "SALE" and approved:
            result["success"] = True
            result["transaction_id"] = txn_id
            result["amount"] = amount
        else:
            err_msg = fields[5].strip() if len(fields) > 5 else ""
            result["error"] = err_msg or f"Терминал татгалзсан (код: {resp_code})"
            result["transaction_id"] = txn_id

    return result


def _build_poslink_payment(amount: int, invoice_no: str = "") -> bytes:
    ref = invoice_no or f"POS{int(time.time())}"
    msg = (
        f"AMOUNT={amount}\r\n"
        f"INVOICE={ref}\r\n"
        f"TIMEOUT={REQUEST_TIMEOUT}\r\n"
    )
    return msg.encode()


def _parse_poslink_response(data: bytes, amount: int) -> dict:
    parsed = {}
    for line in data.decode(errors="replace").strip().split("\r\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            parsed[k.strip().upper()] = v.strip()

    status = parsed.get("STATUS", parsed.get("RESPONSE", "")).upper()
    txn_id = parsed.get("TXNID", parsed.get("TRANSACTIONID", ""))
    result_code = parsed.get("RESULT", parsed.get("CODE", ""))

    if status in ("OK", "APPROVED", "00") or result_code == "00":
        return {"success": True, "transaction_id": txn_id, "amount": amount}
    else:
        error = parsed.get("ERROR", parsed.get("MESSAGE", "")) or f"Код: {result_code}"
        return {"success": False, "error": error, "transaction_id": txn_id}


def send_payment(amount: int, invoice_no: str = ""):
    """Send payment request to PAX A930 terminal.

    Tries PAX native TCP protocol first, falls back to PosLink text protocol.

    Returns:
        dict with keys: success (bool), transaction_id (str), error (str)
    """
    try:
        from config import get_config
        ip = get_config("terminal_ip")
        port = int(get_config("terminal_port") or "10009")
    except Exception as e:
        logger.error("Terminal config error: %s", e)
        return {"success": False, "error": "Терминал тохиргоо буруу"}

    if not ip:
        logger.warning("No terminal IP configured")
        return {"success": False, "error": "Терминал хаяг тохируулаагүй"}

    logger.info("Connecting to PAX terminal at %s:%s (amount=%s)", ip, port, amount)

    sock = None
    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((ip, port))
            logger.info("TCP connected to %s:%s (attempt %d)", ip, port, attempt)
            break
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            logger.warning("Connection attempt %d failed: %s", attempt, e)
            if sock:
                sock.close()
                sock = None
            if attempt < MAX_RECONNECT_ATTEMPTS:
                time.sleep(RECONNECT_DELAY)
            continue

    if sock is None:
        return {"success": False, "error": f"Терминал холбогдохгүй байна ({ip}:{port})"}

    _register_socket(invoice_no, sock)
    try:
        sock.settimeout(REQUEST_TIMEOUT)

        request = _build_pax_request(amount, invoice_no)
        logger.info("Sending PAX request (%d bytes)", len(request))
        sock.sendall(request)

        raw_response = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw_response += chunk
                if ETX in chunk:
                    break
            except socket.timeout:
                break

        _unregister_socket(invoice_no)
        sock.close()
        sock = None

        if not raw_response:
            return {"success": False, "error": "Терминал хариу өгөөгүй"}

        result = _parse_pax_response(raw_response, amount)
        if result is not None and result.get("success"):
            logger.info("PAX payment OK: %s", result.get("transaction_id", ""))
            return result

        logger.info("PAX protocol failed, trying PosLink fallback...")
        try:
            sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock2.settimeout(CONNECT_TIMEOUT)
            sock2.connect((ip, port))
            sock2.settimeout(REQUEST_TIMEOUT)

            poslink_req = _build_poslink_payment(amount, invoice_no)
            sock2.sendall(poslink_req)
            time.sleep(0.3)

            pl_response = b""
            while True:
                try:
                    chunk = sock2.recv(4096)
                    if not chunk:
                        break
                    pl_response += chunk
                except socket.timeout:
                    break
            sock2.close()

            if pl_response:
                pl_result = _parse_poslink_response(pl_response, amount)
                if pl_result.get("success"):
                    logger.info("PosLink fallback OK: %s", pl_result.get("transaction_id", ""))
                    return pl_result
                return pl_result
        except Exception as e2:
            logger.warning("PosLink fallback also failed: %s", e2)

        return result or {"success": False, "error": "Терминал хариу өгөөгүй"}

    except socket.timeout:
        logger.error("Terminal timeout (%ss)", REQUEST_TIMEOUT)
        return {"success": False, "error": "Терминал хариу өгөөгүй (хугацаа дууссан)"}
    except ConnectionRefusedError:
        logger.error("Terminal connection refused")
        return {"success": False, "error": "Терминал холбогдохоос татгалзсан"}
    except OSError as e:
        logger.error("Terminal socket error: %s", e)
        return {"success": False, "error": f"Терминал холболтын алдаа: {e}"}
    except Exception as e:
        logger.error("Terminal unexpected error: %s", e)
        return {"success": False, "error": f"Терминал алдаа: {e}"}
    finally:
        _unregister_socket(invoice_no)
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def test_connection():
    """Test TCP connectivity to the configured terminal without sending a payment."""
    try:
        from config import get_config
        ip = get_config("terminal_ip")
        port = int(get_config("terminal_port") or "10009")
    except Exception as e:
        return {"success": False, "error": f"Тохиргоо буруу: {e}"}

    if not ip:
        return {"success": False, "error": "IP хаяг тохируулаагүй"}

    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((ip, port))

            sock.settimeout(5)
            banner = sock.recv(1024)
            sock.close()

            info = f"холбогдлоо"
            if banner:
                hexdump = " ".join(f"{b:02x}" for b in banner[:32])
                info += f", эхний өгөгдөл: {hexdump}"

            logger.info("Terminal test OK at %s:%s — %s", ip, port, info)
            return {"success": True, "message": f"Холболт амжилттай ({info})", "ip": ip, "port": port}
        except socket.timeout:
            if attempt < MAX_RECONNECT_ATTEMPTS:
                time.sleep(RECONNECT_DELAY)
                continue
            return {"success": False, "error": f"Холбогдох хугацаа дууссан ({ip}:{port})"}
        except ConnectionRefusedError:
            return {"success": False, "error": f"Холболт татгалзсан — PAX дээр TCP Server идэвхжээгүй байна ({ip}:{port})"}
        except OSError as e:
            if attempt < MAX_RECONNECT_ATTEMPTS:
                time.sleep(RECONNECT_DELAY)
                continue
            return {"success": False, "error": f"Холболтын алдаа: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Алдаа: {e}"}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    return {"success": False, "error": f"Холбогдож чадсангүй ({ip}:{port})"}

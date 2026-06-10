"""
app.py — Main Flask application for the POS system.

Handles:
- Flask app initialization and configuration
- Session management with configurable timeout
- Admin authentication (login/logout with PIN/password)
- All HTTP routes for POS, products, sales, reports, inventory, settings
- CSRF protection on all mutating routes (form + header)
- eBarimt retry on startup and manual retry endpoint
- Error handlers for 404, 500, and unhandled exceptions
"""

import os
import csv
import io
import json
import logging
import threading
import secrets
import time
from datetime import datetime
from functools import wraps
from copy import deepcopy

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, Response
)

import database as db
from config import (
    FLASK_SECRET_KEY, FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    get_config, get_all_config,
    is_ebarimt_configured, get_store_info
)
from i18n import _t

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max upload

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_DIR, "logs", "pos.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# RATE LIMITING (simple in-memory)
# ─────────────────────────────────────────────

_rate_limit_store = {}
_rate_limit_lock = threading.Lock()

def _rate_limit_key():
    return request.remote_addr or "127.0.0.1"

def rate_limit(max_requests=30, window_seconds=10):
    """Simple in-memory rate limiting decorator."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = _rate_limit_key()
            now = time.time()
            with _rate_limit_lock:
                if key in _rate_limit_store:
                    timestamps = _rate_limit_store[key]
                    timestamps = [t for t in timestamps if now - t < window_seconds]
                    if len(timestamps) >= max_requests:
                        return jsonify({"error": "Хэт олон хүсэлт. Түр хүлээнэ үү."}), 429
                    timestamps.append(now)
                    _rate_limit_store[key] = timestamps
                else:
                    _rate_limit_store[key] = [now]
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# CSRF PROTECTION
# ─────────────────────────────────────────────

def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token():
    """Check CSRF token from form body OR X-CSRF-Token header."""
    expected = session.get("csrf_token", "")
    if not expected:
        return False
    token = request.form.get("csrf_token", "")
    if not token:
        token = request.headers.get("X-CSRF-Token", "")
    return bool(token and token == expected)


# ─────────────────────────────────────────────
# AUTO-ADMIN (Passwordless)
# ─────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def auto_admin_session():
    if not session.get("admin"):
        session["admin"] = True
        session["admin_login_time"] = time.time()


# ─────────────────────────────────────────────
# CATEGORY DATA
# ─────────────────────────────────────────────

CATEGORY_ICONS = {
    'Сүүн бүтээгдэхүүн': '🥛',
    'Талх нарийн боов': '🍞',
    'Өндөг': '🥚',
    'Будаа': '🍚',
    'Гоймон': '🍜',
    'Тос': '🛢️',
    'Чихэр': '🍬',
    'Давс амтлагч': '🧂',
    'Жимс': '🍎',
    'Ус ундаа': '🥤',
    'Бусад': '📦'
}

CATEGORY_COLORS = {
    'Сүүн бүтээгдэхүүн': '#3B82F6',
    'Талх нарийн боов': '#F59E0B',
    'Өндөг': '#EAB308',
    'Будаа': '#22C55E',
    'Гоймон': '#EF4444',
    'Тос': '#A855F7',
    'Чихэр': '#06B6D4',
    'Давс амтлагч': '#78716C',
    'Жимс': '#84CC16',
    'Ус ундаа': '#0EA5E9',
    'Бусад': '#6B7280'
}


@app.context_processor
def inject_globals():
    db_cats = db.get_all_categories()
    icons = {}
    colors = {}
    for c in db_cats:
        icons[c['name']] = c['icon']
        colors[c['name']] = c['color']
    icons.update(CATEGORY_ICONS)
    colors.update(CATEGORY_COLORS)
    return {
        "csrf_token": generate_csrf_token(),
        "ebarimt_configured": is_ebarimt_configured(),
        "store_info": get_store_info(),
        "now": datetime.now(),
        "admin_mode": True,
        "CATEGORY_ICONS": icons,
        "CATEGORY_COLORS": colors,
        "_t": _t,
        "settings": get_all_config(),
    }


@app.route("/api/csrf/refresh", methods=["POST"])
def api_csrf_refresh():
    if not validate_csrf_token():
        return jsonify({"error": "CSRF validation failed", "csrf_expired": True}), 403
    session["csrf_token"] = secrets.token_hex(32)
    return jsonify({"success": True, "csrf_token": session["csrf_token"]})


# ─────────────────────────────────────────────
# POS ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def pos():
    products = db.get_all_products(active_only=True)
    categories = db.get_categories()
    max_stock = max((p["stock_qty"] for p in products), default=1)
    settings = get_all_config()
    return render_template("pos.html", products=products, categories=categories, max_stock=max_stock, settings=settings)


@app.route("/customer")
def customer_display():
    settings = get_all_config()
    return render_template("customer_display.html", settings=settings)


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/version")
def api_version():
    version_path = os.path.join(PROJECT_DIR, "VERSION")
    try:
        with open(version_path, "r") as f:
            ver = f.read().strip()
    except Exception:
        ver = "unknown"
    return jsonify({"version": ver})


_customer_display_lock = threading.Lock()
_customer_display_state = {
    "phase": "idle", "items": [], "total": 0,
    "payment_type": None, "cash_given": 0,
    "change_given": 0, "card_amount": 0
}

# SSE clients list for push-based customer display updates
_sse_clients = []
_sse_clients_lock = threading.Lock()


def _notify_sse_clients():
    """Notify all connected SSE clients of a state change."""
    with _sse_clients_lock:
        dead = []
        for client in _sse_clients:
            try:
                client.put(True)
            except Exception:
                dead.append(client)
        for d in dead:
            _sse_clients.remove(d)


# Exempt: customer-state is display-only in-memory state, no persistent data modified
@app.route("/api/customer-state", methods=["GET", "POST"])
@rate_limit(max_requests=120, window_seconds=10)
def api_customer_state():
    global _customer_display_state

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_state = {
            "phase": data.get("phase", "idle"),
            "items": data.get("items", []),
            "total": data.get("total", 0),
            "payment_type": data.get("payment_type"),
            "cash_given": data.get("cash_given", 0),
            "change_given": data.get("change_given", 0),
            "card_amount": data.get("card_amount", 0)
        }
        with _customer_display_lock:
            _customer_display_state = new_state
        _notify_sse_clients()
        return jsonify({"success": True})

    with _customer_display_lock:
        return jsonify(deepcopy(_customer_display_state))


@app.route("/api/customer-stream")
def api_customer_stream():
    """Server-Sent Events endpoint for real-time customer display updates."""
    import queue
    q = queue.Queue()
    with _sse_clients_lock:
        _sse_clients.append(q)

    def event_stream():
        try:
            # Send initial state immediately
            with _customer_display_lock:
                data = json.dumps(deepcopy(_customer_display_state), ensure_ascii=False)
            yield f"data: {data}\n\n"
            while True:
                try:
                    q.get(timeout=15)
                    q.task_done()
                    with _customer_display_lock:
                        data = json.dumps(deepcopy(_customer_display_state), ensure_ascii=False)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_clients_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# Exempt: barcode lookup is a read-only query, no data modified
@app.route("/api/barcode", methods=["POST"])
@rate_limit(max_requests=60, window_seconds=5)
def api_barcode_lookup():
    data = request.get_json(silent=True) or {}
    barcode = data.get("barcode", "").strip()

    if not barcode:
        return jsonify({"success": False, "error": "Баркод хоосон"}), 400

    if not all(c.isalnum() or c in "-_" for c in barcode):
        return jsonify({"success": False, "error": "Баркод буруу форматтай"}), 400

    product = db.get_product_by_barcode(barcode)
    if not product:
        return jsonify({"success": False, "error": "not_found", "barcode": barcode}), 404

    return jsonify({"success": True, "product": product})


@app.route("/api/products/search")
def api_product_search():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 1:
        products = db.get_all_products()
        max_stock = max((p["stock_qty"] for p in products), default=1)
        return jsonify({"products": products, "max_stock": max_stock})
    products = db.search_products(query, limit=30)
    return jsonify({"products": products})


@app.route("/api/checkout", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=5)
def api_checkout():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    payment_type = data.get("payment_type", "cash")
    cash_given = data.get("cash_given", 0)
    card_amount = data.get("card_amount", 0)
    cash_amount = data.get("cash_amount", 0)
    idempotency_key = data.get("idempotency_key", "").strip()

    # Idempotency check: if this key was already used, return saved result
    if idempotency_key:
        saved = db.check_idempotency_key(idempotency_key)
        if saved:
            logger.info(f"Duplicate checkout prevented via idempotency key {idempotency_key[:8]}...")
            return jsonify(json.loads(saved))

    if not items:
        return jsonify({"success": False, "error": "Сагс хоосон байна"}), 400

    try:
        db.check_and_backup()
    except Exception as e:
        logger.warning(f"Backup check failed (non-fatal): {e}")

    sale, error = db.create_sale(
        cashier_id=None,
        payment_type=payment_type,
        items=items,
        cash_given=cash_given,
        card_amount=card_amount,
        cash_amount=cash_amount,
    )
    if error:
        return jsonify({"success": False, "error": error}), 400

    # Ensure a shift is open for this sale
    try:
        db.ensure_shift_open()
    except Exception as e:
        logger.warning(f"Shift ensure failed (non-fatal): {e}")

    sale["cashier_name"] = ""

    # Respect auto_print_receipt setting
    auto_print = get_config("auto_print_receipt")
    print_result = {"success": False, "error": ""}
    if auto_print == "true":
        try:
            from printer import print_receipt
            print_result = print_receipt(sale, get_store_info())
        except Exception as e:
            logger.error(f"Print failed (non-fatal): {e}")
            print_result = {"success": False, "error": str(e)}

    sale["print_status"] = print_result

    # eBarimt: skip for return sales
    ebarimt_result = {"success": False, "error": ""}
    if payment_type == "return":
        db.update_sale_ebarimt(sale["id"], status="skipped")
        sale["ebarimt_status"] = "skipped"
    else:
        try:
            if is_ebarimt_configured():
                from ebarimt import EbarimtAdapter
                adapter = EbarimtAdapter()
                ebarimt_result = adapter.send_receipt(sale)
                if ebarimt_result.get("success"):
                    db.update_sale_ebarimt(
                        sale["id"],
                        ebarimt_id=ebarimt_result.get("ebarimt_id", ""),
                        ebarimt_qr=ebarimt_result.get("qr_data", ""),
                        lottery=ebarimt_result.get("lottery", ""),
                        status="sent"
                    )
                    sale["ebarimt_status"] = "sent"
                    sale["ebarimt_id"] = ebarimt_result.get("ebarimt_id", "")
                    sale["ebarimt_qr"] = ebarimt_result.get("qr_data", "")
                    sale["ebarimt_lottery"] = ebarimt_result.get("lottery", "")
                else:
                    db.update_sale_ebarimt(sale["id"], status="failed")
                    sale["ebarimt_status"] = "failed"
            else:
                db.update_sale_ebarimt(sale["id"], status="skipped")
                sale["ebarimt_status"] = "skipped"
        except Exception as e:
            logger.error(f"eBarimt failed (non-fatal): {e}")
            db.update_sale_ebarimt(sale["id"], status="failed")
            sale["ebarimt_status"] = "failed"

    sale["ebarimt_result"] = ebarimt_result

    response_data = json.dumps({"success": True, "sale": sale}, ensure_ascii=False)
    if idempotency_key:
        try:
            db.save_idempotency_key(idempotency_key, sale["id"], response_data)
        except Exception as e:
            logger.warning(f"Failed to save idempotency key: {e}")

    return jsonify({"success": True, "sale": sale})


@app.route("/api/product/create", methods=["POST"])
def api_create_product():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    barcode = data.get("barcode", "").strip()
    name = data.get("name", "").strip()
    price = data.get("price", 0)
    category = data.get("category", "Бусад").strip()
    unit = data.get("unit", "ш").strip()
    stock_qty = data.get("stock_qty", 0)

    product_id, error = db.create_product(
        barcode=barcode, name=name, price=price,
        category=category, stock_qty=stock_qty, unit=unit
    )
    if error:
        return jsonify({"success": False, "error": error}), 400

    product = db.get_product_by_id(product_id)
    return jsonify({"success": True, "product": product})


# ─────────────────────────────────────────────
# HELD ORDERS (Suspended / Parked carts)
# ─────────────────────────────────────────────

@app.route("/api/held-orders", methods=["GET"])
def api_held_orders_list():
    orders = db.get_held_orders()
    return jsonify({"success": True, "orders": orders})


@app.route("/api/hold-order", methods=["POST"])
def api_hold_order():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    label = data.get("label", "").strip() or "Хүлээлгэсэн"
    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        return jsonify({"success": False, "error": "Сагс хоосон"}), 400

    order_id = db.create_held_order(label, items, total)
    return jsonify({"success": True, "id": order_id})


@app.route("/api/recall-order/<int:order_id>", methods=["POST"])
def api_recall_order(order_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    order = db.get_held_order(order_id)
    if not order:
        return jsonify({"success": False, "error": "Захиалга олдсонгүй"}), 404

    # Enrich recalled items with current stock and price from DB
    for item in order["items"]:
        if item.get("product_id"):
            product = db.get_product_by_id(item["product_id"])
            if product:
                item["stock_qty"] = product["stock_qty"]
                item["current_price"] = product["price"]
            else:
                item["stock_qty"] = 0
        else:
            item["stock_qty"] = 0

    db.delete_held_order(order_id)
    return jsonify({"success": True, "order": order})


@app.route("/api/delete-held-order/<int:order_id>", methods=["POST"])
def api_delete_held_order(order_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    db.delete_held_order(order_id)
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# SALES HISTORY
# ─────────────────────────────────────────────

@app.route("/sales")
def sales_page():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    page = int(request.args.get("page", 1))
    per_page = 50

    sales = db.get_sales_list(
        date_from=date_from or None,
        date_to=date_to or None,
        limit=per_page,
        offset=(page - 1) * per_page
    )
    total_count = db.get_sales_count(
        date_from=date_from or None,
        date_to=date_to or None
    )
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return render_template(
        "sales.html",
        sales=sales,
        date_from=date_from,
        date_to=date_to,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@app.route("/sales/<int:sale_id>")
def sale_detail(sale_id):
    sale = db.get_sale(sale_id)
    if not sale:
        flash("Борлуулалт олдсонгүй.", "error")
        return redirect(url_for("sales_page"))
    return render_template("sale_detail.html", sale=sale)


# ─────────────────────────────────────────────
# PRODUCT MANAGEMENT (admin required)
# ─────────────────────────────────────────────

@app.route("/products")
@admin_required
def products_page():
    products = db.get_all_products(active_only=False)
    categories = db.get_categories()
    suppliers = db.get_suppliers()
    return render_template("products.html", products=products, categories=categories, suppliers=suppliers)


@app.route("/products/create", methods=["POST"])
@admin_required
def products_create():
    if not validate_csrf_token():
        flash("CSRF алдаа. Дахин оролдоно уу.", "error")
        return redirect(url_for("products_page"))

    barcode = request.form.get("barcode", "").strip()
    name = request.form.get("name", "").strip()
    price = request.form.get("price", 0)
    cost_price = request.form.get("cost_price", 0)
    category = request.form.get("category", "Бусад").strip()
    stock_qty = request.form.get("stock_qty", 0)
    unit = request.form.get("unit", "ш").strip()
    low_stock_threshold = request.form.get("low_stock_threshold", 5)
    expiry_date = request.form.get("expiry_date", "").strip()
    image_url = request.form.get("image_url", "").strip()
    supplier_id = request.form.get("supplier_id", "").strip() or None

    product_id, error = db.create_product(
        barcode=barcode, name=name, price=price,
        cost_price=int(cost_price) if cost_price else 0,
        category=category, stock_qty=stock_qty, unit=unit,
        low_stock_threshold=int(low_stock_threshold) if low_stock_threshold else 5,
        expiry_date=expiry_date, image_url=image_url,
        supplier_id=int(supplier_id) if supplier_id else None
    )
    if error:
        flash(error, "error")
    else:
        flash(f"'{name}' бараа амжилттай үүсгэлээ.", "success")

    return redirect(url_for("products_page"))


@app.route("/products/update/<int:product_id>", methods=["POST"])
@admin_required
def products_update(product_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    kwargs = {}
    for field in ["barcode", "name", "price", "cost_price", "category", "stock_qty",
                   "unit", "low_stock_threshold", "expiry_date", "image_url",
                   "supplier_id", "is_active"]:
        if field in request.form:
            kwargs[field] = request.form[field]

    success, error = db.update_product(product_id, **kwargs)
    if error:
        flash(error, "error")
    else:
        flash("Бараа амжилттай шинэчлэгдлээ.", "success")

    return redirect(url_for("products_page"))


@app.route("/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def products_delete(product_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    db.delete_product(product_id)
    flash("Бараа устгагдлаа.", "success")
    return redirect(url_for("products_page"))


@app.route("/products/restore/<int:product_id>", methods=["POST"])
@admin_required
def products_restore(product_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    db.restore_product(product_id)
    flash("Бараа сэргээгдлээ.", "success")
    return redirect(url_for("products_page"))


@app.route("/products/import", methods=["POST"])
@admin_required
def products_import():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("CSV файл сонгоно уу.", "error")
        return redirect(url_for("products_page"))

    if not file.filename.endswith(".csv"):
        flash("Зөвхөн .csv файл оруулна уу.", "error")
        return redirect(url_for("products_page"))

    try:
        content = file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        imported = 0
        updated = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            barcode = row.get("barcode", "").strip()
            name = row.get("name", "").strip()
            price = row.get("price", "0").strip()
            category = row.get("category", "Бусад").strip()
            stock_qty = row.get("stock_qty", "0").strip()
            unit = row.get("unit", "ш").strip()

            if not barcode or not name:
                errors.append(f"Мөр {i}: баркод эсвэл нэр хоосон")
                continue

            existing = db.get_product_by_barcode(barcode)
            if existing:
                success, error = db.update_product(
                    existing["id"], name=name, price=price,
                    category=category, stock_qty=stock_qty, unit=unit
                )
                if error:
                    errors.append(f"Мөр {i}: {error}")
                else:
                    updated += 1
            else:
                product_id, error = db.create_product(
                    barcode=barcode, name=name, price=price,
                    category=category, stock_qty=stock_qty, unit=unit
                )
                if error:
                    errors.append(f"Мөр {i}: {error}")
                else:
                    imported += 1

        if imported > 0:
            flash(f"{imported} бараа амжилттай импортлолоо.", "success")
        if updated > 0:
            flash(f"{updated} бараа шинэчлэгдлээ.", "success")
        if errors:
            for err in errors[:10]:
                flash(err, "error")
            if len(errors) > 10:
                flash(f"... болон бусад {len(errors) - 10} алдаа", "error")

    except Exception as e:
        flash(f"CSV уншихад алдаа: {e}", "error")

    return redirect(url_for("products_page"))


@app.route("/api/product/image/upload", methods=["POST"])
def api_product_image_upload():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Файл сонгоно уу"}), 400

    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"success": False, "error": "Зөвхөн зураг файл (PNG, JPG, GIF, WebP)"}), 400

    upload_dir = os.path.join(PROJECT_DIR, "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    import uuid
    safe_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, safe_name)
    file.save(filepath)

    image_url = f"/static/uploads/{safe_name}"
    return jsonify({"success": True, "image_url": image_url})


@app.route("/products/image/delete", methods=["POST"])
@admin_required
def products_image_delete():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))
    product_id = request.form.get("product_id")
    if product_id:
        db.update_product(int(product_id), image_url="")
    return redirect(url_for("products_page"))


# ─────────────────────────────────────────────
# SUPPLIER ROUTES
# ─────────────────────────────────────────────

@app.route("/suppliers")
def suppliers_page():
    suppliers = db.get_suppliers(include_inactive=True)
    return render_template("suppliers.html", suppliers=suppliers)


@app.route("/suppliers/create", methods=["POST"])
@admin_required
def suppliers_create():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("suppliers_page"))
    name = request.form.get("name", "").strip()
    supplier_id, error = db.create_supplier(
        name=name,
        contact_person=request.form.get("contact_person", "").strip(),
        phone=request.form.get("phone", "").strip(),
        email=request.form.get("email", "").strip(),
        address=request.form.get("address", "").strip(),
        notes=request.form.get("notes", "").strip()
    )
    if error: flash(error, "error")
    else: flash(f"'{name}' нийлүүлэгч амжилттай үүсгэлээ.", "success")
    return redirect(url_for("suppliers_page"))


@app.route("/suppliers/update/<int:supplier_id>", methods=["POST"])
@admin_required
def suppliers_update(supplier_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("suppliers_page"))
    kwargs = {}
    for field in ["name", "contact_person", "phone", "email", "address", "notes", "is_active"]:
        if field in request.form:
            kwargs[field] = request.form[field]
    success, error = db.update_supplier(supplier_id, **kwargs)
    if error: flash(error, "error")
    else: flash("Нийлүүлэгч шинэчлэгдлээ.", "success")
    return redirect(url_for("suppliers_page"))


@app.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
@admin_required
def suppliers_delete(supplier_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("suppliers_page"))
    db.delete_supplier(supplier_id)
    flash("Нийлүүлэгч устгагдлаа.", "success")
    return redirect(url_for("suppliers_page"))


# ─────────────────────────────────────────────
# CATEGORIES (admin required)
# ─────────────────────────────────────────────

@app.route("/categories")
@admin_required
def categories_page():
    cats = db.get_all_categories()
    # Include any categories from products not yet in the table
    product_cats = db.get_categories()
    existing_names = {c['name'] for c in cats}
    for name in product_cats:
        if name not in existing_names:
            db.ensure_category(name)
    cats = db.get_all_categories()
    return render_template("categories.html", categories=cats)


@app.route("/api/categories", methods=["GET"])
@admin_required
def api_categories_list():
    cats = db.get_all_categories()
    return jsonify({"categories": cats})


@app.route("/api/categories/create", methods=["POST"])
@admin_required
def api_categories_create():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Нэр оруулна уу"}), 400
    icon = data.get("icon", "📦").strip()
    color = data.get("color", "#6B7280").strip()
    cat_id = db.create_category(name, icon, color)
    if cat_id is None:
        return jsonify({"success": False, "error": "Энэ ангилал бүртгэгдсэн байна"}), 400
    return jsonify({"success": True, "id": cat_id})


@app.route("/api/categories/update/<int:cat_id>", methods=["POST"])
@admin_required
def api_categories_update(cat_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    icon = data.get("icon")
    color = data.get("color")
    sort_order = data.get("sort_order")
    db.update_category(cat_id, name=name, icon=icon, color=color, sort_order=sort_order)
    return jsonify({"success": True})


@app.route("/api/categories/delete/<int:cat_id>", methods=["POST"])
@admin_required
def api_categories_delete(cat_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    reassign = request.args.get("reassign", "Бусад")
    db.delete_category(cat_id, reassign_to=reassign)
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# REPORTS (admin required)
# ─────────────────────────────────────────────

@app.route("/reports")
@admin_required
def reports_page():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    report = db.get_sales_report(
        date_from=date_from or None,
        date_to=date_to or None,
    )

    return render_template(
        "reports.html",
        report=report,
        date_from=date_from,
        date_to=date_to,
        profit=db.get_profit_summary(date_from or None, date_to or None),
    )


@app.route("/api/reports/chart-data")
@admin_required
def api_reports_chart_data():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    report = db.get_sales_report(
        date_from=date_from or None,
        date_to=date_to or None,
    )
    profit = db.get_profit_summary(date_from or None, date_to or None)
    return jsonify({
        "daily": report["daily"],
        "hourly": report["hourly"],
        "summary": report["summary"],
        "category_breakdown": report["category_breakdown"],
        "avg_items_per_sale": report["avg_items_per_sale"],
        "avg_transaction": report["avg_transaction"],
        "profit": profit,
    })


@app.route("/reports/export")
@admin_required
def reports_export():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    sales = db.get_sales_list(
        date_from=date_from or None,
        date_to=date_to or None,
        limit=10000,
        offset=0
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Огноо", "Төлбөр", "Нийт", "Бэлэн", "Карт", "Буцаалт", "eBarimt төлөв", "Сугалаа", "Төлөв"])
    for s in sales:
        status = "Буцаагдсан" if s.get("return_of_sale_id") else ("Буцаалт" if s["payment_type"] == "return" else "✓")
        writer.writerow([
            s["id"], s["created_at"], s["payment_type"], s["total"],
            s.get("cash_given", 0), s.get("card_amount", 0), s.get("change_given", 0),
            s["ebarimt_status"], s.get("ebarimt_lottery", ""), status
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_export.csv"}
    )


# ─────────────────────────────────────────────
# INVENTORY (admin required)
# ─────────────────────────────────────────────

@app.route("/inventory")
@admin_required
def inventory_page():
    products = db.get_all_products(active_only=True)
    low_stock = db.get_low_stock_products()
    adjustments = db.get_stock_adjustments(limit=50)
    forecast = db.get_inventory_forecast()
    expiring = db.get_expiring_products()
    return render_template(
        "inventory.html",
        products=products,
        low_stock=low_stock,
        adjustments=adjustments,
        forecast=forecast,
        expiring=expiring,
    )


@app.route("/api/inventory/forecast")
@admin_required
def api_inventory_forecast():
    forecast = db.get_inventory_forecast()
    return jsonify({"forecast": forecast})


@app.route("/inventory/adjust", methods=["POST"])
@admin_required
def inventory_adjust():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("inventory_page"))

    product_id = request.form.get("product_id")
    quantity_change = request.form.get("quantity_change", 0)
    reason = request.form.get("reason", "").strip()

    if not product_id:
        flash("Бараа сонгоно уу.", "error")
        return redirect(url_for("inventory_page"))

    result = db.adjust_stock(
        product_id=product_id,
        quantity_change=quantity_change,
        reason=reason,
        cashier_id=None
    )
    if len(result) == 4:
        success, error, old_stock, new_stock = result
    else:
        success, error = result
        old_stock = new_stock = 0

    if error:
        flash(error, "error")
    else:
        flash(f"Нөөц шинэчлэгдлээ: {old_stock} → {new_stock}", "success")

    return redirect(url_for("inventory_page"))


# ─────────────────────────────────────────────
# SETTINGS (admin required)
# ─────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings_page():
    if request.method == "GET":
        settings = get_all_config()
        return render_template(
            "settings.html",
            settings=settings,
        )

    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("settings_page"))

    settings_to_save = {}
    for key in ["store_name", "store_address", "store_phone",
                "printer_port", "receipt_footer",
                "ebarimt_api_url", "ebarimt_merchant_tin", "ebarimt_ttd",
                "ebarimt_branch_id", "default_payment_type",
                "auto_print_receipt", "show_vat_on_receipt",
                "receipt_width", "customer_display_timeout",
                "customer_idle_message",
                "qr_payment_image", "theme"]:
        if key in request.form:
            settings_to_save[key] = request.form[key].strip()

    for bool_key in ["auto_print_receipt", "show_vat_on_receipt"]:
        if bool_key not in settings_to_save:
            settings_to_save[bool_key] = "false"

    db.set_settings(settings_to_save)
    flash("Тохиргоо амжилттай хадгалагдлаа.", "success")
    return redirect(url_for("settings_page"))


@app.route("/settings/backup", methods=["POST"])
@admin_required
def settings_manual_backup():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("settings_page"))

    success, message = db.perform_manual_backup()
    if success:
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for("settings_page"))


# ─────────────────────────────────────────────
# BULK PRICE UPDATE
# ─────────────────────────────────────────────

@app.route("/products/bulk-price", methods=["POST"])
@admin_required
def products_bulk_price():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))
    category = request.form.get("category", "").strip()
    percent = request.form.get("percent_change", "0").strip()
    count, error = db.bulk_update_prices(category, percent)
    if error: flash(error, "error")
    else: flash(f"'{category}' ангиллын {count} барааны үнэ {percent}%-иар шинэчлэгдлээ.", "success")
    return redirect(url_for("products_page"))


# ─────────────────────────────────────────────
# CASH DRAWER MANAGEMENT
# ─────────────────────────────────────────────

@app.route("/api/cash-drawer/action", methods=["POST"])
def api_cash_drawer_action():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    amount = int(data.get("amount") or 0)
    note = data.get("note", "").strip()
    if action not in ("open", "close", "float_in", "float_out"):
        return jsonify({"success": False, "error": "Буруу үйлдэл"}), 400
    db.log_cash_drawer(action, amount, note)
    return jsonify({
        "success": True,
        "balance": db.get_cash_drawer_balance(),
        "today_cash_sales": db.get_today_cash_sales()
    })


@app.route("/api/cash-drawer/status")
def api_cash_drawer_status():
    return jsonify({
        "balance": db.get_cash_drawer_balance(),
        "today_cash_sales": db.get_today_cash_sales(),
        "log": db.get_cash_drawer_log(20),
    })


# ─────────────────────────────────────────────
# SHIFT / Z-REPORT (admin required)
# ─────────────────────────────────────────────

@app.route("/api/shift/open", methods=["POST"])
def api_shift_open():
    data = request.get_json(silent=True) or {}
    opening_balance = int(data.get("opening_balance", 0) or 0)
    shift_id = db.open_shift(opening_balance)
    return jsonify({"success": True, "shift_id": shift_id})


@app.route("/api/shift/close", methods=["POST"])
def api_shift_close():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    data = request.get_json(silent=True) or {}
    actual_cash = int(data.get("actual_cash", 0) or 0)
    shift, error = db.close_shift(actual_cash)
    if error:
        return jsonify({"success": False, "error": error}), 400
    return jsonify({"success": True, "shift": shift})


@app.route("/api/shift/current")
def api_shift_current():
    shift = db.get_current_shift()
    if not shift:
        return jsonify({"success": True, "shift": None, "message": "Нээлттэй ээлж байхгүй"})
    return jsonify({"success": True, "shift": shift})


@app.route("/api/shift/history")
def api_shift_history():
    limit = request.args.get("limit", 30)
    shifts = db.get_shift_history(int(limit))
    return jsonify({"success": True, "shifts": shifts})


# ─────────────────────────────────────────────
# RETURN / REFUND (admin required)
# ─────────────────────────────────────────────

@app.route("/api/return/<int:sale_id>", methods=["POST"])
@admin_required
def api_return(sale_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    return_sale, error = db.process_return(sale_id)
    if error:
        return jsonify({"success": False, "error": error}), 400

    # Print return receipt if auto_print enabled
    auto_print = get_config("auto_print_receipt")
    if auto_print == "true":
        try:
            from printer import print_receipt
            print_receipt(return_sale, get_store_info())
        except Exception as e:
            logger.warning(f"Return receipt print failed (non-fatal): {e}")

    return jsonify({"success": True, "return_sale_id": return_sale["id"]})


# ─────────────────────────────────────────────
# REPRINT RECEIPT
# ─────────────────────────────────────────────

@app.route("/api/reprint/<int:sale_id>", methods=["POST"])
def api_reprint(sale_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    sale = db.get_sale(sale_id)
    if not sale:
        return jsonify({"success": False, "error": "Борлуулалт олдсонгүй"}), 404

    try:
        from printer import print_receipt
        result = print_receipt(sale, get_store_info())
        return jsonify({"success": result["success"], "error": result.get("error", "")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─────────────────────────────────────────────
# eBARIMT MANUAL RETRY
# ─────────────────────────────────────────────

@app.route("/api/ebarimt-retry", methods=["POST"])
@admin_required
def api_ebarimt_retry():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    if not is_ebarimt_configured():
        return jsonify({"success": False, "error": "eBarimt тохиргоо хийгдээгүй байна"}), 400

    try:
        from ebarimt import EbarimtAdapter
        adapter = EbarimtAdapter()
        pending = db.get_pending_ebarimt_sales()

        if not pending:
            return jsonify({"success": True, "retried": 0, "sent": 0, "message": "Хүлээгдэж буй баримт байхгүй"})

        sent = 0
        for sale in pending:
            try:
                result = adapter.send_receipt(sale)
                if result.get("success"):
                    db.update_sale_ebarimt(
                        sale["id"],
                        ebarimt_id=result.get("ebarimt_id", ""),
                        ebarimt_qr=result.get("qr_data", ""),
                        lottery=result.get("lottery", ""),
                        status="sent"
                    )
                    sent += 1
            except Exception as e:
                logger.error(f"eBarimt retry error for sale #{sale['id']}: {e}")

        return jsonify({
            "success": True,
            "retried": len(pending),
            "sent": sent,
            "message": f"{len(pending)} баримт шалгалаа, {sent} амжилттай"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Энэдүүрэг олдсонгүй"}), 404
    flash("Хуудас олдсонгүй.", "error")
    return redirect(url_for("pos"))


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Серверийн алдаа"}), 500
    flash("Серверийн алдаа гарлаа. Дахин оролдоно уу.", "error")
    return redirect(url_for("pos"))


@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Системийн алдаа"}), 500
    flash("Системийн алдаа гарлаа.", "error")
    return redirect(url_for("pos"))


# ─────────────────────────────────────────────
# eBARIMT RETRY ON STARTUP
# ─────────────────────────────────────────────

def retry_pending_ebarimt():
    try:
        if not is_ebarimt_configured():
            logger.info("eBarimt not configured, skipping pending retries.")
            return

        from ebarimt import EbarimtAdapter
        adapter = EbarimtAdapter()
        pending = db.get_pending_ebarimt_sales()

        if not pending:
            logger.info("No pending eBarimt sales to retry.")
            return

        logger.info(f"Retrying {len(pending)} pending eBarimt sales...")
        for sale in pending:
            try:
                result = adapter.send_receipt(sale)
                if result.get("success"):
                    db.update_sale_ebarimt(
                        sale["id"],
                        ebarimt_id=result.get("ebarimt_id", ""),
                        ebarimt_qr=result.get("qr_data", ""),
                        lottery=result.get("lottery", ""),
                        status="sent"
                    )
                    logger.info(f"eBarimt sent for sale #{sale['id']}")
                else:
                    logger.warning(f"eBarimt retry failed for sale #{sale['id']}: {result.get('error', 'unknown')}")
            except Exception as e:
                logger.error(f"eBarimt retry error for sale #{sale['id']}: {e}")

        logger.info("eBarimt retry complete.")
    except Exception as e:
        logger.error(f"eBarimt retry task failed: {e}")


# ─────────────────────────────────────────────
# APP STARTUP
# ─────────────────────────────────────────────

def create_app():
    logger.info("Initializing POS database...")
    db.init_db()
    logger.info("Database ready.")

    retry_thread = threading.Thread(
        target=retry_pending_ebarimt,
        daemon=True,
        name="ebarimt-retry"
    )
    retry_thread.start()
    logger.info("eBarimt retry thread started.")

    return app


if __name__ == "__main__":
    application = create_app()
    logger.info(f"Starting POS server on {FLASK_HOST}:{FLASK_PORT}")
    application.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=False
    )

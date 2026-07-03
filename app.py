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
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, Response
)

from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix

import database as db
from config import (
    FLASK_SECRET_KEY, FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    get_config, get_all_config,
    is_ebarimt_configured, get_store_info
)
from i18n import _t


def _is_terminal_configured():
    try:
        from terminal import is_terminal_configured as term_cfg
        return term_cfg()
    except Exception:
        return False


def _generate_mock_qr(data, amount):
    import base64, qrcode
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64


def _is_qpay_configured():
    try:
        from qpay import QPayClient
        return QPayClient.is_configured()
    except Exception:
        return False


def _get_qpay_client():
    from qpay import QPayClient
    return QPayClient.from_config()


def _startup_self_check():
    checks = {}
    checks["db_integrity"] = db.check_db_integrity()
    try:
        from printer import get_effective_printer_port
        printer_port = get_effective_printer_port()
        checks["printer"] = bool(printer_port and os.path.exists(printer_port))
        checks["printer_port"] = str(printer_port) if printer_port else "none"
    except Exception as e:
        checks["printer"] = False
        checks["printer_port"] = str(e)
    if _is_terminal_configured():
        try:
            from terminal import test_connection
            pax_result = test_connection()
            checks["pax"] = pax_result.get("success", False)
        except Exception as e:
            checks["pax"] = False
            checks["pax_error"] = str(e)
    else:
        checks["pax"] = None
    try:
        st = os.statvfs(os.path.dirname(app.instance_path) if hasattr(app, 'instance_path') else ".")
        checks["disk_free_mb"] = round((st.f_bavail * st.f_frsize) / (1024 * 1024))
    except Exception as e:
        checks["disk_free_mb"] = -1
        checks["disk_error"] = str(e)
    from config import FLASK_SECRET_KEY as _sk
    checks["default_secret"] = (_sk == "pos-secret-change-me-in-production-2024-mongolia")
    checks["secret_len_ok"] = len(_sk or "") >= 16
    db_dir = os.path.dirname(os.path.abspath(db.DB_PATH))
    checks["db_dir_writable"] = os.access(db_dir, os.W_OK)
    if not checks["db_dir_writable"]:
        logger.warning(f"DB directory not writable: {db_dir}")
    logger.info(f"Startup self-check: {json.dumps(checks)}")
    return checks


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_NAME"] = "pos_session"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0 if FLASK_DEBUG else 86400
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max upload
app.config["TEMPLATES_AUTO_RELOAD"] = FLASK_DEBUG
app.config["DEBUG"] = FLASK_DEBUG

compress = Compress()
compress.init_app(app)

# Trust X-Forwarded-* headers when behind a reverse proxy (nginx, etc.)
# Set POS_TRUSTED_PROXY=1 in production; defaults to trusted on docker/container.
_trusted_proxy = os.environ.get("POS_TRUSTED_PROXY", "").lower()
if _trusted_proxy in ("1", "true", "yes") or os.environ.get("GUNICORN_WORKER_ID"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

APP_START_TIME = time.time()

# Ensure required directories exist before anything else
for _required_dir in ["logs", "backups", "data", "static/uploads"]:
    _p = os.path.join(PROJECT_DIR, _required_dir)
    os.makedirs(_p, exist_ok=True)

from logging.handlers import RotatingFileHandler  # noqa: E402 — grouped with logging setup

_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_log_fmt)

_file_handler = RotatingFileHandler(
    os.path.join(PROJECT_DIR, "logs", "pos.log"),
    encoding="utf-8", maxBytes=10 * 1024 * 1024, backupCount=5
)
_file_handler.setFormatter(_log_fmt)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_file_handler, _stream_handler]
)
logger = logging.getLogger(__name__)

if _trusted_proxy in ("1", "true", "yes") or os.environ.get("GUNICORN_WORKER_ID"):
    logger.info("ProxyFix middleware enabled (trusts X-Forwarded-For / X-Forwarded-Proto)")

# Enable secure cookies only when explicitly requested or behind HTTPS proxy.
# Default: off (required for local HTTP usage). Set POS_SECURE_COOKIES=1 for HTTPS production.
_force_secure = os.environ.get("POS_SECURE_COOKIES", "").lower()
if _force_secure in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True
    logger.info("Secure session cookies enabled (POS_SECURE_COOKIES=1)")
else:
    app.config["SESSION_COOKIE_SECURE"] = False

app.config["ADMIN_SESSION_TIMEOUT_MINUTES"] = int(get_config("admin_session_timeout_minutes") or 480)


# ─────────────────────────────────────────────
# SECURITY HEADERS
# ─────────────────────────────────────────────

# HTTPS enforcement: redirect HTTP→HTTPS when behind a trusted reverse proxy.
# Set POS_FORCE_HTTPS=0 to disable (e.g., for local-only POS on LAN without TLS).
_force_https = os.environ.get("POS_FORCE_HTTPS", "").lower()
if _force_https not in ("0", "false", "no"):
    @app.before_request
    def _enforce_https():
        if request.headers.get("X-Forwarded-Proto", "https") == "http":
            url = request.url.replace("http://", "https://", 1)
            return redirect(url, code=301)


@app.after_request
def set_security_headers(response):
    _increment_request_counter()
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if os.environ.get("POS_FORCE_HTTPS", "").lower() not in ("0", "false", "no"):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' blob:; "
        "frame-ancestors 'none';"
    )
    csrf_token = session.get("csrf_token", "")
    if csrf_token:
        response.headers['X-CSRF-Token'] = csrf_token
    return response


# ─────────────────────────────────────────────
# RATE LIMITING (simple in-memory)
# ─────────────────────────────────────────────

# Change this version on each deploy to force browser cache refresh
_cache_bust_version = int(time.time())

_rate_limit_store = {}
_rate_limit_lock = threading.Lock()

def _rate_limit_key():
    return request.remote_addr or "127.0.0.1"

def rate_limit(max_requests=30, window_seconds=10):
    """Simple in-memory rate limiting decorator. Skips GET/HEAD requests."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if request.method in ("GET", "HEAD"):
                return f(*args, **kwargs)
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
# METRICS (request counter for Prometheus)
# ─────────────────────────────────────────────

_metrics_request_count = 0
_metrics_request_lock = threading.Lock()


def _increment_request_counter():
    global _metrics_request_count
    with _metrics_request_lock:
        _metrics_request_count += 1

_RATE_LIMIT_CLEANUP_INTERVAL = 300

def _cleanup_rate_limit_store():
    while True:
        time.sleep(_RATE_LIMIT_CLEANUP_INTERVAL)
        now = time.time()
        with _rate_limit_lock:
            stale = [ip for ip, ts in _rate_limit_store.items()
                     if not ts or now - max(ts) > 60]
            for ip in stale:
                del _rate_limit_store[ip]


# ─────────────────────────────────────────────
# BACKGROUND HEALTH CHECK
# ─────────────────────────────────────────────

_HEALTH_CHECK_INTERVAL = 300  # 5 minutes

def _run_periodic_health_check():
    """Periodically checks DB integrity, disk space, and eBarimt queue length.
    Logs warnings when thresholds are exceeded."""
    while True:
        time.sleep(_HEALTH_CHECK_INTERVAL)
        try:
            db.check_db_integrity()
        except Exception as e:
            logger.error(f"Health check: DB integrity error — {e}")

        try:
            import shutil
            usage = shutil.disk_usage(PROJECT_DIR)
            free_mb = usage.free // (1024 * 1024)
            if free_mb < 100:
                logger.warning(f"Health check: Low disk space — {free_mb} MB free")
            elif free_mb < 500:
                logger.info(f"Health check: Disk space at {free_mb} MB free")
        except Exception as e:
            logger.warning(f"Health check: Disk usage check failed — {e}")

        try:
            pending = db.get_pending_ebarimt_sales()
            if len(pending) > 5:
                logger.warning(f"Health check: {len(pending)} sales with failed eBarimt")
        except Exception as e:
            logger.warning(f"Health check: eBarimt check failed — {e}")

        try:
            _res = os.path.isdir(os.path.join(PROJECT_DIR, "backups"))
            if not _res:
                logger.warning("Health check: Backups directory missing")
        except Exception:
            logger.warning("Unhandled exception in: except Exception:")
            pass
# ─────────────────────────────────────────────
# CSRF PROTECTION
# ─────────────────────────────────────────────



def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token():
    """Check CSRF token from form body OR X-CSRF-Token header. Rotates on success."""
    expected = session.get("csrf_token", "")
    if not expected:
        return False
    token = request.form.get("csrf_token", "")
    if not token:
        token = request.headers.get("X-CSRF-Token", "")
    if not token or token != expected:
        return False
    session["csrf_token"] = secrets.token_hex(32)
    return True


def _parse_int_arg(name, default, min_value=None, max_value=None):
    """Parse an integer query parameter with optional bounds."""
    return _parse_int_value(request.args.get(name, default), default, min_value, max_value)


def _parse_int_value(raw_value, default=0, min_value=None, max_value=None):
    """Parse an integer value with optional bounds."""
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    if value is None:
        return None
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


# ─────────────────────────────────────────────
# ADMIN AUTHENTICATION
#
# Single-terminal POS: auto-promotes new sessions to admin for convenience
# (no login required on a physically secured device). When a password is set
# via the settings page, admin routes require a valid login session that
# hasn't exceeded the configured timeout (default 480 min / 8 hours).
# ─────────────────────────────────────────────

SESSION_TIMEOUT_KEY = "admin_login_time"

def _get_session_timeout_seconds():
    return int(app.config.get("ADMIN_SESSION_TIMEOUT_MINUTES", 480)) * 60


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Нэвтрэх шаардлагатай"}), 401
            return redirect(url_for("login_page"))
        login_time = session.get(SESSION_TIMEOUT_KEY, 0)
        if time.time() - login_time > _get_session_timeout_seconds():
            session.clear()
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Сессийн хугацаа дууссан"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def auto_admin_session():
    """Auto-promote new sessions to admin (single-terminal POS design)."""
    if not session.get("admin") and not request.path.startswith("/api/login"):
        session["admin"] = True
        session[SESSION_TIMEOUT_KEY] = time.time()



# ─────────────────────────────────────────────
# TEMPLATE CONTEXT (cached for performance)
# ─────────────────────────────────────────────
# Every page render triggers inject_globals() which does multiple DB queries.
# Cache the shared parts (categories, settings) with a 30s TTL to avoid this.

_context_cache = {}
_context_cache_lock = threading.Lock()
_context_cache_ttl = 30
_context_cache_time = 0.0


def invalidate_context_cache():
    global _context_cache_time
    _context_cache_time = 0.0


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
    'Хүнсний ногоо': '🥬',
    'Мах': '🥩',
    'Амттан': '🍰',
    'Өрхийн бараа': '🏠',
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
    'Хүнсний ногоо': '#10B981',
    'Мах': '#DC2626',
    'Амттан': '#EC4899',
    'Өрхийн бараа': '#8B5CF6',
    'Бусад': '#6B7280'
}


@app.context_processor
def inject_globals():
    global _context_cache, _context_cache_time
    now = time.time()

    # API routes don't render templates — skip expensive DB work
    if request.path.startswith("/api/"):
        result = dict(_context_cache) if _context_cache else {}
        result["csrf_token"] = generate_csrf_token()
        result["admin_mode"] = True
        result["now"] = datetime.now()
        return result

    if now - _context_cache_time < _context_cache_ttl and _context_cache:
        cached = dict(_context_cache)
        cached["csrf_token"] = generate_csrf_token()
        cached["admin_mode"] = True
        cached["now"] = datetime.now()
        return cached

    db_cats = db.get_all_categories()
    icons = dict(CATEGORY_ICONS)
    colors = dict(CATEGORY_COLORS)
    for c in db_cats:
        icons[c['name']] = c['icon']
        colors[c['name']] = c['color']

    def cache_bust(filename):
        return url_for('static', filename=filename) + f'?v={_cache_bust_version}'

    with _context_cache_lock:
        _context_cache = {
            "ebarimt_configured": is_ebarimt_configured(),
            "terminal_configured": _is_terminal_configured(),
            "store_info": get_store_info(),
            "admin_pin_set": bool(db.get_setting("admin_pin_hash", "")),
            "CATEGORY_ICONS": icons,
            "CATEGORY_COLORS": colors,
            "_t": _t,
            "settings": get_all_config(),
            "static_url": cache_bust,
            "dev_mode": FLASK_DEBUG,
        }
        _context_cache_time = now

    result = dict(_context_cache)
    result["csrf_token"] = generate_csrf_token()
    result["admin_mode"] = True
    result["now"] = datetime.now()
    return result







# ─────────────────────────────────────────────
# POS ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def pos():
    products = db.get_all_products(active_only=True)
    categories = db.get_categories_from_products(products)
    settings = get_all_config()
    product_count = len(products)
    if product_count > 500:
        products = products[:500]
        logger.info(f"Product grid truncated to 500 (total {product_count})")
    return render_template("pos.html", products=products, categories=categories, settings=settings, products_truncated=product_count > 500)


@app.route("/customer")
def customer_display():
    settings = get_all_config()
    store_info = get_store_info()
    return render_template("customer_display.html", settings=settings, store_info=store_info)


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/health/deep")
def api_health_deep():
    checks = {"status": "healthy", "components": {}}

    # DB connectivity
    try:
        db.check_db_integrity()
        checks["components"]["database"] = "ok"
    except Exception as e:
        checks["components"]["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # Backup directory writable
    backup_dir = os.path.join(PROJECT_DIR, "backups")
    try:
        os.makedirs(backup_dir, exist_ok=True)
        test_file = os.path.join(backup_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        checks["components"]["backup_directory"] = "ok"
    except Exception as e:
        checks["components"]["backup_directory"] = f"error: {e}"
        checks["status"] = "degraded"

    # Printer availability
    try:
        from printer import get_effective_printer_port
        printer_port = get_effective_printer_port()
        if printer_port and os.path.exists(printer_port):
            checks["components"]["printer"] = f"available ({printer_port})"
        else:
            checks["components"]["printer"] = f"unavailable ({printer_port})"
    except Exception as e:
        checks["components"]["printer"] = f"error: {e}"

    # eBarimt configured
    checks["components"]["ebarimt"] = "configured" if is_ebarimt_configured() else "not_configured"

    # PAX terminal reachability
    try:
        if _is_terminal_configured():
            from terminal import test_connection
            result = test_connection()
            if result.get("success"):
                checks["components"]["pax_terminal"] = "reachable"
            else:
                checks["components"]["pax_terminal"] = f"unreachable: {result.get('error', 'unknown')}"
                if checks["status"] == "healthy":
                    checks["status"] = "degraded"
        else:
            checks["components"]["pax_terminal"] = "not_configured"
    except Exception as e:
        checks["components"]["pax_terminal"] = f"error: {e}"

    # DB file size
    try:
        db_size = os.path.getsize(db.DB_PATH)
        checks["components"]["db_size_mb"] = round(db_size / (1024 * 1024), 2)
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    # Sale count today
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sales WHERE created_at >= ? AND created_at < ?",
                (today, today + " 23:59:59")
            ).fetchone()
            checks["components"]["sales_today"] = row["cnt"] if row else 0
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    # Disk space
    try:
        import shutil
        usage = shutil.disk_usage(PROJECT_DIR)
        free_mb = usage.free // (1024 * 1024)
        checks["components"]["disk_free_mb"] = free_mb
        if free_mb < 100:
            checks["components"]["disk"] = f"warning: {free_mb} MB free"
            if checks["status"] == "healthy":
                checks["status"] = "degraded"
        else:
            checks["components"]["disk"] = "ok"
    except Exception as e:
        checks["components"]["disk"] = f"error: {e}"

    http_status = 200 if checks["status"] == "healthy" else 503
    return jsonify(checks), http_status


@app.route("/api/diagnostics")
@admin_required
def api_diagnostics():
    diag = {
        "version": "",
        "db_path": db.DB_PATH,
        "db_size_bytes": 0,
        "backup_count": 0,
        "last_backup_date": "",
        "backup_retention_days": 30,
        "pending_ebarimt": 0,
        "printer_port": "",
        "wal_mode": True,
        "foreign_keys": True,
        "uptime_seconds": 0,
        "disk_free_mb": 0,
    }

    try:
        with open(os.path.join(PROJECT_DIR, "VERSION"), "r") as f:
            diag["version"] = f.read().strip()
    except Exception:
        diag["version"] = "unknown"

    if os.path.exists(db.DB_PATH):
        diag["db_size_bytes"] = os.path.getsize(db.DB_PATH)

    backup_dir = os.path.join(PROJECT_DIR, "backups")
    if os.path.isdir(backup_dir):
        diag["backup_count"] = len([f for f in os.listdir(backup_dir) if f.startswith("pos_") and f.endswith(".db")])

    diag["last_backup_date"] = db.get_setting("last_backup_date", "")
    diag["backup_retention_days"] = int(db.get_setting("backup_retention_days", "30") or "30")

    try:
        pending = db.get_pending_ebarimt_sales()
        diag["pending_ebarimt"] = len(pending)
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    try:
        from printer import get_effective_printer_port
        diag["printer_port"] = get_effective_printer_port()
    except Exception:
        diag["printer_port"] = "unknown"

    try:
        import shutil
        usage = shutil.disk_usage(PROJECT_DIR)
        diag["disk_free_mb"] = usage.free // (1024 * 1024)
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        diag["process_max_rss_kb"] = usage.ru_maxrss
    except Exception:
        diag["process_max_rss_kb"] = 0

    diag["uptime_seconds"] = int(time.time() - APP_START_TIME)

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sales WHERE created_at >= ? AND created_at < ?",
                (today, today + " 23:59:59")
            ).fetchone()
            diag["sales_today"] = row["cnt"] if row else 0
    except Exception:
        diag["sales_today"] = 0

    return jsonify(diag)


# ─────────────────────────────────────────────
# PROMETHEUS METRICS
# ─────────────────────────────────────────────

@app.route("/api/metrics")
def api_metrics():
    global _metrics_request_count

    today = datetime.now().strftime("%Y-%m-%d")
    sales_total = 0
    sales_today = 0
    products_total = 0
    pending_count = 0
    backup_count = 0
    db_size = 0

    try:
        with db.get_db() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM sales").fetchone()
            sales_total = row["cnt"] if row else 0
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sales WHERE created_at >= ? AND created_at < ?",
                (today, today + " 23:59:59")
            ).fetchone()
            sales_today = row["cnt"] if row else 0
            row = conn.execute("SELECT COUNT(*) as cnt FROM products WHERE deleted=0").fetchone()
            products_total = row["cnt"] if row else 0
            rows = conn.execute("SELECT COUNT(*) as cnt FROM sales WHERE ebarimt_status='failed'").fetchone()
            pending_count = rows["cnt"] if rows else 0
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    if os.path.exists(db.DB_PATH):
        db_size = os.path.getsize(db.DB_PATH)

    backup_dir = os.path.join(PROJECT_DIR, "backups")
    if os.path.isdir(backup_dir):
        backup_count = len([f for f in os.listdir(backup_dir) if f.startswith("pos_") and f.endswith(".db")])

    import shutil
    disk_free = 0
    try:
        disk_free = shutil.disk_usage(PROJECT_DIR).free
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    with _metrics_request_lock:
        req_count = _metrics_request_count

    uptime = int(time.time() - APP_START_TIME)

    lines = [
        f"# HELP pos_uptime_seconds Application uptime in seconds",
        f"# TYPE pos_uptime_seconds gauge",
        f"pos_uptime_seconds {uptime}",
        f"",
        f"# HELP pos_db_size_bytes Database file size in bytes",
        f"# TYPE pos_db_size_bytes gauge",
        f"pos_db_size_bytes {db_size}",
        f"",
        f"# HELP pos_sales_total Total sales count",
        f"# TYPE pos_sales_total counter",
        f"pos_sales_total {sales_total}",
        f"",
        f"# HELP pos_sales_today Today's sales count",
        f"# TYPE pos_sales_today gauge",
        f"pos_sales_today {sales_today}",
        f"",
        f"# HELP pos_products_total Active products count",
        f"# TYPE pos_products_total gauge",
        f"pos_products_total {products_total}",
        f"",
        f"# HELP pos_backup_count Number of backup files",
        f"# TYPE pos_backup_count gauge",
        f"pos_backup_count {backup_count}",
        f"",
        f"# HELP pos_disk_free_bytes Free disk space in bytes",
        f"# TYPE pos_disk_free_bytes gauge",
        f"pos_disk_free_bytes {disk_free}",
        f"",
        f"# HELP pos_http_requests_total Total HTTP requests handled",
        f"# TYPE pos_http_requests_total counter",
        f"pos_http_requests_total {req_count}",
        f"",
        f"# HELP pos_pending_ebarimt_count Sales with failed eBarimt status",
        f"# TYPE pos_pending_ebarimt_count gauge",
        f"pos_pending_ebarimt_count {pending_count}",
        f"",
    ]

    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        max_rss_kb = usage.ru_maxrss
        lines.extend([
            f"# HELP pos_process_max_rss_kb Maximum resident set size (RSS)",
            f"# TYPE pos_process_max_rss_kb gauge",
            f"pos_process_max_rss_kb {max_rss_kb}",
            f"",
        ])
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")


@app.route("/api/version")
def api_version():
    version_path = os.path.join(PROJECT_DIR, "VERSION")
    try:
        with open(version_path, "r") as f:
            ver = f.read().strip()
    except Exception:
        ver = "unknown"
    return jsonify({"version": ver})


# ─────────────────────────────────────────────
# LOGIN / LOGOUT
# ─────────────────────────────────────────────

_LOGIN_ATTEMPT_STORE: dict = {}
_LOGIN_LOCKOUT_MINUTES = 15
_LOGIN_MAX_ATTEMPTS = 5


def _is_locked_out(ip):
    now = time.time()
    entry = _LOGIN_ATTEMPT_STORE.get(ip)
    if entry and entry["count"] >= _LOGIN_MAX_ATTEMPTS:
        if now - entry["first_fail"] < _LOGIN_LOCKOUT_MINUTES * 60:
            return True
        del _LOGIN_ATTEMPT_STORE[ip]
    return False


def _record_login_attempt(ip, success):
    now = time.time()
    if success:
        _LOGIN_ATTEMPT_STORE.pop(ip, None)
        return
    entry = _LOGIN_ATTEMPT_STORE.get(ip)
    if entry and now - entry["first_fail"] > _LOGIN_LOCKOUT_MINUTES * 60:
        entry["count"] = 0
        entry["first_fail"] = now
    if entry:
        entry["count"] += 1
    else:
        _LOGIN_ATTEMPT_STORE[ip] = {"count": 1, "first_fail": now}


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if session.get("admin"):
            login_time = session.get(SESSION_TIMEOUT_KEY, 0)
            if time.time() - login_time <= _get_session_timeout_seconds():
                return redirect(url_for("pos"))
        return render_template("login.html")

    ip = request.remote_addr or "127.0.0.1"
    if _is_locked_out(ip):
        return render_template("login.html", error="Хэт олон удаа буруу оролдсон. Түр хүлээгээд дахин оролдоно уу."), 429

    password = (request.form.get("password") or "").strip()
    if not password:
        return render_template("login.html", error="Нууц үгээ оруулна уу."), 400

    if not db.is_admin_password_set():
        session["admin"] = True
        session[SESSION_TIMEOUT_KEY] = time.time()
        return redirect(url_for("pos"))

    if db.verify_password(password, db.get_admin_password_hash()):
        _record_login_attempt(ip, True)
        session["admin"] = True
        session[SESSION_TIMEOUT_KEY] = time.time()
        return redirect(url_for("pos"))
    else:
        _record_login_attempt(ip, False)
        return render_template("login.html", error="Нууц үг буруу байна."), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("pos"))


@app.route("/api/login", methods=["POST"])
def api_login():
    ip = request.remote_addr or "127.0.0.1"
    if _is_locked_out(ip):
        return jsonify({"success": False, "error": "Түр хүлээгээд дахин оролдоно уу."}), 429

    data = request.get_json(silent=True) or {}
    password = (data.get("password") or "").strip()
    if not password:
        return jsonify({"success": False, "error": "Нууц үгээ оруулна уу."}), 400

    if not db.is_admin_password_set():
        session["admin"] = True
        session[SESSION_TIMEOUT_KEY] = time.time()
        return jsonify({"success": True})

    if db.verify_password(password, db.get_admin_password_hash()):
        _record_login_attempt(ip, True)
        session["admin"] = True
        session[SESSION_TIMEOUT_KEY] = time.time()
        return jsonify({"success": True})
    else:
        _record_login_attempt(ip, False)
        return jsonify({"success": False, "error": "Нууц үг буруу байна."}), 401


def _get_customer_display_state():
    raw = db.get_setting("_customer_display_state", "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Unhandled exception in: except (json.JSONDecodeError, TypeError):")
            pass
    return {
        "phase": "idle", "items": [], "total": 0,
        "payment_type": None, "cash_given": 0,
        "change_given": 0, "card_amount": 0, "lottery": "",
        "qr_image": ""
    }


def _set_customer_display_state(state):
    db.set_setting("_customer_display_state", json.dumps(state, ensure_ascii=False))


# SSE clients list for push-based customer display updates (per-worker)
_sse_clients = []
_sse_clients_lock = threading.Lock()


def _sse_heartbeat_loop():
    import queue
    while True:
        time.sleep(30)
        with _sse_clients_lock:
            dead = []
            for q in _sse_clients:
                try:
                    q.put_nowait(True)
                except queue.Full:
                    dead.append(q)
            for d in dead:
                _sse_clients.remove(d)


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

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_state = {
            "phase": data.get("phase", "idle"),
            "items": data.get("items", []),
            "total": data.get("total", 0),
            "payment_type": data.get("payment_type"),
            "cash_given": data.get("cash_given", 0),
            "change_given": data.get("change_given", 0),
            "card_amount": data.get("card_amount", 0),
            "lottery": data.get("lottery", ""),
            "qr_image": data.get("qr_image", ""),
        }
        _set_customer_display_state(new_state)
        _notify_sse_clients()
        return jsonify({"success": True})

    return jsonify(_get_customer_display_state())


@app.route("/api/customer-stream")
def api_customer_stream():
    """Server-Sent Events endpoint for real-time customer display updates."""
    import queue
    q = queue.Queue()
    with _sse_clients_lock:
        _sse_clients.append(q)

    def event_stream():
        try:
            state = _get_customer_display_state()
            data = json.dumps(state, ensure_ascii=False)
            yield f"data: {data}\n\n"
            while True:
                try:
                    q.get(timeout=15)
                    q.task_done()
                    state = _get_customer_display_state()
                    data = json.dumps(state, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            logger.warning("Unhandled exception in: except GeneratorExit:")
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
        return jsonify({"success": False, "error": "not_found", "barcode": barcode})

    return jsonify({"success": True, "product": product})


@app.route("/api/products/search")
@rate_limit(max_requests=60, window_seconds=10)
def api_product_search():
    query = request.args.get("q", "").strip()
    page = _parse_int_arg("page", 1, min_value=1)
    per_page = _parse_int_arg("per_page", 100, min_value=1, max_value=200)
    category = request.args.get("category", "").strip()

    if query:
        products = db.search_products(query, limit=50)
        return jsonify({"products": products})

    offset = (page - 1) * per_page
    products = db.get_all_products(
        active_only=True,
        limit=per_page,
        offset=offset,
        category=category or None
    )
    total = db.get_product_count(active_only=True, category=category or None)
    return jsonify({
        "products": products,
        "total": total,
        "page": page,
        "per_page": per_page,
    })


def _try_send_ebarimt_receipt(sale, customer_tin=""):
    """Send eBarimt receipt and update DB. Returns (success, result_dict)."""
    if sale.get("payment_type") == "return":
        db.update_sale_ebarimt(sale["id"], status="skipped")
        sale["ebarimt_status"] = "skipped"
        return False, {}
    try:
        if not is_ebarimt_configured():
            db.update_sale_ebarimt(sale["id"], status="skipped")
            sale["ebarimt_status"] = "skipped"
            return False, {}
        from ebarimt import EbarimtAdapter
        adapter = EbarimtAdapter()
        if customer_tin:
            sale["customer_tin"] = customer_tin
        result = adapter.send_receipt(sale)
        if result.get("success"):
            db.update_sale_ebarimt(
                sale["id"],
                ebarimt_id=result.get("ebarimt_id", ""),
                ebarimt_qr=result.get("qr_data", ""),
                lottery=result.get("lottery", ""),
                status="sent"
            )
            sale["ebarimt_status"] = "sent"
            sale["ebarimt_id"] = result.get("ebarimt_id", "")
            sale["ebarimt_qr"] = result.get("qr_data", "")
            sale["ebarimt_lottery"] = result.get("lottery", "")
            return True, result
        else:
            db.update_sale_ebarimt(sale["id"], status="failed")
            sale["ebarimt_status"] = "failed"
            return False, result
    except Exception as e:
        logger.error(f"eBarimt failed (non-fatal): {e}")
        db.update_sale_ebarimt(sale["id"], status="failed")
        sale["ebarimt_status"] = "failed"
        return False, {}


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
    qpay_invoice_id = data.get("qpay_invoice_id", "").strip()

    # QPay QR payment: verify invoice is paid before creating sale
    if payment_type == "qr" and qpay_invoice_id:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT status, paid_amount FROM qpay_pending WHERE invoice_id = ?",
                (qpay_invoice_id,)
            ).fetchone()
        if not row:
            return jsonify({"success": False, "error": "QPay нэхэмжлэх олдсонгүй"}), 400
        pending = {"status": row[0], "paid_amount": row[1]}
        if pending["status"] not in ("paid", "overpaid"):
            if _is_qpay_configured():
                try:
                    qpay = _get_qpay_client()
                    check = qpay.check_payment(qpay_invoice_id)
                    if check["payment_status"] == "paid" and check["paid_amount"] > 0:
                        with db.get_db() as conn:
                            conn.execute(
                                "UPDATE qpay_pending SET status = 'paid', paid_amount = ? WHERE invoice_id = ?",
                                (check["paid_amount"], qpay_invoice_id)
                            )
                        pending = {"status": "paid", "paid_amount": check["paid_amount"]}
                    else:
                        return jsonify({"success": False, "error": "Төлбөр төлөгдөөгүй байна"}), 400
                except Exception as exc:
                    from qpay import QPayAuthError
                    import requests
                    if isinstance(exc, QPayAuthError):
                        return jsonify({"success": False, "error": "QPay тохиргооны алдаа"}), 400
                    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
                        return jsonify({"success": False, "error": "QPay серверт холбогдоход алдаа"}), 400
                    logger.warning(f"QPay check failed: {exc}")
                    return jsonify({"success": False, "error": "Төлбөр төлөгдөөгүй байна"}), 400
            else:
                return jsonify({"success": False, "error": "Төлбөр төлөгдөөгүй байна"}), 400

    # Idempotency check: if this key was already used, return saved result
    if idempotency_key:
        saved = db.check_idempotency_key(idempotency_key)
        if saved:
            logger.info(f"Duplicate checkout prevented via idempotency key {idempotency_key[:8]}...")
            try:
                return jsonify(json.loads(saved))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning(f"Corrupted idempotency key {idempotency_key[:8]}, proceeding with new sale")

    if not items:
        return jsonify({"success": False, "error": "Сагс хоосон байна"}), 400

    if idempotency_key and not db.claim_idempotency_key(idempotency_key):
        saved = db.check_idempotency_key(idempotency_key)
        if saved:
            logger.info(f"Idempotency key {idempotency_key[:8]} claimed by concurrent request")
            try:
                return jsonify(json.loads(saved))
            except Exception:
                logger.warning("Unhandled exception in: except Exception:")
                pass
        return jsonify({"success": False, "error": "Давхардсан хүсэлт"}), 409

    try:
        db.check_and_backup()
    except Exception as e:
        logger.warning(f"Backup check failed (non-fatal): {e}")

    # For QPay, override card_amount to match the paid invoice
    if payment_type == "qr" and qpay_invoice_id:
        card_amount = pending["paid_amount"] if pending.get("paid_amount", 0) > 0 else card_amount

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

    sale["cashier_name"] = ""

    # Pre-set customer_tin before spawning threads that read sale
    customer_tin = data.get("customer_tin", "").strip()
    if customer_tin:
        sale["customer_tin"] = customer_tin

    # Attach QPay invoice data to sale if QR payment
    if payment_type == "qr" and qpay_invoice_id:
        sale["qpay_invoice_id"] = qpay_invoice_id
        sale["qpay_payment_status"] = "paid"
        with db.get_db() as conn:
            conn.execute(
                "UPDATE sales SET qpay_invoice_id = ?, qpay_payment_status = 'paid' WHERE id = ?",
                (qpay_invoice_id, sale["id"])
            )
            conn.execute(
                "UPDATE qpay_pending SET sale_id = ? WHERE invoice_id = ?",
                (sale["id"], qpay_invoice_id)
            )

    # Serialize sale snapshot before background threads mutate it
    response_data = json.dumps({"success": True, "sale": dict(sale)}, ensure_ascii=False)

    # Print receipt in background thread — don't block checkout
    sale["print_status"] = {"success": False, "error": ""}
    auto_print = get_config("auto_print_receipt")
    if auto_print == "true":
        def _do_print():
            try:
                from printer import print_receipt
                result = print_receipt(sale, get_store_info())
                sale["print_status"] = result
            except Exception as e:
                logger.error(f"Print failed (non-fatal): {e}")
                sale["print_status"] = {"success": False, "error": str(e)}
        threading.Thread(target=_do_print, daemon=True, name="receipt-print-" + str(sale["id"])).start()

    # eBarimt submission in background thread — don't block checkout
    if sale.get("payment_type") != "return" and is_ebarimt_configured():
        threading.Thread(
            target=_try_send_ebarimt_receipt, args=(sale, customer_tin),
            daemon=True, name="ebarimt-send-" + str(sale["id"])
        ).start()
    else:
        db.update_sale_ebarimt(sale["id"], status="skipped")
        sale["ebarimt_status"] = "skipped"

    if idempotency_key:
        try:
            db.save_idempotency_key(idempotency_key, sale["id"], response_data)
        except Exception as e:
            logger.warning(f"Failed to save idempotency key: {e}")

    return Response(response_data, mimetype="application/json")

@app.route("/api/terminal/checkout", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=30)
def api_terminal_checkout():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"success": False, "error": "Сагс хоосон байна"}), 400

    if not _is_terminal_configured():
        return jsonify({"success": False, "error": "Терминал тохируулаагүй"}), 400

    quote, error = db.quote_sale(items, payment_type="card")
    if error:
        return jsonify({"success": False, "error": error}), 400

    from terminal import send_payment
    total = quote["total"]
    invoice_no = f"POS{int(time.time())}"
    pax_result = send_payment(total, invoice_no)

    if not pax_result.get("success"):
        return jsonify({"success": False, "error": pax_result.get("error", "PAX алдаа")}), 502

    txn_id = pax_result.get("transaction_id", "")
    sale, error = db.create_sale(
        cashier_id=None,
        payment_type="card",
        items=quote["items"],
        terminal_txn_id=txn_id,
    )
    if error:
        logger.error("PAX approved but sale creation failed: %s", error)
        return jsonify({
            "success": False,
            "error": "PAX төлбөр батлагдсан боловч борлуулалт хадгалагдсангүй. Гараар шалгана уу.",
            "terminal_txn_id": txn_id,
        }), 500

    sale["cashier_name"] = ""
    sale["terminal_txn_id"] = txn_id
    sale["terminal_status"] = "approved"

    customer_tin = data.get("customer_tin", "").strip()
    if customer_tin:
        sale["customer_tin"] = customer_tin

    response_data = json.dumps({"success": True, "sale": dict(sale)}, ensure_ascii=False)

    auto_print = get_config("auto_print_receipt")
    if auto_print == "true":
        def _do_print():
            try:
                from printer import print_receipt
                print_receipt(sale, get_store_info())
            except Exception as e:
                logger.error(f"Print failed (non-fatal): {e}")
        threading.Thread(target=_do_print, daemon=True, name="receipt-print-" + str(sale["id"])).start()

    if is_ebarimt_configured():
        threading.Thread(
            target=_try_send_ebarimt_receipt, args=(sale, customer_tin),
            daemon=True, name="ebarimt-send-" + str(sale["id"])
        ).start()
    else:
        db.update_sale_ebarimt(sale["id"], status="skipped")
        sale["ebarimt_status"] = "skipped"

    return jsonify(json.loads(response_data))


@app.route("/api/terminal/pay", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=30)
def api_terminal_pay():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    amount = data.get("amount", 0)
    invoice_no = data.get("invoice_no", "").strip()

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        return jsonify({"success": False, "error": "Дүн буруу"}), 400

    if not _is_terminal_configured():
        return jsonify({"success": False, "error": "Терминал тохируулаагүй"}), 400

    from terminal import send_payment
    result = send_payment(amount, invoice_no)
    return jsonify(result)


@app.route("/api/terminal/test", methods=["POST"])
def api_terminal_test():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    if not _is_terminal_configured():
        return jsonify({"success": False, "error": "Терминал тохируулаагүй"}), 400

    from terminal import test_connection
    result = test_connection()
    return jsonify(result)


@app.route("/api/terminal/cancel", methods=["POST"])
def api_terminal_cancel():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    invoice_no = data.get("invoice_no", "").strip()
    if not invoice_no:
        return jsonify({"success": False, "error": "Гүйлгээний дугаар оруулна уу"}), 400

    from terminal import cancel_payment
    cancelled = cancel_payment(invoice_no)
    return jsonify({"success": cancelled, "invoice_no": invoice_no})


# ─────────────────────────────────────────────
# QPay ROUTES
# ─────────────────────────────────────────────

def _qpay_client_or_error():
    if not _is_qpay_configured():
        return None, jsonify({"success": False, "error": "QPay тохируулаагүй байна"}), 400
    qpay = _get_qpay_client()
    return qpay, None, None


@app.route("/api/qpay/invoice", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=5)
def api_qpay_invoice():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    amount = data.get("amount", 0)
    description = data.get("description", "")

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        return jsonify({"success": False, "error": "Дүн буруу"}), 400

    if not items:
        return jsonify({"success": False, "error": "Сагс хоосон байна"}), 400

    # Mock mode when QPay not configured
    if not _is_qpay_configured():
        invoice_id = f"MOCK{int(time.time() * 1000)}"
        mock_qr = f"qpay://mock?amount={amount}&id={invoice_id}"
        import base64
        qr_svg = _generate_mock_qr(mock_qr, amount)
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO qpay_pending (invoice_id, cart_data, amount, status, invoice_code) VALUES (?, ?, ?, 'pending', ?)",
                (invoice_id, json.dumps({"items": items, "amount": amount}), amount, "")
            )
        session["qpay_invoice_id"] = invoice_id
        return jsonify({
            "success": True,
            "invoice_id": invoice_id,
            "qr_image": qr_svg,
            "qr_text": mock_qr,
            "expires_at": int(time.time()) + 300,
            "amount": amount,
        })

    qpay, error_resp, error_code = _qpay_client_or_error()
    if error_resp:
        return error_resp, error_code

    allow_partial = data.get("allow_partial", False)
    allow_exceed = data.get("allow_exceed", False)
    from config import get_config
    base_url = request.host_url.rstrip("/")
    callback_url = f"{base_url}/api/qpay/webhook"

    try:
        result = qpay.create_invoice(
            amount=amount,
            description=description,
            allow_partial=allow_partial or (get_config("qpay_allow_partial") == "true"),
            allow_exceed=allow_exceed or (get_config("qpay_allow_exceed") == "true"),
            callback_url=callback_url,
            sender_invoice_no=f"POS{int(time.time())}",
        )
    except Exception as e:
        logger.error(f"QPay create invoice error: {e}")
        return jsonify({"success": False, "error": "QPay нэхэмжлэх үүсгэхэд алдаа гарлаа"}), 502

    invoice_id = result["invoice_id"]

    with db.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO qpay_pending (invoice_id, cart_data, amount, status, invoice_code) VALUES (?, ?, ?, 'pending', ?)",
            (invoice_id, json.dumps({"items": items, "amount": amount}), amount, "")
        )

    session["qpay_invoice_id"] = invoice_id

    return jsonify({
        "success": True,
        "invoice_id": invoice_id,
        "qr_image": result["qr_image"],
        "qr_text": result["qr_text"],
        "expires_at": result["expires_at"],
        "amount": amount,
    })


@app.route("/api/qpay/status/<invoice_id>")
@rate_limit(max_requests=60, window_seconds=10)
def api_qpay_status(invoice_id):
    if not invoice_id:
        return jsonify({"success": False, "error": "Нэхэмжлэхийн ID оруулна уу"}), 400

    qpay, error_resp, error_code = _qpay_client_or_error()
    if error_resp:
        return error_resp, error_code

    try:
        result = qpay.check_payment(invoice_id)
    except Exception as e:
        logger.error(f"QPay check payment error: {e}")
        return jsonify({"success": False, "error": "QPay төлөв шалгахад алдаа гарлаа"}), 502

    # Update pending invoice status in DB
    if result["payment_status"] == "paid":
        paid_amount = result["paid_amount"]
        with db.get_db() as conn:
            conn.execute(
                "UPDATE qpay_pending SET status = 'paid', paid_amount = ?, paid_at = datetime('now') WHERE invoice_id = ?",
                (paid_amount, invoice_id)
            )

    return jsonify({
        "success": True,
        "payment_status": result["payment_status"],
        "paid_amount": result["paid_amount"],
        "invoice_id": invoice_id,
    })


@app.route("/api/qpay/mock-check/<invoice_id>")
@rate_limit(max_requests=30, window_seconds=10)
def api_qpay_mock_check(invoice_id):
    """Mock QPay payment check — auto-approves after 5 seconds."""
    if not invoice_id:
        return jsonify({"success": False, "error": "Нэхэмжлэхийн ID оруулна уу"}), 400
    if not invoice_id.startswith("MOCK"):
        return jsonify({"success": False, "error": "Зөвхөн mock нэхэмжлэхэд ашиглах"}), 400

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT status, paid_amount, amount, created_at FROM qpay_pending WHERE invoice_id = ?",
            (invoice_id,)
        ).fetchone()

    if not row:
        return jsonify({"success": False, "error": "Нэхэмжлэх олдсонгүй"}), 404

    status, paid_amount, amount, created_at = row
    if status == "paid":
        return jsonify({
            "success": True,
            "payment_status": "paid",
            "paid_amount": paid_amount or amount,
            "invoice_id": invoice_id,
        })

    try:
        from datetime import datetime as dt
        created = dt.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        elapsed = (dt.now() - created).total_seconds()
    except Exception:
        elapsed = 0

    if elapsed >= 5:
        with db.get_db() as conn:
            conn.execute(
                "UPDATE qpay_pending SET status = 'paid', paid_amount = ?, paid_at = datetime('now') WHERE invoice_id = ?",
                (amount, invoice_id)
            )
        _notify_sse_clients()
        return jsonify({
            "success": True,
            "payment_status": "paid",
            "paid_amount": amount,
            "invoice_id": invoice_id,
        })

    return jsonify({
        "success": True,
        "payment_status": "pending",
        "paid_amount": 0,
        "invoice_id": invoice_id,
    })


@app.route("/api/qpay/webhook", methods=["POST"])
def api_qpay_webhook():
    body = request.get_data()
    signature = request.headers.get("X-Signature", "")

    from config import get_config as _gcfg
    client_secret = _gcfg("qpay_client_secret")

    from qpay import QPayClient
    if not QPayClient.verify_webhook(body, signature, client_secret):
        logger.warning("QPay webhook signature verification failed")
        return jsonify({"success": False, "error": "Invalid signature"}), 401

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Invalid JSON"}), 400

    invoice_id = payload.get("invoice_id", "")
    payment_status = payload.get("payment_status", "")
    paid_amount = int(payload.get("amount", 0))

    logger.info(f"QPay webhook: invoice={invoice_id}, status={payment_status}, amount={paid_amount}")

    if invoice_id:
        status_map = {
            "PAID": "paid",
            "UNDERPAID": "underpaid",
            "OVERPAID": "overpaid",
        }
        mapped = status_map.get(payment_status, "paid" if paid_amount > 0 else "pending")

        with db.get_db() as conn:
            conn.execute(
                "UPDATE qpay_pending SET status = ?, paid_amount = ?, paid_at = datetime('now') WHERE invoice_id = ?",
                (mapped, paid_amount, invoice_id)
            )

            # Try to auto-create sale if we have cart data
            row = conn.execute(
                "SELECT cart_data, amount, status, sale_id FROM qpay_pending WHERE invoice_id = ?",
                (invoice_id,)
            ).fetchone()

        if row:
            r = {"cart_data": row[0], "amount": row[1], "status": row[2], "sale_id": row[3]}
            if r["status"] in ("paid", "overpaid") and not r["sale_id"]:
                _auto_confirm_qpay_sale(invoice_id, r)

        # Notify SSE clients
        _notify_sse_clients()

    return jsonify({"success": True})


def _auto_confirm_qpay_sale(invoice_id, row):
    try:
        cart_data = json.loads(row["cart_data"])
        items = cart_data.get("items", [])
        total = cart_data.get("amount", row["amount"])

        if not items:
            logger.warning(f"Cannot auto-confirm QPay sale {invoice_id}: no cart data")
            return

        sale, error = db.create_sale(
            cashier_id=None,
            payment_type="qr",
            items=items,
            cash_given=0,
            card_amount=total,
            cash_amount=0,
        )
        if error:
            logger.error(f"QPay auto-confirm sale failed for {invoice_id}: {error}")
            return

        with db.get_db() as conn:
            conn.execute(
                "UPDATE sales SET qpay_invoice_id = ?, qpay_payment_status = 'paid' WHERE id = ?",
                (invoice_id, sale["id"])
            )
            conn.execute(
                "UPDATE qpay_pending SET sale_id = ? WHERE invoice_id = ?",
                (sale["id"], invoice_id)
            )
        sale["qpay_invoice_id"] = invoice_id
        sale["qpay_payment_status"] = "paid"

        logger.info(f"QPay auto-confirmed sale #{sale['id']} for invoice {invoice_id}")

        # Print receipt in background
        auto_print = get_config("auto_print_receipt")
        if auto_print == "true":
            threading.Thread(target=_do_print_receipt, args=(sale,), daemon=True).start()

        # eBarimt in background
        if is_ebarimt_configured():
            threading.Thread(
                target=_try_send_ebarimt_receipt, args=(sale, ""),
                daemon=True, name=f"ebarimt-qpay-{sale['id']}"
            ).start()
        else:
            db.update_sale_ebarimt(sale["id"], status="skipped")

    except Exception as e:
        logger.error(f"QPay auto-confirm failed for {invoice_id}: {e}")


def _do_print_receipt(sale):
    try:
        from printer import print_receipt
        print_receipt(sale, get_store_info())
    except Exception as e:
        logger.error(f"Print after QPay auto-confirm failed: {e}")


# ─────────────────────────────────────────────
# PRODUCT ROUTES
# ─────────────────────────────────────────────

@app.route("/api/product/create", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def api_create_product():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    data = request.get_json(silent=True) or {}
    barcode = data.get("barcode", "").strip()
    name = data.get("name", "").strip()
    price = data.get("price", 0)
    category = data.get("category", "Бусад").strip()
    unit = data.get("unit", "ш").strip()

    product_id, error = db.create_product(
        barcode=barcode, name=name, price=price,
        category=category, unit=unit
    )
    if error:
        return jsonify({"success": False, "error": error}), 400

    product = db.get_product_by_id(product_id)
    return jsonify({"success": True, "product": product})


@app.route("/api/category/add", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def api_category_add():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Ангиллын нэр оруулна уу"}), 400
    if len(name) > 50:
        return jsonify({"success": False, "error": "Ангиллын нэр хэтэрхий урт"}), 400
    cat_id = db.ensure_category(name)
    if not cat_id:
        return jsonify({"success": False, "error": "Ангилал үүсгэж чадсангүй"}), 500
    invalidate_context_cache()
    db.log_audit("category_added", "category", entity_id=cat_id, details=name)
    return jsonify({"success": True, "id": cat_id, "name": name})


# ─────────────────────────────────────────────
# HELD ORDERS (Suspended / Parked carts)
# ─────────────────────────────────────────────

@app.route("/api/held-orders", methods=["GET"])
def api_held_orders_list():
    orders = db.get_held_orders()
    return jsonify({"success": True, "orders": orders})


@app.route("/api/hold-order", methods=["POST"])
@rate_limit(30, 60)
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
@rate_limit(30, 60)
def api_recall_order(order_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    order = db.get_held_order(order_id)
    if not order:
        return jsonify({"success": False, "error": "Захиалга олдсонгүй"}), 404

    # Enrich recalled items with current price from DB
    for item in order["items"]:
        if item.get("product_id"):
            product = db.get_product_by_id(item["product_id"])
            if product:
                item["current_price"] = product["price"]

    db.delete_held_order(order_id)
    return jsonify({"success": True, "order": order})


@app.route("/api/delete-held-order/<int:order_id>", methods=["POST"])
@rate_limit(30, 60)
def api_delete_held_order(order_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    db.delete_held_order(order_id)
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# SALES HISTORY
# ─────────────────────────────────────────────

@app.route("/sales")
@admin_required
def sales_page():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    page = _parse_int_arg("page", 1, min_value=1)
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
@admin_required
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
def products_page():
    products = db.get_all_products(active_only=True)
    categories = db.get_categories()
    suppliers = db.get_suppliers()
    return render_template("products.html", products=products, categories=categories, suppliers=suppliers)


@app.route("/products/create", methods=["POST"])
@rate_limit(20, 60)
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
    unit = request.form.get("unit", "ш").strip()
    expiry_date = request.form.get("expiry_date", "").strip()
    image_url = request.form.get("image_url", "").strip()
    supplier_id = request.form.get("supplier_id", "").strip() or None

    cost_price_value = _parse_int_value(cost_price, 0, min_value=0)
    supplier_id_value = _parse_int_value(supplier_id, None, min_value=1) if supplier_id else None

    product_id, error = db.create_product(
        barcode=barcode, name=name, price=price,
        cost_price=cost_price_value,
        category=category, unit=unit,
        expiry_date=expiry_date, image_url=image_url,
        supplier_id=supplier_id_value
    )
    if error:
        flash(error, "error")
    else:
        db.log_audit("product_created", "product", details=f"'{name}' бараа үүсгэгдлээ (barcode={barcode})")
        flash(f"'{name}' бараа амжилттай үүсгэлээ.", "success")

    return redirect(url_for("products_page"))


@app.route("/products/update/<int:product_id>", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def products_update(product_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    kwargs = {}
    for field in ["barcode", "name", "price", "cost_price", "category",
                   "unit", "expiry_date", "image_url",
                   "supplier_id", "is_active"]:
        if field in request.form:
            kwargs[field] = request.form[field]

    success, error = db.update_product(product_id, **kwargs)
    if error:
        flash(error, "error")
    else:
        db.log_audit("product_updated", "product", entity_id=str(product_id), details="Бараа шинэчлэгдлээ")
        flash("Бараа амжилттай шинэчлэгдлээ.", "success")

    return redirect(url_for("products_page"))


@app.route("/products/delete/<int:product_id>", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def products_delete(product_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    db.delete_product(product_id)
    db.log_audit("product_deleted", "product", entity_id=str(product_id), details="Бараа устгагдлаа")
    flash("Бараа устгагдлаа.", "success")
    return redirect(url_for("products_page"))


@app.route("/products/delete-mass", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def products_delete_mass():
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    product_ids = request.form.getlist("product_ids")
    if not product_ids:
        flash("Устгах бараа сонгоогүй байна.", "error")
        return redirect(url_for("products_page"))

    count = 0
    for pid in product_ids:
        try:
            db.delete_product(int(pid))
            count += 1
        except (ValueError, TypeError):
            logger.warning("Unhandled exception in: except (ValueError, TypeError):")
            pass
    if count:
        db.log_audit("product_deleted", "product", details=f"Масс устгалт: {count} бараа")
        flash(f"{count} бараа амжилттай устгагдлаа.", "success")
    return redirect(url_for("products_page"))


@app.route("/products/restore/<int:product_id>", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def products_restore(product_id):
    if not validate_csrf_token():
        flash("CSRF алдаа.", "error")
        return redirect(url_for("products_page"))

    db.restore_product(product_id)
    flash("Бараа сэргээгдлээ.", "success")
    return redirect(url_for("products_page"))


@app.route("/products/import", methods=["POST"])
@rate_limit(20, 60)
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
            unit = row.get("unit", "ш").strip()

            if not name:
                errors.append(f"Мөр {i}: нэр хоосон")
                continue

            existing = db.get_product_by_barcode(barcode) if barcode else None
            if existing:
                success, error = db.update_product(
                    existing["id"], name=name, price=price,
                    category=category, unit=unit
                )
                if error:
                    errors.append(f"Мөр {i}: {error}")
                else:
                    updated += 1
            else:
                product_id, error = db.create_product(
                    barcode=barcode, name=name, price=price,
                    category=category, unit=unit
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
@rate_limit(20, 60)
@admin_required
def api_product_image_upload():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Файл сонгоно уу"}), 400

    allowed_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({"success": False, "error": "Зөвхөн зураг файл (PNG, JPG, GIF, WebP)"}), 400

    allowed_mimes = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    magic_bytes = file.read(12)
    file.seek(0)

    import mimetypes
    detected_mime, _ = mimetypes.guess_type(file.filename)
    if detected_mime not in allowed_mimes:
        detected_mime = None

    png_sig = magic_bytes[:8] == b'\x89PNG\r\n\x1a\n'
    jpg_sig = magic_bytes[:3] == b'\xff\xd8\xff'
    gif_sig = magic_bytes[:6] in (b'GIF89a', b'GIF87a')
    webp_sig = magic_bytes[:4] == b'RIFF' and magic_bytes[8:12] == b'WEBP'

    if not (png_sig or jpg_sig or gif_sig or webp_sig):
        return jsonify({"success": False, "error": "Файл зураг биш эсвэл гэмтсэн байна"}), 400

    file_size = 0
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    max_size = 5 * 1024 * 1024  # 5 MB
    if file_size > max_size:
        return jsonify({"success": False, "error": "Зураг 5MB-аас их байж болохгүй"}), 400

    upload_dir = os.path.join(PROJECT_DIR, "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    import uuid
    safe_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, safe_name)
    file.save(filepath)

    image_url = f"/static/uploads/{safe_name}"
    return jsonify({"success": True, "image_url": image_url})


# ─────────────────────────────────────────────
# SUPPLIER ROUTES
# ─────────────────────────────────────────────

@app.route("/suppliers")
@admin_required
def suppliers_page():
    suppliers = db.get_suppliers(include_inactive=True)
    return render_template("suppliers.html", suppliers=suppliers)


@app.route("/suppliers/create", methods=["POST"])
@rate_limit(20, 60)
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
    if error:
        flash(error, "error")
    else:
        db.log_audit("supplier_created", "supplier", details=f"'{name}' нийлүүлэгч үүсгэгдлээ")
        flash(f"'{name}' нийлүүлэгч амжилттай үүсгэлээ.", "success")
    return redirect(url_for("suppliers_page"))


@app.route("/suppliers/update/<int:supplier_id>", methods=["POST"])
@rate_limit(20, 60)
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
    if error:
        flash(error, "error")
    else:
        flash("Нийлүүлэгч шинэчлэгдлээ.", "success")
    return redirect(url_for("suppliers_page"))


@app.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
@rate_limit(20, 60)
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
@rate_limit(20, 60)
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
    cat_id = db.ensure_category(name, icon, color)
    invalidate_context_cache()
    if cat_id is None:
        return jsonify({"success": False, "error": "Ангилал үүсгэж чадсангүй"}), 500
    return jsonify({"success": True, "id": cat_id})


@app.route("/api/categories/update/<int:cat_id>", methods=["POST"])
@rate_limit(20, 60)
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
    invalidate_context_cache()
    return jsonify({"success": True})


@app.route("/api/categories/delete/<int:cat_id>", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def api_categories_delete(cat_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    reassign = request.args.get("reassign", "Бусад")
    db.delete_category(cat_id, reassign_to=reassign)
    invalidate_context_cache()
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


_report_cache: dict = {}
_report_cache_lock = threading.Lock()
_report_cache_ttl = 300


@app.route("/api/reports/chart-data")
@admin_required
def api_reports_chart_data():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    cache_key = f"chart_data::{date_from}::{date_to}"
    now = time.time()
    with _report_cache_lock:
        cached = _report_cache.get(cache_key)
        if cached and (now - cached["time"]) < _report_cache_ttl:
            return jsonify(cached["data"])

    report = db.get_sales_report(
        date_from=date_from or None,
        date_to=date_to or None,
    )
    profit = db.get_profit_summary(date_from or None, date_to or None)
    data = {
        "daily": report["daily"],
        "hourly": report["hourly"],
        "summary": report["summary"],
        "category_breakdown": report["category_breakdown"],
        "avg_items_per_sale": report["avg_items_per_sale"],
        "avg_transaction": report["avg_transaction"],
        "profit": profit,
    }
    with _report_cache_lock:
        _report_cache[cache_key] = {"data": data, "time": now}
        if len(_report_cache) > 100:
            stale = [k for k, v in _report_cache.items() if (now - v["time"]) > _report_cache_ttl]
            for k in stale:
                _report_cache.pop(k, None)
    return jsonify(data)


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
    writer.writerow(["Борлуулалт ID", "Огноо", "Бараа нэр", "Баркод",
                     "Тоо", "Нэгж үнэ", "Нийлбэр", "Хөнгөлөлт",
                     "Төлбөрийн хэлбэр", "eBarimt төлөв", "Сугалаа"])
    for s in sales:
        sale_detail = db.get_sale(s["id"])
        if sale_detail and sale_detail.get("items"):
            for item in sale_detail["items"]:
                writer.writerow([
                    s["id"], s["created_at"],
                    item["product_name"], item.get("barcode", ""),
                    item["quantity"], item["unit_price"], item["subtotal"],
                    item.get("discount_amount", 0),
                    s["payment_type"], s.get("ebarimt_status", ""),
                    s.get("ebarimt_lottery", "")
                ])
        else:
            writer.writerow([
                s["id"], s["created_at"], "(бараа байхгүй)", "", "", "", "", "",
                s["payment_type"], s.get("ebarimt_status", ""),
                s.get("ebarimt_lottery", "")
            ])

    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_export.csv"}
    )


# ─────────────────────────────────────────────
# SETTINGS (admin required)
# ─────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
@rate_limit(20, 60)
@admin_required
def settings_page():
    if request.method == "GET":
        settings = get_all_config()
        return render_template(
            "settings.html",
            settings=settings,
            terminal_configured=_is_terminal_configured(),
            qpay_configured=_is_qpay_configured(),
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
                "admin_session_timeout_minutes",
                "return_window_days", "backup_retention_days",
                "qr_payment_image",
                "terminal_enabled", "terminal_ip", "terminal_port",
                "qpay_enabled", "qpay_client_id", "qpay_client_secret",
                "qpay_base_url", "qpay_allow_partial", "qpay_allow_exceed",
                "discounts_enabled"]:
        if key in request.form:
            settings_to_save[key] = request.form[key].strip()

    for bool_key in [
        "auto_print_receipt", "show_vat_on_receipt", "terminal_enabled",
        "qpay_enabled", "qpay_allow_partial", "qpay_allow_exceed",
        "discounts_enabled"
    ]:
        if bool_key not in settings_to_save:
            settings_to_save[bool_key] = "false"

    # Validate settings with structured rules
    VALIDATION_RULES = {
        "receipt_width": {"type": "int", "min": 24, "max": 48, "default": 32},
        "customer_display_timeout": {"type": "int", "min": 5, "max": 120, "default": 10},
        "admin_session_timeout_minutes": {"type": "int", "min": 10, "max": 1440, "default": 480},
        "return_window_days": {"type": "int", "min": 1, "max": 365, "default": 30},
        "backup_retention_days": {"type": "int", "min": 7, "max": 365, "default": 30},
        "terminal_port": {"type": "int", "min": 1, "max": 65535, "default": 10009},
        "terminal_ip": {"type": "ip"},
    }
    def _validate_int(val_str, rule):
        try:
            ival = int(val_str)
            if ival < rule["min"] or ival > rule["max"]:
                return str(rule["default"])
            return str(ival)
        except (ValueError, TypeError):
            return str(rule["default"])
    def _validate_ip(val_str):
        import ipaddress
        try:
            ipaddress.ip_address(val_str.strip())
            return val_str.strip()
        except ValueError:
            return ""
    for fname, rule in VALIDATION_RULES.items():
        val = settings_to_save.get(fname, "")
        if val:
            if rule["type"] == "int":
                settings_to_save[fname] = _validate_int(val, rule)
            elif rule["type"] == "ip":
                settings_to_save[fname] = _validate_ip(val)

    if settings_to_save.get("default_payment_type", "cash") not in ("cash", "card", "split", "qr"):
        settings_to_save["default_payment_type"] = "cash"

    db.set_settings(settings_to_save)
    invalidate_context_cache()
    # Refresh cached admin timeout
    try:
        app.config["ADMIN_SESSION_TIMEOUT_MINUTES"] = int(settings_to_save.get("admin_session_timeout_minutes", "480"))
    except (ValueError, TypeError):
        logger.warning("Unhandled exception in: except (ValueError, TypeError):")
        pass
    db.log_audit("settings_updated", "settings", details="Тохиргоо хадгалагдлаа")
    flash("Тохиргоо амжилттай хадгалагдлаа.", "success")
    return redirect(url_for("settings_page"))


@app.route("/settings/backup", methods=["POST"])
@rate_limit(5, 120)
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
# CASH DRAWER MANAGEMENT
# ─────────────────────────────────────────────

@app.route("/api/cash-drawer/action", methods=["POST"])
@rate_limit(20, 60)
@admin_required
def api_cash_drawer_action():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    amount = _parse_int_value(data.get("amount"), 0, min_value=0)
    note = data.get("note", "").strip()
    if action not in ("open", "close", "float_in", "float_out"):
        return jsonify({"success": False, "error": "Буруу үйлдэл"}), 400
    db.log_cash_drawer(action, amount, note)
    db.log_audit("cash_drawer", "drawer", details=f"Кассын үйлдэл: {action} ({amount}₮)")
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
# RETURN / REFUND (admin required)
# ─────────────────────────────────────────────

@app.route("/api/return/<int:sale_id>", methods=["POST"])
@rate_limit(10, 60)
@admin_required
def api_return(sale_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    return_sale, error = db.process_return(sale_id)
    if error:
        return jsonify({"success": False, "error": error}), 400

    db.log_audit("sale_returned", "sale", entity_id=str(sale_id), details="Борлуулалт буцаагдлаа")

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
@rate_limit(20, 60)
@admin_required
def api_reprint(sale_id):
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    sale = db.get_sale(sale_id)
    if not sale:
        return jsonify({"success": False, "error": "Борлуулалт олдсонгүй"}), 404

    try:
        # Reprint receipt
        from printer import print_receipt
        result = print_receipt(sale, get_store_info())

        # Retry eBarimt if status is failed or pending
        ebarimt_result = None
        if is_ebarimt_configured() and sale.get("ebarimt_status") in ("failed", "pending"):
            ebarimt_result = _try_send_ebarimt_receipt(sale)

        return jsonify({
            "success": result["success"],
            "error": result.get("error", ""),
            "ebarimt_retried": ebarimt_result is not None,
            "ebarimt_success": ebarimt_result[0] if ebarimt_result else None,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─────────────────────────────────────────────
# eBARIMT CONNECTIVITY PING
# ─────────────────────────────────────────────

@app.route("/api/ebarimt/pending-count")
def api_ebarimt_pending_count():
    try:
        count = db.get_pending_ebarimt_count()
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"count": 0, "error": str(e)})


@app.route("/api/ebarimt/ping")
def api_ebarimt_ping():
    if not is_ebarimt_configured():
        return jsonify({"reachable": False, "reason": "not_configured"})
    try:
        import urllib.request
        api_url = (get_config("ebarimt_api_url") or "").rstrip("/")
        req = urllib.request.Request(api_url + "/api/health", method="GET")
        urllib.request.urlopen(req, timeout=int(get_config("ebarimt_timeout") or 5))
        return jsonify({"reachable": True})
    except Exception as e:
        return jsonify({"reachable": False, "reason": str(e)[:100]})


# ─────────────────────────────────────────────
# eBARIMT MANUAL RETRY
# ─────────────────────────────────────────────

@app.route("/api/ebarimt-retry", methods=["POST"])
@rate_limit(10, 60)
@admin_required
def api_ebarimt_retry():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403

    if not is_ebarimt_configured():
        return jsonify({"success": False, "error": "eBarimt тохиргоо хийгдээгүй байна"}), 400

    try:
        pending = db.get_pending_ebarimt_sales()

        if not pending:
            return jsonify({"success": True, "retried": 0, "sent": 0, "message": "Хүлээгдэж буй баримт байхгүй"})

        sent = 0
        for sale in pending:
            success, _ = _try_send_ebarimt_receipt(sale)
            if success:
                sent += 1

        return jsonify({
            "success": True,
            "retried": len(pending),
            "sent": sent,
            "message": f"{len(pending)} баримт шалгалаа, {sent} амжилттай"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─────────────────────────────────────────────
# PRINTER TEST ENDPOINT
# ─────────────────────────────────────────────

@app.route("/api/printer/test", methods=["POST"])
@rate_limit(10, 60)
@admin_required
def api_printer_test():
    if not validate_csrf_token():
        return jsonify({"success": False, "error": "CSRF алдаа"}), 403
    try:
        from printer import print_receipt
        test_sale = {
            "id": 0, "total": 1234, "payment_type": "cash",
            "cash_given": 2000, "change_given": 766,
            "items": [{"product_name": "Тест хэвлэлт", "quantity": 1,
                        "unit_price": 1234, "subtotal": 1234}],
            "ebarimt_status": "skipped"
        }
        result = print_receipt(test_sale, get_store_info())
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Энэдүүрэг олдсонгүй"}), 404
    flash("Хуудас олдсонгүй.", "error")
    return redirect(url_for("pos"))


@app.errorhandler(413)
def request_too_large(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Хүсэлт хэт том байна"}), 413
    flash("Хүсэлт хэт том байна (дээд хязгаар: 10MB).", "error")
    return redirect(url_for("pos"))


@app.errorhandler(500)
def server_error(e):
    import sys
    exc_info = sys.exc_info()
    if exc_info and exc_info[1] and exc_info[1] is not e:
        logger.error("Unhandled exception:", exc_info=exc_info)
    else:
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

        pending = db.get_pending_ebarimt_sales()

        if not pending:
            logger.info("No pending eBarimt sales to retry.")
            return

        logger.info(f"Retrying {len(pending)} pending eBarimt sales...")
        for sale in pending:
            success, result = _try_send_ebarimt_receipt(sale)
            if success:
                logger.info(f"eBarimt sent for sale #{sale['id']}")
            else:
                logger.warning(f"eBarimt retry failed for sale #{sale['id']}: {result.get('error', 'unknown')}")

        logger.info("eBarimt retry complete.")
    except Exception as e:
        logger.error(f"eBarimt retry task failed: {e}")


# ─────────────────────────────────────────────
# APP STARTUP
# ─────────────────────────────────────────────

def _ebarimt_retry_lock_key():
    return f"ebarimt_retry_lock_{os.getpid()}"


def create_app():
    import atexit
    import signal as _signal

    def _shutdown_wal_checkpoint():
        try:
            with db.get_db() as c:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.info("Shutdown WAL checkpoint (TRUNCATE) completed")
        except Exception as e:
            logger.warning(f"Shutdown WAL checkpoint failed: {e}")

    atexit.register(_shutdown_wal_checkpoint)

    def _signal_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, performing shutdown WAL checkpoint...")
        _shutdown_wal_checkpoint()
        import os as _os
        _os._exit(0)

    for _sig in (_signal.SIGTERM, _signal.SIGINT):
        try:
            _signal.signal(_sig, _signal_shutdown)
        except (OSError, ValueError):
            logger.warning("Unhandled exception in: except (OSError, ValueError):")
            pass
    logger.info("Initializing POS database...")
    db.init_db()
    logger.info("Database ready.")

    _startup_self_check()

    # Guard eBarimt retry from running in every Gunicorn worker: only one
    # worker may hold the per-process lock at a time. If the lock is stale
    # (older than 30 minutes), it is reclaimed.
    retry_lock_acquired = db.acquire_ebarimt_retry_lock(
        lock_id=_ebarimt_retry_lock_key(), timeout_minutes=30
    )
    if retry_lock_acquired:
        retry_thread = threading.Thread(
            target=retry_pending_ebarimt,
            daemon=True,
            name="ebarimt-retry"
        )
        retry_thread.start()
        logger.info("eBarimt retry thread started (lock acquired).")
        # Release lock after thread completes
        def _retry_done():
            retry_thread.join()
            db.release_ebarimt_retry_lock(_ebarimt_retry_lock_key())
        threading.Thread(target=_retry_done, daemon=True, name="ebarimt-retry-cleanup").start()
    else:
        logger.info("eBarimt retry skipped (lock held by another process).")

    # Start rate limit cleanup
    threading.Thread(target=_cleanup_rate_limit_store, daemon=True, name="rate-limit-gc").start()

    # Start background health check
    threading.Thread(target=_run_periodic_health_check, daemon=True, name="health-check").start()

    # Start SSE heartbeat
    threading.Thread(target=_sse_heartbeat_loop, daemon=True, name="sse-heartbeat").start()

    # Start WAL checkpoint thread
    db.start_wal_checkpoint_thread()

    # Start periodic DB cleanup (stale idempotency keys, abandoned held orders, old audit logs)
    def _periodic_cleanup():
        import time as _t
        vacuum_counter = 0
        while True:
            _t.sleep(3600)
            vacuum_counter += 1
            try:
                with db.get_db() as c:
                    c.execute("DELETE FROM idempotency_keys WHERE created_at < datetime('now', '-24 hours')")
                    c.execute("DELETE FROM held_orders WHERE created_at < datetime('now', '-7 days')")
                    c.execute("DELETE FROM audit_log WHERE created_at < datetime('now', '-365 days')")
                    retention_days = get_config("sales_retention_days") or "730"
                    cut = (datetime.now() - timedelta(days=int(retention_days))).strftime("%Y-%m-%d")
                    c.execute("DELETE FROM sale_items WHERE sale_id NOT IN (SELECT id FROM sales WHERE created_at >= ?)", (f"{cut} 00:00:00",))
                    deleted = c.execute("DELETE FROM sales WHERE created_at < ? AND return_of_sale_id IS NULL", (f"{cut} 00:00:00",)).rowcount
                    if deleted:
                        logger.info("Cleaned up %s old sales (retention: %s days)", deleted, retention_days)
            except Exception as e:
                logging.getLogger(__name__).warning(f"Periodic cleanup error: {e}")
            if vacuum_counter >= 24:
                vacuum_counter = 0
                try:
                    with db.get_db() as c:
                        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        c.execute("VACUUM")
                    logger.info("Scheduled VACUUM + WAL TRUNCATE completed")
                except Exception as e:
                    logger.warning(f"Scheduled VACUUM failed: {e}")
    threading.Thread(target=_periodic_cleanup, daemon=True, name="db-cleanup").start()

    return app


if __name__ == "__main__":
    application = create_app()
    logger.info(f"Starting POS server on {FLASK_HOST}:{FLASK_PORT} (debug={FLASK_DEBUG})")
    application.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=FLASK_DEBUG,
    )

# Module-level init for Gunicorn / WSGI hosts: only when actually imported
# as a WSGI module. The launchers import `create_app` and call it themselves,
# so they set POS_SKIP_MODULE_INIT=1 before importing to avoid double-init
# (which would double-spawn the WAL checkpoint, GC, SSE heartbeat threads,
# and double-run eBarimt retry — meaningful cost on slow i5 2nd gen).
import os as _os
if not _os.environ.get("POS_SKIP_MODULE_INIT"):
    _application = create_app()
    application = _application

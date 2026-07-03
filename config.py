"""
config.py — Configuration layer for the POS system.

Reads settings from the database's settings table and provides
safe defaults for every configuration value. This module ensures
the application can start and function even if no settings have
been configured yet (first-run experience).
"""

import os
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# SAFE DEFAULTS — used when DB has no value
# ─────────────────────────────────────────────

DEFAULTS = {
    "store_name": "Моност",
    "store_address": "Улаанбаатар",
    "store_phone": "",
    "printer_port": "/dev/usb/lp0",
    "ebarimt_api_url": "",
    "ebarimt_ttd": "",
    "ebarimt_branch_id": "",
    "ebarimt_merchant_tin": "",
    "ebarimt_timeout": "5",
    "receipt_footer": "Баярлалаа! Дахин үйлчлүүлнэ үү.",
    "last_backup_date": "",
    "admin_password_hash": "",
    "default_payment_type": "cash",
    "auto_print_receipt": "true",
    "show_vat_on_receipt": "false",
    "show_stock_warnings": "true",
    "discounts_enabled": "false",
    "receipt_width": "32",
    "customer_display_timeout": "10",
    "customer_idle_message": "Тавтай морилно уу",
    "admin_session_timeout_minutes": "480",
    "ui_language": "mn",
    "theme": "auto",
    "db_sync_mode": "FULL",
    "return_window_days": "30",
    "backup_retention_days": "30",
    "sales_retention_days": "730",
    "terminal_enabled": "false",
    "terminal_ip": "",
    "terminal_port": "10009",
    "qpay_enabled": "false",
    "qpay_client_id": "",
    "qpay_client_secret": "",
    "qpay_base_url": "https://merchant.qpay.mn/v2",
    "qpay_timeout": "15",
    "qpay_allow_partial": "false",
    "qpay_allow_exceed": "false",
    # "low_perf_mode" — set to "true" on slow store computers (e.g. i5 2nd gen
    # on Linux Mint XFCE) to disable expensive CSS animations and backdrop-filter.
    "low_perf_mode": "false",
}

import threading as _threading  # noqa: E402 — kept near cache state for readability
import time as _time  # noqa: E402 — kept near cache state for readability

_settings_cache: dict = dict(DEFAULTS)
_settings_cache_lock = _threading.Lock()
_settings_cache_ttl = 30
_settings_last_load = 0.0

def _get_cached_settings():
    global _settings_cache, _settings_last_load
    now = _time.monotonic()
    if now - _settings_last_load > _settings_cache_ttl:
        with _settings_cache_lock:
            if now - _settings_last_load > _settings_cache_ttl:
                try:
                    from database import get_all_settings
                    fresh = dict(DEFAULTS)
                    fresh.update(get_all_settings())
                    _settings_cache = fresh
                    _settings_last_load = now
                except Exception as e:
                    logger.warning("Failed to load settings from DB (cache miss): %s", e)
    return _settings_cache


def invalidate_settings_cache():
    global _settings_last_load
    _settings_last_load = 0.0

# Flask configuration
def _generate_secret_key():
    """Generate a random secret key. Saved to DB for persistence across restarts."""
    import secrets
    return secrets.token_hex(32)

def _get_or_create_secret_key():
    env_key = os.environ.get("POS_SECRET_KEY", "")
    if env_key and env_key != "pos-secret-change-me-in-production-2024-mongolia":
        return env_key
    # Try DB-stored key first
    try:
        from database import get_setting
        db_key = get_setting("pos_secret_key", "")
        if db_key and len(db_key) >= 32:
            return db_key
    except Exception:
        pass
    # Generate and store a new key
    new_key = _generate_secret_key()
    try:
        from database import set_setting
        set_setting("pos_secret_key", new_key)
    except Exception:
        pass
    # Fallback: random key for this session (won't persist, but safe)
    if not env_key:
        return new_key
    return env_key

FLASK_SECRET_KEY = _get_or_create_secret_key()
FLASK_HOST = os.environ.get("POS_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("POS_PORT", "8765"))
FLASK_DEBUG = os.environ.get("POS_DEBUG", "0") == "1"


def get_config(key):
    """
    Get a configuration value from the database settings table.
    Falls back to DEFAULTS if the key is not found or DB is unavailable.

    This function imports database lazily to avoid circular imports
    and to handle the case where the DB hasn't been initialized yet.
    """
    try:
        return _get_cached_settings().get(key, DEFAULTS.get(key, ""))
    except Exception:
        return DEFAULTS.get(key, "")


def get_all_config():
    """
    Get all configuration values as a dict.
    Merges DB settings on top of defaults.
    """
    try:
        return dict(_get_cached_settings())
    except Exception:
        return dict(DEFAULTS)


def is_ebarimt_configured():
    """
    Check if eBarimt API credentials are configured.
    Returns True only if all required fields have non-empty values.
    Minimal check: api_url + merchant_tin + branch_id + ttd (pos_no).
    """
    api_url = get_config("ebarimt_api_url")
    merchant_tin = get_config("ebarimt_merchant_tin")
    ttd = get_config("ebarimt_ttd")
    branch_id = get_config("ebarimt_branch_id")
    return bool(api_url and merchant_tin and ttd and branch_id)


def get_printer_port():
    """Get the configured printer port path."""
    return get_config("printer_port")


def get_store_info():
    """Get store name, address, and phone as a dict."""
    return {
        "name": get_config("store_name"),
        "address": get_config("store_address"),
        "phone": get_config("store_phone"),
    }

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
    "store_name": "Миний дэлгүүр",
    "store_address": "Улаанбаатар",
    "store_phone": "",
    "printer_port": "/dev/usb/lp0",
    "low_stock_default": "5",
    "ebarimt_api_url": "",
    "ebarimt_ttd": "",
    "ebarimt_branch_id": "",
    "ebarimt_merchant_tin": "",
    "receipt_footer": "Баярлалаа! Дахин үйлчлүүлнэ үү.",
    "last_backup_date": "",
    "admin_password_hash": "",  # Empty = not set yet, user sets on first admin unlock
    "default_payment_type": "cash",
    "auto_print_receipt": "true",
    "show_vat_on_receipt": "false",
    "receipt_width": "32",
    "customer_display_timeout": "10",
    "customer_idle_message": "Тавтай морилно уу",
    "admin_session_timeout_minutes": "480",
    "theme": "auto",
    "db_sync_mode": "FULL",
    "return_window_days": "30",
}

# Flask configuration
def _generate_secret_key():
    """Generate a random secret key. Saved to DB for persistence across restarts."""
    import secrets
    import os as _os
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
FLASK_PORT = int(os.environ.get("POS_PORT", "5000"))
FLASK_DEBUG = os.environ.get("POS_DEBUG", "0") == "1"

# Session timeout: 8 hours in seconds
SESSION_TIMEOUT_SECONDS = 8 * 60 * 60


def get_config(key):
    """
    Get a configuration value from the database settings table.
    Falls back to DEFAULTS if the key is not found or DB is unavailable.

    This function imports database lazily to avoid circular imports
    and to handle the case where the DB hasn't been initialized yet.
    """
    try:
        from database import get_setting
        value = get_setting(key, DEFAULTS.get(key, ""))
        return value
    except Exception as e:
        logger.warning(f"Could not read setting '{key}' from DB: {e}")
        return DEFAULTS.get(key, "")


def get_all_config():
    """
    Get all configuration values as a dict.
    Merges DB settings on top of defaults.
    """
    config = dict(DEFAULTS)
    try:
        from database import get_all_settings
        db_settings = get_all_settings()
        config.update(db_settings)
    except Exception as e:
        logger.warning(f"Could not read settings from DB: {e}")
    return config


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


def is_admin_password_set():
    """
    Check if an admin password has been configured.
    Returns True if admin_password_hash is non-empty.
    """
    password_hash = get_config("admin_password_hash")
    return bool(password_hash)


def get_admin_password_hash():
    """Get the admin password hash from config."""
    return get_config("admin_password_hash")

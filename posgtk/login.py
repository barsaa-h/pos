"""
gtk/login.py — Admin login dialog with PIN/password + brute-force lockout.
Same logic as app.py:888-900 (5 failures = 15 minute lockout per IP).
"""

import time
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

logger = logging.getLogger("pos.gtk.login")

LOCKOUT_MINUTES = 15
MAX_ATTEMPTS = 5
_attempt_store = {}


def _is_locked_out(identifier="localhost"):
    now = time.time()
    entry = _attempt_store.get(identifier)
    if entry and entry["count"] >= MAX_ATTEMPTS:
        if now - entry["first_fail"] < LOCKOUT_MINUTES * 60:
            return True
        del _attempt_store[identifier]
    return False


def _record_failure(identifier="localhost"):
    now = time.time()
    entry = _attempt_store.get(identifier)
    if entry:
        entry["count"] += 1
    else:
        _attempt_store[identifier] = {"count": 1, "first_fail": now, "last_fail": now}


def _clear_attempts(identifier="localhost"):
    _attempt_store.pop(identifier, None)


class LoginDialog(Gtk.Dialog):
    def __init__(self, parent=None):
        super().__init__(
            title="Нэвтрэх",
            transient_for=parent,
            flags=Gtk.DialogFlags.MODAL,
        )
        self.set_default_size(320, 180)
        self.authenticated = False

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(24)
        content.set_margin_end(24)

        title = Gtk.Label(label="🔒 Админ нэвтрэх")
        title.get_style_context().add_class("title")
        title.set_margin_bottom(8)
        content.add(title)

        self.pin_entry = Gtk.Entry()
        self.pin_entry.set_visibility(False)
        self.pin_entry.set_max_length(6)
        self.pin_entry.set_placeholder_text("PIN код оруулна уу")
        self.pin_entry.set_activates_default(True)
        content.add(self.pin_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_no_show_all(True)
        content.add(self.error_label)

        self.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        self.add_button("Нэвтрэх", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        self.show_all()

    def do_response(self, response):
        if response == Gtk.ResponseType.OK:
            if _is_locked_out():
                remaining = int(LOCKOUT_MINUTES * 60 - (time.time() - _attempt_store.get("localhost", {}).get("first_fail", 0)))
                minutes = max(1, remaining // 60)
                self.error_label.set_label(f"Хэтэрхий олон буруу оролдлого.\n{minutes} минутын дараа дахин оролдоно уу.")
                self.error_label.show()
                self.pin_entry.grab_focus()
                self.stop_emission_by_name("response")
                return

            if self._verify_pin(self.pin_entry.get_text()):
                _clear_attempts()
                self.authenticated = True
                super().do_response(response)
            else:
                _record_failure()
                remaining = MAX_ATTEMPTS - _attempt_store.get("localhost", {}).get("count", 0)
                self.error_label.set_label(f"Буруу PIN код! Үлдсэн: {remaining}")
                self.error_label.show()
                self.pin_entry.set_text("")
                self.pin_entry.grab_focus()
                self.stop_emission_by_name("response")
        else:
            super().do_response(response)

    def _verify_pin(self, pin):
        if not pin:
            return False
        try:
            import database as db
            if db.verify_admin_password(pin):
                return True
        except Exception as e:
            logger.error(f"PIN verification error: {e}")
        return False

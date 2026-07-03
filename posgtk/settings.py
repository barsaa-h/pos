"""
posgtk/settings.py — Settings screen with card-based layout matching web.

Store info, payment, printer, display, security sections.
All changes go to DB via db.set_settings().
"""

import logging
import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.settings")


class SettingsScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_box.set_margin_start(16)
        header_box.set_margin_end(16)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(8)

        header = Gtk.Label(label="⚙️ Тохиргоо")
        header.get_style_context().add_class("page-title")
        header.set_halign(Gtk.Align.START)
        header_box.pack_start(header, True, True, 0)
        self.pack_start(header_box, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        form_box.set_margin_start(16)
        form_box.set_margin_end(16)
        form_box.set_margin_bottom(12)

        self._build_store_section(form_box)
        self._build_payment_section(form_box)
        self._build_printer_section(form_box)
        self._build_display_section(form_box)
        self._build_security_section(form_box)

        scrolled.add(form_box)
        self.pack_start(scrolled, True, True, 0)

        save_btn = Gtk.Button(label="✓ Бүх тохиргоог хадгалах")
        save_btn.set_margin_start(16)
        save_btn.set_margin_end(16)
        save_btn.set_margin_top(8)
        save_btn.set_margin_bottom(8)
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self._on_save_all)
        self.pack_end(save_btn, False, False, 0)

        self.show_all()
        GLib.idle_add(self._load_settings)

    def _make_section_card(self, parent, icon, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("settings-card")

        title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_bar.get_style_context().add_class("settings-card-title")
        title_bar.set_margin_start(18)
        title_bar.set_margin_end(18)
        title_bar.set_margin_top(14)
        title_bar.set_margin_bottom(14)

        icon_label = Gtk.Label(label=icon)
        icon_label.get_style_context().add_class("settings-card-icon")
        title_bar.pack_start(icon_label, False, False, 0)

        title_label = Gtk.Label(label=title)
        title_label.get_style_context().add_class("settings-card-title-text")
        title_label.set_xalign(0)
        title_bar.pack_start(title_label, False, False, 0)

        card.pack_start(title_bar, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.get_style_context().add_class("settings-section")
        body.set_margin_start(18)
        body.set_margin_end(18)
        body.set_margin_top(16)
        body.set_margin_bottom(16)
        card.pack_start(body, False, False, 0)

        parent.pack_start(card, False, False, 0)
        return body

    def _add_form_row(self, parent, label_text, widget):
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(12)

        lbl = Gtk.Label(label=label_text, xalign=0)
        lbl.get_style_context().add_class("form-label")
        grid.attach(lbl, 0, 0, 1, 1)

        widget.get_style_context().add_class("form-row-widget")
        widget.set_hexpand(True)
        grid.attach(widget, 1, 0, 1, 1)

        parent.pack_start(grid, False, False, 0)

    def _add_form_group(self, parent, label_text, widget):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        lbl = Gtk.Label(label=label_text, xalign=0)
        lbl.get_style_context().add_class("form-label")
        box.pack_start(lbl, False, False, 0)

        widget.get_style_context().add_class("form-row-widget")
        widget.set_hexpand(True)
        box.pack_start(widget, False, False, 0)

        parent.pack_start(box, False, False, 0)

    def _add_toggle_row(self, parent, label_text, default=False):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_hexpand(True)

        switch = Gtk.Switch()
        switch.set_active(default)
        switch.get_style_context().add_class("form-switch")
        box.pack_start(switch, False, False, 0)

        lbl = Gtk.Label(label=label_text, xalign=0)
        lbl.get_style_context().add_class("toggle-text")
        box.pack_start(lbl, True, True, 0)

        parent.pack_start(box, False, False, 0)
        return switch

    def _build_store_section(self, parent):
        body = self._make_section_card(parent, "🏪", "Дэлгүүрийн мэдээлэл")

        self._store_name = Gtk.Entry()
        self._store_name.set_placeholder_text("Дэлгүүрийн нэр")
        self._add_form_row(body, "Дэлгүүрийн нэр:", self._store_name)

        self._store_phone = Gtk.Entry()
        self._store_phone.set_placeholder_text("Утасны дугаар")
        self._add_form_row(body, "Утасны дугаар:", self._store_phone)

        self._store_address = Gtk.Entry()
        self._store_address.set_placeholder_text("Хаяг")
        self._add_form_group(body, "Хаяг:", self._store_address)

    def _build_payment_section(self, parent):
        body = self._make_section_card(parent, "💳", "Төлбөрийн тохиргоо")

        self._default_payment = Gtk.ComboBoxText()
        for val, label in [("cash", "💵 Бэлэн"), ("card", "💳 Карт"), ("qr", "📱 QR"), ("split", "🔀 Холимог")]:
            self._default_payment.append(val, label)
        self._add_form_row(body, "Анхны төлбөрийн төрөл:", self._default_payment)

        self._qr_payment_image = Gtk.Entry()
        self._qr_payment_image.set_placeholder_text("https://... эсвэл /static/uploads/...")
        self._add_form_group(body, "QR төлбөрийн зураг:", self._qr_payment_image)

    def _build_printer_section(self, parent):
        body = self._make_section_card(parent, "🖨", "Баримт тохиргоо")

        self._printer_port = Gtk.Entry()
        self._printer_port.set_placeholder_text("/dev/usb/lp0")
        self._add_form_group(body, "Хэвлэгчийн порт:", self._printer_port)

        self._receipt_footer = Gtk.Entry()
        self._receipt_footer.set_placeholder_text("Баримтын хөл хэсэг")
        self._add_form_group(body, "Баримтын хөл хэсэг:", self._receipt_footer)

        self._auto_print = self._add_toggle_row(body, "Борлуулалтын дараа автомат хэвлэх", True)

        self._show_vat = self._add_toggle_row(body, "НӨАТ-ыг тусад нь харуулах", False)

        self._receipt_width = Gtk.SpinButton.new_with_range(24, 48, 1)
        self._receipt_width.set_value(32)
        self._add_form_group(body, "Баримтын өргөн (тэмдэгт/мөр):", self._receipt_width)

    def _build_display_section(self, parent):
        body = self._make_section_card(parent, "🖥", "Дэлгэцийн тохиргоо")

        self._show_stock_warnings = self._add_toggle_row(body, "Бага/дууссан барааг тэмдэглэх", True)

        self._discounts_enabled = self._add_toggle_row(body, "Хямдрал идэвхжүүлэх", False)

        self._theme = Gtk.ComboBoxText()
        for val, label in [("auto", "🌓 Авто"), ("light", "☀️ Гэрэлтэй"), ("dark", "🌙 Бараан")]:
            self._theme.append(val, label)
        self._add_form_row(body, "Өнгөний горим:", self._theme)

        self._customer_display_timeout = Gtk.SpinButton.new_with_range(5, 120, 1)
        self._add_form_row(body, "Idle хугацаа (сек):", self._customer_display_timeout)

        self._customer_idle_message = Gtk.Entry()
        self._customer_idle_message.set_placeholder_text("Тавтай морилно уу")
        self._add_form_group(body, "Idle мессеж:", self._customer_idle_message)

    def _build_security_section(self, parent):
        body = self._make_section_card(parent, "🔒", "Хамгаалалт ба систем")

        self._admin_session_timeout = Gtk.SpinButton.new_with_range(10, 1440, 10)
        self._add_form_row(body, "Админ сессын хугацаа (мин):", self._admin_session_timeout)

        self._return_window_days = Gtk.SpinButton.new_with_range(1, 365, 1)
        self._add_form_row(body, "Буцаалт хийх хоног:", self._return_window_days)

        self._backup_retention_days = Gtk.SpinButton.new_with_range(7, 365, 1)
        self._add_form_group(body, "Нөөц хадгалах хоног:", self._backup_retention_days)

    def _load_settings(self):
        try:
            import database as db
            self._settings = db.get_all_settings()
        except Exception:
            self._settings = {}

        s = self._settings
        self._store_name.set_text(s.get("store_name", ""))
        self._store_phone.set_text(s.get("store_phone", ""))
        self._store_address.set_text(s.get("store_address", ""))
        self._default_payment.set_active_id(s.get("default_payment_type", "cash"))
        self._qr_payment_image.set_text(s.get("qr_payment_image", ""))
        self._printer_port.set_text(s.get("printer_port", "/dev/usb/lp0"))
        self._receipt_footer.set_text(s.get("receipt_footer", ""))
        self._auto_print.set_active(s.get("auto_print_receipt", "true") == "true")
        self._show_vat.set_active(s.get("show_vat_on_receipt", "false") == "true")
        self._receipt_width.set_value(int(s.get("receipt_width", "32")))
        self._show_stock_warnings.set_active(s.get("show_stock_warnings", "true") == "true")
        self._discounts_enabled.set_active(s.get("discounts_enabled", "false") == "true")
        self._theme.set_active_id(s.get("theme", "auto"))
        self._customer_display_timeout.set_value(int(s.get("customer_display_timeout", "10")))
        self._customer_idle_message.set_text(s.get("customer_idle_message", "Тавтай морилно уу"))
        self._admin_session_timeout.set_value(int(s.get("admin_session_timeout_minutes", "480")))
        self._return_window_days.set_value(int(s.get("return_window_days", "30")))
        self._backup_retention_days.set_value(int(s.get("backup_retention_days", "30")))

    def _on_save_all(self, btn):
        values = {
            "store_name": self._store_name.get_text().strip(),
            "store_phone": self._store_phone.get_text().strip(),
            "store_address": self._store_address.get_text().strip(),
            "receipt_footer": self._receipt_footer.get_text().strip(),
            "default_payment_type": self._default_payment.get_active_id() or "cash",
            "qr_payment_image": self._qr_payment_image.get_text().strip(),
            "printer_port": self._printer_port.get_text().strip(),
            "receipt_width": str(int(self._receipt_width.get_value())),
            "auto_print_receipt": "true" if self._auto_print.get_active() else "false",
            "show_vat_on_receipt": "true" if self._show_vat.get_active() else "false",
            "show_stock_warnings": "true" if self._show_stock_warnings.get_active() else "false",
            "discounts_enabled": "true" if self._discounts_enabled.get_active() else "false",
            "theme": self._theme.get_active_id() or "auto",
            "customer_display_timeout": str(int(self._customer_display_timeout.get_value())),
            "customer_idle_message": self._customer_idle_message.get_text().strip(),
            "admin_session_timeout_minutes": str(int(self._admin_session_timeout.get_value())),
            "return_window_days": str(int(self._return_window_days.get_value())),
            "backup_retention_days": str(int(self._backup_retention_days.get_value())),
        }

        try:
            import database as db
            db.set_settings(values)
            if self.app and self.app.theme:
                self.app.theme.apply(
                    values.get("theme", "auto"),
                    scale=getattr(self.app, '_display_scale', 1.0),
                )
            if self.app and self.app.cache:
                self.app.cache.invalidate()
        except Exception as e:
            logger.error(f"Save settings failed: {e}")

        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="✅ Тохиргоо хадгалагдлаа!",
        )
        dialog.run()
        dialog.destroy()

"""
posgtk/settings.py — Settings screen with card-based layout matching web.

Store info, payment (eBarimt/PAX/QPay), printer, display, database sections.
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
        self._build_database_section(form_box)

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

    def _make_spin(self, min_val, max_val, step):
        spin = Gtk.SpinButton.new_with_range(min_val, max_val, step)
        spin.connect("scroll-event", lambda w, e: not w.has_focus())
        return spin

    def _add_form_note(self, parent, text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("text-muted")
        lbl.set_margin_top(-4)
        parent.pack_start(lbl, False, False, 0)

    def _add_info_row(self, parent, label_text, value_text):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=label_text, xalign=0)
        lbl.get_style_context().add_class("form-label")
        row.pack_start(lbl, False, False, 0)
        val = Gtk.Label(label=value_text, xalign=1, hexpand=True)
        val.get_style_context().add_class("text-muted")
        row.pack_start(val, True, True, 0)
        parent.pack_start(row, False, False, 0)

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
        self._add_form_group(body, "QR төлбөрийн зураг (URL):", self._qr_payment_image)

        self._return_window_days = self._make_spin(1, 365, 1)
        self._return_window_days.set_value(30)
        self._add_form_row(body, "Буцаалт хийх хоног:", self._return_window_days)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        body.pack_start(sep, False, False, 0)

        ebarimt_exp = Gtk.Expander(label="🧾 eBarimt тохиргоо")
        ebarimt_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ebarimt_body.set_margin_top(8)

        self._add_form_note(ebarimt_body, "Монголын Татварын Газрын цахим баримтын систем. POS төхөөрөмжийн REST API хаяг, НӨАТ төлөгчийн дугаар, салбар, TTD мэдээллийг оруулна уу.")

        self._ebarimt_api_url = Gtk.Entry()
        self._ebarimt_api_url.set_placeholder_text("http://192.168.1.100:8080")
        self._add_form_group(ebarimt_body, "POS төхөөрөмжийн API URL:", self._ebarimt_api_url)

        self._ebarimt_merchant_tin = Gtk.Entry()
        self._ebarimt_merchant_tin.set_placeholder_text("0000000000")
        self._add_form_row(ebarimt_body, "НӨАТ төлөгчийн дугаар (TIN):", self._ebarimt_merchant_tin)

        self._ebarimt_ttd = Gtk.Entry()
        self._ebarimt_ttd.set_placeholder_text("TTD дугаар")
        self._add_form_row(ebarimt_body, "TTD (POS №):", self._ebarimt_ttd)

        self._ebarimt_branch_id = Gtk.Entry()
        self._ebarimt_branch_id.set_placeholder_text("Салбарын ID")
        self._add_form_group(ebarimt_body, "Салбарын ID (branch_no):", self._ebarimt_branch_id)

        ebarimt_exp.add(ebarimt_body)
        body.pack_start(ebarimt_exp, False, False, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_top(8)
        sep2.set_margin_bottom(8)
        body.pack_start(sep2, False, False, 0)

        pax_exp = Gtk.Expander(label="💳 PAX A930 Терминал тохиргоо")
        pax_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pax_body.set_margin_top(8)

        self._add_form_note(pax_body, "PAX A930 TCP/IP төлбөрийн терминал. Терминал дээрээ TCP Server режимийг ON болгоод дотоод сүлжээний IP хаягийг оруулна уу. Стандарт порт: 10009.")

        self._terminal_enabled = self._add_toggle_row(pax_body, "Төлбөрийн терминал ашиглах", False)

        self._terminal_ip = Gtk.Entry()
        self._terminal_ip.set_placeholder_text("192.168.1.150")
        self._add_form_row(pax_body, "Терминалын IP хаяг:", self._terminal_ip)

        self._terminal_port = self._make_spin(1, 65535, 1)
        self._terminal_port.set_value(10009)
        self._add_form_row(pax_body, "Терминалын порт:", self._terminal_port)

        pax_exp.add(pax_body)
        body.pack_start(pax_exp, False, False, 0)

        sep3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep3.set_margin_top(8)
        sep3.set_margin_bottom(8)
        body.pack_start(sep3, False, False, 0)

        qpay_exp = Gtk.Expander(label="📱 QPay тохиргоо")
        qpay_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        qpay_body.set_margin_top(8)

        self._add_form_note(qpay_body, "QPay — Монголын QR төлбөрийн систем. Merchant дэлгүүрийн ID, хэрэглэгч, нууц үгээ оруулна уу.")

        self._qpay_enabled = self._add_toggle_row(qpay_body, "QPay QR төлбөр ашиглах", False)

        self._qpay_client_id = Gtk.Entry()
        self._qpay_client_id.set_placeholder_text("QPay Client ID")
        self._add_form_row(qpay_body, "Client ID:", self._qpay_client_id)

        self._qpay_client_secret = Gtk.Entry()
        self._qpay_client_secret.set_placeholder_text("QPay Client Secret")
        self._qpay_client_secret.set_visibility(False)
        self._add_form_row(qpay_body, "Client Secret:", self._qpay_client_secret)

        self._qpay_base_url = Gtk.ComboBoxText()
        for val, label in [
            ("https://merchant.qpay.mn/v2", "🏭 Бодит (merchant.qpay.mn/v2)"),
            ("https://sandbox.qpay.mn/v2", "🧪 Сандал (sandbox.qpay.mn/v2)"),
        ]:
            self._qpay_base_url.append(val, label)
        self._add_form_row(qpay_body, "API URL:", self._qpay_base_url)

        self._qpay_allow_partial = self._add_toggle_row(qpay_body, "Хэсэгчилсэн төлбөр зөвшөөрөх", False)
        self._qpay_allow_exceed = self._add_toggle_row(qpay_body, "Илүү төлбөр зөвшөөрөх", False)

        qpay_exp.add(qpay_body)
        body.pack_start(qpay_exp, False, False, 0)

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

        self._receipt_width = self._make_spin(24, 48, 1)
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

        self._customer_display_timeout = self._make_spin(5, 120, 1)
        self._add_form_row(body, "Idle хугацаа (сек):", self._customer_display_timeout)

        self._customer_idle_message = Gtk.Entry()
        self._customer_idle_message.set_placeholder_text("Тавтай морилно уу")
        self._add_form_group(body, "Idle мессеж:", self._customer_idle_message)

    def _build_database_section(self, parent):
        body = self._make_section_card(parent, "🗄", "Өгөгдлийн сан")

        self._admin_session_timeout = self._make_spin(10, 1440, 10)
        self._admin_session_timeout.set_value(480)
        self._add_form_row(body, "Админ сессын хугацаа (мин):", self._admin_session_timeout)

        self._backup_retention_days = self._make_spin(7, 365, 1)
        self._backup_retention_days.set_value(30)
        self._add_form_group(body, "Нөөц хадгалах хоног:", self._backup_retention_days)

        self._last_backup_val = Gtk.Label(label="Хийгдээгүй", xalign=1, hexpand=True)
        self._last_backup_val.get_style_context().add_class("text-muted")
        last_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        last_lbl = Gtk.Label(label="Сүүлийн нөөц хуулбар:", xalign=0)
        last_lbl.get_style_context().add_class("form-label")
        last_row.pack_start(last_lbl, False, False, 0)
        last_row.pack_start(self._last_backup_val, True, True, 0)
        body.pack_start(last_row, False, False, 0)

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
        self._return_window_days.set_value(int(s.get("return_window_days", "30")))

        self._ebarimt_api_url.set_text(s.get("ebarimt_api_url", ""))
        self._ebarimt_merchant_tin.set_text(s.get("ebarimt_merchant_tin", ""))
        self._ebarimt_ttd.set_text(s.get("ebarimt_ttd", ""))
        self._ebarimt_branch_id.set_text(s.get("ebarimt_branch_id", ""))

        self._terminal_enabled.set_active(s.get("terminal_enabled", "false") == "true")
        self._terminal_ip.set_text(s.get("terminal_ip", ""))
        self._terminal_port.set_value(int(s.get("terminal_port", "10009")))

        self._qpay_enabled.set_active(s.get("qpay_enabled", "false") == "true")
        self._qpay_client_id.set_text(s.get("qpay_client_id", ""))
        self._qpay_client_secret.set_text(s.get("qpay_client_secret", ""))
        self._qpay_base_url.set_active_id(s.get("qpay_base_url", "https://merchant.qpay.mn/v2"))
        self._qpay_allow_partial.set_active(s.get("qpay_allow_partial", "false") == "true")
        self._qpay_allow_exceed.set_active(s.get("qpay_allow_exceed", "false") == "true")

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
        self._backup_retention_days.set_value(int(s.get("backup_retention_days", "30")))
        self._last_backup_val.set_text(s.get("last_backup_date", "Хийгдээгүй"))

    def _on_save_all(self, btn):
        values = {
            "store_name": self._store_name.get_text().strip(),
            "store_phone": self._store_phone.get_text().strip(),
            "store_address": self._store_address.get_text().strip(),
            "receipt_footer": self._receipt_footer.get_text().strip(),
            "default_payment_type": self._default_payment.get_active_id() or "cash",
            "qr_payment_image": self._qr_payment_image.get_text().strip(),
            "return_window_days": str(int(self._return_window_days.get_value())),
            "printer_port": self._printer_port.get_text().strip(),
            "receipt_width": str(int(self._receipt_width.get_value())),
            "auto_print_receipt": "true" if self._auto_print.get_active() else "false",
            "show_vat_on_receipt": "true" if self._show_vat.get_active() else "false",
            "show_stock_warnings": "true" if self._show_stock_warnings.get_active() else "false",
            "discounts_enabled": "true" if self._discounts_enabled.get_active() else "false",
            "theme": self._theme.get_active_id() or "auto",
            "customer_display_timeout": str(int(self._customer_display_timeout.get_value())),
            "customer_idle_message": self._customer_idle_message.get_text().strip(),
            "ebarimt_api_url": self._ebarimt_api_url.get_text().strip(),
            "ebarimt_merchant_tin": self._ebarimt_merchant_tin.get_text().strip(),
            "ebarimt_ttd": self._ebarimt_ttd.get_text().strip(),
            "ebarimt_branch_id": self._ebarimt_branch_id.get_text().strip(),
            "terminal_enabled": "true" if self._terminal_enabled.get_active() else "false",
            "terminal_ip": self._terminal_ip.get_text().strip(),
            "terminal_port": str(int(self._terminal_port.get_value())),
            "qpay_enabled": "true" if self._qpay_enabled.get_active() else "false",
            "qpay_client_id": self._qpay_client_id.get_text().strip(),
            "qpay_client_secret": self._qpay_client_secret.get_text().strip(),
            "qpay_base_url": self._qpay_base_url.get_active_id() or "https://merchant.qpay.mn/v2",
            "qpay_allow_partial": "true" if self._qpay_allow_partial.get_active() else "false",
            "qpay_allow_exceed": "true" if self._qpay_allow_exceed.get_active() else "false",
            "admin_session_timeout_minutes": str(int(self._admin_session_timeout.get_value())),
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
            if self.app and hasattr(self.app, 'pos_screen') and self.app.pos_screen:
                self.app.pos_screen._discounts_enabled = values.get("discounts_enabled") == "true"
                if hasattr(self.app, 'customer_window') and self.app.customer_window:
                    self.app.customer_window._display_timeout = int(values.get("customer_display_timeout", 10))
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="✅ Тохиргоо хадгалагдлаа!",
            )
            dialog.run()
            dialog.destroy()
        except Exception as e:
            logger.error(f"Save settings failed: {e}")
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"❌ Хадгалахад алдаа: {e}",
            )
            dialog.run()
            dialog.destroy()

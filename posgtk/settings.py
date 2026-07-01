"""
posgtk/settings.py — Full settings screen with tabs.

Store info, printer, terminal, eBarimt, QPay, security, display, system.
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

        notebook = Gtk.Notebook()
        notebook.set_margin_start(8)

        notebook.set_margin_end(8)

        notebook.set_margin_top(8)

        notebook.set_margin_bottom(8)

        self._store_tab = self._make_store_tab()
        self._printer_tab = self._make_printer_tab()
        self._payment_tab = self._make_payment_tab()
        self._tax_tab = self._make_tax_tab()
        self._security_tab = self._make_security_tab()
        self._display_tab = self._make_display_tab()
        self._system_tab = self._make_system_tab()

        notebook.append_page(self._store_tab, Gtk.Label(label="🏪 Дэлгүүр"))
        notebook.append_page(self._printer_tab, Gtk.Label(label="🖨 Хэвлэгч"))
        notebook.append_page(self._payment_tab, Gtk.Label(label="💳 Төлбөр"))
        notebook.append_page(self._tax_tab, Gtk.Label(label="🧾 eBarimt"))
        notebook.append_page(self._security_tab, Gtk.Label(label="🔒 Хамгаалалт"))
        notebook.append_page(self._display_tab, Gtk.Label(label="🖥 Дэлгэц"))
        notebook.append_page(self._system_tab, Gtk.Label(label="⚙️ Систем"))

        self.pack_start(notebook, True, True, 0)

        save_btn = Gtk.Button(label="💾  Бүх тохиргоог хадгалах")
        save_btn.set_margin_start(8)

        save_btn.set_margin_end(8)

        save_btn.set_margin_top(8)

        save_btn.set_margin_bottom(8)
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self._on_save_all)
        self.pack_end(save_btn, False, False, 0)

        self.show_all()
        GLib.idle_add(self._load_settings)

    def _load_settings(self):
        try:
            import database as db
            self._settings = db.get_all_settings()
        except Exception:
            self._settings = {}
        self._populate_store()
        self._populate_printer()
        self._populate_payment()
        self._populate_tax()
        self._populate_security()
        self._populate_display()

    def _setting(self, key, default=""):
        return self._settings.get(key, default)

    def _make_store_tab(self):
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        self._store_fields = {
            "store_name": ("Дэлгүүрийн нэр", ""),
            "store_address": ("Хаяг", ""),
            "store_phone": ("Утас", ""),
            "receipt_footer": ("Баримтын хөл хэсэг", ""),
        }
        row = 0
        for key, (label, _) in self._store_fields.items():
            lbl = Gtk.Label(label=label + ":", xalign=1)
            grid.attach(lbl, 0, row, 1, 1)
            entry = Gtk.Entry()
            grid.attach(entry, 1, row, 1, 1)
            setattr(self, f"_store_{key}", entry)
            row += 1

        lbl = Gtk.Label(label="Баримтын өргөн (тэмдэгт):", xalign=1)
        grid.attach(lbl, 0, row, 1, 1)
        self._receipt_width_spin = Gtk.SpinButton.new_with_range(24, 48, 1)
        grid.attach(self._receipt_width_spin, 1, row, 1, 1)
        row += 1

        self._show_vat_switch = Gtk.Switch()
        grid.attach(Gtk.Label(label="НӨАТ-ыг баримтанд харуулах:", xalign=1), 0, row, 1, 1)
        grid.attach(self._show_vat_switch, 1, row, 1, 1)
        row += 1

        return grid

    def _populate_store(self):
        for key in self._store_fields:
            entry = getattr(self, f"_store_{key}", None)
            if entry:
                entry.set_text(self._setting(key, ""))
        try:
            self._receipt_width_spin.set_value(int(self._setting("receipt_width", "32") or 32))
        except ValueError:
            self._receipt_width_spin.set_value(32)
        self._show_vat_switch.set_active(self._setting("show_vat_on_receipt", "false") == "true")

    def _make_printer_tab(self):
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        row = 0

        lbl = Gtk.Label(label="Хэвлэгчийн порт:", xalign=1)
        grid.attach(lbl, 0, row, 1, 1)
        self._printer_port_entry = Gtk.Entry()
        self._printer_port_entry.set_placeholder_text("/dev/usb/lp0 (auto бол хоосон)")
        grid.attach(self._printer_port_entry, 1, row, 1, 1)
        row += 1

        self._auto_print_switch = Gtk.Switch()
        lbl2 = Gtk.Label(label="Автомат хэвлэх:", xalign=1)
        grid.attach(lbl2, 0, row, 1, 1)
        grid.attach(self._auto_print_switch, 1, row, 1, 1)
        row += 1

        return grid

    def _populate_printer(self):
        self._printer_port_entry.set_text(self._setting("printer_port", ""))
        self._auto_print_switch.set_active(self._setting("auto_print_receipt", "true") == "true")

    def _make_payment_tab(self):
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        row = 0

        self._terminal_enabled_switch = Gtk.Switch()
        grid.attach(Gtk.Label(label="PAX терминал:", xalign=1), 0, row, 1, 1)
        grid.attach(self._terminal_enabled_switch, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Терминал IP:", xalign=1), 0, row, 1, 1)
        self._terminal_ip_entry = Gtk.Entry()
        grid.attach(self._terminal_ip_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Терминал порт:", xalign=1), 0, row, 1, 1)
        self._terminal_port_entry = Gtk.Entry()
        self._terminal_port_entry.set_text("10009")
        grid.attach(self._terminal_port_entry, 1, row, 1, 1)
        row += 1

        self._discounts_switch = Gtk.Switch()
        grid.attach(Gtk.Label(label="Хөнгөлөлт:", xalign=1), 0, row, 1, 1)
        grid.attach(self._discounts_switch, 1, row, 1, 1)
        row += 1

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        grid.attach(sep, 0, row, 2, 1)
        row += 1

        self._qpay_enabled_switch = Gtk.Switch()
        grid.attach(Gtk.Label(label="QPay:", xalign=1), 0, row, 1, 1)
        grid.attach(self._qpay_enabled_switch, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="QPay Client ID:", xalign=1), 0, row, 1, 1)
        self._qpay_client_id_entry = Gtk.Entry()
        grid.attach(self._qpay_client_id_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="QPay Client Secret:", xalign=1), 0, row, 1, 1)
        self._qpay_client_secret_entry = Gtk.Entry()
        self._qpay_client_secret_entry.set_visibility(False)
        grid.attach(self._qpay_client_secret_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="QPay сервер:", xalign=1), 0, row, 1, 1)
        self._qpay_base_url_entry = Gtk.Entry()
        self._qpay_base_url_entry.set_placeholder_text("https://merchant.qpay.mn/v2")
        grid.attach(self._qpay_base_url_entry, 1, row, 1, 1)
        row += 1

        self._qpay_allow_partial_switch = Gtk.Switch()
        grid.attach(Gtk.Label(label="Хэсэгчилсэн төлбөр зөвшөөрөх:", xalign=1), 0, row, 1, 1)
        grid.attach(self._qpay_allow_partial_switch, 1, row, 1, 1)
        row += 1

        self._qpay_allow_exceed_switch = Gtk.Switch()
        grid.attach(Gtk.Label(label="Илүү төлбөр зөвшөөрөх:", xalign=1), 0, row, 1, 1)
        grid.attach(self._qpay_allow_exceed_switch, 1, row, 1, 1)
        row += 1

        return grid

    def _populate_payment(self):
        self._terminal_enabled_switch.set_active(self._setting("terminal_enabled") == "true")
        self._terminal_ip_entry.set_text(self._setting("terminal_ip", ""))
        self._terminal_port_entry.set_text(self._setting("terminal_port", "10009"))
        self._discounts_switch.set_active(self._setting("discounts_enabled") == "true")
        self._qpay_enabled_switch.set_active(self._setting("qpay_enabled") == "true")
        self._qpay_client_id_entry.set_text(self._setting("qpay_client_id", ""))
        self._qpay_client_secret_entry.set_text(self._setting("qpay_client_secret", ""))
        self._qpay_base_url_entry.set_text(self._setting("qpay_base_url", "https://merchant.qpay.mn/v2"))
        self._qpay_allow_partial_switch.set_active(self._setting("qpay_allow_partial") == "true")
        self._qpay_allow_exceed_switch.set_active(self._setting("qpay_allow_exceed") == "true")

    def _make_tax_tab(self):
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        row = 0
        grid.attach(Gtk.Label(label="eBarimt төлөв:", xalign=1), 0, row, 1, 1)
        self._ebarimt_status_label = Gtk.Label(label="Шалгаж байна...", xalign=0)
        grid.attach(self._ebarimt_status_label, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="API URL:", xalign=1), 0, row, 1, 1)
        self._ebarimt_api_url_entry = Gtk.Entry()
        self._ebarimt_api_url_entry.set_placeholder_text("http://192.168.1.100:8080")
        grid.attach(self._ebarimt_api_url_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="ТТД (Татвар төлөгчийн дугаар):", xalign=1), 0, row, 1, 1)
        self._ebarimt_merchant_tin_entry = Gtk.Entry()
        self._ebarimt_merchant_tin_entry.set_placeholder_text("0000000000")
        grid.attach(self._ebarimt_merchant_tin_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="TTD дугаар:", xalign=1), 0, row, 1, 1)
        self._ebarimt_ttd_entry = Gtk.Entry()
        grid.attach(self._ebarimt_ttd_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Салбарын ID:", xalign=1), 0, row, 1, 1)
        self._ebarimt_branch_id_entry = Gtk.Entry()
        grid.attach(self._ebarimt_branch_id_entry, 1, row, 1, 1)
        row += 1

        return grid

    def _populate_tax(self):
        from config import is_ebarimt_configured
        configured = is_ebarimt_configured()
        self._ebarimt_status_label.set_label(
            "\u2705 \u0422\u043e\u0445\u0438\u0440\u0443\u0443\u043b\u0441\u0430\u043d" if configured else "\u26a0\ufe0f \u0422\u043e\u0445\u0438\u0440\u0443\u0443\u043b\u0430\u0430\u0433\u04af\u0439"
        )
        self._ebarimt_api_url_entry.set_text(self._setting("ebarimt_api_url", ""))
        self._ebarimt_merchant_tin_entry.set_text(self._setting("ebarimt_merchant_tin", ""))
        self._ebarimt_ttd_entry.set_text(self._setting("ebarimt_ttd", ""))
        self._ebarimt_branch_id_entry.set_text(self._setting("ebarimt_branch_id", ""))

    def _make_security_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Label(label="Админ PIN:", xalign=1), False, False, 0)
        self._change_pin_btn = Gtk.Button(label="PIN солих")
        self._change_pin_btn.connect("clicked", self._on_change_pin)
        row.pack_start(self._change_pin_btn, False, False, 0)
        box.pack_start(row, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._auto_admin_switch = Gtk.Switch()
        row2.pack_start(Gtk.Label(label="Авто админ:", xalign=1), False, False, 0)
        row2.pack_start(self._auto_admin_switch, False, False, 0)
        box.pack_start(row2, False, False, 0)

        return box

    def _populate_security(self):
        self._auto_admin_switch.set_active(self._setting("auto_admin_session", "true") == "true")

    def _make_display_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Label(label="Сэдэв:", xalign=1), False, False, 0)
        self._theme_combo = Gtk.ComboBoxText()
        for t in ("auto", "light", "dark"):
            self._theme_combo.append_text(t)
        self._theme_combo.set_active(0)
        row.pack_start(self._theme_combo, False, False, 0)
        box.pack_start(row, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._low_perf_switch = Gtk.Switch()
        row2.pack_start(Gtk.Label(label="Low perf mode:", xalign=1), False, False, 0)
        row2.pack_start(self._low_perf_switch, False, False, 0)
        box.pack_start(row2, False, False, 0)

        scale_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        scale_row.set_margin_top(8)
        scale_row.pack_start(Gtk.Label(label="Дэлгэцийн хэмжээ:", xalign=1), False, False, 0)
        self._display_scale_adj = Gtk.Adjustment(
            value=1.0, lower=0.5, upper=3.0, step_increment=0.05,
        )
        self._display_scale_spin = Gtk.SpinButton(adjustment=self._display_scale_adj)
        self._display_scale_spin.set_digits(2)
        self._display_scale_spin.set_width_chars(6)
        scale_row.pack_start(self._display_scale_spin, False, False, 0)

        scale_hint = Gtk.Label(label="(0.5=жижиг, 1.0=хэвийн, 3.0=том)")
        scale_hint.set_margin_start(4)
        scale_hint.get_style_context().add_class("text-muted")
        scale_row.pack_start(scale_hint, False, False, 0)
        box.pack_start(scale_row, False, False, 0)

        return box

    def _populate_display(self):
        theme_val = self._setting("theme", "auto")
        model = self._theme_combo.get_model()
        for i in range(len(model)):
            if model[i][0] == theme_val:
                self._theme_combo.set_active(i)
                break
        self._low_perf_switch.set_active(self._setting("low_perf_mode") == "true")
        try:
            scale = float(self._setting("display_scale", "0"))
            if 0.5 <= scale <= 3.0:
                self._display_scale_spin.set_value(scale)
            elif hasattr(self.app, '_display_scale'):
                self._display_scale_spin.set_value(self.app._display_scale)
            else:
                self._display_scale_spin.set_value(1.0)
        except Exception:
            auto = getattr(self.app, '_display_scale', 1.0)
            self._display_scale_spin.set_value(auto)

    def _make_system_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)

        backup_btn = Gtk.Button(label="📦 Өгөгдлийн сангийн нөөц хийх")
        backup_btn.set_size_request(-1, 40)
        backup_btn.connect("clicked", lambda b: self._do_backup())
        box.pack_start(backup_btn, False, False, 0)

        restore_btn = Gtk.Button(label="📥 Нөөцөөс сэргээх")
        restore_btn.set_size_request(-1, 40)
        restore_btn.connect("clicked", lambda b: self._do_restore())
        box.pack_start(restore_btn, False, False, 0)

        check_btn = Gtk.Button(label="🔍 Өгөгдлийн сан шалгах")
        check_btn.set_size_request(-1, 40)
        check_btn.connect("clicked", lambda b: self._do_integrity_check())
        box.pack_start(check_btn, False, False, 0)

        info_label = Gtk.Label(label="")
        info_label.set_has_window(False)
        self._sys_info_label = info_label
        box.pack_start(info_label, False, False, 0)

        version_text = "unknown"
        try:
            import os as _os
            vpath = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "VERSION")
            with open(vpath) as f:
                version_text = f.read().strip()
        except Exception:
            pass
        box.pack_start(Gtk.Label(label=f"Хувилбар: {version_text}"), False, False, 0)

        return box

    def _on_save_all(self, btn):
        values = {}

        for key in ("store_name", "store_address", "store_phone", "receipt_footer"):
            entry = getattr(self, f"_store_{key}", None)
            if entry:
                values[key] = entry.get_text().strip()
        values["receipt_width"] = str(int(self._receipt_width_spin.get_value()))
        values["show_vat_on_receipt"] = "true" if self._show_vat_switch.get_active() else "false"

        values["printer_port"] = self._printer_port_entry.get_text().strip()
        values["auto_print_receipt"] = "true" if self._auto_print_switch.get_active() else "false"

        values["terminal_enabled"] = "true" if self._terminal_enabled_switch.get_active() else "false"
        values["terminal_ip"] = self._terminal_ip_entry.get_text().strip()
        values["terminal_port"] = self._terminal_port_entry.get_text().strip()
        values["discounts_enabled"] = "true" if self._discounts_switch.get_active() else "false"

        values["qpay_enabled"] = "true" if self._qpay_enabled_switch.get_active() else "false"
        values["qpay_client_id"] = self._qpay_client_id_entry.get_text().strip()
        values["qpay_client_secret"] = self._qpay_client_secret_entry.get_text().strip()
        values["qpay_base_url"] = self._qpay_base_url_entry.get_text().strip()
        values["qpay_allow_partial"] = "true" if self._qpay_allow_partial_switch.get_active() else "false"
        values["qpay_allow_exceed"] = "true" if self._qpay_allow_exceed_switch.get_active() else "false"

        values["ebarimt_api_url"] = self._ebarimt_api_url_entry.get_text().strip()
        values["ebarimt_merchant_tin"] = self._ebarimt_merchant_tin_entry.get_text().strip()
        values["ebarimt_ttd"] = self._ebarimt_ttd_entry.get_text().strip()
        values["ebarimt_branch_id"] = self._ebarimt_branch_id_entry.get_text().strip()
        values["auto_admin_session"] = "true" if self._auto_admin_switch.get_active() else "false"

        theme_val = self._theme_combo.get_active_text() or "auto"
        values["theme"] = theme_val
        values["low_perf_mode"] = "true" if self._low_perf_switch.get_active() else "false"
        values["display_scale"] = str(self._display_scale_spin.get_value())

        try:
            import database as db
            db.set_settings(values)
            from config import invalidate_settings_cache
            invalidate_settings_cache()
        except Exception as e:
            logger.error(f"Save settings failed: {e}")

        theme_val = values.get("theme", "auto")
        scale = float(values.get("display_scale", "1.0"))
        low_perf = self._low_perf_switch.get_active()
        if self.app and hasattr(self.app, 'theme'):
            try:
                self.app.theme.apply(theme_val, scale=scale, low_perf=low_perf)
                self.app._display_scale = scale
                if hasattr(self.app, 'cache') and self.app.cache:
                    cat_css = self.app.cache.generate_category_css()
                    self.app.theme.append_css(cat_css)
            except Exception:
                pass

        self._show_info("\u2705 Тохиргоо хадгалагдлаа")

    def _on_change_pin(self, btn):
        dialog = Gtk.Dialog(
            title="PIN код солих",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_start(16)

        content.set_margin_end(16)

        content.set_margin_top(16)

        content.set_margin_bottom(16)

        fields = [("Одоогийн PIN:", "current"), ("Шинэ PIN:", "new"), ("Шинэ PIN давтах:", "confirm")]
        entries = {}
        for label, key in fields:
            content.add(Gtk.Label(label=label, xalign=0))
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_max_length(6)
            entries[key] = entry
            content.add(entry)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        dialog.add_button("Хадгалах", Gtk.ResponseType.OK)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            current = entries["current"].get_text().strip()
            new = entries["new"].get_text().strip()
            confirm = entries["confirm"].get_text().strip()

            if new != confirm:
                self._show_error("Шинэ PIN тохирохгүй байна")
            elif not new:
                self._show_error("Шинэ PIN хоосон байж болохгүй")
            else:
                try:
                    import database as db
                    success, error = db.change_admin_password(current, new)
                    if error:
                        self._show_error(error)
                    else:
                        self._show_info("✅ PIN код амжилттай солигдлоо")
                except Exception as e:
                    self._show_error(f"Алдаа: {e}")

        dialog.destroy()

    def _do_backup(self):
        try:
            import database as db
            path = db.perform_manual_backup()
            self._show_info(f"✅ Нөөц амжилттай: {path}")
        except Exception as e:
            self._show_error(f"Нөөц амжилтгүй: {e}")

    def _do_restore(self):
        dialog = Gtk.FileChooserDialog(
            title="Нөөц файл сонгох",
            transient_for=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        dialog.add_button("Сэргээх", Gtk.ResponseType.OK)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            dialog.destroy()
            try:
                import database as db
                db.verify_backup(filename)
                confirm = Gtk.MessageDialog(
                    transient_for=self.get_toplevel(),
                    flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text="Та итгэлтэй байна уу?\nОдоогийн өгөгдөл устгагдаж нөөцөөс сэргээгдэнэ!",
                )
                if confirm.run() == Gtk.ResponseType.YES:
                    import shutil
                    import database as db2
                    db_path = db2.DB_PATH
                    shutil.copy2(filename, db_path)
                    self._show_info("✅ Сэргээгдлээ. Программ дахин ачаална уу.")
                confirm.destroy()
            except Exception as e:
                self._show_error(f"Сэргээхэд алдаа: {e}")
        else:
            dialog.destroy()

    def _do_integrity_check(self):
        try:
            import database as db
            ok = db.check_db_integrity()
            if ok:
                self._show_info("✅ Өгөгдлийн сан хэвийн")
            else:
                self._show_error("❌ Өгөгдлийн сан гэмтсэн! Нөөцөөс сэргээнэ үү.")
        except Exception as e:
            self._show_error(f"Шалгалтад алдаа: {e}")

    def _show_info(self, msg):
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        d.run()
        d.destroy()

    def _show_error(self, msg):
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        d.run()
        d.destroy()

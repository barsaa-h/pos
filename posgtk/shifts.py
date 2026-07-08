"""
posgtk/shifts.py — Shift management with open/close, Z-report, history.
"""
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.shifts")


class ShiftScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app
        self._page = 1
        self._per_page = 30

        header = Gtk.Label(label="🔄 Ээлж")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        self._current_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._current_card.set_margin_start(16)
        self._current_card.set_margin_end(16)
        self._current_card.set_margin_top(12)
        self._current_card.set_margin_bottom(8)
        self._current_card.get_style_context().add_class("content-panel")
        self.pack_start(self._current_card, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        self.store = Gtk.ListStore(int, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.get_style_context().add_class("data-table")
        self.tree.get_style_context().add_class("treeview-table")

        for title, col_id, width in [
            ("ID", 0, 60),
            ("Нээгдсэн", 1, 160),
            ("Хаагдсан", 2, 160),
            ("Борлуулалт", 3, 100),
        ]:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.tree.append_column(col)

        self.tree.connect("row-activated", self._on_row_activated)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.tree)
        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)

        page_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        page_box.set_halign(Gtk.Align.CENTER)
        page_box.set_margin_top(8)
        page_box.set_margin_bottom(8)

        self.prev_btn = Gtk.Button(label="‹ Өмнөх")
        self.prev_btn.get_style_context().add_class("category-btn")
        self.prev_btn.connect("clicked", lambda b: self._change_page(-1))
        self.prev_btn.set_sensitive(False)
        page_box.pack_start(self.prev_btn, False, False, 0)

        self.page_label = Gtk.Label(label="Хуудас 1")
        self.page_label.set_margin_start(12)
        self.page_label.set_margin_end(12)
        self.page_label.get_style_context().add_class("text-muted")
        page_box.pack_start(self.page_label, False, False, 0)

        self.next_btn = Gtk.Button(label="Дараах ›")
        self.next_btn.get_style_context().add_class("category-btn")
        self.next_btn.connect("clicked", lambda b: self._change_page(1))
        page_box.pack_start(self.next_btn, False, False, 0)

        self.pack_start(page_box, False, False, 0)

        self.show_all()
        GLib.idle_add(self._refresh)

    def _refresh(self, *args):
        self._update_current_card()
        self._load_history()

    def _update_current_card(self):
        for child in self._current_card.get_children():
            self._current_card.remove(child)

        import database as db
        shift = db.get_current_shift()

        if shift and not shift.get("closed_at"):
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            card.set_margin_start(16)
            card.set_margin_end(16)
            card.set_margin_top(12)
            card.set_margin_bottom(12)

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info.set_hexpand(True)

            title = Gtk.Label()
            title.set_markup(f'<span weight="800" size="12000">Ээлж #{shift["id"]} — Нээлттэй</span>')
            title.set_halign(Gtk.Align.START)
            info.pack_start(title, False, False, 0)

            opened = Gtk.Label(label=f"Нээгдсэн: {shift['opened_at']}", xalign=0)
            opened.get_style_context().add_class("text-muted")
            info.pack_start(opened, False, False, 0)

            balance = Gtk.Label(label=f"Нээлтийн үлдэгдэл: {format_money(shift['opening_balance'])}₮", xalign=0)
            balance.get_style_context().add_class("text-muted")
            info.pack_start(balance, False, False, 0)

            card.pack_start(info, True, True, 0)

            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            close_btn = Gtk.Button(label="🔒 Ээлж хаах")
            close_btn.get_style_context().add_class("destructive-action")
            close_btn.connect("clicked", lambda b: self._show_close_dialog(shift))
            actions.pack_start(close_btn, False, False, 0)
            card.pack_start(actions, False, False, 0)

            self._current_card.pack_start(card, False, False, 0)
        else:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            card.set_margin_start(16)
            card.set_margin_end(16)
            card.set_margin_top(12)
            card.set_margin_bottom(12)

            info = Gtk.Label(label="Нээлттэй ээлж байхгүй", xalign=0)
            info.set_hexpand(True)
            info.get_style_context().add_class("text-muted")
            card.pack_start(info, True, True, 0)

            open_btn = Gtk.Button(label="🆕 Ээлж нээх")
            open_btn.get_style_context().add_class("suggested-action")
            open_btn.connect("clicked", lambda b: self._show_open_dialog())
            card.pack_start(open_btn, False, False, 0)

            self._current_card.pack_start(card, False, False, 0)

        self._current_card.show_all()

    def _show_open_dialog(self):
        dialog = Gtk.Dialog(
            title="Ээлж нээх",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(350, 180)
        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label()
        title.set_markup('<span weight="800" size="14000">Ээлж нээх</span>')
        title.set_halign(Gtk.Align.START)
        content.add(title)

        balance_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        balance_box.add(Gtk.Label(label="Нээлтийн үлдэгдэл (₮):", xalign=0))
        entry = Gtk.Entry()
        entry.set_text("0")
        entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        balance_box.pack_start(entry, False, False, 0)
        content.add(balance_box)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        save_btn = dialog.add_button("Нээх", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")

        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            balance = entry.get_text().strip()
            import database as db
            result, error = db.open_shift(balance or "0")
            if error:
                err = Gtk.MessageDialog(
                    transient_for=dialog, flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK, text=error,
                )
                err.run()
                err.destroy()
            else:
                self._refresh()
        dialog.destroy()

    def _show_close_dialog(self, shift):
        import database as db
        sales = db.get_sales_list(
            date_from=shift["opened_at"],
            limit=99999, offset=0,
        )
        expected = shift["opening_balance"]
        cash_total = 0
        card_total = 0
        qr_total = 0
        return_total = 0
        sale_count = 0
        for s in (sales or []):
            pt = s.get("payment_type", "")
            total = s.get("total", 0)
            if pt == "cash":
                cash_total += total
                sale_count += 1
            elif pt == "card":
                card_total += total
                sale_count += 1
            elif pt == "qr":
                qr_total += total
                sale_count += 1
            elif pt == "return":
                return_total += total
        expected += cash_total - return_total

        dialog = Gtk.Dialog(
            title="Ээлж хаах",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(400, 300)
        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label()
        title.set_markup('<span weight="800" size="14000">Ээлж хаах</span>')
        title.set_halign(Gtk.Align.START)
        content.add(title)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_margin_top(8)
        info_box.set_margin_bottom(8)
        for line in [
            f"Нээлтийн үлдэгдэл: {format_money(shift['opening_balance'])}₮",
            f"Бэлэн буюу: +{format_money(cash_total)}₮",
            f"Карт: {format_money(card_total)}₮",
            f"QR: {format_money(qr_total)}₮",
            f"Буцаалт: -{format_money(return_total)}₮",
            f"Хүлээгдэж буй үлдэгдэл: {format_money(expected)}₮",
        ]:
            lbl = Gtk.Label(label=line, xalign=0)
            info_box.pack_start(lbl, False, False, 0)
        content.add(info_box)

        cash_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cash_box.add(Gtk.Label(label="Бодит үлдэгдэл (₮):", xalign=0))
        actual_entry = Gtk.Entry()
        actual_entry.set_text(str(expected))
        actual_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        cash_box.pack_start(actual_entry, False, False, 0)
        content.add(cash_box)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        close_btn = dialog.add_button("Хаах", Gtk.ResponseType.OK)
        close_btn.get_style_context().add_class("destructive-action")

        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            actual = actual_entry.get_text().strip() or "0"
            result, error = db.close_shift(actual)
            if error:
                err = Gtk.MessageDialog(
                    transient_for=dialog, flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK, text=error,
                )
                err.run()
                err.destroy()
            else:
                self._show_z_report(result)
                self._refresh()
        dialog.destroy()

    def _show_z_report(self, shift):
        dialog = Gtk.Dialog(
            title="Z-Tайлан",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(400, 350)
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label()
        title.set_markup(f'<span weight="800" size="14000">Z-Tайлан — Ээлж #{shift["id"]}</span>')
        title.set_halign(Gtk.Align.START)
        content.add(title)

        lines = [
            ("Нээгдсэн:", shift.get("opened_at", "")),
            ("Хаагдсан:", shift.get("closed_at", "")),
            ("Нээлтийн үлдэгдэл:", f"{format_money(shift.get('opening_balance', 0))}₮"),
            ("Бэлэн буюу:", f"+{format_money(shift.get('cash_sales_total', 0))}₮"),
            ("Карт:", f"{format_money(shift.get('card_sales_total', 0))}₮"),
            ("QR:", f"{format_money(shift.get('qr_sales_total', 0))}₮"),
            ("Буцаалт:", f"-{format_money(shift.get('return_total', 0))}₮"),
            ("Хүлээгдэж буй үлдэгдэл:", f"{format_money(shift.get('expected_cash', 0))}₮"),
            ("Бодит үлдэгдэл:", f"{format_money(shift.get('actual_cash', 0))}₮"),
        ]
        diff = shift.get("difference", 0)
        diff_str = f"{format_money(diff)}₮"
        if diff > 0:
            diff_str += " (илүү)"
        elif diff < 0:
            diff_str += " (дутуу)"
        lines.append({"label": "Зөрүү:", "value": diff_str})

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        content.add(sep)

        for item in lines:
            if isinstance(item, dict):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                lbl = Gtk.Label(label=f"<b>{item['label']}</b>", use_markup=True, xalign=0)
                lbl.set_size_request(160, -1)
                row.pack_start(lbl, False, False, 0)
                row.pack_start(Gtk.Label(label=item["value"], xalign=0), True, True, 0)
            else:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                lbl = Gtk.Label(label=f"<b>{item[0]}</b>", use_markup=True, xalign=0)
                lbl.set_size_request(160, -1)
                row.pack_start(lbl, False, False, 0)
                row.pack_start(Gtk.Label(label=item[1], xalign=0), True, True, 0)
            content.add(row)

        summary = Gtk.Label()
        summary.set_markup(
            f'<span weight="800">Борлуулалт: {shift.get("sale_count", 0)} | '
            f'Буцаалт: {shift.get("return_count", 0)}</span>'
        )
        summary.set_margin_top(8)
        content.add(summary)

        ok_btn = dialog.add_button("✔ Хаах", Gtk.ResponseType.OK)
        ok_btn.get_style_context().add_class("suggested-action")
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _load_history(self):
        def fetch_background():
            import database as db
            shifts = db.get_shifts(limit=self._per_page, offset=(self._page - 1) * self._per_page)
            total = db.get_shifts(limit=99999, offset=0)
            total_pages = max(1, (len(total) + self._per_page - 1) // self._per_page)
            return shifts, len(total), total_pages

        def on_fetch_complete(result):
            shifts, total_count, total_pages = result
            self.store.clear()
            for s in (shifts or []):
                closed = s.get("closed_at") or "Нээлттэй"
                self.store.append([
                    s.get("id", 0),
                    s.get("opened_at", ""),
                    closed,
                    s.get("sale_count", 0),
                ])
            self.page_label.set_label(f"Хуудас {self._page}/{total_pages}  (Нийт: {total_count})")
            self.prev_btn.set_sensitive(self._page > 1)
            self.next_btn.set_sensitive(self._page < total_pages)

        def on_fetch_error(error_msg):
            logger.error(f"Background shifts load failed: {error_msg}")

        if self.app and self.app.workqueue:
            self.app.workqueue.async_op(fetch_background, on_result=on_fetch_complete, on_error=on_fetch_error)
        else:
            try:
                on_fetch_complete(fetch_background())
            except Exception as e:
                on_fetch_error(str(e))

    def _change_page(self, delta):
        self._page = max(1, self._page + delta)
        self._load_history()

    def _on_row_activated(self, tree, path, col):
        it = self.store.get_iter(path)
        shift_id = self.store.get_value(it, 0)
        import database as db
        shift = db.get_shift(shift_id)
        if shift:
            self._show_z_report(shift)

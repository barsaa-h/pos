"""
posgtk/stock.py — Stock adjustments screen.

Product stock increase/decrease with reason tracking and audit history.
Uses database.adjust_stock() and database.get_stock_adjustments().
"""

import logging
from datetime import datetime
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from posgtk.widgets import format_money, get_category_icon

logger = logging.getLogger("pos.gtk.stock")


class StockScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.app = app
        self.cache = app.cache if app else None
        self.workqueue = app.workqueue if app else None
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(20)
        self.set_margin_end(20)

        title = Gtk.Label(label="Агуулахын тохируулга")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(4)
        title.get_style_context().add_class("dialog-title")
        self.pack_start(title, False, False, 0)

        form_grid = Gtk.Grid()
        form_grid.set_column_spacing(12)
        form_grid.set_row_spacing(10)
        form_grid.set_margin_bottom(12)

        barcode_lbl = Gtk.Label(label="Баркод:")
        barcode_lbl.set_halign(Gtk.Align.END)
        barcode_lbl.get_style_context().add_class("split-label")
        form_grid.attach(barcode_lbl, 0, 0, 1, 1)

        self.barcode_entry = Gtk.Entry()
        self.barcode_entry.set_placeholder_text("Сканнердах...")
        self.barcode_entry.get_style_context().add_class("barcode-entry")
        self.barcode_entry.set_hexpand(True)
        self.barcode_entry.connect("activate", self._on_barcode_activate)
        form_grid.attach(self.barcode_entry, 1, 0, 1, 1)

        qty_lbl = Gtk.Label(label="Тоо ширхэг (+/-):")
        qty_lbl.set_halign(Gtk.Align.END)
        qty_lbl.get_style_context().add_class("split-label")
        form_grid.attach(qty_lbl, 0, 1, 1, 1)

        qty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.qty_entry = Gtk.Entry()
        self.qty_entry.set_placeholder_text("+10 = нэмэх, -5 = хасах")
        self.qty_entry.get_style_context().add_class("barcode-entry")
        self.qty_entry.set_hexpand(True)
        qty_box.pack_start(self.qty_entry, True, True, 0)
        quick_add = Gtk.Button(label="+1")
        quick_add.connect("clicked", lambda b: self._set_qty(1))
        quick_add.get_style_context().add_class("cash-quick-btn")
        qty_box.pack_start(quick_add, False, False, 0)
        quick_sub = Gtk.Button(label="-1")
        quick_sub.connect("clicked", lambda b: self._set_qty(-1))
        quick_sub.get_style_context().add_class("cash-quick-btn")
        qty_box.pack_start(quick_sub, False, False, 0)
        form_grid.attach(qty_box, 1, 1, 1, 1)

        reason_lbl = Gtk.Label(label="Шалтгаан:")
        reason_lbl.set_halign(Gtk.Align.END)
        reason_lbl.get_style_context().add_class("split-label")
        form_grid.attach(reason_lbl, 0, 2, 1, 1)

        self.reason_entry = Gtk.Entry()
        self.reason_entry.set_placeholder_text("Шалтгаан бичих...")
        self.reason_entry.get_style_context().add_class("form-entry")
        form_grid.attach(self.reason_entry, 1, 2, 1, 1)

        self.pack_start(form_grid, False, False, 0)

        self.product_label = Gtk.Label(label="")
        self.product_label.set_halign(Gtk.Align.START)
        self.product_label.set_margin_bottom(4)
        self.pack_start(self.product_label, False, False, 0)

        self.stock_label = Gtk.Label(label="")
        self.stock_label.set_halign(Gtk.Align.START)
        self.stock_label.set_margin_bottom(8)
        self.pack_start(self.stock_label, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        submit_btn = Gtk.Button(label="Тохируулах")
        submit_btn.get_style_context().add_class("suggested-action")
        submit_btn.connect("clicked", self._on_submit)
        btn_box.pack_start(submit_btn, False, False, 0)

        clear_btn = Gtk.Button(label="Цэвэрлэх")
        clear_btn.connect("clicked", self._on_clear)
        btn_box.pack_start(clear_btn, False, False, 0)
        self.pack_start(btn_box, False, False, 0)

        history_label = Gtk.Label(label="Сүүлийн тохируулгууд:")
        history_label.set_halign(Gtk.Align.START)
        history_label.set_margin_top(16)
        history_label.get_style_context().add_class("dialog-title")
        self.pack_start(history_label, False, False, 0)

        hist_scroll = Gtk.ScrolledWindow()
        hist_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        hist_scroll.set_vexpand(True)
        self.history_store = Gtk.ListStore(str, str, str, str)
        self.history_tree = Gtk.TreeView(model=self.history_store)
        self.history_tree.get_style_context().add_class("treeview-table")

        columns = [
            ("Огноо", 0, 150),
            ("Бараа", 1, 200),
            ("Өөрчлөлт", 2, 100),
            ("Шалтгаан", 3, 200),
        ]
        for i, (title_text, col_id, width) in enumerate(columns):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title_text, renderer, text=col_id)
            col.set_min_width(width)
            col.set_resizable(True)
            self.history_tree.append_column(col)

        hist_scroll.add(self.history_tree)
        self.pack_start(hist_scroll, True, True, 0)

        self._current_product = None
        self._load_history()

    def _set_qty(self, val):
        try:
            current = int(self.qty_entry.get_text() or "0")
        except ValueError:
            current = 0
        self.qty_entry.set_text(str(current + val))

    def _on_barcode_activate(self, entry):
        barcode = entry.get_text().strip()
        if not barcode or not self.cache:
            return

        product = self.cache.get_by_barcode(barcode)
        if not product:
            for p in self.cache.all_products():
                if p.get("barcode", "") == barcode:
                    product = p
                    break

        if product:
            self._show_product(product)
        else:
            self.product_label.set_text("Бараа олдсонгүй!")

    def _show_product(self, product):
        self._current_product = product
        name = product.get("name", "?")
        category = product.get("category", "")
        icon = get_category_icon(category)
        price = product.get("price", 0)
        stock = product.get("stock_qty", "?")
        self.product_label.set_text(f"{icon} {name} — {format_money(price)}")
        self.stock_label.set_text(f"Одоогийн үлдэгдэл: {stock}")

    def _on_submit(self, btn):
        if not self._current_product:
            self._show_error("Эхлээд бараа сонгоно уу")
            return
        try:
            qty = int(self.qty_entry.get_text() or "0")
        except ValueError:
            self._show_error("Тоо ширхэгээ зөв оруулна уу")
            return
        if qty == 0:
            self._show_error("Тоо ширхэг 0 байж болохгүй")
            return

        reason = self.reason_entry.get_text().strip() or "Гараар тохируулга"
        product_id = self._current_product["id"]
        product_name = self._current_product.get("name", "?")

        def _write():
            import database as db
            return db.adjust_stock(product_id, qty, reason)

        def _on_done(result):
            if result is None:
                self._show_error("Хадгалалт амжилтгүй")
                return
            self._show_toast(f"{product_name}: {qty:+d} амжилттай")
            self._load_history()
            if self.cache:
                self.cache.invalidate()
            self._on_clear()
            try:
                self.barcode_entry.grab_focus()
            except Exception:
                pass

        def _on_error(err):
            self._show_error(f"Алдаа: {err}")

        if self.workqueue:
            self.workqueue.write(_write, on_done=_on_done, on_error=_on_error)
        else:
            try:
                result = _write()
            except Exception as e:
                _on_error(str(e))
            else:
                _on_done(result)

    def _on_clear(self, btn=None):
        self._current_product = None
        self.barcode_entry.set_text("")
        self.qty_entry.set_text("")
        self.reason_entry.set_text("")
        self.product_label.set_text("")
        self.stock_label.set_text("")
        self.barcode_entry.grab_focus()

    def _load_history(self):
        def _fetch():
            import database as db
            return db.get_stock_adjustments(limit=50)

        def _populate(data):
            self.history_store.clear()
            for adj in data:
                self.history_store.append([
                    adj.get("created_at", ""),
                    adj.get("product_name", "?"),
                    f"{adj.get('quantity_change', 0):+d}",
                    adj.get("reason", ""),
                ])

        def _on_error(err):
            self._show_error(f"Түүх ачаалахад алдаа: {err}")

        if self.workqueue:
            self.workqueue.async_op(_fetch, on_result=_populate, on_error=_on_error)
        else:
            try:
                _populate(_fetch())
            except Exception as e:
                _on_error(str(e))

    def _show_error(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        dialog.run()
        dialog.destroy()

    def _show_toast(self, msg):
        if hasattr(self.app, 'pos_screen') and self.app.pos_screen:
            self.app.pos_screen._show_toast(msg, "success")

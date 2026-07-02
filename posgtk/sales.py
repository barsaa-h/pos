"""
posgtk/sales.py — Sales history with pagination and detail view.
"""
import logging
import json
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.sales")


class SalesScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app
        self._page = 1
        self._per_page = 50
        self._date_from = ""
        self._date_to = ""

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.set_margin_start(8)

        filter_box.set_margin_end(8)

        filter_box.set_margin_top(8)

        filter_box.set_margin_bottom(8)

        self.date_from_entry = Gtk.Entry()
        self.date_from_entry.set_placeholder_text("Эхлэх (YYYY-MM-DD)")
        self.date_from_entry.set_tooltip_text("Огноогоор шүүх — эхлэх")
        filter_box.pack_start(self.date_from_entry, False, False, 0)

        self.date_to_entry = Gtk.Entry()
        self.date_to_entry.set_placeholder_text("Дуусах (YYYY-MM-DD)")
        self.date_to_entry.set_tooltip_text("Огноогоор шүүх — дуусах")
        filter_box.pack_start(self.date_to_entry, False, False, 0)

        filter_btn = Gtk.Button(label="Шүүх")
        filter_btn.connect("clicked", lambda b: self._apply_filter())
        filter_box.pack_start(filter_btn, False, False, 0)

        clear_btn = Gtk.Button(label="Цэвэрлэх")
        clear_btn.connect("clicked", lambda b: self._clear_filter())
        filter_box.pack_start(clear_btn, False, False, 0)

        self.pack_start(filter_box, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_margin_start(8)

        scrolled.set_margin_end(8)

        scrolled.set_margin_top(8)

        scrolled.set_margin_bottom(8)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.store = Gtk.ListStore(int, str, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.get_style_context().add_class("treeview-table")

        cols = [
            ("ID", 0, 60), ("Огноо", 1, 140), ("Төлбөр", 2, 80),
            ("Нийт", 3, 100), ("Буцаалт", 4, 60),
            ("eBarimt", 5, 70), ("sale_id", 6, 0),
        ]
        for title, col_id, width in cols:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            if width == 0:
                col.set_visible(False)
            self.tree.append_column(col)

        self.tree.connect("row-activated", self._on_row_activated)
        scrolled.add(self.tree)
        self.pack_start(scrolled, True, True, 0)

        page_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        page_box.set_halign(Gtk.Align.CENTER)
        page_box.set_margin_start(8)
        page_box.set_margin_end(8)
        page_box.set_margin_top(4)
        page_box.set_margin_bottom(4)

        self.prev_btn = Gtk.Button(label="‹ Өмнөх")
        self.prev_btn.connect("clicked", lambda b: self._change_page(-1))
        self.prev_btn.set_sensitive(False)
        page_box.pack_start(self.prev_btn, False, False, 0)

        self.page_label = Gtk.Label(label="Хуудас 1")
        self.page_label.set_margin_start(12)
        self.page_label.set_margin_end(12)
        page_box.pack_start(self.page_label, False, False, 0)

        self.next_btn = Gtk.Button(label="Дараах ›")
        self.next_btn.connect("clicked", lambda b: self._change_page(1))
        page_box.pack_start(self.next_btn, False, False, 0)

        self.pack_start(page_box, False, False, 0)

        self.show_all()
        GLib.idle_add(self._load_data)

    def _load_data(self, *args):
        date_from = self._date_from or None
        date_to = self._date_to or None
        page = self._page
        per_page = self._per_page

        def fetch_background():
            import database as db
            sales = db.get_sales_list(
                date_from=date_from, date_to=date_to,
                limit=per_page, offset=(page - 1) * per_page,
            )
            total_count = db.get_sales_count(date_from=date_from, date_to=date_to)
            total_pages = max(1, (total_count + per_page - 1) // per_page)
            return sales, total_count, total_pages

        def on_fetch_complete(result):
            sales, total_count, total_pages = result
            self.store.clear()
            for s in sales:
                is_return = s.get("payment_type") == "return"
                self.store.append([
                    s.get("id", 0),
                    s.get("created_at", ""),
                    s.get("payment_type", ""),
                    format_money(s.get("total", 0)),
                    "Буцаасан" if is_return else "",
                    s.get("ebarimt_status", ""),
                    s.get("id", 0),
                ])
            self.page_label.set_label(f"Хуудас {page}/{total_pages}  (Нийт: {total_count})")
            self.prev_btn.set_sensitive(page > 1)
            self.next_btn.set_sensitive(page < total_pages)

        def on_fetch_error(error_msg):
            logger.error(f"Background sales load failed: {error_msg}")

        if self.app and self.app.workqueue:
            self.app.workqueue.async_op(fetch_background, on_result=on_fetch_complete, on_error=on_fetch_error)
        else:
            try:
                on_fetch_complete(fetch_background())
            except Exception as e:
                on_fetch_error(str(e))

    def _change_page(self, delta):
        self._page = max(1, self._page + delta)
        self._load_data()

    def _on_row_activated(self, tree, path, col):
        it = self.store.get_iter(path)
        sale_id = self.store.get_value(it, 6)
        self._show_detail(sale_id)

    def _show_detail(self, sale_id):
        try:
            import database as db
            sale = db.get_sale(sale_id)
        except Exception:
            return
        if not sale:
            return

        items = sale.get("items", [])
        try:
            if isinstance(items, str):
                items = json.loads(items)
        except Exception:
            items = []

        dialog = Gtk.Dialog(
            title=f"Борлуулалт #{sale.get('id', '?')}",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(500, 400)
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_start(16)

        content.set_margin_end(16)

        content.set_margin_top(16)

        content.set_margin_bottom(16)

        info_lines = [
            f"ID: {sale.get('id', '')}",
            f"Огноо: {sale.get('created_at', '')}",
            f"Төлбөр: {sale.get('payment_type', '')}",
        ]
        txn_id = sale.get("terminal_txn_id", "")
        if txn_id:
            info_lines.append(f"Терминал гүйлгээ: {txn_id}")

        for line in info_lines:
            content.add(Gtk.Label(label=line, xalign=0))

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        content.add(sep)

        items_label = Gtk.Label(label="<b>Бараа:</b>", use_markup=True, xalign=0)
        content.add(items_label)

        for item in (items or []):
            if isinstance(item, dict):
                name = item.get("product_name", "")
                qty = item.get("quantity", 1)
                subtotal = item.get("subtotal", 0)
            else:
                name, qty, subtotal = str(item), 1, 0
            content.add(Gtk.Label(
                label=f"  {qty}× {name[:30]} — {format_money(subtotal)}", xalign=0
            ))

        total_label = Gtk.Label()
        total_label.set_markup(f"<b>Нийт: {format_money(sale.get('total', 0))}</b>")
        total_label.set_margin_top(8)
        content.add(total_label)

        if sale.get("change_given"):
            content.add(Gtk.Label(label=f"Буцаалт: {format_money(sale['change_given'])}"))

        ebarimt = sale.get("ebarimt_status", "")
        if ebarimt:
            content.add(Gtk.Label(label=f"eBarimt: {ebarimt}"))

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_margin_top(12)

        print_btn = Gtk.Button(label="🖨 Хэвлэх")
        print_btn.connect("clicked", lambda b: self._do_print(sale))
        btn_box.pack_start(print_btn, False, False, 0)

        if sale.get("payment_type") != "return":
            return_btn = Gtk.Button(label="↩ Буцаалт")
            return_btn.get_style_context().add_class("destructive-action")
            return_btn.connect("clicked", lambda b: self._do_return(sale_id, dialog))
            btn_box.pack_start(return_btn, False, False, 0)

        btn_box.pack_end(Gtk.Button(label="✕ Хаах"), False, False, 0)

        content.add(btn_box)
        dialog.add_button("Хаах", Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _do_print(self, sale):
        if not sale:
            return

        def async_print_job():
            from printer import print_receipt
            from config import get_store_info
            print_receipt(sale, get_store_info())
            return True

        def on_print_success(result):
            if self.app and hasattr(self.app, 'pos_screen'):
                self.app.pos_screen._show_toast("🖨 Баримтыг амжилттай дахин хэвлэлээ.", "success")

        def on_print_failure(error_msg):
            logger.error(f"Receipt reprint failed: {error_msg}")
            if self.app and hasattr(self.app, 'pos_screen'):
                self.app.pos_screen._show_toast(f"❌ Хэвлэхэд алдаа гарлаа: {error_msg}", "warning")

        if self.app and self.app.workqueue:
            self.app.workqueue.async_op(async_print_job, on_result=on_print_success, on_error=on_print_failure)
        else:
            try:
                async_print_job()
            except Exception as e:
                logger.error(f"Synchronous fallback print failed: {e}")

    def _do_return(self, sale_id, detail_dialog):
        confirm = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Борлуулалт #{sale_id}-г буцаах уу?",
        )
        resp = confirm.run()
        confirm.destroy()
        if resp != Gtk.ResponseType.YES:
            return

        def _write():
            import database as db
            return db.process_return(sale_id)

        def _on_done(result):
            if result is None:
                self._show_return_error("Буцаалт амжилтгүй")
                return
            detail_dialog.destroy()
            if self.app and hasattr(self.app, 'pos_screen'):
                self.app.pos_screen._show_toast(f"#{sale_id} буцаалт амжилттай", "success")
                try:
                    from printer import print_receipt
                    from config import get_store_info
                    print_receipt(result, get_store_info())
                except Exception:
                    pass

        def _on_error(err):
            self._show_return_error(f"Алдаа: {err}")

        if self.app and self.app.workqueue:
            self.app.workqueue.write(_write, on_done=_on_done, on_error=_on_error)
        else:
            _on_done(_write())

    def _show_return_error(self, msg):
        err = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        err.run()
        err.destroy()

    def _apply_filter(self):
        self._date_from = self.date_from_entry.get_text().strip()
        self._date_to = self.date_to_entry.get_text().strip()
        self._page = 1
        self._load_data()

    def _clear_filter(self):
        self._date_from = ""
        self._date_to = ""
        self.date_from_entry.set_text("")
        self.date_to_entry.set_text("")
        self._page = 1
        self._load_data()

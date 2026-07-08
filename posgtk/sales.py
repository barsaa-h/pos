"""
posgtk/sales.py — Sales history with pagination, quick filters, modern ListBox layout.
"""
import logging
import json
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.sales")


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _yesterday_str():
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _week_start_str():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def _month_start_str():
    today = datetime.now()
    return today.replace(day=1).strftime("%Y-%m-%d")


_PAYMENT_LABELS = {
    "cash": "💵 Бэлэн",
    "card": "💳 Карт",
    "qr": "📱 QR",
    "split": "🔀 Холимог",
    "return": "↩️ Буцаалт",
}

_PAYMENT_CLASSES = {
    "cash": "pay-cash",
    "card": "pay-card",
    "qr": "pay-qr",
    "split": "pay-split",
    "return": "pay-return",
}

_EBARIMT_CLASSES = {
    "sent": "ebarimt-sent",
    "pending": "ebarimt-pending",
    "failed": "ebarimt-failed",
    "none": "ebarimt-none",
}


def payment_badge(payment_type):
    label = _PAYMENT_LABELS.get(payment_type, payment_type)
    cls = _PAYMENT_CLASSES.get(payment_type, "")
    return f'<span class="payment-badge {cls}">{label}</span>'


class SalesScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app
        self._page = 1
        self._per_page = 50
        self._date_from = ""
        self._date_to = ""

        header = Gtk.Label(label="📋 Борлуулалтын түүх")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        qf_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        qf_box.set_margin_start(16)
        qf_box.set_margin_end(16)
        qf_box.set_margin_top(8)
        qf_box.set_margin_bottom(4)

        self._qf_buttons = []
        for label, handler in [
            ("Өнөөдөр", self._qf_today),
            ("Өчигдөр", self._qf_yesterday),
            ("Энэ долоо хоног", self._qf_week),
            ("Энэ сар", self._qf_month),
        ]:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("quick-filter-btn")
            btn.connect("clicked", handler)
            qf_box.pack_start(btn, False, False, 0)
            self._qf_buttons.append(btn)

        self.pack_start(qf_box, False, False, 0)

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.get_style_context().add_class("search-toolbar")

        self.date_from_entry = Gtk.Entry()
        self.date_from_entry.set_placeholder_text("📅  Эхлэх (YYYY-MM-DD)")
        self.date_from_entry.set_tooltip_text("Огноогоор шүүх — эхлэх")
        filter_box.pack_start(self.date_from_entry, False, False, 0)

        self.date_to_entry = Gtk.Entry()
        self.date_to_entry.set_placeholder_text("📅  Дуусах (YYYY-MM-DD)")
        self.date_to_entry.set_tooltip_text("Огноогоор шүүх — дуусах")
        filter_box.pack_start(self.date_to_entry, False, False, 0)

        filter_btn = Gtk.Button(label="🔍 Шүүх")
        filter_btn.get_style_context().add_class("category-btn")
        filter_btn.connect("clicked", lambda b: self._apply_filter())
        filter_box.pack_start(filter_btn, False, False, 0)

        clear_btn = Gtk.Button(label="❌ Цэвэрлэх")
        clear_btn.get_style_context().add_class("category-btn")
        clear_btn.connect("clicked", lambda b: self._clear_filter())
        filter_box.pack_start(clear_btn, False, False, 0)

        self.pack_start(filter_box, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-activated", self._on_row_activated)
        self.list_box.get_style_context().add_class("sales-list")
        scrolled.add(self.list_box)
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
        GLib.idle_add(self._load_data)

    def _load_data(self, *args):
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        date_from = self._date_from or None
        date_to = self._date_to or None
        page = self._page
        per_page = self._per_page

        try:
            import database as db
            sales = db.get_sales_list(
                date_from=date_from, date_to=date_to,
                limit=per_page, offset=(page - 1) * per_page,
            )
            total_count = db.get_sales_count(date_from=date_from, date_to=date_to)
            total_pages = max(1, (total_count + per_page - 1) // per_page)
        except Exception as e:
            logger.error(f"Sales load failed: {e}")
            err_lbl = Gtk.Label(label=f"Алдаа: {e}")
            err_lbl.set_halign(Gtk.Align.CENTER)
            err_lbl.set_margin_top(24)
            err_lbl.get_style_context().add_class("text-muted")
            self.list_box.add(err_lbl)
            self.list_box.show_all()
            return

        header_row = Gtk.ListBoxRow()
        header_row.get_style_context().add_class("sales-header-row")
        header_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_hbox.set_margin_start(12)
        header_hbox.set_margin_end(12)
        header_hbox.set_margin_top(8)
        header_hbox.set_margin_bottom(8)

        for text, width, xalign in [
            ("#", 50, 0),
            ("Огноо", 150, 0),
            ("Төлбөр", 110, 0),
            ("Нийт", 110, 1),
            ("eBarimt", 90, 0),
        ]:
            lbl = Gtk.Label(label=text, xalign=xalign)
            if width:
                lbl.set_size_request(width, -1)
            else:
                lbl.set_hexpand(True)
            lbl.get_style_context().add_class("text-muted")
            header_hbox.pack_start(lbl, False if width else True, False, 0)

        header_row.add(header_hbox)
        self.list_box.add(header_row)

        for s in sales:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("sales-row")
            row._sale_id = s.get("id")

            is_return = s.get("payment_type") == "return"
            if is_return:
                row.get_style_context().add_class("sales-row-return")

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hbox.set_margin_start(12)
            hbox.set_margin_end(12)
            hbox.set_margin_top(10)
            hbox.set_margin_bottom(10)

            id_lbl = Gtk.Label(label=str(s.get("id", "")), xalign=0)
            id_lbl.set_size_request(50, -1)
            id_lbl.get_style_context().add_class("sale-id")
            hbox.pack_start(id_lbl, False, False, 0)

            date_lbl = Gtk.Label(label=s.get("created_at", ""), xalign=0)
            date_lbl.set_size_request(150, -1)
            date_lbl.get_style_context().add_class("sale-date")
            hbox.pack_start(date_lbl, False, False, 0)

            pt = s.get("payment_type", "")
            pt_lbl = Gtk.Label(label=_PAYMENT_LABELS.get(pt, pt), xalign=0)
            pt_lbl.set_size_request(110, -1)
            pt_cls = _PAYMENT_CLASSES.get(pt, "")
            if pt_cls:
                pt_lbl.get_style_context().add_class(pt_cls)
            hbox.pack_start(pt_lbl, False, False, 0)

            total = s.get("total", 0)
            total_text = format_money(total)
            if is_return:
                total_text = f"-{total_text}"
            total_lbl = Gtk.Label(label=total_text, xalign=1)
            total_lbl.set_size_request(110, -1)
            total_lbl.get_style_context().add_class("sale-total")
            if is_return:
                total_lbl.get_style_context().add_class("sale-total-return")
            hbox.pack_start(total_lbl, False, False, 0)

            ebarimt = s.get("ebarimt_status", "")
            ebarimt_lbl = Gtk.Label(label=ebarimt or "-", xalign=0)
            ebarimt_lbl.set_size_request(90, -1)
            ebarimt_cls = _EBARIMT_CLASSES.get(ebarimt, "ebarimt-none")
            ebarimt_lbl.get_style_context().add_class(ebarimt_cls)
            hbox.pack_start(ebarimt_lbl, False, False, 0)

            row.add(hbox)
            self.list_box.add(row)

        if not sales:
            empty_lbl = Gtk.Label(label="Борлуулалт олдсонгүй.")
            empty_lbl.set_halign(Gtk.Align.CENTER)
            empty_lbl.set_margin_top(32)
            empty_lbl.get_style_context().add_class("text-muted")
            self.list_box.add(empty_lbl)

        self.page_label.set_label(f"Хуудас {page}/{total_pages}  (Нийт: {total_count})")
        self.prev_btn.set_sensitive(page > 1)
        self.next_btn.set_sensitive(page < total_pages)

        self.list_box.show_all()

    def _change_page(self, delta):
        self._page = max(1, self._page + delta)
        self._load_data()

    def _on_row_activated(self, listbox, row):
        sale_id = getattr(row, '_sale_id', None)
        if sale_id:
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
        content.get_style_context().add_class("form-card")
        content.set_spacing(8)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        dlg_title = Gtk.Label()
        dlg_title.set_markup(f'<span weight="800" size="14000">Борлуулалт #{sale.get("id", "?")}</span>')
        dlg_title.set_halign(Gtk.Align.START)
        content.add(dlg_title)

        info_lines = [
            ("ID", str(sale.get('id', ''))),
            ("Огноо", sale.get('created_at', '')),
            ("Төлбөр", _PAYMENT_LABELS.get(sale.get('payment_type', ''), sale.get('payment_type', ''))),
        ]
        txn_id = sale.get("terminal_txn_id", "")
        if txn_id:
            info_lines.append(("Терминал", txn_id))

        for lab, val in info_lines:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row.pack_start(Gtk.Label(label=f"<b>{lab}:</b>", use_markup=True, xalign=0), False, False, 0)
            row.pack_start(Gtk.Label(label=val, xalign=0), True, True, 0)
            content.add(row)

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
        print_btn.get_style_context().add_class("category-btn")
        print_btn.connect("clicked", lambda b: self._do_print(sale))
        btn_box.pack_start(print_btn, False, False, 0)

        if sale.get("payment_type") != "return":
            return_btn = Gtk.Button(label="↩ Буцаалт")
            return_btn.get_style_context().add_class("destructive-action")
            return_btn.connect("clicked", lambda b: self._do_return(sale_id, dialog))
            btn_box.pack_start(return_btn, False, False, 0)

        close_btn = Gtk.Button(label="✕ Хаах")
        close_btn.get_style_context().add_class("category-btn")
        btn_box.pack_end(close_btn, False, False, 0)

        content.add(btn_box)
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
            self._load_data()
            if self.app and hasattr(self.app, 'pos_screen'):
                self.app.pos_screen._show_toast(f"#{sale_id} буцаалт амжилттай", "success")
                try:
                    from printer import print_receipt
                    from config import get_store_info
                    print_receipt(result, get_store_info())
                except Exception as e:
                    logger.error(f"Return print failed: {e}")
                    self.app.pos_screen._show_toast(f"⚠️ Хэвлэх алдаа: {e}", "warning")

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

    def _qf_today(self, btn):
        self._set_qf_dates(_today_str(), _today_str())

    def _qf_yesterday(self, btn):
        self._set_qf_dates(_yesterday_str(), _yesterday_str())

    def _qf_week(self, btn):
        self._set_qf_dates(_week_start_str(), _today_str())

    def _qf_month(self, btn):
        self._set_qf_dates(_month_start_str(), _today_str())

    def _set_qf_dates(self, date_from, date_to):
        self.date_from_entry.set_text(date_from)
        self.date_to_entry.set_text(date_to)
        self._date_from = date_from
        self._date_to = date_to
        self._page = 1
        self._load_data()

"""
posgtk/reports.py — Sales and profit reports with modern card layout, Niit filter,
separate qty/amount columns, and top products table.
"""
import logging
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.reports")


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _week_start_str():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def _month_start_str():
    today = datetime.now()
    return today.replace(day=1).strftime("%Y-%m-%d")


class ReportsScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        header = Gtk.Label(label="📈 Тайлан")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        qf_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        qf_box.set_margin_start(16)
        qf_box.set_margin_end(16)
        qf_box.set_margin_top(8)
        qf_box.set_margin_bottom(4)

        for label, handler in [
            ("📅 Өнөөдөр", self._qf_today),
            ("📅 Энэ долоо хоног", self._qf_week),
            ("📅 Энэ сар", self._qf_month),
            ("📅 Бүх хугацаа", self._qf_all),
        ]:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("quick-filter-btn")
            btn.connect("clicked", handler)
            qf_box.pack_start(btn, False, False, 0)

        self.pack_start(qf_box, False, False, 0)

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.get_style_context().add_class("search-toolbar")

        self.date_from_entry = Gtk.Entry()
        self.date_from_entry.set_placeholder_text("📅  Эхлэх (YYYY-MM-DD)")
        filter_box.pack_start(self.date_from_entry, False, False, 0)

        self.date_to_entry = Gtk.Entry()
        self.date_to_entry.set_placeholder_text("📅  Дуусах (YYYY-MM-DD)")
        filter_box.pack_start(self.date_to_entry, False, False, 0)

        run_btn = Gtk.Button(label="📊 Гаргах")
        run_btn.get_style_context().add_class("category-btn")
        run_btn.connect("clicked", lambda b: self._load_data())
        filter_box.pack_start(run_btn, False, False, 0)

        self.pack_start(filter_box, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.content_box.set_margin_start(16)
        self.content_box.set_margin_end(16)
        self.content_box.set_margin_top(16)
        self.content_box.set_margin_bottom(16)
        scrolled.add(self.content_box)

        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)
        self.show_all()
        GLib.idle_add(self._load_data)

    def _qf_today(self, btn):
        self.date_from_entry.set_text(_today_str())
        self.date_to_entry.set_text(_today_str())
        self._load_data()

    def _qf_week(self, btn):
        self.date_from_entry.set_text(_week_start_str())
        self.date_to_entry.set_text(_today_str())
        self._load_data()

    def _qf_month(self, btn):
        self.date_from_entry.set_text(_month_start_str())
        self.date_to_entry.set_text(_today_str())
        self._load_data()

    def _qf_all(self, btn):
        self.date_from_entry.set_text("")
        self.date_to_entry.set_text("")
        self._load_data()

    def _make_group_label(self, text):
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{text}</b>")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_top(8)
        return lbl

    def _load_data(self, *args):
        for child in self.content_box.get_children():
            self.content_box.remove(child)

        date_from = self.date_from_entry.get_text().strip() or None
        date_to = self.date_to_entry.get_text().strip() or None

        try:
            import database as db
            summary = db.get_profit_summary(date_from=date_from, date_to=date_to)
            report = db.get_sales_report(date_from=date_from, date_to=date_to)
        except Exception as e:
            self.content_box.add(Gtk.Label(label=f"Алдаа: {e}"))
            self.content_box.show_all()
            return

        total_sales_amount = summary.get("total_sales", 0)
        total_profit = summary.get("total_profit", 0)
        cash_total = summary.get("cash_total", 0)
        card_total = summary.get("card_total", 0)
        split_total = summary.get("split_total", 0)
        total_cost = summary.get("total_cost", 0)
        return_total = summary.get("return_total", 0)
        avg_sale = summary.get("avg_sale", 0)
        avg_items = summary.get("avg_items_per_sale", 0)
        total_count = summary.get("total_count", 0)
        total_qty = summary.get("total_qty", 0)

        stat_grid = Gtk.Grid()
        stat_grid.set_column_spacing(10)
        stat_grid.set_row_spacing(10)

        stat_data = []
        stat_data.append(("🧾", format_money(total_sales_amount), "Нийт борлуулалт"))
        stat_data.append(("💰", format_money(total_profit), "Цэвэр ашиг"))
        stat_data.append(("💵", format_money(cash_total), "Бэлэн"))
        stat_data.append(("💳", format_money(card_total), "Карт"))
        stat_data.append(("🔀", format_money(split_total), "Холимог"))

        if return_total:
            stat_data.append(("↩️", format_money(return_total), "Буцаалт"))

        for i, (icon, value, label) in enumerate(stat_data):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.get_style_context().add_class("stat-card")
            card.set_size_request(160, -1)
            icon_lbl = Gtk.Label(label=icon)
            icon_lbl.get_style_context().add_class("stat-card-icon")
            card.pack_start(icon_lbl, False, False, 0)
            val_lbl = Gtk.Label(label=str(value))
            val_lbl.get_style_context().add_class("stat-value")
            card.pack_start(val_lbl, False, False, 0)
            lab_lbl = Gtk.Label(label=label)
            lab_lbl.get_style_context().add_class("stat-label")
            card.pack_start(lab_lbl, False, False, 0)
            stat_grid.attach(card, i % 6, i // 6, 1, 1)

        self.content_box.add(stat_grid)

        if total_qty or total_count:
            qty_label = self._make_group_label("📊 Тоо ширхэг")
            self.content_box.add(qty_label)

            qty_grid = Gtk.Grid()
            qty_grid.set_column_spacing(10)
            qty_grid.set_row_spacing(10)
            qty_grid.set_margin_top(4)

            qty_cards = []
            if total_qty:
                qty_cards.append(("📦", str(total_qty), "Нийт зарагдсан тоо"))
            if total_count:
                qty_cards.append(("🧾", str(total_count), "Нийт гүйлгээ"))
            if avg_items:
                qty_cards.append(("📊", str(avg_items), "Дундаж бараа/гүйлгээ"))
            if avg_sale:
                qty_cards.append(("💰", format_money(avg_sale), "Дундаж дүн/гүйлгээ"))

            for i, (icon, value, label) in enumerate(qty_cards):
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                card.get_style_context().add_class("stat-card")
                card.set_size_request(160, -1)
                icon_lbl = Gtk.Label(label=icon)
                icon_lbl.get_style_context().add_class("stat-card-icon")
                card.pack_start(icon_lbl, False, False, 0)
                val_lbl = Gtk.Label(label=str(value))
                val_lbl.get_style_context().add_class("stat-value")
                card.pack_start(val_lbl, False, False, 0)
                lab_lbl = Gtk.Label(label=label)
                lab_lbl.get_style_context().add_class("stat-label")
                card.pack_start(lab_lbl, False, False, 0)
                qty_grid.attach(card, i % 4, i // 4, 1, 1)

            self.content_box.add(qty_grid)

        top_products = report.get("top_products", [])
        if top_products:
            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            sep.set_margin_top(12)
            sep.set_margin_bottom(8)
            self.content_box.add(sep)

            title = self._make_group_label("🏆 Хамгийн их зарагдсан бараа")
            self.content_box.add(title)

            list_box = Gtk.ListBox()
            list_box.set_selection_mode(Gtk.SelectionMode.NONE)

            header_row = Gtk.ListBoxRow()
            header_row.get_style_context().add_class("data-row")
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

            header_data = [
                ("", 32, 0),
                ("Бараа", 0, 0),
                ("Тоо (ширхэг)", 120, 1),
                ("Орлого (₮)", 140, 1),
            ]
            for text, width, xalign in header_data:
                lbl = Gtk.Label(label=text, xalign=xalign)
                lbl.set_size_request(width, -1) if width else lbl.set_hexpand(True)
                lbl.get_style_context().add_class("text-muted")
                hbox.pack_start(lbl, False if width else True, False, 0)
            header_row.add(hbox)
            list_box.add(header_row)

            from posgtk.widgets import CAT_ICONS
            for p in top_products:
                row = Gtk.ListBoxRow()
                row.get_style_context().add_class("data-row")
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

                cat = p.get("category", "Бусад")
                icon = CAT_ICONS.get(cat, "📦")
                icon_lbl = Gtk.Label(label=icon, xalign=0)
                icon_lbl.set_size_request(32, -1)
                hbox.pack_start(icon_lbl, False, False, 0)

                name_lbl = Gtk.Label(label=p.get("product_name", ""), xalign=0, hexpand=True)
                hbox.pack_start(name_lbl, True, True, 0)

                qty_lbl = Gtk.Label(label=str(p.get("total_qty", 0)), xalign=1)
                qty_lbl.set_size_request(120, -1)
                hbox.pack_start(qty_lbl, False, False, 0)

                rev_lbl = Gtk.Label(label=f"{format_money(p.get('total_revenue', 0))} ₮", xalign=1)
                rev_lbl.set_size_request(140, -1)
                rev_lbl.get_style_context().add_class("text-muted")
                hbox.pack_start(rev_lbl, False, False, 0)

                row.add(hbox)
                list_box.add(row)

            self.content_box.add(list_box)

        if not total_sales_amount and not top_products:
            no_data = Gtk.Label()
            no_data.set_markup('<span size="12000">Тайлангийн мэдээлэл байхгүй</span>')
            no_data.set_halign(Gtk.Align.START)
            no_data.set_margin_top(12)
            no_data.get_style_context().add_class("text-muted")
            self.content_box.add(no_data)

        self.content_box.show_all()

"""
posgtk/reports.py — Sales and profit reports with stat cards, quick filters, top products.
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

        stat_cards = Gtk.FlowBox()
        stat_cards.set_selection_mode(Gtk.SelectionMode.NONE)
        stat_cards.set_column_spacing(12)
        stat_cards.set_row_spacing(12)

        cards_data = [
            ("🧾", format_money(summary.get("total_sales", 0)), "Нийт борлуулалт"),
            ("💰", format_money(summary.get("total_profit", 0)), "Цэвэр орлого"),
            ("💵", format_money(summary.get("cash_total", 0)), "Бэлэн"),
            ("💳", format_money(summary.get("card_total", 0)), "Карт"),
            ("🔀", format_money(summary.get("split_total", 0)), "Холимог"),
            ("📈", format_money(summary.get("total_profit", 0)), "Цэвэр ашиг"),
            ("📦", format_money(summary.get("total_cost", 0)), "Нийт өртөг"),
        ]
        return_total = summary.get("return_total", 0)
        if return_total:
            cards_data.append(("↩️", format_money(return_total), "Буцаалт"))

        for icon, value, label in cards_data:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.get_style_context().add_class("stat-card")
            icon_lbl = Gtk.Label(label=icon)
            icon_lbl.get_style_context().add_class("stat-card-icon")
            card.pack_start(icon_lbl, False, False, 0)
            val_lbl = Gtk.Label(label=str(value))
            val_lbl.get_style_context().add_class("stat-value")
            card.pack_start(val_lbl, False, False, 0)
            lab_lbl = Gtk.Label(label=label)
            lab_lbl.get_style_context().add_class("stat-label")
            card.pack_start(lab_lbl, False, False, 0)
            stat_cards.add(card)

        self.content_box.add(stat_cards)

        avg_txn = summary.get("avg_sale", 0)
        avg_items = summary.get("avg_items_per_sale", 0)
        if avg_txn or avg_items:
            insight_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            insight_box.set_margin_top(8)
            if avg_txn:
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                card.get_style_context().add_class("insight-card")
                val = Gtk.Label(label=str(format_money(avg_txn)))
                val.get_style_context().add_class("value")
                card.pack_start(val, False, False, 0)
                lab = Gtk.Label(label="Дундаж гүйлгээний дүн")
                lab.get_style_context().add_class("label")
                card.pack_start(lab, False, False, 0)
                insight_box.pack_start(card, True, True, 0)
            if avg_items:
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                card.get_style_context().add_class("insight-card")
                val = Gtk.Label(label=str(avg_items))
                val.get_style_context().add_class("value")
                card.pack_start(val, False, False, 0)
                lab = Gtk.Label(label="Дундаж барааны тоо")
                lab.get_style_context().add_class("label")
                card.pack_start(lab, False, False, 0)
                insight_box.pack_start(card, True, True, 0)
            self.content_box.add(insight_box)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        self.content_box.add(sep)

        payment_label = Gtk.Label()
        payment_label.set_markup("<b>Төлбөрийн төрлөөр:</b>")
        payment_label.set_halign(Gtk.Align.START)
        self.content_box.add(payment_label)

        payments = report.get("payments", [])
        if payments:
            for p in payments:
                self.content_box.add(Gtk.Label(
                    label=f"  {p.get('payment_type', '')}: {format_money(p.get('total_amount', 0))} ({p.get('count', 0)} удаа)",
                    xalign=0,
                ))
        else:
            no_data = Gtk.Label()
            no_data.set_markup('<span size="12000">Тайлангийн мэдээлэл байхгүй</span>')
            no_data.set_halign(Gtk.Align.START)
            no_data.set_margin_top(12)
            no_data.get_style_context().add_class("text-muted")
            self.content_box.add(no_data)

        top_products = report.get("top_products", [])
        if top_products:
            sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            sep2.set_margin_top(12)
            sep2.set_margin_bottom(8)
            self.content_box.add(sep2)

            title = Gtk.Label()
            title.set_markup("<b>🏆 Хамгийн их зарагдсан бараа</b>")
            title.set_halign(Gtk.Align.START)
            self.content_box.add(title)

            list_box = Gtk.ListBox()
            list_box.set_selection_mode(Gtk.SelectionMode.NONE)

            header_row = Gtk.ListBoxRow()
            header_row.get_style_context().add_class("data-row")
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for text, width in [("Бараа", 0), ("Тоо", 80), ("Орлого", 120)]:
                lbl = Gtk.Label(label=text, xalign=1 if width else 0, hexpand=True if width == 0 else False)
                lbl.get_style_context().add_class("text-muted")
                hbox.pack_start(lbl, True, True, 0)
            header_row.add(hbox)
            list_box.add(header_row)

            from posgtk.widgets import CAT_ICONS
            for p in top_products:
                row = Gtk.ListBoxRow()
                row.get_style_context().add_class("data-row")
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                cat = p.get("category", "Бусад")
                icon = CAT_ICONS.get(cat, "📦")
                name_lbl = Gtk.Label(label=f"{icon} {p.get('product_name', '')}", xalign=0, hexpand=True)
                hbox.pack_start(name_lbl, True, True, 0)
                qty_lbl = Gtk.Label(label=str(p.get("total_qty", 0)), xalign=1)
                hbox.pack_start(qty_lbl, False, False, 0)
                rev_lbl = Gtk.Label(label=f"{format_money(p.get('total_revenue', 0))} ₮", xalign=1)
                rev_lbl.get_style_context().add_class("text-muted")
                hbox.pack_start(rev_lbl, False, False, 0)
                row.add(hbox)
                list_box.add(row)

            self.content_box.add(list_box)

        self.content_box.show_all()

"""
posgtk/reports.py — Sales and profit reports.
"""
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.reports")


class ReportsScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.set_margin_start(8)

        filter_box.set_margin_end(8)

        filter_box.set_margin_top(8)

        filter_box.set_margin_bottom(8)

        self.date_from_entry = Gtk.Entry()
        self.date_from_entry.set_placeholder_text("Эхлэх (YYYY-MM-DD)")
        filter_box.pack_start(self.date_from_entry, False, False, 0)

        self.date_to_entry = Gtk.Entry()
        self.date_to_entry.set_placeholder_text("Дуусах (YYYY-MM-DD)")
        filter_box.pack_start(self.date_to_entry, False, False, 0)

        run_btn = Gtk.Button(label="Гаргах")
        run_btn.connect("clicked", lambda b: self._load_data())
        filter_box.pack_start(run_btn, False, False, 0)

        self.pack_start(filter_box, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_margin_start(8)

        scrolled.set_margin_end(8)

        scrolled.set_margin_top(8)

        scrolled.set_margin_bottom(8)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.content_box.set_margin_start(16)
        self.content_box.set_margin_end(16)
        self.content_box.set_margin_top(16)
        self.content_box.set_margin_bottom(16)
        scrolled.add(self.content_box)

        self.pack_start(scrolled, True, True, 0)
        self.show_all()
        GLib.idle_add(self._load_data)

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

        title = Gtk.Label()
        title.set_markup("<b><span size='large'>📈 Тайлан</span></b>")
        title.set_halign(Gtk.Align.START)
        self.content_box.add(title)

        date_label = Gtk.Label(label=f"Хугацаа: {date_from or 'эхнээс'} — {date_to or 'өнөөдөр'}")
        date_label.set_halign(Gtk.Align.START)
        self.content_box.add(date_label)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        self.content_box.add(sep)

        metrics = [
            ("Нийт борлуулалт", summary.get("total_sales", 0)),
            ("Нийт тоо ширхэг", summary.get("total_quantity", 0)),
            ("Дундаж дүн", summary.get("avg_sale", 0)),
            ("Нийт ашиг", summary.get("total_profit", 0)),
            ("Борлуулалтын тоо", summary.get("sale_count", 0)),
        ]

        for label, value in metrics:
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            lbl = Gtk.Label(label=label, xalign=0)
            lbl.set_width_chars(20)
            row_box.pack_start(lbl, False, False, 0)
            row_box.pack_start(Gtk.Label(
                label=format_money(value) if value else "—", xalign=0
            ), False, False, 0)
            self.content_box.add(row_box)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_top(12)
        sep2.set_margin_bottom(8)
        self.content_box.add(sep2)

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

        self.content_box.show_all()

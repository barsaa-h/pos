"""
posgtk/diagnostics.py — Health diagnostics screen with stat cards.
"""
import logging
import shutil
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

logger = logging.getLogger("pos.gtk.diagnostics")


class DiagnosticsScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        header = Gtk.Label(label="🩺 Оношлогоо")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self._inner.set_margin_start(16)
        self._inner.set_margin_end(16)
        self._inner.set_margin_top(16)
        self._inner.set_margin_bottom(16)

        scrolled.add(self._inner)
        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)

        refresh_btn = Gtk.Button(label="🔄 Сэргээх")
        refresh_btn.get_style_context().add_class("suggested-action")
        refresh_btn.set_halign(Gtk.Align.CENTER)
        refresh_btn.set_margin_bottom(12)
        refresh_btn.connect("clicked", lambda b: self._load_data())
        self.pack_start(refresh_btn, False, False, 0)

        self._last_checked_label = Gtk.Label()
        self._last_checked_label.set_halign(Gtk.Align.CENTER)
        self._last_checked_label.set_margin_bottom(8)
        self._last_checked_label.get_style_context().add_class("hint-label")
        self.pack_start(self._last_checked_label, False, False, 0)

        self.show_all()
        GLib.idle_add(self._load_data)

    def _make_stat_card(self, value, label_text):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("stat-card")
        val_lbl = Gtk.Label(label=str(value))
        val_lbl.get_style_context().add_class("stat-card-value")
        card.pack_start(val_lbl, False, False, 0)
        lab_lbl = Gtk.Label(label=label_text)
        lab_lbl.get_style_context().add_class("stat-card-label")
        card.pack_start(lab_lbl, False, False, 0)
        return card

    def _load_data(self, *args):
        for child in self._inner.get_children():
            self._inner.remove(child)

        loading = Gtk.Label(label="🔄 Ачааллаж байна...")
        loading.set_halign(Gtk.Align.CENTER)
        loading.set_margin_top(48)
        self._inner.pack_start(loading, False, False, 0)
        self._inner.show_all()

        import database as db
        import time as _time

        def _bg():
            try:
                results = {
                    "integrity": db.check_db_integrity(),
                    "db_size": db.get_database_size(),
                    "products": db.get_total_products_count(),
                    "sales": db.get_total_sales_count(),
                    "ebarimt": db.get_ebarimt_failed_count(),
                    "low_stock": db.get_low_stock_count(),
                    "uptime": self.app.uptime_seconds if self.app else 0,
                    "timestamp": _time.strftime("%H:%M:%S"),
                }
                try:
                    import shutil, os
                    usage = shutil.disk_usage(os.path.dirname(db.DB_PATH))
                    results["disk_free"] = usage.free
                    results["disk_total"] = usage.total
                except Exception:
                    results["disk_free"] = 0
                    results["disk_total"] = 0
                try:
                    conn = db.get_connection()
                    c = conn.execute("PRAGMA journal_mode")
                    results["journal_mode"] = c.fetchone()[0]
                    c = conn.execute("PRAGMA synchronous")
                    results["synchronous"] = c.fetchone()[0]
                    c = conn.execute("PRAGMA foreign_keys")
                    results["foreign_keys"] = c.fetchone()[0]
                except Exception:
                    pass
            except Exception as e:
                logger.error("Diagnostics fetch error: %s", e)
                results = {"error": str(e)}
            GLib.idle_add(self._populate, results)

        import threading
        threading.Thread(target=_bg, daemon=True).start()

    def _populate(self, data):
        for child in self._inner.get_children():
            self._inner.remove(child)

        if "error" in data:
            err_lbl = Gtk.Label(label="❌ Алдаа: " + data["error"])
            err_lbl.set_halign(Gtk.Align.CENTER)
            err_lbl.set_margin_top(48)
            self._inner.pack_start(err_lbl, False, False, 0)
            self._inner.show_all()
            return

        db_size_mb = data.get("db_size", 0) / (1024 * 1024)
        integrity_ok = data.get("integrity", False)
        integrity_text = "✔️" if integrity_ok else "❌"

        uptime = data.get("uptime", 0)
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        if hours > 0:
            uptime_str = f"{hours}ц {minutes}м"
        else:
            uptime_str = f"{minutes}м {int(uptime % 60)}с"

        ebarimt_count = data.get("ebarimt", 0)
        if ebarimt_count == 0:
            ebarimt_color = "green"
        elif ebarimt_count <= 5:
            ebarimt_color = "#ccaa00"
        else:
            ebarimt_color = "red"

        disk_free = data.get("disk_free", 0)
        disk_free_gb = disk_free / (1024 * 1024 * 1024)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row1.set_homogeneous(True)
        row1.pack_start(self._make_stat_card(integrity_text, "Бүрэн бүтэн байдал"), True, True, 0)
        row1.pack_start(self._make_stat_card(f"{db_size_mb:.1f} MB", "Өгөгдлийн сан"), True, True, 0)
        row1.pack_start(self._make_stat_card(str(data.get("products", 0)), "Бараа"), True, True, 0)
        row1.pack_start(self._make_stat_card(str(data.get("sales", 0)), "Борлуулалт"), True, True, 0)
        self._inner.pack_start(row1, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row2.set_homogeneous(True)
        ebarimt_card = self._make_stat_card(str(ebarimt_count), "eBarimt хүлээгдэж буй")
        val_lbl = ebarimt_card.get_children()[0]
        val_lbl.set_markup(f'<span color="{ebarimt_color}">{ebarimt_count}</span>')
        row2.pack_start(ebarimt_card, True, True, 0)
        row2.pack_start(self._make_stat_card(str(data.get("low_stock", 0)), "Бага нөөц"), True, True, 0)
        row2.pack_start(self._make_stat_card(uptime_str, "Ажилласан хугацаа"), True, True, 0)
        row2.pack_start(self._make_stat_card(f"{disk_free_gb:.1f} GB чөлөөтэй", "Диск"), True, True, 0)
        self._inner.pack_start(row2, False, False, 0)

        self._last_checked_label.set_text(f"Сүүлд шалгасан: {data.get('timestamp', '')}")

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(16)
        sep.set_margin_bottom(8)
        self._inner.pack_start(sep, False, False, 0)

        jm = data.get("journal_mode", "?")
        sm = data.get("synchronous", "?")
        sm_text = {0: "OFF", 1: "NORMAL", 2: "FULL"}.get(sm, str(sm))
        fk = data.get("foreign_keys", "?")
        fk_text = "ON" if fk == 1 or fk == "1" else "OFF"

        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_box.set_margin_top(8)
        for line in [
            f"Журнал: {jm}",
            f"Синхрон: {sm_text}",
            f"Гадаад түлхүүр: {fk_text}",
        ]:
            lbl = Gtk.Label(label=line, xalign=0)
            lbl.get_style_context().add_class("hint-label")
            status_box.pack_start(lbl, False, False, 0)
        self._inner.pack_start(status_box, False, False, 0)

        self._inner.show_all()

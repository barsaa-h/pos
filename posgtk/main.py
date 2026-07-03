"""
posgtk/main.py — GTK Application entry point.

No Flask server needed. Calls database, printer, terminal, ebarimt directly.
"""

import os
import sys
import time
import logging

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject, Gio

from posgtk.scaling import init_scaling, get_scale, scaled_px, scaled_size_request

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logger = logging.getLogger("pos.gtk")

_IMPORTED_SCREENS = set()
_LOADING_TEXTS = {
    "sales": "Борлуулалтын түүх",
    "products": "Бараа",
    "categories": "Ангилал",
    "suppliers": "Ханган нийлүүлэгч",
    "stock": "Агуулахын тохируулга",
    "reports": "Тайлан",
    "settings": "Тохиргоо",
}




def _make_placeholder(name):
    from posgtk.widgets import make_loading_placeholder
    return make_loading_placeholder(name)


class POSApplication(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="mn.monost.pos.gtk",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        self.stack = None
        self.customer_window = None
        self.pos_screen = None
        self.cache = None
        self.workqueue = None
        self.theme = None
        self.clock_label = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self._init_db()
        self._init_cache()
        self._init_workqueue()

        self.window = Gtk.ApplicationWindow(
            application=self, title="POS Систем",
            window_position=Gtk.WindowPosition.CENTER,
        )
        self.window.get_style_context().add_class("main-window-bg")
        self.window.connect("key-press-event", self._on_key_press)
        self.window.connect("destroy", self._on_quit)

        self._init_theme()
        self.window.set_default_size(scaled_px(1024), scaled_px(640))

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_box.get_style_context().add_class("content-area")
        content_box.pack_start(self.stack, True, True, 0)
        main_vbox.pack_start(content_box, True, True, 0)

        self.window.add(main_vbox)

        try:
            from posgtk.pos import POSScreen
            self.pos_screen = POSScreen(app=self)
            self.stack.add_titled(self.pos_screen, "pos", "Борлуулалт")
        except ImportError:
            self.stack.add_titled(_make_placeholder("pos"), "pos", "Борлуулалт")

        for name, title in _LOADING_TEXTS.items():
            self.stack.add_titled(_make_placeholder(title), name, title)

        self.window.maximize()
        self.window.show_all()
        GLib.idle_add(self._show_pos)

        self.window.connect("realize", self._on_window_realized)

    def _init_db(self):
        import database as db
        db.init_db()

    def _init_cache(self):
        from posgtk.cache import ProductCache
        self.cache = ProductCache()
        self.cache.load()

    def _init_workqueue(self):
        from posgtk.workqueue import WorkQueue
        self.workqueue = WorkQueue()

    def _init_theme(self):
        from posgtk.theme import Theme
        self.theme = Theme()

        display = Gdk.Display.get_default()
        init_scaling(display)
        css_scale = get_scale()

        try:
            import database as db
            settings = db.get_all_settings()
            mode = settings.get("theme", "light")
            user_scale = settings.get("display_scale", "")
            if user_scale and user_scale != "1.0":
                css_scale = max(0.5, float(user_scale))
            low_perf = settings.get("low_perf_mode", "false") == "true"
        except Exception:
            mode = "light"
            low_perf = False

        self.theme.apply(mode, scale=css_scale, low_perf=low_perf)
        self._display_scale = css_scale
        if self.cache:
            cat_css = self.cache.generate_category_css()
            self.theme.append_css(cat_css)

    def _switch_screen(self, name):
        if name == "pos":
            self._show_pos()
            return
        self._ensure_screen_imported(name)
        self.stack.set_visible_child_name(name)

    def _ensure_screen_imported(self, name):
        if name in _IMPORTED_SCREENS:
            return
        logger.info(f"Lazy importing screen: {name}")
        try:
            if name == "sales":
                from posgtk.sales import SalesScreen
                scr = SalesScreen(app=self)
            elif name == "products":
                from posgtk.products import ProductsScreen
                scr = ProductsScreen(app=self)
            elif name == "categories":
                from posgtk.categories import CategoriesScreen
                scr = CategoriesScreen(app=self)
            elif name == "suppliers":
                from posgtk.suppliers import SuppliersScreen
                scr = SuppliersScreen(app=self)
            elif name == "reports":
                from posgtk.reports import ReportsScreen
                scr = ReportsScreen(app=self)
            elif name == "stock":
                from posgtk.stock import StockScreen
                scr = StockScreen(app=self)
            elif name == "settings":
                from posgtk.settings import SettingsScreen
                scr = SettingsScreen(app=self)
            else:
                return
            self.stack.remove(self.stack.get_child_by_name(name))
            self.stack.add_titled(scr, name, name)
            self.stack.show_all()
        except ImportError as e:
            logger.warning(f"Screen {name} not implemented yet: {e}")
        _IMPORTED_SCREENS.add(name)

    def _show_pos(self):
        self.stack.set_visible_child_name("pos")
        self._refocus_pos()

    def _refocus_pos(self):
        if self.pos_screen and hasattr(self.pos_screen, 'barcode_entry'):
            self.pos_screen.barcode_entry.grab_focus()

    def _update_clock(self):
        from datetime import datetime
        if self.clock_label:
            now = datetime.now()
            self.clock_label.set_text(now.strftime("%H:%M:%S"))
        return True

    def _on_key_press(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if not self.pos_screen:
            return False

        if ctrl and keyname == "f":
            if hasattr(self.pos_screen, 'search_entry_inline'):
                self.pos_screen.search_entry_inline.grab_focus()
            elif hasattr(self.pos_screen, 'search_entry'):
                self.pos_screen.search_entry.grab_focus()
            return True

        if keyname == "F1":
            self.pos_screen._show_help()
            return True

        if keyname == "F2":
            self.pos_screen.handle_payment_trigger("Бэлэн")
            return True

        if keyname == "F3":
            self.pos_screen._hold_order()
            return True

        if keyname == "F4":
            self.pos_screen.handle_payment_trigger("Карт")
            return True

        if keyname == "F5":
            self.pos_screen._show_checkout("qr")
            return True

        if keyname == "F6":
            self.pos_screen._show_anonymous_price_prompt()
            return True

        if keyname == "F7":
            self.pos_screen._toggle_ebarimt_type()
            return True

        if keyname == "F9":
            self.pos_screen._on_hold_order_clicked()
            return True

        if keyname == "F10":
            self.pos_screen._on_resume_order_clicked()
            return True

        if keyname == "Escape":
            focus = widget.get_focus()
            if isinstance(focus, (Gtk.Entry,)):
                widget.set_focus(None)
                self.pos_screen.barcode_entry.grab_focus()
                return True
            if self.pos_screen.cart:
                self.pos_screen._clear_cart()
                self.pos_screen._show_toast("🗑️ Сагсыг цэвэрлэв.", "info")
            self.pos_screen.barcode_entry.grab_focus()
            return True

        if keyname in ("Up", "Down", "Left", "Right", "KP_Up", "KP_Down", "KP_Left", "KP_Right"):
            return self._handle_grid_nav(keyname)

        if widget.get_focus() and isinstance(widget.get_focus(), Gtk.Entry):
            return False

        return False

    def _handle_grid_nav(self, direction):
        if not self.pos_screen:
            return False
        grid = self.pos_screen.product_grid
        visible = self.pos_screen._get_visible_children()
        if not visible:
            return False
        cols = max(1, min(grid.get_max_children_per_line() or 6, len(visible)))
        idx = self.pos_screen._selected_index
        if idx < 0:
            idx = 0
        if "Up" in direction:
            idx = max(0, idx - cols)
        elif "Down" in direction:
            idx = min(len(visible) - 1, idx + cols)
        elif "Left" in direction:
            idx = max(0, idx - 1)
        elif "Right" in direction:
            idx = min(len(visible) - 1, idx + 1)
        self.pos_screen._selected_index = idx
        if idx < len(visible):
            child = visible[idx]
            grid.select_child(child)
            child.grab_focus()
        return True

    def _on_window_realized(self, widget):
        self._show_customer_display()

    def _show_customer_display(self):
        try:
            from posgtk.customer_display import get_secondary_monitor, CustomerDisplayWindow
            secondary = get_secondary_monitor()
            if secondary and self.pos_screen:
                display = Gdk.Display.get_default()
                has_second_monitor = display.get_n_monitors() >= 2 if display else False
                self.customer_window = CustomerDisplayWindow(
                    self.pos_screen, secondary, fullscreen=has_second_monitor,
                )
                self.customer_window.show_all()
                self.pos_screen.connect("show-paying", lambda ps, total, ptype: self.customer_window.show_paying(total, ptype))
                self.pos_screen.connect("show-qr", lambda ps, total, pixbuf: self.customer_window.show_qr(total, pixbuf))
                self.pos_screen.connect("sale-complete", lambda ps, sale: self.customer_window.show_complete(sale))
        except Exception as e:
            logger.warning(f"Customer display failed: {e}")

    def _on_quit(self, widget):
        if self.workqueue:
            self.workqueue.shutdown()
        if self.customer_window:
            self.customer_window.destroy()
        self.quit()


def run():
    import database as db

    db_dir = os.path.dirname(os.path.abspath(
        db.DB_PATH if hasattr(db, 'DB_PATH') else os.path.join(PROJECT_DIR, "pos.db")
    ))
    os.makedirs(db_dir, exist_ok=True)
    for d in ["logs", "backups", "static/uploads"]:
        os.makedirs(os.path.join(PROJECT_DIR, d), exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("=== POS GTK Desktop Starting ===")
    logger.info(f"Project: {PROJECT_DIR}")
    logger.info(f"Python: {sys.version}")

    try:
        from printer import detect_printer_port
        port = detect_printer_port()
        logger.info(f"Printer port detected: {port}")
    except Exception as e:
        logger.warning(f"Printer detection failed: {e}")

    app = POSApplication()
    app.run(None)


if __name__ == "__main__":
    run()

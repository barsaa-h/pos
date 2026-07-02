"""
posgtk/customer_display.py — Second-monitor customer-facing window.
Optimized for low-end hardware (i5-2450M / Intel HD 3000).
Reuses widgets instead of destroying/recreating them to prevent UI stutter.
"""
import time
import re
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from posgtk.widgets import format_money
from posgtk.scaling import scaled_px, get_scale
from posgtk.theme import scale_css

CATEGORY_ICONS = {
    "Хүнс": "🍖", "Ундаа": "🥤", "Амттан": "🍬", "Сүүн бүтээгдэхүүн": "🥛",
    "Цэвэрлэгээ": "🧹", "Тамхи": "🚬", "Ахуйн": "🏠", "Хэрэгсэл": "💿",
    "Бусад": "📦", "Гоймон": "🍜", "Будаа": "🍚", "Мах": "🥩",
    "Талх": "🍞", "Амтлагч": "🧂", "Ус ундаа": "🧃",
}

def get_secondary_monitor():
    display = Gdk.Display.get_default()
    if not display:
        return None
    n = display.get_n_monitors()
    primary_geom = None
    secondary_geom = None
    for i in range(n):
        monitor = display.get_monitor(i)
        geom = monitor.get_geometry()
        is_primary = monitor.is_primary() if hasattr(monitor, 'is_primary') else (i == 0)
        if is_primary:
            primary_geom = (geom.x, geom.y, geom.width, geom.height)
        else:
            secondary_geom = (geom.x, geom.y, geom.width, geom.height)
    if secondary_geom:
        return secondary_geom
    if n >= 2:
        monitor = display.get_monitor(1)
        geom = monitor.get_geometry()
        return (geom.x, geom.y, geom.width, geom.height)
    if primary_geom:
        return primary_geom
    return None

class CustomerDisplayWindow(Gtk.Window):
    def __init__(self, pos_screen, monitor_geometry, fullscreen=True):
        super().__init__(title="Моност — Үйлчлүүлэгч")
        x, y, w, h = monitor_geometry
        self.move(x, y)
        self.set_default_size(w, h)
        if fullscreen:
            self.fullscreen()
        else:
            self.resize(w // 2, h)
            self.move(0, 0)

        self._pos_screen = pos_screen
        self._store_info = self._load_store_info()
        self._item_widgets = {}

        provider = Gtk.CssProvider()
        customer_css = scale_css(CUSTOMER_CSS.decode(), get_scale()).encode()
        provider.load_from_data(customer_css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._build_ui()
        self._start_clock()

        if pos_screen and hasattr(pos_screen, 'connect'):
            try:
                pos_screen.connect("cart-changed", self._on_cart_changed)
            except TypeError:
                pass

    def _load_store_info(self):
        try:
            from config import get_store_info
            return get_store_info()
        except Exception:
            return {"name": "Моност", "address": ""}

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.set_name("customer-display")

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        top_bar.set_name("customer-top-bar")
        top_bar.set_margin_top(scaled_px(24))
        top_bar.set_margin_start(scaled_px(48))
        top_bar.set_margin_end(scaled_px(48))

        store_name = Gtk.Label(label=self._store_info.get("name", "Моност").upper())
        store_name.set_name("cd-store-name")
        store_name.set_halign(Gtk.Align.START)
        store_name.set_hexpand(True)
        top_bar.pack_start(store_name, True, True, 0)

        self.clock_label = Gtk.Label()
        self.clock_label.set_name("cd-clock")
        self.clock_label.set_halign(Gtk.Align.END)
        top_bar.pack_end(self.clock_label, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)

        self._build_idle_view()
        self._build_shopping_view()
        self._build_paying_view()
        self._build_qr_view()

        vbox.pack_start(top_bar, False, False, 0)
        vbox.pack_start(self.stack, True, True, 0)
        self.add(vbox)
        self.stack.set_visible_child_name("idle")

    def _build_idle_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("cd-idle-view")
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)

        icon_label = Gtk.Label(label="🛍️")
        icon_label.set_name("cd-idle-icon")

        title = Gtk.Label()
        title.set_markup('<span font_weight="900" size="64000" foreground="#15803d">Тавтай морилно уу</span>')
        title.set_name("cd-idle-title")

        subtitle = Gtk.Label()
        subtitle.set_markup('<span font_weight="700" size="28000" foreground="#0f172a">Бараа сонгоно уу</span>')
        subtitle.set_name("cd-idle-subtitle")
        subtitle.set_margin_top(scaled_px(16))

        box.pack_start(icon_label, False, False, 0)
        box.pack_start(title, False, False, 0)
        box.pack_start(subtitle, False, False, 0)
        self.stack.add_named(box, "idle")

    def _build_shopping_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("cd-shopping-view")
        box.set_margin_start(scaled_px(48))
        box.set_margin_end(scaled_px(48))
        box.set_margin_bottom(scaled_px(48))

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(12))
        header_box.set_margin_top(scaled_px(16))
        header_box.set_margin_bottom(scaled_px(24))
        header_label = Gtk.Label(label="🛒 Таны сагс")
        header_label.set_name("cd-shop-header")
        header_label.set_halign(Gtk.Align.START)
        header_label.set_hexpand(True)
        header_box.pack_start(header_label, True, True, 0)
        self.item_count_badge = Gtk.Label(label="0")
        self.item_count_badge.set_name("cd-item-count")
        header_box.pack_end(self.item_count_badge, False, False, 0)
        box.pack_start(header_box, False, False, 0)

        self.item_grid = Gtk.FlowBox()
        self.item_grid.set_name("cd-item-grid")
        self.item_grid.set_max_children_per_line(3)
        self.item_grid.set_min_children_per_line(1)
        self.item_grid.set_homogeneous(True)
        self.item_grid.set_column_spacing(scaled_px(12))
        self.item_grid.set_row_spacing(scaled_px(12))
        self.item_grid.set_selection_mode(Gtk.SelectionMode.NONE)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_name("cd-scrolled")
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.item_grid)
        box.pack_start(scrolled, True, True, 0)

        total_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        total_box.set_name("cd-total-box")
        total_box.set_margin_top(scaled_px(16))
        total_label = Gtk.Label(label="💰 НИЙТ")
        total_label.set_name("cd-total-label")
        total_box.pack_start(total_label, False, False, 0)
        self.total_amount_label = Gtk.Label(label="0 ₮")
        self.total_amount_label.set_name("cd-total-amount")
        self.total_amount_label.set_halign(Gtk.Align.END)
        self.total_amount_label.set_hexpand(True)
        total_box.pack_end(self.total_amount_label, True, True, 0)
        box.pack_start(total_box, False, False, 0)

        self.stack.add_named(box, "shopping")

    def _build_paying_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("cd-paying-view")
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Label(label="💳")
        icon.set_name("cd-paying-icon")

        title = Gtk.Label()
        title.set_markup('<span font_weight="900" size="52000" foreground="#d97706">Төлбөр хүлээж байна…</span>')
        title.set_name("cd-paying-title")
        title.set_margin_top(24)

        self.paying_total_label = Gtk.Label()
        self.paying_total_label.set_name("cd-paying-total")
        self.paying_total_label.set_margin_top(16)

        hint = Gtk.Label(label="Картаа терминалд дөхүүлнэ үү")
        hint.set_name("cd-paying-hint")
        hint.set_margin_top(12)

        box.pack_start(icon, False, False, 0)
        box.pack_start(title, False, False, 0)
        box.pack_start(self.paying_total_label, False, False, 0)
        box.pack_start(hint, False, False, 0)
        self.stack.add_named(box, "paying")

    def _build_qr_view(self):
        overlay = Gtk.Overlay()
        overlay.set_name("cd-qr-overlay")

        self.qr_image = Gtk.Image()
        self.qr_image.set_name("cd-qr-image")
        self.qr_image.set_halign(Gtk.Align.CENTER)
        self.qr_image.set_valign(Gtk.Align.CENTER)

        qr_amount_label = Gtk.Label()
        qr_amount_label.set_name("cd-qr-amount")

        qr_hint = Gtk.Label(label="📱 Гар утаснаасаа QR код уншуулна уу")
        qr_hint.set_name("cd-qr-hint")

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_valign(Gtk.Align.CENTER)
        inner.set_halign(Gtk.Align.CENTER)
        inner.pack_start(qr_amount_label, False, False, 0)
        inner.pack_start(self.qr_image, True, True, 0)
        inner.pack_start(qr_hint, False, False, 0)
        overlay.add(inner)
        self.stack.add_named(overlay, "qr")

    def _start_clock(self):
        def _update_clock():
            self.clock_label.set_label(time.strftime("%H:%M:%S"))
            return True
        GLib.timeout_add_seconds(1, _update_clock)
        _update_clock()

    def _on_cart_changed(self, pos_screen, items, total):
        if not items:
            GLib.idle_add(self._show_idle)
            return
        GLib.idle_add(self._show_shopping, items, total)

    def _show_idle(self):
        self.stack.set_visible_child_name("idle")
        return False

    def _create_item_card(self, item):
        name = item.product_name if hasattr(item, 'product_name') else item.get("product_name", "")
        category = item.category if hasattr(item, 'category') else item.get("category", "")
        icon = CATEGORY_ICONS.get(category, "📦")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(8))
        card.set_name("cd-item-card")
        card.set_margin_top(scaled_px(6))
        card.set_margin_bottom(scaled_px(6))
        card.set_margin_start(scaled_px(12))
        card.set_margin_end(scaled_px(12))

        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_box.set_halign(Gtk.Align.CENTER)
        icon_label = Gtk.Label(label=icon)
        icon_label.set_name("cd-item-icon")
        icon_box.pack_start(icon_label, False, False, 0)
        card.pack_start(icon_box, False, False, 0)

        name_label = Gtk.Label(label=name[:25])
        name_label.set_name("cd-item-name")
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_max_width_chars(18)
        card.pack_start(name_label, False, False, 0)

        qty_label = Gtk.Label(label="")
        qty_label.set_name("cd-item-qty")
        qty_label.set_halign(Gtk.Align.START)
        card.pack_start(qty_label, False, False, 0)

        price_label = Gtk.Label(label="")
        price_label.set_name("cd-item-price")
        price_label.set_halign(Gtk.Align.END)
        card.pack_start(price_label, False, False, 0)

        card.qty_label = qty_label
        card.price_label = price_label
        return card

    def _update_item_card(self, card, item):
        qty = item.quantity if hasattr(item, 'quantity') else item.get("quantity", 1)
        price = item.unit_price if hasattr(item, 'unit_price') else item.get("unit_price", 0)
        subtotal = item.subtotal if hasattr(item, 'subtotal') else item.get("subtotal", 0)
        card.qty_label.set_text(f"{qty}× = {format_money(subtotal)}")
        card.price_label.set_text(format_money(price) + "/ш")

    def _show_shopping(self, items, total):
        active_keys = set()

        for item in items:
            pid = item.product_id if hasattr(item, 'product_id') else item.get("product_id")
            key = pid if pid else (item.product_name if hasattr(item, 'product_name') else item.get("product_name"))
            active_keys.add(key)

            if key not in self._item_widgets:
                card = self._create_item_card(item)
                self.item_grid.add(card)
                self._item_widgets[key] = card
            else:
                card = self._item_widgets[key]
                self._update_item_card(card, item)

        for key in list(self._item_widgets.keys()):
            if key not in active_keys:
                self.item_grid.remove(self._item_widgets[key])
                del self._item_widgets[key]

        self.item_grid.show_all()

        total_items = sum(
            item.quantity if hasattr(item, 'quantity') else item.get("quantity", 1)
            for item in items
        )
        self.item_count_badge.set_label(str(int(total_items)) if total_items else "0")
        self.total_amount_label.set_text(format_money(total))
        self.stack.set_visible_child_name("shopping")
        return False

    def show_paying(self, total, payment_type=""):
        self.paying_total_label.set_markup(
            f'<span font_weight="900" size="40000" foreground="#d97706">{format_money(total)}</span>'
        )
        self.stack.set_visible_child_name("paying")

    def show_qr(self, total, qr_pixbuf):
        self.qr_image.set_from_pixbuf(qr_pixbuf)
        self.stack.set_visible_child_name("qr")

    def show_idle(self):
        self.stack.set_visible_child_name("idle")

CUSTOMER_CSS = b"""
#customer-display {
    background: #f8fafc;
    font-family: sans-serif;
}
#customer-top-bar { background: transparent; }
#cd-store-name {
    font-size: 18px; font-weight: 800; color: #0f172a;
    text-transform: uppercase; letter-spacing: 2px;
}
#cd-clock {
    font-family: monospace; font-size: 16px; font-weight: 800; color: #334155;
}
#cd-idle-view { background: transparent; }
#cd-idle-icon { font-size: 80px; }
#cd-idle-title { font-size: 42px; font-weight: 900; color: #15803d; }
#cd-idle-subtitle { font-size: 22px; color: #0f172a; }
#cd-shopping-view { background: transparent; }
#cd-shop-header { font-size: 20px; font-weight: 800; color: #0f172a; }
#cd-item-count {
    padding: 4px 14px; background: #dcfce7; color: #15803d;
    border-radius: 20px; font-size: 14px; font-weight: 800; border: 2px solid #15803d;
}
#cd-item-grid { background: transparent; }
#cd-item-card {
    background: #ffffff; border: 2px solid #cbd5e1; border-radius: 16px; padding: 22px 26px;
}
#cd-item-icon { font-size: 30px; }
#cd-item-name { font-size: 20px; font-weight: 800; color: #0f172a; }
#cd-item-qty { font-size: 16px; color: #334155; font-weight: 700; }
#cd-item-price { font-size: 24px; font-weight: 900; color: #15803d; }
#cd-scrolled { background: transparent; }
#cd-total-box {
    background: #f0fdf4; border: 3px solid #15803d; border-radius: 16px; padding: 18px 30px;
}
#cd-total-label { font-size: 20px; font-weight: 900; color: #15803d; }
#cd-total-amount { font-size: 32px; font-weight: 900; color: #0f172a; }
#cd-paying-view { background: transparent; }
#cd-paying-icon { font-size: 64px; }
#cd-paying-title { color: #d97706; }
#cd-paying-total { color: #0f172a; }
#cd-paying-hint { font-size: 20px; color: #64748b; font-weight: 600; }
#cd-qr-overlay { background: #000000; }
#cd-qr-image { padding: 12px; background: #ffffff; border-radius: 20px; }
#cd-qr-amount { font-size: 36px; font-weight: 900; color: #ffffff; }
#cd-qr-hint { font-size: 18px; color: #cccccc; font-weight: 700; }
"""

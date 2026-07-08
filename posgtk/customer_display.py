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
            self.move(w // 2, 0)

        self._pos_screen = pos_screen
        self._store_info = self._load_store_info()
        self._item_widgets = {}
        self._complete_timeout_id = 0
        self._showing_complete = False

        provider = Gtk.CssProvider()
        customer_css = scale_css(CUSTOMER_CSS, get_scale()).encode()
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
        top_bar.set_margin_start(scaled_px(16))
        top_bar.set_margin_end(scaled_px(16))
        top_bar.set_margin_top(scaled_px(10))

        store_name = Gtk.Label(label=self._store_info.get("name", "Моност").upper())
        store_name.set_name("cd-store-name")
        store_name.set_halign(Gtk.Align.START)
        store_name.set_hexpand(True)
        top_bar.pack_start(store_name, False, False, 0)

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
        self._build_complete_view()

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
        icon_label.set_margin_bottom(scaled_px(24))

        try:
            from config import get_settings
            idle_msg = get_settings().get("customer_idle_message", "Тавтай морилно уу")
        except Exception:
            idle_msg = "Тавтай морилно уу"

        title = Gtk.Label()
        title.set_markup(f'<span font_weight="900" size="52000" foreground="#0f172a">{idle_msg}</span>')
        title.set_name("cd-idle-title")

        subtitle = Gtk.Label(label="Бараа сонгоно уу")
        subtitle.set_name("cd-idle-subtitle")
        subtitle.set_margin_top(scaled_px(8))

        box.pack_start(icon_label, False, False, 0)
        box.pack_start(title, False, False, 0)
        box.pack_start(subtitle, False, False, 0)
        self.stack.add_named(box, "idle")

    def _build_shopping_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("cd-shopping-view")
        box.set_margin_start(scaled_px(16))
        box.set_margin_end(scaled_px(16))
        box.set_hexpand(True)
        box.set_vexpand(True)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(12))
        header_box.set_margin_top(scaled_px(8))
        header_box.set_margin_bottom(scaled_px(12))
        header_label = Gtk.Label(label="🛒 Таны сагс")
        header_label.set_name("cd-shop-header")
        header_label.set_halign(Gtk.Align.START)
        header_label.set_hexpand(True)
        header_box.pack_start(header_label, False, False, 0)
        self.item_count_badge = Gtk.Label(label="0")
        self.item_count_badge.set_name("cd-item-count")
        header_box.pack_end(self.item_count_badge, False, False, 0)
        box.pack_start(header_box, False, False, 0)

        self.item_grid = Gtk.FlowBox()
        self.item_grid.set_name("cd-item-grid")
        self.item_grid.set_max_children_per_line(2)
        self.item_grid.set_min_children_per_line(1)
        self.item_grid.set_homogeneous(True)
        self.item_grid.set_column_spacing(scaled_px(8))
        self.item_grid.set_row_spacing(scaled_px(8))
        self.item_grid.set_selection_mode(Gtk.SelectionMode.NONE)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_name("cd-scrolled")
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        scrolled.add(self.item_grid)
        box.pack_start(scrolled, True, True, 0)

        total_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        total_box.set_name("cd-total-box")
        total_box.set_margin_top(scaled_px(12))
        total_box.set_margin_bottom(scaled_px(14))
        total_box.set_hexpand(True)
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
        icon.set_margin_bottom(scaled_px(16))

        self._paying_label = Gtk.Label(label="Төлбөр хүлээж байна")
        self._paying_label.set_name("cd-paying-title")
        self._paying_label.set_margin_bottom(scaled_px(28))

        total_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        total_wrap.set_name("cd-paying-box")

        total_inner_label = Gtk.Label(label="ТӨЛБӨР ДҮН")
        total_inner_label.set_name("cd-paying-box-label")

        self.paying_total_label = Gtk.Label()
        self.paying_total_label.set_name("cd-paying-total")

        total_wrap.pack_start(total_inner_label, False, False, 0)
        total_wrap.pack_start(self.paying_total_label, False, False, 0)

        hint = Gtk.Label(label="Картаа терминалд дөхүүлнэ үү")
        hint.set_name("cd-paying-hint")
        hint.set_margin_top(scaled_px(16))

        box.pack_start(icon, False, False, 0)
        box.pack_start(self._paying_label, False, False, 0)
        box.pack_start(total_wrap, False, False, 0)
        box.pack_start(hint, False, False, 0)
        self.stack.add_named(box, "paying")

    def _build_qr_view(self):
        overlay = Gtk.Overlay()
        overlay.set_name("cd-qr-overlay")

        self.qr_image = Gtk.Image()
        self.qr_image.set_name("cd-qr-image")
        self.qr_image.set_halign(Gtk.Align.CENTER)
        self.qr_image.set_valign(Gtk.Align.CENTER)

        self.qr_amount_label = Gtk.Label()
        self.qr_amount_label.set_name("cd-qr-amount")

        qr_hint = Gtk.Label(label="📱 Гар утаснаасаа QR код уншуулна уу")
        qr_hint.set_name("cd-qr-hint")

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_valign(Gtk.Align.CENTER)
        inner.set_halign(Gtk.Align.CENTER)
        inner.pack_start(self.qr_amount_label, False, False, 0)
        inner.pack_start(self.qr_image, True, True, 0)
        inner.pack_start(qr_hint, False, False, 0)
        overlay.add(inner)
        self.stack.add_named(overlay, "qr")

    def _build_complete_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("cd-complete-view")
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Label(label="✅")
        icon.set_name("cd-complete-icon")
        icon.set_margin_bottom(scaled_px(12))

        title = Gtk.Label()
        title.set_markup('<span font_weight="900" size="42000" foreground="#d97706">ТӨЛБӨР АМЖИЛТТАЙ</span>')
        title.set_name("cd-complete-title")
        title.set_margin_bottom(scaled_px(16))

        self.complete_sale_id = Gtk.Label()
        self.complete_sale_id.set_name("cd-complete-sale-id")
        self.complete_sale_id.set_margin_bottom(scaled_px(4))

        total_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        total_wrap.set_name("cd-complete-box")

        self.complete_total = Gtk.Label()
        self.complete_total.set_name("cd-complete-total")

        self.complete_payment = Gtk.Label()
        self.complete_payment.set_name("cd-complete-payment")

        self.complete_change = Gtk.Label()
        self.complete_change.set_name("cd-complete-change")

        self.complete_lottery = Gtk.Label()
        self.complete_lottery.set_name("cd-complete-lottery")

        total_wrap.pack_start(self.complete_total, False, False, 0)
        total_wrap.pack_start(self.complete_payment, False, False, 0)
        total_wrap.pack_start(self.complete_change, False, False, 0)
        total_wrap.pack_start(self.complete_lottery, False, False, 0)

        hint = Gtk.Label()
        hint.set_markup('<span font_weight="700" size="22000" foreground="#64748b">Шинэ бараа сонгоно уу</span>')
        hint.set_name("cd-complete-hint")
        hint.set_margin_top(scaled_px(24))

        box.pack_start(icon, False, False, 0)
        box.pack_start(title, False, False, 0)
        box.pack_start(self.complete_sale_id, False, False, 0)
        box.pack_start(total_wrap, False, False, 0)
        box.pack_start(hint, False, False, 0)
        self.stack.add_named(box, "complete")

    def _start_clock(self):
        def _update_clock():
            self.clock_label.set_label(time.strftime("%H:%M"))
            return True
        GLib.timeout_add_seconds(1, _update_clock)
        _update_clock()

    def _on_cart_changed(self, pos_screen, items, total):
        if self._showing_complete:
            return
        if not items:
            GLib.idle_add(self._show_idle)
            return
        GLib.idle_add(self._show_shopping, items, total)

    def _show_idle(self):
        self.stack.set_visible_child_name("idle")
        return False

    def _get_item_attr(self, item, name, default=""):
        if hasattr(item, name):
            return getattr(item, name, default)
        if isinstance(item, dict):
            return item.get(name, default)
        return default

    def _get_category_icon(self, category):
        if not category:
            return "📦"
        return CATEGORY_ICONS.get(category, "📦")

    def _create_item_card(self, item):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(14))
        card.set_name("cd-item-card")
        card.set_size_request(-1, scaled_px(80))
        card.set_hexpand(True)

        cat_name = self._get_item_attr(item, "category", "")
        icon_text = self._get_category_icon(cat_name)
        icon_label = Gtk.Label(label=icon_text)
        icon_label.set_name("cd-item-icon")
        icon_label.set_size_request(scaled_px(56), scaled_px(56))
        icon_label.set_halign(Gtk.Align.CENTER)
        icon_label.set_valign(Gtk.Align.CENTER)
        card.pack_start(icon_label, False, False, 0)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(2))
        inner.set_valign(Gtk.Align.CENTER)
        inner.set_hexpand(True)

        name_lbl = Gtk.Label(label=self._get_item_attr(item, "product_name", ""))
        name_lbl.set_name("cd-item-name")
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_valign(Gtk.Align.END)
        name_lbl.set_line_wrap(True)
        name_lbl.set_max_width_chars(25)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        inner.pack_start(name_lbl, False, False, 0)

        qty = self._get_item_attr(item, "quantity", 1)
        price = self._get_item_attr(item, "unit_price", 0)
        qty_str = f"{qty:g}" if isinstance(qty, float) and qty == int(qty) else str(qty)
        detail_lbl = Gtk.Label(label=f"{qty_str} × {int(price):,} ₮")
        detail_lbl.set_name("cd-item-detail")
        detail_lbl.set_halign(Gtk.Align.START)
        detail_lbl.set_valign(Gtk.Align.START)
        inner.pack_start(detail_lbl, False, False, 0)

        card.pack_start(inner, True, True, 0)

        subtotal = self._get_item_attr(item, "subtotal", 0)
        total_lbl = Gtk.Label(label=f"{int(subtotal):,} ₮")
        total_lbl.set_name("cd-item-total")
        total_lbl.set_valign(Gtk.Align.CENTER)
        total_lbl.set_margin_start(scaled_px(8))
        card.pack_end(total_lbl, False, False, 0)

        card.get_style_context().add_class("cd-item-card")
        card.detail_lbl = detail_lbl
        card.total_lbl = total_lbl
        return card

    def _update_item_card(self, card, item):
        qty = self._get_item_attr(item, "quantity", 1)
        price = self._get_item_attr(item, "unit_price", 0)
        subtotal = self._get_item_attr(item, "subtotal", 0)
        qty_str = f"{qty:g}" if isinstance(qty, float) and qty == int(qty) else str(qty)
        card.detail_lbl.set_text(f"{qty_str} × {int(price):,} ₮")
        card.total_lbl.set_text(f"{int(subtotal):,} ₮")

    def _show_shopping(self, items, total):
        active_keys = set()

        for item in items:
            pid = self._get_item_attr(item, "product_id")
            key = pid if pid else self._get_item_attr(item, "product_name", "")
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
            int(self._get_item_attr(item, "quantity", 1))
            for item in items
        )
        self.item_count_badge.set_label(f"{int(total_items)} бараа")
        self.total_amount_label.set_text(format_money(total))
        self.stack.set_visible_child_name("shopping")
        return False

    def show_paying(self, total, payment_type=""):
        self.paying_total_label.set_markup(
            f'<span font_weight="900" size="64000" foreground="#b45309">{format_money(total)}</span>'
        )
        self.stack.set_visible_child_name("paying")
        if hasattr(self, '_paying_dots_source_id') and self._paying_dots_source_id:
            GLib.source_remove(self._paying_dots_source_id)
        self._paying_dots_source_id = GLib.timeout_add(500, self._animate_paying_dots)

    def show_qr(self, total, qr_pixbuf):
        self.qr_image.set_from_pixbuf(qr_pixbuf)
        self.qr_amount_label.set_markup(
            f'<span font_weight="900" size="36000" foreground="#b45309">{format_money(total)}</span>'
        )
        self.stack.set_visible_child_name("qr")

    def _animate_paying_dots(self):
        if not self._paying_label:
            return False
        if self.stack.get_visible_child_name() != "paying":
            self._paying_dots_source_id = 0
            return False
        if not hasattr(self, '_paying_dot_count'):
            self._paying_dot_count = 0
        self._paying_dot_count = (self._paying_dot_count + 1) % 4
        dots = "." * self._paying_dot_count
        self._paying_label.set_text(f"Төлбөр хүлээж байна{dots}")
        return True

    def show_idle(self):
        self._showing_complete = False
        if self._complete_timeout_id:
            GLib.source_remove(self._complete_timeout_id)
            self._complete_timeout_id = 0
        if hasattr(self, '_paying_dots_source_id') and self._paying_dots_source_id:
            GLib.source_remove(self._paying_dots_source_id)
            self._paying_dots_source_id = 0
        self.stack.set_visible_child_name("idle")

    def show_complete(self, sale):
        if self._complete_timeout_id:
            GLib.source_remove(self._complete_timeout_id)
        self._showing_complete = True

        payment_labels = {"cash": "💵 Бэлэн", "card": "💳 Карт", "split": "🔀 Холимог", "qr": "📱 QR"}
        ptype = sale.get("payment_type", "")
        payment_label = payment_labels.get(ptype, ptype.upper())

        total = sale.get("total", 0)
        change = sale.get("change_given", 0)
        lottery = sale.get("ebarimt_lottery", "")

        self.complete_sale_id.set_markup(
            f'<span font_weight="800" size="20000" foreground="#475569">✅ №{sale.get("id", "?")}</span>'
        )
        self.complete_total.set_markup(
            f'<span font_weight="900" size="64000" foreground="#b45309">{format_money(total)}</span>'
        )
        self.complete_payment.set_markup(
            f'<span font_weight="800" size="24000" foreground="#334155">{payment_label}</span>'
        )
        if change > 0 and ptype in ("cash", "split"):
            self.complete_change.set_markup(
                f'<span font_weight="800" size="28000" foreground="#d97706">Хариулт: {format_money(change)}</span>'
            )
            self.complete_change.show()
        else:
            self.complete_change.hide()

        if lottery:
            self.complete_lottery.set_markup(
                f'<span font_weight="900" size="30000" foreground="#b45309">🎰 {lottery}</span>'
            )
            self.complete_lottery.show()
        else:
            self.complete_lottery.hide()

        self.stack.set_visible_child_name("complete")
        timeout = getattr(self, '_display_timeout', 10)
        self._complete_timeout_id = GLib.timeout_add_seconds(timeout, self._on_complete_timeout)

    def _on_complete_timeout(self):
        self._showing_complete = False
        self._complete_timeout_id = 0
        self.stack.set_visible_child_name("idle")
        return False

CUSTOMER_CSS = """
#customer-display {
    background: #f8fafc;
    font-family: sans-serif;
}
#customer-top-bar { background: transparent; }
#cd-store-name {
    font-size: 18px;
    font-weight: 800;
    color: #475569;
    letter-spacing: 0.5px;
}
#cd-clock {
    font-family: monospace;
    font-size: 16px;
    font-weight: 800;
    color: #475569;
    margin-left: 14px;
}
#cd-idle-view { background: transparent; }
#cd-idle-icon { font-size: 80px; }
#cd-idle-title { font-size: 42px; font-weight: 900; color: #0f172a; }
#cd-idle-subtitle { font-size: 22px; color: #475569; font-weight: 700; }
#cd-shopping-view { background: transparent; }
#cd-shop-header { font-size: 20px; font-weight: 800; color: #0f172a; }
#cd-item-count {
    padding: 4px 14px;
    background: #dcfce7;
    color: #15803d;
    border-radius: 20px;
    font-size: 14px;
    font-weight: 800;
    border: 2px solid #15803d;
}
#cd-item-grid { background: transparent; }
#cd-scrolled { background: transparent; }
#cd-item-card {
    background: #ffffff;
    border: 2px solid #E2E8F0;
    border-radius: 16px;
    padding: 8px 16px;
}
#cd-item-icon {
    font-size: 32px;
    background: #f1f5f9;
    border-radius: 14px;
}
#cd-item-name {
    font-size: 20px;
    font-weight: 800;
    color: #0f172a;
}
#cd-item-detail {
    font-size: 16px;
    color: #475569;
    font-weight: 700;
}
#cd-item-total {
    font-size: 26px;
    font-weight: 900;
    color: #15803d;
}
#cd-total-box {
    background: #f0fdf4;
    border: 3px solid #15803d;
    border-radius: 16px;
    padding: 14px 24px;
}
#cd-total-label { font-size: 22px; font-weight: 900; color: #15803d; }
#cd-total-amount { font-size: 36px; font-weight: 900; color: #0f172a; }
#cd-paying-view { background: transparent; }
#cd-paying-icon { font-size: 72px; }
#cd-paying-title {
    font-size: 38px;
    font-weight: 900;
    color: #d97706;
}
#cd-paying-box {
    background: #fef3c7;
    border: 4px solid #b45309;
    border-radius: 24px;
    padding: 28px 56px;
}
#cd-paying-box-label {
    font-size: 20px;
    font-weight: 800;
    color: #92400e;
}
#cd-paying-total { }
#cd-paying-hint { font-size: 20px; color: #64748b; font-weight: 600; }
#cd-qr-overlay { background: #000000; }
#cd-qr-amount { font-size: 44px; font-weight: 900; color: #ffffff; }
#cd-qr-image { padding: 12px; background: #ffffff; border-radius: 20px; }
#cd-qr-hint { font-size: 20px; color: rgba(255,255,255,0.75); font-weight: 700; }
#cd-complete-view { background: transparent; }
#cd-complete-icon { font-size: 72px; }
#cd-complete-box {
    background: #fef3c7;
    border: 4px solid #b45309;
    border-radius: 24px;
    padding: 28px 56px;
    margin-top: 8px;
}
"""

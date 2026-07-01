"""
posgtk/pos.py — Main POS screen.

Product grid, barcode scanning, cart management, checkout, held orders.
Uses ProductCache for zero-DB lookups. Emits GObject signals for customer display.
"""

import logging
import time
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from posgtk.widgets import (
    CartItem, format_money, make_product_card, make_cart_item_row,
    make_category_button,
)
from posgtk.scaling import scaled_px, scaled_size_request

logger = logging.getLogger("pos.gtk.pos")


class POSScreen(Gtk.Box):
    __gsignals__ = {
        'cart-changed': (GObject.SIGNAL_RUN_LAST, None, (object, int)),
        'show-paying': (GObject.SIGNAL_RUN_LAST, None, (int, str)),
        'show-qr': (GObject.SIGNAL_RUN_LAST, None, (int, object)),
        'show-idle': (GObject.SIGNAL_RUN_LAST, None, ()),
    }

    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.app = app
        self.cache = app.cache if app else None
        self.workqueue = app.workqueue if app else None

        self.cart = []
        self.held_orders = []
        self._active_category = ""
        self._search_query = ""
        self._selected_index = -1
        self._discounts_enabled = False
        self.ebarimt_type = "individual"

        self._load_settings()
        self._build_left_panel()
        self._build_right_panel()

        self._build_product_grid()
        self._setup_event_handlers()
        self.show_all()
        self._on_category_selected("")
        GLib.idle_add(self.barcode_entry.grab_focus)
        GLib.idle_add(self.bind_keyboard_accelerators)

    def _load_settings(self):
        try:
            import database as db
            settings = db.get_all_settings()
            self._discounts_enabled = settings.get("discounts_enabled", "false") == "true"
        except Exception:
            pass

    def _build_left_panel(self):
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left.set_hexpand(True)
        left.set_vexpand(True)
        left.get_style_context().add_class("pos-left")

        self.barcode_entry = Gtk.Entry()
        self.barcode_entry.set_placeholder_text("Баркод сканнердах эсвэл оруулна уу...")
        self.barcode_entry.connect("key-press-event", self._on_barcode_key_press)
        self.barcode_entry.get_style_context().add_class("barcode-entry")
        left.pack_start(self.barcode_entry, False, False, 0)

        search_revealer = Gtk.Revealer()
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("🔍  Бараа хайх...")
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.connect("stop-search", self._on_search_stopped)
        search_revealer.add(self.search_entry)
        self._search_revealer = search_revealer

        self.search_entry_inline = Gtk.Entry()
        self.search_entry_inline.set_placeholder_text("🔍  Бараа хайх...")
        self.search_entry_inline.get_style_context().add_class("search-entry-inline")
        self.search_entry_inline.connect("changed", self._on_search_inline_changed)
        self.search_entry_inline.connect("activate", lambda e: GLib.idle_add(self.barcode_entry.grab_focus))
        left.pack_start(self.search_entry_inline, False, False, 0)

        category_scroll = Gtk.ScrolledWindow()
        category_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        category_scroll.set_kinetic_scrolling(True)
        category_scroll.get_style_context().add_class("category-scroll")

        self.category_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._build_category_buttons()

        category_scroll.add(self.category_box)
        left.pack_start(category_scroll, False, False, 0)

        grid_scroller = Gtk.ScrolledWindow()
        grid_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        grid_scroller.set_kinetic_scrolling(True)
        grid_scroller.set_capture_button_press(True)
        grid_scroller.set_hexpand(True)
        grid_scroller.set_vexpand(True)

        self.product_grid = Gtk.FlowBox()
        self.product_grid.set_valign(Gtk.Align.START)
        self.product_grid.set_max_children_per_line(6)
        self.product_grid.set_min_children_per_line(2)
        self.product_grid.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.product_grid.set_activate_on_single_click(True)
        self.product_grid.set_homogeneous(True)
        self.product_grid.set_row_spacing(0)
        self.product_grid.set_column_spacing(0)
        self.product_grid.connect("child-activated", self._on_grid_child_activated)
        self.product_grid.connect("key-press-event", self._on_grid_key_press)
        grid_scroller.add(self.product_grid)

        self._empty_label = Gtk.Label(label="Бараа олдсонгүй")
        self._empty_label.set_halign(Gtk.Align.CENTER)
        self._empty_label.set_no_show_all(True)
        self._empty_label.set_visible(False)
        left.pack_start(self._empty_label, False, False, 0)

        left.pack_start(grid_scroller, True, True, 0)

        self.pack_start(left, True, True, 0)

    def _build_right_panel(self):
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right.get_style_context().add_class("cart-panel")
        right.set_vexpand(True)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_box.get_style_context().add_class("cart-header-bar")

        cart_title = Gtk.Label(label="🛒 Сагс")
        cart_title.get_style_context().add_class("cart-title")
        header_box.pack_start(cart_title, False, False, 0)

        self.cart_count_label = Gtk.Label(label="0")
        self.cart_count_label.get_style_context().add_class("cart-count-badge")
        header_box.pack_start(self.cart_count_label, False, False, 0)

        self.tax_mode_label = Gtk.Label(label="")
        self.tax_mode_label.set_tooltip_text("eBarimt төрөл (F7)")
        self.tax_mode_label.get_style_context().add_class("tax-mode-badge")
        header_box.pack_start(self.tax_mode_label, False, False, 0)

        ebarimt_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        ebarimt_btn = Gtk.Button(label="\u26a0")
        ebarimt_btn.set_tooltip_text("\u0425\u0443\u043b\u0434\u0430\u0430\u043d\u0434 \u0430\u043c\u0436\u0438\u043b\u0442\u0433\u04af\u0439 eBarimt")
        ebarimt_btn.set_relief(Gtk.ReliefStyle.NONE)
        ebarimt_btn.connect("clicked", lambda b: self._show_ebarimt_pending())
        ebarimt_box.pack_start(ebarimt_btn, False, False, 0)
        self.ebarimt_badge = Gtk.Label(label="")
        self.ebarimt_badge.get_style_context().add_class("badge")
        self.ebarimt_badge.get_style_context().add_class("amber")
        ebarimt_box.pack_start(self.ebarimt_badge, False, False, 0)
        header_box.pack_start(ebarimt_box, False, False, 0)

        held_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        held_btn = Gtk.Button(label="📋")
        held_btn.set_tooltip_text("\u0425\u04af\u043b\u044d\u044d\u043b\u0433\u044d\u0441\u044d\u043d \u0437\u0430\u0445\u0438\u0430\u043b\u0433\u0443\u0443\u0434")
        held_btn.set_relief(Gtk.ReliefStyle.NONE)
        held_btn.connect("clicked", lambda b: self._show_held_orders())
        held_box.pack_start(held_btn, False, False, 0)
        self.held_badge = Gtk.Label(label="")
        self.held_badge.get_style_context().add_class("badge")
        self.held_badge.get_style_context().add_class("amber")
        held_box.pack_start(self.held_badge, False, False, 0)
        header_box.pack_end(held_box, False, False, 0)

        clear_btn = Gtk.Button(label="🗑")
        clear_btn.set_tooltip_text("Цэвэрлэх (ESC)")
        clear_btn.set_relief(Gtk.ReliefStyle.NONE)
        clear_btn.connect("clicked", lambda b: self._clear_cart(confirm=True))
        header_box.pack_end(clear_btn, False, False, 0)

        right.pack_start(header_box, False, False, 0)

        cart_scroll = Gtk.ScrolledWindow()
        cart_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cart_scroll.set_kinetic_scrolling(True)
        cart_scroll.set_vexpand(True)
        cart_scroll.get_style_context().add_class("cart-scroll")
        self.cart_list = Gtk.ListBox()
        self.cart_list.set_selection_mode(Gtk.SelectionMode.NONE)
        cart_scroll.add(self.cart_list)
        right.pack_start(cart_scroll, True, True, 0)

        totals_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        totals_box.get_style_context().add_class("cart-total-row")

        self.total_label = Gtk.Label()
        self.total_label.set_markup("<span>Нийт: 0 ₮</span>")
        self.total_label.get_style_context().add_class("cart-total-label")
        self.total_label.set_halign(Gtk.Align.END)
        totals_box.pack_start(self.total_label, False, False, 0)

        right.pack_start(totals_box, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        btn_box.get_style_context().add_class("checkout-btn-row")

        self.pay_btn = Gtk.Button(label="💰  ТӨЛБӨР ТӨЛӨХ")
        self.pay_btn.get_style_context().add_class("checkout-pay-btn")
        self.pay_btn.connect("clicked", self._on_pay_clicked)
        self.pay_btn.set_sensitive(False)
        btn_box.pack_start(self.pay_btn, True, True, 0)

        hold_btn = Gtk.Button(label="⏸")
        hold_btn.set_tooltip_text("Түр хадгалах (F9)")
        hold_btn.get_style_context().add_class("hold-btn")
        hold_btn.connect("clicked", lambda b: self._on_hold_order_clicked())
        btn_box.pack_start(hold_btn, False, False, 0)
        self.held_count_label = Gtk.Label(label="")
        self.held_count_label.get_style_context().add_class("badge")
        btn_box.pack_start(self.held_count_label, False, False, 0)

        right.pack_start(btn_box, False, False, 0)

        self.pack_end(right, False, True, 0)

    def _build_category_buttons(self):
        for child in self.category_box.get_children():
            self.category_box.remove(child)

        all_btn = Gtk.ToggleButton(label="🌐 Бүгд")
        all_btn.set_active(not self._active_category)
        all_btn.connect("toggled", self._on_category_toggled, "")
        all_btn.category = ""
        all_btn.get_style_context().add_class("category-btn")
        self.category_box.pack_start(all_btn, False, False, 0)

        if self.cache:
            cats = self.cache.categories()
            CAT_ICONS = {
                "Хүнс": "🍖", "Ундаа": "🥤", "Амттан": "🍬", "Цэвэрлэгээ": "🧹",
                "Тамхи": "🚬", "Ахуйн": "🏠", "Бусад": "📦",
            }
            for cat in cats:
                icon = CAT_ICONS.get(cat, "📦")
                btn = Gtk.ToggleButton(label=f"{icon} {cat}")
                btn.set_active(cat == self._active_category)
                btn.connect("toggled", self._on_category_toggled, cat)
                btn.category = cat
                btn.get_style_context().add_class("category-btn")
                self.category_box.pack_start(btn, False, False, 0)

        self.category_box.show_all()

    def _on_category_toggled(self, btn, category):
        if not btn.get_active():
            return
        for child in self.category_box.get_children():
            if hasattr(child, 'category') and child.category != category:
                child.set_active(False)
        self._on_category_selected(category)

    def _build_product_grid(self):
        for child in self.product_grid.get_children():
            self.product_grid.remove(child)
        if not self.cache:
            return
        for p in self.cache.all_products():
            card = make_product_card(p, self._on_product_clicked, cache=self.cache)
            self.product_grid.add(card)

    def _on_category_selected(self, category_name):
        self._active_category = category_name
        self.product_grid.freeze_child_notify()
        try:
            children = self.product_grid.get_children()
            for child in children:
                btn = child.get_child()
                if not btn or not hasattr(btn, 'product'):
                    continue
                product = btn.product
                matches_category = (not category_name or product.get("category") == category_name)
                q = self._search_query.lower() if self._search_query else ""
                matches_search = (not q or q in product.get("name", "").lower() or q in product.get("barcode", "").lower())
                if matches_category and matches_search:
                    child.show()
                else:
                    child.hide()
        finally:
            self.product_grid.thaw_child_notify()
            self.product_grid.queue_draw()
        has_visible = any(
            child.get_visible() for child in self.product_grid.get_children()
        )
        self._empty_label.set_visible(not has_visible)

    def _get_visible_children(self):
        return [c for c in self.product_grid.get_children() if c.get_visible()]

    def _on_product_clicked(self, product):
        unit = product.get("unit", "ш")
        if unit in ("кг", "л", "хайрцаг"):
            self._show_weight_prompt(product)
        else:
            self._add_product_to_cart(product)

    def _on_grid_child_activated(self, flowbox, child):
        widget = child.get_child()
        if hasattr(widget, 'product'):
            unit = widget.product.get("unit", "ш")
            if unit in ("кг", "л", "хайрцаг"):
                self._show_weight_prompt(widget.product)
            else:
                self._add_product_to_cart(widget.product)

    def _on_grid_key_press(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        if keyname == "Return" and self._selected_index >= 0:
            visible = self._get_visible_children()
            if 0 <= self._selected_index < len(visible):
                child = visible[self._selected_index]
                if hasattr(child.get_child(), 'product'):
                    p = child.get_child().product
                    unit = p.get("unit", "ш")
                    if unit in ("кг", "л", "хайрцаг"):
                        self._show_weight_prompt(p)
                    else:
                        self._add_product_to_cart(p)
            return True
        return False

    def _on_barcode_scanned(self, entry):
        raw_text = entry.get_text().strip()
        entry.set_text("")
        entry.grab_focus()

        if not raw_text:
            return

        quantity_multiplier = 1
        barcode = raw_text

        if "*" in raw_text:
            try:
                parts = raw_text.split("*", 1)
                quantity_multiplier = max(1, int(parts[0]))
                barcode = parts[1].strip()
            except (ValueError, IndexError):
                quantity_multiplier = 1
                barcode = raw_text

        if self.cache and hasattr(self.cache, '_loaded') and self.cache._loaded:
            product = self.cache._by_barcode.get(barcode)
        else:
            import database as db
            product = db.get_product_by_barcode(barcode)

        if product:
            if product.get("stock_qty", 99999) <= 0:
                self._show_toast(f"⚠️ '{product.get('name')}' барааны үлдэгдэл дууссан байна!", "warning")
            self._add_product_to_cart(product, quantity=quantity_multiplier)
        else:
            self._show_not_found_dialog(barcode)

    def _on_barcode_key_press(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        if keyname == "Escape":
            self._clear_cart()
            return True
        if keyname in ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"):
            return False
        return False

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text().lower().strip()
        self._on_category_selected(self._active_category)

    def _on_search_stopped(self, entry):
        if hasattr(self, '_search_revealer'):
            self._search_revealer.set_reveal_child(False)
        self._search_query = ""
        self._on_category_selected(self._active_category)
        GLib.idle_add(self.barcode_entry.grab_focus)

    def _on_search_inline_changed(self, entry):
        query = entry.get_text().lower().strip()
        if self._search_query != query:
            self._search_query = query
            self._on_category_selected(self._active_category)
        if self._active_category:
            for child in self.category_box.get_children():
                if hasattr(child, 'category') and child.category:
                    if child.get_active():
                        child.set_active(False)
                        all_children = self.category_box.get_children()
                        if all_children:
                            all_children[0].set_active(True)
                        break

    def _on_pay_clicked(self, btn):
        if not self.cart:
            return
        total = self._calc_total()
        dialog = Gtk.Dialog(
            title="",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(scaled_px(320), scaled_px(280))
        content = dialog.get_content_area()
        content.set_spacing(0)
        content.set_margin_top(0)
        content.set_margin_bottom(0)
        content.set_margin_start(0)
        content.set_margin_end(0)

        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        summary.get_style_context().add_class("pay-select-summary")
        summary.set_margin_start(scaled_px(24))
        summary.set_margin_end(scaled_px(24))
        summary.set_margin_top(scaled_px(20))
        summary.set_margin_bottom(scaled_px(20))

        title_label = Gtk.Label(label="Төлбөрийн төрөл")
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.get_style_context().add_class("pay-select-title")
        summary.pack_start(title_label, False, False, 0)

        total_label = Gtk.Label()
        total_label.set_markup(f'<span size="28000" weight="900" foreground="#FFFFFF">{format_money(total)}</span>')
        total_label.set_halign(Gtk.Align.CENTER)
        total_label.set_margin_top(scaled_px(8))
        summary.pack_start(total_label, False, False, 0)

        content.pack_start(summary, False, False, 0)

        btn_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(10))
        btn_grid.set_margin_start(scaled_px(24))
        btn_grid.set_margin_end(scaled_px(24))
        btn_grid.set_margin_top(scaled_px(8))
        btn_grid.set_margin_bottom(scaled_px(20))

        cash_btn = Gtk.Button(label="💵  Бэлэн (F2)")
        scaled_size_request(cash_btn, -1, 68)
        cash_btn.get_style_context().add_class("pay-select-cash")
        cash_btn.connect("clicked", lambda b: [dialog.response(Gtk.ResponseType.OK), self._show_checkout("cash")])
        btn_grid.pack_start(cash_btn, False, False, 0)

        card_btn = Gtk.Button(label="💳  Карт (F4)")
        scaled_size_request(card_btn, -1, 68)
        card_btn.get_style_context().add_class("pay-select-card")
        card_btn.connect("clicked", lambda b: [dialog.response(Gtk.ResponseType.OK), self._show_checkout("card")])
        btn_grid.pack_start(card_btn, False, False, 0)

        qr_btn = Gtk.Button(label="📱  QR (F5)")
        scaled_size_request(qr_btn, -1, 68)
        qr_btn.get_style_context().add_class("pay-select-qr")
        qr_btn.connect("clicked", lambda b: [dialog.response(Gtk.ResponseType.OK), self._show_checkout("qr")])
        btn_grid.pack_start(qr_btn, False, False, 0)

        content.pack_start(btn_grid, False, False, 0)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _show_checkout(self, default_type="cash"):
        total = self._calc_total()
        if total <= 0:
            return
        items_data = [item.to_dict() for item in self.cart]

        dialog = Gtk.Dialog(
            title="\u0422\u04e9\u043b\u0431\u04e9\u0440",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(scaled_px(420), scaled_px(400))
        dialog.get_content_area().get_style_context().add_class("checkout-dialog")
        content = dialog.get_content_area()
        content.set_spacing(scaled_px(8))
        content.set_margin_top(scaled_px(12))
        content.set_margin_bottom(scaled_px(12))
        content.set_margin_start(scaled_px(16))
        content.set_margin_end(scaled_px(16))

        total_markup = f'<span size="24000" weight="900">\u041d\u0438\u0439\u0442: {format_money(total)}</span>'
        total_label = Gtk.Label()
        total_label.set_markup(total_markup)
        total_label.set_halign(Gtk.Align.CENTER)
        total_label.set_margin_bottom(scaled_px(8))
        content.add(total_label)

        pay_type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(8))
        pay_type_box.set_hexpand(True)
        pay_type_box.set_margin_bottom(scaled_px(8))

        cash_toggle = Gtk.ToggleButton(label="\U0001f4b5  \u0411\u044d\u043b\u044d\u043d (F2)")
        cash_toggle.get_style_context().add_class("payment-cash")
        scaled_size_request(cash_toggle, -1, 44)
        pay_type_box.pack_start(cash_toggle, True, True, 0)

        card_toggle = Gtk.ToggleButton(label="\U0001f4b3  \u041a\u0430\u0440\u0442 (F4)")
        card_toggle.get_style_context().add_class("payment-card")
        scaled_size_request(card_toggle, -1, 44)
        pay_type_box.pack_start(card_toggle, True, True, 0)

        qr_toggle = Gtk.ToggleButton(label="\U0001f4f1  QR (F5)")
        qr_toggle.get_style_context().add_class("payment-qr")
        scaled_size_request(qr_toggle, -1, 44)
        pay_type_box.pack_start(qr_toggle, True, True, 0)

        content.add(pay_type_box)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        stack.set_transition_duration(150)

        cash_page = self._build_cash_page(total)
        stack.add_titled(cash_page, "cash", "\u0411\u044d\u043b\u044d\u043d")

        card_page = self._build_card_page(total, items_data, dialog)
        stack.add_titled(card_page, "card", "\u041a\u0430\u0440\u0442")

        qr_page = self._build_qr_page(total, items_data)
        stack.add_titled(qr_page, "qr", "QR")

        content.pack_start(stack, True, True, 0)

        tin_expander = Gtk.Expander(label="\U0001f4c4  \u0411\u0430\u0439\u0433\u0443\u0443\u043b\u043b\u0430\u0433\u044b\u043d \u0440\u0435\u0433\u0438\u0441\u0442\u0440")
        tin_entry = Gtk.Entry()
        tin_entry.set_placeholder_text("\u0420\u0435\u0433\u0438\u0441\u0442\u0440 \u0434\u0443\u0433\u0430\u0430\u0440 (\u0445\u043e\u043e\u0441\u043e\u043d = \u0445\u0443\u0432\u044c \u0445\u04af\u043d)")
        tin_entry.set_max_length(12)
        tin_expander.add(tin_entry)
        content.pack_start(tin_expander, False, False, 0)

        def on_toggle(active_btn, other1, other2, page_name):
            if active_btn.get_active():
                other1.set_active(False)
                other2.set_active(False)
                stack.set_visible_child_name(page_name)
            else:
                if not other1.get_active() and not other2.get_active():
                    active_btn.set_active(True)

        cash_toggle.connect("toggled", on_toggle, card_toggle, qr_toggle, "cash")
        card_toggle.connect("toggled", on_toggle, cash_toggle, qr_toggle, "card")
        qr_toggle.connect("toggled", on_toggle, cash_toggle, card_toggle, "qr")

        if default_type == "card":
            card_toggle.set_active(True)
        elif default_type == "qr":
            qr_toggle.set_active(True)
        else:
            cash_toggle.set_active(True)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(8))
        btn_box.set_margin_top(scaled_px(8))
        cancel_btn = Gtk.Button(label="\u0426\u0443\u0446\u043b\u0430\u0445")
        cancel_btn.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))
        btn_box.pack_start(cancel_btn, True, True, 0)

        confirm_btn = Gtk.Button(label="\u2713  \u0411\u0410\u0422\u041b\u0410\u0425")
        confirm_btn.get_style_context().add_class("suggested-action")
        btn_box.pack_end(confirm_btn, True, True, 0)
        content.pack_start(btn_box, False, False, 0)

        dialog.show_all()
        tin_expander.set_expanded(False)

        current_type = ["cash"]
        sale_done = [False]

        def set_cash_amount(amt):
            cash_entry = cash_page.cash_entry
            cash_entry.set_text(str(amt))

        def do_confirm(btn):
            ptype = current_type[0]
            if ptype == "cash":
                try:
                    given = int(cash_page.cash_entry.get_text() or "0")
                except ValueError:
                    given = 0
                if given < total:
                    err = Gtk.MessageDialog(
                        transient_for=dialog,
                        flags=Gtk.DialogFlags.MODAL,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.OK,
                        text=f"\u0411\u044d\u043b\u044d\u043d \u043c\u04e9\u043d\u0433\u04e9 \u0445\u04af\u0440\u044d\u043b\u0446\u044d\u0445\u0433\u04af\u0439.\n\u041d\u0438\u0439\u0442: {format_money(total)}\n\u04e8\u0433\u0441\u04e9\u043d: {format_money(given)}",
                    )
                    err.run()
                    err.destroy()
                    return
                dialog.response(Gtk.ResponseType.OK)
                self._complete_sale("cash", cash_given=given)
                sale_done[0] = True
                dialog.destroy()
            else:
                err = Gtk.MessageDialog(
                    transient_for=dialog,
                    flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="\u0422\u0443\u0441\u0442\u0430\u0439 \u0442\u04e9\u043b\u0431\u04e9\u0440\u0438\u0439\u043d \u0442\u043e\u0432\u0447 \u0434\u0430\u0440\u043d\u0430 \u0443\u0443"
                )
                err.run()
                err.destroy()

        confirm_btn.connect("clicked", do_confirm)

        def on_stack_changed(ps, param):
            name = stack.get_visible_child_name()
            current_type[0] = name
            if name == "card":
                try:
                    self.emit("show-paying", total, "card")
                except Exception:
                    pass
            elif name == "cash":
                try:
                    self.emit("show-paying", total, "cash")
                except Exception:
                    pass

        stack.connect("notify::visible-child-name", on_stack_changed)

        old_key_press = dialog.key_press_event
        def on_dialog_key(w, event):
            k = Gdk.keyval_name(event.keyval)
            ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
            if k == "Escape":
                dialog.response(Gtk.ResponseType.CANCEL)
                return True
            if ctrl and k == "Return":
                do_confirm(None)
                return True
            if current_type[0] == "cash":
                amts = {"1": 1000, "2": 5000, "3": 10000, "4": 20000, "5": 50000, "6": 100000, "0": total}
                if k in amts:
                    cash_page.cash_entry.set_text(str(amts[k]))
                    return True
            return False

        dialog.key_press_event = on_dialog_key

        resp = dialog.run()
        dialog.destroy()
        if not sale_done[0]:
            try:
                self.emit("show-idle")
            except Exception:
                pass

    def _build_cash_page(self, total):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(8))

        cash_entry = Gtk.Entry()
        cash_entry.set_placeholder_text(f"\u0413\u0430\u0440\u0430\u0430\u0441 \u0434\u04af\u043d \u043e\u0440\u0443\u0443\u043b\u0430\u0445 (\u041d\u0438\u0439\u0442: {format_money(total)})")
        cash_entry.get_style_context().add_class("barcode-entry")
        box.pack_start(cash_entry, False, False, 0)

        change_label = Gtk.Label(label="\u0411\u0443\u0446\u0430\u0430\u043b\u0442: 0 \u20ae")
        box.pack_start(change_label, False, False, 0)

        quick_grid = Gtk.FlowBox()
        quick_grid.set_max_children_per_line(3)
        quick_grid.set_min_children_per_line(3)
        quick_grid.set_homogeneous(True)
        quick_grid.set_column_spacing(scaled_px(6))
        quick_grid.set_row_spacing(scaled_px(6))
        for amt in (1000, 5000, 10000, 20000, 50000, 100000):
            btn = Gtk.Button(label=format_money(amt))
            btn.get_style_context().add_class("cash-quick-btn")
            btn.connect("clicked", lambda b, a=amt, e=cash_entry: e.set_text(str(a)))
            quick_grid.add(btn)
        box.pack_start(quick_grid, False, False, 0)

        def on_cash_changed(entry):
            try:
                given = int(entry.get_text() or "0")
                chg = given - total
                change_label.set_label(f"\u0411\u0443\u0446\u0430\u0430\u043b\u0442: {format_money(max(0, chg))}")
            except ValueError:
                change_label.set_label("\u0411\u0443\u0446\u0430\u0430\u043b\u0442: \u2014")

        cash_entry.connect("changed", on_cash_changed)

        box.cash_entry = cash_entry
        box.change_label = change_label
        return box

    def _build_card_page(self, total, items, dialog):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(12))

        card_label = Gtk.Label()
        card_label.set_markup(f'<span size="18000" weight="800" color="#1E40AF">{format_money(total)}</span>')
        card_label.set_halign(Gtk.Align.CENTER)
        box.pack_start(card_label, False, False, 0)

        terminal_btn = Gtk.Button(label="\U0001f4b3  \u041a\u0430\u0440\u0442\u0430\u0430\u0440 \u0442\u04e9\u043b\u04af\u04af\u043b\u044d\u0445")
        terminal_btn.get_style_context().add_class("payment-card")
        scaled_size_request(terminal_btn, -1, 54)
        box.pack_start(terminal_btn, False, False, 0)

        spinner = Gtk.Spinner()
        spinner.set_halign(Gtk.Align.CENTER)
        box.pack_start(spinner, False, False, 0)

        status_label = Gtk.Label(label="")
        status_label.set_halign(Gtk.Align.CENTER)
        box.pack_start(status_label, False, False, 0)

        try:
            from config import get_config
            term_enabled = get_config("terminal_enabled") == "true"
            term_ip = get_config("terminal_ip")
        except Exception:
            term_enabled = False
            term_ip = ""

        def on_terminal_click(btn):
            if not term_enabled or not term_ip:
                status_label.set_label("\u0422\u0435\u0440\u043c\u0438\u043d\u0430\u043b \u0442\u043e\u0445\u0438\u0440\u0443\u0443\u043b\u0430\u0430\u0433\u04af\u0439")
                return
            import database as db
            quote, error = db.quote_sale(items, payment_type="card")
            if error:
                status_label.set_label(error)
                return
            spinner.start()
            terminal_btn.set_sensitive(False)

            def _do_terminal():
                from terminal import send_payment
                invoice = f"POS{int(time.time())}"
                result = send_payment(quote["total"], invoice)
                if result.get("success"):
                    txn_id = result.get("transaction_id", "")
                    import database as db2
                    sale, err = db2.create_sale(
                        cashier_id=None, payment_type="card",
                        items=quote["items"], terminal_txn_id=txn_id,
                    )
                    GLib.idle_add(lambda: [spinner.stop(), terminal_btn.set_sensitive(True),
                        status_label.set_label("\u2713 \u0422\u04e9\u043b\u0431\u04e9\u0440 \u0430\u043c\u0436\u0438\u043b\u0442\u0442\u0430\u0439") if err else
                        self._after_sale(sale), False])
                else:
                    GLib.idle_add(lambda: [spinner.stop(), terminal_btn.set_sensitive(True),
                        status_label.set_label(f"\u0410\u043b\u0434\u0430\u0430: {result.get('error', 'PAX \u0430\u043b\u0434\u0430\u0430')}")])

            import threading
            threading.Thread(target=_do_terminal, daemon=True).start()

        terminal_btn.connect("clicked", on_terminal_click)

        return box

    def _build_qr_page(self, total, items):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(8))

        qr_img_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(4))
        qr_img_box.set_halign(Gtk.Align.CENTER)

        qr_label = Gtk.Label(label="QR \u043a\u043e\u0434 \u04af\u04af\u0441\u0433\u044d\u0436 \u0431\u0430\u0439\u043d\u0430...")
        qr_label.set_halign(Gtk.Align.CENTER)
        qr_img_box.pack_start(qr_label, False, False, 0)

        qr_image = Gtk.Image()
        qr_img_box.pack_start(qr_image, False, False, 0)

        box.pack_start(qr_img_box, False, False, 0)

        status_label = Gtk.Label(label="")
        status_label.set_halign(Gtk.Align.CENTER)
        box.pack_start(status_label, False, False, 0)

        fallback_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fallback_box.set_halign(Gtk.Align.CENTER)
        fallback_box.set_no_show_all(True)
        fallback_box.set_visible(False)
        cash_fallback_btn = Gtk.Button(label="\U0001f4b5 \u0411\u044d\u043b\u044d\u043d")
        cash_fallback_btn.connect("clicked", lambda b: self._show_checkout("cash"))
        fallback_box.pack_start(cash_fallback_btn, False, False, 0)
        card_fallback_btn = Gtk.Button(label="\U0001f4b3 \u041a\u0430\u0440\u0442")
        card_fallback_btn.connect("clicked", lambda b: self._show_checkout("card"))
        fallback_box.pack_start(card_fallback_btn, False, False, 0)
        box.pack_start(fallback_box, False, False, 0)

        qr_result = None
        qpay_client = None
        is_mock = False
        invoice_id = ""

        try:
            from qpay import QPayClient
            if QPayClient.is_configured():
                qpay_client = QPayClient.from_config()
                qr_result = qpay_client.create_invoice(total)
            else:
                is_mock = True
        except Exception:
            is_mock = True

        if is_mock or qr_result is None or not qr_result.get("invoice_id"):
            qr_label.set_label("QR \u043a\u043e\u0434 \u0430\u043b\u0434\u0430\u0430 \u0433\u0430\u0440\u043b\u0430\u0430")
            import base64 as b64_mod, io
            buf = io.BytesIO()
            mock_data = f"MOCK{int(time.time())}"
            try:
                import qrcode
                qr = qrcode.QRCode(box_size=10, border=2)
                qr.add_data(mock_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                img.save(buf, format="PNG")
                qr_b64 = b64_mod.b64encode(buf.getvalue()).decode()
            except ImportError:
                qr_b64 = None
            qr_result = {"invoice_id": mock_data, "qr_image": qr_b64, "is_mock": True}
            invoice_id = mock_data
            status_label.set_label("QPay \u0442\u043e\u0445\u0438\u0440\u0443\u0443\u043b\u0430\u0430\u0433\u04af\u0439. \u0411\u044d\u043b\u044d\u043d/\u043a\u0430\u0440\u0442\u0430\u0430\u0440 \u0442\u04e9\u043b\u04af\u04af\u043b\u043d\u044d \u04af\u04af.")
            fallback_box.set_visible(True)

        if qr_result and qr_result.get("qr_image"):
            try:
                import base64 as b64_mod2
                loader = Gdk.PixbufLoader.new_with_type("png")
                loader.write(b64_mod2.b64decode(qr_result["qr_image"]))
                loader.close()
                pixbuf = loader.get_pixbuf().scale_simple(200, 200, Gdk.InterpType.BILINEAR)
                qr_image.set_from_pixbuf(pixbuf)
                qr_label.hide()
                try:
                    self.emit("show-qr", total, pixbuf)
                except Exception:
                    pass
            except Exception:
                pass

        if not is_mock and qpay_client and qr_result:
            invoice_id = qr_result.get("invoice_id", "")
            qr_label.set_label(f"\u041d\u044d\u0445\u044d\u043c\u0436\u043b\u044d\u0445: {invoice_id}\n\U0001f4f1 \u04ae\u0439\u043b\u0447\u043b\u04af\u04af\u043b\u044d\u0433\u0447 QR \u0443\u043d\u0448\u0443\u0443\u043b\u043d\u0430 \u0443\u0443")
            status_label.set_label("\u0422\u04e9\u043b\u0431\u04e9\u0440 \u0445\u04af\u043b\u044d\u044d\u0436 \u0431\u0430\u0439\u043d\u0430...")

            check_stop = [False]

            def _poll_qr():
                if check_stop[0]:
                    return False
                try:
                    result = qpay_client.check_payment(invoice_id)
                    if result.get("payment_status") == "paid":
                        GLib.idle_add(lambda: [status_label.set_label("\u2713 \u0422\u04e9\u043b\u04e9\u0440 \u0430\u043c\u0436\u0438\u043b\u0442\u0442\u0430\u0439"),
                            self._complete_sale("qr", qpay_invoice_id=invoice_id), False])
                        return False
                except Exception:
                    pass
                return True

            def _start_poll():
                import threading
                def poll_loop():
                    for _ in range(100):
                        if check_stop[0]:
                            break
                        if not _poll_qr():
                            break
                        time.sleep(3)

                t = threading.Thread(target=poll_loop, daemon=True)
                t.start()
                box.qr_poll_thread = t
                box.qr_check_stop = check_stop

            _start_poll()

        return box

    def _add_product_to_cart(self, product, quantity=1.0):
        name = product.get("name", "")
        barcode = product.get("barcode", "")
        price = product.get("price", 0)
        pid = product.get("id")
        unit = product.get("unit", "ш")
        category = product.get("category", "")

        if product.get("stock_qty", 99999) <= 0:
            self._show_toast(f"⚠️ '{name}' барааны үлдэгдэл дууссан байна!", "warning")

        for item in self.cart:
            if item.barcode and item.barcode == barcode and item.unit_price == price:
                item.quantity += quantity
                self._update_cart_ui()
                self._play_beep()
                return
            if item.product_id and item.product_id == pid and not barcode:
                item.quantity += quantity
                self._update_cart_ui()
                self._play_beep()
                return

        cart_item = CartItem(
            product_id=pid, barcode=barcode, product_name=name,
            category=category, unit_price=price, quantity=quantity, unit=unit,
        )
        self.cart.append(cart_item)
        self._update_cart_ui()
        self._play_beep()

    def _play_beep(self):
        try:
            Gdk.beep()
        except Exception:
            pass

    def _on_remove_item(self, item):
        if item in self.cart:
            self.cart.remove(item)
            self._update_cart_ui()

    def _clear_cart(self, confirm=False):
        if confirm and self.cart:
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="\u0421\u0430\u0433\u0441\u044b\u0433 \u0446\u044d\u0432\u044d\u0440\u043b\u044d\u0445 \u04af\u04af?",
            )
            resp = dialog.run()
            dialog.destroy()
            if resp != Gtk.ResponseType.YES:
                return
        self.cart.clear()
        self._update_cart_ui()

    def _update_cart_ui(self):
        for child in self.cart_list.get_children():
            self.cart_list.remove(child)

        if not self.cart:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            empty_box.set_halign(Gtk.Align.CENTER)
            empty_box.set_margin_top(40)
            empty_box.set_margin_bottom(40)
            empty_icon = Gtk.Label(label="🛒")
            empty_icon.get_style_context().add_class("cart-empty-icon")
            empty_icon.set_halign(Gtk.Align.CENTER)
            empty_box.pack_start(empty_icon, False, False, 0)
            empty_label = Gtk.Label(label="Бараа сканнердах эсвэл\nдарж сонгоно уу")
            empty_label.set_justify(Gtk.Justification.CENTER)
            empty_label.get_style_context().add_class("cart-empty-state")
            empty_box.pack_start(empty_label, False, False, 0)
            empty_box.show_all()
            self.cart_list.add(empty_box)

        total_amount = 0
        total_items = 0
        for item in self.cart:
            subtotal = item.subtotal
            total_amount += subtotal
            total_items += item.quantity

            row = make_cart_item_row(
                item,
                on_remove=self._on_remove_item,
                on_qty_change=self._on_qty_changed,
            )
            row.show_all()
            self.cart_list.add(row)

        total = self._calc_total()
        self.total_label.set_markup(
            f"<span>Нийт:  </span><span weight=\"800\" foreground=\"#059669\">{format_money(total)}</span>"
        )
        self.cart_count_label.set_label(str(len(self.cart)))
        self.cart_list.show_all()

        self.pay_btn.set_sensitive(total > 0)

        self._update_badges()

        try:
            self.emit("cart-changed", self.cart, total)
        except Exception:
            pass

    def _update_badges(self):
        import database as db
        try:
            held = db.get_held_orders()
            count = len(held)
            if count > 0:
                self.held_badge.set_label(str(count))
                self.held_badge.show()
            else:
                self.held_badge.set_label("")
                self.held_badge.hide()

            failed_count = db.get_ebarimt_failed_count()
            if failed_count > 0 and hasattr(self, 'ebarimt_badge'):
                self.ebarimt_badge.set_label(str(failed_count))
                self.ebarimt_badge.show()
            elif hasattr(self, 'ebarimt_badge'):
                self.ebarimt_badge.set_label("")
                self.ebarimt_badge.hide()
        except Exception:
            pass

    def _calc_total(self):
        return sum(item.subtotal for item in self.cart)

    def _on_qty_changed(self, item, delta):
        item.quantity = max(0.1, item.quantity + delta)
        self._update_cart_ui()

    def _complete_sale(self, payment_type, cash_given=0, card_amount=0, txn_id="", qpay_invoice_id=""):
        if getattr(self, "_checkout_in_flight", False):
            return
        self._checkout_in_flight = True
        if hasattr(self, "pay_btn"):
            self.pay_btn.set_sensitive(False)

        items = [item.to_dict() for item in self.cart]
        total = self._calc_total()

        def _write():
            import database as db
            if payment_type == "cash":
                sale, error = db.create_sale(
                    cashier_id=None, payment_type="cash",
                    items=items, cash_given=cash_given,
                    cash_amount=total,
                )
            elif payment_type == "card":
                sale, error = db.create_sale(
                    cashier_id=None, payment_type="card",
                    items=items, card_amount=total,
                    terminal_txn_id=txn_id,
                )
            elif payment_type == "qr":
                sale, error = db.create_sale(
                    cashier_id=None, payment_type="qr",
                    items=items, card_amount=total,
                )
            else:
                sale, error = None, f"Төлбөрийн төрөл буруу: {payment_type}"

            if error:
                return {"error": error}

            if qpay_invoice_id and sale:
                try:
                    with db.get_db() as conn:
                        conn.execute(
                            "UPDATE sales SET qpay_invoice_id = ?, qpay_payment_status = 'paid' WHERE id = ?",
                            (qpay_invoice_id, sale["id"])
                        )
                except Exception:
                    pass

            return {"sale": sale}

        def _on_done(result):
            self._checkout_in_flight = False
            if result.get("error"):
                if hasattr(self, "pay_btn"):
                    self.pay_btn.set_sensitive(True)
                self._show_error_dialog(f"Борлуулалт хадгалахад алдаа: {result['error']}")
                return
            self._after_sale(result["sale"])

        def _on_error(err):
            self._checkout_in_flight = False
            if hasattr(self, "pay_btn"):
                self.pay_btn.set_sensitive(True)
            self._show_error_dialog(f"Борлуулалт хадгалахад алдаа: {err}")

        if self.workqueue:
            self.workqueue.write(_write, on_done=_on_done, on_error=_on_error)
        else:
            _on_done(_write())

    def _after_sale(self, sale):
        if self.workqueue:
            def _print():
                from printer import print_receipt
                from config import get_store_info
                try:
                    print_receipt(sale, get_store_info())
                except Exception as e:
                    logger.error(f"Print failed: {e}")

            from config import is_ebarimt_configured
            if is_ebarimt_configured():
                def _ebarimt():
                    import database as db
                    try:
                        from ebarimt import EbarimtAdapter
                        adapter = EbarimtAdapter()
                        result = adapter.send_receipt(sale)
                        db.update_sale_ebarimt(
                            sale["id"],
                            status="sent" if result.get("success") else "failed",
                            ebarimt_id=result.get("ebarimt_id", ""),
                            ebarimt_qr=result.get("qr_data", ""),
                            lottery=result.get("lottery", ""),
                        )
                    except ImportError:
                        logger.warning("ebarimt.py not available — leaving sale eBarimt status as pending")
                    except Exception as e:
                        logger.error(f"eBarimt submit failed: {e}")
                        try:
                            db.update_sale_ebarimt(sale["id"], status="failed")
                        except Exception:
                            pass
                self.workqueue.async_op(_ebarimt)

            self.workqueue.async_op(_print)

        self._after_sale_done(sale)
        self._clear_cart()

    def _after_sale_done(self, sale):
        self._last_sale = sale
        self._show_sale_complete(sale)
        try:
            self.emit("show-idle")
        except Exception:
            pass

    def _show_sale_complete(self, sale):
        dialog = Gtk.Dialog(
            title=f"\u2705 \u0411\u043e\u0440\u043b\u0443\u0443\u043b\u0430\u043b\u0442 \u0430\u043c\u0436\u0438\u043b\u0442\u0442\u0430\u0439 \u2116{sale.get('id','?')}",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(scaled_px(400), scaled_px(500))
        content = dialog.get_content_area()
        content.set_spacing(scaled_px(8))
        content.set_margin_top(scaled_px(12))
        content.set_margin_bottom(scaled_px(12))
        content.set_margin_start(scaled_px(16))
        content.set_margin_end(scaled_px(16))

        receipt_items = "\n".join(
            f'{i.get("product_name","")}\n    {i.get("quantity",1)}\u00d7{format_money(i.get("unit_price",0))}  = {format_money(i.get("subtotal",0))}'
            for i in sale.get("items", [])
        )
        receipt_text = f"""================================
      \u0411\u041e\u0420\u041b\u0423\u0423\u041b\u0410\u041b\u0422\u042b\u041d \u0411\u0410\u0420\u0418\u041c\u0422
================================

\u0414\u0443\u0433\u0430\u0430\u0440: \u2116{sale.get("id","?")}
\u041e\u0433\u043d\u043e\u043e: {sale.get("created_at","")[:16]}
\u0422\u04e9\u043b\u0431\u04e9\u0440: {sale.get("payment_type","").upper()}
--------------------------------

{receipt_items}

--------------------------------
          \u041d\u0418\u0419\u0422: {format_money(sale.get("total",0))}
================================
        """
        receipt_label = Gtk.Label(label=receipt_text)
        receipt_label.set_selectable(True)
        receipt_label.set_justify(Gtk.Justification.LEFT)
        css = b"label.receipt-text { font-family: monospace; font-size: 13px; background: #F8FAFC; padding: 12px; border-radius: 8px; }"
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        receipt_label.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        receipt_label.get_style_context().add_class("receipt-text")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(scaled_px(250))
        scrolled.add(receipt_label)
        content.add(scrolled)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(8))
        btn_box.set_homogeneous(True)

        print_btn = Gtk.Button(label="\ud83d\udda8  \u0425\u042d\u0412\u041b\u042d\u0425")
        print_btn.get_style_context().add_class("suggested-action")
        print_btn.connect("clicked", lambda b: self._print_receipt(sale))
        btn_box.add(print_btn)

        new_btn = Gtk.Button(label="\ud83d\udd86  \u0428\u0418\u041d\u042d")
        new_btn.connect("clicked", lambda b: [self._clear_cart(), self._update_cart_ui(), dialog.response(Gtk.ResponseType.OK)])
        btn_box.add(new_btn)

        close_btn = Gtk.Button(label="\u2715  \u0425\u0410\u0410\u0425")
        close_btn.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))
        btn_box.add(close_btn)

        content.add(btn_box)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _print_receipt(self, sale):
        try:
            import printer
            store_info = {}
            printer.print_receipt(sale, store_info)
        except Exception as e:
            self._show_error_dialog(f"\u0425\u044d\u0432\u043b\u044d\u0445 \u0430\u043b\u0434\u0430\u0430: {e}")

    def _show_weight_prompt(self, product):
        dialog = Gtk.Dialog(
            title=product.get("name", ""),
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(360, 300)
        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(24)
        content.set_margin_end(24)

        header = Gtk.Label()
        unit = product.get("unit", "ш")
        header.set_markup(f'<span size="16000" weight="800">{product.get("name", "")}</span>\n<span size="12000">{format_money(product.get("price",0))}/{unit}</span>')
        content.add(header)

        content.add(Gtk.Label(label=f"\u0422\u043e\u043e \u0445\u044d\u043c\u0436\u044d\u044d\u0433\u04e9\u04e9 \u043e\u0440\u0443\u0443\u043b\u0430\u0443\u043b ({unit})"))

        entry = Gtk.Entry()
        entry.set_text("1")
        entry.set_activates_default(True)
        entry.set_alignment(1.0)
        entry.set_size_request(-1, 48)
        entry.get_style_context().add_class("barcode-entry")
        content.add(entry)

        presets = Gtk.FlowBox()
        presets.set_max_children_per_line(4)
        presets.set_min_children_per_line(4)
        presets.set_homogeneous(True)
        presets.set_column_spacing(6)
        presets.set_row_spacing(6)
        for p in [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]:
            btn = Gtk.Button(label=str(p))
            btn.connect("clicked", lambda b, v=p: entry.set_text(str(v)))
            presets.add(btn)
        content.add(presets)

        total_label = Gtk.Label()
        total_label.set_markup(f"\u0414\u04af\u043d: {format_money(product.get('price',0))}")
        content.add(total_label)

        def on_qty_changed(e):
            try:
                q = float(e.get_text() or "0")
                total_label.set_markup(f"\u0414\u04af\u043d: {format_money(product.get('price',0) * q)}")
            except ValueError:
                pass
        entry.connect("changed", on_qty_changed)

        dialog.add_button("\u0425\u0430\u0430\u0445", Gtk.ResponseType.CANCEL)
        confirm_btn = dialog.add_button("\u2713 \u041d\u044d\u043c\u044d\u0445", Gtk.ResponseType.OK)
        confirm_btn.get_style_context().add_class("suggested-action")

        dialog.show_all()
        entry.grab_focus()

        if dialog.run() == Gtk.ResponseType.OK:
            try:
                qty = float(entry.get_text() or "0")
            except ValueError:
                qty = 0
            if qty > 0:
                self._add_product_to_cart(product, quantity=qty)
        dialog.destroy()

    def _show_not_found_dialog(self, barcode):
        dialog = Gtk.Dialog(
            title="❓ Баркод олдсонгүй",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(420, 320)
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(16)
        content.set_margin_end(16)

        content.add(Gtk.Label(label=f"Баркод: <b>{barcode}</b>\nШинэ бараа үүсгэх үү?", use_markup=True))

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Барааны нэр")
        content.add(name_entry)

        price_entry = Gtk.Entry()
        price_entry.set_placeholder_text("Үнэ (₮)")
        price_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        content.add(price_entry)

        content.add(Gtk.Label(label="Ангилал:"))

        cat_combo = Gtk.ComboBoxText()
        cat_combo.append_text("Бусад")
        if self.cache:
            for cat in self.cache.categories():
                cat_combo.append_text(cat)
        cat_combo.set_active(0)
        content.add(cat_combo)

        unit_combo = Gtk.ComboBoxText()
        for u in ("ш", "кг", "л", "хайрцаг"):
            unit_combo.append_text(u)
        unit_combo.set_active(0)
        content.add(unit_combo)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        create_btn = dialog.add_button("✓ Үүсгэх + Сагсанд нэмэх", Gtk.ResponseType.OK)
        create_btn.get_style_context().add_class("suggested-action")

        while True:
            dialog.show_all()
            resp = dialog.run()
            if resp == Gtk.ResponseType.OK:
                name = name_entry.get_text().strip()
                try:
                    price = int(price_entry.get_text() or "0")
                except ValueError:
                    price = 0
                category = cat_combo.get_active_text() or "Бусад"
                unit = unit_combo.get_active_text() or "ш"

                if not name or price <= 0:
                    err = Gtk.MessageDialog(
                        transient_for=dialog,
                        flags=Gtk.DialogFlags.MODAL,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.OK,
                        text="Нэр болон үнэ оруулна уу",
                    )
                    err.run()
                    err.destroy()
                    continue

                import database as db
                pid, err = db.create_product(
                    barcode=barcode, name=name, price=price,
                    category=category, unit=unit,
                )
                if err:
                    err = Gtk.MessageDialog(
                        transient_for=dialog,
                        flags=Gtk.DialogFlags.MODAL,
                        message_type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        text=f"Алдаа: {err}",
                    )
                    err.run()
                    err.destroy()
                    continue

                if self.cache:
                    self.cache.invalidate()
                if self.app and self.app.cache:
                    self.app.cache.invalidate()

                product = {"id": pid, "name": name, "barcode": barcode,
                          "price": price, "category": category, "unit": unit}
                self._add_product_to_cart(product)
                self._build_product_grid()
                self._apply_filters()
                dialog.destroy()
                return
            dialog.destroy()
            return

    def _show_held_orders(self):
        import database as db
        orders = db.get_held_orders()

        dialog = Gtk.Dialog(
            title="📋 Хүлээлгэсэн захиалгууд",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(500, 400)
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(16)
        content.set_margin_end(16)

        scrolled = Gtk.ScrolledWindow()
        lb = Gtk.ListBox()
        scrolled.add(lb)
        content.add(scrolled)

        for o in orders:
            import json
            try:
                items = json.loads(o["items"]) if isinstance(o["items"], str) else o["items"]
            except Exception:
                items = []
            item_count = len(items) if isinstance(items, list) else 0
            label = f"{o['label']} — {item_count} бараа — {format_money(o['total'])}"
            row = Gtk.ListBoxRow()
            row_label = Gtk.Label(label=label, xalign=0, margin=4)
            row.add(row_label)
            row.order_id = o["id"]
            row.order_items = items
            row.connect("activate", self._on_held_order_activate)
            lb.add(row)

        if not orders:
            lb.add(Gtk.Label(label="Хүлээлгэсэн захиалга байхгүй"))

        dialog.add_button("Хаах", Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _on_held_order_activate(self, listbox, row):
        if not hasattr(row, 'order_items'):
            return
        items = row.order_items
        if isinstance(items, list):
            import database as db
            for item_data in items:
                if isinstance(item_data, dict):
                    product = {
                        "id": item_data.get("product_id"),
                        "barcode": item_data.get("barcode", ""),
                        "name": item_data.get("product_name", ""),
                        "price": item_data.get("unit_price", 0),
                        "unit": item_data.get("unit", "ш"),
                        "category": "",
                    }
                    qty = item_data.get("quantity", 1)
                    self._add_product_to_cart(product, quantity=qty)
            try:
                db.delete_held_order(row.order_id)
            except Exception:
                pass
        self.get_toplevel().get_children()[-1].destroy()

    def _hold_order(self):
        if not self.cart:
            return
        dialog = Gtk.Dialog(
            title="Захиалга хүлээлгэх",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_start(16)

        content.set_margin_end(16)

        content.set_margin_top(16)

        content.set_margin_bottom(16)
        content.add(Gtk.Label(label="Захиалгын нэр:"))
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Захиалгын нэр")
        name_entry.set_activates_default(True)
        content.add(name_entry)
        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        dialog.add_button("Хадгалах", Gtk.ResponseType.OK)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            label = name_entry.get_text().strip() or "Захиалга"
            items = [item.to_dict() for item in self.cart]
            total = self._calc_total()
            import database as db
            db.create_held_order(label, items, total)
            self._clear_cart()
        dialog.destroy()

    def _show_ebarimt_pending(self):
        import database as db
        pending = db.get_pending_ebarimt_sales()
        dialog = Gtk.Dialog(
            title=f"Худалдан амжилтгүй eBarimt ({len(pending)})",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(500, 400)
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(16)
        content.set_margin_end(16)

        if not pending:
            content.add(Gtk.Label(label="Худалдан амжилтгүй eBarimt байхгүй"))
        else:
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_min_content_height(250)
            listbox = Gtk.ListBox()
            for s in pending:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(
                    label=f"№{s['id']} | {s.get('created_at','')[:16]} | {s.get('ebarimt_status','')} | ₮{format_money(s.get('total',0))}",
                    xalign=0, margin=8,
                )
                row.add(label)
                row.sale_id = s["id"]
                listbox.add(row)

            listbox.connect("row-activated", lambda lb, r: self._retry_ebarimt(r.sale_id))
            scrolled.add(listbox)
            content.add(scrolled)

            retry_all = Gtk.Button(label="Бүгдийг дахин илгээх")
            retry_all.connect("clicked", lambda b: self._retry_all_ebarimt(pending))
            content.add(retry_all)

        dialog.add_button("Хаах", Gtk.ResponseType.OK)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _retry_ebarimt(self, sale_id):
        try:
            from ebarimt import EbarimtAdapter
            import database as db
            adapter = EbarimtAdapter()
            sale = db.get_sale(sale_id)
            if not sale:
                self._show_error_dialog(f"Sale #{sale_id} not found")
                return
            result = adapter.send_receipt(sale)
            db.update_sale_ebarimt(
                sale_id,
                status="sent" if result.get("success") else "failed",
                ebarimt_id=result.get("ebarimt_id", ""),
                ebarimt_qr=result.get("qr_data", ""),
                lottery=result.get("lottery", ""),
            )
            self._show_toast("✅ eBarimt дахин илгээгдлээ", "success")
            self._update_badges()
        except Exception as e:
            self._show_error_dialog(f"eBarimt алдаа: {e}")

    def _retry_all_ebarimt(self, pending):
        from config import is_ebarimt_configured
        if not is_ebarimt_configured():
            self._show_error_dialog("eBarimt тохируулаагүй")
            return
        import database as db
        from ebarimt import EbarimtAdapter
        adapter = EbarimtAdapter()
        success = 0
        fail = 0
        for s in pending:
            try:
                result = adapter.send_receipt(s)
                db.update_sale_ebarimt(
                    s["id"],
                    status="sent" if result.get("success") else "failed",
                    ebarimt_id=result.get("ebarimt_id", ""),
                    ebarimt_qr=result.get("qr_data", ""),
                    lottery=result.get("lottery", ""),
                )
                success += 1
            except Exception:
                fail += 1
                try:
                    db.update_sale_ebarimt(s["id"], status="failed")
                except Exception:
                    pass
        self._show_toast(f"✅ eBarimt: {success} амжилттай, {fail} амжилтгүй", "success")
        self._update_badges()

    def _show_anonymous_price_prompt(self):
        dialog = Gtk.Dialog(
            title="\u0411\u04af\u0440\u0442\u0433\u044d\u043b\u0433\u04af\u0439 \u0431\u0430\u0440\u0430\u0430",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(350, 200)
        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(24)
        content.set_margin_end(24)

        title = Gtk.Label()
        title.set_markup('<span size="18000" weight="800">\u0411\u04af\u0440\u0442\u0433\u044d\u043b\u0433\u04af\u0439 \u0431\u0430\u0440\u0430\u0430</span>')
        content.add(title)

        content.add(Gtk.Label(label="\u0414\u04af\u043d\u0433\u044d\u044d \u043e\u0440\u0443\u0443\u043b\u0430\u0430\u0434 Enter \u0434\u0430\u0440\u043d\u0430 \u0443\u0443"))

        entry = Gtk.Entry()
        entry.set_placeholder_text("\u04e8\u0440\u0442\u04e9\u0433 (\u20ae)")
        entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        entry.set_activates_default(True)
        entry.set_size_request(-1, 48)
        content.add(entry)

        dialog.add_button("\u0425\u0430\u0430\u0445", Gtk.ResponseType.CANCEL)
        confirm_btn = dialog.add_button("\u2713 \u0411\u0430\u0442\u043b\u0430\u0445", Gtk.ResponseType.OK)
        confirm_btn.get_style_context().add_class("suggested-action")

        dialog.show_all()
        entry.grab_focus()

        if dialog.run() == Gtk.ResponseType.OK:
            try:
                price = int(entry.get_text() or "0")
            except ValueError:
                price = 0
            if price > 0:
                product = {
                    "id": None, "barcode": "", "name": "\u0411\u04af\u0440\u0442\u0433\u044d\u043b\u0433\u04af\u0439 \u0431\u0430\u0440\u0430\u0430",
                    "price": price, "category": "\u0411\u0443\u0441\u0430\u0434", "unit": "\u0448",
                }
                self._add_product_to_cart(product)
        dialog.destroy()

    def _show_error_dialog(self, message):
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        d.run()
        d.destroy()

    def _setup_event_handlers(self):
        self.barcode_entry.connect("activate", self._on_barcode_scanned)
        self.search_entry.connect("search-changed", self._on_search_changed)

    def handle_payment_trigger(self, payment_type):
        self._on_pay_clicked(None)

    def _toggle_ebarimt_type(self):
        if self.ebarimt_type == "individual":
            self.ebarimt_type = "corporate"
            self._show_toast("🏢 Байгууллагын eBarimt сонгогдлоо. (ТТД оруулах шаардлагатай)", "info")
        elif self.ebarimt_type == "corporate":
            self.ebarimt_type = "none"
            self._show_toast("🧾 Зөвхөн дотоод талон хэвлэгдэнэ (НӨАТ хасав).", "warning")
        else:
            self.ebarimt_type = "individual"
            self._show_toast("👤 Иргэний eBarimt сонгогдлоо.", "success")
        self._update_tax_indicator_ui()

    def _update_tax_indicator_ui(self):
        if hasattr(self, 'tax_mode_label'):
            mapping = {"individual": "👤 Иргэн", "corporate": "🏢 Байгууллага", "none": "❌ Талон"}
            self.tax_mode_label.set_markup(f"<b>{mapping.get(self.ebarimt_type)}</b>")
            ctx = self.tax_mode_label.get_style_context()
            for cls in ["individual", "corporate", "none"]:
                ctx.remove_class(cls)
            ctx.add_class(self.ebarimt_type)

    def _on_hold_order_clicked(self, button=None):
        if not self.cart:
            self._show_toast("⚠️ Сагс хоосон тул түр хадгалах боломжгүй.", "warning")
            return

        import time
        order_snapshot = {
            "id": int(time.time()),
            "items": list(self.cart),
            "time_str": time.strftime("%H:%M:%S"),
            "total": sum(item.subtotal for item in self.cart),
        }
        self.held_orders.append(order_snapshot)
        self._clear_cart()
        self._update_held_orders_counter_ui()
        self._show_toast("📥 Захиалгыг түр хадгаллаа.", "info")

    def _on_resume_order_clicked(self, button=None):
        if not self.held_orders:
            self._show_toast("🔍 Түр хадгалсан захиалга байхгүй байна.", "warning")
            return

        if self.cart:
            self._show_toast("⚠️ Одоогийн сагсыг түр хадгалах эсвэл устгасны дараа сэргээнэ үү!", "warning")
            return

        last_order = self.held_orders.pop()
        self.cart = last_order["items"]
        self._update_cart_ui()
        self._update_held_orders_counter_ui()
        self._show_toast("📤 Захиалгыг сэргээлээ.", "success")

    def _update_held_orders_counter_ui(self):
        count = len(self.held_orders)
        if hasattr(self, 'held_count_label'):
            if count > 0:
                self.held_count_label.set_text(str(count))
                self.held_count_label.show()
            else:
                self.held_count_label.set_text("")
                self.held_count_label.hide()

    def bind_keyboard_accelerators(self):
        toplevel = self.get_toplevel()
        if not toplevel or not isinstance(toplevel, Gtk.Window):
            GLib.idle_add(self.bind_keyboard_accelerators)
            return False

        def on_key_pressed(window, event):
            keyval = event.keyval

            if keyval == Gdk.KEY_F2:
                self.handle_payment_trigger("Бэлэн")
                return True
            elif keyval == Gdk.KEY_F4:
                self.handle_payment_trigger("Карт")
                return True
            elif keyval == Gdk.KEY_F7:
                self._toggle_ebarimt_type()
                return True
            elif keyval == Gdk.KEY_F9:
                self._on_hold_order_clicked()
                return True
            elif keyval == Gdk.KEY_F10:
                self._on_resume_order_clicked()
                return True
            elif keyval == Gdk.KEY_Escape:
                if isinstance(window.get_focus(), (Gtk.Entry, Gtk.SearchEntry)):
                    window.set_focus(None)
                    self.barcode_entry.grab_focus()
                    return True
                if self.cart:
                    self._clear_cart()
                    self._show_toast("🗑️ Сагсыг цэвэрлэв.", "info")
                self.barcode_entry.grab_focus()
                return True

            return False

        toplevel.connect("key-press-event", on_key_pressed)
        logger.info("Native POS keyboard accelerators wired.")
        return False

    def _show_help(self):
        text = """╔══════════════════════════════╗
║     ⌨ Товчны тусламж         ║
╠══════════════════════════════╣
║ F1  — Энэ тусламж           ║
║ F2  — Бэлнээр төлөх         ║
║ F4  — Картаар төлөх         ║
║ F5  — QR төлбөр             ║
║ F3  — Захиалга хүлээлгэх    ║
║ ESC — Сагс цэвэрлэх         ║
║ Ctrl+F — Хайлт              ║
║ →←↑↓  — Бараа сонгох        ║
║ Enter — Сонгосон бараа нэмэх║
║ 1-6   — Түргэн дүн          ║
╚══════════════════════════════╝"""
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )
        d.run()
        d.destroy()

    def _show_toast(self, text, toast_type="info"):
        parent = self.get_toplevel()
        content = parent.get_child()
        if not content:
            return

        toast = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_top=8,
            margin_bottom=8,
            margin_start=16,
            margin_end=16,
        )
        toast.set_valign(Gtk.Align.START)
        toast.set_halign(Gtk.Align.CENTER)
        toast.get_style_context().add_class("notification-toast")
        toast.get_style_context().add_class(toast_type)

        icon = "\u2705" if toast_type == "success" else "\u26a0\ufe0f" if toast_type == "warning" else "\u2139\ufe0f"
        icon_label = Gtk.Label(label=icon)
        toast.add(icon_label)
        msg_label = Gtk.Label(label=text)
        msg_label.set_max_width_chars(50)
        msg_label.set_wrap(True)
        toast.add(msg_label)

        content.pack_start(toast, False, False, 0)
        content.reorder_child(toast, 0)
        toast.show_all()

        def remove_toast():
            try:
                if toast in list(content.get_children()):
                    content.remove(toast)
            except Exception:
                pass

        import threading
        threading.Timer(3.0, GLib.idle_add, args=(remove_toast,)).start()

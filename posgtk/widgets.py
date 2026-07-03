"""
posgtk/widgets.py — Styled GTK widget factories matching production web app design.

ProductCard with 4px category accent bar, emoji icon, name, price.
CartItemRow with category-colored icon box, qty controls, subtotal.
Styled by posgtk/theme.py via dark.css / light.css.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Pango

from posgtk.scaling import scaled_px

CAT_ICONS = {
    "Сүүн бүтээгдэхүүн": "🥛", "Талх нарийн боов": "🍞", "Өндөг": "🥚",
    "Будаа": "🍚", "Гоймон": "🍜", "Тос": "🛢️", "Чихэр": "🍬",
    "Давс амтлагч": "🧂", "Жимс": "🍎", "Ус ундаа": "🥤",
    "Хүнсний ногоо": "🥬", "Мах": "🥩", "Амттан": "🍰",
    "Өрхийн бараа": "🏠", "Бусад": "📦",
    "Хүнс": "🍖", "Ундаа": "🥤", "Цэвэрлэгээ": "🧹", "Тамхи": "🚬",
    "Ахуйн": "🏠",
}

WEB_CAT_COLORS = {
    "Сүүн бүтээгдэхүүн": "#3B82F6", "Талх нарийн боов": "#F59E0B",
    "Өндөг": "#EAB308", "Будаа": "#22C55E", "Гоймон": "#EF4444",
    "Тос": "#A855F7", "Чихэр": "#06B6D4", "Давс амтлагч": "#78716C",
    "Жимс": "#84CC16", "Ус ундаа": "#0EA5E9",
    "Хүнсний ногоо": "#10B981", "Мах": "#DC2626", "Амттан": "#EC4899",
    "Өрхийн бараа": "#8B5CF6", "Бусад": "#6B7280",
}


def format_money(amount):
    return f"{amount:,.0f} ₮"


def get_category_icon(category):
    return CAT_ICONS.get(category, "📦")


def get_category_color(category, cache=None):
    if cache:
        color = cache.get_category_color(category)
        if color and color != "#6B7280":
            return color
    return WEB_CAT_COLORS.get(category, "#6B7280")


def make_loading_placeholder(title):
    b = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=12,
        margin_top=80, margin_bottom=80, margin_start=40, margin_end=40,
    )
    label = Gtk.Label(
        label=f"{title}\n\nДарвал ачааллана",
        justify=Gtk.Justification.CENTER,
    )
    b.pack_start(label, True, True, 0)
    return b


def make_product_card(product, on_click, cache=None):
    category = product.get("category", "Бусад")
    cat_color = get_category_color(category, cache)

    card = Gtk.Button()
    card.set_relief(Gtk.ReliefStyle.NONE)
    card.get_style_context().add_class("product-card")
    card.set_size_request(scaled_px(146), scaled_px(165))

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

    accent = Gtk.Box()
    accent.get_style_context().add_class("card-accent")
    accent.set_size_request(-1, scaled_px(4))
    color_str = cat_color.lstrip("#")
    if len(color_str) == 6:
        r, g, b = int(color_str[0:2], 16), int(color_str[2:4], 16), int(color_str[4:6], 16)
        accent.override_background_color(
            Gtk.StateFlags.NORMAL,
            Gdk.RGBA(r/255.0, g/255.0, b/255.0, 1.0)
        )
    outer.pack_start(accent, False, False, 0)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=scaled_px(4))
    content.set_valign(Gtk.Align.CENTER)
    content.set_halign(Gtk.Align.CENTER)
    content.set_margin_top(scaled_px(8))
    content.set_margin_bottom(scaled_px(8))
    content.set_margin_start(scaled_px(6))
    content.set_margin_end(scaled_px(6))

    icon_label = Gtk.Label(label=get_category_icon(category))
    icon_label.get_style_context().add_class("card-icon")
    icon_label.set_halign(Gtk.Align.CENTER)
    content.pack_start(icon_label, False, False, 0)

    name = product.get("name", "")
    name_label = Gtk.Label(label=name)
    name_label.get_style_context().add_class("product-name")
    name_label.set_line_wrap(True)
    name_label.set_max_width_chars(14)
    name_label.set_alignment(0.5, 0.5)
    name_label.set_ellipsize(Pango.EllipsizeMode.END)
    name_label.set_lines(2)
    name_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    unit = product.get("unit", "ш")
    barcode_val = product.get("barcode", "")
    name_label.set_tooltip_text(f"{name}\nБаркод: {barcode_val}\nНэгж: {unit}")
    content.pack_start(name_label, True, True, 0)

    price_label = Gtk.Label(label=format_money(product.get("price", 0)))
    price_label.get_style_context().add_class("product-price")
    price_label.set_alignment(0.5, 0.5)
    content.pack_end(price_label, False, False, 0)

    stock_qty = product.get("stock_qty", 99999)
    if stock_qty == 0:
        card.get_style_context().add_class("out-of-stock")
        stock_label = Gtk.Label(label="⛔ Дууссан")
        stock_label.set_halign(Gtk.Align.CENTER)
        content.pack_start(stock_label, False, False, 0)
    elif stock_qty is not None and stock_qty < 10:
        stock_label = Gtk.Label(label=f"✕ {stock_qty}")
        stock_label.get_style_context().add_class("low-stock-badge")
        stock_label.set_halign(Gtk.Align.CENTER)
        content.pack_start(stock_label, False, False, 0)

    if not barcode_val:
        card.get_style_context().add_class("no-barcode-card")

    outer.pack_start(content, True, True, 0)
    card.add(outer)
    card.product = product
    card.connect("clicked", lambda b: on_click(b.product))
    return card


class CartItem:
    def __init__(self, product_id, barcode, product_name, category, unit_price,
                 quantity=1.0, discount_amount=0, unit="ш"):
        self.product_id = product_id
        self.barcode = barcode
        self.product_name = product_name
        self.category = category
        self.unit_price = unit_price
        self.quantity = quantity
        self.discount_amount = discount_amount
        self.unit = unit

    @property
    def subtotal(self):
        return round(self.quantity * self.unit_price) - self.discount_amount

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "barcode": self.barcode,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "subtotal": self.subtotal,
            "discount_amount": self.discount_amount,
            "unit": self.unit,
        }


def make_cart_item_row(item, on_remove, on_qty_change, cache=None):
    row = Gtk.ListBoxRow()
    row.get_style_context().add_class("cart-row")

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    hbox.set_valign(Gtk.Align.CENTER)

    qty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    qty_box.get_style_context().add_class("qty-control-group")

    dec_btn = Gtk.Button(label="−")
    dec_btn.get_style_context().add_class("qty-btn")
    dec_btn.set_size_request(28, 28)
    dec_btn.connect("clicked", lambda b: on_qty_change(item, -1))
    qty_box.pack_start(dec_btn, False, False, 0)

    qty_label = Gtk.Label(label=str(item.quantity))
    qty_label.get_style_context().add_class("qty-text-label")
    qty_box.pack_start(qty_label, False, False, 0)

    inc_btn = Gtk.Button(label="+")
    inc_btn.get_style_context().add_class("qty-btn")
    inc_btn.set_size_request(28, 28)
    inc_btn.connect("clicked", lambda b: on_qty_change(item, 1))
    qty_box.pack_start(inc_btn, False, False, 0)

    hbox.pack_start(qty_box, False, False, 0)

    icon_box = Gtk.Box()
    icon_box.get_style_context().add_class("cart-item-icon-box")
    icon_box.set_size_request(36, 36)
    icon_label = Gtk.Label(label=get_category_icon(item.category))
    icon_label.set_halign(Gtk.Align.CENTER)
    icon_label.set_valign(Gtk.Align.CENTER)
    icon_box.add(icon_label)

    cat_color = get_category_color(item.category, cache)
    color_str = cat_color.lstrip("#")
    if len(color_str) == 6:
        r, g, b = int(color_str[0:2], 16), int(color_str[2:4], 16), int(color_str[4:6], 16)
        icon_box.override_background_color(
            Gtk.StateFlags.NORMAL,
            Gdk.RGBA(r/255.0, g/255.0, b/255.0, 0.15)
        )
    hbox.pack_start(icon_box, False, False, 0)

    info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    info_box.set_hexpand(True)

    name_label = Gtk.Label(label=item.product_name)
    name_label.get_style_context().add_class("cart-item-title")
    name_label.set_ellipsize(Pango.EllipsizeMode.END)
    name_label.set_halign(Gtk.Align.START)
    name_label.set_xalign(0.0)
    name_label.set_max_width_chars(16)
    info_box.pack_start(name_label, False, False, 0)

    if item.unit and item.unit != "ш":
        unit_label = Gtk.Label(label=f"1 _ = {format_money(item.unit_price)}")
        unit_label.get_style_context().add_class("cart-item-unit")
        unit_label.set_halign(Gtk.Align.START)
        unit_label.set_xalign(0.0)
        info_box.pack_start(unit_label, False, False, 0)

    hbox.pack_start(info_box, True, True, 0)

    subtotal_label = Gtk.Label(label=format_money(item.subtotal))
    subtotal_label.get_style_context().add_class("cart-item-subtotal")
    subtotal_label.set_halign(Gtk.Align.END)
    subtotal_label.set_size_request(80, -1)
    hbox.pack_start(subtotal_label, False, False, 0)

    remove_btn = Gtk.Button(label="✕")
    remove_btn.get_style_context().add_class("cart-remove-btn")
    remove_btn.set_size_request(28, 28)
    remove_btn.connect("clicked", lambda b: on_remove(item))
    hbox.pack_start(remove_btn, False, False, 0)

    row.add(hbox)
    row.item = item
    row.qty_label = qty_label
    row.subtotal_label = subtotal_label
    return row


def make_category_button(category, icon, on_click, is_selected=False):
    btn = Gtk.ToggleButton()
    btn.set_label(f"{icon} {category}")
    btn.set_active(is_selected)
    btn.get_style_context().add_class("category-btn")
    btn.connect("toggled", on_click)
    btn.category = category
    return btn


def make_section_header(title):
    label = Gtk.Label(label=title)
    label.set_halign(Gtk.Align.START)
    label.set_margin_top(12)
    label.set_margin_bottom(8)
    label.set_margin_start(8)
    return label


class POSHeader(Gtk.Box):
    def __init__(self, title="Моност — POS Систем", clock_label=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.get_style_context().add_class("pos-header")

        self._title = Gtk.Label(label=title)
        self._title.get_style_context().add_class("title")
        self._title.set_hexpand(True)
        self._title.set_halign(Gtk.Align.CENTER)
        self.pack_start(self._title, True, True, 0)

        if clock_label:
            self._clock = clock_label
            self._clock.set_margin_end(scaled_px(12))
            self._clock.get_style_context().add_class("clock-label")
            self.pack_end(self._clock, False, False, 0)

"""
posgtk/widgets.py — Styled GTK widget factories matching the web app design.

ProductCard, CartItemRow, category buttons — all with CSS classes
styled by posgtk/theme.py (dark/light CSS).
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Pango

from posgtk.cache import css_class_name
CAT_ICONS = {
    "Хүнс": "🍖", "Ундаа": "🥤", "Амттан": "🍬",
    "Цэвэрлэгээ": "🧹", "Тамхи": "🚬", "Ахуйн": "🏠",
    "Будаа": "🍚", "Гоймон": "🍜", "Давс амтлагч": "🧂",
    "Жимс": "🍎", "Сүүн бүтээгдэхүүн": "🥛",
    "Талх нарийн боов": "🍞", "Тос": "🛢️",
    "Ус ундаа": "🥤", "Чихэр": "🍬", "Өндөг": "🥚",
    "Бусад": "📦",
}


def format_money(amount):
    return f"{amount:,.0f} ₮"


def get_category_icon(category):
    return CAT_ICONS.get(category, "📦")


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
    card = Gtk.Button()
    card.set_relief(Gtk.ReliefStyle.NONE)
    card.get_style_context().add_class("product-card")

    category = product.get("category", "")
    cat_cls = css_class_name(category)
    card.get_style_context().add_class(cat_cls)

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    vbox.set_valign(Gtk.Align.FILL)
    vbox.set_halign(Gtk.Align.FILL)

    icon_label = Gtk.Label(label=get_category_icon(category))
    icon_label.get_style_context().add_class("card-icon")
    icon_label.set_halign(Gtk.Align.CENTER)
    vbox.pack_start(icon_label, False, False, 0)

    name = product.get("name", "")
    name_label = Gtk.Label(label=name)
    name_label.get_style_context().add_class("product-name")
    name_label.set_line_wrap(True)
    name_label.set_max_width_chars(12)
    name_label.set_alignment(0.5, 0.3)
    name_label.set_hexpand(True)
    name_label.set_vexpand(True)
    unit = product.get("unit", "ш")
    barcode_val = product.get("barcode", "")
    name_label.set_tooltip_text(f"{name}\nБаркод: {barcode_val}\nНэгж: {unit}")
    vbox.pack_start(name_label, True, True, 0)

    price_label = Gtk.Label(label=format_money(product.get("price", 0)))
    price_label.get_style_context().add_class("product-price")
    price_label.set_alignment(0.5, 0.7)
    vbox.pack_end(price_label, False, False, 0)

    stock_qty = product.get("stock_qty", 99999)
    if stock_qty == 0:
        card.get_style_context().add_class("out-of-stock")
        stock_label = Gtk.Label(label="⛔ Дууссан")
        stock_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(stock_label, False, False, 0)
    elif stock_qty is not None and stock_qty < 10:
        stock_label = Gtk.Label(label=f"✕ {stock_qty}")
        stock_label.get_style_context().add_class("low-stock-badge")
        stock_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(stock_label, False, False, 0)

    if not barcode_val:
        card.get_style_context().add_class("no-barcode-card")

    card.add(vbox)
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


def make_cart_item_row(item, on_remove, on_qty_change):
    row = Gtk.ListBoxRow()
    row.get_style_context().add_class("cart-row")

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    hbox.set_valign(Gtk.Align.CENTER)

    qty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    qty_box.get_style_context().add_class("qty-control-group")

    dec_btn = Gtk.Button(label="-")
    dec_btn.get_style_context().add_class("qty-btn")
    dec_btn.connect("clicked", lambda b: on_qty_change(item, -1))
    qty_box.pack_start(dec_btn, False, False, 0)

    qty_label = Gtk.Label(label=str(item.quantity))
    qty_label.get_style_context().add_class("qty-text-label")
    qty_box.pack_start(qty_label, False, False, 0)

    inc_btn = Gtk.Button(label="+")
    inc_btn.get_style_context().add_class("qty-btn")
    inc_btn.connect("clicked", lambda b: on_qty_change(item, 1))
    qty_box.pack_start(inc_btn, False, False, 0)

    hbox.pack_start(qty_box, False, False, 0)

    name_label = Gtk.Label(label=item.product_name)
    name_label.get_style_context().add_class("cart-item-title")
    name_label.set_ellipsize(Pango.EllipsizeMode.END)
    name_label.set_halign(Gtk.Align.START)
    name_label.set_hexpand(True)
    hbox.pack_start(name_label, True, True, 0)

    subtotal_label = Gtk.Label(label=format_money(item.subtotal))
    subtotal_label.get_style_context().add_class("cart-item-subtotal")
    subtotal_label.set_halign(Gtk.Align.END)
    hbox.pack_start(subtotal_label, False, False, 0)

    remove_btn = Gtk.Button(label="✕")
    remove_btn.get_style_context().add_class("cart-remove-btn")
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

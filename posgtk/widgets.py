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
from posgtk.scaling import scaled_px, scaled_size_request

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
    btn = Gtk.Button()
    btn.set_relief(Gtk.ReliefStyle.NONE)

    scaled_size_request(btn, 135, 175)
    btn.get_style_context().add_class("product-card")

    name = product.get("name", "")
    barcode_val = product.get("barcode", "")
    image_url = product.get("image_url", "")
    price = product.get("price", 0)
    unit = product.get("unit", "ш")
    product_id = product.get("id")
    stock_qty = product.get("stock_qty", 99999)
    category = product.get("category", "")

    cat_cls = css_class_name(category)
    btn.get_style_context().add_class(cat_cls)

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    vbox.set_hexpand(True)
    vbox.set_vexpand(True)

    icon_label = Gtk.Label(label="")
    icon_label.get_style_context().add_class("card-icon")
    icon_label.set_halign(Gtk.Align.CENTER)

    if image_url:
        try:
            if image_url.startswith(("http://", "https://")) or image_url.startswith("/"):
                icon_label.set_label("🖼")
            else:
                pb = Gdk.Pixbuf.new_from_file_at_size(image_url, 48, 48)
                img = Gtk.Image.new_from_pixbuf(pb)
                vbox.pack_start(img, False, False, 2)
                icon_label = None
        except Exception:
            icon_label.set_label("📦")
    else:
        icon_label.set_label(get_category_icon(category))

    if icon_label:
        vbox.pack_start(icon_label, False, False, 2)

    name_label = Gtk.Label()
    name_label.set_markup(f"<span weight='semibold'>{name}</span>")
    name_label.set_line_wrap(True)
    name_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    name_label.set_lines(2)
    name_label.set_ellipsize(Pango.EllipsizeMode.END)
    name_label.set_justify(Gtk.Justification.CENTER)
    name_label.set_halign(Gtk.Align.CENTER)
    name_label.set_valign(Gtk.Align.CENTER)
    name_label.set_xalign(0.5)
    name_label.set_yalign(0.5)
    name_label.get_style_context().add_class("card-name")
    name_label.set_tooltip_text(f"{name}\nБаркод: {barcode_val}\nНэгж: {unit}")

    vbox.pack_start(name_label, True, True, 0)

    price_label = Gtk.Label(label=format_money(price))
    price_label.get_style_context().add_class("card-price")
    price_label.set_halign(Gtk.Align.CENTER)
    price_label.set_valign(Gtk.Align.END)
    price_label.set_xalign(0.5)
    price_label.set_yalign(1.0)
    vbox.pack_start(price_label, False, False, 2)

    if stock_qty == 0:
        btn.get_style_context().add_class("out-of-stock")
        stock_label = Gtk.Label(label="⛔ Дууссан")
        stock_label.set_halign(Gtk.Align.CENTER)
        stock_label.set_xalign(0.5)
        vbox.pack_start(stock_label, False, False, 0)
    elif stock_qty is not None and stock_qty < 10:
        stock_label = Gtk.Label(label=f"✕ {stock_qty}")
        stock_label.get_style_context().add_class("low-stock-badge")
        stock_label.set_halign(Gtk.Align.CENTER)
        stock_label.set_xalign(0.5)
        vbox.pack_start(stock_label, False, False, 0)

    if not barcode_val:
        btn.get_style_context().add_class("no-barcode-card")

    btn.add(vbox)
    btn.product = product
    btn.connect("clicked", lambda b: on_click(b.product))
    return btn


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
    row.get_style_context().add_class("cart-item")

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(6))
    hbox.set_margin_top(scaled_px(6))
    hbox.set_margin_bottom(scaled_px(6))
    hbox.set_margin_start(scaled_px(6))
    hbox.set_margin_end(scaled_px(6))

    icon_label = Gtk.Label(label=get_category_icon(item.category))
    icon_label.get_style_context().add_class("item-icon")
    icon_label.set_halign(Gtk.Align.CENTER)
    hbox.pack_start(icon_label, False, False, 0)

    qty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=scaled_px(2))
    qty_box.set_valign(Gtk.Align.CENTER)

    dec_btn = Gtk.Button(label="-")
    dec_btn.get_style_context().add_class("qty-btn")
    dec_btn.connect("clicked", lambda b: on_qty_change(item, -1))
    qty_box.pack_start(dec_btn, False, False, 0)

    qty_label = Gtk.Label(label=str(item.quantity))
    qty_label.get_style_context().add_class("item-qty-label")
    qty_label.set_halign(Gtk.Align.CENTER)
    qty_label.set_valign(Gtk.Align.CENTER)
    qty_label.set_xalign(0.5)
    qty_label.set_yalign(0.5)
    scaled_size_request(qty_label, 28, -1)
    qty_box.pack_start(qty_label, False, False, 0)

    inc_btn = Gtk.Button(label="+")
    inc_btn.get_style_context().add_class("qty-btn")
    inc_btn.connect("clicked", lambda b: on_qty_change(item, 1))
    qty_box.pack_start(inc_btn, False, False, 0)

    hbox.pack_start(qty_box, False, False, 0)

    name_label = Gtk.Label(label=item.product_name[:22])
    name_label.get_style_context().add_class("item-name")
    name_label.set_ellipsize(Pango.EllipsizeMode.END)
    name_label.set_halign(Gtk.Align.START)
    name_label.set_xalign(0.0)
    name_label.set_hexpand(True)
    hbox.pack_start(name_label, True, True, 0)

    subtotal_label = Gtk.Label(label=format_money(item.subtotal))
    subtotal_label.get_style_context().add_class("item-subtotal")
    subtotal_label.set_halign(Gtk.Align.END)
    subtotal_label.set_xalign(1.0)
    hbox.pack_start(subtotal_label, False, False, 0)

    remove_btn = Gtk.Button(label="✕")
    remove_btn.set_relief(Gtk.ReliefStyle.NONE)
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

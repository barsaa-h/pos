"""
posgtk/products.py — Product management with card grid layout.

Card grid with search/filter + category chips + add/edit/delete dialogs.
Invalidates cache after any mutation so POS screen stays in sync.
"""

import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GLib

from posgtk.widgets import format_money, get_category_icon

logger = logging.getLogger("pos.gtk.products")


class ProductsScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app
        self._active_category = ""

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_box.get_style_context().add_class("page-header")
        header_box.set_margin_start(16)
        header_box.set_margin_end(16)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(8)

        header = Gtk.Label(label="📦 Бараа")
        header.get_style_context().add_class("page-title")
        header.set_halign(Gtk.Align.START)
        header.set_hexpand(True)
        header_box.pack_start(header, True, True, 0)

        add_btn = Gtk.Button(label="➕ Шинэ бараа")
        add_btn.connect("clicked", self._on_add)
        header_box.pack_end(add_btn, False, False, 0)
        self.pack_start(header_box, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_start(16)
        search_box.set_margin_end(16)
        search_box.set_margin_bottom(8)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("🔍  Бараа хайх (нэр эсвэл баркод)...")
        self.search_entry.connect("search-changed", self._on_search)
        self.search_entry.connect("stop-search", lambda e: self._apply_filters())
        search_box.pack_start(self.search_entry, True, True, 0)

        self._count_label = Gtk.Label(label="Нийт: 0 бараа")
        self._count_label.get_style_context().add_class("text-muted")
        search_box.pack_end(self._count_label, False, False, 0)

        self.pack_start(search_box, False, False, 0)

        self._chip_box = Gtk.FlowBox()
        self._chip_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._chip_box.set_margin_start(16)
        self._chip_box.set_margin_end(16)
        self._chip_box.set_margin_bottom(8)
        self._chip_buttons = []
        self.pack_start(self._chip_box, False, False, 0)

        self._product_grid = Gtk.FlowBox()
        self._product_grid.set_valign(Gtk.Align.START)
        self._product_grid.set_max_children_per_line(4)
        self._product_grid.set_min_children_per_line(2)
        self._product_grid.set_homogeneous(True)
        self._product_grid.set_column_spacing(12)
        self._product_grid.set_row_spacing(12)
        self._product_grid.set_selection_mode(Gtk.SelectionMode.NONE)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.add(self._product_grid)
        self.pack_start(scrolled, True, True, 0)

        self.show_all()
        GLib.idle_add(self._load_data)
        GLib.idle_add(self._load_categories)

    def _load_categories(self):
        try:
            import database as db
            cats = db.get_all_categories()
        except Exception:
            cats = []
        for child in self._chip_box.get_children():
            self._chip_box.remove(child)
        self._chip_buttons.clear()

        all_btn = Gtk.ToggleButton(label="🌐 Бүгд")
        all_btn.get_style_context().add_class("category-chip")
        all_btn.set_active(True)
        all_btn.connect("toggled", self._on_category_chip, "")
        self._chip_box.add(all_btn)
        self._chip_buttons.append(("", all_btn))

        for cat in cats:
            name = cat.get("name", "")
            if not name:
                continue
            icon = get_category_icon(name)
            btn = Gtk.ToggleButton(label=f"{icon} {name}")
            btn.get_style_context().add_class("category-chip")
            btn.connect("toggled", self._on_category_chip, name)
            self._chip_box.add(btn)
            self._chip_buttons.append((name, btn))

        self._chip_box.show_all()

    def _on_category_chip(self, toggle_btn, category):
        if not toggle_btn.get_active():
            return
        self._active_category = category
        for name, btn in self._chip_buttons:
            if btn != toggle_btn:
                btn.set_active(False)
        self._apply_filters()

    def _load_data(self, *args):
        self._apply_filters()

    def _apply_filters(self, *args):
        query = ""
        if hasattr(self, "search_entry") and self.search_entry:
            query = self.search_entry.get_text().strip().lower()
        category = self._active_category

        def fetch_background():
            import database as db
            products = db.get_all_products(active_only=True)
            if query:
                products = [
                    p for p in products
                    if query in p.get("name", "").lower() or query in p.get("barcode", "").lower()
                ]
            if category:
                products = [p for p in products if p.get("category", "") == category]
            return products

        def on_fetch_complete(products):
            for child in self._product_grid.get_children():
                self._product_grid.remove(child)
            for p in products:
                card = self._make_product_card(p)
                self._product_grid.add(card)
            self._product_grid.show_all()
            total = len(products)
            self._count_label.set_label(f"Нийт: {total} бараа")

        def on_fetch_error(error_msg):
            logger.error(f"Background product load failed: {error_msg}")

        if self.app and self.app.workqueue:
            self.app.workqueue.async_op(fetch_background, on_result=on_fetch_complete, on_error=on_fetch_error)
        else:
            try:
                on_fetch_complete(fetch_background())
            except Exception as e:
                on_fetch_error(str(e))

    def _make_product_card(self, product):
        name = product.get("name", "")
        barcode = product.get("barcode", "")
        price = product.get("price", 0)
        category = product.get("category", "")
        unit = product.get("unit", "ш")
        stock = product.get("stock_qty", 0)
        icon = get_category_icon(category)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("product-card-item")
        card.set_size_request(200, -1)

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_row.set_margin_start(12)
        header_row.set_margin_end(12)
        header_row.set_margin_top(10)

        icon_label = Gtk.Label(label=icon)
        icon_label.get_style_context().add_class("product-icon")
        header_row.pack_start(icon_label, False, False, 0)

        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_max_width_chars(20)
        name_label.get_style_context().add_class("product-card-name")
        name_box.pack_start(name_label, False, False, 0)

        if barcode:
            barcode_label = Gtk.Label(label=barcode)
            barcode_label.set_xalign(0)
            barcode_label.get_style_context().add_class("product-card-barcode")
            name_box.pack_start(barcode_label, False, False, 0)

        header_row.pack_start(name_box, True, True, 0)
        card.pack_start(header_row, False, False, 0)

        price_label = Gtk.Label(label=f"{format_money(price)}₮")
        price_label.set_xalign(0)
        price_label.set_margin_start(12)
        price_label.set_margin_top(6)
        price_label.get_style_context().add_class("product-card-price")
        card.pack_start(price_label, False, False, 0)

        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        meta_box.set_margin_start(12)
        meta_box.set_margin_top(4)

        cat_label = Gtk.Label(label=f"{icon} {category}")
        cat_label.get_style_context().add_class("product-card-meta")
        meta_box.pack_start(cat_label, False, False, 0)

        stock_label = Gtk.Label(label=f"Үлдэгдэл: {stock}")
        stock_label.get_style_context().add_class("product-card-meta")
        meta_box.pack_start(stock_label, False, False, 0)

        card.pack_start(meta_box, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        card.pack_start(sep, False, False, 0)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_box.set_margin_start(12)
        action_box.set_margin_end(12)
        action_box.set_margin_top(6)
        action_box.set_margin_bottom(8)

        edit_btn = Gtk.Button(label="✏️ Засах")
        edit_btn.get_style_context().add_class("product-card-edit-btn")
        edit_btn.connect("clicked", lambda b, p=product: self._show_edit_dialog(p))
        action_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label="🗑 Устгах")
        del_btn.get_style_context().add_class("product-card-delete-btn")
        del_btn.connect("clicked", lambda b, p=product: self._delete_product(p))
        action_box.pack_end(del_btn, False, False, 0)

        card.pack_start(action_box, False, False, 0)

        return card

    def _on_search(self, entry):
        self._apply_filters()

    def _on_add(self, btn):
        self._show_edit_dialog(None)

    def _delete_product(self, product):
        name = product.get("name", "")
        confirm = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"'{name}' барааг устгах уу?",
        )
        if confirm.run() == Gtk.ResponseType.YES:
            try:
                import database as db
                db.delete_product(product["id"])
                db.log_audit("product_deleted", "product", entity_id=str(product["id"]), details=name)
                self._invalidate_cache()
            except Exception as e:
                logger.error(f"Delete failed: {e}")
            self._load_data()
        confirm.destroy()

    def _show_edit_dialog(self, product):
        is_new = product is None
        title = "Шинэ бараа" if is_new else f"Засах: {product.get('name', '')}"

        dialog = Gtk.Dialog(
            title=title,
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(400, 380)
        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        dialog_title = Gtk.Label()
        dialog_title.set_markup(f'<span weight="800" size="14000">{title}</span>')
        dialog_title.set_halign(Gtk.Align.START)
        content.add(dialog_title)

        fields = [
            ("Баркод:", "barcode", ""),
            ("Нэр:", "name", ""),
            ("Үнэ (₮):", "price", 0),
            ("Ангилал:", "category", "Бусад"),
            ("Нэгж:", "unit", "ш"),
        ]
        entries = {}
        for label_text, key, default in fields:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl = Gtk.Label(label=label_text, xalign=0)
            box.pack_start(lbl, False, False, 0)

            if key == "category":
                combo = Gtk.ComboBoxText()
                categories = []
                try:
                    import database as db
                    cats = db.get_categories()
                    categories = [c.get("name", "") for c in cats if c.get("name")]
                except Exception:
                    pass
                if not categories:
                    categories = ["Бусад"]
                for cat in categories:
                    combo.append_text(cat)
                if product and product.get("category"):
                    idx = categories.index(product["category"]) if product["category"] in categories else 0
                    combo.set_active(idx)
                else:
                    combo.set_active(0)
                entries[key] = combo
                box.pack_start(combo, True, True, 0)
            elif key == "unit":
                combo = Gtk.ComboBoxText()
                for u in ("ш", "кг", "л", "хайрцаг"):
                    combo.append_text(u)
                if product and product.get("unit"):
                    units = ["ш", "кг", "л", "хайрцаг"]
                    combo.set_active(units.index(product["unit"]) if product["unit"] in units else 0)
                else:
                    combo.set_active(0)
                entries[key] = combo
                box.pack_start(combo, True, True, 0)
            else:
                entry = Gtk.Entry()
                val = str(product.get(key, default)) if product else str(default)
                if key == "price":
                    val = str(product.get(key, 0)) if product else "0"
                entry.set_text(val)
                if key == "price":
                    entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
                entries[key] = entry
                box.pack_start(entry, True, True, 0)

            content.add(box)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)

        if not is_new:
            del_btn = dialog.add_button("Устгах", Gtk.ResponseType.NO)
            del_btn.get_style_context().add_class("destructive-action")

        save_btn = dialog.add_button("Хадгалах" if is_new else "Шинэчлэх", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")

        while True:
            dialog.show_all()
            resp = dialog.run()

            if resp == Gtk.ResponseType.OK:
                barcode = entries["barcode"].get_text().strip()
                name = entries["name"].get_text().strip()
                try:
                    price = int(entries["price"].get_text() or "0")
                except ValueError:
                    price = 0
                category = entries["category"].get_active_text() or "Бусад"
                unit = entries["unit"].get_active_text() or "ш"

                if not name or price <= 0:
                    err = Gtk.MessageDialog(
                        transient_for=dialog, flags=Gtk.DialogFlags.MODAL,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.OK,
                        text="Нэр болон үнэ оруулна уу",
                    )
                    err.run()
                    err.destroy()
                    continue

                import database as db
                try:
                    if is_new:
                        pid, error = db.create_product(
                            barcode=barcode, name=name, price=price,
                            category=category, unit=unit,
                        )
                        if error:
                            raise Exception(error)
                        db.log_audit("product_created", "product", details=f"{name} (barcode={barcode})")
                    else:
                        success, error = db.update_product(
                            product["id"],
                            barcode=barcode, name=name, price=price,
                            category=category, unit=unit,
                        )
                        if error:
                            raise Exception(error)
                        db.log_audit("product_updated", "product", entity_id=str(product["id"]), details=name)

                    self._invalidate_cache()
                    dialog.destroy()
                    GLib.idle_add(self._load_data)
                    return
                except Exception as e:
                    err = Gtk.MessageDialog(
                        transient_for=dialog, flags=Gtk.DialogFlags.MODAL,
                        message_type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        text=f"Алдаа: {e}",
                    )
                    err.run()
                    err.destroy()
                    continue

            elif resp == Gtk.ResponseType.NO and not is_new:
                confirm = Gtk.MessageDialog(
                    transient_for=dialog, flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text=f"'{product.get('name', '')}' устгах уу?",
                )
                if confirm.run() == Gtk.ResponseType.YES:
                    try:
                        import database as db
                        db.delete_product(product["id"])
                        db.log_audit("product_deleted", "product", entity_id=str(product["id"]), details=product.get("name", ""))
                        self._invalidate_cache()
                    except Exception as e:
                        logger.error(f"Delete failed: {e}")
                confirm.destroy()
                dialog.destroy()
                GLib.idle_add(self._load_data)
                return

            dialog.destroy()
            return

    def _invalidate_cache(self):
        if self.app and self.app.cache:
            self.app.cache.invalidate()

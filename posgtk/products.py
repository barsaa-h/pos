"""
posgtk/products.py — Product management with inline CRUD.

TreeView list with search/filter + add/edit/delete dialogs.
Invalidates cache after any mutation so POS screen stays in sync.
"""

import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GLib

from posgtk.widgets import format_money

logger = logging.getLogger("pos.gtk.products")


class ProductsScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        header = Gtk.Label(label="📦 Бараа")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.get_style_context().add_class("action-toolbar")

        add_btn = Gtk.Button(label="➕ Шинэ бараа")
        add_btn.set_tooltip_text("Шинэ бараа үүсгэх")
        add_btn.connect("clicked", self._on_add)
        toolbar.pack_start(add_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="🔄 Сэргээх")
        refresh_btn.set_tooltip_text("Жагсаалт сэргээх")
        refresh_btn.connect("clicked", lambda b: self._load_data())
        toolbar.pack_start(refresh_btn, False, False, 0)

        self.pack_start(toolbar, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        search_box.get_style_context().add_class("search-toolbar")

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("🔍  Бараа хайх (нэр эсвэл баркод)...")
        self.search_entry.connect("search-changed", self._on_search)
        self.search_entry.connect("stop-search", lambda e: self._load_data())
        search_box.pack_start(self.search_entry, True, True, 0)
        self.pack_start(search_box, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.store = Gtk.ListStore(int, str, str, str, str, str, int, object)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_enable_search(False)
        self.tree.get_style_context().add_class("data-table")
        self.tree.get_style_context().add_class("treeview-table")

        cols = [
            ("Д/д", 0, 50),
            ("Баркод", 1, 120),
            ("Нэр", 2, 200),
            ("Үнэ", 3, 100),
            ("Ангилал", 4, 100),
            ("Нэгж", 5, 60),
            ("ID", 6, 0),
        ]
        for i, (title, col_id, width) in enumerate(cols):
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END if col_id > 0 else Pango.EllipsizeMode.NONE)
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            if width == 0:
                col.set_visible(False)
            self.tree.append_column(col)

        action_col = Gtk.TreeViewColumn("Үйлдэл")
        edit_renderer = Gtk.CellRendererText()
        edit_renderer.set_property("foreground", "#2563EB")
        edit_renderer.set_property("text", "✏")
        action_col.pack_start(edit_renderer, False)
        action_col.set_cell_data_func(edit_renderer, self._action_cell_data)
        action_col.set_min_width(80)
        self.tree.append_column(action_col)

        self.tree.connect("row-activated", self._on_row_activated)
        scrolled.add(self.tree)
        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)

        self.show_all()
        GLib.idle_add(self._load_data)

    def _action_cell_data(self, column, cell, model, iter, data):
        cell.set_property("text", "✏ Засах")

    def _load_data(self, *args):
        search_query = getattr(self, "search_entry", None)
        query_text = search_query.get_text().strip().lower() if search_query else ""

        def fetch_background():
            import database as db
            products = db.get_all_products(active_only=True)
            if query_text:
                products = [
                    p for p in products
                    if query_text in p.get("name", "").lower() or query_text in p.get("barcode", "")
                ]
            return products

        def on_fetch_complete(products):
            self.store.clear()
            for i, p in enumerate(products, 1):
                self.store.append([
                    i,
                    p.get("barcode", ""),
                    p.get("name", ""),
                    format_money(p.get("price", 0)),
                    p.get("category", ""),
                    p.get("unit", ""),
                    p.get("id", 0),
                    p,
                ])

        def on_fetch_error(error_msg):
            logger.error(f"Background product load failed: {error_msg}")

        if self.app and self.app.workqueue:
            self.app.workqueue.async_op(fetch_background, on_result=on_fetch_complete, on_error=on_fetch_error)
        else:
            try:
                on_fetch_complete(fetch_background())
            except Exception as e:
                on_fetch_error(str(e))

    def _on_search(self, entry):
        query = entry.get_text().strip()
        if not query:
            self._load_data()
            return
        q = query.lower()
        self.store.clear()

        def fetch_background():
            import database as db
            return db.search_products(query, limit=50)

        def on_fetch_complete(products):
            self.store.clear()
            for i, p in enumerate(products, 1):
                self.store.append([
                    i,
                    p.get("barcode", ""),
                    p.get("name", ""),
                    format_money(p.get("price", 0)),
                    p.get("category", ""),
                    p.get("unit", ""),
                    p.get("id", 0),
                    p,
                ])

        def on_fetch_error(error_msg):
            logger.error(f"Background search failed: {error_msg}")

        if self.app and self.app.workqueue:
            self.app.workqueue.async_op(fetch_background, on_result=on_fetch_complete, on_error=on_fetch_error)
        else:
            try:
                on_fetch_complete(fetch_background())
            except Exception as e:
                on_fetch_error(str(e))

    def _on_row_activated(self, tree, path, column):
        it = self.store.get_iter(path)
        product = self.store.get_value(it, 7)
        self._show_edit_dialog(product)

    def _on_add(self, btn):
        self._show_edit_dialog(None)

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
        content.get_style_context().add_class("form-card")
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
                    combo.set_active(categories.index(product["category"]) if product["category"] in categories else 0)
                else:
                    combo.set_active(0)
                entries[key] = combo
                box.pack_start(combo, True, True, 0)
            elif key == "unit":
                combo = Gtk.ComboBoxText()
                for u in ("ш", "кг", "л", "хайрцаг"):
                    combo.append_text(u)
                if product and product.get("unit"):
                    combo.set_active(max(0, combo.get_model().index_of(product["unit"])))
                else:
                    combo.set_active(0)
                entries[key] = combo
                box.pack_start(combo, True, True, 0)
            else:
                entry = Gtk.Entry()
                val = str(product.get(key, default)) if product else str(default)
                if key in ("price",):
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

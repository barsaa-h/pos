"""
posgtk/suppliers.py — Supplier management.
"""
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

logger = logging.getLogger("pos.gtk.suppliers")


class SuppliersScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        toolbar = Gtk.Toolbar()
        add_btn = Gtk.ToolButton.new(
            Gtk.Image.new_from_icon_name("list-add", Gtk.IconSize.SMALL_TOOLBAR), "Шинэ"
        )
        add_btn.connect("clicked", self._on_add)
        toolbar.insert(add_btn, -1)
        self.pack_start(toolbar, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_margin_start(8)

        scrolled.set_margin_end(8)

        scrolled.set_margin_top(8)

        scrolled.set_margin_bottom(8)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.store = Gtk.ListStore(str, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.get_style_context().add_class("treeview-table")

        cols = [
            ("Нэр", 0, 150), ("Холбоо барих", 1, 120),
            ("Утас", 2, 120), ("Имэйл", 3, 150),
            ("Хаяг", 4, 200),
        ]
        for title, col_id, width in cols:
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.tree.append_column(col)

        self.tree.connect("row-activated", self._on_row_activated)
        scrolled.add(self.tree)
        self.pack_start(scrolled, True, True, 0)

        self.show_all()
        GLib.idle_add(self._load_data)

    def _load_data(self, *args):
        self.store.clear()
        try:
            import database as db
            suppliers = db.get_suppliers(include_inactive=True)
        except Exception:
            suppliers = []
        for s in suppliers:
            self.store.append([
                s.get("name", ""),
                s.get("contact_person", ""),
                s.get("phone", ""),
                s.get("email", ""),
                s.get("address", ""),
                s.get("id", 0),
            ])

    def _on_row_activated(self, tree, path, col):
        it = self.store.get_iter(path)
        sid = self.store.get_value(it, 5)
        self._show_edit_dialog(sid)

    def _on_add(self, btn):
        self._show_edit_dialog(None)

    def _show_edit_dialog(self, sid):
        try:
            import database as db
            supplier = db.get_supplier(sid) if sid else None
        except Exception:
            supplier = None
        is_new = not supplier

        dialog = Gtk.Dialog(
            title="Шинэ ханган нийлүүлэгч" if is_new else "Засах",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(400, 300)
        content = dialog.get_content_area()
        content.set_spacing(6)
        content.set_margin_start(16)

        content.set_margin_end(16)

        content.set_margin_top(16)

        content.set_margin_bottom(16)

        fields = [
            ("Нэр:", "name", ""),
            ("Холбоо барих хүн:", "contact_person", ""),
            ("Утас:", "phone", ""),
            ("Имэйл:", "email", ""),
            ("Хаяг:", "address", ""),
            ("Тэмдэглэл:", "notes", ""),
        ]
        entries = {}
        for label_text, key, default in fields:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            lbl = Gtk.Label(label=label_text, xalign=1)
            lbl.set_width_chars(15)
            hbox.pack_start(lbl, False, False, 0)
            entry = Gtk.Entry()
            entry.set_text(str(supplier.get(key, default)) if supplier else default)
            entries[key] = entry
            hbox.pack_start(entry, True, True, 0)
            content.add(hbox)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        if not is_new:
            dialog.add_button("Устгах", Gtk.ResponseType.NO)
        dialog.add_button("Хадгалах", Gtk.ResponseType.OK)
        dialog.show_all()

        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            values = {k: e.get_text().strip() for k, e in entries.items()}
            try:
                import database as db
                if is_new:
                    db.create_supplier(**values)
                else:
                    db.update_supplier(sid, **values)
            except Exception as e:
                logger.error(f"Supplier save failed: {e}")
            self._load_data()
        elif resp == Gtk.ResponseType.NO and not is_new:
            try:
                import database as db
                db.delete_supplier(sid)
            except Exception as e:
                logger.error(f"Delete supplier failed: {e}")
            self._load_data()
        dialog.destroy()

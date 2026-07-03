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

        header = Gtk.Label(label="🚛 Ханган нийлүүлэгч")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.get_style_context().add_class("action-toolbar")
        add_btn = Gtk.Button(label="➕ Шинэ")
        add_btn.connect("clicked", self._on_add)
        toolbar.pack_start(add_btn, False, False, 0)
        self.pack_start(toolbar, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.store = Gtk.ListStore(str, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.get_style_context().add_class("data-table")
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
        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)

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

        title_text = "Шинэ ханган нийлүүлэгч" if is_new else "Засах"
        dialog = Gtk.Dialog(
            title=title_text,
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.set_default_size(400, 300)
        content = dialog.get_content_area()
        content.get_style_context().add_class("form-card")
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        dlg_title = Gtk.Label()
        dlg_title.set_markup(f'<span weight="800" size="14000">{title_text}</span>')
        dlg_title.set_halign(Gtk.Align.START)
        content.add(dlg_title)

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
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl = Gtk.Label(label=label_text, xalign=0)
            vbox.pack_start(lbl, False, False, 0)
            entry = Gtk.Entry()
            entry.set_text(str(supplier.get(key, default)) if supplier else default)
            entries[key] = entry
            vbox.pack_start(entry, True, True, 0)
            content.add(vbox)

        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        if not is_new:
            del_btn = dialog.add_button("Устгах", Gtk.ResponseType.NO)
            del_btn.get_style_context().add_class("destructive-action")
        save_btn = dialog.add_button("Хадгалах", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")
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

"""
posgtk/suppliers.py — Supplier management with card grid layout.
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

        self._grid = Gtk.FlowBox()
        self._grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self._grid.set_column_spacing(16)
        self._grid.set_row_spacing(16)
        self._grid.set_margin_start(16)
        self._grid.set_margin_end(16)
        self._grid.set_margin_top(16)
        self._grid.set_margin_bottom(16)

        scrolled.add(self._grid)
        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)

        self.show_all()
        GLib.idle_add(self._load_data)

    def _load_data(self, *args):
        for child in self._grid.get_children():
            self._grid.remove(child)

        try:
            import database as db
            suppliers = db.get_suppliers(include_inactive=True)
        except Exception:
            suppliers = []

        if not suppliers:
            empty = Gtk.Label(label="Нийлүүлэгч бүртгэгдээгүй байна.")
            empty.get_style_context().add_class("text-muted")
            empty.set_margin_top(48)
            self._grid.add(empty)
            self._grid.show_all()
            return

        for s in suppliers:
            card = self._make_card(s)
            self._grid.add(card)

        self._grid.show_all()

    def _make_card(self, s):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("product-card-item")
        card.set_size_request(280, -1)

        if not s.get("is_active", True):
            card.set_opacity(0.5)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon_lbl = Gtk.Label(label="🚛")
        icon_lbl.get_style_context().add_class("product-icon")
        header_box.pack_start(icon_lbl, False, False, 0)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)
        name_lbl = Gtk.Label(label=s.get("name", ""), xalign=0)
        name_lbl.get_style_context().add_class("product-card-name")
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.set_max_width_chars(25)
        info_box.pack_start(name_lbl, False, False, 0)

        contact = s.get("contact_person", "")
        if contact:
            contact_lbl = Gtk.Label(label=f"👤 {contact}", xalign=0)
            contact_lbl.get_style_context().add_class("product-card-barcode")
            info_box.pack_start(contact_lbl, False, False, 0)

        header_box.pack_start(info_box, True, True, 0)
        card.pack_start(header_box, False, False, 0)

        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        phone = s.get("phone", "")
        if phone:
            phone_lbl = Gtk.Label(label=f"📞 {phone}")
            phone_lbl.get_style_context().add_class("text-muted")
            meta_box.pack_start(phone_lbl, False, False, 0)
        email = s.get("email", "")
        if email:
            email_lbl = Gtk.Label(label=f"✉️ {email}")
            email_lbl.get_style_context().add_class("text-muted")
            meta_box.pack_start(email_lbl, False, False, 0)
        if not s.get("is_active", True):
            badge = Gtk.Label(label="Идэвхгүй")
            badge.get_style_context().add_class("status-badge")
            badge.get_style_context().add_class("status-failed")
            meta_box.pack_start(badge, False, False, 0)
        if phone or email or not s.get("is_active", True):
            card.pack_start(meta_box, False, False, 0)

        address = s.get("address", "")
        if address:
            addr_lbl = Gtk.Label(label=f"📍 {address}", xalign=0)
            addr_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            addr_lbl.set_max_width_chars(35)
            card.pack_start(addr_lbl, False, False, 0)

        notes = s.get("notes", "")
        if notes:
            notes_lbl = Gtk.Label(label=f"📝 {notes}", xalign=0)
            notes_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            notes_lbl.set_max_width_chars(35)
            notes_lbl.get_style_context().add_class("text-muted")
            card.pack_start(notes_lbl, False, False, 0)

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions_box.get_style_context().add_class("product-card-actions")

        edit_btn = Gtk.Button(label="✏️ Засах")
        edit_btn.get_style_context().add_class("category-btn")
        sid = s.get("id")
        edit_btn.connect("clicked", lambda b: self._show_edit_dialog(sid))
        actions_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label="🗑 Устгах")
        del_btn.get_style_context().add_class("destructive-action")
        del_btn.connect("clicked", lambda b: self._do_delete(sid))
        actions_box.pack_start(del_btn, False, False, 0)

        card.pack_start(actions_box, False, False, 0)
        return card

    def _on_add(self, btn):
        self._show_edit_dialog(None)

    def _do_delete(self, sid):
        confirm = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Устгах уу?",
        )
        if confirm.run() == Gtk.ResponseType.YES:
            try:
                import database as db
                db.delete_supplier(sid)
            except Exception as e:
                logger.error(f"Delete supplier failed: {e}")
                self._show_error(f"Устгахад алдаа: {e}")
            self._load_data()
        confirm.destroy()

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
                self._show_error(f"Хадгалахад алдаа: {e}")
            self._load_data()
        elif resp == Gtk.ResponseType.NO and not is_new:
            try:
                import database as db
                db.delete_supplier(sid)
            except Exception as e:
                logger.error(f"Delete supplier failed: {e}")
                self._show_error(f"Устгахад алдаа: {e}")
            self._load_data()
        dialog.destroy()

    def _show_error(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        dialog.run()
        dialog.destroy()

    def _show_toast(self, msg):
        if hasattr(self.app, 'pos_screen') and self.app.pos_screen:
            self.app.pos_screen._show_toast(msg, "success")

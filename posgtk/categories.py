"""
posgtk/categories.py — Category management with icon/color editing.
"""
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

logger = logging.getLogger("pos.gtk.categories")

CAT_ICONS = {
    "Хүнс": "🍖", "Ундаа": "🥤", "Амттан": "🍬", "Цэвэрлэгээ": "🧹",
    "Тамхи": "🚬", "Ахуйн": "🏠", "Бусад": "📦",
}
CAT_COLORS = {
    "Хүнс": "#EF4444", "Ундаа": "#3B82F6", "Амттан": "#F59E0B",
    "Цэвэрлэгээ": "#10B981", "Тамхи": "#6B7280", "Ахуйн": "#8B5CF6",
    "Бусад": "#9CA3AF",
}


class CategoriesScreen(Gtk.Box):
    def __init__(self, app=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.app = app

        header = Gtk.Label(label="🏷 Ангилал")
        header.get_style_context().add_class("page-header")
        header.set_halign(Gtk.Align.START)
        self.pack_start(header, False, False, 0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.get_style_context().add_class("action-toolbar")
        add_btn = Gtk.Button(label="➕ Шинэ ангилал")
        add_btn.connect("clicked", self._on_add)
        toolbar.pack_start(add_btn, False, False, 0)
        self.pack_start(toolbar, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.get_style_context().add_class("content-panel")
        panel.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.listbox)
        panel.pack_start(scrolled, True, True, 0)
        self.pack_start(panel, True, True, 0)

        self.show_all()
        GLib.idle_add(self._load_data)

    def _load_data(self, *args):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        try:
            import database as db
            categories = db.get_all_categories()
        except Exception:
            categories = []

        for cat in categories:
            row = self._make_row(cat)
            row.show_all()
            self.listbox.add(row)

        if not categories:
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label="Ангилал байхгүй", margin=20))
            self.listbox.add(row)

        self.listbox.show_all()

    def _make_row(self, cat):
        name = cat.get("name", "")
        icon = cat.get("icon", "📦")
        color = cat.get("color", "#6B7280")
        cat_id = cat.get("id")

        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("data-row")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.set_margin_start(8)
        hbox.set_margin_end(8)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)

        color_indicator = Gtk.Box()
        color_indicator.get_style_context().add_class("category-color-indicator")
        color_str = color.lstrip("#")
        if len(color_str) == 6:
            r, g, b = int(color_str[0:2], 16), int(color_str[2:4], 16), int(color_str[4:6], 16)
            color_indicator.override_background_color(
                Gtk.StateFlags.NORMAL,
                Gdk.RGBA(r/255.0, g/255.0, b/255.0, 1.0)
            )
        hbox.pack_start(color_indicator, False, False, 0)

        icon_btn = Gtk.Button(label=icon)
        icon_btn.set_relief(Gtk.ReliefStyle.NONE)
        icon_btn.set_size_request(40, 40)
        icon_btn.connect("clicked", lambda b: self._pick_icon(cat, icon_btn))
        hbox.pack_start(icon_btn, False, False, 0)

        name_label = Gtk.Label(label=name, xalign=0)
        name_label.set_hexpand(True)
        hbox.pack_start(name_label, True, True, 0)

        color_btn = Gtk.ColorButton()
        try:
            gdk_color = Gdk.RGBA()
            gdk_color.parse(color)
            color_btn.set_rgba(gdk_color)
        except Exception:
            pass
        color_btn.set_size_request(32, 32)
        color_btn.connect("color-set", lambda b: self._update_color(cat_id, b.get_rgba()))
        hbox.pack_start(color_btn, False, False, 0)

        edit_btn = Gtk.Button(label="✏️")
        edit_btn.set_relief(Gtk.ReliefStyle.NONE)
        edit_btn.connect("clicked", lambda b, c=cat: self._edit_name(c))
        hbox.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label="🗑️")
        del_btn.set_relief(Gtk.ReliefStyle.NONE)
        del_btn.connect("clicked", lambda b, c=cat: self._delete(c))
        hbox.pack_start(del_btn, False, False, 0)

        row.add(hbox)
        return row

    def _on_add(self, btn):
        dialog = Gtk.Dialog(
            title="Шинэ ангилал",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        content = dialog.get_content_area()
        content.get_style_context().add_class("form-card")
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label()
        title.set_markup('<span weight="800" size="14000">Шинэ ангилал</span>')
        title.set_halign(Gtk.Align.START)
        content.add(title)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Ангиллын нэр")
        entry.set_activates_default(True)
        content.add(entry)
        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        save_btn = dialog.add_button("Үүсгэх", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                try:
                    import database as db
                    icon = CAT_ICONS.get(name, "📦")
                    color = CAT_COLORS.get(name, "#6B7280")
                    db.create_category(name, icon=icon, color=color)
                    if self.app and self.app.cache:
                        self.app.cache.invalidate()
                except Exception as e:
                    logger.error(f"Create category failed: {e}")
                self._load_data()
        dialog.destroy()

    def _edit_name(self, cat):
        dialog = Gtk.Dialog(
            title="Ангилал засах",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        content = dialog.get_content_area()
        content.get_style_context().add_class("form-card")
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label()
        title.set_markup(f'<span weight="800" size="14000">{cat.get("name", "")}</span>')
        title.set_halign(Gtk.Align.START)
        content.add(title)

        entry = Gtk.Entry()
        entry.set_text(cat.get("name", ""))
        entry.set_activates_default(True)
        content.add(entry)
        dialog.add_button("Цуцлах", Gtk.ResponseType.CANCEL)
        save_btn = dialog.add_button("Хадгалах", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                try:
                    import database as db
                    db.update_category(cat["id"], name=name)
                    if self.app and self.app.cache:
                        self.app.cache.invalidate()
                except Exception as e:
                    logger.error(f"Update category failed: {e}")
                self._load_data()
        dialog.destroy()

    def _update_color(self, cat_id, rgba):
        color = "#{:02X}{:02X}{:02X}".format(
            int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255)
        )
        try:
            import database as db
            db.update_category(cat_id, color=color)
            if self.app and self.app.cache:
                self.app.cache.invalidate()
        except Exception as e:
            logger.error(f"Update category color failed: {e}")

    def _pick_icon(self, cat, button):
        icons = "🍖🥤🍬🧹🚬🏠📦💊📚👟🎮🎁🍔🍕🍩"
        popover = Gtk.Popover()
        grid = Gtk.FlowBox()
        grid.set_max_children_per_line(6)
        grid.set_homogeneous(True)
        for ch in icons:
            btn = Gtk.Button(label=ch)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_size_request(36, 36)
            btn.connect("clicked", lambda b, i=ch: self._update_icon(cat["id"], i, popover, button))
            grid.add(btn)
        popover.add(grid)
        popover.set_relative_to(button)
        popover.show_all()
        popover.popup()

    def _update_icon(self, cat_id, icon, popover, icon_btn):
        try:
            import database as db
            db.update_category(cat_id, icon=icon)
            if self.app and self.app.cache:
                self.app.cache.invalidate()
        except Exception as e:
            logger.error(f"Update icon failed: {e}")
        popover.popdown()
        icon_btn.set_label(icon)

    def _delete(self, cat):
        name = cat.get("name", "")
        confirm = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"'{name}' ангилал устгах уу?\nБүх бараа 'Бусад'-д шилжинэ.",
        )
        if confirm.run() == Gtk.ResponseType.YES:
            try:
                import database as db
                db.delete_category(cat["id"], reassign_to="Бусад")
                if self.app and self.app.cache:
                    self.app.cache.invalidate()
            except Exception as e:
                logger.error(f"Delete category failed: {e}")
            self._load_data()
        confirm.destroy()

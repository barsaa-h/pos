import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class SystemTray:
    def __init__(self, app, window):
        self.app = app
        self.window = window
        self._icon = Gtk.StatusIcon()
        self._icon.set_from_icon_name("weather-clear")
        self._icon.set_title("POS Систем")
        self._icon.set_tooltip_text("POS Систем — Моност")
        self._icon.connect("activate", self._on_activate)
        self._icon.connect("popup-menu", self._on_popup_menu)

    def _on_activate(self, icon):
        if self.window.get_visible():
            self.window.hide()
        else:
            self.window.show()
            self.window.present()

    def _on_popup_menu(self, icon, button, activate_time):
        menu = Gtk.Menu()
        item_toggle = Gtk.MenuItem(label="Нээх / Хаах")
        item_toggle.connect("activate", lambda w: self._on_activate(icon))
        menu.append(item_toggle)
        menu.append(Gtk.SeparatorMenuItem())
        item_quit = Gtk.MenuItem(label="Гарах")
        item_quit.connect("activate", lambda w: self.app._on_quit(None))
        menu.append(item_quit)
        menu.show_all()
        menu.popup(None, None, None, None, button, activate_time)

    def destroy(self):
        if self._icon:
            self._icon.set_visible(False)
            self._icon = None

"""
posgtk/theme.py — GTK CSS theming matching the production web app visual design.

Loads CSS from external dark.css / light.css files in this directory.
Caches scaled CSS to avoid re-parsing regex on every apply.
Supports low-perf mode (disables transitions) and category accent CSS injection.
"""

import os
import re
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

logger = logging.getLogger("pos.gtk.theme")

_THEME_DIR = os.path.dirname(os.path.abspath(__file__))

_CACHED_CSS = {}       # (mode, scale, low_perf) -> bytes
_RAW_CSS = {}           # mode -> str (loaded from file)


def _load_css_file(theme_name):
    """Load raw CSS from file, with caching."""
    if theme_name not in _RAW_CSS:
        path = os.path.join(_THEME_DIR, f"{theme_name}.css")
        if not os.path.isfile(path):
            logger.warning(f"Theme file not found: {path}")
            _RAW_CSS[theme_name] = ""
        else:
            with open(path, "r", encoding="utf-8") as f:
                _RAW_CSS[theme_name] = f.read()
            logger.debug(f"Loaded theme CSS: {path} ({len(_RAW_CSS[theme_name])} bytes)")
    return _RAW_CSS[theme_name]


def scale_css(css, factor):
    """Multiply all NNpx values in CSS by factor. Clamps border-like values >=1px."""
    if factor == 1.0:
        return css

    def _replace(m):
        val = int(m.group(0)[:-2])
        scaled = round(val * factor)
        if scaled < 1:
            scaled = 1
        return f"{scaled}px"
    return re.sub(r'\d+px', _replace, css)


def _build_css(mode, scale, low_perf):
    """Build final CSS bytes for a (mode, scale, low_perf) combination."""
    key = (mode, scale, low_perf)
    if key in _CACHED_CSS:
        return _CACHED_CSS[key]

    raw = _load_css_file(mode)
    if not raw:
        raw = _load_css_file("dark")  # fallback

    if scale != 1.0:
        raw = scale_css(raw, scale)

    if low_perf:
        raw += "\n* { transition: none !important; animation: none !important; }"

    css_bytes = raw.encode("utf-8")
    _CACHED_CSS[key] = css_bytes
    return css_bytes


def clear_cache():
    """Clear the scaled CSS cache (e.g. after DPI change)."""
    _CACHED_CSS.clear()


class Theme:
    def __init__(self):
        self._current_mode = "dark"
        self._current_provider = None
        self._extra_providers = []

    def apply(self, mode="dark", scale=1.0, low_perf=False):
        screen = Gdk.Screen.get_default()
        if not screen:
            return

        if self._current_provider:
            Gtk.StyleContext.remove_provider_for_screen(
                screen, self._current_provider
            )
        for p in self._extra_providers:
            Gtk.StyleContext.remove_provider_for_screen(screen, p)
        self._extra_providers.clear()

        css_bytes = _build_css(mode, scale, low_perf)
        provider = Gtk.CssProvider()
        provider.load_from_data(css_bytes)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._current_provider = provider
        self._current_mode = mode
        logger.info(f"Theme applied: {mode}, scale={scale}, low_perf={low_perf}")

    def reload(self, scale=1.0, low_perf=False):
        """Force reload CSS from file (useful during development)."""
        _RAW_CSS.clear()
        clear_cache()
        self.apply(self._current_mode, scale=scale, low_perf=low_perf)

    def append_css(self, css_string):
        """Add extra CSS rules on top of the current theme."""
        screen = Gdk.Screen.get_default()
        if not screen or not css_string.strip():
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(css_string.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._extra_providers.append(provider)

    def get_mode(self):
        return self._current_mode

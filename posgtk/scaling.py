"""
posgtk/scaling.py — Global DPI-aware scaling for GTK3.

Calculates a global CSS scale factor based on screen physical DPI and monitor size.
Designed for POS terminals with varying screen sizes (10" tablet to 24" desktop).
"""

import os
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

_SCALE = 1.0
_INITIALIZED = False


def init_scaling(display=None):
    """Initialize global scaling based on primary monitor. Call once at startup."""
    global _SCALE, _INITIALIZED
    if _INITIALIZED:
        return _SCALE
    _INITIALIZED = True

    # Check for environment override first
    env_scale = os.environ.get("POS_GTK_SCALE")
    if env_scale:
        try:
            _SCALE = max(0.5, min(3.0, float(env_scale)))
            return _SCALE
        except ValueError:
            pass

    if display is None:
        display = Gdk.Display.get_default()
    if not display:
        _SCALE = 1.0
        return _SCALE

    monitor = display.get_primary_monitor() or display.get_monitor(0)
    if not monitor:
        _SCALE = 1.0
        return _SCALE

    geo = monitor.get_geometry()
    scale_factor = monitor.get_scale_factor() if hasattr(monitor, 'get_scale_factor') else 1

    phys_width = geo.width * scale_factor
    phys_height = geo.height * scale_factor

    reference_height = 768
    reference_width = 1366

    scale_h = phys_height / reference_height
    scale_w = phys_width / reference_width

    _SCALE = max(0.6, min(2.0, min(scale_h, scale_w)))
    _SCALE = round(_SCALE * 10) / 10

    return _SCALE


def get_scale():
    """Get the current global scale factor."""
    global _SCALE, _INITIALIZED
    if not _INITIALIZED:
        init_scaling()
    return _SCALE


def scaled_px(px):
    """Scale a pixel value by global factor."""
    return max(1, int(round(px * get_scale())))


def scaled_size(width, height):
    """Scale a (width, height) tuple."""
    return (scaled_px(width), scaled_px(height))


def scaled_size_request(widget, width, height):
    """Set size request with scaling applied."""
    if width >= 0 and height >= 0:
        widget.set_size_request(scaled_px(width), scaled_px(height))
    elif width >= 0:
        widget.set_size_request(scaled_px(width), -1)
    elif height >= 0:
        widget.set_size_request(-1, scaled_px(height))


def reset():
    """Reset scaling (for testing)."""
    global _SCALE, _INITIALIZED
    _SCALE = 1.0
    _INITIALIZED = False
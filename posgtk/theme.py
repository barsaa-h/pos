"""
posgtk/theme.py -- GTK CSS theming matching the web app visual design.

Dark (modern, emerald-green) and light (high-contrast blue) themes.
Supports appending category color CSS for product card accents.
"""

import re
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

logger = logging.getLogger("pos.gtk.theme")


def _scale_css(css, factor):
    """Multiply all NNpx values in CSS by factor. Clamps border-like values >=1px."""
    def _replace(m):
        val = int(m.group(0)[:-2])
        scaled = round(val * factor)
        if scaled < 1:
            scaled = 1
        return f"{scaled}px"
    return re.sub(r'\d+px', _replace, css)

DARK_CSS = """\
/* MODERN POS THEME — Emerald Green Primary, White Surface (GTK3-compatible) */

* {
    font-family: DejaVu Sans, Liberation Sans, Ubuntu, Sans, sans-serif;
}

/* SIDEBAR */
.sidebar-list {
    background: #1E293B;
    color: #E2E8F0;
    min-width: 170px;
}
.sidebar-row {
    padding: 10px 16px;
    margin: 2px 6px;
    border-radius: 10px;
    color: #CBD5E1;
    font-size: 14px;
    font-weight: 600;
}
.sidebar-row:selected {
    background: #059669;
    color: #FFFFFF;
}

/* HEADER BAR */
.pos-header {
    background: #FFFFFF;
    border-bottom: 2px solid #E2E8F0;
    min-height: 52px;
    padding: 4px 12px;
}
.pos-header label {
    font-size: 16px;
    font-weight: 800;
    color: #0F172A;
}
.clock-label {
    font-size: 12px;
    font-weight: 600;
    color: #64748B;
}

/* BACKGROUND */
.screen-box {
    background: #F8FAFC;
}
.pos-left {
    background: #F8FAFC;
}

/* BARCODE INPUT */
.barcode-entry {
    padding: 14px 20px;
    border: 2px solid #E2E8F0;
    border-radius: 16px;
    font-size: 16px;
    font-family: DejaVu Sans Mono, Liberation Mono, monospace;
    background: #FFFFFF;
    color: #0F172A;
    min-height: 52px;
}
.barcode-entry:focus {
    border-color: #059669;
}
/* SEARCH */
.search-entry {
    padding: 10px 14px;
    border: 2px solid #E2E8F0;
    border-radius: 12px;
    font-size: 14px;
    background: #FFFFFF;
}
.search-entry:focus {
    border-color: #059669;
}

/* CATEGORY BUTTONS */
.category-btn {
    padding: 8px 16px;
    border: 2px solid #E2E8F0;
    border-radius: 20px;
    background: #FFFFFF;
    color: #64748B;
    font-weight: 600;
    font-size: 12px;
    min-height: 38px;
}
.category-btn:hover {
    border-color: #059669;
    color: #047857;
}
.category-btn:checked, .category-btn:active {
    background: #059669;
    color: #FFFFFF;
    border-color: #059669;
}

/* PRODUCT CARD */
.product-card {
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    background: #FFFFFF;
    min-width: 130px;
    min-height: 160px;
    padding: 16px 12px;
}
.product-card:hover {
    border-color: #059669;
}
.product-card:active {
    opacity: 0.85;
}
.product-card .card-icon {
    font-size: 28px;
    margin-bottom: 8px;
}
.product-card .card-name {
    font-weight: 700;
    font-size: 12px;
    color: #0F172A;
    padding: 0 4px;
    min-height: 2.6em;
}
.product-card .card-price {
    font-weight: 800;
    font-size: 18px;
    color: #059669;
    padding-bottom: 4px;
}
.out-of-stock {
    opacity: 0.45;
}
.no-barcode-card {
    border-color: #EF4444;
    border-width: 2px;
}
.no-barcode-card:hover {
    border-color: #EF4444;
}
.grid-selected {
    border-color: #059669;
    border-width: 2px;
}
.low-stock-badge {
    font-size: 10px;
    font-weight: 700;
    color: #D97706;
    background: #FEF3C7;
    border-radius: 10px;
    padding: 1px 8px;
    margin-top: 2px;
}

/* CART PANEL */
.cart-panel {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    min-width: 300px;
}
.cart-header-bar {
    padding: 14px 16px;
    border-bottom: 1px solid #F1F5F9;
    background: #FFFFFF;
    border-radius: 16px 16px 0 0;
}
.cart-header-bar .cart-title {
    font-weight: 800;
    font-size: 16px;
    color: #0F172A;
}
.cart-count-badge {
    background: #059669;
    color: #FFFFFF;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    min-width: 24px;
    min-height: 24px;
}

/* CART ITEMS */
.cart-scroll {
    background: #FFFFFF;
}
.cart-item {
    padding: 8px 12px;
    border-bottom: 1px solid #F1F5F9;
}
.cart-item:last-child {
    border-bottom: none;
}
.cart-item .item-icon {
    font-size: 24px;
    min-width: 36px;
}
.cart-item .item-qty-label {
    font-weight: 700;
    font-size: 14px;
    color: #64748B;
    min-width: 36px;
}
.cart-item .item-name {
    font-weight: 600;
    font-size: 12px;
    color: #0F172A;
}
.cart-item .item-subtotal {
    font-weight: 700;
    font-size: 14px;
    color: #059669;
    min-width: 80px;
}
.qty-btn {
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    background: #FFFFFF;
    color: #64748B;
    font-weight: 700;
    font-size: 16px;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
}
.qty-btn:hover {
    border-color: #059669;
    color: #059669;
    background: #F0FDF4;
}
.qty-btn:active {
    background: #DCFCE7;
}
.cart-empty-state {
    color: #94A3B8;
    font-size: 14px;
    padding: 0 20px;
}
.cart-empty-icon {
    font-size: 40px;
    opacity: 0.5;
}

/* CART TOTAL */
.cart-total-row {
    padding: 14px 18px;
    border-top: 2px dashed #E2E8F0;
    background: #F8FAFC;
}
.cart-total-label {
    font-weight: 800;
    font-size: 22px;
    color: #047857;
}

/* CHECKOUT BUTTONS */
.checkout-pay-btn {
    background: #059669;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 800;
    font-size: 17px;
    min-height: 54px;
    border: none;
}
.checkout-pay-btn:hover {
    background: #047857;
}
.checkout-pay-btn:disabled {
    opacity: 0.35;
}
.hold-btn {
    background: #F1F5F9;
    color: #94A3B8;
    border: 2px solid #E2E8F0;
    border-radius: 12px;
    font-size: 20px;
}
.hold-btn:hover {
    background: #FEF3C7;
    color: #D97706;
    border-color: #F59E0B;
}

.search-entry-inline {
    padding: 10px 14px;
    border: 2px solid #E2E8F0;
    border-radius: 12px;
    font-size: 14px;
    background: #FFFFFF;
    color: #1E293B;
    min-height: 40px;
}
.search-entry-inline:focus {
    border-color: #059669;
}

/* PAYMENT SELECTOR (3-button picker) */
.pay-select-summary {
    background: #065F46;
    border-radius: 16px;
    padding: 16px;
}
.pay-select-title {
    font-size: 16px;
    font-weight: 700;
    color: #D1FAE5;
}
.pay-select-cash {
    background: #22C55E;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 800;
    font-size: 18px;
    border: none;
}
.pay-select-card {
    background: #3B82F6;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 800;
    font-size: 18px;
    border: none;
}
.pay-select-qr {
    background: #8B5CF6;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 800;
    font-size: 18px;
    border: none;
}

/* PAYMENT TYPE BUTTONS */
.payment-cash {
    background: #059669;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 700;
    font-size: 16px;
    min-height: 52px;
    border: none;
}
.payment-cash:hover {
    background: #047857;
}
.payment-card {
    background: #3B82F6;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 700;
    font-size: 16px;
    min-height: 52px;
    border: none;
}
.payment-card:hover {
    background: #2563EB;
}
.payment-qr {
    background: #8B5CF6;
    color: #FFFFFF;
    border-radius: 14px;
    font-weight: 700;
    font-size: 16px;
    min-height: 52px;
    border: none;
}
.payment-qr:hover {
    background: #7C3AED;
}

/* QUICK CASH BUTTONS */
.cash-quick-btn {
    border: 2px solid #E2E8F0;
    border-radius: 10px;
    background: #FFFFFF;
    color: #0F172A;
    font-weight: 700;
    font-size: 16px;
    padding: 12px 8px;
    min-height: 56px;
}
.cash-quick-btn:hover {
    border-color: #059669;
    background: #F0FDF4;
}

/* DIALOGS */
.checkout-dialog {
    padding: 20px;
    border-radius: 18px;
    background: #FFFFFF;
}
.dialog-title {
    font-weight: 800;
    font-size: 18px;
    color: #0F172A;
}

/* SUGGESTED / DESTRUCTIVE */
.suggested-action {
    background: #059669;
    color: #FFFFFF;
    border-radius: 12px;
    font-weight: 700;
    font-size: 15px;
    min-height: 46px;
    border: none;
}
.suggested-action:hover {
    background: #047857;
}
.destructive-action {
    background: #EF4444;
    color: #FFFFFF;
    border-radius: 12px;
    font-weight: 700;
    font-size: 15px;
    min-height: 46px;
    border: none;
}

/* TREEVIEW */
.treeview-table {
    background: #FFFFFF;
}
.treeview-table header button {
    background: #F8FAFC;
    font-weight: 700;
    font-size: 12px;
    color: #475569;
    padding: 10px 12px;
    border-bottom: 2px solid #E2E8F0;
}
.treeview-table cell {
    font-size: 14px;
    color: #0F172A;
    padding: 8px 12px;
}
.treeview-table tr:nth-child(even) {
    background: #F8FAFC;
}

/* COMBOBOX */
combobox entry, .form-entry {
    border: 2px solid #E2E8F0;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
    background: #FFFFFF;
}
combobox entry:focus, .form-entry:focus {
    border-color: #059669;
}

/* NOTEBOOK TABS */
notebook tab {
    padding: 10px 20px;
    font-weight: 600;
    font-size: 14px;
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
}
notebook tab:checked {
    background: #FFFFFF;
    border-bottom-color: transparent;
}
notebook tab label {
    color: #64748B;
}
notebook tab:checked label {
    color: #059669;
}

/* SPINNER */
spinner {
    color: #059669;
}

/* BADGE (for eBarimt pending, held orders) */
.badge {
    background: #EF4444;
    color: #FFFFFF;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    min-width: 18px;
    min-height: 18px;
}
.badge.amber {
    background: #F59E0B;
}

/* SALES COMPLETE DIALOG */
.sale-complete-dialog {
    padding: 16px;
}
.receipt-preview {
    font-family: DejaVu Sans Mono, Liberation Mono, monospace;
    font-size: 12px;
    background: #F8FAFC;
    border: 2px dashed #E2E8F0;
    border-radius: 12px;
    padding: 16px;
}
.action-btn-primary {
    background: #059669;
    color: #FFFFFF;
    border-radius: 12px;
    font-weight: 800;
    font-size: 16px;
    min-height: 58px;
    padding: 0 24px;
    border: none;
}
.action-btn-primary:hover {
    background: #047857;
}
.action-btn-success {
    background: #22C55E;
    color: #FFFFFF;
    border-radius: 12px;
    font-weight: 800;
    font-size: 16px;
    min-height: 58px;
    padding: 0 24px;
    border: none;
}
.action-btn-success:hover {
    background: #15803D;
}
.action-btn-secondary {
    background: #F1F5F9;
    color: #64748B;
    border-radius: 12px;
    font-weight: 700;
    font-size: 16px;
    min-height: 58px;
    padding: 0 24px;
    border: 1px solid #E2E8F0;
}
.action-btn-secondary:hover {
    background: #E2E8F0;
}

/* HELP DIALOG KEYBOARD SHORTCUT */
.kbd-key {
    font-family: DejaVu Sans Mono, Liberation Mono, monospace;
    font-size: 12px;
    font-weight: 700;
    background: #F1F5F9;
    color: #475569;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 4px 8px;
}

/* NOTIFICATION TOAST */
.notification-overlay {
    background: transparent;
}
.notification-toast {
    border-radius: 12px;
    padding: 12px 16px;
    margin: 4px 8px;
    font-weight: 600;
    font-size: 12px;
    border-left: 4px solid;
    min-width: 280px;
}
.notification-toast.success {
    background: #F0FDF4;
    color: #166534;
    border-left-color: #059669;
}
.notification-toast.error {
    background: #FEF2F2;
    color: #991B1B;
    border-left-color: #EF4444;
}
.notification-toast.warning {
    background: #FFFBEB;
    color: #92400E;
    border-left-color: #F59E0B;
}
.notification-toast.info {
    background: #EFF6FF;
    color: #1E40AF;
    border-left-color: #3B82F6;
}
.notification-close {
    color: inherit;
    opacity: 0.5;
    font-weight: 700;
    font-size: 16px;
    min-width: 24px;
    min-height: 24px;
    padding: 0;
    border: none;
    background: transparent;
}
.notification-close:hover {
    opacity: 1;
}

/* Scrollbars */
scrolledwindow scrollbar {
    -GtkScrollbar-has-backward-stepper: 0;
    -GtkScrollbar-has-forward-stepper: 0;
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical {
    min-width: 6px;
}
scrolledwindow scrollbar.vertical trough {
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical slider {
    background-color: #94A3B8;
    border-radius: 3px;
    min-height: 40px;
    border: none;
}
scrolledwindow scrollbar.vertical slider:hover {
    background-color: #059669;
}

/* Text entry */
entry {
    min-height: 38px;
}

/* Frame borders */
frame > border {
    border-style: none;
}

/* Focus state */
*:focus {
    outline-color: rgba(5, 150, 105, 0.4);
    outline-style: solid;
    outline-width: 2px;
    outline-offset: -2px;
}
"""

LIGHT_CSS = """\
/* CRISP RETAIL LIGHT THEME — Emerald Green & High Contrast White (GTK3-compatible) */

* {
    font-family: DejaVu Sans, Liberation Sans, Ubuntu, Sans, sans-serif;
    color: #0F172A;
}

window, .main-window-bg, stack {
    background-color: #F8FAFC;
}

.sidebar-list {
    background: #1E293B;
    color: #E2E8F0;
    min-width: 170px;
}
.sidebar-row {
    padding: 10px 16px;
    margin: 2px 6px;
    border-radius: 10px;
    color: #CBD5E1;
    font-size: 14px;
    font-weight: 600;
}
.sidebar-row:selected {
    background: #059669;
    color: #FFFFFF;
}

.product-card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 12px;
}
.product-card:hover {
    border-color: #059669;
    background-color: #F0FDF4;
}

.cart-panel {
    background-color: #FFFFFF;
    border-left: 2px solid #E2E8F0;
}

button {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}
button:hover {
    background: #F1F5F9;
    border-color: #94A3B8;
}
button.suggested-action, button.payment-btn {
    background: #059669;
    color: #FFFFFF;
    border: none;
}
button.suggested-action:hover, button.payment-btn:hover {
    background: #047857;
}
button.destructive-action {
    background: #EF4444;
    color: #FFFFFF;
    border: none;
}

entry {
    background: #FFFFFF;
    border: 2px solid #CBD5E1;
    border-radius: 8px;
    padding: 10px;
    font-size: 16px;
    font-weight: 700;
    min-height: 38px;
}
entry:focus {
    border-color: #059669;
}

scrolledwindow scrollbar {
    -GtkScrollbar-has-backward-stepper: 0;
    -GtkScrollbar-has-forward-stepper: 0;
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical {
    min-width: 6px;
}
scrolledwindow scrollbar.vertical trough {
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical slider {
    background-color: #94A3B8;
    border-radius: 3px;
    min-height: 40px;
    border: none;
}
scrolledwindow scrollbar.vertical slider:hover {
    background-color: #059669;
}

frame > border {
    border-style: none;
}

*:focus {
    outline-color: rgba(5, 150, 105, 0.4);
    outline-style: solid;
    outline-width: 2px;
    outline-offset: -2px;
}
"""

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

        raw = DARK_CSS if mode != "light" else LIGHT_CSS
        if scale != 1.0:
            raw = _scale_css(raw, scale)
        if low_perf:
            raw += "\n* { transition: none !important; animation: none !important; }"
        css = raw.encode("utf-8")
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._current_provider = provider
        self._current_mode = mode
        logger.info(f"Theme applied: {mode}, scale={scale}, low_perf={low_perf}")

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

"""
posgtk/theme.py -- GTK CSS theming matching the web app visual design.

Dark (modern, emerald-green slate) and light (high-contrast blue/emerald) themes.
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
/* DARK POS THEME — Deep Slate & Emerald Green */

* {
    font-family: DejaVu Sans, Liberation Sans, Ubuntu, Sans, sans-serif;
    color: #F8FAFC;
}

window, .main-window-bg {
    background-color: #0F172A;
}

.sidebar-list {
    background: #020617;
    color: #94A3B8;
    min-width: 170px;
}
.sidebar-list label { color: #94A3B8; }
.sidebar-row {
    padding: 10px 16px;
    margin: 2px 6px;
    border-radius: 10px;
    color: #94A3B8;
    font-size: 14px;
    font-weight: 600;
}
.sidebar-row label { color: #94A3B8; }
.sidebar-row:selected { background: #059669; }
.sidebar-row:selected label { color: #FFFFFF; }

.pos-header {
    background: #1E293B;
    border-bottom: 2px solid #334155;
    padding: 4px 12px;
}
.pos-header label { font-size: 16px; font-weight: 800; color: #F8FAFC; }
.clock-label { font-size: 12px; font-weight: 600; color: #94A3B8; }

.screen-box, .pos-left {
    background: #0F172A;
}

/* ENTRIES */
.barcode-entry, .search-entry, .search-entry-inline, entry {
    padding: 12px 16px;
    border: 2px solid #334155;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 700;
    background: #1E293B;
    color: #F8FAFC;
    margin: 8px;
}
.barcode-entry:focus, .search-entry:focus, .search-entry-inline:focus, entry:focus {
    border-color: #34D399;
}

/* CATEGORY SCROLL */
.category-scroll {
    min-height: 46px;
}
.category-scroll scrollbar { opacity: 0; min-width: 0; }

/* CATEGORY BUTTONS */
.category-btn {
    padding: 8px 16px;
    border: 2px solid #334155;
    border-radius: 20px;
    background: #1E293B;
    color: #94A3B8;
    font-weight: 600;
    font-size: 12px;
}
.category-btn label { color: #94A3B8; }
.category-btn:hover { border-color: #34D399; }
.category-btn:hover label { color: #34D399; }
.category-btn:checked, .category-btn:active {
    background: #059669;
    border-color: #059669;
}
.category-btn:checked label, .category-btn:active label { color: #FFFFFF; }

/* PRODUCT GRID */
flowboxchild {
    padding: 6px;
}

/* PRODUCT CARD */
.product-card {
    border: 1px solid #334155;
    border-radius: 10px;
    background: #1E293B;
    min-width: 110px;
    min-height: 130px;
    padding: 12px;
}
.product-card:hover {
    border-color: #34D399;
    background: #1E293B;
}
.product-card:active { opacity: 0.85; }
.product-card .card-icon {
    font-size: 26px;
    padding: 4px 0;
}
.product-name {
    font-size: 13px;
    font-weight: 700;
    color: #E2E8F0;
}
.product-price {
    font-size: 15px;
    font-weight: 800;
    color: #34D399;
}
.out-of-stock { opacity: 0.45; }
.no-barcode-card { border-color: #EF4444; border-width: 2px; }
.low-stock-badge {
    font-size: 10px;
    font-weight: 700;
    color: #F59E0B;
    background: #78350F;
    border-radius: 10px;
    padding: 1px 8px;
}

/* CART PANEL */
.cart-panel {
    background: #1E293B;
    border-left: 2px solid #334155;
    min-width: 320px;
}
.cart-header-bar {
    background: #1E293B;
    border-bottom: 1px solid #334155;
    padding: 12px 16px;
}
.cart-header-bar .cart-title {
    font-weight: 800;
    font-size: 16px;
    color: #F8FAFC;
    padding: 0 8px 0 0;
}
.cart-count-badge {
    background: #059669;
    color: #FFFFFF;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    min-width: 22px;
}

/* TAX MODE BADGE */
.tax-mode-badge {
    background: #1E3A8A;
    border: 1px solid #3B82F6;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    color: #93C5FD;
    font-weight: 700;
}
.tax-mode-badge label { color: #93C5FD; }
.tax-mode-badge.corporate {
    background: #78350F;
    border-color: #F59E0B;
    color: #FDE68A;
}
.tax-mode-badge.none {
    background: #7F1D1D;
    border-color: #EF4444;
    color: #FECACA;
}

/* CART ROWS */
.cart-scroll { background: #1E293B; }
.cart-row {
    background: #1E293B;
    border-bottom: 1px solid #334155;
    padding: 10px 6px;
}
.cart-row:hover { background: #182235; }
.cart-row:last-child { border-bottom: none; }
.cart-item-title {
    font-size: 13px;
    font-weight: 700;
    color: #E2E8F0;
    padding: 0 0 0 10px;
}
.cart-item-subtotal {
    font-size: 14px;
    font-weight: 800;
    color: #34D399;
    padding: 0 10px 0 6px;
}

/* QTY CONTROL GROUP */
.qty-control-group {
    border: 1px solid #475569;
    border-radius: 6px;
    background: #0F172A;
    overflow: hidden;
}
.qty-btn {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 4px 10px;
    font-size: 14px;
    font-weight: 800;
    color: #CBD5E1;
    min-width: 0;
}
.qty-btn:hover { background: #334155; }
.qty-text-label {
    font-size: 13px;
    font-weight: 800;
    color: #F8FAFC;
    min-width: 24px;
    text-align: center;
}

.cart-empty-state { color: #64748B; font-size: 14px; padding: 0 20px; }
.cart-empty-icon { font-size: 40px; opacity: 0.5; }

/* CART TOTAL */
.cart-total-row {
    padding: 14px 18px;
    border-top: 2px dashed #334155;
    background: #0F172A;
}
.cart-total-label { font-weight: 800; font-size: 22px; color: #34D399; }

/* CHECKOUT ROW */
.checkout-btn-row {
    padding: 10px 12px;
    background: #0F172A;
}
.checkout-pay-btn {
    background: #059669;
    color: #FFFFFF;
    border-radius: 10px;
    font-weight: 800;
    font-size: 16px;
    padding: 14px 18px;
    border: none;
}
.checkout-pay-btn label { color: #FFFFFF; }
.checkout-pay-btn:hover { background: #34D399; }
.checkout-pay-btn:disabled { opacity: 0.35; }
.hold-btn {
    background: #1E293B;
    color: #64748B;
    border: 2px solid #334155;
    border-radius: 10px;
    font-size: 20px;
    padding: 8px 14px;
}
.hold-btn:hover {
    background: #78350F;
    border-color: #F59E0B;
    color: #F59E0B;
}

/* CART REMOVE BTN */
.cart-remove-btn {
    background: transparent;
    border: none;
    border-radius: 0;
    font-size: 14px;
    font-weight: 800;
    color: #EF4444;
    padding: 4px 8px;
}
.cart-remove-btn:hover { color: #DC2626; }

/* DIALOGS */
.checkout-dialog, dialog, .dialog {
    padding: 20px;
    border-radius: 14px;
    background: #1E293B;
    color: #F8FAFC;
    border: 1px solid #334155;
}
.checkout-dialog label, dialog label, .dialog label { color: #F8FAFC; }
.dialog-title { font-weight: 800; font-size: 18px; color: #F8FAFC; }

/* BUTTONS SUGGESTED / DESTRUCTIVE */
.suggested-action, button.suggested-action {
    background: #059669;
    color: #FFFFFF;
    border-radius: 10px;
    font-weight: 700;
    font-size: 15px;
    padding: 12px 18px;
    border: none;
}
.suggested-action:hover { background: #34D399; }
.destructive-action, button.destructive-action {
    background: #EF4444;
    color: #FFFFFF;
    border-radius: 10px;
    font-weight: 700;
    font-size: 15px;
    padding: 12px 18px;
    border: none;
}
.destructive-action:hover { background: #DC2626; }

/* TREEVIEW / TABLE */
.treeview-table { background: #1E293B; }
.treeview-table header button {
    background: #0F172A;
    font-weight: 700;
    font-size: 12px;
    color: #94A3B8;
    padding: 10px 12px;
    border-bottom: 2px solid #334155;
}
.treeview-table cell {
    font-size: 14px;
    color: #E2E8F0;
    padding: 8px 12px;
}
.treeview-table tr:nth-child(even) { background: #182235; }
treeview.view {
    background-color: #1E293B;
    border: 1px solid #334155;
}
treeview.view cell { padding: 8px 12px; }
treeview.view:hover { background-color: #182235; }

/* COMBOS / NOTEBOOK / TABS */
combobox, combobox entry, .form-entry {
    border: 2px solid #334155;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
    background: #1E293B;
    color: #F8FAFC;
}
combobox entry:focus, .form-entry:focus { border-color: #34D399; }
notebook {
    background-color: #1E293B;
    border: 1px solid #334155;
}
notebook tab {
    padding: 10px 20px;
    font-weight: 600;
    font-size: 14px;
    background: #0F172A;
    border: 1px solid #334155;
}
notebook tab:checked { background: #1E293B; border-bottom: 3px solid #059669; }
notebook tab label { color: #94A3B8; }
notebook tab:checked label { color: #34D399; }
spinner { color: #34D399; }

.badge {
    background: #EF4444;
    color: #FFFFFF;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    min-width: 18px;
}
.badge.amber { background: #F59E0B; }

/* NOTIFICATIONS */
.notification-toast {
    border-radius: 10px;
    padding: 12px 16px;
    margin: 4px 8px;
    font-weight: 600;
    font-size: 12px;
    border-left: 4px solid;
}
.notification-toast.success { background: #064E3B; color: #A7F3D0; border-left-color: #34D399; }
.notification-toast.error { background: #7F1D1D; color: #FEE2E2; border-left-color: #EF4444; }
.notification-toast.warning { background: #78350F; color: #FEF3C7; border-left-color: #F59E0B; }
.notification-toast.info { background: #1E3A8A; color: #DBEAFE; border-left-color: #3B82F6; }

/* SCROLLBARS */
scrolledwindow scrollbar {
    -GtkScrollbar-has-backward-stepper: 0;
    -GtkScrollbar-has-forward-stepper: 0;
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical { min-width: 6px; }
scrolledwindow scrollbar.vertical trough {
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical slider {
    background-color: #475569;
    border-radius: 3px;
    min-height: 40px;
    border: none;
}
scrolledwindow scrollbar.vertical slider:hover { background-color: #34D399; }

frame > border { border-style: none; }
*:focus {
    outline-color: rgba(52, 211, 153, 0.4);
    outline-style: solid;
    outline-width: 2px;
    outline-offset: -2px;
}
"""

LIGHT_CSS = """\
/* UNIFIED RETAIL LIGHT INTERFACE — Emerald Green Primary & Crisp Controls */

* {
    font-family: DejaVu Sans, Liberation Sans, Ubuntu, Sans, sans-serif;
    color: #0F172A;
}

window, .main-window-bg {
    background-color: #F8FAFC;
}

.sidebar-list {
    background: #1E293B;
    color: #CBD5E1;
    min-width: 170px;
}
.sidebar-list label { color: #CBD5E1; }
.sidebar-row {
    padding: 10px 16px;
    margin: 2px 6px;
    border-radius: 10px;
    color: #CBD5E1;
    font-size: 14px;
    font-weight: 600;
}
.sidebar-row label { color: #CBD5E1; }
.sidebar-row:selected { background: #059669; }
.sidebar-row:selected label { color: #FFFFFF; }

.pos-header {
    background: #FFFFFF;
    border-bottom: 2px solid #E2E8F0;
    padding: 4px 12px;
}
.pos-header label { font-size: 16px; font-weight: 800; color: #0F172A; }
.clock-label { font-size: 12px; font-weight: 600; color: #64748B; }

.screen-box, .pos-left {
    background: #F8FAFC;
}

/* ENTRIES */
.barcode-entry, .search-entry, .search-entry-inline, entry {
    padding: 12px 16px;
    border: 2px solid #CBD5E1;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 700;
    background: #FFFFFF;
    color: #0F172A;
    margin: 8px;
}
.barcode-entry:focus, .search-entry:focus, .search-entry-inline:focus, entry:focus {
    border-color: #059669;
}

/* CATEGORY SCROLL */
.category-scroll {
    min-height: 46px;
}
.category-scroll scrollbar { opacity: 0; min-width: 0; }

/* CATEGORY BUTTONS */
.category-btn {
    padding: 8px 16px;
    border: 2px solid #E2E8F0;
    border-radius: 20px;
    background: #FFFFFF;
    color: #64748B;
    font-weight: 600;
    font-size: 12px;
}
.category-btn label { color: #64748B; }
.category-btn:hover { border-color: #059669; }
.category-btn:hover label { color: #059669; }
.category-btn:checked, .category-btn:active {
    background: #059669;
    border-color: #059669;
}
.category-btn:checked label, .category-btn:active label { color: #FFFFFF; }

/* PRODUCT GRID */
flowboxchild {
    padding: 6px;
}

/* PRODUCT CARD */
.product-card {
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    background: #FFFFFF;
    min-width: 110px;
    min-height: 130px;
    padding: 12px;
}
.product-card:hover {
    border-color: #059669;
    background-color: #F0FDF4;
}
.product-card:active { opacity: 0.85; }
.product-card .card-icon {
    font-size: 26px;
    padding: 4px 0;
}
.product-name {
    font-size: 13px;
    font-weight: 700;
    color: #1E293B;
}
.product-price {
    font-size: 15px;
    font-weight: 800;
    color: #059669;
}
.out-of-stock { opacity: 0.45; }
.no-barcode-card { border-color: #EF4444; border-width: 2px; }
.low-stock-badge {
    font-size: 10px;
    font-weight: 700;
    color: #D97706;
    background: #FEF3C7;
    border-radius: 10px;
    padding: 1px 8px;
}

/* CART PANEL */
.cart-panel {
    background: #FFFFFF;
    border-left: 2px solid #E2E8F0;
    min-width: 320px;
}
.cart-header-bar {
    background: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 12px 16px;
}
.cart-header-bar .cart-title {
    font-weight: 800;
    font-size: 16px;
    color: #0F172A;
    padding: 0 8px 0 0;
}
.cart-count-badge {
    background: #059669;
    color: #FFFFFF;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    min-width: 22px;
}

/* TAX MODE BADGE */
.tax-mode-badge {
    background: #EFF6FF;
    border: 1px solid #3B82F6;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    color: #1E40AF;
    font-weight: 700;
}
.tax-mode-badge label { color: #1E40AF; }
.tax-mode-badge.corporate {
    background: #FEF3C7;
    border-color: #F59E0B;
    color: #B45309;
}
.tax-mode-badge.none {
    background: #FEE2E2;
    border-color: #EF4444;
    color: #B91C1C;
}

/* CART ROWS */
.cart-scroll { background: #FFFFFF; }
.cart-row {
    background: #FFFFFF;
    border-bottom: 1px solid #F1F5F9;
    padding: 10px 6px;
}
.cart-row:hover { background: #F8FAFC; }
.cart-row:last-child { border-bottom: none; }
.cart-item-title {
    font-size: 13px;
    font-weight: 700;
    color: #0F172A;
    padding: 0 0 0 10px;
}
.cart-item-subtotal {
    font-size: 14px;
    font-weight: 800;
    color: #0F172A;
    padding: 0 10px 0 6px;
}

/* QTY CONTROL GROUP */
.qty-control-group {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    background: #F8FAFC;
    overflow: hidden;
}
.qty-btn {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 4px 10px;
    font-size: 14px;
    font-weight: 800;
    color: #64748B;
    min-width: 0;
}
.qty-btn:hover { background: #E2E8F0; }
.qty-text-label {
    font-size: 13px;
    font-weight: 800;
    color: #0F172A;
    min-width: 24px;
    text-align: center;
}

.cart-empty-state { color: #94A3B8; font-size: 14px; padding: 0 20px; }
.cart-empty-icon { font-size: 40px; opacity: 0.5; }

/* CART TOTAL */
.cart-total-row {
    padding: 14px 18px;
    border-top: 2px dashed #E2E8F0;
    background: #F8FAFC;
}
.cart-total-label { font-weight: 800; font-size: 22px; color: #047857; }

/* CHECKOUT ROW */
.checkout-btn-row {
    padding: 10px 12px;
    background: #F8FAFC;
}
.checkout-pay-btn {
    background: #059669;
    color: #FFFFFF;
    border-radius: 10px;
    font-weight: 800;
    font-size: 16px;
    padding: 14px 18px;
    border: none;
}
.checkout-pay-btn label { color: #FFFFFF; }
.checkout-pay-btn:hover { background: #047857; }
.checkout-pay-btn:disabled { opacity: 0.35; }
.hold-btn {
    background: #F1F5F9;
    color: #94A3B8;
    border: 2px solid #E2E8F0;
    border-radius: 10px;
    font-size: 20px;
    padding: 8px 14px;
}
.hold-btn:hover {
    background: #FEF3C7;
    border-color: #F59E0B;
    color: #D97706;
}

/* CART REMOVE BTN */
.cart-remove-btn {
    background: transparent;
    border: none;
    border-radius: 0;
    font-size: 14px;
    font-weight: 800;
    color: #EF4444;
    padding: 4px 8px;
}
.cart-remove-btn:hover { color: #DC2626; }

/* DIALOGS */
.checkout-dialog, dialog, .dialog {
    padding: 20px;
    border-radius: 14px;
    background: #FFFFFF;
    color: #0F172A;
    border: 1px solid #E2E8F0;
}
.checkout-dialog label, dialog label, .dialog label { color: #0F172A; }
.dialog-title { font-weight: 800; font-size: 18px; color: #0F172A; }

/* BUTTONS SUGGESTED / DESTRUCTIVE */
.suggested-action, button.suggested-action {
    background: #059669;
    color: #FFFFFF;
    border-radius: 10px;
    font-weight: 700;
    font-size: 15px;
    padding: 12px 18px;
    border: none;
}
.suggested-action:hover { background: #047857; }
.destructive-action, button.destructive-action {
    background: #EF4444;
    color: #FFFFFF;
    border-radius: 10px;
    font-weight: 700;
    font-size: 15px;
    padding: 12px 18px;
    border: none;
}
.destructive-action:hover { background: #DC2626; }

/* TREEVIEW / TABLE */
.treeview-table { background: #FFFFFF; }
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
.treeview-table tr:nth-child(even) { background: #F8FAFC; }
treeview.view {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
}
treeview.view cell { padding: 8px 12px; }
treeview.view:hover { background-color: #F8FAFC; }

/* COMBOS / NOTEBOOK / TABS */
combobox, combobox entry, .form-entry {
    border: 2px solid #E2E8F0;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
    background: #FFFFFF;
    color: #0F172A;
}
combobox entry:focus, .form-entry:focus { border-color: #059669; }
notebook {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
}
notebook tab {
    padding: 10px 20px;
    font-weight: 600;
    font-size: 14px;
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
}
notebook tab:checked { background: #FFFFFF; border-bottom: 3px solid #059669; }
notebook tab label { color: #64748B; }
notebook tab:checked label { color: #059669; }
spinner { color: #059669; }

.badge {
    background: #EF4444;
    color: #FFFFFF;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    min-width: 18px;
}
.badge.amber { background: #F59E0B; }

/* NOTIFICATIONS */
.notification-toast {
    border-radius: 10px;
    padding: 12px 16px;
    margin: 4px 8px;
    font-weight: 600;
    font-size: 12px;
    border-left: 4px solid;
}
.notification-toast.success { background: #F0FDF4; color: #166534; border-left-color: #059669; }
.notification-toast.error { background: #FEF2F2; color: #991B1B; border-left-color: #EF4444; }
.notification-toast.warning { background: #FFFBEB; color: #92400E; border-left-color: #F59E0B; }
.notification-toast.info { background: #EFF6FF; color: #1E40AF; border-left-color: #3B82F6; }

/* SCROLLBARS */
scrolledwindow scrollbar {
    -GtkScrollbar-has-backward-stepper: 0;
    -GtkScrollbar-has-forward-stepper: 0;
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical { min-width: 6px; }
scrolledwindow scrollbar.vertical trough {
    background-color: transparent;
    border: none;
}
scrolledwindow scrollbar.vertical slider {
    background-color: #CBD5E1;
    border-radius: 3px;
    min-height: 40px;
    border: none;
}
scrolledwindow scrollbar.vertical slider:hover { background-color: #94A3B8; }

frame > border { border-style: none; }
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

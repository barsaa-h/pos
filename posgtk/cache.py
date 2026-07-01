"""
gtk/cache.py — In-memory product cache with category colors.

Pre-loads all active products at startup.
Zero DB hits during POS operation.
Supports category color CSS generation for product card accents.
"""

import logging
import re

logger = logging.getLogger("pos.gtk.cache")

_CSS_SAFE = re.compile(r"[^a-zA-Z0-9\u0080-\uFFFF_-]")


def css_class_name(name):
    """Convert a category name to a valid CSS class name."""
    return "cat-" + _CSS_SAFE.sub("-", name.strip().replace(" ", "-"))


class ProductCache:
    def __init__(self):
        self._by_barcode = {}
        self._by_id = {}
        self._all = []
        self._categories = []
        self._by_category = {}
        self._category_colors = {}
        self._loaded = False

    def load(self):
        """Load all active products and category colors from DB."""
        try:
            import database as db
            products = db.get_all_products(active_only=True)
        except Exception as e:
            logger.error(f"Product cache load failed: {e}")
            return  # _loaded stays False — next access retries instead of permanently serving an empty cache

        self._by_barcode.clear()
        self._by_id.clear()
        self._all.clear()
        self._by_category.clear()
        self._category_colors.clear()
        cats = set()

        for p in products:
            self._by_id[p["id"]] = p
            barcode = p.get("barcode", "")
            if barcode:
                self._by_barcode[barcode] = p
            self._all.append(p)
            cat = p.get("category", "Бусад")
            cats.add(cat)
            if cat not in self._by_category:
                self._by_category[cat] = []
            self._by_category[cat].append(p)

        self._categories = sorted(cats)

        try:
            import database as db
            with db.get_db() as conn:
                rows = conn.execute(
                    "SELECT name, color FROM categories WHERE color IS NOT NULL"
                ).fetchall()
                for row in rows:
                    self._category_colors[row["name"]] = row["color"]
        except Exception:
            pass

        self._loaded = True
        logger.info(
            f"Product cache loaded: {len(self._all)} products, "
            f"{len(self._categories)} categories, "
            f"{len(self._category_colors)} colors"
        )

    def get_by_barcode(self, barcode):
        self._ensure_loaded()
        return self._by_barcode.get(barcode)

    def get(self, product_id):
        self._ensure_loaded()
        return self._by_id.get(product_id)

    def all_products(self):
        self._ensure_loaded()
        return self._all

    def categories(self):
        self._ensure_loaded()
        return self._categories

    def filter_by_category(self, category):
        self._ensure_loaded()
        if not category:
            return self._all
        return self._by_category.get(category, [])

    def search(self, query, limit=50):
        self._ensure_loaded()
        if not query:
            return self._all[:limit]
        q = query.lower()
        results = []
        for p in self._all:
            if q in p.get("name", "").lower():
                results.append(p)
                if len(results) >= limit:
                    break
        return results

    def get_category_color(self, category):
        """Return hex color for a category, or default gray."""
        self._ensure_loaded()
        return self._category_colors.get(category, "#6B7280")

    def generate_category_css(self):
        """Generate CSS rules for per-category card accent colors."""
        self._ensure_loaded()
        lines = []
        for name, color in self._category_colors.items():
            cls = css_class_name(name)
            lines.append(f".{cls} {{ border-top: 4px solid {color}; }}")
            lines.append(
                f".{cls}:hover {{ border-color: {color}; }}"
            )
        return "\n".join(lines)

    def invalidate(self):
        self._loaded = False
        logger.info("Product cache invalidated")

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

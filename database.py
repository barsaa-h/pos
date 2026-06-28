"""
database.py — SQLite database layer for the POS system.

Responsibilities:
- Enable WAL mode on the very first connection (critical for crash safety).
- Create all tables with exact schema specified in requirements.
- Seed default data (sample products, settings, admin password).
- Provide query helper functions for all CRUD operations.
- Daily backup: copy pos.db on first sale of each day, keep 30 days.
- All functions are safe to call multiple times (idempotent where needed).
"""

import os
import sqlite3
import logging
import hashlib
import threading
from datetime import datetime, timedelta
from contextlib import contextmanager

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("POS_DB_PATH") or os.path.join(BASE_DIR, "pos.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

_db_connection_lock = threading.Lock()
_db_connection = None


def _get_persistent_connection():
    global _db_connection
    with _db_connection_lock:
        if _db_connection is None:
            _db_connection = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
            _db_connection.row_factory = sqlite3.Row
            _db_connection.execute("PRAGMA journal_mode=WAL")
            _db_connection.execute("PRAGMA foreign_keys=ON")
            try:
                row = _db_connection.execute(
                    "SELECT value FROM settings WHERE key = ?", ("db_sync_mode",)
                ).fetchone()
                sync_mode = row["value"] if row and row["value"] in ("NORMAL", "FULL") else "FULL"
            except Exception:
                sync_mode = "FULL"
            _db_connection.execute(f"PRAGMA synchronous={sync_mode}")
            _db_connection.execute("PRAGMA cache_size=-64000")
            _db_connection.execute("PRAGMA temp_store=MEMORY")
            _db_connection.execute("PRAGMA mmap_size=268435456")
            journal_mode = _db_connection.execute("PRAGMA journal_mode").fetchone()[0]
            logger.info(f"DB: {journal_mode} mode, sync={sync_mode}")
        return _db_connection


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Read sync mode directly to avoid recursion through get_setting
    sync_mode = "FULL"
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("db_sync_mode",)
        ).fetchone()
        if row and row["value"] in ("NORMAL", "FULL"):
            sync_mode = row["value"]
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    conn.execute(f"PRAGMA synchronous={sync_mode}")
    return conn


_cached_sync_mode = None

_thread_local = threading.local()

def _get_thread_connection():
    global _cached_sync_mode
    if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        _thread_local.conn.row_factory = sqlite3.Row
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")
        _thread_local.conn.execute("PRAGMA foreign_keys=ON")
        _thread_local.conn.execute("PRAGMA cache_size=-64000")
        _thread_local.conn.execute("PRAGMA temp_store=MEMORY")
        _thread_local.conn.execute("PRAGMA mmap_size=268435456")
        if _cached_sync_mode is None:
            try:
                row = _thread_local.conn.execute(
                    "SELECT value FROM settings WHERE key = ?", ("db_sync_mode",)
                ).fetchone()
                _cached_sync_mode = row["value"] if row and row["value"] in ("NORMAL", "FULL") else "FULL"
            except Exception:
                _cached_sync_mode = "FULL"
        _thread_local.conn.execute(f"PRAGMA synchronous={_cached_sync_mode}")
    return _thread_local.conn


@contextmanager
def get_db():
    conn = _get_thread_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _get_password_salt():
    """Get or create a unique salt for this installation."""
    try:
        salt = get_setting("password_salt", "")
        if salt and len(salt) >= 16:
            return salt
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    salt = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    try:
        set_setting("password_salt", salt)
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
    return salt

def hash_password(password):
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    salt = _get_password_salt()
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _is_bcrypt_hash(password_hash):
    return password_hash.startswith("$2b$")


def _is_sha256_hash(password_hash):
    return not _is_bcrypt_hash(password_hash) and len(password_hash) == 64


def verify_password(password, password_hash):
    if not password_hash:
        return False
    if BCRYPT_AVAILABLE and _is_bcrypt_hash(password_hash):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False
    salt = _get_password_salt()
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest() == password_hash


def init_db():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)

        cursor = conn.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        if count == 0:
            _seed_data(conn)
            logger.info("Database initialized with default settings (no products).")
        else:
            logger.info("Database already initialized, skipping seed.")

    migrate_db()

    orphans = audit_orphans()
    if orphans:
        logger.warning(f"FK orphan audit found issues: {orphans}")
    else:
        logger.info("FK orphan audit: clean")


def migrate_db():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_migration_backup = os.path.join(BACKUP_DIR, f"pos_pre_migration_{ts}.db")
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        source = get_connection()
        dest = sqlite3.connect(pre_migration_backup)
        source.backup(dest)
        dest.close()
        source.close()
        logger.info(f"Pre-migration backup created: {pre_migration_backup}")
    except Exception as e:
        logger.warning(f"Pre-migration backup failed (non-fatal): {e}")

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key = 'admin_password_hash'"
        )
        if cursor.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('admin_password_hash', '')"
            )
            logger.info("Migration: Added admin_password_hash setting")

        cursor = conn.execute("PRAGMA table_info(sales)")
        columns = cursor.fetchall()
        cashier_col = [c for c in columns if c[1] == 'cashier_id']
        if cashier_col and cashier_col[0][3] == 1:
            logger.info("Migration: Making cashier_id nullable in sales table...")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript("""
                DROP TABLE IF EXISTS sales_new;
                CREATE TABLE sales_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cashier_id INTEGER,
                    payment_type TEXT DEFAULT 'cash' CHECK(payment_type IN ('cash', 'card', 'split', 'return')),
                    subtotal INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    cash_given INTEGER DEFAULT 0,
                    change_given INTEGER DEFAULT 0,
                    card_amount INTEGER DEFAULT 0,
                    cash_amount INTEGER DEFAULT 0,
                    ebarimt_id TEXT DEFAULT '',
                    ebarimt_qr TEXT DEFAULT '',
                    ebarimt_status TEXT DEFAULT 'pending'
                        CHECK(ebarimt_status IN ('pending', 'sent', 'failed', 'skipped')),
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
                INSERT INTO sales_new SELECT id, cashier_id, payment_type, subtotal, total,
                    cash_given, change_given, card_amount, cash_amount,
                    ebarimt_id, ebarimt_qr, ebarimt_status, created_at FROM sales;
                DROP TABLE sales;
                ALTER TABLE sales_new RENAME TO sales;
            """)
            conn.execute("PRAGMA foreign_keys=ON")
            logger.info("Migration: cashier_id is now nullable in sales table")

        cursor = conn.execute("PRAGMA table_info(sale_items)")
        columns = cursor.fetchall()
        qty_col = [c for c in columns if c[1] == 'quantity']
        if qty_col:
            try:
                conn.execute("INSERT INTO sale_items (sale_id, product_name, quantity, unit_price, subtotal) VALUES (0, 'test', -1, 0, 0)")
                conn.execute("DELETE FROM sale_items WHERE sale_id = 0")
            except sqlite3.IntegrityError:
                logger.info("Migration: Removing quantity CHECK constraint in sale_items table...")
                conn.execute("PRAGMA foreign_keys=OFF")
                conn.executescript("""
                    DROP TABLE IF EXISTS sale_items_new;
                    CREATE TABLE sale_items_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sale_id INTEGER NOT NULL,
                        product_id INTEGER,
                        product_name TEXT NOT NULL,
                        barcode TEXT DEFAULT '',
                        quantity REAL NOT NULL,
                        unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
                        subtotal INTEGER NOT NULL DEFAULT 0,
                        FOREIGN KEY (sale_id) REFERENCES sales(id),
                        FOREIGN KEY (product_id) REFERENCES products(id)
                    );
                    INSERT INTO sale_items_new SELECT id, sale_id, product_id, product_name,
                        barcode, quantity, unit_price, subtotal FROM sale_items;
                    DROP TABLE sale_items;
                    ALTER TABLE sale_items_new RENAME TO sale_items;
                """)
                conn.execute("PRAGMA foreign_keys=ON")
                logger.info("Migration: quantity CHECK constraint removed from sale_items table")

        cursor = conn.execute("PRAGMA table_info(sales)")
        columns = cursor.fetchall()
        col_names = [c[1] for c in columns]
        if 'return_of_sale_id' not in col_names:
            logger.info("Migration: Adding return_of_sale_id column to sales table...")
            conn.execute("ALTER TABLE sales ADD COLUMN return_of_sale_id INTEGER DEFAULT NULL")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_return_of ON sales(return_of_sale_id)")
            logger.info("Migration: return_of_sale_id column added")

        cursor = conn.execute("PRAGMA table_info(sales)")
        columns = cursor.fetchall()
        col_names = [c[1] for c in columns]
        if 'ebarimt_lottery' not in col_names:
            logger.info("Migration: Adding ebarimt_lottery column to sales table...")
            conn.execute("ALTER TABLE sales ADD COLUMN ebarimt_lottery TEXT DEFAULT ''")
            logger.info("Migration: ebarimt_lottery column added")

        # Migration: Add cost_price and expiry_date to products table
        cursor = conn.execute("PRAGMA table_info(products)")
        pcols = [c[1] for c in cursor.fetchall()]
        if 'cost_price' not in pcols:
            logger.info("Migration: Adding cost_price column to products table...")
            conn.execute("ALTER TABLE products ADD COLUMN cost_price INTEGER DEFAULT 0")
            logger.info("Migration: cost_price column added")
        if 'expiry_date' not in pcols:
            logger.info("Migration: Adding expiry_date column to products table...")
            conn.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT DEFAULT ''")
            logger.info("Migration: expiry_date column added")

        # Migration: Add image_url and supplier_id to products table
        cursor = conn.execute("PRAGMA table_info(products)")
        pcols = [c[1] for c in cursor.fetchall()]
        if 'image_url' not in pcols:
            logger.info("Migration: Adding image_url column to products table...")
            conn.execute("ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''")
            logger.info("Migration: image_url column added")
        if 'supplier_id' not in pcols:
            logger.info("Migration: Adding supplier_id column to products table...")
            conn.execute("ALTER TABLE products ADD COLUMN supplier_id INTEGER DEFAULT NULL")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id)")
            logger.info("Migration: supplier_id column added")

        # Migration: Create suppliers table
        conn.execute("""CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_person TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            address TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )""")

        # Migration: Allow 'qr' payment type in sales table
        cursor = conn.execute("PRAGMA table_info(sales)")
        pt_cols = [c for c in cursor.fetchall() if c[1] == 'payment_type']
        if pt_cols:
            old_cols = [c[1] for c in conn.execute("PRAGMA table_info(sales)").fetchall()]
            has_qpay = 'qpay_invoice_id' in old_cols
            conn.execute("PRAGMA foreign_keys=OFF")
            if has_qpay:
                terminal_cols = ""
                if 'terminal_txn_id' in old_cols:
                    terminal_cols = ", terminal_txn_id TEXT DEFAULT '', terminal_status TEXT DEFAULT ''"
                conn.executescript(f"""
                    DROP TABLE IF EXISTS sales_new;
                    CREATE TABLE sales_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cashier_id INTEGER,
                        payment_type TEXT DEFAULT 'cash' CHECK(payment_type IN ('cash', 'card', 'split', 'qr', 'return')),
                        subtotal INTEGER NOT NULL DEFAULT 0,
                        total INTEGER NOT NULL DEFAULT 0,
                        cash_given INTEGER DEFAULT 0,
                        change_given INTEGER DEFAULT 0,
                        card_amount INTEGER DEFAULT 0,
                        cash_amount INTEGER DEFAULT 0,
                        ebarimt_id TEXT DEFAULT '',
                        ebarimt_qr TEXT DEFAULT '',
                        ebarimt_status TEXT DEFAULT 'pending'
                            CHECK(ebarimt_status IN ('pending', 'sent', 'failed', 'skipped')),
                        created_at TEXT DEFAULT (datetime('now', 'localtime')),
                        return_of_sale_id INTEGER DEFAULT NULL,
                        ebarimt_lottery TEXT DEFAULT '',
                        qpay_invoice_id TEXT DEFAULT '',
                        qpay_payment_status TEXT DEFAULT 'none'{terminal_cols},
                        FOREIGN KEY (cashier_id) REFERENCES cashiers(id)
                    );
                    INSERT INTO sales_new SELECT * FROM sales;
                    DROP TABLE sales;
                    ALTER TABLE sales_new RENAME TO sales;
                    CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at);
                    CREATE INDEX IF NOT EXISTS idx_sales_ebarimt ON sales(ebarimt_status);
                    CREATE INDEX IF NOT EXISTS idx_sales_return_of ON sales(return_of_sale_id);
                """)
            else:
                term_cols2 = ""
                if 'terminal_txn_id' in old_cols:
                    term_cols2 = ", terminal_txn_id TEXT DEFAULT '', terminal_status TEXT DEFAULT ''"
                conn.executescript(f"""
                    DROP TABLE IF EXISTS sales_new;
                    CREATE TABLE sales_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cashier_id INTEGER,
                        payment_type TEXT DEFAULT 'cash' CHECK(payment_type IN ('cash', 'card', 'split', 'qr', 'return')),
                        subtotal INTEGER NOT NULL DEFAULT 0,
                        total INTEGER NOT NULL DEFAULT 0,
                        cash_given INTEGER DEFAULT 0,
                        change_given INTEGER DEFAULT 0,
                        card_amount INTEGER DEFAULT 0,
                        cash_amount INTEGER DEFAULT 0,
                        ebarimt_id TEXT DEFAULT '',
                        ebarimt_qr TEXT DEFAULT '',
                        ebarimt_status TEXT DEFAULT 'pending'
                            CHECK(ebarimt_status IN ('pending', 'sent', 'failed', 'skipped')),
                        created_at TEXT DEFAULT (datetime('now', 'localtime')),
                        return_of_sale_id INTEGER DEFAULT NULL,
                        ebarimt_lottery TEXT DEFAULT ''{term_cols2},
                        FOREIGN KEY (cashier_id) REFERENCES cashiers(id)
                    );
                    INSERT INTO sales_new SELECT * FROM sales;
                    DROP TABLE sales;
                    ALTER TABLE sales_new RENAME TO sales;
                    CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at);
                    CREATE INDEX IF NOT EXISTS idx_sales_ebarimt ON sales(ebarimt_status);
                    CREATE INDEX IF NOT EXISTS idx_sales_return_of ON sales(return_of_sale_id);
                """)
            conn.execute("PRAGMA foreign_keys=ON")
            logger.info("Migration: Updated sales payment_type CHECK to include 'qr'")

        # Migration: Create cash_drawer_log table
        conn.execute("""CREATE TABLE IF NOT EXISTS cash_drawer_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL CHECK(action IN ('open', 'close', 'float_in', 'float_out')),
            amount INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_drawer_created ON cash_drawer_log(created_at)")

        # Migration: Create idempotency_keys table
        conn.execute("""CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY,
            sale_id INTEGER NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )""")
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '1')"
        )

        cursor = conn.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            logger.info("Migration: Seeding categories from existing products...")
            cat_rows = conn.execute(
                "SELECT DISTINCT category FROM products WHERE is_active = 1 ORDER BY category"
            ).fetchall()
            default_icons = {
                'Сүүн бүтээгдэхүүн': '🥛', 'Талх нарийн боов': '🍞', 'Өндөг': '🥚',
                'Будаа': '🍚', 'Гоймон': '🍜', 'Тос': '🛢️', 'Чихэр': '🍬',
                'Давс амтлагч': '🧂', 'Жимс': '🍎', 'Ус ундаа': '🥤',
            }
            default_colors = {
                'Сүүн бүтээгдэхүүн': '#3B82F6', 'Талх нарийн боов': '#F59E0B', 'Өндөг': '#EAB308',
                'Будаа': '#22C55E', 'Гоймон': '#EF4444', 'Тос': '#A855F7', 'Чихэр': '#06B6D4',
                'Давс амтлагч': '#78716C', 'Жимс': '#84CC16', 'Ус ундаа': '#0EA5E9',
            }
            for i, row in enumerate(cat_rows):
                name = row[0]
                icon = default_icons.get(name, '📦')
                color = default_colors.get(name, '#6B7280')
                conn.execute(
                    "INSERT OR IGNORE INTO categories (name, icon, color, sort_order) VALUES (?, ?, ?, ?)",
                    (name, icon, color, i * 10)
                )
            logger.info("Migration: Categories table seeded successfully")

        # Migration: Add QPay columns to sales table
        cursor = conn.execute("PRAGMA table_info(sales)")
        col_names = [c[1] for c in cursor.fetchall()]
        if 'qpay_invoice_id' not in col_names:
            logger.info("Migration: Adding qpay_invoice_id column to sales table...")
            conn.execute("ALTER TABLE sales ADD COLUMN qpay_invoice_id TEXT DEFAULT ''")
            conn.execute("ALTER TABLE sales ADD COLUMN qpay_payment_status TEXT DEFAULT 'none'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_qpay_invoice ON sales(qpay_invoice_id)")
            logger.info("Migration: QPay columns added to sales table")

        # Migration: Create qpay_pending table for pre-sale invoice tracking
        conn.execute("""CREATE TABLE IF NOT EXISTS qpay_pending (
            invoice_id TEXT PRIMARY KEY,
            cart_data TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            paid_amount INTEGER DEFAULT 0,
            sale_id INTEGER DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            paid_at TEXT DEFAULT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qpay_pending_status ON qpay_pending(status)")
        cursor = conn.execute("PRAGMA table_info(qpay_pending)")
        qp_cols = [c[1] for c in cursor.fetchall()]
        if 'invoice_code' not in qp_cols:
            try:
                conn.execute("ALTER TABLE qpay_pending ADD COLUMN invoice_code TEXT DEFAULT ''")
            except Exception:
                logger.warning("Unhandled exception in: except Exception:")
                pass
        # Migration: Drop shifts table (shift management removed)
        conn.execute("DROP TABLE IF EXISTS shifts")

        # Migration: Add discount_amount column to sale_items
        cursor = conn.execute("PRAGMA table_info(sale_items)")
        si_cols = [c[1] for c in cursor.fetchall()]
        if 'discount_amount' not in si_cols:
            try:
                conn.execute("ALTER TABLE sale_items ADD COLUMN discount_amount INTEGER DEFAULT 0")
                logger.info("Migration: discount_amount column added to sale_items table")
            except Exception:
                logger.warning("Unhandled exception in: except Exception:")
                pass
        # Migration: Add PAX terminal columns to sales table
        cursor = conn.execute("PRAGMA table_info(sales)")
        col_names = [c[1] for c in cursor.fetchall()]
        if 'terminal_txn_id' not in col_names:
            logger.info("Migration: Adding terminal_txn_id column to sales table...")
            conn.execute("ALTER TABLE sales ADD COLUMN terminal_txn_id TEXT DEFAULT ''")
            logger.info("Migration: terminal_txn_id column added")
        if 'terminal_status' not in col_names:
            logger.info("Migration: Adding terminal_status column to sales table...")
            conn.execute("ALTER TABLE sales ADD COLUMN terminal_status TEXT DEFAULT ''")
            logger.info("Migration: terminal_status column added")

        # Migration: Remove UNIQUE constraint on barcode — items without
        # barcodes (potatoes, carrots, custom items) must not collide.
        cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='products'")
        existing_sql = (cursor.fetchone() or [""])[0]
        has_unique_bc = ('barcode TEXT UNIQUE' in existing_sql or
                         'barcode TEXT NOT NULL UNIQUE' in existing_sql or
                         '"barcode"' in existing_sql and 'UNIQUE' in existing_sql)
        # Also check via PRAGMA index_list for a UNIQUE index on barcode
        unique_indexes = conn.execute("""
            SELECT il.name FROM pragma_index_list('products') il
            JOIN pragma_index_info(il.name) ii ON 1
            WHERE il.\"unique\" = 1 AND ii.name = 'barcode'
        """).fetchall()
        if has_unique_bc or unique_indexes:
            logger.info("Migration: Removing UNIQUE constraint from products.barcode...")
            conn.executescript("""
                PRAGMA foreign_keys=OFF;
                DROP TABLE IF EXISTS products_new;
                CREATE TABLE products_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    barcode TEXT DEFAULT '',
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK(price >= 0),
                    cost_price INTEGER DEFAULT 0,
                    category TEXT DEFAULT 'Бусад',
                    unit TEXT DEFAULT 'ш',
                    expiry_date TEXT DEFAULT '',
                    image_url TEXT DEFAULT '',
                    supplier_id INTEGER DEFAULT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
                INSERT INTO products_new SELECT * FROM products;
                DROP TABLE products;
                ALTER TABLE products_new RENAME TO products;
                PRAGMA foreign_keys=ON;
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id)")
            logger.info("Migration: barcode UNIQUE constraint removed")


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode TEXT DEFAULT '',
    name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK(price >= 0),
    cost_price INTEGER DEFAULT 0,
    category TEXT DEFAULT 'Бусад',
    unit TEXT DEFAULT 'ш',
    expiry_date TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    supplier_id INTEGER DEFAULT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    address TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS cashiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pin_hash TEXT NOT NULL,
    role TEXT DEFAULT 'cashier' CHECK(role IN ('cashier', 'manager')),
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cashier_id INTEGER,
    payment_type TEXT DEFAULT 'cash' CHECK(payment_type IN ('cash', 'card', 'split', 'qr', 'return')),
    subtotal INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    cash_given INTEGER DEFAULT 0,
    change_given INTEGER DEFAULT 0,
    card_amount INTEGER DEFAULT 0,
    cash_amount INTEGER DEFAULT 0,
    ebarimt_id TEXT DEFAULT '',
    ebarimt_qr TEXT DEFAULT '',
    ebarimt_status TEXT DEFAULT 'pending'
        CHECK(ebarimt_status IN ('pending', 'sent', 'failed', 'skipped')),
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    return_of_sale_id INTEGER DEFAULT NULL,
    qpay_invoice_id TEXT DEFAULT '',
    qpay_payment_status TEXT DEFAULT 'none',
    FOREIGN KEY (cashier_id) REFERENCES cashiers(id)
);

CREATE TABLE IF NOT EXISTS qpay_pending (
    invoice_id TEXT PRIMARY KEY,
    cart_data TEXT NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    paid_amount INTEGER DEFAULT 0,
    sale_id INTEGER DEFAULT NULL,
    invoice_code TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    paid_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS cash_drawer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL CHECK(action IN ('open', 'close', 'float_in', 'float_out')),
    amount INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    sale_id INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER,
    product_name TEXT NOT NULL,
    barcode TEXT DEFAULT '',
    quantity REAL NOT NULL,
    unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
    subtotal INTEGER NOT NULL DEFAULT 0,
    discount_amount INTEGER DEFAULT 0,
    FOREIGN KEY (sale_id) REFERENCES sales(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    icon TEXT DEFAULT '📦',
    color TEXT DEFAULT '#6B7280',
    sort_order INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);
CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_sales_ebarimt ON sales(ebarimt_status);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_sales_payment_type ON sales(payment_type);
CREATE INDEX IF NOT EXISTS idx_sale_items_product ON sale_items(product_id);
CREATE INDEX IF NOT EXISTS idx_sales_date_payment ON sales(created_at, payment_type);
CREATE INDEX IF NOT EXISTS idx_sales_return_of ON sales(return_of_sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale_product ON sale_items(sale_id, product_id);

CREATE TABLE IF NOT EXISTS held_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL DEFAULT '',
    items_json TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id TEXT DEFAULT '',
    details TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_held_orders_created ON held_orders(created_at);
"""


def _seed_data(conn):
    default_settings = {
        "store_name": "Моност",
        "store_address": "Улаанбаатар, БЗД, 1-р хороо",
        "store_phone": "70112233",
        "printer_port": "/dev/usb/lp0",
        "ebarimt_api_url": "",
        "ebarimt_ttd": "",
        "ebarimt_branch_id": "",
        "ebarimt_merchant_tin": "",
        "receipt_footer": "Баярлалаа! Дахин үйлчлүүлнэ үү.",
        "last_backup_date": "",
        "admin_password_hash": "",
        "admin_session_timeout_minutes": "480",
        "schema_version": "1",
    }
    for key, value in default_settings.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )


# ─────────────────────────────────────────────
# CATEGORY QUERIES
# ─────────────────────────────────────────────

def get_all_categories():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM categories ORDER BY sort_order, name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_category(name):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None


def create_category(name, icon='📦', color='#6B7280', sort_order=0):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO categories (name, icon, color, sort_order) VALUES (?, ?, ?, ?)",
                (name, icon, color, sort_order)
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_category(cat_id, name=None, icon=None, color=None, sort_order=None):
    with get_db() as conn:
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if icon is not None:
            fields.append("icon = ?")
            params.append(icon)
        if color is not None:
            fields.append("color = ?")
            params.append(color)
        if sort_order is not None:
            fields.append("sort_order = ?")
            params.append(sort_order)
        if not fields:
            return False
        params.append(cat_id)
        conn.execute(
            f"UPDATE categories SET {', '.join(fields)} WHERE id = ?",
            params
        )
        return True


def delete_category(cat_id, reassign_to='Бусад'):
    with get_db() as conn:
        row = conn.execute(
            "SELECT name FROM categories WHERE id = ?", (cat_id,)
        ).fetchone()
        if not row:
            return False
        old_name = row[0]
        if reassign_to != old_name:
            ensure_category(reassign_to)
            conn.execute(
                "UPDATE products SET category = ? WHERE category = ?",
                (reassign_to, old_name)
            )
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        return True


def ensure_category(name, icon=None, color=None):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            updates = []
            params = []
            if icon:
                updates.append("icon = ?")
                params.append(icon)
            if color:
                updates.append("color = ?")
                params.append(color)
            if updates:
                params.append(existing[0])
                conn.execute(
                    f"UPDATE categories SET {', '.join(updates)} WHERE id = ?",
                    params
                )
            return existing[0]
        conn.execute(
            "INSERT INTO categories (name, icon, color) VALUES (?, ?, ?)",
            (name, icon or '📦', color or '#6B7280')
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ─────────────────────────────────────────────
# SUPPLIER QUERIES
# ─────────────────────────────────────────────

def get_suppliers(include_inactive=False):
    with get_db() as conn:
        query = "SELECT * FROM suppliers"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


def get_supplier(supplier_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE id = ?", (supplier_id,)
        ).fetchone()
        return dict(row) if row else None


def create_supplier(name, contact_person="", phone="", email="", address="", notes=""):
    if not name or not name.strip():
        return None, "Нийлүүлэгчийн нэр хоосон байж болохгүй"
    with get_db() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO suppliers (name, contact_person, phone, email, address, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name.strip(), contact_person.strip(), phone.strip(),
                 email.strip(), address.strip(), notes.strip())
            )
            return cursor.lastrowid, None
        except Exception as e:
            return None, str(e)


def update_supplier(supplier_id, **kwargs):
    allowed = {"name", "contact_person", "phone", "email", "address", "notes", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False, "Шинэчлэх талбар байхгүй"
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [supplier_id]
    with get_db() as conn:
        try:
            conn.execute(f"UPDATE suppliers SET {set_clause} WHERE id = ?", values)
            return True, None
        except Exception as e:
            return False, str(e)


def delete_supplier(supplier_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE suppliers SET is_active = 0 WHERE id = ?", (supplier_id,)
        )
        conn.execute(
            "UPDATE products SET supplier_id = NULL WHERE supplier_id = ?", (supplier_id,)
        )
    return True


# ─────────────────────────────────────────────
# PRODUCT QUERIES
# ─────────────────────────────────────────────

def get_all_products(active_only=True, limit=None, offset=None, category=None):
    with get_db() as conn:
        parts = ["SELECT * FROM products"]
        conds = []
        if active_only:
            conds.append("is_active = 1")
        if category:
            conds.append("category = ?")
        if conds:
            parts.append("WHERE " + " AND ".join(conds))
        parts.append("ORDER BY name")
        if limit is not None:
            parts.append("LIMIT ?")
        if offset is not None:
            parts.append("OFFSET ?")
        sql = " ".join(parts)
        params = []
        if category:
            params.append(category)
        if limit is not None:
            params.append(limit)
        if offset is not None:
            params.append(offset)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_product_by_barcode(barcode):
    if not barcode or not barcode.strip():
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE barcode = ? AND is_active = 1",
            (barcode.strip(),)
        ).fetchone()
        return dict(row) if row else None


def get_product_by_id(product_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None


def create_product(barcode, name, price, category="Бусад",
                   unit="ш", cost_price=0, expiry_date="",
                   image_url="", supplier_id=None):
    if not name or not name.strip():
        return None, "Нэр хоосон байж болохгүй"
    try:
        price = int(price)
        cost_price = int(cost_price) if cost_price else 0
    except (TypeError, ValueError):
        return None, "Үнэ бүхэл тоо байх ёстой"
    if price < 0:
        return None, "Үнэ сөрөг байж болохгүй"
    if cost_price < 0:
        cost_price = 0

    barcode_val = barcode.strip() if barcode else ""

    result = None
    error = None
    with get_db() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO products
                   (barcode, name, price, cost_price, category, unit, expiry_date, image_url, supplier_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (barcode_val, name.strip(), price, cost_price, category.strip(),
                 unit.strip(), expiry_date.strip(),
                 image_url.strip() if image_url else "", int(supplier_id) if supplier_id else None)
            )
            result = cursor.lastrowid
        except sqlite3.IntegrityError:
            if barcode_val:
                error = f"Баркод '{barcode_val}' аль хэдийн бүртгэгдсэн байна"
            else:
                error = "Бараа бүртгэхэд алдаа гарлаа"
    if result:
        ensure_category(category.strip())
    return result, error


def update_product(product_id, **kwargs):
    allowed_fields = {
        "barcode", "name", "price", "cost_price", "category",
        "unit", "expiry_date", "image_url", "supplier_id", "is_active"
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return False, "Шинэчлэх талбар байхгүй"

    if "price" in updates:
        try:
            updates["price"] = int(updates["price"])
        except (TypeError, ValueError):
            return False, "Үнэ бүхэл тоо байх ёстой"
        if updates["price"] < 0:
            return False, "Үнэ сөрөг байж болохгүй"

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [product_id]

    with get_db() as conn:
        try:
            conn.execute(
                f"UPDATE products SET {set_clause} WHERE id = ?", values
            )
        except sqlite3.IntegrityError as e:
            return False, f"Алдаа: {e}"

    if "category" in updates:
        ensure_category(updates["category"])
    return True, None


def delete_product(product_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE products SET is_active = 0 WHERE id = ?", (product_id,)
        )
    return True


def restore_product(product_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE products SET is_active = 1 WHERE id = ?", (product_id,)
        )
    return True


def search_products(query, limit=50):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM products
               WHERE is_active = 1
               AND (name LIKE ? OR barcode LIKE ?)
               ORDER BY name LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# CASH DRAWER QUERIES
# ─────────────────────────────────────────────

def log_cash_drawer(action, amount=0, note=""):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO cash_drawer_log (action, amount, note) VALUES (?, ?, ?)",
            (action, amount or 0, note)
        )

def get_cash_drawer_log(limit=50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM cash_drawer_log ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_cash_drawer_balance():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN action = 'float_in' THEN amount ELSE 0 END), 0) - "
            "COALESCE(SUM(CASE WHEN action = 'float_out' THEN amount ELSE 0 END), 0) AS balance "
            "FROM cash_drawer_log"
        ).fetchone()
        return row["balance"] if row else 0

def get_today_cash_sales():
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(cash_amount), 0) AS cash_total
               FROM sales
               WHERE payment_type IN ('cash', 'split')
               AND created_at >= ? AND created_at < ?
               AND return_of_sale_id IS NULL""",
            (today, today + " 23:59:59")
        ).fetchone()
        return row["cash_total"] if row else 0


# ─────────────────────────────────────────────
# BULK OPERATIONS
# ─────────────────────────────────────────────

def check_idempotency_key(key):
    """Check if an idempotency key was already used. Returns the saved response or None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT response_json FROM idempotency_keys WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return row["response_json"]
    return None


def save_idempotency_key(key, sale_id, response_json):
    """Save an idempotency key after a successful sale."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO idempotency_keys (key, sale_id, response_json) VALUES (?, ?, ?)",
            (key, sale_id, response_json)
        )


def get_profit_summary(date_from=None, date_to=None):
    """Calculate total cost, revenue, and profit for a date range."""
    params = []
    where = ""
    if date_from:
        where += " AND s.created_at >= ?"
        params.append(date_from)
    if date_to:
        where += " AND s.created_at <= ?"
        params.append(date_to + " 23:59:59")

    with get_db() as conn:
        row = conn.execute(
            f"""SELECT
                COALESCE(SUM(si.subtotal), 0) AS total_revenue,
                COALESCE(SUM(si.quantity * COALESCE(p.cost_price, 0)), 0) AS total_cost
               FROM sale_items si
               JOIN sales s ON si.sale_id = s.id
               LEFT JOIN products p ON si.product_id = p.id
               WHERE s.return_of_sale_id IS NULL AND s.payment_type != 'return'{where}""",
            params
        ).fetchone()
        if not row:
            return {"total_revenue": 0, "total_cost": 0, "profit": 0, "margin": 0}
        revenue = row["total_revenue"] or 0
        cost = row["total_cost"] or 0
        profit = revenue - cost
        margin = round((profit / revenue * 100), 1) if revenue > 0 else 0
        return {
            "total_revenue": revenue,
            "total_cost": cost,
            "profit": profit,
            "margin": margin,
        }


def get_categories():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT category FROM products
               WHERE is_active = 1 ORDER BY category"""
        ).fetchall()
        return [r[0] for r in rows]


# ─────────────────────────────────────────────
# SALE QUOTE / VALIDATION
# ─────────────────────────────────────────────

def quote_sale(items, payment_type="card"):
    """Validate cart items and return authoritative totals without writing a sale."""
    if not items:
        return None, "Сагс хоосон байна"

    if payment_type not in ("cash", "card", "split", "qr"):
        return None, f"Буруу төлбөрийн төрөл: {payment_type}"

    validated_items = []
    with get_db() as conn:
        for item in items:
            qty = item.get("quantity", 0)
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                return None, f"Буруу тоо: {item.get('product_name', '?')}"
            if qty <= 0:
                return None, f"Тоо 0-ээс их байх ёстой: {item.get('product_name', '?')}"

            pid = item.get("product_id")
            barcode = (item.get("barcode") or "").strip()
            product = None
            if pid:
                product = conn.execute(
                    "SELECT id, name, barcode, price, is_active FROM products WHERE id = ?",
                    (pid,)
                ).fetchone()
            elif barcode:
                product = conn.execute(
                    "SELECT id, name, barcode, price, is_active FROM products WHERE barcode = ? AND is_active = 1",
                    (barcode,)
                ).fetchone()

            if product:
                if not product["is_active"]:
                    return None, f"Бараа идэвхгүй: {product['name']}"
                product_id = product["id"]
                product_name = product["name"]
                barcode = product["barcode"] or barcode
                unit_price = int(product["price"])
            else:
                product_id = pid
                product_name = item.get("product_name", "")
                try:
                    unit_price = int(item.get("unit_price", 0))
                except (TypeError, ValueError):
                    return None, f"Буруу үнэ: {product_name or '?'}"
                if unit_price < 0:
                    return None, f"Үнэ сөрөг байж болохгүй: {product_name or '?'}"

            try:
                discount_amount = int(item.get("discount_amount", 0) or 0)
            except (TypeError, ValueError):
                discount_amount = 0
            if discount_amount < 0:
                discount_amount = 0

            subtotal = int(qty * unit_price)
            if discount_amount > subtotal:
                discount_amount = 0
            validated_items.append({
                "product_id": product_id,
                "product_name": product_name,
                "barcode": barcode,
                "quantity": qty,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "discount_amount": discount_amount,
            })

    subtotal = sum(item["subtotal"] for item in validated_items)
    total_discount = sum(item["discount_amount"] for item in validated_items)
    total = subtotal - total_discount
    return {
        "payment_type": payment_type,
        "subtotal": subtotal,
        "total_discount": total_discount,
        "total": total,
        "items": validated_items,
    }, None


# ─────────────────────────────────────────────
# SALE QUERIES
# ─────────────────────────────────────────────

_integrity_check_counter = 0
_integrity_check_lock = threading.Lock()
_integrity_check_interval = 100


def _maybe_integrity_check():
    global _integrity_check_counter
    with _integrity_check_lock:
        _integrity_check_counter += 1
        current = _integrity_check_counter
    if current % _integrity_check_interval == 0:
        try:
            with get_db() as conn:
                result = conn.execute("PRAGMA quick_check").fetchone()
                logger.debug(f"Integrity check (sale #{current}): {result[0]}")
        except Exception as e:
            logger.warning(f"Integrity check failed: {e}")


def create_sale(cashier_id=None, payment_type="cash", items=None, cash_given=0,
                card_amount=0, cash_amount=0, return_of_sale_id=None,
                terminal_txn_id=""):
    """
    Create a sale with server-side stock validation inside the transaction.
    For returns, payment_type='return' and quantities should be negative.
    """
    if not items:
        return None, "Сагс хоосон байна"

    is_return = (payment_type == "return")

    subtotal = 0
    validated_items = []
    for item in items:
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price", 0)
        discount_amount = item.get("discount_amount", 0)

        try:
            qty = float(qty)
        except (TypeError, ValueError):
            return None, f"Буруу тоо: {item.get('product_name', '?')}"

        if not is_return and qty <= 0:
            return None, f"Тоо 0-ээс их байх ёстой: {item.get('product_name', '?')}"
        if is_return and qty >= 0:
            return None, f"Буцаалтын тоо сөрөг байх ёстой: {item.get('product_name', '?')}"

        try:
            unit_price = int(unit_price)
        except (TypeError, ValueError):
            return None, f"Буруу үнэ: {item.get('product_name', '?')}"
        if unit_price < 0:
            return None, f"Үнэ сөрөг байж болохгүй: {item.get('product_name', '?')}"

        try:
            discount_amount = int(discount_amount)
        except (TypeError, ValueError):
            discount_amount = 0
        if discount_amount < 0:
            discount_amount = 0

        item_subtotal = int(qty * unit_price)
        if discount_amount > item_subtotal:
            discount_amount = 0
        subtotal += item_subtotal
        validated_items.append({
            "product_id": item.get("product_id"),
            "product_name": item.get("product_name", ""),
            "barcode": item.get("barcode", ""),
            "quantity": qty,
            "unit_price": unit_price,
            "subtotal": item_subtotal,
            "discount_amount": discount_amount,
        })

    total = subtotal

    # Parse payment amounts early but defer final calculation to inside the transaction
    if is_return:
        change_given = 0
        cash_given = 0
        card_amount = 0
        cash_amount = 0
    else:
        try:
            cash_given = int(cash_given) if cash_given else 0
            card_amount = int(card_amount) if card_amount else 0
            cash_amount = int(cash_amount) if cash_amount else 0
        except (TypeError, ValueError):
            return None, "Буруу төлбөрийн дүн"

    # Write to database with server-side stock validation
    with get_db() as conn:
        # Acquire immediate write lock to prevent TOCTOU race conditions
        conn.execute("BEGIN IMMEDIATE")

        # Verify return isn't already processed (atomic check inside transaction)
        if return_of_sale_id:
            already = conn.execute(
                "SELECT COUNT(*) as cnt FROM sales WHERE return_of_sale_id = ?",
                (return_of_sale_id,)
            ).fetchone()[0]
            if already > 0:
                return None, "Энэ борлуулалт аль хэдийн буцаагдсан"

        # Server-side price validation (inside transaction with write lock)
        if not is_return:
            for item in validated_items:
                pid = item["product_id"]
                if not pid:
                    continue
                product = conn.execute(
                    "SELECT is_active, name, price FROM products WHERE id = ?",
                    (pid,)
                ).fetchone()
                if not product:
                    return None, f"Бараа олдсонгүй: {item['product_name']}"
                if not product["is_active"]:
                    return None, f"Бараа идэвхгүй: {product['name']}"
                # Price validation: use DB price as authoritative source
                if item["unit_price"] != product["price"]:
                    item["unit_price"] = product["price"]
                    item["subtotal"] = int(item["quantity"] * product["price"])

        # Recalculate totals after possible price corrections
        subtotal = sum(item["subtotal"] for item in validated_items)
        total_discount = sum(item["discount_amount"] for item in validated_items)
        total = subtotal - total_discount

        # Calculate payment amounts with the corrected total
        if is_return:
            change_given = 0
            cash_given = 0
            card_amount = 0
        else:
            if payment_type == "cash":
                if cash_given < total:
                    return None, f"Бэлэн мөнгө хүрэлцэхгүй. Нийт: {total:,} ₮, Өгсөн: {cash_given:,} ₮"
                change_given = cash_given - total
                cash_amount = cash_given
                card_amount = 0
            elif payment_type == "card":
                change_given = 0
                cash_given = 0
                cash_amount = 0
                card_amount = total
            elif payment_type == "split":
                total_paid = card_amount + cash_amount
                if total_paid < total:
                    return None, f"Төлбөр хүрэлцэхгүй. Нийт: {total:,} ₮, Төлсөн: {total_paid:,} ₮"
                change_given = 0
                cash_given = 0
            elif payment_type == "qr":
                change_given = 0
                cash_given = 0
                cash_amount = 0
                card_amount = total
            else:
                return None, f"Буруу төлбөрийн төрөл: {payment_type}"

        if return_of_sale_id:
            cursor = conn.execute(
                """INSERT INTO sales
                   (cashier_id, payment_type, subtotal, total,
                    cash_given, change_given, card_amount, cash_amount,
                    ebarimt_status, return_of_sale_id, terminal_txn_id, terminal_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (cashier_id, payment_type, subtotal, total,
                 cash_given, change_given, card_amount, cash_amount,
                 return_of_sale_id, terminal_txn_id, terminal_txn_id and "approved" or "")
            )
        else:
            terminal_status = ""
            if terminal_txn_id:
                terminal_status = "approved"
            cursor = conn.execute(
                """INSERT INTO sales
                   (cashier_id, payment_type, subtotal, total,
                    cash_given, change_given, card_amount, cash_amount,
                    ebarimt_status, terminal_txn_id, terminal_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (cashier_id, payment_type, subtotal, total,
                 cash_given, change_given, card_amount, cash_amount,
                 terminal_txn_id, terminal_status)
            )
        sale_id = cursor.lastrowid

        for item in validated_items:
            conn.execute(
                """INSERT INTO sale_items
                   (sale_id, product_id, product_name, barcode,
                    quantity, unit_price, subtotal, discount_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sale_id, item["product_id"], item["product_name"],
                 item["barcode"], item["quantity"], item["unit_price"],
                 item["subtotal"], item["discount_amount"])
            )
    sale = {
        "id": sale_id,
        "cashier_id": cashier_id,
        "payment_type": payment_type,
        "subtotal": subtotal,
        "total": total,
        "cash_given": cash_given,
        "change_given": change_given,
        "card_amount": card_amount,
        "cash_amount": cash_amount,
        "ebarimt_status": "pending",
        "ebarimt_lottery": "",
        "total_discount": total_discount,
        "return_of_sale_id": return_of_sale_id if is_return else None,
        "terminal_txn_id": terminal_txn_id,
        "terminal_status": terminal_txn_id and "approved" or "",
        "items": validated_items,
    }
    _maybe_integrity_check()
    return sale, None


def process_return(sale_id):
    """
    Atomically process a return/refund in a single transaction.
    Returns (return_sale_dict, error_message).
    """
    sale = get_sale(sale_id)
    if not sale:
        return None, "Борлуулалт олдсонгүй"

    if sale.get("payment_type") == "return":
        return None, "Энэ борлуулалт аль хэдийн буцаагдсан"

    if is_sale_returned(sale_id):
        return None, "Энэ борлуулалт аль хэдийн буцаагдсан"

    # Check return window (default 30 days)
    try:
        from config import get_config
        return_days = int(get_config("return_window_days") or 30)
        sale_date = datetime.strptime(sale.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - sale_date).days > return_days:
            return None, f"Буцаалт хийх хугацаа хэтэрсэн ({return_days} хоног)"
    except (ValueError, TypeError):
        pass  # If date parsing fails, allow the return

    return_items = []
    for item in sale["items"]:
        return_items.append({
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "barcode": item["barcode"],
            "quantity": -item["quantity"],
            "unit_price": item["unit_price"]
        })

    # create_sale with payment_type='return' handles stock restore + sale creation atomically
    return_sale, error = create_sale(
        cashier_id=None,
        payment_type="return",
        items=return_items,
        cash_given=0,
        card_amount=0,
        cash_amount=0,
        return_of_sale_id=sale_id
    )

    if error:
        return None, error

    set_sale_returned(sale_id, return_sale["id"])

    return_sale["cashier_name"] = ""
    return return_sale, None


def get_sale(sale_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if not row:
            return None
        sale = dict(row)
        items = conn.execute(
            "SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)
        ).fetchall()
        sale["items"] = [dict(i) for i in items]

        for item in sale["items"]:
            if item.get("product_id"):
                product = conn.execute(
                    "SELECT category FROM products WHERE id = ?", (item["product_id"],)
                ).fetchone()
                item["category"] = product["category"] if product else "Бусад"
            else:
                item["category"] = "Бусад"

        if sale.get("cashier_id"):
            cashier = conn.execute(
                "SELECT name FROM cashiers WHERE id = ?", (sale["cashier_id"],)
            ).fetchone()
            sale["cashier_name"] = cashier["name"] if cashier else "Тодорхойгүй"
        else:
            sale["cashier_name"] = ""
        return sale


def get_pending_ebarimt_sales():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM sales
               WHERE ebarimt_status IN ('pending', 'failed')
               AND payment_type != 'return'
               ORDER BY created_at ASC"""
        ).fetchall()
        result = []
        for row in rows:
            sale = dict(row)
            items = conn.execute(
                "SELECT * FROM sale_items WHERE sale_id = ?", (sale["id"],)
            ).fetchall()
            sale["items"] = [dict(i) for i in items]
            result.append(sale)
        return result


def is_sale_returned(sale_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM sales WHERE return_of_sale_id = ?",
            (sale_id,)
        ).fetchone()
        return row["cnt"] > 0 if row else False


def set_sale_returned(sale_id, return_sale_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE sales SET return_of_sale_id = ? WHERE id = ?",
            (sale_id, return_sale_id)
        )


def update_sale_ebarimt(sale_id, ebarimt_id="", ebarimt_qr="", status="sent", lottery=""):
    with get_db() as conn:
        conn.execute(
            """UPDATE sales
               SET ebarimt_id = ?, ebarimt_qr = ?, ebarimt_status = ?, ebarimt_lottery = ?
               WHERE id = ?
               AND ebarimt_status IN ('pending', 'failed')""",
            (ebarimt_id, ebarimt_qr, status, lottery, sale_id)
        )


def get_sales_list(date_from=None, date_to=None, limit=100, offset=0):
    with get_db() as conn:
        query = """SELECT s.*, c.name as cashier_name
                   FROM sales s
                   LEFT JOIN cashiers c ON s.cashier_id = c.id
                   WHERE 1=1"""
        params = []

        if date_from:
            query += " AND s.created_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND s.created_at <= ?"
            params.append(date_to + " 23:59:59")

        query += " ORDER BY s.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("cashier_name") is None:
                d["cashier_name"] = ""
            result.append(d)
        return result


def get_sales_count(date_from=None, date_to=None):
    with get_db() as conn:
        query = "SELECT COUNT(*) FROM sales WHERE 1=1"
        params = []
        if date_from:
            query += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND created_at <= ?"
            params.append(date_to + " 23:59:59")
        return conn.execute(query, params).fetchone()[0]


def get_sales_report(date_from=None, date_to=None):
    with get_db() as conn:
        where = ""
        params = []
        if date_from or date_to:
            conditions = []
            if date_from:
                conditions.append("s.created_at >= ?")
                params.append(date_from)
            if date_to:
                conditions.append("s.created_at <= ?")
                params.append(date_to + " 23:59:59")
            where = "WHERE " + " AND ".join(conditions)

        summary = conn.execute(
            f"""SELECT
                COUNT(*) as total_sales,
                COALESCE(SUM(CASE WHEN payment_type != 'return' THEN total ELSE 0 END), 0) as total_revenue,
                COALESCE(SUM(CASE WHEN payment_type='cash' AND payment_type != 'return' THEN total ELSE 0 END), 0) as cash_total,
                COALESCE(SUM(CASE WHEN payment_type='card' AND payment_type != 'return' THEN total ELSE 0 END), 0) as card_total,
                COALESCE(SUM(CASE WHEN payment_type='split' AND payment_type != 'return' THEN total ELSE 0 END), 0) as split_total,
                COALESCE(SUM(CASE WHEN payment_type='return' THEN total ELSE 0 END), 0) as return_total,
                COALESCE(SUM(CASE WHEN payment_type='return' THEN 1 ELSE 0 END), 0) as return_count,
                COUNT(CASE WHEN payment_type != 'return' THEN 1 END) as non_return_count
                FROM sales s {where}""",
            params
        ).fetchone()

        daily = conn.execute(
            f"""SELECT
                DATE(created_at) as sale_date,
                COUNT(*) as count,
                SUM(CASE WHEN payment_type != 'return' THEN total ELSE 0 END) as daily_total,
                SUM(CASE WHEN payment_type = 'return' THEN 1 ELSE 0 END) as return_count
                FROM sales s {where}
                GROUP BY DATE(created_at)
                ORDER BY sale_date DESC""",
            params
        ).fetchall()

        hourly = conn.execute(
            f"""SELECT
                CAST(strftime('%H', created_at) AS INTEGER) as hour,
                COUNT(*) as count,
                COALESCE(SUM(CASE WHEN payment_type != 'return' THEN total ELSE 0 END), 0) as total
                FROM sales s {where}
                GROUP BY hour
                ORDER BY hour""",
            params
        ).fetchall()

        # Build hourly array for all 24 hours
        hourly_map = {r['hour']: {'count': r['count'], 'total': r['total']} for r in hourly}
        hourly_full = []
        for h in range(24):
            hourly_full.append({
                'hour': str(h).zfill(2) + ':00',
                'count': hourly_map[h]['count'] if h in hourly_map else 0,
                'total': hourly_map[h]['total'] if h in hourly_map else 0
            })

        # Avg items per sale (non-return)
        avg_items_sql = """SELECT COALESCE(AVG(item_count), 0) as avg_items
            FROM (
                SELECT COUNT(*) as item_count FROM sale_items si
                WHERE si.sale_id IN (SELECT id FROM sales WHERE payment_type != 'return'"""
        avg_items_params = []
        if date_from:
            avg_items_sql += " AND created_at >= ?"
            avg_items_params.append(date_from)
        if date_to:
            avg_items_sql += " AND created_at <= ?"
            avg_items_params.append(date_to + " 23:59:59")
        avg_items_sql += "))"
        avg_items = conn.execute(avg_items_sql, avg_items_params).fetchone()

        # Exclude return sales from top products
        top_where = "WHERE si.sale_id IN (SELECT id FROM sales WHERE payment_type != 'return')"
        top_params = []
        if date_from:
            top_where += " AND si.sale_id IN (SELECT id FROM sales WHERE created_at >= ?)"
            top_params.append(date_from)
        if date_to:
            top_where += " AND si.sale_id IN (SELECT id FROM sales WHERE created_at <= ?)"
            top_params.append(date_to + " 23:59:59")

        top_products = conn.execute(
            f"""SELECT
                si.product_name,
                p.category,
                SUM(si.quantity) as total_qty,
                SUM(si.subtotal) as total_revenue
                FROM sale_items si
                LEFT JOIN products p ON si.product_id = p.id
                {top_where}
                GROUP BY si.product_name
                ORDER BY total_revenue DESC
                LIMIT 20""",
            top_params
        ).fetchall()

        category_breakdown = conn.execute(
            f"""SELECT
                COALESCE(p.category, 'Бусад') as category,
                SUM(si.quantity) as total_qty,
                SUM(si.subtotal) as total_revenue
                FROM sale_items si
                LEFT JOIN products p ON si.product_id = p.id
                {top_where}
                GROUP BY p.category
                ORDER BY total_revenue DESC""",
            top_params
        ).fetchall()

        s = dict(summary) if summary else {}
        non_return = s.get('non_return_count', 0) or 1
        avg_transaction = s['total_revenue'] // non_return if non_return else 0

        return {
            "summary": s,
            "daily": [dict(d) for d in daily],
            "hourly": hourly_full,
            "top_products": [dict(p) for p in top_products],
            "category_breakdown": [dict(c) for c in category_breakdown],
            "avg_items_per_sale": round(avg_items['avg_items'], 1) if avg_items else 0,
            "avg_transaction": avg_transaction,
        }


# ─────────────────────────────────────────────
# ADMIN PASSWORD FUNCTIONS
# ─────────────────────────────────────────────

def get_admin_password_hash():
    return get_setting("admin_password_hash", "")


def set_admin_password_hash(password_hash):
    set_setting("admin_password_hash", password_hash)


def verify_admin_password(password):
    stored_hash = get_admin_password_hash()
    if not stored_hash:
        return False
    result = verify_password(password, stored_hash)
    if result and BCRYPT_AVAILABLE and _is_sha256_hash(stored_hash):
        set_admin_password_hash(hash_password(password))
    return result


def is_admin_password_set():
    return bool(get_admin_password_hash())


def set_admin_password(password):
    if not password or len(password) < 4:
        return False, "Нууц үг дор хаяж 4 тэмдэгт байх ёстой"
    password_hash = hash_password(password)
    set_admin_password_hash(password_hash)
    return True, None


def change_admin_password(current_password, new_password):
    if not verify_admin_password(current_password):
        return False, "Одоогийн нууц үг буруу"
    return set_admin_password(new_password)


# ─────────────────────────────────────────────
# SETTINGS QUERIES
# ─────────────────────────────────────────────

def get_setting(key, default=""):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def get_all_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def set_setting(key, value):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
    try:
        from config import invalidate_settings_cache
        invalidate_settings_cache()
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
def set_settings(settings_dict):
    with get_db() as conn:
        for key, value in settings_dict.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )


# ─────────────────────────────────────────────
# BACKUP
# ─────────────────────────────────────────────

def perform_daily_backup():
    today = datetime.now().strftime("%Y-%m-%d")
    last_backup = get_setting("last_backup_date", "")

    if last_backup == today:
        return True, "Өнөөдрийн нөөц хуулбар аль хэдийн хийгдсэн"

    return perform_manual_backup()


def verify_backup(backup_path):
    import shutil
    if not os.path.exists(backup_path):
        logger.error(f"Backup verification failed: file not found — {backup_path}")
        return False
    tmp_path = backup_path + ".verify_tmp"
    try:
        shutil.copy2(backup_path, tmp_path)
        conn = sqlite3.connect(tmp_path)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        ok = result[0] == "ok"
        if ok:
            logger.info(f"Backup verified OK: {backup_path}")
        else:
            logger.error(f"Backup integrity check FAILED: {backup_path} — {result[0]}")
        return ok
    except Exception as e:
        logger.error(f"Backup verification error for {backup_path}: {e}")
        return False
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            logger.warning("Unhandled exception in: except OSError:")
            pass
def perform_manual_backup():
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_filename = f"pos_{today}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    source = None
    dest = None
    try:
        source = get_connection()
        dest = sqlite3.connect(backup_path)
        source.backup(dest)

        dest.close()
        dest = None
        source.close()
        source = None

        verify_ok = verify_backup(backup_path)
        if not verify_ok:
            logger.warning(f"Backup created but integrity check failed: {backup_filename}")

        set_setting("last_backup_date", today)
        _cleanup_old_backups()

        logger.info(f"Backup created: {backup_path} (verified={verify_ok})")
        return True, f"Нөөц хуулбар амжилттай: {backup_filename}"
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False, f"Нөөц хуулбар амжилтгүй: {e}"
    finally:
        if dest:
            dest.close()
        if source:
            source.close()


def _cleanup_old_backups():
    cutoff = datetime.now() - timedelta(days=30)
    try:
        for filename in os.listdir(BACKUP_DIR):
            if not filename.startswith("pos_") or not filename.endswith(".db"):
                continue
            filepath = os.path.join(BACKUP_DIR, filename)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if file_mtime < cutoff:
                os.remove(filepath)
                logger.info(f"Deleted old backup: {filename}")
    except Exception as e:
        logger.error(f"Backup cleanup error: {e}")


def check_and_backup():
    today = datetime.now().strftime("%Y-%m-%d")
    last_backup = get_setting("last_backup_date", "")
    if last_backup != today:
        perform_daily_backup()


# ─────────────────────────────────────────────
# HELD ORDERS (Suspended / Parked carts)
# ─────────────────────────────────────────────

def create_held_order(label, items, total):
    import json as _json
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO held_orders (label, items_json, total) VALUES (?, ?, ?)",
            (label, _json.dumps(items), total)
        )
        return cursor.lastrowid


def get_held_orders():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, label, items_json, total, created_at FROM held_orders ORDER BY created_at DESC"
        ).fetchall()
        import json as _json
        result = []
        for r in rows:
            d = dict(r)
            d["items"] = _json.loads(d.pop("items_json", "[]"))
            result.append(d)
        return result


def get_held_order(order_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, label, items_json, total, created_at FROM held_orders WHERE id = ?",
            (order_id,)
        ).fetchone()
        if not row:
            return None
        import json as _json
        d = dict(row)
        d["items"] = _json.loads(d.pop("items_json", "[]"))
        return d


def delete_held_order(order_id):
    with get_db() as conn:
        conn.execute("DELETE FROM held_orders WHERE id = ?", (order_id,))


def check_db_integrity():
    try:
        with get_db() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result[0] == "ok"
    except Exception:
        return False


def _get_schema_version():
    try:
        v = get_setting("schema_version", "0")
        return int(v)
    except Exception:
        return 0


_ebarimt_locks: dict = {}


def acquire_ebarimt_retry_lock(lock_id, timeout_minutes=30):
    import time as _time
    now = _time.time()
    _cleanup_expired = [
        k for k, v in _ebarimt_locks.items()
        if v < now - (timeout_minutes * 60)
    ]
    for k in _cleanup_expired:
        _ebarimt_locks.pop(k, None)
    if lock_id in _ebarimt_locks:
        return False
    _ebarimt_locks[lock_id] = now
    return True


def release_ebarimt_retry_lock(lock_id):
    _ebarimt_locks.pop(lock_id, None)


def log_audit(action, entity_type, entity_id="", details=""):
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO audit_log (action, entity_type, entity_id, details) VALUES (?, ?, ?, ?)",
                (action, entity_type, str(entity_id or ""), details)
            )
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
def start_wal_checkpoint_thread():
    import threading as _t
    import time as _time
    def _checkpoint_loop():
        while True:
            _time.sleep(120)
            try:
                with get_db() as conn:
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                logger.warning("Unhandled exception in: except Exception:")
                pass
    _t.Thread(target=_checkpoint_loop, daemon=True, name="wal-checkpoint").start()


def get_product_count(active_only=True, category=None):
    with get_db() as conn:
        if category:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM products WHERE is_active = 1 AND category = ?",
                (category,)
            ).fetchone()
        elif active_only:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM products WHERE is_active = 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM products"
            ).fetchone()
        return row["cnt"] if row else 0


def get_categories_from_products(products):
    seen = set()
    result = []
    for p in products:
        cat = p.get("category") if isinstance(p, dict) else p["category"]
        if cat and cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


def claim_idempotency_key(key):
    with get_db() as conn:
        row = conn.execute(
            "SELECT key FROM idempotency_keys WHERE key = ?",
            (key,)
        ).fetchone()
        if row:
            return False
        conn.execute(
            "INSERT INTO idempotency_keys (key, sale_id, response_json) VALUES (?, 0, '')",
            (key,)
        )
        return True


def audit_orphans():
    orphans = {}
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT si.id, si.sale_id, si.product_name FROM sale_items si "
                "WHERE si.sale_id NOT IN (SELECT id FROM sales)"
            ).fetchall()
            if rows:
                orphans["sale_items_orphans"] = [dict(r) for r in rows]
                logger.warning(f"FK audit: found {len(rows)} orphaned sale_items "
                               f"(sale_id references non-existent sales)")
    except Exception as e:
        logger.warning(f"FK audit failed: {e}")
    return orphans

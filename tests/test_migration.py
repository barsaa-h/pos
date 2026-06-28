import sqlite3
import pytest

import database as db


def test_empty_migration_ok():
    assert db.check_db_integrity() is True
    with db.get_db() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        assert cnt > 0  # settings table is seeded


def test_migrate_db_idempotent():
    with db.get_db() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('migrate_test', '1')")
    db.migrate_db()
    db.migrate_db()
    assert db.check_db_integrity() is True


def test_migrate_db_adds_missing_columns():
    """Verify migrate_db adds columns that may be missing from an older schema."""
    with db.get_db() as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(sales)").fetchall()]
    for required in ("return_of_sale_id", "qpay_invoice_id", "qpay_payment_status"):
        assert required in cols, f"Missing column after migration: {required}"


def test_migrate_db_makes_cashier_id_nullable():
    with db.get_db() as conn:
        cols = conn.execute("PRAGMA table_info(sales)").fetchall()
        col = [c for c in cols if c[1] == "cashier_id"][0]
        assert col[3] == 0, "cashier_id should be nullable (0 = no NOT NULL)"


def test_migrate_db_removes_quantity_check():
    with db.get_db() as conn:
        # Create a minimal sale to reference
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO sales (cashier_id, payment_type, subtotal, total) "
            "VALUES (NULL, 'cash', 0, 0)"
        )
        sid = conn.execute("SELECT MAX(id) FROM sales").fetchone()[0]
        result = conn.execute(
            "INSERT INTO sale_items (sale_id, product_name, quantity, unit_price, subtotal) "
            "VALUES (?, 'test', -1, 0, 0)", (sid,)
        )
        conn.execute("DELETE FROM sale_items WHERE sale_id=?", (sid,))
        conn.execute("PRAGMA foreign_keys=ON")
    assert result.rowcount == 1


def test_schema_version_present():
    version = db._get_schema_version()
    assert version >= 1

def test_create_product(db, request):
    bc = f"tcp_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, category, unit) VALUES (?, ?, ?, ?, ?)",
        (bc, "Туршилтын бүтээгдэхүүн", 5000, "Бусад", "ш")
    )
    row = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()
    assert row is not None
    assert row["name"] == "Туршилтын бүтээгдэхүүн"
    assert row["price"] == 5000


def test_create_product_duplicate_barcode(db, request):
    from database import create_product
    bc = f"cpd_{request.node.name}"
    create_product(bc, "Эхний бүтээгдэхүүн", 3000, "Бусад", "ш")
    # Barcode no longer unique; duplicate allowed
    result_id, error = create_product(bc, "Хоёр дахь бүтээгдэхүүн", 5000, "Бусад", "ш")
    assert result_id is not None
    assert error is None


def test_get_product_by_barcode(db, request):
    bc = f"gpb_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, category, unit) VALUES (?, ?, ?, ?, ?)",
        (bc, "Бараа", 2500, "Бусад", "ш")
    )
    db.commit()
    from database import get_product_by_barcode
    product = get_product_by_barcode(bc)
    assert product is not None
    assert product["name"] == "Бараа"
    assert product["price"] == 2500

    missing = get_product_by_barcode("nonexistent_barcode")
    assert missing is None


def test_update_product(db, request):
    bc = f"up_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, category, unit) VALUES (?, ?, ?, ?, ?)",
        (bc, "Хуучин нэр", 1000, "Бусад", "ш")
    )
    db.commit()
    from database import update_product
    p = db.execute("SELECT id FROM products WHERE barcode = ?", (bc,)).fetchone()
    success, _ = update_product(p["id"], name="Шинэ нэр", price=2000)
    assert success is True
    row = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()
    assert row["name"] == "Шинэ нэр"
    assert row["price"] == 2000


def test_restore_product(db, request):
    bc = f"rp_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, category, unit, is_active) VALUES (?, ?, ?, ?, ?, ?)",
        (bc, "Устгасан бараа", 3000, "Бусад", "ш", 0)
    )
    db.commit()
    from database import restore_product
    p = db.execute("SELECT id FROM products WHERE barcode = ?", (bc,)).fetchone()
    result = restore_product(p["id"])
    assert result is True
    row = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()

    assert row["is_active"] == 1


def test_create_sale_and_get_sale(db, request):
    from database import create_product, get_sale, create_sale
    bc1, bc2 = f"cs1_{request.node.name}", f"cs2_{request.node.name}"
    create_product(bc1, "Бараа 1", 1000, "Бусад", "ш")
    create_product(bc2, "Бараа 2", 2000, "Бусад", "ш")

    p1 = db.execute("SELECT * FROM products WHERE barcode = ?", (bc1,)).fetchone()
    p2 = db.execute("SELECT * FROM products WHERE barcode = ?", (bc2,)).fetchone()

    result, error = create_sale(
        items=[
            {"product_id": p1["id"], "product_name": "Бараа 1", "barcode": bc1, "quantity": 2, "unit_price": 1000, "subtotal": 2000},
            {"product_id": p2["id"], "product_name": "Бараа 2", "barcode": bc2, "quantity": 1, "unit_price": 2000, "subtotal": 2000},
        ],
        payment_type="cash",
        cash_given=5000,
    )
    assert error is None
    assert result is not None
    assert result["total"] == 4000
    assert result["payment_type"] == "cash"

    fetched = get_sale(result["id"])
    assert fetched is not None
    assert fetched["total"] == 4000
    assert len(fetched["items"]) == 2


def test_create_sale_inactive_product(db, request):
    bc = f"cip_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, is_active) VALUES (?, ?, ?, ?)",
        (bc, "Идэвхгүй", 1000, 0)
    )
    db.commit()
    p = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()

    from database import create_sale
    result, error = create_sale(
        items=[
            {"product_id": p["id"], "product_name": "Идэвхгүй", "barcode": bc, "quantity": 1, "unit_price": 1000, "subtotal": 1000},
        ],
        payment_type="cash",
    )
    assert error is not None
    assert result is None


def test_process_return(db, request):
    from database import create_product, create_sale, process_return
    bc = f"pr_{request.node.name}"
    create_product(bc, "Буцаалт бараа", 5000, "Бусад", "ш")
    p = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()

    orig, error = create_sale(
        items=[{"product_id": p["id"], "product_name": "Буцаалт бараа", "barcode": bc, "quantity": 2, "unit_price": 5000, "subtotal": 10000}],
        payment_type="cash",
        cash_given=10000,
    )
    assert error is None, f"create_sale error: {error}"
    db.commit()

    ret, error = process_return(orig["id"])
    assert error is None
    assert ret is not None
    assert ret["return_of_sale_id"] == orig["id"]
    assert ret["total"] == -10000
    db.commit()


def test_process_return_double_return_blocked(db, request):
    from database import create_product, create_sale, process_return
    bc = f"pdr_{request.node.name}"
    create_product(bc, "Давхар буцаалт", 3000, "Бусад", "ш")
    p = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()

    orig, _ = create_sale(
        items=[{"product_id": p["id"], "product_name": "Давхар буцаалт", "barcode": bc, "quantity": 1, "unit_price": 3000, "subtotal": 3000}],
        payment_type="cash",
        cash_given=3000,
    )

    process_return(orig["id"])
    result, error = process_return(orig["id"])
    assert error is not None
    assert "буцаагдсан" in error
    assert result is None


def test_get_pending_ebarimt_sales(db, request):
    from database import create_product, create_sale, get_pending_ebarimt_sales
    bc = f"gpes_{request.node.name}"
    create_product(bc, "Хүлээгдэж буй", 1000, "Бусад", "ш")
    p = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()
    create_sale(
        items=[{"product_id": p["id"], "product_name": "Хүлээгдэж буй", "barcode": bc, "quantity": 1, "unit_price": 1000, "subtotal": 1000}],
        payment_type="cash",
        cash_given=1000,
    )

    pending = get_pending_ebarimt_sales()
    assert len(pending) >= 1


def test_update_sale_ebarimt(db, request):
    from database import create_product, create_sale, update_sale_ebarimt
    bc = f"use_{request.node.name}"
    create_product(bc, "eBarimt тест", 2000, "Бусад", "ш")
    p = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()
    sale, _ = create_sale(
        items=[{"product_id": p["id"], "product_name": "eBarimt тест", "barcode": bc, "quantity": 1, "unit_price": 2000, "subtotal": 2000}],
        payment_type="cash",
        cash_given=2000,
    )

    update_sale_ebarimt(sale["id"], ebarimt_id="REC123", ebarimt_qr="QRDATA", lottery="LOT456", status="sent")
    row = db.execute("SELECT * FROM sales WHERE id = ?", (sale["id"],)).fetchone()
    assert row["ebarimt_id"] == "REC123"
    assert row["ebarimt_qr"] == "QRDATA"
    assert row["ebarimt_lottery"] == "LOT456"
    assert row["ebarimt_status"] == "sent"


def test_settings_get_set(db):
    from database import set_setting
    from config import get_config
    set_setting("test_key", "test_value")
    val = get_config("test_key")
    assert val == "test_value"

    missing = get_config("nonexistent_key")
    assert missing == ""


def test_get_store_info(db):
    from config import get_store_info
    info = get_store_info()
    assert info["name"] == "Моност"
    assert info["address"] == "Улаанбаатар, БЗД, 1-р хороо"
    assert info["phone"] == "70112233"


def test_get_sales_crud(db):
    from database import get_sales_list
    sales = get_sales_list()
    assert isinstance(sales, list)


def test_weighted_product_sale(db):
    from database import create_product, create_sale
    bc = "weight_test_001"
    pid, err = create_product(bc, "Жинтэй бараа", 5000, "Бусад", unit="кг")
    assert pid is not None
    assert err is None

    sale, err = create_sale(
        items=[{"product_id": pid, "product_name": "Жинтэй бараа", "barcode": bc, "quantity": 0.5, "unit_price": 5000, "subtotal": 2500}],
        payment_type="cash",
        cash_given=2500,
    )
    assert err is None
    assert sale is not None


def test_weighted_product_return(db):
    from database import create_product, create_sale, process_return
    bc = "weight_ret_001"
    pid, err = create_product(bc, "Буцаах жинтэй", 3000, "Бусад", unit="л")
    assert pid is not None

    sale, err = create_sale(
        items=[{"product_id": pid, "product_name": "Буцаах жинтэй", "barcode": bc, "quantity": 1.5, "unit_price": 3000, "subtotal": 4500}],
        payment_type="cash",
        cash_given=4500,
    )
    assert err is None

    ret_sale, err = process_return(sale["id"])
    assert err is None


def test_db_integrity_check(db):
    from database import check_db_integrity
    result = check_db_integrity()
    assert result is True


def test_backup_integrity_check(db):
    from database import perform_manual_backup
    success, msg = perform_manual_backup()
    assert success is True


def test_schema_version_applied(db):
    from database import _get_schema_version
    version = _get_schema_version()
    assert version >= 1


def test_ebarimt_retry_lock(db):
    from database import acquire_ebarimt_retry_lock, release_ebarimt_retry_lock
    lock_id = "test_lock_proc"

    acquired = acquire_ebarimt_retry_lock(lock_id, timeout_minutes=1)
    assert acquired is True

    acquired2 = acquire_ebarimt_retry_lock(lock_id, timeout_minutes=1)
    assert acquired2 is False

    release_ebarimt_retry_lock(lock_id)

    acquired3 = acquire_ebarimt_retry_lock(lock_id, timeout_minutes=1)
    assert acquired3 is True

    release_ebarimt_retry_lock(lock_id)


def test_empty_barcode_allowed(db):
    from database import create_product
    pid, err = create_product("", "Баркодгүй бараа", 5000, "Бусад", "ш")
    assert pid is not None
    assert err is None
    product = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    assert product is not None
    assert product["barcode"] == ""
    assert product["name"] == "Баркодгүй бараа"


def test_create_sale_with_discount(db):
    from database import create_product, create_sale, get_sale
    bc = "disc_test_001"
    pid, err = create_product(bc, "Хөнгөлөлттэй бараа", 10000, "Бусад", "ш")
    assert pid is not None

    sale, err = create_sale(
        items=[{
            "product_id": pid, "product_name": "Хөнгөлөлттэй бараа",
            "barcode": bc, "quantity": 2, "unit_price": 10000,
            "subtotal": 20000, "discount_amount": 3000
        }],
        payment_type="cash",
        cash_given=20000,
    )
    assert err is None
    assert sale is not None
    full_sale = get_sale(sale["id"])
    assert full_sale is not None
    item = full_sale["items"][0]
    assert item["discount_amount"] == 3000


def test_input_validation_length_limits(db):
    from database import create_product
    long_barcode = "A" * 65
    pid, err = create_product(long_barcode, "Урт баркод", 1000, "Бусад", "ш")
    assert pid is not None
    assert err is None


def test_verify_backup_valid(monkeypatch):
    import tempfile, os, sqlite3
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x int)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.close()

    from database import verify_backup
    assert verify_backup(path) is True
    os.unlink(path)


def test_verify_backup_missing():
    from database import verify_backup
    assert verify_backup("/nonexistent/path.db") is False


def test_verify_backup_corrupt(monkeypatch):
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(b"not a real sqlite database")

    from database import verify_backup
    assert verify_backup(path) is False
    os.unlink(path)


def test_audit_orphans_finds_none(db):
    from database import audit_orphans
    result = audit_orphans()
    assert result == {}


def test_maybe_integrity_check(db):
    from database import _maybe_integrity_check
    for _ in range(3):
        _maybe_integrity_check()


def test_check_db_integrity(db):
    from database import check_db_integrity
    assert check_db_integrity() is True


def test_perform_manual_backup(db):
    from database import perform_manual_backup, BACKUP_DIR, verify_backup
    import os
    success, msg = perform_manual_backup()
    assert success is True
    backup_files = os.listdir(BACKUP_DIR)
    assert len(backup_files) >= 1
    backup_path = os.path.join(BACKUP_DIR, backup_files[0])
    assert verify_backup(backup_path) is True

def test_create_product(db, request):
    bc = f"tcp_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, category, stock_qty, unit) VALUES (?, ?, ?, ?, ?, ?)",
        (bc, "Туршилтын бүтээгдэхүүн", 5000, "Бусад", 10, "ш")
    )
    row = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()
    assert row is not None
    assert row["name"] == "Туршилтын бүтээгдэхүүн"
    assert row["price"] == 5000
    assert row["stock_qty"] == 10


def test_create_product_duplicate_barcode(db, request):
    from database import create_product
    bc = f"cpd_{request.node.name}"
    create_product(bc, "Эхний бүтээгдэхүүн", 3000, "Бусад", 5, "ш")
    result_id, error = create_product(bc, "Хоёр дахь бүтээгдэхүүн", 5000, "Бусад", 10, "ш")
    assert result_id is None
    assert error is not None
    assert "аль хэдийн" in error


def test_get_product_by_barcode(db, request):
    bc = f"gpb_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, category, stock_qty, unit) VALUES (?, ?, ?, ?, ?, ?)",
        (bc, "Бараа", 2500, "Бусад", 3, "ш")
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
        "INSERT INTO products (barcode, name, price, category, stock_qty, unit) VALUES (?, ?, ?, ?, ?, ?)",
        (bc, "Хуучин нэр", 1000, "Бусад", 5, "ш")
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
        "INSERT INTO products (barcode, name, price, category, stock_qty, unit, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (bc, "Устгасан бараа", 3000, "Бусад", 0, "ш", 0)
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
    create_product(bc1, "Бараа 1", 1000, "Бусад", 10, "ш")
    create_product(bc2, "Бараа 2", 2000, "Бусад", 5, "ш")

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


def test_create_sale_insufficient_stock(db, request):
    from database import create_product, create_sale
    bc = f"cis_{request.node.name}"
    create_product(bc, "Бага нөөц", 1000, "Бусад", 1, "ш")
    p = db.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()

    result, error = create_sale(
        items=[
            {"product_id": p["id"], "product_name": "Бага нөөц", "barcode": bc, "quantity": 5, "unit_price": 1000, "subtotal": 5000},
        ],
        payment_type="cash",
    )
    assert error is not None
    assert "хүрэлцэхгүй" in error
    assert result is None


def test_create_sale_inactive_product(db, request):
    bc = f"cip_{request.node.name}"
    db.execute(
        "INSERT INTO products (barcode, name, price, stock_qty, is_active) VALUES (?, ?, ?, ?, ?)",
        (bc, "Идэвхгүй", 1000, 10, 0)
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
    create_product(bc, "Буцаалт бараа", 5000, "Бусад", 10, "ш")
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

    stock = db.execute("SELECT stock_qty FROM products WHERE id = ?", (p["id"],)).fetchone()
    assert stock["stock_qty"] == 10


def test_process_return_double_return_blocked(db, request):
    from database import create_product, create_sale, process_return
    bc = f"pdr_{request.node.name}"
    create_product(bc, "Давхар буцаалт", 3000, "Бусад", 5, "ш")
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
    create_product(bc, "Хүлээгдэж буй", 1000, "Бусад", 10, "ш")
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
    create_product(bc, "eBarimt тест", 2000, "Бусад", 10, "ш")
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
    assert info["name"] == "Миний дэлгүүр"
    assert info["address"] == "Улаанбаатар, БЗД, 1-р хороо"
    assert info["phone"] == "70112233"


def test_get_sales_crud(db):
    from database import get_sales_list
    sales = get_sales_list()
    assert isinstance(sales, list)


def test_check_db_integrity(db):
    from database import check_db_integrity
    assert check_db_integrity() is True


def test_get_ebarimt_failed_count(db):
    from database import get_ebarimt_failed_count
    count = get_ebarimt_failed_count()
    assert isinstance(count, int)
    assert count >= 0


def test_quote_sale(db):
    from database import quote_sale
    items = [{"product_name": "Test", "quantity": 2, "unit_price": 500, "subtotal": 1000}]
    quote, error = quote_sale(items, payment_type="card")
    assert error is None
    assert quote["subtotal"] == 1000
    assert quote["total"] == 1000


def test_log_audit(db):
    from database import log_audit
    log_audit("test_action", "test_entity", entity_id="1", details="test details")
    row = db.execute("SELECT * FROM audit_log WHERE action = ?", ("test_action",)).fetchone()
    assert row is not None
    assert row["entity_type"] == "test_entity"
    assert row["entity_id"] == "1"


def test_create_cashier(db, request):
    from database import create_cashier, get_cashier, verify_cashier_pin
    cid, error = create_cashier("Кассчин 1", "1234", role="cashier")
    assert error is None
    assert cid is not None
    cashier = get_cashier(cid)
    assert cashier["name"] == "Кассчин 1"
    assert cashier["role"] == "cashier"
    assert verify_cashier_pin(cid, "1234") is True
    assert verify_cashier_pin(cid, "0000") is False


def test_get_all_cashiers(db, request):
    from database import create_cashier, get_cashiers, delete_cashier
    create_cashier("Кассчин 2", "5678")
    create_cashier("Кассчин 3", "9012")
    cashiers = get_cashiers()
    assert len(cashiers) >= 2
    delete_cashier(cashiers[0]["id"])
    active = get_cashiers(include_inactive=False)
    assert len(active) < len(cashiers)


def test_invalidate_settings_cache():
    from config import invalidate_settings_cache, get_config, _SETTINGS_CACHE
    _SETTINGS_CACHE["test_x"] = "cached"
    assert get_config("test_x") == "cached"
    invalidate_settings_cache()
    assert "test_x" not in _SETTINGS_CACHE


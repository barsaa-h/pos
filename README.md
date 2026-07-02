# Миний дэлгүүр — POS / My Store POS

Борлуулалт, нөөц, тайлан, хэвлэгч болон eBarimt-ийн нэгдсэн систем.
Монголын хүнсний дэлгүүрүүдэд зориулсан **production-ready** ПОС (POS) програм.

**GTK Desktop app** — Програмын дүрс дээр double-click хийхэд хоёр native цонх зэрэг нээгдэнэ:
* **Кассчны цонх** — Бараа, сагс, төлбөр, гарын түргэн товчлуурууд
* **Үйлчлүүлэгчийн дэлгэц** — Худалдан авагчид харагдах хоёр дахь дэлгэц

No browser, no `localhost`, no command line needed.

---

## Агуулга / Table of Contents

1. [Эхлүүлэх / Quick Start](#эхлүүлэх--quick-start)
2. [Файлын бүтэц / Project Structure](#файлын-бүтэц--project-structure)
3. [Бүх боломжууд / All Features](#бүх-боломжууд--all-features)
4. [Өгөгдлийн сан / Database](#өгөгдлийн-сан--database)
5. [Гарын товчлуурууд / Keyboard Shortcuts](#гарын-товчлуурууд--keyboard-shortcuts)
6. [Тохиргоо / Configuration](#тохиргоо--configuration)
7. [Тоног төхөөрөмж / Hardware Setup](#тоног-төхөөрөмж--hardware-setup)
8. [Суулгах заавар / Installation](#суулгах-заавар--installation)
9. [eBarimt тохиргоо / eBarimt](#ebarimt-тохиргоо--ebarimt)
10. [Нөөц хуулбар / Backup](#нөөц-хуулбар--backup)
11. [Ээлжийн хаалт / Z-Report](#ээлжийн-хаалт--z-report)
12. [Аюулгүй байдал / Security](#аюулгүй-байдал--security)
13. [Туршилт / Testing](#туршилт--testing)
14. [Алдаа засах / Troubleshooting](#алдаа-засах--troubleshooting)

---

## Эхлүүлэх / Quick Start

### Ubuntu (Linux)

```bash
cd ~/pos
./posgtk-dev.sh
```

Шаардлагатай сангууд / Dependencies:
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-pango-1.0
source venv/bin/activate && pip install -r requirements.txt
```

### Терминалаас ажиллуулах / From Terminal
```bash
cd ~/pos && ./posgtk-dev.sh
```

---

## Файлын бүтэц / Project Structure

```
pos/
├── posgtk/                         ← GTK desktop app (үндсэн програм)
│   ├── main.py                     ← App entry, sidebar+stack, keyboard dispatch
│   ├── pos.py                      ← POS screen (grid, cart, checkout, held orders)
│   ├── sales.py                    ← Sales history, pagination, returns
│   ├── products.py                 ← Product CRUD
│   ├── categories.py               ← Category CRUD
│   ├── suppliers.py                ← Supplier CRUD
│   ├── stock.py                    ← Stock adjustments
│   ├── reports.py                  ← Sales/profit reports
│   ├── settings.py                 ← 7-tab settings
│   ├── customer_display.py         ← Second-monitor customer window
│   ├── login.py                    ← Admin PIN login
│   ├── widgets.py                  ← ProductCard, CartItem, cart rows
│   ├── cache.py                    ← Product cache, prefix search, category CSS
│   ├── theme.py                    ← CSS loader + scaler, dark/light themes
│   ├── workqueue.py                ← Thread pool for async operations
│   ├── scaling.py                  ← DPI-aware scaling
│   ├── dark.css                    ← Dark theme (600+ rules)
│   └── light.css                   ← Light theme (600+ rules)
├── database.py                     ← SQLite schema, migrations, CRUD, backups
├── config.py                       ← Config defaults, DB-backed settings
├── printer.py                      ← ESC/POS thermal printer
├── ebarimt.py                      ← eBarimt API integration
├── tests/
│   ├── conftest.py                 ← Test fixtures (temp DB)
│   ├── test_database.py            ← Database CRUD tests
│   ├── test_ebarimt.py             ← eBarimt adapter tests
│   ├── test_held_orders.py         ← Held order tests
│   └── test_scaling.py             ← DPI scaling tests
├── posgtk-dev.sh                   ← GTK launcher script
├── requirements.txt                ← Python dependencies
├── .env.example                    ← Environment variables
├── VERSION                         ← Version string
├── AGENTS.md                       ← AI development guide
├── static/uploads/                 ← Product images
├── data/                           ← SQLite database location
├── logs/                           ← System logs
└── backups/                        ← Automatic daily backups (30 day retention)
```

---

## Бүх боломжууд / All Features

### Кассчны дэлгэц / Cashier Screen

| Монгол | English | Тайлбар |
|--------|---------|---------|
| Баркод сканнер | Barcode scanner | USB сканнерыг HID гар горимоор уншина. Оролтын талбар үргэлж автоматаар фокуслагдана |
| Барааны карт | Product cards | Эможи дүрс, нэр, үнэ, үлдэгдэл нөөц болон stock bar-тай харагдана |
| Ангиллаар шүүх | Category filter | Түргэн шүүх товчлуурууд |
| Бараа хайх | Product search | `Ctrl+F` товчлуур эсвэл хайлтын талбараар хайна |
| Сагс | Cart | Бараа нэмэх (+), хасах (-), тоо хэмжээ өөрчлөх, устгах үйлдлүүд |
| Сагс цэвэрлэх | Clear cart | `ESC` товчлуур |
| Бэлнээр төлөх | Cash payment | `F2` товчлуур |
| Картаар төлөх | Card payment | `F4` товчлуур |
| Холимог төлбөр | Split payment | Карт + Бэлэн мөнгө хослуулан төлөх |
| QR төлбөр | QR payment | `F5` товчлуур |
| Түргэн мөнгөний товчлуурууд | Quick cash buttons | 1000₮, 5000₮, 10000₮, 20000₮, 50000₮, 100000₮ |
| Захиалга түр хүлээлгэх | Hold order | `F3` товчлуур |
| Захиалга сэргээх | Recall order | Түр хадгалсан сагсыг буцаан дуудах |
| Жинлүүртэй бараа | Weight items | `кг`, `л`, `хайрцаг` → Тоо хэмжээ оруулах цонх |
| Баримт хэвлэх | Print receipt | Төлбөр дуусмагц автоматаар хэвлэнэ |
| Баримт дахин хэвлэх | Reprint receipt | Сүүлчийн борлуулалтын баримтыг дахин хэвлэх |
| Дохионы дуу | Beep sound | Баркод амжилттай уншигдах үед дуут дохио |
| Сумтай товчлууроор удирдах | Arrow-key navigation | Гарын сумнуудаар бараа сонгож, Enter товчоор сагсанд нэмнэ |

### Үйлчлүүлэгчийн дэлгэц / Customer Display

| Монгол | English |
|--------|---------|
| Хүлээлгийн төлөв | Idle state — "Тавтай морилно уу" мессеж |
| Худалдан авалтын явц | Shopping — сагсны барааны жагсаалт |
| Төлбөр төлөх үеийн төлөв | Paying — төлбөрийн хэлбэр, нийт дүн |
| Гүйлгээ дууссан төлөв | Complete — хариулт мөнгө, eBarimt сугалаа |
| Compact grid | 5+ бараа орох үед 2 багана руу шилжинэ |
| Автомат идэвхгүй горим | Auto idle after configurable timeout |

### Барааны удирдлага / Products page

| Монгол | English |
|--------|---------|
| Барааны жагсаалт | Product list with search/filter |
| Шинэ бараа бүртгэх | Create product (barcode, name, price, cost, category, stock, unit) |
| Бараа засах / устгах | Edit / soft-delete / restore |
| Барааны зураг | Image upload (PNG, JPG, GIF, WebP) |

### Нөөцийн удирдлага / Stock Adjustments

| Монгол | English |
|--------|---------|
| Нөөц тохируулах | Adjust stock with barcode scan + reason |
| Тохируулгын түүх | Adjustment history (last 50) |
| Бага нөөцийн анхааруулга | Low stock alert in product grid |

### Борлуулалтын түүх / Sales History

| Монгол | English |
|--------|---------|
| Гүйлгээний жагсаалт | List with date filter |
| Хуудаслалт | Pagination (50 per page) |
| Дэлгэрэнгүй мэдээлэл | Sale detail with items, eBarimt info |
| Бараа буцаалт | Return processing (30 day window) |
| Баримт дахин хэвлэх | Reprint from history |

### Тайлан / Reports

| Монгол | English |
|--------|---------|
| Нэгдсэн хураангуй | Summary: total sales, returns, average check |
| Төлбөрийн төрлөөр | By payment type (cash, card, split, QR) |
| Өдрүүдийн график | Daily sales chart |
| Цагийн хамаарал | Hourly distribution |
| Шилдэг борлуулалттай | Top 20 products |
| Цэвэр ашиг | Profit = Revenue - Cost |
| Ангиллын борлуулалт | Category breakdown |

---

## Өгөгдлийн сан / Database

### Schema — Бүх таблицууд / All Tables

#### products (Бараа)

| Багана | Төрөл | Тайлбар |
|--------|-------|---------|
| id | INTEGER PK | Дотоод ID |
| barcode | TEXT UNIQUE | Баркод (EAN-13) |
| name | TEXT | Барааны нэр |
| price | INTEGER | Худалдах үнө (төгрөг) |
| cost_price | INTEGER | Өртөг үнө |
| category | TEXT | Ангилал |
| stock_qty | INTEGER | Үлдэгдэл нөөц |
| unit | TEXT | Хэмжих нэгж (ш, кг, л, хайрцаг) |
| low_stock_threshold | INTEGER | Доод хязгаар |
| expiry_date | TEXT | Хүчинтэй хугацаа |
| image_url | TEXT | Зургийн зам |
| supplier_id | INTEGER FK | Нийлүүлэгч |
| is_active | INTEGER | Идэвхтэй эсэх |
| created_at | TEXT | Бүртгэсэн огноо |

#### sales (Борлуулалт)

| Багана | Төрөл | Тайлбар |
|--------|-------|---------|
| id | INTEGER PK | Борлуулалтын дугаар |
| cashier_id | INTEGER FK | Кассчин |
| payment_type | TEXT | cash, card, split, qr, return |
| subtotal | INTEGER | Татваргүй дүн |
| total | INTEGER | Нийт дүн |
| cash_given | INTEGER | Өгсөн бэлэн мөнгө |
| change_given | INTEGER | Хариулт мөнгө |
| card_amount | INTEGER | Картаар төлсөн дүн |
| cash_amount | INTEGER | Бэлнээр төлсөн дүн |
| ebarimt_id | TEXT | eBarimt баримтын ID |
| ebarimt_qr | TEXT | eBarimt QR код |
| ebarimt_lottery | TEXT | Сугалааны дугаар |
| ebarimt_status | TEXT | pending, sent, failed, skipped |
| return_of_sale_id | INTEGER FK | Буцаагдсан борлуулалт |
| created_at | TEXT | Огноо |

Бусад таблицууд: `sale_items`, `settings`, `categories`, `suppliers`, `stock_adjustments`, `cash_drawer_log`, `shifts`, `idempotency_keys`, `held_orders`, `audit_log`, `cashiers`.

### Migrations

Бүх миграц `migrate_db()` функц дотор автоматаар хийгддэг (15 migration).

### PRAGMA тохиргоо

```sql
PRAGMA journal_mode=WAL
PRAGMA foreign_keys=ON
PRAGMA synchronous=FULL
PRAGMA cache_size=-64000
PRAGMA temp_store=MEMORY
PRAGMA mmap_size=268435456
```

---

## Гарын товчлуурууд / Keyboard Shortcuts

| Товчлуур | Үйлдэл |
|----------|--------|
| `F1` | Тусламж / Help |
| `F2` | Бэлнээр төлөх / Cash |
| `F3` | Захиалга хүлээлгэх / Hold order |
| `F4` | Картаар төлөх / Card |
| `F5` | QR төлбөр / QR |
| `F6` | Нэргүй үнэ / Anonymous price |
| `F7` | eBarimt төрөл солих / Toggle eBarimt type |
| `F9` | Түргэн хадгалах / Quick hold |
| `F10` | Хадгалсан захиалга сэргээх / Resume order |
| `Ctrl+F` | Бараа хайх / Search |
| `Ctrl+Enter` | Төлбөр баталгаажуулах / Confirm checkout |
| `ESC` | Цэвэрлэх / Clear |

---

## Тохиргоо / Configuration

All settings stored in `settings` table with safe defaults in `config.py`:

| Түлхүүр | Анхны утга | Тайлбар |
|---------|-----------|---------|
| store_name | Миний дэлгүүр | Баримт дээр хэвлэгдэх нэр |
| store_address | Улаанбаатар, БЗД, 1-р хороо | Дэлгүүрийн хаяг |
| store_phone | 70112233 | Утас |
| printer_port | /dev/usb/lp0 | Хэвлэгчийн порт |
| theme | auto | auto / light / dark |
| db_sync_mode | FULL | SQLite sync: FULL / NORMAL |
| default_payment_type | cash | cash / card / qr |
| auto_print_receipt | true | Автомат хэвлэлт |
| return_window_days | 30 | Буцаалт хийх хугацаа |

---

## Тоног төхөөрөмж / Hardware Setup

### Хэвлэгч / Printer
ESC/POS дулааны принтер. Linux дээр `/dev/usb/lp*` автомат танигддаг.
Тохиргоо > Хэвлэгч хэсгээс портыг өөрчлөх боломжтой.

### Баркод сканнер / Barcode Scanner
USB HID гар горимд тохируулсан сканнер ашиглана. Ямар ч тусгай драйвер шаардлагагүй.

### Үйлчлүүлэгчийн дэлгэц / Customer Display
Хоёр дахь мониторт автоматаар нээгдэнэ. Тохиргоо > Дэлгэц хэсгээс тохируулна.

---

## Суулгах заавар / Installation

### Ubuntu 22.04+

```bash
# Системийн сангууд
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0

# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ажиллуулах
./posgtk-dev.sh
```

---

## eBarimt тохиргоо / eBarimt

1. Тохиргоо > Татвар хэсэгт eBarimt API мэдээллээ оруулна
2. API URL, ТТД, Салбар, ПОС дугаарыг бөглөнө
3. Хадгалаад POS дэлгэц дээр `F7` товчоор eBarimt-ийг идэвхжүүлнэ

---

## Нөөц хуулбар / Backup

Өдөр бүрийн анхны борлуулалт хийгдэхэд автоматаар нөөцлөгдөнө (30 хоног хадгална).
Тохиргоо > Систем хэсгээс гараар нөөцлөх, сэргээх боломжтой.

---

## Ээлжийн хаалт / Z-Report

Ээлж нээх, хаах үйлдлүүд Тохиргоо > Систем хэсэгт байрлана.
Ээлж хаах үед:

| Талбар | Тайлбар |
|--------|---------|
| opening_balance | Ээлж нээх үеийн үлдэгдэл |
| cash_sales | Бэлэн мөнгөний борлуулалт |
| card_sales | Картын борлуулалт |
| return_total | Буцаалтын дүн |
| expected_cash | Байх ёстой мөнгө |
| actual_cash | Бодит мөнгө |
| difference | Зөрүү |

---

## Аюулгүй байдал / Security

- Admin PIN: bcrypt хэш, 5 удаа буруу орвол 15 минут блок
- SQLite WAL + synchronous=FULL: тог тасрахад өгөгдөл алдагдахгүй
- Idempotency keys: давхар гүйлгээнээс сэргийлнэ
- BEGIN IMMEDIATE: зэрэгцээ checkout-оос сэргийлнэ

---

## Туршилт / Testing

```bash
source venv/bin/activate
python -m pytest tests/ -v    # Full verbose
python -m pytest tests/ -x    # Stop on first failure
```

28 tests: database CRUD, eBarimt adapter, held orders, DPI scaling.

---

## Алдаа засах / Troubleshooting

| Алдаа | Шийдэл |
|-------|--------|
| `gi.repository` алдаа | `sudo apt install python3-gi gir1.2-gtk-3.0` |
| Хэвлэгч олдсонгүй | `/dev/usb/lp0` байгаа эсэхийг шалгах |
| eBarimt илгээгдэхгүй | API тохиргоо, интернет холболт шалгах |
| Өгөгдлийн сан гэмтсэн | Нөөцөөс сэргээх (Settings > System > Restore) |

"""
Баримтын жишээ — Sample Receipt Preview

Run: python3 sample_receipt_preview.py
This shows what the printed receipt looks like based on printer.py format.
Modify printer.py functions to customize the receipt layout.
"""

from printer import (
    _print_header, _print_items, _print_totals, _print_payment,
    _print_ebarimt, _print_lottery, _print_footer, _print_separator
)


class MockPrinter:
    """Simulates ESC/POS printer output to console."""
    def __init__(self):
        self.lines = []
        self.bold = False

    def set(self, align="left", bold=False, width=1, height=1):
        self.bold = bold
        self.align = align

    def text(self, t):
        self.lines.append(t)

    def qr(self, data, size=4):
        self.lines.append(f"[QR: {data[:40]}...]\n")

    def cut(self):
        self.lines.append("-" * 32 + "\n")

    def pulse(self):
        pass

    def show(self):
        print("=" * 32)
        print("  БАРИМТЫН ЖИШЭЭ / SAMPLE")
        print("=" * 32)
        for line in self.lines:
            print(line, end="")


# ─── Жишээ өгөгдөл / Sample data ───
store_info = {
    "name": "Миний дэлгүүр",
    "address": "Улаанбаатар, Сүхбаатар дүүрэг",
    "phone": "99112233",
}

sale_data = {
    "id": 1245,
    "cashier_name": "Бат",
    "payment_type": "card",
    "total": 52700,
    "card_amount": 52700,
    "cash_given": 52700,
    "change_given": 0,
    "ebarimt_status": "sent",
    "ebarimt_id": "EB20260625-ABCDEF",
    "ebarimt_qr": "0000AAAA1111BBBB2222CCCC3333",
    "ebarimt_lottery": "AB12345678",
    "items": [
        {"product_name": "Үнээний сүү 1л", "quantity": 2, "unit_price": 8500, "subtotal": 17000, "unit": "ш", "category": "Сүүн бүтээгдэхүүн"},
        {"product_name": "Талх цагаан", "quantity": 1, "unit_price": 4200, "subtotal": 4200, "unit": "ш", "category": "Талх"},
        {"product_name": "Цагаан будаа 5кг", "quantity": 1, "unit_price": 16500, "subtotal": 16500, "unit": "ш", "category": "Хүнс"},
        {"product_name": "Улаан лооль", "quantity": 0.500, "unit_price": 10000, "subtotal": 5000, "unit": "кг", "category": "Хүнс"},
        {"product_name": "Махны шөлний багц", "quantity": 1, "unit_price": 10000, "subtotal": 10000, "unit": "ш", "category": "Хүнс"},
    ],
    "customer_tin": "",
}

width = 32
p = MockPrinter()

_print_header(p, store_info, sale_data, width)
_print_items(p, sale_data, width)
_print_totals(p, sale_data, width)
_print_payment(p, sale_data, width)
_print_ebarimt(p, sale_data)
_print_lottery(p, sale_data)
_print_footer(p, width)
p.cut()

p.show()

print()
print()
print("═" * 40)
print("   ХЭРХЭН ӨӨРЧЛӨХ ВЭ / HOW TO CUSTOMIZE")
print("═" * 40)
print()
print("Баримтын хэлбэрийг өөрчлөх: printer.py файл доторх")
print("_print_header, _print_items, _print_totals, _print_payment,")
print("_print_ebarimt, _print_lottery, _print_footer функцүүдийг")
print("засварлана уу.")
print()
print("Жишээ нь:")
print("  - Баримтын дээд хэсэг: _print_header()")
print("  - Барааны жагсаалт: _print_items()")
print("  - Дүн, НӨАТ: _print_totals()")
print("  - eBarimt QR: _print_ebarimt()")
print("  - Сугалаа: _print_lottery()")
print("  - Доод хэсэг: _print_footer()")
print()
print("Тохиргоо хуудсанд:")
print("  - Дэлгүүрийн нэр, хаяг, утас")
print("  - Баримтын width (32 эсвэл 42)")
print("  - Receipt footer текст")
print("  - НӨАТ харуулах эсэх")
print("  - Auto print receipt ON/OFF")

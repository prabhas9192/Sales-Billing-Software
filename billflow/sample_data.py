"""Sample data (products, customers, staff and seven weeks of bills) to try BillFlow with."""
import datetime
import random
from contextlib import closing

from billflow import clock
from billflow.analytics import auto_tag_customer, compute_bill_totals
from billflow.database import db_all, db_one, get_conn, init_db
from billflow.schema import record_opening_balances

CATEGORIES = {
    "Electronics": [
        ("Wireless Mouse", 499.0, 45, "8471", 18.0),
        ("Mechanical Keyboard", 1899.0, 20, "8471", 18.0),
        ("USB-C Fast Cable", 199.0, 80, "8544", 18.0),
        ("Bluetooth Speaker", 1299.0, 15, "8518", 18.0),
        ("Power Bank 10000mAh", 999.0, 4, "8507", 18.0),   # low stock
        ("Noise Cancelling Earbuds", 2499.0, 12, "8518", 18.0),
        ("HD Webcam 1080p", 1499.0, 3, "8525", 18.0),      # low stock
    ],
    "Grocery": [
        ("Organic Basmati Rice 5kg", 450.0, 60, "1006", 5.0),
        ("Whole Wheat Flour 5kg", 240.0, 50, "1101", 5.0),
        ("Extra Virgin Olive Oil 1L", 750.0, 18, "1509", 12.0),
        ("Pure Cow Ghee 500ml", 360.0, 25, "0405", 12.0),
        ("Almonds Premium 500g", 490.0, 30, "0802", 12.0),
        ("Green Tea Bags 50s", 180.0, 40, "0902", 5.0),
        ("Organic Honey 500g", 299.0, 2, "0409", 5.0),     # low stock
    ],
    "Beverages": [
        ("Cold Brew Coffee 250ml", 120.0, 35, "2202", 18.0),
        ("Artisan Lemonade 300ml", 75.0, 40, "2202", 12.0),
        ("Mineral Water 1L", 25.0, 150, "2201", 18.0),
        ("Energy Drink Can", 99.0, 60, "2202", 28.0),
        ("Fresh Orange Juice 500ml", 110.0, 20, "2009", 12.0),
    ],
    "Clothing": [
        ("Cotton Slim Fit T-Shirt", 599.0, 35, "6109", 5.0),
        ("Denim Jeans Regular", 1499.0, 22, "6203", 12.0),
        ("Formal Cotton Shirt", 899.0, 18, "6205", 5.0),
        ("Sports Track Pants", 699.0, 14, "6103", 5.0),
        ("Winter Fleece Jacket", 1999.0, 2, "6101", 12.0),  # low stock
    ],
    "Stationery": [
        ("Hardcover Ruled Notebook", 140.0, 75, "4820", 12.0),
        ("Gel Pen Pack of 5", 99.0, 90, "9608", 18.0),
        ("Desk Organizer Mesh", 299.0, 16, "8304", 18.0),
        ("Sticky Notes Pastel 4-Pack", 120.0, 45, "4820", 12.0),
        ("Permanent Marker Set", 150.0, 30, "9608", 18.0),
    ],
}

CUSTOMERS = [
    ("Aarav Sharma", "9876543210", "aarav.sharma@example.com", 29, "Male"),
    ("Priya Patel", "9823456789", "priya.patel@example.com", 26, "Female"),
    ("Rahul Verma", "9811223344", "rahul.v@example.com", 34, "Male"),
    ("Sneha Kulkarni", "9944556677", "sneha.k@example.com", 31, "Female"),
    ("Vikram Singh", "9766554433", "vikram.singh@example.com", 42, "Male"),
    ("Ananya Roy", "9833445566", "ananya.roy@example.com", 24, "Female"),
    ("Rohan Mehta", "9899887766", "rohan.mehta@example.com", 28, "Male"),
    ("Kavita Nair", "9755443322", "kavita.n@example.com", 38, "Female"),
    ("Aditya Joshi", "9844332211", "aditya.j@example.com", 30, "Male"),
    ("Neha Gupta", "9911992288", "neha.gupta@example.com", 27, "Female"),
    ("Siddharth Rao", "9877665544", "sid.rao@example.com", 35, "Male"),
    ("Divya Iyer", "9822334455", "divya.iyer@example.com", 32, "Female"),
    ("Karan Malhotra", "9711223344", "karan.m@example.com", 40, "Male"),
    ("Pooja Choudhary", "9933445566", "pooja.c@example.com", 25, "Female"),
    ("Manish Tiwari", "9866554411", "manish.t@example.com", 45, "Male"),
]

STAFF = [  # name, phone, role, shift start, shift end, salary, commission %
    ("Arjun Kapoor", "9812345670", "Manager", "09:00", "18:00", 35000.0, 2.0),
    ("Deepika Sen", "9823456781", "Cashier", "09:00", "17:30", 22000.0, 1.0),
    ("Manoj Kumar", "9834567892", "Staff", "10:00", "19:00", 18000.0, 1.5),
    ("Sunita Das", "9845678903", "Staff", "09:30", "18:30", 18000.0, 1.5),
    ("Ravi Shankar", "9856789014", "Delivery", "08:30", "16:30", 16000.0, 0.5),
]

COUPONS = [  # code, type, value, minimum bill, days valid, description
    ("WELCOME10", "percent", 10.0, 300.0, 120, "10% off for new shoppers"),
    ("FESTIVE20", "percent", 20.0, 1000.0, 60, "Festival discount 20%"),
    ("FLAT100", "fixed", 100.0, 800.0, 45, "Flat 100 off on 800+"),
    ("SUPER50", "percent", 50.0, 3000.0, 20, "Mega clearance 50%"),
    ("SAVE50", "fixed", 50.0, 250.0, 120, "Quick savings, 50 off"),
]

# Who supplies each category, and what the shop pays as a share of the selling price.
SUPPLIERS = {
    "Electronics": ("TechSource Distributors", "9810011122", "07AAACT1234F1Z5", 0.62),
    "Grocery": ("GreenLeaf Foods", "9820022233", "27AABCG5678H1Z2", 0.72),
    "Beverages": ("GreenLeaf Foods", "9820022233", "27AABCG5678H1Z2", 0.68),
    "Clothing": ("Northwind Apparel", "9830033344", "29AADCN9012K1Z8", 0.55),
    "Stationery": ("PaperTrail Wholesale", "9840044455", "33AAECP3456M1Z1", 0.60),
}

SALE_DAYS = 50
PAYMENT_MODES = ["Cash", "UPI", "UPI", "Card", "Card", "Cash"]
COUPON_CHOICES = ["", "", "", "WELCOME10", "FLAT100", ""]


def is_empty() -> bool:
    return all(db_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] == 0 for t in ("products", "customers", "bills"))


def load_sample_data(say=print) -> bool:
    """Fill an empty database with sample data. Changes nothing, and returns False, if it holds any data."""
    init_db()
    if not is_empty():
        say("The database already has data, so no sample data was added.")
        return False

    today = clock.today()
    month = f"{today.year:04d}-{today.month:02d}"
    days = lambda n: (today + datetime.timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731

    with closing(get_conn()) as conn:
        with conn:
            supplier_ids = {}
            for name, phone, gstin, _ in SUPPLIERS.values():
                if name not in supplier_ids:
                    supplier_ids[name] = conn.execute("INSERT INTO suppliers (name, phone, gstin) VALUES (?, ?, ?)",
                                                      (name, phone, gstin)).lastrowid
            conn.executemany(
                "INSERT INTO products (name, price, quantity, category, hsn_code, gst_rate, cost, supplier_id, sku) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(name, price, qty, cat, hsn, gst, round(price * SUPPLIERS[cat][3], 2), supplier_ids[SUPPLIERS[cat][0]],
                  f"{cat[:3].upper()}-{i + 1:03d}")
                 for cat, items in CATEGORIES.items() for i, (name, price, qty, hsn, gst) in enumerate(items)])
            record_opening_balances(conn)
            conn.executemany("INSERT INTO customers (name, phone, email, age, gender) VALUES (?, ?, ?, ?, ?)", CUSTOMERS)
            conn.executemany(
                "INSERT INTO staff (name, phone, role, shift_start, shift_end, salary, commission_pct) VALUES (?, ?, ?, ?, ?, ?, ?)",
                STAFF)
            conn.executemany(
                "INSERT INTO coupons (code, type, value, min_bill, expiry, description) VALUES (?, ?, ?, ?, ?, ?)",
                [(code, kind, value, minimum, days(valid), text) for code, kind, value, minimum, valid, text in COUPONS])
            conn.execute("INSERT INTO sales_targets (period, target_amt, staff_id) VALUES (?, 120000, 0)", (month,))
            conn.executemany("INSERT INTO holidays (date, name, type) VALUES (?, ?, 'holiday')",
                             [(days(14), "Store Holiday"), (days(15), "Festival Closure"), (days(30), "Stock-Taking Day")])

            products = [dict(r) for r in conn.execute("SELECT id, name, price, gst_rate, cost FROM products ORDER BY id").fetchall()]
            customers = [dict(r) for r in conn.execute("SELECT id, name FROM customers ORDER BY id").fetchall()]
            staff_ids = [r["id"] for r in conn.execute("SELECT id FROM staff ORDER BY id").fetchall()]

            spent, visits = {}, {}
            for offset in range(SALE_DAYS, -1, -1):
                day = today - datetime.timedelta(days=offset)
                for _ in range(random.randint(2, 6)):
                    stamp = f"{day:%Y-%m-%d} {random.randint(10, 20):02d}:{random.randint(5, 55):02d}:00"
                    customer = random.choice(customers) if random.random() < 0.7 else None  # 70% registered

                    lines = []
                    for p in random.sample(products, k=random.randint(1, 4)):
                        lines.append({"id": p["id"], "name": p["name"], "price": float(p["price"]),
                                      "gst_rate": float(p["gst_rate"]), "qty": random.randint(1, 3),
                                      "cost": float(p["cost"])})
                    subtotal = sum(l["price"] * l["qty"] for l in lines)

                    coupon = random.choice(COUPON_CHOICES)
                    discount = 0.0
                    if coupon == "WELCOME10" and subtotal >= 300:
                        discount = subtotal * 0.10
                    elif coupon == "FLAT100" and subtotal >= 800:
                        discount = 100.0
                    else:
                        coupon = ""
                    totals = compute_bill_totals(lines, discount)

                    cur = conn.execute(
                        "INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, coupon_code, staff_id, payment_mode) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (stamp, customer["name"] if customer else "Walk-in", customer["id"] if customer else None,
                         totals["subtotal"], totals["discount"], totals["tax"], totals["total"], coupon,
                         random.choice(staff_ids), random.choice(PAYMENT_MODES)))
                    conn.executemany(
                        "INSERT INTO bill_items (bill_id, product_id, name, price, qty, cost) VALUES (?, ?, ?, ?, ?, ?)",
                        [(cur.lastrowid, l["id"], l["name"], l["price"], l["qty"], l["cost"]) for l in lines])
                    if customer:
                        spent[customer["id"]] = spent.get(customer["id"], 0.0) + totals["total"]
                        visits[customer["id"]] = visits.get(customer["id"], 0) + 1

            conn.executemany("UPDATE customers SET total_spent = ?, visit_count = ? WHERE id = ?",
                             [(round(spent[c], 2), visits[c], c) for c in spent])
            conn.executemany("INSERT INTO expenses (date, category, amount, note) VALUES (?, ?, ?, ?)", [
                (f"{month}-01", "Rent", 25000.0, "Store Monthly Rent"),
                (f"{month}-05", "Electricity", 4200.0, "Commercial Power Bill"),
                (f"{month}-10", "Supplies", 1850.0, "Packaging Bags & Tape"),
                (f"{month}-15", "Marketing", 3500.0, "Social Media Ads"),
                (f"{month}-20", "Maintenance", 1200.0, "POS Printer Servicing"),
            ])
            conn.execute("INSERT INTO cash_register (date, opening_cash, notes) VALUES (?, 5000.0, 'Initial float')",
                         (today.strftime("%Y-%m-%d"),))

    # Tagging reads and writes through its own connections, so it runs once the data is committed.
    for row in db_all("SELECT id FROM customers"):
        auto_tag_customer(row["id"])
    say("Sample data loaded.")
    return True

#!/usr/bin/env python3
"""
Sample Database Seeder for BillFlow
Generates realistic data for testing POS, analytics, charts, and reports.
"""

import os
import sys
import random
import datetime
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from billflow.database import get_conn, init_db, db_run, db_runmany, db_all
from billflow.config import DB_PATH
from billflow.analytics import auto_tag_customer

CATEGORIES = {
    "Electronics": [
        ("Wireless Mouse", 499.0, 45, "8471", 18.0),
        ("Mechanical Keyboard", 1899.0, 20, "8471", 18.0),
        ("USB-C Fast Cable", 199.0, 80, "8544", 18.0),
        ("Bluetooth Speaker", 1299.0, 15, "8518", 18.0),
        ("Power Bank 10000mAh", 999.0, 4, "8507", 18.0), # low stock
        ("Noise Cancelling Earbuds", 2499.0, 12, "8518", 18.0),
        ("HD Webcam 1080p", 1499.0, 3, "8525", 18.0),     # low stock
    ],
    "Grocery": [
        ("Organic Basmati Rice 5kg", 450.0, 60, "1006", 5.0),
        ("Whole Wheat Flour 5kg", 240.0, 50, "1101", 5.0),
        ("Extra Virgin Olive Oil 1L", 750.0, 18, "1509", 12.0),
        ("Pure Cow Ghee 500ml", 360.0, 25, "0405", 12.0),
        ("Almonds Premium 500g", 490.0, 30, "0802", 12.0),
        ("Green Tea Bags 50s", 180.0, 40, "0902", 5.0),
        ("Organic Honey 500g", 299.0, 2, "0409", 5.0),    # low stock
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
        ("Winter Fleece Jacket", 1999.0, 2, "6101", 12.0), # low stock
    ],
    "Stationery": [
        ("Hardcover Ruled Notebook", 140.0, 75, "4820", 12.0),
        ("Gel Pen Pack of 5", 99.0, 90, "9608", 18.0),
        ("Desk Organizer Mesh", 299.0, 16, "8304", 18.0),
        ("Sticky Notes Pastel 4-Pack", 120.0, 45, "4820", 12.0),
        ("Permanent Marker Set", 150.0, 30, "9608", 18.0),
    ]
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

STAFF = [
    ("Arjun Kapoor", "9812345670", "Manager", "09:00", "18:00", 35000.0, 2.0),
    ("Deepika Sen", "9823456781", "Cashier", "09:00", "17:30", 22000.0, 1.0),
    ("Manoj Kumar", "9834567892", "Staff", "10:00", "19:00", 18000.0, 1.5),
    ("Sunita Das", "9845678903", "Staff", "09:30", "18:30", 18000.0, 1.5),
    ("Ravi Shankar", "9856789014", "Delivery", "08:30", "16:30", 16000.0, 0.5),
]

COUPONS = [
    ("WELCOME10", "percent", 10.0, 300.0, "2026-12-31", "10% off for new shoppers"),
    ("FESTIVE20", "percent", 20.0, 1000.0, "2026-12-25", "Festival discount 20%"),
    ("FLAT100", "fixed", 100.0, 800.0, "2026-11-30", "Flat Rs. 100 off on Rs. 800+"),
    ("SUPER50", "percent", 50.0, 3000.0, "2026-11-15", "Mega clearance 50%"),
    ("SAVE50", "fixed", 50.0, 250.0, "2026-12-31", "Quick savings Rs. 50 off"),
]

def seed():
    print(f"Connecting to database at: {DB_PATH}")
    init_db()

    with closing(get_conn()) as conn:
        with conn:
            # 1. Insert Products
            cur_p = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if cur_p == 0:
                print("Seeding Products...")
                prod_records = []
                for cat, items in CATEGORIES.items():
                    for name, price, qty, hsn, gst in items:
                        prod_records.append((name, price, qty, cat, hsn, gst))
                conn.executemany(
                    "INSERT INTO products (name, price, quantity, category, hsn_code, gst_rate) VALUES (?, ?, ?, ?, ?, ?)",
                    prod_records
                )
                print(f" -> Inserted {len(prod_records)} products.")

            # 2. Insert Customers
            cur_c = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            if cur_c == 0:
                print("Seeding Customers...")
                conn.executemany(
                    "INSERT INTO customers (name, phone, email, age, gender) VALUES (?, ?, ?, ?, ?)",
                    CUSTOMERS
                )
                print(f" -> Inserted {len(CUSTOMERS)} customers.")

            # 3. Insert Staff
            cur_s = conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0]
            if cur_s == 0:
                print("Seeding Staff...")
                conn.executemany(
                    "INSERT INTO staff (name, phone, role, shift_start, shift_end, salary, commission_pct) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    STAFF
                )
                print(f" -> Inserted {len(STAFF)} staff members.")

            # 4. Insert Coupons
            cur_cp = conn.execute("SELECT COUNT(*) FROM coupons").fetchone()[0]
            if cur_cp == 0:
                print("Seeding Coupons...")
                conn.executemany(
                    "INSERT INTO coupons (code, type, value, min_bill, expiry, description) VALUES (?, ?, ?, ?, ?, ?)",
                    COUPONS
                )
                print(f" -> Inserted {len(COUPONS)} coupons.")

            # 5. Insert Sales Targets & Holidays
            conn.execute("INSERT OR IGNORE INTO sales_targets (period, target_amt, staff_id) VALUES ('2026-11', 120000, 0)")
            conn.execute("INSERT OR IGNORE INTO holidays (date, name, type) VALUES ('2026-11-14', 'Diwali Festival', 'holiday')")
            conn.execute("INSERT OR IGNORE INTO holidays (date, name, type) VALUES ('2026-11-15', 'Govardhan Puja', 'holiday')")
            conn.execute("INSERT OR IGNORE INTO holidays (date, name, type) VALUES ('2026-11-27', 'Guru Nanak Jayanti', 'holiday')")

            # 6. Fetch products, customers, staff for bill creation
            products = [dict(r) for r in conn.execute("SELECT id, name, price, quantity FROM products").fetchall()]
            customers = [dict(r) for r in conn.execute("SELECT id, name FROM customers").fetchall()]
            staff_members = [dict(r) for r in conn.execute("SELECT id, name FROM staff").fetchall()]

            # 7. Generate Bills spanning the last 60 days
            cur_b = conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0]
            if cur_b == 0 and products and customers:
                print("Generating 180 realistic historical bills with line items...")
                today = datetime.date.today()
                payment_modes = ["Cash", "UPI", "UPI", "Card", "Card", "Cash"]
                coupon_codes = ["", "", "", "WELCOME10", "FLAT100", ""]

                bill_batch = []
                for day_offset in range(50, -1, -1):
                    bill_date = today - datetime.timedelta(days=day_offset)
                    # 2 to 6 bills per day
                    num_bills_today = random.randint(2, 6)
                    for b_idx in range(num_bills_today):
                        hour = random.randint(10, 20)
                        minute = random.randint(5, 55)
                        dt_str = f"{bill_date.strftime('%Y-%m-%d')} {hour:02d}:{minute:02d}:00"

                        # 70% registered customers, 30% walk-in
                        if random.random() < 0.7:
                            c = random.choice(customers)
                            cust_name = c["name"]
                            cust_id = c["id"]
                        else:
                            cust_name = "Walk-in"
                            cust_id = None

                        staff_id = random.choice(staff_members)["id"] if staff_members else 0
                        pay_mode = random.choice(payment_modes)
                        chosen_coupon = random.choice(coupon_codes)

                        # 1 to 4 items in bill
                        num_items = random.randint(1, 4)
                        selected_prods = random.sample(products, k=min(num_items, len(products)))

                        subtotal = 0.0
                        items_to_insert = []
                        for sp in selected_prods:
                            qty = random.randint(1, 3)
                            price = float(sp["price"])
                            subtotal += price * qty
                            items_to_insert.append((sp["id"], sp["name"], price, qty))

                        disc_pct = 0.0
                        tax_pct = 18.0
                        after_disc = subtotal
                        tax_amt = after_disc * 0.18
                        grand = after_disc + tax_amt

                        if chosen_coupon == "WELCOME10" and grand >= 300:
                            grand -= grand * 0.10
                        elif chosen_coupon == "FLAT100" and grand >= 800:
                            grand -= 100.0

                        cur = conn.execute(
                            "INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, coupon_code, staff_id, payment_mode) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (dt_str, cust_name, cust_id, round(subtotal, 2), disc_pct, tax_pct, round(grand, 2), chosen_coupon, staff_id, pay_mode)
                        )
                        bid = cur.lastrowid

                        for pid, pname, pprice, pqty in items_to_insert:
                            conn.execute(
                                "INSERT INTO bill_items (bill_id, product_id, name, price, qty) VALUES (?, ?, ?, ?, ?)",
                                (bid, pid, pname, pprice, pqty)
                            )

                        if cust_id:
                            conn.execute(
                                "UPDATE customers SET total_spent = total_spent + ?, visit_count = visit_count + 1 WHERE id = ?",
                                (round(grand, 2), cust_id)
                            )

                print(f" -> Finished bill generation.")

            # 8. Insert Expenses
            cur_exp = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            if cur_exp == 0:
                print("Seeding monthly operating expenses...")
                today = datetime.date.today()
                exp_list = [
                    (f"{today.year:04d}-{today.month:02d}-01", "Rent", 25000.0, "Store Monthly Rent"),
                    (f"{today.year:04d}-{today.month:02d}-05", "Electricity", 4200.0, "Commercial Power Bill"),
                    (f"{today.year:04d}-{today.month:02d}-10", "Supplies", 1850.0, "Packaging Bags & Tape"),
                    (f"{today.year:04d}-{today.month:02d}-15", "Marketing", 3500.0, "Social Media Ads"),
                    (f"{today.year:04d}-{today.month:02d}-20", "Maintenance", 1200.0, "POS Printer Servicing"),
                ]
                conn.executemany("INSERT INTO expenses (date, category, amount, note) VALUES (?, ?, ?, ?)", exp_list)
                print(f" -> Inserted {len(exp_list)} expenses.")

            # 9. Cash Register Opening Cash
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            conn.execute("INSERT OR IGNORE INTO cash_register (date, opening_cash, notes) VALUES (?, 5000.0, 'Initial float')", (today_str,))

            # 10. Auto-tag all customers
            cust_rows = conn.execute("SELECT id FROM customers").fetchall()
            for cr in cust_rows:
                auto_tag_customer(cr[0])

    print("\n=======================================================")
    print(" SAMPLE DATABASE SUCCESSFULLY SEEDED & INDEXED!")
    print("=======================================================")

if __name__ == "__main__":
    seed()

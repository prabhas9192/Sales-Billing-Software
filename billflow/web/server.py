"""
BillFlow Modern Web Server & Comprehensive REST API.
Zero external dependencies - powered by Python's standard library.
"""
import calendar
import http.server
import json
import os
import sys
import urllib.parse
from datetime import datetime, date, timedelta

# Add root project dir to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from billflow.database import db_all, db_one, db_run, get_conn, closing
from billflow.config import APP_SETTINGS, save_settings
from billflow import analytics

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class BillFlowAPIHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def parse_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if not path.startswith("/api/"):
            if path in ("", "/"):
                self.path = "/index.html"
            return super().do_GET()

        try:
            # Core
            if path == "/api/overview":
                self.handle_overview()
            elif path == "/api/chart-data":
                self.handle_chart_data(query)
            elif path == "/api/products":
                self.handle_get_products(query)
            elif path == "/api/customers":
                self.handle_get_customers(query)
            elif path == "/api/bills":
                self.handle_get_bills(query)
            elif path.startswith("/api/bills/"):
                bill_id = int(path.split("/")[-1])
                self.handle_get_bill_detail(bill_id)
            elif path == "/api/coupons":
                self.handle_get_coupons()
            elif path == "/api/analytics":
                self.handle_get_analytics()
            # Operations
            elif path == "/api/cash-register":
                self.handle_get_cash_register(query)
            elif path == "/api/purchase-orders":
                self.handle_get_purchase_orders()
            elif path == "/api/refunds/search":
                self.handle_search_refunds(query)
            elif path == "/api/eod":
                self.handle_get_eod(query)
            # People & HR
            elif path == "/api/staff":
                self.handle_get_staff()
            elif path == "/api/roster":
                self.handle_get_roster(query)
            elif path == "/api/salary":
                self.handle_get_salary()
            elif path == "/api/targets":
                self.handle_get_targets()
            elif path == "/api/expenses":
                self.handle_get_expenses()
            elif path == "/api/holidays":
                self.handle_get_holidays()
            # Advanced Analytics
            elif path == "/api/calendar-heat":
                self.handle_get_calendar_heat(query)
            elif path == "/api/gst-report":
                self.handle_get_gst_report(query)
            elif path == "/api/breakeven":
                self.handle_get_breakeven(query)
            elif path == "/api/insights":
                self.handle_get_insights()
            elif path == "/api/analytics-plus":
                self.handle_get_analytics_plus()
            # Settings & Export
            elif path == "/api/settings":
                self.handle_get_settings()
            elif path.startswith("/api/export/"):
                export_type = path.split("/")[-1]
                self.handle_export(export_type)
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        payload = self.parse_json_body()

        try:
            # Core
            if path == "/api/checkout":
                self.handle_checkout(payload)
            elif path == "/api/products":
                self.handle_create_product(payload)
            elif path == "/api/customers":
                self.handle_create_customer(payload)
            elif path == "/api/coupons":
                self.handle_create_coupon(payload)
            elif path == "/api/coupons/validate":
                self.handle_validate_coupon(payload)
            # Operations
            elif path == "/api/cash-register/opening":
                self.handle_set_cash_opening(payload)
            elif path == "/api/purchase-orders":
                self.handle_create_purchase_order(payload)
            elif path.startswith("/api/purchase-orders/") and path.endswith("/receive"):
                po_id = int(path.split("/")[3])
                self.handle_receive_purchase_order(po_id)
            elif path.startswith("/api/purchase-orders/") and path.endswith("/cancel"):
                po_id = int(path.split("/")[3])
                self.handle_cancel_purchase_order(po_id)
            elif path == "/api/purchase-orders/reorder-all":
                self.handle_reorder_all()
            elif path == "/api/refunds":
                self.handle_process_refund(payload)
            # People & HR
            elif path == "/api/staff":
                self.handle_create_staff(payload)
            elif path == "/api/roster":
                self.handle_save_roster(payload)
            elif path == "/api/salary/advance":
                self.handle_record_advance(payload)
            elif path == "/api/targets":
                self.handle_set_target(payload)
            elif path == "/api/expenses":
                self.handle_create_expense(payload)
            elif path == "/api/holidays":
                self.handle_create_holiday(payload)
            # Settings
            elif path == "/api/settings":
                self.handle_save_settings(payload)
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        payload = self.parse_json_body()

        try:
            if path.startswith("/api/products/"):
                prod_id = int(path.split("/")[-1])
                self.handle_update_product(prod_id, payload)
            elif path.startswith("/api/coupons/") and path.endswith("/toggle"):
                c_id = int(path.split("/")[3])
                db_run("UPDATE coupons SET active = 1 - active WHERE id = ?", (c_id,))
                self.send_json({"success": True})
            elif path.startswith("/api/staff/") and path.endswith("/toggle"):
                s_id = int(path.split("/")[3])
                db_run("UPDATE staff SET active = 1 - active WHERE id = ?", (s_id,))
                self.send_json({"success": True})
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path.startswith("/api/products/"):
                prod_id = int(path.split("/")[-1])
                db_run("DELETE FROM products WHERE id = ?", (prod_id,))
                self.send_json({"success": True})
            elif path.startswith("/api/coupons/"):
                c_id = int(path.split("/")[-1])
                db_run("DELETE FROM coupons WHERE id = ?", (c_id,))
                self.send_json({"success": True})
            elif path.startswith("/api/staff/"):
                s_id = int(path.split("/")[-1])
                db_run("DELETE FROM staff WHERE id = ?", (s_id,))
                self.send_json({"success": True})
            elif path.startswith("/api/expenses/"):
                exp_id = int(path.split("/")[-1])
                db_run("DELETE FROM expenses WHERE id = ?", (exp_id,))
                self.send_json({"success": True})
            elif path.startswith("/api/holidays/"):
                h_id = int(path.split("/")[-1])
                db_run("DELETE FROM holidays WHERE id = ?", (h_id,))
                self.send_json({"success": True})
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    # ---------------- 1. Core Endpoints ---------------- #

    def handle_overview(self):
        totals = db_one("SELECT COALESCE(SUM(total), 0) as rev, COUNT(*) as bills_count FROM bills WHERE total >= 0")
        total_rev = round(totals["rev"] if totals else 0.0, 2)
        total_bills = totals["bills_count"] if totals else 0
        aov = round(total_rev / total_bills, 2) if total_bills else 0.0

        cust_count = db_one("SELECT COUNT(*) as count FROM customers")["count"]
        prod_count = db_one("SELECT COUNT(*) as count FROM products")["count"]
        low_stock = db_one("SELECT COUNT(*) as count FROM products WHERE quantity < 15")["count"]

        top_prods = db_all("""
            SELECT p.id, p.name, p.category, p.price, p.quantity,
                   COALESCE(SUM(bi.qty), 0) as units_sold,
                   COALESCE(SUM(bi.price * bi.qty), 0) as revenue
            FROM products p
            LEFT JOIN bill_items bi ON bi.product_id = p.id
            GROUP BY p.id
            ORDER BY units_sold DESC
            LIMIT 5
        """)

        recent_bills = db_all("""
            SELECT id, date, customer, payment_mode, total, subtotal, tax, discount
            FROM bills
            ORDER BY id DESC
            LIMIT 6
        """)

        self.send_json({
            "total_revenue": total_rev,
            "total_bills": total_bills,
            "avg_order_value": aov,
            "total_customers": cust_count,
            "total_products": prod_count,
            "low_stock_count": low_stock,
            "top_products": top_prods,
            "recent_bills": recent_bills,
        })

    def handle_chart_data(self, query):
        days = int(query.get("days", [30])[0])
        rows = db_all("""
            SELECT substr(date, 1, 10) as day, SUM(total) as revenue, COUNT(*) as orders
            FROM bills
            WHERE date >= date('now', ?) AND total >= 0
            GROUP BY substr(date, 1, 10)
            ORDER BY day ASC
        """, (f"-{days} days",))

        if not rows:
            rows = db_all("""
                SELECT substr(date, 1, 10) as day, SUM(total) as revenue, COUNT(*) as orders
                FROM bills
                WHERE total >= 0
                GROUP BY substr(date, 1, 10)
                ORDER BY day DESC
                LIMIT ?
            """, (days,))
            rows.reverse()

        labels = [r["day"] for r in rows]
        revenues = [round(r["revenue"], 2) for r in rows]
        orders = [r["orders"] for r in rows]

        self.send_json({
            "labels": labels,
            "revenues": revenues,
            "orders": orders
        })

    def handle_get_products(self, query):
        cat = query.get("category", [None])[0]
        search = query.get("search", [None])[0]

        sql = "SELECT id, name, price, quantity, category, hsn_code, gst_rate FROM products WHERE 1=1"
        params = []
        if cat and cat.lower() != "all":
            sql += " AND category = ?"
            params.append(cat)
        if search:
            sql += " AND (name LIKE ? OR category LIKE ? OR hsn_code LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])
        sql += " ORDER BY name ASC"

        prods = db_all(sql, tuple(params))
        cats = [r["category"] for r in db_all("SELECT DISTINCT category FROM products ORDER BY category ASC")]

        self.send_json({
            "products": prods,
            "categories": cats
        })

    def handle_create_product(self, data):
        name = data.get("name", "").strip()
        price = float(data.get("price", 0))
        quantity = int(data.get("quantity", 0))
        category = data.get("category", "General").strip()
        hsn_code = data.get("hsn_code", "").strip()
        gst_rate = float(data.get("gst_rate", 18.0))

        if not name or price <= 0:
            return self.send_json({"error": "Valid name and positive price required"}, 400)

        prod_id = db_run(
            "INSERT INTO products (name, price, quantity, category, hsn_code, gst_rate) VALUES (?, ?, ?, ?, ?, ?)",
            (name, price, quantity, category, hsn_code, gst_rate)
        )
        self.send_json({"id": prod_id, "name": name, "price": price, "quantity": quantity, "category": category})

    def handle_update_product(self, prod_id, data):
        name = data.get("name")
        price = data.get("price")
        quantity = data.get("quantity")
        category = data.get("category")
        hsn = data.get("hsn_code")

        db_run("""
            UPDATE products
            SET name = COALESCE(?, name),
                price = COALESCE(?, price),
                quantity = COALESCE(?, quantity),
                category = COALESCE(?, category),
                hsn_code = COALESCE(?, hsn_code)
            WHERE id = ?
        """, (name, price, quantity, category, hsn, prod_id))
        self.send_json({"success": True, "id": prod_id})

    def handle_get_customers(self, query):
        search = query.get("search", [None])[0]
        sql = "SELECT id, name, phone, email, total_spent, visit_count, tag FROM customers WHERE 1=1"
        params = []
        if search:
            sql += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])
        sql += " ORDER BY total_spent DESC"

        customers = db_all(sql, tuple(params))
        self.send_json(customers)

    def handle_create_customer(self, data):
        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip()
        tag = data.get("tag", "Regular").strip()

        if not name:
            return self.send_json({"error": "Name is required"}, 400)

        cust_id = db_run(
            "INSERT INTO customers (name, phone, email, total_spent, visit_count, tag) VALUES (?, ?, ?, 0.0, 0, ?)",
            (name, phone, email, tag)
        )
        self.send_json({"id": cust_id, "name": name, "phone": phone, "email": email, "tag": tag})

    def handle_get_bills(self, query):
        limit = int(query.get("limit", [50])[0])
        bills = db_all("""
            SELECT id, date, customer, customer_id, subtotal, discount, tax, total, payment_mode, coupon_code, note
            FROM bills
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        self.send_json(bills)

    def handle_get_bill_detail(self, bill_id):
        bill = db_one("SELECT * FROM bills WHERE id = ?", (bill_id,))
        if not bill:
            return self.send_json({"error": "Bill not found"}, 404)
        items = db_all("SELECT * FROM bill_items WHERE bill_id = ?", (bill_id,))
        self.send_json({"bill": bill, "items": items})

    def handle_get_coupons(self):
        coupons = db_all("SELECT * FROM coupons ORDER BY id DESC")
        self.send_json(coupons)

    def handle_create_coupon(self, data):
        code = data.get("code", "").strip().upper()
        ctype = data.get("type", "percent")
        val = float(data.get("value", 10.0))
        min_bill = float(data.get("min_bill", 0.0))
        expiry = data.get("expiry", "").strip()
        desc = data.get("description", "").strip()

        if not code or val <= 0:
            return self.send_json({"error": "Valid code and positive value required"}, 400)

        cid = db_run("""
            INSERT INTO coupons (code, type, value, min_bill, expiry, active, usage_count, description)
            VALUES (?, ?, ?, ?, ?, 1, 0, ?)
        """, (code, ctype, val, min_bill, expiry, desc))
        self.send_json({"id": cid, "code": code, "success": True})

    def handle_validate_coupon(self, data):
        code = data.get("code", "").strip().upper()
        subtotal = float(data.get("subtotal", 0.0))
        disc, msg = analytics.validate_coupon(code, subtotal)
        valid = disc > 0 or "off" in msg.lower()
        self.send_json({"valid": valid, "code": code, "discount": disc, "message": msg})

    def handle_checkout(self, data):
        items = data.get("items", [])
        if not items:
            return self.send_json({"error": "Cart is empty"}, 400)

        customer_name = data.get("customer_name", "Walk-in Customer")
        customer_id = data.get("customer_id")
        payment_mode = data.get("payment_mode", "Cash")
        coupon_code = data.get("coupon_code", "")
        discount = float(data.get("discount", 0.0))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subtotal = 0.0
        for it in items:
            subtotal += float(it["price"]) * int(it["qty"])

        taxable = max(0.0, subtotal - discount)
        tax = round(taxable * 0.18, 2)
        total = round(taxable + tax, 2)

        with closing(get_conn()) as conn:
            with conn:
                cur = conn.execute("""
                    INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, note, coupon_code, payment_mode, staff_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (now_str, customer_name, customer_id, subtotal, discount, tax, total, "Register Checkout", coupon_code, payment_mode))
                bill_id = cur.lastrowid

                for it in items:
                    conn.execute("""
                        INSERT INTO bill_items (bill_id, product_id, name, price, qty)
                        VALUES (?, ?, ?, ?, ?)
                    """, (bill_id, it["id"], it["name"], float(it["price"]), int(it["qty"])))

                    conn.execute("""
                        UPDATE products
                        SET quantity = MAX(0, quantity - ?)
                        WHERE id = ?
                    """, (int(it["qty"]), it["id"]))

                if customer_id:
                    conn.execute("""
                        UPDATE customers
                        SET total_spent = total_spent + ?,
                            visit_count = visit_count + 1
                        WHERE id = ?
                    """, (total, customer_id))
                    analytics.auto_tag_customer(customer_id)

                if coupon_code:
                    conn.execute("""
                        UPDATE coupons
                        SET usage_count = usage_count + 1
                        WHERE code = ?
                    """, (coupon_code,))

        self.send_json({
            "success": True,
            "bill_id": bill_id,
            "date": now_str,
            "customer": customer_name,
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
            "payment_mode": payment_mode,
            "items_count": len(items)
        })

    def handle_get_analytics(self):
        cat_rev = db_all("""
            SELECT p.category, ROUND(SUM(bi.price * bi.qty), 2) as revenue
            FROM bill_items bi
            JOIN products p ON bi.product_id = p.id
            GROUP BY p.category
            ORDER BY revenue DESC
        """)

        pay_modes = db_all("""
            SELECT payment_mode, COUNT(*) as count, ROUND(SUM(total), 2) as total
            FROM bills
            WHERE total >= 0
            GROUP BY payment_mode
            ORDER BY total DESC
        """)

        monthly = db_all("""
            SELECT substr(date, 1, 7) as month, ROUND(SUM(total), 2) as revenue, COUNT(*) as bills
            FROM bills
            WHERE total >= 0
            GROUP BY substr(date, 1, 7)
            ORDER BY month DESC
            LIMIT 6
        """)
        monthly.reverse()

        self.send_json({
            "categories": cat_rev,
            "payment_modes": pay_modes,
            "monthly": monthly
        })

    # ---------------- 2. Operations Endpoints ---------------- #

    def handle_get_cash_register(self, query):
        date_str = query.get("date", [date.today().strftime("%Y-%m-%d")])[0]
        bal = analytics.get_cash_balance(date_str)
        logs = []
        logs.append({"type": "Opening", "desc": "Opening Cash Float", "amount": bal["opening"]})
        for b in db_all("SELECT id, customer, total FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total>=0", (f"{date_str}%",)):
            logs.append({"type": "Sale", "desc": f"Bill #{b['id']} - {b['customer']}", "amount": float(b["total"])})
        for b in db_all("SELECT id, customer, total FROM bills WHERE date LIKE ? AND total<0", (f"{date_str}%",)):
            logs.append({"type": "Refund", "desc": f"Refund #{b['id']} - {b['customer']}", "amount": float(b["total"])})
        for e in db_all("SELECT category, amount, note FROM expenses WHERE date=?", (date_str,)):
            logs.append({"type": "Expense", "desc": f"Expense: {e['category']} - {e.get('note', '')}", "amount": -float(e["amount"])})

        self.send_json({"date": date_str, "balance": bal, "logs": logs})

    def handle_set_cash_opening(self, data):
        date_str = data.get("date", date.today().strftime("%Y-%m-%d"))
        amount = float(data.get("amount", 0.0))
        notes = data.get("notes", "Register opening float")

        existing = db_one("SELECT id FROM cash_register WHERE date=?", (date_str,))
        if existing:
            db_run("UPDATE cash_register SET opening_cash=?, notes=? WHERE date=?", (amount, notes, date_str))
        else:
            db_run("INSERT INTO cash_register (date, opening_cash, notes) VALUES (?, ?, ?)", (date_str, amount, notes))
        self.send_json({"success": True, "date": date_str, "opening_cash": amount})

    def handle_get_purchase_orders(self):
        orders = db_all("SELECT * FROM purchase_orders ORDER BY id DESC")
        suggestions = analytics.get_reorder_suggestions()
        self.send_json({"orders": orders, "reorder_suggestions": suggestions})

    def handle_create_purchase_order(self, data):
        pid = int(data.get("product_id"))
        pname = data.get("product_name")
        qty = int(data.get("qty_ordered", 10))
        cost = float(data.get("unit_cost", 0.0))
        supp = data.get("supplier", "").strip()
        note = data.get("note", "").strip()
        today_str = date.today().strftime("%Y-%m-%d")

        poid = db_run("""
            INSERT INTO purchase_orders (date, product_id, product_name, qty_ordered, unit_cost, supplier, status, note)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?)
        """, (today_str, pid, pname, qty, cost, supp, note))
        self.send_json({"success": True, "id": poid})

    def handle_receive_purchase_order(self, po_id):
        po = db_one("SELECT * FROM purchase_orders WHERE id=?", (po_id,))
        if not po:
            return self.send_json({"error": "Purchase order not found"}, 404)
        if po["status"] == "Received":
            return self.send_json({"error": "Already marked received"}, 400)

        with closing(get_conn()) as conn:
            with conn:
                conn.execute("UPDATE purchase_orders SET status='Received' WHERE id=?", (po_id,))
                if po["product_id"]:
                    conn.execute("UPDATE products SET quantity = quantity + ? WHERE id=?", (po["qty_ordered"], po["product_id"]))
        self.send_json({"success": True, "id": po_id})

    def handle_cancel_purchase_order(self, po_id):
        db_run("UPDATE purchase_orders SET status='Cancelled' WHERE id=?", (po_id,))
        self.send_json({"success": True, "id": po_id})

    def handle_reorder_all(self):
        sugs = analytics.get_reorder_suggestions()
        today_str = date.today().strftime("%Y-%m-%d")
        created = 0
        for p in sugs:
            db_run("""
                INSERT INTO purchase_orders (date, product_id, product_name, qty_ordered, unit_cost, supplier, status, note)
                VALUES (?, ?, ?, 20, ?, 'Auto-Restock', 'Pending', 'Auto reorder below threshold')
            """, (today_str, p["id"], p["name"], float(p["price"]) * 0.7))
            created += 1
        self.send_json({"success": True, "created": created})

    def handle_search_refunds(self, query):
        q = query.get("q", [""])[0].strip().lower()
        if not q:
            bills = db_all("SELECT * FROM bills WHERE total > 0 ORDER BY id DESC LIMIT 30")
        else:
            bills = db_all("""
                SELECT * FROM bills
                WHERE total > 0 AND (id = ? OR lower(customer) LIKE ?)
                ORDER BY id DESC LIMIT 30
            """, (int(q) if q.isdigit() else -1, f"%{q}%"))
        self.send_json(bills)

    def handle_process_refund(self, data):
        bill_id = int(data.get("bill_id"))
        reason = data.get("reason", "Customer return").strip()
        b = db_one("SELECT * FROM bills WHERE id=?", (bill_id,))
        if not b:
            return self.send_json({"error": "Bill not found"}, 404)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(get_conn()) as conn:
            with conn:
                cur = conn.execute("""
                    INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, note, coupon_code, staff_id, payment_mode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """, (now_str, b["customer"], b.get("customer_id"),
                      -float(b["subtotal"]), float(b["discount"]), float(b["tax"]), -float(b["total"]),
                      f"REFUND of Bill #{bill_id}: {reason}", b.get("staff_id", 1), b.get("payment_mode", "Cash")))
                refund_id = cur.lastrowid

                items = conn.execute("SELECT * FROM bill_items WHERE bill_id=?", (bill_id,)).fetchall()
                for it in items:
                    conn.execute("""
                        INSERT INTO bill_items (bill_id, product_id, name, price, qty)
                        VALUES (?, ?, ?, ?, ?)
                    """, (refund_id, it["product_id"], it["name"], it["price"], -it["qty"]))
                    if it["product_id"]:
                        conn.execute("UPDATE products SET quantity = quantity + ? WHERE id=?", (it["qty"], it["product_id"]))

                if b.get("customer_id"):
                    conn.execute("""
                        UPDATE customers
                        SET total_spent = MAX(0, total_spent - ?),
                            visit_count = MAX(0, visit_count - 1)
                        WHERE id=?
                    """, (float(b["total"]), b["customer_id"]))

        self.send_json({"success": True, "refund_id": refund_id, "amount": float(b["total"])})

    def handle_get_eod(self, query):
        date_str = query.get("date", [date.today().strftime("%Y-%m-%d")])[0]
        bills = db_all("SELECT * FROM bills WHERE date LIKE ?", (f"{date_str}%",))
        rev = sum(float(b["total"]) for b in bills if float(b["total"]) >= 0)
        refunds = sum(abs(float(b["total"])) for b in bills if float(b["total"]) < 0)
        count = len([b for b in bills if float(b["total"]) >= 0])
        avg = (rev / count) if count else 0.0
        exp = sum(float(r["amount"]) for r in db_all("SELECT amount FROM expenses WHERE date=?", (date_str,)))

        pay_totals = {}
        for b in bills:
            pm = b.get("payment_mode") or "Cash"
            pay_totals[pm] = pay_totals.get(pm, 0.0) + float(b["total"])

        staff_perf = db_all("""
            SELECT s.name, COUNT(b.id) as bills, COALESCE(SUM(b.total), 0) as total
            FROM staff s
            LEFT JOIN bills b ON b.staff_id = s.id AND b.date LIKE ?
            GROUP BY s.id
        """, (f"{date_str}%",))

        top_items = db_all("""
            SELECT bi.name, SUM(bi.qty) as qty, SUM(bi.price * bi.qty) as revenue
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.id
            WHERE b.date LIKE ? AND b.total >= 0
            GROUP BY bi.name
            ORDER BY qty DESC
            LIMIT 6
        """, (f"{date_str}%",))

        self.send_json({
            "date": date_str,
            "revenue": round(rev, 2),
            "refunds": round(refunds, 2),
            "net_revenue": round(rev - refunds, 2),
            "bills_count": count,
            "avg_bill": round(avg, 2),
            "expenses": round(exp, 2),
            "payment_breakdown": pay_totals,
            "staff_performance": staff_perf,
            "top_items": top_items
        })

    # ---------------- 3. People & HR Endpoints ---------------- #

    def handle_get_staff(self):
        staff = db_all("SELECT * FROM staff ORDER BY active DESC, name ASC")
        self.send_json(staff)

    def handle_create_staff(self, data):
        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        role = data.get("role", "Cashier").strip()
        shift_start = data.get("shift_start", "09:00")
        shift_end = data.get("shift_end", "18:00")
        comm = float(data.get("commission_pct", 0.0))
        salary = float(data.get("salary", 20000.0))

        sid = db_run("""
            INSERT INTO staff (name, phone, role, shift_start, shift_end, commission_pct, salary, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (name, phone, role, shift_start, shift_end, comm, salary))
        self.send_json({"success": True, "id": sid, "name": name})

    def handle_get_roster(self, query):
        week = query.get("week", ["2026-W45"])[0]
        rosters = db_all("""
            SELECT r.*, s.name as staff_name, s.role as staff_role
            FROM staff s
            LEFT JOIN roster r ON r.staff_id = s.id AND r.week_start = ?
            ORDER BY s.name ASC
        """, (week,))
        self.send_json({"week": week, "roster": rosters})

    def handle_save_roster(self, data):
        staff_id = int(data.get("staff_id"))
        week = data.get("week", "2026-W45")
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        vals = [data.get(d, "09:00 - 18:00") for d in days]

        existing = db_one("SELECT id FROM roster WHERE staff_id=? AND week_start=?", (staff_id, week))
        if existing:
            db_run("""
                UPDATE roster
                SET monday=?, tuesday=?, wednesday=?, thursday=?, friday=?, saturday=?, sunday=?
                WHERE id=?
            """, tuple(vals + [existing["id"]]))
        else:
            db_run("""
                INSERT INTO roster (staff_id, week_start, monday, tuesday, wednesday, thursday, friday, saturday, sunday)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple([staff_id, week] + vals))
        self.send_json({"success": True})

    def handle_get_salary(self):
        staff_list = db_all("SELECT * FROM staff WHERE active=1")
        now = datetime.now()
        cur_month = f"{now.year:04d}-{now.month:02d}"

        slips = []
        for s in staff_list:
            base = float(s["salary"] or 0.0)
            comm_pct = float(s["commission_pct"] or 0.0)
            sales = sum(float(b["total"]) for b in db_all("SELECT total FROM bills WHERE staff_id=? AND date LIKE ? AND total>0", (s["id"], f"{cur_month}%")))
            comm_amt = round(sales * (comm_pct / 100.0), 2)
            advances = sum(float(a["amount"]) for a in db_all("SELECT amount FROM staff_advances WHERE staff_id=? AND date LIKE ?", (s["id"], f"{cur_month}%")))
            net = round(base + comm_amt - advances, 2)

            slips.append({
                "staff_id": s["id"],
                "name": s["name"],
                "role": s["role"],
                "month": cur_month,
                "base_salary": base,
                "sales_total": sales,
                "commission_pct": comm_pct,
                "commission_amt": comm_amt,
                "advances": advances,
                "net_salary": net
            })
        self.send_json(slips)

    def handle_record_advance(self, data):
        staff_id = int(data.get("staff_id"))
        amount = float(data.get("amount", 0.0))
        note = data.get("note", "").strip()
        today_str = date.today().strftime("%Y-%m-%d")

        aid = db_run("""
            INSERT INTO staff_advances (staff_id, date, amount, note)
            VALUES (?, ?, ?, ?)
        """, (staff_id, today_str, amount, note))
        self.send_json({"success": True, "id": aid})

    def handle_get_targets(self):
        now = datetime.now()
        period = f"{now.year:04d}-{now.month:02d}"
        target_row = db_one("SELECT target_amt FROM sales_targets WHERE period=? AND staff_id=0", (period,))
        target_amt = float(target_row["target_amt"]) if target_row else 500000.0
        current_rev = analytics.get_month_revenue(now.year, now.month)
        pct = round((current_rev / target_amt * 100.0), 1) if target_amt > 0 else 0.0

        staff_targets = []
        for s in db_all("SELECT id, name, role FROM staff WHERE active=1"):
            st = db_one("SELECT target_amt FROM sales_targets WHERE period=? AND staff_id=?", (period, s["id"]))
            s_target = float(st["target_amt"]) if st else 100000.0
            s_rev = sum(float(b["total"]) for b in db_all("SELECT total FROM bills WHERE staff_id=? AND date LIKE ? AND total>0", (s["id"], f"{period}%")))
            s_pct = round((s_rev / s_target * 100.0), 1) if s_target > 0 else 0.0
            staff_targets.append({"staff_id": s["id"], "name": s["name"], "role": s["role"], "target": s_target, "revenue": s_rev, "pct": s_pct})

        self.send_json({
            "period": period,
            "overall_target": target_amt,
            "overall_revenue": current_rev,
            "overall_pct": pct,
            "staff_targets": staff_targets
        })

    def handle_set_target(self, data):
        period = data.get("period", datetime.now().strftime("%Y-%m"))
        staff_id = int(data.get("staff_id", 0))
        amt = float(data.get("target_amt", 500000.0))

        existing = db_one("SELECT id FROM sales_targets WHERE period=? AND staff_id=?", (period, staff_id))
        if existing:
            db_run("UPDATE sales_targets SET target_amt=? WHERE id=?", (amt, existing["id"]))
        else:
            db_run("INSERT INTO sales_targets (period, target_amt, staff_id) VALUES (?, ?, ?)", (period, amt, staff_id))
        self.send_json({"success": True})

    def handle_get_expenses(self):
        expenses = db_all("SELECT * FROM expenses ORDER BY date DESC, id DESC LIMIT 100")
        total = sum(float(e["amount"]) for e in expenses)
        self.send_json({"expenses": expenses, "total": total, "categories": analytics.EXPENSE_CATS})

    def handle_create_expense(self, data):
        dt = data.get("date", date.today().strftime("%Y-%m-%d"))
        cat = data.get("category", "General").strip()
        amt = float(data.get("amount", 0.0))
        note = data.get("note", "").strip()

        eid = db_run("""
            INSERT INTO expenses (date, category, amount, note, staff_id)
            VALUES (?, ?, ?, ?, 1)
        """, (dt, cat, amt, note))
        self.send_json({"success": True, "id": eid})

    def handle_get_holidays(self):
        hols = db_all("SELECT * FROM holidays ORDER BY date ASC")
        self.send_json(hols)

    def handle_create_holiday(self, data):
        dt = data.get("date", "").strip()
        name = data.get("name", "").strip()
        htype = data.get("type", "National").strip()
        hid = db_run("INSERT INTO holidays (date, name, type) VALUES (?, ?, ?)", (dt, name, htype))
        self.send_json({"success": True, "id": hid})

    # ---------------- 4. Analytics Endpoints ---------------- #

    def handle_get_calendar_heat(self, query):
        now = datetime.now()
        year = int(query.get("year", [now.year])[0])
        month = int(query.get("month", [now.month])[0])
        daily_rev = analytics.get_daily_revenue(year, month)
        num_days = calendar.monthrange(year, month)[1]
        days_data = []
        for d in range(1, num_days + 1):
            rev = round(daily_rev.get(d, 0.0), 2)
            days_data.append({"day": d, "date": f"{year:04d}-{month:02d}-{d:02d}", "revenue": rev})
        self.send_json({"year": year, "month": month, "days": days_data})

    def handle_get_gst_report(self, query):
        from_date = query.get("from", [f"{date.today().year}-01-01"])[0]
        to_date = query.get("to", [f"{date.today().year}-12-31"])[0]

        rows = db_all("""
            SELECT p.hsn_code, p.category, SUM(bi.qty) as qty, SUM(bi.price * bi.qty) as taxable_val
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.id
            JOIN products p ON bi.product_id = p.id
            WHERE b.date >= ? AND b.date <= ? AND b.total >= 0
            GROUP BY p.hsn_code, p.category
        """, (from_date, f"{to_date} 23:59:59"))

        taxable_total = sum(float(r["taxable_val"]) for r in rows)
        cgst = round(taxable_total * 0.09, 2)
        sgst = round(taxable_total * 0.09, 2)
        total_tax = round(cgst + sgst, 2)

        self.send_json({
            "from": from_date, "to": to_date,
            "taxable_total": round(taxable_total, 2),
            "cgst": cgst, "sgst": sgst, "total_tax": total_tax,
            "hsn_breakdown": rows
        })

    def handle_get_breakeven(self, query):
        now = datetime.now()
        year = int(query.get("year", [now.year])[0])
        month = int(query.get("month", [now.month])[0])
        be = analytics.get_breakeven(year, month)
        self.send_json(be)

    def handle_get_insights(self):
        dead = analytics.get_dead_stock(30)
        reorders = analytics.get_reorder_suggestions()
        cohorts = analytics.get_cohort_data()
        elasticity = analytics.get_price_elasticity_hints()
        prediction = analytics.predict_tomorrow()
        best_day = analytics.get_best_day_of_week()

        self.send_json({
            "dead_stock": dead,
            "reorder_suggestions": reorders,
            "cohorts": cohorts,
            "elasticity": elasticity,
            "prediction": prediction,
            "best_day": best_day
        })

    def handle_get_analytics_plus(self):
        avgs = analytics.get_weekly_day_avg()
        labels = analytics.WEEKDAYS
        vals = [round(avgs.get(i, 0.0), 2) for i in range(7)]
        self.send_json({
            "labels": labels,
            "averages": vals,
            "best_day": analytics.get_best_day_of_week(),
            "prediction": analytics.predict_tomorrow()
        })

    # ---------------- 5. Settings & Export ---------------- #

    def handle_get_settings(self):
        self.send_json(APP_SETTINGS)

    def handle_save_settings(self, data):
        APP_SETTINGS.update(data)
        save_settings(APP_SETTINGS)
        self.send_json({"success": True, "settings": APP_SETTINGS})

    def handle_export(self, export_type):
        if export_type == "bills":
            rows = db_all("SELECT id, date, customer, subtotal, discount, tax, total, payment_mode FROM bills ORDER BY id ASC")
            csv_lines = ["Invoice,Date,Customer,Subtotal,Discount,Tax,Total,PaymentMode"]
            for r in rows:
                csv_lines.append(f"{r['id']},{r['date']},{r['customer']},{r['subtotal']},{r['discount']},{r['tax']},{r['total']},{r['payment_mode']}")
            data = "\n".join(csv_lines)
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=bills_export.csv")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
        elif export_type == "products":
            rows = db_all("SELECT id, name, price, quantity, category, hsn_code, gst_rate FROM products ORDER BY name ASC")
            csv_lines = ["ID,Name,Price,Stock,Category,HSN,GSTRate"]
            for r in rows:
                csv_lines.append(f"{r['id']},{r['name']},{r['price']},{r['quantity']},{r['category']},{r['hsn_code']},{r['gst_rate']}")
            data = "\n".join(csv_lines)
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=products_export.csv")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
        else:
            self.send_json({"error": "Unknown export type"}, 400)


def run_server(host="127.0.0.1", port=5050):
    server = http.server.ThreadingHTTPServer((host, port), BillFlowAPIHandler)
    print(f"BillFlow Modern Server running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    run_server(port=port)

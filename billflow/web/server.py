"""
BillFlow Modern Web Server & REST API.
Zero external dependencies - powered by Python's standard library.
"""
import http.server
import json
import os
import sys
import urllib.parse
from datetime import datetime

# Add root project dir to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from billflow.database import db_all, db_one, db_run, get_conn, closing
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
            # Serve static files, default to index.html
            if path in ("", "/"):
                self.path = "/index.html"
            return super().do_GET()

        try:
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
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        payload = self.parse_json_body()

        try:
            if path == "/api/checkout":
                self.handle_checkout(payload)
            elif path == "/api/products":
                self.handle_create_product(payload)
            elif path == "/api/customers":
                self.handle_create_customer(payload)
            elif path == "/api/coupons/validate":
                self.handle_validate_coupon(payload)
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
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    # ---------------- API Handlers ---------------- #

    def handle_overview(self):
        totals = db_one("SELECT COALESCE(SUM(total), 0) as rev, COUNT(*) as bills_count FROM bills")
        total_rev = round(totals["rev"] if totals else 0.0, 2)
        total_bills = totals["bills_count"] if totals else 0
        aov = round(total_rev / total_bills, 2) if total_bills else 0.0

        cust_count = db_one("SELECT COUNT(*) as count FROM customers")["count"]
        prod_count = db_one("SELECT COUNT(*) as count FROM products")["count"]
        low_stock = db_one("SELECT COUNT(*) as count FROM products WHERE quantity < 15")["count"]

        # Top products
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

        # Recent bills
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
        # Aggregate revenue by date
        rows = db_all("""
            SELECT substr(date, 1, 10) as day, SUM(total) as revenue, COUNT(*) as orders
            FROM bills
            WHERE date >= date('now', ?)
            GROUP BY substr(date, 1, 10)
            ORDER BY day ASC
        """, (f"-{days} days",))

        if not rows:
            # Fallback if dates are in past months: get latest N recorded days
            rows = db_all("""
                SELECT substr(date, 1, 10) as day, SUM(total) as revenue, COUNT(*) as orders
                FROM bills
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
            SELECT id, date, customer, customer_id, subtotal, discount, tax, total, payment_mode, coupon_code
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
        coupons = db_all("SELECT * FROM coupons WHERE active = 1")
        self.send_json(coupons)

    def handle_validate_coupon(self, data):
        code = data.get("code", "").strip().upper()
        subtotal = float(data.get("subtotal", 0.0))
        coupon = db_one("SELECT * FROM coupons WHERE code = ? AND active = 1", (code,))

        if not coupon:
            return self.send_json({"valid": False, "message": "Invalid coupon code"})

        min_bill = float(coupon.get("min_bill") or 0.0)
        if subtotal < min_bill:
            return self.send_json({
                "valid": False,
                "message": f"Minimum order amount ₹{min_bill:.2f} required for this coupon"
            })

        val = float(coupon["value"])
        if coupon["type"] == "percent":
            discount = round(subtotal * (val / 100.0), 2)
        else:
            discount = round(min(subtotal, val), 2)

        self.send_json({
            "valid": True,
            "code": coupon["code"],
            "type": coupon["type"],
            "value": val,
            "discount": discount,
            "description": coupon.get("description", "")
        })

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

        # Calculate subtotal and tax
        subtotal = 0.0
        for it in items:
            subtotal += float(it["price"]) * int(it["qty"])

        taxable = max(0.0, subtotal - discount)
        tax = round(taxable * 0.18, 2)  # Standard 18% GST
        total = round(taxable + tax, 2)

        with closing(get_conn()) as conn:
            with conn:
                cur = conn.execute("""
                    INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, note, coupon_code, payment_mode, staff_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (now_str, customer_name, customer_id, subtotal, discount, tax, total, "Web Checkout", coupon_code, payment_mode))
                bill_id = cur.lastrowid

                for it in items:
                    conn.execute("""
                        INSERT INTO bill_items (bill_id, product_id, name, price, qty)
                        VALUES (?, ?, ?, ?, ?)
                    """, (bill_id, it["id"], it["name"], float(it["price"]), int(it["qty"])))

                    # Deduct inventory quantity safely
                    conn.execute("""
                        UPDATE products
                        SET quantity = MAX(0, quantity - ?)
                        WHERE id = ?
                    """, (int(it["qty"]), it["id"]))

                # Update customer stats if selected
                if customer_id:
                    conn.execute("""
                        UPDATE customers
                        SET total_spent = total_spent + ?,
                            visit_count = visit_count + 1
                        WHERE id = ?
                    """, (total, customer_id))

                # Increment coupon usage
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
        # Category breakdown
        cat_rev = db_all("""
            SELECT p.category, ROUND(SUM(bi.price * bi.qty), 2) as revenue
            FROM bill_items bi
            JOIN products p ON bi.product_id = p.id
            GROUP BY p.category
            ORDER BY revenue DESC
        """)

        # Payment mode breakdown
        pay_modes = db_all("""
            SELECT payment_mode, COUNT(*) as count, ROUND(SUM(total), 2) as total
            FROM bills
            GROUP BY payment_mode
            ORDER BY total DESC
        """)

        # Monthly performance
        monthly = db_all("""
            SELECT substr(date, 1, 7) as month, ROUND(SUM(total), 2) as revenue, COUNT(*) as bills
            FROM bills
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


def run_server(host="127.0.0.1", port=5050):
    server = http.server.ThreadingHTTPServer((host, port), BillFlowAPIHandler)
    print(f"🚀 BillFlow Modern Server running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    run_server(port=port)

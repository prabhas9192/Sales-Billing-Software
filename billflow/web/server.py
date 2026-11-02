"""
BillFlow Modern Web Server & Comprehensive REST API.
Zero external dependencies - powered by Python's standard library.
"""
import calendar
import csv
import http.cookies
import io
import http.server
import json
import os
import shutil
import socket
import sys
import urllib.parse
from contextlib import closing
from datetime import timedelta

# Add root project dir to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from billflow.database import database_info, db_all, db_one, db_run, get_conn
from billflow.config import APP_SETTINGS, CURRENCIES, currency_code, curr_sym, save_settings
from billflow.dbconfig import DatabaseConfigError
from billflow import analytics, audit, clock, inventory, onboarding
from billflow.inventory import StockError
from billflow.web import staff_session
from billflow.web.access import (
    AccessControl, COOKIE_NAME, PROXY_HEADERS, SESSION_SECONDS,
    host_allowed, is_loopback, lan_addresses,
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

PAYMENT_MODES = ("Cash", "UPI", "Card", "Credit", "Other")


class ApiError(Exception):
    """Raised by a handler to answer with a client error instead of a 500."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


MAX_BODY_BYTES = 1_000_000


class BillFlowAPIHandler(http.server.SimpleHTTPRequestHandler):
    timeout = 30  # seconds a client may stall mid-request before its connection is dropped

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        # No CORS headers on purpose: the UI is served from this same origin, so
        # no other website may read or call the API from a visitor's browser.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_json({"error": "Method not allowed"}, 405)

    def do_HEAD(self):
        if self.guard():
            super().do_HEAD()

    def send_json(self, data, status=200, headers=None):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def parse_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        if content_length > MAX_BODY_BYTES:
            raise ApiError("Request body too large", 413)
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    # ---------------- Access control ---------------- #

    def is_trusted_local(self):
        """True for requests from this computer itself. A request that carries
        proxy headers came through a tunnel or reverse proxy, so it is not local."""
        return is_loopback(self.client_address[0]) and not any(h in self.headers for h in PROXY_HEADERS)

    def is_signed_in(self):
        access = getattr(self.server, "access", None)
        if access is None:
            return False
        try:
            session = http.cookies.SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE_NAME)
        except http.cookies.CookieError:
            return False
        return session is not None and access.valid_token(session.value)

    def current_staff(self) -> dict:
        """The staff member who made this request, proven by the signed bf_staff cookie. Returns a
        dict with at least {id, name}, or {id: None, name: ''} when nobody valid is signed in."""
        try:
            morsel = http.cookies.SimpleCookie(self.headers.get("Cookie", "")).get(staff_session.COOKIE_NAME)
        except http.cookies.CookieError:
            morsel = None
        staff = staff_session.staff_from_cookie(morsel.value) if morsel else None
        return staff or {"id": None, "name": ""}

    def setup_gate(self):
        """On a first run nothing but the setup screen works yet. Returns True to carry on."""
        if not getattr(self.server, "setup_pending", False):
            return True
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/") and not path.startswith("/api/setup/"):
            self.send_json({"error": "Setup is not finished yet.", "setup_required": True}, 409)
            return False
        if path in ("", "/", "/index.html"):
            self.redirect("/setup")
            return False
        return True

    def require_local(self):
        """Setup can change the database, so only the computer running BillFlow may do it, never a phone."""
        if not self.is_trusted_local():
            raise ApiError("Setup can only be changed on the computer running BillFlow.", 403)

    def guard(self):
        """Runs before every request. Returns True to carry on; otherwise the
        refusal has already been sent."""
        host = self.headers.get("Host", "")
        if not host_allowed(host):
            self.send_json({"error": "Open BillFlow by this computer's IP address or name."}, 400)
            return False
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlsplit(origin).netloc.lower() != host.lower():
            self.send_json({"error": "Cross-origin requests are not allowed."}, 403)
            return False
        if self.is_trusted_local() or self.is_signed_in():
            return self.setup_gate()

        path = urllib.parse.urlparse(self.path).path
        if getattr(self.server, "access", None) is None:
            self.send_json({"error": "Remote access is not enabled on this server."}, 403)
        elif path in ("/api/login", "/login", "/login.html"):
            return True
        elif path.startswith("/api/"):
            self.send_json({"error": "PIN required"}, 401)
        else:
            self.redirect("/login")
        return False

    def do_GET(self):
        if not self.guard():
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if not path.startswith("/api/"):
            if path in ("", "/"):
                self.path = "/index.html"
            elif path == "/login":
                self.path = "/login.html"
            elif path == "/setup":
                self.path = "/setup.html"
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
            elif path == "/api/suppliers":
                self.send_json(db_all("SELECT * FROM suppliers ORDER BY LOWER(name), id"))
            elif path == "/api/stock/movements":
                self.send_json(inventory.list_movements(query.get("product_id", [None])[0],
                                                        query.get("type", [None])[0] or None,
                                                        query.get("limit", [200])[0]))
            elif path == "/api/stock/valuation":
                self.send_json(inventory.stock_valuation())
            elif path == "/api/stock/profit":
                days = max(1, min(int(query.get("days", [30])[0]), 3650))
                since = (clock.today() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
                self.send_json({"days": days, **inventory.profit_report(since)})
            elif path == "/api/stock/check":
                mismatches = inventory.ledger_mismatches()
                self.send_json({"ok": not mismatches, "mismatches": mismatches})
            elif path == "/api/stock/reasons":
                self.send_json({"reasons": list(inventory.ADJUST_REASONS),
                                "write_offs": list(inventory.WRITE_OFF_REASONS)})
            elif path == "/api/staff/me":
                self.send_json(self.current_staff())
            elif path == "/api/audit-log":
                self.send_json(audit.get_audit_log(
                    entity=query.get("entity", [None])[0],
                    entity_id=query.get("entity_id", [None])[0],
                    staff_id=query.get("staff_id", [None])[0],
                    limit=query.get("limit", [200])[0]))
            elif path.startswith("/api/refunds/") and path.split("/")[-1].isdigit():
                # GET /api/refunds/{bill_id}: what can still be returned from that bill
                rbid = int(path.split("/")[-1])
                self.send_json(inventory.returnable_lines(rbid))
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
            elif path == "/api/network-info":
                self.handle_network_info()
            elif path == "/api/db-info":
                self.send_json(database_info())
            elif path == "/api/setup/state":
                self.handle_setup_state()
            elif path.startswith("/api/export/"):
                export_type = path.split("/")[-1]
                self.handle_export(export_type)
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except (ApiError, StockError) as e:
            self.send_json({"error": str(e)}, e.status)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_POST(self):
        if not self.guard():
            return
        path = urllib.parse.urlparse(self.path).path

        try:
            payload = self.parse_json_body()
            # Access
            if path == "/api/login":
                self.handle_login(payload)
            elif path == "/api/logout":
                self.handle_logout()
            elif path == "/api/setup/test-db":
                self.handle_setup_test(payload)
            elif path == "/api/setup/apply":
                self.handle_setup_apply(payload)
            # Core
            elif path == "/api/checkout":
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
                self.send_json({"success": True, "id": po_id,
                                **inventory.receive_purchase_order(po_id, payload.get("qty"))})
            elif path.startswith("/api/purchase-orders/") and path.endswith("/cancel"):
                po_id = int(path.split("/")[3])
                self.send_json({"success": True, "id": po_id, "status": inventory.cancel_purchase_order(po_id)})
            elif path == "/api/purchase-orders/reorder-all":
                self.handle_reorder_all()
            elif path == "/api/suppliers":
                self.handle_save_supplier(None, payload)
            elif path == "/api/staff/login":
                self.handle_staff_login(payload)
            elif path == "/api/staff/logout":
                self.handle_staff_logout()
            elif path == "/api/stock/adjust":
                self.handle_adjust_stock(payload)
            elif path.startswith("/api/products/") and path.endswith("/restore"):
                prod_id = int(path.split("/")[3])
                db_run("UPDATE products SET archived = 0 WHERE id = ?", (prod_id,))
                staff = self.current_staff()
                audit.log_action_standalone(staff_id=staff["id"], staff_name=staff["name"],
                                            action="restore", entity="product", entity_id=prod_id)
                self.send_json({"success": True})
            elif path == "/api/stock/stocktake":
                counts = {line.get("product_id"): line.get("counted") for line in payload.get("counts") or []}
                self.send_json({"success": True, **inventory.post_stocktake(counts, str(payload.get("note") or "")[:200])})
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
        except (ApiError, StockError) as e:
            self.send_json({"error": str(e)}, e.status)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_PUT(self):
        if not self.guard():
            return
        path = urllib.parse.urlparse(self.path).path

        try:
            payload = self.parse_json_body()
            if path.startswith("/api/products/"):
                prod_id = int(path.split("/")[-1])
                self.handle_update_product(prod_id, payload)
            elif path.startswith("/api/suppliers/"):
                self.handle_save_supplier(int(path.split("/")[-1]), payload)
            elif path.startswith("/api/coupons/") and path.endswith("/toggle"):
                c_id = int(path.split("/")[3])
                db_run("UPDATE coupons SET active = 1 - active WHERE id = ?", (c_id,))
                self.send_json({"success": True})
            elif path.startswith("/api/staff/") and path.endswith("/pin"):
                self.handle_set_staff_pin(int(path.split("/")[3]), payload)
            elif path.startswith("/api/staff/") and path.endswith("/toggle"):
                s_id = int(path.split("/")[3])
                db_run("UPDATE staff SET active = 1 - active WHERE id = ?", (s_id,))
                self.send_json({"success": True})
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        except (ApiError, StockError) as e:
            self.send_json({"error": str(e)}, e.status)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_DELETE(self):
        if not self.guard():
            return
        path = urllib.parse.urlparse(self.path).path
        try:
            if path.startswith("/api/products/"):
                prod_id = int(path.split("/")[-1])
                db_run("UPDATE products SET archived = 1 WHERE id = ?", (prod_id,))
                staff = self.current_staff()
                audit.log_action_standalone(staff_id=staff["id"], staff_name=staff["name"],
                                            action="archive", entity="product", entity_id=prod_id)
                self.send_json({"success": True})
            elif path.startswith("/api/suppliers/"):
                self.handle_delete_supplier(int(path.split("/")[-1]))
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
        except (ApiError, StockError) as e:
            self.send_json({"error": str(e)}, e.status)
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
        low_stock = analytics.get_low_stock_count()

        top_prods = db_all("""
            SELECT p.id, p.name, p.category, p.price, p.quantity,
                   COALESCE(SUM(bi.qty), 0) as units_sold,
                   COALESCE(SUM(bi.price * bi.qty), 0) as revenue
            FROM products p
            LEFT JOIN bill_items bi ON bi.product_id = p.id
            GROUP BY p.id
            ORDER BY units_sold DESC, p.id
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
            WHERE date >= ? AND total >= 0
            GROUP BY substr(date, 1, 10)
            ORDER BY day ASC
        """, ((clock.today() - timedelta(days=days)).strftime("%Y-%m-%d"),))

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

        code = (query.get("code", [""])[0] or "").strip()

        include_archived = query.get("include_archived", [""])[0] == "1"
        sql = ("SELECT p.id, p.name, p.price, p.quantity, p.category, p.hsn_code, p.gst_rate, p.sku, p.barcode, "
               "p.cost, p.reorder_level, p.supplier_id, p.archived, COALESCE(s.name, '') AS supplier_name "
               "FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id WHERE 1=1")
        if not include_archived:
            sql += " AND p.archived = 0"
        params = []
        if cat and cat.lower() != "all":
            sql += " AND p.category = ?"
            params.append(cat)
        if search:
            sql += " AND (p.name LIKE ? OR p.category LIKE ? OR p.hsn_code LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s, s, s])
        if code:  # an exact barcode or SKU, as a scanner types it
            sql += " AND (p.barcode = ? OR p.sku = ?)"
            params.extend([code, code])
        sql += " ORDER BY LOWER(p.name) ASC, p.id"

        prods = db_all(sql, tuple(params))
        for p in prods:
            p["low"] = analytics.is_low_stock(p["quantity"], p["reorder_level"])
        cats = [r["category"] for r in db_all("SELECT DISTINCT category FROM products ORDER BY category ASC")]

        self.send_json({
            "products": prods,
            "categories": cats
        })

    def product_stock_fields(self, data):
        """The stock-keeping fields a product request may set (SKU, barcode, cost, reorder level,
        supplier), checked. Fields the request leaves out are left out here too."""
        fields = {}
        for key in ("sku", "barcode"):
            if data.get(key) is not None:
                fields[key] = str(data[key]).strip()[:64]
        if data.get("cost") not in (None, ""):
            try:
                cost = float(data["cost"])
            except (TypeError, ValueError):
                raise ApiError("Cost must be a number")
            if cost < 0:
                raise ApiError("Cost cannot be negative")
            fields["cost"] = round(cost, 4)
        if data.get("reorder_level") not in (None, ""):
            level = inventory.whole_number(data["reorder_level"], "Reorder level")
            if level < 0:
                raise ApiError("Reorder level cannot be negative")
            fields["reorder_level"] = level
        if "supplier_id" in data:
            sid = data["supplier_id"]
            fields["supplier_id"] = int(sid) if sid not in (None, "", 0, "0") else None
            if fields["supplier_id"] and not db_one("SELECT id FROM suppliers WHERE id = ?", (fields["supplier_id"],)):
                raise ApiError("Supplier not found", 404)
        return fields

    def check_codes_unused(self, fields, prod_id=0):
        """A barcode or SKU must find exactly one product when it is scanned."""
        for key, label in (("barcode", "Barcode"), ("sku", "SKU")):
            if fields.get(key):
                other = db_one(f"SELECT name FROM products WHERE {key} = ? AND id <> ?", (fields[key], prod_id))
                if other:
                    raise ApiError(f"{label} '{fields[key]}' is already used by '{other['name']}'", 409)

    def handle_create_product(self, data):
        name = str(data.get("name") or "").strip()
        try:
            price = float(data.get("price", 0))
            gst_rate = float(data.get("gst_rate", 18.0))
        except (TypeError, ValueError):
            raise ApiError("Price and GST rate must be numbers")
        quantity = inventory.whole_number(data.get("quantity") or 0, "Initial stock")
        category = str(data.get("category") or "General").strip()
        hsn_code = str(data.get("hsn_code") or "").strip()

        if not name or price <= 0:
            raise ApiError("Valid name and positive price required")
        if quantity < 0:
            raise ApiError("Initial stock cannot be negative")
        fields = self.product_stock_fields(data)
        self.check_codes_unused(fields)

        columns = ["name", "price", "quantity", "category", "hsn_code", "gst_rate", *fields]
        with closing(get_conn()) as conn:
            with conn:
                conn.begin_write()
                prod_id = conn.execute(
                    f"INSERT INTO products ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                    (name, price, 0, category, hsn_code, gst_rate, *fields.values())).lastrowid
                if quantity:
                    inventory.move_stock(conn, prod_id, quantity, "Opening", reason="Opening balance")
                staff = self.current_staff()
                audit.log_action(conn, staff_id=staff["id"], staff_name=staff["name"],
                                 action="create", entity="product", entity_id=prod_id,
                                 detail=f"{name}, qty {quantity}, price {price}")
        self.send_json({"id": prod_id, "name": name, "price": price, "quantity": quantity, "category": category})

    def handle_update_product(self, prod_id, data):
        fields = self.product_stock_fields(data)
        for key in ("name", "category", "hsn_code"):
            if data.get(key) is not None:
                fields[key] = str(data[key]).strip()
        if "name" in fields and not fields["name"]:
            raise ApiError("Product name cannot be empty")
        for key in ("price", "gst_rate"):
            if data.get(key) not in (None, ""):
                try:
                    fields[key] = float(data[key])
                except (TypeError, ValueError):
                    raise ApiError(f"{key.replace('_', ' ').capitalize()} must be a number")
        if fields.get("price", 1) <= 0:
            raise ApiError("Price must be positive")
        self.check_codes_unused(fields, prod_id)

        with closing(get_conn()) as conn:
            with conn:
                conn.begin_write()
                row = conn.execute("SELECT quantity FROM products WHERE id = ?" + conn.for_update, (prod_id,)).fetchone()
                if row is None:
                    raise ApiError("Product not found", 404)
                if fields:
                    conn.execute(f"UPDATE products SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                                 (*fields.values(), prod_id))
                if data.get("quantity") not in (None, ""):
                    # Typing a new stock figure is recorded as an adjustment, so the ledger still adds up.
                    new_qty = inventory.whole_number(data["quantity"], "Stock")
                    if new_qty < 0:
                        raise ApiError("Stock cannot be negative")
                    if new_qty != int(row["quantity"]):
                        inventory.move_stock(conn, prod_id, new_qty - int(row["quantity"]), "Adjustment",
                                             reason="Edited", note="Stock changed in the product editor")
                staff = self.current_staff()
                audit.log_action(conn, staff_id=staff["id"], staff_name=staff["name"],
                                 action="update", entity="product", entity_id=prod_id,
                                 detail=f"Changed: {', '.join(fields.keys())}")
        self.send_json({"success": True, "id": prod_id})

    def handle_adjust_stock(self, data):
        try:
            pid = int(data.get("product_id"))
        except (TypeError, ValueError):
            raise ApiError("product_id is required")
        balance = inventory.adjust_stock(pid, data.get("qty"), data.get("reason"), str(data.get("note") or "")[:200])
        self.send_json({"success": True, "product_id": pid, "quantity": balance})

    def handle_save_supplier(self, supplier_id, data):
        name = str(data.get("name") or "").strip()
        if not name:
            raise ApiError("Supplier name is required")
        clash = db_one("SELECT id FROM suppliers WHERE LOWER(name) = LOWER(?) AND id <> ?", (name, supplier_id or 0))
        if clash:
            raise ApiError(f"A supplier called '{name}' already exists", 409)
        text = lambda key, size: str(data.get(key) or "").strip()[:size]  # noqa: E731
        values = (name[:255], text("phone", 30), text("email", 255), text("gstin", 20).upper(),
                  text("address", 500), text("note", 500))
        if supplier_id is None:
            new_id = db_run("INSERT INTO suppliers (name, phone, email, gstin, address, note) VALUES (?, ?, ?, ?, ?, ?)", values)
            return self.send_json({"success": True, "id": new_id})
        if not db_one("SELECT id FROM suppliers WHERE id = ?", (supplier_id,)):
            raise ApiError("Supplier not found", 404)
        db_run("UPDATE suppliers SET name = ?, phone = ?, email = ?, gstin = ?, address = ?, note = ? WHERE id = ?",
               (*values, supplier_id))
        self.send_json({"success": True, "id": supplier_id})

    def handle_delete_supplier(self, supplier_id):
        with closing(get_conn()) as conn:
            with conn:
                conn.execute("UPDATE products SET supplier_id = NULL WHERE supplier_id = ?", (supplier_id,))
                conn.execute("UPDATE purchase_orders SET supplier_id = NULL WHERE supplier_id = ?", (supplier_id,))
                conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        self.send_json({"success": True})

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
        # The client only says what is in the cart. Prices, GST, discounts and
        # stock are all decided here, from the database.
        requested = {}
        try:
            for it in data.get("items") or []:
                pid, qty = int(it["id"]), int(it["qty"])
                if qty <= 0:
                    raise ValueError("quantity must be positive")
                requested[pid] = requested.get(pid, 0) + qty
            customer_id = int(data["customer_id"]) if data.get("customer_id") else None
        except (KeyError, TypeError, ValueError):
            raise ApiError("Each cart item needs a product id and a positive quantity")
        if not requested:
            raise ApiError("Cart is empty")

        customer_name = data.get("customer_name") or "Walk-in Customer"
        payment_mode = data.get("payment_mode") or "Cash"
        if payment_mode not in PAYMENT_MODES:
            raise ApiError(f"Unknown payment mode '{payment_mode}'")
        coupon_code = (data.get("coupon_code") or "").strip().upper()
        now_str = clock.now().strftime("%Y-%m-%d %H:%M:%S")

        with closing(get_conn()) as conn:
            with conn:
                # Lock first so the stock check and the stock update cannot be
                # interleaved with another sale. Products are locked in id order
                # so two sales cannot wait on each other.
                conn.begin_write()

                lines = []
                for pid, qty in sorted(requested.items()):
                    p = conn.execute(
                        "SELECT id, name, price, quantity, gst_rate, cost FROM products WHERE id = ?" + conn.for_update,
                        (pid,)
                    ).fetchone()
                    if p is None:
                        raise ApiError(f"Product #{pid} not found", 404)
                    went_negative = qty > p["quantity"]
                    lines.append({"id": pid, "name": p["name"], "price": p["price"],
                                  "qty": qty, "gst_rate": p["gst_rate"], "cost": float(p["cost"] or 0),
                                  "_went_negative": went_negative})

                if customer_id:
                    cust = conn.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
                    if cust is None:
                        raise ApiError("Customer not found", 404)
                    customer_name = cust["name"]

                discount = 0.0
                if coupon_code:
                    subtotal = sum(l["price"] * l["qty"] for l in lines)
                    discount, msg = analytics.validate_coupon(coupon_code, subtotal)
                    if discount <= 0:
                        raise ApiError(msg or "Invalid coupon")
                totals = analytics.compute_bill_totals(lines, discount)

                cur = conn.execute("""
                    INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, note, coupon_code, payment_mode, staff_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (now_str, customer_name, customer_id, totals["subtotal"], totals["discount"],
                      totals["tax"], totals["total"], "Register Checkout", coupon_code, payment_mode))
                bill_id = cur.lastrowid

                for l in lines:
                    # The cost is copied onto the line, so this sale's profit stays right when the cost changes later.
                    conn.execute("""
                        INSERT INTO bill_items (bill_id, product_id, name, price, qty, cost)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (bill_id, l["id"], l["name"], l["price"], l["qty"], l["cost"]))
                    inventory.move_stock(conn, l["id"], -l["qty"], "Sale", ref_id=bill_id,
                                         reason=f"Bill #{bill_id}", allow_negative=True)

                if customer_id:
                    conn.execute("""
                        UPDATE customers
                        SET total_spent = total_spent + ?,
                            visit_count = visit_count + 1
                        WHERE id = ?
                    """, (totals["total"], customer_id))

                if coupon_code:
                    conn.execute("""
                        UPDATE coupons
                        SET usage_count = usage_count + 1
                        WHERE code = ?
                    """, (coupon_code,))

                staff = self.current_staff()
                audit.log_action(conn, staff_id=staff["id"], staff_name=staff["name"],
                                 action="sale", entity="bill", entity_id=bill_id,
                                 detail=f"{len(lines)} item(s), total {totals['total']}")

        # auto_tag_customer reads and writes through its own connections, so it
        # has to run after the sale is committed, not inside the transaction.
        if customer_id:
            analytics.auto_tag_customer(customer_id)

        self.send_json({
            "success": True,
            "bill_id": bill_id,
            "negative_stock": [l["name"] for l in lines if l.get("_went_negative")],
            "date": now_str,
            "customer": customer_name,
            "subtotal": totals["subtotal"],
            "discount": totals["discount"],
            "tax": totals["tax"],
            "total": totals["total"],
            "payment_mode": payment_mode,
            "items_count": len(lines)
        })

    def handle_get_analytics(self):
        cat_rev = db_all("""
            SELECT p.category, SUM(bi.price * bi.qty) as revenue
            FROM bill_items bi
            JOIN products p ON bi.product_id = p.id
            GROUP BY p.category
            ORDER BY revenue DESC
        """)

        pay_modes = db_all("""
            SELECT payment_mode, COUNT(*) as count, SUM(total) as total
            FROM bills
            WHERE total >= 0
            GROUP BY payment_mode
            ORDER BY total DESC
        """)

        monthly = db_all("""
            SELECT substr(date, 1, 7) as month, SUM(total) as revenue, COUNT(*) as bills
            FROM bills
            WHERE total >= 0
            GROUP BY substr(date, 1, 7)
            ORDER BY month DESC
            LIMIT 6
        """)
        monthly.reverse()
        for rows, column in ((cat_rev, "revenue"), (pay_modes, "total"), (monthly, "revenue")):
            for row in rows:
                row[column] = round(row[column], 2)

        self.send_json({
            "categories": cat_rev,
            "payment_modes": pay_modes,
            "monthly": monthly
        })

    # ---------------- 2. Operations Endpoints ---------------- #

    def handle_get_cash_register(self, query):
        date_str = query.get("date", [clock.today().strftime("%Y-%m-%d")])[0]
        bal = analytics.get_cash_balance(date_str)
        logs = []
        logs.append({"type": "Opening", "desc": "Opening Cash Float", "amount": bal["opening"]})
        for b in db_all("SELECT id, customer, total FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total>=0", (f"{date_str}%",)):
            logs.append({"type": "Sale", "desc": f"Bill #{b['id']} - {b['customer']}", "amount": float(b["total"])})
        for b in db_all("SELECT id, customer, total FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total<0", (f"{date_str}%",)):
            logs.append({"type": "Refund", "desc": f"Refund #{b['id']} - {b['customer']}", "amount": float(b["total"])})
        for e in db_all("SELECT category, amount, note FROM expenses WHERE date=?", (date_str,)):
            logs.append({"type": "Expense", "desc": f"Expense: {e['category']} - {e.get('note', '')}", "amount": -float(e["amount"])})

        self.send_json({"date": date_str, "balance": bal, "logs": logs})

    def handle_set_cash_opening(self, data):
        date_str = data.get("date", clock.today().strftime("%Y-%m-%d"))
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
        try:
            pid = int(data.get("product_id"))
        except (TypeError, ValueError):
            raise ApiError("product_id is required")
        product = db_one("SELECT id, name, cost, supplier_id FROM products WHERE id = ?", (pid,))
        if product is None:
            raise ApiError("Product not found", 404)
        qty = inventory.whole_number(data.get("qty_ordered", 10), "Quantity to order")
        if qty < 1:
            raise ApiError("Quantity to order must be at least 1")
        try:
            # No cost given: the product's current average cost.
            cost = float(product["cost"] or 0) if data.get("unit_cost") in (None, "") else float(data["unit_cost"])
        except (TypeError, ValueError):
            raise ApiError("Unit cost must be a number")
        if cost < 0:
            raise ApiError("Unit cost cannot be negative")

        supplier_name = str(data.get("supplier") or "").strip()[:255]
        supplier_id = data.get("supplier_id") or None
        if supplier_id:
            supplier = db_one("SELECT id, name FROM suppliers WHERE id = ?", (int(supplier_id),))
            if supplier is None:
                raise ApiError("Supplier not found", 404)
            supplier_id, supplier_name = supplier["id"], supplier["name"]
        elif not supplier_name and product["supplier_id"]:
            supplier = db_one("SELECT id, name FROM suppliers WHERE id = ?", (product["supplier_id"],))
            if supplier:
                supplier_id, supplier_name = supplier["id"], supplier["name"]
        note = str(data.get("note") or "").strip()[:500]
        today_str = clock.today().strftime("%Y-%m-%d")

        poid = db_run("""
            INSERT INTO purchase_orders (date, product_id, product_name, qty_ordered, unit_cost, supplier, supplier_id, status, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
        """, (today_str, pid, product["name"], qty, cost, supplier_name, supplier_id, note))
        self.send_json({"success": True, "id": poid})

    def handle_reorder_all(self):
        sugs = analytics.get_reorder_suggestions()
        today_str = clock.today().strftime("%Y-%m-%d")
        created = 0
        for p in sugs:
            # The product's own cost and supplier; an unknown cost stays 0 rather than a guess,
            # because receiving at a guessed cost would quietly change the product's average cost.
            db_run("""
                INSERT INTO purchase_orders (date, product_id, product_name, qty_ordered, unit_cost, supplier, supplier_id, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', 'Auto reorder below reorder level')
            """, (today_str, p["id"], p["name"], p["suggested_qty"], float(p["cost"] or 0),
                  p["supplier_name"] or "Auto-Restock", p["supplier_id"]))
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
        try:
            bill_id = int(data.get("bill_id"))
        except (TypeError, ValueError):
            raise ApiError("bill_id is required")
        reason = data.get("reason", "Customer return").strip()[:200]
        lines = data.get("lines")
        staff = self.current_staff()

        if lines:
            # Line-level return: the caller specifies which items and how many.
            result = inventory.process_return(
                bill_id, lines, reason=reason,
                staff_id=staff["id"], staff_name=staff["name"])
            return self.send_json({"success": True, **result})

        # Full-bill refund (backward compatible).
        now_str = clock.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(get_conn()) as conn:
            with conn:
                conn.begin_write()
                row = conn.execute("SELECT * FROM bills WHERE id=?" + conn.for_update, (bill_id,)).fetchone()
                if row is None:
                    raise ApiError("Bill not found", 404)
                b = dict(row)
                if float(b["total"]) < 0 or str(b.get("note") or "").startswith("REFUND of Bill #"):
                    raise ApiError("A refund cannot itself be refunded")
                if analytics.find_refund(bill_id, conn):
                    raise ApiError(f"Bill #{bill_id} has already been refunded", 409)

                cur = conn.execute(
                    "INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, "
                    "note, coupon_code, staff_id, payment_mode, refund_of, credit_note) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, '')",
                    (now_str, b["customer"], b.get("customer_id"),
                     -float(b["subtotal"]), float(b["discount"]), float(b["tax"]), -float(b["total"]),
                     f"REFUND of Bill #{bill_id}: {reason}", b.get("staff_id", 1),
                     b.get("payment_mode", "Cash"), bill_id))
                refund_id = cur.lastrowid
                credit_note = f"CN-{refund_id}"
                conn.execute("UPDATE bills SET credit_note = ? WHERE id = ?", (credit_note, refund_id))

                items = conn.execute("SELECT * FROM bill_items WHERE bill_id=? ORDER BY product_id", (bill_id,)).fetchall()
                for it in items:
                    conn.execute(
                        "INSERT INTO bill_items (bill_id, product_id, name, price, qty, cost, return_status) "
                        "VALUES (?, ?, ?, ?, ?, ?, 'restock')",
                        (refund_id, it["product_id"], it["name"], it["price"], -it["qty"], it["cost"]))
                    if it["product_id"]:
                        inventory.move_stock(conn, it["product_id"], it["qty"], "Refund", ref_id=refund_id,
                                             reason=f"Refund of bill #{bill_id}", allow_negative=True)

                if b.get("customer_id"):
                    cust = conn.execute("SELECT total_spent, visit_count FROM customers WHERE id=?" + conn.for_update,
                                        (b["customer_id"],)).fetchone()
                    if cust:
                        conn.execute("UPDATE customers SET total_spent=?, visit_count=? WHERE id=?",
                                     (max(0.0, float(cust["total_spent"]) - float(b["total"])),
                                      max(0, int(cust["visit_count"]) - 1), b["customer_id"]))

                audit.log_action(conn, staff_id=staff["id"], staff_name=staff["name"],
                                 action="refund", entity="bill", entity_id=bill_id,
                                 detail=f"Full refund, credit note {credit_note}, refund bill #{refund_id}")

        self.send_json({"success": True, "refund_id": refund_id, "credit_note": credit_note,
                        "amount": float(b["total"])})

    def handle_get_eod(self, query):
        date_str = query.get("date", [clock.today().strftime("%Y-%m-%d")])[0]
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
            ORDER BY s.id
        """, (f"{date_str}%",))

        top_items = db_all("""
            SELECT bi.name, SUM(bi.qty) as qty, SUM(bi.price * bi.qty) as revenue
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.id
            WHERE b.date LIKE ? AND b.total >= 0
            GROUP BY bi.name
            ORDER BY qty DESC, bi.name
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
        for s in staff:
            s["has_pin"] = bool(s.pop("pin", ""))
        self.send_json(staff)

    def handle_create_staff(self, data):
        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        role = data.get("role", "Cashier").strip()
        shift_start = data.get("shift_start", "09:00")
        shift_end = data.get("shift_end", "18:00")
        comm = float(data.get("commission_pct", 0.0))
        salary = float(data.get("salary", 20000.0))
        pin = str(data.get("pin", "")).strip()
        if pin and (len(pin) < 4 or not pin.isdigit()):
            raise ApiError("Staff PIN must be 4 or more digits")
        if pin and db_one("SELECT id FROM staff WHERE pin = ?", (pin,)):
            raise ApiError("This PIN is already used by another staff member", 409)

        sid = db_run("""
            INSERT INTO staff (name, phone, role, shift_start, shift_end, commission_pct, salary, active, pin)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (name, phone, role, shift_start, shift_end, comm, salary, pin))
        self.send_json({"success": True, "id": sid, "name": name})

    def handle_get_roster(self, query):
        week = query.get("week", [clock.today().strftime("%G-W%V")])[0]
        rosters = db_all("""
            SELECT r.*, s.name as staff_name, s.role as staff_role
            FROM staff s
            LEFT JOIN roster r ON r.staff_id = s.id AND r.week_start = ?
            ORDER BY s.name ASC
        """, (week,))
        self.send_json({"week": week, "roster": rosters})

    def handle_save_roster(self, data):
        staff_id = int(data.get("staff_id"))
        week = data.get("week", clock.today().strftime("%G-W%V"))
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
        staff_list = db_all("SELECT * FROM staff WHERE active=1 ORDER BY id")
        now = clock.now()
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
        today_str = clock.today().strftime("%Y-%m-%d")

        aid = db_run("""
            INSERT INTO staff_advances (staff_id, date, amount, note)
            VALUES (?, ?, ?, ?)
        """, (staff_id, today_str, amount, note))
        self.send_json({"success": True, "id": aid})

    def handle_get_targets(self):
        now = clock.now()
        period = f"{now.year:04d}-{now.month:02d}"
        target_row = db_one("SELECT target_amt FROM sales_targets WHERE period=? AND staff_id=0", (period,))
        target_amt = float(target_row["target_amt"]) if target_row else 500000.0
        current_rev = analytics.get_month_revenue(now.year, now.month)
        pct = round((current_rev / target_amt * 100.0), 1) if target_amt > 0 else 0.0

        staff_targets = []
        for s in db_all("SELECT id, name, role FROM staff WHERE active=1 ORDER BY id"):
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
        period = data.get("period", clock.now().strftime("%Y-%m"))
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
        dt = data.get("date", clock.today().strftime("%Y-%m-%d"))
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
        now = clock.now()
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
        from_date = query.get("from", [f"{clock.today().year}-01-01"])[0]
        to_date = query.get("to", [f"{clock.today().year}-12-31"])[0]

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
        now = clock.now()
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

    def handle_login(self, data):
        access = getattr(self.server, "access", None)
        if access is None:
            raise ApiError("Remote access is not enabled on this server.", 403)
        accepted, wait = access.check_pin(self.client_address[0], str(data.get("pin", "")).strip())
        if not accepted:
            if wait:
                raise ApiError(f"Too many wrong PINs. Try again in {wait} seconds.", 429)
            raise ApiError("Incorrect PIN", 401)
        cookie = f"{COOKIE_NAME}={access.make_token()}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_SECONDS}"
        self.send_json({"success": True}, headers={"Set-Cookie": cookie})

    def handle_logout(self):
        cookie = f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        self.send_json({"success": True}, headers={"Set-Cookie": cookie})

    def handle_staff_login(self, data):
        """A staff member identifies themselves by their own PIN, separate from the access PIN."""
        pin = str(data.get("pin", "")).strip()
        if not pin:
            raise ApiError("Enter your staff PIN")
        client = self.client_address[0]
        wait = staff_session.seconds_locked_out(client)
        if wait:
            raise ApiError(f"Too many wrong PINs. Try again in {wait} seconds.", 429)
        staff = db_one("SELECT id, name, role, permissions FROM staff WHERE pin = ? AND active = 1", (pin,))
        if staff is None:
            staff_session.record_failure(client)
            raise ApiError("Unknown PIN", 401)
        staff_session.clear_failures(client)
        cookie = (f"{staff_session.COOKIE_NAME}={staff_session.make_cookie_value(staff['id'], pin)}; "
                  f"Path=/; HttpOnly; SameSite=Lax; Max-Age={staff_session.SESSION_SECONDS}")
        audit.log_action_standalone(staff_id=staff["id"], staff_name=staff["name"],
                                    action="staff_login", entity="staff", entity_id=staff["id"])
        self.send_json({"success": True, "id": staff["id"], "name": staff["name"],
                        "role": staff["role"]}, headers={"Set-Cookie": cookie})

    def handle_set_staff_pin(self, staff_id, data):
        pin = str(data.get("pin", "")).strip()
        if pin and (len(pin) < 4 or not pin.isdigit()):
            raise ApiError("Staff PIN must be 4 or more digits")
        target = db_one("SELECT id, name FROM staff WHERE id = ?", (staff_id,))
        if target is None:
            raise ApiError("Staff member not found", 404)
        if pin and db_one("SELECT id FROM staff WHERE pin = ? AND id != ?", (pin, staff_id)):
            raise ApiError("This PIN is already used by another staff member", 409)
        db_run("UPDATE staff SET pin = ? WHERE id = ?", (pin, staff_id))
        actor = self.current_staff()
        audit.log_action_standalone(staff_id=actor["id"], staff_name=actor["name"], action="set_pin",
                                    entity="staff", entity_id=staff_id,
                                    detail=f"PIN {'changed' if pin else 'removed'} for {target['name']}")
        self.send_json({"success": True, "has_pin": bool(pin)})

    def handle_staff_logout(self):
        staff = self.current_staff()
        cookie = f"{staff_session.COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        if staff["id"]:
            audit.log_action_standalone(staff_id=staff["id"], staff_name=staff["name"],
                                        action="staff_logout", entity="staff", entity_id=staff["id"])
        self.send_json({"success": True}, headers={"Set-Cookie": cookie})

    def handle_network_info(self):
        access = getattr(self.server, "access", None)
        bound, port = self.server.server_address[:2]
        local = self.is_trusted_local()
        urls = []
        if access is not None:
            addresses = lan_addresses() if bound in ("0.0.0.0", "::") else [bound]
            urls = [f"http://{addr}:{port}/" for addr in addresses]
        self.send_json({
            "lan_enabled": access is not None,
            "port": port,
            "hostname": socket.gethostname(),
            "urls": urls,
            "local": local,
            # The PIN is only ever shown on the host computer itself.
            "pin": access.pin if access is not None and local else None,
        })

    def handle_get_settings(self):
        today = clock.today()
        self.send_json({
            **APP_SETTINGS,
            "currency": currency_code(),
            "currency_symbol": curr_sym(),
            "currency_locale": CURRENCIES[currency_code()]["locale"],
            "currencies": [{"code": c, "name": v["name"], "symbol": v["symbol"]} for c, v in CURRENCIES.items()],
            "today": today.strftime("%Y-%m-%d"),
            "week": today.strftime("%G-W%V"),
        })

    def handle_save_settings(self, data):
        try:
            APP_SETTINGS.update(onboarding.clean_settings(data))
        except onboarding.SetupError as exc:
            raise ApiError(str(exc))
        save_settings(APP_SETTINGS)
        self.send_json({"success": True})

    # ---------------- Setup ---------------- #

    def handle_setup_state(self):
        self.require_local()
        self.send_json(onboarding.state())

    def handle_setup_test(self, data):
        self.require_local()
        try:
            self.send_json(onboarding.test_database(data.get("database") or {}))
        except (onboarding.SetupError, DatabaseConfigError) as exc:
            raise ApiError(str(exc))

    def handle_setup_apply(self, data):
        self.require_local()
        try:
            result = onboarding.apply(data, sharing_active=getattr(self.server, "access", None) is not None)
        except (onboarding.SetupError, DatabaseConfigError) as exc:
            raise ApiError(str(exc))
        self.server.setup_pending = False
        self.send_json(result)

    def send_csv(self, filename, header, rows):
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        data = out.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
            rows = db_all("SELECT id, name, price, quantity, category, hsn_code, gst_rate, sku, barcode, cost, reorder_level "
                          "FROM products ORDER BY LOWER(name), id")
            self.send_csv("products_export.csv",
                          ["ID", "Name", "Price", "Stock", "Category", "HSN", "GSTRate", "SKU", "Barcode", "Cost", "ReorderLevel"],
                          [[r["id"], r["name"], r["price"], r["quantity"], r["category"], r["hsn_code"], r["gst_rate"],
                            r["sku"], r["barcode"], r["cost"], r["reorder_level"]] for r in rows])
        elif export_type == "movements":
            # The stock account per item that GST Rule 56(2) asks for: every receipt, supply and write-off.
            rows = db_all("SELECT m.date, m.product_id, p.name, p.hsn_code, m.type, m.qty, m.balance, m.unit_cost, "
                          "m.reason, m.ref_id, m.note FROM stock_movements m JOIN products p ON p.id = m.product_id "
                          "ORDER BY m.product_id, m.id")
            self.send_csv("stock_movements.csv",
                          ["Date", "ProductID", "Product", "HSN", "Type", "Qty", "Balance", "UnitCost", "Reason", "Reference", "Note"],
                          [[r["date"], r["product_id"], r["name"], r["hsn_code"], r["type"], r["qty"], r["balance"],
                            "" if r["unit_cost"] is None else r["unit_cost"], r["reason"], r["ref_id"] or "", r["note"]]
                           for r in rows])
        else:
            self.send_json({"error": "Unknown export type"}, 400)


class BillFlowServer(http.server.ThreadingHTTPServer):
    # Python's default queue of 5 waiting connections is too short when several phones and the
    # laptop act at once: the extra connections are dropped and each device retries a second later.
    request_queue_size = 128


def create_server(host="127.0.0.1", port=5050, pin=None, setup_pending=False):
    """Bind the server without starting it. Any host other than this computer's
    own loopback address turns on LAN mode, where every other device must enter
    the access PIN (pin, the saved one, or a new random one) before it gets in."""
    server = BillFlowServer((host, port), BillFlowAPIHandler)
    server.setup_pending = setup_pending  # a first run: only the setup screen works until it is finished
    if host != "localhost" and not is_loopback(host):
        server.access = AccessControl(pin=pin)
    return server


def startup_message(server):
    port = server.server_address[1]
    lines = ["BillFlow is running.", f"  On this computer : http://127.0.0.1:{port}/"]
    if getattr(server, "setup_pending", False):
        lines.append(f"  First run        : finish setting up at http://127.0.0.1:{port}/setup")
    access = getattr(server, "access", None)
    if access is not None:
        bound = server.server_address[0]
        for addr in (lan_addresses() if bound in ("0.0.0.0", "::") else [bound]):
            lines.append(f"  On your phone    : http://{addr}:{port}/   (same Wi-Fi / network)")
        lines.append(f"  Access PIN       : {access.pin}   (asked once per phone)")
        if sys.platform.startswith("linux") and shutil.which("firewall-cmd"):
            lines.append(f"  Phone can't connect? Allow the port:  sudo firewall-cmd --add-port={port}/tcp")
    return "\n".join(lines)


def run_server(host="127.0.0.1", port=5050, pin=None):
    server = create_server(host, port, pin)
    print(startup_message(server), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    run_server(port=port)

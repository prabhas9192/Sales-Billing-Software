"""
Tests for checkout, refunds, purchase orders, low-stock alerts and the cash drawer.
Drives the REST API against a throwaway database, so nothing touches your real data.
"""

import http.server
import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from billflow import analytics
from billflow.database import db_one, db_run
from billflow.web.server import BillFlowAPIHandler
from support import DatabaseTestCase


class QuietHandler(BillFlowAPIHandler):
    def log_message(self, *args):
        pass


class ApiTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def api(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            with err:
                return err.code, json.loads(err.read())

    def add_product(self, name="Widget", price=100.0, qty=10, gst=18.0):
        return db_run("INSERT INTO products (name, price, quantity, category, gst_rate) VALUES (?, ?, ?, 'General', ?)",
                      (name, price, qty, gst))

    def add_customer(self, name="Asha", spent=0.0, visits=0):
        return db_run("INSERT INTO customers (name, total_spent, visit_count) VALUES (?, ?, ?)",
                      (name, spent, visits))

    def add_coupon(self, code="SAVE10", kind="percent", value=10.0, min_bill=0.0):
        return db_run("INSERT INTO coupons (code, type, value, min_bill, expiry) VALUES (?, ?, ?, ?, '')",
                      (code, kind, value, min_bill))

    def stock(self, pid):
        return db_one("SELECT quantity FROM products WHERE id = ?", (pid,))["quantity"]

    def bill_count(self):
        return db_one("SELECT COUNT(*) AS n FROM bills")["n"]

    def checkout(self, pid, qty=1, **extra):
        # Deliberately sends a bogus price; the server must ignore it.
        body = {"items": [{"id": pid, "name": "ignored", "price": 0.01, "qty": qty}]}
        body.update(extra)
        return self.api("POST", "/api/checkout", body)


class TestCheckout(ApiTestCase):
    def test_sale_to_registered_customer_completes(self):
        pid = self.add_product(price=1000.0)
        cid = self.add_customer(spent=4900.0, visits=1)
        started = time.time()
        status, res = self.checkout(pid, customer_id=cid)
        self.assertEqual(status, 200, res)
        self.assertLess(time.time() - started, 3, "checkout waited on a database lock")
        cust = db_one("SELECT * FROM customers WHERE id = ?", (cid,))
        self.assertEqual(cust["visit_count"], 2)
        self.assertAlmostEqual(cust["total_spent"], 4900.0 + res["total"])
        self.assertEqual(cust["tag"], "VIP")  # tagging must see the committed sale

    def test_unknown_customer_rejected(self):
        pid = self.add_product()
        status, _ = self.checkout(pid, customer_id=999)
        self.assertEqual(status, 404)
        self.assertEqual(self.bill_count(), 0)

    def test_client_price_ignored_and_product_gst_used(self):
        pid = self.add_product(price=100.0, gst=5.0)
        status, res = self.checkout(pid, qty=2)
        self.assertEqual(status, 200, res)
        self.assertEqual((res["subtotal"], res["tax"], res["total"]), (200.0, 10.0, 210.0))
        item = db_one("SELECT price, qty FROM bill_items WHERE bill_id = ?", (res["bill_id"],))
        self.assertEqual((item["price"], item["qty"]), (100.0, 2))

    def test_mixed_gst_rates(self):
        a = self.add_product("A", 100.0, gst=5.0)
        b = self.add_product("B", 100.0, gst=18.0)
        status, res = self.api("POST", "/api/checkout", {"items": [
            {"id": a, "qty": 1}, {"id": b, "qty": 1}]})
        self.assertEqual(status, 200, res)
        self.assertEqual((res["subtotal"], res["tax"], res["total"]), (200.0, 23.0, 223.0))

    def test_client_discount_ignored_without_coupon(self):
        pid = self.add_product(price=100.0)
        status, res = self.checkout(pid, discount=100000)
        self.assertEqual(status, 200, res)
        self.assertEqual((res["discount"], res["total"]), (0.0, 118.0))
        status, res = self.checkout(pid, discount=-500)
        self.assertEqual(res["total"], 118.0)

    def test_valid_coupon_applied_and_counted(self):
        pid = self.add_product(price=1000.0)
        self.add_coupon("SAVE10", "percent", 10.0)
        status, res = self.checkout(pid, coupon_code=" save10 ")
        self.assertEqual(status, 200, res)
        self.assertEqual((res["discount"], res["tax"], res["total"]), (100.0, 162.0, 1062.0))
        self.assertEqual(db_one("SELECT usage_count FROM coupons WHERE code = 'SAVE10'")["usage_count"], 1)

    def test_invalid_coupon_rejected(self):
        pid = self.add_product()
        self.add_coupon("BIG", "percent", 10.0, min_bill=5000.0)
        for code in ("NOPE", "BIG"):
            status, res = self.checkout(pid, coupon_code=code)
            self.assertEqual(status, 400, res)
        self.assertEqual(self.bill_count(), 0)

    def test_selling_more_than_stock_goes_negative(self):
        """Negative stock is allowed — the sale goes through and the product's stock goes below zero."""
        pid = self.add_product(qty=5)
        status, res = self.checkout(pid, qty=6)
        self.assertEqual(status, 200)
        self.assertEqual(self.stock(pid), -1)
        self.assertIn("negative_stock", res)

    def test_duplicate_cart_lines_merged_and_go_negative(self):
        pid = self.add_product(qty=5)
        status, _ = self.api("POST", "/api/checkout", {"items": [
            {"id": pid, "qty": 3}, {"id": pid, "qty": 3}]})
        self.assertEqual(status, 200)
        self.assertEqual(self.stock(pid), -1)

    def test_bad_requests(self):
        pid = self.add_product()
        self.assertEqual(self.api("POST", "/api/checkout", {"items": []})[0], 400)
        self.assertEqual(self.checkout(pid, qty=0)[0], 400)
        self.assertEqual(self.checkout(pid, qty=-2)[0], 400)
        self.assertEqual(self.checkout(pid, qty="lots")[0], 400)
        self.assertEqual(self.checkout(pid + 99)[0], 404)
        self.assertEqual(self.checkout(pid, payment_mode="Barter")[0], 400)
        self.assertEqual(self.bill_count(), 0)


class TestRefunds(ApiTestCase):
    def sell(self, qty=2, stock=10):
        pid = self.add_product(qty=stock)
        status, res = self.checkout(pid, qty=qty)
        self.assertEqual(status, 200, res)
        return pid, res["bill_id"]

    def test_refund_restocks_exactly_once(self):
        pid, bill_id = self.sell()
        self.assertEqual(self.stock(pid), 8)
        status, res = self.api("POST", "/api/refunds", {"bill_id": bill_id})
        self.assertEqual(status, 200, res)
        self.assertEqual(self.stock(pid), 10)
        status, res = self.api("POST", "/api/refunds", {"bill_id": bill_id})
        self.assertEqual(status, 409, res)
        self.assertEqual(self.stock(pid), 10)
        self.assertEqual(self.bill_count(), 2)

    def test_refund_cannot_be_refunded(self):
        _, bill_id = self.sell()
        _, refund = self.api("POST", "/api/refunds", {"bill_id": bill_id})
        status, _ = self.api("POST", "/api/refunds", {"bill_id": refund["refund_id"]})
        self.assertEqual(status, 400)

    def test_unknown_or_missing_bill(self):
        self.assertEqual(self.api("POST", "/api/refunds", {"bill_id": 12345})[0], 404)
        self.assertEqual(self.api("POST", "/api/refunds", {})[0], 400)

    def test_simultaneous_refunds_only_one_succeeds(self):
        pid, bill_id = self.sell()
        statuses = []
        def refund():
            statuses.append(self.api("POST", "/api/refunds", {"bill_id": bill_id})[0])
        threads = [threading.Thread(target=refund) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(statuses), [200, 409, 409, 409])
        self.assertEqual(self.stock(pid), 10)


class TestPurchaseOrders(ApiTestCase):
    def order(self, pid, qty=10):
        status, res = self.api("POST", "/api/purchase-orders", {
            "product_id": pid, "product_name": "Widget", "qty_ordered": qty, "unit_cost": 50, "supplier": "Acme"})
        self.assertEqual(status, 200, res)
        return res["id"]

    def po_status(self, po_id):
        return db_one("SELECT status FROM purchase_orders WHERE id = ?", (po_id,))["status"]

    def receive(self, po_id):
        return self.api("POST", f"/api/purchase-orders/{po_id}/receive")

    def cancel(self, po_id):
        return self.api("POST", f"/api/purchase-orders/{po_id}/cancel")

    def test_receive_adds_stock_exactly_once(self):
        pid = self.add_product(qty=5)
        po = self.order(pid, qty=10)
        self.assertEqual(self.receive(po)[0], 200)
        self.assertEqual((self.stock(pid), self.po_status(po)), (15, "Received"))
        status, res = self.receive(po)
        self.assertEqual(status, 409, res)
        self.assertEqual(self.stock(pid), 15)

    def test_cancelled_order_cannot_be_received(self):
        pid = self.add_product(qty=5)
        po = self.order(pid)
        self.assertEqual(self.cancel(po)[0], 200)
        status, res = self.receive(po)
        self.assertEqual(status, 409, res)
        self.assertEqual((self.stock(pid), self.po_status(po)), (5, "Cancelled"))

    def test_received_order_cannot_be_cancelled_or_received_again(self):
        pid = self.add_product(qty=5)
        po = self.order(pid, qty=10)
        self.receive(po)
        status, res = self.cancel(po)
        self.assertEqual(status, 409, res)
        self.assertEqual(self.po_status(po), "Received")
        # Cancel-then-receive used to be a way to count the same delivery twice.
        self.assertEqual(self.receive(po)[0], 409)
        self.assertEqual(self.stock(pid), 15)

    def test_cancelling_leaves_stock_alone(self):
        pid = self.add_product(qty=5)
        po = self.order(pid)
        self.assertEqual(self.cancel(po)[0], 200)
        self.assertEqual((self.stock(pid), self.po_status(po)), (5, "Cancelled"))

    def test_unknown_order(self):
        self.assertEqual(self.receive(12345)[0], 404)
        self.assertEqual(self.cancel(12345)[0], 404)

    def test_simultaneous_receives_add_stock_once(self):
        pid = self.add_product(qty=5)
        po = self.order(pid, qty=10)
        statuses = []
        def receive():
            statuses.append(self.receive(po)[0])
        threads = [threading.Thread(target=receive) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(statuses), [200, 409, 409, 409])
        self.assertEqual(self.stock(pid), 15)

    def test_receive_and_cancel_racing_end_in_one_state(self):
        pid = self.add_product(qty=5)
        po = self.order(pid, qty=10)
        results = {}
        threads = [threading.Thread(target=lambda: results.update(receive=self.receive(po)[0])),
                   threading.Thread(target=lambda: results.update(cancel=self.cancel(po)[0]))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Whichever got there first wins. Stock must match the final status, never both.
        if self.po_status(po) == "Received":
            self.assertEqual((results["receive"], results["cancel"], self.stock(pid)), (200, 409, 15))
        else:
            self.assertEqual((self.po_status(po), results["cancel"], results["receive"], self.stock(pid)),
                             ("Cancelled", 200, 409, 5))


class TestLowStock(ApiTestCase):
    def test_dashboard_badges_and_reorder_list_agree(self):
        # Quantities the old, separate rules (under 15, under 10, under 5) disagreed about.
        quantities = [0, 4, 5, 9, 10, 14, 15, 20]
        for i, qty in enumerate(quantities):
            self.add_product(name=f"Item {i}", qty=qty)
        expected = sum(q < analytics.LOW_STOCK_LEVEL for q in quantities)

        status, overview = self.api("GET", "/api/overview")
        self.assertEqual(status, 200, overview)
        status, catalog = self.api("GET", "/api/products")
        self.assertEqual(status, 200, catalog)
        status, orders = self.api("GET", "/api/purchase-orders")
        self.assertEqual(status, 200, orders)

        self.assertEqual(overview["low_stock_count"], expected)
        self.assertEqual(sum(1 for p in catalog["products"] if p["low"]), expected)
        self.assertEqual(len(orders["reorder_suggestions"]), expected)
        for p in catalog["products"]:
            self.assertEqual(p["low"], p["quantity"] < analytics.LOW_STOCK_LEVEL, p)

    def test_selling_the_last_units_makes_an_item_low(self):
        pid = self.add_product(qty=analytics.LOW_STOCK_LEVEL)
        self.assertEqual(self.api("GET", "/api/overview")[1]["low_stock_count"], 0)
        self.assertEqual(self.checkout(pid, qty=1)[0], 200)
        self.assertEqual(self.api("GET", "/api/overview")[1]["low_stock_count"], 1)


class TestCashDrawer(ApiTestCase):
    DAY = "2031-01-01"

    def add_bill(self, total, mode):
        return db_run(
            "INSERT INTO bills (date, customer, subtotal, discount, tax, total, payment_mode) "
            "VALUES (?, 'Walk-in', ?, 0, 0, ?, ?)", (f"{self.DAY} 10:00:00", total, total, mode))

    def seed_day(self):
        db_run("INSERT INTO cash_register (date, opening_cash) VALUES (?, 1000)", (self.DAY,))
        db_run("INSERT INTO expenses (date, category, amount) VALUES (?, 'Rent', 300)", (self.DAY,))
        self.add_bill(500, "Cash")
        self.add_bill(-200, "Cash")   # refund paid out of the drawer
        self.add_bill(400, "UPI")
        self.add_bill(-100, "UPI")    # refund to UPI, drawer untouched

    def test_closing_balance(self):
        self.seed_day()
        bal = analytics.get_cash_balance(self.DAY)
        self.assertEqual(bal["sales_cash"], 500)
        self.assertEqual(bal["refunds"], 200)
        self.assertEqual(bal["expenses"], 300)
        self.assertEqual(bal["closing"], 1000 + 500 - 200 - 300)

    def test_expense_alone_lowers_balance(self):
        db_run("INSERT INTO cash_register (date, opening_cash) VALUES (?, 1000)", (self.DAY,))
        db_run("INSERT INTO expenses (date, category, amount) VALUES (?, 'Rent', 300)", (self.DAY,))
        self.assertEqual(analytics.get_cash_balance(self.DAY)["closing"], 700)

    def test_register_log_adds_up_to_closing(self):
        self.seed_day()
        status, res = self.api("GET", f"/api/cash-register?date={self.DAY}")
        self.assertEqual(status, 200)
        self.assertAlmostEqual(sum(l["amount"] for l in res["logs"]), res["balance"]["closing"])


class TestBillTotals(unittest.TestCase):
    def test_discount_is_clamped_to_subtotal(self):
        lines = [{"price": 100.0, "qty": 1, "gst_rate": 18.0}]
        self.assertEqual(analytics.compute_bill_totals(lines, 500)["total"], 0.0)
        self.assertEqual(analytics.compute_bill_totals(lines, -50)["total"], 118.0)

    def test_empty_cart(self):
        self.assertEqual(analytics.compute_bill_totals([], 10)["total"], 0.0)


if __name__ == "__main__":
    unittest.main()

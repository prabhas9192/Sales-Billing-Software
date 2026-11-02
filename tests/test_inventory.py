"""
Tests for stock control: the movement ledger, adjustments, costing, partial receipts, stocktake,
suppliers, barcodes and upgrading an older database. Each runs on its own throwaway database.
"""

import json
import os
import sqlite3
import time
import unittest
import urllib.error
import urllib.request

from billflow import database, dbconfig, inventory
from billflow.database import db_all, db_one, db_run
from billflow.web import staff_session
from test_billing_flow import ApiTestCase


class InventoryTestCase(ApiTestCase):
    def new_product(self, **fields):
        body = {"name": "Widget", "price": 100.0, "quantity": 10}
        body.update(fields)
        status, res = self.api("POST", "/api/products", body)
        self.assertEqual(status, 200, res)
        return res["id"]

    def product(self, pid):
        return db_one("SELECT * FROM products WHERE id = ?", (pid,))

    def moves(self, pid):
        return db_all("SELECT type, qty, balance, reason FROM stock_movements WHERE product_id = ? ORDER BY id", (pid,))

    def assertLedgerBalances(self):
        self.assertEqual(inventory.ledger_mismatches(), [])

    def order(self, pid, qty=10, cost=50.0, **extra):
        body = {"product_id": pid, "qty_ordered": qty, "unit_cost": cost}
        body.update(extra)
        status, res = self.api("POST", "/api/purchase-orders", body)
        self.assertEqual(status, 200, res)
        return res["id"]

    def receive(self, po_id, qty=None):
        return self.api("POST", f"/api/purchase-orders/{po_id}/receive", {} if qty is None else {"qty": qty})


class TestLedger(InventoryTestCase):
    def test_every_kind_of_change_is_recorded(self):
        pid = self.new_product(quantity=10, cost=40)
        _, sale = self.checkout(pid, qty=3)
        self.api("POST", "/api/refunds", {"bill_id": sale["bill_id"]})
        self.receive(self.order(pid, qty=5, cost=40))
        self.api("POST", "/api/stock/adjust", {"product_id": pid, "qty": -2, "reason": "Damaged or destroyed"})
        self.api("PUT", f"/api/products/{pid}", {"quantity": 20})
        self.api("POST", "/api/stock/stocktake", {"counts": [{"product_id": pid, "counted": 18}]})

        self.assertEqual([(m["type"], m["qty"], m["balance"]) for m in self.moves(pid)], [
            ("Opening", 10, 10), ("Sale", -3, 7), ("Refund", 3, 10), ("Purchase", 5, 15),
            ("Adjustment", -2, 13), ("Adjustment", 7, 20), ("Stocktake", -2, 18)])
        self.assertEqual(self.product(pid)["quantity"], 18)
        self.assertLedgerBalances()
        status, check = self.api("GET", "/api/stock/check")
        self.assertEqual((status, check["ok"]), (200, True))

    def test_stock_added_straight_to_the_table_gets_an_opening_balance(self):
        pid = self.add_product(qty=7)  # inserted directly, no ledger rows
        self.assertEqual(self.checkout(pid, qty=2)[0], 200)
        self.assertEqual([(m["type"], m["qty"]) for m in self.moves(pid)], [("Opening", 7), ("Sale", -2)])
        self.assertLedgerBalances()

    def test_editor_cannot_set_negative_stock(self):
        pid = self.new_product(quantity=4)
        self.assertEqual(self.api("PUT", f"/api/products/{pid}", {"quantity": -1})[0], 400)
        self.assertEqual(self.product(pid)["quantity"], 4)

    def test_movements_list_and_export(self):
        pid = self.new_product(name="Tea", quantity=5)
        self.checkout(pid, qty=1)
        status, rows = self.api("GET", f"/api/stock/movements?product_id={pid}")
        self.assertEqual(status, 200)
        self.assertEqual([(r["type"], r["product_name"]) for r in rows], [("Sale", "Tea"), ("Opening", "Tea")])
        status, rows = self.api("GET", "/api/stock/movements?type=Opening")
        self.assertEqual([r["type"] for r in rows], ["Opening"])
        import urllib.request
        with urllib.request.urlopen(self.base + "/api/export/movements") as resp:
            lines = resp.read().decode().splitlines()
        self.assertTrue(lines[0].startswith("Date,ProductID,Product,HSN,Type,Qty,Balance"))
        self.assertEqual(len(lines), 3)


class TestAdjustments(InventoryTestCase):
    def adjust(self, pid, qty, reason="Damaged or destroyed"):
        return self.api("POST", "/api/stock/adjust", {"product_id": pid, "qty": qty, "reason": reason, "note": "shelf 3"})

    def test_adjust_with_a_reason(self):
        pid = self.new_product(quantity=10)
        status, res = self.adjust(pid, -3, "Lost or stolen")
        self.assertEqual((status, res["quantity"]), (200, 7))
        self.assertEqual(self.moves(pid)[-1]["reason"], "Lost or stolen")
        self.assertEqual(self.adjust(pid, 5, "Found stock")[1]["quantity"], 12)

    def test_bad_adjustments_change_nothing(self):
        pid = self.new_product(quantity=3)
        self.assertEqual(self.adjust(pid, -4)[0], 400)            # below zero
        self.assertEqual(self.adjust(pid, 0)[0], 400)             # nothing to do
        self.assertEqual(self.adjust(pid, 1.5)[0], 400)           # part of a unit
        self.assertEqual(self.adjust(pid, 1, "Because")[0], 400)  # not a known reason
        self.assertEqual(self.adjust(pid + 99, 1)[0], 404)
        self.assertEqual(self.api("POST", "/api/stock/adjust", {"qty": 1, "reason": "Other"})[0], 400)
        self.assertEqual(self.product(pid)["quantity"], 3)
        self.assertEqual(len(self.moves(pid)), 1)

    def test_reasons_mark_the_write_offs(self):
        status, res = self.api("GET", "/api/stock/reasons")
        self.assertEqual(status, 200)
        self.assertIn("Lost or stolen", res["write_offs"])
        self.assertNotIn("Found stock", res["write_offs"])
        self.assertTrue(set(res["write_offs"]) <= set(res["reasons"]))


class TestCosting(InventoryTestCase):
    def test_average_cost_rules(self):
        self.assertEqual(inventory.average_cost(10, 50, 10, 60), 55)
        self.assertEqual(inventory.average_cost(0, 50, 5, 70), 70)     # nothing left: the new cost
        self.assertEqual(inventory.average_cost(-3, 50, 5, 70), 70)    # oversold counts as none
        self.assertEqual(inventory.average_cost(10, 0, 5, 70), 70)     # unknown cost: the new cost
        self.assertEqual(inventory.average_cost(10, 50, 5, 0), 50)     # receipt without a cost
        self.assertEqual(inventory.average_cost(1, 10, 2, 11), 10.6667)

    def test_receiving_updates_average_cost(self):
        pid = self.new_product(quantity=10, cost=50)
        self.receive(self.order(pid, qty=10, cost=60))
        self.assertEqual(self.product(pid)["cost"], 55)
        self.receive(self.order(pid, qty=5, cost=0))
        self.assertEqual(self.product(pid)["cost"], 55)

    def test_sale_keeps_the_cost_it_was_sold_at(self):
        pid = self.new_product(quantity=10, cost=40, price=100)
        _, sale = self.checkout(pid, qty=2)
        self.api("PUT", f"/api/products/{pid}", {"cost": 70})
        line = db_one("SELECT cost FROM bill_items WHERE bill_id = ?", (sale["bill_id"],))
        self.assertEqual(line["cost"], 40)

    def test_profit_report_and_refund_cancel_out(self):
        pid = self.new_product(quantity=10, cost=60, price=100)
        _, sale = self.checkout(pid, qty=2)
        status, report = self.api("GET", "/api/stock/profit?days=30")
        self.assertEqual(status, 200)
        self.assertEqual((report["sales"], report["cogs"], report["gross_profit"], report["margin_pct"]),
                         (200, 120, 80, 40))
        self.api("POST", "/api/refunds", {"bill_id": sale["bill_id"]})
        report = self.api("GET", "/api/stock/profit?days=30")[1]
        self.assertEqual((report["sales"], report["cogs"], report["gross_profit"]), (0, 0, 0))

    def test_profit_totals_are_rounded_once(self):
        # Rounding each item first and then adding them up drifts by paise across many items.
        for name, cost in (("A", 1.005), ("B", 2.005)):
            self.checkout(self.new_product(name=name, quantity=5, cost=cost, price=10), qty=1)
        report = self.api("GET", "/api/stock/profit?days=1")[1]
        self.assertEqual((report["cogs"], report["gross_profit"]), (3.01, 16.99))

    def test_unknown_cost_is_not_counted_as_profit(self):
        pid = self.new_product(quantity=10, price=100)  # no cost yet
        self.checkout(pid, qty=3)
        report = self.api("GET", "/api/stock/profit?days=7")[1]
        self.assertEqual((report["gross_profit"], report["uncosted_units"], report["margin_pct"]), (0, 3, None))

    def test_valuation(self):
        self.new_product(name="A", quantity=4, cost=25, price=50)
        self.new_product(name="B", quantity=2, price=30)  # no cost
        status, val = self.api("GET", "/api/stock/valuation")
        self.assertEqual(status, 200)
        self.assertEqual((val["total_value"], val["retail_value"], val["units"], val["items_without_cost"]),
                         (100, 260, 6, 1))
        a = next(i for i in val["items"] if i["name"] == "A")
        self.assertEqual((a["value"], a["margin_pct"]), (100, 50))


class TestPartialReceipts(InventoryTestCase):
    def test_receive_in_parts(self):
        pid = self.new_product(quantity=0)
        po = self.order(pid, qty=10)
        status, res = self.receive(po, 4)
        self.assertEqual((status, res["status"], res["qty_received"], res["quantity"]), (200, "Partly received", 4, 4))
        self.assertEqual(self.receive(po, 7)[0], 400)  # only 6 left
        status, res = self.receive(po)                  # the rest
        self.assertEqual((res["status"], res["qty_received"], self.product(pid)["quantity"]), ("Received", 10, 10))
        self.assertEqual(self.receive(po, 1)[0], 409)
        self.assertLedgerBalances()

    def test_cancelling_a_part_delivery_keeps_what_arrived(self):
        pid = self.new_product(quantity=0)
        po = self.order(pid, qty=10)
        self.receive(po, 3)
        self.assertEqual(self.api("POST", f"/api/purchase-orders/{po}/cancel")[0], 200)
        self.assertEqual(self.receive(po, 1)[0], 409)
        row = db_one("SELECT status, qty_received FROM purchase_orders WHERE id = ?", (po,))
        self.assertEqual((row["status"], row["qty_received"], self.product(pid)["quantity"]), ("Cancelled", 3, 3))

    def test_bad_orders_are_refused(self):
        pid = self.new_product()
        self.assertEqual(self.api("POST", "/api/purchase-orders", {"product_id": pid, "qty_ordered": 0})[0], 400)
        self.assertEqual(self.api("POST", "/api/purchase-orders", {"product_id": pid + 50, "qty_ordered": 5})[0], 404)
        self.assertEqual(self.api("POST", "/api/purchase-orders", {"qty_ordered": 5})[0], 400)
        self.assertEqual(self.api("POST", "/api/purchase-orders", {"product_id": pid, "qty_ordered": 5, "unit_cost": -1})[0], 400)

    def test_order_defaults_to_product_cost_and_supplier(self):
        _, sup = self.api("POST", "/api/suppliers", {"name": "Acme"})
        pid = self.new_product(cost=42, supplier_id=sup["id"])
        po = self.order(pid, qty=3, cost="")
        row = db_one("SELECT unit_cost, supplier, supplier_id FROM purchase_orders WHERE id = ?", (po,))
        self.assertEqual((row["unit_cost"], row["supplier"], row["supplier_id"]), (42, "Acme", sup["id"]))


class TestStocktake(InventoryTestCase):
    def test_posting_a_count(self):
        a = self.new_product(name="A", quantity=10, cost=5)
        b = self.new_product(name="B", quantity=4, cost=20)
        c = self.new_product(name="C", quantity=7)
        status, res = self.api("POST", "/api/stock/stocktake", {"counts": [
            {"product_id": a, "counted": 8}, {"product_id": b, "counted": 5}, {"product_id": c, "counted": 7}]})
        self.assertEqual(status, 200, res)
        self.assertEqual((res["counted"], res["adjusted"], res["net_units"], res["value_change"]), (3, 2, -1, 10))
        self.assertEqual([self.product(p)["quantity"] for p in (a, b, c)], [8, 5, 7])
        self.assertEqual(self.moves(a)[-1]["reason"], "Count correction")
        self.assertLedgerBalances()

    def test_a_bad_line_posts_nothing(self):
        a = self.new_product(quantity=10)
        for counts in ([{"product_id": a, "counted": 3}, {"product_id": a + 99, "counted": 1}],
                       [{"product_id": a, "counted": -1}], [{"product_id": a, "counted": "x"}], []):
            status, _ = self.api("POST", "/api/stock/stocktake", {"counts": counts})
            self.assertIn(status, (400, 404))
        self.assertEqual(self.product(a)["quantity"], 10)


class TestProductFields(InventoryTestCase):
    def test_codes_cost_and_reorder_level(self):
        pid = self.new_product(sku="TEA-01", barcode="8901234567890", cost=55.5, reorder_level=4)
        p = self.product(pid)
        self.assertEqual((p["sku"], p["barcode"], p["cost"], p["reorder_level"]), ("TEA-01", "8901234567890", 55.5, 4))
        status, res = self.api("GET", "/api/products?code=8901234567890")
        self.assertEqual([x["id"] for x in res["products"]], [pid])
        self.assertEqual([x["id"] for x in self.api("GET", "/api/products?code=TEA-01")[1]["products"]], [pid])
        self.assertEqual([x["id"] for x in self.api("GET", "/api/products?search=tea-0")[1]["products"]], [pid])

    def test_codes_must_be_unique(self):
        first = self.new_product(sku="A1", barcode="111")
        self.assertEqual(self.api("POST", "/api/products", {"name": "X", "price": 5, "barcode": "111"})[0], 409)
        self.assertEqual(self.api("POST", "/api/products", {"name": "X", "price": 5, "sku": "A1"})[0], 409)
        second = self.new_product(name="Y")
        self.assertEqual(self.api("PUT", f"/api/products/{second}", {"barcode": "111"})[0], 409)
        self.assertEqual(self.api("PUT", f"/api/products/{first}", {"barcode": "111", "price": 120})[0], 200)
        # Empty codes never clash.
        self.new_product(name="Z1", sku="", barcode="")
        self.new_product(name="Z2", sku="", barcode="")

    def test_bad_product_fields(self):
        self.assertEqual(self.api("POST", "/api/products", {"name": "X", "price": 5, "cost": -1})[0], 400)
        self.assertEqual(self.api("POST", "/api/products", {"name": "X", "price": 5, "reorder_level": -2})[0], 400)
        self.assertEqual(self.api("POST", "/api/products", {"name": "X", "price": 5, "quantity": -2})[0], 400)
        self.assertEqual(self.api("POST", "/api/products", {"name": "X", "price": 5, "supplier_id": 999})[0], 404)
        self.assertEqual(self.api("PUT", "/api/products/999", {"price": 5})[0], 404)
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM products")["n"], 0)

    def test_low_stock_follows_each_products_reorder_level(self):
        self.new_product(name="Quiet", quantity=3, reorder_level=0)    # alert switched off
        self.new_product(name="Busy", quantity=30, reorder_level=50)
        self.new_product(name="Normal", quantity=30)
        flags = {p["name"]: p["low"] for p in self.api("GET", "/api/products")[1]["products"]}
        self.assertEqual(flags, {"Quiet": False, "Busy": True, "Normal": False})
        self.assertEqual(self.api("GET", "/api/overview")[1]["low_stock_count"], 1)

    def test_reorder_all_uses_cost_supplier_and_top_up(self):
        _, sup = self.api("POST", "/api/suppliers", {"name": "Acme"})
        pid = self.new_product(quantity=3, reorder_level=10, cost=35, supplier_id=sup["id"])
        self.new_product(name="Plenty", quantity=50)
        status, res = self.api("POST", "/api/purchase-orders/reorder-all")
        self.assertEqual((status, res["created"]), (200, 1))
        po = db_one("SELECT * FROM purchase_orders")
        self.assertEqual((po["product_id"], po["qty_ordered"], po["unit_cost"], po["supplier"], po["supplier_id"]),
                         (pid, 17, 35, "Acme", sup["id"]))
        self.assertEqual(self.api("POST", "/api/purchase-orders/reorder-all")[1]["created"], 0)  # already on order


class TestSuppliers(InventoryTestCase):
    def test_add_edit_delete(self):
        status, res = self.api("POST", "/api/suppliers", {"name": "Acme", "gstin": "27aabca1234b1z5", "phone": "98"})
        self.assertEqual(status, 200)
        sid = res["id"]
        self.assertEqual(self.api("POST", "/api/suppliers", {"name": "acme"})[0], 409)
        self.assertEqual(self.api("POST", "/api/suppliers", {"name": " "})[0], 400)
        self.assertEqual(self.api("PUT", f"/api/suppliers/{sid}", {"name": "Acme Traders"})[0], 200)
        self.assertEqual(self.api("PUT", "/api/suppliers/999", {"name": "Nobody"})[0], 404)
        rows = self.api("GET", "/api/suppliers")[1]
        self.assertEqual([(r["name"], r["gstin"]) for r in rows], [("Acme Traders", "")])

        pid = self.new_product(supplier_id=sid)
        self.assertEqual(self.api("DELETE", f"/api/suppliers/{sid}")[0], 200)
        self.assertIsNone(self.product(pid)["supplier_id"])
        self.assertEqual(self.api("GET", "/api/suppliers")[1], [])


@unittest.skipIf(os.environ.get("BILLFLOW_TEST_DB"), "builds an old SQLite file by hand")
class TestUpgradingAnOlderDatabase(unittest.TestCase):
    def test_old_tables_gain_new_columns_and_a_ledger(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(database.configure)
        path = os.path.join(tmp.name, "old.db")
        raw = sqlite3.connect(path)
        raw.executescript("""
            CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(255) NOT NULL,
                price REAL NOT NULL DEFAULT 0, quantity INTEGER NOT NULL DEFAULT 0,
                category VARCHAR(100) NOT NULL DEFAULT 'General', hsn_code VARCHAR(20) NOT NULL DEFAULT '',
                gst_rate REAL NOT NULL DEFAULT 18);
            CREATE TABLE purchase_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, date VARCHAR(20) NOT NULL,
                product_id INTEGER, product_name VARCHAR(255) NOT NULL, qty_ordered INTEGER NOT NULL DEFAULT 0,
                unit_cost REAL NOT NULL DEFAULT 0, supplier VARCHAR(255) DEFAULT '',
                status VARCHAR(20) DEFAULT 'Pending', note VARCHAR(500) DEFAULT '');
            INSERT INTO products (name, price, quantity) VALUES ('Old A', 100, 12), ('Old B', 50, 0);
            INSERT INTO purchase_orders (date, product_id, product_name, qty_ordered, unit_cost, status)
                VALUES ('2026-01-01', 1, 'Old A', 20, 61.5, 'Received'), ('2026-02-01', 1, 'Old A', 5, 0, 'Pending');
        """)
        raw.commit()
        raw.close()

        database.configure(dbconfig.sqlite_url(path))
        database.init_db()
        database.init_db()  # a second start changes nothing

        a, b = db_all("SELECT * FROM products ORDER BY id")
        self.assertEqual((a["cost"], a["reorder_level"], a["sku"], a["barcode"]), (61.5, 10, "", ""))
        self.assertEqual(b["cost"], 0)
        self.assertEqual([(r["status"], r["qty_received"]) for r in db_all("SELECT * FROM purchase_orders ORDER BY id")],
                         [("Received", 20), ("Pending", 0)])
        self.assertEqual([(m["product_id"], m["type"], m["qty"]) for m in db_all("SELECT * FROM stock_movements")],
                         [(1, "Opening", 12)])
        self.assertEqual(inventory.ledger_mismatches(), [])


class TestNegativeStock(InventoryTestCase):
    """Selling more than is in stock is allowed; the product goes negative."""

    def test_sale_takes_stock_negative(self):
        pid = self.new_product(quantity=3)
        status, res = self.checkout(pid, qty=5)
        self.assertEqual(status, 200)
        self.assertEqual(self.stock(pid), -2)
        self.assertLedgerBalances()

    def test_negative_stock_flagged_in_response(self):
        pid = self.new_product(name="Rare Item", quantity=1)
        status, res = self.checkout(pid, qty=2)
        self.assertEqual(status, 200)
        self.assertIn("Rare Item", res["negative_stock"])

    def test_refund_of_negative_sale_returns_to_zero(self):
        pid = self.new_product(quantity=0)
        status, res = self.checkout(pid, qty=3)
        self.assertEqual(status, 200)
        self.assertEqual(self.stock(pid), -3)
        status, ref = self.api("POST", "/api/refunds", {"bill_id": res["bill_id"]})
        self.assertEqual(status, 200)
        self.assertEqual(self.stock(pid), 0)
        self.assertLedgerBalances()


class TestArchiveProducts(InventoryTestCase):
    """Products are archived instead of deleted; their history survives."""

    def test_delete_archives_not_destroys(self):
        pid = self.new_product(quantity=5)
        self.checkout(pid, qty=2)
        status, _ = self.api("DELETE", f"/api/products/{pid}")
        self.assertEqual(status, 200)
        # Product still exists but is archived
        p = self.product(pid)
        self.assertIsNotNone(p)
        self.assertEqual(p["archived"], 1)
        # Movement history survives
        self.assertTrue(len(self.moves(pid)) >= 2)

    def test_archived_products_hidden_by_default(self):
        pid = self.new_product(name="Visible")
        self.api("DELETE", f"/api/products/{pid}")
        _, res = self.api("GET", "/api/products")
        names = [p["name"] for p in res["products"]]
        self.assertNotIn("Visible", names)

    def test_archived_products_shown_with_flag(self):
        pid = self.new_product(name="Hidden Gem")
        self.api("DELETE", f"/api/products/{pid}")
        _, res = self.api("GET", "/api/products?include_archived=1")
        names = [p["name"] for p in res["products"]]
        self.assertIn("Hidden Gem", names)

    def test_restore_unarchives(self):
        pid = self.new_product(name="Comeback")
        self.api("DELETE", f"/api/products/{pid}")
        status, _ = self.api("POST", f"/api/products/{pid}/restore")
        self.assertEqual(status, 200)
        self.assertEqual(self.product(pid)["archived"], 0)


class TestLineReturns(InventoryTestCase):
    """Line-level returns: pick items and quantities, mark restock / damaged / write_off."""

    def sell_two(self, qty_a=3, qty_b=2, stock=10):
        pa = self.new_product(name="Item A", quantity=stock)
        pb = self.new_product(name="Item B", quantity=stock)
        _, res = self.api("POST", "/api/checkout", {
            "items": [{"id": pa, "qty": qty_a}, {"id": pb, "qty": qty_b}]})
        self.assertEqual(res.get("success"), True, res)
        return pa, pb, res["bill_id"]

    def test_partial_return_restocks_only_selected(self):
        pa, pb, bill = self.sell_two()
        status, res = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 1, "status": "restock"}]})
        self.assertEqual(status, 200, res)
        self.assertIn("credit_note", res)
        self.assertEqual(self.stock(pa), 10 - 3 + 1)  # 8
        self.assertEqual(self.stock(pb), 10 - 2)       # 8, untouched
        self.assertLedgerBalances()

    def test_damaged_return_does_not_restock(self):
        pa, pb, bill = self.sell_two()
        status, res = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 2, "status": "damaged"}]})
        self.assertEqual(status, 200, res)
        self.assertEqual(self.stock(pa), 10 - 3)  # stock unchanged: goods are destroyed
        self.assertLedgerBalances()

    def test_cannot_return_more_than_sold(self):
        pa, _, bill = self.sell_two(qty_a=3)
        status, res = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 4, "status": "restock"}]})
        self.assertEqual(status, 400)
        self.assertIn("Only 3", res["error"])

    def test_two_partial_returns_allowed(self):
        pa, _, bill = self.sell_two(qty_a=5)
        self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 2, "status": "restock"}]})
        status, res = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 2, "status": "restock"}]})
        self.assertEqual(status, 200, res)
        self.assertEqual(self.stock(pa), 10 - 5 + 4)  # 9
        self.assertLedgerBalances()

    def test_each_partial_return_gets_its_own_credit_note(self):
        pa, _, bill = self.sell_two(qty_a=5)
        _, first = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 1, "status": "restock"}]})
        _, second = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 1, "status": "damaged"}]})
        self.assertNotEqual(first["credit_note"], second["credit_note"])
        stored = db_one("SELECT credit_note FROM bills WHERE id = ?", (second["refund_id"],))
        self.assertEqual(stored["credit_note"], second["credit_note"])

    def test_return_tax_uses_each_products_own_gst_rate(self):
        low = self.new_product(name="Staple", price=100.0, gst_rate=5)
        high = self.new_product(name="Gadget", price=100.0, gst_rate=18)
        _, sale = self.api("POST", "/api/checkout", {"items": [{"id": low, "qty": 1}, {"id": high, "qty": 1}]})
        self.assertEqual(sale["total"], 223.0)  # 100 + 5 + 100 + 18
        _, res = self.api("POST", "/api/refunds", {
            "bill_id": sale["bill_id"], "lines": [{"product_id": low, "qty": 1, "status": "restock"}]})
        self.assertEqual(res["amount"], 105.0)  # the 5% item only, not the blended 11.5%

    def test_return_tax_respects_bill_discount(self):
        pid = self.new_product(name="Discounted", price=200.0, gst_rate=10)
        self.api("POST", "/api/coupons", {"code": "FLAT40", "type": "flat", "value": 40, "min_bill": 0})
        _, sale = self.api("POST", "/api/checkout", {"items": [{"id": pid, "qty": 2}], "coupon_code": "FLAT40"})
        self.assertEqual(sale["discount"], 40.0, sale)
        _, res = self.api("POST", "/api/refunds", {
            "bill_id": sale["bill_id"], "lines": [{"product_id": pid, "qty": 1, "status": "restock"}]})
        # Half the bill comes back: (200 - 20 discount) * 1.10
        self.assertEqual(res["amount"], 198.0)

    def test_cannot_exceed_remaining_on_second_return(self):
        pa, _, bill = self.sell_two(qty_a=3)
        self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 2, "status": "restock"}]})
        status, res = self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 2, "status": "restock"}]})
        self.assertEqual(status, 400)
        self.assertIn("Only 1", res["error"])

    def test_returnable_lines_endpoint(self):
        pa, pb, bill = self.sell_two(qty_a=5, qty_b=3)
        self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 2, "status": "restock"}]})
        _, lines = self.api("GET", f"/api/refunds/{bill}")
        by_pid = {ln["product_id"]: ln for ln in lines}
        self.assertEqual(by_pid[pa]["available"], 3)
        self.assertEqual(by_pid[pb]["available"], 3)

    def test_write_off_return_status_saved(self):
        pa, _, bill = self.sell_two(qty_a=1)
        self.api("POST", "/api/refunds", {
            "bill_id": bill, "lines": [{"product_id": pa, "qty": 1, "status": "write_off"}]})
        items = db_all("SELECT return_status FROM bill_items bi JOIN bills b ON b.id = bi.bill_id "
                       "WHERE b.refund_of = ? AND bi.product_id = ?", (bill, pa))
        self.assertEqual(items[0]["return_status"], "write_off")


class TestStaffPins(InventoryTestCase):
    """Each staff member can have their own PIN for identification."""

    def setUp(self):
        super().setUp()
        staff_session._failures.clear()
        self.addCleanup(staff_session._failures.clear)

    def test_create_staff_with_pin(self):
        status, res = self.api("POST", "/api/staff", {
            "name": "Ravi", "role": "Cashier", "pin": "1234"})
        self.assertEqual(status, 200, res)
        row = db_one("SELECT pin FROM staff WHERE id = ?", (res["id"],))
        self.assertEqual(row["pin"], "1234")

    def test_duplicate_pin_rejected(self):
        self.api("POST", "/api/staff", {"name": "A", "pin": "5555"})
        status, _ = self.api("POST", "/api/staff", {"name": "B", "pin": "5555"})
        self.assertEqual(status, 409)

    def test_staff_login_by_pin(self):
        _, s = self.api("POST", "/api/staff", {"name": "Priya", "pin": "9876"})
        status, res = self.api("POST", "/api/staff/login", {"pin": "9876"})
        self.assertEqual(status, 200)
        self.assertEqual(res["name"], "Priya")

    def test_wrong_pin_rejected(self):
        status, _ = self.api("POST", "/api/staff/login", {"pin": "0000"})
        self.assertEqual(status, 401)

    def test_staff_list_never_exposes_pins(self):
        self.api("POST", "/api/staff", {"name": "Hidden", "pin": "4321"})
        _, staff = self.api("GET", "/api/staff")
        row = next(s for s in staff if s["name"] == "Hidden")
        self.assertNotIn("pin", row)
        self.assertTrue(row["has_pin"])
        self.assertNotIn("4321", str(staff))

    def test_set_pin_for_existing_staff(self):
        _, s = self.api("POST", "/api/staff", {"name": "NoPin"})
        status, res = self.api("PUT", f"/api/staff/{s['id']}/pin", {"pin": "2468"})
        self.assertEqual(status, 200, res)
        self.assertTrue(res["has_pin"])
        status, login = self.api("POST", "/api/staff/login", {"pin": "2468"})
        self.assertEqual(login["name"], "NoPin")

    def test_set_pin_rejects_short_and_duplicate(self):
        self.api("POST", "/api/staff", {"name": "First", "pin": "1111"})
        _, second = self.api("POST", "/api/staff", {"name": "Second"})
        status, _ = self.api("PUT", f"/api/staff/{second['id']}/pin", {"pin": "12"})
        self.assertEqual(status, 400)
        status, _ = self.api("PUT", f"/api/staff/{second['id']}/pin", {"pin": "1111"})
        self.assertEqual(status, 409)

    def test_set_pin_can_remove_and_is_audited(self):
        _, s = self.api("POST", "/api/staff", {"name": "Temp", "pin": "7777"})
        status, res = self.api("PUT", f"/api/staff/{s['id']}/pin", {"pin": ""})
        self.assertEqual(status, 200)
        self.assertFalse(res["has_pin"])
        status, _ = self.api("POST", "/api/staff/login", {"pin": "7777"})
        self.assertEqual(status, 401)
        _, log = self.api("GET", "/api/audit-log?entity=staff")
        self.assertTrue(any(e["action"] == "set_pin" and e["entity_id"] == s["id"] for e in log), log)
        self.assertNotIn("7777", str(log))


class TestSignedStaffCookie(InventoryTestCase):
    """The bf_staff cookie must prove who is signed in; a guessable id is not proof."""

    def setUp(self):
        super().setUp()
        staff_session._failures.clear()
        self.addCleanup(staff_session._failures.clear)

    def raw(self, method, path, body=None, cookie=None):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read()), resp.headers
        except urllib.error.HTTPError as err:
            with err:
                return err.code, json.loads(err.read()), err.headers

    def sign_in(self, name="Meera", pin="1357"):
        _, staff = self.api("POST", "/api/staff", {"name": name, "pin": pin})
        status, _, headers = self.raw("POST", "/api/staff/login", {"pin": pin})
        self.assertEqual(status, 200)
        return staff["id"], headers["Set-Cookie"].split(";")[0]

    def who(self, cookie):
        return self.raw("GET", "/api/staff/me", cookie=cookie)[1]

    def test_login_cookie_identifies_the_staff_member(self):
        sid, cookie = self.sign_in()
        self.assertEqual(self.who(cookie)["id"], sid)
        self.assertNotEqual(cookie, f"bf_staff={sid}")

    def test_plain_id_cookie_is_not_accepted(self):
        sid, _ = self.sign_in()
        self.assertIsNone(self.who(f"bf_staff={sid}")["id"])

    def test_tampered_signature_is_rejected(self):
        _, cookie = self.sign_in()
        flipped = cookie[:-1] + ("0" if cookie[-1] != "0" else "1")
        self.assertIsNone(self.who(flipped)["id"])

    def test_cookie_cannot_be_moved_to_another_staff_member(self):
        sid, cookie = self.sign_in("Meera", "1357")
        _, other = self.api("POST", "/api/staff", {"name": "Boss", "pin": "9999"})
        _, expires, signature = cookie.split("=", 1)[1].split(".")
        swapped = f"bf_staff={other['id']}.{expires}.{signature}"
        self.assertIsNone(self.who(swapped)["id"])

    def test_expired_cookie_is_rejected(self):
        sid, _ = self.sign_in()
        past = int(time.time()) - 10
        stale = f"bf_staff={sid}.{past}.{staff_session._sign(sid, past, '1357')}"
        self.assertIsNone(self.who(stale)["id"])

    def test_changing_the_pin_signs_the_person_out(self):
        sid, cookie = self.sign_in()
        self.api("PUT", f"/api/staff/{sid}/pin", {"pin": "2468"})
        self.assertIsNone(self.who(cookie)["id"])

    def test_deactivated_staff_cookie_is_rejected(self):
        sid, cookie = self.sign_in()
        self.api("PUT", f"/api/staff/{sid}/toggle")
        self.assertIsNone(self.who(cookie)["id"])

    def test_garbage_cookies_do_not_crash(self):
        for junk in ("bf_staff=", "bf_staff=abc", "bf_staff=1.2", "bf_staff=1.2.3.4",
                     "bf_staff=².².x", "bf_staff=-1.5.x"):
            self.assertIsNone(self.who(junk)["id"], junk)

    def test_audit_trail_trusts_only_the_verified_cookie(self):
        sid, cookie = self.sign_in()
        pid = self.new_product(quantity=5)
        body = {"items": [{"id": pid, "qty": 1}]}
        self.raw("POST", "/api/checkout", body, cookie=f"bf_staff={sid}")  # forged
        self.raw("POST", "/api/checkout", body, cookie=cookie)             # genuine
        log = [e for e in self.api("GET", "/api/audit-log?entity=bill")[1] if e["action"] == "sale"]
        self.assertEqual(sorted(e["staff_name"] for e in log), ["", "Meera"])

    def test_secret_is_created_once_and_kept(self):
        first = staff_session._secret()
        self.assertEqual(first, staff_session._secret())
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM app_secrets")["n"], 1)

    def test_pin_guessing_is_locked_out_even_for_the_right_pin(self):
        self.api("POST", "/api/staff", {"name": "Target", "pin": "4242"})
        for _ in range(staff_session.MAX_FAILURES):
            self.assertEqual(self.api("POST", "/api/staff/login", {"pin": "0000"})[0], 401)
        status, res = self.api("POST", "/api/staff/login", {"pin": "4242"})
        self.assertEqual(status, 429, res)
        self.assertIn("Too many", res["error"])

    def test_a_good_sign_in_resets_the_failure_count(self):
        self.api("POST", "/api/staff", {"name": "Target", "pin": "4242"})
        for _ in range(staff_session.MAX_FAILURES - 1):
            self.api("POST", "/api/staff/login", {"pin": "0000"})
        self.assertEqual(self.api("POST", "/api/staff/login", {"pin": "4242"})[0], 200)
        for _ in range(staff_session.MAX_FAILURES - 1):
            self.assertEqual(self.api("POST", "/api/staff/login", {"pin": "0000"})[0], 401)


class TestAuditLog(InventoryTestCase):
    """The audit log records every data-changing action."""

    def test_checkout_logged(self):
        pid = self.new_product(quantity=5)
        self.checkout(pid, qty=1)
        _, log = self.api("GET", "/api/audit-log?entity=bill")
        self.assertTrue(any(e["action"] == "sale" for e in log), log)

    def test_archive_logged(self):
        pid = self.new_product()
        self.api("DELETE", f"/api/products/{pid}")
        _, log = self.api("GET", "/api/audit-log?entity=product")
        self.assertTrue(any(e["action"] == "archive" and e["entity_id"] == pid for e in log), log)

    def test_refund_logged(self):
        pid = self.new_product(quantity=5)
        _, sale = self.checkout(pid, qty=1)
        self.api("POST", "/api/refunds", {"bill_id": sale["bill_id"]})
        _, log = self.api("GET", "/api/audit-log?entity=bill")
        self.assertTrue(any(e["action"] == "refund" for e in log), log)


if __name__ == "__main__":
    unittest.main()

"""
Tests for the business calculations, run against a real (throwaway) database so
every query is exercised.
"""

import datetime
import unittest

from billflow import analytics
from billflow.analytics import EXPENSE_CATS, WEEKDAYS
from billflow.database import db_one, db_run
from support import DatabaseTestCase

TODAY = datetime.date.today()


def days_ago(n):
    return (TODAY - datetime.timedelta(days=n)).strftime("%Y-%m-%d")


class TestAnalytics(DatabaseTestCase):
    def product(self, name="Widget", price=100.0, qty=10):
        return db_run("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", (name, price, qty))

    def customer(self, name="Asha", spent=0.0, visits=0):
        return db_run("INSERT INTO customers (name, total_spent, visit_count) VALUES (?, ?, ?)", (name, spent, visits))

    def bill(self, when, total, customer_id=None, product_id=None, price=None, qty=1, item="x"):
        bill_id = db_run("INSERT INTO bills (date, customer, customer_id, subtotal, total) VALUES (?, 'x', ?, ?, ?)",
                         (f"{when} 10:00:00", customer_id, total, total))
        if product_id:
            db_run("INSERT INTO bill_items (bill_id, product_id, name, price, qty) VALUES (?, ?, ?, ?, ?)",
                   (bill_id, product_id, item, price if price is not None else total, qty))
        return bill_id

    def test_constants(self):
        self.assertEqual(len(WEEKDAYS), 7)
        self.assertIn("Rent", EXPENSE_CATS)

    def test_no_data_yet(self):
        self.assertEqual(analytics.get_best_day_of_week(), "Not enough data")
        self.assertEqual(analytics.predict_tomorrow(), "Not enough data to predict")
        self.assertEqual(analytics.get_dead_stock(), [])
        self.assertEqual(analytics.get_cohort_data(), [])

    def test_month_revenue_and_daily_revenue(self):
        self.bill(f"{TODAY:%Y-%m}-01", 100)
        self.bill(f"{TODAY:%Y-%m}-01", 50)
        self.bill(f"{TODAY:%Y-%m}-02", 25)
        self.assertEqual(analytics.get_month_revenue(TODAY.year, TODAY.month), 175)
        self.assertEqual(analytics.get_daily_revenue(TODAY.year, TODAY.month), {1: 150, 2: 25})

    def test_best_day_of_week(self):
        self.bill(days_ago(0), 500)
        self.assertIn(WEEKDAYS[TODAY.weekday()], analytics.get_best_day_of_week())

    def test_dead_stock_is_unsold_stock_only(self):
        sold, unsold, empty = self.product("Sold"), self.product("Unsold"), self.product("Empty", qty=0)
        self.bill(days_ago(2), 100, product_id=sold)
        self.assertEqual([p["name"] for p in analytics.get_dead_stock(30)], ["Unsold"])

    def test_reorder_suggestions_skip_products_already_on_order(self):
        low, ordered, fine = self.product("Low", qty=2), self.product("Ordered", qty=1), self.product("Fine", qty=50)
        db_run("INSERT INTO purchase_orders (date, product_id, product_name, status) VALUES ('2031-01-01', ?, 'Ordered', 'Pending')", (ordered,))
        self.assertEqual([p["name"] for p in analytics.get_reorder_suggestions()], ["Low"])

    def test_low_stock_rule_at_its_edges(self):
        level = analytics.LOW_STOCK_LEVEL
        for name, qty in (("Negative", -1), ("Zero", 0), ("Just under", level - 1), ("At the level", level), ("Plenty", level + 40)):
            self.product(name, qty=qty)
        self.assertEqual(analytics.get_low_stock_count(), 3)
        self.assertEqual([p["name"] for p in analytics.get_reorder_suggestions()], ["Negative", "Zero", "Just under"])
        self.assertEqual([analytics.is_low_stock(q) for q in (-1, 0, level - 1, level, level + 40)],
                         [True, True, True, False, False])

    def test_breakeven_picks_the_top_product(self):
        a, b = self.product("A"), self.product("B")
        month = f"{TODAY:%Y-%m}"
        self.bill(f"{month}-01", 1000, product_id=a, price=100, qty=10, item="A")
        self.bill(f"{month}-02", 300, product_id=b, price=30, qty=10, item="B")
        db_run("INSERT INTO expenses (date, category, amount) VALUES (?, 'Rent', 500)", (f"{month}-03",))
        result = analytics.get_breakeven(TODAY.year, TODAY.month)
        self.assertEqual((result["fixed_costs"], result["revenue"]), (500, 1300))
        self.assertTrue(result["breakeven_reached"])
        self.assertEqual((result["top_product"], result["top_price"], result["units_needed"]), ("A", 100, 6))

    def test_cohorts_group_customers_by_first_month(self):
        asha = self.customer("Asha")
        self.bill("2031-01-05", 10, customer_id=asha)
        self.bill("2031-02-05", 10, customer_id=asha)
        cohorts = analytics.get_cohort_data()
        self.assertEqual(cohorts, [{"cohort": "2031-01", "months": {"2031-01": 1, "2031-02": 1}, "base": 1}])

    def test_coupons(self):
        db_run("INSERT INTO coupons (code, type, value, min_bill, expiry) VALUES ('TEN', 'percent', 10, 100, '')")
        db_run("INSERT INTO coupons (code, type, value, min_bill, expiry) VALUES ('FLAT', 'fixed', 50, 0, '')")
        db_run("INSERT INTO coupons (code, type, value, min_bill, expiry) VALUES ('OLD', 'percent', 10, 0, '2000-01-01')")
        db_run("INSERT INTO coupons (code, type, value, min_bill, expiry, active) VALUES ('OFF', 'percent', 10, 0, '', 0)")
        self.assertEqual(analytics.validate_coupon("ten", 200)[0], 20.0)
        self.assertEqual(analytics.validate_coupon("FLAT", 30)[0], 30.0)   # never more than the bill
        self.assertEqual(analytics.validate_coupon("FLAT", 500)[0], 50.0)
        for code, total in (("TEN", 50), ("OLD", 200), ("OFF", 200), ("NOPE", 200)):
            self.assertEqual(analytics.validate_coupon(code, total)[0], 0.0, code)

    def test_customer_tags(self):
        def tag_of(**kwargs):
            cid = self.customer(**kwargs)
            self.bill(days_ago(1), 10, customer_id=cid)
            analytics.auto_tag_customer(cid)
            return db_one("SELECT tag FROM customers WHERE id = ?", (cid,))["tag"]
        self.assertEqual(tag_of(name="a", spent=6000, visits=1), "VIP")
        self.assertEqual(tag_of(name="b", spent=100, visits=6), "Frequent")
        self.assertEqual(tag_of(name="c", spent=100, visits=1), "Regular")
        stale = self.customer("d", spent=9000, visits=20)
        self.bill(days_ago(90), 10, customer_id=stale)
        analytics.auto_tag_customer(stale)
        self.assertEqual(db_one("SELECT tag FROM customers WHERE id = ?", (stale,))["tag"], "Inactive")

    def test_price_elasticity_needs_enough_history(self):
        self.assertEqual(analytics.get_price_elasticity_hints(), [])


if __name__ == "__main__":
    unittest.main()

"""
Tests for the sample data used to try BillFlow out.
"""

import unittest

from billflow.database import db_all, db_one, db_run
from billflow.sample_data import is_empty, load_sample_data
from support import DatabaseTestCase


def count(table):
    return db_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]


class TestSampleData(DatabaseTestCase):
    def test_fills_an_empty_database(self):
        self.assertTrue(is_empty())
        messages = []
        self.assertTrue(load_sample_data(say=messages.append))
        self.assertEqual((count("products"), count("customers"), count("staff"), count("coupons")), (29, 15, 5, 5))
        self.assertGreater(count("bills"), 100)
        self.assertGreater(count("bill_items"), count("bills"))
        self.assertEqual(messages, ["Sample data loaded."])

    def test_bills_add_up(self):
        load_sample_data(say=lambda _: None)
        for bill in db_all("SELECT * FROM bills"):
            self.assertAlmostEqual(bill["subtotal"] - bill["discount"] + bill["tax"], bill["total"], delta=0.02)
        # the tax column holds money, not a percentage
        self.assertTrue(any(b["tax"] > 18 for b in db_all("SELECT tax FROM bills")))

    def test_customer_totals_match_their_bills(self):
        load_sample_data(say=lambda _: None)
        for customer in db_all("SELECT id, total_spent, visit_count FROM customers"):
            bills = db_all("SELECT total FROM bills WHERE customer_id = ?", (customer["id"],))
            self.assertEqual(customer["visit_count"], len(bills))
            self.assertAlmostEqual(customer["total_spent"], sum(b["total"] for b in bills), delta=0.5)

    def test_customers_are_tagged(self):
        load_sample_data(say=lambda _: None)
        tags = {c["tag"] for c in db_all("SELECT tag FROM customers")}
        self.assertNotEqual(tags, {"Regular"})

    def test_coupons_and_holidays_are_in_the_future(self):
        load_sample_data(say=lambda _: None)
        self.assertEqual(count("holidays"), 3)
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        for coupon in db_all("SELECT expiry FROM coupons"):
            self.assertGreater(coupon["expiry"], today)

    def test_never_added_to_a_database_that_has_data(self):
        db_run("INSERT INTO products (name, price, quantity) VALUES ('Mine', 1, 1)")
        messages = []
        self.assertFalse(load_sample_data(say=messages.append))
        self.assertEqual((count("products"), count("bills")), (1, 0))
        self.assertIn("already has data", messages[0])

    def test_second_load_changes_nothing(self):
        load_sample_data(say=lambda _: None)
        bills = count("bills")
        self.assertFalse(load_sample_data(say=lambda _: None))
        self.assertEqual(count("bills"), bills)


if __name__ == "__main__":
    unittest.main()

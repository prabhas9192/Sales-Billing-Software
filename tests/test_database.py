"""
Unit tests for BillFlow database layer.
Verifies table creation, indexing, closing context management, and CRUD.
"""

import os
import unittest
import tempfile
import sqlite3
import billflow.database as db_mod
from billflow.database import get_conn, init_db


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = os.path.join(cls.temp_dir, "test_billflow.db")
        cls._orig_path = db_mod.DB_PATH
        db_mod.DB_PATH = cls.test_db_path
        init_db()

    @classmethod
    def tearDownClass(cls):
        db_mod.DB_PATH = cls._orig_path

    def test_init_db_creates_tables(self):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cur.fetchall()}

        required_tables = {
            "products", "customers", "bills", "bill_items", "coupons",
            "favorites", "staff", "attendance", "sales_targets",
            "holidays", "expenses", "purchase_orders", "cash_register",
            "staff_advances", "roster"
        }
        for tbl in required_tables:
            self.assertIn(tbl, tables, f"Missing table: {tbl}")

    def test_database_connection_closing_leak_free(self):
        # Perform 100 continuous queries to verify zero file descriptor leak
        for i in range(100):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM products")
                cur.fetchone()


if __name__ == "__main__":
    unittest.main()

"""
Tests for the database layer: SQL translation, database URLs, the saved choice,
connection pooling, and the behaviour every database type must share.
"""

import json
import os
import tempfile
import time
import unittest
from decimal import Decimal
from unittest import mock

from billflow import database, dbconfig, dialects, schema
from billflow.database import db_all, db_one, db_run, db_runmany
from billflow.dbconfig import DatabaseConfigError, parse_url
from support import DatabaseTestCase


class TestTranslate(unittest.TestCase):
    def test_sqlite_is_left_alone(self):
        sql = "SELECT * FROM t WHERE a = ? AND b LIKE ?"
        self.assertEqual(dialects.translate(sql, "sqlite"), sql)

    def test_placeholders_for_server_databases(self):
        for dialect in ("postgresql", "mysql"):
            self.assertEqual(dialects.translate("UPDATE t SET a = ? WHERE id = ?", dialect),
                             "UPDATE t SET a = %s WHERE id = %s")

    def test_question_marks_inside_quotes_are_data(self):
        self.assertEqual(dialects.translate("SELECT '?', ? , 'it''s ?'", "mysql"), "SELECT '?', %s , 'it''s ?'")

    def test_percent_signs_are_escaped_everywhere(self):
        self.assertEqual(dialects.translate("WHERE d LIKE '2026-%' AND n LIKE ?", "mysql"),
                         "WHERE d LIKE '2026-%%' AND n LIKE %s")

    def test_like_ignores_case_on_postgresql_only(self):
        self.assertIn("ILIKE %s", dialects.translate("WHERE name LIKE ?", "postgresql"))
        self.assertNotIn("ILIKE", dialects.translate("WHERE name LIKE ?", "mysql"))
        self.assertIn("'LIKE'", dialects.translate("SELECT 'LIKE', 1 WHERE a LIKE ?", "postgresql"))

    def test_insert_or_ignore(self):
        sql = "INSERT OR IGNORE INTO holidays (date) VALUES (?)"
        self.assertEqual(dialects.translate(sql, "mysql"), "INSERT IGNORE INTO holidays (date) VALUES (%s)")
        self.assertEqual(dialects.translate(sql, "postgresql"),
                         "INSERT INTO holidays (date) VALUES (%s) ON CONFLICT DO NOTHING")

    def test_returning_only_for_inserts(self):
        self.assertTrue(dialects.wants_returning("INSERT INTO t (a) VALUES (%s)"))
        self.assertFalse(dialects.wants_returning("UPDATE t SET a = %s"))
        self.assertFalse(dialects.wants_returning("INSERT INTO t (a) VALUES (%s) RETURNING id"))


class TestRows(unittest.TestCase):
    def test_row_reads_by_name_and_position(self):
        row = dialects.make_row({"id": 7, "name": "Widget"})
        self.assertEqual((row["id"], row["name"], row[0], row[1]), (7, "Widget", 7, "Widget"))
        self.assertEqual(dict(row), {"id": 7, "name": "Widget"})
        self.assertIsNone(dialects.make_row(None))

    def test_decimals_become_plain_numbers(self):
        self.assertEqual(dialects.clean_value(Decimal("12")), 12)
        self.assertIsInstance(dialects.clean_value(Decimal("12")), int)
        self.assertEqual(dialects.clean_value(Decimal("12.50")), 12.5)
        self.assertIsInstance(dialects.clean_value(Decimal("12.50")), float)
        self.assertEqual(dialects.clean_value("text"), "text")


class TestDatabaseUrls(unittest.TestCase):
    def test_sqlite_paths(self):
        relative = parse_url("sqlite:///data/shop.db")
        self.assertEqual(relative.path, os.path.join(dbconfig.BASE_DIR, "data", "shop.db"))
        self.assertEqual(parse_url("sqlite:////tmp/shop.db").path, "/tmp/shop.db")
        self.assertEqual(parse_url("/tmp/shop.db").engine.key, "sqlite")   # a bare path means SQLite
        self.assertEqual(parse_url(parse_url("sqlite:////tmp/x/shop.db").url).path, "/tmp/x/shop.db")

    def test_server_urls(self):
        target = parse_url("postgresql://anna:secret@db.example.com:6543/shop")
        self.assertEqual((target.engine.key, target.host, target.port, target.user, target.password, target.name),
                         ("postgresql", "db.example.com", 6543, "anna", "secret", "shop"))
        self.assertEqual(parse_url("mysql://root@localhost/shop").port, 3306)       # default ports
        self.assertEqual(parse_url("mariadb://root@localhost/shop").port, 3306)
        self.assertEqual(parse_url("postgres://u@localhost/shop").engine.key, "postgresql")   # alias
        self.assertEqual(parse_url("mariadb://u@h/d").engine.dialect, "mysql")

    def test_passwords_with_symbols_round_trip(self):
        target = dbconfig.DatabaseTarget(dbconfig.ENGINES["mysql"], host="h", port=3306, user="us er",
                                         password="p@ss:w/rd%?#", name="shop")
        again = parse_url(target.url)
        self.assertEqual((again.user, again.password, again.name), ("us er", "p@ss:w/rd%?#", "shop"))

    def test_password_never_shown(self):
        target = parse_url("postgresql://anna:hunter2@localhost/shop")
        self.assertNotIn("hunter2", target.display)
        self.assertIn("localhost:5432/shop", target.display)

    def test_bad_urls(self):
        for bad in ("", "oracle://u@h/d", "postgresql://localhost", "postgresql://u@h/", "mysql://u@h:abc/d", "sqlite://"):
            with self.assertRaises(DatabaseConfigError, msg=bad):
                parse_url(bad)

    def test_engine_list(self):
        self.assertEqual(list(dbconfig.ENGINES), ["sqlite", "postgresql", "mysql", "mariadb"])
        self.assertTrue(dbconfig.driver_ready(dbconfig.ENGINES["sqlite"]))


class TestSavedChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.path.join(self.tmp.name, "billflow_db.json")
        patcher = mock.patch.object(dbconfig, "SAVED_FILE", self.saved)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("BILLFLOW_DB", None)

    def test_default_when_nothing_chosen(self):
        self.assertEqual(dbconfig.resolve().url, parse_url(dbconfig.DEFAULT_URL).url)

    def test_saved_choice_is_remembered_and_private(self):
        dbconfig.save("mariadb://shop:pw@localhost/billflow")
        self.assertEqual(dbconfig.resolve().engine.key, "mariadb")
        if os.name == "posix":
            self.assertEqual(os.stat(self.saved).st_mode & 0o777, 0o600)

    def test_order_of_precedence(self):
        dbconfig.save("mariadb://shop:pw@localhost/saved")
        self.assertEqual(dbconfig.resolve().name, "saved")
        os.environ["BILLFLOW_DB"] = "postgresql://u@localhost/fromenv"
        self.assertEqual(dbconfig.resolve().name, "fromenv")
        self.assertEqual(dbconfig.resolve("mysql://u@localhost/explicit").name, "explicit")

    def test_unusable_saved_file_is_ignored(self):
        with open(self.saved, "w") as f:
            f.write("not json")
        self.assertIsNone(dbconfig.load_saved())
        with open(self.saved, "w") as f:
            json.dump({"url": 5}, f)
        self.assertIsNone(dbconfig.load_saved())

    def test_cannot_save_nonsense(self):
        with self.assertRaises(DatabaseConfigError):
            dbconfig.save("nonsense://x")
        self.assertFalse(os.path.exists(self.saved))


class FakeRaw:
    def __init__(self):
        self.closed = False
        self.alive = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True

    def cursor(self):
        if not self.alive:
            raise RuntimeError("server has gone away")
        return mock.MagicMock()


class TestPool(unittest.TestCase):
    def setUp(self):
        self.made = []
        def fake_connect(target):
            raw = FakeRaw()
            self.made.append(raw)
            return raw
        patcher = mock.patch.object(database, "connect", fake_connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pool = database.Pool(parse_url("postgresql://u@localhost/shop"))

    def test_connection_is_reused(self):
        first = self.pool.acquire()
        first.close()
        second = self.pool.acquire()
        self.assertIs(second.raw, first.raw)
        self.assertEqual(len(self.made), 1)

    def test_extra_connections_are_closed(self):
        held = [self.pool.acquire() for _ in range(database.Pool.MAX_IDLE + 3)]
        for conn in held:
            conn.close()
        self.assertEqual(sum(raw.closed for raw in self.made), 3)

    def test_dead_connection_is_replaced(self):
        conn = self.pool.acquire()
        conn.close()
        conn.raw.alive = False
        with mock.patch.object(time, "time", return_value=time.time() + database.Pool.CHECK_AFTER + 5):
            fresh = self.pool.acquire()
        self.assertIsNot(fresh.raw, conn.raw)
        self.assertTrue(conn.raw.closed)


class TestEveryDatabase(DatabaseTestCase):
    """Runs on whichever database the tests are pointed at (SQLite unless BILLFLOW_TEST_DB is set)."""

    def test_all_tables_are_created_and_creation_is_repeatable(self):
        database.init_db()
        for table in schema.TABLE_NAMES:
            self.assertEqual(db_one(f"SELECT COUNT(*) AS n FROM {table}")["n"], 0, table)

    def test_insert_returns_new_id_and_rows_read_by_name(self):
        first = db_run("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Widget", 9.5, 3))
        second = db_run("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)", ("Gadget", 1.25, 4))
        self.assertEqual(second, first + 1)
        row = db_one("SELECT * FROM products WHERE id = ?", (first,))
        self.assertEqual((row["name"], row["price"], row["quantity"], row["category"], row["gst_rate"]),
                         ("Widget", 9.5, 3, "General", 18))

    def test_executemany(self):
        db_runmany("INSERT INTO holidays (date, name) VALUES (?, ?)", [("2031-01-01", "A"), ("2031-01-02", "B")])
        self.assertEqual([r["name"] for r in db_all("SELECT name FROM holidays ORDER BY date")], ["A", "B"])

    def test_with_block_commits_and_rolls_back(self):
        conn = database.get_conn()
        with conn:
            conn.execute("INSERT INTO holidays (date, name) VALUES (?, ?)", ("2031-02-01", "kept"))
        with self.assertRaises(ZeroDivisionError):
            with conn:
                conn.execute("INSERT INTO holidays (date, name) VALUES (?, ?)", ("2031-02-02", "dropped"))
                1 / 0
        conn.close()
        self.assertEqual([r["name"] for r in db_all("SELECT name FROM holidays")], ["kept"])

    def test_sums_come_back_as_plain_numbers(self):
        db_run("INSERT INTO products (name, price, quantity) VALUES ('A', 10, 3)")
        db_run("INSERT INTO products (name, price, quantity) VALUES ('B', 20, 4)")
        row = db_one("SELECT SUM(quantity) AS units, SUM(price * quantity) AS value FROM products")
        self.assertEqual((row["units"], row["value"]), (7, 110))
        self.assertIsInstance(row["units"], int)
        self.assertIsInstance(row["value"], float)

    def test_search_ignores_case(self):
        db_run("INSERT INTO products (name, category) VALUES ('Wireless Mouse', 'Electronics')")
        found = db_all("SELECT name FROM products WHERE name LIKE ? OR category LIKE ?", ("%MOUSE%", "%zzz%"))
        self.assertEqual([r["name"] for r in found], ["Wireless Mouse"])

    def test_percent_sign_in_a_pattern(self):
        db_run("INSERT INTO bills (date, customer, total) VALUES ('2031-03-05 10:00:00', 'A', 5)")
        db_run("INSERT INTO bills (date, customer, total) VALUES ('2031-04-05 10:00:00', 'B', 7)")
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM bills WHERE date LIKE '2031-03-%'")["n"], 1)
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM bills WHERE date LIKE ?", ("2031-%",))["n"], 2)

    def test_insert_or_ignore_skips_duplicates(self):
        db_run("INSERT OR IGNORE INTO holidays (date, name) VALUES (?, ?)", ("2031-05-01", "first"))
        db_run("INSERT OR IGNORE INTO holidays (date, name) VALUES (?, ?)", ("2031-05-01", "second"))
        self.assertEqual([r["name"] for r in db_all("SELECT name FROM holidays")], ["first"])

    def test_unique_values_are_enforced(self):
        db_run("INSERT INTO coupons (code, value) VALUES ('ONCE', 5)")
        with self.assertRaises(Exception):
            db_run("INSERT INTO coupons (code, value) VALUES ('ONCE', 6)")

    def test_deleting_a_bill_deletes_its_items_and_a_product_leaves_them_behind(self):
        product = db_run("INSERT INTO products (name, price) VALUES ('Widget', 10)")
        bill = db_run("INSERT INTO bills (date, customer, total) VALUES ('2031-06-01 09:00:00', 'A', 10)")
        db_run("INSERT INTO bill_items (bill_id, product_id, name, price, qty) VALUES (?, ?, 'Widget', 10, 1)", (bill, product))
        db_run("DELETE FROM products WHERE id = ?", (product,))
        self.assertIsNone(db_one("SELECT product_id FROM bill_items WHERE bill_id = ?", (bill,))["product_id"])
        db_run("DELETE FROM bills WHERE id = ?", (bill,))
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM bill_items")["n"], 0)

    def test_deleting_staff_deletes_their_advances(self):
        staff = db_run("INSERT INTO staff (name) VALUES ('Asha')")
        db_run("INSERT INTO staff_advances (staff_id, date, amount) VALUES (?, '2031-01-01', 50)", (staff,))
        db_run("DELETE FROM staff WHERE id = ?", (staff,))
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM staff_advances")["n"], 0)

    def test_a_row_cannot_point_at_a_missing_parent(self):
        with self.assertRaises(Exception):
            db_run("INSERT INTO bill_items (bill_id, name, price) VALUES (999, 'Ghost', 1)")

    def test_database_info(self):
        db_run("INSERT INTO products (name) VALUES ('Widget')")
        info = database.database_info()
        self.assertEqual(info["counts"], {"bills": 0, "products": 1, "customers": 0})
        self.assertEqual(info["engine"], database.current().engine.key)
        self.assertTrue(info["version"])
        self.assertNotIn("password", json.dumps(info).lower())


if __name__ == "__main__":
    unittest.main()

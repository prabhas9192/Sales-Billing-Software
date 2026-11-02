import sqlite3
import os
from contextlib import closing
from .config import DB_PATH

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    with closing(get_conn()) as conn:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT    NOT NULL,
                price    REAL    NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                category TEXT    NOT NULL DEFAULT 'General',
                hsn_code TEXT    NOT NULL DEFAULT '',
                gst_rate REAL    NOT NULL DEFAULT 18
            );
            CREATE TABLE IF NOT EXISTS customers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                phone       TEXT,
                email       TEXT,
                age         INTEGER,
                gender      TEXT,
                tag         TEXT    DEFAULT 'Regular',
                total_spent REAL    NOT NULL DEFAULT 0,
                visit_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS bills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT    NOT NULL,
                customer    TEXT    NOT NULL,
                customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
                subtotal    REAL    NOT NULL DEFAULT 0,
                discount    REAL    NOT NULL DEFAULT 0,
                tax         REAL    NOT NULL DEFAULT 0,
                total       REAL    NOT NULL DEFAULT 0,
                note         TEXT    DEFAULT '',
                coupon_code  TEXT    DEFAULT '',
                payment_mode TEXT    DEFAULT 'Cash'
            );
            CREATE TABLE IF NOT EXISTS bill_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id    INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                name       TEXT    NOT NULL,
                price      REAL    NOT NULL,
                qty        INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS coupons (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                code         TEXT    NOT NULL UNIQUE,
                type         TEXT    NOT NULL DEFAULT 'percent',
                value        REAL    NOT NULL DEFAULT 0,
                min_bill     REAL    NOT NULL DEFAULT 0,
                expiry       TEXT    NOT NULL DEFAULT '',
                active       INTEGER NOT NULL DEFAULT 1,
                usage_count  INTEGER NOT NULL DEFAULT 0,
                description  TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                added_on   TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS staff (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT    NOT NULL,
                phone          TEXT    DEFAULT '',
                role           TEXT    DEFAULT 'Staff',
                shift_start    TEXT    DEFAULT '09:00',
                shift_end      TEXT    DEFAULT '18:00',
                commission_pct REAL    DEFAULT 0,
                salary         REAL    DEFAULT 0,
                active         INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS attendance (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id     INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
                date         TEXT    NOT NULL,
                clock_in     TEXT    DEFAULT '',
                clock_out    TEXT    DEFAULT '',
                overtime_hrs REAL    DEFAULT 0,
                note         TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS sales_targets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                period     TEXT    NOT NULL,
                target_amt REAL    NOT NULL DEFAULT 0,
                staff_id   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS holidays (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT    NOT NULL UNIQUE,
                name TEXT    NOT NULL DEFAULT '',
                type TEXT    NOT NULL DEFAULT 'holiday'
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT    NOT NULL,
                category TEXT    NOT NULL DEFAULT 'General',
                amount   REAL    NOT NULL DEFAULT 0,
                note     TEXT    DEFAULT '',
                staff_id INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT    NOT NULL,
                product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_name TEXT    NOT NULL,
                qty_ordered  INTEGER NOT NULL DEFAULT 0,
                unit_cost    REAL    NOT NULL DEFAULT 0,
                supplier     TEXT    DEFAULT '',
                status       TEXT    DEFAULT 'Pending',
                note         TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS cash_register (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT    NOT NULL UNIQUE,
                opening_cash REAL    NOT NULL DEFAULT 0,
                notes        TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS staff_advances (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
                date     TEXT    NOT NULL,
                amount   REAL    NOT NULL DEFAULT 0,
                note     TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS roster (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id   INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
                week_start TEXT    NOT NULL,
                monday     TEXT    DEFAULT '',
                tuesday    TEXT    DEFAULT '',
                wednesday  TEXT    DEFAULT '',
                thursday   TEXT    DEFAULT '',
                friday     TEXT    DEFAULT '',
                saturday   TEXT    DEFAULT '',
                sunday     TEXT    DEFAULT ''
            );
            """)

            # Safe column migrations
            for col_sql in [
                "ALTER TABLE customers ADD COLUMN tag TEXT DEFAULT 'Regular'",
                "ALTER TABLE customers ADD COLUMN total_spent REAL NOT NULL DEFAULT 0",
                "ALTER TABLE customers ADD COLUMN visit_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE bills ADD COLUMN coupon_code TEXT DEFAULT ''",
                "ALTER TABLE bills ADD COLUMN staff_id INTEGER DEFAULT 0",
                "ALTER TABLE bills ADD COLUMN payment_mode TEXT DEFAULT 'Cash'",
                "ALTER TABLE products ADD COLUMN hsn_code TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE products ADD COLUMN gst_rate REAL NOT NULL DEFAULT 18",
            ]:
                try:
                    conn.execute(col_sql)
                except Exception:
                    pass

            # Performance B-Tree Indexes
            conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_bill_items_bid ON bill_items(bill_id);
            CREATE INDEX IF NOT EXISTS idx_bill_items_pid ON bill_items(product_id);
            CREATE INDEX IF NOT EXISTS idx_bills_date ON bills(date);
            CREATE INDEX IF NOT EXISTS idx_bills_cust ON bills(customer_id);
            CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
            CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
            CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
            CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
            CREATE INDEX IF NOT EXISTS idx_attendance_staff_date ON attendance(staff_id, date);
            """)

# ─────────────────────────── DB helpers (Leak-Free) ──────────────────────
def db_all(sql: str, params: tuple = ()) -> list[dict]:
    with closing(get_conn()) as conn:
        with conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

def db_one(sql: str, params: tuple = ()) -> dict | None:
    with closing(get_conn()) as conn:
        with conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

def db_run(sql: str, params: tuple = ()) -> int:
    with closing(get_conn()) as conn:
        with conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid

def db_runmany(sql: str, seq: list):
    with closing(get_conn()) as conn:
        with conn:
            conn.executemany(sql, seq)

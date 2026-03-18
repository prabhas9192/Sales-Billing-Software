import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3, os, datetime, csv, textwrap, re, calendar
from collections import defaultdict, Counter
from typing import Any, Optional, cast, overload, Literal
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # pyre-ignore[21]
from matplotlib.figure import Figure  # pyre-ignore[21]

# ─────────────────────────── Paths ───────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "billflow.db")

# ═══════════════════════════════════════════════════════════════
#  DATABASE LAYER
# ═══════════════════════════════════════════════════════════════
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_conn() as conn:
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
        conn.commit()

init_db()

# ─────────────────────────── DB helpers ──────────────────────
def db_all(sql, params=()):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def db_one(sql, params=()):
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

def db_run(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid

def db_runmany(sql, seq):
    with get_conn() as conn:
        conn.executemany(sql, seq)
        conn.commit()

# ═══════════════════════════════════════════════════════════════
#  VALIDATION
# ═══════════════════════════════════════════════════════════════
def validate_phone(phone: str):
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[-10:]  # pyre-ignore
    elif digits.startswith('0') and len(digits) == 11:
        digits = digits[-10:]  # pyre-ignore
    if len(digits) < 10:
        return f"Phone too short ({len(digits)} digits). Must be 10 digits."
    if len(digits) > 10:
        return f"Phone too long ({len(digits)} digits). Must be 10 digits."
    return None

def validate_email(email: str):
    if email and re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.-]+', email) is None:
        return "Invalid email address format."
    return None

def _safe_float(s) -> float:
    try:
        return max(0.0, float(s))
    except (ValueError, TypeError):
        return 0.0

def _clamp_discount(val) -> float:
    return min(max(_safe_float(val), 0.0), 100.0)

def _clamp_tax(val) -> float:
    return max(_safe_float(val), 0.0)

def _rnd(val: float, digits: int = 2) -> float:
    return float(f"{float(val):.{digits}f}")

# ═══════════════════════════════════════════════════════════════
#  SMART ANALYTICS HELPERS
# ═══════════════════════════════════════════════════════════════
WEEKDAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

def get_daily_revenue(year: int, month: int) -> dict:
    rows = db_all("SELECT date, total FROM bills WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))
    totals: dict[int, float] = defaultdict[int, float](float)
    for r in rows:
        try:
            day = int(r["date"][8:10])  # pyre-ignore
            totals[day] += float(r["total"])  # pyre-ignore
        except Exception:
            pass
    return {k: v for k, v in totals.items()}

def get_weekly_day_avg() -> dict:
    rows = db_all("SELECT date, total FROM bills")
    day_totals: dict[int, float] = defaultdict[int, float](float)
    day_counts: dict[int, int] = defaultdict[int, int](int)
    for r in rows:
        try:
            d = datetime.datetime.strptime(r["date"][:10], "%Y-%m-%d")  # pyre-ignore
            wd = d.weekday()
            day_totals[wd] += float(r["total"])  # pyre-ignore
            day_counts[wd] += 1  # pyre-ignore
        except Exception:
            pass
    return {wd: day_totals[wd] / day_counts[wd] for wd in day_totals if day_counts[wd] > 0}

def get_best_day_of_week() -> str:
    avgs = get_weekly_day_avg()
    if not avgs:
        return "Not enough data"
    best_wd = max(avgs, key=lambda k: avgs[k])
    overall_avg = sum(avgs.values()) / len(avgs)
    ratio = avgs[best_wd] / overall_avg if overall_avg > 0 else 1
    return f"{WEEKDAYS[best_wd]}s perform {ratio:.1f}x vs average"

def predict_tomorrow() -> str:
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    wd = tomorrow.weekday()
    avgs = get_weekly_day_avg()
    if not avgs or wd not in avgs:
        return "Not enough data to predict"
    overall_avg = sum(avgs.values()) / len(avgs)
    day_avg = avgs[wd]
    day_name = WEEKDAYS[wd]
    if day_avg >= overall_avg * 1.2:
        return f"^ {day_name} looks strong — historically {CURR_SYM()}{day_avg:,.0f} avg"
    elif day_avg <= overall_avg * 0.8:
        return f"v {day_name} likely slow — historically {CURR_SYM()}{day_avg:,.0f} avg"
    else:
        return f"~ {day_name} should be average — ~{CURR_SYM()}{day_avg:,.0f} expected"

def get_dead_stock(days: int = 10) -> list:
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    sold_ids = set(
        r["product_id"] for r in db_all(
            "SELECT DISTINCT bi.product_id FROM bill_items bi "
            "JOIN bills b ON bi.bill_id=b.id WHERE b.date >= ?", (cutoff,)
        ) if r["product_id"]
    )
    all_prods = db_all("SELECT id, name, quantity FROM products WHERE quantity > 0")
    return [p for p in all_prods if p["id"] not in sold_ids]

def get_weekly_revenue_change() -> float:
    today = datetime.date.today()
    this_mon = today - datetime.timedelta(days=today.weekday())
    last_mon = this_mon - datetime.timedelta(days=7)
    this_week = sum(
        float(r["total"]) for r in db_all("SELECT total FROM bills WHERE date >= ?", (this_mon.strftime("%Y-%m-%d"),))
    )
    last_week = sum(
        float(r["total"]) for r in db_all(
            "SELECT total FROM bills WHERE date >= ? AND date < ?",
            (last_mon.strftime("%Y-%m-%d"), this_mon.strftime("%Y-%m-%d"))
        )
    )
    if last_week == 0:
        return 0.0
    return ((this_week - last_week) / last_week) * 100

def auto_tag_customer(cust_id: int):
    c = db_one("SELECT * FROM customers WHERE id=?", (cust_id,))
    if not c:
        return
    visits = c.get("visit_count", 0) or 0
    spent  = c.get("total_spent", 0.0) or 0.0
    last_bill = db_one("SELECT date FROM bills WHERE customer_id=? ORDER BY id DESC LIMIT 1", (cust_id,))
    days_since = 999
    if last_bill:
        try:
            ld = datetime.datetime.strptime(str(last_bill["date"])[:10], "%Y-%m-%d").date()  # pyre-ignore
            days_since = (datetime.date.today() - ld).days
        except Exception:
            pass
    if days_since > 30:
        tag = "Inactive"
    elif spent >= 5000 or visits >= 10:
        tag = "VIP"
    elif visits >= 5:
        tag = "Frequent"
    else:
        tag = "Regular"
    db_run("UPDATE customers SET tag=? WHERE id=?", (tag, cust_id))

def validate_coupon(code: str, bill_total: float):
    if not code:
        return 0.0, ""
    code = code.strip().upper()
    c = db_one("SELECT * FROM coupons WHERE code=? AND active=1", (code,))
    if not c:
        return 0.0, "Coupon not found or inactive."
    today = datetime.date.today().strftime("%Y-%m-%d")
    if c["expiry"] and str(c["expiry"]) < today:
        return 0.0, f"Coupon expired on {c['expiry']}."
    if bill_total < c["min_bill"]:
        return 0.0, f"Minimum bill {CURR_SYM()}{c['min_bill']:.0f} required."
    if c["type"] == "percent":
        disc = _rnd(float(bill_total) * float(c["value"]) / 100.0, 2)
        return disc, f"{c['value']:.0f}% off  -{CURR_SYM()}{disc:.2f}"
    else:
        disc = float(min(float(c.get("value", 0)), float(bill_total)))
        return disc, f"Flat {CURR_SYM()}{disc:.2f} off"

def auto_suggest_coupon(bill_total: float) -> str:
    today = datetime.date.today().strftime("%Y-%m-%d")
    today_rev = sum(
        float(r["total"]) for r in db_all("SELECT total FROM bills WHERE date LIKE ?", (f"{today}%",))
    )
    avgs = get_weekly_day_avg()
    wd = datetime.date.today().weekday()
    day_avg = avgs.get(wd, 0)
    if day_avg > 0 and today_rev < day_avg * 0.5:
        coupons = db_all("SELECT code FROM coupons WHERE active=1 AND (expiry='' OR expiry>=?)", (today,))
        if coupons:
            return f"Slow day — try coupon: {coupons[0]['code']}"
    return ""

def get_month_target(year: int, month: int, staff_id: int = 0) -> float:
    period = f"{year:04d}-{month:02d}"
    row = db_one("SELECT target_amt FROM sales_targets WHERE period=? AND staff_id=?", (period, staff_id))
    return float(row["target_amt"]) if row else 0.0

def get_month_revenue(year: int, month: int) -> float:
    rows = db_all("SELECT total FROM bills WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))
    return sum(float(r["total"]) for r in rows)

def get_working_days_left(year: int, month: int) -> int:
    today = datetime.date.today()
    last  = calendar.monthrange(year, month)[1]
    holidays_set = {r["date"] for r in db_all("SELECT date FROM holidays")}
    count = 0
    for d in range(today.day + 1, last + 1):
        ds = f"{year:04d}-{month:02d}-{d:02d}"
        if ds not in holidays_set:
            count = count + 1  # pyre-ignore
    return count

def required_daily_sales(year: int, month: int) -> float:
    target    = get_month_target(year, month)
    current   = get_month_revenue(year, month)
    remaining = max(0.0, target - current)
    days_left = get_working_days_left(year, month)
    if days_left == 0:
        return remaining
    return remaining / days_left

def get_staff_sales(staff_id: int, year: int, month: int) -> float:
    rows = db_all("SELECT total FROM bills WHERE staff_id=? AND date LIKE ?",
                  (staff_id, f"{year:04d}-{month:02d}-%"))
    return sum(float(r["total"]) for r in rows)

def calc_overtime(staff_id: int, date_str: str) -> float:
    att = db_one("SELECT * FROM attendance WHERE staff_id=? AND date=?", (staff_id, date_str))
    if att is None:
        return 0.0
    clock_out = att.get("clock_out")
    if not att.get("clock_in") or not clock_out:
        return 0.0
    st = db_one("SELECT shift_end FROM staff WHERE id=?", (staff_id,))
    if st is None:
        return 0.0
    shift_end = st.get("shift_end")
    if not shift_end:
        return 0.0
    try:
        def _mins(t: str) -> int:
            parts = str(t).split(":")
            if len(parts) >= 2:
                return int(parts[0]) * 60 + int(parts[1])
            return 0
        out_mins   = _mins(str(clock_out))
        shift_mins = _mins(str(shift_end))
        return _rnd(float(max(0.0, (out_mins - shift_mins) / 60.0)), 2)
    except Exception:
        return 0.0

def get_month_expenses(year: int, month: int) -> float:
    rows = db_all("SELECT amount FROM expenses WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))
    return sum(float(r["amount"]) for r in rows)

def get_month_profit(year: int, month: int) -> float:
    return get_month_revenue(year, month) - get_month_expenses(year, month)

def get_reorder_suggestions() -> list:
    pending_ids = {r["product_id"] for r in
                   db_all("SELECT product_id FROM purchase_orders WHERE status='Pending'")
                   if r["product_id"]}
    low = db_all("SELECT * FROM products WHERE quantity < 5 AND quantity >= 0")
    return [p for p in low if p["id"] not in pending_ids]

EXPENSE_CATS = ["Rent", "Electricity", "Salaries", "Supplies", "Transport",
                "Marketing", "Maintenance", "Miscellaneous"]

def get_cash_balance(date_str: str) -> dict:
    reg = db_one("SELECT opening_cash FROM cash_register WHERE date=?", (date_str,))
    opening = float(reg["opening_cash"]) if reg else 0.0
    sales_cash = sum(
        float(r["total"]) for r in db_all(
            "SELECT total FROM bills WHERE date LIKE ? AND payment_mode='Cash'", (f"{date_str}%",))
    )
    exp_cash = sum(
        float(r["amount"]) for r in db_all("SELECT amount FROM expenses WHERE date=?", (date_str,))
    )
    refunds = sum(
        float(r["total"]) for r in db_all(
            "SELECT total FROM bills WHERE date LIKE ? AND total < 0", (f"{date_str}%",))
    )
    closing = opening + sales_cash + exp_cash + refunds
    return {"opening": opening, "sales_cash": sales_cash,
            "expenses": exp_cash, "refunds": abs(float(refunds)), "closing": closing}

def get_category_revenue(year: int, month: int) -> dict:
    rows = db_all(
        "SELECT p.category, SUM(bi.price * bi.qty) AS rev "
        "FROM bill_items bi LEFT JOIN products p ON bi.product_id = p.id "
        "JOIN bills b ON bi.bill_id = b.id "
        "WHERE b.date LIKE ? AND b.total >= 0 GROUP BY p.category",
        (f"{year:04d}-{month:02d}-%",)
    )
    return {r["category"] or "General": float(r["rev"]) for r in rows}

def get_cohort_data() -> list:
    all_rows = db_all("SELECT customer_id, date FROM bills WHERE customer_id IS NOT NULL ORDER BY date")
    first_visit_map: dict[int, str] = {}
    cohorts = defaultdict(lambda: defaultdict(set))
    for r in all_rows:
        cid = r["customer_id"]
        month = str(r["date"])[:7]  # pyre-ignore
        if cid not in first_visit_map:
            first_visit_map[cid] = month
        cohorts[first_visit_map[cid]][month].add(cid)
    result = []
    for cohort_month in sorted(cohorts.keys()):
        entry: dict = {"cohort": cohort_month, "months": {}}
        base = len(cohorts[cohort_month].get(cohort_month, set()))
        for m in sorted(cohorts[cohort_month].keys()):
            entry["months"][m] = len(cohorts[cohort_month][m])
        entry["base"] = base
        result.append(entry)
    return result

def get_price_elasticity_hints() -> list:
    hints = []
    products = db_all("SELECT id, name FROM products")
    for p in products:
        rows = db_all(
            "SELECT bi.price, bi.qty, b.date FROM bill_items bi "
            "JOIN bills b ON bi.bill_id=b.id "
            "WHERE bi.product_id=? AND b.total>=0 ORDER BY b.date", (p["id"],)
        )
        if len(rows) < 4:
            continue
        mid = len(rows) // 2
        early = list(rows)[:mid]; late = list(rows)[mid:]  # pyre-ignore
        avg_price_early = sum(float(r["price"]) for r in early) / len(early)
        avg_price_late  = sum(float(r["price"]) for r in late)  / len(late)
        avg_qty_early   = sum(int(r["qty"]) for r in early) / len(early)
        avg_qty_late    = sum(int(r["qty"]) for r in late)  / len(late)
        if avg_price_late > avg_price_early * 1.05 and avg_qty_late < avg_qty_early * 0.7:
            drop_pct = (1 - avg_qty_late / avg_qty_early) * 100
            price_rise = (avg_price_late / avg_price_early - 1) * 100
            hints.append({
                "name": p["name"], "price_rise": _rnd(float(price_rise), 1),
                "qty_drop": _rnd(float(drop_pct), 1),
                "old_price": _rnd(float(avg_price_early), 2), "new_price": _rnd(float(avg_price_late), 2),
            })
    return hints

def get_breakeven(year: int, month: int) -> dict:
    fixed = get_month_expenses(year, month)
    rev   = get_month_revenue(year, month)
    top = db_one(
        "SELECT bi.name, bi.price, SUM(bi.qty) AS total_qty, SUM(bi.price*bi.qty) AS total_rev "
        "FROM bill_items bi JOIN bills b ON bi.bill_id=b.id "
        "WHERE b.date LIKE ? AND b.total>=0 "
        "GROUP BY bi.name ORDER BY total_rev DESC LIMIT 1",
        (f"{year:04d}-{month:02d}-%",)
    )
    units_needed = None
    if top and float(top.get("price", 0) or 0) > 0:
        units_needed = int(fixed / float(top["price"])) + 1
    return {
        "fixed_costs": fixed, "revenue": rev,
        "shortfall": max(0.0, fixed - rev), "surplus": max(0.0, rev - fixed),
        "breakeven_reached": rev >= fixed,
        "top_product": top["name"] if top else None,
        "top_price": float(top["price"]) if top else 0,
        "units_needed": units_needed,
    }

# ═══════════════════════════════════════════════════════════════
#  THEMES — 4 switchable palettes
# ═══════════════════════════════════════════════════════════════
THEMES = {
    "Dark Violet": {
        "BG": "#1a1a28", "SIDEBAR_BG": "#111120", "CARD_BG": "#22223a",
        "ACCENT": "#5b54f0", "DANGER": "#e05050", "SUCCESS": "#38d47a",
        "WARNING": "#f0b429", "TEXT": "#dcdcf0", "MUTED": "#6868a0",
        "INPUT_BG": "#2c2c46", "BORDER": "#30305a",
        "CAL_HIGH": "#38d47a", "CAL_MED": "#f0b429",
        "CAL_LOW": "#e05050", "CAL_EMPTY": "#2c2c46",
    },
    "Midnight Blue": {
        "BG": "#0d1117", "SIDEBAR_BG": "#090d12", "CARD_BG": "#161b22",
        "ACCENT": "#58a6ff", "DANGER": "#f85149", "SUCCESS": "#3fb950",
        "WARNING": "#d29922", "TEXT": "#c9d1d9", "MUTED": "#484f58",
        "INPUT_BG": "#21262d", "BORDER": "#30363d",
        "CAL_HIGH": "#3fb950", "CAL_MED": "#d29922",
        "CAL_LOW": "#f85149", "CAL_EMPTY": "#21262d",
    },
    "Solarized Dark": {
        "BG": "#002b36", "SIDEBAR_BG": "#001e26", "CARD_BG": "#073642",
        "ACCENT": "#268bd2", "DANGER": "#dc322f", "SUCCESS": "#859900",
        "WARNING": "#b58900", "TEXT": "#839496", "MUTED": "#586e75",
        "INPUT_BG": "#073642", "BORDER": "#094656",
        "CAL_HIGH": "#859900", "CAL_MED": "#b58900",
        "CAL_LOW": "#dc322f", "CAL_EMPTY": "#073642",
    },
    "Light": {
        "BG": "#f0f2f5", "SIDEBAR_BG": "#e2e6ea", "CARD_BG": "#ffffff",
        "ACCENT": "#4361ee", "DANGER": "#e63946", "SUCCESS": "#2a9d5c",
        "WARNING": "#e07c00", "TEXT": "#1d2333", "MUTED": "#6b7280",
        "INPUT_BG": "#f8f9fa", "BORDER": "#d1d5db",
        "CAL_HIGH": "#2a9d5c", "CAL_MED": "#e07c00",
        "CAL_LOW": "#e63946", "CAL_EMPTY": "#e9ecef",
    },
}

# ── Currencies with flag emoji ──────────────────────────────────
CURRENCIES = {
    "INR — ₹  India":        {"symbol": "₹",  "code": "INR", "flag": "🇮🇳"},
    "USD — $  United States":{"symbol": "$",  "code": "USD", "flag": "🇺🇸"},
    "EUR — €  Euro Zone":    {"symbol": "€",  "code": "EUR", "flag": "🇪🇺"},
    "GBP — £  UK":           {"symbol": "£",  "code": "GBP", "flag": "🇬🇧"},
    "JPY — ¥  Japan":        {"symbol": "¥",  "code": "JPY", "flag": "🇯🇵"},
    "CNY — ¥  China":        {"symbol": "¥",  "code": "CNY", "flag": "🇨🇳"},
    "AED — د.إ  UAE":        {"symbol": "د.إ","code": "AED", "flag": "🇦🇪"},
    "SGD — S$  Singapore":   {"symbol": "S$", "code": "SGD", "flag": "🇸🇬"},
    "AUD — A$  Australia":   {"symbol": "A$", "code": "AUD", "flag": "🇦🇺"},
    "CAD — C$  Canada":      {"symbol": "C$", "code": "CAD", "flag": "🇨🇦"},
    "BRL — R$  Brazil":      {"symbol": "R$", "code": "BRL", "flag": "🇧🇷"},
    "ZAR — R   South Africa":{"symbol": "R",  "code": "ZAR", "flag": "🇿🇦"},
    "NGN — ₦  Nigeria":      {"symbol": "₦",  "code": "NGN", "flag": "🇳🇬"},
    "KES — Ksh Kenya":       {"symbol": "Ksh","code": "KES", "flag": "🇰🇪"},
    "PKR — ₨  Pakistan":     {"symbol": "₨",  "code": "PKR", "flag": "🇵🇰"},
    "BDT — ৳  Bangladesh":   {"symbol": "৳",  "code": "BDT", "flag": "🇧🇩"},
}

# ── App-level mutable settings (loaded/saved to a tiny JSON) ───
import json as _json

_SETTINGS_FILE = os.path.join(BASE_DIR, "billflow_settings.json")

def _load_settings() -> dict:
    defaults = {"theme": "Dark Violet", "currency": "INR — ₹  India",
                "shop_name": "My Shop", "shop_phone": "", "shop_address": ""}
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = _json.load(f)
            defaults.update(saved)
    except Exception:
        pass
    return defaults

def _save_settings(d: dict):
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump(d, f, indent=2)
    except Exception:
        pass

APP_SETTINGS = _load_settings()

BG: str = ""
SIDEBAR_BG: str = ""
CARD_BG: str = ""
ACCENT: str = ""
DANGER: str = ""
SUCCESS: str = ""
WARNING: str = ""
TEXT: str = ""
MUTED: str = ""
INPUT_BG: str = ""
BORDER: str = ""
CAL_HIGH: str = ""
CAL_MED: str = ""
CAL_LOW: str = ""
CAL_EMPTY: str = ""

# ── Apply the active theme into module-level colour globals ─────
def _apply_theme(theme_name: str):
    global BG, SIDEBAR_BG, CARD_BG, ACCENT, DANGER, SUCCESS, WARNING
    global TEXT, MUTED, INPUT_BG, BORDER
    global CAL_HIGH, CAL_MED, CAL_LOW, CAL_EMPTY
    t = THEMES.get(theme_name, THEMES["Dark Violet"])
    BG         = t["BG"];         SIDEBAR_BG = t["SIDEBAR_BG"]
    CARD_BG    = t["CARD_BG"];    ACCENT     = t["ACCENT"]
    DANGER     = t["DANGER"];     SUCCESS    = t["SUCCESS"]
    WARNING    = t["WARNING"];    TEXT       = t["TEXT"]
    MUTED      = t["MUTED"];      INPUT_BG   = t["INPUT_BG"]
    BORDER     = t["BORDER"]
    CAL_HIGH   = t["CAL_HIGH"];   CAL_MED    = t["CAL_MED"]
    CAL_LOW    = t["CAL_LOW"];    CAL_EMPTY  = t["CAL_EMPTY"]

_apply_theme(APP_SETTINGS["theme"])

def CURR_SYM() -> str:
    """Return the active currency symbol, e.g. '₹' or '$'."""
    return CURRENCIES.get(APP_SETTINGS["currency"], {"symbol": "Rs."})["symbol"]

F_TITLE  = ("Segoe UI", 16, "bold")
F_HEAD   = ("Segoe UI", 11, "bold")
F_BODY   = ("Segoe UI", 10)
F_SMALL  = ("Segoe UI",  9)
F_MONO   = ("Consolas", 10)

def _shade(hex_color, delta):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)  # pyre-ignore
    r, g, b = (max(0, min(255, v+delta)) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"

def make_card(parent, **kw):  # pyre-ignore
    kw.setdefault("bg", CARD_BG)
    kw.setdefault("highlightbackground", BORDER)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("relief", "flat")
    return tk.Frame(parent, **kw)  # pyre-ignore

LABEL_STYLES = {
    "title":   {"fg": TEXT,    "font": F_TITLE},
    "heading": {"fg": TEXT,    "font": F_HEAD},
    "body":    {"fg": TEXT,    "font": F_BODY},
    "muted":   {"fg": MUTED,   "font": F_SMALL},
    "accent":  {"fg": ACCENT,  "font": F_BODY},
    "success": {"fg": SUCCESS, "font": F_BODY},
    "warn":    {"fg": WARNING, "font": F_BODY},
    "danger":  {"fg": DANGER,  "font": F_BODY},
    "mono":    {"fg": TEXT,    "font": F_MONO},
}

def make_label(parent, text, style="body", bg=None, **kw):  # pyre-ignore
    cfg = dict(LABEL_STYLES[style])
    cfg["bg"] = bg or CARD_BG
    cfg.update(kw)
    return tk.Label(parent, text=text, **cfg)  # pyre-ignore

def make_entry(parent, width=20, **kw):  # pyre-ignore
    kw.setdefault("bg", INPUT_BG)
    kw.setdefault("fg", TEXT)
    kw.setdefault("insertbackground", ACCENT)
    kw.setdefault("relief", "flat")
    kw.setdefault("font", F_BODY)
    kw.setdefault("bd", 5)
    return tk.Entry(parent, width=width, **kw)  # pyre-ignore

def make_button(parent, text, command, color=ACCENT, **kw):  # pyre-ignore
    btn = tk.Button(
        parent, text=text, command=command,
        bg=color, fg="white", font=F_BODY,
        relief="flat", bd=0, padx=10, pady=5,
        activebackground=color, activeforeground="white",
        cursor="hand2", **kw  # pyre-ignore
    )
    def _enter(e): btn.config(bg=_shade(color, -20))
    def _leave(e): btn.config(bg=color)
    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)
    return btn

_ttk_style_done = False
def _init_ttk_style():
    global _ttk_style_done
    if _ttk_style_done:
        return
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("App.TCombobox",
        fieldbackground=INPUT_BG, background=INPUT_BG,
        foreground=TEXT, selectbackground=ACCENT,
        selectforeground="white", bordercolor=BORDER, arrowcolor=ACCENT)
    s.map("App.TCombobox",
        fieldbackground=[("readonly", INPUT_BG)],
        foreground=[("readonly", TEXT)])
    s.configure("Vertical.TScrollbar",
        troughcolor=SIDEBAR_BG, background=BORDER,
        arrowcolor=MUTED, bordercolor=SIDEBAR_BG)
    s.map("Vertical.TScrollbar", background=[("active", ACCENT)])
    _ttk_style_done = True

def make_combo(parent, values=(), width=20, **kw):  # pyre-ignore
    _init_ttk_style()
    return ttk.Combobox(parent, values=list(values), width=width,
                        state="readonly", style="App.TCombobox", **kw)  # pyre-ignore

def make_listbox(container, **kw):  # pyre-ignore
    kw.setdefault("bg", INPUT_BG)
    kw.setdefault("fg", TEXT)
    kw.setdefault("selectbackground", ACCENT)
    kw.setdefault("selectforeground", "white")
    kw.setdefault("font", F_MONO)
    kw.setdefault("relief", "flat")
    kw.setdefault("bd", 0)
    kw.setdefault("activestyle", "none")
    kw.setdefault("highlightbackground", BORDER)
    kw.setdefault("highlightthickness", 1)
    lb = tk.Listbox(container, **kw)  # pyre-ignore
    sb = ttk.Scrollbar(container, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=sb.set)
    return lb, sb

def sep(parent, bg=BORDER, pady=6):
    tk.Frame(parent, bg=bg, height=1).pack(fill="x", pady=pady)

def field_group(parent, label_text, bg=None):
    make_label(parent, label_text, style="muted", bg=bg or CARD_BG).pack(anchor="w", pady=(5,1))
    e = make_entry(parent, width=24)
    e.pack(anchor="w")
    return e

def stat_tile(parent, title, var, color=ACCENT):
    c = make_card(parent, padx=14, pady=10)
    c.pack(side="left", fill="both", expand=True, padx=5)
    make_label(c, title, style="muted").pack(anchor="w")
    tk.Label(c, textvariable=var, bg=CARD_BG, fg=color,
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    return c

# ═══════════════════════════════════════════════════════════════
#  ROOT WINDOW
# ═══════════════════════════════════════════════════════════════
root = tk.Tk()
root.title(f"BillFlow v6.0 — {APP_SETTINGS.get('shop_name','My Shop')}")
root.geometry("1280x760")
root.minsize(980, 640)
root.configure(bg=BG)
_init_ttk_style()

# ── Sidebar with scrollbar ────────────────────────────────────
sidebar_outer = tk.Frame(root, bg=SIDEBAR_BG, width=200)
sidebar_outer.pack(side="left", fill="y")
sidebar_outer.pack_propagate(False)

_sb_canvas = tk.Canvas(sidebar_outer, bg=SIDEBAR_BG, highlightthickness=0, width=200)
_sb_scrollbar = ttk.Scrollbar(sidebar_outer, orient="vertical", command=_sb_canvas.yview)
sidebar = tk.Frame(_sb_canvas, bg=SIDEBAR_BG)

sidebar.bind("<Configure>",
    lambda e: _sb_canvas.configure(scrollregion=_sb_canvas.bbox("all")))

_sb_canvas_window = _sb_canvas.create_window((0, 0), window=sidebar, anchor="nw")
_sb_canvas.configure(yscrollcommand=_sb_scrollbar.set)

def _on_sidebar_configure(e):
    _sb_canvas.itemconfig(_sb_canvas_window, width=_sb_canvas.winfo_width())
_sb_canvas.bind("<Configure>", _on_sidebar_configure)

_sb_canvas.pack(side="left", fill="both", expand=True)
_sb_scrollbar.pack(side="right", fill="y")

# Scroll only when mouse is over the sidebar (not global bind_all)
def _sb_scroll(event):
    _sb_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

def _sb_bind(event):
    _sb_canvas.bind_all("<MouseWheel>", _sb_scroll)
    # Linux scroll buttons
    _sb_canvas.bind_all("<Button-4>", lambda e: _sb_canvas.yview_scroll(-1, "units"))
    _sb_canvas.bind_all("<Button-5>", lambda e: _sb_canvas.yview_scroll(1, "units"))

def _sb_unbind(event):
    _sb_canvas.unbind_all("<MouseWheel>")
    _sb_canvas.unbind_all("<Button-4>")
    _sb_canvas.unbind_all("<Button-5>")

sidebar_outer.bind("<Enter>", _sb_bind)
sidebar_outer.bind("<Leave>", _sb_unbind)

workspace = tk.Frame(root, bg=BG)
workspace.pack(side="right", fill="both", expand=True)

frames: dict = {}
nav_buttons: list = []

# ─────────────────────────── Navigation ──────────────────────
def navigate(page_name: str):
    for f in frames.values():
        f.pack_forget()
    frames[page_name].pack(fill="both", expand=True, padx=16, pady=16)
    for btn, name in nav_buttons:
        btn.config(
            bg="#1e1e36" if name == page_name else SIDEBAR_BG,
            fg=TEXT if name == page_name else MUTED
        )
    refresh_all()

@overload
def nav_btn(label: str, page: None = None, section: Literal[True] = True): ...

@overload
def nav_btn(label: str, page: str, section: Literal[False] = False): ...

def nav_btn(label: str, page: Optional[str] = None, section: bool = False):
    if section:
        # Section divider label
        tk.Label(sidebar, text=label.upper(), bg=SIDEBAR_BG, fg=MUTED,
                 font=("Segoe UI", 7, "bold"), anchor="w", padx=14, pady=4).pack(fill="x", pady=(8,2))
        return None
    page = cast(str, page)
    btn = tk.Button(
        sidebar, text=f"  {label}",
        bg=SIDEBAR_BG, fg=MUTED, font=("Segoe UI", 9),
        relief="flat", bd=0, anchor="w", padx=8, pady=7,
        activebackground="#1e1e36", activeforeground=TEXT,
        cursor="hand2", command=lambda: navigate(page)  # pyre-ignore
    )
    btn.pack(fill="x", padx=4, pady=1)
    nav_buttons.append((btn, page))
    return btn

# ── Sidebar header ──
lf = tk.Frame(sidebar, bg=SIDEBAR_BG)
lf.pack(fill="x", pady=(18,10), padx=12)
tk.Label(lf, text="BillFlow", bg=SIDEBAR_BG, fg=ACCENT,
         font=("Segoe UI", 13, "bold")).pack(anchor="w")
tk.Label(lf, text="Sales Manager v6.0", bg=SIDEBAR_BG, fg=MUTED,
         font=F_SMALL).pack(anchor="w")
tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10, pady=2)

# ── Nav items (text only, no emojis) ──
nav_btn("Dashboard",    "dashboard")
nav_btn("New Bill",     "bill")
nav_btn("Products",     "products")
nav_btn("Customers",    "customers")
nav_btn("Coupons",      "coupons")

nav_btn("ANALYTICS", section=True)
nav_btn("Calendar",     "calendar")
nav_btn("Insights",     "insights")
nav_btn("Reports",      "reports")
nav_btn("GST Report",   "gst")
nav_btn("Break-Even",   "breakeven")
nav_btn("Analytics+",   "analytics_plus")

nav_btn("OPERATIONS", section=True)
nav_btn("End of Day",   "eod")
nav_btn("Cash Register","cash_register")
nav_btn("Stock Orders", "purchase_orders")
nav_btn("Refunds",      "refunds")

nav_btn("PEOPLE", section=True)
nav_btn("Staff",        "staff")
nav_btn("Roster",       "roster")
nav_btn("Salary Slips", "salary")
nav_btn("Targets",      "targets")
nav_btn("Holidays",     "holidays")
nav_btn("Expenses",     "expenses")

nav_btn("SYSTEM", section=True)
nav_btn("Settings",     "settings")

tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10, pady=6)
tk.Label(sidebar, text="v6.0  SQLite", bg=SIDEBAR_BG, fg=MUTED, font=F_SMALL).pack(pady=(0,12))

# ═══════════════════════════════════════════════════════════════
#  EDIT DIALOGS
# ═══════════════════════════════════════════════════════════════
def _center(win, w, h):
    root.update_idletasks()
    x = root.winfo_x() + (root.winfo_width()  - w) // 2
    y = root.winfo_y() + (root.winfo_height() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

def edit_product_dialog(prod_id: int, on_save):
    p = db_one("SELECT * FROM products WHERE id=?", (prod_id,))
    if not p: return
    win = tk.Toplevel(root)
    win.title(f"Edit Product #{prod_id}")
    win.configure(bg=CARD_BG)
    win.resizable(False, False)
    win.grab_set()
    _center(win, 340, 340)
    pad: dict[str, Any] = {"padx": 20, "pady": 5}
    make_label(win, f"Edit Product  #{prod_id}", style="heading", bg=CARD_BG).pack(anchor="w", padx=20, pady=(14,4))
    sep(win)
    fields = [("Product Name *", p["name"]), ("Price", str(p["price"])),
              ("Stock Qty", str(p["quantity"])), ("Category", p["category"]),
              ("HSN Code", p.get("hsn_code","")), ("GST Rate (%)", str(p.get("gst_rate",18)))]
    entries = []
    for lbl, val in fields:
        make_label(win, lbl, style="muted", bg=CARD_BG).pack(anchor="w", **pad)
        e = make_entry(win, width=30); e.insert(0, str(val)); e.pack(anchor="w", padx=20)
        entries.append(e)
    err_lbl = make_label(win, "", style="danger", bg=CARD_BG); err_lbl.pack(anchor="w", padx=20)

    def do_save():
        name = entries[0].get().strip()
        if not name: err_lbl.config(text="Name required."); return
        try:
            price = float(entries[1].get()); qty = int(entries[2].get())
            gst_r = float(entries[5].get())
        except ValueError:
            err_lbl.config(text="Price/Qty/GST must be numbers."); return
        if price < 0 or qty < 0: err_lbl.config(text="Must be non-negative."); return
        db_run("UPDATE products SET name=?,price=?,quantity=?,category=?,hsn_code=?,gst_rate=? WHERE id=?",
               (name, price, qty, entries[3].get().strip() or "General",
                entries[4].get().strip(), gst_r, prod_id))
        on_save(); win.destroy()

    bf = tk.Frame(win, bg=CARD_BG); bf.pack(fill="x", padx=20, pady=(8,14))
    make_button(bf, "Save",   do_save,     color=SUCCESS).pack(side="left", padx=(0,6))
    make_button(bf, "Cancel", win.destroy, color=DANGER).pack(side="left")


def edit_customer_dialog(cust_id: int, on_save):
    c = db_one("SELECT * FROM customers WHERE id=?", (cust_id,))
    if not c: return
    win = tk.Toplevel(root)
    win.title(f"Edit Customer #{cust_id}")
    win.configure(bg=CARD_BG)
    win.resizable(False, False)
    win.grab_set()
    _center(win, 360, 480)
    pad: dict[str, Any] = {"padx": 20, "pady": 4}
    make_label(win, f"Edit Customer  #{cust_id}", style="heading", bg=CARD_BG).pack(anchor="w", padx=20, pady=(14,4))
    sep(win)
    for lbl in ["Full Name *", "Phone (10 digits)", "Email", "Age"]:
        make_label(win, lbl, style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    # Build entries after labels to keep packing order sane
    win_entries = []
    for i, (lbl, val) in enumerate([("Full Name *", c["name"] or ""), ("Phone", c["phone"] or ""),
                                     ("Email", c["email"] or ""), ("Age", str(c["age"]) if c.get("age") else "")]):
        pass
    # Simpler: just build them directly
    for w in win.winfo_children()[3:]: w.destroy()  # pyre-ignore

    make_label(win, "Full Name *", style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    e_name = make_entry(win, width=30); e_name.insert(0, str(c["name"] or "")); e_name.pack(anchor="w", padx=20)
    make_label(win, "Phone", style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    e_phone = make_entry(win, width=30); e_phone.insert(0, str(c["phone"] or "")); e_phone.pack(anchor="w", padx=20)
    make_label(win, "Email", style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    e_email = make_entry(win, width=30); e_email.insert(0, str(c["email"] or "")); e_email.pack(anchor="w", padx=20)
    make_label(win, "Age", style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    e_age = make_entry(win, width=30)
    if c["age"]: e_age.insert(0, str(c["age"]))
    e_age.pack(anchor="w", padx=20)
    make_label(win, "Gender", style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    cb_gender = make_combo(win, ["Male","Female","Other","Prefer not to say"], width=28)
    cb_gender.pack(anchor="w", padx=20)
    if c["gender"]: cb_gender.set(c["gender"])
    make_label(win, "Tag", style="muted", bg=CARD_BG).pack(anchor="w", **pad)
    cb_tag = make_combo(win, ["Regular","Frequent","VIP","Inactive","First-time"], width=28)
    cb_tag.set(c.get("tag") or "Regular"); cb_tag.pack(anchor="w", padx=20)
    err_lbl = make_label(win, "", style="danger", bg=CARD_BG); err_lbl.pack(anchor="w", padx=20, pady=4)

    def do_save():
        name = e_name.get().strip()
        if not name: err_lbl.config(text="Name required."); return
        phone = e_phone.get().strip()
        if phone:
            perr = validate_phone(phone)
            if perr: err_lbl.config(text=perr); return
        email = e_email.get().strip()
        if email:
            eerr = validate_email(email)
            if eerr: err_lbl.config(text=eerr); return
        age_raw = e_age.get().strip()
        try: age_val = int(age_raw) if age_raw else None
        except ValueError: err_lbl.config(text="Age must be a number."); return
        db_run("UPDATE customers SET name=?,phone=?,email=?,age=?,gender=?,tag=? WHERE id=?",
               (name, phone or None, email or None, age_val, cb_gender.get() or None,
                cb_tag.get() or "Regular", cust_id))
        on_save(); win.destroy()

    bf = tk.Frame(win, bg=CARD_BG); bf.pack(fill="x", padx=20, pady=(8,14))
    make_button(bf, "Save",   do_save,     color=SUCCESS).pack(side="left", padx=(0,6))
    make_button(bf, "Cancel", win.destroy, color=DANGER).pack(side="left")

# ═══════════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════════
def build_dashboard():
    frame = tk.Frame(workspace, bg=BG)
    frames["dashboard"] = frame
    hdr = tk.Frame(frame, bg=BG); hdr.pack(fill="x", pady=(0,10))
    make_label(hdr, "Dashboard", style="title", bg=BG).pack(side="left")
    date_var = tk.StringVar(value=datetime.datetime.now().strftime("%A, %d %B %Y"))
    tk.Label(hdr, textvariable=date_var, bg=BG, fg=MUTED, font=F_SMALL).pack(side="right", padx=4)

    tiles_row = tk.Frame(frame, bg=BG); tiles_row.pack(fill="x", pady=(0,10))
    v_prods = tk.StringVar(value="0"); v_custs = tk.StringVar(value="0")
    v_bills = tk.StringVar(value="0"); v_rev   = tk.StringVar(value=f"{CURR_SYM()}0")
    stat_tile(tiles_row, "Products",  v_prods, ACCENT)
    stat_tile(tiles_row, "Customers", v_custs, SUCCESS)
    stat_tile(tiles_row, "Bills",     v_bills, WARNING)
    stat_tile(tiles_row, "Revenue",   v_rev,   DANGER)

    chart_card = make_card(frame, padx=14, pady=12)
    chart_card.pack(fill="both", expand=True)
    make_label(chart_card, "Bills per Customer (Top 10)", style="heading").pack(anchor="w", pady=(0,6))
    fig  = Figure(figsize=(7, 3.0), dpi=96, facecolor=CARD_BG)
    ax   = cast(Any, fig.add_subplot(111)); ax.set_facecolor(CARD_BG)
    fig.subplots_adjust(bottom=0.22, left=0.04, right=0.98, top=0.88)
    canv = FigureCanvasTkAgg(fig, master=chart_card)
    canv.get_tk_widget().configure(bg=CARD_BG, highlightthickness=0)
    canv.get_tk_widget().pack(fill="both", expand=True)
    return frame, v_prods, v_custs, v_bills, v_rev, ax, canv, date_var

_dash, _v_prods, _v_custs, _v_bills, _v_rev, _ax, _canv, _date_var = build_dashboard()

# ═══════════════════════════════════════════════════════════════
#  PRODUCTS
# ═══════════════════════════════════════════════════════════════
def build_products():
    frame = tk.Frame(workspace, bg=BG)
    frames["products"] = frame
    make_label(frame, "Products", style="title", bg=BG).pack(anchor="w", pady=(0,10))
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)

    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Add Product", style="heading").pack(anchor="w", pady=(0,8))
    e_name  = field_group(fc, "Product Name *")
    e_price = field_group(fc, f"Price ({CURR_SYM()})")
    e_qty   = field_group(fc, "Stock Qty"); e_qty.insert(0, "1")
    e_cat   = field_group(fc, "Category")
    e_hsn   = field_group(fc, "HSN Code")
    make_label(fc, "GST Rate (%)", style="muted").pack(anchor="w", pady=(5,1))
    cb_gst  = make_combo(fc, ["0","5","12","18","28"], width=22)
    cb_gst.set("18"); cb_gst.pack(anchor="w")
    err_lbl = make_label(fc, "", style="danger"); err_lbl.pack(anchor="w", pady=(4,0))
    sep(fc)

    def do_add():
        name = e_name.get().strip()
        if not name: err_lbl.config(text="Product name required."); return
        try: price = float(e_price.get()); qty = int(e_qty.get()); gst_r = float(cb_gst.get())
        except ValueError: err_lbl.config(text="Price=number, Qty=integer."); return
        if price < 0 or qty < 0: err_lbl.config(text="Must be non-negative."); return
        err_lbl.config(text="")
        db_run("INSERT INTO products (name,price,quantity,category,hsn_code,gst_rate) VALUES (?,?,?,?,?,?)",
               (name, price, qty, e_cat.get().strip() or "General", e_hsn.get().strip(), gst_r))
        for e in (e_name, e_price, e_cat, e_hsn): e.delete(0, "end")
        e_qty.delete(0, "end"); e_qty.insert(0, "1")
        refresh_all()

    def do_del():
        sel = lb.curselection()
        if not sel: messagebox.showwarning("Select", "Select a product first"); return
        pid = _lb_ids[sel[0]]
        p = db_one("SELECT name FROM products WHERE id=?", (pid,))
        if p and messagebox.askyesno("Delete", f'Delete "{p["name"]}"?'):
            db_run("DELETE FROM products WHERE id=?", (pid,)); refresh_all()

    def do_edit():
        sel = lb.curselection()
        if not sel: messagebox.showwarning("Select", "Select a product to edit"); return
        edit_product_dialog(_lb_ids[sel[0]], refresh_all)

    def do_fav():
        sel = lb.curselection()
        if not sel: return
        pid = _lb_ids[sel[0]]
        if db_one("SELECT id FROM favorites WHERE product_id=?", (pid,)):
            db_run("DELETE FROM favorites WHERE product_id=?", (pid,))
        else:
            db_run("INSERT INTO favorites (product_id, added_on) VALUES (?,?)",
                   (pid, datetime.datetime.now().strftime("%Y-%m-%d")))
        refresh_all()

    make_button(fc, "Add Product",       do_add).pack(fill="x", pady=2)
    make_button(fc, "Edit Selected",     do_edit,  color=WARNING).pack(fill="x", pady=2)
    make_button(fc, "Toggle Favourite",  do_fav,   color="#7b5ea7").pack(fill="x", pady=2)
    make_button(fc, "Delete Selected",   do_del,   color=DANGER).pack(fill="x", pady=2)

    lc = make_card(cols, padx=14, pady=14); lc.pack(side="right", fill="both", expand=True)
    sf = tk.Frame(lc, bg=CARD_BG); sf.pack(fill="x", pady=(0,6))
    make_label(sf, "Search:", style="muted").pack(side="left", padx=(0,6))
    sv = tk.StringVar(); se = make_entry(sf)
    se.configure(textvariable=sv); se.pack(side="left", fill="x", expand=True)
    make_label(lc, "Inventory", style="heading").pack(anchor="w", pady=(0,4))
    lbf = tk.Frame(lc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf)
    lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    _lb_ids: list = []

    def refresh_lb(*_):
        q = sv.get().lower(); lb.delete(0, "end"); _lb_ids.clear()
        fav_ids = {r["product_id"] for r in db_all("SELECT product_id FROM favorites")}
        for p in db_all("SELECT * FROM products ORDER BY name"):
            if q and q not in p["name"].lower() and q not in p.get("category","").lower(): continue
            flag = " [LOW]" if p.get("quantity", 0) < 5 else ""
            star = "*" if p["id"] in fav_ids else " "
            lb.insert("end",
                f' {star} #{str(p["id"]):<4} {p["name"]:<22}| {CURR_SYM()}{p["price"]:<9.2f}| Qty:{p["quantity"]:<5}| {p.get("category","General")}{flag}')
            _lb_ids.append(p["id"])

    sv.trace("w", refresh_lb)
    lb.bind("<Double-Button-1>", lambda e: do_edit())
    return frame, refresh_lb

_prod_frame, _refresh_prod_lb = build_products()

# ═══════════════════════════════════════════════════════════════
#  CUSTOMERS
# ═══════════════════════════════════════════════════════════════
def build_customers():
    frame = tk.Frame(workspace, bg=BG)
    frames["customers"] = frame
    make_label(frame, "Customers", style="title", bg=BG).pack(anchor="w", pady=(0,10))
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)

    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Add Customer", style="heading").pack(anchor="w", pady=(0,8))
    e_name  = field_group(fc, "Full Name *")
    e_phone = field_group(fc, "Phone (10 digits)")
    e_email = field_group(fc, "Email")
    e_age   = field_group(fc, "Age")
    make_label(fc, "Gender", style="muted").pack(anchor="w", pady=(5,1))
    cb_gender = make_combo(fc, ["Male","Female","Other","Prefer not to say"], width=22); cb_gender.pack(anchor="w")
    make_label(fc, "Tag", style="muted").pack(anchor="w", pady=(5,1))
    cb_tag = make_combo(fc, ["Regular","Frequent","VIP","Inactive","First-time"], width=22)
    cb_tag.set("Regular"); cb_tag.pack(anchor="w")
    err_lbl = make_label(fc, "", style="danger"); err_lbl.pack(anchor="w", pady=(5,0))
    sep(fc)

    def do_add():
        name = e_name.get().strip()
        if not name: err_lbl.config(text="Name required."); return
        phone = e_phone.get().strip()
        if phone:
            perr = validate_phone(phone)
            if perr: err_lbl.config(text=perr); return
        email = e_email.get().strip()
        if email:
            eerr = validate_email(email)
            if eerr: err_lbl.config(text=eerr); return
        age_raw = e_age.get().strip()
        try: age_val = int(age_raw) if age_raw else None
        except ValueError: err_lbl.config(text="Age must be a number."); return
        err_lbl.config(text="")
        db_run("INSERT INTO customers (name,phone,email,age,gender,tag) VALUES (?,?,?,?,?,?)",
               (name, phone or None, email or None, age_val, cb_gender.get() or None, cb_tag.get() or "Regular"))
        for e in (e_name, e_phone, e_email, e_age): e.delete(0, "end")
        cb_gender.set(""); cb_tag.set("Regular"); refresh_all()

    def do_del():
        sel = lb.curselection()
        if not sel: return
        cid = _lb_ids[sel[0]]
        c = db_one("SELECT name FROM customers WHERE id=?", (cid,))
        if c and messagebox.askyesno("Delete", f'Delete "{c["name"]}"?'):
            db_run("DELETE FROM customers WHERE id=?", (cid,)); refresh_all()

    def do_edit():
        sel = lb.curselection()
        if not sel: return
        edit_customer_dialog(_lb_ids[sel[0]], refresh_all)

    def do_history():
        sel = lb.curselection()
        if not sel: return
        cid = _lb_ids[sel[0]]
        c = db_one("SELECT * FROM customers WHERE id=?", (cid,))
        if not c: return
        bills = db_all("SELECT * FROM bills WHERE customer_id=? ORDER BY id DESC", (cid,))
        win = tk.Toplevel(root); win.title(f"History — {c['name']}")
        win.geometry("520x380"); win.configure(bg=CARD_BG); _center(win, 520, 380)
        make_label(win, f"{c['name']}", style="heading", bg=CARD_BG).pack(anchor="w", padx=14, pady=(12,2))
        tk.Label(win, text=f"Tag: {c.get('tag','Regular')}  |  Visits: {c.get('visit_count',0)}  |  Spent: {CURR_SYM()}{c.get('total_spent',0):.2f}",
                 bg=CARD_BG, fg=MUTED, font=F_SMALL).pack(anchor="w", padx=14)
        sep(win)
        lbf2 = tk.Frame(win, bg=CARD_BG); lbf2.pack(fill="both", expand=True, padx=10, pady=4)
        lb2, sb2 = make_listbox(lbf2)
        lb2.pack(side="left", fill="both", expand=True); sb2.pack(side="right", fill="y")
        for b in bills:
            lb2.insert("end", f'  #{b["id"]}  {b["date"][:16]}  {CURR_SYM()}{b["total"]:.2f}')  # pyre-ignore
        make_button(win, "Close", win.destroy, color=DANGER).pack(pady=(4,10))

    make_button(fc, "Add Customer",   do_add).pack(fill="x", pady=2)
    make_button(fc, "Edit Selected",  do_edit,    color=WARNING).pack(fill="x", pady=2)
    make_button(fc, "View History",   do_history, color=ACCENT).pack(fill="x", pady=2)
    make_button(fc, "Delete Selected",do_del,     color=DANGER).pack(fill="x", pady=2)

    lc = make_card(cols, padx=14, pady=14); lc.pack(side="right", fill="both", expand=True)
    sf = tk.Frame(lc, bg=CARD_BG); sf.pack(fill="x", pady=(0,6))
    make_label(sf, "Search:", style="muted").pack(side="left", padx=(0,6))
    sv = tk.StringVar(); se = make_entry(sf); se.configure(textvariable=sv); se.pack(side="left", fill="x", expand=True)
    make_label(lc, "Directory", style="heading").pack(anchor="w", pady=(0,4))
    lbf = tk.Frame(lc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    _lb_ids: list = []

    def refresh_lb(*_):
        q = sv.get().lower(); lb.delete(0, "end"); _lb_ids.clear()
        TAG_ICONS = {"VIP": "[VIP]", "Frequent": "[FRQ]", "Inactive": "[INK]", "First-time": "[NEW]"}
        for c in db_all("SELECT * FROM customers ORDER BY name"):
            if q and q not in c["name"].lower() and q not in (c.get("phone") or "").lower(): continue
            age_str = f"Age:{c['age']}" if c.get("age") else "      "
            icon = TAG_ICONS.get(c.get("tag",""), "     ")
            lb.insert("end", f' {icon} #{str(c["id"]):<3} {c["name"]:<22}| {(c.get("phone") or ""):<13}| {age_str} | {CURR_SYM()}{c.get("total_spent",0):.0f}')
            _lb_ids.append(c["id"])

    sv.trace("w", refresh_lb)
    lb.bind("<Double-Button-1>", lambda e: do_edit())
    return frame, refresh_lb

_cust_frame, _refresh_cust_lb = build_customers()

# ═══════════════════════════════════════════════════════════════
#  COUPONS
# ═══════════════════════════════════════════════════════════════
def build_coupons():
    frame = tk.Frame(workspace, bg=BG)
    frames["coupons"] = frame
    make_label(frame, "Coupons", style="title", bg=BG).pack(anchor="w", pady=(0,10))
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)

    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Create Coupon", style="heading").pack(anchor="w", pady=(0,8))
    e_code  = field_group(fc, "Code (e.g. SAVE10)")
    make_label(fc, "Type", style="muted").pack(anchor="w", pady=(5,1))
    cb_type = make_combo(fc, ["percent","fixed"], width=22); cb_type.set("percent"); cb_type.pack(anchor="w")
    e_val    = field_group(fc, f"Value (% or {CURR_SYM()})")
    e_minbil = field_group(fc, f"Min Bill ({CURR_SYM()})"); e_minbil.insert(0,"0")
    e_expiry = field_group(fc, "Expiry (YYYY-MM-DD)")
    e_desc   = field_group(fc, "Description")
    err_lbl  = make_label(fc, "", style="danger"); err_lbl.pack(anchor="w", pady=(4,0))
    sep(fc)

    def do_add():
        code = e_code.get().strip().upper()
        if not code: err_lbl.config(text="Code required."); return
        try: val = float(e_val.get()); minb = float(e_minbil.get())
        except ValueError: err_lbl.config(text="Value and min bill must be numbers."); return
        expiry = e_expiry.get().strip()
        if expiry:
            try: datetime.datetime.strptime(expiry, "%Y-%m-%d")
            except ValueError: err_lbl.config(text="Expiry: YYYY-MM-DD"); return
        if db_one("SELECT id FROM coupons WHERE code=?", (code,)):
            err_lbl.config(text="Code already exists."); return
        db_run("INSERT INTO coupons (code,type,value,min_bill,expiry,description) VALUES (?,?,?,?,?,?)",
               (code, cb_type.get(), val, minb, expiry, e_desc.get().strip()))
        for e in (e_code, e_val, e_minbil, e_expiry, e_desc): e.delete(0,"end")
        e_minbil.insert(0,"0"); err_lbl.config(text=""); refresh_all()

    def do_toggle():
        sel = lb.curselection()
        if not sel: return
        cid = _lb_ids[sel[0]]
        c = db_one("SELECT active FROM coupons WHERE id=?", (cid,))
        if c: db_run("UPDATE coupons SET active=? WHERE id=?", (0 if c["active"] else 1, cid)); refresh_all()

    def do_del():
        sel = lb.curselection()
        if not sel: return
        if messagebox.askyesno("Delete","Delete this coupon?"):
            db_run("DELETE FROM coupons WHERE id=?", (_lb_ids[sel[0]],)); refresh_all()

    make_button(fc,"Create Coupon",  do_add).pack(fill="x",pady=2)
    make_button(fc,"Toggle Active",  do_toggle,color=WARNING).pack(fill="x",pady=2)
    make_button(fc,"Delete",         do_del,   color=DANGER).pack(fill="x",pady=2)

    lc = make_card(cols, padx=14, pady=14); lc.pack(side="right", fill="both", expand=True)
    make_label(lc, "All Coupons", style="heading").pack(anchor="w", pady=(0,4))
    lbf = tk.Frame(lc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    _lb_ids: list = []

    def refresh_lb(*_):
        lb.delete(0,"end"); _lb_ids.clear()
        for c in db_all("SELECT * FROM coupons ORDER BY id DESC"):
            status = "[ON]" if c["active"] else "[OFF]"
            typ = "%" if c["type"] == "percent" else CURR_SYM()
            lb.insert("end",
                f' {status} {c["code"]:<12} {typ}{c["value"]:<7.1f} min {CURR_SYM()}{c["min_bill"]:<6.0f} exp:{c["expiry"] or "none":<12} used:{c["usage_count"]}')
            _lb_ids.append(c["id"])

    return frame, refresh_lb

_coup_frame, _refresh_coup_lb = build_coupons()

# ═══════════════════════════════════════════════════════════════
#  NEW BILL
# ═══════════════════════════════════════════════════════════════
current_bill: list = []
last_saved_bill: list = []

def build_bill():
    frame = tk.Frame(workspace, bg=BG)
    frames["bill"] = frame

    hdr = tk.Frame(frame, bg=BG); hdr.pack(fill="x", pady=(0,6))
    make_label(hdr, "New Bill", style="title", bg=BG).pack(side="left")
    tk.Label(hdr, text="Ctrl+S Save  |  Ctrl+P Print  |  Ctrl+Z Clear",
             bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right", padx=4)

    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)
    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Build Bill", style="heading").pack(anchor="w", pady=(0,8))

    make_label(fc, "Customer", style="muted").pack(anchor="w", pady=(5,1))
    cb_customer = make_combo(fc, width=26); cb_customer.set("Walk-in"); cb_customer.pack(anchor="w")
    make_label(fc, "Served By", style="muted").pack(anchor="w", pady=(5,1))
    cb_staff = make_combo(fc, width=26); cb_staff.set("—"); cb_staff.pack(anchor="w")
    make_label(fc, "Product", style="muted").pack(anchor="w", pady=(5,1))
    cb_product = make_combo(fc, width=26); cb_product.set("Select product…"); cb_product.pack(anchor="w")
    e_qty      = field_group(fc, "Quantity");     e_qty.insert(0,"1")
    e_discount = field_group(fc, "Discount (%)"); e_discount.insert(0,"0")
    e_tax      = field_group(fc, "Tax (%)");      e_tax.insert(0,"18")
    e_note     = field_group(fc, "Bill Note")
    make_label(fc, "Payment Mode", style="muted").pack(anchor="w", pady=(5,1))
    cb_payment = make_combo(fc, ["Cash","UPI","Card","Credit","Other"], width=26)
    cb_payment.set("Cash"); cb_payment.pack(anchor="w")
    make_label(fc, "Coupon Code", style="muted").pack(anchor="w", pady=(5,1))
    coupon_row = tk.Frame(fc, bg=CARD_BG); coupon_row.pack(anchor="w", fill="x")
    e_coupon = make_entry(coupon_row, width=16); e_coupon.pack(side="left")
    coupon_msg = tk.Label(coupon_row, text="", bg=CARD_BG, fg=SUCCESS, font=F_SMALL, wraplength=160)
    coupon_msg.pack(side="left", padx=(6,0))
    sep(fc)
    suggest_lbl = tk.Label(fc, text="", bg=CARD_BG, fg=WARNING, font=F_SMALL, wraplength=200, justify="left")
    suggest_lbl.pack(anchor="w", pady=(0,4))

    rc = make_card(cols, padx=14, pady=14); rc.pack(side="right", fill="both", expand=True)
    make_label(rc, "Bill Preview", style="heading").pack(anchor="w", pady=(0,6))
    lbf = tk.Frame(rc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    sep(rc, pady=5)

    v_sub  = tk.StringVar(value=f"Subtotal:      {CURR_SYM()}0.00")
    v_disc = tk.StringVar(value=f"Discount (0%): -{CURR_SYM()}0.00")
    v_tax  = tk.StringVar(value=f"Tax (18%):     +{CURR_SYM()}0.00")
    v_coup = tk.StringVar(value=f"Coupon:         {CURR_SYM()}0.00")
    v_tot  = tk.StringVar(value=f"Grand Total:   {CURR_SYM()}0.00")
    for var, col in [(v_sub,MUTED),(v_disc,WARNING),(v_tax,MUTED),(v_coup,SUCCESS)]:
        tk.Label(rc, textvariable=var, bg=CARD_BG, fg=col, font=F_SMALL, anchor="e").pack(fill="x")
    tk.Frame(rc, bg=BORDER, height=1).pack(fill="x", pady=3)
    tk.Label(rc, textvariable=v_tot, bg=CARD_BG, fg=SUCCESS,
             font=("Segoe UI", 12, "bold"), anchor="e").pack(fill="x")

    def compute_total() -> float:
        subtotal   = sum(it["price"] * it["qty"] for it in current_bill)
        disc_pct   = _clamp_discount(e_discount.get())
        tax_pct    = _clamp_tax(e_tax.get())
        after_disc = subtotal * (1 - disc_pct / 100)
        pre_grand  = after_disc * (1 + tax_pct / 100)
        coupon_disc, cmsg = validate_coupon(e_coupon.get(), pre_grand)
        coupon_msg.config(text=cmsg, fg=SUCCESS if "off" in cmsg else DANGER) if cmsg else coupon_msg.config(text="")
        grand = max(0.0, pre_grand - coupon_disc)
        v_sub .set(f"Subtotal:       {CURR_SYM()}{subtotal:.2f}")
        v_disc.set(f"Discount ({disc_pct:.0f}%):  -{CURR_SYM()}{subtotal - after_disc:.2f}")
        v_tax .set(f"Tax ({tax_pct:.0f}%):         +{CURR_SYM()}{after_disc * tax_pct / 100:.2f}")
        v_coup.set(f"Coupon:         -{CURR_SYM()}{coupon_disc:.2f}")
        v_tot .set(f"Grand Total:   {CURR_SYM()}{grand:.2f}")
        sug = auto_suggest_coupon(grand)
        suggest_lbl.config(text=sug)
        return grand

    def render_lb():
        lb.delete(0, "end")
        for it in current_bill:
            lb.insert("end", f' {it["name"]:<24} x{it["qty"]}  @{CURR_SYM()}{it["price"]:.2f} = {CURR_SYM()}{it["price"]*it["qty"]:.2f}')
        compute_total()

    def do_add_item():
        idx = cb_product.current()
        if idx < 0: messagebox.showwarning("Select","Choose a product first"); return
        try:
            qty = int(e_qty.get())
            if qty < 1: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid","Quantity must be a positive integer"); return
        prods = db_all("SELECT * FROM products ORDER BY name")
        if idx >= len(prods): return
        p = prods[idx]
        existing_qty = next((it["qty"] for it in current_bill if it.get("product_id") == p["id"]), 0)
        if existing_qty + qty > (p.get("quantity") or 0):
            messagebox.showwarning("Stock", f'Only {p.get("quantity",0)} in stock.'); return
        for it in current_bill:
            if it["product_id"] == p["id"]:
                it["qty"] += qty; render_lb(); return  # pyre-ignore
        current_bill.append({"product_id": p["id"], "name": p["name"], "price": float(p["price"]), "qty": qty})
        render_lb()

    def do_add_favourite():
        favs = db_all("SELECT p.* FROM products p JOIN favorites f ON p.id=f.product_id ORDER BY p.name")
        if not favs: messagebox.showinfo("Favourites","No favourites yet."); return
        win = tk.Toplevel(root); win.title("Favourites")
        win.geometry("360x300"); win.configure(bg=CARD_BG); _center(win,360,300)
        make_label(win,"Pick a favourite",style="heading",bg=CARD_BG).pack(anchor="w",padx=14,pady=10)
        lbf2 = tk.Frame(win, bg=CARD_BG); lbf2.pack(fill="both", expand=True, padx=10)
        lb2, sb2 = make_listbox(lbf2)
        lb2.pack(side="left", fill="both", expand=True); sb2.pack(side="right", fill="y")
        for f in favs: lb2.insert("end", f' * {f["name"]:<24} {CURR_SYM()}{f["price"]:.2f}  Qty:{f["quantity"]}')
        def _pick():
            sel = lb2.curselection()
            if not sel: return
            p = favs[sel[0]]
            for it in current_bill:
                if it["product_id"] == p["id"]:
                    it["qty"] += 1; render_lb(); win.destroy(); return  # pyre-ignore
            current_bill.append({"product_id": p["id"], "name": p["name"], "price": float(p["price"]), "qty": 1})
            render_lb(); win.destroy()
        make_button(win,"Add to Bill",_pick,color=SUCCESS).pack(pady=8)
        lb2.bind("<Double-Button-1>", lambda _: _pick())

    def do_remove_item():
        sel = lb.curselection()
        if not sel: return
        current_bill.pop(sel[0]); render_lb()

    def do_clear():
        if current_bill and not messagebox.askyesno("Clear","Clear all items?"): return
        current_bill.clear(); render_lb()

    def do_repeat_last():
        if not last_saved_bill: messagebox.showinfo("Repeat","No previous bill."); return
        current_bill.clear(); current_bill.extend([dict(it) for it in last_saved_bill]); render_lb()

    def do_save():
        if not current_bill: messagebox.showwarning("Empty","Add at least one item"); return
        grand    = compute_total()
        subtotal = sum(it["price"] * it["qty"] for it in current_bill)
        disc_pct = _clamp_discount(e_discount.get())
        tax_pct  = _clamp_tax(e_tax.get())
        cust_txt = cb_customer.get() or "Walk-in"
        coupon   = e_coupon.get().strip().upper()
        cust_id  = None
        if cust_txt != "Walk-in":
            row = db_one("SELECT id FROM customers WHERE name=?", (cust_txt,))
            if row: cust_id = row["id"]
        staff_id_val = 0
        staff_sel = cb_staff.get()
        if staff_sel and staff_sel != "—":
            sr = db_one("SELECT id FROM staff WHERE name=?", (staff_sel,))
            if sr: staff_id_val = sr["id"]
        coupon_disc, _ = validate_coupon(coupon, grand) if coupon else (0.0, "")
        bill_id = db_run(
            "INSERT INTO bills (date,customer,customer_id,subtotal,discount,tax,total,note,coupon_code,staff_id,payment_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             cust_txt, cust_id, round(subtotal,2), disc_pct, tax_pct, round(grand,2),
             e_note.get().strip(), coupon, staff_id_val, cb_payment.get() or "Cash")
        )
        db_runmany("INSERT INTO bill_items (bill_id,product_id,name,price,qty) VALUES (?,?,?,?,?)",
                   [(bill_id, it["product_id"], it["name"], it["price"], it["qty"]) for it in current_bill])
        for it in current_bill:
            db_run("UPDATE products SET quantity=MAX(0,quantity-?) WHERE id=?", (it["qty"], it["product_id"]))
        if coupon:
            db_run("UPDATE coupons SET usage_count=usage_count+1 WHERE code=?", (coupon,))
        if cust_id:
            db_run("UPDATE customers SET total_spent=total_spent+?,visit_count=visit_count+1 WHERE id=?",
                   (_rnd(float(grand),2), cust_id))
            auto_tag_customer(cust_id)
        last_saved_bill.clear(); last_saved_bill.extend([dict(it) for it in current_bill])
        current_bill.clear(); render_lb(); refresh_all()
        messagebox.showinfo("Saved", f"Bill #{bill_id} saved!  Total: {CURR_SYM()}{grand:.2f}")

    def do_print():
        if not current_bill: return
        grand = compute_total()
        coupon_disc, _ = validate_coupon(e_coupon.get(), grand)
        lines = _format_receipt(
            bill_id="(preview)", date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            customer=cb_customer.get() or "Walk-in", items=current_bill,
            subtotal=sum(it["price"]*it["qty"] for it in current_bill),
            disc_pct=_clamp_discount(e_discount.get()), tax_pct=_clamp_tax(e_tax.get()),
            grand=grand, note=e_note.get().strip(),
            coupon=e_coupon.get().strip().upper(), coupon_disc=coupon_disc,
            payment_mode=cb_payment.get() or "Cash",
        )
        _save_and_open_receipt(lines)

    make_button(fc,"Add Item",         do_add_item).pack(fill="x",pady=2)
    make_button(fc,"Favourites",        do_add_favourite,color="#7b5ea7").pack(fill="x",pady=2)
    make_button(fc,"Repeat Last Bill",  do_repeat_last,  color=MUTED).pack(fill="x",pady=2)
    make_button(fc,"Remove Item",       do_remove_item,  color=WARNING).pack(fill="x",pady=2)
    make_button(fc,"Save Bill",         do_save,         color=SUCCESS).pack(fill="x",pady=2)
    make_button(fc,"Print / Receipt",   do_print,        color=ACCENT).pack(fill="x",pady=2)
    make_button(fc,"Clear Bill",        do_clear,        color=DANGER).pack(fill="x",pady=2)

    e_discount.bind("<KeyRelease>", lambda _: compute_total())
    e_tax.bind("<KeyRelease>",      lambda _: compute_total())
    e_coupon.bind("<KeyRelease>",   lambda _: compute_total())

    frame.bind_all("<Control-s>", lambda _: do_save())
    frame.bind_all("<Control-p>", lambda _: do_print())
    frame.bind_all("<Control-z>", lambda _: do_clear())
    frame.bind_all("<F1>",        lambda _: navigate("bill"))
    frame.bind_all("<F2>",        lambda _: navigate("products"))
    frame.bind_all("<F3>",        lambda _: navigate("customers"))

    return frame, cb_customer, cb_product, cb_staff, cb_payment

_bill_frame, _bill_cb_cust, _bill_cb_prod, _bill_cb_staff, _bill_cb_payment = build_bill()

# ═══════════════════════════════════════════════════════════════
#  SALES CALENDAR
# ═══════════════════════════════════════════════════════════════
def build_calendar():
    frame = tk.Frame(workspace, bg=BG)
    frames["calendar"] = frame
    cal_year  = tk.IntVar(value=datetime.date.today().year)
    cal_month = tk.IntVar(value=datetime.date.today().month)

    top = tk.Frame(frame, bg=BG); top.pack(fill="x", pady=(0,8))
    make_label(top, "Sales Calendar", style="title", bg=BG).pack(side="left")
    predict_lbl = tk.Label(top, text="", bg=BG, fg=WARNING, font=F_SMALL, wraplength=400)
    predict_lbl.pack(side="right", padx=8)

    nav_f = tk.Frame(frame, bg=BG); nav_f.pack(fill="x", pady=(0,6))
    month_lbl = tk.Label(nav_f, text="", bg=BG, fg=TEXT, font=F_HEAD); month_lbl.pack(side="left", padx=8)

    insight_row = tk.Frame(frame, bg=BG); insight_row.pack(fill="x", pady=(0,6))
    best_day_lbl = tk.Label(insight_row, text="", bg=BG, fg=SUCCESS, font=F_SMALL); best_day_lbl.pack(side="left", padx=8)
    week_chg_lbl = tk.Label(insight_row, text="", bg=BG, fg=ACCENT, font=F_SMALL); week_chg_lbl.pack(side="left", padx=14)

    grid_frame = make_card(frame, padx=8, pady=8); grid_frame.pack(fill="both", expand=False)
    detail_card = make_card(frame, padx=14, pady=10); detail_card.pack(fill="both", expand=True, pady=(6,0))
    detail_lbl = tk.Label(detail_card, text="Click a day to see details",
                          bg=CARD_BG, fg=MUTED, font=F_BODY, justify="left", anchor="nw")
    detail_lbl.pack(fill="both", expand=True)

    def draw_calendar():
        for w in grid_frame.winfo_children(): w.destroy()
        y, m = cal_year.get(), cal_month.get()
        month_lbl.config(text=f"{calendar.month_name[m]}  {y}")
        predict_lbl.config(text=predict_tomorrow())
        best_day_lbl.config(text=f"Best: {get_best_day_of_week()}")
        wc = get_weekly_revenue_change()
        wc_text = f"+{wc:.1f}% vs last week" if wc >= 0 else f"{wc:.1f}% vs last week"
        week_chg_lbl.config(text=wc_text, fg=SUCCESS if wc >= 0 else DANGER)
        day_totals = get_daily_revenue(y, m)
        max_rev = max(day_totals.values()) if day_totals else 1
        med_rev = sorted(day_totals.values())[len(day_totals)//2] if day_totals else 1
        for i, d in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]):
            tk.Label(grid_frame, text=d, bg=CARD_BG, fg=MUTED,
                     font=("Segoe UI", 8, "bold"), width=7).grid(row=0, column=i, padx=2, pady=2)
        first_wd = calendar.monthrange(y, m)[0]
        days_in  = calendar.monthrange(y, m)[1]
        today    = datetime.date.today()
        row, col = 1, first_wd
        for day in range(1, days_in + 1):
            rev  = day_totals.get(day, 0)  # pyre-ignore
            bg_c = CAL_EMPTY if rev == 0 else (CAL_HIGH if rev >= max_rev * 0.7 else (CAL_MED if rev >= med_rev * 0.5 else CAL_LOW))  # pyre-ignore
            is_today = (datetime.date(y, m, day) == today)
            txt_col = "#1a1a28" if rev > 0 else MUTED
            btn = tk.Button(grid_frame,
                text=f"{day}\n{CURR_SYM()+str(int(rev//1000))+'k' if rev>=1000 else (CURR_SYM()+str(int(rev)) if rev>0 else '')}",
                bg=bg_c, fg=txt_col, font=("Segoe UI", 8), relief="flat", bd=2, width=7, height=3,
                highlightbackground=TEXT if is_today else bg_c, highlightthickness=2 if is_today else 0,
                cursor="hand2", command=lambda d=day: show_day_detail(d))  # pyre-ignore
            btn.grid(row=row, column=col, padx=2, pady=2)
            col += 1  # pyre-ignore
            if col > 6: col = 0; row = row + 1

    def show_day_detail(day: int):
        y, m = cal_year.get(), cal_month.get()
        date_str = f"{y:04d}-{m:02d}-{day:02d}"
        bills = db_all("SELECT * FROM bills WHERE date LIKE ?", (f"{date_str}%",))
        total_rev = sum(float(b["total"]) for b in bills)
        item_rev: defaultdict[str, float] = defaultdict(float)
        for b in bills:
            for it in db_all("SELECT * FROM bill_items WHERE bill_id=?", (b["id"],)):
                item_rev[it["name"]] += it["price"] * it["qty"]  # pyre-ignore
        top3 = sorted(item_rev.items(), key=lambda x: x[1], reverse=True)[:3]  # pyre-ignore
        top_txt = "\n".join(f"    {n}  {CURR_SYM()}{v:.2f}" for n, v in top3) if top3 else "    No items"
        detail_lbl.config(text=f"{date_str}\n\n  Revenue:  {CURR_SYM()}{total_rev:,.2f}\n  Bills:    {len(bills)}\n\n  Top Items:\n{top_txt}", fg=TEXT)

    def prev_month():
        m, y = cal_month.get(), cal_year.get()
        m -= 1
        if m < 1: m, y = 12, y - 1
        cal_month.set(m); cal_year.set(y); draw_calendar()

    def next_month():
        m, y = cal_month.get(), cal_year.get()
        m += 1  # pyre-ignore
        if m > 12: m, y = 1, y + 1
        cal_month.set(m); cal_year.set(y); draw_calendar()

    make_button(nav_f,"<",prev_month,color=MUTED).pack(side="left")
    make_button(nav_f,">",next_month,color=MUTED).pack(side="left",padx=4)
    make_button(nav_f,"Today",lambda: (cal_year.set(datetime.date.today().year),
                                        cal_month.set(datetime.date.today().month), draw_calendar()),color=ACCENT).pack(side="left",padx=4)
    leg = tk.Frame(nav_f, bg=BG); leg.pack(side="right")
    for lbl, col in [("High",CAL_HIGH),("Mid",CAL_MED),("Low",CAL_LOW),("None",CAL_EMPTY)]:
        tk.Label(leg, text=f"  {lbl}  ", bg=col if col != CAL_EMPTY else BG,
                 fg="#1a1a28" if col != CAL_EMPTY else MUTED, font=("Segoe UI",8),
                 padx=4, pady=2).pack(side="left", padx=2)

    return frame, draw_calendar

_cal_frame, _draw_calendar = build_calendar()

# ═══════════════════════════════════════════════════════════════
#  SMART INSIGHTS
# ═══════════════════════════════════════════════════════════════
def build_insights():
    frame = tk.Frame(workspace, bg=BG)
    frames["insights"] = frame
    make_label(frame, "Insights", style="title", bg=BG).pack(anchor="w", pady=(0,10))

    tiles = tk.Frame(frame, bg=BG); tiles.pack(fill="x", pady=(0,6))
    v_today = tk.StringVar(value=f"{CURR_SYM()}0"); v_week = tk.StringVar(value=f"{CURR_SYM()}0"); v_month = tk.StringVar(value=f"{CURR_SYM()}0")
    stat_tile(tiles,"Today",     v_today,ACCENT)
    stat_tile(tiles,"This Week", v_week, SUCCESS)
    stat_tile(tiles,"This Month",v_month,WARNING)

    alert_card = make_card(frame, padx=12, pady=8); alert_card.pack(fill="x", pady=(0,6))
    make_label(alert_card,"Alerts",style="heading").pack(anchor="w",pady=(0,4))
    alert_txt = tk.Text(alert_card, bg=INPUT_BG, fg=TEXT, font=F_BODY,
                        relief="flat", bd=6, height=4, wrap="word", state="disabled")
    alert_txt.pack(fill="x")

    row2 = tk.Frame(frame, bg=BG); row2.pack(fill="both", expand=True)
    fm_card = make_card(row2, padx=10, pady=8); fm_card.pack(side="left", fill="both", expand=True, padx=(0,4))
    make_label(fm_card,"Fast Movers (Top 8)",style="heading").pack(anchor="w",pady=(0,4))
    fig_fm = Figure(figsize=(4,2.6),dpi=96,facecolor=CARD_BG)
    ax_fm = cast(Any, fig_fm.add_subplot(111)); ax_fm.set_facecolor(CARD_BG)
    fig_fm.subplots_adjust(left=0.04,right=0.98,top=0.9,bottom=0.28)
    canv_fm = FigureCanvasTkAgg(fig_fm,master=fm_card)
    canv_fm.get_tk_widget().configure(bg=CARD_BG,highlightthickness=0)
    canv_fm.get_tk_widget().pack(fill="both",expand=True)

    ds_card = make_card(row2, padx=10, pady=8); ds_card.pack(side="right", fill="both", expand=True)
    make_label(ds_card,"Dead Stock (not sold 10d)",style="heading").pack(anchor="w",pady=(0,4))
    ds_lbf = tk.Frame(ds_card, bg=CARD_BG); ds_lbf.pack(fill="both", expand=True)
    ds_lb, ds_sb = make_listbox(ds_lbf); ds_lb.pack(side="left",fill="both",expand=True); ds_sb.pack(side="right",fill="y")

    def refresh_insights():
        today = datetime.date.today()
        this_mon = today - datetime.timedelta(days=today.weekday())
        this_month_start = today.replace(day=1)
        _today_rev = sum(float(r["total"]) for r in db_all("SELECT total FROM bills WHERE date LIKE ?", (f"{today.strftime('%Y-%m-%d')}%",)))
        v_today.set(f"{CURR_SYM()}{_today_rev:,.0f}")
        v_week.set(f"{CURR_SYM()}{sum(float(r['total']) for r in db_all('SELECT total FROM bills WHERE date >= ?', (this_mon.strftime('%Y-%m-%d'),))):,.0f}")
        v_month.set(f"{CURR_SYM()}{sum(float(r['total']) for r in db_all('SELECT total FROM bills WHERE date >= ?', (this_month_start.strftime('%Y-%m-%d'),))):,.0f}")
        alerts = []
        dead = get_dead_stock(10)
        if dead: alerts.append(f"{len(dead)} item(s) not sold in 10 days: " + ", ".join(d["name"] for d in dead[:3]) + ("..." if len(dead)>3 else ""))  # pyre-ignore
        wc = get_weekly_revenue_change()
        if wc <= -30: alerts.append(f"Sales dropped {abs(wc):.0f}% this week vs last week!")
        elif wc >= 20: alerts.append(f"Sales up {wc:.0f}% vs last week — great week!")
        for p in db_all("SELECT name, quantity FROM products WHERE quantity < 5 AND quantity > 0"):
            alerts.append(f"Low stock: {p['name']} ({p['quantity']} left)")
        alert_txt.config(state="normal"); alert_txt.delete("1.0","end")
        alert_txt.insert("end", "\n".join(alerts) if alerts else "All clear — no alerts today.")
        alert_txt.config(state="disabled")
        ax_fm.clear(); ax_fm.set_facecolor(CARD_BG)
        for sp in ax_fm.spines.values(): sp.set_visible(False)
        ax_fm.tick_params(colors=MUTED, labelsize=7)
        prod_qty: defaultdict[str, int] = defaultdict(int)
        for it in db_all("SELECT name, qty FROM bill_items"): prod_qty[it["name"]] += it["qty"]  # pyre-ignore
        if prod_qty:
            top = sorted(prod_qty.items(), key=lambda x: x[1], reverse=True)[:8]  # pyre-ignore
            ns, qs = zip(*top); xs = list(range(len(ns)))
            ax_fm.bar(xs, list(qs), color=ACCENT, alpha=0.85)
            ax_fm.set_xticks(xs)
            ax_fm.set_xticklabels(list(ns), rotation=30, ha="right", fontsize=7, color=MUTED)
            ax_fm.set_yticks([])
        else:
            ax_fm.text(0.5,0.5,"No data",ha="center",va="center",transform=ax_fm.transAxes,color=MUTED,fontsize=10)
        canv_fm.draw()
        ds_lb.delete(0,"end")
        dead_full = get_dead_stock(10)
        if not dead_full: ds_lb.insert("end","  All products sold recently")
        for d in dead_full: ds_lb.insert("end", f'  {d["name"]:<28} Qty:{d["quantity"]}')

    return frame, refresh_insights

_ins_frame, _refresh_insights = build_insights()

# ═══════════════════════════════════════════════════════════════
#  REPORTS
# ═══════════════════════════════════════════════════════════════
def build_reports():
    frame = tk.Frame(workspace, bg=BG)
    frames["reports"] = frame
    hdr = tk.Frame(frame, bg=BG); hdr.pack(fill="x", pady=(0,6))
    make_label(hdr,"Reports",style="title",bg=BG).pack(side="left")
    chart_opts = ["Bills per Customer","Revenue by Month","Top Products by Revenue"]
    make_label(hdr,"Chart:",style="muted",bg=BG).pack(side="right",padx=(0,4))
    cb_chart = make_combo(hdr, chart_opts, width=24); cb_chart.set("Bills per Customer"); cb_chart.pack(side="right",padx=(0,8))

    tiles = tk.Frame(frame, bg=BG); tiles.pack(fill="x", pady=(0,6))
    v_rev  = tk.StringVar(value=f"{CURR_SYM()}0"); v_avg = tk.StringVar(value=f"{CURR_SYM()}0"); v_uniq = tk.StringVar(value="0")
    stat_tile(tiles,"Total Revenue",    v_rev,  SUCCESS)
    stat_tile(tiles,"Average Bill",     v_avg,  ACCENT)
    stat_tile(tiles,"Unique Customers", v_uniq, WARNING)

    chart_card = make_card(frame, padx=12, pady=10); chart_card.pack(fill="x", pady=(0,6))
    fig2 = Figure(figsize=(8,2.8),dpi=96,facecolor=CARD_BG)
    ax2  = cast(Any, fig2.add_subplot(111)); ax2.set_facecolor(CARD_BG)
    fig2.subplots_adjust(bottom=0.24,left=0.06,right=0.98,top=0.88)
    canv2 = FigureCanvasTkAgg(fig2,master=chart_card)
    canv2.get_tk_widget().configure(bg=CARD_BG,highlightthickness=0)
    canv2.get_tk_widget().pack(fill="both",expand=True)

    def draw_chart(*_):
        ax2.clear(); ax2.set_facecolor(CARD_BG)
        for sp in ax2.spines.values(): sp.set_visible(False)
        ax2.tick_params(colors=MUTED, labelsize=8)
        bills = db_all("SELECT * FROM bills")
        choice = cb_chart.get()
        if choice == "Bills per Customer":
            cnt = Counter(b["customer"] for b in bills)
            if not cnt: ax2.text(0.5,0.5,"No bills yet",ha="center",va="center",transform=ax2.transAxes,color=MUTED,fontsize=12); canv2.draw(); return
            top = cnt.most_common(10); names_t, vals_t = zip(*top); xs = list(range(len(names_t))); yvals = [float(v) for v in vals_t]
            ax2.fill_between(xs, cast(Any, yvals), alpha=0.25, color=ACCENT)  # type: ignore[arg-type]
            ax2.plot(xs, yvals, "o-", color=ACCENT, linewidth=2, markersize=5)
            for x, y in zip(xs, yvals): ax2.annotate(str(y),(x,y),xytext=(0,5),textcoords="offset points",ha="center",fontsize=8,color=TEXT)
            ax2.set_xticks(xs); ax2.set_xticklabels(list(names_t),rotation=30,ha="right",color=MUTED,fontsize=8); ax2.set_yticks([])
        elif choice == "Revenue by Month":
            monthly: defaultdict[str, float] = defaultdict(float)
            for b in bills:
                k = str(b["date"])[:7]  # pyre-ignore
                monthly[k] += float(b["total"])  # pyre-ignore
            if not monthly: ax2.text(0.5,0.5,"No bills yet",ha="center",va="center",transform=ax2.transAxes,color=MUTED,fontsize=12); canv2.draw(); return
            months = sorted(monthly.keys()); vals = [monthly[m] for m in months]; xs = list(range(len(months)))
            ax2.bar(xs, vals, color=SUCCESS, alpha=0.8, width=0.6)
            for x, y in zip(xs, vals): ax2.annotate(f"{CURR_SYM()}{y:,.0f}",(x,y),xytext=(0,4),textcoords="offset points",ha="center",fontsize=7,color=TEXT)
            ax2.set_xticks(xs); ax2.set_xticklabels(months,rotation=30,ha="right",color=MUTED,fontsize=8); ax2.set_yticks([])
        elif choice == "Top Products by Revenue":
            prod_rev: defaultdict[str, float] = defaultdict(float)
            for it in db_all("SELECT name,price,qty FROM bill_items"):
                prod_rev[it["name"]] += float(it["price"]) * float(it["qty"])
            if not prod_rev: ax2.text(0.5,0.5,"No sales yet",ha="center",va="center",transform=ax2.transAxes,color=MUTED,fontsize=12); canv2.draw(); return
            top = sorted(prod_rev.items(), key=lambda x: x[1], reverse=True)[:10]; names_t, vals_t = zip(*top); xs = list(range(len(names_t))); yvals = list(vals_t)  # pyre-ignore
            ax2.barh(xs, yvals, color=WARNING, alpha=0.85)
            for x, y in zip(xs, yvals): ax2.annotate(f"{CURR_SYM()}{y:,.0f}",(y,x),xytext=(4,0),textcoords="offset points",va="center",fontsize=7,color=TEXT)
            ax2.set_yticks(xs); ax2.set_yticklabels(list(names_t),color=MUTED,fontsize=8); ax2.set_xticks([]); ax2.invert_yaxis()
        canv2.draw()

    cb_chart.bind("<<ComboboxSelected>>", draw_chart)

    def do_export_csv():
        bills = db_all("SELECT * FROM bills ORDER BY id")
        if not bills: messagebox.showwarning("Empty","No bills to export"); return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BASE_DIR, f"bills_export_{ts}.csv")
        with open(path,"w",newline="",encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID","Date","Customer","Subtotal","Discount%","Tax%","Total","Coupon","Note"])
            for b in bills: w.writerow([b["id"],b["date"],b["customer"],b["subtotal"],b["discount"],b["tax"],b["total"],b.get("coupon_code",""),b.get("note","")])
        messagebox.showinfo("Exported", f"Saved to:\n{path}")

    def do_print_bill():
        sel = lb.curselection()
        if not sel: return
        b = db_one("SELECT * FROM bills WHERE id=?", (_lb_ids[sel[0]],))
        if not b: return
        items = db_all("SELECT * FROM bill_items WHERE bill_id=?", (b["id"],))
        coupon = b.get("coupon_code","") or ""
        coupon_disc, _ = validate_coupon(coupon, b["total"]) if coupon else (0.0,"")
        lines = _format_receipt(bill_id=b["id"],date=b["date"],customer=b["customer"],items=items,
                                subtotal=b["subtotal"],disc_pct=b["discount"],tax_pct=b["tax"],grand=b["total"],
                                note=b.get("note",""),coupon=coupon,coupon_disc=coupon_disc,
                                payment_mode=b.get("payment_mode","Cash") or "Cash")
        _save_and_open_receipt(lines)

    def do_delete():
        sel = lb.curselection()
        if not sel: return
        bill_id = _lb_ids[sel[0]]
        if messagebox.askyesno("Delete",f"Delete bill #{bill_id}?"):
            db_run("DELETE FROM bills WHERE id=?", (bill_id,)); refresh_all()

    btn_row = tk.Frame(hdr, bg=BG); btn_row.pack(side="right",padx=(0,8))
    make_button(btn_row,"Export CSV",do_export_csv,color=SUCCESS).pack(side="left",padx=4)
    make_button(btn_row,"Print Bill",do_print_bill,color=ACCENT).pack(side="left",padx=4)
    make_button(btn_row,"Delete",    do_delete,    color=DANGER).pack(side="left",padx=4)

    lc = make_card(frame, padx=14, pady=14); lc.pack(fill="both", expand=True)
    sf = tk.Frame(lc, bg=CARD_BG); sf.pack(fill="x", pady=(0,6))
    make_label(sf,"Search:",style="muted").pack(side="left",padx=(0,6))
    sv = tk.StringVar(); se = make_entry(sf); se.configure(textvariable=sv); se.pack(side="left",fill="x",expand=True)
    make_label(lc,"All Bills",style="heading").pack(anchor="w",pady=(0,4))
    lbf = tk.Frame(lc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list = []

    def refresh_lb(*_):
        q = sv.get().lower(); lb.delete(0,"end"); _lb_ids.clear()
        for b in db_all("SELECT * FROM bills ORDER BY id DESC"):
            coup = f" [{b.get('coupon_code','')}]" if b.get("coupon_code") else ""
            row = f' #{str(b["id"]):<4}  {b["date"]}  {b["customer"]:<20} {CURR_SYM()}{b["total"]}{coup}'
            if q and q not in row.lower(): continue
            lb.insert("end", row); _lb_ids.append(b["id"])
        all_bills = db_all("SELECT total, customer FROM bills")
        if all_bills:
            rev = sum(float(b["total"]) for b in all_bills)
            v_rev.set(f"{CURR_SYM()}{rev:,.2f}"); v_avg.set(f"{CURR_SYM()}{rev/len(all_bills):,.2f}")
            v_uniq.set(str(len(set(b["customer"] for b in all_bills))))
        else:
            v_rev.set(f"{CURR_SYM()}0"); v_avg.set(f"{CURR_SYM()}0"); v_uniq.set("0")
        draw_chart()

    sv.trace("w", refresh_lb)
    return frame, refresh_lb, draw_chart

_rep_frame, _refresh_rep_lb, _draw_rep_chart = build_reports()

# ═══════════════════════════════════════════════════════════════
#  RECEIPT HELPERS
# ═══════════════════════════════════════════════════════════════
def _format_receipt(bill_id, date, customer, items, subtotal, disc_pct, tax_pct, grand, note,
                    coupon="", coupon_disc=0.0, payment_mode="Cash") -> list:
    W = 46
    shop = APP_SETTINGS.get("shop_name", "My Shop")
    phone = APP_SETTINGS.get("shop_phone", "")
    addr  = APP_SETTINGS.get("shop_address", "")
    curr  = CURR_SYM()
    header = [f"  {shop}"]
    if phone: header.append(f"  Tel: {phone}")
    if addr:  header.append(f"  {addr}")
    lines = ["="*W] + header + ["="*W,
             f"  Bill #  : {bill_id}", f"  Date    : {date}", f"  Customer: {customer}",
             "-"*W, f"  {'ITEM':<22} {'QTY':>3}  {'UNIT':>7}  {'TOTAL':>8}", "-"*W]
    for it in items:
        name = textwrap.shorten(it["name"], width=22, placeholder="...")
        lines.append(f"  {name:<22} {it['qty']:>3}  {curr}{it['price']:>5.2f}  {curr}{it['price']*it['qty']:>6.2f}")
    subtotal = float(subtotal); disc_pct = float(disc_pct); tax_pct = float(tax_pct)
    after_disc = subtotal * (1 - disc_pct / 100); tax_amt = after_disc * tax_pct / 100; grand = _rnd(float(grand),2)
    lines += ["-"*W, f"  {'Subtotal':<32} {curr}{subtotal:>6.2f}",  # pyre-ignore
              f"  {'Discount ('+str(disc_pct)+'%)':<32}-{curr}{subtotal-after_disc:>5.2f}",
              f"  {'Tax ('+str(tax_pct)+'%)':<32}+{curr}{tax_amt:>5.2f}"]
    if coupon and coupon_disc > 0: lines.append(f"  {'Coupon ('+coupon+')':<32}-{curr}{coupon_disc:>5.2f}")
    lines += ["="*W, f"  {'GRAND TOTAL':<32} {curr}{grand:>6.2f}", "="*W]  # pyre-ignore
    if note: lines += [f"  Note: {note}", "-"*W]  # pyre-ignore
    lines += [f"  Payment: {payment_mode}", "", "     Thank you for your business!", ""]  # pyre-ignore
    return lines

def _save_and_open_receipt(lines: list):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BASE_DIR, f"receipt_{ts}.txt")
    with open(path,"w",encoding="utf-8") as f: f.write("\n".join(lines))
    win = tk.Toplevel(root); win.title("Receipt"); win.geometry("520x460"); win.configure(bg=BG)
    tk.Label(win,text="Receipt Preview",bg=BG,fg=TEXT,font=F_HEAD).pack(pady=(10,4))
    tk.Label(win,text=f"Saved: {path}",bg=BG,fg=MUTED,font=F_SMALL,wraplength=480).pack()
    txt = tk.Text(win,bg=INPUT_BG,fg=TEXT,font=("Consolas",10),relief="flat",bd=8,wrap="none")
    txt.pack(fill="both",expand=True,padx=10,pady=6)
    txt.insert("end","\n".join(lines)); txt.config(state="disabled")
    make_button(win,"Close",win.destroy,color=DANGER).pack(pady=(0,8))

# ═══════════════════════════════════════════════════════════════
#  STAFF
# ═══════════════════════════════════════════════════════════════
def build_staff():
    frame = tk.Frame(workspace, bg=BG)
    frames["staff"] = frame
    make_label(frame,"Staff",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)
    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc,"Add / Edit Staff",style="heading").pack(anchor="w",pady=(0,8))
    e_sname  = field_group(fc,"Full Name *")
    e_sphone = field_group(fc,"Phone")
    make_label(fc,"Role",style="muted").pack(anchor="w",pady=(5,1))
    cb_role = make_combo(fc,["Manager","Staff","Cashier","Delivery"],width=22); cb_role.set("Staff"); cb_role.pack(anchor="w")
    e_shift_s = field_group(fc,"Shift Start (HH:MM)"); e_shift_s.insert(0,"09:00")
    e_shift_e = field_group(fc,"Shift End (HH:MM)");   e_shift_e.insert(0,"18:00")
    e_salary  = field_group(fc,f"Salary ({CURR_SYM()}/month)");  e_salary.insert(0,"0")
    e_comm    = field_group(fc,"Commission (%)");       e_comm.insert(0,"0")
    err_lbl   = make_label(fc,"",style="danger"); err_lbl.pack(anchor="w",pady=(4,0))
    sep(fc)
    selected_id = tk.IntVar(value=0)

    def clear_form():
        for e in (e_sname,e_sphone,e_shift_s,e_shift_e,e_salary,e_comm): e.delete(0,"end")
        e_shift_s.insert(0,"09:00"); e_shift_e.insert(0,"18:00"); e_salary.insert(0,"0"); e_comm.insert(0,"0")
        cb_role.set("Staff"); selected_id.set(0); err_lbl.config(text="")

    def do_save_staff():
        name = e_sname.get().strip()
        if not name: err_lbl.config(text="Name required."); return
        try: sal = float(e_salary.get()); comm = float(e_comm.get())
        except ValueError: err_lbl.config(text="Salary/commission must be numbers."); return
        sid = selected_id.get()
        if sid:
            db_run("UPDATE staff SET name=?,phone=?,role=?,shift_start=?,shift_end=?,salary=?,commission_pct=? WHERE id=?",
                   (name,e_sphone.get().strip(),cb_role.get(),e_shift_s.get().strip(),e_shift_e.get().strip(),sal,comm,sid))
        else:
            db_run("INSERT INTO staff (name,phone,role,shift_start,shift_end,salary,commission_pct) VALUES (?,?,?,?,?,?,?)",
                   (name,e_sphone.get().strip(),cb_role.get(),e_shift_s.get().strip(),e_shift_e.get().strip(),sal,comm))
        clear_form(); refresh_all()

    def do_del_staff():
        sel = lb.curselection()
        if not sel: return
        sid = _lb_ids[sel[0]]
        s = db_one("SELECT name FROM staff WHERE id=?", (sid,))
        if s and messagebox.askyesno("Delete",f'Delete "{s["name"]}"?'):
            db_run("DELETE FROM staff WHERE id=?", (sid,)); refresh_all()

    def do_load_staff():
        sel = lb.curselection()
        if not sel: return
        s = db_one("SELECT * FROM staff WHERE id=?", (_lb_ids[sel[0]],))
        if not s: return
        clear_form(); e_sname.insert(0,s["name"]); e_sphone.insert(0,s.get("phone",""))
        cb_role.set(s.get("role","Staff")); e_shift_s.delete(0,"end"); e_shift_s.insert(0,s.get("shift_start","09:00"))
        e_shift_e.delete(0,"end"); e_shift_e.insert(0,s.get("shift_end","18:00"))
        e_salary.delete(0,"end"); e_salary.insert(0,str(s.get("salary",0)))
        e_comm.delete(0,"end"); e_comm.insert(0,str(s.get("commission_pct",0))); selected_id.set(s["id"])

    def do_clock():
        sel = lb.curselection()
        if not sel: return
        sid = _lb_ids[sel[0]]; today = datetime.date.today().strftime("%Y-%m-%d"); now = datetime.datetime.now().strftime("%H:%M")
        att = db_one("SELECT * FROM attendance WHERE staff_id=? AND date=?", (sid,today))
        if not att:
            db_run("INSERT INTO attendance (staff_id,date,clock_in) VALUES (?,?,?)",(sid,today,now))
            messagebox.showinfo("Clock In",f"Clocked IN at {now}")
        elif not att.get("clock_out"):
            ot = calc_overtime(sid,today)
            db_run("UPDATE attendance SET clock_out=?,overtime_hrs=? WHERE staff_id=? AND date=?",(now,ot,sid,today))
            messagebox.showinfo("Clock Out",f"Clocked OUT at {now}\nOvertime: {ot:.2f} hrs")
        else:
            messagebox.showinfo("Done",f"Already clocked out at {att['clock_out']}.")

    make_button(fc,"Save / Update",  do_save_staff).pack(fill="x",pady=2)
    make_button(fc,"Load Selected",  do_load_staff,color=WARNING).pack(fill="x",pady=2)
    make_button(fc,"Clock In/Out",   do_clock,     color=ACCENT).pack(fill="x",pady=2)
    make_button(fc,"Delete",         do_del_staff, color=DANGER).pack(fill="x",pady=2)

    lc = make_card(cols, padx=14, pady=14); lc.pack(side="right", fill="both", expand=True)
    make_label(lc,"Team",style="heading").pack(anchor="w",pady=(0,4))
    lbf = tk.Frame(lc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list = []

    def refresh_lb(*_):
        lb.delete(0,"end"); _lb_ids.clear()
        y = datetime.date.today().year; m = datetime.date.today().month
        for s in db_all("SELECT * FROM staff ORDER BY name"):
            sales = get_staff_sales(s["id"],y,m); comm = _rnd(float(sales)*float(s.get("commission_pct",0))/100.0,2)
            lb.insert("end",f' {"[ON]" if s["active"] else "[OFF]"} {s["name"]:<20} {s.get("role",""):<10} Sales:{CURR_SYM()}{sales:,.0f} Comm:{CURR_SYM()}{comm:.0f}')
            _lb_ids.append(s["id"])
        lb.bind("<Double-Button-1>",lambda e: do_load_staff())

    return frame, refresh_lb

_staff_frame, _refresh_staff_lb = build_staff()

# ═══════════════════════════════════════════════════════════════
#  TARGETS
# ═══════════════════════════════════════════════════════════════
def build_targets():
    frame = tk.Frame(workspace, bg=BG)
    frames["targets"] = frame
    make_label(frame,"Sales Targets",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    today = datetime.date.today()
    ctrl = tk.Frame(frame, bg=BG); ctrl.pack(fill="x", pady=(0,8))
    make_label(ctrl,"Year:",style="muted",bg=BG).pack(side="left")
    e_year = make_entry(ctrl,width=6); e_year.insert(0,str(today.year)); e_year.pack(side="left",padx=4)
    make_label(ctrl,"Month:",style="muted",bg=BG).pack(side="left",padx=(8,0))
    cb_month = make_combo(ctrl,[str(i) for i in range(1,13)],width=4); cb_month.set(str(today.month)); cb_month.pack(side="left",padx=4)
    make_label(ctrl,f"Target ({CURR_SYM()}):",style="muted",bg=BG).pack(side="left",padx=(8,0))
    e_target = make_entry(ctrl,width=12); e_target.pack(side="left",padx=4)
    cb_staff_t = make_combo(ctrl,width=18); cb_staff_t.set("—"); cb_staff_t.pack(side="left",padx=4)

    def do_set():
        try: y=int(e_year.get()); m=int(cb_month.get()); tgt=float(e_target.get())
        except ValueError: messagebox.showerror("Invalid","Enter valid numbers."); return
        period=f"{y:04d}-{m:02d}"; sname=cb_staff_t.get(); sid=0
        if sname and sname!="—":
            sr=db_one("SELECT id FROM staff WHERE name=?",(sname,))
            if sr: sid=sr["id"]
        existing=db_one("SELECT id FROM sales_targets WHERE period=? AND staff_id=?",(period,sid))
        if existing: db_run("UPDATE sales_targets SET target_amt=? WHERE id=?",(tgt,existing["id"]))
        else: db_run("INSERT INTO sales_targets (period,target_amt,staff_id) VALUES (?,?,?)",(period,tgt,sid))
        refresh_all()

    make_button(ctrl,"Set Target",do_set,color=SUCCESS).pack(side="left",padx=8)
    prog_card = make_card(frame, padx=18, pady=14); prog_card.pack(fill="x", pady=(0,8))
    make_label(prog_card,"This Month Progress",style="heading").pack(anchor="w",pady=(0,6))
    v_target=tk.StringVar(value=f"Target: {CURR_SYM()}0"); v_current=tk.StringVar(value=f"Achieved: {CURR_SYM()}0")
    v_remain=tk.StringVar(value=f"Remaining: {CURR_SYM()}0"); v_daily=tk.StringVar(value=f"Req/day: {CURR_SYM()}0"); v_pct=tk.StringVar(value="0%")
    row_t = tk.Frame(prog_card, bg=CARD_BG); row_t.pack(fill="x")
    for var,col in [(v_target,MUTED),(v_current,SUCCESS),(v_remain,DANGER),(v_daily,WARNING)]:
        tk.Label(row_t,textvariable=var,bg=CARD_BG,fg=col,font=("Segoe UI",11,"bold")).pack(side="left",padx=16)
    prog_canvas = tk.Canvas(prog_card,bg=INPUT_BG,height=22,highlightthickness=0); prog_canvas.pack(fill="x",pady=(8,4),padx=4)
    tk.Label(prog_card,textvariable=v_pct,bg=CARD_BG,fg=TEXT,font=F_SMALL).pack(anchor="e")

    def _draw_progress(pct: float):
        prog_canvas.update_idletasks(); w=prog_canvas.winfo_width(); prog_canvas.delete("all")
        prog_canvas.create_rectangle(0,0,w,22,fill=INPUT_BG,outline="")
        fill_w=int(w*float(min(float(pct),1.0))); color=SUCCESS if pct>=1.0 else (WARNING if pct>=0.6 else DANGER)
        prog_canvas.create_rectangle(0,0,fill_w,22,fill=color,outline="")

    st_card = make_card(frame, padx=14, pady=10); st_card.pack(fill="both", expand=True)
    make_label(st_card,"Staff Targets",style="heading").pack(anchor="w",pady=(0,4))
    lbf = tk.Frame(st_card, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")

    def refresh_targets():
        y=today.year; m=today.month; target=get_month_target(y,m); current=get_month_revenue(y,m)
        remain=max(0.0,target-current); daily=required_daily_sales(y,m); pct=(current/target) if target>0 else 0.0
        v_target.set(f"Target:   {CURR_SYM()}{target:,.0f}"); v_current.set(f"Achieved: {CURR_SYM()}{current:,.0f}")
        v_remain.set(f"Remaining: {CURR_SYM()}{remain:,.0f}"); v_daily.set(f"Req/day:  {CURR_SYM()}{daily:,.0f}")
        v_pct.set(f"{pct*100:.1f}%  achieved"); prog_card.after(50,lambda: _draw_progress(pct))
        lb.delete(0,"end")
        staff_list=db_all("SELECT * FROM staff WHERE active=1 ORDER BY name")
        cb_staff_t.configure(values=["—"]+[s["name"] for s in staff_list])
        for s in staff_list:
            st_tgt=get_month_target(y,m,s["id"]); st_rev=get_staff_sales(s["id"],y,m)
            st_pct=(st_rev/st_tgt*100) if st_tgt>0 else 0
            bar="█"*int(st_pct/10)+"░"*(10-int(float(min(float(st_pct),100.0))/10))
            lb.insert("end",f' {s["name"]:<20} Target:{CURR_SYM()}{st_tgt:>8,.0f}  Got:{CURR_SYM()}{st_rev:>8,.0f}  {bar} {st_pct:.0f}%')

    return frame, refresh_targets

_tgt_frame, _refresh_targets = build_targets()

# ═══════════════════════════════════════════════════════════════
#  HOLIDAYS
# ═══════════════════════════════════════════════════════════════
def build_holidays():
    frame = tk.Frame(workspace, bg=BG)
    frames["holidays"] = frame
    make_label(frame,"Holidays & Closures",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)
    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc,"Mark Holiday",style="heading").pack(anchor="w",pady=(0,8))
    e_hdate = field_group(fc,"Date (YYYY-MM-DD)"); e_hdate.insert(0,datetime.date.today().strftime("%Y-%m-%d"))
    e_hname = field_group(fc,"Name / Reason")
    make_label(fc,"Type",style="muted").pack(anchor="w",pady=(5,1))
    cb_htype = make_combo(fc,["holiday","half-day","closure","festival"],width=22); cb_htype.set("holiday"); cb_htype.pack(anchor="w")
    err_lbl = make_label(fc,"",style="danger"); err_lbl.pack(anchor="w",pady=(4,0)); sep(fc)

    def do_add():
        dt=e_hdate.get().strip()
        try: datetime.datetime.strptime(dt,"%Y-%m-%d")
        except ValueError: err_lbl.config(text="Date: YYYY-MM-DD"); return
        nm=e_hname.get().strip() or dt
        existing=db_one("SELECT id FROM holidays WHERE date=?",(dt,))
        if existing: db_run("UPDATE holidays SET name=?,type=? WHERE date=?",(nm,cb_htype.get(),dt))
        else: db_run("INSERT INTO holidays (date,name,type) VALUES (?,?,?)",(dt,nm,cb_htype.get()))
        err_lbl.config(text=""); refresh_all()

    def do_del():
        sel=lb.curselection()
        if not sel: return
        if messagebox.askyesno("Delete","Remove this holiday?"):
            db_run("DELETE FROM holidays WHERE id=?",(_lb_ids[sel[0]],)); refresh_all()

    def do_bulk_add():
        today=datetime.date.today(); y,m=today.year,today.month; last=calendar.monthrange(y,m)[1]; count=0
        for d in range(1,last+1):
            dd=datetime.date(y,m,d)
            if dd.weekday()==6:
                ds=dd.strftime("%Y-%m-%d")
                if not db_one("SELECT id FROM holidays WHERE date=?",(ds,)):
                    db_run("INSERT INTO holidays (date,name,type) VALUES (?,?,?)",(ds,"Sunday","holiday")); count = count + 1  # pyre-ignore
        messagebox.showinfo("Done",f"Added {count} Sundays."); refresh_all()

    make_button(fc,"Mark Holiday",    do_add).pack(fill="x",pady=2)
    make_button(fc,"Add All Sundays", do_bulk_add,color=WARNING).pack(fill="x",pady=2)
    make_button(fc,"Delete",          do_del,     color=DANGER).pack(fill="x",pady=2)

    lc = make_card(cols, padx=14, pady=14); lc.pack(side="right", fill="both", expand=True)
    make_label(lc,"All Holidays",style="heading").pack(anchor="w",pady=(0,4))
    lbf = tk.Frame(lc, bg=CARD_BG); lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list = []

    def refresh_lb(*_):
        lb.delete(0,"end"); _lb_ids.clear()
        ICONS={"holiday":"[HOL]","half-day":"[HLF]","closure":"[CLS]","festival":"[FES]"}
        for h in db_all("SELECT * FROM holidays ORDER BY date"):
            lb.insert("end",f' {ICONS.get(h["type"],"[---]")}  {h["date"]}  {h["name"]:<28} [{h["type"]}]')
            _lb_ids.append(h["id"])

    return frame, refresh_lb

_hol_frame, _refresh_hol_lb = build_holidays()

# ═══════════════════════════════════════════════════════════════
#  EXPENSES
# ═══════════════════════════════════════════════════════════════
def build_expenses():
    frame = tk.Frame(workspace, bg=BG)
    frames["expenses"] = frame
    make_label(frame,"Expenses & Profit",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    tiles = tk.Frame(frame, bg=BG); tiles.pack(fill="x", pady=(0,8))
    v_rev_t=tk.StringVar(value=f"{CURR_SYM()}0"); v_exp_t=tk.StringVar(value=f"{CURR_SYM()}0"); v_pft_t=tk.StringVar(value=f"{CURR_SYM()}0")
    stat_tile(tiles,"Revenue (month)",  v_rev_t,SUCCESS)
    stat_tile(tiles,"Expenses (month)", v_exp_t,DANGER)
    stat_tile(tiles,"Profit (month)",   v_pft_t,ACCENT)
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)
    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc,"Add Expense",style="heading").pack(anchor="w",pady=(0,8))
    e_edate = field_group(fc,"Date (YYYY-MM-DD)"); e_edate.insert(0,datetime.date.today().strftime("%Y-%m-%d"))
    make_label(fc,"Category",style="muted").pack(anchor="w",pady=(5,1))
    cb_ecat = make_combo(fc,EXPENSE_CATS,width=22); cb_ecat.set("General"); cb_ecat.pack(anchor="w")
    e_eamt = field_group(fc,f"Amount ({CURR_SYM()})"); e_enote = field_group(fc,"Note")
    err_lbl = make_label(fc,"",style="danger"); err_lbl.pack(anchor="w",pady=(4,0)); sep(fc)

    def do_add():
        dt=e_edate.get().strip()
        try: datetime.datetime.strptime(dt,"%Y-%m-%d")
        except ValueError: err_lbl.config(text="Date: YYYY-MM-DD"); return
        try: amt=float(e_eamt.get()); assert amt>0
        except: err_lbl.config(text="Amount must be > 0."); return
        db_run("INSERT INTO expenses (date,category,amount,note) VALUES (?,?,?,?)",
               (dt,cb_ecat.get(),amt,e_enote.get().strip()))
        for e in (e_eamt,e_enote): e.delete(0,"end"); err_lbl.config(text=""); refresh_all()

    def do_del():
        sel=lb.curselection()
        if not sel: return
        if messagebox.askyesno("Delete","Delete this expense?"):
            db_run("DELETE FROM expenses WHERE id=?",(_lb_ids[sel[0]],)); refresh_all()

    make_button(fc,"Add Expense",do_add).pack(fill="x",pady=2)
    make_button(fc,"Delete",     do_del,color=DANGER).pack(fill="x",pady=2)
    rc = make_card(cols, padx=14, pady=14); rc.pack(side="right", fill="both", expand=True)
    fig_e=Figure(figsize=(4,2.2),dpi=96,facecolor=CARD_BG)
    ax_e=cast(Any, fig_e.add_subplot(111)); ax_e.set_facecolor(CARD_BG)
    fig_e.subplots_adjust(left=0.04,right=0.98,top=0.88,bottom=0.1)
    canv_e=FigureCanvasTkAgg(fig_e,master=rc)
    canv_e.get_tk_widget().configure(bg=CARD_BG,highlightthickness=0); canv_e.get_tk_widget().pack(fill="x",pady=(0,6))
    sep(rc,pady=4)
    lbf=tk.Frame(rc,bg=CARD_BG); lbf.pack(fill="both",expand=True)
    lb,sb=make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list = []

    def refresh_expenses():
        y=datetime.date.today().year; m=datetime.date.today().month
        rev=get_month_revenue(y,m); exp=get_month_expenses(y,m); pft=get_month_profit(y,m)
        v_rev_t.set(f"{CURR_SYM()}{rev:,.0f}"); v_exp_t.set(f"{CURR_SYM()}{exp:,.0f}"); v_pft_t.set(f"{CURR_SYM()}{pft:,.0f}")
        cats: dict = defaultdict(float)
        for r in db_all("SELECT category,amount FROM expenses WHERE date LIKE ?",(f"{y:04d}-{m:02d}-%",)):
            cats[r["category"]] = float(cats[r["category"]]) + float(r["amount"])  # pyre-ignore
        ax_e.clear(); ax_e.set_facecolor(CARD_BG)
        for sp in ax_e.spines.values(): sp.set_visible(False)
        if cats:
            labels=list(cats.keys()); vals2=[cats[k] for k in labels]
            colors=[DANGER,WARNING,ACCENT,SUCCESS,MUTED,"#7b5ea7","#e74c3c","#1abc9c"][:len(labels)]
            ax_e.pie(vals2,labels=labels,colors=colors,textprops={"color":TEXT,"fontsize":7},startangle=90)
        else:
            ax_e.text(0.5,0.5,"No expenses",ha="center",va="center",transform=ax_e.transAxes,color=MUTED,fontsize=10)
        canv_e.draw()
        lb.delete(0,"end"); _lb_ids.clear()
        for r in db_all("SELECT * FROM expenses ORDER BY date DESC LIMIT 100"):
            lb.insert("end",f' {r["date"]}  {r["category"]:<16} {CURR_SYM()}{r["amount"]:>8.2f}  {r.get("note","")[:24]}')  # pyre-ignore
            _lb_ids.append(r["id"])

    return frame, refresh_expenses

_exp_frame, _refresh_expenses = build_expenses()

# ═══════════════════════════════════════════════════════════════
#  PURCHASE ORDERS
# ═══════════════════════════════════════════════════════════════
def build_purchase_orders():
    frame = tk.Frame(workspace, bg=BG)
    frames["purchase_orders"] = frame
    make_label(frame,"Stock Orders",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    cols = tk.Frame(frame, bg=BG); cols.pack(fill="both", expand=True)
    fc = make_card(cols, padx=18, pady=16); fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc,"Create Order",style="heading").pack(anchor="w",pady=(0,8))
    make_label(fc,"Product",style="muted").pack(anchor="w",pady=(5,1))
    cb_po_prod=make_combo(fc,width=24); cb_po_prod.set("Select..."); cb_po_prod.pack(anchor="w")
    e_po_qty  = field_group(fc,"Qty to Order"); e_po_qty.insert(0,"10")
    e_po_cost = field_group(fc,f"Unit Cost ({CURR_SYM()})"); e_po_cost.insert(0,"0")
    e_po_supp = field_group(fc,"Supplier")
    e_po_note = field_group(fc,"Note")
    err_lbl   = make_label(fc,"",style="danger"); err_lbl.pack(anchor="w",pady=(4,0)); sep(fc)
    make_label(fc,"Reorder Needed",style="warn").pack(anchor="w",pady=(4,0))
    sug_lbf=tk.Frame(fc,bg=CARD_BG); sug_lbf.pack(fill="x")
    sug_lb=tk.Listbox(sug_lbf,bg=INPUT_BG,fg=WARNING,font=F_SMALL,height=5,relief="flat",bd=0,activestyle="none")
    sug_lb.pack(fill="x")

    def do_create():
        idx=cb_po_prod.current(); prods=db_all("SELECT * FROM products ORDER BY name")
        if idx<0 or idx>=len(prods): err_lbl.config(text="Select a product."); return
        p=prods[idx]
        try: qty=int(e_po_qty.get()); cost=float(e_po_cost.get())
        except ValueError: err_lbl.config(text="Qty=integer, Cost=number."); return
        db_run("INSERT INTO purchase_orders (date,product_id,product_name,qty_ordered,unit_cost,supplier,note) VALUES (?,?,?,?,?,?,?)",
               (datetime.date.today().strftime("%Y-%m-%d"),p["id"],p["name"],qty,cost,e_po_supp.get().strip(),e_po_note.get().strip()))
        for e in (e_po_qty,e_po_cost,e_po_supp,e_po_note): e.delete(0,"end")
        e_po_qty.insert(0,"10"); err_lbl.config(text=""); refresh_all()

    def do_receive():
        sel=lb.curselection()
        if not sel: return
        o=db_one("SELECT * FROM purchase_orders WHERE id=?",(_lb_ids[sel[0]],))
        if not o: return
        if o["status"]!="Pending": messagebox.showinfo("Done","Already processed."); return
        db_run("UPDATE purchase_orders SET status='Received' WHERE id=?",(_lb_ids[sel[0]],))
        if o["product_id"]: db_run("UPDATE products SET quantity=quantity+? WHERE id=?",(o["qty_ordered"],o["product_id"]))
        refresh_all(); messagebox.showinfo("Received",f"Stock +{o['qty_ordered']} {o['product_name']}")

    def do_cancel():
        sel=lb.curselection()
        if not sel: return
        if messagebox.askyesno("Cancel","Cancel this order?"):
            db_run("UPDATE purchase_orders SET status='Cancelled' WHERE id=?",(_lb_ids[sel[0]],)); refresh_all()

    def do_quick_reorder():
        sugs=get_reorder_suggestions()
        if not sugs: messagebox.showinfo("Good","No reorder needed."); return
        for p in sugs:
            db_run("INSERT INTO purchase_orders (date,product_id,product_name,qty_ordered,unit_cost,note) VALUES (?,?,?,?,?,?)",
                   (datetime.date.today().strftime("%Y-%m-%d"),p["id"],p["name"],20,0,"Auto-reorder"))
        messagebox.showinfo("Done",f"Created {len(sugs)} reorder(s)."); refresh_all()

    make_button(fc,"Create Order",    do_create).pack(fill="x",pady=2)
    make_button(fc,"Mark Received",   do_receive,       color=SUCCESS).pack(fill="x",pady=2)
    make_button(fc,"Quick Reorder All",do_quick_reorder,color=WARNING).pack(fill="x",pady=2)
    make_button(fc,"Cancel Order",    do_cancel,        color=DANGER).pack(fill="x",pady=2)

    lc=make_card(cols,padx=14,pady=14); lc.pack(side="right",fill="both",expand=True)
    make_label(lc,"All Orders",style="heading").pack(anchor="w",pady=(0,4))
    lbf=tk.Frame(lc,bg=CARD_BG); lbf.pack(fill="both",expand=True)
    lb,sb=make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list=[]

    def refresh_po(*_):
        lb.delete(0,"end"); _lb_ids.clear()
        sug_lb.delete(0,"end")
        for p in get_reorder_suggestions(): sug_lb.insert("end",f" {p['name']} — only {p['quantity']} left")
        cb_po_prod.configure(values=[p["name"] for p in db_all("SELECT name FROM products ORDER BY name")])
        STATUS={"Pending":"[...]","Received":"[OK ]","Cancelled":"[---]"}
        for o in db_all("SELECT * FROM purchase_orders ORDER BY id DESC"):
            lb.insert("end",f' {STATUS.get(o["status"],"?")} #{o["id"]:<3} {o["date"]}  {o["product_name"]:<22} x{o["qty_ordered"]}  @{CURR_SYM()}{o["unit_cost"]:.0f}  {o.get("supplier","")[:16]}')  # pyre-ignore
            _lb_ids.append(o["id"])

    return frame, refresh_po

_po_frame, _refresh_po = build_purchase_orders()

# ═══════════════════════════════════════════════════════════════
#  GST REPORT
# ═══════════════════════════════════════════════════════════════
def build_gst():
    frame = tk.Frame(workspace, bg=BG)
    frames["gst"] = frame
    hdr=tk.Frame(frame,bg=BG); hdr.pack(fill="x",pady=(0,8))
    make_label(hdr,"GST Report",style="title",bg=BG).pack(side="left")
    ctrl=tk.Frame(frame,bg=BG); ctrl.pack(fill="x",pady=(0,8))
    make_label(ctrl,"Year:",style="muted",bg=BG).pack(side="left")
    e_gy=make_entry(ctrl,width=6); e_gy.insert(0,str(datetime.date.today().year)); e_gy.pack(side="left",padx=4)
    make_label(ctrl,"Month:",style="muted",bg=BG).pack(side="left",padx=(8,0))
    cb_gm=make_combo(ctrl,[str(i) for i in range(1,13)],width=4); cb_gm.set(str(datetime.date.today().month)); cb_gm.pack(side="left",padx=4)
    make_button(ctrl,"Generate",lambda: do_generate(),color=ACCENT).pack(side="left",padx=8)
    make_button(ctrl,"Export CSV",lambda: do_export_gst(),color=SUCCESS).pack(side="left",padx=4)
    tiles=tk.Frame(frame,bg=BG); tiles.pack(fill="x",pady=(0,8))
    v_taxable=tk.StringVar(value=f"{CURR_SYM()}0"); v_cgst=tk.StringVar(value=f"{CURR_SYM()}0")
    v_sgst=tk.StringVar(value=f"{CURR_SYM()}0"); v_total_tax=tk.StringVar(value=f"{CURR_SYM()}0")
    stat_tile(tiles,"Taxable Value",v_taxable,ACCENT); stat_tile(tiles,"CGST (9%)",v_cgst,WARNING)
    stat_tile(tiles,"SGST (9%)",v_sgst,WARNING); stat_tile(tiles,"Total Tax",v_total_tax,DANGER)
    hsn_card=make_card(frame,padx=14,pady=10); hsn_card.pack(fill="x",pady=(0,6))
    make_label(hsn_card,"HSN-wise Summary",style="heading").pack(anchor="w",pady=(0,4))
    hsn_lbf=tk.Frame(hsn_card,bg=CARD_BG); hsn_lbf.pack(fill="x")
    hsn_lb,hsn_sb=make_listbox(hsn_lbf,height=5); hsn_lb.pack(side="left",fill="x",expand=True); hsn_sb.pack(side="right",fill="y")
    lc=make_card(frame,padx=14,pady=10); lc.pack(fill="both",expand=True)
    make_label(lc,"Bill-wise Tax Breakdown",style="heading").pack(anchor="w",pady=(0,4))
    lbf=tk.Frame(lc,bg=CARD_BG); lbf.pack(fill="both",expand=True)
    lb,sb=make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _report_data: list=[]

    def do_generate():
        _report_data.clear()
        try: y=int(e_gy.get()); m=int(cb_gm.get())
        except ValueError: messagebox.showerror("Invalid","Enter valid year/month"); return
        bills=db_all("SELECT * FROM bills WHERE date LIKE ?",(f"{y:04d}-{m:02d}-%",))
        lb.delete(0,"end"); hsn_lb.delete(0,"end")
        total_taxable=0.0; total_tax=0.0; hsn_map = defaultdict(lambda:{"taxable":0.0,"tax":0.0,"gst_rate":18.0})
        for b in bills:
            tax_pct=float(b.get("tax",0) or 0); subtotal=float(b.get("subtotal",0) or 0)
            disc_pct=float(b.get("discount",0) or 0); after_disc=subtotal*(1-disc_pct/100)
            tax_amt=_rnd(float(after_disc)*float(tax_pct)/100.0,2); cgst=_rnd(float(tax_amt)/2.0,2); sgst=_rnd(float(tax_amt)/2.0,2)
            total_taxable+=after_disc; total_tax+=tax_amt  # pyre-ignore
            _report_data.append({"bill_id":b["id"],"date":b["date"][:10],"customer":b["customer"],  # pyre-ignore
                                  "taxable":after_disc,"tax_pct":tax_pct,"tax_amt":tax_amt,
                                  "cgst":cgst,"sgst":sgst,"total":float(b["total"]),"payment_mode":b.get("payment_mode","Cash")})
            lb.insert("end",f' #{str(b["id"]):<4} {b["date"][:10]}  {b["customer"]:<18} Tax:{tax_pct:.0f}%  Taxable:{CURR_SYM()}{after_disc:>8.2f}  CGST:{CURR_SYM()}{cgst:>7.2f}  SGST:{CURR_SYM()}{sgst:>7.2f}')  # pyre-ignore
            items=db_all("SELECT bi.*,p.hsn_code,p.gst_rate FROM bill_items bi LEFT JOIN products p ON bi.product_id=p.id WHERE bi.bill_id=?",(b["id"],))
            for it in items:
                hsn=str(it.get("hsn_code") or "N/A"); grat=float(it.get("gst_rate") or tax_pct or 18)
                item_val=float(it["price"])*int(it["qty"])
                hsn_map[hsn]["taxable"] = float(hsn_map[hsn]["taxable"]) + item_val  # pyre-ignore
                hsn_map[hsn]["tax"] = float(hsn_map[hsn]["tax"]) + item_val*grat/100.0  # pyre-ignore
                hsn_map[hsn]["gst_rate"] = grat
        v_taxable.set(f"{CURR_SYM()}{total_taxable:,.2f}"); v_cgst.set(f"{CURR_SYM()}{total_tax/2.0:,.2f}")
        v_sgst.set(f"{CURR_SYM()}{total_tax/2:,.2f}"); v_total_tax.set(f"{CURR_SYM()}{total_tax:,.2f}")
        hsn_lb.delete(0,"end")
        hsn_lb.insert("end",f' {"HSN":<12} {"GST%":>5}  {"Taxable":>12}  {"CGST":>10}  {"SGST":>10}')
        hsn_lb.insert("end","  "+"─"*55)
        for hsn,vals in sorted(hsn_map.items()):
            hsn_lb.insert("end",f' {hsn:<12} {vals["gst_rate"]:>5.0f}%  {CURR_SYM()}{vals["taxable"]:>10.2f}  {CURR_SYM()}{vals["tax"]/2:>8.2f}  {CURR_SYM()}{vals["tax"]/2:>8.2f}')

    def do_export_gst():
        if not _report_data: do_generate()
        if not _report_data: messagebox.showwarning("Empty","No data to export"); return
        ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); path=os.path.join(BASE_DIR,f"gst_report_{ts}.csv")
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["Bill#","Date","Customer","Taxable","Tax%","Tax","CGST","SGST","Total","Payment"])
            for r in _report_data: w.writerow([r["bill_id"],r["date"],r["customer"],_rnd(float(r["taxable"]),2),r["tax_pct"],_rnd(float(r["tax_amt"]),2),_rnd(float(r["cgst"]),2),_rnd(float(r["sgst"]),2),_rnd(float(r["total"]),2),r["payment_mode"]])
        messagebox.showinfo("Exported",f"Saved:\n{path}")

    def refresh_gst(): do_generate()
    return frame, refresh_gst

_gst_frame, _refresh_gst = build_gst()

# ═══════════════════════════════════════════════════════════════
#  END OF DAY
# ═══════════════════════════════════════════════════════════════
def build_eod():
    frame = tk.Frame(workspace, bg=BG)
    frames["eod"] = frame
    hdr=tk.Frame(frame,bg=BG); hdr.pack(fill="x",pady=(0,8))
    make_label(hdr,"End of Day Report",style="title",bg=BG).pack(side="left")
    ctrl=tk.Frame(frame,bg=BG); ctrl.pack(fill="x",pady=(0,8))
    make_label(ctrl,"Date:",style="muted",bg=BG).pack(side="left")
    e_eod_date=make_entry(ctrl,width=14); e_eod_date.insert(0,datetime.date.today().strftime("%Y-%m-%d")); e_eod_date.pack(side="left",padx=6)
    make_button(ctrl,"Load",lambda: do_load_eod(),color=ACCENT).pack(side="left",padx=4)
    make_button(ctrl,"Print / Save",lambda: do_print_eod(),color=SUCCESS).pack(side="left",padx=4)
    tiles=tk.Frame(frame,bg=BG); tiles.pack(fill="x",pady=(0,8))
    v_erev=tk.StringVar(value=f"{CURR_SYM()}0"); v_ebills=tk.StringVar(value="0"); v_eavg=tk.StringVar(value=f"{CURR_SYM()}0"); v_eexp=tk.StringVar(value=f"{CURR_SYM()}0")
    stat_tile(tiles,"Revenue",v_erev,SUCCESS); stat_tile(tiles,"Bills",v_ebills,ACCENT)
    stat_tile(tiles,"Avg Bill",v_eavg,WARNING); stat_tile(tiles,"Expenses",v_eexp,DANGER)
    cols=tk.Frame(frame,bg=BG); cols.pack(fill="both",expand=True)
    lc=make_card(cols,padx=14,pady=12); lc.pack(side="left",fill="both",expand=True,padx=(0,4))
    make_label(lc,"Payment Breakdown",style="heading").pack(anchor="w",pady=(0,4))
    pay_lbf=tk.Frame(lc,bg=CARD_BG); pay_lbf.pack(fill="x")
    pay_lb,pay_sb=make_listbox(pay_lbf,height=5); pay_lb.pack(side="left",fill="x",expand=True); pay_sb.pack(side="right",fill="y")
    sep(lc,pady=6)
    make_label(lc,"Staff Performance",style="heading").pack(anchor="w",pady=(0,4))
    staff_lbf=tk.Frame(lc,bg=CARD_BG); staff_lbf.pack(fill="both",expand=True)
    staff_lb,staff_sb=make_listbox(staff_lbf,height=6); staff_lb.pack(side="left",fill="both",expand=True); staff_sb.pack(side="right",fill="y")
    rc=make_card(cols,padx=14,pady=12); rc.pack(side="right",fill="both",expand=True)
    make_label(rc,"Top Items Sold",style="heading").pack(anchor="w",pady=(0,4))
    top_lbf=tk.Frame(rc,bg=CARD_BG); top_lbf.pack(fill="x")
    top_lb,top_sb=make_listbox(top_lbf,height=6); top_lb.pack(side="left",fill="x",expand=True); top_sb.pack(side="right",fill="y")
    sep(rc,pady=6)
    make_label(rc,"Payment Split",style="heading").pack(anchor="w",pady=(0,4))
    fig_pay=Figure(figsize=(3.5,2.2),dpi=96,facecolor=CARD_BG)
    ax_pay=cast(Any, fig_pay.add_subplot(111)); ax_pay.set_facecolor(CARD_BG)
    fig_pay.subplots_adjust(left=0.04,right=0.98,top=0.92,bottom=0.04)
    canv_pay=FigureCanvasTkAgg(fig_pay,master=rc)
    canv_pay.get_tk_widget().configure(bg=CARD_BG,highlightthickness=0); canv_pay.get_tk_widget().pack(fill="both",expand=True)
    _eod_lines: list=[]

    def do_load_eod():
        _eod_lines.clear(); date_str=e_eod_date.get().strip()
        try: datetime.datetime.strptime(date_str,"%Y-%m-%d")
        except ValueError: messagebox.showerror("Invalid","Date: YYYY-MM-DD"); return
        bills=db_all("SELECT * FROM bills WHERE date LIKE ?",(f"{date_str}%",))
        rev=sum(float(b["total"]) for b in bills); count=len(bills); avg=(rev/count) if count else 0.0
        exp=sum(float(r["amount"]) for r in db_all("SELECT amount FROM expenses WHERE date=?",(date_str,)))
        v_erev.set(f"{CURR_SYM()}{rev:,.2f}"); v_ebills.set(str(count)); v_eavg.set(f"{CURR_SYM()}{avg:,.2f}"); v_eexp.set(f"{CURR_SYM()}{exp:,.2f}")
        pay_totals: dict=defaultdict(float); pay_counts: dict=defaultdict(int)
        for b in bills:
            pm=str(b.get("payment_mode","Cash") or "Cash"); pay_totals[pm] = float(pay_totals[pm]) + float(b["total"]); pay_counts[pm] = int(pay_counts[pm]) + 1  # pyre-ignore
        pay_lb.delete(0,"end"); pay_lb.insert("end",f' {"Mode":<12} {"Bills":>6}  {"Amount":>12}'); pay_lb.insert("end","  "+"─"*32)
        for pm,amt in sorted(pay_totals.items(),key=lambda x: x[1],reverse=True):
            pay_lb.insert("end",f' {pm:<12} {pay_counts[pm]:>6}  {CURR_SYM()}{amt:>10.2f}')
        ax_pay.clear(); ax_pay.set_facecolor(CARD_BG)
        if pay_totals:
            labels=list(pay_totals.keys()); vals2=list(pay_totals.values()); colors=[ACCENT,SUCCESS,WARNING,DANGER,MUTED][:len(labels)]  # pyre-ignore
            ax_pay.pie(vals2,labels=labels,colors=colors,textprops={"color":TEXT,"fontsize":8},startangle=90,autopct="%1.0f%%",pctdistance=0.75)
        else: ax_pay.text(0.5,0.5,"No data",ha="center",va="center",transform=ax_pay.transAxes,color=MUTED,fontsize=10)
        canv_pay.draw()
        item_qty: dict=defaultdict(int); item_rev: dict=defaultdict(float)
        for b in bills:
            for it in db_all("SELECT * FROM bill_items WHERE bill_id=?",(b["id"],)):
                item_qty[it["name"]]=int(item_qty[it["name"]])+int(it["qty"]); item_rev[it["name"]]=float(item_rev[it["name"]])+float(it["price"])*float(it["qty"])  # pyre-ignore
        top_lb.delete(0,"end"); top_lb.insert("end",f' {"Item":<26} {"Qty":>5}  {"Revenue":>10}'); top_lb.insert("end","  "+"─"*44)
        for nm,rev2 in sorted(item_rev.items(),key=lambda x: x[1],reverse=True)[:8]:  # pyre-ignore
            top_lb.insert("end",f' {nm:<26} {item_qty[nm]:>5}  {CURR_SYM()}{rev2:>8.2f}')
        staff_sales: dict=defaultdict(float); staff_bills: dict=defaultdict(int)
        for b in bills:
            sid=b.get("staff_id") or 0
            sname="Unassigned"
            if sid:
                s=db_one("SELECT name FROM staff WHERE id=?",(sid,))
                if s: sname=s["name"]
            staff_sales[sname]=float(staff_sales[sname])+float(b["total"]); staff_bills[sname]=int(staff_bills[sname])+1  # pyre-ignore
        staff_lb.delete(0,"end"); staff_lb.insert("end",f' {"Staff":<22} {"Bills":>6}  {"Revenue":>12}'); staff_lb.insert("end","  "+"─"*42)
        for sn,sal in sorted(staff_sales.items(),key=lambda x: x[1],reverse=True):
            staff_lb.insert("end",f' {sn:<22} {staff_bills[sn]:>6}  {CURR_SYM()}{sal:>10.2f}')
        _eod_lines.extend(["="*48,"    END OF DAY REPORT","="*48,f"  Date: {date_str}",
                            f"  Revenue: {CURR_SYM()}{rev:,.2f}   Bills: {count}   Avg: {CURR_SYM()}{avg:,.2f}",
                            f"  Expenses: {CURR_SYM()}{exp:,.2f}   Net: {CURR_SYM()}{float(rev)-float(exp):,.2f}",""])

    def do_print_eod():
        if not _eod_lines: do_load_eod()
        if not _eod_lines: return
        ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); path=os.path.join(BASE_DIR,f"eod_report_{ts}.txt")
        with open(path,"w",encoding="utf-8") as f: f.write("\n".join(_eod_lines))
        win=tk.Toplevel(root); win.title("EOD Report"); win.geometry("540x440"); win.configure(bg=BG); _center(win,540,440)
        txt=tk.Text(win,bg=INPUT_BG,fg=TEXT,font=("Consolas",9),relief="flat",bd=8,wrap="none")
        txt.pack(fill="both",expand=True,padx=8,pady=6); txt.insert("end","\n".join(_eod_lines)); txt.config(state="disabled")
        make_button(win,"Close",win.destroy,color=DANGER).pack(pady=(0,8))

    def refresh_eod():
        e_eod_date.delete(0,"end"); e_eod_date.insert(0,datetime.date.today().strftime("%Y-%m-%d")); do_load_eod()

    return frame, refresh_eod

_eod_frame, _refresh_eod = build_eod()

# ═══════════════════════════════════════════════════════════════
#  CASH REGISTER
# ═══════════════════════════════════════════════════════════════
def build_cash_register():
    frame = tk.Frame(workspace, bg=BG)
    frames["cash_register"] = frame
    make_label(frame,"Cash Register",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    ctrl=tk.Frame(frame,bg=BG); ctrl.pack(fill="x",pady=(0,8))
    make_label(ctrl,"Date:",style="muted",bg=BG).pack(side="left")
    e_date=make_entry(ctrl,width=14); e_date.insert(0,datetime.date.today().strftime("%Y-%m-%d")); e_date.pack(side="left",padx=6)
    make_label(ctrl,f"Opening Cash ({CURR_SYM()}):",style="muted",bg=BG).pack(side="left",padx=(8,0))
    e_opening=make_entry(ctrl,width=12); e_opening.insert(0,"0"); e_opening.pack(side="left",padx=4)
    make_button(ctrl,"Set Opening",lambda: do_set_opening(),color=ACCENT).pack(side="left",padx=6)
    make_button(ctrl,"Load",lambda: do_load(),color=MUTED).pack(side="left",padx=4)
    tiles=tk.Frame(frame,bg=BG); tiles.pack(fill="x",pady=(0,8))
    v_open=tk.StringVar(value=f"{CURR_SYM()}0"); v_cash_in=tk.StringVar(value=f"{CURR_SYM()}0"); v_out=tk.StringVar(value=f"{CURR_SYM()}0"); v_close=tk.StringVar(value=f"{CURR_SYM()}0")
    stat_tile(tiles,"Opening",   v_open,   MUTED); stat_tile(tiles,"Cash Sales",v_cash_in,SUCCESS)
    stat_tile(tiles,"Cash Out",  v_out,    DANGER); stat_tile(tiles,"Expected Close",v_close,ACCENT)
    detail_card=make_card(frame,padx=18,pady=12); detail_card.pack(fill="both",expand=True)
    make_label(detail_card,"Transaction Log",style="heading").pack(anchor="w",pady=(0,4))
    lbf=tk.Frame(detail_card,bg=CARD_BG); lbf.pack(fill="both",expand=True)
    lb,sb=make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")

    def do_set_opening():
        date_str=e_date.get().strip()
        try: datetime.datetime.strptime(date_str,"%Y-%m-%d"); opening=float(e_opening.get())
        except ValueError: messagebox.showerror("Invalid","Check date and amount"); return
        existing=db_one("SELECT id FROM cash_register WHERE date=?",(date_str,))
        if existing: db_run("UPDATE cash_register SET opening_cash=? WHERE date=?",(opening,date_str))
        else: db_run("INSERT INTO cash_register (date,opening_cash) VALUES (?,?)",(date_str,opening))
        do_load()

    def do_load():
        date_str=e_date.get().strip()
        try: datetime.datetime.strptime(date_str,"%Y-%m-%d")
        except ValueError: messagebox.showerror("Invalid","Date: YYYY-MM-DD"); return
        bal=get_cash_balance(date_str)
        v_open.set(f"{CURR_SYM()}{bal['opening']:,.2f}"); v_cash_in.set(f"{CURR_SYM()}{bal['sales_cash']:,.2f}")
        v_out.set(f"{CURR_SYM()}{bal['expenses']:,.2f}"); v_close.set(f"{CURR_SYM()}{bal['closing']:,.2f}")
        lb.delete(0,"end"); lb.insert("end",f' {"DESCRIPTION":<36} {"AMOUNT":>12}'); lb.insert("end","  "+"─"*50)
        lb.insert("end",f' {"Opening Cash":<36} {CURR_SYM()}{bal["opening"]:>10.2f}')
        for b in db_all("SELECT * FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total>=0",(f"{date_str}%",)):
            lb.insert("end",f' Bill #{b["id"]} — {b["customer"]:<26} +{CURR_SYM()}{b["total"]:>8.2f}')
        for b in db_all("SELECT * FROM bills WHERE date LIKE ? AND total<0",(f"{date_str}%",)):
            lb.insert("end",f' REFUND #{b["id"]} — {b["customer"]:<24} -{CURR_SYM()}{abs(float(b["total"])):>8.2f}')
        for e in db_all("SELECT * FROM expenses WHERE date=?",(date_str,)):
            lb.insert("end",f' Expense: {e["category"]:<29} -{CURR_SYM()}{e["amount"]:>8.2f}')
        lb.insert("end","  "+"─"*50); lb.insert("end",f' {"EXPECTED CLOSING":<36} {CURR_SYM()}{bal["closing"]:>10.2f}')

    def refresh_cr():
        e_date.delete(0,"end"); e_date.insert(0,datetime.date.today().strftime("%Y-%m-%d")); do_load()

    return frame, refresh_cr

_cr_frame, _refresh_cr = build_cash_register()

# ═══════════════════════════════════════════════════════════════
#  REFUNDS
# ═══════════════════════════════════════════════════════════════
def build_refunds():
    frame = tk.Frame(workspace, bg=BG)
    frames["refunds"] = frame
    make_label(frame,"Refunds & Returns",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    sf=make_card(frame,padx=16,pady=12); sf.pack(fill="x",pady=(0,8))
    make_label(sf,"Find Bill to Refund",style="heading").pack(anchor="w",pady=(0,6))
    sr=tk.Frame(sf,bg=CARD_BG); sr.pack(fill="x")
    make_label(sr,"Bill # or Customer:",style="muted").pack(side="left")
    e_search=make_entry(sr,width=20); e_search.pack(side="left",padx=6)
    make_button(sr,"Search",lambda: do_search(),color=ACCENT).pack(side="left",padx=4)
    make_label(sf,"Reason:",style="muted").pack(anchor="w",pady=(6,1))
    e_reason=make_entry(sf,width=40); e_reason.pack(anchor="w")
    lc=make_card(frame,padx=14,pady=12); lc.pack(fill="both",expand=True)
    make_label(lc,"Results — select a bill then click Refund",style="muted").pack(anchor="w",pady=(0,4))
    lbf=tk.Frame(lc,bg=CARD_BG); lbf.pack(fill="both",expand=True)
    lb,sb=make_listbox(lbf); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list=[]
    hist_card=make_card(frame,padx=14,pady=10); hist_card.pack(fill="x",pady=(6,0))
    make_label(hist_card,"Recent Refunds",style="heading").pack(anchor="w",pady=(0,4))
    hist_lbf=tk.Frame(hist_card,bg=CARD_BG); hist_lbf.pack(fill="x")
    hist_lb,hist_sb=make_listbox(hist_lbf,height=4); hist_lb.pack(side="left",fill="x",expand=True); hist_sb.pack(side="right",fill="y")

    def do_search():
        q=e_search.get().strip().lower(); lb.delete(0,"end"); _lb_ids.clear()
        if not q: return
        for b in db_all("SELECT * FROM bills WHERE total>0 ORDER BY id DESC LIMIT 200"):
            if q in str(b["id"]) or q in b["customer"].lower():
                lb.insert("end",f' #{b["id"]:<4} {b["date"][:16]}  {b["customer"]:<22}  {CURR_SYM()}{b["total"]:.2f}  [{b.get("payment_mode","Cash")}]')  # pyre-ignore
                _lb_ids.append(b["id"])

    def do_refund():
        sel=lb.curselection()
        if not sel: messagebox.showwarning("Select","Select a bill first"); return
        b=db_one("SELECT * FROM bills WHERE id=?",(_lb_ids[sel[0]],))
        if not b: return
        reason=e_reason.get().strip() or "Customer return"
        if not messagebox.askyesno("Confirm",f'Refund Bill #{b["id"]} — {b["customer"]} — {CURR_SYM()}{b["total"]:.2f}?\nReason: {reason}'): return
        refund_id=db_run("INSERT INTO bills (date,customer,customer_id,subtotal,discount,tax,total,note,coupon_code,staff_id,payment_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),b["customer"],b.get("customer_id"),-float(b["subtotal"]),b["discount"],b["tax"],-float(b["total"]),f"REFUND of Bill #{b['id']}: {reason}","",b.get("staff_id",0),b.get("payment_mode","Cash")))
        for it in db_all("SELECT * FROM bill_items WHERE bill_id=?",(b["id"],)):
            db_run("INSERT INTO bill_items (bill_id,product_id,name,price,qty) VALUES (?,?,?,?,?)",(refund_id,it["product_id"],it["name"],it["price"],-it["qty"]))
            if it["product_id"]: db_run("UPDATE products SET quantity=quantity+? WHERE id=?",(it["qty"],it["product_id"]))
        if b.get("customer_id"):
            db_run("UPDATE customers SET total_spent=MAX(0,total_spent-?),visit_count=MAX(0,visit_count-1) WHERE id=?",(float(b["total"]),b["customer_id"]))
        lb.delete(0,"end"); _lb_ids.clear(); refresh_all()
        messagebox.showinfo("Refunded",f"Refund #{refund_id} created.  -{CURR_SYM()}{b['total']:.2f}")

    make_button(lc,"Process Refund",do_refund,color=DANGER).pack(anchor="w",pady=(6,0))

    def refresh_refunds():
        hist_lb.delete(0,"end")
        refunds=db_all("SELECT * FROM bills WHERE total<0 ORDER BY id DESC LIMIT 20")
        if not refunds: hist_lb.insert("end","  No refunds yet.")
        for r in refunds: hist_lb.insert("end",f' #{r["id"]:<4} {r["date"][:16]}  {r["customer"]:<22}  {CURR_SYM()}{r["total"]:.2f}')  # pyre-ignore

    return frame, refresh_refunds

_ref_frame, _refresh_refunds = build_refunds()

# ═══════════════════════════════════════════════════════════════
#  BREAK-EVEN
# ═══════════════════════════════════════════════════════════════
def build_breakeven():
    frame = tk.Frame(workspace, bg=BG)
    frames["breakeven"] = frame
    make_label(frame,"Break-Even Calculator",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    ctrl=tk.Frame(frame,bg=BG); ctrl.pack(fill="x",pady=(0,8))
    make_label(ctrl,"Year:",style="muted",bg=BG).pack(side="left")
    e_bey=make_entry(ctrl,width=6); e_bey.insert(0,str(datetime.date.today().year)); e_bey.pack(side="left",padx=4)
    make_label(ctrl,"Month:",style="muted",bg=BG).pack(side="left",padx=(8,0))
    cb_bem=make_combo(ctrl,[str(i) for i in range(1,13)],width=4); cb_bem.set(str(datetime.date.today().month)); cb_bem.pack(side="left",padx=4)
    make_button(ctrl,"Calculate",lambda: do_calc(),color=ACCENT).pack(side="left",padx=8)
    tiles=tk.Frame(frame,bg=BG); tiles.pack(fill="x",pady=(0,8))
    v_fixed=tk.StringVar(value=f"{CURR_SYM()}0"); v_rev_be=tk.StringVar(value=f"{CURR_SYM()}0"); v_status=tk.StringVar(value="—"); v_units=tk.StringVar(value="—")
    stat_tile(tiles,"Fixed Costs",v_fixed,DANGER); stat_tile(tiles,"Revenue",v_rev_be,SUCCESS)
    stat_tile(tiles,"Status",     v_status,ACCENT); stat_tile(tiles,"Units to B/E",v_units,WARNING)
    chart_card=make_card(frame,padx=12,pady=10); chart_card.pack(fill="x",pady=(0,6))
    make_label(chart_card,"Revenue vs Expenses (12 months)",style="heading").pack(anchor="w",pady=(0,4))
    fig_be=Figure(figsize=(8,2.8),dpi=96,facecolor=CARD_BG)
    ax_be=cast(Any, fig_be.add_subplot(111)); ax_be.set_facecolor(CARD_BG)
    fig_be.subplots_adjust(left=0.06,right=0.98,top=0.88,bottom=0.24)
    canv_be=FigureCanvasTkAgg(fig_be,master=chart_card)
    canv_be.get_tk_widget().configure(bg=CARD_BG,highlightthickness=0); canv_be.get_tk_widget().pack(fill="both",expand=True)
    detail_card=make_card(frame,padx=16,pady=10); detail_card.pack(fill="both",expand=True)
    detail_txt=tk.Text(detail_card,bg=INPUT_BG,fg=TEXT,font=F_BODY,relief="flat",bd=6,height=5,wrap="word",state="disabled")
    detail_txt.pack(fill="both",expand=True)

    def do_calc():
        try: y=int(e_bey.get()); m=int(cb_bem.get())
        except ValueError: messagebox.showerror("Invalid","Enter valid year/month"); return
        be=get_breakeven(y,m)
        v_fixed.set(f"{CURR_SYM()}{be['fixed_costs']:,.0f}"); v_rev_be.set(f"{CURR_SYM()}{be['revenue']:,.0f}")
        v_status.set(f"Profit {CURR_SYM()}{be['surplus']:,.0f}" if be["breakeven_reached"] else f"Need {CURR_SYM()}{be['shortfall']:,.0f} more")
        v_units.set(f"{be['units_needed']} x {(be['top_product'] or '')[:12]}" if be["units_needed"] else "—")  # pyre-ignore
        ax_be.clear(); ax_be.set_facecolor(CARD_BG)
        for sp in ax_be.spines.values(): sp.set_visible(False)
        ax_be.tick_params(colors=MUTED,labelsize=8)
        months_data=[]
        for i in range(11,-1,-1):
            dt=datetime.date(y,m,1)-datetime.timedelta(days=i*30)
            months_data.append((f"{dt.year}-{dt.month:02d}",get_month_revenue(dt.year,dt.month),get_month_expenses(dt.year,dt.month)))
        xs=list(range(len(months_data))); labels=[d[0] for d in months_data]; revs=[d[1] for d in months_data]; exps=[d[2] for d in months_data]
        ax_be.bar(xs,revs,color=SUCCESS,alpha=0.7,width=0.4,label="Revenue")
        ax_be.bar([x+0.4 for x in xs],exps,color=DANGER,alpha=0.7,width=0.4,label="Expenses")
        ax_be.axhline(be["fixed_costs"],color=WARNING,linewidth=1.5,linestyle="--",label=f"B/E {CURR_SYM()}{be['fixed_costs']:,.0f}")
        ax_be.set_xticks(xs); ax_be.set_xticklabels(labels,rotation=30,ha="right",color=MUTED,fontsize=7)
        ax_be.set_yticks([]); ax_be.legend(fontsize=7,labelcolor=TEXT,facecolor=CARD_BG,edgecolor=BORDER)
        canv_be.draw()
        text=f"Month: {y}-{m:02d}\n\n  Fixed Costs: {CURR_SYM()}{be['fixed_costs']:,.2f}\n  Revenue:     {CURR_SYM()}{be['revenue']:,.2f}\n"
        if be["breakeven_reached"]: text+=f"  Break-even reached! Surplus: {CURR_SYM()}{be['surplus']:,.2f}\n"  # pyre-ignore
        else: text+=f"  Still need: {CURR_SYM()}{be['shortfall']:,.2f}\n  Units needed: {be['units_needed']} x {be['top_product'] or 'N/A'}\n"  # pyre-ignore
        detail_txt.config(state="normal"); detail_txt.delete("1.0","end"); detail_txt.insert("end",text); detail_txt.config(state="disabled")

    def refresh_be(): do_calc()
    return frame, refresh_be

_be_frame, _refresh_be = build_breakeven()

# ═══════════════════════════════════════════════════════════════
#  ROSTER
# ═══════════════════════════════════════════════════════════════
def build_roster():
    frame = tk.Frame(workspace, bg=BG)
    frames["roster"] = frame
    make_label(frame,"Staff Roster",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    DAYS=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    DAY_KEYS=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    SHIFT_OPTS=["—","Morning (6-14)","Afternoon (14-22)","Night (22-6)","Full Day","Half Day","Off"]
    ctrl=tk.Frame(frame,bg=BG); ctrl.pack(fill="x",pady=(0,8))
    make_label(ctrl,"Week of:",style="muted",bg=BG).pack(side="left")
    today=datetime.date.today(); mon=today-datetime.timedelta(days=today.weekday())
    e_week=make_entry(ctrl,width=14); e_week.insert(0,mon.strftime("%Y-%m-%d")); e_week.pack(side="left",padx=6)
    make_button(ctrl,"Load Week",lambda: do_load_week(),color=ACCENT).pack(side="left",padx=4)
    make_button(ctrl,"Save Roster",lambda: do_save_roster(),color=SUCCESS).pack(side="left",padx=4)
    make_button(ctrl,"Print",lambda: do_print_roster(),color=MUTED).pack(side="left",padx=4)
    grid_card=make_card(frame,padx=12,pady=10); grid_card.pack(fill="both",expand=True)
    hdr_row=tk.Frame(grid_card,bg=CARD_BG); hdr_row.pack(fill="x",pady=(0,4))
    tk.Label(hdr_row,text="Staff",bg=CARD_BG,fg=MUTED,font=F_SMALL,width=18,anchor="w").pack(side="left")
    for d in DAYS: tk.Label(hdr_row,text=d[:3],bg=CARD_BG,fg=MUTED,font=F_SMALL,width=10).pack(side="left")  # pyre-ignore
    scroll_frame=tk.Frame(grid_card,bg=CARD_BG); scroll_frame.pack(fill="both",expand=True)
    _roster_widgets: dict={}

    def do_load_week():
        for w in scroll_frame.winfo_children(): w.destroy()
        _roster_widgets.clear()
        week_start=e_week.get().strip()
        try: datetime.datetime.strptime(week_start,"%Y-%m-%d")
        except ValueError: messagebox.showerror("Invalid","Date: YYYY-MM-DD"); return
        staff_list=db_all("SELECT * FROM staff WHERE active=1 ORDER BY name")
        if not staff_list: make_label(scroll_frame,"No active staff.",style="muted").pack(pady=16); return
        for s in staff_list:
            row=tk.Frame(scroll_frame,bg=CARD_BG); row.pack(fill="x",pady=2)
            tk.Label(row,text=s["name"][:18],bg=CARD_BG,fg=TEXT,font=F_SMALL,width=18,anchor="w").pack(side="left")  # pyre-ignore
            existing=db_one("SELECT * FROM roster WHERE staff_id=? AND week_start=?",(s["id"],week_start))
            day_combos={}
            for dk in DAY_KEYS:
                cb=ttk.Combobox(row,values=SHIFT_OPTS,width=10,state="readonly",style="App.TCombobox")
                saved=(existing.get(dk,"—") if existing else "—") or "—"
                cb.set(saved); cb.pack(side="left",padx=1); day_combos[dk]=cb
            _roster_widgets[s["id"]]=day_combos

    def do_save_roster():
        week_start=e_week.get().strip()
        for staff_id,day_combos in _roster_widgets.items():
            vals={dk: day_combos[dk].get() for dk in DAY_KEYS}
            existing=db_one("SELECT id FROM roster WHERE staff_id=? AND week_start=?",(staff_id,week_start))
            if existing:
                db_run("UPDATE roster SET monday=?,tuesday=?,wednesday=?,thursday=?,friday=?,saturday=?,sunday=? WHERE staff_id=? AND week_start=?",
                       (vals["monday"],vals["tuesday"],vals["wednesday"],vals["thursday"],vals["friday"],vals["saturday"],vals["sunday"],staff_id,week_start))
            else:
                db_run("INSERT INTO roster (staff_id,week_start,monday,tuesday,wednesday,thursday,friday,saturday,sunday) VALUES (?,?,?,?,?,?,?,?,?)",
                       (staff_id,week_start,vals["monday"],vals["tuesday"],vals["wednesday"],vals["thursday"],vals["friday"],vals["saturday"],vals["sunday"]))
        messagebox.showinfo("Saved","Roster saved.")

    def do_print_roster():
        week_start=e_week.get().strip()
        staff_list=db_all("SELECT * FROM staff WHERE active=1 ORDER BY name")
        lines=["="*80,f"  STAFF ROSTER — Week of {week_start}","="*80,f' {"STAFF":<20}'+"".join(f"{d[:3]:^12}" for d in DAYS),"-"*80]  # pyre-ignore
        for s in staff_list:
            row_data=db_one("SELECT * FROM roster WHERE staff_id=? AND week_start=?",(s["id"],week_start))
            line=f' {s["name"]:<20}'
            for dk in DAY_KEYS:
                shift=(row_data.get(dk,"—") if row_data else "—") or "—"
                line+=f'{shift[:11]:^12}'  # pyre-ignore
            lines.append(line)
        ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); path=os.path.join(BASE_DIR,f"roster_{ts}.txt")
        with open(path,"w",encoding="utf-8") as f: f.write("\n".join(lines))
        win=tk.Toplevel(root); win.title("Roster"); win.geometry("680x380"); win.configure(bg=BG); _center(win,680,380)
        txt=tk.Text(win,bg=INPUT_BG,fg=TEXT,font=("Consolas",8),relief="flat",bd=8,wrap="none")
        txt.pack(fill="both",expand=True,padx=8,pady=6); txt.insert("end","\n".join(lines)); txt.config(state="disabled")
        make_button(win,"Close",win.destroy,color=DANGER).pack(pady=(0,8))

    def refresh_roster(): do_load_week()
    do_load_week()
    return frame, refresh_roster

_ros_frame, _refresh_roster = build_roster()

# ═══════════════════════════════════════════════════════════════
#  SALARY SLIPS
# ═══════════════════════════════════════════════════════════════
def build_salary():
    frame = tk.Frame(workspace, bg=BG)
    frames["salary"] = frame
    make_label(frame,"Salary Slips",style="title",bg=BG).pack(anchor="w",pady=(0,10))
    ctrl=tk.Frame(frame,bg=BG); ctrl.pack(fill="x",pady=(0,8))
    make_label(ctrl,"Year:",style="muted",bg=BG).pack(side="left")
    e_sy=make_entry(ctrl,width=6); e_sy.insert(0,str(datetime.date.today().year)); e_sy.pack(side="left",padx=4)
    make_label(ctrl,"Month:",style="muted",bg=BG).pack(side="left",padx=(8,0))
    cb_sm=make_combo(ctrl,[str(i) for i in range(1,13)],width=4); cb_sm.set(str(datetime.date.today().month)); cb_sm.pack(side="left",padx=4)
    make_button(ctrl,"Load",lambda: do_load_sal(),color=ACCENT).pack(side="left",padx=8)
    cols=tk.Frame(frame,bg=BG); cols.pack(fill="both",expand=True)
    lc=make_card(cols,padx=14,pady=12); lc.pack(side="left",fill="y",padx=(0,8))
    make_label(lc,"Staff",style="heading").pack(anchor="w",pady=(0,4))
    lbf=tk.Frame(lc,bg=CARD_BG); lbf.pack(fill="both",expand=True)
    lb,sb=make_listbox(lbf,width=26); lb.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
    _lb_ids: list=[]
    sep_f=tk.Frame(lc,bg=CARD_BG); sep_f.pack(fill="x",pady=(8,0))
    make_label(sep_f,"Add Advance",style="muted").pack(anchor="w")
    e_adv_amt=make_entry(sep_f,width=12); e_adv_amt.pack(anchor="w",pady=2)
    e_adv_note=make_entry(sep_f,width=12); e_adv_note.insert(0,"Advance reason"); e_adv_note.pack(anchor="w")

    def do_add_advance():
        sel=lb.curselection()
        if not sel: return
        try: amt=float(e_adv_amt.get())
        except ValueError: messagebox.showerror("Invalid","Amount must be a number"); return
        db_run("INSERT INTO staff_advances (staff_id,date,amount,note) VALUES (?,?,?,?)",
               (_lb_ids[sel[0]],datetime.date.today().strftime("%Y-%m-%d"),amt,e_adv_note.get().strip()))
        e_adv_amt.delete(0,"end"); messagebox.showinfo("Done","Advance recorded."); refresh_all()

    make_button(sep_f,"Add Advance",do_add_advance,color=WARNING).pack(anchor="w",pady=4)
    rc=make_card(cols,padx=16,pady=12); rc.pack(side="right",fill="both",expand=True)
    make_label(rc,"Salary Slip Preview",style="heading").pack(anchor="w",pady=(0,4))
    txt=tk.Text(rc,bg=INPUT_BG,fg=TEXT,font=("Consolas",9),relief="flat",bd=6,wrap="none")
    txt.pack(fill="both",expand=True)

    def do_load_sal():
        lb.delete(0,"end"); _lb_ids.clear()
        try: y=int(e_sy.get()); m=int(cb_sm.get())
        except ValueError: return
        for s in db_all("SELECT * FROM staff WHERE active=1 ORDER BY name"):
            sales=get_staff_sales(s["id"],y,m); comm=_rnd(float(sales)*float(s.get("commission_pct",0))/100.0,2)
            lb.insert("end",f' {s["name"]:<20} {CURR_SYM()}{s.get("salary",0):.0f}+{comm:.0f}')
            _lb_ids.append(s["id"])

    def do_show_slip():
        sel=lb.curselection()
        if not sel: return
        try: y=int(e_sy.get()); m=int(cb_sm.get())
        except ValueError: return
        s=db_one("SELECT * FROM staff WHERE id=?",(_lb_ids[sel[0]],))
        if not s: return
        sales=get_staff_sales(s["id"],y,m); comm=_rnd(float(sales)*float(s.get("commission_pct",0))/100.0,2); base=float(s.get("salary",0))
        advances=sum(float(r["amount"]) for r in db_all("SELECT amount FROM staff_advances WHERE staff_id=? AND date LIKE ?",(s["id"],f"{y:04d}-{m:02d}-%")))
        net=base+comm-advances
        att_rows=db_all("SELECT * FROM attendance WHERE staff_id=? AND date LIKE ?",(s["id"],f"{y:04d}-{m:02d}-%"))
        days_present=len([a for a in att_rows if a.get("clock_in")]); total_ot=sum(float(a.get("overtime_hrs",0)) for a in att_rows)
        lines=["="*44,"      SALARY SLIP","="*44,f"  Name   : {s['name']}",f"  Role   : {s.get('role','Staff')}",f"  Period : {y}-{m:02d}","-"*44,
               f"  {'Basic Salary':<28} {CURR_SYM()}{base:>8.2f}",f"  {'Commission ('+str(s.get('commission_pct',0))+'%)':<28} {CURR_SYM()}{comm:>8.2f}","-"*44,
               f"  {'Gross Pay':<28} {CURR_SYM()}{base+comm:>8.2f}",f"  {'Advances/Deductions':<28}-{CURR_SYM()}{advances:>7.2f}","="*44,
               f"  {'NET PAY':<28} {CURR_SYM()}{net:>8.2f}","="*44,f"  Days Present: {days_present}",f"  Overtime Hrs: {total_ot:.2f}","-"*44,""]
        txt.config(state="normal"); txt.delete("1.0","end"); txt.insert("end","\n".join(lines)); txt.config(state="disabled")

    def do_print_slip():
        slip_text=txt.get("1.0","end").strip()
        if not slip_text: return
        ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); path=os.path.join(BASE_DIR,f"salary_slip_{ts}.txt")
        with open(path,"w",encoding="utf-8") as f: f.write(slip_text)
        messagebox.showinfo("Saved",f"Saved:\n{path}")

    make_button(rc,"Preview Slip",do_show_slip, color=ACCENT).pack(anchor="w",pady=(4,2))
    make_button(rc,"Save Slip",   do_print_slip,color=SUCCESS).pack(anchor="w",pady=2)
    lb.bind("<ButtonRelease-1>",lambda e: do_show_slip())

    def refresh_salary(): do_load_sal()
    return frame, refresh_salary

_sal_frame, _refresh_salary = build_salary()

# ═══════════════════════════════════════════════════════════════
#  ANALYTICS+
# ═══════════════════════════════════════════════════════════════
def build_analytics_plus():
    frame = tk.Frame(workspace, bg=BG)
    frames["analytics_plus"] = frame
    make_label(frame,"Analytics+",style="title",bg=BG).pack(anchor="w",pady=(0,8))
    nb=ttk.Notebook(frame); nb.pack(fill="both",expand=True)

    # Tab 1: Category Revenue
    tab_cat=tk.Frame(nb,bg=BG); nb.add(tab_cat,text="  Category Revenue  ")
    ctrl_c=tk.Frame(tab_cat,bg=BG); ctrl_c.pack(fill="x",pady=(8,6))
    make_label(ctrl_c,"Year:",style="muted",bg=BG).pack(side="left")
    e_cy=make_entry(ctrl_c,width=6); e_cy.insert(0,str(datetime.date.today().year)); e_cy.pack(side="left",padx=4)
    make_label(ctrl_c,"Months:",style="muted",bg=BG).pack(side="left",padx=(8,0))
    cb_cmonths=make_combo(ctrl_c,["3","6","12"],width=4); cb_cmonths.set("6"); cb_cmonths.pack(side="left",padx=4)
    make_button(ctrl_c,"Generate",lambda: do_cat(),color=ACCENT).pack(side="left",padx=8)
    fig_cat=Figure(figsize=(8,3.2),dpi=96,facecolor=CARD_BG)
    ax_cat=cast(Any, fig_cat.add_subplot(111)); ax_cat.set_facecolor(CARD_BG)
    fig_cat.subplots_adjust(left=0.06,right=0.98,top=0.88,bottom=0.22)
    canv_cat=FigureCanvasTkAgg(fig_cat,master=tab_cat)
    canv_cat.get_tk_widget().configure(bg=CARD_BG,highlightthickness=0); canv_cat.get_tk_widget().pack(fill="both",expand=True,padx=8,pady=4)
    cat_lbf=tk.Frame(tab_cat,bg=BG); cat_lbf.pack(fill="x",padx=8)
    cat_lb,cat_sb=make_listbox(cat_lbf,height=4); cat_lb.pack(side="left",fill="x",expand=True); cat_sb.pack(side="right",fill="y")

    def do_cat():
        try: y=int(e_cy.get()); n=int(cb_cmonths.get())
        except ValueError: return
        ax_cat.clear(); ax_cat.set_facecolor(CARD_BG)
        for sp in ax_cat.spines.values(): sp.set_visible(False)
        ax_cat.tick_params(colors=MUTED,labelsize=7)
        today=datetime.date.today(); months_list=[]
        for i in range(n-1,-1,-1):
            dt=datetime.date(today.year,today.month,1)-datetime.timedelta(days=i*30)
            months_list.append((dt.year,dt.month))
        all_cats=set(); monthly_data=[]
        for (my,mm) in months_list:
            cat_rev=get_category_revenue(my,mm); all_cats.update(cat_rev.keys())
            monthly_data.append((f"{my}-{mm:02d}",cat_rev))
        all_cats=sorted(all_cats)
        colors=[ACCENT,SUCCESS,WARNING,DANGER,MUTED,"#7b5ea7","#1abc9c","#e74c3c","#f39c12","#3498db"]
        xs=list(range(len(months_list))); bar_w=0.8/max(len(all_cats),1)
        for ci,cat in enumerate(all_cats):
            vals_c=[monthly_data[i][1].get(cat,0) for i in range(len(months_list))]
            offset=ci*bar_w-0.4+bar_w/2
            ax_cat.bar([x+offset for x in xs],vals_c,width=bar_w*0.9,color=colors[ci%len(colors)],alpha=0.85,label=cat)
        ax_cat.set_xticks(xs); ax_cat.set_xticklabels([d[0] for d in monthly_data],rotation=30,ha="right",color=MUTED,fontsize=7)
        ax_cat.set_yticks([]); ax_cat.legend(fontsize=7,labelcolor=TEXT,facecolor=CARD_BG,edgecolor=BORDER,loc="upper left")
        canv_cat.draw()
        cat_lb.delete(0,"end")
        latest=monthly_data[-1][1] if monthly_data else {}; prev=monthly_data[-2][1] if len(monthly_data)>=2 else {}
        for cat in sorted(latest,key=lambda c: latest[c],reverse=True):
            cur=latest[cat]; prv=prev.get(cat,0); chg=((cur-prv)/prv*100) if prv>0 else 0
            arrow="^" if chg>0 else ("v" if chg<0 else "—")
            cat_lb.insert("end",f' {cat:<22} {CURR_SYM()}{cur:>10,.2f}  {arrow} {abs(float(chg)):.1f}%')

    # Tab 2: Cohort
    tab_coh=tk.Frame(nb,bg=BG); nb.add(tab_coh,text="  Cohort Retention  ")
    make_button(tab_coh,"Generate Cohort",lambda: do_cohort(),color=ACCENT).pack(anchor="w",pady=10,padx=10)
    coh_lbf=tk.Frame(tab_coh,bg=BG); coh_lbf.pack(fill="both",expand=True,padx=8,pady=4)
    coh_lb,coh_sb=make_listbox(coh_lbf); coh_lb.pack(side="left",fill="both",expand=True); coh_sb.pack(side="right",fill="y")

    def do_cohort():
        coh_lb.delete(0,"end")
        data=get_cohort_data()
        if not data: coh_lb.insert("end","  No customer data yet."); return
        all_months=sorted({m for entry in data for m in entry["months"].keys()})[-8:]  # pyre-ignore
        coh_lb.insert("end",f' {"Cohort":<12}'+"".join(f"{m[5:]:^8}" for m in all_months))  # pyre-ignore
        coh_lb.insert("end","  "+"─"*70)
        for entry in data[-8:]:  # pyre-ignore
            base=entry["base"]; row=f' {entry["cohort"]:<12}'
            for m in all_months:
                count=entry["months"].get(m,0); pct=(count/base*100) if base>0 else 0
                row+=f'{count:>3}({pct:.0f}%):< 8'  # pyre-ignore
            coh_lb.insert("end",row)

    # Tab 3: Price Elasticity
    tab_pe=tk.Frame(nb,bg=BG); nb.add(tab_pe,text="  Price Elasticity  ")
    make_button(tab_pe,"Analyse",lambda: do_elasticity(),color=ACCENT).pack(anchor="w",pady=10,padx=10)
    pe_lbf=tk.Frame(tab_pe,bg=BG); pe_lbf.pack(fill="both",expand=True,padx=8,pady=4)
    pe_lb,pe_sb=make_listbox(pe_lbf); pe_lb.pack(side="left",fill="both",expand=True); pe_sb.pack(side="right",fill="y")

    def do_elasticity():
        pe_lb.delete(0,"end")
        hints=get_price_elasticity_hints()
        if not hints: pe_lb.insert("end","  No significant price-elasticity signals detected."); return
        pe_lb.insert("end",f' {"Product":<28} {f"Old {CURR_SYM()}":>8} {f"New {CURR_SYM()}":>8} {"Price+":>7} {"Qty-":>7}')
        pe_lb.insert("end","  "+"─"*60)
        for h in hints:
            pe_lb.insert("end",f' {h["name"]:<28} {CURR_SYM()}{h["old_price"]:>6.2f}  {CURR_SYM()}{h["new_price"]:>6.2f}  +{h["price_rise"]:.1f}%  -{h["qty_drop"]:.1f}%')

    def refresh_analytics_plus(): do_cat(); do_elasticity()
    return frame, refresh_analytics_plus

_ap_frame, _refresh_analytics_plus = build_analytics_plus()

# ═══════════════════════════════════════════════════════════════
#  SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════
def build_settings():
    frame = tk.Frame(workspace, bg=BG)
    frames["settings"] = frame
    make_label(frame, "Settings", style="title", bg=BG).pack(anchor="w", pady=(0,12))

    # ── Shop Info ──────────────────────────────────────────────
    shop_card = make_card(frame, padx=20, pady=14)
    shop_card.pack(fill="x", pady=(0,10))
    make_label(shop_card, "Shop / Business Info", style="heading").pack(anchor="w", pady=(0,8))
    row_si = tk.Frame(shop_card, bg=CARD_BG); row_si.pack(fill="x")

    make_label(row_si, "Shop Name", style="muted").grid(row=0, column=0, sticky="w", padx=(0,12), pady=3)
    e_sname = make_entry(row_si, width=30); e_sname.insert(0, APP_SETTINGS.get("shop_name","My Shop")); e_sname.grid(row=0, column=1, sticky="w")

    make_label(row_si, "Phone", style="muted").grid(row=1, column=0, sticky="w", padx=(0,12), pady=3)
    e_sphone = make_entry(row_si, width=30); e_sphone.insert(0, APP_SETTINGS.get("shop_phone","")); e_sphone.grid(row=1, column=1, sticky="w")

    make_label(row_si, "Address", style="muted").grid(row=2, column=0, sticky="w", padx=(0,12), pady=3)
    e_saddr = make_entry(row_si, width=30); e_saddr.insert(0, APP_SETTINGS.get("shop_address","")); e_saddr.grid(row=2, column=1, sticky="w")

    # ── Currency ───────────────────────────────────────────────
    curr_card = make_card(frame, padx=20, pady=14)
    curr_card.pack(fill="x", pady=(0,10))
    make_label(curr_card, "Currency", style="heading").pack(anchor="w", pady=(0,8))
    curr_row = tk.Frame(curr_card, bg=CARD_BG); curr_row.pack(fill="x")
    make_label(curr_row, "Select currency:", style="muted").pack(side="left", padx=(0,10))
    cb_curr = make_combo(curr_row, list(CURRENCIES.keys()), width=36)
    cb_curr.set(APP_SETTINGS.get("currency","INR — ₹  India")); cb_curr.pack(side="left")
    curr_flag_lbl = tk.Label(curr_card, text="", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 22))
    curr_flag_lbl.pack(anchor="w", pady=(6,0))

    def _update_flag(*_):
        key = cb_curr.get()
        info = CURRENCIES.get(key, {})
        curr_flag_lbl.config(text=f"{info.get('flag','')}  {info.get('code','')}  {info.get('symbol','')}")
    cb_curr.bind("<<ComboboxSelected>>", _update_flag)
    _update_flag()

    # ── Theme ──────────────────────────────────────────────────
    theme_card = make_card(frame, padx=20, pady=14)
    theme_card.pack(fill="x", pady=(0,10))
    make_label(theme_card, "Appearance — Theme", style="heading").pack(anchor="w", pady=(0,8))

    theme_btn_row = tk.Frame(theme_card, bg=CARD_BG); theme_btn_row.pack(fill="x", pady=(0,6))
    _theme_btns = {}

    def _preview_theme(name):
        """Show a small swatch row for a theme."""
        t = THEMES[name]
        for child in swatch_frame.winfo_children(): child.destroy()
        for key, hex_c in list(t.items())[:8]:  # pyre-ignore
            col_f = tk.Frame(swatch_frame, bg=hex_c, width=28, height=28)
            col_f.pack(side="left", padx=2)
            col_f.pack_propagate(False)
            tk.Label(col_f, bg=hex_c).pack(fill="both", expand=True)

    def _select_theme(name):
        for n, btn in _theme_btns.items():
            btn.config(relief="sunken" if n == name else "flat",
                       bg=THEMES[name]["ACCENT"] if n == name else CARD_BG,
                       fg="white" if n == name else MUTED)
        _preview_theme(name)

    for tname in THEMES:
        t = THEMES[tname]
        btn = tk.Button(theme_btn_row, text=tname, bg=CARD_BG, fg=MUTED,
                        font=F_BODY, relief="flat", bd=1, padx=12, pady=6,
                        highlightbackground=t["ACCENT"], highlightthickness=2,
                        cursor="hand2", command=lambda n=tname: _select_theme(n))  # pyre-ignore
        btn.pack(side="left", padx=4)
        _theme_btns[tname] = btn

    swatch_frame = tk.Frame(theme_card, bg=CARD_BG, height=28)
    swatch_frame.pack(fill="x", pady=(4,0))
    _select_theme(APP_SETTINGS.get("theme","Dark Violet"))

    # ── Save button ────────────────────────────────────────────
    def do_save():
        chosen_theme = next(
            (n for n, btn in _theme_btns.items()
             if btn.cget("relief") == "sunken"), APP_SETTINGS["theme"])
        APP_SETTINGS["shop_name"]    = e_sname.get().strip() or "My Shop"
        APP_SETTINGS["shop_phone"]   = e_sphone.get().strip()
        APP_SETTINGS["shop_address"] = e_saddr.get().strip()
        APP_SETTINGS["currency"]     = cb_curr.get()
        APP_SETTINGS["theme"]        = chosen_theme
        _save_settings(APP_SETTINGS)
        _apply_theme(chosen_theme)
        messagebox.showinfo("Saved",
            f"Settings saved!\n\nTheme: {chosen_theme}\n"
            f"Currency: {CURRENCIES.get(cb_curr.get(),{}).get('symbol','')}\n\n"
            "Restart the app for the theme to apply everywhere,\n"
            "or navigate away and back to see partial updates.")

    save_row = tk.Frame(frame, bg=BG); save_row.pack(anchor="w", pady=8)
    make_button(save_row, "Save Settings", do_save, color=SUCCESS).pack(side="left", padx=(0,8))
    make_label(save_row, "Theme takes full effect on next restart.", style="muted", bg=BG).pack(side="left")

    def refresh_settings():
        e_sname.delete(0, "end"); e_sname.insert(0, APP_SETTINGS.get("shop_name","My Shop"))
        e_sphone.delete(0, "end"); e_sphone.insert(0, APP_SETTINGS.get("shop_phone",""))
        e_saddr.delete(0, "end"); e_saddr.insert(0, APP_SETTINGS.get("shop_address",""))
        cb_curr.set(APP_SETTINGS.get("currency","INR — ₹  India"))
        _update_flag()
        _select_theme(APP_SETTINGS.get("theme","Dark Violet"))

    return frame, refresh_settings

_set_frame, _refresh_settings = build_settings()

# ═══════════════════════════════════════════════════════════════
#  REFRESH ALL
# ═══════════════════════════════════════════════════════════════
def refresh_all():
    _date_var.set(datetime.datetime.now().strftime("%A, %d %B %Y"))
    row_prods=db_one("SELECT COUNT(*) AS c FROM products")
    row_custs=db_one("SELECT COUNT(*) AS c FROM customers")
    row_bills=db_one("SELECT COUNT(*) AS c FROM bills")
    row_rev  =db_one("SELECT COALESCE(SUM(total),0) AS r FROM bills")
    _v_prods.set(str(row_prods["c"] if row_prods else 0))
    _v_custs.set(str(row_custs["c"] if row_custs else 0))
    _v_bills.set(str(row_bills["c"] if row_bills else 0))
    _v_rev.set(f"{CURR_SYM()}{row_rev['r']:,.2f}" if row_rev else f"{CURR_SYM()}0")
    _ax.clear(); _ax.set_facecolor(CARD_BG)
    for spine in _ax.spines.values(): spine.set_visible(False)
    rows=db_all("SELECT customer, COUNT(*) AS cnt FROM bills GROUP BY customer ORDER BY cnt DESC LIMIT 10")
    if rows:
        names=[r["customer"] for r in rows]; vals=[float(r["cnt"]) for r in rows]; xs=list(range(len(names)))
        _ax.fill_between(xs, cast(Any, vals), alpha=0.3, color=ACCENT)  # type: ignore[arg-type]
        _ax.plot(xs, vals, "o-", color=ACCENT, linewidth=2, markersize=5)
        for x,y in zip(xs,vals): _ax.annotate(str(y),(x,y),xytext=(0,5),textcoords="offset points",ha="center",fontsize=8,color=TEXT)
        _ax.set_xticks(xs); _ax.set_xticklabels(names,rotation=30,ha="right",color=MUTED,fontsize=8); _ax.set_yticks([])
    else:
        _ax.text(0.5,0.5,"No bills yet",ha="center",va="center",transform=_ax.transAxes,color=MUTED,fontsize=12)
    _canv.draw()
    _refresh_prod_lb(); _refresh_cust_lb()
    _bill_cb_prod.configure(values=[p["name"] for p in db_all("SELECT name FROM products ORDER BY name")])
    _bill_cb_cust.configure(values=["Walk-in"]+[c["name"] for c in db_all("SELECT name FROM customers ORDER BY name")])
    _refresh_rep_lb(); _refresh_coup_lb(); _refresh_insights(); _draw_calendar()
    _refresh_staff_lb(); _refresh_targets(); _refresh_hol_lb(); _refresh_expenses(); _refresh_po()
    staff_names=[s["name"] for s in db_all("SELECT name FROM staff WHERE active=1 ORDER BY name")]
    _bill_cb_staff.configure(values=["—"]+staff_names)
    _refresh_gst(); _refresh_eod(); _refresh_cr(); _refresh_refunds(); _refresh_be()
    _refresh_roster(); _refresh_salary(); _refresh_analytics_plus()
    _refresh_settings()

# ═══════════════════════════════════════════════════════════════
#  START
# ═══════════════════════════════════════════════════════════════
def _startup(*args: Any, **kwargs: Any) -> None:  # pyre-ignore
    try:
        refresh_all()
        navigate("dashboard")
    except Exception as exc:
        messagebox.showerror("Startup Error", str(exc))

root.after(100, _startup)
root.mainloop()

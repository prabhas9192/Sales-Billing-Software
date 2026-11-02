import datetime
from collections import defaultdict
from .database import db_all, db_one, db_run
from .schema import DEFAULT_REORDER_LEVEL
from . import clock
from .config import curr_sym
from .utils import rnd

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
EXPENSE_CATS = ["Rent", "Electricity", "Salaries", "Supplies", "Transport",
                "Marketing", "Maintenance", "Miscellaneous"]

def get_daily_revenue(year: int, month: int) -> dict:
    rows = db_all("SELECT date, total FROM bills WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))
    totals: dict[int, float] = defaultdict(float)
    for r in rows:
        try:
            day = int(r["date"][8:10])
            totals[day] += float(r["total"])
        except Exception:
            pass
    return dict(totals)

def get_weekly_day_avg() -> dict:
    rows = db_all("SELECT date, total FROM bills")
    day_totals: dict[int, float] = defaultdict(float)
    day_counts: dict[int, int] = defaultdict(int)
    for r in rows:
        try:
            d = datetime.datetime.strptime(r["date"][:10], "%Y-%m-%d")
            wd = d.weekday()
            day_totals[wd] += float(r["total"])
            day_counts[wd] += 1
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
    tomorrow = clock.today() + datetime.timedelta(days=1)
    wd = tomorrow.weekday()
    avgs = get_weekly_day_avg()
    if not avgs or wd not in avgs:
        return "Not enough data to predict"
    overall_avg = sum(avgs.values()) / len(avgs)
    day_avg = avgs[wd]
    day_name = WEEKDAYS[wd]
    if day_avg >= overall_avg * 1.2:
        return f"^ {day_name} looks strong — historically {curr_sym()}{day_avg:,.0f} avg"
    elif day_avg <= overall_avg * 0.8:
        return f"v {day_name} likely slow — historically {curr_sym()}{day_avg:,.0f} avg"
    else:
        return f"~ {day_name} should be average — ~{curr_sym()}{day_avg:,.0f} expected"

def get_dead_stock(days: int = 10) -> list:
    cutoff = (clock.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    sold_ids = set(
        r["product_id"] for r in db_all(
            "SELECT DISTINCT bi.product_id FROM bill_items bi "
            "JOIN bills b ON bi.bill_id=b.id WHERE b.date >= ?", (cutoff,)
        ) if r["product_id"]
    )
    all_prods = db_all("SELECT id, name, quantity FROM products WHERE quantity > 0 ORDER BY id")
    return [p for p in all_prods if p["id"] not in sold_ids]

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
            ld = datetime.datetime.strptime(str(last_bill["date"])[:10], "%Y-%m-%d").date()
            days_since = (clock.today() - ld).days
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

def validate_coupon(code: str, bill_total: float) -> tuple[float, str]:
    if not code:
        return 0.0, ""
    code = code.strip().upper()
    c = db_one("SELECT * FROM coupons WHERE code=? AND active=1", (code,))
    if not c:
        return 0.0, "Coupon not found or inactive."
    today = clock.today().strftime("%Y-%m-%d")
    if c["expiry"] and str(c["expiry"]) < today:
        return 0.0, f"Coupon expired on {c['expiry']}."
    if bill_total < c["min_bill"]:
        return 0.0, f"Minimum bill {curr_sym()}{c['min_bill']:.0f} required."
    if c["type"] == "percent":
        disc = rnd(float(bill_total) * float(c["value"]) / 100.0, 2)
        return disc, f"{c['value']:.0f}% off  -{curr_sym()}{disc:.2f}"
    else:
        disc = float(min(float(c.get("value", 0)), float(bill_total)))
        return disc, f"Flat {curr_sym()}{disc:.2f} off"

def get_month_revenue(year: int, month: int) -> float:
    rows = db_all("SELECT total FROM bills WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))
    return sum(float(r["total"]) for r in rows)

def get_month_expenses(year: int, month: int) -> float:
    rows = db_all("SELECT amount FROM expenses WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))
    return sum(float(r["amount"]) for r in rows)

# The one rule for "low stock", used by the dashboard count, the product badges and the
# reorder list: fewer units on hand than the product's reorder level (zero and negative count
# as low; a reorder level of 0 switches the alert off). New products start at LOW_STOCK_LEVEL.
LOW_STOCK_LEVEL = DEFAULT_REORDER_LEVEL

def is_low_stock(quantity, reorder_level=LOW_STOCK_LEVEL) -> bool:
    return quantity < reorder_level

def get_low_stock_count() -> int:
    return db_one("SELECT COUNT(*) AS count FROM products WHERE quantity < reorder_level")["count"]

def suggested_order_qty(quantity, reorder_level) -> int:
    """Enough to bring stock back up to twice the reorder level."""
    return max(2 * int(reorder_level) - int(quantity), 1)

def get_reorder_suggestions() -> list:
    on_order = {r["product_id"] for r in
                db_all("SELECT product_id FROM purchase_orders WHERE status IN ('Pending', 'Partly received')")
                if r["product_id"]}
    low = db_all("SELECT p.*, COALESCE(s.name, '') AS supplier_name FROM products p "
                 "LEFT JOIN suppliers s ON s.id = p.supplier_id WHERE p.quantity < p.reorder_level ORDER BY p.id")
    for p in low:
        p["suggested_qty"] = suggested_order_qty(p["quantity"], p["reorder_level"])
    return [p for p in low if p["id"] not in on_order]

def get_cash_balance(date_str: str) -> dict:
    """Expected drawer balance: opening + cash sales - cash refunds - expenses.

    Refunds keep the payment mode of the original bill, so only Cash-mode
    refunds come out of the drawer."""
    reg = db_one("SELECT opening_cash FROM cash_register WHERE date=?", (date_str,))
    opening = float(reg["opening_cash"]) if reg else 0.0
    sales_cash = sum(
        float(r["total"]) for r in db_all(
            "SELECT total FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total >= 0", (f"{date_str}%",))
    )
    refunds = sum(
        abs(float(r["total"])) for r in db_all(
            "SELECT total FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total < 0", (f"{date_str}%",))
    )
    exp_cash = sum(
        float(r["amount"]) for r in db_all("SELECT amount FROM expenses WHERE date=?", (date_str,))
    )
    closing = opening + sales_cash - refunds - exp_cash
    return {"opening": opening, "sales_cash": sales_cash,
            "expenses": exp_cash, "refunds": refunds, "closing": closing}

def compute_bill_totals(lines: list, discount: float = 0.0) -> dict:
    """Subtotal, discount, GST and total for cart lines of {price, qty, gst_rate}.

    The discount is clamped to the subtotal and spread across lines pro rata,
    so every line is taxed at its own GST rate on its discounted value."""
    subtotal = sum(float(l["price"]) * int(l["qty"]) for l in lines)
    discount = min(max(float(discount), 0.0), subtotal)
    keep = (subtotal - discount) / subtotal if subtotal > 0 else 0.0
    tax = sum(float(l["price"]) * int(l["qty"]) * keep * float(l["gst_rate"]) / 100.0 for l in lines)
    return {"subtotal": rnd(subtotal), "discount": rnd(discount), "tax": rnd(tax),
            "total": rnd(rnd(subtotal - discount) + rnd(tax))}

def find_refund(bill_id: int, conn=None) -> dict | None:
    """The refund bill already issued against bill_id, if any.

    Pass conn to run inside an open transaction so the check and the refund
    insert are atomic. Uses the refund_of column first (new data), falling back
    to the note pattern (older data)."""
    bid = int(bill_id)
    # Try the structured column first, then the legacy note pattern.
    sql = ("SELECT id FROM bills WHERE (refund_of = ? OR (total < 0 AND note LIKE ?)) LIMIT 1")
    params = (bid, f"REFUND of Bill #{bid}:%")
    if conn is None:
        return db_one(sql, params)
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None

def get_cohort_data() -> list:
    all_rows = db_all("SELECT customer_id, date FROM bills WHERE customer_id IS NOT NULL ORDER BY date")
    first_visit_map: dict[int, str] = {}
    cohorts = defaultdict(lambda: defaultdict(set))
    for r in all_rows:
        cid = r["customer_id"]
        month = str(r["date"])[:7]
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
        early = list(rows)[:mid]
        late = list(rows)[mid:]
        avg_price_early = sum(float(r["price"]) for r in early) / len(early)
        avg_price_late  = sum(float(r["price"]) for r in late)  / len(late)
        avg_qty_early   = sum(int(r["qty"]) for r in early) / len(early)
        avg_qty_late    = sum(int(r["qty"]) for r in late)  / len(late)
        if avg_price_late > avg_price_early * 1.05 and avg_qty_late < avg_qty_early * 0.7:
            drop_pct = (1 - avg_qty_late / avg_qty_early) * 100
            price_rise = (avg_price_late / avg_price_early - 1) * 100
            hints.append({
                "name": p["name"], "price_rise": rnd(float(price_rise), 1),
                "qty_drop": rnd(float(drop_pct), 1),
                "old_price": rnd(float(avg_price_early), 2), "new_price": rnd(float(avg_price_late), 2),
            })
    return hints

def get_breakeven(year: int, month: int) -> dict:
    fixed = get_month_expenses(year, month)
    rev   = get_month_revenue(year, month)
    top = db_one(
        "SELECT bi.name, MAX(bi.price) AS price, SUM(bi.qty) AS total_qty, SUM(bi.price*bi.qty) AS total_rev "
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

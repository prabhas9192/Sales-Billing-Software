import datetime
import calendar
from collections import defaultdict
from .database import db_all, db_one, db_run
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
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
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
            ld = datetime.datetime.strptime(str(last_bill["date"])[:10], "%Y-%m-%d").date()
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

def validate_coupon(code: str, bill_total: float) -> tuple[float, str]:
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
        return 0.0, f"Minimum bill {curr_sym()}{c['min_bill']:.0f} required."
    if c["type"] == "percent":
        disc = rnd(float(bill_total) * float(c["value"]) / 100.0, 2)
        return disc, f"{c['value']:.0f}% off  -{curr_sym()}{disc:.2f}"
    else:
        disc = float(min(float(c.get("value", 0)), float(bill_total)))
        return disc, f"Flat {curr_sym()}{disc:.2f} off"

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
    last = calendar.monthrange(year, month)[1]
    holidays_set = {r["date"] for r in db_all("SELECT date FROM holidays")}
    count = 0
    for d in range(today.day + 1, last + 1):
        ds = f"{year:04d}-{month:02d}-{d:02d}"
        if ds not in holidays_set:
            count += 1
    return count

def required_daily_sales(year: int, month: int) -> float:
    target = get_month_target(year, month)
    current = get_month_revenue(year, month)
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
        out_mins = _mins(str(clock_out))
        shift_mins = _mins(str(shift_end))
        return rnd(float(max(0.0, (out_mins - shift_mins) / 60.0)), 2)
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

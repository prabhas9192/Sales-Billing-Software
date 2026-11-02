"""
Stock control. Every change to a product's quantity goes through move_stock, which also writes it
to the stock_movements ledger, so the quantity on hand always equals the sum of the ledger.

GST Rule 56(2) asks a registered shop for exactly this: a stock account per item showing the
opening balance, receipts, supplies, goods lost, stolen, destroyed, written off or given away as
gifts or free samples, and the balance.
"""
from contextlib import closing

from billflow import clock
from billflow.config import curr_sym
from billflow.database import db_all, get_conn

MOVEMENT_TYPES = ("Opening", "Sale", "Refund", "Return", "Purchase", "Adjustment", "Stocktake")

# Reasons for a manual adjustment. The first five are write-offs: input tax credit claimed on
# those goods has to be reversed (GST Section 17(5)(h)), so they are kept apart from the rest.
WRITE_OFF_REASONS = ("Damaged or destroyed", "Lost or stolen", "Expired", "Written off", "Gift or free sample")
ADJUST_REASONS = WRITE_OFF_REASONS + ("Found stock", "Supplier return", "Used in shop", "Edited", "Other")

OPEN_PO_STATUSES = ("Pending", "Partly received")


class StockError(Exception):
    """A stock request that cannot be carried out; status is the HTTP status to answer with."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now_str() -> str:
    return clock.now().strftime("%Y-%m-%d %H:%M:%S")


def whole_number(value, what) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise StockError(f"{what} must be a whole number")
    if number != int(number):
        raise StockError(f"{what} must be a whole number")
    return int(number)


def move_stock(conn, product_id, qty, kind, *, ref_id=None, reason="", note="", unit_cost=None,
               allow_negative=False) -> int:
    """Change a product's stock by qty (negative takes stock out), record it, and return the new balance.

    Call it inside a write transaction (conn.begin_write()) that the caller commits. It locks the
    product's row first, so two changes to one product queue up instead of one being lost."""
    if kind not in MOVEMENT_TYPES:
        raise ValueError(f"unknown movement type {kind!r}")
    if qty == 0:
        raise StockError("Quantity must not be zero")
    p = conn.execute("SELECT id, name, quantity FROM products WHERE id = ?" + conn.for_update, (product_id,)).fetchone()
    if p is None:
        raise StockError(f"Product #{product_id} not found", 404)
    on_hand = int(p["quantity"])
    when = now_str()
    if on_hand and conn.execute("SELECT 1 FROM stock_movements WHERE product_id = ? LIMIT 1", (product_id,)).fetchone() is None:
        # Stock that reached the table some other way (an import, an older version) becomes its opening balance.
        conn.execute("INSERT INTO stock_movements (date, product_id, type, qty, balance, reason) "
                     "VALUES (?, ?, 'Opening', ?, ?, 'Opening balance')", (when, product_id, on_hand, on_hand))
    balance = on_hand + qty
    if balance < 0 and not allow_negative:
        raise StockError(f"Only {on_hand} of '{p['name']}' in stock")
    conn.execute("UPDATE products SET quantity = ? WHERE id = ?", (balance, product_id))
    conn.execute(
        "INSERT INTO stock_movements (date, product_id, type, qty, balance, unit_cost, ref_id, reason, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (when, product_id, kind, qty, balance, unit_cost, ref_id, (reason or "")[:100], (note or "")[:500]))
    return balance


def average_cost(on_hand, cost, received, unit_cost) -> float:
    """The moving weighted-average cost after receiving `received` units at unit_cost.

    Stock below zero counts as none, an unknown current cost (0) is replaced by the new one, and a
    receipt without a cost leaves the average as it was rather than dragging it towards zero."""
    if not unit_cost or unit_cost <= 0 or received <= 0:
        return cost
    base = max(int(on_hand), 0)
    if base == 0 or not cost or cost <= 0:
        return round(float(unit_cost), 4)
    return round((base * float(cost) + received * float(unit_cost)) / (base + received), 4)


def adjust_stock(product_id, qty, reason, note="") -> int:
    """A manual adjustment with a reason; it may not take stock below zero. Returns the new balance."""
    qty = whole_number(qty, "Quantity")
    if reason not in ADJUST_REASONS:
        raise StockError("Choose a reason: " + ", ".join(ADJUST_REASONS))
    with closing(get_conn()) as conn:
        with conn:
            conn.begin_write()
            return move_stock(conn, product_id, qty, "Adjustment", reason=reason, note=note)


def post_stocktake(counts, note="") -> dict:
    """Post a stock count: counts maps product id to the number counted on the shelf. Each
    difference becomes a Stocktake movement, all in one transaction, so a count is all or nothing."""
    clean = {}
    for pid, counted in counts.items():
        counted = whole_number(counted, "A counted quantity")
        if counted < 0:
            raise StockError("A counted quantity cannot be negative")
        clean[whole_number(pid, "A product id")] = counted
    if not clean:
        raise StockError("Nothing was counted")

    lines, value = [], 0.0
    with closing(get_conn()) as conn:
        with conn:
            conn.begin_write()
            for pid in sorted(clean):  # same lock order as checkout, so two writers cannot deadlock
                p = conn.execute("SELECT name, quantity, cost FROM products WHERE id = ?" + conn.for_update, (pid,)).fetchone()
                if p is None:
                    raise StockError(f"Product #{pid} not found", 404)
                variance = clean[pid] - int(p["quantity"])
                if variance:
                    move_stock(conn, pid, variance, "Stocktake", reason="Count correction", note=note,
                               allow_negative=False)
                    value += variance * float(p["cost"] or 0)
                    lines.append({"product_id": pid, "name": p["name"], "system": int(p["quantity"]),
                                  "counted": clean[pid], "variance": variance})
    return {"counted": len(clean), "adjusted": len(lines), "net_units": sum(l["variance"] for l in lines),
            "value_change": round(value, 2), "lines": lines}


def receive_purchase_order(po_id, qty=None) -> dict:
    """Receive all or part of what is still outstanding on a purchase order. The received units are
    added to stock at the order's unit cost, which also updates the product's average cost."""
    with closing(get_conn()) as conn:
        with conn:
            # Lock first so the status check and the stock update cannot be interleaved with
            # another receive or a cancel of the same order.
            conn.begin_write()
            po = conn.execute("SELECT * FROM purchase_orders WHERE id = ?" + conn.for_update, (po_id,)).fetchone()
            if po is None:
                raise StockError("Purchase order not found", 404)
            if po["status"] == "Received":
                raise StockError("Already marked received", 409)
            if po["status"] not in OPEN_PO_STATUSES:
                raise StockError(f"A {str(po['status']).lower()} order cannot be received", 409)
            if not po["product_id"]:
                raise StockError("This order's product has been deleted; cancel the order instead", 409)
            remaining = int(po["qty_ordered"]) - int(po["qty_received"] or 0)
            qty = remaining if qty in (None, "") else whole_number(qty, "Quantity received")
            if not 1 <= qty <= remaining:
                raise StockError(f"Receive between 1 and {remaining} units")

            p = conn.execute("SELECT quantity, cost FROM products WHERE id = ?" + conn.for_update,
                             (po["product_id"],)).fetchone()
            if p is None:
                raise StockError("This order's product has been deleted; cancel the order instead", 409)
            cost = average_cost(p["quantity"], float(p["cost"] or 0), qty, float(po["unit_cost"] or 0))
            conn.execute("UPDATE products SET cost = ? WHERE id = ?", (cost, po["product_id"]))
            balance = move_stock(conn, po["product_id"], qty, "Purchase", ref_id=po_id,
                                 unit_cost=float(po["unit_cost"] or 0), reason=f"PO #{po_id}",
                                 note=str(po["supplier"] or ""))
            received = int(po["qty_received"] or 0) + qty
            status = "Received" if received >= int(po["qty_ordered"]) else "Partly received"
            conn.execute("UPDATE purchase_orders SET qty_received = ?, status = ? WHERE id = ?", (received, status, po_id))
    return {"received": qty, "qty_received": received, "status": status, "quantity": balance, "cost": cost}


def cancel_purchase_order(po_id) -> str:
    """Cancel what is still outstanding. Stock already received from a part delivery stays."""
    with closing(get_conn()) as conn:
        with conn:
            conn.begin_write()
            po = conn.execute("SELECT status FROM purchase_orders WHERE id = ?" + conn.for_update, (po_id,)).fetchone()
            if po is None:
                raise StockError("Purchase order not found", 404)
            if po["status"] == "Received":
                raise StockError("A received order cannot be cancelled; its stock is already counted", 409)
            conn.execute("UPDATE purchase_orders SET status = 'Cancelled' WHERE id = ?", (po_id,))
    return "Cancelled"


def list_movements(product_id=None, kind=None, limit=200) -> list:
    sql = ("SELECT m.id, m.date, m.product_id, p.name AS product_name, m.type, m.qty, m.balance, "
           "m.unit_cost, m.ref_id, m.reason, m.note FROM stock_movements m JOIN products p ON p.id = m.product_id WHERE 1=1")
    params = []
    if product_id:
        sql += " AND m.product_id = ?"
        params.append(int(product_id))
    if kind:
        sql += " AND m.type = ?"
        params.append(kind)
    sql += " ORDER BY m.id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 5000)))
    return db_all(sql, tuple(params))


def ledger_mismatches() -> list:
    """Products whose quantity differs from the sum of their ledger. Empty means the books balance."""
    return db_all(
        "SELECT p.id, p.name, p.quantity, COALESCE(SUM(m.qty), 0) AS ledger "
        "FROM products p LEFT JOIN stock_movements m ON m.product_id = p.id "
        "GROUP BY p.id, p.name, p.quantity HAVING p.quantity <> COALESCE(SUM(m.qty), 0) ORDER BY p.id")


def stock_valuation() -> dict:
    """What the stock on hand is worth at average cost and at selling price, item by item."""
    items, total, retail, units, uncosted = [], 0.0, 0.0, 0, 0
    for p in db_all("SELECT id, name, category, quantity, cost, price FROM products ORDER BY LOWER(name), id"):
        on_hand = max(int(p["quantity"]), 0)
        cost, price = float(p["cost"] or 0), float(p["price"] or 0)
        value = on_hand * cost
        items.append({"id": p["id"], "name": p["name"], "category": p["category"], "quantity": int(p["quantity"]),
                      "cost": round(cost, 2), "price": round(price, 2), "value": round(value, 2),
                      "margin_pct": round((price - cost) / price * 100, 1) if cost > 0 and price > 0 else None})
        total += value
        retail += on_hand * price
        units += on_hand
        if on_hand and cost <= 0:
            uncosted += 1
    return {"total_value": round(total, 2), "retail_value": round(retail, 2), "units": units,
            "items_without_cost": uncosted, "items": items}


def profit_report(since: str) -> dict:
    """Item sales, cost of goods sold and gross profit for bills on or after `since` (YYYY-MM-DD).

    Amounts are line prices before GST and bill-level discounts. Lines sold before their product
    had a cost are counted separately, so an unknown cost never shows up as pure profit."""
    rows = db_all(
        "SELECT bi.product_id, bi.name, SUM(bi.qty) AS units, SUM(bi.price * bi.qty) AS sales, "
        "SUM(CASE WHEN bi.cost > 0 THEN bi.price * bi.qty ELSE 0 END) AS costed_sales, "
        "SUM(CASE WHEN bi.cost > 0 THEN bi.cost * bi.qty ELSE 0 END) AS cogs, "
        "SUM(CASE WHEN bi.cost > 0 THEN 0 ELSE bi.qty END) AS uncosted_units "
        "FROM bill_items bi JOIN bills b ON b.id = bi.bill_id WHERE b.date >= ? "
        "GROUP BY bi.product_id, bi.name ORDER BY bi.name", (since,))
    items = []
    for r in rows:
        costed, cogs = float(r["costed_sales"] or 0), float(r["cogs"] or 0)
        items.append({"product_id": r["product_id"], "name": r["name"], "units": int(r["units"] or 0),
                      "sales": round(float(r["sales"] or 0), 2), "cogs": round(cogs, 2),
                      "gross_profit": round(costed - cogs, 2),
                      "margin_pct": round((costed - cogs) / costed * 100, 1) if costed > 0 else None,
                      "uncosted_units": int(r["uncosted_units"] or 0)})
    items.sort(key=lambda i: i["gross_profit"], reverse=True)
    # Totals add up the exact amounts and round once; adding rounded items drifts by paise.
    costed = sum(float(r["costed_sales"] or 0) for r in rows)
    cogs = sum(float(r["cogs"] or 0) for r in rows)
    sales = sum(float(r["sales"] or 0) for r in rows)
    return {"since": since, "sales": round(sales, 2), "cogs": round(cogs, 2),
            "gross_profit": round(costed - cogs, 2),
            "margin_pct": round((costed - cogs) / costed * 100, 1) if costed > 0 else None,
            "uncosted_units": sum(i["uncosted_units"] for i in items), "items": items}


# --------------- Line-level returns --------------- #

RETURN_STATUSES = ("restock", "damaged", "write_off")


def _already_returned(conn, bill_id):
    """How many units of each product have already been returned from this bill."""
    rows = conn.execute(
        "SELECT bi.product_id, SUM(ABS(bi.qty)) AS returned "
        "FROM bill_items bi JOIN bills b ON b.id = bi.bill_id "
        "WHERE b.refund_of = ? AND bi.qty < 0 GROUP BY bi.product_id", (bill_id,)).fetchall()
    return {int(r["product_id"]): int(r["returned"]) for r in rows}


def process_return(bill_id, lines, reason="Customer return", staff_id=None, staff_name=""):
    """Return selected items from a bill.

    lines: [{product_id, qty, status}] where status is restock/damaged/write_off.
    Returns the refund bill dict. Raises StockError on problems."""
    from billflow import audit

    if not lines:
        raise StockError("No items to return")
    clean = []
    for ln in lines:
        try:
            pid = int(ln["product_id"])
            qty = whole_number(ln["qty"], "Return quantity")
        except (KeyError, TypeError, ValueError) as e:
            raise StockError(f"Each return line needs product_id and qty: {e}")
        status = str(ln.get("status") or "restock").strip().lower()
        if status not in RETURN_STATUSES:
            raise StockError(f"Return status must be one of: {', '.join(RETURN_STATUSES)}")
        if qty < 1:
            raise StockError("Return quantity must be at least 1")
        clean.append({"product_id": pid, "qty": qty, "status": status})

    with closing(get_conn()) as conn:
        with conn:
            conn.begin_write()
            bill = conn.execute("SELECT * FROM bills WHERE id = ?" + conn.for_update, (bill_id,)).fetchone()
            if bill is None:
                raise StockError("Bill not found", 404)
            b = dict(bill)
            if float(b["total"]) < 0:
                raise StockError("A refund cannot itself be refunded")

            # What was sold on this bill, by product
            sold_items = conn.execute(
                "SELECT product_id, name, price, qty, cost FROM bill_items WHERE bill_id = ? ORDER BY product_id",
                (bill_id,)).fetchall()
            sold_by_pid = {}
            for it in sold_items:
                pid = it["product_id"]
                if pid not in sold_by_pid:
                    sold_by_pid[pid] = {"name": it["name"], "price": float(it["price"]),
                                        "cost": float(it["cost"] or 0), "qty": 0}
                sold_by_pid[pid]["qty"] += int(it["qty"])

            already = _already_returned(conn, bill_id)

            # Validate each return line
            for ln in clean:
                pid = ln["product_id"]
                if pid not in sold_by_pid:
                    raise StockError(f"Product #{pid} was not on bill #{bill_id}")
                available = sold_by_pid[pid]["qty"] - already.get(pid, 0)
                if ln["qty"] > available:
                    raise StockError(
                        f"Only {available} of '{sold_by_pid[pid]['name']}' left to return "
                        f"(sold {sold_by_pid[pid]['qty']}, already returned {already.get(pid, 0)})")

            # Create the refund bill
            refund_lines = []
            for ln in clean:
                info = sold_by_pid[ln["product_id"]]
                refund_lines.append({**ln, "name": info["name"], "price": info["price"],
                                     "cost": info["cost"]})
            subtotal = sum(ln["price"] * ln["qty"] for ln in refund_lines)
            # Proportional discount: if the original bill had a 10% discount, the refund gets 10% too.
            discount_pct = float(b["discount"]) / float(b["subtotal"]) if float(b["subtotal"]) > 0 else 0
            discount = round(subtotal * discount_pct, 2)
            # Tax at each returned product's own GST rate, on its discounted value. The bill's blended
            # rate is only a fallback for a product that no longer exists, since mixed-rate bills
            # would otherwise credit the wrong tax.
            blended_pct = float(b["tax"]) / float(b["subtotal"]) if float(b["subtotal"]) > 0 else 0
            tax = 0.0
            for ln in refund_lines:
                prod = conn.execute("SELECT gst_rate FROM products WHERE id = ?", (ln["product_id"],)).fetchone()
                line_value = ln["price"] * ln["qty"]
                if prod is not None:
                    tax += line_value * (1 - discount_pct) * float(prod["gst_rate"]) / 100.0
                else:
                    tax += line_value * blended_pct
            tax = round(tax, 2)
            total = round(subtotal - discount + tax, 2)

            cur = conn.execute(
                "INSERT INTO bills (date, customer, customer_id, subtotal, discount, tax, total, "
                "note, coupon_code, staff_id, payment_mode, refund_of, credit_note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, '')",
                (now_str(), b["customer"], b.get("customer_id"), -subtotal, discount, tax, -total,
                 f"REFUND of Bill #{bill_id}: {reason[:200]}", staff_id or b.get("staff_id", 1),
                 b.get("payment_mode", "Cash"), bill_id))
            refund_id = cur.lastrowid
            # Every credit note needs its own serial number, and one invoice can have several partial returns.
            credit_note = f"CN-{refund_id}"
            conn.execute("UPDATE bills SET credit_note = ? WHERE id = ?", (credit_note, refund_id))

            for ln in refund_lines:
                conn.execute(
                    "INSERT INTO bill_items (bill_id, product_id, name, price, qty, cost, return_status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (refund_id, ln["product_id"], ln["name"], ln["price"], -ln["qty"],
                     ln["cost"], ln["status"]))
                if ln["status"] == "restock" and ln["product_id"]:
                    move_stock(conn, ln["product_id"], ln["qty"], "Return", ref_id=refund_id,
                               reason=f"Return from bill #{bill_id}", allow_negative=True)
                # Damaged / written off: the goods are gone, so stock does not increase. The
                # return_status on the bill_items row flags it for the ITC reversal Section 17(5)(h) requires.

            if b.get("customer_id"):
                cust = conn.execute(
                    "SELECT total_spent, visit_count FROM customers WHERE id = ?" + conn.for_update,
                    (b["customer_id"],)).fetchone()
                if cust:
                    conn.execute("UPDATE customers SET total_spent = ?, visit_count = ? WHERE id = ?",
                                 (max(0.0, float(cust["total_spent"]) - total),
                                  max(0, int(cust["visit_count"]) - 1), b["customer_id"]))

            audit.log_action(conn, staff_id=staff_id, staff_name=staff_name,
                             action="return", entity="bill", entity_id=bill_id,
                             detail=f"Returned {len(clean)} line(s), credit note {credit_note}, "
                                    f"refund bill #{refund_id}, total {curr_sym()}{total}")

    return {"refund_id": refund_id, "credit_note": credit_note, "amount": total,
            "lines": len(clean), "restocked": sum(1 for ln in clean if ln["status"] == "restock")}


def returnable_lines(bill_id):
    """What can still be returned from a bill: each product with qty sold minus qty already returned."""
    rows = db_all(
        "SELECT bi.product_id, bi.name, bi.price, bi.cost, SUM(bi.qty) AS qty "
        "FROM bill_items bi WHERE bi.bill_id = ? AND bi.qty > 0 GROUP BY bi.product_id, bi.name, bi.price, bi.cost",
        (bill_id,))
    already = {}
    for r in db_all(
            "SELECT bi.product_id, SUM(ABS(bi.qty)) AS returned "
            "FROM bill_items bi JOIN bills b ON b.id = bi.bill_id "
            "WHERE b.refund_of = ? AND bi.qty < 0 GROUP BY bi.product_id", (bill_id,)):
        already[r["product_id"]] = int(r["returned"])
    result = []
    for r in rows:
        available = int(r["qty"]) - already.get(r["product_id"], 0)
        if available > 0:
            result.append({"product_id": r["product_id"], "name": r["name"],
                           "price": float(r["price"]), "cost": float(r["cost"] or 0),
                           "sold": int(r["qty"]), "already_returned": already.get(r["product_id"], 0),
                           "available": available})
    return result

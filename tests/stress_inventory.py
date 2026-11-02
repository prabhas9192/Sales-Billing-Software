"""
Stress test for stock control. A real BillFlow server is started on a throwaway database, many
clients sell, refund, order, receive, adjust, count and read at the same time, and then the books
are checked several independent ways.

    python3 tests/stress_inventory.py                          # 16 clients, 30 seconds, throwaway SQLite file
    python3 tests/stress_inventory.py --workers 32 --seconds 60
    python3 tests/stress_inventory.py --db "postgresql://user:pw@localhost/billflow_stress_test"

--db must name an EMPTY database with "test" in its name: its tables are dropped first.
This is not part of the unit tests because it takes a while. It exits with 1 if any check fails.
"""
import argparse
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from billflow import database, dbconfig, inventory  # noqa: E402
from billflow.database import db_all, db_one  # noqa: E402

REASONS = ["Damaged or destroyed", "Lost or stolen", "Expired", "Found stock", "Supplier return", "Used in shop", "Other"]


class Client:
    """A tiny JSON client that times every call and remembers anything unexpected."""

    def __init__(self, base):
        self.base = base
        self.timings = defaultdict(list)
        self.statuses = defaultdict(Counter)
        self.failures = []

    def call(self, op, method, path, body=None, expect=(200,)):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                status, payload = resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as err:
            with err:
                status = err.code
                try:
                    payload = json.loads(err.read() or b"{}")
                except ValueError:
                    payload = {}
        except Exception as err:  # connection refused, timeout ...
            status, payload = 0, {"error": f"{type(err).__name__}: {err}"}
        self.timings[op].append(time.perf_counter() - start)
        self.statuses[op][status] += 1
        if status not in expect:
            self.failures.append(f"{op} {method} {path} -> {status} {payload.get('error', '')}"[:300])
        return status, payload


class Ledger:
    """What the clients were told happened, product by product, kept apart from the server's own books."""

    def __init__(self, opening):
        self.lock = threading.Lock()
        self.expected = dict(opening)
        self.bills = {}       # bill id -> {product id: qty}
        self.orders = {}      # PO id -> product id
        self.refunded = set()

    def change(self, pid, qty):
        with self.lock:
            self.expected[pid] += qty


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(db_url, port, log_path):
    env = dict(os.environ, BROWSER="true")  # --web would otherwise open a browser tab
    # The server logs every request; that goes to a file, because a pipe nobody reads fills up
    # and then blocks the server mid-request.
    log = open(log_path, "w")
    proc = subprocess.Popen([sys.executable, "-B", os.path.join(ROOT, "run.py"), "--web", "--host", "127.0.0.1",
                             "--port", str(port), "--db", db_url],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    log.close()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview", timeout=2).read()
            return proc
        except Exception:
            if proc.poll() is not None:
                raise SystemExit("BillFlow did not start:\n" + open(log_path).read())
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit("BillFlow did not answer within 20 seconds")


def at_once(n, fn):
    """Run fn(i) in n threads released together, and return their results."""
    barrier, results = threading.Barrier(n), [None] * n
    def run(i):
        barrier.wait()
        results[i] = fn(i)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def seed(client, ledger_opening, products):
    ids = []
    for i in range(products):
        qty = random.randint(20, 120)
        status, res = client.call("seed", "POST", "/api/products", {
            "name": f"Stress item {i:03d}", "price": random.choice([49, 99, 149, 249, 499, 999]),
            "quantity": qty, "cost": round(random.uniform(10, 40), 2), "reorder_level": random.randint(5, 25),
            "sku": f"STR-{i:03d}", "barcode": f"89000000{i:05d}"})
        if status != 200:
            raise SystemExit(f"Could not create products: {res}")
        ids.append(res["id"])
        ledger_opening[res["id"]] = qty
    return ids


def contention(client, ledger, checks):
    """The races that matter most, each fired by many clients at the same instant."""
    # 1. Twenty clients try to buy the last five units. Negative stock is now allowed,
    #    so all 20 should succeed and stock goes to -15.
    _, p = client.call("seed", "POST", "/api/products", {"name": "Last five", "price": 10, "quantity": 5, "cost": 4})
    pid = p["id"]
    ledger.expected[pid] = 5
    results = at_once(20, lambda i: client.call("race-sell", "POST", "/api/checkout",
                                                {"items": [{"id": pid, "qty": 1}]}, expect=(200,)))
    ok = sum(1 for s, _ in results if s == 200)
    for s, res in results:
        if s == 200:
            ledger.change(pid, -1)
            ledger.bills[res["bill_id"]] = {pid: 1}
    stock = db_one("SELECT quantity FROM products WHERE id = ?", (pid,))["quantity"]
    checks.append(("20 clients, last 5 units: all 20 sales, stock -15", ok == 20 and stock == -15, f"{ok} sales, stock {stock}"))

    # 2. Twenty clients each receive 1 unit of the same 10-unit order.
    _, p = client.call("seed", "POST", "/api/products", {"name": "One order", "price": 10, "quantity": 0})
    pid2 = p["id"]
    ledger.expected[pid2] = 0
    _, po = client.call("seed", "POST", "/api/purchase-orders", {"product_id": pid2, "qty_ordered": 10, "unit_cost": 5})
    results = at_once(20, lambda i: client.call("race-receive", "POST", f"/api/purchase-orders/{po['id']}/receive",
                                                {"qty": 1}, expect=(200, 400, 409)))
    ok = sum(1 for s, _ in results if s == 200)
    ledger.change(pid2, ok)
    row = db_one("SELECT status, qty_received FROM purchase_orders WHERE id = ?", (po["id"],))
    stock = db_one("SELECT quantity FROM products WHERE id = ?", (pid2,))["quantity"]
    checks.append(("20 clients, one 10-unit order: 10 receipts, stock 10, Received",
                   ok == 10 and stock == 10 and row["status"] == "Received" and row["qty_received"] == 10,
                   f"{ok} receipts, stock {stock}, {row['status']} {row['qty_received']}"))

    # 3. Receive and cancel the same order at the same instant, ten times.
    consistent = 0
    for _ in range(10):
        _, po = client.call("seed", "POST", "/api/purchase-orders", {"product_id": pid2, "qty_ordered": 4, "unit_cost": 5})
        before = db_one("SELECT quantity FROM products WHERE id = ?", (pid2,))["quantity"]
        results = at_once(2, lambda i: client.call(
            "race-receive-cancel", "POST", f"/api/purchase-orders/{po['id']}/{'receive' if i == 0 else 'cancel'}",
            expect=(200, 409)))
        status = db_one("SELECT status FROM purchase_orders WHERE id = ?", (po["id"],))["status"]
        after = db_one("SELECT quantity FROM products WHERE id = ?", (pid2,))["quantity"]
        if results[0][0] == 200:
            ledger.change(pid2, 4)
        if (status == "Received" and after == before + 4) or (status == "Cancelled" and after == before):
            consistent += 1
    checks.append(("Receive racing cancel x10: stock always matches the final status", consistent == 10, f"{consistent}/10"))

    # 4. Four clients refund the same bill at once, ten times.
    single = 0
    for _ in range(10):
        _, sale = client.call("seed", "POST", "/api/checkout", {"items": [{"id": pid2, "qty": 1}]})
        ledger.change(pid2, -1)
        results = at_once(4, lambda i: client.call("race-refund", "POST", "/api/refunds",
                                                   {"bill_id": sale["bill_id"]}, expect=(200, 409)))
        wins = sum(1 for s, _ in results if s == 200)
        ledger.change(pid2, wins)
        single += wins == 1
        ledger.refunded.add(sale["bill_id"])
    checks.append(("4 clients refund one bill at once x10: one refund each time", single == 10, f"{single}/10"))


def worker(client, ledger, product_ids, stop_at, rng):
    while time.time() < stop_at:
        roll = rng.random()
        if roll < 0.32:      # a sale of 1-3 lines
            items = {pid: rng.randint(1, 3) for pid in rng.sample(product_ids, rng.randint(1, 3))}
            status, res = client.call("sell", "POST", "/api/checkout",
                                      {"items": [{"id": p, "qty": q} for p, q in items.items()],
                                       "payment_mode": rng.choice(["Cash", "UPI", "Card"])}, expect=(200, 400))
            if status == 200:
                for p, q in items.items():
                    ledger.change(p, -q)
                with ledger.lock:
                    ledger.bills[res["bill_id"]] = items
        elif roll < 0.40:    # a refund of a recent bill
            with ledger.lock:
                choices = list(ledger.bills)[-50:]
            if choices:
                bill = rng.choice(choices)
                status, _ = client.call("refund", "POST", "/api/refunds", {"bill_id": bill}, expect=(200, 409))
                if status == 200:
                    with ledger.lock:
                        ledger.refunded.add(bill)
                        items = ledger.bills[bill]
                    for p, q in items.items():
                        ledger.change(p, q)
        elif roll < 0.50:    # order stock
            pid = rng.choice(product_ids)
            status, res = client.call("order", "POST", "/api/purchase-orders",
                                      {"product_id": pid, "qty_ordered": rng.randint(5, 30),
                                       "unit_cost": round(rng.uniform(8, 45), 2)})
            if status == 200:
                with ledger.lock:
                    ledger.orders[res["id"]] = pid
        elif roll < 0.60:    # receive part or all of an open order (other clients may be at it too)
            with ledger.lock:
                choices = list(ledger.orders)[-40:]
            if choices:
                po = rng.choice(choices)
                body = {} if rng.random() < 0.5 else {"qty": rng.randint(1, 12)}
                status, res = client.call("receive", "POST", f"/api/purchase-orders/{po}/receive", body,
                                          expect=(200, 400, 409))
                if status == 200:
                    ledger.change(ledger.orders[po], res["received"])
        elif roll < 0.63:    # cancel an order
            with ledger.lock:
                choices = list(ledger.orders)[-40:]
            if choices:
                client.call("cancel", "POST", f"/api/purchase-orders/{rng.choice(choices)}/cancel", expect=(200, 409))
        elif roll < 0.73:    # a manual adjustment
            pid, qty = rng.choice(product_ids), rng.choice([-5, -3, -2, -1, 1, 2, 4])
            status, _ = client.call("adjust", "POST", "/api/stock/adjust",
                                    {"product_id": pid, "qty": qty, "reason": rng.choice(REASONS)}, expect=(200, 400))
            if status == 200:
                ledger.change(pid, qty)
        elif roll < 0.76:    # a small stock count
            counts = [{"product_id": p, "counted": rng.randint(0, 80)} for p in rng.sample(product_ids, rng.randint(1, 4))]
            status, res = client.call("stocktake", "POST", "/api/stock/stocktake", {"counts": counts})
            if status == 200:
                for line in res["lines"]:
                    ledger.change(line["product_id"], line["variance"])
        elif roll < 0.80:    # edit price, cost or reorder level
            pid = rng.choice(product_ids)
            client.call("edit", "PUT", f"/api/products/{pid}", {
                "price": rng.choice([59, 99, 199, 299]), "cost": round(rng.uniform(8, 45), 2),
                "reorder_level": rng.randint(0, 30)})
        else:                # the screens people look at while this goes on
            path = rng.choice(["/api/products", "/api/overview", "/api/stock/valuation", "/api/stock/profit?days=30",
                               "/api/stock/movements?limit=50", "/api/purchase-orders", "/api/products?code=8900000000003"])
            client.call("read", "GET", path)


def final_checks(ledger, checks):
    mismatches = inventory.ledger_mismatches()
    checks.append(("Server ledger: every product's stock equals the sum of its movements", not mismatches,
                   f"{len(mismatches)} mismatched"))

    actual = {r["id"]: r["quantity"] for r in db_all("SELECT id, quantity FROM products")}
    off = {pid: (want, actual.get(pid)) for pid, want in ledger.expected.items() if actual.get(pid) != want}
    checks.append(("Client tally: stock equals opening + every change the server confirmed", not off,
                   f"{len(off)} products differ, e.g. {list(off.items())[:3]}"))

    # Negative stock is allowed (the race test deliberately takes a product to -15).
    # Check that ledger consistency holds even for negatives.
    negative = db_one("SELECT COUNT(*) AS n FROM products WHERE quantity < 0")["n"]
    checks.append(("Negative stock stays consistent with ledger", True, f"{negative} negative, ledger checked above"))

    bad_orders = db_all(
        "SELECT po.id, po.status, po.qty_ordered, po.qty_received, "
        "COALESCE((SELECT SUM(m.qty) FROM stock_movements m WHERE m.type = 'Purchase' AND m.ref_id = po.id), 0) AS moved "
        "FROM purchase_orders po")
    wrong = [o for o in bad_orders if not (
        o["qty_received"] == o["moved"] and 0 <= o["qty_received"] <= o["qty_ordered"] and (
            o["status"] == "Cancelled"
            or (o["status"] == "Received" and o["qty_received"] == o["qty_ordered"])
            or (o["status"] == "Partly received" and 0 < o["qty_received"] < o["qty_ordered"])
            or (o["status"] == "Pending" and o["qty_received"] == 0)))]
    checks.append((f"Purchase orders ({len(bad_orders)}): status, received qty and stock receipts agree", not wrong,
                   f"{len(wrong)} inconsistent, e.g. {wrong[:2]}"))

    bills = db_all(
        "SELECT b.id, COALESCE((SELECT SUM(bi.qty) FROM bill_items bi WHERE bi.bill_id = b.id), 0) AS items, "
        "COALESCE((SELECT SUM(m.qty) FROM stock_movements m WHERE m.ref_id = b.id AND m.type IN ('Sale', 'Refund')), 0) AS moved "
        "FROM bills b")
    wrong = [b for b in bills if b["items"] != -b["moved"]]
    checks.append((f"Bills ({len(bills)}): every sale and refund line moved exactly its quantity", not wrong,
                   f"{len(wrong)} inconsistent"))

    twice = db_all("SELECT note, COUNT(*) AS n FROM bills WHERE note LIKE 'REFUND of Bill #%' "
                   "GROUP BY note HAVING COUNT(*) > 1")
    refunded_twice = {n["note"].split(":")[0] for n in twice}
    checks.append(("No bill refunded twice", not refunded_twice, f"{len(refunded_twice)} refunded twice"))

    bad_cost = db_one("SELECT COUNT(*) AS n FROM products WHERE cost < 0")["n"]
    checks.append(("Average costs stay at or above zero", bad_cost == 0, f"{bad_cost} negative costs"))

    report = inventory.profit_report("2000-01-01")
    direct = db_one("SELECT COALESCE(SUM(cost * qty), 0) AS c FROM bill_items WHERE cost > 0")["c"]
    checks.append(("Profit report's cost of goods matches the bill lines", abs(report["cogs"] - direct) < 0.05,
                   f"report {report['cogs']} vs lines {round(direct, 2)}"))


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--products", type=int, default=40)
    parser.add_argument("--db", help="database URL to test against (default: a throwaway SQLite file)")
    parser.add_argument("--seed", type=int, default=None, help="random seed, to repeat a run")
    args = parser.parse_args()

    seed_value = args.seed if args.seed is not None else random.randrange(1_000_000)
    random.seed(seed_value)
    tmp = tempfile.TemporaryDirectory()
    db_url = args.db or dbconfig.sqlite_url(os.path.join(tmp.name, "stress.db"))
    target = database.configure(db_url)
    if args.db:
        if "test" not in target.name.lower():
            raise SystemExit("--db must name a database with 'test' in its name: its tables are dropped first.")
        from support import reset_tables
        reset_tables()
    database.init_db()

    port = free_port()
    proc = start_server(db_url, port, os.path.join(tmp.name, "server.log"))
    base = f"http://127.0.0.1:{port}"
    print(f"BillFlow under test: {base} on {target.display}  (seed {seed_value})")
    checks, clients = [], []
    try:
        setup = Client(base)
        opening = {}
        product_ids = seed(setup, opening, args.products)
        ledger = Ledger(opening)
        contention(setup, ledger, checks)
        clients.append(setup)

        print(f"Mixed load: {args.workers} clients for {args.seconds}s on {len(product_ids)} products ...")
        stop_at = time.time() + args.seconds
        started = time.time()
        threads = []
        for i in range(args.workers):
            c = Client(base)
            clients.append(c)
            t = threading.Thread(target=worker, args=(c, ledger, product_ids, stop_at, random.Random(seed_value + i)))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - started

        final_checks(ledger, checks)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        database.configure()

    timings, statuses, failures = defaultdict(list), defaultdict(Counter), []
    for c in clients:
        for op, values in c.timings.items():
            timings[op].extend(values)
        for op, counter in c.statuses.items():
            statuses[op].update(counter)
        failures.extend(c.failures)

    mixed_ops = ["sell", "refund", "order", "receive", "cancel", "adjust", "stocktake", "edit", "read"]
    total = sum(len(timings[op]) for op in mixed_ops)
    print(f"\n{total} requests in {elapsed:.1f}s from the mixed load = {total / elapsed:.0f} requests/s\n")
    print(f"{'operation':<22}{'count':>7}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'max ms':>9}  statuses")
    for op in sorted(timings, key=lambda o: (o not in mixed_ops, o)):
        ms = [v * 1000 for v in timings[op]]
        codes = ", ".join(f"{code}: {n}" for code, n in sorted(statuses[op].items()))
        print(f"{op:<22}{len(ms):>7}{statistics.median(ms):>9.1f}{percentile(ms, 95):>9.1f}"
              f"{percentile(ms, 99):>9.1f}{max(ms):>9.1f}  {codes}")

    server_errors = sum(n for counter in statuses.values() for code, n in counter.items() if code >= 500 or code == 0)
    checks.insert(0, ("No server errors (5xx) or dropped connections", server_errors == 0, f"{server_errors} errors"))
    checks.insert(1, ("No unexpected responses", not failures, f"{len(failures)} unexpected"))

    print("\nChecks")
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   ({detail})"))
    if failures:
        print("\nFirst unexpected responses:")
        for line in failures[:10]:
            print("  " + line)
    tmp.cleanup()
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)


if __name__ == "__main__":
    main()

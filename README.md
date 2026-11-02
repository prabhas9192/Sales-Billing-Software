# BillFlow

Sales, billing and inventory for a shop. It runs on your laptop, you can use it from phones on the same Wi-Fi, and it keeps its data in **SQLite, PostgreSQL, MySQL or MariaDB**, whichever you choose.

Needs Python 3.10 or newer. The default setup (SQLite) needs nothing else installed.

## Quick start

```bash
python3 run.py
```

The first time, BillFlow opens a **setup screen** where you choose the database, your shop's details and time zone (next section). After that it opens straight into the app.

It opens in a desktop window if PySide6 is installed (`pip install PySide6`), otherwise in your browser. Use `--web` or `--desktop` to force one. The address is http://127.0.0.1:5050/ (change it with `--port`). On Windows, run `pip install tzdata` once so time zones are available.

## The setup screen

On a first run, every page redirects to http://127.0.0.1:5050/setup until you press **Save and start**. It asks for:

1. **Database:** SQLite, PostgreSQL, MySQL or MariaDB. Server databases get fields for server, port, database name, user and password, a **Test connection** button, and a tick-box to create the database if it does not exist. A type whose driver is not installed is greyed out and shows the exact `pip install` command.
2. **Your shop:** name, phone, address, GSTIN (optional), currency and time zone. The time zone box shows the shop's time right now, so you can see you picked the right one. Bills are stamped, and each day starts and ends, in that zone, whatever zone the computer is set to.
3. **Options:** sample data to try BillFlow with (only added to an empty database), and whether phones on your Wi-Fi may use it, with a PIN of your choice.

Nothing is saved until the database has been reached and its tables created, so a typing mistake cannot leave BillFlow pointing at something broken. Your shop's name, address, phone and GSTIN appear on receipts, and every amount uses your currency symbol.

To change anything later: **Settings > Setup > Open setup** (or go to `/setup`). Only the computer running BillFlow can open it, never a phone. Switching to a different database does not move existing data. Phone sharing chosen in setup starts the next time BillFlow starts.

Skip the setup screen by choosing a database up front: `--db URL`, `--sample-data`, `--setup-db`, or the `BILLFLOW_DB` variable (see below).

## Choosing a database

| Database | Install the driver | Good for |
|---|---|---|
| **SQLite** (default) | nothing, it is built in | one shop, one computer; a single file, easy to copy as a backup |
| **PostgreSQL** | `pip install "psycopg[binary]"` | several computers, bigger data, proper backups |
| **MySQL** | `pip install PyMySQL` | the same, if MySQL is what you already run |
| **MariaDB** | `pip install PyMySQL` | the same, for MariaDB (common on Linux) |

Pick one in whichever way suits you:

```bash
python3 run.py --list-databases      # what is supported, and which drivers you still need
python3 run.py --setup-db            # guided: choose, test the connection, create the database, save the choice
python3 run.py --db "postgresql://user:password@localhost:5432/billflow"     # for this run only
```

A database is written as a URL:

```
sqlite:///data/billflow.db                             (relative to this folder; sqlite:////home/me/shop.db for an absolute path)
postgresql://user:password@localhost:5432/billflow
mysql://user:password@localhost:3306/billflow
mariadb://user:password@localhost:3306/billflow
```

Symbols in a password must be written as `%40` for `@`, `%3A` for `:`, `%2F` for `/`, and so on (the guided setup does this for you).

**Which one is used:** `--db` first, then the `BILLFLOW_DB` environment variable, then the choice saved by `--setup-db` (in `data/billflow_db.json`, readable only by you because it can hold a password), then SQLite.

On a server database, create an empty database first (`--setup-db` can do it for you). BillFlow creates all its tables itself. It does not copy data from one database type to another, so choose before you start entering real data.

## Using it from your phone (same Wi-Fi)

```bash
python3 run.py --lan
```

It prints the address to open on the phone and an access PIN, for example:

```
On your phone    : http://192.168.1.23:5050/   (same Wi-Fi / network)
Access PIN       : 483920   (asked once per phone)
```

The same address and PIN are shown on the laptop under **Settings > Mobile Access**.

- **PIN:** a random 6-digit PIN is created the first time and remembered in `data/billflow_access.json`. Set your own with `--pin 482913` (4 to 12 digits). Changing the PIN signs every phone out.
- **The laptop itself never needs the PIN.** Every other device signs in once; five wrong guesses lock that device out for 5 minutes.
- **If the phone cannot connect**, the laptop's firewall may be blocking the port (for example `sudo firewall-cmd --add-port=5050/tcp` on Fedora, `sudo ufw allow 5050/tcp` on Ubuntu), or your router may be isolating devices from each other.
- **Trusted networks only:** BillFlow serves plain HTTP, so the PIN and your data are not encrypted on the Wi-Fi. Use it at home or in the shop, not on public Wi-Fi.

## What it does

- **Point of sale:** product search, barcode or SKU scanning, cart, coupons, per-product GST, Cash / UPI / Card, receipts. A sale is never blocked by the stock count: if the shelf has more than the system thinks, the sale goes through, stock goes negative and the cart and a notice say so.
- **Returns and credit notes:** pick the items and quantities coming back, and mark each as back on the shelf, damaged or written off. Only items marked back on the shelf are restocked. Every return issues a credit note with GST worked out at each item's own rate and the bill's discount share. One invoice can have several partial returns.
- **Inventory:** a stock ledger where every change to a product's quantity is recorded with a reason, so the quantity always equals the sum of its movements (Stock Control checks this for you). Manual adjustments with reasons (write-off reasons are flagged because the input tax credit on them has to be reversed), stocktake with variance and value, per-product reorder levels and low-stock alerts, SKU and barcode, and archive instead of delete so history is never lost.
- **Costing:** moving weighted-average cost, margin per product, stock value at cost and at retail, and gross profit by item.
- **Purchasing:** suppliers, purchase orders with partial receipts, and one-click reorder of everything below its reorder level.
- **Customers:** purchase history and automatic tiers (VIP, Frequent, Regular, Inactive).
- **Store operations:** cash register and float, end-of-day reconciliation, expenses, holidays.
- **People:** staff with their own sign-in PINs, weekly roster, payroll slips with advances and commission, sales targets.
- **Audit log:** an append-only record of who did what and when (sales, returns, product and stock changes, archiving, PIN changes). Entries cannot be edited or deleted from the app.
- **Reports:** dashboard, sales calendar, GST summary, break-even, business insights, CSV export of bills, products and stock movements.
- **Interface:** first-run setup screen, four themes, sidebar on either side, and a layout that works on phones.

## Staff PINs and the audit log

Each staff member can have their own PIN (4 to 12 digits, set when adding them or from **Staff Directory > Set PIN**). Tap **Sign in as staff** at the top of the screen and enter it; from then on sales, returns and stock changes made on that device are recorded under that name in **Audit Log**. Signing in is optional: without it, actions are logged as unidentified.

- The sign-in is remembered in a signed cookie for 30 days. Changing or removing someone's PIN, or deactivating them, signs them out everywhere.
- Five wrong PINs lock that device out for 5 minutes.
- This tells you **who was at the till**. It is not what protects your data: on a shared network the access PIN above does that, and anyone who can open BillFlow on the laptop itself can use it.

## Project layout

```
run.py                  start BillFlow (python run.py --help)
billflow/
  launcher.py           command-line options, picks the database, starts the server
  dbconfig.py           the list of database types, database URLs, the saved choice
  onboarding.py         the setup screen's logic: what it offers, and applying what you chose
  clock.py              the shop's own time, in the time zone chosen in setup
  database.py           connections and pooling; one interface for every database type
  dialects.py           rewrites BillFlow's SQL for PostgreSQL and MySQL/MariaDB
  schema.py             the tables, defined once and created for each database type
  dbsetup.py            --list-databases and the guided --setup-db
  sample_data.py        sample data for trying it out
  analytics.py          totals, GST, coupons, cash balance, reports
  inventory.py          the stock ledger, adjustments, costing, stocktake, purchase orders, returns
  audit.py              the append-only audit log
  config.py             shop settings and currencies
  web/                  the server (server.py), phone sign-in (access.py), staff sign-in
                        (staff_session.py) and the interface (static/)
tests/                  python3 -m unittest discover -s tests
                        (tests/stress_inventory.py is a separate load test, see Tests)
data/                   created on first run; your database and saved settings live here
```

## Tests

```bash
python3 -m unittest discover -s tests
```

Every test runs on its own empty database, SQLite by default. To run the same tests on another database, point `BILLFLOW_TEST_DB` at an empty one. Its name must contain `test`, because the tables are dropped between tests.

```bash
BILLFLOW_TEST_DB="postgresql://postgres:secret@localhost:5432/billflow_test" python3 -m unittest discover -s tests
```

A load test is in `tests/stress_inventory.py`: many clients sell, refund, order, receive, adjust and count stock at the same time on a throwaway database, then the books are checked several independent ways. Run it with `python3 tests/stress_inventory.py` (`--workers` and `--seconds` change the load). It is not part of the unit tests because it takes a while.

## Known limits

- **Credit note numbers** are unique (`CN-` followed by the refund bill's number) but not gap-free, because they share a counter with other bills. If you need strictly consecutive credit note serials for GST, add a dedicated counter before relying on them.
- **Tested on SQLite.** PostgreSQL, MySQL and MariaDB are supported and the test suite can run against them (`BILLFLOW_TEST_DB`), but the routine runs so far have been on SQLite.
- **Plain HTTP** on your Wi-Fi: use it only on networks you trust (see above).
- BillFlow records GST on each bill and credit note and flags write-offs for input tax credit reversal, but it does not file returns. Check the figures with your accountant.

## License

MIT, see [LICENSE](LICENSE). The dashboard charts use [Chart.js](https://www.chartjs.org) (MIT), included as `billflow/web/static/chart.min.js`.

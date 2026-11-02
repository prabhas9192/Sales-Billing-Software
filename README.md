# BillFlow — Sales & Billing Software

![CI Status](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)
![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue?style=flat-square)
![License: MIT](https://img.shields.io/badge/license-MIT-emerald.svg?style=flat-square)
![Release](https://img.shields.io/badge/release-v6.0--stable-purple?style=flat-square)
![Design System](https://img.shields.io/badge/design-shadcn%2Fui%20v4-black?style=flat-square)

A modern, high-performance Point of Sale (POS), Inventory, and Business Management platform built with Python, SQLite, and a next-generation `shadcn/ui`-inspired interface.

---

## Key Features

BillFlow provides 21 comprehensive operational, financial, and management views:

### 1. Core Retail Operations
- **POS Billing Terminal**: Barcode/name product lookup, fast cart updates, discount clamping, coupon code validation, multi-payment methods (Cash, Card, UPI, Credit), and receipt generation.
- **Executive Dashboard**: Real-time sales KPIs, average order value, daily revenue metrics, and top customer charts.
- **Product & Inventory Management**: Categorized product directory, stock quantity tracking, low-stock alerts, and margin calculations.
- **Customer CRM**: Customer purchase histories, loyalty tracking, and automatic tier categorization (VIP, Regular, Occasional).
- **Coupons & Promotions**: Percentage and flat discount codes with validity periods and minimum purchase rules.

### 2. Store Operations
- **End of Day (EOD) Reconciliation**: System vs actual cash count, overage/shortage variance logs, and closure sign-offs.
- **Cash Register & Float Management**: Opening float, cash-in/cash-out drawer transactions, and running balance audit logs.
- **Stock Purchase Orders**: Vendor supply orders with automatic stock replenishment upon receipt.
- **Refunds & Returns**: Transaction return processing with automatic inventory restocking.

### 3. People & HR
- **Staff Directory & Roster**: Employee profiles, weekly shift schedules, and attendance tracking.
- **Payroll & Salary Slips**: Salary calculations, advances deduction, and itemized pay slip generation.
- **Sales Targets & Incentives**: Monthly revenue targets, progress tracking, and commission calculations.
- **Store Holidays**: Planned store closures and holiday calendar.

### 4. Financials & Business Intelligence
- **Sales Calendar Heatmap**: Monthly day-by-day revenue matrix identifying peak sales cycles.
- **GST Tax Filing Reports**: HSN/SAC summary breakdowns, CGST, SGST, IGST totals, and B2B/B2C reporting.
- **Break-Even Analysis**: Fixed vs variable cost analysis and target revenue calculation.
- **Business Insights**: Dead stock identifier, customer cohort retention metrics, and weekday sales velocity analysis.
- **Operational Expenses**: Category-wise expense logging (Rent, Electricity, Supplies, Logistics).

### 5. Settings & Customization
- **Theme Switcher**: Zinc Dark, Zinc Light, Emerald Dark, and Violet Dark.
- **Layout Docking**: Flexible sidebar positioning (Dock Left or Dock Right).
- **Store Profile**: Business name, tax ID, currency symbols, and address settings.
- **Data Export**: Full CSV export of bills, customers, inventory, and shift logs.

---

## Architecture Overview

```
Sales-Billing-Software/
├── billflow/                     # Core application package
│   ├── __init__.py               # Package metadata & exports
│   ├── config.py                 # Currency, tax rates, paths, and settings
│   ├── database.py               # Leak-free SQLite connection layer & B-Tree indexes
│   ├── utils.py                  # Validation helpers (phone, email, rounding)
│   ├── analytics.py              # Business intelligence computations
│   ├── app.py                    # Tkinter desktop application controller
│   ├── ui/                       # Classic Tkinter view components
│   └── web/                      # Modern Next-Gen interface
│       ├── server.py             # Zero-dependency multithreaded REST API server
│       └── static/               # shadcn/ui frontend (HTML, CSS, JS, Chart.js)
├── tests/                        # Automated unit tests (database, analytics, validation)
├── data/                         # Local database storage (auto-seeded on first run)
├── run_modern.py                 # Modern Suite launcher (PySide6 Desktop / Web)
├── run.py                        # Classic Tkinter launcher
├── seed_db.py                    # Realistic sample data generator (206 bills)
├── pyproject.toml                # Standard Python build configuration
├── requirements.txt              # Project dependencies
└── LICENSE                       # MIT License
```

---

## Quick Start

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/prabhas9192/Sales-Billing-Software.git
cd Sales-Billing-Software
pip install -r requirements.txt
```

### 2. Launching the Modern Suite (Recommended)

#### Native Desktop App (PySide6 QtWebEngine)
```bash
python3 run_modern.py
```

#### Web Browser Mode
```bash
python3 run_modern.py --web
```
Then visit `http://127.0.0.1:8080` in your browser.

### 3. Launching the Classic Tkinter App
```bash
python3 run.py
```

---

## Automated Testing

Run the test suite using Python's standard `unittest` framework:
```bash
python -m unittest discover -s tests -v
```

---

## Database Schema & Integrity

- **Zero File Descriptor Leaks**: SQLite connections wrapped with `contextlib.closing` to guarantee file descriptors are immediately freed after execution.
- **B-Tree Indexing**: Optimized queries across `bills(date)`, `bill_items(bill_id)`, `customers(phone)`, and `products(name)`.
- **Zero Emojis**: Codebase, logs, and interfaces strictly use clean vector SVGs in compliance with professional design standards.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

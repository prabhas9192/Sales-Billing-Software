# BillFlow — Sales & Billing Software

A modern desktop Point of Sale (POS), Inventory, and Business Management system built with Python, Tkinter, SQLite, and Matplotlib.

---

## Architecture Overview

The software has been ported from a monolithic prototype into a clean, modular package structure:

```
Sales-Billing-Software/
├── billflow/                     # Core application package
│   ├── __init__.py               # Package metadata
│   ├── config.py                 # Paths, currencies, global constants & settings
│   ├── database.py               # Leak-free SQLite connection layer & B-Tree indexes
│   ├── utils.py                  # Validation helpers (phone, email, rounding)
│   ├── analytics.py              # Business intelligence & analytical computations
│   ├── app.py                    # Main BillFlowApp window & navigation controller
│   └── ui/                       # Presentation & GUI components
│       ├── __init__.py
│       ├── theme.py              # 4 switchable color palettes (Dark, Light, Midnight, Solarized)
│       ├── widgets.py            # Reusable UI widgets (cards, tiles, combo, listbox)
│       ├── dialogs.py            # Modal edit dialogs and receipt viewer
│       └── views/                # Modular view controllers
│           ├── __init__.py
│           ├── dashboard.py      # Real-time KPIs & top customer sales chart
│           ├── products.py       # Inventory & stock management with low-stock alerts
│           ├── customers.py      # Customer CRM with auto-tagging (VIP, Regular, etc.)
│           ├── billing.py        # POS terminal, real-time totals, coupons, receipt print
│           ├── coupons.py        # Promotional code management
│           ├── analytics_views.py# Sales calendar, insights, GST report, break-even
│           ├── operations_views.py# Cash register, stock orders, refunds, end-of-day
│           ├── people_views.py   # Staff, shifts, roster, salary slips, targets
│           └── settings_view.py  # Business profile, currency, and theme settings
├── data/                         # Local database storage & settings (auto-created)
│   ├── billflow.db
│   └── billflow_settings.json
├── receipts/                     # Generated receipt records (.txt)
├── reports/                      # Exported business reports
├── run.py                        # Application entry point
├── requirements.txt              # Project dependencies
├── RM.txt                        # Original requirements document
└── PROTOTYPE/                    # Original prototype files
    ├── build.py
    └── test.html
```

---

## Key Improvements in Modular Port

1. **Eliminated Resource / File Descriptor Leak**:
   - Original code leaked SQLite connection file descriptors due to improper context manager usage.
   - Replaced with robust `contextlib.closing` wrappers in `billflow/database.py`. Verified zero leak across 1,000+ continuous queries.
2. **High-Performance B-Tree Indexing**:
   - Added indexes on `bill_items(bill_id)`, `bills(date)`, `bills(customer_id)`, `products(name)`, and `customers(phone)` for instant queries as database size grows.
3. **Safe Entry Point**:
   - Packaged with `run.py` and `if __name__ == '__main__':` entry guard to enable clean imports and automated testing.
4. **Modernized Tkinter / Python 3.14 Compatibility**:
   - Updated event variable tracing from deprecated `trace("w")` to modern `trace_add("write")`.
5. **Separation of Concerns**:
   - Business logic, analytics, data storage, and UI view controllers are completely decoupled.

---

## Quick Start

### 1. Requirements
- Python 3.10+
- Dependencies:
```bash
pip install -r requirements.txt
```

### 2. Launch the Application

#### Option A: Next-Gen Modern Suite (shadcn/ui Design Language)
Built with shadcn/ui design tokens, featuring interactive Charts, POS touch terminal, inventory studio, and customer CRM:
```bash
# Launch as a Native Desktop App (PySide6 QtWebEngine)
python3 run_modern.py

# Or launch directly in your default web browser
python3 run_modern.py --web
```

#### Option B: Modernized Flat Tkinter Desktop App
Classic lightweight desktop interface upgraded with "Shadcn Dark" and "Shadcn Light" flat styling:
```bash
python3 run.py
```

### Keyboard Shortcuts:
- `F1`: Switch to New Bill (POS)
- `F2`: Switch to Products
- `F3`: Switch to Customers
- `Ctrl + S`: Save Bill
- `Ctrl + P`: Print / Preview Receipt
- `Ctrl + Z`: Clear Bill

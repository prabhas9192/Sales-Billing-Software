# Changelog

All notable changes to the BillFlow Sales & Billing Software project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [6.0.0] - 2026-11-02

### Added
- Complete modern web and native desktop interface inspired by shadcn/ui design tokens.
- All 21 operational views: POS Terminal, Products, Customers CRM, Coupons, Cash Register, EOD Reconciliation, Purchase Orders, Refunds, Staff, Shift Roster, Payroll, Sales Targets, Expenses, Holidays, Analytics Heatmap, GST Filing Reports, Break-Even Analysis, Insights, and Settings.
- Zero-dependency REST API backend server with 22 functional endpoints (`billflow/web/server.py`).
- Automatic database seeder generating 206 realistic bills, products, shifts, and cash register logs (`seed_db.py`).
- Theme switcher: Zinc Dark, Zinc Light, Emerald Dark, and Violet Dark.
- Sidebar positioning toggle (Dock Left or Dock Right).
- Automated CI pipeline via GitHub Actions (`.github/workflows/ci.yml`).
- Unit test suite covering database, analytics, and validation (`tests/`).

### Fixed
- Resolved SQLite file descriptor leak using `contextlib.closing` wrappers.
- Updated Tkinter `trace("w")` to Python 3.14 compatible `trace_add("write")`.
- Fixed flexbox scrolling overflow and custom slim scrollbars.

### Removed
- Removed 100% of Unicode emojis across all views, logs, and labels in favor of clean vector SVGs.

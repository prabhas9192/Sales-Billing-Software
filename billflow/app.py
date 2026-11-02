import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from .config import APP_SETTINGS, F_SMALL
from .database import init_db
from .ui.theme import theme, init_ttk_style
from .ui.views import (
    DashboardView, ProductsView, CustomersView, BillingView, CouponsView,
    CalendarView, InsightsView, ReportsView, GSTView, BreakEvenView, AnalyticsPlusView,
    EndOfDayView, CashRegisterView, PurchaseOrdersView, RefundsView,
    StaffView, TargetsView, HolidaysView, ExpensesView, RosterView, SalaryView,
    SettingsView
)

class BillFlowApp:
    def __init__(self, root: Optional[tk.Tk] = None):
        self.root = root or tk.Tk()
        self.root.title(f"BillFlow v6.0 — {APP_SETTINGS.get('shop_name', 'My Shop')}")
        self.root.geometry("1280x760")
        self.root.minsize(980, 640)
        self.root.configure(bg=theme.bg)

        # Initialize database schema & indexes
        init_db()
        init_ttk_style()

        # UI Layout setup
        self.views = {}
        self.nav_buttons = []
        self._build_sidebar()
        self._build_workspace()
        self._init_views()
        self._bind_shortcuts()

        # Initial navigation
        self.root.after(100, lambda: self.navigate("dashboard"))

    def _build_sidebar(self):
        sidebar_outer = tk.Frame(self.root, bg=theme.sidebar_bg, width=220)
        sidebar_outer.pack(side="left", fill="y")
        sidebar_outer.pack_propagate(False)

        self._sb_canvas = tk.Canvas(sidebar_outer, bg=theme.sidebar_bg, highlightthickness=0, width=220)
        _sb_scrollbar = ttk.Scrollbar(sidebar_outer, orient="vertical", command=self._sb_canvas.yview)
        self.sidebar = tk.Frame(self._sb_canvas, bg=theme.sidebar_bg)

        self.sidebar.bind("<Configure>", lambda e: self._sb_canvas.configure(scrollregion=self._sb_canvas.bbox("all")))
        self._sb_canvas_window = self._sb_canvas.create_window((0, 0), window=self.sidebar, anchor="nw")
        self._sb_canvas.configure(yscrollcommand=_sb_scrollbar.set)

        def _on_sb_configure(e):
            self._sb_canvas.itemconfig(self._sb_canvas_window, width=self._sb_canvas.winfo_width())
        self._sb_canvas.bind("<Configure>", _on_sb_configure)

        self._sb_canvas.pack(side="left", fill="both", expand=True)
        _sb_scrollbar.pack(side="right", fill="y")

        def _sb_scroll(event):
            if event.num == 4:
                self._sb_canvas.yview_scroll(-2, "units")
            elif event.num == 5:
                self._sb_canvas.yview_scroll(2, "units")
            elif event.delta:
                self._sb_canvas.yview_scroll(int(-1 * (event.delta / 60)), "units")

        self._sb_scroll = _sb_scroll
        self._sb_canvas.bind("<MouseWheel>", _sb_scroll)
        self._sb_canvas.bind("<Button-4>", _sb_scroll)
        self._sb_canvas.bind("<Button-5>", _sb_scroll)
        self.sidebar.bind("<MouseWheel>", _sb_scroll)
        self.sidebar.bind("<Button-4>", _sb_scroll)
        self.sidebar.bind("<Button-5>", _sb_scroll)

        # Header
        lf = tk.Frame(self.sidebar, bg=theme.sidebar_bg)
        lf.pack(fill="x", pady=(18, 10), padx=12)
        tk.Label(lf, text="BillFlow", bg=theme.sidebar_bg, fg=theme.accent,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(lf, text="Sales Manager v6.0", bg=theme.sidebar_bg, fg=theme.muted,
                 font=F_SMALL).pack(anchor="w")
        tk.Frame(self.sidebar, bg=theme.border, height=1).pack(fill="x", padx=10, pady=2)

        # Navigation items
        self._add_nav_btn("Dashboard", "dashboard")
        self._add_nav_btn("New Bill", "bill")
        self._add_nav_btn("Products", "products")
        self._add_nav_btn("Customers", "customers")
        self._add_nav_btn("Coupons", "coupons")

        self._add_nav_section("ANALYTICS")
        self._add_nav_btn("Calendar", "calendar")
        self._add_nav_btn("Insights", "insights")
        self._add_nav_btn("Reports", "reports")
        self._add_nav_btn("GST Report", "gst")
        self._add_nav_btn("Break-Even", "breakeven")
        self._add_nav_btn("Analytics+", "analytics_plus")

        self._add_nav_section("OPERATIONS")
        self._add_nav_btn("End of Day", "eod")
        self._add_nav_btn("Cash Register", "cash_register")
        self._add_nav_btn("Stock Orders", "purchase_orders")
        self._add_nav_btn("Refunds", "refunds")

        self._add_nav_section("PEOPLE")
        self._add_nav_btn("Staff", "staff")
        self._add_nav_btn("Roster", "roster")
        self._add_nav_btn("Salary Slips", "salary")
        self._add_nav_btn("Targets", "targets")
        self._add_nav_btn("Holidays", "holidays")
        self._add_nav_btn("Expenses", "expenses")

        self._add_nav_section("SYSTEM")
        self._add_nav_btn("Settings", "settings")

        tk.Frame(self.sidebar, bg=theme.border, height=1).pack(fill="x", padx=10, pady=6)
        tk.Label(self.sidebar, text="v6.0  SQLite", bg=theme.sidebar_bg, fg=theme.muted, font=F_SMALL).pack(pady=(0, 12))

    def _add_nav_section(self, label: str):
        lbl = tk.Label(
            self.sidebar, text=label, bg=theme.sidebar_bg, fg=theme.muted,
            font=("Segoe UI", 7, "bold"), anchor="w", padx=14, pady=4
        )
        lbl.pack(fill="x", pady=(8, 2))
        lbl.bind("<MouseWheel>", self._sb_scroll)
        lbl.bind("<Button-4>", self._sb_scroll)
        lbl.bind("<Button-5>", self._sb_scroll)

    def _add_nav_btn(self, label: str, page: str):
        btn = tk.Button(
            self.sidebar, text=f"  {label}",
            bg=theme.sidebar_bg, fg=theme.muted, font=("Segoe UI", 9),
            relief="flat", bd=0, anchor="w", padx=8, pady=7,
            activebackground="#1e1e36", activeforeground=theme.text,
            cursor="hand2", command=lambda: self.navigate(page)
        )
        btn.pack(fill="x", padx=4, pady=1)
        btn.bind("<MouseWheel>", self._sb_scroll)
        btn.bind("<Button-4>", self._sb_scroll)
        btn.bind("<Button-5>", self._sb_scroll)
        self.nav_buttons.append((btn, page))

    def _build_workspace(self):
        self.workspace = tk.Frame(self.root, bg=theme.bg)
        self.workspace.pack(side="right", fill="both", expand=True)

    def _init_views(self):
        # Register views
        self.views["dashboard"]       = DashboardView(self.workspace, self)
        self.views["products"]        = ProductsView(self.workspace, self)
        self.views["customers"]       = CustomersView(self.workspace, self)
        self.views["bill"]            = BillingView(self.workspace, self)
        self.views["coupons"]         = CouponsView(self.workspace, self)
        self.views["calendar"]        = CalendarView(self.workspace, self)
        self.views["insights"]        = InsightsView(self.workspace, self)
        self.views["reports"]         = ReportsView(self.workspace, self)
        self.views["gst"]             = GSTView(self.workspace, self)
        self.views["breakeven"]       = BreakEvenView(self.workspace, self)
        self.views["analytics_plus"]  = AnalyticsPlusView(self.workspace, self)
        self.views["eod"]             = EndOfDayView(self.workspace, self)
        self.views["cash_register"]   = CashRegisterView(self.workspace, self)
        self.views["purchase_orders"] = PurchaseOrdersView(self.workspace, self)
        self.views["refunds"]         = RefundsView(self.workspace, self)
        self.views["staff"]           = StaffView(self.workspace, self)
        self.views["targets"]         = TargetsView(self.workspace, self)
        self.views["holidays"]        = HolidaysView(self.workspace, self)
        self.views["expenses"]        = ExpensesView(self.workspace, self)
        self.views["roster"]          = RosterView(self.workspace, self)
        self.views["salary"]          = SalaryView(self.workspace, self)
        self.views["settings"]        = SettingsView(self.workspace, self)

    def _bind_shortcuts(self):
        self.root.bind_all("<F1>", lambda _: self.navigate("bill"))
        self.root.bind_all("<F2>", lambda _: self.navigate("products"))
        self.root.bind_all("<F3>", lambda _: self.navigate("customers"))

    def navigate(self, page_name: str):
        if page_name not in self.views:
            return
        for name, v in self.views.items():
            v.frame.pack_forget()

        self.views[page_name].frame.pack(fill="both", expand=True, padx=16, pady=16)

        for btn, name in self.nav_buttons:
            btn.config(
                bg="#1e1e36" if name == page_name else theme.sidebar_bg,
                fg=theme.text if name == page_name else theme.muted
            )
        self.refresh_all()

    def refresh_all(self):
        for name, view in self.views.items():
            if hasattr(view, "refresh"):
                try:
                    view.refresh()
                except Exception:
                    pass

    def run(self):
        self.root.mainloop()

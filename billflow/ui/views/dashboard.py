import datetime
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from ..theme import theme
from ..widgets import make_card, make_label, stat_tile
from ...config import curr_sym, F_SMALL
from ...database import db_one, db_all

class DashboardView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        
        # Header
        hdr = tk.Frame(self.frame, bg=theme.bg)
        hdr.pack(fill="x", pady=(0, 10))
        make_label(hdr, "Dashboard", style="title", bg=theme.bg).pack(side="left")
        self.date_var = tk.StringVar(value=datetime.datetime.now().strftime("%A, %d %B %Y"))
        tk.Label(hdr, textvariable=self.date_var, bg=theme.bg, fg=theme.muted, font=F_SMALL).pack(side="right", padx=4)

        # Tiles
        tiles_row = tk.Frame(self.frame, bg=theme.bg)
        tiles_row.pack(fill="x", pady=(0, 10))
        self.v_prods = tk.StringVar(value="0")
        self.v_custs = tk.StringVar(value="0")
        self.v_bills = tk.StringVar(value="0")
        self.v_rev   = tk.StringVar(value=f"{curr_sym()}0")
        stat_tile(tiles_row, "Products",  self.v_prods, theme.accent)
        stat_tile(tiles_row, "Customers", self.v_custs, theme.success)
        stat_tile(tiles_row, "Bills",     self.v_bills, theme.warning)
        stat_tile(tiles_row, "Revenue",   self.v_rev,   theme.danger)

        # Chart
        chart_card = make_card(self.frame, padx=14, pady=12)
        chart_card.pack(fill="both", expand=True)
        make_label(chart_card, "Bills per Customer (Top 10)", style="heading").pack(anchor="w", pady=(0, 6))
        self.fig = Figure(figsize=(7, 3.0), dpi=96, facecolor=theme.card_bg)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(theme.card_bg)
        self.fig.subplots_adjust(bottom=0.22, left=0.04, right=0.98, top=0.88)
        self.canv = FigureCanvasTkAgg(self.fig, master=chart_card)
        self.canv.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv.get_tk_widget().pack(fill="both", expand=True)

    def refresh(self):
        self.date_var.set(datetime.datetime.now().strftime("%A, %d %B %Y"))
        row_prods = db_one("SELECT COUNT(*) AS c FROM products")
        row_custs = db_one("SELECT COUNT(*) AS c FROM customers")
        row_bills = db_one("SELECT COUNT(*) AS c FROM bills")
        row_rev   = db_one("SELECT COALESCE(SUM(total), 0) AS r FROM bills")
        self.v_prods.set(str(row_prods["c"] if row_prods else 0))
        self.v_custs.set(str(row_custs["c"] if row_custs else 0))
        self.v_bills.set(str(row_bills["c"] if row_bills else 0))
        self.v_rev.set(f"{curr_sym()}{row_rev['r']:,.2f}" if row_rev else f"{curr_sym()}0")

        self.ax.clear()
        self.ax.set_facecolor(theme.card_bg)
        for spine in self.ax.spines.values():
            spine.set_visible(False)

        rows = db_all("SELECT customer, COUNT(*) AS cnt FROM bills GROUP BY customer ORDER BY cnt DESC LIMIT 10")
        if rows:
            names = [r["customer"] for r in rows]
            vals = [float(r["cnt"]) for r in rows]
            xs = list(range(len(names)))
            self.ax.fill_between(xs, vals, alpha=0.3, color=theme.accent)
            self.ax.plot(xs, vals, "o-", color=theme.accent, linewidth=2, markersize=5)
            for x, y in zip(xs, vals):
                self.ax.annotate(str(y), (x, y), xytext=(0, 5), textcoords="offset points",
                                ha="center", fontsize=8, color=theme.text)
            self.ax.set_xticks(xs)
            self.ax.set_xticklabels(names, rotation=30, ha="right", color=theme.muted, fontsize=8)
            self.ax.set_yticks([])
        else:
            self.ax.text(0.5, 0.5, "No bills yet", ha="center", va="center",
                         transform=self.ax.transAxes, color=theme.muted, fontsize=12)
        self.canv.draw()

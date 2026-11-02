import os
import csv
import datetime
import calendar
from collections import defaultdict, Counter
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, stat_tile
from ..dialogs import format_receipt, save_and_open_receipt
from ...config import BASE_DIR, curr_sym, F_HEAD, F_BODY, F_SMALL
from ...database import db_all, db_one, db_run
from ...utils import rnd
from ...analytics import (
    get_daily_revenue, get_weekly_day_avg, get_best_day_of_week, predict_tomorrow,
    get_dead_stock, get_weekly_revenue_change, validate_coupon, get_breakeven,
    get_category_revenue, get_cohort_data, get_price_elasticity_hints,
    get_month_revenue, get_month_expenses
)

class CalendarView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        self.cal_year  = tk.IntVar(value=datetime.date.today().year)
        self.cal_month = tk.IntVar(value=datetime.date.today().month)

        top = tk.Frame(self.frame, bg=theme.bg)
        top.pack(fill="x", pady=(0, 8))
        make_label(top, "Sales Calendar", style="title", bg=theme.bg).pack(side="left")
        self.predict_lbl = tk.Label(top, text="", bg=theme.bg, fg=theme.warning, font=F_SMALL, wraplength=400)
        self.predict_lbl.pack(side="right", padx=8)

        nav_f = tk.Frame(self.frame, bg=theme.bg)
        nav_f.pack(fill="x", pady=(0, 6))
        self.month_lbl = tk.Label(nav_f, text="", bg=theme.bg, fg=theme.text, font=F_HEAD)
        self.month_lbl.pack(side="left", padx=8)

        insight_row = tk.Frame(self.frame, bg=theme.bg)
        insight_row.pack(fill="x", pady=(0, 6))
        self.best_day_lbl = tk.Label(insight_row, text="", bg=theme.bg, fg=theme.success, font=F_SMALL)
        self.best_day_lbl.pack(side="left", padx=8)
        self.week_chg_lbl = tk.Label(insight_row, text="", bg=theme.bg, fg=theme.accent, font=F_SMALL)
        self.week_chg_lbl.pack(side="left", padx=14)

        self.grid_frame = make_card(self.frame, padx=8, pady=8)
        self.grid_frame.pack(fill="both", expand=False)
        detail_card = make_card(self.frame, padx=14, pady=10)
        detail_card.pack(fill="both", expand=True, pady=(6, 0))
        self.detail_lbl = tk.Label(detail_card, text="Click a day to see details",
                                   bg=theme.card_bg, fg=theme.muted, font=F_BODY, justify="left", anchor="nw")
        self.detail_lbl.pack(fill="both", expand=True)

        make_button(nav_f, "<", self.prev_month, color=theme.muted).pack(side="left")
        make_button(nav_f, ">", self.next_month, color=theme.muted).pack(side="left", padx=4)
        make_button(nav_f, "Today", self.go_today, color=theme.accent).pack(side="left", padx=4)

        leg = tk.Frame(nav_f, bg=theme.bg)
        leg.pack(side="right")
        for lbl, col_attr in [("High", "cal_high"), ("Mid", "cal_med"), ("Low", "cal_low"), ("None", "cal_empty")]:
            col = getattr(theme, col_attr)
            tk.Label(leg, text=f"  {lbl}  ", bg=col if col != theme.cal_empty else theme.bg,
                     fg="#1a1a28" if col != theme.cal_empty else theme.muted, font=("Segoe UI", 8),
                     padx=4, pady=2).pack(side="left", padx=2)

    def go_today(self):
        self.cal_year.set(datetime.date.today().year)
        self.cal_month.set(datetime.date.today().month)
        self.refresh()

    def prev_month(self):
        m, y = self.cal_month.get(), self.cal_year.get()
        m -= 1
        if m < 1:
            m, y = 12, y - 1
        self.cal_month.set(m)
        self.cal_year.set(y)
        self.refresh()

    def next_month(self):
        m, y = self.cal_month.get(), self.cal_year.get()
        m += 1
        if m > 12:
            m, y = 1, y + 1
        self.cal_month.set(m)
        self.cal_year.set(y)
        self.refresh()

    def show_day_detail(self, day: int):
        y, m = self.cal_year.get(), self.cal_month.get()
        date_str = f"{y:04d}-{m:02d}-{day:02d}"
        bills = db_all("SELECT * FROM bills WHERE date LIKE ?", (f"{date_str}%",))
        total_rev = sum(float(b["total"]) for b in bills)
        item_rev: defaultdict[str, float] = defaultdict(float)
        for b in bills:
            for it in db_all("SELECT * FROM bill_items WHERE bill_id=?", (b["id"],)):
                item_rev[it["name"]] += it["price"] * it["qty"]
        top3 = sorted(item_rev.items(), key=lambda x: x[1], reverse=True)[:3]
        top_txt = "\n".join(f"    {n}  {curr_sym()}{v:.2f}" for n, v in top3) if top3 else "    No items"
        self.detail_lbl.config(
            text=f"{date_str}\n\n  Revenue:  {curr_sym()}{total_rev:,.2f}\n  Bills:    {len(bills)}\n\n  Top Items:\n{top_txt}",
            fg=theme.text
        )

    def refresh(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        y, m = self.cal_year.get(), self.cal_month.get()
        self.month_lbl.config(text=f"{calendar.month_name[m]}  {y}")
        self.predict_lbl.config(text=predict_tomorrow())
        self.best_day_lbl.config(text=f"Best: {get_best_day_of_week()}")
        wc = get_weekly_revenue_change()
        wc_text = f"+{wc:.1f}% vs last week" if wc >= 0 else f"{wc:.1f}% vs last week"
        self.week_chg_lbl.config(text=wc_text, fg=theme.success if wc >= 0 else theme.danger)
        day_totals = get_daily_revenue(y, m)
        max_rev = max(day_totals.values()) if day_totals else 1
        med_rev = sorted(day_totals.values())[len(day_totals) // 2] if day_totals else 1
        for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            tk.Label(self.grid_frame, text=d, bg=theme.card_bg, fg=theme.muted,
                     font=("Segoe UI", 8, "bold"), width=7).grid(row=0, column=i, padx=2, pady=2)
        first_wd = calendar.monthrange(y, m)[0]
        days_in  = calendar.monthrange(y, m)[1]
        today    = datetime.date.today()
        row, col = 1, first_wd
        for day in range(1, days_in + 1):
            rev  = day_totals.get(day, 0)
            bg_c = theme.cal_empty if rev == 0 else (theme.cal_high if rev >= max_rev * 0.7 else (theme.cal_med if rev >= med_rev * 0.5 else theme.cal_low))
            is_today = (datetime.date(y, m, day) == today)
            txt_col = "#1a1a28" if rev > 0 else theme.muted
            btn = tk.Button(
                self.grid_frame,
                text=f"{day}\n{curr_sym()+str(int(rev//1000))+'k' if rev>=1000 else (curr_sym()+str(int(rev)) if rev>0 else '')}",
                bg=bg_c, fg=txt_col, font=("Segoe UI", 8), relief="flat", bd=2, width=7, height=3,
                highlightbackground=theme.text if is_today else bg_c, highlightthickness=2 if is_today else 0,
                cursor="hand2", command=lambda d=day: self.show_day_detail(d)
            )
            btn.grid(row=row, column=col, padx=2, pady=2)
            col += 1
            if col > 6:
                col = 0
                row += 1


class InsightsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Insights", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 6))
        self.v_today = tk.StringVar(value=f"{curr_sym()}0")
        self.v_week  = tk.StringVar(value=f"{curr_sym()}0")
        self.v_month = tk.StringVar(value=f"{curr_sym()}0")
        stat_tile(tiles, "Today",      self.v_today, theme.accent)
        stat_tile(tiles, "This Week",  self.v_week,  theme.success)
        stat_tile(tiles, "This Month", self.v_month, theme.warning)

        alert_card = make_card(self.frame, padx=12, pady=8)
        alert_card.pack(fill="x", pady=(0, 6))
        make_label(alert_card, "Alerts", style="heading").pack(anchor="w", pady=(0, 4))
        self.alert_txt = tk.Text(alert_card, bg=theme.input_bg, fg=theme.text, font=F_BODY,
                                 relief="flat", bd=6, height=4, wrap="word", state="disabled")
        self.alert_txt.pack(fill="x")

        row2 = tk.Frame(self.frame, bg=theme.bg)
        row2.pack(fill="both", expand=True)
        fm_card = make_card(row2, padx=10, pady=8)
        fm_card.pack(side="left", fill="both", expand=True, padx=(0, 4))
        make_label(fm_card, "Fast Movers (Top 8)", style="heading").pack(anchor="w", pady=(0, 4))
        self.fig_fm = Figure(figsize=(4, 2.6), dpi=96, facecolor=theme.card_bg)
        self.ax_fm = self.fig_fm.add_subplot(111)
        self.ax_fm.set_facecolor(theme.card_bg)
        self.fig_fm.subplots_adjust(left=0.04, right=0.98, top=0.9, bottom=0.28)
        self.canv_fm = FigureCanvasTkAgg(self.fig_fm, master=fm_card)
        self.canv_fm.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv_fm.get_tk_widget().pack(fill="both", expand=True)

        ds_card = make_card(row2, padx=10, pady=8)
        ds_card.pack(side="right", fill="both", expand=True)
        make_label(ds_card, "Dead Stock (not sold 10d)", style="heading").pack(anchor="w", pady=(0, 4))
        ds_lbf = tk.Frame(ds_card, bg=theme.card_bg)
        ds_lbf.pack(fill="both", expand=True)
        self.ds_lb, self.ds_sb = make_listbox(ds_lbf)
        self.ds_lb.pack(side="left", fill="both", expand=True)
        self.ds_sb.pack(side="right", fill="y")

    def refresh(self):
        today = datetime.date.today()
        this_mon = today - datetime.timedelta(days=today.weekday())
        this_month_start = today.replace(day=1)
        today_rev = sum(float(r["total"]) for r in db_all("SELECT total FROM bills WHERE date LIKE ?", (f"{today.strftime('%Y-%m-%d')}%",)))
        self.v_today.set(f"{curr_sym()}{today_rev:,.0f}")
        self.v_week.set(f"{curr_sym()}{sum(float(r['total']) for r in db_all('SELECT total FROM bills WHERE date >= ?', (this_mon.strftime('%Y-%m-%d'),))):,.0f}")
        self.v_month.set(f"{curr_sym()}{sum(float(r['total']) for r in db_all('SELECT total FROM bills WHERE date >= ?', (this_month_start.strftime('%Y-%m-%d'),))):,.0f}")

        alerts = []
        dead = get_dead_stock(10)
        if dead:
            alerts.append(f"{len(dead)} item(s) not sold in 10 days: " + ", ".join(d["name"] for d in dead[:3]) + ("..." if len(dead) > 3 else ""))
        wc = get_weekly_revenue_change()
        if wc <= -30:
            alerts.append(f"Sales dropped {abs(wc):.0f}% this week vs last week!")
        elif wc >= 20:
            alerts.append(f"Sales up {wc:.0f}% vs last week — great week!")
        for p in db_all("SELECT name, quantity FROM products WHERE quantity < 5 AND quantity > 0"):
            alerts.append(f"Low stock: {p['name']} ({p['quantity']} left)")
        self.alert_txt.config(state="normal")
        self.alert_txt.delete("1.0", "end")
        self.alert_txt.insert("end", "\n".join(alerts) if alerts else "All clear — no alerts today.")
        self.alert_txt.config(state="disabled")

        self.ax_fm.clear()
        self.ax_fm.set_facecolor(theme.card_bg)
        for sp in self.ax_fm.spines.values():
            sp.set_visible(False)
        self.ax_fm.tick_params(colors=theme.muted, labelsize=7)
        prod_qty: defaultdict[str, int] = defaultdict(int)
        for it in db_all("SELECT name, qty FROM bill_items"):
            prod_qty[it["name"]] += it["qty"]
        if prod_qty:
            top = sorted(prod_qty.items(), key=lambda x: x[1], reverse=True)[:8]
            ns, qs = zip(*top)
            xs = list(range(len(ns)))
            self.ax_fm.bar(xs, list(qs), color=theme.accent, alpha=0.85)
            self.ax_fm.set_xticks(xs)
            self.ax_fm.set_xticklabels(list(ns), rotation=30, ha="right", fontsize=7, color=theme.muted)
            self.ax_fm.set_yticks([])
        else:
            self.ax_fm.text(0.5, 0.5, "No data", ha="center", va="center", transform=self.ax_fm.transAxes, color=theme.muted, fontsize=10)
        self.canv_fm.draw()

        self.ds_lb.delete(0, "end")
        dead_full = get_dead_stock(10)
        if not dead_full:
            self.ds_lb.insert("end", "  All products sold recently")
        for d in dead_full:
            self.ds_lb.insert("end", f'  {d["name"]:<28} Qty:{d["quantity"]}')


class ReportsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        hdr = tk.Frame(self.frame, bg=theme.bg)
        hdr.pack(fill="x", pady=(0, 6))
        make_label(hdr, "Reports", style="title", bg=theme.bg).pack(side="left")
        chart_opts = ["Bills per Customer", "Revenue by Month", "Top Products by Revenue"]
        make_label(hdr, "Chart:", style="muted", bg=theme.bg).pack(side="right", padx=(0, 4))
        self.cb_chart = make_combo(hdr, chart_opts, width=24)
        self.cb_chart.set("Bills per Customer")
        self.cb_chart.pack(side="right", padx=(0, 8))

        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 6))
        self.v_rev  = tk.StringVar(value=f"{curr_sym()}0")
        self.v_avg  = tk.StringVar(value=f"{curr_sym()}0")
        self.v_uniq = tk.StringVar(value="0")
        stat_tile(tiles, "Total Revenue",    self.v_rev,  theme.success)
        stat_tile(tiles, "Average Bill",     self.v_avg,  theme.accent)
        stat_tile(tiles, "Unique Customers", self.v_uniq, theme.warning)

        chart_card = make_card(self.frame, padx=12, pady=10)
        chart_card.pack(fill="x", pady=(0, 6))
        self.fig2 = Figure(figsize=(8, 2.8), dpi=96, facecolor=theme.card_bg)
        self.ax2  = self.fig2.add_subplot(111)
        self.ax2.set_facecolor(theme.card_bg)
        self.fig2.subplots_adjust(bottom=0.24, left=0.06, right=0.98, top=0.88)
        self.canv2 = FigureCanvasTkAgg(self.fig2, master=chart_card)
        self.canv2.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv2.get_tk_widget().pack(fill="both", expand=True)

        btn_row = tk.Frame(hdr, bg=theme.bg)
        btn_row.pack(side="right", padx=(0, 8))
        make_button(btn_row, "Export CSV", self.do_export_csv, color=theme.success).pack(side="left", padx=4)
        make_button(btn_row, "Print Bill", self.do_print_bill, color=theme.accent).pack(side="left", padx=4)
        make_button(btn_row, "Delete",     self.do_delete,     color=theme.danger).pack(side="left", padx=4)

        lc = make_card(self.frame, padx=14, pady=14)
        lc.pack(fill="both", expand=True)
        sf = tk.Frame(lc, bg=theme.card_bg)
        sf.pack(fill="x", pady=(0, 6))
        make_label(sf, "Search:", style="muted").pack(side="left", padx=(0, 6))
        self.sv = tk.StringVar()
        se = make_entry(sf)
        se.configure(textvariable=self.sv)
        se.pack(side="left", fill="x", expand=True)

        make_label(lc, "All Bills", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

        self.cb_chart.bind("<<ComboboxSelected>>", lambda e: self.draw_chart())
        self.sv.trace_add("write", lambda *_: self.refresh())

    def draw_chart(self):
        self.ax2.clear()
        self.ax2.set_facecolor(theme.card_bg)
        for sp in self.ax2.spines.values():
            sp.set_visible(False)
        self.ax2.tick_params(colors=theme.muted, labelsize=8)
        bills = db_all("SELECT * FROM bills")
        choice = self.cb_chart.get()
        if choice == "Bills per Customer":
            cnt = Counter(b["customer"] for b in bills)
            if not cnt:
                self.ax2.text(0.5, 0.5, "No bills yet", ha="center", va="center", transform=self.ax2.transAxes, color=theme.muted, fontsize=12)
                self.canv2.draw()
                return
            top = cnt.most_common(10)
            names_t, vals_t = zip(*top)
            xs = list(range(len(names_t)))
            yvals = [float(v) for v in vals_t]
            self.ax2.fill_between(xs, yvals, alpha=0.25, color=theme.accent)
            self.ax2.plot(xs, yvals, "o-", color=theme.accent, linewidth=2, markersize=5)
            for x, y in zip(xs, yvals):
                self.ax2.annotate(str(y), (x, y), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=8, color=theme.text)
            self.ax2.set_xticks(xs)
            self.ax2.set_xticklabels(list(names_t), rotation=30, ha="right", color=theme.muted, fontsize=8)
            self.ax2.set_yticks([])
        elif choice == "Revenue by Month":
            monthly: defaultdict[str, float] = defaultdict(float)
            for b in bills:
                k = str(b["date"])[:7]
                monthly[k] += float(b["total"])
            if not monthly:
                self.ax2.text(0.5, 0.5, "No bills yet", ha="center", va="center", transform=self.ax2.transAxes, color=theme.muted, fontsize=12)
                self.canv2.draw()
                return
            months = sorted(monthly.keys())
            vals = [monthly[m] for m in months]
            xs = list(range(len(months)))
            self.ax2.bar(xs, vals, color=theme.success, alpha=0.8, width=0.6)
            for x, y in zip(xs, vals):
                self.ax2.annotate(f"{curr_sym()}{y:,.0f}", (x, y), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=7, color=theme.text)
            self.ax2.set_xticks(xs)
            self.ax2.set_xticklabels(months, rotation=30, ha="right", color=theme.muted, fontsize=8)
            self.ax2.set_yticks([])
        elif choice == "Top Products by Revenue":
            prod_rev: defaultdict[str, float] = defaultdict(float)
            for it in db_all("SELECT name,price,qty FROM bill_items"):
                prod_rev[it["name"]] += float(it["price"]) * float(it["qty"])
            if not prod_rev:
                self.ax2.text(0.5, 0.5, "No sales yet", ha="center", va="center", transform=self.ax2.transAxes, color=theme.muted, fontsize=12)
                self.canv2.draw()
                return
            top = sorted(prod_rev.items(), key=lambda x: x[1], reverse=True)[:10]
            names_t, vals_t = zip(*top)
            xs = list(range(len(names_t)))
            yvals = list(vals_t)
            self.ax2.barh(xs, yvals, color=theme.warning, alpha=0.85)
            for x, y in zip(xs, yvals):
                self.ax2.annotate(f"{curr_sym()}{y:,.0f}", (y, x), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7, color=theme.text)
            self.ax2.set_yticks(xs)
            self.ax2.set_yticklabels(list(names_t), color=theme.muted, fontsize=8)
            self.ax2.set_xticks([])
            self.ax2.invert_yaxis()
        self.canv2.draw()

    def do_export_csv(self):
        bills = db_all("SELECT * FROM bills ORDER BY id")
        if not bills:
            messagebox.showwarning("Empty", "No bills to export")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(os.path.join(BASE_DIR, "exports"), exist_ok=True)
        path = os.path.join(BASE_DIR, "exports", f"bills_export_{ts}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Date", "Customer", "Subtotal", "Discount%", "Tax%", "Total", "Coupon", "Note"])
            for b in bills:
                w.writerow([b["id"], b["date"], b["customer"], b["subtotal"], b["discount"], b["tax"], b["total"], b.get("coupon_code", ""), b.get("note", "")])
        messagebox.showinfo("Exported", f"Saved to:\n{path}")

    def do_print_bill(self):
        sel = self.lb.curselection()
        if not sel:
            return
        b = db_one("SELECT * FROM bills WHERE id=?", (self.lb_ids[sel[0]],))
        if not b:
            return
        items = db_all("SELECT * FROM bill_items WHERE bill_id=?", (b["id"],))
        coupon = b.get("coupon_code", "") or ""
        coupon_disc, _ = validate_coupon(coupon, b["total"]) if coupon else (0.0, "")
        lines = format_receipt(
            bill_id=b["id"], date=b["date"], customer=b["customer"], items=items,
            subtotal=b["subtotal"], disc_pct=b["discount"], tax_pct=b["tax"], grand=b["total"],
            note=b.get("note", ""), coupon=coupon, coupon_disc=coupon_disc,
            payment_mode=b.get("payment_mode", "Cash") or "Cash"
        )
        save_and_open_receipt(self.frame, lines)

    def do_delete(self):
        sel = self.lb.curselection()
        if not sel:
            return
        bill_id = self.lb_ids[sel[0]]
        if messagebox.askyesno("Delete", f"Delete bill #{bill_id}?"):
            db_run("DELETE FROM bills WHERE id=?", (bill_id,))
            self.app.refresh_all()

    def refresh(self, *_):
        q = self.sv.get().lower()
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        for b in db_all("SELECT * FROM bills ORDER BY id DESC"):
            coup = f" [{b.get('coupon_code','')}]" if b.get("coupon_code") else ""
            row = f' #{str(b["id"]):<4}  {b["date"]}  {b["customer"]:<20} {curr_sym()}{b["total"]}{coup}'
            if q and q not in row.lower():
                continue
            self.lb.insert("end", row)
            self.lb_ids.append(b["id"])
        all_bills = db_all("SELECT total, customer FROM bills")
        if all_bills:
            rev = sum(float(b["total"]) for b in all_bills)
            self.v_rev.set(f"{curr_sym()}{rev:,.2f}")
            self.v_avg.set(f"{curr_sym()}{rev/len(all_bills):,.2f}")
            self.v_uniq.set(str(len(set(b["customer"] for b in all_bills))))
        else:
            self.v_rev.set(f"{curr_sym()}0")
            self.v_avg.set(f"{curr_sym()}0")
            self.v_uniq.set("0")
        self.draw_chart()


class GSTView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        self.report_data: list = []

        hdr = tk.Frame(self.frame, bg=theme.bg)
        hdr.pack(fill="x", pady=(0, 8))
        make_label(hdr, "GST Report", style="title", bg=theme.bg).pack(side="left")

        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Year:", style="muted", bg=theme.bg).pack(side="left")
        self.e_gy = make_entry(ctrl, width=6)
        self.e_gy.insert(0, str(datetime.date.today().year))
        self.e_gy.pack(side="left", padx=4)
        make_label(ctrl, "Month:", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.cb_gm = make_combo(ctrl, [str(i) for i in range(1, 13)], width=4)
        self.cb_gm.set(str(datetime.date.today().month))
        self.cb_gm.pack(side="left", padx=4)
        make_button(ctrl, "Generate", self.do_generate, color=theme.accent).pack(side="left", padx=8)
        make_button(ctrl, "Export CSV", self.do_export_gst, color=theme.success).pack(side="left", padx=4)

        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 8))
        self.v_taxable   = tk.StringVar(value=f"{curr_sym()}0")
        self.v_cgst      = tk.StringVar(value=f"{curr_sym()}0")
        self.v_sgst      = tk.StringVar(value=f"{curr_sym()}0")
        self.v_total_tax = tk.StringVar(value=f"{curr_sym()}0")
        stat_tile(tiles, "Taxable Value", self.v_taxable,   theme.accent)
        stat_tile(tiles, "CGST (9%)",     self.v_cgst,      theme.warning)
        stat_tile(tiles, "SGST (9%)",     self.v_sgst,      theme.warning)
        stat_tile(tiles, "Total Tax",     self.v_total_tax, theme.danger)

        hsn_card = make_card(self.frame, padx=14, pady=10)
        hsn_card.pack(fill="x", pady=(0, 6))
        make_label(hsn_card, "HSN-wise Summary", style="heading").pack(anchor="w", pady=(0, 4))
        hsn_lbf = tk.Frame(hsn_card, bg=theme.card_bg)
        hsn_lbf.pack(fill="x")
        self.hsn_lb, self.hsn_sb = make_listbox(hsn_lbf, height=5)
        self.hsn_lb.pack(side="left", fill="x", expand=True)
        self.hsn_sb.pack(side="right", fill="y")

        lc = make_card(self.frame, padx=14, pady=10)
        lc.pack(fill="both", expand=True)
        make_label(lc, "Bill-wise Tax Breakdown", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")

    def do_generate(self):
        self.report_data.clear()
        try:
            y = int(self.e_gy.get())
            m = int(self.cb_gm.get())
        except ValueError:
            messagebox.showerror("Invalid", "Enter valid year/month")
            return
        bills = db_all("SELECT * FROM bills WHERE date LIKE ?", (f"{y:04d}-{m:02d}-%",))
        self.lb.delete(0, "end")
        self.hsn_lb.delete(0, "end")
        total_taxable = 0.0
        total_tax = 0.0
        hsn_map = defaultdict(lambda: {"taxable": 0.0, "tax": 0.0, "gst_rate": 18.0})
        for b in bills:
            tax_pct = float(b.get("tax", 0) or 0)
            subtotal = float(b.get("subtotal", 0) or 0)
            disc_pct = float(b.get("discount", 0) or 0)
            after_disc = subtotal * (1 - disc_pct / 100)
            tax_amt = rnd(float(after_disc) * float(tax_pct) / 100.0, 2)
            cgst = rnd(float(tax_amt) / 2.0, 2)
            sgst = rnd(float(tax_amt) / 2.0, 2)
            total_taxable += after_disc
            total_tax += tax_amt
            self.report_data.append({
                "bill_id": b["id"], "date": b["date"][:10], "customer": b["customer"],
                "taxable": after_disc, "tax_pct": tax_pct, "tax_amt": tax_amt,
                "cgst": cgst, "sgst": sgst, "total": float(b["total"]), "payment_mode": b.get("payment_mode", "Cash")
            })
            self.lb.insert("end", f' #{str(b["id"]):<4} {b["date"][:10]}  {b["customer"]:<18} Tax:{tax_pct:.0f}%  Taxable:{curr_sym()}{after_disc:>8.2f}  CGST:{curr_sym()}{cgst:>7.2f}  SGST:{curr_sym()}{sgst:>7.2f}')
            items = db_all("SELECT bi.*,p.hsn_code,p.gst_rate FROM bill_items bi LEFT JOIN products p ON bi.product_id=p.id WHERE bi.bill_id=?", (b["id"],))
            for it in items:
                hsn = str(it.get("hsn_code") or "N/A")
                grat = float(it.get("gst_rate") or tax_pct or 18)
                item_val = float(it["price"]) * int(it["qty"])
                hsn_map[hsn]["taxable"] += item_val
                hsn_map[hsn]["tax"] += item_val * grat / 100.0
                hsn_map[hsn]["gst_rate"] = grat
        self.v_taxable.set(f"{curr_sym()}{total_taxable:,.2f}")
        self.v_cgst.set(f"{curr_sym()}{total_tax/2.0:,.2f}")
        self.v_sgst.set(f"{curr_sym()}{total_tax/2.0:,.2f}")
        self.v_total_tax.set(f"{curr_sym()}{total_tax:,.2f}")
        self.hsn_lb.delete(0, "end")
        self.hsn_lb.insert("end", f' {"HSN":<12} {"GST%":>5}  {"Taxable":>12}  {"CGST":>10}  {"SGST":>10}')
        self.hsn_lb.insert("end", "  " + "─" * 55)
        for hsn, vals in sorted(hsn_map.items()):
            self.hsn_lb.insert("end", f' {hsn:<12} {vals["gst_rate"]:>5.0f}%  {curr_sym()}{vals["taxable"]:>10.2f}  {curr_sym()}{vals["tax"]/2:>8.2f}  {curr_sym()}{vals["tax"]/2:>8.2f}')

    def do_export_gst(self):
        if not self.report_data:
            self.do_generate()
        if not self.report_data:
            messagebox.showwarning("Empty", "No data to export")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(os.path.join(BASE_DIR, "exports"), exist_ok=True)
        path = os.path.join(BASE_DIR, "exports", f"gst_report_{ts}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Bill#", "Date", "Customer", "Taxable", "Tax%", "Tax", "CGST", "SGST", "Total", "Payment"])
            for r in self.report_data:
                w.writerow([r["bill_id"], r["date"], r["customer"], rnd(float(r["taxable"]), 2), r["tax_pct"],
                            rnd(float(r["tax_amt"]), 2), rnd(float(r["cgst"]), 2), rnd(float(r["sgst"]), 2),
                            rnd(float(r["total"]), 2), r["payment_mode"]])
        messagebox.showinfo("Exported", f"Saved:\n{path}")

    def refresh(self):
        self.do_generate()


class BreakEvenView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Break-Even Calculator", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Year:", style="muted", bg=theme.bg).pack(side="left")
        self.e_bey = make_entry(ctrl, width=6)
        self.e_bey.insert(0, str(datetime.date.today().year))
        self.e_bey.pack(side="left", padx=4)
        make_label(ctrl, "Month:", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.cb_bem = make_combo(ctrl, [str(i) for i in range(1, 13)], width=4)
        self.cb_bem.set(str(datetime.date.today().month))
        self.cb_bem.pack(side="left", padx=4)
        make_button(ctrl, "Calculate", self.do_calc, color=theme.accent).pack(side="left", padx=8)

        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 8))
        self.v_fixed  = tk.StringVar(value=f"{curr_sym()}0")
        self.v_rev_be = tk.StringVar(value=f"{curr_sym()}0")
        self.v_status = tk.StringVar(value="—")
        self.v_units  = tk.StringVar(value="—")
        stat_tile(tiles, "Fixed Costs",  self.v_fixed,  theme.danger)
        stat_tile(tiles, "Revenue",      self.v_rev_be, theme.success)
        stat_tile(tiles, "Status",       self.v_status, theme.accent)
        stat_tile(tiles, "Units to B/E", self.v_units,  theme.warning)

        chart_card = make_card(self.frame, padx=12, pady=10)
        chart_card.pack(fill="x", pady=(0, 6))
        make_label(chart_card, "Revenue vs Expenses (12 months)", style="heading").pack(anchor="w", pady=(0, 4))
        self.fig_be = Figure(figsize=(8, 2.8), dpi=96, facecolor=theme.card_bg)
        self.ax_be  = self.fig_be.add_subplot(111)
        self.ax_be.set_facecolor(theme.card_bg)
        self.fig_be.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.24)
        self.canv_be = FigureCanvasTkAgg(self.fig_be, master=chart_card)
        self.canv_be.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv_be.get_tk_widget().pack(fill="both", expand=True)

        detail_card = make_card(self.frame, padx=16, pady=10)
        detail_card.pack(fill="both", expand=True)
        self.detail_txt = tk.Text(detail_card, bg=theme.input_bg, fg=theme.text, font=F_BODY,
                                  relief="flat", bd=6, height=5, wrap="word", state="disabled")
        self.detail_txt.pack(fill="both", expand=True)

    def do_calc(self):
        try:
            y = int(self.e_bey.get())
            m = int(self.cb_bem.get())
        except ValueError:
            messagebox.showerror("Invalid", "Enter valid year/month")
            return
        be = get_breakeven(y, m)
        self.v_fixed.set(f"{curr_sym()}{be['fixed_costs']:,.0f}")
        self.v_rev_be.set(f"{curr_sym()}{be['revenue']:,.0f}")
        self.v_status.set(f"Profit {curr_sym()}{be['surplus']:,.0f}" if be["breakeven_reached"] else f"Need {curr_sym()}{be['shortfall']:,.0f} more")
        self.v_units.set(f"{be['units_needed']} x {(be['top_product'] or '')[:12]}" if be["units_needed"] else "—")

        self.ax_be.clear()
        self.ax_be.set_facecolor(theme.card_bg)
        for sp in self.ax_be.spines.values():
            sp.set_visible(False)
        self.ax_be.tick_params(colors=theme.muted, labelsize=8)
        months_data = []
        for i in range(11, -1, -1):
            dt = datetime.date(y, m, 1) - datetime.timedelta(days=i * 30)
            months_data.append((f"{dt.year}-{dt.month:02d}", get_month_revenue(dt.year, dt.month), get_month_expenses(dt.year, dt.month)))
        xs = list(range(len(months_data)))
        labels = [d[0] for d in months_data]
        revs = [d[1] for d in months_data]
        exps = [d[2] for d in months_data]
        self.ax_be.bar(xs, revs, color=theme.success, alpha=0.7, width=0.4, label="Revenue")
        self.ax_be.bar([x + 0.4 for x in xs], exps, color=theme.danger, alpha=0.7, width=0.4, label="Expenses")
        self.ax_be.axhline(be["fixed_costs"], color=theme.warning, linewidth=1.5, linestyle="--", label=f"B/E {curr_sym()}{be['fixed_costs']:,.0f}")
        self.ax_be.set_xticks(xs)
        self.ax_be.set_xticklabels(labels, rotation=30, ha="right", color=theme.muted, fontsize=7)
        self.ax_be.set_yticks([])
        self.ax_be.legend(fontsize=7, labelcolor=theme.text, facecolor=theme.card_bg, edgecolor=theme.border)
        self.canv_be.draw()

        text = f"Month: {y}-{m:02d}\n\n  Fixed Costs: {curr_sym()}{be['fixed_costs']:,.2f}\n  Revenue:     {curr_sym()}{be['revenue']:,.2f}\n"
        if be["breakeven_reached"]:
            text += f"  Break-even reached! Surplus: {curr_sym()}{be['surplus']:,.2f}\n"
        else:
            text += f"  Still need: {curr_sym()}{be['shortfall']:,.2f}\n  Units needed: {be['units_needed']} x {be['top_product'] or 'N/A'}\n"
        self.detail_txt.config(state="normal")
        self.detail_txt.delete("1.0", "end")
        self.detail_txt.insert("end", text)
        self.detail_txt.config(state="disabled")

    def refresh(self):
        self.do_calc()


class AnalyticsPlusView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Analytics+", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 8))
        nb = ttk.Notebook(self.frame)
        nb.pack(fill="both", expand=True)

        # Tab 1: Category Revenue
        tab_cat = tk.Frame(nb, bg=theme.bg)
        nb.add(tab_cat, text="  Category Revenue  ")
        ctrl_c = tk.Frame(tab_cat, bg=theme.bg)
        ctrl_c.pack(fill="x", pady=(8, 6))
        make_label(ctrl_c, "Year:", style="muted", bg=theme.bg).pack(side="left")
        self.e_cy = make_entry(ctrl_c, width=6)
        self.e_cy.insert(0, str(datetime.date.today().year))
        self.e_cy.pack(side="left", padx=4)
        make_label(ctrl_c, "Months:", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.cb_cmonths = make_combo(ctrl_c, ["3", "6", "12"], width=4)
        self.cb_cmonths.set("6")
        self.cb_cmonths.pack(side="left", padx=4)
        make_button(ctrl_c, "Generate", self.do_cat, color=theme.accent).pack(side="left", padx=8)

        self.fig_cat = Figure(figsize=(8, 3.2), dpi=96, facecolor=theme.card_bg)
        self.ax_cat  = self.fig_cat.add_subplot(111)
        self.ax_cat.set_facecolor(theme.card_bg)
        self.fig_cat.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.22)
        self.canv_cat = FigureCanvasTkAgg(self.fig_cat, master=tab_cat)
        self.canv_cat.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv_cat.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=4)

        cat_lbf = tk.Frame(tab_cat, bg=theme.bg)
        cat_lbf.pack(fill="x", padx=8)
        self.cat_lb, self.cat_sb = make_listbox(cat_lbf, height=4)
        self.cat_lb.pack(side="left", fill="x", expand=True)
        self.cat_sb.pack(side="right", fill="y")

        # Tab 2: Cohort
        tab_coh = tk.Frame(nb, bg=theme.bg)
        nb.add(tab_coh, text="  Cohort Retention  ")
        make_button(tab_coh, "Generate Cohort", self.do_cohort, color=theme.accent).pack(anchor="w", pady=10, padx=10)
        coh_lbf = tk.Frame(tab_coh, bg=theme.bg)
        coh_lbf.pack(fill="both", expand=True, padx=8, pady=4)
        self.coh_lb, self.coh_sb = make_listbox(coh_lbf)
        self.coh_lb.pack(side="left", fill="both", expand=True)
        self.coh_sb.pack(side="right", fill="y")

        # Tab 3: Price Elasticity
        tab_pe = tk.Frame(nb, bg=theme.bg)
        nb.add(tab_pe, text="  Price Elasticity  ")
        make_button(tab_pe, "Analyse", self.do_elasticity, color=theme.accent).pack(anchor="w", pady=10, padx=10)
        pe_lbf = tk.Frame(tab_pe, bg=theme.bg)
        pe_lbf.pack(fill="both", expand=True, padx=8, pady=4)
        self.pe_lb, self.pe_sb = make_listbox(pe_lbf)
        self.pe_lb.pack(side="left", fill="both", expand=True)
        self.pe_sb.pack(side="right", fill="y")

    def do_cat(self):
        try:
            y = int(self.e_cy.get())
            n = int(self.cb_cmonths.get())
        except ValueError:
            return
        self.ax_cat.clear()
        self.ax_cat.set_facecolor(theme.card_bg)
        for sp in self.ax_cat.spines.values():
            sp.set_visible(False)
        self.ax_cat.tick_params(colors=theme.muted, labelsize=7)
        today = datetime.date.today()
        months_list = []
        for i in range(n - 1, -1, -1):
            dt = datetime.date(today.year, today.month, 1) - datetime.timedelta(days=i * 30)
            months_list.append((dt.year, dt.month))
        all_cats = set()
        monthly_data = []
        for (my, mm) in months_list:
            cat_rev = get_category_revenue(my, mm)
            all_cats.update(cat_rev.keys())
            monthly_data.append((f"{my}-{mm:02d}", cat_rev))
        all_cats = sorted(all_cats)
        colors = [theme.accent, theme.success, theme.warning, theme.danger, theme.muted, "#7b5ea7", "#1abc9c", "#e74c3c", "#f39c12", "#3498db"]
        xs = list(range(len(months_list)))
        bar_w = 0.8 / max(len(all_cats), 1)
        for ci, cat in enumerate(all_cats):
            vals_c = [monthly_data[i][1].get(cat, 0) for i in range(len(months_list))]
            offset = ci * bar_w - 0.4 + bar_w / 2
            self.ax_cat.bar([x + offset for x in xs], vals_c, width=bar_w * 0.9, color=colors[ci % len(colors)], alpha=0.85, label=cat)
        self.ax_cat.set_xticks(xs)
        self.ax_cat.set_xticklabels([d[0] for d in monthly_data], rotation=30, ha="right", color=theme.muted, fontsize=7)
        self.ax_cat.set_yticks([])
        if all_cats:
            self.ax_cat.legend(fontsize=7, labelcolor=theme.text, facecolor=theme.card_bg, edgecolor=theme.border, loc="upper left")
        self.canv_cat.draw()
        self.cat_lb.delete(0, "end")
        latest = monthly_data[-1][1] if monthly_data else {}
        prev   = monthly_data[-2][1] if len(monthly_data) >= 2 else {}
        for cat in sorted(latest, key=lambda c: latest[c], reverse=True):
            cur = latest[cat]
            prv = prev.get(cat, 0)
            chg = ((cur - prv) / prv * 100) if prv > 0 else 0
            arrow = "^" if chg > 0 else ("v" if chg < 0 else "—")
            self.cat_lb.insert("end", f' {cat:<22} {curr_sym()}{cur:>10,.2f}  {arrow} {abs(float(chg)):.1f}%')

    def do_cohort(self):
        self.coh_lb.delete(0, "end")
        data = get_cohort_data()
        if not data:
            self.coh_lb.insert("end", "  No customer data yet.")
            return
        all_months = sorted({m for entry in data for m in entry["months"].keys()})[-8:]
        self.coh_lb.insert("end", f' {"Cohort":<12}' + "".join(f"{m[5:]:^8}" for m in all_months))
        self.coh_lb.insert("end", "  " + "─" * 70)
        for entry in data[-8:]:
            base = entry["base"]
            row = f' {entry["cohort"]:<12}'
            for m in all_months:
                count = entry["months"].get(m, 0)
                pct = (count / base * 100) if base > 0 else 0
                row += f'{count:>3}({pct:.0f}%):< 8'
            self.coh_lb.insert("end", row)

    def do_elasticity(self):
        self.pe_lb.delete(0, "end")
        hints = get_price_elasticity_hints()
        if not hints:
            self.pe_lb.insert("end", "  No significant price-elasticity signals detected.")
            return
        self.pe_lb.insert("end", f' {"Product":<28} {f"Old {curr_sym()}":>8} {f"New {curr_sym()}":>8} {"Price+":>7} {"Qty-":>7}')
        self.pe_lb.insert("end", "  " + "─" * 60)
        for h in hints:
            self.pe_lb.insert("end", f' {h["name"]:<28} {curr_sym()}{h["old_price"]:>6.2f}  {curr_sym()}{h["new_price"]:>6.2f}  +{h["price_rise"]:.1f}%  -{h["qty_drop"]:.1f}%')

    def refresh(self):
        self.do_cat()
        self.do_elasticity()

import os
import datetime
import calendar
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, sep, field_group, stat_tile
from ..dialogs import center_window
from ...config import BASE_DIR, curr_sym, F_HEAD, F_SMALL
from ...database import db_all, db_one, db_run
from ...utils import rnd
from ...analytics import (
    calc_overtime, get_staff_sales, get_month_target, get_month_revenue,
    required_daily_sales, get_month_expenses, get_month_profit, EXPENSE_CATS
)

class StaffView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Staff", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Add / Edit Staff", style="heading").pack(anchor="w", pady=(0, 8))
        self.e_sname  = field_group(fc, "Full Name *")
        self.e_sphone = field_group(fc, "Phone")
        make_label(fc, "Role", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_role = make_combo(fc, ["Manager", "Staff", "Cashier", "Delivery"], width=22)
        self.cb_role.set("Staff")
        self.cb_role.pack(anchor="w")
        self.e_shift_s = field_group(fc, "Shift Start (HH:MM)")
        self.e_shift_s.insert(0, "09:00")
        self.e_shift_e = field_group(fc, "Shift End (HH:MM)")
        self.e_shift_e.insert(0, "18:00")
        self.e_salary  = field_group(fc, f"Salary ({curr_sym()}/month)")
        self.e_salary.insert(0, "0")
        self.e_comm    = field_group(fc, "Commission (%)")
        self.e_comm.insert(0, "0")
        self.err_lbl   = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)
        self.selected_id = tk.IntVar(value=0)

        make_button(fc, "Save / Update",  self.do_save_staff).pack(fill="x", pady=2)
        make_button(fc, "Load Selected",  self.do_load_staff, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Clock In/Out",   self.do_clock,      color=theme.accent).pack(fill="x", pady=2)
        make_button(fc, "Delete",         self.do_del_staff,  color=theme.danger).pack(fill="x", pady=2)

        lc = make_card(cols, padx=14, pady=14)
        lc.pack(side="right", fill="both", expand=True)
        make_label(lc, "Team", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []
        self.lb.bind("<Double-Button-1>", lambda e: self.do_load_staff())

    def clear_form(self):
        for e in (self.e_sname, self.e_sphone, self.e_shift_s, self.e_shift_e, self.e_salary, self.e_comm):
            e.delete(0, "end")
        self.e_shift_s.insert(0, "09:00")
        self.e_shift_e.insert(0, "18:00")
        self.e_salary.insert(0, "0")
        self.e_comm.insert(0, "0")
        self.cb_role.set("Staff")
        self.selected_id.set(0)
        self.err_lbl.config(text="")

    def do_save_staff(self):
        name = self.e_sname.get().strip()
        if not name:
            self.err_lbl.config(text="Name required.")
            return
        try:
            sal = float(self.e_salary.get())
            comm = float(self.e_comm.get())
        except ValueError:
            self.err_lbl.config(text="Salary/commission must be numbers.")
            return
        sid = self.selected_id.get()
        if sid:
            db_run("UPDATE staff SET name=?,phone=?,role=?,shift_start=?,shift_end=?,salary=?,commission_pct=? WHERE id=?",
                   (name, self.e_sphone.get().strip(), self.cb_role.get(), self.e_shift_s.get().strip(), self.e_shift_e.get().strip(), sal, comm, sid))
        else:
            db_run("INSERT INTO staff (name,phone,role,shift_start,shift_end,salary,commission_pct) VALUES (?,?,?,?,?,?,?)",
                   (name, self.e_sphone.get().strip(), self.cb_role.get(), self.e_shift_s.get().strip(), self.e_shift_e.get().strip(), sal, comm))
        self.clear_form()
        self.app.refresh_all()

    def do_del_staff(self):
        sel = self.lb.curselection()
        if not sel:
            return
        sid = self.lb_ids[sel[0]]
        s = db_one("SELECT name FROM staff WHERE id=?", (sid,))
        if s and messagebox.askyesno("Delete", f'Delete "{s["name"]}"?'):
            db_run("DELETE FROM staff WHERE id=?", (sid,))
            self.app.refresh_all()

    def do_load_staff(self):
        sel = self.lb.curselection()
        if not sel:
            return
        s = db_one("SELECT * FROM staff WHERE id=?", (self.lb_ids[sel[0]],))
        if not s:
            return
        self.clear_form()
        self.e_sname.insert(0, s["name"])
        self.e_sphone.insert(0, s.get("phone", ""))
        self.cb_role.set(s.get("role", "Staff"))
        self.e_shift_s.delete(0, "end")
        self.e_shift_s.insert(0, s.get("shift_start", "09:00"))
        self.e_shift_e.delete(0, "end")
        self.e_shift_e.insert(0, s.get("shift_end", "18:00"))
        self.e_salary.delete(0, "end")
        self.e_salary.insert(0, str(s.get("salary", 0)))
        self.e_comm.delete(0, "end")
        self.e_comm.insert(0, str(s.get("commission_pct", 0)))
        self.selected_id.set(s["id"])

    def do_clock(self):
        sel = self.lb.curselection()
        if not sel:
            return
        sid = self.lb_ids[sel[0]]
        today = datetime.date.today().strftime("%Y-%m-%d")
        now = datetime.datetime.now().strftime("%H:%M")
        att = db_one("SELECT * FROM attendance WHERE staff_id=? AND date=?", (sid, today))
        if not att:
            db_run("INSERT INTO attendance (staff_id,date,clock_in) VALUES (?,?,?)", (sid, today, now))
            messagebox.showinfo("Clock In", f"Clocked IN at {now}")
        elif not att.get("clock_out"):
            ot = calc_overtime(sid, today)
            db_run("UPDATE attendance SET clock_out=?,overtime_hrs=? WHERE staff_id=? AND date=?", (now, ot, sid, today))
            messagebox.showinfo("Clock Out", f"Clocked OUT at {now}\nOvertime: {ot:.2f} hrs")
        else:
            messagebox.showinfo("Done", f"Already clocked out at {att['clock_out']}.")

    def refresh(self, *_):
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        y = datetime.date.today().year
        m = datetime.date.today().month
        for s in db_all("SELECT * FROM staff ORDER BY name"):
            sales = get_staff_sales(s["id"], y, m)
            comm = rnd(float(sales) * float(s.get("commission_pct", 0)) / 100.0, 2)
            self.lb.insert("end", f' {"[ON]" if s["active"] else "[OFF]"} {s["name"]:<20} {s.get("role",""):<10} Sales:{curr_sym()}{sales:,.0f} Comm:{curr_sym()}{comm:.0f}')
            self.lb_ids.append(s["id"])


class TargetsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Sales Targets", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        today = datetime.date.today()
        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Year:", style="muted", bg=theme.bg).pack(side="left")
        self.e_year = make_entry(ctrl, width=6)
        self.e_year.insert(0, str(today.year))
        self.e_year.pack(side="left", padx=4)
        make_label(ctrl, "Month:", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.cb_month = make_combo(ctrl, [str(i) for i in range(1, 13)], width=4)
        self.cb_month.set(str(today.month))
        self.cb_month.pack(side="left", padx=4)
        make_label(ctrl, f"Target ({curr_sym()}):", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.e_target = make_entry(ctrl, width=12)
        self.e_target.pack(side="left", padx=4)
        self.cb_staff_t = make_combo(ctrl, width=18)
        self.cb_staff_t.set("—")
        self.cb_staff_t.pack(side="left", padx=4)
        make_button(ctrl, "Set Target", self.do_set, color=theme.success).pack(side="left", padx=8)

        self.prog_card = make_card(self.frame, padx=18, pady=14)
        self.prog_card.pack(fill="x", pady=(0, 8))
        make_label(self.prog_card, "This Month Progress", style="heading").pack(anchor="w", pady=(0, 6))
        self.v_target  = tk.StringVar(value=f"Target: {curr_sym()}0")
        self.v_current = tk.StringVar(value=f"Achieved: {curr_sym()}0")
        self.v_remain  = tk.StringVar(value=f"Remaining: {curr_sym()}0")
        self.v_daily   = tk.StringVar(value=f"Req/day: {curr_sym()}0")
        self.v_pct     = tk.StringVar(value="0%")
        row_t = tk.Frame(self.prog_card, bg=theme.card_bg)
        row_t.pack(fill="x")
        for var, col in [(self.v_target, theme.muted), (self.v_current, theme.success), (self.v_remain, theme.danger), (self.v_daily, theme.warning)]:
            tk.Label(row_t, textvariable=var, bg=theme.card_bg, fg=col, font=("Segoe UI", 11, "bold")).pack(side="left", padx=16)
        self.prog_canvas = tk.Canvas(self.prog_card, bg=theme.input_bg, height=22, highlightthickness=0)
        self.prog_canvas.pack(fill="x", pady=(8, 4), padx=4)
        tk.Label(self.prog_card, textvariable=self.v_pct, bg=theme.card_bg, fg=theme.text, font=F_SMALL).pack(anchor="e")

        st_card = make_card(self.frame, padx=14, pady=10)
        st_card.pack(fill="both", expand=True)
        make_label(st_card, "Staff Targets", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(st_card, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")

    def do_set(self):
        try:
            y = int(self.e_year.get())
            m = int(self.cb_month.get())
            tgt = float(self.e_target.get())
        except ValueError:
            messagebox.showerror("Invalid", "Enter valid numbers.")
            return
        period = f"{y:04d}-{m:02d}"
        sname = self.cb_staff_t.get()
        sid = 0
        if sname and sname != "—":
            sr = db_one("SELECT id FROM staff WHERE name=?", (sname,))
            if sr:
                sid = sr["id"]
        existing = db_one("SELECT id FROM sales_targets WHERE period=? AND staff_id=?", (period, sid))
        if existing:
            db_run("UPDATE sales_targets SET target_amt=? WHERE id=?", (tgt, existing["id"]))
        else:
            db_run("INSERT INTO sales_targets (period,target_amt,staff_id) VALUES (?,?,?)", (period, tgt, sid))
        self.app.refresh_all()

    def draw_progress(self, pct: float):
        self.prog_canvas.update_idletasks()
        w = self.prog_canvas.winfo_width()
        self.prog_canvas.delete("all")
        self.prog_canvas.create_rectangle(0, 0, w, 22, fill=theme.input_bg, outline="")
        fill_w = int(w * float(min(float(pct), 1.0)))
        color = theme.success if pct >= 1.0 else (theme.warning if pct >= 0.6 else theme.danger)
        self.prog_canvas.create_rectangle(0, 0, fill_w, 22, fill=color, outline="")

    def refresh(self):
        today = datetime.date.today()
        y = today.year
        m = today.month
        target = get_month_target(y, m)
        current = get_month_revenue(y, m)
        remain = max(0.0, target - current)
        daily = required_daily_sales(y, m)
        pct = (current / target) if target > 0 else 0.0
        self.v_target.set(f"Target:   {curr_sym()}{target:,.0f}")
        self.v_current.set(f"Achieved: {curr_sym()}{current:,.0f}")
        self.v_remain.set(f"Remaining: {curr_sym()}{remain:,.0f}")
        self.v_daily.set(f"Req/day:  {curr_sym()}{daily:,.0f}")
        self.v_pct.set(f"{pct*100:.1f}%  achieved")
        self.prog_card.after(50, lambda: self.draw_progress(pct))

        self.lb.delete(0, "end")
        staff_list = db_all("SELECT * FROM staff WHERE active=1 ORDER BY name")
        self.cb_staff_t.configure(values=["—"] + [s["name"] for s in staff_list])
        for s in staff_list:
            st_tgt = get_month_target(y, m, s["id"])
            st_rev = get_staff_sales(s["id"], y, m)
            st_pct = (st_rev / st_tgt * 100) if st_tgt > 0 else 0
            bar = "█" * int(st_pct / 10) + "░" * (10 - int(float(min(float(st_pct), 100.0)) / 10))
            self.lb.insert("end", f' {s["name"]:<20} Target:{curr_sym()}{st_tgt:>8,.0f}  Got:{curr_sym()}{st_rev:>8,.0f}  {bar} {st_pct:.0f}%')


class HolidaysView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Holidays & Closures", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Mark Holiday", style="heading").pack(anchor="w", pady=(0, 8))
        self.e_hdate = field_group(fc, "Date (YYYY-MM-DD)")
        self.e_hdate.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.e_hname = field_group(fc, "Name / Reason")
        make_label(fc, "Type", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_htype = make_combo(fc, ["holiday", "half-day", "closure", "festival"], width=22)
        self.cb_htype.set("holiday")
        self.cb_htype.pack(anchor="w")
        self.err_lbl = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)

        make_button(fc, "Mark Holiday",    self.do_add).pack(fill="x", pady=2)
        make_button(fc, "Add All Sundays", self.do_bulk_add, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Delete",          self.do_del,      color=theme.danger).pack(fill="x", pady=2)

        lc = make_card(cols, padx=14, pady=14)
        lc.pack(side="right", fill="both", expand=True)
        make_label(lc, "All Holidays", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

    def do_add(self):
        dt = self.e_hdate.get().strip()
        try:
            datetime.datetime.strptime(dt, "%Y-%m-%d")
        except ValueError:
            self.err_lbl.config(text="Date: YYYY-MM-DD")
            return
        nm = self.e_hname.get().strip() or dt
        existing = db_one("SELECT id FROM holidays WHERE date=?", (dt,))
        if existing:
            db_run("UPDATE holidays SET name=?,type=? WHERE date=?", (nm, self.cb_htype.get(), dt))
        else:
            db_run("INSERT INTO holidays (date,name,type) VALUES (?,?,?)", (dt, nm, self.cb_htype.get()))
        self.err_lbl.config(text="")
        self.app.refresh_all()

    def do_del(self):
        sel = self.lb.curselection()
        if not sel:
            return
        if messagebox.askyesno("Delete", "Remove this holiday?"):
            db_run("DELETE FROM holidays WHERE id=?", (self.lb_ids[sel[0]],))
            self.app.refresh_all()

    def do_bulk_add(self):
        today = datetime.date.today()
        y, m = today.year, today.month
        last = calendar.monthrange(y, m)[1]
        count = 0
        for d in range(1, last + 1):
            dd = datetime.date(y, m, d)
            if dd.weekday() == 6:
                ds = dd.strftime("%Y-%m-%d")
                if not db_one("SELECT id FROM holidays WHERE date=?", (ds,)):
                    db_run("INSERT INTO holidays (date,name,type) VALUES (?,?,?)", (ds, "Sunday", "holiday"))
                    count += 1
        messagebox.showinfo("Done", f"Added {count} Sundays.")
        self.app.refresh_all()

    def refresh(self, *_):
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        icons = {"holiday": "[HOL]", "half-day": "[HLF]", "closure": "[CLS]", "festival": "[FES]"}
        for h in db_all("SELECT * FROM holidays ORDER BY date"):
            self.lb.insert("end", f' {icons.get(h["type"],"[---]")}  {h["date"]}  {h["name"]:<28} [{h["type"]}]')
            self.lb_ids.append(h["id"])


class ExpensesView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Expenses & Profit", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 8))
        self.v_rev_t = tk.StringVar(value=f"{curr_sym()}0")
        self.v_exp_t = tk.StringVar(value=f"{curr_sym()}0")
        self.v_pft_t = tk.StringVar(value=f"{curr_sym()}0")
        stat_tile(tiles, "Revenue (month)",  self.v_rev_t, theme.success)
        stat_tile(tiles, "Expenses (month)", self.v_exp_t, theme.danger)
        stat_tile(tiles, "Profit (month)",   self.v_pft_t, theme.accent)

        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Add Expense", style="heading").pack(anchor="w", pady=(0, 8))
        self.e_edate = field_group(fc, "Date (YYYY-MM-DD)")
        self.e_edate.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        make_label(fc, "Category", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_ecat = make_combo(fc, EXPENSE_CATS, width=22)
        self.cb_ecat.set("General")
        self.cb_ecat.pack(anchor="w")
        self.e_eamt  = field_group(fc, f"Amount ({curr_sym()})")
        self.e_enote = field_group(fc, "Note")
        self.err_lbl = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)

        make_button(fc, "Add Expense", self.do_add).pack(fill="x", pady=2)
        make_button(fc, "Delete",      self.do_del, color=theme.danger).pack(fill="x", pady=2)

        rc = make_card(cols, padx=14, pady=14)
        rc.pack(side="right", fill="both", expand=True)
        self.fig_e = Figure(figsize=(4, 2.2), dpi=96, facecolor=theme.card_bg)
        self.ax_e  = self.fig_e.add_subplot(111)
        self.ax_e.set_facecolor(theme.card_bg)
        self.fig_e.subplots_adjust(left=0.04, right=0.98, top=0.88, bottom=0.1)
        self.canv_e = FigureCanvasTkAgg(self.fig_e, master=rc)
        self.canv_e.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv_e.get_tk_widget().pack(fill="x", pady=(0, 6))
        sep(rc, pady=4)
        lbf = tk.Frame(rc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

    def do_add(self):
        dt = self.e_edate.get().strip()
        try:
            datetime.datetime.strptime(dt, "%Y-%m-%d")
        except ValueError:
            self.err_lbl.config(text="Date: YYYY-MM-DD")
            return
        try:
            amt = float(self.e_eamt.get())
            assert amt > 0
        except Exception:
            self.err_lbl.config(text="Amount must be > 0.")
            return
        db_run("INSERT INTO expenses (date,category,amount,note) VALUES (?,?,?,?)",
               (dt, self.cb_ecat.get(), amt, self.e_enote.get().strip()))
        for e in (self.e_eamt, self.e_enote):
            e.delete(0, "end")
        self.err_lbl.config(text="")
        self.app.refresh_all()

    def do_del(self):
        sel = self.lb.curselection()
        if not sel:
            return
        if messagebox.askyesno("Delete", "Delete this expense?"):
            db_run("DELETE FROM expenses WHERE id=?", (self.lb_ids[sel[0]],))
            self.app.refresh_all()

    def refresh(self):
        today = datetime.date.today()
        y, m = today.year, today.month
        rev = get_month_revenue(y, m)
        exp = get_month_expenses(y, m)
        pft = get_month_profit(y, m)
        self.v_rev_t.set(f"{curr_sym()}{rev:,.0f}")
        self.v_exp_t.set(f"{curr_sym()}{exp:,.0f}")
        self.v_pft_t.set(f"{curr_sym()}{pft:,.0f}")

        cats: dict = defaultdict(float)
        for r in db_all("SELECT category,amount FROM expenses WHERE date LIKE ?", (f"{y:04d}-{m:02d}-%",)):
            cats[r["category"]] += float(r["amount"])
        self.ax_e.clear()
        self.ax_e.set_facecolor(theme.card_bg)
        for sp in self.ax_e.spines.values():
            sp.set_visible(False)
        if cats:
            labels = list(cats.keys())
            vals2 = [cats[k] for k in labels]
            colors = [theme.danger, theme.warning, theme.accent, theme.success, theme.muted, "#7b5ea7", "#e74c3c", "#1abc9c"][:len(labels)]
            self.ax_e.pie(vals2, labels=labels, colors=colors, textprops={"color": theme.text, "fontsize": 7}, startangle=90)
        else:
            self.ax_e.text(0.5, 0.5, "No expenses", ha="center", va="center", transform=self.ax_e.transAxes, color=theme.muted, fontsize=10)
        self.canv_e.draw()

        self.lb.delete(0, "end")
        self.lb_ids.clear()
        for r in db_all("SELECT * FROM expenses ORDER BY date DESC LIMIT 100"):
            self.lb.insert("end", f' {r["date"]}  {r["category"]:<16} {curr_sym()}{r["amount"]:>8.2f}  {r.get("note","")[:24]}')
            self.lb_ids.append(r["id"])


class RosterView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        self.days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self.day_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        self.shift_opts = ["—", "Morning (6-14)", "Afternoon (14-22)", "Night (22-6)", "Full Day", "Half Day", "Off"]

        make_label(self.frame, "Staff Roster", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Week of:", style="muted", bg=theme.bg).pack(side="left")
        today = datetime.date.today()
        mon = today - datetime.timedelta(days=today.weekday())
        self.e_week = make_entry(ctrl, width=14)
        self.e_week.insert(0, mon.strftime("%Y-%m-%d"))
        self.e_week.pack(side="left", padx=6)
        make_button(ctrl, "Load Week",   self.do_load_week,   color=theme.accent).pack(side="left", padx=4)
        make_button(ctrl, "Save Roster", self.do_save_roster, color=theme.success).pack(side="left", padx=4)
        make_button(ctrl, "Print",       self.do_print_roster, color=theme.muted).pack(side="left", padx=4)

        grid_card = make_card(self.frame, padx=12, pady=10)
        grid_card.pack(fill="both", expand=True)
        hdr_row = tk.Frame(grid_card, bg=theme.card_bg)
        hdr_row.pack(fill="x", pady=(0, 4))
        tk.Label(hdr_row, text="Staff", bg=theme.card_bg, fg=theme.muted, font=F_SMALL, width=18, anchor="w").pack(side="left")
        for d in self.days:
            tk.Label(hdr_row, text=d[:3], bg=theme.card_bg, fg=theme.muted, font=F_SMALL, width=10).pack(side="left")

        self.scroll_frame = tk.Frame(grid_card, bg=theme.card_bg)
        self.scroll_frame.pack(fill="both", expand=True)
        self.roster_widgets: dict = {}
        self.do_load_week()

    def do_load_week(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.roster_widgets.clear()
        week_start = self.e_week.get().strip()
        try:
            datetime.datetime.strptime(week_start, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid", "Date: YYYY-MM-DD")
            return
        staff_list = db_all("SELECT * FROM staff WHERE active=1 ORDER BY name")
        if not staff_list:
            make_label(self.scroll_frame, "No active staff.", style="muted").pack(pady=16)
            return
        for s in staff_list:
            row = tk.Frame(self.scroll_frame, bg=theme.card_bg)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=s["name"][:18], bg=theme.card_bg, fg=theme.text, font=F_SMALL, width=18, anchor="w").pack(side="left")
            existing = db_one("SELECT * FROM roster WHERE staff_id=? AND week_start=?", (s["id"], week_start))
            day_combos = {}
            for dk in self.day_keys:
                cb = ttk.Combobox(row, values=self.shift_opts, width=10, state="readonly", style="App.TCombobox")
                saved = (existing.get(dk, "—") if existing else "—") or "—"
                cb.set(saved)
                cb.pack(side="left", padx=1)
                day_combos[dk] = cb
            self.roster_widgets[s["id"]] = day_combos

    def do_save_roster(self):
        week_start = self.e_week.get().strip()
        for staff_id, day_combos in self.roster_widgets.items():
            vals = {dk: day_combos[dk].get() for dk in self.day_keys}
            existing = db_one("SELECT id FROM roster WHERE staff_id=? AND week_start=?", (staff_id, week_start))
            if existing:
                db_run("UPDATE roster SET monday=?,tuesday=?,wednesday=?,thursday=?,friday=?,saturday=?,sunday=? WHERE staff_id=? AND week_start=?",
                       (vals["monday"], vals["tuesday"], vals["wednesday"], vals["thursday"], vals["friday"], vals["saturday"], vals["sunday"], staff_id, week_start))
            else:
                db_run("INSERT INTO roster (staff_id,week_start,monday,tuesday,wednesday,thursday,friday,saturday,sunday) VALUES (?,?,?,?,?,?,?,?,?)",
                       (staff_id, week_start, vals["monday"], vals["tuesday"], vals["wednesday"], vals["thursday"], vals["friday"], vals["saturday"], vals["sunday"]))
        messagebox.showinfo("Saved", "Roster saved.")

    def do_print_roster(self):
        week_start = self.e_week.get().strip()
        staff_list = db_all("SELECT * FROM staff WHERE active=1 ORDER BY name")
        lines = ["=" * 80, f"  STAFF ROSTER — Week of {week_start}", "=" * 80, f' {"STAFF":<20}' + "".join(f"{d[:3]:^12}" for d in self.days), "-" * 80]
        for s in staff_list:
            row_data = db_one("SELECT * FROM roster WHERE staff_id=? AND week_start=?", (s["id"], week_start))
            line = f' {s["name"]:<20}'
            for dk in self.day_keys:
                shift = (row_data.get(dk, "—") if row_data else "—") or "—"
                line += f'{shift[:11]:^12}'
            lines.append(line)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
        path = os.path.join(BASE_DIR, "reports", f"roster_{ts}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        win = tk.Toplevel(self.frame)
        win.title("Roster")
        win.geometry("680x380")
        win.configure(bg=theme.bg)
        center_window(win, self.frame, 680, 380)
        txt = tk.Text(win, bg=theme.input_bg, fg=theme.text, font=("Consolas", 8), relief="flat", bd=8, wrap="none")
        txt.pack(fill="both", expand=True, padx=8, pady=6)
        txt.insert("end", "\n".join(lines))
        txt.config(state="disabled")
        make_button(win, "Close", win.destroy, color=theme.danger).pack(pady=(0, 8))

    def refresh(self):
        self.do_load_week()


class SalaryView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Salary Slips", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Year:", style="muted", bg=theme.bg).pack(side="left")
        self.e_sy = make_entry(ctrl, width=6)
        self.e_sy.insert(0, str(datetime.date.today().year))
        self.e_sy.pack(side="left", padx=4)
        make_label(ctrl, "Month:", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.cb_sm = make_combo(ctrl, [str(i) for i in range(1, 13)], width=4)
        self.cb_sm.set(str(datetime.date.today().month))
        self.cb_sm.pack(side="left", padx=4)
        make_button(ctrl, "Load", self.do_load_sal, color=theme.accent).pack(side="left", padx=8)

        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        lc = make_card(cols, padx=14, pady=12)
        lc.pack(side="left", fill="y", padx=(0, 8))
        make_label(lc, "Staff", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf, width=26)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

        sep_f = tk.Frame(lc, bg=theme.card_bg)
        sep_f.pack(fill="x", pady=(8, 0))
        make_label(sep_f, "Add Advance", style="muted").pack(anchor="w")
        self.e_adv_amt = make_entry(sep_f, width=12)
        self.e_adv_amt.pack(anchor="w", pady=2)
        self.e_adv_note = make_entry(sep_f, width=12)
        self.e_adv_note.insert(0, "Advance reason")
        self.e_adv_note.pack(anchor="w")
        make_button(sep_f, "Add Advance", self.do_add_advance, color=theme.warning).pack(anchor="w", pady=4)

        rc = make_card(cols, padx=16, pady=12)
        rc.pack(side="right", fill="both", expand=True)
        make_label(rc, "Salary Slip Preview", style="heading").pack(anchor="w", pady=(0, 4))
        self.txt = tk.Text(rc, bg=theme.input_bg, fg=theme.text, font=("Consolas", 9), relief="flat", bd=6, wrap="none")
        self.txt.pack(fill="both", expand=True)

        make_button(rc, "Preview Slip", self.do_show_slip,  color=theme.accent).pack(anchor="w", pady=(4, 2))
        make_button(rc, "Save Slip",    self.do_print_slip, color=theme.success).pack(anchor="w", pady=2)
        self.lb.bind("<ButtonRelease-1>", lambda e: self.do_show_slip())

    def do_add_advance(self):
        sel = self.lb.curselection()
        if not sel:
            return
        try:
            amt = float(self.e_adv_amt.get())
        except ValueError:
            messagebox.showerror("Invalid", "Amount must be a number")
            return
        db_run("INSERT INTO staff_advances (staff_id,date,amount,note) VALUES (?,?,?,?)",
               (self.lb_ids[sel[0]], datetime.date.today().strftime("%Y-%m-%d"), amt, self.e_adv_note.get().strip()))
        self.e_adv_amt.delete(0, "end")
        messagebox.showinfo("Done", "Advance recorded.")
        self.app.refresh_all()

    def do_load_sal(self):
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        try:
            y = int(self.e_sy.get())
            m = int(self.cb_sm.get())
        except ValueError:
            return
        for s in db_all("SELECT * FROM staff WHERE active=1 ORDER BY name"):
            sales = get_staff_sales(s["id"], y, m)
            comm = rnd(float(sales) * float(s.get("commission_pct", 0)) / 100.0, 2)
            self.lb.insert("end", f' {s["name"]:<20} {curr_sym()}{s.get("salary",0):.0f}+{comm:.0f}')
            self.lb_ids.append(s["id"])

    def do_show_slip(self):
        sel = self.lb.curselection()
        if not sel:
            return
        try:
            y = int(self.e_sy.get())
            m = int(self.cb_sm.get())
        except ValueError:
            return
        s = db_one("SELECT * FROM staff WHERE id=?", (self.lb_ids[sel[0]],))
        if not s:
            return
        sales = get_staff_sales(s["id"], y, m)
        comm = rnd(float(sales) * float(s.get("commission_pct", 0)) / 100.0, 2)
        base = float(s.get("salary", 0))
        advances = sum(float(r["amount"]) for r in db_all("SELECT amount FROM staff_advances WHERE staff_id=? AND date LIKE ?", (s["id"], f"{y:04d}-{m:02d}-%")))
        net = base + comm - advances
        att_rows = db_all("SELECT * FROM attendance WHERE staff_id=? AND date LIKE ?", (s["id"], f"{y:04d}-{m:02d}-%"))
        days_present = len([a for a in att_rows if a.get("clock_in")])
        total_ot = sum(float(a.get("overtime_hrs", 0)) for a in att_rows)
        lines = [
            "=" * 44, "      SALARY SLIP", "=" * 44, f"  Name   : {s['name']}", f"  Role   : {s.get('role','Staff')}", f"  Period : {y}-{m:02d}", "-" * 44,
            f"  {'Basic Salary':<28} {curr_sym()}{base:>8.2f}", f"  {'Commission ('+str(s.get('commission_pct',0))+'%)':<28} {curr_sym()}{comm:>8.2f}", "-" * 44,
            f"  {'Gross Pay':<28} {curr_sym()}{base+comm:>8.2f}", f"  {'Advances/Deductions':<28}-{curr_sym()}{advances:>7.2f}", "=" * 44,
            f"  {'NET PAY':<28} {curr_sym()}{net:>8.2f}", "=" * 44, f"  Days Present: {days_present}", f"  Overtime Hrs: {total_ot:.2f}", "-" * 44, ""
        ]
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", "\n".join(lines))
        self.txt.config(state="disabled")

    def do_print_slip(self):
        slip_text = self.txt.get("1.0", "end").strip()
        if not slip_text:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
        path = os.path.join(BASE_DIR, "reports", f"salary_slip_{ts}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(slip_text)
        messagebox.showinfo("Saved", f"Saved:\n{path}")

    def refresh(self):
        self.do_load_sal()

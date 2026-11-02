import os
import datetime
from collections import defaultdict
import tkinter as tk
from tkinter import messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, sep, field_group, stat_tile
from ..dialogs import center_window
from ...config import BASE_DIR, curr_sym, F_SMALL
from ...database import db_all, db_one, db_run
from ...analytics import get_reorder_suggestions, get_cash_balance

class EndOfDayView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        self.eod_lines: list = []

        hdr = tk.Frame(self.frame, bg=theme.bg)
        hdr.pack(fill="x", pady=(0, 8))
        make_label(hdr, "End of Day Report", style="title", bg=theme.bg).pack(side="left")

        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Date:", style="muted", bg=theme.bg).pack(side="left")
        self.e_eod_date = make_entry(ctrl, width=14)
        self.e_eod_date.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.e_eod_date.pack(side="left", padx=6)
        make_button(ctrl, "Load", self.do_load_eod, color=theme.accent).pack(side="left", padx=4)
        make_button(ctrl, "Print / Save", self.do_print_eod, color=theme.success).pack(side="left", padx=4)

        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 8))
        self.v_erev   = tk.StringVar(value=f"{curr_sym()}0")
        self.v_ebills = tk.StringVar(value="0")
        self.v_eavg   = tk.StringVar(value=f"{curr_sym()}0")
        self.v_eexp   = tk.StringVar(value=f"{curr_sym()}0")
        stat_tile(tiles, "Revenue",  self.v_erev,   theme.success)
        stat_tile(tiles, "Bills",    self.v_ebills, theme.accent)
        stat_tile(tiles, "Avg Bill", self.v_eavg,   theme.warning)
        stat_tile(tiles, "Expenses", self.v_eexp,   theme.danger)

        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        lc = make_card(cols, padx=14, pady=12)
        lc.pack(side="left", fill="both", expand=True, padx=(0, 4))
        make_label(lc, "Payment Breakdown", style="heading").pack(anchor="w", pady=(0, 4))
        pay_lbf = tk.Frame(lc, bg=theme.card_bg)
        pay_lbf.pack(fill="x")
        self.pay_lb, self.pay_sb = make_listbox(pay_lbf, height=5)
        self.pay_lb.pack(side="left", fill="x", expand=True)
        self.pay_sb.pack(side="right", fill="y")
        sep(lc, pady=6)
        make_label(lc, "Staff Performance", style="heading").pack(anchor="w", pady=(0, 4))
        staff_lbf = tk.Frame(lc, bg=theme.card_bg)
        staff_lbf.pack(fill="both", expand=True)
        self.staff_lb, self.staff_sb = make_listbox(staff_lbf, height=6)
        self.staff_lb.pack(side="left", fill="both", expand=True)
        self.staff_sb.pack(side="right", fill="y")

        rc = make_card(cols, padx=14, pady=12)
        rc.pack(side="right", fill="both", expand=True)
        make_label(rc, "Top Items Sold", style="heading").pack(anchor="w", pady=(0, 4))
        top_lbf = tk.Frame(rc, bg=theme.card_bg)
        top_lbf.pack(fill="x")
        self.top_lb, self.top_sb = make_listbox(top_lbf, height=6)
        self.top_lb.pack(side="left", fill="x", expand=True)
        self.top_sb.pack(side="right", fill="y")
        sep(rc, pady=6)
        make_label(rc, "Payment Split", style="heading").pack(anchor="w", pady=(0, 4))
        self.fig_pay = Figure(figsize=(3.5, 2.2), dpi=96, facecolor=theme.card_bg)
        self.ax_pay = self.fig_pay.add_subplot(111)
        self.ax_pay.set_facecolor(theme.card_bg)
        self.fig_pay.subplots_adjust(left=0.04, right=0.98, top=0.92, bottom=0.04)
        self.canv_pay = FigureCanvasTkAgg(self.fig_pay, master=rc)
        self.canv_pay.get_tk_widget().configure(bg=theme.card_bg, highlightthickness=0)
        self.canv_pay.get_tk_widget().pack(fill="both", expand=True)

    def do_load_eod(self):
        self.eod_lines.clear()
        date_str = self.e_eod_date.get().strip()
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid", "Date: YYYY-MM-DD")
            return
        bills = db_all("SELECT * FROM bills WHERE date LIKE ?", (f"{date_str}%",))
        rev = sum(float(b["total"]) for b in bills)
        count = len(bills)
        avg = (rev / count) if count else 0.0
        exp = sum(float(r["amount"]) for r in db_all("SELECT amount FROM expenses WHERE date=?", (date_str,)))
        self.v_erev.set(f"{curr_sym()}{rev:,.2f}")
        self.v_ebills.set(str(count))
        self.v_eavg.set(f"{curr_sym()}{avg:,.2f}")
        self.v_eexp.set(f"{curr_sym()}{exp:,.2f}")

        pay_totals: dict = defaultdict(float)
        pay_counts: dict = defaultdict(int)
        for b in bills:
            pm = str(b.get("payment_mode", "Cash") or "Cash")
            pay_totals[pm] += float(b["total"])
            pay_counts[pm] += 1
        self.pay_lb.delete(0, "end")
        self.pay_lb.insert("end", f' {"Mode":<12} {"Bills":>6}  {"Amount":>12}')
        self.pay_lb.insert("end", "  " + "─" * 32)
        for pm, amt in sorted(pay_totals.items(), key=lambda x: x[1], reverse=True):
            self.pay_lb.insert("end", f' {pm:<12} {pay_counts[pm]:>6}  {curr_sym()}{amt:>10.2f}')

        self.ax_pay.clear()
        self.ax_pay.set_facecolor(theme.card_bg)
        if pay_totals:
            labels = list(pay_totals.keys())
            vals2 = list(pay_totals.values())
            colors = [theme.accent, theme.success, theme.warning, theme.danger, theme.muted][:len(labels)]
            self.ax_pay.pie(vals2, labels=labels, colors=colors, textprops={"color": theme.text, "fontsize": 8},
                            startangle=90, autopct="%1.0f%%", pctdistance=0.75)
        else:
            self.ax_pay.text(0.5, 0.5, "No data", ha="center", va="center", transform=self.ax_pay.transAxes, color=theme.muted, fontsize=10)
        self.canv_pay.draw()

        item_qty: dict = defaultdict(int)
        item_rev: dict = defaultdict(float)
        for b in bills:
            for it in db_all("SELECT * FROM bill_items WHERE bill_id=?", (b["id"],)):
                item_qty[it["name"]] += int(it["qty"])
                item_rev[it["name"]] += float(it["price"]) * float(it["qty"])
        self.top_lb.delete(0, "end")
        self.top_lb.insert("end", f' {"Item":<26} {"Qty":>5}  {"Revenue":>10}')
        self.top_lb.insert("end", "  " + "─" * 44)
        for nm, rev2 in sorted(item_rev.items(), key=lambda x: x[1], reverse=True)[:8]:
            self.top_lb.insert("end", f' {nm:<26} {item_qty[nm]:>5}  {curr_sym()}{rev2:>8.2f}')

        staff_sales: dict = defaultdict(float)
        staff_bills: dict = defaultdict(int)
        for b in bills:
            sid = b.get("staff_id") or 0
            sname = "Unassigned"
            if sid:
                s = db_one("SELECT name FROM staff WHERE id=?", (sid,))
                if s:
                    sname = s["name"]
            staff_sales[sname] += float(b["total"])
            staff_bills[sname] += 1
        self.staff_lb.delete(0, "end")
        self.staff_lb.insert("end", f' {"Staff":<22} {"Bills":>6}  {"Revenue":>12}')
        self.staff_lb.insert("end", "  " + "─" * 42)
        for sn, sal in sorted(staff_sales.items(), key=lambda x: x[1], reverse=True):
            self.staff_lb.insert("end", f' {sn:<22} {staff_bills[sn]:>6}  {curr_sym()}{sal:>10.2f}')

        self.eod_lines.extend([
            "=" * 48, "    END OF DAY REPORT", "=" * 48, f"  Date: {date_str}",
            f"  Revenue: {curr_sym()}{rev:,.2f}   Bills: {count}   Avg: {curr_sym()}{avg:,.2f}",
            f"  Expenses: {curr_sym()}{exp:,.2f}   Net: {curr_sym()}{float(rev)-float(exp):,.2f}", ""
        ])

    def do_print_eod(self):
        if not self.eod_lines:
            self.do_load_eod()
        if not self.eod_lines:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
        path = os.path.join(BASE_DIR, "reports", f"eod_report_{ts}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.eod_lines))
        win = tk.Toplevel(self.frame)
        win.title("EOD Report")
        win.geometry("540x440")
        win.configure(bg=theme.bg)
        center_window(win, self.frame, 540, 440)
        txt = tk.Text(win, bg=theme.input_bg, fg=theme.text, font=("Consolas", 9), relief="flat", bd=8, wrap="none")
        txt.pack(fill="both", expand=True, padx=8, pady=6)
        txt.insert("end", "\n".join(self.eod_lines))
        txt.config(state="disabled")
        make_button(win, "Close", win.destroy, color=theme.danger).pack(pady=(0, 8))

    def refresh(self):
        self.e_eod_date.delete(0, "end")
        self.e_eod_date.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.do_load_eod()


class CashRegisterView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Cash Register", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        ctrl = tk.Frame(self.frame, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 8))
        make_label(ctrl, "Date:", style="muted", bg=theme.bg).pack(side="left")
        self.e_date = make_entry(ctrl, width=14)
        self.e_date.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.e_date.pack(side="left", padx=6)
        make_label(ctrl, f"Opening Cash ({curr_sym()}):", style="muted", bg=theme.bg).pack(side="left", padx=(8, 0))
        self.e_opening = make_entry(ctrl, width=12)
        self.e_opening.insert(0, "0")
        self.e_opening.pack(side="left", padx=4)
        make_button(ctrl, "Set Opening", self.do_set_opening, color=theme.accent).pack(side="left", padx=6)
        make_button(ctrl, "Load", self.do_load, color=theme.muted).pack(side="left", padx=4)

        tiles = tk.Frame(self.frame, bg=theme.bg)
        tiles.pack(fill="x", pady=(0, 8))
        self.v_open    = tk.StringVar(value=f"{curr_sym()}0")
        self.v_cash_in = tk.StringVar(value=f"{curr_sym()}0")
        self.v_out     = tk.StringVar(value=f"{curr_sym()}0")
        self.v_close   = tk.StringVar(value=f"{curr_sym()}0")
        stat_tile(tiles, "Opening",        self.v_open,    theme.muted)
        stat_tile(tiles, "Cash Sales",     self.v_cash_in, theme.success)
        stat_tile(tiles, "Cash Out",       self.v_out,     theme.danger)
        stat_tile(tiles, "Expected Close", self.v_close,   theme.accent)

        detail_card = make_card(self.frame, padx=18, pady=12)
        detail_card.pack(fill="both", expand=True)
        make_label(detail_card, "Transaction Log", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(detail_card, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")

    def do_set_opening(self):
        date_str = self.e_date.get().strip()
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            opening = float(self.e_opening.get())
        except ValueError:
            messagebox.showerror("Invalid", "Check date and amount")
            return
        existing = db_one("SELECT id FROM cash_register WHERE date=?", (date_str,))
        if existing:
            db_run("UPDATE cash_register SET opening_cash=? WHERE date=?", (opening, date_str))
        else:
            db_run("INSERT INTO cash_register (date,opening_cash) VALUES (?,?)", (date_str, opening))
        self.do_load()

    def do_load(self):
        date_str = self.e_date.get().strip()
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid", "Date: YYYY-MM-DD")
            return
        bal = get_cash_balance(date_str)
        self.v_open.set(f"{curr_sym()}{bal['opening']:,.2f}")
        self.v_cash_in.set(f"{curr_sym()}{bal['sales_cash']:,.2f}")
        self.v_out.set(f"{curr_sym()}{bal['expenses']:,.2f}")
        self.v_close.set(f"{curr_sym()}{bal['closing']:,.2f}")
        self.lb.delete(0, "end")
        self.lb.insert("end", f' {"DESCRIPTION":<36} {"AMOUNT":>12}')
        self.lb.insert("end", "  " + "─" * 50)
        self.lb.insert("end", f' {"Opening Cash":<36} {curr_sym()}{bal["opening"]:>10.2f}')
        for b in db_all("SELECT * FROM bills WHERE date LIKE ? AND payment_mode='Cash' AND total>=0", (f"{date_str}%",)):
            self.lb.insert("end", f' Bill #{b["id"]} — {b["customer"]:<26} +{curr_sym()}{b["total"]:>8.2f}')
        for b in db_all("SELECT * FROM bills WHERE date LIKE ? AND total<0", (f"{date_str}%",)):
            self.lb.insert("end", f' REFUND #{b["id"]} — {b["customer"]:<24} -{curr_sym()}{abs(float(b["total"])):>8.2f}')
        for e in db_all("SELECT * FROM expenses WHERE date=?", (date_str,)):
            self.lb.insert("end", f' Expense: {e["category"]:<29} -{curr_sym()}{e["amount"]:>8.2f}')
        self.lb.insert("end", "  " + "─" * 50)
        self.lb.insert("end", f' {"EXPECTED CLOSING":<36} {curr_sym()}{bal["closing"]:>10.2f}')

    def refresh(self):
        self.e_date.delete(0, "end")
        self.e_date.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.do_load()


class PurchaseOrdersView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Stock Orders", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Create Order", style="heading").pack(anchor="w", pady=(0, 8))
        make_label(fc, "Product", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_po_prod = make_combo(fc, width=24)
        self.cb_po_prod.set("Select...")
        self.cb_po_prod.pack(anchor="w")
        self.e_po_qty  = field_group(fc, "Qty to Order")
        self.e_po_qty.insert(0, "10")
        self.e_po_cost = field_group(fc, f"Unit Cost ({curr_sym()})")
        self.e_po_cost.insert(0, "0")
        self.e_po_supp = field_group(fc, "Supplier")
        self.e_po_note = field_group(fc, "Note")
        self.err_lbl   = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)
        make_label(fc, "Reorder Needed", style="warn").pack(anchor="w", pady=(4, 0))
        sug_lbf = tk.Frame(fc, bg=theme.card_bg)
        sug_lbf.pack(fill="x")
        self.sug_lb = tk.Listbox(sug_lbf, bg=theme.input_bg, fg=theme.warning, font=F_SMALL, height=5, relief="flat", bd=0, activestyle="none")
        self.sug_lb.pack(fill="x")

        make_button(fc, "Create Order",      self.do_create).pack(fill="x", pady=2)
        make_button(fc, "Mark Received",     self.do_receive,       color=theme.success).pack(fill="x", pady=2)
        make_button(fc, "Quick Reorder All", self.do_quick_reorder, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Cancel Order",      self.do_cancel,        color=theme.danger).pack(fill="x", pady=2)

        lc = make_card(cols, padx=14, pady=14)
        lc.pack(side="right", fill="both", expand=True)
        make_label(lc, "All Orders", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

    def do_create(self):
        idx = self.cb_po_prod.current()
        prods = db_all("SELECT * FROM products ORDER BY name")
        if idx < 0 or idx >= len(prods):
            self.err_lbl.config(text="Select a product.")
            return
        p = prods[idx]
        try:
            qty = int(self.e_po_qty.get())
            cost = float(self.e_po_cost.get())
        except ValueError:
            self.err_lbl.config(text="Qty=integer, Cost=number.")
            return
        db_run("INSERT INTO purchase_orders (date,product_id,product_name,qty_ordered,unit_cost,supplier,note) VALUES (?,?,?,?,?,?,?)",
               (datetime.date.today().strftime("%Y-%m-%d"), p["id"], p["name"], qty, cost, self.e_po_supp.get().strip(), self.e_po_note.get().strip()))
        for e in (self.e_po_qty, self.e_po_cost, self.e_po_supp, self.e_po_note):
            e.delete(0, "end")
        self.e_po_qty.insert(0, "10")
        self.err_lbl.config(text="")
        self.app.refresh_all()

    def do_receive(self):
        sel = self.lb.curselection()
        if not sel:
            return
        o = db_one("SELECT * FROM purchase_orders WHERE id=?", (self.lb_ids[sel[0]],))
        if not o:
            return
        if o["status"] != "Pending":
            messagebox.showinfo("Done", "Already processed.")
            return
        db_run("UPDATE purchase_orders SET status='Received' WHERE id=?", (self.lb_ids[sel[0]],))
        if o["product_id"]:
            db_run("UPDATE products SET quantity=quantity+? WHERE id=?", (o["qty_ordered"], o["product_id"]))
        self.app.refresh_all()
        messagebox.showinfo("Received", f"Stock +{o['qty_ordered']} {o['product_name']}")

    def do_cancel(self):
        sel = self.lb.curselection()
        if not sel:
            return
        if messagebox.askyesno("Cancel", "Cancel this order?"):
            db_run("UPDATE purchase_orders SET status='Cancelled' WHERE id=?", (self.lb_ids[sel[0]],))
            self.app.refresh_all()

    def do_quick_reorder(self):
        sugs = get_reorder_suggestions()
        if not sugs:
            messagebox.showinfo("Good", "No reorder needed.")
            return
        for p in sugs:
            db_run("INSERT INTO purchase_orders (date,product_id,product_name,qty_ordered,unit_cost,note) VALUES (?,?,?,?,?,?)",
                   (datetime.date.today().strftime("%Y-%m-%d"), p["id"], p["name"], 20, 0, "Auto-reorder"))
        messagebox.showinfo("Done", f"Created {len(sugs)} reorder(s).")
        self.app.refresh_all()

    def refresh(self, *_):
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        self.sug_lb.delete(0, "end")
        for p in get_reorder_suggestions():
            self.sug_lb.insert("end", f" {p['name']} — only {p['quantity']} left")
        self.cb_po_prod.configure(values=[p["name"] for p in db_all("SELECT name FROM products ORDER BY name")])
        status_map = {"Pending": "[...]", "Received": "[OK ]", "Cancelled": "[---]"}
        for o in db_all("SELECT * FROM purchase_orders ORDER BY id DESC"):
            self.lb.insert("end", f' {status_map.get(o["status"],"?")} #{o["id"]:<3} {o["date"]}  {o["product_name"]:<22} x{o["qty_ordered"]}  @{curr_sym()}{o["unit_cost"]:.0f}  {o.get("supplier","")[:16]}')
            self.lb_ids.append(o["id"])


class RefundsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Refunds & Returns", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        sf = make_card(self.frame, padx=16, pady=12)
        sf.pack(fill="x", pady=(0, 8))
        make_label(sf, "Find Bill to Refund", style="heading").pack(anchor="w", pady=(0, 6))
        sr = tk.Frame(sf, bg=theme.card_bg)
        sr.pack(fill="x")
        make_label(sr, "Bill # or Customer:", style="muted").pack(side="left")
        self.e_search = make_entry(sr, width=20)
        self.e_search.pack(side="left", padx=6)
        make_button(sr, "Search", self.do_search, color=theme.accent).pack(side="left", padx=4)
        make_label(sf, "Reason:", style="muted").pack(anchor="w", pady=(6, 1))
        self.e_reason = make_entry(sf, width=40)
        self.e_reason.pack(anchor="w")

        lc = make_card(self.frame, padx=14, pady=12)
        lc.pack(fill="both", expand=True)
        make_label(lc, "Results — select a bill then click Refund", style="muted").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

        hist_card = make_card(self.frame, padx=14, pady=10)
        hist_card.pack(fill="x", pady=(6, 0))
        make_label(hist_card, "Recent Refunds", style="heading").pack(anchor="w", pady=(0, 4))
        hist_lbf = tk.Frame(hist_card, bg=theme.card_bg)
        hist_lbf.pack(fill="x")
        self.hist_lb, self.hist_sb = make_listbox(hist_lbf, height=4)
        self.hist_lb.pack(side="left", fill="x", expand=True)
        self.hist_sb.pack(side="right", fill="y")

        make_button(lc, "Process Refund", self.do_refund, color=theme.danger).pack(anchor="w", pady=(6, 0))

    def do_search(self):
        q = self.e_search.get().strip().lower()
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        if not q:
            return
        for b in db_all("SELECT * FROM bills WHERE total>0 ORDER BY id DESC LIMIT 200"):
            if q in str(b["id"]) or q in b["customer"].lower():
                self.lb.insert("end", f' #{b["id"]:<4} {b["date"][:16]}  {b["customer"]:<22}  {curr_sym()}{b["total"]:.2f}  [{b.get("payment_mode","Cash")}]')
                self.lb_ids.append(b["id"])

    def do_refund(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showwarning("Select", "Select a bill first")
            return
        b = db_one("SELECT * FROM bills WHERE id=?", (self.lb_ids[sel[0]],))
        if not b:
            return
        reason = self.e_reason.get().strip() or "Customer return"
        if not messagebox.askyesno("Confirm", f'Refund Bill #{b["id"]} — {b["customer"]} — {curr_sym()}{b["total"]:.2f}?\nReason: {reason}'):
            return
        refund_id = db_run(
            "INSERT INTO bills (date,customer,customer_id,subtotal,discount,tax,total,note,coupon_code,staff_id,payment_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), b["customer"], b.get("customer_id"),
             -float(b["subtotal"]), b["discount"], b["tax"], -float(b["total"]),
             f"REFUND of Bill #{b['id']}: {reason}", "", b.get("staff_id", 0), b.get("payment_mode", "Cash"))
        )
        for it in db_all("SELECT * FROM bill_items WHERE bill_id=?", (b["id"],)):
            db_run("INSERT INTO bill_items (bill_id,product_id,name,price,qty) VALUES (?,?,?,?,?)",
                   (refund_id, it["product_id"], it["name"], it["price"], -it["qty"]))
            if it["product_id"]:
                db_run("UPDATE products SET quantity=quantity+? WHERE id=?", (it["qty"], it["product_id"]))
        if b.get("customer_id"):
            db_run("UPDATE customers SET total_spent=MAX(0,total_spent-?),visit_count=MAX(0,visit_count-1) WHERE id=?",
                   (float(b["total"]), b["customer_id"]))
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        self.app.refresh_all()
        messagebox.showinfo("Refunded", f"Refund #{refund_id} created.  -{curr_sym()}{b['total']:.2f}")

    def refresh(self):
        self.hist_lb.delete(0, "end")
        refunds = db_all("SELECT * FROM bills WHERE total<0 ORDER BY id DESC LIMIT 20")
        if not refunds:
            self.hist_lb.insert("end", "  No refunds yet.")
        for r in refunds:
            self.hist_lb.insert("end", f' #{r["id"]:<4} {r["date"][:16]}  {r["customer"]:<22}  {curr_sym()}{r["total"]:.2f}')

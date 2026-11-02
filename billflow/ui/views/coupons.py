import datetime
import tkinter as tk
from tkinter import messagebox
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, sep, field_group
from ...config import curr_sym
from ...database import db_all, db_one, db_run

class CouponsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Coupons", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Create Coupon", style="heading").pack(anchor="w", pady=(0, 8))
        
        self.e_code = field_group(fc, "Code (e.g. SAVE10)")
        make_label(fc, "Type", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_type = make_combo(fc, ["percent", "fixed"], width=22)
        self.cb_type.set("percent")
        self.cb_type.pack(anchor="w")
        
        self.e_val    = field_group(fc, f"Value (% or {curr_sym()})")
        self.e_minbil = field_group(fc, f"Min Bill ({curr_sym()})")
        self.e_minbil.insert(0, "0")
        self.e_expiry = field_group(fc, "Expiry (YYYY-MM-DD)")
        self.e_desc   = field_group(fc, "Description")
        self.err_lbl  = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)

        make_button(fc, "Create Coupon", self.do_add).pack(fill="x", pady=2)
        make_button(fc, "Toggle Active", self.do_toggle, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Delete",        self.do_del,    color=theme.danger).pack(fill="x", pady=2)

        lc = make_card(cols, padx=14, pady=14)
        lc.pack(side="right", fill="both", expand=True)
        make_label(lc, "All Coupons", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

    def do_add(self):
        code = self.e_code.get().strip().upper()
        if not code:
            self.err_lbl.config(text="Code required.")
            return
        try:
            val = float(self.e_val.get())
            minb = float(self.e_minbil.get())
        except ValueError:
            self.err_lbl.config(text="Value and min bill must be numbers.")
            return
        expiry = self.e_expiry.get().strip()
        if expiry:
            try:
                datetime.datetime.strptime(expiry, "%Y-%m-%d")
            except ValueError:
                self.err_lbl.config(text="Expiry: YYYY-MM-DD")
                return
        if db_one("SELECT id FROM coupons WHERE code=?", (code,)):
            self.err_lbl.config(text="Code already exists.")
            return
        db_run("INSERT INTO coupons (code,type,value,min_bill,expiry,description) VALUES (?,?,?,?,?,?)",
               (code, self.cb_type.get(), val, minb, expiry, self.e_desc.get().strip()))
        for e in (self.e_code, self.e_val, self.e_minbil, self.e_expiry, self.e_desc):
            e.delete(0, "end")
        self.e_minbil.insert(0, "0")
        self.err_lbl.config(text="")
        self.app.refresh_all()

    def do_toggle(self):
        sel = self.lb.curselection()
        if not sel:
            return
        cid = self.lb_ids[sel[0]]
        c = db_one("SELECT active FROM coupons WHERE id=?", (cid,))
        if c:
            db_run("UPDATE coupons SET active=? WHERE id=?", (0 if c["active"] else 1, cid))
            self.app.refresh_all()

    def do_del(self):
        sel = self.lb.curselection()
        if not sel:
            return
        if messagebox.askyesno("Delete", "Delete this coupon?"):
            db_run("DELETE FROM coupons WHERE id=?", (self.lb_ids[sel[0]],))
            self.app.refresh_all()

    def refresh(self, *_):
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        for c in db_all("SELECT * FROM coupons ORDER BY id DESC"):
            status = "[ON]" if c["active"] else "[OFF]"
            typ = "%" if c["type"] == "percent" else curr_sym()
            self.lb.insert("end",
                f' {status} {c["code"]:<12} {typ}{c["value"]:<7.1f} min {curr_sym()}{c["min_bill"]:<6.0f} exp:{c["expiry"] or "none":<12} used:{c["usage_count"]}')
            self.lb_ids.append(c["id"])

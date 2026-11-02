import tkinter as tk
from tkinter import messagebox
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, sep, field_group
from ..dialogs import edit_customer_dialog
from ...config import curr_sym
from ...database import db_all, db_one, db_run
from ...utils import validate_phone, validate_email
from ...analytics import auto_tag_customer

class CustomersView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Customers", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Add Customer", style="heading").pack(anchor="w", pady=(0, 8))

        self.e_name  = field_group(fc, "Full Name *")
        self.e_phone = field_group(fc, "Phone (10 digits)")
        self.e_email = field_group(fc, "Email Address")
        self.e_age   = field_group(fc, "Age")
        
        make_label(fc, "Gender", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_gender = make_combo(fc, ["Male", "Female", "Other", "Prefer not to say"], width=22)
        self.cb_gender.set("Prefer not to say")
        self.cb_gender.pack(anchor="w")

        make_label(fc, "Tag", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_tag = make_combo(fc, ["Regular", "Frequent", "VIP", "Inactive", "First-time"], width=22)
        self.cb_tag.set("Regular")
        self.cb_tag.pack(anchor="w")

        self.err_lbl = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)

        make_button(fc, "Add Customer",   self.do_add).pack(fill="x", pady=2)
        make_button(fc, "Edit Selected",  self.do_edit, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Delete Customer", self.do_del, color=theme.danger).pack(fill="x", pady=2)

        lc = make_card(cols, padx=14, pady=14)
        lc.pack(side="right", fill="both", expand=True)
        sf = tk.Frame(lc, bg=theme.card_bg)
        sf.pack(fill="x", pady=(0, 6))
        make_label(sf, "Search:", style="muted").pack(side="left", padx=(0, 6))

        self.sv = tk.StringVar()
        se = make_entry(sf)
        se.configure(textvariable=self.sv)
        se.pack(side="left", fill="x", expand=True)

        make_label(lc, "Customer Directory", style="heading").pack(anchor="w", pady=(0, 4))
        lbf = tk.Frame(lc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.lb_ids: list = []

        self.sv.trace_add("write", lambda *_: self.refresh())
        self.lb.bind("<Double-Button-1>", lambda e: self.do_edit())

    def do_add(self):
        name = self.e_name.get().strip()
        if not name:
            self.err_lbl.config(text="Customer name required.")
            return
        phone = self.e_phone.get().strip()
        if phone:
            perr = validate_phone(phone)
            if perr:
                self.err_lbl.config(text=perr)
                return
        email = self.e_email.get().strip()
        if email:
            eerr = validate_email(email)
            if eerr:
                self.err_lbl.config(text=eerr)
                return
        age_raw = self.e_age.get().strip()
        try:
            age_val = int(age_raw) if age_raw else None
        except ValueError:
            self.err_lbl.config(text="Age must be a number.")
            return

        self.err_lbl.config(text="")
        cid = db_run(
            "INSERT INTO customers (name,phone,email,age,gender,tag) VALUES (?,?,?,?,?,?)",
            (name, phone or None, email or None, age_val, self.cb_gender.get(), self.cb_tag.get())
        )
        auto_tag_customer(cid)
        for e in (self.e_name, self.e_phone, self.e_email, self.e_age):
            e.delete(0, "end")
        self.app.refresh_all()

    def do_del(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showwarning("Select", "Select a customer first")
            return
        cid = self.lb_ids[sel[0]]
        c = db_one("SELECT name FROM customers WHERE id=?", (cid,))
        if c and messagebox.askyesno("Delete", f'Delete customer "{c["name"]}"?'):
            db_run("DELETE FROM customers WHERE id=?", (cid,))
            self.app.refresh_all()

    def do_edit(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showwarning("Select", "Select a customer to edit")
            return
        edit_customer_dialog(self.frame, self.lb_ids[sel[0]], self.app.refresh_all)

    def refresh(self, *_):
        q = self.sv.get().lower()
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        for c in db_all("SELECT * FROM customers ORDER BY name"):
            row_str = f' #{str(c["id"]):<4} {c["name"]:<22}| {c.get("phone","") or "—":<12}| {curr_sym()}{c.get("total_spent",0):<8.2f}| {c.get("tag","Regular")}'
            if q and q not in row_str.lower():
                continue
            self.lb.insert("end", row_str)
            self.lb_ids.append(c["id"])

import datetime
import tkinter as tk
from tkinter import messagebox
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, sep, field_group
from ..dialogs import edit_product_dialog
from ...config import curr_sym
from ...database import db_all, db_one, db_run

class ProductsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        
        make_label(self.frame, "Products", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 10))
        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)

        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Add Product", style="heading").pack(anchor="w", pady=(0, 8))
        
        self.e_name  = field_group(fc, "Product Name *")
        self.e_price = field_group(fc, f"Price ({curr_sym()})")
        self.e_qty   = field_group(fc, "Stock Qty")
        self.e_qty.insert(0, "1")
        self.e_cat   = field_group(fc, "Category")
        self.e_hsn   = field_group(fc, "HSN Code")
        
        make_label(fc, "GST Rate (%)", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_gst = make_combo(fc, ["0", "5", "12", "18", "28"], width=22)
        self.cb_gst.set("18")
        self.cb_gst.pack(anchor="w")
        
        self.err_lbl = make_label(fc, "", style="danger")
        self.err_lbl.pack(anchor="w", pady=(4, 0))
        sep(fc)

        make_button(fc, "Add Product",      self.do_add).pack(fill="x", pady=2)
        make_button(fc, "Edit Selected",    self.do_edit, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Toggle Favourite", self.do_fav,  color="#7b5ea7").pack(fill="x", pady=2)
        make_button(fc, "Delete Selected",  self.do_del,  color=theme.danger).pack(fill="x", pady=2)

        lc = make_card(cols, padx=14, pady=14)
        lc.pack(side="right", fill="both", expand=True)
        sf = tk.Frame(lc, bg=theme.card_bg)
        sf.pack(fill="x", pady=(0, 6))
        make_label(sf, "Search:", style="muted").pack(side="left", padx=(0, 6))
        
        self.sv = tk.StringVar()
        se = make_entry(sf)
        se.configure(textvariable=self.sv)
        se.pack(side="left", fill="x", expand=True)
        
        make_label(lc, "Inventory", style="heading").pack(anchor="w", pady=(0, 4))
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
            self.err_lbl.config(text="Product name required.")
            return
        try:
            price = float(self.e_price.get())
            qty = int(self.e_qty.get())
            gst_r = float(self.cb_gst.get())
        except ValueError:
            self.err_lbl.config(text="Price=number, Qty=integer.")
            return
        if price < 0 or qty < 0:
            self.err_lbl.config(text="Must be non-negative.")
            return
            
        self.err_lbl.config(text="")
        db_run("INSERT INTO products (name,price,quantity,category,hsn_code,gst_rate) VALUES (?,?,?,?,?,?)",
               (name, price, qty, self.e_cat.get().strip() or "General", self.e_hsn.get().strip(), gst_r))
        for e in (self.e_name, self.e_price, self.e_cat, self.e_hsn):
            e.delete(0, "end")
        self.e_qty.delete(0, "end")
        self.e_qty.insert(0, "1")
        self.app.refresh_all()

    def do_del(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showwarning("Select", "Select a product first")
            return
        pid = self.lb_ids[sel[0]]
        p = db_one("SELECT name FROM products WHERE id=?", (pid,))
        if p and messagebox.askyesno("Delete", f'Delete "{p["name"]}"?'):
            db_run("DELETE FROM products WHERE id=?", (pid,))
            self.app.refresh_all()

    def do_edit(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showwarning("Select", "Select a product to edit")
            return
        edit_product_dialog(self.frame, self.lb_ids[sel[0]], self.app.refresh_all)

    def do_fav(self):
        sel = self.lb.curselection()
        if not sel:
            return
        pid = self.lb_ids[sel[0]]
        if db_one("SELECT id FROM favorites WHERE product_id=?", (pid,)):
            db_run("DELETE FROM favorites WHERE product_id=?", (pid,))
        else:
            db_run("INSERT INTO favorites (product_id, added_on) VALUES (?,?)",
                   (pid, datetime.datetime.now().strftime("%Y-%m-%d")))
        self.app.refresh_all()

    def refresh(self, *_):
        q = self.sv.get().lower()
        self.lb.delete(0, "end")
        self.lb_ids.clear()
        fav_ids = {r["product_id"] for r in db_all("SELECT product_id FROM favorites")}
        for p in db_all("SELECT * FROM products ORDER BY name"):
            if q and q not in p["name"].lower() and q not in p.get("category", "").lower():
                continue
            flag = " [LOW]" if p.get("quantity", 0) < 5 else ""
            star = "*" if p["id"] in fav_ids else " "
            self.lb.insert("end",
                f' {star} #{str(p["id"]):<4} {p["name"]:<22}| {curr_sym()}{p["price"]:<9.2f}| Qty:{p["quantity"]:<5}| {p.get("category","General")}{flag}')
            self.lb_ids.append(p["id"])

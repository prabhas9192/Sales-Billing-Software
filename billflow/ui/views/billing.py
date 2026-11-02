import datetime
import tkinter as tk
from tkinter import messagebox
from ..theme import theme
from ..widgets import make_card, make_label, make_entry, make_button, make_combo, make_listbox, sep, field_group
from ..dialogs import format_receipt, save_and_open_receipt, center_window
from ...config import curr_sym, F_SMALL
from ...database import db_all, db_one, db_run, db_runmany
from ...utils import clamp_discount, clamp_tax, rnd
from ...analytics import validate_coupon, auto_suggest_coupon, auto_tag_customer

class BillingView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)
        self.current_bill: list[dict] = []
        self.last_saved_bill: list[dict] = []

        hdr = tk.Frame(self.frame, bg=theme.bg)
        hdr.pack(fill="x", pady=(0, 6))
        make_label(hdr, "New Bill", style="title", bg=theme.bg).pack(side="left")
        tk.Label(hdr, text="Ctrl+S Save  |  Ctrl+P Print  |  Ctrl+Z Clear",
                 bg=theme.bg, fg=theme.muted, font=("Segoe UI", 8)).pack(side="right", padx=4)

        cols = tk.Frame(self.frame, bg=theme.bg)
        cols.pack(fill="both", expand=True)
        fc = make_card(cols, padx=18, pady=16)
        fc.pack(side="left", fill="y", padx=(0, 8))
        make_label(fc, "Build Bill", style="heading").pack(anchor="w", pady=(0, 8))

        make_label(fc, "Customer", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_customer = make_combo(fc, width=26)
        self.cb_customer.set("Walk-in")
        self.cb_customer.pack(anchor="w")

        make_label(fc, "Served By", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_staff = make_combo(fc, width=26)
        self.cb_staff.set("—")
        self.cb_staff.pack(anchor="w")

        make_label(fc, "Product", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_product = make_combo(fc, width=26)
        self.cb_product.set("Select product…")
        self.cb_product.pack(anchor="w")

        self.e_qty      = field_group(fc, "Quantity")
        self.e_qty.insert(0, "1")
        self.e_discount = field_group(fc, "Discount (%)")
        self.e_discount.insert(0, "0")
        self.e_tax      = field_group(fc, "Tax (%)")
        self.e_tax.insert(0, "18")
        self.e_note     = field_group(fc, "Bill Note")

        make_label(fc, "Payment Mode", style="muted").pack(anchor="w", pady=(5, 1))
        self.cb_payment = make_combo(fc, ["Cash", "UPI", "Card", "Credit", "Other"], width=26)
        self.cb_payment.set("Cash")
        self.cb_payment.pack(anchor="w")

        make_label(fc, "Coupon Code", style="muted").pack(anchor="w", pady=(5, 1))
        coupon_row = tk.Frame(fc, bg=theme.card_bg)
        coupon_row.pack(anchor="w", fill="x")
        self.e_coupon = make_entry(coupon_row, width=16)
        self.e_coupon.pack(side="left")
        self.coupon_msg = tk.Label(coupon_row, text="", bg=theme.card_bg, fg=theme.success, font=F_SMALL, wraplength=160)
        self.coupon_msg.pack(side="left", padx=(6, 0))
        sep(fc)

        self.suggest_lbl = tk.Label(fc, text="", bg=theme.card_bg, fg=theme.warning, font=F_SMALL, wraplength=200, justify="left")
        self.suggest_lbl.pack(anchor="w", pady=(0, 4))

        rc = make_card(cols, padx=14, pady=14)
        rc.pack(side="right", fill="both", expand=True)
        make_label(rc, "Bill Preview", style="heading").pack(anchor="w", pady=(0, 6))
        lbf = tk.Frame(rc, bg=theme.card_bg)
        lbf.pack(fill="both", expand=True)
        self.lb, self.sb = make_listbox(lbf)
        self.lb.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        sep(rc, pady=5)

        self.v_sub  = tk.StringVar(value=f"Subtotal:      {curr_sym()}0.00")
        self.v_disc = tk.StringVar(value=f"Discount (0%): -{curr_sym()}0.00")
        self.v_tax  = tk.StringVar(value=f"Tax (18%):     +{curr_sym()}0.00")
        self.v_coup = tk.StringVar(value=f"Coupon:         {curr_sym()}0.00")
        self.v_tot  = tk.StringVar(value=f"Grand Total:   {curr_sym()}0.00")
        for var, col in [(self.v_sub, theme.muted), (self.v_disc, theme.warning), (self.v_tax, theme.muted), (self.v_coup, theme.success)]:
            tk.Label(rc, textvariable=var, bg=theme.card_bg, fg=col, font=F_SMALL, anchor="e").pack(fill="x")
        tk.Frame(rc, bg=theme.border, height=1).pack(fill="x", pady=3)
        tk.Label(rc, textvariable=self.v_tot, bg=theme.card_bg, fg=theme.success,
                 font=("Segoe UI", 12, "bold"), anchor="e").pack(fill="x")

        make_button(fc, "Add Item",        self.do_add_item).pack(fill="x", pady=2)
        make_button(fc, "Favourites",      self.do_add_favourite, color="#7b5ea7").pack(fill="x", pady=2)
        make_button(fc, "Repeat Last Bill", self.do_repeat_last, color=theme.muted).pack(fill="x", pady=2)
        make_button(fc, "Remove Item",      self.do_remove_item, color=theme.warning).pack(fill="x", pady=2)
        make_button(fc, "Save Bill",        self.do_save,        color=theme.success).pack(fill="x", pady=2)
        make_button(fc, "Print / Receipt",  self.do_print,       color=theme.accent).pack(fill="x", pady=2)
        make_button(fc, "Clear Bill",       self.do_clear,       color=theme.danger).pack(fill="x", pady=2)

        self.e_discount.bind("<KeyRelease>", lambda _: self.compute_total())
        self.e_tax.bind("<KeyRelease>",      lambda _: self.compute_total())
        self.e_coupon.bind("<KeyRelease>",   lambda _: self.compute_total())

        self.frame.bind_all("<Control-s>", lambda _: self.do_save())
        self.frame.bind_all("<Control-p>", lambda _: self.do_print())
        self.frame.bind_all("<Control-z>", lambda _: self.do_clear())

    def compute_total(self) -> float:
        subtotal   = sum(it["price"] * it["qty"] for it in self.current_bill)
        disc_pct   = clamp_discount(self.e_discount.get())
        tax_pct    = clamp_tax(self.e_tax.get())
        after_disc = subtotal * (1 - disc_pct / 100)
        pre_grand  = after_disc * (1 + tax_pct / 100)
        coupon_disc, cmsg = validate_coupon(self.e_coupon.get(), pre_grand)
        if cmsg:
            self.coupon_msg.config(text=cmsg, fg=theme.success if "off" in cmsg else theme.danger)
        else:
            self.coupon_msg.config(text="")
        grand = max(0.0, pre_grand - coupon_disc)
        self.v_sub.set(f"Subtotal:       {curr_sym()}{subtotal:.2f}")
        self.v_disc.set(f"Discount ({disc_pct:.0f}%):  -{curr_sym()}{subtotal - after_disc:.2f}")
        self.v_tax.set(f"Tax ({tax_pct:.0f}%):         +{curr_sym()}{after_disc * tax_pct / 100:.2f}")
        self.v_coup.set(f"Coupon:         -{curr_sym()}{coupon_disc:.2f}")
        self.v_tot.set(f"Grand Total:   {curr_sym()}{grand:.2f}")
        sug = auto_suggest_coupon(grand)
        self.suggest_lbl.config(text=sug)
        return grand

    def render_lb(self):
        self.lb.delete(0, "end")
        for it in self.current_bill:
            self.lb.insert("end", f' {it["name"]:<24} x{it["qty"]}  @{curr_sym()}{it["price"]:.2f} = {curr_sym()}{it["price"]*it["qty"]:.2f}')
        self.compute_total()

    def do_add_item(self):
        idx = self.cb_product.current()
        if idx < 0:
            messagebox.showwarning("Select", "Choose a product first")
            return
        try:
            qty = int(self.e_qty.get())
            if qty < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "Quantity must be a positive integer")
            return
        prods = db_all("SELECT * FROM products ORDER BY name")
        if idx >= len(prods):
            return
        p = prods[idx]
        existing_qty = next((it["qty"] for it in self.current_bill if it.get("product_id") == p["id"]), 0)
        if existing_qty + qty > (p.get("quantity") or 0):
            messagebox.showwarning("Stock", f'Only {p.get("quantity", 0)} in stock.')
            return
        for it in self.current_bill:
            if it["product_id"] == p["id"]:
                it["qty"] += qty
                self.render_lb()
                return
        self.current_bill.append({"product_id": p["id"], "name": p["name"], "price": float(p["price"]), "qty": qty})
        self.render_lb()

    def do_add_favourite(self):
        favs = db_all("SELECT p.* FROM products p JOIN favorites f ON p.id=f.product_id ORDER BY p.name")
        if not favs:
            messagebox.showinfo("Favourites", "No favourites yet.")
            return
        win = tk.Toplevel(self.frame)
        win.title("Favourites")
        win.geometry("360x300")
        win.configure(bg=theme.card_bg)
        center_window(win, self.frame, 360, 300)
        make_label(win, "Pick a favourite", style="heading", bg=theme.card_bg).pack(anchor="w", padx=14, pady=10)
        lbf2 = tk.Frame(win, bg=theme.card_bg)
        lbf2.pack(fill="both", expand=True, padx=10)
        lb2, sb2 = make_listbox(lbf2)
        lb2.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        for f in favs:
            lb2.insert("end", f' * {f["name"]:<24} {curr_sym()}{f["price"]:.2f}  Qty:{f["quantity"]}')
        def _pick():
            sel = lb2.curselection()
            if not sel:
                return
            p = favs[sel[0]]
            for it in self.current_bill:
                if it["product_id"] == p["id"]:
                    it["qty"] += 1
                    self.render_lb()
                    win.destroy()
                    return
            self.current_bill.append({"product_id": p["id"], "name": p["name"], "price": float(p["price"]), "qty": 1})
            self.render_lb()
            win.destroy()
        make_button(win, "Add to Bill", _pick, color=theme.success).pack(pady=8)
        lb2.bind("<Double-Button-1>", lambda _: _pick())

    def do_remove_item(self):
        sel = self.lb.curselection()
        if not sel:
            return
        self.current_bill.pop(sel[0])
        self.render_lb()

    def do_clear(self):
        if self.current_bill and not messagebox.askyesno("Clear", "Clear all items?"):
            return
        self.current_bill.clear()
        self.render_lb()

    def do_repeat_last(self):
        if not self.last_saved_bill:
            messagebox.showinfo("Repeat", "No previous bill.")
            return
        self.current_bill.clear()
        self.current_bill.extend([dict(it) for it in self.last_saved_bill])
        self.render_lb()

    def do_save(self):
        if not self.current_bill:
            messagebox.showwarning("Empty", "Add at least one item")
            return
        grand    = self.compute_total()
        subtotal = sum(it["price"] * it["qty"] for it in self.current_bill)
        disc_pct = clamp_discount(self.e_discount.get())
        tax_pct  = clamp_tax(self.e_tax.get())
        cust_txt = self.cb_customer.get() or "Walk-in"
        coupon   = self.e_coupon.get().strip().upper()
        cust_id  = None
        if cust_txt != "Walk-in":
            row = db_one("SELECT id FROM customers WHERE name=?", (cust_txt,))
            if row:
                cust_id = row["id"]
        staff_id_val = 0
        staff_sel = self.cb_staff.get()
        if staff_sel and staff_sel != "—":
            sr = db_one("SELECT id FROM staff WHERE name=?", (staff_sel,))
            if sr:
                staff_id_val = sr["id"]
        coupon_disc, _ = validate_coupon(coupon, grand) if coupon else (0.0, "")
        bill_id = db_run(
            "INSERT INTO bills (date,customer,customer_id,subtotal,discount,tax,total,note,coupon_code,staff_id,payment_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             cust_txt, cust_id, round(subtotal, 2), disc_pct, tax_pct, round(grand, 2),
             self.e_note.get().strip(), coupon, staff_id_val, self.cb_payment.get() or "Cash")
        )
        db_runmany("INSERT INTO bill_items (bill_id,product_id,name,price,qty) VALUES (?,?,?,?,?)",
                   [(bill_id, it["product_id"], it["name"], it["price"], it["qty"]) for it in self.current_bill])
        for it in self.current_bill:
            db_run("UPDATE products SET quantity=MAX(0,quantity-?) WHERE id=?", (it["qty"], it["product_id"]))
        if coupon:
            db_run("UPDATE coupons SET usage_count=usage_count+1 WHERE code=?", (coupon,))
        if cust_id:
            db_run("UPDATE customers SET total_spent=total_spent+?,visit_count=visit_count+1 WHERE id=?",
                   (rnd(float(grand), 2), cust_id))
            auto_tag_customer(cust_id)
        self.last_saved_bill.clear()
        self.last_saved_bill.extend([dict(it) for it in self.current_bill])
        self.current_bill.clear()
        self.render_lb()
        self.app.refresh_all()
        messagebox.showinfo("Saved", f"Bill #{bill_id} saved!  Total: {curr_sym()}{grand:.2f}")

    def do_print(self):
        if not self.current_bill:
            return
        grand = self.compute_total()
        coupon_disc, _ = validate_coupon(self.e_coupon.get(), grand)
        lines = format_receipt(
            bill_id="(preview)", date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            customer=self.cb_customer.get() or "Walk-in", items=self.current_bill,
            subtotal=sum(it["price"] * it["qty"] for it in self.current_bill),
            disc_pct=clamp_discount(self.e_discount.get()), tax_pct=clamp_tax(self.e_tax.get()),
            grand=grand, note=self.e_note.get().strip(),
            coupon=self.e_coupon.get().strip().upper(), coupon_disc=coupon_disc,
            payment_mode=self.cb_payment.get() or "Cash",
        )
        save_and_open_receipt(self.frame, lines)

    def refresh(self):
        # Update comboboxes
        prod_names = [p["name"] for p in db_all("SELECT name FROM products ORDER BY name")]
        self.cb_product.configure(values=prod_names)
        
        cust_names = ["Walk-in"] + [c["name"] for c in db_all("SELECT name FROM customers ORDER BY name")]
        self.cb_customer.configure(values=cust_names)
        
        staff_names = ["—"] + [s["name"] for s in db_all("SELECT name FROM staff WHERE active=1 ORDER BY name")]
        self.cb_staff.configure(values=staff_names)

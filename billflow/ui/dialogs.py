import os
import datetime
import textwrap
import tkinter as tk
from tkinter import ttk, messagebox
from .theme import theme
from .widgets import make_card, make_label, make_entry, make_button, make_combo, sep
from ..config import BASE_DIR, APP_SETTINGS, curr_sym, F_HEAD, F_SMALL, F_MONO
from ..database import db_one, db_run
from ..utils import validate_phone, validate_email, rnd

def center_window(win: tk.Toplevel, parent: tk.Misc, w: int, h: int):
    parent.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - w) // 2
    y = parent.winfo_y() + (parent.winfo_height() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

def edit_product_dialog(parent: tk.Misc, prod_id: int, on_save):
    p = db_one("SELECT * FROM products WHERE id=?", (prod_id,))
    if not p:
        return
    win = tk.Toplevel(parent)
    win.title(f"Edit Product #{prod_id}")
    win.configure(bg=theme.card_bg)
    win.resizable(False, False)
    win.grab_set()
    center_window(win, parent, 340, 360)

    pad = {"padx": 20, "pady": 4}
    make_label(win, f"Edit Product #{prod_id}", style="heading", bg=theme.card_bg).pack(anchor="w", padx=20, pady=(12, 4))
    sep(win)

    fields = [
        ("Product Name *", p["name"]),
        ("Price", str(p["price"])),
        ("Stock Qty", str(p["quantity"])),
        ("Category", p.get("category", "General")),
        ("HSN Code", p.get("hsn_code", "")),
        ("GST Rate (%)", str(p.get("gst_rate", 18)))
    ]
    entries = []
    for lbl, val in fields:
        make_label(win, lbl, style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
        e = make_entry(win, width=30)
        e.insert(0, str(val))
        e.pack(anchor="w", padx=20)
        entries.append(e)

    err_lbl = make_label(win, "", style="danger", bg=theme.card_bg)
    err_lbl.pack(anchor="w", padx=20, pady=(2, 0))

    def do_save():
        name = entries[0].get().strip()
        if not name:
            err_lbl.config(text="Name required.")
            return
        try:
            price = float(entries[1].get())
            qty = int(entries[2].get())
            gst_r = float(entries[5].get())
        except ValueError:
            err_lbl.config(text="Price/Qty/GST must be numbers.")
            return
        if price < 0 or qty < 0:
            err_lbl.config(text="Must be non-negative.")
            return

        db_run("UPDATE products SET name=?,price=?,quantity=?,category=?,hsn_code=?,gst_rate=? WHERE id=?",
               (name, price, qty, entries[3].get().strip() or "General",
                entries[4].get().strip(), gst_r, prod_id))
        on_save()
        win.destroy()

    bf = tk.Frame(win, bg=theme.card_bg)
    bf.pack(fill="x", padx=20, pady=(8, 14))
    make_button(bf, "Save", do_save, color=theme.success).pack(side="left", padx=(0, 6))
    make_button(bf, "Cancel", win.destroy, color=theme.danger).pack(side="left")

def edit_customer_dialog(parent: tk.Misc, cust_id: int, on_save):
    c = db_one("SELECT * FROM customers WHERE id=?", (cust_id,))
    if not c:
        return
    win = tk.Toplevel(parent)
    win.title(f"Edit Customer #{cust_id}")
    win.configure(bg=theme.card_bg)
    win.resizable(False, False)
    win.grab_set()
    center_window(win, parent, 360, 490)

    pad = {"padx": 20, "pady": 4}
    make_label(win, f"Edit Customer #{cust_id}", style="heading", bg=theme.card_bg).pack(anchor="w", padx=20, pady=(12, 4))
    sep(win)

    make_label(win, "Full Name *", style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
    e_name = make_entry(win, width=30)
    e_name.insert(0, str(c["name"] or ""))
    e_name.pack(anchor="w", padx=20)

    make_label(win, "Phone", style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
    e_phone = make_entry(win, width=30)
    e_phone.insert(0, str(c["phone"] or ""))
    e_phone.pack(anchor="w", padx=20)

    make_label(win, "Email", style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
    e_email = make_entry(win, width=30)
    e_email.insert(0, str(c["email"] or ""))
    e_email.pack(anchor="w", padx=20)

    make_label(win, "Age", style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
    e_age = make_entry(win, width=30)
    if c["age"]:
        e_age.insert(0, str(c["age"]))
    e_age.pack(anchor="w", padx=20)

    make_label(win, "Gender", style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
    cb_gender = make_combo(win, ["Male", "Female", "Other", "Prefer not to say"], width=28)
    cb_gender.pack(anchor="w", padx=20)
    if c["gender"]:
        cb_gender.set(c["gender"])

    make_label(win, "Tag", style="muted", bg=theme.card_bg).pack(anchor="w", **pad)
    cb_tag = make_combo(win, ["Regular", "Frequent", "VIP", "Inactive", "First-time"], width=28)
    cb_tag.set(c.get("tag") or "Regular")
    cb_tag.pack(anchor="w", padx=20)

    err_lbl = make_label(win, "", style="danger", bg=theme.card_bg)
    err_lbl.pack(anchor="w", padx=20, pady=4)

    def do_save():
        name = e_name.get().strip()
        if not name:
            err_lbl.config(text="Name required.")
            return
        phone = e_phone.get().strip()
        if phone:
            perr = validate_phone(phone)
            if perr:
                err_lbl.config(text=perr)
                return
        email = e_email.get().strip()
        if email:
            eerr = validate_email(email)
            if eerr:
                err_lbl.config(text=eerr)
                return
        age_raw = e_age.get().strip()
        try:
            age_val = int(age_raw) if age_raw else None
        except ValueError:
            err_lbl.config(text="Age must be a number.")
            return

        db_run("UPDATE customers SET name=?,phone=?,email=?,age=?,gender=?,tag=? WHERE id=?",
               (name, phone or None, email or None, age_val, cb_gender.get() or None,
                cb_tag.get() or "Regular", cust_id))
        on_save()
        win.destroy()

    bf = tk.Frame(win, bg=theme.card_bg)
    bf.pack(fill="x", padx=20, pady=(8, 14))
    make_button(bf, "Save", do_save, color=theme.success).pack(side="left", padx=(0, 6))
    make_button(bf, "Cancel", win.destroy, color=theme.danger).pack(side="left")

def format_receipt(bill_id, date, customer, items, subtotal, disc_pct, tax_pct, grand, note,
                   coupon="", coupon_disc=0.0, payment_mode="Cash") -> list[str]:
    w = 46
    shop = APP_SETTINGS.get("shop_name", "My Shop")
    phone = APP_SETTINGS.get("shop_phone", "")
    addr = APP_SETTINGS.get("shop_address", "")
    curr = curr_sym()
    header = [f"  {shop}"]
    if phone:
        header.append(f"  Tel: {phone}")
    if addr:
        header.append(f"  {addr}")
    lines = ["=" * w] + header + ["=" * w,
             f"  Bill #  : {bill_id}", f"  Date    : {date}", f"  Customer: {customer}",
             "-" * w, f"  {'ITEM':<22} {'QTY':>3}  {'UNIT':>7}  {'TOTAL':>8}", "-" * w]
    for it in items:
        name = textwrap.shorten(it["name"], width=22, placeholder="...")
        lines.append(f"  {name:<22} {it['qty']:>3}  {curr}{it['price']:>5.2f}  {curr}{it['price']*it['qty']:>6.2f}")
    subtotal = float(subtotal)
    disc_pct = float(disc_pct)
    tax_pct = float(tax_pct)
    after_disc = subtotal * (1 - disc_pct / 100)
    tax_amt = after_disc * tax_pct / 100
    grand = rnd(float(grand), 2)
    lines += ["-" * w, f"  {'Subtotal':<32} {curr}{subtotal:>6.2f}",
              f"  {'Discount ('+str(disc_pct)+'%)':<32}-{curr}{subtotal-after_disc:>5.2f}",
              f"  {'Tax ('+str(tax_pct)+'%)':<32}+{curr}{tax_amt:>5.2f}"]
    if coupon and coupon_disc > 0:
        lines.append(f"  {'Coupon ('+coupon+')':<32}-{curr}{coupon_disc:>5.2f}")
    lines += ["=" * w, f"  {'GRAND TOTAL':<32} {curr}{grand:>6.2f}", "=" * w]
    if note:
        lines += [f"  Note: {note}", "-" * w]
    lines += [f"  Payment: {payment_mode}", "", "     Thank you for your business!", ""]
    return lines

def save_and_open_receipt(parent: tk.Misc, lines: list[str]):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.join(BASE_DIR, "receipts"), exist_ok=True)
    path = os.path.join(BASE_DIR, "receipts", f"receipt_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    win = tk.Toplevel(parent)
    win.title("Receipt")
    win.geometry("520x460")
    win.configure(bg=theme.bg)
    tk.Label(win, text="Receipt Preview", bg=theme.bg, fg=theme.text, font=F_HEAD).pack(pady=(10, 4))
    tk.Label(win, text=f"Saved: {path}", bg=theme.bg, fg=theme.muted, font=F_SMALL, wraplength=480).pack()
    txt = tk.Text(win, bg=theme.input_bg, fg=theme.text, font=F_MONO, relief="flat", bd=8, wrap="none")
    txt.pack(fill="both", expand=True, padx=10, pady=6)
    txt.insert("end", "\n".join(lines))
    txt.config(state="disabled")
    make_button(win, "Close", win.destroy, color=theme.danger).pack(pady=(0, 8))

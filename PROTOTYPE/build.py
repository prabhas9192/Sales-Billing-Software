import tkinter as tk
from tkinter import ttk, messagebox
import json, os, datetime, csv, textwrap
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ─────────────────────────── Paths ───────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_PRODUCTS  = os.path.join(BASE_DIR, "products.json")
DATA_CUSTOMERS = os.path.join(BASE_DIR, "customers.json")
DATA_BILLS     = os.path.join(BASE_DIR, "bills.json")

# ─────────────────────────── Data I/O ────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ─────────────────────────── App State ───────────────────────
class AppState:
    def __init__(self):
        self.products  = load_json(DATA_PRODUCTS,  [])
        self.customers = load_json(DATA_CUSTOMERS, [])
        self.bills     = load_json(DATA_BILLS,     [])
        self.current_bill: list[dict] = []

    def next_bill_id(self):
        if not self.bills:
            return 1
        return max(b.get("id", 0) for b in self.bills) + 1

    def save_products(self):  save_json(DATA_PRODUCTS,  self.products)
    def save_customers(self): save_json(DATA_CUSTOMERS, self.customers)
    def save_bills(self):     save_json(DATA_BILLS,     self.bills)

state = AppState()

# ─────────────────────────── Theme ───────────────────────────
BG         = "#1c1c27"
SIDEBAR_BG = "#14141e"
CARD_BG    = "#24243a"
ACCENT     = "#6c63ff"
DANGER     = "#ff5c5c"
SUCCESS    = "#43e97b"
WARNING    = "#f9c74f"
TEXT       = "#e0e0f0"
MUTED      = "#7878a0"
INPUT_BG   = "#2e2e48"
BORDER     = "#33334d"

F_TITLE  = ("Segoe UI", 18, "bold")
F_HEAD   = ("Segoe UI", 12, "bold")
F_BODY   = ("Segoe UI", 10)
F_SMALL  = ("Segoe UI",  9)
F_MONO   = ("Consolas", 10)

# ─────────────────────────── Widget Helpers ──────────────────
def make_card(parent, **kw):
    kw.setdefault("bg", CARD_BG)
    kw.setdefault("highlightbackground", BORDER)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("relief", "flat")
    return tk.Frame(parent, **kw)

def make_label(parent, text, style="body", bg=None, **kw):
    cfg = {
        "title":   dict(fg=TEXT,    font=F_TITLE),
        "heading": dict(fg=TEXT,    font=F_HEAD),
        "body":    dict(fg=TEXT,    font=F_BODY),
        "muted":   dict(fg=MUTED,   font=F_SMALL),
        "accent":  dict(fg=ACCENT,  font=F_BODY),
        "success": dict(fg=SUCCESS, font=F_BODY),
        "warn":    dict(fg=WARNING, font=F_BODY),
        "danger":  dict(fg=DANGER,  font=F_BODY),
        "mono":    dict(fg=TEXT,    font=F_MONO),
    }[style]
    cfg["bg"] = bg or CARD_BG
    cfg.update(kw)
    return tk.Label(parent, text=text, **cfg)

def make_entry(parent, width=20, **kw):
    kw.setdefault("bg", INPUT_BG)
    kw.setdefault("fg", TEXT)
    kw.setdefault("insertbackground", ACCENT)
    kw.setdefault("relief", "flat")
    kw.setdefault("font", F_BODY)
    kw.setdefault("bd", 5)
    return tk.Entry(parent, width=width, **kw)

def make_button(parent, text, command, color=ACCENT, **kw):
    btn = tk.Button(
        parent, text=text, command=command,
        bg=color, fg="white", font=F_BODY,
        relief="flat", bd=0, padx=12, pady=6,
        activebackground=color, activeforeground="white",
        cursor="hand2", **kw
    )
    def _enter(e): btn.config(bg=_shade(color, -25))
    def _leave(e): btn.config(bg=color)
    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)
    return btn

def _shade(hex_color, delta):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    r, g, b = (max(0,min(255,v+delta)) for v in (r,g,b))
    return f"#{r:02x}{g:02x}{b:02x}"

def make_combo(parent, values=(), width=20, **kw):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("App.TCombobox",
        fieldbackground=INPUT_BG, background=INPUT_BG,
        foreground=TEXT, selectbackground=ACCENT,
        selectforeground="white", bordercolor=BORDER,
        arrowcolor=ACCENT)
    cb = ttk.Combobox(parent, values=list(values), width=width,
                      state="readonly", style="App.TCombobox", **kw)
    return cb

def make_listbox(container, **kw):
    """Returns (listbox, scrollbar) — caller must pack both."""
    kw.setdefault("bg", INPUT_BG)
    kw.setdefault("fg", TEXT)
    kw.setdefault("selectbackground", ACCENT)
    kw.setdefault("selectforeground", "white")
    kw.setdefault("font", F_MONO)
    kw.setdefault("relief", "flat")
    kw.setdefault("bd", 0)
    kw.setdefault("activestyle", "none")
    kw.setdefault("highlightbackground", BORDER)
    kw.setdefault("highlightthickness", 1)
    lb = tk.Listbox(container, **kw)
    sb = ttk.Scrollbar(container, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=sb.set)
    return lb, sb

def sep(parent, bg=BORDER, pady=8):
    tk.Frame(parent, bg=bg, height=1).pack(fill="x", pady=pady)

def field_group(parent, label_text):
    """Returns (outer_frame, entry) — label + entry stacked."""
    make_label(parent, label_text, style="muted").pack(anchor="w", pady=(6,1))
    e = make_entry(parent, width=24)
    e.pack(anchor="w")
    return e

def stat_tile(parent, title, var, color=ACCENT):
    c = make_card(parent, padx=16, pady=12)
    c.pack(side="left", fill="both", expand=True, padx=6)
    make_label(c, title, style="muted").pack(anchor="w")
    tk.Label(c, textvariable=var, bg=CARD_BG, fg=color,
             font=("Segoe UI", 20, "bold")).pack(anchor="w")
    return c

# ─────────────────────────── Root ────────────────────────────
root = tk.Tk()
root.title("BillFlow — Sales Billing")
root.geometry("1120x700")
root.minsize(900, 600)
root.configure(bg=BG)

# ─────────────────────────── Layout ──────────────────────────
sidebar = tk.Frame(root, bg=SIDEBAR_BG, width=200)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

workspace = tk.Frame(root, bg=BG)
workspace.pack(side="right", fill="both", expand=True)

frames: dict[str, tk.Frame] = {}
nav_buttons: list[tuple[tk.Button, str]] = []

# ─────────────────────────── Navigation ──────────────────────
def navigate(page_name: str):
    for f in frames.values():
        f.pack_forget()
    frames[page_name].pack(fill="both", expand=True, padx=18, pady=18)
    for btn, name in nav_buttons:
        btn.config(bg=SIDEBAR_BG if name != page_name else "#2a2a42",
                   fg=MUTED      if name != page_name else TEXT)
    refresh_all()

def nav_btn(label, icon, page):
    def _click(): navigate(page)
    btn = tk.Button(
        sidebar, text=f"  {icon}  {label}",
        bg=SIDEBAR_BG, fg=MUTED, font=F_BODY,
        relief="flat", bd=0, anchor="w", padx=10, pady=10,
        activebackground="#2a2a42", activeforeground=TEXT,
        cursor="hand2", command=_click
    )
    btn.pack(fill="x", padx=6, pady=1)
    nav_buttons.append((btn, page))
    return btn

# Sidebar logo
lf = tk.Frame(sidebar, bg=SIDEBAR_BG)
lf.pack(fill="x", pady=(22,14), padx=14)
tk.Label(lf, text="⚡ BillFlow", bg=SIDEBAR_BG, fg=ACCENT,
         font=("Segoe UI", 14, "bold")).pack(anchor="w")
tk.Label(lf, text="Sales Manager", bg=SIDEBAR_BG, fg=MUTED,
         font=F_SMALL).pack(anchor="w")
tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=12, pady=4)

nav_btn("Dashboard", "▣", "dashboard")
nav_btn("New Bill",  "＋", "bill")
nav_btn("Products",  "◈", "products")
nav_btn("Customers", "◉", "customers")
nav_btn("Reports",   "◎", "reports")

tk.Label(sidebar, text="v2.0", bg=SIDEBAR_BG, fg=MUTED,
         font=F_SMALL).pack(side="bottom", pady=10)

# ═══════════════════════ DASHBOARD ═══════════════════════════
def build_dashboard():
    frame = tk.Frame(workspace, bg=BG)
    frames["dashboard"] = frame

    # Header
    hdr = tk.Frame(frame, bg=BG)
    hdr.pack(fill="x", pady=(0,12))
    make_label(hdr, "Dashboard", style="title", bg=BG).pack(side="left")
    make_label(hdr, datetime.datetime.now().strftime("%A, %d %B %Y"),
               style="muted", bg=BG).pack(side="right", padx=4)

    # Stat tiles
    tiles_row = tk.Frame(frame, bg=BG)
    tiles_row.pack(fill="x", pady=(0,12))
    v_prods = tk.StringVar(value="0")
    v_custs = tk.StringVar(value="0")
    v_bills = tk.StringVar(value="0")
    v_rev   = tk.StringVar(value="$0.00")
    stat_tile(tiles_row, "Products",    v_prods, ACCENT)
    stat_tile(tiles_row, "Customers",   v_custs, SUCCESS)
    stat_tile(tiles_row, "Bills",       v_bills, WARNING)
    stat_tile(tiles_row, "Revenue",     v_rev,   DANGER)

    # Chart
    chart_card = make_card(frame, padx=16, pady=14)
    chart_card.pack(fill="both", expand=True)
    make_label(chart_card, "Bills per Customer", style="heading").pack(anchor="w", pady=(0,8))

    fig = Figure(figsize=(7, 3.2), dpi=96, facecolor=CARD_BG)
    ax  = fig.add_subplot(111)
    ax.set_facecolor(CARD_BG)
    fig.subplots_adjust(bottom=0.22, left=0.04, right=0.98, top=0.88)
    canv = FigureCanvasTkAgg(fig, master=chart_card)
    canv.get_tk_widget().configure(bg=CARD_BG, highlightthickness=0)
    canv.get_tk_widget().pack(fill="both", expand=True)

    return frame, v_prods, v_custs, v_bills, v_rev, ax, canv

_dash, _v_prods, _v_custs, _v_bills, _v_rev, _ax, _canv = build_dashboard()

# ═══════════════════════ PRODUCTS ════════════════════════════
def build_products():
    frame = tk.Frame(workspace, bg=BG)
    frames["products"] = frame

    make_label(frame, "Products", style="title", bg=BG).pack(anchor="w", pady=(0,12))

    cols = tk.Frame(frame, bg=BG)
    cols.pack(fill="both", expand=True)

    # ── Form card ──
    fc = make_card(cols, padx=20, pady=18)
    fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Add Product", style="heading").pack(anchor="w", pady=(0,8))

    e_name  = field_group(fc, "Product Name *")
    e_price = field_group(fc, "Price")
    e_qty   = field_group(fc, "Stock Qty"); e_qty.insert(0, "1")
    e_cat   = field_group(fc, "Category")

    sep(fc)

    def do_add():
        name = e_name.get().strip()
        if not name:
            messagebox.showerror("Missing", "Product name is required"); return
        try:
            price = float(e_price.get())
            qty   = int(e_qty.get())
        except ValueError:
            messagebox.showerror("Invalid", "Price must be a number; Qty must be an integer"); return
        cat = e_cat.get().strip() or "General"
        state.products.append({"name": name, "price": price, "quantity": qty, "category": cat})
        state.save_products()
        for e in (e_name, e_price, e_cat): e.delete(0, "end")
        e_qty.delete(0, "end"); e_qty.insert(0, "1")
        refresh_all()

    def do_del():
        sel = lb.curselection()
        if not sel: messagebox.showwarning("Select", "Select a product first"); return
        idx = lb.get(sel[0]).split("|")[0].strip()
        real_idx = next((i for i, p in enumerate(state.products)
                         if p["name"] == idx), None)
        if real_idx is None: return
        if messagebox.askyesno("Delete", f'Delete "{state.products[real_idx]["name"]}"?'):
            state.products.pop(real_idx)
            state.save_products()
            refresh_all()

    make_button(fc, "＋  Add Product",    do_add).pack(fill="x", pady=2)
    make_button(fc, "🗑  Delete Selected", do_del, color=DANGER).pack(fill="x", pady=2)

    # ── List card ──
    lc = make_card(cols, padx=16, pady=16)
    lc.pack(side="right", fill="both", expand=True)

    # Search bar
    sf = tk.Frame(lc, bg=CARD_BG)
    sf.pack(fill="x", pady=(0,8))
    make_label(sf, "Search:", style="muted").pack(side="left", padx=(0,6))
    sv = tk.StringVar()
    se = make_entry(sf); se.configure(textvariable=sv); se.pack(side="left", fill="x", expand=True)

    make_label(lc, "Inventory", style="heading").pack(anchor="w", pady=(0,6))

    lbf = tk.Frame(lc, bg=CARD_BG)
    lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def refresh_lb(*_):
        q = sv.get().lower()
        lb.delete(0, "end")
        for p in state.products:
            if q and q not in p["name"].lower() and q not in p.get("category","").lower():
                continue
            flag = "  ⚠ LOW" if p.get("quantity", 0) < 5 else ""
            lb.insert("end", f'{p["name"]:<26}| ₹{p["price"]:<9.2f}| Qty:{p["quantity"]:<5}| {p.get("category","General")}{flag}')

    sv.trace("w", refresh_lb)
    return frame, refresh_lb

_prod_frame, _refresh_prod_lb = build_products()

# ═══════════════════════ CUSTOMERS ═══════════════════════════
def build_customers():
    frame = tk.Frame(workspace, bg=BG)
    frames["customers"] = frame

    make_label(frame, "Customers", style="title", bg=BG).pack(anchor="w", pady=(0,12))

    cols = tk.Frame(frame, bg=BG)
    cols.pack(fill="both", expand=True)

    fc = make_card(cols, padx=20, pady=18)
    fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Add Customer", style="heading").pack(anchor="w", pady=(0,8))

    e_name  = field_group(fc, "Full Name *")
    e_phone = field_group(fc, "Phone")
    e_email = field_group(fc, "Email")
    e_age   = field_group(fc, "Age")

    make_label(fc, "Gender", style="muted").pack(anchor="w", pady=(6,1))
    cb_gender = make_combo(fc, ["Male","Female","Other","Prefer not to say"], width=22)
    cb_gender.pack(anchor="w")

    sep(fc)

    def do_add():
        name = e_name.get().strip()
        if not name: messagebox.showerror("Missing", "Name is required"); return
        age_raw = e_age.get().strip()
        try:
            age_val = int(age_raw) if age_raw else None
        except ValueError:
            messagebox.showerror("Invalid", "Age must be a whole number"); return
        gender = cb_gender.get() or None
        state.customers.append({
            "name": name, "phone": e_phone.get().strip(),
            "email": e_email.get().strip(),
            "age": age_val, "gender": gender
        })
        state.save_customers()
        for e in (e_name, e_phone, e_email, e_age): e.delete(0, "end")
        cb_gender.set("")
        refresh_all()

    def do_del():
        sel = lb.curselection()
        if not sel: messagebox.showwarning("Select", "Select a customer first"); return
        name_field = lb.get(sel[0]).split("|")[0].strip()
        idx = next((i for i, c in enumerate(state.customers)
                    if c["name"] == name_field), None)
        if idx is None: return
        if messagebox.askyesno("Delete", f'Delete customer "{state.customers[idx]["name"]}"?'):
            state.customers.pop(idx)
            state.save_customers()
            refresh_all()

    make_button(fc, "＋  Add Customer",   do_add).pack(fill="x", pady=2)
    make_button(fc, "🗑  Delete Selected", do_del, color=DANGER).pack(fill="x", pady=2)

    lc = make_card(cols, padx=16, pady=16)
    lc.pack(side="right", fill="both", expand=True)

    sf = tk.Frame(lc, bg=CARD_BG)
    sf.pack(fill="x", pady=(0,8))
    make_label(sf, "Search:", style="muted").pack(side="left", padx=(0,6))
    sv = tk.StringVar()
    se = make_entry(sf); se.configure(textvariable=sv); se.pack(side="left", fill="x", expand=True)

    make_label(lc, "Directory", style="heading").pack(anchor="w", pady=(0,6))

    lbf = tk.Frame(lc, bg=CARD_BG)
    lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def refresh_lb(*_):
        q = sv.get().lower()
        lb.delete(0, "end")
        for c in state.customers:
            if q and q not in c["name"].lower() and q not in c.get("phone","").lower():
                continue
            age_str = f"Age:{c['age']}" if c.get("age") else ""
            lb.insert("end", f'{c["name"]:<26}| {c.get("phone",""):<16}| {age_str}')

    sv.trace("w", refresh_lb)
    return frame, refresh_lb

_cust_frame, _refresh_cust_lb = build_customers()

# ═══════════════════════ NEW BILL ════════════════════════════
def build_bill():
    frame = tk.Frame(workspace, bg=BG)
    frames["bill"] = frame

    make_label(frame, "New Bill", style="title", bg=BG).pack(anchor="w", pady=(0,12))

    cols = tk.Frame(frame, bg=BG)
    cols.pack(fill="both", expand=True)

    # ── Controls ──
    fc = make_card(cols, padx=20, pady=18)
    fc.pack(side="left", fill="y", padx=(0,8))
    make_label(fc, "Build Bill", style="heading").pack(anchor="w", pady=(0,8))

    make_label(fc, "Customer", style="muted").pack(anchor="w", pady=(6,1))
    cb_customer = make_combo(fc, width=24)
    cb_customer.set("Walk-in")
    cb_customer.pack(anchor="w")

    make_label(fc, "Product", style="muted").pack(anchor="w", pady=(6,1))
    cb_product = make_combo(fc, width=24)
    cb_product.set("Select product…")
    cb_product.pack(anchor="w")

    e_qty      = field_group(fc, "Quantity"); e_qty.insert(0, "1")
    e_discount = field_group(fc, "Discount (%)"); e_discount.insert(0, "0")
    e_tax      = field_group(fc, "Tax (%)"); e_tax.insert(0, "18")
    e_note     = field_group(fc, "Bill Note (optional)")

    sep(fc)

    # ── Preview ──
    rc = make_card(cols, padx=16, pady=16)
    rc.pack(side="right", fill="both", expand=True)
    make_label(rc, "Bill Preview", style="heading").pack(anchor="w", pady=(0,8))

    lbf = tk.Frame(rc, bg=CARD_BG)
    lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    sep(rc, pady=6)

    v_sub  = tk.StringVar(value="Subtotal:      ₹0.00")
    v_disc = tk.StringVar(value="Discount (0%): -₹0.00")
    v_tax  = tk.StringVar(value="Tax (0%):      +₹0.00")
    v_tot  = tk.StringVar(value="Grand Total:   ₹0.00")

    for var, col in [(v_sub, MUTED), (v_disc, WARNING), (v_tax, MUTED)]:
        tk.Label(rc, textvariable=var, bg=CARD_BG, fg=col,
                 font=F_SMALL, anchor="e").pack(fill="x")
    tk.Frame(rc, bg=BORDER, height=1).pack(fill="x", pady=3)
    tk.Label(rc, textvariable=v_tot, bg=CARD_BG, fg=SUCCESS,
             font=("Segoe UI", 13, "bold"), anchor="e").pack(fill="x")

    def compute_total() -> float:
        subtotal = sum(it["price"] * it["qty"] for it in state.current_bill)
        try: disc_pct = max(0.0, min(100.0, float(e_discount.get())))
        except ValueError: disc_pct = 0.0
        try: tax_pct = max(0.0, float(e_tax.get()))
        except ValueError: tax_pct = 0.0
        after_disc = subtotal * (1 - disc_pct / 100)
        grand      = after_disc * (1 + tax_pct / 100)
        v_sub .set(f"Subtotal:       ₹{subtotal:.2f}")
        v_disc.set(f"Discount ({disc_pct:.0f}%):  -₹{subtotal - after_disc:.2f}")
        v_tax .set(f"Tax ({tax_pct:.0f}%):         +₹{after_disc * tax_pct / 100:.2f}")
        v_tot .set(f"Grand Total:   ₹{grand:.2f}")
        return grand

    def render_lb():
        lb.delete(0, "end")
        for it in state.current_bill:
            lb.insert("end", f'  {it["name"]:<24} x{it["qty"]}  @₹{it["price"]:.2f} = ₹{it["price"]*it["qty"]:.2f}')
        compute_total()

    def do_add_item():
        idx = cb_product.current()
        if idx < 0: messagebox.showwarning("Select", "Choose a product first"); return
        try:
            qty = int(e_qty.get())
            if qty < 1: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "Quantity must be a positive integer"); return
        p = state.products[idx]
        if qty > p.get("quantity", 9999):
            messagebox.showwarning("Stock", f'Only {p["quantity"]} units in stock.'); return
        # Merge duplicates
        for it in state.current_bill:
            if it["name"] == p["name"]:
                it["qty"] += qty
                render_lb(); return
        state.current_bill.append({"name": p["name"], "price": p["price"], "qty": qty})
        render_lb()

    def do_remove_item():
        sel = lb.curselection()
        if not sel: return
        state.current_bill.pop(sel[0])
        render_lb()

    def do_clear():
        state.current_bill.clear()
        render_lb()

    def do_save():
        if not state.current_bill:
            messagebox.showwarning("Empty", "Add at least one item to the bill"); return
        grand    = compute_total()
        customer = cb_customer.get() or "Walk-in"
        note     = e_note.get().strip()
        bill_id  = state.next_bill_id()
        bill = {
            "id":       bill_id,
            "date":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer": customer,
            "items":    list(state.current_bill),
            "subtotal": round(sum(it["price"]*it["qty"] for it in state.current_bill), 2),
            "discount": _safe_float(e_discount.get()),
            "tax":      _safe_float(e_tax.get()),
            "total":    round(grand, 2),
            "note":     note,
        }
        state.bills.append(bill)
        # Deduct stock
        for it in state.current_bill:
            for p in state.products:
                if p["name"] == it["name"]:
                    p["quantity"] = max(0, p.get("quantity", 0) - it["qty"])
        state.save_bills()
        state.save_products()
        do_clear()
        refresh_all()
        messagebox.showinfo("Saved", f"Bill #{bill_id} saved!\nTotal: ₹{grand:.2f}")

    def do_print():
        """Generate a formatted receipt .txt and open it."""
        if not state.current_bill:
            messagebox.showwarning("Empty", "Add items before printing"); return
        grand    = compute_total()
        customer = cb_customer.get() or "Walk-in"
        note     = e_note.get().strip()
        lines = _format_receipt(
            bill_id  = "(preview)",
            date     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            customer = customer,
            items    = state.current_bill,
            subtotal = sum(it["price"]*it["qty"] for it in state.current_bill),
            disc_pct = _safe_float(e_discount.get()),
            tax_pct  = _safe_float(e_tax.get()),
            grand    = grand,
            note     = note,
        )
        _save_and_open_receipt(lines)

    make_button(fc, "＋  Add Item",    do_add_item).pack(fill="x", pady=2)
    make_button(fc, "✕  Remove Item",  do_remove_item, color=WARNING).pack(fill="x", pady=2)
    make_button(fc, "✓  Save Bill",    do_save,   color=SUCCESS).pack(fill="x", pady=2)
    make_button(fc, "🖨  Print / Save Receipt", do_print, color=ACCENT).pack(fill="x", pady=2)
    make_button(fc, "🗑  Clear Bill",  do_clear,  color=DANGER).pack(fill="x", pady=2)

    e_discount.bind("<KeyRelease>", lambda _: compute_total())
    e_tax.bind     ("<KeyRelease>", lambda _: compute_total())

    return frame, cb_customer, cb_product

_bill_frame, _bill_cb_cust, _bill_cb_prod = build_bill()

# ═══════════════════════ REPORTS ═════════════════════════════
def build_reports():
    frame = tk.Frame(workspace, bg=BG)
    frames["reports"] = frame

    hdr = tk.Frame(frame, bg=BG)
    hdr.pack(fill="x", pady=(0,10))
    make_label(hdr, "Reports", style="title", bg=BG).pack(side="left")

    def do_export_csv():
        if not state.bills: messagebox.showwarning("Empty", "No bills to export"); return
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BASE_DIR, f"bills_export_{ts}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID","Date","Customer","Subtotal","Discount%","Tax%","Total","Note"])
            for b in state.bills:
                w.writerow([b.get("id",""), b["date"], b["customer"],
                             b.get("subtotal",""), b.get("discount",""),
                             b.get("tax",""), b["total"], b.get("note","")])
        messagebox.showinfo("Exported", f"Saved to:\n{path}")

    def do_print_bill():
        sel = lb.curselection()
        if not sel: messagebox.showwarning("Select", "Select a bill to print"); return
        b = state.bills[sel[0]]
        lines = _format_receipt(
            bill_id  = b.get("id","?"),
            date     = b["date"],
            customer = b["customer"],
            items    = b.get("items", []),
            subtotal = b.get("subtotal", b["total"]),
            disc_pct = b.get("discount", 0),
            tax_pct  = b.get("tax", 0),
            grand    = b["total"],
            note     = b.get("note",""),
        )
        _save_and_open_receipt(lines)

    def do_delete():
        sel = lb.curselection()
        if not sel: messagebox.showwarning("Select", "Select a bill first"); return
        if messagebox.askyesno("Delete", "Delete this bill record?"):
            state.bills.pop(sel[0])
            state.save_bills()
            refresh_all()

    btn_row = tk.Frame(hdr, bg=BG)
    btn_row.pack(side="right")
    make_button(btn_row, "⬇  Export CSV",   do_export_csv,  color=SUCCESS).pack(side="left", padx=4)
    make_button(btn_row, "🖨  Print Bill",   do_print_bill,  color=ACCENT).pack(side="left", padx=4)
    make_button(btn_row, "🗑  Delete",       do_delete,      color=DANGER).pack(side="left", padx=4)

    # Summary tiles
    tiles = tk.Frame(frame, bg=BG)
    tiles.pack(fill="x", pady=(0,10))
    v_rev  = tk.StringVar(value="₹0.00")
    v_avg  = tk.StringVar(value="₹0.00")
    v_uniq = tk.StringVar(value="0")
    stat_tile(tiles, "Total Revenue",    v_rev,  SUCCESS)
    stat_tile(tiles, "Average Bill",     v_avg,  ACCENT)
    stat_tile(tiles, "Unique Customers", v_uniq, WARNING)

    # Search
    lc = make_card(frame, padx=16, pady=16)
    lc.pack(fill="both", expand=True)

    sf = tk.Frame(lc, bg=CARD_BG)
    sf.pack(fill="x", pady=(0,8))
    make_label(sf, "Search:", style="muted").pack(side="left", padx=(0,6))
    sv = tk.StringVar()
    make_entry(sf).configure(textvariable=sv)
    make_entry(sf, textvariable=sv).pack(side="left", fill="x", expand=True)

    make_label(lc, "All Bills", style="heading").pack(anchor="w", pady=(0,6))

    lbf = tk.Frame(lc, bg=CARD_BG)
    lbf.pack(fill="both", expand=True)
    lb, sb = make_listbox(lbf)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def refresh_lb(*_):
        q = sv.get().lower()
        lb.delete(0, "end")
        for b in state.bills:
            row = f'  #{str(b.get("id","?")):<4}  {b["date"]}  {b["customer"]:<22} ₹{b["total"]}'
            if q and q not in row.lower(): continue
            lb.insert("end", row)
        # Summary
        if state.bills:
            rev = sum(float(b["total"]) for b in state.bills)
            v_rev .set(f"₹{rev:,.2f}")
            v_avg .set(f"₹{rev/len(state.bills):,.2f}")
            v_uniq.set(str(len(set(b["customer"] for b in state.bills))))
        else:
            v_rev.set("₹0.00"); v_avg.set("₹0.00"); v_uniq.set("0")

    sv.trace("w", refresh_lb)
    return frame, refresh_lb

_rep_frame, _refresh_rep_lb = build_reports()

# ─────────────────────────── Receipt Helpers ─────────────────
def _safe_float(s: str) -> float:
    try:
        return max(0.0, float(s))
    except (ValueError, TypeError):
        return 0.0

def _format_receipt(bill_id, date, customer, items,
                    subtotal, disc_pct, tax_pct, grand, note) -> list[str]:
    W = 44
    lines = [
        "=" * W,
        "          BillFlow — SALES RECEIPT",
        "=" * W,
        f"  Bill #  : {bill_id}",
        f"  Date    : {date}",
        f"  Customer: {customer}",
        "-" * W,
        f"  {'ITEM':<22} {'QTY':>3}  {'UNIT':>7}  {'TOTAL':>7}",
        "-" * W,
    ]
    for it in items:
        name = textwrap.shorten(it["name"], width=22, placeholder="…")
        lines.append(f"  {name:<22} {it['qty']:>3}  ₹{it['price']:>6.2f}  ₹{it['price']*it['qty']:>6.2f}")
    after_disc = subtotal * (1 - disc_pct / 100)
    tax_amt    = after_disc * tax_pct / 100
    lines += [
        "-" * W,
        f"  {'Subtotal':<30} ₹{subtotal:>7.2f}",
        f"  {'Discount (' + str(disc_pct) + '%)':<30}-₹{subtotal - after_disc:>6.2f}",
        f"  {'Tax (' + str(tax_pct) + '%)':<30}+₹{tax_amt:>6.2f}",
        "=" * W,
        f"  {'GRAND TOTAL':<30} ₹{grand:>7.2f}",
        "=" * W,
    ]
    if note:
        lines += [f"  Note: {note}", "-" * W]
    lines += ["", "     Thank you for your business!", ""]
    return lines

def _save_and_open_receipt(lines: list[str]):
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BASE_DIR, f"receipt_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # Show in a small Tk window (works on all platforms without needing notepad)
    win = tk.Toplevel(root)
    win.title(f"Receipt — {ts}")
    win.geometry("520x500")
    win.configure(bg=BG)
    tk.Label(win, text="Receipt Preview", bg=BG, fg=TEXT,
             font=F_HEAD).pack(pady=(12,4))
    tk.Label(win, text=f"Saved to: {path}", bg=BG, fg=MUTED,
             font=F_SMALL, wraplength=480).pack()
    txt = tk.Text(win, bg=INPUT_BG, fg=TEXT, font=("Consolas", 10),
                  relief="flat", bd=8, wrap="none")
    txt.pack(fill="both", expand=True, padx=12, pady=8)
    txt.insert("end", "\n".join(lines))
    txt.config(state="disabled")
    make_button(win, "Close", win.destroy, color=DANGER).pack(pady=(0,10))

# ─────────────────────────── Refresh All ─────────────────────
def refresh_all():
    # Dashboard
    _v_prods.set(str(len(state.products)))
    _v_custs.set(str(len(state.customers)))
    _v_bills.set(str(len(state.bills)))
    total_rev = sum(float(b["total"]) for b in state.bills)
    _v_rev.set(f"₹{total_rev:,.2f}")

    # Dashboard chart
    _ax.clear()
    _ax.set_facecolor(CARD_BG)
    ccount: dict[str,int] = {}
    for b in state.bills:
        ccount[b["customer"]] = ccount.get(b["customer"], 0) + 1
    if ccount:
        top = sorted(ccount.items(), key=lambda x: x[1], reverse=True)[:10]
        names, vals = zip(*top)
        xs = list(range(len(names)))
        _ax.fill_between(xs, vals, alpha=0.3, color=ACCENT)
        _ax.plot(xs, vals, "o-", color=ACCENT, linewidth=2, markersize=5)
        for x, y in zip(xs, vals):
            _ax.annotate(str(y), (x, y), xytext=(0,5),
                         textcoords="offset points", ha="center",
                         fontsize=8, color=TEXT)
        _ax.set_xticks(xs)
        _ax.set_xticklabels(names, rotation=30, ha="right",
                             color=MUTED, fontsize=8)
        _ax.set_yticks([])
    else:
        _ax.text(0.5, 0.5, "No bills yet", ha="center", va="center",
                 transform=_ax.transAxes, color=MUTED, fontsize=12)
    for spine in _ax.spines.values(): spine.set_visible(False)
    _ax.set_facecolor(CARD_BG)
    _canv.draw()

    # Product / customer listboxes
    _refresh_prod_lb()
    _refresh_cust_lb()

    # Bill dropdowns
    _bill_cb_prod["values"] = [p["name"] for p in state.products]
    _bill_cb_cust["values"] = [c["name"] for c in state.customers]

    # Reports
    _refresh_rep_lb()

# ─────────────────────────── Start ───────────────────────────
navigate("dashboard")
root.mainloop()

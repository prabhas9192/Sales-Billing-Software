import tkinter as tk
from tkinter import ttk, messagebox
import json, os, datetime
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ================== Data Handling ==================
DATA_PRODUCTS = "products.json"
DATA_CUSTOMERS = "customers.json"
DATA_BILLS = "bills.json"

def load_data(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except:
                return default
    return default

def save_data(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# Initialize
products = load_data(DATA_PRODUCTS, [])
customers = load_data(DATA_CUSTOMERS, [])
bills = load_data(DATA_BILLS, [])
current_bill = []

# ================== Root Window ==================
root = tk.Tk()
root.title("Sales Billing Software")
root.geometry("900x600")

# ================== Layout ==================
sidebar = tk.Frame(root, bg="#2f3640", width=180)
sidebar.pack(side="left", fill="y")

content = tk.Frame(root, bg="#f5f6fa")
content.pack(side="right", fill="both", expand=True)

frames = {}
menu_buttons = []

# ================== Navigation ==================
def show(name):
    for f in frames.values():
        f.pack_forget()
    frames[name].pack(fill="both", expand=True)
    refresh_all()

def highlight_button(active_btn):
    for b in menu_buttons:
        b.config(bg="#353b48")
    active_btn.config(bg="#00a8ff")

def make_btn(text, page_name):
    def on_click():
        show(page_name)
        highlight_button(btn)
    btn = tk.Button(
        sidebar, text=text, bg="#353b48", fg="white",
        bd=0, pady=10, activebackground="#40739e",
        activeforeground="white", command=on_click
    )
    btn.pack(fill="x")
    menu_buttons.append(btn)
    return btn

# Sidebar buttons
btn_dashboard = make_btn("Dashboard", "dashboard")
btn_bill = make_btn("New Bill", "bill")
btn_products = make_btn("Products", "products")
btn_customers = make_btn("Customers", "customers")
btn_reports = make_btn("Reports", "reports")

# ================== Dashboard ==================
def create_dashboard(parent):
    frame = tk.Frame(parent, bg="#f5f6fa")
    frames["dashboard"] = frame

    tk.Label(frame, text="Dashboard", font=("Arial", 18), bg="#f5f6fa").pack(pady=10)
    stats_label = tk.Label(frame, text="", font=("Arial", 14), bg="#f5f6fa")
    stats_label.pack(pady=5)

    fig = Figure(figsize=(6, 4), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.get_tk_widget().pack(fill="both", expand=True, padx=20, pady=20)

    return frame, stats_label, ax, canvas

dash, stats_label, ax, canvas = create_dashboard(content)

# ================== Products ==================
def create_products_frame(parent):
    frame = tk.Frame(parent, bg="#f5f6fa")
    frames["products"] = frame

    tk.Label(frame, text="Products", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)

    # --- Entry Row Frame ---
    entry_frame = tk.Frame(frame, bg="#f5f6fa")
    entry_frame.pack(pady=5, padx=10, fill="x")

    # Name
    tk.Label(entry_frame, text="Name", bg="#f5f6fa").grid(row=0, column=0, sticky="w")
    pname = tk.Entry(entry_frame)
    pname.grid(row=1, column=0, padx=5, pady=2)

    # Price
    tk.Label(entry_frame, text="Price", bg="#f5f6fa").grid(row=0, column=1, sticky="w")
    pprice = tk.Entry(entry_frame)
    pprice.grid(row=1, column=1, padx=5, pady=2)

    # Quantity
    tk.Label(entry_frame, text="Quantity", bg="#f5f6fa").grid(row=0, column=2, sticky="w")
    pquantity = tk.Entry(entry_frame)
    pquantity.insert(0, "1")
    pquantity.grid(row=1, column=2, padx=5, pady=2)

    # --- Buttons Frame ---
    btn_frame = tk.Frame(frame, bg="#f5f6fa")
    btn_frame.pack(pady=5)
    
    prod_list = tk.Listbox(frame)
    prod_list.pack(fill="both", expand=True, padx=20, pady=10)

    def add_product():
        name = pname.get().strip()
        try:
            price = float(pprice.get())
            quantity = int(pquantity.get())
        except:
            messagebox.showerror("Error", "Invalid price or quantity")
            return
        if not name:
            messagebox.showerror("Error", "Please enter product name")
            return
        products.append({"name": name, "price": price, "quantity": quantity})
        save_data(DATA_PRODUCTS, products)
        pname.delete(0, "end")
        pprice.delete(0, "end")
        pquantity.delete(0, "end")
        pquantity.insert(0, "1")
        refresh_all()

    def del_product():
        sel = prod_list.curselection()
        if not sel: return
        products.pop(sel[0])
        save_data(DATA_PRODUCTS, products)
        refresh_all()

    tk.Button(btn_frame, text="Add Product", command=add_product).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Delete Selected", command=del_product).pack(side="left", padx=5)

    return frame, prod_list

prod, prod_list = create_products_frame(content)

# ================== Customers ==================
def create_customers_frame(parent):
    frame = tk.Frame(parent, bg="#f5f6fa")
    frames["customers"] = frame

    tk.Label(frame, text="Customers", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)

    # --- Entry Row Frame ---
    entry_frame = tk.Frame(frame, bg="#f5f6fa")
    entry_frame.pack(pady=5, padx=10, fill="x")

    # Name
    tk.Label(entry_frame, text="Name", bg="#f5f6fa").grid(row=0, column=0, sticky="w")
    cname = tk.Entry(entry_frame)
    cname.grid(row=1, column=0, padx=5, pady=2)

    # Phone
    tk.Label(entry_frame, text="Phone", bg="#f5f6fa").grid(row=0, column=1, sticky="w")
    cphone = tk.Entry(entry_frame)
    cphone.grid(row=1, column=1, padx=5, pady=2)

    # Age (optional)
    tk.Label(entry_frame, text="Age", bg="#f5f6fa").grid(row=0, column=2, sticky="w")
    cage = tk.Entry(entry_frame)
    cage.grid(row=1, column=2, padx=5, pady=2)

    # Gender (optional)
    tk.Label(entry_frame, text="Gender", bg="#f5f6fa").grid(row=0, column=3, sticky="w")
    gender_var = tk.StringVar(value="Select")
    cgender = ttk.Combobox(entry_frame, values=["Male", "Female", "Other"], state="readonly", textvariable=gender_var)
    cgender.grid(row=1, column=3, padx=5, pady=2)

    # --- Customer List ---
    cust_list = tk.Listbox(frame)
    cust_list.pack(fill="both", expand=True, padx=20, pady=10)

    # --- Buttons Frame ---
    btn_frame = tk.Frame(frame, bg="#f5f6fa")
    btn_frame.pack(pady=5)

    def add_customer():
        name = cname.get().strip()
        phone = cphone.get().strip()
        age = cage.get().strip()
        gender = gender_var.get()
        
        if not name:
            messagebox.showerror("Error", "Please enter a name")
            return

        # Only add age if it's a number
        try:
            age_val = int(age) if age else None
        except:
            messagebox.showerror("Error", "Age must be a number")
            return

        # Gender optional
        gender_val = gender if gender != "Select" else None

        customers.append({
            "name": name,
            "phone": phone,
            "age": age_val,
            "gender": gender_val
        })
        save_data(DATA_CUSTOMERS, customers)
        cname.delete(0, "end")
        cphone.delete(0, "end")
        cage.delete(0, "end")
        gender_var.set("Select")
        refresh_all()

    def del_customer():
        sel = cust_list.curselection()
        if not sel: return
        customers.pop(sel[0])
        save_data(DATA_CUSTOMERS, customers)
        refresh_all()

    tk.Button(btn_frame, text="Add Customer", command=add_customer).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Delete Selected", command=del_customer).pack(side="left", padx=5)

    return frame, cust_list

cust, cust_list = create_customers_frame(content)

# ================== New Bill ==================
def create_bill_frame(parent):
    frame = tk.Frame(parent, bg="#f5f6fa")
    frames["bill"] = frame

    tk.Label(frame, text="New Bill", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)

    # Customer & Product
    selection_frame = tk.Frame(frame, bg="#f5f6fa")
    selection_frame.pack(pady=5, padx=10, fill="x")

    tk.Label(selection_frame, text="Customer", bg="#f5f6fa").grid(row=0, column=0, sticky="w")
    bill_customer = ttk.Combobox(selection_frame, values=[], state="readonly")
    bill_customer.set("Select customer")
    bill_customer.grid(row=1, column=0, padx=5, pady=2)

    tk.Label(selection_frame, text="Product", bg="#f5f6fa").grid(row=0, column=1, sticky="w")
    bill_product = ttk.Combobox(selection_frame, values=[], state="readonly")
    bill_product.set("Select product")
    bill_product.grid(row=1, column=1, padx=5, pady=2)

    # Quantity & Tax
    qty_tax_frame = tk.Frame(frame, bg="#f5f6fa")
    qty_tax_frame.pack(pady=5, padx=10, fill="x")

    tk.Label(qty_tax_frame, text="Quantity", bg="#f5f6fa").grid(row=0, column=0, sticky="w")
    bill_qty = tk.Entry(qty_tax_frame)
    bill_qty.insert(0, "1")
    bill_qty.grid(row=1, column=0, padx=5, pady=2)

    tk.Label(qty_tax_frame, text="Tax (%)", bg="#f5f6fa").grid(row=0, column=1, sticky="w")
    tax_entry = tk.Entry(qty_tax_frame)
    tax_entry.insert(0, "0")
    tax_entry.grid(row=1, column=1, padx=5, pady=2)

    # Buttons
    btn_frame = tk.Frame(frame, bg="#f5f6fa")
    btn_frame.pack(pady=5)

    bill_list = tk.Listbox(frame)
    bill_list.pack(fill="both", expand=True, padx=20, pady=10)

    total_label = tk.Label(frame, text="Grand Total: 0", font=("Arial", 14), bg="#f5f6fa")
    total_label.pack(pady=5)

    def render_bill():
        bill_list.delete(0, "end")
        total = 0
        for it in current_bill:
            t = it["price"] * it["qty"]
            total += t
            bill_list.insert("end", f'{it["name"]} x{it["qty"]} = {t}')
        try:
            tax = float(tax_entry.get())
        except:
            tax = 0
        grand = total + (total * tax / 100)
        total_label.config(text=f"Grand Total: {grand:.2f}")

    def add_to_bill():
        if bill_product.current() < 0: return
        try:
            qty = int(bill_qty.get())
        except:
            return
        p = products[bill_product.current()]
        current_bill.append({"name": p["name"], "price": p["price"], "qty": qty})
        render_bill()

    def clear_bill():
        current_bill.clear()
        render_bill()

    def save_bill():
        if not current_bill:
            return
        cust_name = bill_customer.get() or "Walk-in"
        total = total_label.cget("text").replace("Grand Total: ", "")
        bills.append({
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer": cust_name,
            "total": total
        })
        save_data(DATA_BILLS, bills)
        clear_bill()
        messagebox.showinfo("Saved", "Bill saved!")

    tk.Button(btn_frame, text="Add Item", command=add_to_bill).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Save Bill", command=save_bill).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Clear Bill", command=clear_bill).pack(side="left", padx=5)

    return frame, bill_customer, bill_product, bill_qty, bill_list, tax_entry, total_label

bill, bill_customer, bill_product, bill_qty, bill_list, tax_entry, total_label = create_bill_frame(content)

# ================== Reports ==================
def create_reports_frame(parent):
    frame = tk.Frame(parent, bg="#f5f6fa")
    frames["reports"] = frame

    tk.Label(frame, text="Reports", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)

    rep_list = tk.Listbox(frame)
    rep_list.pack(fill="both", expand=True, padx=20, pady=10)

    def delete_report():
        sel = rep_list.curselection()
        if not sel:
            messagebox.showwarning("Delete", "Please select a report to delete")
            return
        if not messagebox.askyesno("Confirm", "Delete selected report?"):
            return
        bills.pop(sel[0])
        save_data(DATA_BILLS, bills)
        refresh_all()

    btn_frame = tk.Frame(frame, bg="#f5f6fa")
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="Delete Selected", command=delete_report).pack()

    return frame, rep_list

rep, rep_list = create_reports_frame(content)

# ================== Refresh All ==================
def refresh_all():
    # Dashboard Stats
    stats_label.config(
        text=f"Products: {len(products)} | Customers: {len(customers)} | Bills: {len(bills)}"
    )

    # Dashboard Graph
    ax.clear()
    customer_count = {}
    for b in bills:
        customer_count[b["customer"]] = customer_count.get(b["customer"], 0) + 1

    if customer_count:
        names = list(customer_count.keys())
        values = list(customer_count.values())
        x = list(range(len(names)))
        ax.fill_between(x, values, alpha=0.6)
        ax.plot(x, values, marker='o')
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=45)
        ax.set_title("Bills per Customer (Area Plot)")
        ax.set_ylabel("Number of Bills")
    else:
        ax.text(0.5, 0.5, "No data yet", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Bills per Customer")
    canvas.draw()

    # Products List
    prod_list.delete(0, "end")
    for p in products:
        prod_list.insert("end", f'{p["name"]} - {p["price"]}')

    # Customers List
    cust_list.delete(0, "end")
    for c in customers:
        cust_list.insert("end", f'{c["name"]} - {c.get("phone","")}')

    # Combobox Values
    bill_product["values"] = [p["name"] for p in products]
    bill_customer["values"] = [c["name"] for c in customers]

    # Reports List
    rep_list.delete(0, "end")
    for b in bills:
        rep_list.insert("end", f'{b["date"]} | {b["customer"]} | {b["total"]}')

    # Bill Totals
    try:
        bill_list.delete(0, "end")
        total = 0
        for it in current_bill:
            t = it["price"] * it["qty"]
            total += t
            bill_list.insert("end", f'{it["name"]} x{it["qty"]} = {t}')
        try:
            tax = float(tax_entry.get())
        except:
            tax = 0
        grand = total + (total * tax / 100)
        total_label.config(text=f"Grand Total: {grand:.2f}")
    except NameError:
        pass

# ================== Start App ==================
show("dashboard")
highlight_button(btn_dashboard)
refresh_all()
root.mainloop()

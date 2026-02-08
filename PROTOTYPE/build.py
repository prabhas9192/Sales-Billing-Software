import tkinter as tk
from tkinter import ttk, messagebox
import json, os, datetime

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

products = load_data(DATA_PRODUCTS, [])
customers = load_data(DATA_CUSTOMERS, [])
bills = load_data(DATA_BILLS, [])

current_bill = []

root = tk.Tk()
root.title("Sales Billing Software")
root.geometry("900x600")

# --- Layout ---
sidebar = tk.Frame(root, bg="#2f3640", width=180)
sidebar.pack(side="left", fill="y")

content = tk.Frame(root, bg="#f5f6fa")
content.pack(side="right", fill="both", expand=True)

frames = {}
menu_buttons = []

# --- Navigation logic ---
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
        bd=0, pady=10, activebackground="#40739e", activeforeground="white"
    )
    btn.config(command=on_click)
    btn.pack(fill="x")

    menu_buttons.append(btn)
    return btn

btn_dashboard = make_btn("Dashboard", "dashboard")
btn_bill = make_btn("New Bill", "bill")
btn_products = make_btn("Products", "products")
btn_customers = make_btn("Customers", "customers")
btn_reports = make_btn("Reports", "reports")

# --- Dashboard ---
dash = tk.Frame(content, bg="#f5f6fa")
frames["dashboard"] = dash
dash_label = tk.Label(dash, text="", font=("Arial", 16), bg="#f5f6fa")
dash_label.pack(pady=20)

# --- Products ---
prod = tk.Frame(content, bg="#f5f6fa")
frames["products"] = prod

tk.Label(prod, text="Products", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)
pname = tk.Entry(prod)
pprice = tk.Entry(prod)
tk.Label(prod, text="Name", bg="#f5f6fa").pack()
pname.pack()
tk.Label(prod, text="Price", bg="#f5f6fa").pack()
pprice.pack()

def add_product():
    name = pname.get().strip()
    try:
        price = float(pprice.get())
    except:
        messagebox.showerror("Error", "Invalid price")
        return
    if not name:
        return
    products.append({"name": name, "price": price})
    save_data(DATA_PRODUCTS, products)
    pname.delete(0, "end")
    pprice.delete(0, "end")
    refresh_all()

tk.Button(prod, text="Add Product", command=add_product).pack(pady=5)

prod_list = tk.Listbox(prod)
prod_list.pack(fill="both", expand=True, padx=20, pady=10)

def del_product():
    sel = prod_list.curselection()
    if not sel: return
    products.pop(sel[0])
    save_data(DATA_PRODUCTS, products)
    refresh_all()

tk.Button(prod, text="Delete Selected", command=del_product).pack()

# --- Customers ---
cust = tk.Frame(content, bg="#f5f6fa")
frames["customers"] = cust

tk.Label(cust, text="Customers", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)
cname = tk.Entry(cust)
cphone = tk.Entry(cust)
tk.Label(cust, text="Name", bg="#f5f6fa").pack()
cname.pack()
tk.Label(cust, text="Phone", bg="#f5f6fa").pack()
cphone.pack()

def add_customer():
    name = cname.get().strip()
    phone = cphone.get().strip()
    if not name: return
    customers.append({"name": name, "phone": phone})
    save_data(DATA_CUSTOMERS, customers)
    cname.delete(0, "end")
    cphone.delete(0, "end")
    refresh_all()

tk.Button(cust, text="Add Customer", command=add_customer).pack(pady=5)

cust_list = tk.Listbox(cust)
cust_list.pack(fill="both", expand=True, padx=20, pady=10)

def del_customer():
    sel = cust_list.curselection()
    if not sel: return
    customers.pop(sel[0])
    save_data(DATA_CUSTOMERS, customers)
    refresh_all()

tk.Button(cust, text="Delete Selected", command=del_customer).pack()

# --- New Bill ---
billf = tk.Frame(content, bg="#f5f6fa")
frames["bill"] = billf

tk.Label(billf, text="New Bill", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)

bill_customer = ttk.Combobox(billf, values=[], state="readonly")
bill_customer.set("Select customer")
bill_customer.pack()

bill_product = ttk.Combobox(billf, values=[], state="readonly")
bill_product.set("Select product")
bill_product.pack()

tk.Label(billf, text="Quantity").pack()
bill_qty = tk.Entry(billf)
bill_qty.insert(0, "1")
bill_qty.pack()


def add_to_bill():
    if bill_product.current() < 0: return
    try:
        qty = int(bill_qty.get())
    except:
        return
    p = products[bill_product.current()]
    current_bill.append({"name": p["name"], "price": p["price"], "qty": qty})
    render_bill()

tk.Button(billf, text="Add Item", command=add_to_bill).pack(pady=5)

bill_list = tk.Listbox(billf)
bill_list.pack(fill="both", expand=True, padx=20, pady=10)

tk.Label(billf, text="Tax (%)").pack()
tax_entry = tk.Entry(billf)
tax_entry.insert(0, "0")
tax_entry.pack()


total_label = tk.Label(billf, text="Grand Total: 0", font=("Arial", 14), bg="#f5f6fa")
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

tk.Button(billf, text="Save Bill", command=save_bill).pack()
tk.Button(billf, text="Clear Bill", command=clear_bill).pack()

# --- Reports ---
rep = tk.Frame(content, bg="#f5f6fa")
frames["reports"] = rep

tk.Label(rep, text="Reports", font=("Arial", 16), bg="#f5f6fa").pack(pady=10)

rep_list = tk.Listbox(rep)
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

btn_frame = tk.Frame(rep, bg="#f5f6fa")
btn_frame.pack(pady=5)

tk.Button(btn_frame, text="Delete Selected", command=delete_report).pack()


# --- Refresh ---
def refresh_all():
    dash_label.config(text=f"Products: {len(products)} | Customers: {len(customers)} | Bills: {len(bills)}")

    prod_list.delete(0, "end")
    for p in products:
        prod_list.insert("end", f'{p["name"]} - {p["price"]}')

    cust_list.delete(0, "end")
    for c in customers:
        cust_list.insert("end", f'{c["name"]} - {c.get("phone","")}')

    bill_product["values"] = [p["name"] for p in products]
    bill_customer["values"] = [c["name"] for c in customers]

    rep_list.delete(0, "end")
    for b in bills:
        rep_list.insert("end", f'{b["date"]} | {b["customer"]} | {b["total"]}')

    render_bill()

# --- Start ---
show("dashboard")
highlight_button(btn_dashboard)
root.mainloop()

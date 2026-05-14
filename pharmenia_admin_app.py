# -*- coding: utf-8 -*-
"""
Pharmenia Admin UI (Tkinter + MySQL)
- Invoice: medicine SEARCH fixed (typing 'par' finds Paracetamol)
- Enter-to-search binding
- New Business Reports tab: Purchase Records + Customer Revenue (date-range)
- Delete/Select actions retained
- PDF invoice
Requirements:
  pip install mysql-connector-python reportlab
"""

import datetime
from contextlib import contextmanager
from tkinter import *
from tkinter import ttk, messagebox, filedialog

import mysql.connector
from mysql.connector import Error
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ----------------------------
# DB connection configuration
# ----------------------------
DB = dict(
    host="127.0.0.1",
    user="root",
    password="wordpass",
    database="pharmenia",
    auth_plugin="mysql_native_password"
)


@contextmanager
def db_conn():
    con = mysql.connector.connect(**DB)
    try:
        yield con
    finally:
        try:
            con.close()
        except:
            pass

def ql(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur

# ----------------------------
# Simple Admin Login (hard-coded)
# ----------------------------
class LoginWindow(Tk):
    def __init__(self):
        super().__init__()
        self.title("Pharmenia — Admin Login")
        self.geometry("360x180")
        self.configure(bg="#f6f7fb")
        self.resizable(False, False)

        frm = Frame(self, bg="white", highlightthickness=1, highlightbackground="#e5e7eb")
        frm.pack(fill=BOTH, expand=True, padx=16, pady=16)

        Label(frm, text="Admin Login", bg="white", font=("Segoe UI Semibold", 14)).grid(row=0, column=0, columnspan=2, pady=(10, 14))

        Label(frm, text="User ID", bg="white").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        self.e_user = Entry(frm, width=24)
        self.e_user.grid(row=1, column=1, sticky="w", padx=8, pady=6)
        self.e_user.insert(0, "")  # leave empty; user types 'admin'

        Label(frm, text="Password", bg="white").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        self.e_pass = Entry(frm, width=24, show="*")
        self.e_pass.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        btn = Button(frm, text="Login", command=self.try_login)
        btn.grid(row=3, column=0, columnspan=2, pady=(10, 12))

        # Enter to submit; Tab between fields works by default
        self.bind("<Return>", lambda e: self.try_login())

        # Autofocus on user and select all
        self.e_user.focus_set()
        self.e_user.select_range(0, "end")

    def try_login(self):
        uid = self.e_user.get().strip()
        pwd = self.e_pass.get().strip()
        if uid == "admin" and pwd == "admin123":
            self.destroy()   # close login window; main() will launch dashboard next
        else:
            messagebox.showerror("Login Failed", "Invalid credentials. Try again.")
            self.e_pass.delete(0, "end")
            self.e_pass.focus_set()

# ----------------------------
# Shared master-data cache
# ----------------------------
class MasterCache:
    def __init__(self):
        self.suppliers = []   # list[(id, label)]
        self.customers = []   # list[(id, label)]

    def reload(self):
        with db_conn() as con:
            cur = con.cursor()
            ql(cur, "SELECT supplier_id, legal_name FROM supplier ORDER BY legal_name ASC")
            self.suppliers = [(sid, name) for sid, name in cur.fetchall()]

            ql(cur, "SELECT customer_id, full_name FROM customer ORDER BY full_name ASC")
            self.customers = [(cid, name) for cid, name in cur.fetchall()]

CACHE = MasterCache()

def combo_set_values(combo: ttk.Combobox, kv_list):
    combo_ids = [str(k) for k, _ in kv_list]
    combo_labels = [v for _, v in kv_list]
    combo._ids = combo_ids
    combo._labels = combo_labels
    combo["values"] = combo_labels
    if combo_labels:
        combo.current(0)

def combo_get_id(combo: ttk.Combobox):
    sel = combo.get().strip()
    if not hasattr(combo, "_labels") or not combo._labels:
        return None
    try:
        idx = combo._labels.index(sel)
        return int(combo._ids[idx])
    except ValueError:
        return None

def tree_selected_id(tree: ttk.Treeview):
    sel = tree.selection()
    if not sel: return None
    values = tree.item(sel[0], "values")
    if not values: return None
    try:
        return int(values[0])
    except:
        return None

# ----------------------------
# Main App with modern styling
# ----------------------------
class PharmeniaApp(Tk):
    def __init__(self):
        super().__init__()
        self.title("Pharmenia Admin — Pharmacy Management")
        self.geometry("1240x820")
        self.configure(bg="#f6f7fb")

        # ttk theme & style
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except:
            pass
        style.configure("TNotebook", background="#f6f7fb")
        style.configure("TNotebook.Tab", padding=(16, 8, 16, 8), font=("Segoe UI", 10))
        style.configure("TFrame", background="white")
        style.configure("TLabel", background="white", font=("Segoe UI", 10))
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))

        # Header Bar
        top = Frame(self, bg="#eef1ff")
        top.pack(fill=X)
        Label(top, text="Pharmenia Admin", bg="#eef1ff",
              font=("Segoe UI Semibold", 16)).pack(side=LEFT, padx=14, pady=10)
        Button(top, text="Reload Master Data", command=self.reload_master_data).pack(side=RIGHT, padx=10, pady=10)

        # Prepare master cache
        self.reload_master_data(silent=True)

        nb = ttk.Notebook(self)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.meds = MedicinesTab(nb)
        self.supp = SuppliersTab(nb)
        self.cust = CustomersTab(nb)
        self.purch = PurchaseTab(nb)
        self.inv = InvoiceTab(nb)
        self.reps = ReportsTab(nb)              # existing reports (stock/expiry/top sellers)
        self.biz  = BusinessReportsTab(nb)      # NEW: purchases + customer revenue

        nb.add(self.meds, text="Medicines")
        nb.add(self.supp, text="Suppliers")
        nb.add(self.cust, text="Customers")
        nb.add(self.purch, text="Purchase")
        nb.add(self.inv, text="Invoice")
        nb.add(self.reps, text="Inventory Reports")
        nb.add(self.biz,  text="Business Reports")   # <-- new tab

    def reload_master_data(self, silent=False):
        try:
            CACHE.reload()
            if not silent:
                messagebox.showinfo("Reloaded", "Suppliers / Customers refreshed.")
            if hasattr(self, "purch"): self.purch.refresh_combos()
            if hasattr(self, "inv"):   self.inv.refresh_combos()
        except Error as e:
            messagebox.showerror("DB Error", str(e))

# ----------------------------
# Medicines tab (with Delete)
# ----------------------------
class MedicinesTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")
        card = Frame(self, bg="white", bd=0, highlightthickness=1, highlightbackground="#e5e7eb")
        card.pack(fill=X, padx=12, pady=12)

        Label(card, text="Add Medicine", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w", padx=8, pady=(8,2))
        frm = Frame(card, bg="white"); frm.grid(row=1, column=0, sticky="we", padx=8, pady=6)
        frm.grid_columnconfigure(1, weight=1); frm.grid_columnconfigure(3, weight=1)

        Label(frm, text="Name").grid(row=0, column=0, sticky="w"); self.e_name=Entry(frm); self.e_name.grid(row=0,column=1, sticky="we", padx=8)
        Label(frm, text="Salt").grid(row=0, column=2, sticky="w"); self.e_salt=Entry(frm); self.e_salt.grid(row=0,column=3, sticky="we", padx=8)

        Label(frm, text="Form").grid(row=1, column=0, sticky="w")
        self.cmb_form=ttk.Combobox(frm, values=["TABLET","CAPSULE","SYRUP","INJECTION","OINTMENT","DROPS","OTHER"])
        self.cmb_form.current(0); self.cmb_form.grid(row=1,column=1, sticky="we", padx=8)

        Label(frm, text="HSN").grid(row=1, column=2, sticky="w"); self.e_hsn=Entry(frm); self.e_hsn.grid(row=1,column=3, sticky="we", padx=8)

        Label(frm, text="MRP").grid(row=2, column=0, sticky="w"); self.e_mrp=Entry(frm); self.e_mrp.grid(row=2,column=1, sticky="we", padx=8)
        Button(frm, text="Add", command=self.add_medicine).grid(row=2,column=3, sticky="e", padx=8)

        sfrm = Frame(self, bg="white"); sfrm.pack(fill=X, padx=12, pady=(4,0))
        Label(sfrm, text="Search").pack(side=LEFT); self.e_search=Entry(sfrm, width=40); self.e_search.pack(side=LEFT, padx=8)
        Button(sfrm, text="Go", command=self.search).pack(side=LEFT, padx=4)
        Button(sfrm, text="Refresh", command=self.refresh).pack(side=LEFT, padx=6)
        Button(sfrm, text="Delete Selected", command=self.delete_selected).pack(side=RIGHT, padx=6)

        self.tree = ttk.Treeview(self, columns=("id","name","salt","form","mrp","stock"), show="headings")
        for col, w in [("id",90),("name",280),("salt",240),("form",120),("mrp",120),("stock",100)]:
            self.tree.heading(col, text=col.upper()); self.tree.column(col, width=w, anchor=W)
        self.tree.pack(fill=BOTH, expand=True, padx=12, pady=10)

        self.refresh()

    def add_medicine(self):
        name=self.e_name.get().strip(); salt=self.e_salt.get().strip()
        form=self.cmb_form.get().strip(); hsn=self.e_hsn.get().strip()
        try:
            mrp=float(self.e_mrp.get().strip())
        except:
            messagebox.showerror("Invalid", "Enter numeric MRP"); return
        if not name:
            messagebox.showerror("Required","Name required"); return
        try:
            with db_conn() as con:
                cur=con.cursor()
                cur.callproc("sp_add_medicine", (name, salt or None, form, hsn or None, mrp))
                con.commit()
            messagebox.showinfo("OK","Medicine added")
            self.refresh()
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def search(self):
        key = self.e_search.get().strip()
        with db_conn() as con:
            cur=con.cursor()
            q = """
            SELECT m.medicine_id, m.name, IFNULL(m.salt,''), m.form_factor, m.mrp,
                   fn_stock_available(m.medicine_id) AS stock
            FROM medicine m
            WHERE m.name LIKE %s OR IFNULL(m.salt,'') LIKE %s
            ORDER BY m.name
            """
            ql(cur, q, (f"%{key}%", f"%{key}%"))
            self._fill(cur.fetchall())

    def delete_selected(self):
        mid = tree_selected_id(self.tree)
        if not mid:
            messagebox.showwarning("Select", "Choose a medicine row first"); return
        if not messagebox.askyesno("Confirm", f"Delete medicine #{mid}? This can fail if referenced by stock/invoices."):
            return
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, "DELETE FROM medicine WHERE medicine_id=%s", (mid,))
                con.commit()
            self.refresh()
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def refresh(self):
        with db_conn() as con:
            cur=con.cursor()
            ql(cur, "SELECT medicine_id,name,IFNULL(salt,''),form_factor,mrp,fn_stock_available(medicine_id) FROM medicine ORDER BY name")
            self._fill(cur.fetchall())

    def _fill(self, rows):
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert("", "end", values=r)

# ----------------------------
# Suppliers tab (with Delete)
# ----------------------------
class SuppliersTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")
        card = Frame(self, bg="white", highlightthickness=1, highlightbackground="#e5e7eb"); card.pack(fill=X, padx=12, pady=12)
        Label(card, text="Add Supplier", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w", padx=8, pady=(8,2))

        f = Frame(card, bg="white"); f.grid(row=1, column=0, sticky="we", padx=8, pady=6)
        f.grid_columnconfigure(1, weight=1); f.grid_columnconfigure(3, weight=1)
        Label(f, text="Legal Name").grid(row=0,column=0); self.e_name=Entry(f); self.e_name.grid(row=0,column=1, sticky="we", padx=8)
        Label(f, text="GSTIN").grid(row=0,column=2); self.e_gstin=Entry(f); self.e_gstin.grid(row=0,column=3, sticky="we", padx=8)
        Label(f, text="Phone").grid(row=1,column=0); self.e_phone=Entry(f); self.e_phone.grid(row=1,column=1, sticky="we", padx=8)
        Label(f, text="Email").grid(row=1,column=2); self.e_email=Entry(f); self.e_email.grid(row=1,column=3, sticky="we", padx=8)
        Button(f, text="Add Supplier", command=self.add).grid(row=1,column=4, padx=8)

        sfrm = Frame(self, bg="white"); sfrm.pack(fill=X, padx=12, pady=(4,0))
        Button(sfrm, text="Refresh", command=self.refresh).pack(side=LEFT, padx=6)
        Button(sfrm, text="Delete Selected", command=self.delete_selected).pack(side=LEFT, padx=6)

        self.tree=ttk.Treeview(self, columns=("id","name","gstin","phone","email"), show="headings")
        for c,w in [("id",90),("name",320),("gstin",160),("phone",160),("email",320)]:
            self.tree.heading(c, text=c.upper()); self.tree.column(c,width=w,anchor=W)
        self.tree.pack(fill=BOTH, expand=True, padx=12, pady=10)
        self.refresh()

    def add(self):
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, "INSERT INTO supplier(legal_name,gstin,phone,email) VALUES(%s,%s,%s,%s)",
                   (self.e_name.get().strip(), self.e_gstin.get().strip() or None, self.e_phone.get().strip() or None, self.e_email.get().strip() or None))
                con.commit()
            self.refresh(); messagebox.showinfo("OK","Supplier added")
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def delete_selected(self):
        sid = tree_selected_id(self.tree)
        if not sid:
            messagebox.showwarning("Select", "Choose a supplier row first"); return
        if not messagebox.askyesno("Confirm", f"Delete supplier #{sid}? This can fail if referenced by purchases."):
            return
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, "DELETE FROM supplier WHERE supplier_id=%s", (sid,))
                con.commit()
            self.refresh()
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def refresh(self):
        with db_conn() as con:
            cur=con.cursor()
            ql(cur, "SELECT supplier_id,legal_name,IFNULL(gstin,''),IFNULL(phone,''),IFNULL(email,'') FROM supplier ORDER BY legal_name")
            self._fill(cur.fetchall())

    def _fill(self, rows):
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert("", "end", values=r)

# ----------------------------
# Customers tab (with Delete + de-dup “Walk-in”)
# ----------------------------
class CustomersTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")
        card = Frame(self, bg="white", highlightthickness=1, highlightbackground="#e5e7eb"); card.pack(fill=X, padx=12, pady=12)
        Label(card, text="Add Customer", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w", padx=8, pady=(8,2))

        f = Frame(card, bg="white"); f.grid(row=1, column=0, sticky="we", padx=8, pady=6)
        f.grid_columnconfigure(1, weight=1); f.grid_columnconfigure(3, weight=1)
        Label(f, text="Full Name").grid(row=0,column=0); self.e_name=Entry(f); self.e_name.grid(row=0,column=1, sticky="we", padx=8)
        Label(f, text="Phone").grid(row=0,column=2); self.e_phone=Entry(f); self.e_phone.grid(row=0,column=3, sticky="we", padx=8)
        Label(f, text="Email").grid(row=0,column=4); self.e_email=Entry(f); self.e_email.grid(row=0,column=5, sticky="we", padx=8)
        Button(f, text="Add Customer", command=self.add).grid(row=0,column=6, padx=8)

        sfrm = Frame(self, bg="white"); sfrm.pack(fill=X, padx=12, pady=(4,0))
        Button(sfrm, text="Refresh", command=self.refresh).pack(side=LEFT, padx=6)
        Button(sfrm, text="Delete Selected", command=self.delete_selected).pack(side=LEFT, padx=6)
        Button(sfrm, text="Keep single Walk-in", command=self.dedup_walkin).pack(side=LEFT, padx=6)

        self.tree=ttk.Treeview(self, columns=("id","name","phone","email"), show="headings")
        for c,w in [("id",90),("name",320),("phone",200),("email",320)]:
            self.tree.heading(c, text=c.upper()); self.tree.column(c,width=w,anchor=W)
        self.tree.pack(fill=BOTH, expand=True, padx=12, pady=10)
        self.refresh()

    def add(self):
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, "INSERT INTO customer(full_name,phone,email) VALUES(%s,%s,%s)",
                   (self.e_name.get().strip(), self.e_phone.get().strip() or None, self.e_email.get().strip() or None))
                con.commit()
            self.refresh(); messagebox.showinfo("OK","Customer added")
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def delete_selected(self):
        cid = tree_selected_id(self.tree)
        if not cid:
            messagebox.showwarning("Select", "Choose a customer row first"); return
        if not messagebox.askyesno("Confirm", f"Delete customer #{cid}? This can fail if referenced by invoices."):
            return
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, "DELETE FROM customer WHERE customer_id=%s", (cid,))
                con.commit()
            self.refresh()
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def dedup_walkin(self):
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, """
SET @keep := (SELECT MIN(customer_id) FROM customer WHERE full_name='Walk-in Customer');
DELETE FROM customer
WHERE full_name='Walk-in Customer'
  AND customer_id <> @keep
LIMIT 1000000;
                """)
                for _ in cur.stored_results(): pass
                con.commit()
            self.refresh()
            messagebox.showinfo("Done","Kept a single Walk-in Customer")
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def refresh(self):
        with db_conn() as con:
            cur=con.cursor()
            ql(cur, "SELECT customer_id,full_name,IFNULL(phone,''),IFNULL(email,'') FROM customer ORDER BY full_name")
            self._fill(cur.fetchall())

    def _fill(self, rows):
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert("", "end", values=r)

# ----------------------------
# Purchase tab (line add/remove)
# ----------------------------
class PurchaseTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")

        card = Frame(self, bg="white", highlightthickness=1, highlightbackground="#e5e7eb"); card.pack(fill=X, padx=12, pady=12)
        Label(card, text="New Purchase", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w", padx=8, pady=(8,2))
        f = Frame(card, bg="white"); f.grid(row=1, column=0, sticky="we", padx=8, pady=6)
        for i in range(8): f.grid_columnconfigure(i, weight=1)

        Label(f, text="Supplier").grid(row=0, column=0, sticky="w")
        self.cmb_supplier = ttk.Combobox(f, state="readonly"); self.cmb_supplier.grid(row=0, column=1, sticky="we", padx=6)

        Label(f, text="Supplier Invoice #").grid(row=0, column=2, sticky="w")
        self.e_invno=Entry(f); self.e_invno.grid(row=0, column=3, sticky="we", padx=6)

        Label(f, text="Date (YYYY-MM-DD)").grid(row=0, column=4, sticky="w")
        self.e_date=Entry(f); self.e_date.insert(0, datetime.date.today().isoformat())
        self.e_date.grid(row=0, column=5, sticky="we", padx=6)

        Label(f, text="Medicine").grid(row=1, column=0, sticky="w")
        self.cmb_medicine = ttk.Combobox(f, state="readonly"); self.cmb_medicine.grid(row=1, column=1, sticky="we", padx=6)

        Label(f, text="Batch Code").grid(row=1, column=2, sticky="w")
        self.e_bcode=Entry(f); self.e_bcode.grid(row=1, column=3, sticky="we", padx=6)

        Label(f, text="Expiry (YYYY-MM-DD)").grid(row=1, column=4, sticky="w")
        self.e_exp=Entry(f); self.e_exp.grid(row=1, column=5, sticky="we", padx=6)

        Label(f, text="Purchase Price").grid(row=2, column=0, sticky="w")
        self.e_pprice=Entry(f); self.e_pprice.grid(row=2, column=1, sticky="we", padx=6)

        Label(f, text="Qty").grid(row=2, column=2, sticky="w")
        self.e_qty=Entry(f); self.e_qty.grid(row=2, column=3, sticky="we", padx=6)

        Label(f, text="GST %").grid(row=2, column=4, sticky="w")
        self.e_gst=Entry(f); self.e_gst.insert(0,"12"); self.e_gst.grid(row=2, column=5, sticky="we", padx=6)

        Button(f, text="Add Line", command=self.add_line).grid(row=2, column=6, sticky="e", padx=6)

        sfrm = Frame(self, bg="white"); sfrm.pack(fill=X, padx=12, pady=(6,0))
        Button(sfrm, text="Commit Purchase", command=self.commit_purchase).pack(side=RIGHT)
        Button(sfrm, text="Remove Selected Line", command=self.remove_selected_line).pack(side=LEFT)
        Button(sfrm, text="Reload Master Data", command=self.refresh_combos).pack(side=LEFT, padx=8)

        self.listbox = Listbox(self, height=9); self.listbox.pack(fill=X, padx=12, pady=8)
        self.lines = []
        self.refresh_combos()

    def refresh_combos(self):
        combo_set_values(self.cmb_supplier, CACHE.suppliers)
        with db_conn() as con:
            cur = con.cursor()
            ql(cur, "SELECT medicine_id, name, form_factor, mrp FROM medicine ORDER BY name")
            meds = [(mid, f"{name} [{form}] ₹{mrp:.2f}") for mid, name, form, mrp in cur.fetchall()]
            combo_set_values(self.cmb_medicine, meds)

    def add_line(self):
        try:
            sid = combo_get_id(self.cmb_supplier)
            mid = combo_get_id(self.cmb_medicine)
            if not sid or not mid:
                messagebox.showerror("Required","Select Supplier and Medicine"); return
            line = dict(
                sid=sid, invno=self.e_invno.get().strip(), dt=self.e_date.get().strip(),
                mid=mid, bcode=self.e_bcode.get().strip(), exp=self.e_exp.get().strip(),
                price=float(self.e_pprice.get().strip()), qty=int(self.e_qty.get().strip()),
                gst=float(self.e_gst.get().strip() or 0.0), mlabel=self.cmb_medicine.get()
            )
        except Exception:
            messagebox.showerror("Invalid","Fill all fields correctly"); return
        self.lines.append(line)
        self.listbox.insert(END, f"{line['dt']} | {self.e_invno.get().strip()} | {line['mlabel']} | Batch {line['bcode']} | x{line['qty']} @ {line['price']}")
        for e in [self.e_bcode, self.e_exp, self.e_pprice, self.e_qty]:
            e.delete(0, END)

    def remove_selected_line(self):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        self.listbox.delete(idx)
        del self.lines[idx]

    def commit_purchase(self):
        if not self.lines:
            messagebox.showwarning("No lines","Add lines first"); return
        try:
            with db_conn() as con:
                cur=con.cursor()
                for ln in self.lines:
                    cur.callproc("sp_purchase_stock", (
                        ln['sid'], ln['invno'], ln['dt'],
                        ln['mid'], ln['bcode'], ln['exp'], ln['price'],
                        ln['qty'], ln['gst']
                    ))
                con.commit()
            self.lines.clear(); self.listbox.delete(0, END)
            messagebox.showinfo("OK","Purchase committed & stock updated")
        except Error as e:
            messagebox.showerror("DB Error", str(e))

# ----------------------------
# Invoice tab — Live SEARCH UX
# ----------------------------
class InvoiceTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")

        card = Frame(self, bg="white", highlightthickness=1, highlightbackground="#e5e7eb"); card.pack(fill=X, padx=12, pady=12)
        Label(card, text="Create Invoice", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w", padx=8, pady=(8,2))
        f = Frame(card, bg="white"); f.grid(row=1, column=0, sticky="we", padx=8, pady=6)
        for i in range(10): f.grid_columnconfigure(i, weight=1)

        # Customer dropdown (kept)
        Label(f, text="Customer").grid(row=0, column=0, sticky="w")
        self.cmb_customer = ttk.Combobox(f, state="readonly"); self.cmb_customer.grid(row=0, column=1, sticky="we", padx=6)

        # Medicine SEARCH (live)
        Label(f, text="Find Medicine (name/salt)").grid(row=0, column=2, sticky="w")
        self.e_find = Entry(f); self.e_find.grid(row=0, column=3, sticky="we", padx=6)

        Label(f, text="Qty").grid(row=0, column=5, sticky="w")
        self.e_qty = Entry(f, width=8); self.e_qty.insert(0, "1"); self.e_qty.grid(row=0, column=6, sticky="we", padx=6)

        Button(f, text="Add Selected", command=self.add_selected_medicine).grid(row=0, column=7, sticky="e", padx=6)

        # Search results table
        self.res_tree = ttk.Treeview(self, columns=("id","name","salt","form","mrp","stock"), show="headings", height=8)
        for c,w in [("id",80),("name",280),("salt",240),("form",120),("mrp",100),("stock",100)]:
            self.res_tree.heading(c, text=c.upper()); self.res_tree.column(c,width=w,anchor=W)
        self.res_tree.pack(fill=X, padx=12, pady=(4,0))

        # Mouse wheel scrolling on results
        self.res_tree.bind("<MouseWheel>", lambda e: self.res_tree.yview_scroll(-1*(e.delta//120), "units"))

        sfrm = Frame(self, bg="white"); sfrm.pack(fill=X, padx=12, pady=(6,0))
        Button(sfrm, text="Create Invoice", command=self.create_invoice).pack(side=LEFT)
        Button(sfrm, text="Download PDF", command=self.download_pdf).pack(side=LEFT, padx=8)
        Button(sfrm, text="Clear Lines", command=self.clear).pack(side=LEFT, padx=8)
        Button(sfrm, text="Remove Selected Line", command=self.remove_selected_line).pack(side=LEFT, padx=8)
        Button(sfrm, text="Reload Master Data", command=self.refresh_combos).pack(side=RIGHT)

        self.linebox = Listbox(self, height=9); self.linebox.pack(fill=X, padx=12, pady=8)
        self.lines = []
        self.created_invoice_id = None

        self._search_after_id = None  # for debounce
        self.refresh_combos()

        # ---------- UX bindings ----------
        # live search as you type
        self.e_find.bind("<KeyRelease>", self._on_search_key)
        # Enter in search -> jump to qty (keep current selection)
        self.e_find.bind("<Return>", lambda e: self._focus_qty())
        # Up/Down in search to move selection in results
        self.e_find.bind("<Down>", lambda e: self._move_selection(1))
        self.e_find.bind("<Up>",   lambda e: self._move_selection(-1))
        # Enter in results also jumps to qty
        self.res_tree.bind("<Return>", lambda e: self._focus_qty())
        # Enter in qty -> add + go back to search
        self.e_qty.bind("<Return>", lambda e: self._add_and_return())

    def refresh_combos(self):
        combo_set_values(self.cmb_customer, CACHE.customers)
        # kick an initial search to fill grid
        self._do_search()

    # ------- live search helpers -------
    def _on_search_key(self, _event):
        """Debounce search so it runs ~150ms after typing stops."""
        if self._search_after_id:
            try: self.after_cancel(self._search_after_id)
            except: pass
        self._search_after_id = self.after(150, self._do_search)

    def _do_search(self):
        key = (self.e_find.get().strip() or "").lower()
        with db_conn() as con:
            cur = con.cursor()
            q = """
            SELECT m.medicine_id, m.name, IFNULL(m.salt,''), m.form_factor, m.mrp,
                   fn_stock_available(m.medicine_id) AS stock
            FROM medicine m
            WHERE LOWER(m.name) LIKE %s OR LOWER(IFNULL(m.salt,'')) LIKE %s
            ORDER BY m.name
            """
            ql(cur, q, (f"%{key}%", f"%{key}%"))
            rows = cur.fetchall()

        # fill result grid
        for i in self.res_tree.get_children(): self.res_tree.delete(i)
        for r in rows: self.res_tree.insert("", "end", values=r)

        # auto-select top row (so Enter immediately goes to qty)
        kids = self.res_tree.get_children()
        if kids:
            self.res_tree.selection_set(kids[0])
            self.res_tree.focus(kids[0])

    def _move_selection(self, delta):
        """Move selection up/down in the results while cursor stays in search box."""
        kids = self.res_tree.get_children()
        if not kids: return
        try:
            cur_iid = self.res_tree.selection()[0]
            idx = kids.index(cur_iid)
        except Exception:
            idx = 0
        idx = max(0, min(len(kids)-1, idx + delta))
        self.res_tree.selection_set(kids[idx])
        self.res_tree.focus(kids[idx])
        # keep the selected row visible
        self.res_tree.see(kids[idx])

    def _focus_qty(self):
        self.e_qty.focus_set()
        self.e_qty.select_range(0, END)

    def _add_and_return(self):
        # add selected with current qty
        self.add_selected_medicine()
        # refocus to search & select all text for quick next entry
        self.e_find.focus_set()
        self.e_find.select_range(0, END)
        # reset qty to 1
        self.e_qty.delete(0, END); self.e_qty.insert(0, "1")

    # ------- existing actions (unchanged logic) -------
    def search_medicine(self):
        # kept for compatibility if you call it elsewhere
        self._do_search()

    def add_selected_medicine(self):
        sel = self.res_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Pick a medicine from the search results"); return
        vals = self.res_tree.item(sel[0], "values")
        try:
            mid = int(vals[0]); label = f"{vals[1]} [{vals[3]}] ₹{float(vals[4]):.2f}"
            qty = int(self.e_qty.get().strip())
            if qty < 1: raise ValueError()
        except Exception:
            messagebox.showerror("Invalid","Enter positive qty"); return
        self.lines.append((mid, qty, label))
        self.linebox.insert(END, f"{label}  x{qty}")

    def remove_selected_line(self):
        sel = self.linebox.curselection()
        if not sel: return
        idx = sel[0]
        self.linebox.delete(idx)
        del self.lines[idx]

    def create_invoice(self):
        if not self.lines:
            messagebox.showwarning("No lines","Add items"); return
        cid = combo_get_id(self.cmb_customer)  # may be None (walk-in)
        try:
            with db_conn() as con:
                cur = con.cursor()
                ql(cur, "TRUNCATE TABLE invoice_items_temp")
                for mid, qty, _ in self.lines:
                    ql(cur, "INSERT INTO invoice_items_temp(medicine_id,qty) VALUES(%s,%s)", (mid, qty))
                args = [cid, 0]
                res = cur.callproc("sp_invoice_create", args)
                con.commit()
                self.created_invoice_id = res[1]
            messagebox.showinfo("OK", f"Invoice #{self.created_invoice_id} created")
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def download_pdf(self):
        if not self.created_invoice_id:
            messagebox.showwarning("No invoice","Create invoice first"); return
        save = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"invoice_{self.created_invoice_id}.pdf")
        if not save: return
        try:
            with db_conn() as con:
                cur=con.cursor()
                ql(cur, """
                    SELECT i.invoice_id, i.invoice_date, IFNULL(c.full_name,'Walk-in') cust
                    FROM invoice i LEFT JOIN customer c USING(customer_id)
                    WHERE i.invoice_id=%s
                """, (self.created_invoice_id,))
                hdr=cur.fetchone()
                ql(cur, """
                    SELECT m.name, b.batch_code, ii.qty, ii.unit_price
                    FROM invoice_item ii JOIN med_batch b USING(batch_id)
                    JOIN medicine m ON m.medicine_id=b.medicine_id
                    WHERE ii.invoice_id=%s
                """, (self.created_invoice_id,))
                items=cur.fetchall()

            total = sum(qty*price for _,_,qty,price in items)
            c = canvas.Canvas(save, pagesize=A4)
            w, h = A4
            c.setFont("Helvetica-Bold", 16); c.drawString(40, h-40, f"Pharmenia Invoice #{hdr[0]}")
            c.setFont("Helvetica", 11); c.drawString(40, h-60, f"Date: {hdr[1]}    Customer: {hdr[2]}")

            y = h-100
            c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Item"); c.drawString(300, y, "Batch"); c.drawString(430, y, "Qty"); c.drawString(480, y, "Price"); y-=15
            c.setFont("Helvetica", 10)
            for name, batch, qty, price in items:
                c.drawString(40, y, name[:40]); c.drawString(300, y, str(batch)); c.drawRightString(460, y, str(qty)); c.drawRightString(560, y, f"{price:.2f}")
                y-=14
                if y < 80: c.showPage(); y=h-60
            c.setFont("Helvetica-Bold", 12); c.drawRightString(560, 70, f"TOTAL: ₹{total:.2f}")
            c.showPage(); c.save()
            messagebox.showinfo("Saved", f"Saved: {save}")
        except Error as e:
            messagebox.showerror("DB Error", str(e))

    def clear(self):
        self.lines.clear(); self.linebox.delete(0,END); self.created_invoice_id=None

# ----------------------------
# Inventory Reports (existing: OOS, Near-expiry, Top sellers, Sales summary)
# ----------------------------
class ReportsTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")

        f1 = Frame(self, bg="white"); f1.pack(fill=X, padx=12, pady=(12,6))
        Label(f1, text="Near Expiry (days):").pack(side=LEFT)
        self.e_days = Entry(f1, width=6); self.e_days.insert(0, "30"); self.e_days.pack(side=LEFT, padx=6)
        Button(f1, text="Show Near Expiry", command=self.show_near_days).pack(side=LEFT, padx=6)

        f2 = Frame(self, bg="white"); f2.pack(fill=X, padx=12, pady=6)
        Button(f2, text="Out of Stock", command=self.show_oos).pack(side=LEFT)
        Button(f2, text="Top Sellers (90d)", command=self.show_top).pack(side=LEFT, padx=8)

        f3 = Frame(self, bg="white"); f3.pack(fill=X, padx=12, pady=6)
        Label(f3, text="Sales From (YYYY-MM-DD):").pack(side=LEFT)
        self.e_from = Entry(f3, width=12); self.e_from.pack(side=LEFT, padx=6)
        Label(f3, text="To (YYYY-MM-DD):").pack(side=LEFT)
        self.e_to = Entry(f3, width=12); self.e_to.pack(side=LEFT, padx=6)
        Button(f3, text="Sales Summary", command=self.show_sales_summary).pack(side=LEFT, padx=8)

        self.tree = ttk.Treeview(self, columns=("c1","c2","c3","c4"), show="headings", height=20)
        for i in range(1,5):
            self.tree.heading(f"c{i}", text=f"C{i}")
            self.tree.column(f"c{i}", width= max(140, 880//4), anchor=W)
        self.tree.pack(fill=BOTH, expand=True, padx=12, pady=12)

    def _fill(self, rows, headers):
        self.tree.config(columns=[f"c{i}" for i in range(1, len(headers)+1)])
        for i,h in enumerate(headers, start=1):
            self.tree.heading(f"c{i}", text=h)
            self.tree.column(f"c{i}", width=max(140, 1000//len(headers)), anchor=W)
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert("", "end", values=r)

    def show_oos(self):
        with db_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT m.medicine_id, m.name, m.form_factor, v.qty_available
                FROM vw_medicine_stock v
                JOIN medicine m USING(medicine_id)
                WHERE v.qty_available <= 0
                ORDER BY m.name
            """)
            self._fill(cur.fetchall(), ["Medicine ID","Name","Form","Qty"])

    def show_near_days(self):
        try:
            days = int(self.e_days.get().strip() or "30")
            if days < 1 or days > 365: raise ValueError()
        except Exception:
            messagebox.showerror("Invalid", "Enter days between 1 and 365"); return
        with db_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT b.batch_id, m.name, b.batch_code, b.expiry_date,
                       IFNULL(inv.qty_available,0) AS qty_available
                FROM med_batch b
                LEFT JOIN inventory_batch inv USING(batch_id)
                JOIN medicine m ON m.medicine_id=b.medicine_id
                WHERE b.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s DAY)
                ORDER BY b.expiry_date ASC
            """, (days,))
            self._fill(cur.fetchall(), ["Batch ID","Medicine","Batch","Expiry","Qty"])

    def show_top(self):
        with db_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT medicine_id, name, units_sold_90d FROM vw_top_sellers LIMIT 50")
            self._fill(cur.fetchall(), ["Medicine ID","Name","Units Sold (90d)"])

    def show_sales_summary(self):
        from_s = (self.e_from.get().strip() or "")
        to_s   = (self.e_to.get().strip() or "")
        def _ok(d):
            if len(d)!=10: return False
            y,m,dd = d.split("-")
            return y.isdigit() and m.isdigit() and dd.isdigit()
        if not (_ok(from_s) and _ok(to_s)):
            messagebox.showerror("Invalid", "Enter dates as YYYY-MM-DD"); return
        with db_conn() as con:
            cur = con.cursor()
            cur.callproc("sp_sales_summary", (from_s + " 00:00:00", to_s + " 00:00:00"))
            rows = []
            for result in cur.stored_results():
                rows = result.fetchall()
                break
        self._fill(rows, ["Medicine ID","Name","Units Sold","Revenue"])

# ----------------------------
# NEW: Business Reports tab (Purchases + Customer Revenue)
# ----------------------------
class BusinessReportsTab(Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="white")

        # --- Purchase Records ---
        grp1 = LabelFrame(self, text="Purchase Records", bg="white")
        grp1.pack(fill=X, padx=12, pady=(12,6))

        Label(grp1, text="From (YYYY-MM-DD)").pack(side=LEFT, padx=6, pady=6)
        self.p_from = Entry(grp1, width=12); self.p_from.pack(side=LEFT, padx=6)
        Label(grp1, text="To").pack(side=LEFT)
        self.p_to = Entry(grp1, width=12); self.p_to.pack(side=LEFT, padx=6)
        Button(grp1, text="Load Purchases", command=self.load_purchases).pack(side=LEFT, padx=8)

        self.p_tree = ttk.Treeview(self, columns=("dt","supplier","medicine","batch","expiry","qty","price","total"), show="headings", height=8)
        headers = [("dt","Date"),("supplier","Supplier"),("medicine","Medicine"),("batch","Batch"),("expiry","Expiry"),
                   ("qty","Qty"),("price","Price"),("total","Line Total")]
        for c,h in headers:
            self.p_tree.heading(c, text=h)
            self.p_tree.column(c, width= max(120, 1000//len(headers)), anchor=W)
        self.p_tree.pack(fill=X, padx=12, pady=6)

        # --- Customer Revenue ---
        grp2 = LabelFrame(self, text="Customer Revenue", bg="white")
        grp2.pack(fill=X, padx=12, pady=(12,6))

        Label(grp2, text="From (YYYY-MM-DD)").pack(side=LEFT, padx=6, pady=6)
        self.c_from = Entry(grp2, width=12); self.c_from.pack(side=LEFT, padx=6)
        Label(grp2, text="To").pack(side=LEFT)
        self.c_to = Entry(grp2, width=12); self.c_to.pack(side=LEFT, padx=6)
        Button(grp2, text="Load Revenue", command=self.load_customer_rev).pack(side=LEFT, padx=8)

        self.c_tree = ttk.Treeview(self, columns=("customer","day","units","revenue"), show="headings", height=8)
        for c,h in [("customer","Customer"),("day","Day"),("units","Units"),("revenue","Revenue")]:
            self.c_tree.heading(c, text=h)
            self.c_tree.column(c, width= max(140, 900//4), anchor=W)
        self.c_tree.pack(fill=X, padx=12, pady=6)

    def load_purchases(self):
        f = self.p_from.get().strip(); t = self.p_to.get().strip()
        if not (self._ok(f) and self._ok(t)):
            messagebox.showerror("Invalid","Enter dates as YYYY-MM-DD"); return
        with db_conn() as con:
            cur = con.cursor()
            cur.callproc("sp_purchase_report", (f, t))
            rows = []
            for rs in cur.stored_results():
                rows = rs.fetchall()
                break
        for i in self.p_tree.get_children(): self.p_tree.delete(i)
        for r in rows: self.p_tree.insert("", "end", values=r)

    def load_customer_rev(self):
        f = self.c_from.get().strip(); t = self.c_to.get().strip()
        if not (self._ok(f) and self._ok(t)):
            messagebox.showerror("Invalid","Enter dates as YYYY-MM-DD"); return
        with db_conn() as con:
            cur = con.cursor()
            cur.callproc("sp_customer_revenue", (f, t))
            rows = []
            for rs in cur.stored_results():
                rows = rs.fetchall()
                break
        for i in self.c_tree.get_children(): self.c_tree.delete(i)
        for r in rows: self.c_tree.insert("", "end", values=r)

    def _ok(self, d):
        if len(d)!=10: return False
        try:
            datetime.date.fromisoformat(d)
            return True
        except:
            return False

# ----------------------------
# Main
# ----------------------------
def main():
    # 1) Show login first
    login = LoginWindow()
    login.mainloop()      # blocks here until login window is destroyed

    # If the user closed the window without logging in, just exit quietly
    # (i.e., only proceed if credentials were correct and window was destroyed by try_login)
    try:
        # 2) Launch the main dashboard
        app = PharmeniaApp()
        app.mainloop()
    except Exception as e:
        # If something unexpected happens, show it
        messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    main()

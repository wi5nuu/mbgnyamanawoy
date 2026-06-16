import re, time, csv, json
from collections import Counter

start = time.time()

# ===== 1. SALES HISTORY AUDIT =====
print("=" * 60)
print("SALES HISTORY AUDIT")
print("=" * 60)

date_fmts = Counter()
total = 0
trx_empty = 0
trx_ids = set()
dup_count = 0
emp_empty = 0
menu_empty = 0
qty_empty = 0
qty_zero = 0
qty_neg = 0
qty_unparse = 0

with open("D:/hackathon-techprint/otherthings/sales_history (Competitors).csv", encoding="utf-8") as f:
    reader = csv.reader(f)
    header = next(reader)
    for row in reader:
        total += 1
        trx_id = row[0].strip() if len(row) > 0 else ""
        emp_id = row[2].strip() if len(row) > 2 else ""
        menu_id = row[3].strip() if len(row) > 3 else ""
        qty_str = row[5].strip() if len(row) > 5 else ""
        dt = row[1].strip() if len(row) > 1 else ""

        # Transaction_ID
        if not trx_id:
            trx_empty += 1
        elif trx_id in trx_ids:
            dup_count += 1
        else:
            trx_ids.add(trx_id)

        if not emp_id:
            emp_empty += 1
        if not menu_id:
            menu_empty += 1

        # Quantity
        if not qty_str:
            qty_empty += 1
        else:
            try:
                q = float(qty_str.replace(",", "."))
                if q == 0:
                    qty_zero += 1
                elif q < 0:
                    qty_neg += 1
            except ValueError:
                qty_unparse += 1

        # Date format
        if not dt:
            date_fmts["EMPTY"] += 1
        elif re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", dt):
            date_fmts["ISO YYYY-MM-DD HH:MM:SS"] += 1
        elif re.match(r"^\d{2}/\d{2}/\d{4}", dt):
            date_fmts["DD/MM/YYYY"] += 1
        elif re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{4}", dt):
            date_fmts["Month DD YYYY"] += 1
        elif re.match(r"^\d{12}", dt):
            date_fmts["Compact 12-digit"] += 1
        elif re.match(r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}\s+(AM|PM)", dt):
            date_fmts["MM-DD-YYYY AM/PM"] += 1
        else:
            date_fmts["OTHER"] += 1
            print(f"  UNKNOWN DATE: {dt}")

elapsed = time.time() - start
print(f"Total rows: {total}")
print(f"Time: {elapsed:.2f}s")
print()
print("Date Formats:")
for k, v in sorted(date_fmts.items()):
    print(f"  {k}: {v} ({v/total*100:.1f}%)")
print()
print(f"Transaction_ID empty: {trx_empty}")
print(f"Transaction_ID duplicated (2nd+ occ): {dup_count}")
print(f"Unique Transaction_ID: {len(trx_ids)}")
print(f"Employee_ID empty: {emp_empty}")
print(f"Menu_ID empty: {menu_empty}")
print()
print(f"Quantity empty: {qty_empty}")
print(f"Quantity zero: {qty_zero}")
print(f"Quantity negative: {qty_neg}")
print(f"Quantity unparseable: {qty_unparse}")

# ===== 2. WAREHOUSE AUDIT =====
print()
print("=" * 60)
print("WAREHOUSE AUDIT")
print("=" * 60)

with open("D:/hackathon-techprint/otherthings/warehouse_stock (Competitors).json") as f:
    wh = json.load(f)

recs = wh["records"]
print(f"Total warehouse records: {len(recs)}")

# Check schema
old_fmt = new_fmt = 0
dates_set = set()
for r in recs:
    dates_set.add(r["date"])
    has_old = any("stock_remaining" in e for e in r["stock_entries"])
    has_new = any("sisa_stok_akhir" in e for e in r["stock_entries"])
    if has_old:
        old_fmt += 1
    if has_new:
        new_fmt += 1

print(f"Old format (stock_remaining): {old_fmt}")
print(f"New format (sisa_stok_akhir): {new_fmt}")
print(f"Unique dates: {len(dates_set)}")
print(f"Date range: {min(dates_set)} to {max(dates_set)}")

# ===== 3. MASTER INVENTORY AUDIT =====
print()
print("=" * 60)
print("MASTER INVENTORY AUDIT")
print("=" * 60)

with open("D:/hackathon-techprint/otherthings/Master_Inventory (Competitors).csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    items = list(reader)

print(f"Total items: {len(items)}")

karton = [i for i in items if i["Supplier_UoM"].strip() == "Karton"]
non_karton = [i for i in items if i["Supplier_UoM"].strip() != "Karton"]
print(f"Karton items: {len(karton)}")
print(f"Non-Karton items: {len(non_karton)}")
print()
print("UoM distribution:")
uom_counts = Counter(i["Supplier_UoM"].strip() for i in items)
for uom, count in sorted(uom_counts.items()):
    print(f"  {uom}: {count}")

# ===== 4. RECIPE BOM AUDIT =====
print()
print("=" * 60)
print("RECIPE BOM AUDIT")
print("=" * 60)

with open("D:/hackathon-techprint/otherthings/Recipe_BOM (Competitors).json") as f:
    bom = json.load(f)

menus = bom["menu_items"]
print(f"Total menu items: {len(menus)}")
total_ingredients = sum(len(m["ingredients"]) for m in menus)
print(f"Total ingredient links: {total_ingredients}")
print(f"Avg ingredients per menu: {total_ingredients/len(menus):.1f}")

# ===== 5. EMPLOYEE AUDIT =====
print()
print("=" * 60)
print("EMPLOYEE AUDIT")
print("=" * 60)

with open("D:/hackathon-techprint/otherthings/Employee (Competitors).json") as f:
    emp = json.load(f)

emps = emp["employees"]
print(f"Total employees: {len(emps)}")
for e in emps:
    print(f"  {e['Employee_ID']}: {e['Full_Name']} ({e['Role']})")

# ===== SUMMARY =====
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Sales rows:      {total}")
print(f"Warehouse recs:  {len(recs)} ({old_fmt} old + {new_fmt} new)")
print(f"Master Inventory:{len(items)} items ({len(karton)} Karton)")
print(f"Recipe BOM:      {len(menus)} menu items")
print(f"Employees:       {len(emps)}")
print(f"Total time:      {time.time()-start:.2f}s")

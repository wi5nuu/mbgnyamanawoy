#!/usr/bin/env python3
"""
generate_extra_dirty_v2.py — Generator EXTREME DIRTY 5 Dataset
================================================================
Bikin 5 dataset jauh lebih kotor untuk stress test ETL pipeline.
Semua schema tetap, tapi konten dibuat sangat kotor.
Pipeline.py yang SAMA harus tetap jalan tanpa crash.
"""

import csv, json, os, random, shutil, math
from datetime import datetime, timedelta
import copy

random.seed(12345)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'extra_dirty')
SRC_DIR = os.path.dirname(__file__)

START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 6, 30)

TARGET_SALES = 235_000  # Target lebih besar

# ─── REFERENCE DATA ──────────────────────────────────────────
MENU_NAMES = {
    'MENU-001': 'Espresso', 'MENU-002': 'Americano', 'MENU-003': 'Iced Americano',
    'MENU-004': 'Caffe Latte', 'MENU-005': 'Iced Latte', 'MENU-006': 'Cappuccino',
    'MENU-007': 'Caramel Macchiato', 'MENU-008': 'Vanilla Latte', 'MENU-009': 'Hazelnut Latte',
    'MENU-010': 'Kopi Susu Gula Aren', 'MENU-011': 'Mocha', 'MENU-012': 'Iced Mocha',
    'MENU-013': 'Hot Chocolate', 'MENU-014': 'Matcha Latte', 'MENU-015': 'Iced Matcha Latte',
    'MENU-016': 'Hot Tea', 'MENU-017': 'Lemon Iced Tea', 'MENU-018': 'Green Tea Latte',
    'MENU-019': 'Honey Lemon Sparkling', 'MENU-020': 'Affogato', 'MENU-021': 'Croissant Plain',
    'MENU-022': 'Almond Croissant', 'MENU-023': 'Banana Bread', 'MENU-024': 'Chocolate Muffin',
    'MENU-025': 'Cheese Toast',
}
VALID_MENU_IDS = list(MENU_NAMES.keys())
GHOST_MENU_IDS = ['PROMO-01', 'TEST', 'MENU-999', 'MENU-000', 'SPECIAL-01', 'FREE-ITEM', 'VOID', 'CANCEL', 'DISCONTINUED']
VALID_EMP_IDS = ['EMP-01', 'EMP-02', 'EMP-03', 'EMP-04', 'EMP-05', 'EMP-06']
GHOST_EMP_IDS = ['EMP-99', 'EMP-00', 'STAFF01', 'XX', 'TRAINEE', 'EMP-77', 'MANAGER', 'OWNER', 'INTERN', 'EMP-88']
ALL_ITEM_IDS = [f'INV-{i:04d}' for i in range(1, 43)]

ERROR_FLAGS = [
    'EROR', '#REF!', '#VALUE', 'ERROR', 'Err0r', 'ROER',
    'undefined', 'INVALID', 'NULL', 'N/A', 'nan', 'inv4lid',
    'SYSERR', 'TIMEOUT', 'UNKNOWN',
    '<script>alert(\"xss\")</script>',  # XSS injection
    "'; DROP TABLE sales; --",          # SQL injection
    '<!-- HIDDEN COMMENT -->',
    'null', 'None', '#DIV/0!', '#NAME?', '#N/A',
]

UNICODE_TOKS = [
    'caf\xe9', 'caf\xe9 au lait', '\u00f1ame', '\u4e2d\u56fd\u8336',
    '\u30b3\u30fc\u30d2\u30fc', 'k\xf6fte', '\u03b3\u03b1\u03bb\u03b1\u03ba\u03c4\u03bf\u03c2',
    '\u2601\ufe0f', '\u2615', '\U0001f525',
]

# ─── EXTREME DIRT: function bantu ────────────────────────────

def extreme_quantity():
    r = random.random()
    if r < 0.04:
        return f'{random.randint(1,5)},{random.randint(0,9)}'
    elif r < 0.07:
        return f'{random.randint(1,5)} pcs'
    elif r < 0.09:
        return random.choice(['one','two','three','four','five','ten','satu','dua','tiga'])
    elif r < 0.12:
        return str(-random.randint(1, 99))
    elif r < 0.16:
        return '0'
    elif r < 0.18:
        return str(random.randint(5000, 99999))
    elif r < 0.19:
        return str(-random.randint(5000, 99999))
    elif r < 0.20:
        return random.choice(['INF', '-INF', 'NaN', 'nan', 'N/A', 'null', 'None', 'undefined', 'Infinity'])
    elif r < 0.21:
        return random.choice(['', '   ', '\t', '\n'])
    elif r < 0.22:
        return random.choice(['99999', '-99999', '100000', '50000'])
    elif r < 0.225:
        return f'{random.randint(1,5)}.{random.randint(1,999999)}'
    else:
        return str(random.randint(1, 8))

def extreme_datetime(dt):
    """Generate berbagai format datetime extreme."""
    r = random.random()
    if r < 0.40:
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    elif r < 0.50:
        return dt.strftime('%d/%m/%Y %H:%M')
    elif r < 0.57:
        return dt.strftime('%b %d %Y %H:%M')
    elif r < 0.62:
        return dt.strftime('%Y%m%d%H%M')
    elif r < 0.67:
        ampm = 'AM' if dt.hour < 12 else 'PM'
        h12 = dt.hour % 12 or 12
        return f'{dt.month:02d}-{dt.day:02d}-{dt.year} {h12:02d}:{dt.minute:02d} {ampm}'
    elif r < 0.70:
        return dt.strftime('%Y%m%d')
    elif r < 0.73:
        return dt.strftime('%Y-%m-%dT%H:%M:%S+07:00')  # ISO with TZ
    elif r < 0.75:
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')        # ISO Z
    elif r < 0.77:
        return dt.strftime('%m/%d/%Y %I:%M %p')          # MM/DD/YYYY US format
    elif r < 0.79:
        return f'{dt.day}.{dt.month}.{dt.year}'           # EU dots format
    elif r < 0.80:
        return f'{dt.year}{dt.month:02d}{dt.day:02d}'     # YYYYMMDD without separator
    elif r < 0.82:
        return dt.strftime('%d-%b-%Y %H:%M:%S')            # 01-Jan-2025
    elif r < 0.84:
        return dt.strftime('%Y/%m/%d %H:%M')               # YYYY/MM/DD
    elif r < 0.85:
        return f'{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}'  # only time, no date!
    elif r < 0.87:
        return f'{dt.day}/{dt.month}'                       # DD/MM only, no year
    elif r < 0.88:
        return 'not-a-date-???'
    elif r < 0.89:
        return ''
    elif r < 0.90:
        return '2025-02-29 10:00:00'                       # Leap day in non-leap year!
    elif r < 0.91:
        return '   '                                       # Whitespace only
    elif r < 0.92:
        return random.choice(UNICODE_TOKS)
    elif r < 0.93:
        future = random.choice([datetime(2099,6,15), datetime(3000,1,1), datetime(1970,1,1)])
        return future.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return dt.strftime('%Y-%m-%d %H:%M:%S')

def extreme_trx_id(date, seq):
    """Generate Transaction_ID dengan format sangat variatif."""
    ds = date.strftime('%Y%m%d')
    r = random.random()
    if r < 0.75:
        return f'TRX-{ds}-{seq:04d}'
    elif r < 0.80:
        return f'TRX--{ds}-{seq:04d}'         # double dash
    elif r < 0.84:
        return f'TRX_{ds}-{seq:04d}X'          # underscore + suffix
    elif r < 0.87:
        return f'TRX-{ds}-{seq:04d}Z'
    elif r < 0.89:
        return f'TRX-{ds}-{seq:04d}BKP'
    elif r < 0.91:
        return f'TXN-{ds}-{seq:04d}'
    elif r < 0.93:
        return f'TRX-{ds}-{seq:04d}REVERSAL'
    elif r < 0.94:
        return f'  TRX-{ds}-{seq:04d}  '      # whitespace padding
    elif r < 0.95:
        return f'TRX-{ds}-{seq:04d}\t'
    elif r < 0.96:
        return f'TRX-{random.choice([2099,3000])}{random.choice(["01","06"])}{random.choice(["01","15"])}-{seq:04d}'  # future year
    elif r < 0.97:
        return ''                              # empty
    elif r < 0.98:
        return 'N/A'
    else:
        return f'TRX-{ds}-OVERFLOW-{seq}'

# ─── GENERATE SALES ──────────────────────────────────────────
def generate_sales():
    print("[SALES] Generating 235,000 extreme dirty rows...")
    all_dates = [START_DATE + timedelta(days=i) for i in range((END_DATE-START_DATE).days+1)]

    rows = []
    trx_counters = {}
    dup_pool = []

    for i in range(TARGET_SALES):
        date = random.choice(all_dates)
        ds = date.strftime('%Y%m%d')
        trx_counters[ds] = trx_counters.get(ds, 0) + 1
        seq = trx_counters[ds]

        # TRX_ID
        trx_id = extreme_trx_id(date, seq)

        # DateTime
        dt_val = random_datetime(date)
        dt_str = extreme_datetime(dt_val)

        # Employee (10% ghost)
        if random.random() < 0.10:
            emp_id = random.choice(GHOST_EMP_IDS)
        else:
            emp_id = random.choice(VALID_EMP_IDS)

        # 3% whitespace padding on employee
        if random.random() < 0.03:
            emp_id = f'  {emp_id}  '

        # Menu (8% ghost)
        if random.random() < 0.08:
            menu_id = random.choice(GHOST_MENU_IDS)
            item_name = random.choice(['Unknown Item', '??', 'Promo Bundle', 'Free Item', 'TEST', '', '\u2601\ufe0f Promo', '<deleted>'])
        else:
            menu_id = random.choice(VALID_MENU_IDS)
            item_name = MENU_NAMES[menu_id]

        # 3% unicode in menu name
        if random.random() < 0.03:
            item_name = random.choice(UNICODE_TOKS) + ' ' + item_name if item_name else random.choice(UNICODE_TOKS)

        # Quantity
        qty = extreme_quantity()

        # Additional_Info (15% error flag)
        add_info = ''
        r_add = random.random()
        if r_add < 0.10:
            add_info = random.choice(ERROR_FLAGS)
        elif r_add < 0.13:
            add_info = f'{random.choice(ERROR_FLAGS)}, {random.choice(ERROR_FLAGS)}'
        elif r_add < 0.15:
            add_info = random.choice(UNICODE_TOKS) + ' ' + random.choice(ERROR_FLAGS)

        # 1.5% null critical field
        if random.random() < 0.015:
            choice = random.choice(['dt', 'menu', 'qty', 'trx', 'emp'])
            if choice == 'dt': dt_str = ''
            elif choice == 'menu': menu_id = ''; item_name = ''
            elif choice == 'qty': qty = ''
            elif choice == 'trx': trx_id = ''
            elif choice == 'emp': emp_id = ''

        row = [trx_id, dt_str, emp_id, menu_id, item_name, qty, add_info]
        rows.append(row)

        if i % 50000 == 0 and i > 0:
            print(f"  ... {i:,} rows")

    # Duplicate (1.5%)
    n_dup = int(TARGET_SALES * 0.015)
    print(f"  + Adding {n_dup} duplicate Transaction_ID rows...")
    for _ in range(n_dup):
        if rows:
            src = random.choice(rows)
            dup = src.copy()
            dup[0] = src[0]  # same TRX ID
            dup[1] = extreme_datetime(random_datetime(random.choice(all_dates)))
            dup[2] = random.choice(VALID_EMP_IDS + GHOST_EMP_IDS)
            dup[5] = extreme_quantity()
            rows.append(dup)

    random.shuffle(rows)

    header = ['Transaction_ID', 'DateTime', 'Employee_ID', 'Menu_ID', 'Item_Name', 'Quantity', 'Additional_Info']
    filepath = os.path.join(OUTPUT_DIR, 'sales_history (Competitors).csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  [OK] {len(rows):,} rows -> {filepath}")
    return rows


def random_datetime(d):
    h = random.randint(0, 23)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return d.replace(hour=h, minute=m, second=s)


# ─── GENERATE WAREHOUSE ──────────────────────────────────────
def generate_warehouse():
    print("\n[WAREHOUSE] Generating extreme dirty warehouse...")
    all_dates = [START_DATE + timedelta(days=i) for i in range((END_DATE-START_DATE).days+1)]

    skip_dates = set(random.sample(all_dates, k=int(len(all_dates)*0.04)))
    record_dates = [d for d in all_dates if d not in skip_dates]

    RECORDED_POOL = VALID_EMP_IDS + ['EMP-07', 'EMP-88', 'TRAINEE', 'SYSADMIN', 'ROBOT', 'SYSTEM', '']

    records = []
    for i, rec_date in enumerate(record_dates):
        rec_id = f'WH-{rec_date.strftime("%Y%m%d")}-{random.randint(1,5):03d}'
        recorded_by = random.choice(RECORDED_POOL)

        stock_entries = []
        for item_id in ALL_ITEM_IDS:
            # 5% missing item
            if random.random() < 0.05:
                continue

            # Schema drift: 50/50 stock_remaining vs sisa_stok_akhir
            use_drift = random.random() < 0.5

            # 3% negative stock
            if random.random() < 0.03:
                stock_val = round(-random.uniform(1, 99999), random.choice([0,1,2,3]))
            else:
                stock_val = round(random.uniform(0.1, 99999), random.choice([0,1,2]))

            # 2% extreme values
            if random.random() < 0.02:
                stock_val = random.choice([999999, -999999, 0.001, 500000])

            # 1.5% stock as string/weird
            if random.random() < 0.015:
                stock_val = random.choice(['ERROR', 'N/A', '?', 'UNKNOWN', '', '<missing>'])

            delivery = round(random.uniform(0, 5000), 1) if random.random() < 0.20 else 0.0

            # UoM sesuai item
            uom = get_item_uom(item_id)

            # 2% wrong UoM
            if random.random() < 0.02:
                uom = random.choice(['kg', 'L', 'oz', 'ml', '', 'unknown', 'boxes', 'PACKS', 'UNIT', 'SERVING'])

            # Build entry
            if use_drift:
                entry = {'Item_ID': item_id, 'sisa_stok_akhir': stock_val, 'delivery_in': delivery, 'UoM': uom}
            else:
                entry = {'Item_ID': item_id, 'stock_remaining': stock_val, 'delivery_in': delivery, 'UoM': uom}

            # 1% extra fields
            if random.random() < 0.01:
                entry['notes'] = random.choice(['Checked manually', 'Damaged goods', 'Expired', '<deleted>', '\u2713 verified'])
                entry['last_updated'] = random.choice(['2025-06-30', '', 'N/A'])

            # 1% null Item_ID
            if random.random() < 0.01:
                entry['Item_ID'] = None

            stock_entries.append(entry)

        # 2% empty entries
        if random.random() < 0.02:
            stock_entries = []

        records.append({
            'record_id': rec_id,
            'date': rec_date.strftime('%Y-%m-%d'),
            'recorded_by': recorded_by,
            'stock_entries': stock_entries,
        })

    # Tambah 2 duplicate records
    for _ in range(2):
        src = random.choice(records)
        dup = dict(src)
        dup['date'] = (datetime.strptime(src['date'], '%Y-%m-%d') + timedelta(days=random.randint(1,5))).strftime('%Y-%m-%d')
        records.append(dup)

    # Tambah 1 completely corrupted record
    records.append({
        'record_id': 'CORRUPTED-999',
        # 'date' missing
        # 'stock_entries' missing
    })

    random.shuffle(records)
    warehouse = {'records': records}

    filepath = os.path.join(OUTPUT_DIR, 'warehouse_stock (Competitors).json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(warehouse, f, indent=2, ensure_ascii=False)

    total_entries = sum(len(r.get('stock_entries', [])) for r in records)
    print(f"  {len(records)} records, {total_entries} stock entries -> {filepath}")
    return records


def get_item_uom(item_id):
    n = int(item_id.split('-')[1])
    if n <= 3 or n in (14,15,19,23,24,41):
        return 'gram'
    elif n in (17,18,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40):
        return 'pcs'
    else:
        return 'ml'


# ─── GENERATE MASTER_INVENTORY ───────────────────────────────
def generate_inventory():
    print("\n[INVENTORY] Generating dirty Master_Inventory...")
    original = []
    with open(os.path.join(SRC_DIR, 'Master_Inventory (Competitors).csv'), encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            original.append(row)

    rows = []
    # Copy all original
    for r in original:
        rows.append(dict(r))
        # 10% add whitespace to Item_ID
        if random.random() < 0.10:
            rows[-1]['Item_ID'] = f'  {rows[-1]["Item_ID"]}  '

    # Add 5 extra dirty items
    extras = [
        {'Item_ID': 'INV-0099', 'Item_Name': 'EXTRA DIRTY ITEM', 'Supplier_UoM': 'Box', 'Min_Stock_Threshold': '10', 'Category': 'EXTRA'},
        {'Item_ID': 'INV-0001', 'Item_Name': 'DUPLICATE ESPRESSO', 'Supplier_UoM': 'Kilogram', 'Min_Stock_Threshold': '99', 'Category': 'Coffee Bean'},
        {'Item_ID': 'INV-0100', 'Item_Name': 'SYRUP EKSTRIM\nBARU', 'Supplier_UoM': 'Unknown_UoM', 'Min_Stock_Threshold': '-5', 'Category': ''},
        {'Item_ID': '', 'Item_Name': 'NO ID ITEM', 'Supplier_UoM': 'Pcs', 'Min_Stock_Threshold': '100', 'Category': 'Other'},
        {'Item_ID': None, 'Item_Name': '', 'Supplier_UoM': '', 'Min_Stock_Threshold': 'N/A', 'Category': ''},
        {'Item_ID': 'INV-0200', 'Item_Name': '\u2601\ufe0f SPECIAL \u2615', 'Supplier_UoM': 'Sachet', 'Min_Stock_Threshold': '500', 'Category': 'Limited'},
        {'Item_ID': 'INV-0002', 'Item_Name': 'DUPLICATE ROBUSTA', 'Supplier_UoM': 'Kilogram', 'Min_Stock_Threshold': '3', 'Category': 'Coffee Bean'},
    ]
    for e in extras:
        rows.append(e)

    header = ['Item_ID', 'Item_Name', 'Supplier_UoM', 'Min_Stock_Threshold', 'Category']
    filepath = os.path.join(OUTPUT_DIR, 'Master_Inventory (Competitors).csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, '') for h in header])
    print(f"  {len(rows)} rows (orig: 42 + 7 dirty) -> {filepath}")


# ─── GENERATE RECIPE_BOM ──────────────────────────────────────
def generate_bom():
    print("\n[BOM] Generating dirty Recipe_BOM...")
    with open(os.path.join(SRC_DIR, 'Recipe_BOM (Competitors).json'), encoding='utf-8') as f:
        data = json.load(f)

    menu_items = data['menu_items']

    # Tambah item kotor
    dirty_items = [
        {'Menu_ID': 'MENU-001', 'Menu_Name': 'ESPRESSO DUP', 'Selling_Price_IDR': 'Rp 18.000', 'ingredients': []},
        {'Menu_ID': 'MENU-099', 'Menu_Name': '\u2601\ufe0f CLOUD COFFEE \u2615', 'Selling_Price_IDR': 99999,
         'ingredients': [
             {'Item_ID': 'INV-0099', 'Item_Name': 'Non-existent Item', 'qty_used': -99, 'UoM': ''},
             {'Item_ID': 'INV-0001', 'Item_Name': 'Espresso Bean', 'qty_used': 0, 'UoM': 'gram'},
             {'Item_ID': 'INV-0004', 'Item_Name': 'Fresh Milk', 'qty_used': 99999, 'UoM': 'ml'},
         ]},
        {'Menu_ID': None, 'Menu_Name': 'NO ID MENU', 'Selling_Price_IDR': 0, 'ingredients': [{'Item_ID': 'INV-0001', 'Item_Name': 'Coffee', 'qty_used': 18, 'UoM': 'gram'}]},
        {'Menu_ID': 'MENU-100', 'Menu_Name': '', 'Selling_Price_IDR': -5000, 'ingredients': []},
        {'Menu_ID': '<SCRIPT>ALERT(1)</SCRIPT>', 'Menu_Name': 'XSS MENU', 'Selling_Price_IDR': 0,
         'ingredients': [{'Item_ID': 'INV-0001', 'Item_Name': "' OR 1=1 --", 'qty_used': 'infinity', 'UoM': '\x00'}]},
    ]

    for item in dirty_items:
        menu_items.append(item)

    # Kasih duplikat ingredients di beberapa item asli
    for mi in menu_items:
        if mi.get('Menu_ID') in ['MENU-005', 'MENU-010'] and mi.get('ingredients'):
            dup = dict(mi['ingredients'][0])
            mi['ingredients'].append(dup)  # duplicate ingredient

    filepath = os.path.join(OUTPUT_DIR, 'Recipe_BOM (Competitors).json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'menu_items': menu_items}, f, indent=2, ensure_ascii=False)
    print(f"  {len(menu_items)} menu items (orig: 25 + dirty) -> {filepath}")


# ─── GENERATE EMPLOYEE ────────────────────────────────────────
def generate_employee():
    print("\n[EMPLOYEE] Generating dirty Employee...")
    with open(os.path.join(SRC_DIR, 'Employee (Competitors).json'), encoding='utf-8') as f:
        data = json.load(f)

    employees = data['employees']

    # Tambah dirty employees
    dirty_emps = [
        {'Employee_ID': 'EMP-01', 'Full_Name': 'BUDI SANTOSO COPY', 'Role': 'Barista', 'Shift': 'Morning'},
        {'Employee_ID': '', 'Full_Name': 'NO ID EMPLOYEE', 'Role': '', 'Shift': ''},
        {'Employee_ID': None, 'Full_Name': None, 'Role': None, 'Shift': None},
        {'Employee_ID': 'EMP-999', 'Full_Name': 'GHOST EMPLOYEE', 'Role': 'HACKER', 'Shift': 'MIDNIGHT'},
        {'Employee_ID': 'EMP-88', 'Full_Name': 'SYSTEM ACCOUNT', 'Role': 'BOT', 'Shift': '24/7'},
        {'Employee_ID': 'TRAINEE', 'Full_Name': 'MAGANG JOE', 'Role': 'Trainee', 'Shift': 'Flexible'},
        {'Employee_ID': 'EMP-07', 'Full_Name': 'ROBO BARISTA 3000', 'Role': 'AI', 'Shift': 'Morning'},
        {'Employee_ID': 'EMP-01 ', 'Full_Name': 'WHITESPACE ID', 'Role': 'Barista', 'Shift': 'Evening'},
    ]
    for e in dirty_emps:
        employees.append(e)

    # Extra field di beberapa
    for e in employees:
        if random.random() < 0.15:
            e['Access_Level'] = random.choice(['admin', 'user', 'root', ''])
        if random.random() < 0.10:
            e['Salary'] = random.choice(['5.000.000', '', None])

    filepath = os.path.join(OUTPUT_DIR, 'Employee (Competitors).json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'employees': employees}, f, indent=2, ensure_ascii=False)
    print(f"  {len(employees)} employees (orig: 6 + dirty) -> {filepath}")


# ─── MAIN ─────────────────────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  GENERATOR EXTREME DIRTY V2")
    print("  5 dataset super kotor untuk stress test ETL pipeline")
    print("=" * 60)

    generate_sales()
    generate_warehouse()
    generate_inventory()
    generate_bom()
    generate_employee()

    # Copy pipeline
    for f in ['pipeline.py', 'utils.py']:
        shutil.copy2(os.path.join(SRC_DIR, f), os.path.join(OUTPUT_DIR, f))

    print("\n" + "=" * 60)
    print("  GENERATION COMPLETE")
    print("=" * 60)
    for fn in sorted(os.listdir(OUTPUT_DIR)):
        if fn.endswith(('.py', '.pyc', '__pycache__')):
            continue
        fp = os.path.join(OUTPUT_DIR, fn)
        size = os.path.getsize(fp)
        print(f"    {fn:<50s} {size:>12,} bytes")


if __name__ == '__main__':
    main()

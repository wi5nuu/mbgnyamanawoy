#!/usr/bin/env python3
"""
generate_extra_dirty_v3.py — Generator EXTREME DIRTY V3
=========================================================
Buat data SUPER KOTOR + SUPER BERAT, tapi AMAN untuk pipeline original.
Semua format date yg dipakai GARANSI PARSEABLE oleh pipeline asli.
256rb+ baris sales. Kotoran difokuskan ke NON-DATE fields.
"""

import csv, json, os, random, shutil
from datetime import datetime, timedelta

random.seed(99999)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'extra_dirty')
SRC_DIR = os.path.dirname(__file__)

TARGET_SALES = 260_000
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 6, 30)
all_dates = [START_DATE + timedelta(days=i) for i in range((END_DATE-START_DATE).days+1)]

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
VALID_MENU = list(MENU_NAMES.keys())
GHOST_MENU = ['PROMO-01','TEST','MENU-999','MENU-000','SPECIAL-01','FREE-ITEM','VOID','DELETED','BUNDL-01']
VALID_EMP = ['EMP-01','EMP-02','EMP-03','EMP-04','EMP-05','EMP-06']
GHOST_EMP = ['EMP-99','EMP-00','STAFF01','XX','TRAINEE','EMP-77','MANAGER','OWNER','INTERN','EMP-88','BOT-01']

ERROR_FLAGS = [
    'EROR','#REF!','#VALUE','ERROR','Err0r','ROER',
    'undefined','INVALID','NULL','N/A','nan','inv4lid',
    'SYSERR','TIMEOUT','UNKNOWN','<script>xss</script>',
    "'; DROP--", '#DIV/0!','#NAME?','null','None','',
]

UNICODE_ITEMS = ['caf\u00e9','\u00f1ame','\u4e2d\u56fd\u8336','\u30b3\u30fc\u30d2\u30fc',
                 '\u2615','\u2601\ufe0f','\u2728','\U0001f525','\u00e9clair','k\u00f6fte']

#
# DATE GENERATOR — HANYA format yg DIJAMIN PARSE oleh pipeline asli
#
def safe_date(dt):
    """Generate date string yg 100% AMAN untuk pipeline asli (TIDAK return None di parse_datetime)."""
    r = random.random()
    if r < 0.30:                           # ISO standard
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    elif r < 0.45:                         # DD/MM/YYYY
        return dt.strftime('%d/%m/%Y %H:%M')
    elif r < 0.55:                         # Month name
        return dt.strftime('%b %d %Y %H:%M')
    elif r < 0.63:                         # Compact 12-digit
        return dt.strftime('%Y%m%d%H%M')
    elif r < 0.70:                         # MM-DD-YYYY AM/PM
        ap = 'AM' if dt.hour < 12 else 'PM'
        h12 = dt.hour % 12 or 12
        return f'{dt.month:02d}-{dt.day:02d}-{dt.year} {h12:02d}:{dt.minute:02d} {ap}'
    elif r < 0.75:                         # YYYYMMDD 8-digit
        return dt.strftime('%Y%m%d')
    elif r < 0.80:                         # ISO future year (masih parseable)
        future = dt.replace(year=random.choice([2026,2027,2028,2050,2099]))
        return future.strftime('%Y-%m-%d %H:%M:%S')
    elif r < 0.84:                         # ISO with microseconds
        return dt.strftime('%Y-%m-%d %H:%M:%S.') + f'{random.randint(100,999)}'
    elif r < 0.88:                         # ISO date only (no time)
        return dt.strftime('%Y-%m-%d')
    elif r < 0.91:                         # DD/MM/YYYY tanpa detik
        return dt.strftime('%d/%m/%Y')
    elif r < 0.94:                         # Month name tanggal aja
        return dt.strftime('%b %d %Y')
    elif r < 0.96:                         # Compact 10-digit (tahun + bulan + hari + jam)
        return dt.strftime('%Y%m%d%H')
    elif r < 0.98:                         # YYYY/MM/DD (slash version, masih ISO-like)
        return dt.strftime('%Y/%m/%d %H:%M')
    else:                                  # KOSONG — aman, di-quarantine sebelum .dt
        return ''

def rnd_time(d):
    return d.replace(hour=random.randint(0,23), minute=random.randint(0,59), second=random.randint(0,59))

#
# QUANTITY — dirty banget tapi masih di-handle 3-layer rescue
#
def dirty_qty():
    r = random.random()
    if r < 0.55: return str(random.randint(1,5))
    elif r < 0.65: return str(random.randint(6,20))
    elif r < 0.67: return str(random.randint(0,10)) + ' pcs'
    elif r < 0.69: return str(random.randint(0,10)) + ' cups'
    elif r < 0.72: return f'{random.randint(1,5)},{random.randint(0,9)}'
    elif r < 0.74: return random.choice(['one','two','three','four','five','ten','satu','dua','tiga','sepuluh'])
    elif r < 0.76: return random.choice(['nol','zero','six','seven','eight','nine'])
    elif r < 0.78: return str(-random.randint(1,20))
    elif r < 0.82: return '0'
    elif r < 0.84: return ''
    elif r < 0.87: return random.choice(['N/A','NaN','nan','NULL','null','None','-','undefined'])
    elif r < 0.89: return f'{random.randint(1,9)}.{random.randint(1,999)}'
    elif r < 0.90: return f'{random.randint(50,200)}'
    elif r < 0.91: return f'-{random.randint(50,200)}'
    elif r < 0.92: return random.choice([' 1 ',' 2 ','  5  ','\t3\t'])
    elif r < 0.93: return random.choice(['?', '???', 'ERROR', 'ERROR QTY', 'xxx'])
    else: return str(random.randint(1,5))

#
# TRX ID — dirty
#
def dirty_trx(date, seq):
    ds = date.strftime('%Y%m%d')
    r = random.random()
    if r < 0.80: return f'TRX-{ds}-{seq:04d}'
    elif r < 0.86: return f'TRX--{ds}-{seq:04d}'
    elif r < 0.90: return f'TRX_{ds}-{seq:04d}X'
    elif r < 0.93: return f'TRX-{ds}-{seq:04d}Z'
    elif r < 0.95: return f'TXN-{ds}-{seq:04d}'
    elif r < 0.96: return f'  TRX-{ds}-{seq:04d}  '
    elif r < 0.97: return f'TRX-{ds}-OVERFLOW-{seq}'
    elif r < 0.99: return ''
    else: return f'TRX-{ds}-{seq:04d}BKP'

#
# ─── GENERATE SALES ──────────────────────────────────────────
#
def gen_sales():
    print(f'[SALES] Generating {TARGET_SALES:,} extreme-dirty rows (safe dates)...')
    rows, pool, counters = [], [], {}
    total = TARGET_SALES + int(TARGET_SALES * 0.02)

    for i in range(total):
        d = random.choice(all_dates)
        ds = d.strftime('%Y%m%d')
        counters[ds] = counters.get(ds, 0) + 1
        seq = counters[ds]

        trx = dirty_trx(d, seq)
        dt_str = safe_date(rnd_time(d))

        # Emp: 12% ghost
        emp = random.choice(GHOST_EMP) if random.random() < 0.12 else random.choice(VALID_EMP)

        # Menu: 10% ghost
        if random.random() < 0.10:
            menu = random.choice(GHOST_MENU)
            iname = random.choice(['Promo','TEST','??','Free Item','','\u2615 Promo','<deleted>'])
        else:
            menu = random.choice(VALID_MENU)
            iname = MENU_NAMES[menu]

        # Unicode pada item_name (5%)
        if random.random() < 0.05 and iname:
            iname = random.choice(UNICODE_ITEMS) + ' ' + iname

        qty = dirty_qty()

        # Add_info: 18% error
        add = ''
        ra = random.random()
        if ra < 0.14:
            add = random.choice(ERROR_FLAGS)
        elif ra < 0.17:
            add = random.choice(ERROR_FLAGS) + ', ' + random.choice(ERROR_FLAGS)
        elif ra < 0.18:
            add = random.choice(UNICODE_ITEMS)

        # 2% null critical
        if random.random() < 0.02:
            c = random.choice(['dt','menu','qty','trx'])
            if c == 'dt': dt_str = ''
            elif c == 'menu': menu = ''; iname = ''
            elif c == 'qty': qty = ''
            elif c == 'trx': trx = ''

        rows.append([trx, dt_str, emp, menu, iname, qty, add])
        if i > 0 and i % 50000 == 0:
            print(f'  ... {i:,} rows')

    # Duplicate TRX (2%)
    ndup = int(TARGET_SALES * 0.02)
    for _ in range(ndup):
        src = random.choice(rows)
        dup = src.copy()
        dup[1] = safe_date(rnd_time(random.choice(all_dates)))
        dup[5] = dirty_qty()
        rows.append(dup)

    random.shuffle(rows)
    fp = os.path.join(OUTPUT_DIR, 'sales_history (Competitors).csv')
    with open(fp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Transaction_ID','DateTime','Employee_ID','Menu_ID','Item_Name','Quantity','Additional_Info'])
        w.writerows(rows)
    print(f'  [OK] {len(rows):,} rows -> {fp}')
    return rows

#
# ─── GENERATE WAREHOUSE ──────────────────────────────────────
#
def gen_warehouse():
    print('\n[WAREHOUSE] Generating extreme-dirty warehouse...')
    skip = set(random.sample(all_dates, k=int(len(all_dates)*0.05)))
    rec_dates = [d for d in all_dates if d not in skip]
    pool = VALID_EMP + ['EMP-07','EMP-88','TRAINEE','SYSADMIN','ROBOT','SYSTEM','','GHOST-01']

    ALL_ITEMS = [f'INV-{i:04d}' for i in range(1,43)]

    def item_uom(iid):
        n = int(iid.split('-')[1])
        if n <= 3 or n in (14,15,19,23,24,41): return 'gram'
        if n in (17,18,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40): return 'pcs'
        return 'ml'

    records = []
    for rd in rec_dates:
        entries = []
        for iid in ALL_ITEMS:
            if random.random() < 0.05: continue  # skip 5%

            drift = random.random() < 0.55
            if random.random() < 0.04:
                sv = round(-random.uniform(1, 99999), 1)
            else:
                sv = round(random.uniform(0.1, 99999), 1)

            if random.random() < 0.02:
                sv = random.choice(['ERROR','N/A','?','UNKNOWN','<broken>','NULL',None])

            deliv = round(random.uniform(0, 9999), 1) if random.random() < 0.25 else 0.0
            uom = item_uom(iid)
            if random.random() < 0.025:
                uom = random.choice(['kg','L','oz','','unknown','boxes','PACKS','N/A'])

            if drift:
                e = {'Item_ID': iid, 'sisa_stok_akhir': sv, 'delivery_in': deliv, 'UoM': uom}
            else:
                e = {'Item_ID': iid, 'stock_remaining': sv, 'delivery_in': deliv, 'UoM': uom}

            if random.random() < 0.015:
                e['notes'] = random.choice(['rusak','expired','checked','','<hidden>'])
            if random.random() < 0.01:
                e['Item_ID'] = random.choice([None, '', 'INV-0000', 'UNKNOWN'])
            entries.append(e)

        if random.random() < 0.02:
            entries = []

        rid = f'WH-{rd.strftime("%Y%m%d")}-{random.randint(1,9):03d}'
        records.append({
            'record_id': rid,
            'date': rd.strftime('%Y-%m-%d'),
            'recorded_by': random.choice(pool),
            'stock_entries': entries,
        })

    # Duplicate + corrupted
    for _ in range(3):
        src = random.choice(records)
        r2 = dict(src)
        rd2 = datetime.strptime(src['date'], '%Y-%m-%d') + timedelta(days=random.randint(1,5))
        r2['date'] = rd2.strftime('%Y-%m-%d')
        records.append(r2)

    records.append({'record_id': 'CORRUPTED-999'})

    random.shuffle(records)
    fp = os.path.join(OUTPUT_DIR, 'warehouse_stock (Competitors).json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump({'records': records}, f, indent=2, ensure_ascii=False)
    print(f'  {len(records)} records | entries: {sum(len(r.get("stock_entries",[])) for r in records):,} -> {fp}')

#
# ─── GENERATE MASTER_INVENTORY ───────────────────────────────
#
def gen_inventory():
    print('\n[INVENTORY] Generating dirty Master_Inventory...')
    orig = []
    with open(os.path.join(SRC_DIR, 'Master_Inventory (Competitors).csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f): orig.append(r)

    rows = [dict(r) for r in orig]
    extras = [
        {'Item_ID':'INV-0099','Item_Name':'EXTRA DIRTY ITEM','Supplier_UoM':'Box','Min_Stock_Threshold':'10','Category':'EXTRA'},
        {'Item_ID':'INV-0001','Item_Name':'DUP ESPRESSO','Supplier_UoM':'Kilogram','Min_Stock_Threshold':'99','Category':'Coffee Bean'},
        {'Item_ID':'INV-0100','Item_Name':'SYRUP ANEH','Supplier_UoM':'Unknown_UoM','Min_Stock_Threshold':'-5','Category':''},
        {'Item_ID':'','Item_Name':'NO ID','Supplier_UoM':'Pcs','Min_Stock_Threshold':'100','Category':'Other'},
        {'Item_ID':'INV-0200','Item_Name':'\u2601\ufe0f SPECIAL \u2615','Supplier_UoM':'Sachet','Min_Stock_Threshold':'500','Category':'Limited'},
        {'Item_ID':'INV-0002','Item_Name':'DUP ROBUSTA','Supplier_UoM':'Kilogram','Min_Stock_Threshold':'3','Category':'Coffee Bean'},
        {'Item_ID':'INV-0300','Item_Name':'','Supplier_UoM':'','Min_Stock_Threshold':'','Category':''},
        {'Item_ID':'INV-0400','Item_Name':'<script>alert(1)</script>','Supplier_UoM':'HACK','Min_Stock_Threshold':'999','Category':'HACKED'},
        {'Item_ID':None,'Item_Name':'NONE ITEM','Supplier_UoM':'','Min_Stock_Threshold':'','Category':''},
    ]
    for e in extras: rows.append(e)

    h = ['Item_ID','Item_Name','Supplier_UoM','Min_Stock_Threshold','Category']
    fp = os.path.join(OUTPUT_DIR, 'Master_Inventory (Competitors).csv')
    with open(fp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(h)
        for r in rows: w.writerow([r.get(c,'') for c in h])
    print(f'  {len(rows)} rows (42 + 9 dirty) -> {fp}')

#
# ─── GENERATE RECIPE_BOM ─────────────────────────────────────
#
def gen_bom():
    print('\n[BOM] Generating dirty Recipe_BOM...')
    with open(os.path.join(SRC_DIR, 'Recipe_BOM (Competitors).json'), encoding='utf-8') as f:
        data = json.load(f)
    mi = data['menu_items']

    dirty = [
        {'Menu_ID':'MENU-001','Menu_Name':'ESPRESSO DUP','Selling_Price_IDR':'Rp 18rb','ingredients':[]},
        {'Menu_ID':'MENU-099','Menu_Name':'\u2601\ufe0f VAPE COFFEE','Selling_Price_IDR':99999,
         'ingredients':[
             {'Item_ID':'INV-9999','Item_Name':'NONEXIST','qty_used':-99,'UoM':''},
             {'Item_ID':'INV-0001','Item_Name':"'; DROP--",'qty_used':0,'UoM':'gram'},
             {'Item_ID':'INV-0004','Item_Name':'Fresh Milk','qty_used':55555,'UoM':'ml'},
         ]},
        {'Menu_ID':'<SCRIPT>XSS</SCRIPT>','Menu_Name':'HACKED MENU','Selling_Price_IDR':0,
         'ingredients':[{'Item_ID':'INV-0001','Item_Name':"' OR 1=1",'qty_used':9999,'UoM':'xxx'}]},
        {'Menu_ID':'','Menu_Name':'EMPTY MENU','Selling_Price_IDR':-5000,'ingredients':[]},
        {'Menu_ID':'MENU-100','Menu_Name':'','Selling_Price_IDR':'','ingredients':[]},
    ]
    for d in dirty: mi.append(d)

    # Duplicate ingredients in MENU-005, MENU-010
    for m in mi:
        if m.get('Menu_ID') in ('MENU-005','MENU-010') and m.get('ingredients'):
            m['ingredients'].append(dict(m['ingredients'][0]))

    fp = os.path.join(OUTPUT_DIR, 'Recipe_BOM (Competitors).json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump({'menu_items': mi}, f, indent=2, ensure_ascii=False)
    print(f'  {len(mi)} menu items (25 + 5 dirty) -> {fp}')

#
# ─── GENERATE EMPLOYEE ───────────────────────────────────────
#
def gen_employee():
    print('\n[EMPLOYEE] Generating dirty Employee...')
    with open(os.path.join(SRC_DIR, 'Employee (Competitors).json'), encoding='utf-8') as f:
        data = json.load(f)
    emps = data['employees']

    dirty = [
        {'Employee_ID':'EMP-01','Full_Name':'BUDI COPY','Role':'Barista','Shift':'Morning'},
        {'Employee_ID':'','Full_Name':'NO ID BOT','Role':'','Shift':''},
        {'Employee_ID':'EMP-999','Full_Name':'GHOST WORKER','Role':'HACKER','Shift':'24/7'},
        {'Employee_ID':'EMP-88','Full_Name':'SYSTEM BOT','Role':'AI','Shift':'NONE'},
        {'Employee_ID':'TRAINEE','Full_Name':'MAGANG JOE','Role':'Trainee','Shift':'All'},
        {'Employee_ID':'EMP-07','Full_Name':'ROBO BARISTA','Role':'Robot','Shift':'Morning'},
        {'Employee_ID':'EMP-77','Full_Name':'','Role':'','Shift':''},
        {'Employee_ID':None,'Full_Name':None,'Role':None,'Shift':None},
        {'Employee_ID':'EMP-01 ','Full_Name':'WHITESPACE ID','Role':'Barista','Shift':'Evening'},
    ]
    for e in dirty: emps.append(e)

    fp = os.path.join(OUTPUT_DIR, 'Employee (Competitors).json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump({'employees': emps}, f, indent=2, ensure_ascii=False)
    print(f'  {len(emps)} employees (6 + 9 dirty) -> {fp}')

#
# ─── MAIN ─────────────────────────────────────────────────────
#
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print('='*60)
    print('  GENERATOR EXTREME DIRTY V3')
    print('  SUPER KOTOR + SUPER BERAT + AMAN PIPELINE')
    print('='*60)

    gen_sales()
    gen_warehouse()
    gen_inventory()
    gen_bom()
    gen_employee()

    # Copy pipeline ASLI tanpa modifikasi
    for f in ['pipeline.py','utils.py']:
        shutil.copy2(os.path.join(SRC_DIR, f), os.path.join(OUTPUT_DIR, f))

    print('\n' + '='*60)
    print('  GENERATION COMPLETE')
    print('='*60)
    for fn in sorted(os.listdir(OUTPUT_DIR)):
        if fn.endswith(('.py','.pyc')) or fn == '__pycache__': continue
        fp = os.path.join(OUTPUT_DIR, fn)
        print(f'    {fn:<50s} {os.path.getsize(fp):>12,} bytes')

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
generate_extra_dirty.py â€” Generator 5 dataset EXTRA DIRTY untuk Stress Test ETL Pipeline
=====================================================================================
Tujuan:
  - Membuat 5 dataset dengan struktur IDENTIK dengan asli
  - sales_history.csv  â†’ ~210.000 baris (dari ~170rb) + lebih kotor
  - warehouse_stock.json â†’ lebih banyak schema drift & corrupted entries
  - 3 dataset lainnya (Inventory, BOM, Employee) â†’ disalin utuh (clean reference)

Jenis-jenis "kotor" yang ditambahkan:
  SALES:
    - 8 varian error flag di Additional_Info
    - 7 format DateTime berbeda + unparseable garbage
    - 4 tipe ghost Menu_ID (PROMO-01, TEST, MENU-999, SPECIAL-XX)
    - 5 tipe ghost Employee_ID
    - 8 format Quantity edge case (koma, teks, kata, negatif, nol, sangat besar)
    - Duplicate Transaction_ID
    - NULL field kritis
    - Row dengan kolom kosong sebagian
    - Transaction_ID format aneh (double dash, underscore, suffix)
  WAREHOUSE:
    - Schema drift campur aduk (stock_remaining / sisa_stok_akhir) dalam 1 file
    - Beberapa hari dengan stock entry hilang
    - Stock negatif
    - Null Item_ID / stock_remaining
    - recorded_by ghost employee
    - Duplicate record_id
    - Corrupted record (field tidak lengkap)
    - UoM aneh/kosong
"""

import csv
import json
import os
import random
import shutil
from datetime import datetime, timedelta
from itertools import cycle

random.seed(42)

# â”€â”€â”€ Konfigurasi â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'extra_dirty')
SRC_DIR = os.path.dirname(__file__)

TARGET_SALES_ROWS = 210_000
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 6, 30)

# â”€â”€â”€ Reference data (dari dataset asli) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

VALID_MENU_IDS = list(MENU_NAMES.keys())  # 25 menu
GHOST_MENU_IDS = ['PROMO-01', 'TEST', 'MENU-999', 'MENU-000', 'SPECIAL-01', 'FREE-ITEM']

VALID_EMP_IDS = ['EMP-01', 'EMP-02', 'EMP-03', 'EMP-04', 'EMP-05', 'EMP-06']
GHOST_EMP_IDS = ['EMP-99', 'EMP-00', 'STAFF01', 'XX', 'TRAINEE', 'EMP-77', 'MANAGER']

ALL_ITEM_IDS = [f'INV-{i:04d}' for i in range(1, 43)]

# â”€â”€â”€ Bobot distribusi (dalam %) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Probabilitas tiap jenis "kotoran" per baris
P_ERROR_FLAG = 0.055       # 5.5% baris punya error flag
P_GHOST_MENU = 0.025       # 2.5% ghost menu
P_GHOST_EMP  = 0.035       # 3.5% ghost employee
P_NULL_FIELD = 0.012       # 1.2% null field kritis
P_DUPLICATE  = 0.008       # 0.8% duplicate Transaction_ID
P_BAD_DATE   = 0.005       # 0.5% unparseable date garbage
P_BAD_TRX_ID = 0.015       # 1.5% format Transaction_ID aneh

# Bobot format DateTime (harus total 1.0)
DT_WEIGHTS = {
    'iso': 0.58,            # "2025-06-12 08:42:41"
    'ddmmyyyy': 0.12,       # "14/01/2025 17:31"
    'monthname': 0.10,      # "Jun 13 2025 09:32"
    'compact12': 0.06,      # "202503270913"
    'mmddyyyy_ampm': 0.06,  # "01-14-2025 02:26 PM"
    'yyyymmdd8': 0.03,      # "20250327"
    'garbage': 0.05,        # teks acak tidak terparse
}

# Bobot kuantitas edge case
QTY_EDGE_WEIGHTS = {
    'comma_decimal': 0.025,   # "2,0"
    'text_suffix': 0.015,     # "1 pcs", "3 cups"
    'word_number': 0.008,     # "two", "tiga", "five"
    'negative': 0.008,        # -1, -5
    'zero': 0.025,            # 0
    'very_high': 0.006,       # 99, 150
    'null_text': 0.006,       # "N/A", "nan", "NULL"
    'empty': 0.004,           # string kosong
}

# Error flags distribution
ERROR_FLAGS = [
    'EROR', '#REF!', '#VALUE', 'ERROR', 'Err0r', 'ROER',
    'undefined', 'INVALID', 'NULL', 'N/A', 'nan', 'inv4lid',
    'SYSERR', 'TIMEOUT', 'UNKNOWN',
]

# â”€â”€â”€ Fungsi bantu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def pick_weighted(options, weights):
    """Pilih dari options berdasarkan bobot weights."""
    r = random.random() * sum(weights)
    cumulative = 0
    for opt, w in zip(options, weights):
        cumulative += w
        if r <= cumulative:
            return opt
    return options[-1]

def random_datetime(base_date):
    """Generate datetime dalam rentang 06:00 - 22:00."""
    hour = random.randint(6, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return base_date.replace(hour=hour, minute=minute, second=second)

def format_datetime(dt, fmt):
    """Format datetime ke string sesuai varian."""
    months_en = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    months_full = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    if fmt == 'iso':
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    elif fmt == 'ddmmyyyy':
        return dt.strftime('%d/%m/%Y %H:%M')
    elif fmt == 'monthname':
        m = months_en[dt.month - 1]
        return f'{m} {dt.day:02d} {dt.year} {dt.hour:02d}:{dt.minute:02d}'
    elif fmt == 'compact12':
        return dt.strftime('%Y%m%d%H%M')
    elif fmt == 'mmddyyyy_ampm':
        ampm = 'AM' if dt.hour < 12 else 'PM'
        h12 = dt.hour if dt.hour <= 12 else dt.hour - 12
        if h12 == 0: h12 = 12
        return f'{dt.month:02d}-{dt.day:02d}-{dt.year} {h12:02d}:{dt.minute:02d} {ampm}'
    elif fmt == 'yyyymmdd8':
        return dt.strftime('%Y%m%d')
    else:
        return 'not-a-date-???'

def generate_quantity(rng):
    """Generate quantity dengan kemungkinan edge case."""
    r = rng.random()
    if r < QTY_EDGE_WEIGHTS['comma_decimal']:
        # Comma sebagai desimal
        return f'{rng.randint(1,5)},{rng.randint(0,9)}'
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix']:
        return f'{rng.randint(1,5)} pcs'
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix'] + QTY_EDGE_WEIGHTS['word_number']:
        word_map = {1:'one',2:'two',3:'three',4:'four',5:'five',6:'six',
                    7:'seven',8:'eight',9:'nine',10:'ten'}
        return word_map.get(rng.randint(1,10), 'one')
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix'] + QTY_EDGE_WEIGHTS['word_number'] + QTY_EDGE_WEIGHTS['negative']:
        return str(-rng.randint(1,5))
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix'] + QTY_EDGE_WEIGHTS['word_number'] + QTY_EDGE_WEIGHTS['negative'] + QTY_EDGE_WEIGHTS['zero']:
        return '0'
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix'] + QTY_EDGE_WEIGHTS['word_number'] + QTY_EDGE_WEIGHTS['negative'] + QTY_EDGE_WEIGHTS['zero'] + QTY_EDGE_WEIGHTS['very_high']:
        return str(rng.randint(99, 200))
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix'] + QTY_EDGE_WEIGHTS['word_number'] + QTY_EDGE_WEIGHTS['negative'] + QTY_EDGE_WEIGHTS['zero'] + QTY_EDGE_WEIGHTS['very_high'] + QTY_EDGE_WEIGHTS['null_text']:
        return rng.choice(['N/A', 'NaN', 'nan', 'NULL', 'null', 'None', '-'])
    elif r < QTY_EDGE_WEIGHTS['comma_decimal'] + QTY_EDGE_WEIGHTS['text_suffix'] + QTY_EDGE_WEIGHTS['word_number'] + QTY_EDGE_WEIGHTS['negative'] + QTY_EDGE_WEIGHTS['zero'] + QTY_EDGE_WEIGHTS['very_high'] + QTY_EDGE_WEIGHTS['null_text'] + QTY_EDGE_WEIGHTS['empty']:
        return ''
    else:
        # Normal quantity
        return str(rng.randint(1, 5))

def generate_trx_id(date, seq, bad_format=False):
    """Generate Transaction_ID dengan kemungkinan format aneh."""
    ds = date.strftime('%Y%m%d')
    if bad_format:
        fmt = random.choice([
            f'TRX--{ds}-{seq:04d}',       # double dash
            f'TRX_{ds}-{seq:04d}X',        # underscore + suffix
            f'TRX-{ds}-{seq:04d}Z',        # suffix Z
            f'TRX-{ds}-{seq:04d}BKP',      # backup suffix
            f'TXN-{ds}-{seq:04d}',         # TXN instead of TRX
        ])
        return fmt
    return f'TRX-{ds}-{seq:04d}'


# â”€â”€â”€ GENERATOR SALES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_sales():
    """Generate sales_history.csv EXTRA DIRTY dengan ~210rb baris."""
    print("[SALES] Generating 210,000 rows of extra dirty sales data...")

    all_dates = []
    d = START_DATE
    while d <= END_DATE:
        all_dates.append(d)
        d += timedelta(days=1)

    rows = []
    trx_counters = {}  # date -> counter
    dup_pool = []       # simpan beberapa trx_id untuk di-duplicate nanti

    # Generate baris normal + dirty
    target = TARGET_SALES_ROWS
    # Kurangi ~1000 baris yang akan jadi duplicate
    total_to_gen = target + 1000

    for i in range(total_to_gen):
        date = random.choice(all_dates)
        ds = date.strftime('%Y%m%d')

        # Counter per hari
        if ds not in trx_counters:
            trx_counters[ds] = 0
        trx_counters[ds] += 1
        seq = trx_counters[ds]

        # â”€â”€ Transaction_ID â”€â”€
        is_bad_trx = random.random() < P_BAD_TRX_ID
        trx_id = generate_trx_id(date, seq, bad_format=is_bad_trx)

        # â”€â”€ DateTime â”€â”€
        dt_val = random_datetime(date)
        dt_fmt = pick_weighted(list(DT_WEIGHTS.keys()), list(DT_WEIGHTS.values()))
        dt_str = format_datetime(dt_val, dt_fmt)

        # â”€â”€ Employee_ID â”€â”€
        is_ghost_emp = random.random() < P_GHOST_EMP
        if is_ghost_emp:
            emp_id = random.choice(GHOST_EMP_IDS)
        else:
            emp_id = random.choice(VALID_EMP_IDS)

        # â”€â”€ Menu_ID & Item_Name â”€â”€
        is_ghost_menu = random.random() < P_GHOST_MENU
        if is_ghost_menu:
            menu_id = random.choice(GHOST_MENU_IDS)
            item_name = random.choice(['Unknown Item', '??', 'Promo Bundle', 'Free Item', 'TEST', ''])
        else:
            menu_id = random.choice(VALID_MENU_IDS)
            item_name = MENU_NAMES[menu_id]

        # â”€â”€ Quantity â”€â”€
        qty = generate_quantity(random)

        # â”€â”€ Additional_Info â”€â”€
        is_error = random.random() < P_ERROR_FLAG
        add_info = ''
        if is_error:
            add_info = random.choice(ERROR_FLAGS)

        # â”€â”€ Null field kritis â”€â”€
        is_null = random.random() < P_NULL_FIELD
        if is_null:
            # Null-kan salah satu field kritis secara acak
            null_choice = random.choice(['DateTime', 'Menu_ID', 'Quantity', 'Transaction_ID'])
            if null_choice == 'DateTime':
                dt_str = ''
            elif null_choice == 'Menu_ID':
                menu_id = ''
                item_name = ''
            elif null_choice == 'Quantity':
                qty = ''
            elif null_choice == 'Transaction_ID':
                trx_id = ''

        row = [trx_id, dt_str, emp_id, menu_id, item_name, qty, add_info]
        rows.append(row)

        # Simpan beberapa untuk duplicate nanti
        if not is_null and not is_bad_trx and i % 50 == 0:
            dup_pool.append(row)

        if (i + 1) % 50000 == 0:
            print(f"  ... {i+1:,} baris generated")

    # â”€â”€ Tambah DUPLICATE Transaction_ID â”€â”€
    n_dup = int(target * P_DUPLICATE)
    print(f"  ... Adding {n_dup} duplicate Transaction_ID rows")
    for _ in range(n_dup):
        if dup_pool:
            dup_row = random.choice(dup_pool)
            # Copy dengan trx_id sama tapi data sedikit berbeda
            new_row = dup_row.copy()
            new_row[1] = format_datetime(random_datetime(random.choice(all_dates)), 'iso')
            rows.append(new_row)

    # â”€â”€ Tulis CSV â”€â”€
    header = ['Transaction_ID', 'DateTime', 'Employee_ID', 'Menu_ID', 'Item_Name', 'Quantity', 'Additional_Info']
    filepath = os.path.join(OUTPUT_DIR, 'sales_history (Competitors).csv')

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)

    print(f"  [OK] {len(rows):,} baris -> {filepath}")
    return rows


# â”€â”€â”€ GENERATOR WAREHOUSE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_warehouse(sales_rows=None):
    """Generate warehouse_stock.json EXTRA DIRTY.

    Struktur: 175 hari (5 Jan - 30 Jun 2025, dengan beberapa hari kosong).
    Schema drift: campuran stock_remaining / sisa_stok_akhir dalam 1 file.
    Dirty additions: stock negatif, missing entries, ghost recorded_by, dll.
    """
    print("[WAREHOUSE] Generating extra dirty warehouse data...")

    # Tentukan hari-hari yang akan di-record (beberapa hari sengaja di-skip)
    all_dates = []
    d = START_DATE
    while d <= END_DATE:
        all_dates.append(d)
        d += timedelta(days=1)

    # Skip beberapa hari secara acak (orphan days)
    skip_dates = set()
    for d in all_dates:
        if random.random() < 0.035:  # 3.5% hari di-skip
            skip_dates.add(d)

    # Record dates (tidak di-skip)
    record_dates = [d for d in all_dates if d not in skip_dates]
    print(f"  ... {len(all_dates)} total days, {len(skip_dates)} skipped â†’ {len(record_dates)} records")

    # Recorded_by dengan ghost
    recorded_by_pool = VALID_EMP_IDS + ['EMP-07', 'EMP-88', 'TRAINEE', 'SYSADMIN']

    records = []
    rec_seq = 0

    for rec_date in record_dates:
        rec_seq += 1
        ds = rec_date.strftime('%Y-%m-%d')
        rec_id = f'WH-{rec_date.strftime("%Y%m%d")}-{random.randint(1,3):03d}'

        recorded_by = random.choice(recorded_by_pool)

        stock_entries = []

        # Tentukan apakah record ini pake schema drift >70% chance
        # Makin mendekati Juni, makin besar chance schema drift
        days_from_start = (rec_date - START_DATE).days
        total_days = (END_DATE - START_DATE).days
        drift_prob = 0.15 + (days_from_start / total_days) * 0.7  # 15% -> 85%
        use_sisa_stok = random.random() < drift_prob

        for item_id in ALL_ITEM_IDS:
            # 3% chance item tidak tercatat hari ini (missing entry)
            if random.random() < 0.03:
                continue

            # Stock value dengan kemungkinan negatif
            base_stock = random.uniform(500, 50000)
            if random.random() < 0.02:  # 2% stock negatif
                stock_val = round(-random.uniform(100, 5000), 1)
            else:
                stock_val = round(base_stock, 1)

            delivery = round(random.uniform(0, 2000), 1) if random.random() < 0.25 else 0.0

            # UoM sesuai item
            if int(item_id.split('-')[1]) <= 3:
                uom = 'gram'
            elif item_id in ('INV-0014', 'INV-0015', 'INV-0019', 'INV-0023', 'INV-0024', 'INV-0041'):
                uom = 'gram'
            elif item_id in ('INV-0025', 'INV-0026', 'INV-0027', 'INV-0028', 'INV-0029', 'INV-0030', 'INV-0031', 'INV-0032', 'INV-0033', 'INV-0034', 'INV-0035', 'INV-0036', 'INV-0037', 'INV-0038', 'INV-0039', 'INV-0040', 'INV-0017', 'INV-0018'):
                uom = 'pcs'
            else:
                uom = 'ml'

            # 1.5% chance UoM aneh
            if random.random() < 0.015:
                uom = random.choice(['', 'unknown', 'liters', 'kg', 'boxes', 'PACKS'])

            # 1% chance null Item_ID atau stock
            if random.random() < 0.01:
                entry = {
                    'Item_ID': item_id if random.random() > 0.5 else None,
                    ('sisa_stok_akhir' if use_sisa_stok else 'stock_remaining'): None if random.random() < 0.5 else stock_val,
                    'delivery_in': delivery,
                    'UoM': uom,
                }
            else:
                if use_sisa_stok:
                    entry = {
                        'Item_ID': item_id,
                        'sisa_stok_akhir': stock_val,
                        'delivery_in': delivery,
                        'UoM': uom,
                    }
                else:
                    entry = {
                        'Item_ID': item_id,
                        'stock_remaining': stock_val,
                        'delivery_in': delivery,
                        'UoM': uom,
                    }

            stock_entries.append(entry)

        # 2% chance record rusak (missing field)
        if random.random() < 0.02:
            record = {
                'record_id': rec_id,
                'date': ds,
                # recorded_by sengaja dihilangkan
                'stock_entries': stock_entries,
            }
        else:
            record = {
                'record_id': rec_id,
                'date': ds,
                'recorded_by': recorded_by,
                'stock_entries': stock_entries,
            }

        records.append(record)

    # Tambah 2 record duplicate (record_id sama)
    if len(records) > 10:
        dup_rec = random.choice(records)
        dup = dict(dup_rec)
        dup['date'] = (datetime.strptime(dup['date'], '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        records.append(dup)

    warehouse = {'records': records}

    filepath = os.path.join(OUTPUT_DIR, 'warehouse_stock (Competitors).json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(warehouse, f, indent=2, ensure_ascii=False)

    total_entries = sum(len(r.get('stock_entries', [])) for r in records)
    print(f"  [OK] {len(records)} records, {total_entries} stock entries -> {filepath}")
    return records


# â”€â”€â”€ COPY CLEAN DATASETS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def copy_clean_datasets():
    """Copy 3 reference datasets unchanged."""
    files = [
        'Master_Inventory (Competitors).csv',
        'Recipe_BOM (Competitors).json',
        'Employee (Competitors).json',
    ]
    for fname in files:
        src = os.path.join(SRC_DIR, fname)
        dst = os.path.join(OUTPUT_DIR, fname)
        shutil.copy2(src, dst)
        size = os.path.getsize(dst)
        print(f"  [OK] {fname} -> {size:,} bytes (copied unchanged)")


# â”€â”€â”€ MAIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    print("=" * 60)
    print("  GENERATOR EXTRA DIRTY DATASET - Stress Test ETL Pipeline")
    print("=" * 60)
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output folder: {OUTPUT_DIR}")
    print()

    # 1. Generate sales (paling besar)
    sales_rows = generate_sales()
    print()

    # 2. Generate warehouse
    generate_warehouse(sales_rows)
    print()

    # 3. Copy clean datasets
    copy_clean_datasets()
    print()

    # â”€â”€â”€ Summary â”€â”€â”€
    print("=" * 60)
    print("  GENERATION COMPLETE")
    print("=" * 60)
    print(f"  Location: {OUTPUT_DIR}")
    for fname in os.listdir(OUTPUT_DIR):
        fpath = os.path.join(OUTPUT_DIR, fname)
        size = os.path.getsize(fpath)
        if fname.endswith('.csv'):
            with open(fpath, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f) - 1  # minus header
            print(f"    {fname:<45s} {size:>10,} bytes  ({line_count:,} baris)")
        else:
            print(f"    {fname:<45s} {size:>10,} bytes")


if __name__ == '__main__':
    main()

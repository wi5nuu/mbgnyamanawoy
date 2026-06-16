# ============================================================
# utils.py — Helper Functions & Constants
# Kopikita Roastery — Data Automation Pipeline
# ============================================================
# Berisi semua fungsi pendukung yang dipakai oleh pipeline.py:
#   - Konstanta & konfigurasi
#   - Parser tanggal multi-format (resilient terhadap pandas 3.x)
#   - Parser kuantitas (3-layer rescue dari teks kotor)
#   - Normalisasi schema drift gudang (stock_remaining vs sisa_stok_akhir)
#   - Konversi UoM Supplier → Warehouse (Kilogram/Liter/Karton → gram/ml/pcs)
#   - Builder BOM DataFrame dari nested JSON
# ============================================================

import re
import json
import logging
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

# ============================================================
# [CONFIG] PATH FILE
# ============================================================
PATH_SALES      = 'sales_history (Competitors).csv'
PATH_WAREHOUSE  = 'warehouse_stock (Competitors).json'
PATH_INVENTORY  = 'Master_Inventory (Competitors).csv'
PATH_BOM        = 'Recipe_BOM (Competitors).json'
PATH_EMPLOYEE   = 'Employee (Competitors).json'

PATH_OUTPUT_REPORT     = 'outputs/Action_Report.csv'
PATH_OUTPUT_QUARANTINE = 'outputs/quarantine_log.csv'
PATH_OUTPUT_EMPLOYEE   = 'outputs/Employee_Error_Report.csv'

# ============================================================
# [CONFIG] THRESHOLD & ANOMALY DETECTION
# ============================================================

# [ANOMALY LOGIC] JUSTIFIKASI MATEMATIS THRESHOLD:
# Berdasarkan distribusi variance dari 7,308 baris rekonsiliasi historis:
#   - Q1          : -5.00 units
#   - Q3          : 285.25 units
#   - IQR         : 290.25 units
#   - Batas outlier statistik (Q3 + 1.5×IQR) = 720.62 units
#   - Threshold dipilih: 1,000 units (LEBIH KONSERVATIF dari batas statistik)
#
# Artinya: pipeline hanya memflag variance yang benar-benar ekstrem,
# yaitu selisih >1,000 units, yang berada di atas outlier boundary 721.
# Ini meminimalkan false positive dan fokus pada anomali operasional nyata.
#
# Interpretasi Variance:
#   Variance = Physical_Stock - Expected_Stock
#   Positif  → POS overcounting: POS klaim lebih banyak konsumsi dari yg hilang di gudang
#   Negatif  → Shrinkage/theft: stok hilang melebihi apa yang bisa dijelaskan POS
ANOMALY_THRESHOLD = 1_000

# Threshold restock fallback (jika konversi UoM gagal, atau item baru di stress test)
FALLBACK_RESTOCK_THRESHOLD = 20_000

# ============================================================
# [CONFIG] ITEM TANPA RESEP DI BOM (no-BOM items)
# ============================================================
# 8 item ada di Master_Inventory tapi TIDAK muncul di resep manapun:
#   INV-0002 Robusta Bean, INV-0003 Decaf Bean, INV-0005 Oat Milk,
#   INV-0006 Almond Milk, INV-0007 Condensed Milk,
#   INV-0018 Green Tea Bag, INV-0023 Sugar, INV-0027 Paper Cup 16oz
#
# Konsekuensi dalam pipeline:
#   - POS_Consumed item ini selalu = 0 (tidak ada penjualan yang memakai bahan ini)
#   - Expected_Stock = Prev_Physical + Delivery_In (tidak ada pengurangan dari POS)
#   - Jika stock fisik bergerak > ANOMALY_THRESHOLD dari expected → Anomaly
#
# Ini adalah EXPECTED BEHAVIOR yang BENAR secara bisnis:
#   Stock bergerak tanpa penjelasan POS = perlu investigasi owner.
#   Kemungkinan: pemakaian manual, sampel tester, atau kehilangan yang tidak tercatat.
NO_BOM_ITEMS = {
    'INV-0002', 'INV-0003', 'INV-0005', 'INV-0006',
    'INV-0007', 'INV-0018', 'INV-0023', 'INV-0027'
}

# ============================================================
# [INOVASI 2] UNIT COST PER ITEM — Estimasi harga pasar (IDR)
# ============================================================
# Sumber: estimasi harga pasar Indonesia 2025.
# Satuan mengikuti warehouse UoM (gram/ml/pcs).
# Digunakan HANYA untuk Shrinkage Anomaly → Estimated_Loss_IDR.
# Wajib di-label "estimasi" di laporan karena tidak dari dataset.
UNIT_COST_IDR = {
    'INV-0001': 280,    # Espresso Bean Arabica  → Rp 280/gram  (~Rp 280rb/kg)
    'INV-0002': 140,    # Robusta Bean           → Rp 140/gram  (~Rp 140rb/kg)
    'INV-0003': 320,    # Decaf Bean             → Rp 320/gram  (~Rp 320rb/kg)
    'INV-0004': 25,     # Fresh Milk             → Rp 25/ml     (~Rp 25rb/liter)
    'INV-0005': 80,     # Oat Milk               → Rp 80/ml     (~Rp 80rb/liter)
    'INV-0006': 95,     # Almond Milk            → Rp 95/ml     (~Rp 95rb/liter)
    'INV-0007': 15,     # Condensed Milk         → Rp 15/ml
    'INV-0008': 85,     # Whipping Cream         → Rp 85/ml
    'INV-0009': 90,     # Vanilla Syrup          → Rp 90/ml
    'INV-0010': 90,     # Caramel Syrup          → Rp 90/ml
    'INV-0011': 90,     # Hazelnut Syrup         → Rp 90/ml
    'INV-0012': 100,    # Chocolate Powder       → Rp 100/gram
    'INV-0013': 90,     # Taro Powder            → Rp 90/gram
    'INV-0014': 350,    # Matcha Powder          → Rp 350/gram
    'INV-0015': 280,    # Green Tea Powder       → Rp 280/gram
    'INV-0016': 18,     # Simple Syrup           → Rp 18/ml
    'INV-0017': 250,    # Black Tea Bag          → Rp 250/pcs
    'INV-0018': 280,    # Green Tea Bag          → Rp 280/pcs
    'INV-0019': 12,     # Lemon Juice            → Rp 12/ml
    'INV-0020': 30,     # Coconut Milk           → Rp 30/ml
    'INV-0021': 65,     # Brown Sugar Syrup      → Rp 65/ml
    'INV-0022': 20,     # Sparkling Water        → Rp 20/ml
    'INV-0023': 12,     # Sugar                  → Rp 12/gram
    'INV-0024': 2,      # Ice Cube               → Rp 2/gram
    'INV-0025': 1000,   # Paper Cup 8oz          → Rp 1.000/pcs
    'INV-0026': 1100,   # Paper Cup 12oz         → Rp 1.100/pcs
    'INV-0027': 1200,   # Paper Cup 16oz         → Rp 1.200/pcs
    'INV-0028': 1300,   # Plastic Cup 16oz       → Rp 1.300/pcs
    'INV-0029': 500,    # Lid 8oz                → Rp 500/pcs
    'INV-0030': 550,    # Lid 12-16oz            → Rp 550/pcs
    'INV-0031': 600,    # Dome Lid               → Rp 600/pcs
    'INV-0032': 140,    # Paper Straw            → Rp 140/pcs
    'INV-0033': 180,    # Wooden Stirrer         → Rp 180/pcs
    'INV-0034': 200,    # Napkin                 → Rp 200/pcs
    'INV-0035': 15000,  # Croissant Plain Frozen → Rp 15.000/pcs
    'INV-0036': 18000,  # Almond Croissant       → Rp 18.000/pcs
    'INV-0037': 12000,  # Banana Bread Slice     → Rp 12.000/pcs
    'INV-0038': 10000,  # Chocolate Muffin       → Rp 10.000/pcs
    'INV-0039': 5000,   # Cheese Slice           → Rp 5.000/pcs
    'INV-0040': 25000,  # Bread Loaf             → Rp 25.000/pcs
    'INV-0041': 8000,   # Butter Portion         → Rp 8.000/pcs
    'INV-0042': 45,     # Vanilla Ice Cream      → Rp 45/ml
}

# ============================================================
# [CONFIG] KARTON → WAREHOUSE UoM CONVERSION (per Item_ID)
# ============================================================
KARTON_CONVERSION = {
    # Tea bags: 100 pcs per box
    'INV-0017': 100,    # Black Tea Bag  → pcs
    'INV-0018': 100,    # Green Tea Bag  → pcs
    # Dairy liquid items (tracked in ml)
    'INV-0007': 4_440,  # Condensed Milk → 12 kaleng × 370ml
    'INV-0022': 7_920,  # Sparkling Water→ 24 botol × 330ml
    # Cups & Lids: 50 pcs per sleeve
    'INV-0025': 50,     # Paper Cup 8oz
    'INV-0026': 50,     # Paper Cup 12oz
    'INV-0027': 50,     # Paper Cup 16oz
    'INV-0028': 50,     # Plastic Cup 16oz
    'INV-0029': 50,     # Lid 8oz
    'INV-0030': 50,     # Lid 12-16oz
    'INV-0031': 50,     # Dome Lid
    # Straws & Stirrers: 250 pcs per bulk pack
    'INV-0032': 250,    # Paper Straw
    'INV-0033': 250,    # Wooden Stirrer
    # Napkins: 200 pcs per pack
    'INV-0034': 200,
    # Frozen food & cheese: 20 pcs per karton
    'INV-0035': 20,     # Croissant Plain Frozen
    'INV-0036': 20,     # Almond Croissant Frozen
    'INV-0037': 20,     # Banana Bread Slice
    'INV-0038': 24,     # Chocolate Muffin (24 per box)
    'INV-0039': 20,     # Cheese Slice
}

# ============================================================
# [CONFIG] WORD-TO-NUMBER MAPPING (extensible untuk stress test)
# ============================================================
# Rescue untuk kolom Quantity yang berisi teks angka.
# Tambah pasangan baru di sini jika stress test membawa bahasa/format baru.
WORD_TO_NUM = {
    # Bahasa Indonesia
    'satu': 1,  'dua': 2,    'tiga': 3,   'empat': 4, 'lima': 5,
    'enam': 6,  'tujuh': 7,  'delapan': 8,'sembilan': 9, 'sepuluh': 10,
    'nol': 0,   'nul': 0,
    # English
    'one': 1,   'two': 2,    'three': 3,  'four': 4,  'five': 5,
    'six': 6,   'seven': 7,  'eight': 8,  'nine': 9,  'ten': 10,
    'zero': 0,  'nil': 0,
}

# ============================================================
# [CONFIG] POLA ERROR FLAG DI Additional_Info
# ============================================================
# Menangkap semua variasi error output dari POS:
# Err0r, ERROR, EROR, #VALUE, #REF!, undefined, inv4lid, ROER, dll.
# Baris dengan error flag ini dianggap transaksi TIDAK VALID —
# dibuang dari pipeline DAN dicatat di quarantine_log.
ERROR_FLAG_PATTERN = re.compile(
    r'^(err|error|eror|#value|#ref!|undefined|invalid|inv4lid|roer)',
    re.IGNORECASE
)

# ============================================================
# [CONFIG] REASON CODES quarantine_log.csv
# ============================================================
REASON_NULL_FIELD   = 'NULL_CRITICAL_FIELD'
REASON_BAD_DATE     = 'UNPARSEABLE_DATE'
REASON_NEG_QTY      = 'NEGATIVE_QUANTITY'
REASON_BAD_QTY      = 'UNPARSEABLE_QUANTITY'
REASON_ZERO_QTY     = 'ZERO_QUANTITY'          # Qty=0: transaksi void/cancelled, silent drop sebelumnya
REASON_GHOST_MENU   = 'GHOST_MENU_ID'
REASON_ERROR_FLAG   = 'ERROR_FLAG_IN_ADDINFO'
REASON_DUPLICATE    = 'DUPLICATE_TRANSACTION_ID'


# ============================================================
# LOGGING SETUP
# ============================================================
def setup_logging():
    """
    Setup logging yang robust terhadap Windows dan Linux.

    Root cause Bug 1 (Windows):
      Di Windows, library dalam import chain (pandas, numpy) atau IDE (VS Code,
      PyCharm, conda) bisa menambah handler ke root logger SEBELUM basicConfig
      kita dipanggil. Karena basicConfig bersifat idempotent (tidak jalan jika
      handler sudah ada), hasilnya root logger punya 2+ handler.
      Dengan propagate=True pada named logger, setiap log.info() dikirim ke
      named handler + root handler = output ganda/interleaved di terminal.

    Fix:
      1. Hapus SEMUA handler existing dari root dan named logger sebelum setup.
      2. Buat handler tunggal secara eksplisit (bukan via basicConfig).
      3. Pastikan named logger tidak punya handler sendiri (hanya propagasi ke root).
    """
    import sys as _sys

    # ── Bersihkan semua handler existing (Windows fix) ───────────
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        h.close()

    named_logger = logging.getLogger('KopikitaPipeline')
    for h in named_logger.handlers[:]:
        named_logger.removeHandler(h)
        h.close()

    # ── Setup single StreamHandler ke stderr ──────────────────────
    handler = logging.StreamHandler(_sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s  [%(levelname)-7s]  %(message)s',
        datefmt='%H:%M:%S'
    ))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Named logger: propagate=True, tanpa handler sendiri
    # → message cukup naik ke root (1 handler) = 1x output
    named_logger.propagate = True
    named_logger.setLevel(logging.INFO)

    return named_logger


# ============================================================
# [DATA CLEANSING] PARSER — DateTime row-by-row fallback
# ============================================================
# Catatan: infer_datetime_format dihapus di pandas 3.0+.
# Fungsi ini menangani format eksotis yang gagal di vectorized pass.
def parse_datetime(val):
    """
    Parse satu nilai DateTime dari berbagai format.
    Return: pd.Timestamp | None
    Format: ISO · DD/MM/YYYY · Month name · Compact 12-digit · MM-DD-YYYY AM/PM
    """
    if pd.isna(val) or str(val).strip() == '':
        return None
    s = str(val).strip()

    # Try 1: pandas default (ISO 8601 dan turunannya)
    try:
        return pd.to_datetime(s)
    except Exception:
        pass
    # Try 2: DD/MM/YYYY
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    # Try 3: Month name (Jan 01 2025 atau January 1 2025)
    for fmt in ('%b %d %Y %H:%M', '%b %d %Y', '%B %d %Y %H:%M', '%B %d %Y'):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    # Try 4: Compact 12-digit YYYYMMDDHHMI
    if re.match(r'^\d{12}$', s):
        try:
            return pd.to_datetime(s, format='%Y%m%d%H%M')
        except Exception:
            pass
    # Try 5: YYYYMMDD 8-digit
    if re.match(r'^\d{8}$', s):
        try:
            return pd.to_datetime(s, format='%Y%m%d')
        except Exception:
            pass
    # Try 6: MM-DD-YYYY AM/PM
    for fmt in ('%m-%d-%Y %I:%M %p', '%m-%d-%Y %I:%M%p',
                '%m-%d-%Y %H:%M:%S', '%m-%d-%Y %H:%M', '%m-%d-%Y'):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    return None


def parse_datetime_series(series):
    """
    Versi vectorized parse_datetime untuk seluruh Series sekaligus.
    Jauh lebih cepat dari apply() untuk 100K+ baris.
    Strategy: daisy-chain per format → row-by-row hanya untuk sisa exotics.
    """
    result = pd.Series([pd.NaT] * len(series), index=series.index)

    # Pass 1: ISO/default (vectorized, handles most rows)
    mask = result.isna() & series.notna()
    if mask.any():
        result[mask] = pd.to_datetime(series[mask], errors='coerce')

    # Pass 2: DD/MM/YYYY dan variannya (vectorized)
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        mask = result.isna() & series.notna()
        if not mask.any():
            break
        result[mask] = pd.to_datetime(series[mask], format=fmt, errors='coerce')

    # Pass 3: Month name (vectorized)
    for fmt in ('%b %d %Y %H:%M', '%b %d %Y', '%B %d %Y %H:%M', '%B %d %Y'):
        mask = result.isna() & series.notna()
        if not mask.any():
            break
        result[mask] = pd.to_datetime(series[mask], format=fmt, errors='coerce')

    # Pass 4: Compact 12-digit (vectorized, filter ke string 12 char dulu)
    mask = result.isna() & series.notna()
    if mask.any():
        compact = mask & series.str.match(r'^\d{12}$', na=False)
        if compact.any():
            result[compact] = pd.to_datetime(series[compact], format='%Y%m%d%H%M', errors='coerce')

    # Pass 5: Sisa exotics → row-by-row (jumlah baris di sini sangat sedikit)
    mask = result.isna() & series.notna()
    if mask.any():
        result[mask] = series[mask].apply(parse_datetime)

    return result


# ============================================================
# [DATA CLEANSING] PARSER — Quantity 3-layer rescue
# ============================================================
def parse_quantity(val):
    """
    Convert nilai Quantity dari berbagai format ke float.
    Return: float >= 0 | None (jika gagal atau negatif)

    Layer 1: direct numeric cast (ganti koma desimal)
    Layer 2: word-map dict (teks angka BI/EN)
    Layer 3: regex — ekstrak angka pertama dari string apapun
    """
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ('', 'nan', 'none', 'null', 'nil', '-'):
        return None

    # Layer 1: konversi langsung (ganti koma → titik)
    try:
        result = float(s.replace(',', '.'))
        return result if result >= 0 else None
    except ValueError:
        pass

    # Layer 2: word-map
    if s in WORD_TO_NUM:
        return float(WORD_TO_NUM[s])

    # Layer 3: regex ekstrak angka pertama dari string
    match = re.search(r'(\d+[.,]?\d*)', s)
    if match:
        try:
            result = float(match.group(1).replace(',', '.'))
            return result if result >= 0 else None
        except ValueError:
            pass

    return None


# ============================================================
# [DATA CLEANSING] VALIDATOR — Error flag check
# ============================================================
def is_error_flag(val):
    """
    Return True jika Additional_Info mengandung pola error dari POS.
    Baris dengan error flag dianggap transaksi rusak dan di-exclude sepenuhnya.
    """
    if pd.isna(val) or str(val).strip() == '':
        return False
    return bool(ERROR_FLAG_PATTERN.match(str(val).strip()))


# ============================================================
# [DATA INGESTION] SCHEMA DRIFT — Normalisasi warehouse JSON
# ============================================================
def normalize_warehouse_entry(entry):
    """
    FIX SCHEMA DRIFT: per 2025-04-01 key berubah dari
    'stock_remaining' (English) → 'sisa_stok_akhir' (Indonesian).
    Fungsi ini menyatukan keduanya ke 'stock_remaining'.
    """
    if 'sisa_stok_akhir' in entry and 'stock_remaining' not in entry:
        entry = dict(entry)
        entry['stock_remaining'] = entry.pop('sisa_stok_akhir')
    return entry


def flatten_warehouse_records(records):
    """
    Flatten nested warehouse JSON → list of flat dicts.
    Input:  [{record_id, date, recorded_by, stock_entries:[{Item_ID, stock_remaining,...}]}]
    Output: [{date, Item_ID, stock_remaining, delivery_in, UoM}, ...]
    """
    rows = []
    for record in records:
        try:
            date_str = record.get('date')
            try:
                date = pd.to_datetime(date_str).date()
            except Exception:
                continue

            for entry in record.get('stock_entries', []):
                entry = normalize_warehouse_entry(entry)
                item_id  = entry.get('Item_ID')
                stock    = entry.get('stock_remaining')
                delivery = entry.get('delivery_in', 0)
                uom      = entry.get('UoM', '')

                if item_id is None or stock is None:
                    continue

                try:
                    stock    = float(stock)
                    delivery = float(delivery) if delivery is not None else 0.0
                except (TypeError, ValueError):
                    continue

                rows.append({
                    'Date'           : date,
                    'Item_ID'        : str(item_id).strip(),
                    'stock_remaining': stock,
                    'delivery_in'    : delivery,
                    'UoM'            : str(uom).strip().lower(),
                })
        except Exception:
            continue   # record rusak total → skip, pipeline tidak crash
    return rows


# ============================================================
# [CALCULATION] UoM CONVERTER — Supplier UoM → Warehouse UoM
# ============================================================
def build_threshold_dict(inventory_df, log=None):
    """
    Konversi Min_Stock_Threshold dari Supplier_UoM ke Warehouse UoM.
    Kilogram → gram (×1000) | Liter → ml (×1000) | Pcs → pcs | Karton → per-item
    """
    threshold_dict = {}
    for _, row in inventory_df.iterrows():
        item_id      = str(row['Item_ID']).strip()
        supplier_uom = str(row['Supplier_UoM']).strip()
        val          = float(row['Min_Stock_Threshold'])

        if supplier_uom == 'Kilogram':
            threshold_dict[item_id] = val * 1_000          # → gram
        elif supplier_uom == 'Liter':
            threshold_dict[item_id] = val * 1_000          # → ml
        elif supplier_uom == 'Pcs':
            threshold_dict[item_id] = val                  # → pcs (no change)
        elif supplier_uom == 'Karton':
            if item_id in KARTON_CONVERSION:
                threshold_dict[item_id] = val * KARTON_CONVERSION[item_id]
            else:
                threshold_dict[item_id] = FALLBACK_RESTOCK_THRESHOLD
                if log:
                    log.warning(f"Karton conversion tidak ada untuk {item_id}, pakai fallback {FALLBACK_RESTOCK_THRESHOLD:,}")
        else:
            threshold_dict[item_id] = FALLBACK_RESTOCK_THRESHOLD
            if log:
                log.warning(f"UoM tidak dikenal '{supplier_uom}' untuk {item_id}, pakai fallback")
    return threshold_dict


# ============================================================
# [CALCULATION] BOM BUILDER — Recipe_BOM.json → flat DataFrame
# ============================================================
def build_bom_df(bom_data):
    """
    Flatten nested Recipe_BOM.json → DataFrame [Menu_ID, Item_ID, qty_used, BOM_UoM].
    Dipakai di Stage 3 untuk BOM expansion: Sales × BOM → daily ingredient consumption.
    """
    rows = []
    for menu in bom_data.get('menu_items', []):
        menu_id = menu.get('Menu_ID')
        if not menu_id:
            continue
        for ing in menu.get('ingredients', []):
            item_id  = ing.get('Item_ID')
            qty_used = ing.get('qty_used')
            uom      = ing.get('UoM', '')
            if item_id is None or qty_used is None:
                continue
            try:
                qty_used = float(qty_used)
            except (TypeError, ValueError):
                continue
            rows.append({
                'Menu_ID' : str(menu_id).strip(),
                'Item_ID' : str(item_id).strip(),
                'qty_used': qty_used,
                'BOM_UoM' : str(uom).strip().lower(),
            })
    return pd.DataFrame(rows)


def build_valid_employee_set(employee_data):
    """Extract set of valid Employee_IDs dari Employee.json."""
    return set(
        str(e.get('Employee_ID', '')).strip()
        for e in employee_data.get('employees', [])
        if e.get('Employee_ID')
    )

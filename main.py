# =============================================================================
# KOPIKITA ROASTERY — AUTOMATED DATA PIPELINE (ETL)
# Hackathon Track: Data Automation
# Author: Tim Peserta
# Deskripsi: Pipeline otomatis dari ingesti data mentah hingga Action_Report.csv
#             tanpa intervensi manusia (Zero Human Intervention)
# Versi: 2.0 (fixed: day-1 reconciliation, restock per-day, anomaly direction)
# =============================================================================

import sys, io
# Fix encoding untuk Windows PowerShell (agar karakter Unicode bisa ditampilkan)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import json
import re
import os
import warnings
warnings.filterwarnings("ignore")   # Suppress UserWarning dari pandas date parsing

from datetime import datetime

# ==============================================================================
# HELPER RESILIENCE & UTILS
# ==============================================================================
def find_dataset_file(directory: str, pattern_str: str, default_filename: str) -> str:
    """Mencari file di direktori yang mencocokkan pattern (case-insensitive regex).
    Mengembalikan path absolut jika ditemukan, jika tidak kembali ke default."""
    if not os.path.isdir(directory):
        return os.path.join(directory, default_filename)
    try:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        for f in os.listdir(directory):
            if pattern.search(f):
                return os.path.join(directory, f)
    except Exception as e:
        print(f"    WARNING saat memindai direktori: {e}")
    return os.path.join(directory, default_filename)


def standardize_columns(df: pd.DataFrame, alias_map: dict) -> pd.DataFrame:
    """Standardisasi nama kolom DataFrame berdasarkan alias map secara case-insensitive."""
    if df.empty:
        return df
    df.columns = [str(c).strip() for c in df.columns]
    new_cols = []
    for col in df.columns:
        col_lower = col.lower()
        matched = col
        for canonical, aliases in alias_map.items():
            if col_lower == canonical.lower() or col_lower in [a.lower() for a in aliases]:
                matched = canonical
                break
        new_cols.append(matched)
    df.columns = new_cols
    return df


def get_case_insensitive_key(d: dict, aliases: list, default=None):
    """Membaca value dari dict secara case-insensitive & alias-tolerant."""
    if not isinstance(d, dict):
        return default
    aliases_lower = [str(a).strip().lower() for a in aliases]
    for k, v in d.items():
        if str(k).strip().lower() in aliases_lower:
            return v
    for a in aliases:
        if a in d:
            return d[a]
    return default


# ==============================================================================
# ALIAS NAMA KOLOM UNTUK SCHEMA DRIFT RESILIENCE
# ==============================================================================
ALIAS_INVENTORY = {
    "Item_ID": ["item_id", "item id", "itemid", "id_item", "id_barang", "id barang", "id"],
    "Item_Name": ["item_name", "item name", "itemname", "nama_barang", "nama barang", "nama_item", "nama item"],
    "Supplier_UoM": ["supplier_uom", "supplier uom", "supplieruom", "uom", "satuan"],
    "Min_Stock_Threshold": ["min_stock_threshold", "min stock threshold", "min_stock", "min stock", "threshold", "minimum_stok", "minimum stok"],
}

ALIAS_SALES = {
    "Transaction_ID": ["transaction_id", "transaction id", "id_transaction", "id transaction", "trx_id", "trx id", "id_transaksi", "id transaksi"],
    "DateTime": ["datetime", "date_time", "date time", "date", "tanggal", "waktu"],
    "Employee_ID": ["employee_id", "employee id", "id_employee", "id employee", "nik", "id_karyawan", "id karyawan"],
    "Menu_ID": ["menu_id", "menu id", "id_menu", "id menu", "menu"],
    "Item_Name": ["item_name", "item name", "nama_menu", "nama menu", "nama_item", "nama item", "nama barang", "nama_barang"],
    "Quantity": ["quantity", "qty", "amount", "jumlah", "porsi", "count"],
}

# ==============================================================================
# KONFIGURASI PATH DATASET
# ==============================================================================
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset_dataautomation")

PATH_SALES     = find_dataset_file(DATASET_DIR, r"sales_history", "sales_history (Competitors).csv")
PATH_WAREHOUSE = find_dataset_file(DATASET_DIR, r"warehouse_stock", "warehouse_stock (Competitors).json")
PATH_INVENTORY = find_dataset_file(DATASET_DIR, r"Master_Inventory", "Master_Inventory (Competitors).csv")
PATH_BOM       = find_dataset_file(DATASET_DIR, r"Recipe_BOM", "Recipe_BOM (Competitors).json")
PATH_EMPLOYEE  = find_dataset_file(DATASET_DIR, r"Employee", "Employee (Competitors).json")
OUTPUT_PATH    = os.path.join(BASE_DIR, "Action_Report.csv")

# ==============================================================================
# KONSTANTA KONVERSI UNIT PENGUKURAN (UoM)
# Supplier UoM → Warehouse Base Unit
# Sumber: Dokumen Rancangan Teknis — Bagian 3 (UoM Conversion)
# ==============================================================================
UOM_TO_BASE = {
    "kilogram": 1000,   # 1 kg = 1000 gram
    "kg"      : 1000,
    "liter"   : 1000,   # 1 liter = 1000 ml
    "l"       : 1000,
    "galon"   : 3785,   # 1 galon = 3785 ml (US gallon)
    "gallon"  : 3785,
    # Karton/kemasan besar: standar 1 Karton ≈ 1000 pcs
    "karton"  : 1000,
    "carton"  : 1000,
    "ctn"     : 1000,
    "box"     : 1000,
    "pack"    : 1000,
    "bag"     : 1000,
    "bungkus" : 1000,
    "pcs"     : 1,
    "piece"   : 1,
    "pc"      : 1,
    "unit"    : 1,
    "gram"    : 1,      # sudah base unit
    "g"       : 1,
    "ml"      : 1,      # sudah base unit
    "milliliter": 1,
}

# ------------------------------------------------------------------------------
# KONSTANTA THRESHOLD ANOMALI
# Case Study: selisih > 1.000 unit tidak dapat dijelaskan = Anomaly
# Sumber: Case Study — Expected Output (Action_Status: Anomaly)
# ------------------------------------------------------------------------------
ANOMALY_THRESHOLD_ABSOLUTE = 1000   # unit
ANOMALY_SIGMA              = 3      # sigma untuk 3-sigma rule statistik

print("=" * 70)
print("  KOPIKITA ROASTERY — AUTOMATED DATA PIPELINE v2.0")
print("  Memulai eksekusi pipeline ETL...")
print("=" * 70)


# ==============================================================================
# ██████████████████████████████████████████████████████████████████████████████
#                     CHECKPOINT 1: DATA INGESTION & CLEANING
# ██████████████████████████████████████████████████████████████████████████████
# ==============================================================================
print("\n" + "="*70)
print("  CHECKPOINT 1: DATA INGESTION & CLEANING")
print("="*70)


# ------------------------------------------------------------------------------
# [DATA INGESTION - 1a] Membaca Master Inventory (CSV)
# Tujuan: Mendapatkan daftar Item_ID valid + threshold minimum stok per item
# ------------------------------------------------------------------------------
print("\n[1a] Membaca Master_Inventory.csv...")
try:
    if not os.path.exists(PATH_INVENTORY):
        raise FileNotFoundError(f"File Master_Inventory penting tidak ditemukan di: {PATH_INVENTORY}")
    if os.path.getsize(PATH_INVENTORY) == 0:
        raise ValueError(f"File Master_Inventory kosong (0 bytes): {PATH_INVENTORY}")

    df_inventory = pd.read_csv(PATH_INVENTORY, dtype=str)
    
    # [DATA CLEANING] Standardisasi nama kolom & bersihkan whitespace
    df_inventory = standardize_columns(df_inventory, ALIAS_INVENTORY)
    df_inventory = df_inventory.apply(
        lambda col: col.str.strip() if col.dtype == "object" else col
    )

    # Validasi & fallback kolom wajib
    for col in ["Item_ID", "Min_Stock_Threshold", "Supplier_UoM"]:
        if col not in df_inventory.columns:
            if col == "Item_ID":
                raise KeyError(f"Kolom wajib 'Item_ID' tidak ditemukan di Master_Inventory. Kolom tersedia: {list(df_inventory.columns)}")
            elif col == "Min_Stock_Threshold":
                df_inventory["Min_Stock_Threshold"] = "0"
            elif col == "Supplier_UoM":
                df_inventory["Supplier_UoM"] = "pcs"

    # Standardisasi Item_ID ke uppercase agar lookup konsisten
    df_inventory["Item_ID"] = df_inventory["Item_ID"].str.upper()
    df_inventory["Min_Stock_Threshold"] = pd.to_numeric(
        df_inventory["Min_Stock_Threshold"], errors="coerce"
    ).fillna(0)

    # Hitung threshold dalam base unit gudang untuk perbandingan langsung
    def threshold_to_base(supplier_uom: str, threshold: float) -> float:
        """Konversi threshold dari Supplier UoM ke base unit gudang."""
        uom_str = str(supplier_uom).strip().lower()
        if uom_str.endswith('s') and uom_str not in UOM_TO_BASE:
            uom_str = uom_str[:-1]
        
        factor = UOM_TO_BASE.get(uom_str, 1)
        if uom_str not in UOM_TO_BASE and uom_str != "":
            print(f"    WARNING: UoM tidak dikenal '{supplier_uom}' di Master Inventory. Menggunakan faktor 1.")
        return threshold * factor

    df_inventory["threshold_base"] = df_inventory.apply(
        lambda r: threshold_to_base(r["Supplier_UoM"], r["Min_Stock_Threshold"]),
        axis=1
    )

    # Dict lookup cepat: Item_ID → threshold_base
    inventory_threshold_map = dict(
        zip(df_inventory["Item_ID"], df_inventory["threshold_base"])
    )
    # Set Item_ID valid untuk validasi O(1)
    valid_item_ids = set(df_inventory["Item_ID"])

    print(f"    OK Berhasil memuat {len(df_inventory)} item inventaris.")
    print(f"    OK Threshold dikonfigurasikan: {len(inventory_threshold_map)} item")
except Exception as e:
    print(f"    ERROR membaca Master_Inventory: {e}")
    raise


# ------------------------------------------------------------------------------
# [DATA INGESTION - 1b] Membaca Recipe BOM (JSON)
# Tujuan: Mapping Menu_ID → bahan baku + jumlah yang digunakan per porsi
# Schema: {"menu_items": [{"Menu_ID": ..., "ingredients": [...]}]}
# ------------------------------------------------------------------------------
print("\n[1b] Membaca Recipe_BOM.json...")
try:
    if not os.path.exists(PATH_BOM):
        raise FileNotFoundError(f"File Recipe_BOM penting tidak ditemukan di: {PATH_BOM}")
    if os.path.getsize(PATH_BOM) == 0:
        raise ValueError(f"File Recipe_BOM kosong (0 bytes): {PATH_BOM}")

    with open(PATH_BOM, encoding="utf-8") as f:
        bom_raw = json.load(f)

    # [DATA CLEANING - BOM] Handle berbagai struktur JSON (schema drift resilience)
    if isinstance(bom_raw, dict):
        bom_list = (
            get_case_insensitive_key(bom_raw, ["menu_items", "menus", "items", "recipe_bom", "recipe", "bom"])
            or (list(bom_raw.values())[0] if bom_raw else [])
        )
    else:
        bom_list = bom_raw  # Sudah berupa list langsung

    if not isinstance(bom_list, list):
        # Jika bukan list, jadikan single-item list jika berupa dict
        bom_list = [bom_list] if isinstance(bom_list, dict) else []

    # Bangun dict lookup: MENU-XXX → {name, ingredients}
    bom_dict      = {}
    valid_menu_ids = set()

    for menu in bom_list:
        if not isinstance(menu, dict):
            continue
        menu_id = str(get_case_insensitive_key(menu, ["Menu_ID", "menu id", "menu_item_id", "id_menu", "id"], "")).strip().upper()
        if not menu_id:
            continue
        
        menu_name = str(get_case_insensitive_key(menu, ["Menu_Name", "menu name", "name", "nama_menu", "nama"], ""))
        raw_ingredients = get_case_insensitive_key(menu, ["ingredients", "bahan_baku", "ingredients_list", "recipe"], [])
        
        if not isinstance(raw_ingredients, list):
            raw_ingredients = [raw_ingredients] if isinstance(raw_ingredients, dict) else []

        ingredients_cleaned = []
        for ing in raw_ingredients:
            if not isinstance(ing, dict):
                continue
            item_id = str(get_case_insensitive_key(ing, ["Item_ID", "item id", "id_item", "id_barang", "id"], "")).strip().upper()
            qty_used = get_case_insensitive_key(ing, ["qty_used", "qty", "amount", "jumlah", "takaran", "volume"])
            uom = str(get_case_insensitive_key(ing, ["UoM", "uom", "satuan"], "")).strip().lower()
            
            try:
                qty_used = float(qty_used) if qty_used is not None else 0.0
            except Exception:
                qty_used = 0.0

            ingredients_cleaned.append({
                "Item_ID": item_id,
                "qty_used": qty_used,
                "UoM": uom,
            })

        bom_dict[menu_id] = {
            "Menu_Name"  : menu_name,
            "ingredients": ingredients_cleaned,
        }
        valid_menu_ids.add(menu_id)

    print(f"    OK Berhasil memuat {len(bom_dict)} menu dengan BOM.")
    print(f"    OK Menu IDs: {sorted(valid_menu_ids)[:5]}... (total {len(valid_menu_ids)})")
except Exception as e:
    print(f"    ERROR membaca Recipe_BOM: {e}")
    raise


# ------------------------------------------------------------------------------
# [DATA INGESTION - 1c] Membaca Employee Data (JSON)
# Tujuan: Referensi validasi Employee_ID (opsional, digunakan sebagai konteks)
# ------------------------------------------------------------------------------
print("\n[1c] Membaca Employee.json...")
try:
    if not os.path.exists(PATH_EMPLOYEE) or os.path.getsize(PATH_EMPLOYEE) == 0:
        print(f"    WARNING: File Employee.json tidak ditemukan atau kosong. Dilanjutkan tanpa validasi karyawan.")
        valid_emp_ids = set()
    else:
        with open(PATH_EMPLOYEE, encoding="utf-8") as f:
            emp_raw = json.load(f)
        
        if isinstance(emp_raw, dict):
            employees = get_case_insensitive_key(emp_raw, ["employees", "employee_list", "karyawan", "pegawai"], emp_raw)
            if isinstance(employees, dict):
                employees = list(employees.values())
        else:
            employees = emp_raw if isinstance(emp_raw, list) else []

        valid_emp_ids = set()
        for e in employees:
            if isinstance(e, dict):
                emp_id = str(get_case_insensitive_key(e, ["Employee_ID", "employee id", "id_employee", "nik", "id_karyawan", "id"], "")).strip().upper()
                if emp_id:
                    valid_emp_ids.add(emp_id)
        
        print(f"    OK Berhasil memuat {len(valid_emp_ids)} karyawan.")
except Exception as e:
    print(f"    WARNING membaca Employee.json: {e} (dilanjutkan)")
    valid_emp_ids = set()


# ------------------------------------------------------------------------------
# [DATA INGESTION - 1d] Membaca Warehouse Stock (JSON)
# Tujuan: Data stok fisik harian dari gudang (per item, per tanggal)
# Error Handling: Schema drift, missing field, invalid Item_ID → dikarantina
# ------------------------------------------------------------------------------
print("\n[1d] Membaca warehouse_stock.json...")
warehouse_records = []
wh_invalid_count  = 0

try:
    if not os.path.exists(PATH_WAREHOUSE):
        raise FileNotFoundError(f"File warehouse_stock penting tidak ditemukan di: {PATH_WAREHOUSE}")
    if os.path.getsize(PATH_WAREHOUSE) == 0:
        raise ValueError(f"File warehouse_stock kosong (0 bytes): {PATH_WAREHOUSE}")

    with open(PATH_WAREHOUSE, encoding="utf-8") as f:
        wh_raw = json.load(f)

    if isinstance(wh_raw, dict):
        records = get_case_insensitive_key(wh_raw, ["records", "entries", "stock_records", "data"], wh_raw)
        if isinstance(records, dict):
            records = list(records.values())
    else:
        records = wh_raw if isinstance(wh_raw, list) else []

    if not isinstance(records, list):
        records = [records] if isinstance(records, dict) else []

    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            record_id = str(get_case_insensitive_key(record, ["record_id", "record id", "id_record", "id"], "")).strip()

            # [DATA CLEANING - Gudang] Standardisasi format tanggal
            raw_date = str(get_case_insensitive_key(record, ["date", "tanggal", "datetime", "timestamp"], "")).strip()
            try:
                parsed_date = pd.to_datetime(raw_date, dayfirst=False, errors="raise").strftime("%Y-%m-%d")
            except Exception:
                wh_invalid_count += 1
                continue

            recorded_by = str(get_case_insensitive_key(record, ["recorded_by", "recorded by", "pencatat", "oleh", "employee_id"], "")).strip().upper()

            stock_entries = get_case_insensitive_key(record, ["stock_entries", "stock entries", "entries", "details", "stok", "items"], [])
            if not isinstance(stock_entries, list):
                stock_entries = [stock_entries] if isinstance(stock_entries, dict) else []

            for entry in stock_entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    item_id = str(get_case_insensitive_key(entry, ["Item_ID", "item_id", "item id", "id_item", "id_barang", "id"], "")).strip().upper()

                    # [DATA CLEANING - Gudang] Validasi Item_ID ada di Master Inventory
                    if item_id not in valid_item_ids:
                        wh_invalid_count += 1
                        continue

                    # [DATA CLEANING - Gudang] Tangani SCHEMA DRIFT pada field stok
                    stock_rem = get_case_insensitive_key(
                        entry,
                        ["stock_remaining", "sisa_stok_akhir", "remaining_stock", "stock", "sisa_stok", "sisa stok", "stok_akhir", "stok akhir"]
                    )
                    delivery = get_case_insensitive_key(
                        entry,
                        ["delivery_in", "delivery in", "delivery", "barang_masuk", "barang masuk", "masuk", "supply"]
                    )

                    if stock_rem is None:
                        wh_invalid_count += 1
                        continue

                    stock_rem = float(stock_rem)
                    delivery  = float(delivery or 0)
                    uom       = str(get_case_insensitive_key(entry, ["UoM", "uom", "satuan", "unit"], "")).strip().lower()

                    # Standarisasi UoM untuk stock record jika tidak disingkat
                    if uom.endswith('s') and uom not in UOM_TO_BASE:
                        uom = uom[:-1]

                    warehouse_records.append({
                        "date"           : parsed_date,
                        "record_id"      : record_id,
                        "recorded_by"    : recorded_by,
                        "Item_ID"        : item_id,
                        "stock_remaining": stock_rem,
                        "delivery_in"    : delivery,
                        "UoM"            : uom,
                    })
                except Exception:
                    wh_invalid_count += 1
                    continue
        except Exception:
            wh_invalid_count += 1
            continue

    if len(warehouse_records) == 0:
        df_warehouse = pd.DataFrame(columns=["date", "record_id", "recorded_by", "Item_ID", "stock_remaining", "delivery_in", "UoM"])
    else:
        df_warehouse = pd.DataFrame(warehouse_records)
        df_warehouse = df_warehouse.sort_values(["Item_ID", "date"]).reset_index(drop=True)

    print(f"    OK Berhasil memuat {len(df_warehouse):,} baris data gudang.")
    if not df_warehouse.empty:
        print(f"    OK Periode: {df_warehouse['date'].min()} s/d {df_warehouse['date'].max()}")
    print(f"    OK Baris gudang dikarantina: {wh_invalid_count}")

except Exception as e:
    print(f"    ERROR membaca warehouse_stock: {e}")
    raise


# ------------------------------------------------------------------------------
# [DATA INGESTION - 1e] Membaca Sales History (CSV) — Dataset Terbesar
# ~170.000 baris, mengandung dirty data ekstensif
# Resilient reading: pipeline TIDAK BOLEH crash pada anomali data apapun
# ------------------------------------------------------------------------------
print("\n[1e] Membaca sales_history.csv (~170.000 baris)...")

# Kamus konversi teks angka → numerik (menangani typo quantity)
WORD_TO_NUM = {
    "one": 1, "satu": 1, "uno": 1,
    "two": 2, "dua": 2, "dos": 2,
    "three": 3, "tiga": 3, "tres": 3,
    "four": 4, "empat": 4, "cuatro": 4,
    "five": 5, "lima": 5, "cinco": 5,
    "six": 6, "enam": 6, "seis": 6,
    "seven": 7, "tujuh": 7, "siete": 7,
    "eight": 8, "delapan": 8, "ocho": 8,
    "nine": 9, "sembilan": 9, "nueve": 9,
    "ten": 10, "sepuluh": 10, "diez": 10,
}

sales_clean_dfs   = []
sales_invalid_dfs = []
total_read        = 0

try:
    if not os.path.exists(PATH_SALES):
        raise FileNotFoundError(f"File sales_history penting tidak ditemukan di: {PATH_SALES}")
    if os.path.getsize(PATH_SALES) == 0:
        raise ValueError(f"File sales_history kosong (0 bytes): {PATH_SALES}")

    # Baca CSV dengan chunksize untuk efisiensi memori pada dataset besar
    for chunk in pd.read_csv(
        PATH_SALES,
        dtype=str,
        on_bad_lines="skip",    # Lewati baris CSV yang rusak strukturnya
        low_memory=False,
        chunksize=50_000        # Proses 50.000 baris per iterasi (vectorized)
    ):
        chunk_len = len(chunk)
        total_read += chunk_len
        
        # Standardisasi nama kolom (schema drift resilience)
        chunk = standardize_columns(chunk, ALIAS_SALES)
        
        # Pastikan kolom-kolom standar ada
        for col in ["Transaction_ID", "DateTime", "Employee_ID", "Menu_ID", "Item_Name", "Quantity"]:
            if col not in chunk.columns:
                chunk[col] = ""

        # Pembersihan dasar string kolom
        for col in ["Transaction_ID", "Employee_ID", "Menu_ID", "Item_Name"]:
            chunk[col] = chunk[col].fillna("").str.strip()
        chunk["Menu_ID"] = chunk["Menu_ID"].str.upper()
        chunk["Employee_ID"] = chunk["Employee_ID"].str.upper()

        # Vectorized Date Parsing
        parsed_dates = pd.to_datetime(chunk["DateTime"], errors="coerce", format="mixed")
        chunk["date"] = parsed_dates.dt.strftime("%Y-%m-%d")

        # Vectorized Quantity Parsing
        qty_str = chunk["Quantity"].fillna("").str.strip().str.lower()
        
        # Terjemahkan kata angka secara vectorized
        for word, num in WORD_TO_NUM.items():
            qty_str = qty_str.str.replace(word, str(num), regex=False)
            
        # Ganti koma dengan titik desimal
        qty_str = qty_str.str.replace(",", ".", regex=False)
        
        # Hapus semua non-numerik kecuali digit, titik, dan minus (persis seperti original)
        qty_cleaned = qty_str.str.replace(r"[^0-9.\-]", "", regex=True)
        chunk["Quantity_Cleaned"] = pd.to_numeric(qty_cleaned, errors="coerce")

        # Deteksi baris yang invalid
        is_date_invalid = chunk["date"].isna() | (chunk["date"] == "")
        is_menu_invalid = ~chunk["Menu_ID"].isin(valid_menu_ids) | (chunk["Menu_ID"] == "")
        is_qty_invalid  = chunk["Quantity_Cleaned"].isna() | (chunk["Quantity_Cleaned"] <= 0)

        is_row_invalid = is_date_invalid | is_menu_invalid | is_qty_invalid

        # Bangun alasan invalid secara vectorized
        reasons = pd.Series("", index=chunk.index)
        reasons = np.where(is_date_invalid, reasons + "|date_invalid", reasons)
        reasons = np.where(is_menu_invalid, reasons + "|menu_id_not_in_bom", reasons)
        reasons = np.where(is_qty_invalid,  reasons + "|qty_invalid", reasons)
        reasons = pd.Series(reasons, index=chunk.index).str.lstrip("|")

        # Saring baris valid
        chunk_clean = chunk[~is_row_invalid][["Transaction_ID", "date", "Employee_ID", "Menu_ID", "Item_Name", "Quantity_Cleaned"]].rename(
            columns={"Quantity_Cleaned": "Quantity"}
        )
        
        # Saring baris invalid (karantina)
        chunk_invalid = chunk[is_row_invalid][["Transaction_ID", "date", "Employee_ID", "Menu_ID", "Item_Name", "Quantity"]].rename(
            columns={"Quantity": "Quantity_Raw"}
        )
        chunk_invalid["date"] = chunk_invalid["date"].fillna("UNKNOWN")
        chunk_invalid["Menu_ID"] = np.where(chunk_invalid["Menu_ID"] == "", "MISSING", chunk_invalid["Menu_ID"])
        chunk_invalid["Invalid_Reason"] = reasons[is_row_invalid].values

        sales_clean_dfs.append(chunk_clean)
        sales_invalid_dfs.append(chunk_invalid)

except Exception as e:
    print(f"    ERROR membaca sales_history: {e}")
    raise

# Gabungkan hasil chunks
if sales_clean_dfs:
    df_sales_clean = pd.concat(sales_clean_dfs, ignore_index=True)
else:
    df_sales_clean = pd.DataFrame(columns=["Transaction_ID", "date", "Employee_ID", "Menu_ID", "Item_Name", "Quantity"])

if sales_invalid_dfs:
    df_sales_invalid = pd.concat(sales_invalid_dfs, ignore_index=True)
else:
    df_sales_invalid = pd.DataFrame(columns=["Transaction_ID", "date", "Employee_ID", "Menu_ID", "Item_Name", "Quantity_Raw", "Invalid_Reason"])

# Konversi df_sales_clean kembali ke list of records untuk menjaga kompabilitas dengan Checkpoint 2
sales_clean = df_sales_clean.to_dict("records")
total_valid = len(df_sales_clean)
total_invalid = len(df_sales_invalid)

print(f"    OK Total baris dibaca     : {total_read:>10,}")
print(f"    OK Baris valid (bersih)   : {total_valid:>10,}")
print(f"    OK Baris dikarantina      : {total_invalid:>10,} ({total_invalid/max(total_read, 1)*100:.1f}%)")

min_date = df_sales_clean['date'].min() if not df_sales_clean.empty else "N/A"
max_date = df_sales_clean['date'].max() if not df_sales_clean.empty else "N/A"
print(f"    OK Periode penjualan: {min_date} s/d {max_date}")

print("\n" + "-"*70)
print("  >> CHECKPOINT 1 SELESAI: Data berhasil diingesti dan dibersihkan")
print("-"*70)


# ==============================================================================
# ██████████████████████████████████████████████████████████████████████████████
#       CHECKPOINT 2: BOM CALCULATION & STOCK RECONCILIATION
# ██████████████████████████████████████████████████████████████████████████████
# ==============================================================================
print("\n" + "="*70)
print("  CHECKPOINT 2: BOM CALCULATION & STOCK RECONCILIATION")
print("="*70)


# ------------------------------------------------------------------------------
# [CALCULATION - 2a] BOM Unpacking: Konversi POS → Pemakaian Bahan Baku
# Formula utama: Pemakaian_Teoritis = Jumlah_Terjual × qty_used_per_porsi
# Sumber: Dokumen Rancangan Teknis — Bagian 3 (BOM Unpacking)
#
# Contoh:
#   1 Iced Latte → 18g kopi + 150ml susu + ...
#   Jual 10 Iced Latte → 180g kopi + 1500ml susu (pemakaian teoritis)
# ------------------------------------------------------------------------------
print("\n[2a] Menghitung pemakaian teoritis bahan baku (BOM Unpacking)...")

bom_usage_records = []

for row in sales_clean:
    menu_id   = row["Menu_ID"]
    qty_sold  = row["Quantity"]
    sale_date = row["date"]

    if menu_id not in bom_dict:
        continue

    for ingredient in bom_dict[menu_id]["ingredients"]:
        item_id       = str(ingredient.get("Item_ID", "")).strip().upper()
        qty_per_serve = float(ingredient.get("qty_used", 0) or 0)
        uom           = str(ingredient.get("UoM", "")).strip().lower()

        # Validasi item_id ada di master inventory
        if item_id not in valid_item_ids or qty_per_serve <= 0:
            continue

        # Pemakaian teoritis = porsi terjual × bahan per porsi
        theoretical_usage = qty_sold * qty_per_serve

        bom_usage_records.append({
            "date"              : sale_date,
            "Item_ID"           : item_id,
            "UoM"               : uom,
            "theoretical_usage" : theoretical_usage,
        })

df_bom_usage = pd.DataFrame(bom_usage_records)

# Agregasi: total pemakaian teoritis per hari per Item_ID
df_daily_usage = (
    df_bom_usage
    .groupby(["date", "Item_ID"], as_index=False)["theoretical_usage"]
    .sum()
    .rename(columns={"theoretical_usage": "theoretical_usage"})
)

print(f"    OK Total baris pemakaian teoritis : {len(df_daily_usage):,}")
print(f"    OK Item yang terlibat dalam BOM   : {df_daily_usage['Item_ID'].nunique()}")

top_usage = (
    df_daily_usage.groupby("Item_ID")["theoretical_usage"]
    .sum().sort_values(ascending=False).head(5)
)
print(f"    OK Top 5 bahan baku (total pemakaian teoritis):")
for item, usage in top_usage.items():
    item_name = df_inventory.loc[df_inventory["Item_ID"] == item, "Item_Name"].values
    name = item_name[0] if len(item_name) > 0 else "?"
    print(f"       - {item} ({name}): {usage:,.0f} unit")


# ------------------------------------------------------------------------------
# [CALCULATION - 2b] Stock Reconciliation
# Menghitung penurunan stok gudang aktual vs pemakaian teoritis POS
#
# Formula:
#   stock_decreased(d) = stock_remaining(d-1) + delivery_in(d) - stock_remaining(d)
#   delta(d)           = stock_decreased(d) - theoretical_usage(d)
#
# Interpretasi delta:
#   delta > 0  → Gudang berkurang lebih banyak dari teori → indikasi kehilangan/theft
#   delta < 0  → Gudang berkurang lebih sedikit dari teori → mismatch BOM / over-reporting
#   delta ≈ 0  → Normal (operasional wajar)
#
# CATATAN PENTING: Hari pertama per item diabaikan dari deteksi anomali
# karena tidak ada data stok hari sebelumnya (prev_stock = NaN → tidak bisa
# menghitung penurunan yang valid).
# Sumber: Dokumen Rancangan Teknis — Bagian 4 (Anomaly Detection)
# ------------------------------------------------------------------------------
print("\n[2b] Rekonsiliasi stok gudang aktual vs pemakaian teoritis POS...")

df_wh = df_warehouse.copy().sort_values(["Item_ID", "date"])

# Shift stok untuk mendapatkan stok hari sebelumnya per item
df_wh["prev_stock"]     = df_wh.groupby("Item_ID")["stock_remaining"].shift(1)
# Flag hari pertama per item (tidak bisa dihitung delta yang valid)
df_wh["is_first_day"]   = df_wh["prev_stock"].isna()

# Hitung penurunan stok aktual (hanya untuk baris yang punya prev_stock)
df_wh["stock_decreased"] = (
    df_wh["prev_stock"] + df_wh["delivery_in"] - df_wh["stock_remaining"]
)
# Hari pertama: stock_decreased = NaN (tidak digunakan dalam anomali)
# (tidak di-fillna agar terdeteksi sebagai hari pertama)

# Gabungkan dengan pemakaian teoritis
df_reconciliation = df_wh.merge(
    df_daily_usage[["date", "Item_ID", "theoretical_usage"]],
    on=["date", "Item_ID"],
    how="left"
)
# Hari tanpa transaksi → theoretical_usage = 0
df_reconciliation["theoretical_usage"] = df_reconciliation["theoretical_usage"].fillna(0)

# Hitung delta (hanya untuk hari yang bukan hari pertama)
df_reconciliation["delta"] = (
    df_reconciliation["stock_decreased"] - df_reconciliation["theoretical_usage"]
)
# Hari pertama → delta = NaN (tidak di-flag sebagai anomali)

# Statistik rekonsiliasi (exclude hari pertama)
df_recon_valid = df_reconciliation[~df_reconciliation["is_first_day"]]
print(f"    OK Rekonsiliasi selesai    : {len(df_reconciliation):,} total baris")
print(f"    OK Baris valid (bukan hari-1): {len(df_recon_valid):,} baris")
print(f"    OK Rata-rata delta         : {df_recon_valid['delta'].mean():.2f} unit")
print(f"    OK Delta max (surplus loss): {df_recon_valid['delta'].max():.2f} unit")
print(f"    OK Delta min (deficit)     : {df_recon_valid['delta'].min():.2f} unit")

print("\n" + "-"*70)
print("  >> CHECKPOINT 2 SELESAI: BOM Calculation & Rekonsiliasi berhasil")
print("-"*70)


# ==============================================================================
# ██████████████████████████████████████████████████████████████████████████████
#       CHECKPOINT 3: ANOMALY DETECTION & OUTPUT ACTION_REPORT.CSV
# ██████████████████████████████████████████████████████████████████████████████
# ==============================================================================
print("\n" + "="*70)
print("  CHECKPOINT 3: ANOMALY DETECTION & GENERATE ACTION_REPORT.CSV")
print("="*70)


# ------------------------------------------------------------------------------
# [ANOMALY LOGIC - 3a] Hitung Threshold Statistik per Item (3-Sigma Rule)
#
# Pendekatan probabilistik:
#   - Gunakan HANYA data hari non-pertama untuk menghitung baseline statistik
#   - Threshold_upper = μ + 3σ  → delta positif ekstrem (kehilangan tak wajar)
#   - Threshold_lower = μ - 3σ  → delta negatif ekstrem (mismatch BOM ekstrem)
#
# Justifikasi 3-Sigma: Dalam distribusi normal, 99.73% data berada dalam
# μ ± 3σ. Nilai di luar batas ini (p < 0.27%) dianggap anomali statistik.
#
# Sumber: Case Study — Expected Capabilities (Statistical Anomaly Detection)
# ------------------------------------------------------------------------------
print("\n[3a] Menghitung threshold anomali statistik per item (3-sigma rule)...")

df_stats = (
    df_recon_valid
    .groupby("Item_ID")["delta"]
    .agg(delta_mean="mean", delta_std="std", delta_count="count")
    .reset_index()
)
# Proteksi: Jika data historis < 3, gunakan standard deviasi default yang besar (500) untuk mencegah false positive.
# Dan berikan batas minimum standar deviasi (floor) sebesar 10.0 unit untuk item dengan variansi nol/sangat kecil.
df_stats["delta_std"] = np.where(
    df_stats["delta_count"] < 3,
    500.0,
    np.maximum(df_stats["delta_std"].fillna(0), 10.0)
)
df_stats["threshold_upper"]    = df_stats["delta_mean"] + ANOMALY_SIGMA * df_stats["delta_std"]
df_stats["threshold_lower"]    = df_stats["delta_mean"] - ANOMALY_SIGMA * df_stats["delta_std"]

# Merge threshold ke df_reconciliation
df_reconciliation = df_reconciliation.merge(
    df_stats[["Item_ID", "delta_mean", "delta_std", "threshold_upper", "threshold_lower"]],
    on="Item_ID",
    how="left"
)

print(f"    OK Threshold statistik dihitung untuk {len(df_stats)} item (dengan std-dev floor & count safeguard)")


# ------------------------------------------------------------------------------
# [ANOMALY LOGIC - 3b] Klasifikasi Anomali per Baris
#
# Aturan anomali (HARUS memenuhi minimal 1 kriteria):
#
#   1. DELTA POSITIF > 1000 unit (UTAMA — dari Case Study)
#      Gudang berkurang lebih banyak dari teori → kemungkinan pencurian/kehilangan
#
#   2. DELTA POSITIF > threshold_upper (statistik, 3-sigma)
#      Kehilangan yang jauh di atas pola historis normal item tersebut
#
#   3. DELTA NEGATIF < threshold_lower (statistik, ekstrem)
#      Mismatch BOM yang sangat besar → kemungkinan fraud input/salah catat besar
#
# PENGECUALIAN: Hari pertama per item (is_first_day=True) TIDAK di-flag anomali
# karena tidak ada baseline stok yang valid untuk menghitung penurunan.
# ------------------------------------------------------------------------------
print("\n[3b] Mendeteksi anomali inventaris (fully vectorized)...")

# [ANOMALY LOGIC] — 100% Vectorized (tidak ada apply/iterrows)
# Hari pertama selalu dikecualikan (is_first_day=True → tidak punya prev_stock)
_delta      = df_reconciliation["delta"]
_th_upper   = df_reconciliation["threshold_upper"]
_th_lower   = df_reconciliation["threshold_lower"]
_not_first  = ~df_reconciliation["is_first_day"] & _delta.notna()

# Kriteria 1: Delta absolut > 1000 unit (case study requirement)
_anom_abs   = _not_first & (_delta > ANOMALY_THRESHOLD_ABSOLUTE)

# Kriteria 2: Delta statistik atas > threshold_upper (3-sigma)
_anom_stat_up = _not_first & _th_upper.notna() & (_delta > _th_upper)

# Kriteria 3: Delta statistik bawah < threshold_lower (mismatch BOM ekstrem)
_anom_stat_dn = _not_first & _th_lower.notna() & (_delta < _th_lower)

df_reconciliation["is_anomaly"] = _anom_abs | _anom_stat_up | _anom_stat_dn

anomaly_count = int(df_reconciliation["is_anomaly"].sum())
print(f"    OK Anomali terdeteksi: {anomaly_count:,} baris")
print(f"    OK Dari {len(df_recon_valid):,} baris valid ({anomaly_count/max(len(df_recon_valid),1)*100:.1f}%)")


# ------------------------------------------------------------------------------
# [ANOMALY LOGIC - 3c] Identifikasi Status Restock Per Hari
#
# Kondisi Restock: stock_remaining(d) < threshold_base(item)
# Threshold sudah dikonversi ke base unit saat load Master Inventory (langkah 1a)
#
# Catatan: Restock dicek PER HARI, bukan hanya hari terakhir, sehingga laporan
# mencerminkan kapan tepatnya stok turun di bawah batas minimum.
# Sumber: Case Study — Action_Status: "Restock" (stok < batas minimum)
# ------------------------------------------------------------------------------
print("\n[3c] Mengidentifikasi status restock per hari per item...")

# Tambahkan kolom threshold_base ke df_reconciliation
df_reconciliation["threshold_base"] = df_reconciliation["Item_ID"].map(
    inventory_threshold_map
).fillna(20000)  # Default 20.000 jika tidak ditemukan di master

# Flag restock: stok fisik hari ini di bawah threshold minimum
df_reconciliation["needs_restock"] = (
    df_reconciliation["stock_remaining"] < df_reconciliation["threshold_base"]
)

restock_flag_count = df_reconciliation["needs_restock"].sum()
restock_items_unique = df_reconciliation.loc[
    df_reconciliation["needs_restock"], "Item_ID"
].nunique()

print(f"    OK Total baris restock: {restock_flag_count:,} baris")
print(f"    OK Item unik yang pernah restock: {restock_items_unique}")


# ------------------------------------------------------------------------------
# [CALCULATION - 3d] Membangun Action Report
#
# Aturan prioritas klasifikasi (jika lebih dari 1 kondisi terpenuhi):
#   1. Invalid Data  → prioritas tertinggi (data tidak bisa dipercaya)
#   2. Anomaly       → indikasi pencurian/kehilangan serius
#   3. Restock       → stok di bawah minimum
#   4. Safe          → semua kondisi aman
#
# Format output wajib:
#   Date | Item_ID | Action_Status | (kolom opsional tambahan)
# Sumber: Case Study — Expected Output & Rancangan Teknis — Bagian 5A
# ------------------------------------------------------------------------------
print("\n[3d] Membangun Action_Report (fully vectorized)...")

# ==============================================================================
# [ACTION REPORT] FULLY VECTORIZED — No iterrows / No apply
# Menggunakan np.select untuk klasifikasi status multi-kondisi secara paralel
# Menggunakan vectorized string formatting untuk kolom Notes
# ==============================================================================

# --- BAGIAN 1: Data VALID dari rekonsiliasi gudang × POS ---
df_r = df_reconciliation.copy()

# Pastikan tipe data aman untuk operasi string
_delta_r    = df_r["delta"].round(2)
_stock_r    = df_r["stock_remaining"].round(2)
_th_base_r  = df_r["threshold_base"].round(0)
_th_usage_r = df_r["theoretical_usage"].fillna(0).round(2)
_stock_dec_r = df_r["stock_decreased"].round(2)

# Vectorized Action_Status dengan np.select (prioritas: Anomaly > Restock > Safe)
_conditions_status = [
    df_r["is_anomaly"],
    df_r["needs_restock"],
]
_choices_status = ["Anomaly", "Restock"]
df_r["Action_Status"] = np.select(_conditions_status, _choices_status, default="Safe")

# Vectorized Notes untuk tiap kategori
# Notes Anomaly: bedakan antara anomali absolut dan statistik
_notes_anom_abs  = "KEHILANGAN: Delta=+" + _delta_r.astype(str) + " unit > threshold " + str(ANOMALY_THRESHOLD_ABSOLUTE)
_notes_anom_stat = "ANOMALI STATISTIK: Delta=" + _delta_r.astype(str) + " (>3-sigma dari baseline item)"
_notes_anomaly   = np.where(
    _delta_r > ANOMALY_THRESHOLD_ABSOLUTE,
    _notes_anom_abs,
    _notes_anom_stat
)

# Notes Restock
_notes_restock = "Stok=" + _stock_r.astype(str) + " < MinThreshold=" + _th_base_r.astype(str)

# Notes Safe: bedakan hari pertama vs hari biasa
_notes_safe_first  = "Hari pertama rekaman (baseline stok)"
_notes_safe_normal = "Stok=" + _stock_r.astype(str) + ", Delta=" + _delta_r.fillna(0).astype(str)
_notes_safe = np.where(df_r["is_first_day"], _notes_safe_first, _notes_safe_normal)

# Pilih Notes sesuai status
df_r["Notes"] = np.select(
    [df_r["is_anomaly"], df_r["needs_restock"]],
    [_notes_anomaly,     _notes_restock],
    default=_notes_safe
)

# Bangun DataFrame laporan dari rekonsiliasi (tanpa loop)
df_valid_report = pd.DataFrame({
    "Date"              : df_r["date"].astype(str),
    "Item_ID"           : df_r["Item_ID"],
    "Action_Status"     : df_r["Action_Status"],
    "Stock_Remaining"   : _stock_r,
    "Theoretical_Usage" : _th_usage_r,
    "Stock_Decreased"   : _stock_dec_r,
    "Delta"             : _delta_r,
    "Notes"             : df_r["Notes"],
})

# --- BAGIAN 2: Data INVALID dari karantina sales (Menu_ID tidak dikenal) ---
# Transaksi dengan Menu_ID yang tidak ada di BOM/Master → "Invalid Data"
# Vectorized filter: hanya baris dengan reason mengandung 'menu_id_not_in_bom'
if not df_sales_invalid.empty:
    _inv_mask = df_sales_invalid["Invalid_Reason"].astype(str).str.contains(
        "menu_id_not_in_bom", na=False, regex=False
    )
    df_inv_filtered = df_sales_invalid[_inv_mask].copy()

    if not df_inv_filtered.empty:
        df_invalid_report = pd.DataFrame({
            "Date"              : df_inv_filtered["date"].fillna("UNKNOWN").astype(str),
            "Item_ID"           : df_inv_filtered["Menu_ID"].fillna("MISSING").astype(str).str.strip(),
            "Action_Status"     : "Invalid Data",
            "Stock_Remaining"   : None,
            "Theoretical_Usage" : None,
            "Stock_Decreased"   : None,
            "Delta"             : None,
            "Notes"             : "Menu_ID tidak ditemukan di katalog | TRX: " + df_inv_filtered["Transaction_ID"].fillna("?").astype(str),
        })
    else:
        df_invalid_report = pd.DataFrame(columns=df_valid_report.columns)
else:
    df_invalid_report = pd.DataFrame(columns=df_valid_report.columns)

# Gabungkan laporan valid + invalid
df_action_report = pd.concat([df_valid_report, df_invalid_report], ignore_index=True)

# Deduplikasi: ambil status paling kritis per (Date, Item_ID)
STATUS_PRIORITY = {"Invalid Data": 0, "Anomaly": 1, "Restock": 2, "Safe": 3}
df_action_report["_priority"] = df_action_report["Action_Status"].map(
    STATUS_PRIORITY
).fillna(99).astype(int)

df_action_report = (
    df_action_report
    .sort_values(["Date", "Item_ID", "_priority"])
    .drop_duplicates(subset=["Date", "Item_ID"], keep="first")
    .drop(columns=["_priority"])
    .sort_values(["Date", "Item_ID"])
    .reset_index(drop=True)
)

print(f"    OK Total baris Action_Report: {len(df_action_report):,}")
print(f"\n    Distribusi Action_Status:")
status_counts = df_action_report["Action_Status"].value_counts()
for status, count in status_counts.items():
    pct  = count / len(df_action_report) * 100
    bar  = "#" * int(pct / 2)
    print(f"       {status:15s}: {count:>5,} baris ({pct:5.1f}%) {bar}")


# ------------------------------------------------------------------------------
# [OUTPUT] Simpan Action_Report.csv
# Kolom wajib: Date, Item_ID, Action_Status (3 kolom)
# Kolom opsional: Stock_Remaining, Theoretical_Usage, Stock_Decreased, Delta, Notes
# Sumber: Case Study — Expected Output & Rancangan Teknis — Bagian 5A
# ------------------------------------------------------------------------------
print(f"\n[3e] Menyimpan Action_Report.csv...")

# Urutan kolom: 3 wajib di depan, diikuti kolom opsional
cols_required = ["Date", "Item_ID", "Action_Status"]
cols_optional = [c for c in df_action_report.columns if c not in cols_required]
df_action_report = df_action_report[cols_required + cols_optional]

df_action_report.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
print(f"    OK Tersimpan di: {OUTPUT_PATH}")

# Preview 15 baris representatif (5 per status)
print(f"\n    Preview Action_Report.csv (sampel per status):")
preview_rows = []
for s in ["Safe", "Restock", "Anomaly", "Invalid Data"]:
    sample = df_action_report[df_action_report["Action_Status"] == s].head(3)
    preview_rows.append(sample)
preview_df = pd.concat(preview_rows, ignore_index=True)
pd.set_option("display.max_columns", 5)
pd.set_option("display.width", 120)
print(preview_df[["Date", "Item_ID", "Action_Status", "Delta", "Notes"]].to_string(index=False))


# ==============================================================================
# RINGKASAN AKHIR EKSEKUSI PIPELINE
# ==============================================================================
print("\n" + "="*70)
print("  RINGKASAN EKSEKUSI PIPELINE KOPIKITA ROASTERY")
print("="*70)
print(f"  [DATA INGESTION]")
print(f"     Sales History     : {total_read:>10,} baris dibaca")
print(f"     Sales Valid       : {total_valid:>10,} baris ({total_valid/total_read*100:.1f}%)")
print(f"     Sales Dikarantina : {total_invalid:>10,} baris ({total_invalid/total_read*100:.1f}%)")
print(f"     Warehouse Records : {len(df_warehouse):>10,} baris")
print(f"     Master Inventory  : {len(df_inventory):>10,} item")
print(f"     Menu BOM          : {len(bom_dict):>10,} menu")

print(f"\n  [BOM CALCULATION]")
print(f"     Pemakaian teoritis: {len(df_daily_usage):>10,} item-hari dihitung")
print(f"     Rekonsiliasi total: {len(df_reconciliation):>10,} baris")
print(f"     Rekonsiliasi valid: {len(df_recon_valid):>10,} baris (exclude hari-1)")

print(f"\n  [ANOMALY DETECTION]")
print(f"     Anomali terdeteksi: {anomaly_count:>10,} baris")
print(f"     Baris restock flag: {restock_flag_count:>10,} baris")
print(f"     Item unik restock : {restock_items_unique:>10,} item")

print(f"\n  [OUTPUT]")
print(f"     Action_Report.csv : {len(df_action_report):>10,} baris")
for status, count in status_counts.items():
    pct = count / len(df_action_report) * 100
    print(f"       [{status}] {count:,} ({pct:.1f}%)")

print(f"\n  Pipeline selesai: ZERO HUMAN INTERVENTION")
print(f"  File output: {OUTPUT_PATH}")
print("="*70)

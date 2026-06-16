# ============================================================
# pipeline.py — Main ETL Pipeline
# Kopikita Roastery — Data Automation
# ============================================================
#
# Alur eksekusi (6 stage, zero human intervention):
#
#  [DATA INGESTION]  Stage 1 │ Load semua file raw dengan error handling
#  [DATA CLEANSING]  Stage 2 │ Bersihkan noise, quarantine + BUANG baris rusak
#  [CALCULATION]     Stage 3 │ BOM expansion + daily aggregasi konsumsi
#  [CALCULATION]     Stage 4 │ Rekonsiliasi stok POS vs fisik gudang
#  [ANOMALY LOGIC]   Stage 5 │ Klasifikasi Action_Status (Invalid/Anomaly/Restock/Safe)
#                    Stage 6 │ Output Action_Report.csv + quarantine_log.csv
#
# Cara jalankan: python pipeline.py
#
# FIXES yang diterapkan vs versi awal:
#   FIX-1: Error flag rows sekarang di-EXCLUDE dari BOM expansion (tidak hanya dicopy)
#   FIX-2: Tambah kolom Variance_Direction (POS_Overcount/Shrinkage) di output
#   FIX-3: Comment marker eksplisit [DATA INGESTION/CLEANSING/CALCULATION/ANOMALY LOGIC]
#   FIX-4: Justifikasi matematis threshold anomali (IQR-based, threshold 1000 > Q3+1.5IQR=721)
#   FIX-5: Anotasi no-BOM items di Action_Report (kolom Item_Note)
# ============================================================

import os
import sys
import json
import time
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

from utils import (
    # Paths
    PATH_SALES, PATH_WAREHOUSE, PATH_INVENTORY, PATH_BOM, PATH_EMPLOYEE,
    PATH_OUTPUT_REPORT, PATH_OUTPUT_QUARANTINE,
    # Constants
    ANOMALY_THRESHOLD, FALLBACK_RESTOCK_THRESHOLD, NO_BOM_ITEMS, UNIT_COST_IDR,
    # Reason codes
    REASON_NULL_FIELD, REASON_BAD_DATE, REASON_NEG_QTY,
    REASON_BAD_QTY, REASON_ZERO_QTY, REASON_GHOST_MENU, REASON_ERROR_FLAG, REASON_DUPLICATE,
    # Functions
    setup_logging, parse_datetime, parse_datetime_series, parse_quantity,
    is_error_flag, flatten_warehouse_records,
    build_threshold_dict, build_bom_df, build_valid_employee_set,
)

log = setup_logging()


# ============================================================
# [DATA INGESTION] STAGE 1 — Load semua file source
# ============================================================
# Setiap file di-load dalam blok try-except sendiri.
# File kritis (sales, warehouse, inventory, BOM) → sys.exit jika gagal.
# File non-kritis (employee) → warning saja, pipeline tetap jalan.
# ============================================================
def stage1_ingest():
    log.info("=" * 62)
    log.info("STAGE 1  [DATA INGESTION] — Memuat semua file source")
    log.info("=" * 62)

    # ── Sales History (CSV) ──────────────────────────────────
    # Dibaca sebagai string semua kolom: mencegah konversi otomatis
    # yang bisa merusak Quantity dan DateTime sebelum cleansing.
    try:
        sales_raw = pd.read_csv(PATH_SALES, dtype=str, keep_default_na=False)
        sales_raw.replace(
            ['nan', 'NaN', 'NULL', 'None', 'none', '', 'null'],
            np.nan, inplace=True
        )
        log.info(f"[✓] sales_history.csv     → {len(sales_raw):>7,} baris | {sales_raw.shape[1]} kolom")
    except FileNotFoundError:
        log.error(f"[✗] File tidak ditemukan: {PATH_SALES}")
        sys.exit(1)
    except Exception as e:
        log.error(f"[✗] Gagal load sales_history: {e}")
        sys.exit(1)

    # ── Warehouse Stock (JSON) ───────────────────────────────
    # Nested JSON dengan schema drift per 2025-04-01.
    # Normalisasi 'sisa_stok_akhir' → 'stock_remaining' dilakukan di Stage 2.
    try:
        with open(PATH_WAREHOUSE, 'r', encoding='utf-8') as f:
            warehouse_raw = json.load(f)
        n = len(warehouse_raw.get('records', []))
        log.info(f"[✓] warehouse_stock.json  → {n:>7,} daily records")
    except FileNotFoundError:
        log.error(f"[✗] File tidak ditemukan: {PATH_WAREHOUSE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log.error(f"[✗] JSON invalid di warehouse_stock: {e}")
        sys.exit(1)

    # ── Master Inventory (CSV) ───────────────────────────────
    # Katalog 42 item. Sumber kebenaran untuk Item_ID dan Min_Stock_Threshold.
    try:
        inventory_df = pd.read_csv(PATH_INVENTORY, dtype=str)
        inventory_df.replace(['nan','NaN','NULL',''], np.nan, inplace=True)
        inventory_df.dropna(subset=['Item_ID'], inplace=True)
        inventory_df['Item_ID']   = inventory_df['Item_ID'].str.strip()
        inventory_df['Item_Name'] = inventory_df['Item_Name'].str.strip()
        inventory_df['Min_Stock_Threshold'] = pd.to_numeric(
            inventory_df['Min_Stock_Threshold'], errors='coerce'
        ).fillna(0)
        log.info(f"[✓] Master_Inventory.csv  → {len(inventory_df):>7,} items")
    except Exception as e:
        log.error(f"[✗] Gagal load Master_Inventory: {e}")
        sys.exit(1)

    # ── Recipe BOM (JSON) ────────────────────────────────────
    # 25 menu item dengan daftar ingredient masing-masing.
    # Dipakai di Stage 3 untuk BOM expansion.
    try:
        with open(PATH_BOM, 'r', encoding='utf-8') as f:
            bom_data = json.load(f)
        log.info(f"[✓] Recipe_BOM.json       → {len(bom_data.get('menu_items',[])):>7,} menu items")
    except Exception as e:
        log.error(f"[✗] Gagal load Recipe_BOM: {e}")
        sys.exit(1)

    # ── Employee (JSON) ──────────────────────────────────────
    # Non-kritis: hanya untuk validasi Employee_ID (warning only).
    try:
        with open(PATH_EMPLOYEE, 'r', encoding='utf-8') as f:
            employee_data = json.load(f)
        log.info(f"[✓] Employee.json         → {len(employee_data.get('employees',[])):>7,} karyawan")
    except Exception as e:
        log.warning(f"[⚠] Gagal load Employee (non-kritis): {e}")
        employee_data = {'employees': []}

    log.info("")
    return sales_raw, warehouse_raw, inventory_df, bom_data, employee_data


# ============================================================
# [DATA CLEANSING] STAGE 2a — Bersihkan sales_history
# ============================================================
# URUTAN KRITIS pembersihan (tiap langkah mempengaruhi langkah berikutnya):
#   1. Deduplikasi Transaction_ID
#   2. Flag & BUANG error flag rows (FIX-1: sekarang di-exclude, bukan hanya dicopy)
#   3. Buang baris null di field kritis
#   4. Parse & normalisasi DateTime (vectorized multi-format)
#   5. Parse & rescue Quantity (3-layer)
#   6. Tandai ghost Menu_ID → akan jadi Invalid Data di Stage 5
#   7. Flag ghost Employee_ID (warning only, transaksi tetap diproses)
# ============================================================
def stage2_cleanse_sales(sales_raw, valid_menu_ids, valid_emp_ids):
    log.info("=" * 62)
    log.info("STAGE 2  [DATA CLEANSING] — Membersihkan sales_history")
    log.info("=" * 62)

    df = sales_raw.copy()
    quarantine_rows = []
    total_raw = len(df)
    log.info(f"  Total baris raw: {total_raw:,}")

    # ── 2.1 DEDUPLIKASI Transaction_ID ───────────────────────
    # [DATA CLEANSING] Simpan first occurrence, buang duplikat ke quarantine.
    dup_mask = df.duplicated(subset=['Transaction_ID'], keep='first')
    dups = df[dup_mask].copy()
    if len(dups):
        dups['Quarantine_Reason'] = REASON_DUPLICATE
        quarantine_rows.append(dups)
        df = df[~dup_mask].copy()
        log.info(f"  → Duplikat Transaction_ID    : {len(dups):,} baris dikarantina")

    # ── 2.2 ERROR FLAG ROWS → QUARANTINE + EXCLUDE (FIX-1) ──
    # [DATA CLEANSING] PERBAIKAN: baris dengan error POS flag DIBUANG dari pipeline,
    # bukan hanya dicopy ke quarantine. Error flag (EROR, #REF!, dll.) menandakan
    # transaksi tidak valid dari sistem POS → tidak boleh masuk BOM expansion.
    # Sebelumnya: hanya dicopy → inflate POS_Consumed +2.3% → false Anomaly.
    error_mask = df['Additional_Info'].apply(is_error_flag)
    err_rows = df[error_mask].copy()
    if len(err_rows):
        err_rows['Quarantine_Reason'] = REASON_ERROR_FLAG
        quarantine_rows.append(err_rows)
        df = df[~error_mask].copy()   # ← FIX-1: exclude dari processing
        log.info(f"  → Error flag POS (di-exclude) : {len(err_rows):,} baris dikarantina")

    # ── 2.3 NULL CRITICAL FIELDS ─────────────────────────────
    # [DATA CLEANSING] Tanpa DateTime/Menu_ID/Quantity → tidak bisa diproses.
    null_mask = df['DateTime'].isna() | df['Menu_ID'].isna() | df['Quantity'].isna()
    null_rows = df[null_mask].copy()
    if len(null_rows):
        null_rows['Quarantine_Reason'] = REASON_NULL_FIELD
        quarantine_rows.append(null_rows)
        df = df[~null_mask].copy()
        log.info(f"  → Null field kritis          : {len(null_rows):,} baris dikarantina")

    # ── 2.4 PARSE DATETIME (vectorized) ──────────────────────
    # [DATA CLEANSING] Daisy-chain 5 pass vectorized → row-by-row hanya untuk sisa exotics.
    # Kompatibel pandas 2.x dan 3.x (tidak pakai infer_datetime_format yang dihapus di 3.0).
    log.info("  → Parsing DateTime (vectorized multi-format)...")
    df['DateTime_Parsed'] = parse_datetime_series(df['DateTime'])

    bad_date_mask = df['DateTime_Parsed'].isna()
    bad_date_rows = df[bad_date_mask].copy()
    if len(bad_date_rows):
        bad_date_rows['Quarantine_Reason'] = REASON_BAD_DATE
        quarantine_rows.append(bad_date_rows)
        df = df[~bad_date_mask].copy()
        log.info(f"  → DateTime tidak valid        : {len(bad_date_rows):,} baris dikarantina")

    df['Date'] = df['DateTime_Parsed'].dt.date

    # ── 2.5 PARSE & RESCUE QUANTITY ──────────────────────────
    # [DATA CLEANSING] 3-layer rescue: cast langsung → word-map dict → regex.
    # Nilai negatif (system error POS) dipisah dari unparseable.
    log.info("  → Parsing & rescuing Quantity (3-layer)...")
    df['Quantity_Clean'] = df['Quantity'].apply(parse_quantity)

    def _is_negative(x):
        if pd.isna(x):
            return False
        try:
            return float(str(x).strip().replace(',', '.')) < 0
        except Exception:
            return False

    neg_mask     = df['Quantity'].apply(_is_negative)
    bad_qty_mask = df['Quantity_Clean'].isna() & ~neg_mask

    neg_rows = df[neg_mask].copy()
    if len(neg_rows):
        neg_rows['Quarantine_Reason'] = REASON_NEG_QTY
        quarantine_rows.append(neg_rows)
        log.info(f"  → Quantity negatif            : {len(neg_rows):,} baris dikarantina")

    bad_qty_rows = df[bad_qty_mask].copy()
    if len(bad_qty_rows):
        bad_qty_rows['Quarantine_Reason'] = REASON_BAD_QTY
        quarantine_rows.append(bad_qty_rows)
        log.info(f"  → Quantity tidak terparsing   : {len(bad_qty_rows):,} baris dikarantina")

    # [FIX-BUG3] Deteksi zero-quantity (Qty=0) sebelum filter.
    # Sebelumnya 686 baris ini di-drop oleh '> 0' tanpa masuk quarantine (silent leak).
    # Baris Qty=0 adalah transaksi void/cancelled di POS — harus tercatat, bukan diam-diam hilang.
    zero_qty_mask = (df['Quantity_Clean'] == 0) & df['Quantity_Clean'].notna() & ~neg_mask & ~bad_qty_mask
    zero_qty_rows = df[zero_qty_mask].copy()
    if len(zero_qty_rows):
        zero_qty_rows['Quarantine_Reason'] = REASON_ZERO_QTY
        quarantine_rows.append(zero_qty_rows)
        log.info(f"  → Quantity zero (void/cancelled): {len(zero_qty_rows):,} baris dikarantina")

    df = df[df['Quantity_Clean'].notna() & (df['Quantity_Clean'] > 0)].copy()

    # ── 2.6 GHOST MENU_ID CHECK ──────────────────────────────
    # [DATA CLEANSING] Menu_ID tidak ada di BOM → transaksi Invalid Data.
    # Diberi flag is_ghost_menu=True, dikumpulkan di Stage 5 sebagai Invalid Data output.
    df['Menu_ID'] = df['Menu_ID'].str.strip()
    df['is_ghost_menu'] = ~df['Menu_ID'].isin(valid_menu_ids)
    ghost_count = df['is_ghost_menu'].sum()
    if ghost_count:
        log.info(f"  → Ghost Menu_ID (Invalid Data): {ghost_count:,} transaksi ditandai")

    # ── 2.7 GHOST EMPLOYEE_ID — WARNING ONLY ─────────────────
    # [DATA CLEANSING] Ghost Employee_ID tidak membatalkan transaksi.
    # Transaksi tetap diproses tapi owner perlu investigasi.
    if valid_emp_ids:
        df['Employee_ID'] = df['Employee_ID'].fillna('UNKNOWN').str.strip()
        ghost_emp = (~df['Employee_ID'].isin(valid_emp_ids)).sum()
        if ghost_emp:
            log.warning(f"  [⚠] Ghost Employee_ID: {ghost_emp:,} transaksi (diproses, perlu investigasi)")

    total_clean = len(df)
    log.info(f"  ✓ Hasil cleansing: {total_clean:,} baris valid | "
             f"{total_raw - total_clean:,} dikarantina/dibuang")
    log.info("")
    return df, quarantine_rows


# ============================================================
# [DATA CLEANSING] STAGE 2b — Flatten & bersihkan warehouse
# ============================================================
def stage2_cleanse_warehouse(warehouse_raw):
    """
    [DATA CLEANSING] Flatten nested warehouse JSON → tabular DataFrame.
    Menangani schema drift: 'sisa_stok_akhir' → 'stock_remaining'.
    Stock negatif (anomali data) dikoreksi ke 0 secara defensif.
    """
    records = warehouse_raw.get('records', [])
    log.info(f"  → Flattening {len(records)} warehouse records (schema drift handled)...")

    flat = flatten_warehouse_records(records)
    wh_df = pd.DataFrame(flat)

    if wh_df.empty:
        log.error("[✗] Warehouse DataFrame kosong setelah flatten!")
        return wh_df

    wh_df['Date'] = pd.to_datetime(wh_df['Date']).dt.date

    neg_stock = (wh_df['stock_remaining'] < 0).sum()
    if neg_stock:
        log.warning(f"  [⚠] {neg_stock} entri stok negatif → dikoreksi ke 0")
        wh_df['stock_remaining'] = wh_df['stock_remaining'].clip(lower=0)

    log.info(f"  ✓ Warehouse flat: {len(wh_df):,} baris | "
             f"{wh_df['Date'].nunique()} hari | {wh_df['Item_ID'].nunique()} item")
    log.info("")
    return wh_df


# ============================================================
# [CALCULATION] STAGE 3 — BOM Expansion & Daily Aggregation
# ============================================================
# Mengkonversi penjualan menu (Cup/Porsi) menjadi konsumsi bahan baku
# (gram/ml/pcs) menggunakan tabel resep.
#
# Formula:
#   Total_Consumed[date][item] = Σ (Quantity_terjual × qty_used_per_serving)
#
# Catatan tentang no-BOM items (INV-0002, INV-0005, INV-0007, INV-0018, dll.):
#   Item-item ini tidak muncul di resep manapun, sehingga POS_Consumed-nya
#   selalu = 0. Jika stok fisik item ini bergerak di gudang, selisihnya
#   tidak bisa dijelaskan oleh POS → EXPECTED behavior: trigger Anomaly.
#   Ini sesuai bisnis (stok hilang tanpa penjelasan = perlu investigasi).
# ============================================================
def stage3_transform(sales_clean, bom_df):
    log.info("=" * 62)
    log.info("STAGE 3  [CALCULATION] — BOM Expansion & Daily Aggregation")
    log.info("=" * 62)

    # [CALCULATION] Filter: hanya transaksi dengan Menu_ID valid (bukan ghost)
    sales_valid = sales_clean[~sales_clean['is_ghost_menu']].copy()
    log.info(f"  → Transaksi valid untuk BOM expansion: {len(sales_valid):,}")

    # [CALCULATION] Merge sales × BOM pada Menu_ID (inner join)
    # Setiap transaksi "1 Iced Latte" diledakkan jadi 6 baris ingredient:
    #   18g Espresso + 150ml Susu + 200g Es + 1 Cup + 1 Lid + 1 Straw
    sales_bom = sales_valid.merge(
        bom_df[['Menu_ID', 'Item_ID', 'qty_used']],
        on='Menu_ID',
        how='inner'
    )

    if sales_bom.empty:
        log.warning("  [⚠] BOM expansion kosong! Cek koneksi sales ↔ BOM.")
        return pd.DataFrame(columns=['Date', 'Item_ID', 'POS_Consumed'])

    log.info(f"  → Setelah BOM explode: {len(sales_bom):,} baris ingredient-level")

    # [CALCULATION] Hitung konsumsi per transaksi per bahan
    # Contoh: 3 Iced Latte × 18g kopi = 54g kopi
    sales_bom['Total_Consumed'] = sales_bom['Quantity_Clean'] * sales_bom['qty_used']

    # [CALCULATION] Agregasi harian: jumlahkan semua konsumsi per Item_ID per hari
    daily_cons = (
        sales_bom
        .groupby(['Date', 'Item_ID'], as_index=False)['Total_Consumed']
        .sum()
        .rename(columns={'Total_Consumed': 'POS_Consumed'})
    )

    log.info(f"  ✓ Daily consumption: {len(daily_cons):,} baris | "
             f"{daily_cons['Date'].nunique()} hari | "
             f"{daily_cons['Item_ID'].nunique()} item unik")
    log.info(f"  ℹ  {len(NO_BOM_ITEMS)} item tanpa resep BOM → POS_Consumed=0 → "
             f"stok movement mereka SELURUHNYA masuk Anomaly detection")
    log.info("")
    return daily_cons


# ============================================================
# [CALCULATION] STAGE 4 — Stock Reconciliation
# ============================================================
# Menghitung Expected_Stock dari formula rekonsiliasi dan variance-nya.
#
# Formula rekonsiliasi:
#   Expected_Stock[t] = Physical_Stock[t-1] + Delivery_In[t] − POS_Consumed[t]
#   Variance[t]       = Physical_Stock[t] − Expected_Stock[t]
#
# Interpretasi Variance (penting untuk Stage 5):
#   Variance > 0 (Positif)  → Physical > Expected
#                             POS overcounting: POS klaim konsumsi lebih banyak
#                             daripada yang benar-benar hilang di gudang.
#   Variance < 0 (Negatif)  → Physical < Expected
#                             Shrinkage: stok fisik lebih sedikit dari hitungan POS.
#                             Ini yang paling perlu diwaspadai (pencurian/kehilangan).
#
# Catatan delivery_in:
#   delivery_in sudah TERMASUK dalam stock_remaining (closing stock post-delivery).
#   Formula tetap menambahkan delivery_in karena Expected dihitung dari Prev_Physical
#   yang BELUM termasuk delivery hari ini.
# ============================================================
def stage4_reconcile(wh_df, daily_cons):
    log.info("=" * 62)
    log.info("STAGE 4  [CALCULATION] — Stock Reconciliation")
    log.info("=" * 62)

    # [CALCULATION] Sort by Item_ID + Date untuk shift() yang benar
    wh_sorted = wh_df.sort_values(['Item_ID', 'Date']).copy()

    # [CALCULATION] Prev_Physical = stok fisik hari SEBELUMNYA per item
    # shift(1) dalam group Item_ID → nilai kemarin untuk setiap baris hari ini.
    # Baris pertama setiap Item_ID → NaN (tidak ada baseline) → skip reconciliation.
    wh_sorted['Prev_Physical'] = (
        wh_sorted.groupby('Item_ID')['stock_remaining'].shift(1)
    )

    # [CALCULATION] Merge warehouse dengan daily POS consumption
    # Left join: setiap hari + item tetap muncul meski tidak ada penjualan.
    # POS_Consumed = 0 untuk hari tanpa penjualan (atau item tanpa BOM).
    reconcile = wh_sorted.merge(
        daily_cons, on=['Date', 'Item_ID'], how='left'
    )
    reconcile['POS_Consumed'] = reconcile['POS_Consumed'].fillna(0)

    # [FIX-BUG2] Deteksi hari konsumsi POS yang tidak punya pasangan warehouse.
    # Sales history mencakup 181 hari, warehouse hanya 175 hari.
    # 6 hari POS (6,167 transaksi) tidak masuk rekonsiliasi — warning eksplisit di log.
    wh_dates_set = set(wh_sorted['Date'].unique())
    cons_dates_set = set(daily_cons['Date'].unique()) if not daily_cons.empty else set()
    orphan_days = sorted(cons_dates_set - wh_dates_set)
    if orphan_days:
        orphan_trx = daily_cons[daily_cons['Date'].isin(orphan_days)]['POS_Consumed'].sum()
        log.warning(
            f"  [⚠ BUG2] {len(orphan_days)} hari POS tanpa warehouse record "
            f"→ EXCLUDED dari rekonsiliasi (total konsumsi ter-drop: {orphan_trx:,.0f} units):"
        )
        for d in orphan_days:
            day_cons = daily_cons[daily_cons['Date'] == d]['POS_Consumed'].sum()
            log.warning(f"     {d} : {day_cons:,.0f} units POS consumption tidak direkonsiliasi")

    # [CALCULATION] Hitung Expected Stock
    reconcile['Expected_Stock'] = (
        reconcile['Prev_Physical']   # stok awal (closing kemarin)
        + reconcile['delivery_in']   # + kiriman hari ini
        - reconcile['POS_Consumed']  # - konsumsi POS hari ini
    )

    # [CALCULATION] Hitung Variance
    reconcile['Variance'] = reconcile['stock_remaining'] - reconcile['Expected_Stock']

    n_ok  = reconcile['Variance'].notna().sum()
    n_nan = reconcile['Variance'].isna().sum()
    log.info(f"  ✓ Rekonsiliasi: {len(reconcile):,} total | "
             f"{n_ok:,} bisa dianalisis | {n_nan} skip (hari pertama/no baseline)")
    log.info("")
    return reconcile


# ============================================================
# [ANOMALY LOGIC] STAGE 5 — Action Status Classification
# ============================================================
# Prioritas klasifikasi (first match wins, mutually exclusive):
#
#   ① Invalid Data → Menu_ID tidak ditemukan di BOM/Master_Inventory
#   ② Anomaly      → |Variance| > 1,000 units
#                    Justifikasi matematis: 1,000 > Q3+1.5×IQR = 721 (outlier boundary)
#   ③ Restock      → Physical_Stock < Min_Stock_Threshold (setelah konversi UoM)
#                    Primary: per-item threshold dari Master_Inventory
#                    Fallback: 20,000 units (jika konversi gagal)
#   ④ Safe         → Semua kondisi di atas tidak terpenuhi
#
# Output tambahan (FIX-2, FIX-5):
#   Variance_Direction → 'Shrinkage' | 'POS_Overcount' | 'N/A'
#   Item_Note          → catatan untuk item tanpa BOM atau Invalid Data
# ============================================================
def stage5_classify(reconcile, sales_clean, threshold_dict):
    log.info("=" * 62)
    log.info("STAGE 5  [ANOMALY LOGIC] — Action Status Classification")
    log.info("=" * 62)

    # ── 5a. INVALID DATA — dari ghost Menu_ID ────────────────
    # [ANOMALY LOGIC] Transaksi dengan Menu_ID yang tidak ada di BOM
    # tidak bisa direkonsiliasi → langsung Invalid Data.
    ghost_sales = sales_clean[sales_clean['is_ghost_menu']].copy()
    invalid_entries = []

    if not ghost_sales.empty:
        ghost_grouped = (
            ghost_sales
            .groupby(['Date', 'Menu_ID'])
            .agg(
                Quantity_Total=('Quantity_Clean', 'sum'),
                Transaction_Count=('Transaction_ID', 'count')
            )
            .reset_index()
            .rename(columns={'Menu_ID': 'Item_ID'})
        )
        ghost_grouped['Action_Status']      = 'Invalid Data'
        ghost_grouped['Variance_Direction'] = 'N/A'
        ghost_grouped['Item_Note']          = 'Menu_ID tidak terdaftar di BOM/Master_Inventory'
        invalid_entries.append(ghost_grouped)
        log.info(f"  → Invalid Data (ghost Menu_ID): {len(ghost_grouped):,} baris")

    # ── 5b. KLASIFIKASI REKONSILIASI ─────────────────────────
    # [ANOMALY LOGIC] Terapkan priority rules ke setiap (Date × Item_ID)
    rec = reconcile.copy()

    def classify_row(row):
        """Priority: Anomaly → Restock → Safe"""
        physical  = row['stock_remaining']
        variance  = row['Variance']
        threshold = threshold_dict.get(row['Item_ID'], FALLBACK_RESTOCK_THRESHOLD)

        # [ANOMALY LOGIC] Prioritas ②: Anomaly
        # Threshold 1,000 dipilih secara statistik: lebih besar dari Q3+1.5×IQR = 721
        # sehingga hanya variance yang benar-benar ekstrem yang di-flag.
        if pd.notna(variance) and abs(variance) > ANOMALY_THRESHOLD:
            return 'Anomaly'

        # [ANOMALY LOGIC] Prioritas ③: Restock
        if physical < threshold:
            return 'Restock'

        # [ANOMALY LOGIC] Prioritas ④: Safe
        return 'Safe'

    rec['Action_Status'] = rec.apply(classify_row, axis=1)

    # ── 5c. VARIANCE DIRECTION (FIX-2) ───────────────────────
    # [ANOMALY LOGIC] Bedakan arah anomali untuk membantu investigasi:
    #   Shrinkage    → stok fisik KURANG dari ekspektasi (potensi pencurian/kehilangan)
    #   POS_Overcount→ POS mengklaim konsumsi lebih banyak dari stok yang hilang di gudang
    def get_variance_direction(row):
        if row['Action_Status'] != 'Anomaly' or pd.isna(row['Variance']):
            return 'N/A'
        return 'Shrinkage' if row['Variance'] < 0 else 'POS_Overcount'

    rec['Variance_Direction'] = rec.apply(get_variance_direction, axis=1)

    # ── 5d. ITEM NOTE untuk no-BOM items (FIX-5) ─────────────
    # [ANOMALY LOGIC] Tandai item yang tidak memiliki resep di BOM.
    # Anomaly mereka expected karena POS_Consumed selalu = 0.
    def get_item_note(row):
        if row['Item_ID'] in NO_BOM_ITEMS:
            return 'Item tanpa resep BOM; stok movement tidak bisa dijelaskan POS'
        return ''

    rec['Item_Note']    = rec.apply(get_item_note, axis=1)
    rec['Min_Threshold'] = rec['Item_ID'].map(threshold_dict).fillna(FALLBACK_RESTOCK_THRESHOLD)

    # ── 5e. Statistik distribusi ─────────────────────────────
    status_counts = rec['Action_Status'].value_counts()
    log.info("  Distribusi status rekonsiliasi:")
    for status, count in status_counts.items():
        # Breakdown Anomaly per arah variance
        if status == 'Anomaly':
            shrinkage = (rec['Variance_Direction'] == 'Shrinkage').sum()
            overcount = (rec['Variance_Direction'] == 'POS_Overcount').sum()
            log.info(f"    ├─ {status:<15}: {count:>7,}  "
                     f"(Shrinkage: {shrinkage} | POS_Overcount: {overcount})")
        else:
            log.info(f"    ├─ {status:<15}: {count:>7,}")

    if invalid_entries:
        log.info(f"    └─ Invalid Data   : {sum(len(x) for x in invalid_entries):>7,}")

    # ── 5f. Gabungkan rekonsiliasi + invalid data ─────────────
    recon_report = rec[[
        'Date', 'Item_ID', 'Action_Status',
        'stock_remaining', 'Expected_Stock', 'Variance',
        'Variance_Direction', 'POS_Consumed', 'delivery_in',
        'Min_Threshold', 'Item_Note'
    ]].rename(columns={
        'stock_remaining': 'Physical_Stock',
        'delivery_in'    : 'Delivery_In',
    })

    if invalid_entries:
        inv_df = pd.concat(invalid_entries, ignore_index=True)
        for col in recon_report.columns:
            if col not in inv_df.columns:
                inv_df[col] = np.nan
        inv_df = inv_df[recon_report.columns]
        action_report = pd.concat([recon_report, inv_df], ignore_index=True)
    else:
        action_report = recon_report

    # Sort: date asc, status priority (Anomaly/Invalid dulu), item
    status_order = {'Anomaly': 0, 'Invalid Data': 1, 'Restock': 2, 'Safe': 3}
    action_report['_s'] = action_report['Action_Status'].map(status_order).fillna(9)
    action_report.sort_values(['Date', '_s', 'Item_ID'], inplace=True)
    action_report.drop(columns=['_s'], inplace=True)
    action_report.reset_index(drop=True, inplace=True)

    log.info(f"  ✓ Action Report: {len(action_report):,} baris total")
    log.info("")
    return action_report


# ============================================================
# STAGE 6 — Output
# ============================================================
def stage6_output(action_report, quarantine_rows):
    log.info("=" * 62)
    log.info("STAGE 6  — Output files")
    log.info("=" * 62)

    os.makedirs(os.path.dirname(PATH_OUTPUT_REPORT), exist_ok=True)

    # ── Action_Report.csv ────────────────────────────────────
    # Kolom WAJIB (spec lomba): Date | Item_ID | Action_Status
    # Kolom OPSIONAL (tambahan): Physical_Stock | Expected_Stock | Variance |
    #   Variance_Direction | POS_Consumed | Delivery_In | Min_Threshold | Item_Note
    try:
        action_report.to_csv(PATH_OUTPUT_REPORT, index=False)
        log.info(f"  [✓] Action_Report.csv    → {len(action_report):,} baris")
        log.info(f"      Path : {PATH_OUTPUT_REPORT}")
    except Exception as e:
        log.error(f"  [✗] Gagal tulis Action_Report: {e}")

    # ── quarantine_log.csv ────────────────────────────────────
    if quarantine_rows:
        try:
            q_df = pd.concat(quarantine_rows, ignore_index=True)
            if 'Quarantine_Reason' not in q_df.columns:
                q_df['Quarantine_Reason'] = 'UNKNOWN'
            q_df.to_csv(PATH_OUTPUT_QUARANTINE, index=False)
            log.info(f"  [✓] quarantine_log.csv   → {len(q_df):,} baris")
            log.info(f"      Path : {PATH_OUTPUT_QUARANTINE}")
            for reason, cnt in q_df['Quarantine_Reason'].value_counts().items():
                log.info(f"      ├─ {reason}: {cnt:,}")
        except Exception as e:
            log.error(f"  [✗] Gagal tulis quarantine_log: {e}")

    log.info("")



# ============================================================
# INOVASI — Business Intelligence Enhancements
# ============================================================
# Dua inovasi aktif yang mengubah pipeline dari ETL biasa
# menjadi sistem prediktif dan finansial untuk UMKM:
#
#   INOVASI 1 │ Predictive Days-to-Stockout
#   INOVASI 2 │ Shrinkage Financial Impact (Estimated IDR)
#
# Semua inovasi ADDITIVE — tidak mengubah kolom wajib
# (Date, Item_ID, Action_Status) dan logika klasifikasi.
# ============================================================
def stage_innovations(action_report, daily_cons, wh_df, quarantine_rows,
                      threshold_dict):
    """
    Menambahkan 2 lapisan Business Intelligence ke Action_Report
    dan merapikan tata letak kolom output akhir.
    """
    log.info("=" * 62)
    log.info("INOVASI — Business Intelligence Enhancements")
    log.info("=" * 62)

    ar = action_report.copy()
    ar['Date_dt'] = pd.to_datetime(ar['Date'])

    # ── INOVASI 1: Predictive Days-to-Stockout ────────────────
    # [INOVASI] Mengubah pipeline dari REAKTIF menjadi PREDIKTIF.
    # "Stok akan habis dalam N hari berdasarkan konsumsi 7 hari terakhir."
    # Formula: Days_to_Stockout = (Physical_Stock - Min_Threshold) / Avg_7d_Consumption
    log.info("  [Inovasi 1] Menghitung Days-to-Stockout (rolling 7-day avg)...")

    if not daily_cons.empty:
        cons = daily_cons.copy()
        cons['Date'] = pd.to_datetime(cons['Date'])

        # Pivot ke format: baris=tanggal, kolom=Item_ID
        all_dates = pd.date_range(start=cons['Date'].min(), end=cons['Date'].max(), freq='D')
        cons_pivot = (
            cons.pivot(index='Date', columns='Item_ID', values='POS_Consumed')
            .reindex(all_dates, fill_value=0)
            .fillna(0)
        )

        # Rolling 7-hari rata-rata konsumsi harian per item
        rolling_7d = cons_pivot.rolling(window=7, min_periods=1).mean()

        rolling_long = (
            rolling_7d.reset_index()
            .melt(id_vars='index', var_name='Item_ID', value_name='Avg_7d_Consumption')
            .rename(columns={'index': 'Date_dt'})
        )
        rolling_long['Date'] = rolling_long['Date_dt'].dt.date

        ar = ar.merge(
            rolling_long[['Date', 'Item_ID', 'Avg_7d_Consumption']],
            on=['Date', 'Item_ID'],
            how='left'
        )
    else:
        ar['Avg_7d_Consumption'] = np.nan

    def calc_days_to_stockout(row):
        physical  = row['Physical_Stock']
        threshold = threshold_dict.get(row['Item_ID'], FALLBACK_RESTOCK_THRESHOLD)
        avg_cons  = row.get('Avg_7d_Consumption', 0)
        if pd.isna(physical) or pd.isna(avg_cons) or avg_cons <= 0:
            return np.nan
        gap = physical - threshold
        return 0.0 if gap <= 0 else round(gap / avg_cons, 1)

    ar['Days_to_Stockout'] = ar.apply(calc_days_to_stockout, axis=1)

    def get_restock_urgency(days):
        if pd.isna(days): return 'N/A'
        if days == 0:     return 'CRITICAL'
        if days <= 3:     return 'URGENT'
        if days <= 7:     return 'PLAN_ORDER'
        return 'SUFFICIENT'

    ar['Restock_Urgency'] = ar['Days_to_Stockout'].apply(get_restock_urgency)

    urgent_count = (ar['Restock_Urgency'].isin(['CRITICAL', 'URGENT'])).sum()
    log.info(f"  ✓ Days-to-Stockout dihitung | CRITICAL/URGENT: {urgent_count:,} item-hari")

    # ── INOVASI 2: Shrinkage Financial Impact (Estimated IDR) ──
    # [INOVASI] Mengkonversi selisih stok teknis (gram/ml) ke nilai rupiah.
    # Hanya berlaku untuk Shrinkage Anomaly (Variance < 0 = stok hilang).
    # Sumber harga: estimasi pasar Indonesia 2025 (bukan dari dataset asli).
    log.info("  [Inovasi 2] Menghitung Estimated_Loss_IDR untuk Shrinkage...")

    def calc_financial_impact(row):
        if row.get('Variance_Direction') != 'Shrinkage':
            return np.nan
        unit_cost = UNIT_COST_IDR.get(row['Item_ID'], 0)
        if unit_cost <= 0 or pd.isna(row['Variance']):
            return np.nan
        return round(abs(row['Variance']) * unit_cost)

    ar['Estimated_Loss_IDR'] = ar.apply(calc_financial_impact, axis=1)

    total_loss    = ar['Estimated_Loss_IDR'].sum()
    shrink_count  = ar['Estimated_Loss_IDR'].notna().sum()
    log.info(f"  ✓ Financial impact dihitung | {shrink_count} Shrinkage rows | "
             f"Total estimasi kerugian: Rp {total_loss:,.0f}")

    # ── RAPIKAN TATA LETAK KOLOM ──────────────────────────────
    # Kolom dikelompokkan secara logis agar mudah dibaca oleh owner.
    # Urutan: Identifikasi → Posisi Stok → Rekonsiliasi → Dampak → Pendukung → Catatan
    ar.drop(columns=['Date_dt'], inplace=True, errors='ignore')

    FINAL_COLUMN_ORDER = [
        # ── Identifikasi (3 kolom WAJIB case study) ──────────
        'Date', 'Item_ID', 'Action_Status',
        # ── Posisi Stok & Prediksi (Inovasi 1) ───────────────
        'Physical_Stock', 'Min_Threshold',
        'Days_to_Stockout', 'Restock_Urgency',
        # ── Rekonsiliasi POS vs Gudang ────────────────────────
        'Expected_Stock', 'Variance', 'Variance_Direction',
        # ── Dampak Keuangan (Inovasi 2) ───────────────────────
        'Estimated_Loss_IDR',
        # ── Data Pendukung (untuk investigasi) ───────────────
        'POS_Consumed', 'Avg_7d_Consumption', 'Delivery_In',
        # ── Catatan ──────────────────────────────────────────
        'Item_Note',
    ]
    # Hanya masukkan kolom yang benar-benar ada
    final_cols = [c for c in FINAL_COLUMN_ORDER if c in ar.columns]
    ar = ar[final_cols]

    log.info(f"  ✓ Tata letak kolom dirapikan → {len(final_cols)} kolom terurut secara logis")
    log.info("")
    return ar



# ============================================================
# MAIN — Orkestrasi semua stage
# ============================================================
def main():
    start = time.time()
    log.info("")
    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║   KOPIKITA ROASTERY — DATA AUTOMATION PIPELINE v2       ║")
    log.info("╚══════════════════════════════════════════════════════════╝")
    log.info("")

    # Stage 1: Ingest
    sales_raw, warehouse_raw, inventory_df, bom_data, employee_data = stage1_ingest()

    # Build lookup tables
    bom_df         = build_bom_df(bom_data)
    valid_menu_ids = set(bom_df['Menu_ID'].unique())
    valid_emp_ids  = build_valid_employee_set(employee_data)
    threshold_dict = build_threshold_dict(inventory_df, log=log)
    log.info(f"  → Threshold dict: {len(threshold_dict)} items | "
             f"INV-0001={threshold_dict.get('INV-0001',0):,.0f}g | "
             f"INV-0004={threshold_dict.get('INV-0004',0):,.0f}ml")
    log.info("")

    # Stage 2: Cleanse
    sales_clean, quarantine_rows = stage2_cleanse_sales(
        sales_raw, valid_menu_ids, valid_emp_ids
    )
    wh_df = stage2_cleanse_warehouse(warehouse_raw)

    # Stage 3: BOM Expansion
    daily_cons = stage3_transform(sales_clean, bom_df)

    # Stage 4: Reconciliation
    reconcile = stage4_reconcile(wh_df, daily_cons)

    # Stage 5: Classification
    action_report = stage5_classify(reconcile, sales_clean, threshold_dict)

    # Stage INOVASI: Business Intelligence Enhancements (Inovasi 1 + 2)
    action_report = stage_innovations(
        action_report, daily_cons, wh_df, quarantine_rows,
        threshold_dict
    )

    # Stage 6: Output
    stage6_output(action_report, quarantine_rows)

    # Summary
    elapsed = time.time() - start
    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info(f"║  PIPELINE SELESAI dalam {elapsed:.2f} detik{' '*(30-len(f'{elapsed:.2f}'))}║")
    log.info("╚══════════════════════════════════════════════════════════╝")
    log.info("")
    log.info("RINGKASAN ACTION REPORT:")
    for status, cnt in action_report['Action_Status'].value_counts().items():
        log.info(f"  {status:<15}: {cnt:>8,} baris")
    # Breakdown Anomaly direction
    anom = action_report[action_report['Action_Status']=='Anomaly']
    if not anom.empty:
        shrink  = (anom['Variance_Direction']=='Shrinkage').sum()
        overct  = (anom['Variance_Direction']=='POS_Overcount').sum()
        log.info(f"  {'(Shrinkage)':<15}: {shrink:>8,}")
        log.info(f"  {'(POS_Overcount)':<15}: {overct:>8,}")
    log.info(f"  {'TOTAL':<15}: {len(action_report):>8,} baris")


if __name__ == '__main__':
    main()

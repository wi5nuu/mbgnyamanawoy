# Hubungan Antara `quarantine_log.csv` dan `Action_Report.csv`

---

## Diagram Alur Data Lengkap (dari log run)

```
📁 SOURCE FILES
╔═══════════════════════════════════════════════════════════════╗
║ sales_history.csv  → 270.400 baris  │  7 kolom              ║
║ warehouse_stock.json → 176 daily rec │  5+ kolom             ║
║ Master_Inventory.csv → 49 items      │  6 kolom             ║
║ Recipe_BOM.json      → 30 menu items │  nested structure     ║
║ Employee.json        → 15 karyawan   │  3 kolom             ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║ STAGE 1 — DATA INGESTION (0.5 detik)                        ║
║ Memuat semua file, validasi schema dasar, fallback UoM       ║
║ [WARN] 5 UoM tidak dikenal → fallback ke default             ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║ STAGE 2 — DATA CLEANSING (11 detik)                         ║
║                                                               ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ 7 LAPIS VALIDASI                                     │     ║
║  │                                                       │     ║
║  │ 1. DUPLICATE_TRANSACTION_ID    → 11.827 baris ❌     │     ║
║  │ 2. ERROR_FLAG_IN_ADDINFO       → 17.920 baris ❌     │     ║
║  │ 3. NULL_CRITICAL_FIELD         → 17.532 baris ❌     │     ║
║  │ 4. UNPARSEABLE_DATE            →  4.559 baris ❌     │     ║
║  │ 5. NEGATIVE_QUANTITY           →  6.828 baris ❌     │     ║
║  │ 6. UNPARSEABLE_QUANTITY        →  4.840 baris ❌     │     ║
║  │ 7. ZERO_QUANTITY               → 11.464 baris ❌     │     ║
║  │                                                       │     ║
║  │ TOTAL QUARANTINE: 74.970 baris                       │     ║
║  │ VALID: 195.430 baris                                 │     ║
║  │                                                       │     ║
║  │ Ghost Menu_ID: 19.714 transaksi (ditandai)            │     ║
║  │ Ghost Employee_ID: 16.840 transaksi (warnings)        │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                               ║
║  Warehouse: 269 entri stok negatif → dikoreksi ke 0          ║
║  Warehouse flat: 6.615 baris | 167 hari | 45 item            ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║ STAGE 3 — BOM EXPANSION (2 detik)                           ║
║                                                               ║
║  175.716 transaksi valid untuk BOM                           ║
║  → 856.639 baris ingredient-level (×4,87 lipat)              ║
║  → Daily consumption: 23.562 baris | 1.086 hari              ║
║  → 34 item unik                                               ║
║  → 8 item tanpa resep BOM → POS_Consumed = 0                 ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║ STAGE 4 — STOCK RECONCILIATION                              ║
║                                                               ║
║  [⚠ BUG2] 919 hari POS tanpa warehouse record                ║
║  → 23.560.488 units konsumsi TER-DROP                        ║
║  → Ini berarti Action_Report KURANG akurat                   ║
║                                                               ║
║  Rekonsiliasi sukses: 6.570 dari 6.615 baris                  ║
║  45 skip (hari pertama / no baseline)                         ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║ STAGE 5 — ACTION STATUS CLASSIFICATION                      ║
║                                                               ║
║  ┌─ Invalid Data (ghost Menu_ID) ────→ 2.564 baris          ║
║  │                                                             ║
║  ├─ Physical_Stock < Min_Threshold ──→ Restock: 12 baris     ║
║  │                                                             ║
║  ├─ Variance dalam batas ─────────────→ Safe: 159 baris      ║
║  │                                                             ║
║  └─ Variance besar ──────────────────→ Anomaly: 6.444 baris  ║
║       ├─ Shrinkage (UNDER):   2.861   │ Estimated Loss:       ║
║       └─ POS_Overcount (OVER): 3.583  │ Rp 264,8 Miliar      ║
║                                                               ║
║  TOTAL: 9.179 baris Action_Report                            ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║ OUTPUT FILES                                                 ║
║                                                               ║
║  quarantine_log.csv  →  74.970 baris  →  AUDIT KUALITAS DATA ║
║  Action_Report.csv   →   9.179 baris  →  REKOMENDASI BISNIS  ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## Aliran Data: Dari Satu Transaksi ke Dua Output

Mari ikuti satu baris fiktif untuk memahami bagaimana satu transaksi bisa berakhir di quarantine_log ATAU Action_Report.

### Skenario A: Transaksi Masuk Karantina

```
Transaksi: TRX-0500 | 2025-03-15 | EMP-03 | MENU-010 | Quantity: 0 | Info: -
     │
     ▼
Lapis 1: Duplikat? → Tidak (ID unik)
Lapis 2: Error flag? → Tidak (info bersih)
Lapis 3: NULL field? → Tidak (semua terisi)
Lapis 4: Tanggal? → 2025-03-15 ✅ parseable
Lapis 5: Quantity negatif? → Tidak (0 bukan negatif)
Lapis 6: Quantity parseable? → 0 ✅ parseable
Lapis 7: Quantity = 0? → YA ❌
     │
     ▼
✗ QUARANTINE → ZERO_QUANTITY
  Ditulis ke quarantine_log.csv
  TIDAK masuk ke Action_Report
```

### Skenario B: Transaksi Lolos ke Action_Report

```
Transaksi: TRX-0501 | 2025-03-15 | EMP-03 | MENU-010 | Quantity: 5 | Info: -
     │
     ▼
Lapis 1-7: ✅ SEMUA LOLOS
     │
     ▼
✓ Transaksi VALID (195.430 lainnya)
     │
     ▼
BOM Explode: MENU-010 = 10g kopi + 200ml susu + 15g gula
  → 3 baris ingredient: (kopi: 50g, susu: 1000ml, gula: 75g)
     │
     ▼
Daily Aggregation: 2025-03-15 → INV-0001 (kopi): +50g terpakai
     │
     ▼
Stock Reconciliation: INV-0001 pada 2025-03-15
  Physical_Stock = 29.934,8 (dari warehouse)
  Expected_Stock = Stock_14Mar - POS_Consumed_15Mar + Delivery_In
                  = 35.000 - 5.065,2 + 0 = 29.934,8
  Variance = 29.934,8 - 29.934,8 = 0 ✅
     │
     ▼
Classification: Physical_Stock (29.934) < Min_Threshold (99.000)? → YA
     │
     ▼
✓ Action_Report → Status: Restock | Urgency: CRITICAL
```

---

## Statistik Gabungan dari Run

### Distribusi 270.400 transaksi

```
                         ┌──────────────────────────┐
                         │   TOTAL TRANSACTIONS     │
                         │       270.400            │
                         │         100%             │
                         └────────────┬─────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              │                                               │
              ▼                                               ▼
┌─────────────────────────────┐             ┌─────────────────────────────┐
│        QUARANTINED          │             │     PIPELINE LANJUT         │
│         74.970              │             │       195.430               │
│         27,7%               │             │        72,3%               │
│                             │             │                             │
│  Alasan karantina:          │             │                             │
│  ERROR_FLAG_IN_ADDINFO      │             │  → BOM Explode: 175.716    │
│    → 17.920 (23,9%)         │             │  → Ghost ID: 19.714        │
│  NULL_CRITICAL_FIELD        │             │                             │
│    → 17.532 (23,4%)         │             │  → Valid ingredients        │
│  DUPLICATE_TRANSACTION_ID   │             │     856.639 baris           │
│    → 11.827 (15,8%)         │             │                             │
│  ZERO_QUANTITY              │             │  → Rekonsiliasi             │
│    → 11.464 (15,3%)         │             │     6.570 dari 6.615        │
│  NEGATIVE_QUANTITY          │             │                             │
│    →  6.828 (9,1%)          │             │  → Action_Report            │
│  UNPARSEABLE_QUANTITY       │             │     9.179 baris             │
│    →  4.840 (6,5%)          │             │                             │
│  UNPARSEABLE_DATE           │             │                             │
│    →  4.559 (6,1%)          │             │                             │
└─────────────────────────────┘             └─────────────────────────────┘
```

### Visual Persentase

```
Dari 270.400 transaksi:
  ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■□□ 27,7% Karantina
  ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ 72,3% Lanjut

Dari 9.179 Action_Report:
  ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ 70,2% Anomaly
  ■■■■■■■■■■■■■■■■■■■■■■■■□□□□□□□□□□□□□□□□□□□□□□□□□□□□ 27,9% Invalid Data
  ■■□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□ 1,7% Safe
  □□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□ 0,1% Restock
```

---

## Hubungan Antar Data: Tabel Silang

### Dari sisi alasan (quarantine) → dampak ke (action)

| Alasan Karantina | Jumlah | Dampak ke Action_Report | Level Keparahan |
|---|---|---|---|
| ERROR_FLAG_IN_ADDINFO | 17.920 | Data ini TIDAK ADA di Action_Report — transaksi dianggap tidak pernah terjadi | 🔴 Data hilang |
| NULL_CRITICAL_FIELD | 17.532 | Data ini TIDAK ADA di Action_Report — tidak bisa diidentifikasi | 🔴 Data hilang |
| DUPLICATE_TRANSACTION_ID | 11.827 | Data ini TIDAK ADA di Action_Report — hanya 1 dari X yang diproses | 🟡 Potensi undercount |
| ZERO_QUANTITY | 11.464 | Data ini TIDAK ADA di Action_Report — qty 0 tidak berpengaruh | 🟢 Tidak berdampak |
| NEGATIVE_QUANTITY | 6.828 | Jika lolos, akan OVERCOUNT stok. Karena dikarantina → aman | 🟢 Mencegah kesalahan |
| UNPARSEABLE_QUANTITY | 4.840 | Data ini TIDAK ADA di Action_Report — konsumsi tidak terhitung | 🟡 Potensi undercount |
| UNPARSEABLE_DATE | 4.559 | Data ini TIDAK ADA di Action_Report — tanggal tidak dikenal | 🟡 Potensi undercount |
| **Total karantina** | **74.970** | Semua TIDAK MASUK Action_Report | — |
| Ghost Menu_ID (lolos) | 19.714 | Masuk Action_Report sebagai **Invalid Data** (2.564 baris agregat) | 🟡 Diketahui, tidak diproses |
| Ghost Employee_ID (lolos) | 16.840 | Masuk Action_Report seperti normal (diproses) | 🟡 Warning, perlu investigasi |

### Dari sisi status (action) → kemungkinan penyebab di data sumber

| Status Action | Jumlah | Kemungkinan Penyebab di Data Sumber |
|---|---|---|
| **Anomaly (Shrinkage)** | 2.861 | Barang hilang, rusak, kadaluarsa, dicuri. Atau data penjualan tidak lengkap karena banyak transaksi dikarantina. |
| **Anomaly (POS_Overcount)** | 3.583 | Barang masuk tidak tercatat, stok awal salah, atau ada item tanpa BOM. |
| **Invalid Data** | 2.564 | Ghost Menu_ID dari dataset — sengaja dibuat untuk testing. |
| **Safe** | 159 | Data normal. Stok cukup, konsumsi normal. |
| **Restock** | 12 | Stok di bawah threshold. Mungkin karena banyak transaksi valid (penjualan tinggi) atau stok awal memang rendah. |

---

## BUG2: 919 Hari POS Tanpa Warehouse Record

Ini adalah temuan penting dari run ini:

```
[⚠ BUG2] 919 hari POS tanpa warehouse record → EXCLUDED dari rekonsiliasi
Total konsumsi ter-drop: 23,560,488 units
```

**Apa yang terjadi:**
- Pipeline punya data penjualan (POS) dari tahun 2025 sampai 2099
- Tapi data warehouse stock hanya dari 2025-01-01 sampai 2025-06-17 (167 hari)
- Untuk tanggal di luar rentang itu, pipeline tidak bisa rekonsiliasi
- Akibatnya: **23,5 juta unit konsumsi tidak direkonsiliasi**

**Dampak ke Action_Report:**
- 919 hari data penjualan tidak masuk perhitungan
- Action_Report hanya mencakup periode di mana ada data warehouse
- Ini mengurangi coverage Action_Report secara signifikan

**Penyebab di dataset:** Kami sengaja membuat data penjualan dengan tahun 2026-2099 untuk stress test. Warehouse data hanya untuk 2025. Ini mengungkap **BUG asli**: pipeline seharusnya bisa handle missing warehouse data dengan lebih baik.

---

## Studi Kasus Lengkap: INV-0025

Mari lihat bagaimana pipeline menangani satu item secara utuh.

### Langkah 1: Data Sumber

INV-0025 adalah item di Master_Inventory dengan threshold 3.000 unit.

### Langkah 2: Transaksi di Karantina

Di quarantine_log, cari `INV-0025`:
```
Transaction_ID,DateTime,Employee_ID,Menu_ID,Item_Name,Quantity,...,Quarantine_Reason
TRX-A,2025-03-01,EMP-05,MENU-010,Kopi Susu,0,...,ZERO_QUANTITY
TRX-B,2025-03-01,EMP-05,MENU-010,Kopi Susu,-7,...,NEGATIVE_QUANTITY
TRX-C,2025-03-02,,MENU-010,Kopi Susu,5,...,NULL_CRITICAL_FIELD
...
```

→ Beberapa transaksi INV-0025 dikarantina. Ini berarti **data penjualan INV-0025 tidak lengkap** di pipeline.

### Langkah 3: Rekonsiliasi

Di Action_Report:
```
Date,Item_ID,Action_Status,Physical_Stock,Expected_Stock,Variance,Variance_Direction,Estimated_Loss_IDR
2025-01-01,INV-0025,Anomaly,17653.5,149674.6,-132021.1,UNDER,6601055.0
```

**Analisis:**
- Stok fisik: 17.653 unit
- Stok ekspektasi: 149.674 unit
- Variance: -132.021 unit
- Estimated Loss: Rp 6.601.055

### Langkah 4: Diagnosis

Ada dua kemungkinan:

| Kemungkinan | Bukti | Solusi |
|---|---|---|
| **Shrinkage nyata** — barang benar-benar hilang | Jika karantina INV-0025 rendah (< 5% dari total) | Cek fisik gudang, audit keamanan |
| **Data tidak lengkap** — banyak transaksi dikarantina | Jika karantina INV-0025 tinggi (> 20% dari total) | Perbaiki kualitas data entry, update validasi |

Di dataset ini, kemungkinan **shrinkage nyata + data tidak lengkap** — karena stress test sengaja membuat kedua situasi terjadi bersamaan.

---

## Ringkasan Perbandingan Kedua Output

| Aspek | `quarantine_log.csv` | `Action_Report.csv` |
|---|---|---|
| **Fokus** | Kualitas data — apa yang salah? | Kesehatan stok — apa yang harus dilakukan? |
| **Target pengguna** | Data engineer, analis data, auditor | Manajer operasional, pemilik toko, purchasing |
| **Pertanyaan yang dijawab** | "Data mana yang rusak dan kenapa?" | "Apa yang harus saya lakukan?" |
| **Jumlah baris** | 74.970 | 9.179 |
| **Arah analisis** | Masa lalu — debugging sumber data | Masa depan — rekomendasi aksi |
| **Tindak lanjut** | Perbaiki sumber data, update validasi | Restok, investigasi anomali, pantau rutin |
| **Frekuensi** | Setiap kali ETL dijalankan | Setiap kali ETL dijalankan |
| **Nilai bisnis** | Memastikan data bersih sebelum diproses | Memberi rekomendasi aksi nyata |
| **Waktu proses** | ~11 detik (Stage 2) | ~3 detik (Stage 3-5) |
| **Error handling** | Data ditolak | Data diproses dengan flag |
| **Dampak jika diabaikan** | Data kotor mengotori sistem | Stok salah, keputusan bisnis keliru |

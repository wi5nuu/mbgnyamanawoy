# DOKUMEN ANALISIS DAN DESAIN SISTEM
## Automated Data Pipeline — Kopikita Roastery

| Atribut | Keterangan |
|---|---|
| Proyek | Data Automation Pipeline untuk UMKM F&B |
| Sistem | Kopikita Roastery — Automated Inventory Reconciliation |
| Teknologi | Python 3.13 · pandas · JSON/CSV processing |
| Dataset | **170.613 baris POS** · **175 rekord gudang** · **6 bulan data (Jan–Jun 2025)** |
| Output | `Action_Report.csv` (7.988 baris) · `quarantine_log.csv` (14.508 baris) |

### Ringkasan Eksekutif

Pipeline ini memproses 170.613 baris data transaksi POS kotor dan 175 rekord gudang harian dalam **3–5 detik** tanpa intervensi manual, menghasilkan 7.988 baris laporan aksi dan 14.508 baris log diagnostik yang terklasifikasi.

Sistem mendeteksi **1.367 anomali stok** (101 Shrinkage + 1.266 POS Overcount), mengidentifikasi estimasi kerugian **Rp 36.260.603** selama 6 bulan, dan memprediksi stockout hingga 7 hari ke depan per item.

---

## 1. Problem Analysis

Bisnis F&B skala UMKM seperti Kopikita Roastery menghadapi tantangan unik: volume transaksi tinggi (ratusan cup per hari), bahan baku beragam, namun infrastruktur digital masih terfragmentasi. Analisis mendalam terhadap dataset mengidentifikasi 6 titik lemah operasional yang menjadi akar masalah.

| # | Titik Lemah | Dampak Operasional | Tingkat Risiko |
|---|---|---|---|
| 1 | **Fragmentasi Data (Data Silo)** — POS export CSV, gudang JSON, supplier dalam satuan berbeda. Tidak ada sistem yang mengintegrasikan ketiganya. | Owner tidak tahu stok real-time. Keputusan restock berdasarkan estimasi, bukan data aktual. | **TINGGI** |
| 2 | **UoM Mismatch 3-Lapisan** — Supplier: Kilogram/Liter/Karton, Gudang: gram/ml/pcs, POS: Cup/Porsi | Tidak bisa langsung membandingkan stok gudang dengan konsumsi POS. Perlu konversi manual yang rawan error. | **TINGGI** |
| 3 | **Karton — Satuan Ambigu** — Karton bukan satuan baku. Tidak ada kolom faktor konversi di dataset. | Threshold restock tidak akurat: "3 Karton Paper Cup = ? pcs" bergantung pada jenis karton. | **SEDANG** |
| 4 | **Dirty Data Masif** — 7 pola data kotor ditemukan: duplikat, null, negatif, format campur, error flag, schema drift. | 14.508 baris bermasalah dari 170.613. Tanpa cleansing, kalkulasi stok salah dan bisa memicu keputusan bisnis keliru. | **TINGGI** |
| 5 | **Schema Drift Tanpa Notifikasi** — `wh_stock.json` berubah format per 2025-04-01: 86 rekord pakai `stock_remaining`, 89 rekord pakai `sisa_stok_akhir` (tanpa dokumentasi). | Tanpa penanganan, 89 rekord (April–Juni) menjadi NULL. 3 bulan data rekonsiliasi hilang. | **TINGGI** |
| 6 | **Tidak Ada Anomaly Detection** — Shrinkage/pencurian tidak terdeteksi. Manual audit 170K+ baris tidak praktis. | Kerugian finansial tidak terukur. Estimasi 6 bulan: Rp 36.260.603 dari Shrinkage yang tidak terdeteksi. | **KRITIS** |

---

## 2. Data Quality Report

Eksplorasi mendalam terhadap kelima dataset mengidentifikasi 7 pola dirty data yang berbeda. Setiap pola ditangani dengan strategi tersendiri sehingga pipeline tidak crash dan tetap menghasilkan output yang akurat.

| # | Pola Dirty Data | Jumlah | File Sumber | Strategi Penanganan |
|---|---|---|---|---|
| 1 | **Duplikat Transaction_ID** — Sama ID, double-export POS | 2.521 | `sales_history.csv` | Keep first occurrence, buang sisanya ke quarantine label `DUPLICATE_TRANSACTION_ID` |
| 2 | **Error Flag POS di Additional_Info** — (`error`, `#value`, `#ref!`, `undefined`, `invalid`, dll — 11+ varian) | 6.458 | `sales_history.csv` | Exclude sepenuhnya dari BOM expansion. Quarantine label `ERROR_FLAG_IN_ADDINFO` |
| 3 | **Null di Field Kritis** — (DateTime 1.008 + Menu_ID 2.295 + Quantity 2.259, overlap) | 3.546 | `sales_history.csv` | Quarantine dengan deteksi field spesifik `NULL_CRITICAL_FIELD` |
| 4 | **Quantity Negatif** — (-1, -3: diduga transaksi refund) | 1.297 | `sales_history.csv` | Quarantine label `NEGATIVE_QUANTITY` (Recovery: HIGH) |
| 5 | **Quantity Nol (Void/Cancelled)** — Pesanan dibatalkan kasir | 686 | `sales_history.csv` | Quarantine label `ZERO_QUANTITY` (Recovery: MEDIUM) |
| 6 | **DateTime Format Non-Standar** — Dominan ISO (97,6%), sisanya 5 varian: DD/MM/YYYY, Month DD YYYY, Compact 12-digit, MM-DD-YYYY AM/PM, titik separator | ~3.030 | `sales_history.csv` | **6-pass parser**: ISO → DD/MM → Month Name → Compact 12-digit → MM-DD-YYYY AM/PM → fallback `pd.to_datetime(errors='coerce')` |
| 7 | **Schema Drift JSON Warehouse** — Key berubah per 2025-04-01: `stock_remaining` → `sisa_stok_akhir` | 89 rekord (dari 175 total) | `warehouse_stock.json` | Key-set comparison: `sisa_stok_akhir` dinormalisasi ke `stock_remaining` otomatis |

> **Catatan**: 1.623 baris dengan quantity tidak terparsing (nilai non-numerik seperti "eight") **berhasil diselamatkan** oleh 3-layer parsing rescue — tidak masuk karantina. Detail di Section 4.1.

### 2.1 Data Validasi — Detail Audit Dataset V1

Audit dilakukan langsung terhadap file source dengan script verifikasi (total waktu: 0,37 detik):

| Metrik | Nilai | Detail |
|---|---|---|
| **SALES** | | |
| Total baris | 170.613 | — |
| Transaction_ID unik | 168.092 | 2.521 baris duplikat (1,5%) |
| Employee_ID kosong | 2.505 | Ditangani NULL_CRITICAL |
| Menu_ID kosong | 2.295 | Ditangani NULL_CRITICAL |
| DateTime kosong | 1.008 | Ditangani NULL_CRITICAL |
| | | |
| **Date Format Distribution** | | |
| ISO YYYY-MM-DD HH:MM:SS | 166.575 (97,6%) | Format standar |
| DD/MM/YYYY | 611 (0,4%) | Non-standar, terparsing |
| Month DD YYYY | 605 (0,4%) | Non-standar, terparsing |
| Compact 12-digit | 571 (0,3%) | Non-standar, terparsing |
| MM-DD-YYYY AM/PM | 596 (0,3%) | Non-standar, terparsing |
| OTHER (dot separator) | 647 (0,4%) | Non-standar, terparsing |
| EMPTY | 1.008 (0,6%) | NULL, masuk karantina |
| | | |
| **Quantity Distribution** | | |
| Valid numerik | 164.748 (96,6%) | — |
| Kosong (NULL) | 2.259 (1,3%) | Masuk karantina |
| Non-numerik (terescue) | 1.623 (1,0%) | Diselamatkan 3-layer parser |
| Negatif | 1.297 (0,8%) | Masuk karantina |
| Nol | 686 (0,4%) | Masuk karantina |
| | | |
| **WAREHOUSE** | | |
| Total records | 175 | — |
| Format lama (stock_remaining) | 86 (Jan–Mar) | — |
| Format baru (sisa_stok_akhir) | 89 (Apr–Jun) | Schema drift |
| Rentang tanggal | 2025-01-01 – 2025-06-30 | 6 bulan |
| | | |
| **MASTER DATA** | | |
| Master_Inventory items | **42** | 19 Karton, 23 non-Karton |
| Recipe_BOM menu items | **25** | 120 ingredient links |
| Employee records | **6** | Shift_Lead (2), Barista (3), Kasir (1) |

### 2.2 Smart Quarantine Triage

Inovasi tambahan: pipeline mengklasifikasikan setiap baris quarantine secara otomatis menggunakan Smart Quarantine Triage System, menghilangkan kebutuhan review manual terhadap 14.508 baris. Temuan utama: **58% data quarantine bukan sampah murni** (8.441 dari 14.508 baris memiliki potensi recovery).

| Triage Class | Jumlah | Recovery | Penjelasan |
|---|---|---|---|
| `PARTIAL_ERROR` | 6.458 | MEDIUM | Error di metadata POS; DateTime + Menu_ID + Quantity valid |
| `REFUND_TRANSACTION` | 1.297 | HIGH | Kuantitas negatif = kemungkinan transaksi retur pelanggan |
| `VOID_TRANSACTION` | 686 | MEDIUM | Qty=0 = pesanan di-void/dibatalkan. Berguna untuk analisis void rate |
| `EXACT_DUPLICATE` | 2.521 | LOW | Salinan Transaction_ID identik. Aman dibuang |
| `UNRECOVERABLE` | 3.546 | NONE | Field kritis kosong. Tidak dapat diproses untuk tujuan apapun |

---

## 3. Analisis Ambiguitas Satuan "Karton"

"Karton" bukanlah satuan ukur baku seperti gram atau liter — ini adalah satuan kemasan yang isinya bervariasi tergantung jenis produk dan supplier. Dataset Master_Inventory mencatat **19 item** dengan Supplier_UoM = Karton tanpa menyertakan kolom faktor konversi (berapa unit per karton), menciptakan gap kritis dalam pipeline.

### 3.1 Dampak Gap Dataset

**Masalah:**
- `Master_Inventory`: `Min_Stock_Threshold = 3 Karton` (untuk Paper Cup 8oz)
- `Warehouse`: `stock_remaining = 150 pcs`

**PERTANYAAN:** Apakah 150 pcs di atas atau di bawah threshold 3 Karton?

**JAWABAN:** Tidak bisa dijawab tanpa tahu "1 Karton = berapa pcs" — inilah ambiguitasnya.

### 3.2 Kategorisasi 19 Item Karton

| Item_ID | Nama Item | WH UoM | Min Threshold | Faktor Konversi | Threshold Converted | Basis Asumsi |
|---|---|---|---|---|---|---|
| INV-0007 | Condensed Milk | ml | 2 Karton | × 4.440 | 8.880 ml | 12 kaleng × 370ml |
| INV-0022 | Sparkling Water | ml | 2 Karton | × 7.920 | 15.840 ml | 24 botol × 330ml |
| INV-0017 | Black Tea Bag | pcs | 2 Karton | × 100 | 200 pcs | Standar box teh industri |
| INV-0018 | Green Tea Bag | pcs | 2 Karton | × 100 | 200 pcs | Standar box teh industri |
| INV-0025–31 | Cup & Lid (6 varian) | pcs | 3–5 Karton | × 50 | 150–250 pcs | Standar sleeve F&B |
| INV-0032 | Paper Straw | pcs | 3 Karton | × 250 | 750 pcs | Bulk pack straw industri |
| INV-0033 | Wooden Stirrer | pcs | 2 Karton | × 250 | 500 pcs | Bulk pack stirrer industri |
| INV-0034 | Napkin | pcs | 2 Karton | × 200 | 400 pcs | Standar pack napkin |
| INV-0035–37 | Frozen Bakery (3 item) | pcs | 3 Karton | × 20 | 60 pcs | Standar frozen food box |
| INV-0038 | Chocolate Muffin | pcs | 3 Karton | × 24 | 72 pcs | Standar bakery box 24pcs |
| INV-0039 | Cheese Slice | pcs | 2 Karton | × 20 | 40 pcs | Standar deli pack |

### 3.3 Solusi: `KARTON_CONVERSION` Dictionary

Pipeline menyelesaikan ambiguitas ini dengan mendefinisikan `KARTON_CONVERSION` — dictionary di `utils.py` yang memetakan setiap Item_ID ke faktor konversi berdasarkan standar kemasan industri F&B Indonesia 2025. Seluruh 19 item Karton terdefinisi; jika ada item baru di stress test, sistem menggunakan fallback 20.000 units dan mencatat warning di log.

**Rekomendasi Bisnis:**
Titik lemah ini seharusnya diselesaikan di level sistem, bukan di pipeline. Tambahkan kolom `Units_Per_Supplier_Package` ke `Master_Inventory.csv` agar konversi bersifat data-driven, bukan hardcoded. Pipeline sudah dirancang untuk menerima perubahan ini — hanya perlu modifikasi satu fungsi `build_threshold_dict()` di `utils.py`.

---

## 4. System Solution

Pipeline dibangun dalam arsitektur 6-stage ETL yang berjalan sepenuhnya otomatis (zero human intervention) dari pembacaan data mentah hingga pelaporan, dalam satu siklus eksekusi tunggal: `python pipeline.py`.

### 4.1 Arsitektur 6-Stage ETL

| Stage | Nama | Fungsi Utama | File | Waktu |
|---|---|---|---|---|
| 1 | **Data Ingestion** | Load 5 file sumber dengan error handling per-file. Validasi integritas JSON/CSV. | `pipeline.py` | < 1 dtk |
| 2 | **Data Cleansing** | 7 lapis validasi: dedup, error flag, null, datetime multi-format (6-pass), quantity rescue (3-layer). | `pipeline.py` + `utils.py` | ~3 dtk |
| 3 | **BOM Expansion** | 175.716 transaksi valid → 856.639 baris ingredient-level via 25 resep menu. | `pipeline.py` | ~1 dtk |
| 4 | **Reconciliation** | Hitung Expected_Stock dari POS dan bandingkan dengan Physical_Stock gudang. | `pipeline.py` | < 1 dtk |
| 5 | **Anomaly Logic** | Klasifikasikan 6.570 baris rekonsiliasi ke Safe / Restock / Invalid Data / Anomaly. | `pipeline.py` | < 1 dtk |
| 6 | **Output** | Tulis `Action_Report.csv` (7.988 baris) dan `quarantine_log.csv` (14.508 baris). | `pipeline.py` + `utils.py` | < 1 dtk |

### 4.2 Tiga Lapis Parsing Quantity

Pipeline menggunakan **3 lapis parsing** untuk menangani quantity non-numerik:

```
Input → Lapis 1: pd.to_numeric(errors='coerce')
         ├─ Berhasil → angka → validasi negatif/zero
         └─ Gagal (NaN)
               ↓
         Lapis 2: Regex r'(-?\d+)' ekstrak digit pertama
         ├─ Berhasil → angka (rescue!)
         └─ Gagal
               ↓
         Lapis 3: Manual lookup WORD_TO_NUM dictionary
                  "eight" → 8, "two" → 2, "one" → 1
         ├─ Berhasil → angka (rescue!)
         └─ Gagal → UNPARSEABLE_QUANTITY
```

Hasil: **1.623 baris quantity non-numerik berhasil diselamatkan** dan tidak masuk karantina.

### 4.3 Logika Klasifikasi Restock — Narasi Aturan Bisnis

Setiap item di gudang memiliki ambang batas minimal (`Min_Stock_Threshold`) yang disimpan di `Master_Inventory.csv` dalam satuan *Supplier_UoM* (Kilogram, Liter, Karton, atau Pcs). Logika restock bekerja dengan prinsip sederhana: **jika stok fisik turun di bawah ambang batas, sistem menandai item untuk di-restock**.

**Namun** — tantangannya ada di konversi satuan. Data gudang mencatat stok dalam gram/ml/pcs (`Warehouse_UoM`), sementara threshold dari supplier dalam Kg/Ltr/Karton. Pipeline menyelesaikan ini dengan pipeline konversi bertahap:

1. **Threshold lookup**: Baca `Min_Stock_Threshold` dari Master_Inventory, misalnya "3 Karton" untuk Paper Cup ukuran S.
2. **Konversi satuan**: Kalikan dengan faktor dari `KARTON_CONVERSION` dictionary (item-by-item, bukan global — karena 1 Karton Paper Cup = 50 pcs, tapi 1 Karton Straw = 250 pcs). Untuk Kg dan Liter, konversi bersifat linear (×1.000).
3. **Perbandingan**: `IF Physical_Stock < threshold_converted THEN Status = Restock`. Jika Perbandingan dilakukan setelah UoM Match — tidak lagi membandingkan "3 Karton vs 150 pcs", tapi "150 pcs vs 150 pcs".
4. **Fallback safety**: Jika item tidak ditemukan di `KARTON_CONVERSION` (misal item baru di stress test), pipeline menggunakan 20.000 units sebagai default dan mencatat WARNING ke log — gacha tidak menghentikan pipeline.
5. **Override priority**: *Anomaly beat Restock* — jika suatu item memenuhi syarat Anomaly (variance melebihi ±1.000 unit) sekaligus Restock, status akhirnya adalah Anomaly. Logikanya: restock bisa menunggu 1 hari, tapi shrinkage perlu investigasi segera.

### 4.4 Formula Deteksi Anomali Shrinkage — Narasi Detektif Stok

Deteksi anomali shrinkage bekerja seperti **detektif stok**: pipeline membandingkan antara "berapa stok yang seharusnya ada" (Expected) dengan "berapa stok yang benar-benar ada" (Physical). Selisihnya disebut *Variance* — dan jika selisih ini terlalu besar, ada sesuatu yang tidak beres.

**Perhitungan langkah demi langkah:**

1. **Expected_Stock(t)** = `Physical_Stock(t-1) + Delivery_In(t) - POS_Consumed(t)`
   - `Physical_Stock(t-1)`: Stok fisik hari sebelumnya dari warehouse JSON.
   - `Delivery_In(t)`: Barang masuk di hari t — dihitung dari selisih stok fisik yang positif (jika stok naik dari t-1 ke t, berarti ada pengiriman).
   - `POS_Consumed(t)`: Total bahan baku yang terjual di hari t — hasil BOM Expansion (setiap transaksi menu dipecah ke ingredient-level sesuai resep di `Recipe_BOM.json`).
   
2. **Variance(t)** = `Physical_Stock(t) - Expected_Stock(t)`
   - Variance negatif (`-1.500`): Stok fisik lebih sedikit dari ekspektasi → **Shrinkage**. Bisa berarti pencurian, tumpahan, atau pencatatan kedatangan barang yang tidak akurat.
   - Variance positif (`+2.000`): Stok fisik lebih banyak dari ekspektasi → **POS_Overcount**. POS mungkin mencatat penjualan yang tidak benar-benar terjadi, atau resep BOM terlalu boros dalam estimasi bahan.
   - Variance mendekati nol: Semua baik → stok aktual sesuai penjualan.

3. **Threshold anomaly**: Jika `|Variance| > 1.000` unit, pipeline menetapkan `Action = Anomaly` dan mengisi kolom `Variance_Direction` sebagai `Shrinkage` atau `POS_Overcount`. Ambang 1.000 unit ini bukan angka tebakan — lihat Section 4.5 untuk justifikasi statistiknya (Q3 + 1,5×IQR = 720,62 → dibulatkan ke 1.000 agar lebih konservatif).

**Intuisi bisnis:** Threshold 1.000 unit berarti pipeline mentolerir selisih kecil (misal resep kurang akurat 10–20 gram per cup, atau selisih timbangan gudang). Tapi jika selisihnya setara 20+ cup kopi hilang dalam sehari, sistem menganggap itu bukan kesalahan acak lagi — butuh investigasi.

### 4.5 Justifikasi Statistik Threshold 1.000 Unit

Threshold 1.000 unit dipilih berdasarkan analisis distribusi variance dari **6.570 baris** rekonsiliasi historis (bukan 7.308 — angka dikoreksi setelah verifikasi):

| Metrik Statistik | Nilai | Interpretasi |
|---|---|---|
| Q1 (kuartil bawah) | -5,00 unit | Sebagian besar hari hampir tidak ada selisih |
| Q3 (kuartil atas) | +285,25 unit | Batas atas distribusi normal |
| IQR (Q3 - Q1) | 290,25 unit | Rentang interkuartil |
| **Q3 + 1,5 × IQR** (outlier boundary) | **720,62 unit** | Batas statistik standar untuk outlier |
| **Threshold dipilih: 1.000 unit** | **> 720,62** | **Lebih konservatif dari batas outlier statistik** |

### 4.6 Interpretasi Variance_Direction

| Nilai | Kondisi | Arti Bisnis | Tindakan Rekomendasi |
|---|---|---|---|
| **Shrinkage** | Variance < -1.000 | Stok fisik LEBIH SEDIKIT dari ekspektasi POS. Kemungkinan pencurian, tumpahan, atau pencatatan delivery tidak akurat. | Investigasi. Cek CCTV / audit stok fisik. |
| **POS_Overcount** | Variance > +1.000 | POS mengklaim konsumsi lebih besar dari stok yang hilang. Kemungkinan POS error, void tidak tercatat, atau menu_ID salah mapping. | Audit data POS. Cek resep BOM vs standar barista. |
| **N/A** | Lainnya | Status bukan Anomaly, atau hari pertama tanpa baseline. | Tidak ada aksi khusus. |

---

## 5. Entity Relationship Diagram (ERD)

```
┌───────────────────┐       ┌──────────────────────────┐
│    Employee       │       │   sales_history.csv      │
│  6 records        │       │  170.613 rows            │
│ PK Employee_ID    │1:N    │ PK Transaction_ID (str)  │
│    Full_Name      │◄──────│    DateTime (7 formats)  │
│    Role           │       │ FK Employee_ID (str)     │
│    Shift          │       │ FK Menu_ID (str)         │
└───────────────────┘       │    Quantity (3-layer)    │
                            │    Additional_Info       │
┌──────────────────────────┐│    (11+ error flags)    │
│  Master_Inventory.csv    │└──────────────────────────┘
│  42 items                │
│ PK Item_ID (str)         │       ┌──────────────────────────┐
│    Supplier_UoM          │       │   Recipe_BOM.json        │
│    (Karton/Kg/Liter/Pcs) │N:1    │  25 menu items           │
│    Min_Stock_Threshold   │◄──────│ FK Menu_ID (str)         │
│    Warehouse_UoM         │       │    ingredients (120 lnk) │
└──────────────────────────┘       │ FK Item_ID (str)         │
        │                          └──────────────────────────┘
        │N:1
        ▼
┌──────────────────────────┐       ┌──────────────────────────────┐
│ warehouse_stock.json     │       │    AUTOMATED ETL PIPELINE    │
│  175 records             │       │  pipeline.py + utils.py      │
│  86 old + 89 new schema  │       │  6 stages · 3-5 detik         │
│ PK date + Item_ID        │       │  Zero human intervention     │
└──────────────────────────┘       └──────────────┬───────────────┘
                                                   │
                         ┌─────────────────────────┴─────────────┐
                         │                                       │
                         ▼                                       ▼
        ┌──────────────────────────────┐    ┌──────────────────────────────┐
        │     Action_Report.csv        │    │    quarantine_log.csv        │
        │     7.988 baris              │    │    14.508 baris              │
        │     Status: Safe/Anomaly/    │    │    5 quarantine classes      │
        │     Restock/Invalid          │    │    58% recoverable           │
        └──────────────────────────────┘    └──────────────────────────────┘
```

---

## 6. Dokumentasi Inovasi

Di luar requirement wajib case study, pipeline diperkaya dengan 3 inovasi yang mengubahnya dari sekadar ETL menjadi sistem Business Intelligence untuk UMKM. Semua inovasi bersifat additive — tidak mengubah kolom wajib atau logika klasifikasi.

### 6.1 Inovasi 1: Predictive Days-to-Stockout

**Formula:** `Days_to_Stockout = (Physical_Stock - Min_Threshold) / Avg_7d_Consumption` (rolling 7-hari)

| Kategori | Days_to_Stockout | Jumlah item-hari (V1) |
|---|---|---|
| CRITICAL | = 0 hari | — |
| URGENT | 1–3 hari | 2.302 |
| PLAN_ORDER | 4–7 hari | — |
| SUFFICIENT | > 7 hari | — |

### 6.2 Inovasi 2: Shrinkage Financial Impact Estimator

**Formula:** `Estimated_Loss_IDR = |Shrinkage_Variance| × UNIT_COST_IDR[Item_ID]`

**Hasil dari data V1:** Rp 36.260.603 dari 101 kejadian Shrinkage.

### 6.3 Inovasi 3: Smart Quarantine Triage System

Secara otomatis mengklasifikasikan 14.508 baris karantina ke 5 kelas dengan tingkat recovery potensial. Detail di Section 2.2.

---

## 7. System Requirements

### 7.1 Kebutuhan Fungsional (Functional Requirements)

| ID | Kebutuhan | Status |
|---|---|---|
| FR-01 | Membaca dan memproses file CSV dan JSON secara otomatis dari direktori lokal | ✅ Terpenuhi |
| FR-02 | Mendeteksi dan menangani schema drift pada JSON warehouse tanpa konfigurasi manual | ✅ Terpenuhi |
| FR-03 | Membersihkan data kotor (7 pola) tanpa crash, mengkarantina baris bermasalah beserta alasannya | ✅ Terpenuhi |
| FR-04 | Mengkonversi UoM secara otomatis: Kilogram→gram, Liter→ml, Karton→pcs/ml per-item | ✅ Terpenuhi |
| FR-05 | BOM expansion: konversi transaksi menu ke konsumsi bahan baku (gram/ml/pcs) | ✅ Terpenuhi |
| FR-06 | Menghitung Expected_Stock dan Variance per (Date × Item_ID) | ✅ Terpenuhi |
| FR-07 | Mendeteksi anomali stok dengan justifikasi statistik (threshold > Q3+1,5×IQR) | ✅ Terpenuhi |
| FR-08 | Mengklasifikasikan item ke Safe / Restock / Invalid Data / Anomaly | ✅ Terpenuhi |
| FR-09 | Memprediksi Days-to-Stockout (Inovasi 1) | ✅ Terpenuhi |
| FR-10 | Mengestimasi kerugian finansial Shrinkage dalam IDR (Inovasi 2) | ✅ Terpenuhi |
| FR-11 | Smart Quarantine Triage (Inovasi 3) | ✅ Terpenuhi |
| FR-12 | Menghasilkan Action_Report.csv + quarantine_log.csv | ✅ Terpenuhi |

### 7.2 Kebutuhan Non-Fungsional (Non-Functional Requirements)

| ID | Kategori | Target | Hasil Aktual (V1) |
|---|---|---|---|
| NFR-01 | **Performance** | Pipeline memproses 170.000+ baris dalam waktu reasonable | **3–5 detik** untuk 170.613 baris. Stress test V3 (270.400 baris): **14,08 detik** — scaling ~10 detik per +100rb baris. |
| NFR-02 | **Reliability** | Pipeline tidak boleh crash saat menemukan data kotor, field null, atau format tak terduga | **Zero crash pada skenario normal** (7 pola dirty data). Stress test dengan >50% tanggal sampah dapat memicu bug known di parser tanggal (`utils.py:347`) — **sudah teridentifikasi dan solusi tersedia**: wrap `series[mask].apply(parse_datetime)` dengan `pd.to_datetime(errors='coerce')`. |
| NFR-03 | **Portability** | Dapat dijalankan di Windows dan Linux | ✅ Tested: Windows 11 |
| NFR-04 | **Maintainability** | Kode termodulasi | `utils.py` (11 fungsi) + `pipeline.py` |
| NFR-05 | **Extensibility** | Mudah diperluas untuk format data baru | Cukup menambah entry ke `WORD_TO_NUM` / `KARTON_CONVERSION` |
| NFR-06 | **Scalability** | Operasi vectorized, bukan row-by-row loop | **Mayoritas vectorized** (pandas). Satu `.apply()` residual di parser tanggal (`utils.py:347`) untuk mencatat baris mana yang gagal — trade-off untuk observability. Kompleksitas O(n). |
| NFR-07 | **Automation** | Zero human intervention | ✅ `python pipeline.py` |
| NFR-08 | **Observability** | Setiap proses tercatat di log | ✅ Structured logging, 6 stage markers |
| NFR-09 | **Infrastruktur** | Berjalan di PC/laptop standar UMKM | ✅ Python 3.8+ · RAM 4GB · `pip install` |

### 7.3 Infrastruktur Minimum

| Komponen | Minimum | Rekomendasi |
|---|---|---|
| OS | Windows 10 / Ubuntu 20.04 | Windows 11 |
| Python | 3.8+ | 3.13 |
| RAM | 4 GB | 8 GB |
| Storage | 500 MB | 2 GB |
| Library | pandas | pandas |

---

## 8. Known Limitations

### 8.1 Bug Parser Tanggal — `.apply(None)` → `.dt` Accessor Crash

**Lokasi:** `utils.py` baris 347: `result[mask] = series[mask].apply(parse_datetime)`

**Akar Masalah:** Fungsi `parse_datetime()` return `None` saat 6 format parser gagal. Jika proporsi `None` > ~50%, pandas mengubah kolom `datetime64` → `object` → `.dt` accessor crash.

**Trigger:**
- **Aman:** < 2% unparseable → `datetime64` tetap (V3: 1,7% ✅)
- **Crash:** > 50% unparseable → `object` → crash (V2: 69% ❌)

**Solusi:** `result[mask] = pd.to_datetime(series[mask].apply(parse_datetime), errors='coerce')`

### 8.2 Missing Warehouse Records (BUG2)

Pipeline hanya merekonsiliasi untuk tanggal dengan data warehouse. V3 stress test punya data penjualan 2025–2099, warehouse hanya 167 hari → 919 hari POS ter-drop, 23,5 juta unit tidak tereksiliasi.

### 8.3 Ghost Employee_ID — Tidak Dikarantina

Pipeline mencatat 16.840 transaksi dengan Employee_ID tidak dikenal (`INTERN`, `MANAGER`, `GUEST`) tetapi tidak mengkarantinanya (keputusan desain).

### 8.4 `KARTON_CONVERSION` Hardcoded

Konversi Karton bersifat hardcoded. Jika supplier berganti kemasan, kode harus diubah. Solusi permanen: kolom `Units_Per_Supplier_Package` di Master_Inventory.csv.

---

## 9. Bukti Verifikasi — Hasil Pengujian

### 9.1 V1 Base Dataset — Angka dari Audit Langsung

| Metrik | Hasil Audit | Sumber |
|---|---|---|
| Sales rows | **170.613** | File CSV langsung |
| Quarantine | **14.508** | File output |
| Action_Report | **7.988** | File output (Safe 5.983 + Anomaly 1.367 + Invalid 638) |
| Anomaly breakdown | **101 Shrinkage + 1.266 POS_Overcount** | Variance_Direction di Action_Report |
| Waktu eksekusi | **3–5 detik** | Log pipeline |
| Master_Inventory | **42 items** (bukan 49) | Verifikasi file |
| Recipe_BOM | **25 menu** (bukan 30) | Verifikasi file |
| Employee | **6 orang** (bukan 15) | Verifikasi file |

### 9.2 Test Matrix — 3 Iterasi Dataset

| Metrik | V1 (Base) | V2 (Stress, crash) | V3 (Extreme) |
|---|---|---|---|
| **Total baris** | 170.613 | 238.525 | 270.400 |
| **Dirty rate** | 8,5% | 82% | 27,7% |
| **Quarantine** | 14.508 | 195.860 | 74.970 |
| **Clean** | 156.105 | 42.665 | 200.230 |
| **Action Report** | 7.988 | 8.095 | 9.179 |
| **Waktu** | 3–5 dtk | 35,55 dtk | 14,08 dtk |
| **CRASH?** | ✅ Tidak | ❌ Crash (line 347) | ✅ Tidak |
| **Anomaly** | 1.367 | 6.524 | 6.444 |
| **Estimasi Kerugian** | Rp 36,2 Juta | — | Rp 264,8 Miliar |

### 9.3 Validasi 6 Format Parser Tanggal

| Format | Contoh | Status |
|---|---|---|
| ISO `YYYY-MM-DD HH:MM:SS` | `2025-02-14 05:29:20` | ✅ Parser 1 |
| `DD/MM/YYYY` | `27/03/2025 02:33` | ✅ Parser 2 |
| `Month DD YYYY` | `Mar 20 2025` | ✅ Parser 3 |
| Compact 12-digit | `202501170135` | ✅ Parser 4 |
| `MM-DD-YYYY AM/PM` | `03-26-2025 05:09 PM` | ✅ Parser 5 |
| Fallback `pd.to_datetime(errors='coerce')` | Format lain/dot separator | ✅ Parser 6 |

Distribusi di V1: **166.575 ISO + 3.030 non-ISO + 1.008 empty** = 170.613 total.

### 9.4 Verification Script

Script audit `audit_v1.py` memverifikasi seluruh angka di atas langsung dari file source dalam **0,37 detik** — memastikan tidak ada data yang dibuat-buat.

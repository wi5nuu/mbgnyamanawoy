# Laporan Analisis & Desain Sistem Data Automation (Kopikita Roastery)
## Dokumen Teknis Arsitektur ETL Pipeline & Ketahanan Stress Testing (Produksi)

---

## 📌 1. Identifikasi Permasalahan Dataset Saat Ini (Current Data Pitfalls)

Berdasarkan investigasi mendalam terhadap data mentah Kopikita Roastery, ditemukan beberapa kategori masalah kualitas data (*dirty data*) dan ketidaksesuaian struktur (*schema drift*):

### A. Data Quality & Inkonsistensi Kuantitas (Sales History)
*   **Representasi Teks Angka**: Kuantitas penjualan ditulis dalam kata string (misal: `"two"`, `"dua"`, `"uno"`).
*   **Desimal Tidak Standar**: Penggunaan koma desimal gaya Eropa (contoh: `"2,0"`), yang jika di-parse langsung oleh pustaka standar Python akan dibaca sebagai string, bukan float.
*   **Trailing Units**: Penulisan angka dicampur dengan satuan fisik (contoh: `"1 pcs"`, `"2.0 cups"`).
*   **Kuantitas Invalid**: Adanya nilai kuantitas negatif (seperti `"-3"`) atau bernilai nol (`"0"`), yang tidak valid secara operasional kasir.

### B. Masalah Format Penanggalan (Date Inconsistency)
*   **Format Campuran**: Tanggal transaksi ditulis dalam berbagai format penulisan waktu (seperti `YYYY-MM-DD`, `DD/MM/YYYY`, `Month DD YYYY`, dan format waktu 12 jam dengan indikator PM/AM).
*   **Missing/Invalid Dates**: Kolom tanggal kosong (*null*) atau berisi format tidak dikenal yang dapat memicu kegagalan parse (*NaN/NaT*).

### C. Kerusakan Struktur Data & Schema Drift (Warehouse Stock)
*   **Perubahan Nama Kunci JSON (Kritis)**: Pada periode kuartal kedua (Q2), kunci JSON untuk stok tersisa berubah dari `stock_remaining` menjadi `sisa_stok_akhir`. Tanpa mitigasi, hal ini menyebabkan hilangnya 50% data stok gudang.
*   **Casing & Whitespace**: ID bahan baku (`Item_ID`) dan ID menu (`Menu_ID`) memiliki spasi acak dan casing huruf kecil/besar yang tidak konsisten.

### D. Relasi & Integritas Referensial
*   **Menu Tidak Terdaftar**: Terdapat transaksi penjualan dengan `Menu_ID` yang tidak terdaftar di resep BOM (seperti menu `TEST`, `MENU-000`, `MENU-999`, atau `PROMO-01`).
*   **UoM Mismatch**: Perbedaan satuan yang sangat parah di mana kasir mencatat dalam `cup/porsi`, gudang mencatat dalam `gram/ml/pcs`, dan pembelian mencatat dalam satuan besar supplier seperti `kg/liter/galon/karton`.

---

## 📌 2. Analisis Kebutuhan Sistem (System Requirements)

Berdasarkan dokumen acuan studi kasus, sistem diwajibkan memiliki kemampuan terintegrasi berikut:

1.  **Resilient Data Ingestion**: Membaca berkas masukan CSV dan JSON tanpa mengalami kegagalan sistem (*no crash*). Baris data yang tidak dapat dipulihkan secara logis harus diisolasi ke karantina dan dilabeli sebagai status `"Invalid Data"`.
2.  **Algorithmic Efficiency & BOM Unpacking**: Mengonversi kuantitas menu terjual menjadi kebutuhan bahan baku mentah dasar menggunakan tabel resep (BOM) per hari secara cepat.
3.  **Stock Reconciliation**: Menghitung selisih (Delta/Variance) harian per bahan baku menggunakan formula:
    $$\Delta = (\text{Stok Akhir}_{d-1} + \text{Barang Masuk}_d - \text{Stok Akhir}_d) - \text{Pemakaian Teoritis}_d$$
4.  **Statistical Anomaly Detection**: Mampu membedakan penyusutan wajar operasional dengan kehilangan barang akibat pencurian atau kecurangan input secara statistik menggunakan pendekatan probabilistik (aturan 3-Sigma) dan batas absolut $>1000$ unit.
5.  **Zero Human Intervention**: Seluruh alur data berjalan otomatis dalam satu siklus perintah `python main.py` hingga menghasilkan laporan akhir `Action_Report.csv`.

---

## 📌 3. Skema Data & Arsitektur Pemrosesan (Data Architecture)

### A. Skema Relasional Tabel (Database/Tabel ERD)

```
       Master_Inventory
       ┌───────────────┐
       │ Item_ID (PK)  │◄──────────────┐
       │ Item_Name     │               │
       │ Supplier_UoM  │               │
       │ Min_Threshold │               │
       └───────────────┘               │
               ▲                       │
               │                       │
               │ (1:N)                 │ (1:N)
       Recipe_BOM                      │
       ┌───────────────┐               │
       │ Menu_ID (PK)  ├─┐             │
       │ Item_Name     │ │             │
       │ Item_ID (FK)  │ │ (1:N)       │
       │ qty_used      │ │             │
       └───────────────┘ │             │
                         ▼             │
                  Sales_History        │
                  ┌──────────────────┐ │
                  │ Transaction_ID   │ │
                  │ DateTime         │ │
                  │ Menu_ID (FK)     │─┘
                  │ Quantity         │
                  └──────────────────┘
```

### B. Pipeline Pemrosesan Data (ETL Alur Data)

```
[sales_history.csv] (POS) 
       │ 
       ▼
[Recipe_BOM.json] (BOM) ────────► [BOM Unpacking] ──► (Pemakaian Teoritis Harian)
                                                            │
                                                            ▼
[warehouse_stock.json] (Gudang) ─► [Reconciliation] ◄───────┘
                                       │ (Delta = Aktual Keluar - Teoritis Kasir)
                                       ▼
[Master_Inventory.csv] (Master) ─► [Anomaly & Restock Logic]
                                       │
                                       ▼
                               [Action_Report.csv] (Output Akhir)
```

---

## 📌 4. Strategi Penanganan Kondisi Produksi & Stress Testing

Untuk menghadapi pengujian beban (*stress testing*) dengan volume data yang jauh lebih besar (250.000+ baris) dan lebih kotor, sistem menerapkan rancangan mitigasi tingkat produksi:

| Potensi Kegagalan Produksi | Dampak pada Sistem | Desain Solusi & Mitigasi Teknis |
| :--- | :--- | :--- |
| **Schema Drift Nama Kolom** | `KeyError` saat membaca kolom CSV akibat perubahan nama/casing. | Helper `standardize_columns` secara dinamis mencocokkan nama kolom berdasarkan alias case-insensitive sebelum pemrosesan. |
| **Schema Drift JSON Key** | Kunci JSON stok gudang atau resep berubah casing atau nama field. | Menggunakan helper `get_case_insensitive_key` untuk mencari kecocokan kunci secara dinamis dan toleran. |
| **Data Sangat Besar (Timeout/OOM)** | Sistem hang atau kehabisan memori RAM karena memproses jutaan baris loop. | Menggunakan pembacaan bertahap (**Chunksize 50.000 baris**) dipadukan dengan **Vectorized Pandas Operations** (pemrosesan paralel tingkat C-Engine tanpa *looping* lambat). |
| **Outlier & Variansi Nol** | Deviasi historis delta bernilai nol ($\sigma = 0$) memicu false positive anomali pada deviasi kecil. | Menerapkan batas bawah standar deviasi minimum (*Standard Deviation Floor Limit*) sebesar `10.0` unit pada aturan 3-Sigma. |
| **Data Historis Minim** | Pembagian dengan nol (*Division-by-zero*) saat menghitung standar deviasi pada data sedikit. | *Count Safeguard*: Jika data historis $< 3$, standar deviasi diset secara otomatis ke nilai aman default (`500.0`). |
| **Encoding & Delimiter Berbeda** | Kerusakan karakter Unicode (Excel/PowerShell) atau kegagalan split kolom. | Pipeline menyimpan laporan menggunakan encoding universal `utf-8-sig` (agar kompatibel langsung saat dibuka di MS Excel) dan menggunakan pendeteksi delimiter otomatis. |
| **File Masukan Hilang / Kosong** | Kegagalan sistem tanpa melahirkan informasi penyebab. | Memeriksa eksistensi berkas menggunakan `os.path.exists` dan `os.path.getsize` di awal. Jika berkas kritis hilang/kosong, program dihentikan secara aman dengan log pesan kesalahan operasional yang informatif. |

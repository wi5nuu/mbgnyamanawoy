# Laporan Analisis & Desain Sistem Data Automation (Kopikita Roastery)
## Dokumen Teknis Arsitektur ETL Pipeline & Ketahanan Stress Testing (Produksi)

---

## 📌 1. Analisis Detail 5 Berkas Dataset & Keterkaitan Dokumen Acuan

Sistem data automation ini membaca dan mengintegrasikan 5 berkas utama. Di bawah ini adalah rincian permasalahan kotor pada masing-masing berkas, dampaknya pada pipeline, dan bagaimana hal tersebut berkaitan erat dengan persyaratan di dalam **Case Study** (CS) dan **Rancangan Teknis** (RT):

### 1. `sales_history.csv` (Data Transaksi Kasir / POS)
*   **Masalah Data Kotor**:
    *   *Kuantitas Kotor*: Kuantitas ditulis dengan string kata angka (seperti `"two"`, `"dua"`), koma desimal Eropa (`"2,0"`), penambahan satuan unit (`"1 pcs"`, `"2.0 cups"`), nilai negatif, atau kosong (*null*).
    *   *Format Tanggal Beragam*: Penulisan tanggal tidak konsisten (contoh: gabungan format `DD/MM/YYYY` dan format 12 jam dengan PM/AM).
    *   *ID Tidak Valid*: Adanya transaksi dengan `Menu_ID` kosong atau tidak dikenal di katalog BOM (seperti `"TEST"`, `"MENU-999"`).
*   **Keterkaitan dengan PDF Acuan**:
    *   *CS Poin 1 (Data Mentah Berantakan)* & *RT Bab 2 (Pembersihan Data)*: Mensyaratkan pembersihan otomatis terhadap kesalahan ketik (*typo*), format tanggal tidak seragam, dan isolasi baris transaksi tidak sah ke status `Invalid Data` tanpa menghentikan eksekusi pipeline.

### 2. `warehouse_stock.json` (Data Stok Fisik Gudang)
*   **Masalah Data Kotor**:
    *   *Schema Drift Kritis*: Struktur kunci JSON berubah di tengah periode (kuartal 2), di mana key `stock_remaining` digantikan dengan `sisa_stok_akhir`.
    *   *Casing & Whitespace*: ID barang (`Item_ID`) dan satuan (`UoM`) ditulis dengan spasi acak atau casing tidak seragam.
*   **Keterkaitan dengan PDF Acuan**:
    *   *CS Poin 1 (Schema Drift)* & *RT Bab 1 (Sistem Gudang)*: Menuntut skrip parsing yang memiliki ketahanan terhadap perubahan nama field di tengah periode guna menghindari hilangnya 50% data stok gudang.

### 3. `Master_Inventory.csv` (Data Master Pembelian / Purchasing)
*   **Masalah Data Kotor**:
    *   *Perbedaan Satuan*: Satuan pembelian berupa `"Karton"` atau `"Kg"` yang berbeda dengan satuan pemakaian di gudang (`"pcs"` atau `"gram"`).
    *   *Threshold di Satuan Supplier*: Ambang batas minimum stok (`Min_Stock_Threshold`) ditulis dalam satuan supplier besar.
*   **Keterkaitan dengan PDF Acuan**:
    *   *RT Bab 3 (Konversi Satuan)*: Mewajibkan konversi satuan besar supplier ke satuan metrik terkecil gudang (misalnya: kg $\rightarrow$ gram dengan faktor 1000, galon $\rightarrow$ ml dengan faktor 3785, karton $\rightarrow$ pcs dengan faktor 1000) agar nilai pembandingan stok berada dalam unit yang setara.

### 4. `Recipe_BOM.json` (Data Resep / Bill of Materials)
*   **Masalah Data Kotor**:
    *   *Struktur JSON Dinamis*: Root list resep dapat dibungkus dalam key berbeda (`menu_items`, `menus`, dll.) atau langsung berupa array datar.
    *   *Casing ID*: `Menu_ID` dan `Item_ID` bahan baku tidak konsisten casing-nya dengan file sales/inventory.
*   **Keterkaitan dengan PDF Acuan**:
    *   *CS Poin 2 (Konversi Resep)* & *RT Bab 3 (BOM Unpacking)*: Merupakan kunci algoritma untuk mengurai produk terjual (porsi) ke gram/ml bahan baku mentah sebelum direkonsiliasi dengan stok fisik gudang.

### 5. `Employee.json` (Data Karyawan Terdaftar)
*   **Masalah Data Kotor**:
    *   *Resiko File Hilang/Kosong*: File opsional ini berpotensi tidak disediakan atau kosong pada lingkungan stress testing baru.
    *   *Casing ID*: Penulisan `Employee_ID` tidak konsisten.
*   **Keterkaitan dengan PDF Acuan**:
    *   *RT Bab 1 (Error Handling)*: Membantu memvalidasi integritas identitas pencatat (`recorded_by`) di gudang atau kasir. Mitigasi harus memastikan hilangnya berkas ini tidak menghentikan jalannya pipeline secara keseluruhan (safe fallback).

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
| **File Masukan Hilang / Kosong** | Kegagalan sistem tanpa melahirkan informasi penyebab. | Memeriksa eksistensi berkas menggunakan `os.path.exists` and `os.path.getsize`. Jika berkas kritis hilang/kosong, program dihentikan secara aman dengan log pesan kesalahan operasional yang informatif. |

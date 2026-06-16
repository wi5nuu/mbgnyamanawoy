# Ringkasan Progres & Template Submisi Checkpoint (Kopikita Roastery)
## Salin-Tempel Formulir Pengumpulan Checkpoint 1, 2, dan 3

Dokumen ini berisi draf siap pakai untuk mempermudah Anda melakukan pengisian formulir progress pengumpulan di portal penilaian juri.

---

## 🟢 1. Submisi Checkpoint 1: Ingestion & Cleaning

### 🔘 Pilihan Checkpoint (Select Checkpoint)
`Checkpoint 1 — Ingestion & Cleaning`

### 📝 Ringkasan Kemajuan (Progress Summary)
Kami telah menyelesaikan pembangunan modul Penarikan Data (Ingestion) dan Pembersihan Data (Cleansing) secara ter-vektor (vectorized). Pipeline berhasil membaca berkas Master_Inventory.csv (42 item), Recipe_BOM.json (25 menu), Employee.json (6 karyawan), warehouse_stock.json (7.350 baris), dan sales_history.csv (170.613 baris) secara dinamis. Program secara otomatis menyaring baris penjualan valid (163.412 baris) dan mengisolasi baris kotor (7.201 baris) ke dalam karantina data invalid tanpa menghentikan jalannya pipeline.

### ⚠️ Masalah yang Ditemukan & Solusi (Problem)
1. Masalah: Schema Drift di mana kolom gudang 'stock_remaining' berubah nama menjadi 'sisa_stok_akhir' pada kuartal kedua (Q2).
   Solusi: Mengembangkan helper 'get_case_insensitive_key' yang melakukan pencarian dinamis alias kunci JSON sehingga program tetap berjalan normal.
2. Masalah: Kolom penulisan pada CSV kasir rentan mengalami pergeseran posisi atau perubahan nama casing (misal DateTime ditulis date_time).
   Solusi: Mengembangkan fungsi 'standardize_columns' ter-vektor untuk memetakan alias nama kolom secara case-insensitive sebelum pemrosesan.
3. Masalah: Kuantitas kotor berupa string teks ("two"), desimal koma ("2,0"), trailing unit ("1 pcs"), atau nilai negatif.
   Solusi: Mengimplementasikan pembersihan regex ter-vektor 'Quantity_Cleaned' yang membersihkan noise string secara paralel dalam waktu < 1 detik.

---

## 🟡 2. Submisi Checkpoint 2: BOM & Stock Reconciliation

### 🔘 Pilihan Checkpoint (Select Checkpoint)
`Checkpoint 2 — BOM Calculation & Stock Reconciliation`

### 📝 Ringkasan Kemajuan (Progress Summary)
Kami telah berhasil membangun modul perhitungan BOM Unpacking dan Rekonsiliasi Stok Gudang. Transaksi POS kasir berhasil diurai secara harian menggunakan resep Recipe_BOM.json menjadi pemakaian teoritis bahan baku. Sistem juga menghitung penurunan stok gudang aktual harian lewat formula (Stok Hari Sebelumnya + Barang Masuk - Stok Hari Ini) lalu membandingkannya dengan pemakaian teoritis kasir untuk menghasilkan nilai selisih harian (Delta/Variance) per item.

### ⚠️ Masalah yang Ditemukan & Solusi (Problem)
1. Masalah: Kegagalan perhitungan selisih pada hari pertama perekaman data karena tidak adanya data stok hari sebelumnya (prev_stock bernilai NaN).
   Solusi: Menambahkan logika deteksi hari pertama per item ('is_first_day') untuk melewati perhitungan delta hari pertama secara aman guna menghindari false positive anomali.
2. Masalah: Ketidaksesuaian Satuan Pengukuran (UoM Mismatch) antara pembelian (skala besar) dan pemakaian gudang (skala kecil).
   Solusi: Menerapkan kamus konversi 'UOM_TO_BASE' (contoh: kg dikali 1000 ke gram, galon dikali 3785 ke ml) untuk menyamakan unit pengukuran secara otomatis.

---

## 🔴 3. Submisi Checkpoint 3: Anomaly Detection & Output

### 🔘 Pilihan Checkpoint (Select Checkpoint)
`Checkpoint 3 — Anomaly Detection & Action_Report.csv`

### 📝 Ringkasan Kemajuan (Progress Summary)
Kami telah mengimplementasikan logika deteksi anomali statistik berbasis aturan 3-Sigma (Mean + 3*Std) dan ambang batas absolut (>1.000 unit), serta logika pengecekan restock harian. Laporan hasil akhir 'Action_Report.csv' (8.169 baris) telah berhasil diekspor secara otomatis dengan urutan prioritas status yang konsisten: Invalid Data > Anomaly > Restock > Safe.

### ⚠️ Masalah yang Ditemukan & Solusi (Problem)
1. Masalah: Variansi nol (Std Dev = 0) pada item stabil memicu pembagian nol atau alarm anomali palsu akibat fluktuasi kecil di masa depan.
   Solusi: Menambahkan 'Standard Deviation Floor Limit' (minimum 10.0 unit) dan 'Count Safeguard' (default 500.0 std jika data < 3 hari) untuk menstabilkan perhitungan 3-Sigma.
2. Masalah: Tabrakan status ganda untuk satu item di hari yang sama (misal stok tipis sekaligus memiliki selisih anomali).
   Solusi: Merancang penentuan prioritas status (Invalid Data > Anomaly > Restock > Safe) melalui mapping prioritas integer dan deduplikasi terurut di akhir pemrosesan.

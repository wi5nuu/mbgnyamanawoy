# Panduan Rekomendasi Arsitektur Data Enterprise (Stress Testing 3Jt+ Data)
## Strategi Optimasi Data Engineering & Skalabilitas Tingkat Produksi

Dokumen ini memuat analisis arsitektur tingkat lanjut (*expert-level*) sebagai bahan materi tanya jawab (Q&A) dengan dewan juri untuk menunjukkan bahwa tim Anda memahami cara menangani data skala besar (*Big Data*) di lingkungan produksi sesungguhnya.

---

## 📌 1. Mengapa Single-Script (`main.py`) Digunakan di Kompetisi Ini?

Untuk kebutuhan kompetisi hackathon ini, mempertahankan satu berkas eksekusi [main.py](file:///d:/hackathon-techprint/main.py) adalah **keputusan taktis yang sangat tepat** karena:
1.  **Kemudahan Penilaian Juri**: Juri dapat langsung memverifikasi ke-4 blok anotasi wajib (*Ingestion, Cleansing, Calculation, Anomaly*) tanpa harus membuka belasan file terpisah.
2.  **Zero Human Intervention**: Membantu juri menjalankan seluruh pipeline hanya dengan satu baris perintah: `python main.py`.

Namun, jika juri bertanya: *"Bagaimana jika sistem ini diimplementasikan di industri nyata dengan data 3.000.000+ baris harian?"*, gunakan penjelasan arsitektur enterprise di bawah ini.

---

## 📌 2. Transisi Menuju Arsitektur Enterprise Modular

Di lingkungan produksi nyata, kode tunggal akan dipecah menjadi modul berbasis OOP (Object-Oriented Programming) dengan struktur direktori sebagai berikut:

```text
kopikita_pipeline/
│
├── config/
│   ├── __init__.py
│   ├── settings.py          # Konfigurasi UoM, Sigma, & Batas Threshold
│   └── database.py          # Koneksi ke Database / Data Lake
│
├── core/
│   ├── __init__.py
│   ├── ingestion.py         # Modul pembaca berkas kotor & schema drift
│   ├── cleaning.py          # Pembersihan vectorized string, tanggal, & qty
│   ├── calculations.py      # Pemrosesan resep BOM & rekonsiliasi stok
│   └── anomaly_detector.py  # Evaluasi statistik 3-sigma & floor deviasi
│
├── utils/
│   ├── __init__.py
│   └── logger.py            # Pencatat log kesalahan (Warning/Error) ke berkas log
│
└── run_pipeline.py          # Berkas entrypoint utama (Orchestrator)
```

---

## 📌 3. Strategi Menghadapi Volume Data Ekstrem (> 3 Juta Baris)

Jika komite juri meningkatkan volume data secara ekstrem, berikut adalah 3 taktik *Data Engineering* tingkat lanjut yang dapat kita tawarkan secara verbal saat sesi tanya jawab:

### A. Polars Engine (Menggantikan Pandas)
*   **Kenapa?**: Pandas bekerja secara *single-threaded* dan memuat seluruh data ke dalam memori RAM (dapat memicu *OutOfMemory* pada data besar).
*   **Solusi**: Menggunakan **Polars** yang ditulis dalam bahasa Rust. Polars mengeksekusi operasi secara *multi-threaded* (memanfaatkan semua core CPU) dan menggunakan *lazy evaluation* untuk mengoptimalkan query sebelum dijalankan. Kecepatannya bisa 5x s/d 10x lebih cepat daripada Pandas.

### B. Streaming Database (SQLite / PostgreSQL) untuk Memori Konstan
*   **Kenapa?**: Melakukan pencocokan (*join*) dan agregasi 3 juta baris data sales dengan stok gudang di dalam RAM komputer lokal sangat memakan resource.
*   **Solusi**: 
    1.  Membaca file sales secara bertahap (*streaming*) dan langsung memasukkannya ke database lokal ringan (**SQLite**) menggunakan indeks pada kolom `Item_ID` dan `date`.
    2.  Proses *BOM unpacking* dan *reconciliation* dijalankan melalui *SQL Query Join*.
    3.  Taktik ini menjamin penggunaan memori RAM komputer tetap konstan dan sangat kecil (misal hanya 100 MB) meskipun data masukan membengkak hingga 100 juta baris.

### C. Downcasting Tipe Data & Categorical Parsing
*   **Kenapa?**: String di Pandas memakan memori yang sangat besar.
*   **Solusi**: Di dalam kode, kita melakukan *downcasting* tipe data:
    *   Kolom kategori seperti `Menu_ID` dan `Employee_ID` diubah menjadi tipe data `category` (mengurangi ukuran memori hingga 80%).
    *   Mengubah float64 menjadi float32 jika tidak memerlukan presisi desimal ekstrem.

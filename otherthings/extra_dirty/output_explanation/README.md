# Output Pipeline Kopikita — Penjelasan Lengkap

Kedua file ini adalah **hasil akhir** dari proses ETL (Extract, Transform, Load) yang membersihkan dan menganalisis data penjualan Kopikita.

---

## 🏆 Hasil Run Pipeline (Terbaru)

Pipeline dijalankan pada **17 Juni 2026** terhadap **V3 dataset** (270.400 baris, 74.970 karantina).

```
00:42:37  ╔══════════════════════════════════════════════════════════╗
00:42:37  ║   KOPIKITA ROASTERY — DATA AUTOMATION PIPELINE v2       ║
00:42:37  ╚══════════════════════════════════════════════════════════╝

STAGE 1 — DATA INGESTION
  [✓] sales_history.csv     → 270,400 baris | 7 kolom
  [✓] warehouse_stock.json  →     176 daily records
  [✓] Master_Inventory.csv  →      49 items
  [✓] Recipe_BOM.json       →      30 menu items
  [✓] Employee.json         →      15 karyawan

STAGE 2 — DATA CLEANSING
  → Duplikat Transaction_ID    : 11,827 baris dikarantina
  → Error flag POS (di-exclude) : 17,920 baris dikarantina
  → Null field kritis          : 17,532 baris dikarantina
  → DateTime tidak valid        : 4,559 baris dikarantina
  → Quantity negatif            : 6,828 baris dikarantina
  → Quantity tidak terparsing   : 4,840 baris dikarantina
  → Quantity zero (void/cancelled) : 11,464 baris dikarantina
  → Ghost Menu_ID (Invalid Data): 19,714 transaksi ditandai
  → Ghost Employee_ID           : 16,840 transaksi (diproses, perlu investigasi)
  ✓ Hasil cleansing: 195,430 baris valid | 74,970 dikarantina

  → Flattening 176 warehouse records (schema drift handled)...
  → 269 entri stok negatif → dikoreksi ke 0
  ✓ Warehouse flat: 6,615 baris | 167 hari | 45 item

STAGE 3 — BOM EXPANSION & DAILY AGGREGATION
  → Transaksi valid untuk BOM expansion: 175,716
  → Setelah BOM explode: 856,639 baris ingredient-level
  ✓ Daily consumption: 23,562 baris | 1086 hari | 34 item unik

STAGE 4 — STOCK RECONCILIATION
  [⚠ BUG2] 919 hari POS tanpa warehouse record → EXCLUDED
  Total konsumsi ter-drop: 23,560,488 units
  ✓ Rekonsiliasi: 6,615 total | 6,570 bisa dianalisis

STAGE 5 — ACTION STATUS CLASSIFICATION
  Distribusi:
    ├─ Anomaly        :   6,444  (Shrinkage: 2,861 | POS_Overcount: 3,583)
    ├─ Safe           :     159
    ├─ Restock        :      12
    └─ Invalid Data   :   2,564
  ✓ Action Report: 9,179 baris total

INOVASI — Business Intelligence Enhancements
  ✓ Days-to-Stockout dihitung | CRITICAL/URGENT: 1,489 item-hari
  ✓ Financial impact: 2,839 Shrinkage rows
    Total estimasi kerugian: Rp 264,835,215,086

PIPELINE SELESAI dalam 14.08 detik
```

---

## Analogi Besar: "Dapur Restoran"

Bayangkan pipeline ini seperti **proses menerima bahan makanan di dapur restoran**:

| Tahap | Analogi Dapur | File Output |
|---|---|---|
| **Ingestion** (Memuat data) | Kurir datang bawa 5 kotak bahan dari supplier berbeda | Semua file source dibaca |
| **Cleansing** (Karantina) | Koki menyisihkan bahan yang **rusak, kadaluarsa, palsu** | `quarantine_log.csv` |
| **BOM Expansion** (Ekspansi resep) | Koki membongkar setiap menu jadi bahan baku: 1 porsi Es Kopi = 10g kopi + 50ml susu + 5g gula | Data transaksi berlipat 5x |
| **Reconciliation** (Rekonsiliasi) | Koki bandingkan: "stok gula di gudang 50kg, penjualan bilang terpakai 45kg, berarti sisa 5kg. Tapi fisik di gudang cuma 2kg — ada selisih 3kg!" | Perhitungan stok vs penjualan |
| **Action Report** | Koki kasih laporan ke manajer: "Gula mau habis, kopi aman, susu ada anomali" | `Action_Report.csv` |

**Alur lengkap data:**

```
📦 270.400 transaksi mentah (sales_history.csv)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 2 — DATA CLEANSING (Penyaringan 7 lapis)     │
│                                                      │
│  1. Buang duplikat Transaction_ID                    │
│  2. Buang baris dengan ERROR flag di Additional_Info │
│  3. Buang baris dengan field kritis yang NULL        │
│  4. Parsing tanggal → buang yang tidak valid         │
│  5. Parsing quantity → buang yang negatif            │
│  6. Buang quantity yang tidak bisa diubah ke angka   │
│  7. Buang quantity nol (void/cancelled)              │
│                                                      │
└─────────────────────┬───────────────────────────────┘
        │
        ├── 74.970 baris → QUARANTINE_LOG.csv ❌
        │
        ▼
  195.430 baris valid (+ ghost Menu_ID ditandai)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 3 — BOM EXPANSION                            │
│  Setiap transaksi menu → dipecah ke bahan baku      │
│  175.716 transaksi → 856.639 baris ingredient-level │
└─────────────────────┬───────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 4 — STOCK RECONCILIATION                     │
│  Bandingkan: stok fisik (warehouse) vs pemakaian    │
│  dari POS (setelah BOM explode)                     │
└─────────────────────┬───────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 5 — CLASSIFICATION                           │
│  9.179 baris Action_Report:                         │
│  ├── Anomaly     6.444 (stok tidak cocok)           │
│  ├── Invalid     2.564 (Menu_ID ghost)              │
│  ├── Safe          159 (stok aman)                  │
│  └── Restock        12 (stok kritis)                │
└─────────────────────────────────────────────────────┘
```

---

## Ringkasan Kedua File

| File | Jumlah Baris | Isi | Fungsi |
|---|---|---|---|
| `quarantine_log.csv` | 74.970 baris | Data **kotor** yang ditolak pipeline | Mencatat **mengapa** suatu baris ditolak, untuk audit & debug |
| `Action_Report.csv` | 9.179 baris | Data **bersih** yang sudah dianalisis stoknya | Memberi **rekomendasi bisnis**: restok, aman, anomali, atau data tidak valid |

---

## Cara Baca Bersama Kedua File

Pipeline ini ibarat **satpam + manajer toko**:

1. **Satpam** (`quarantine_log`) — menyaring pengunjung yang mencurigakan: yang tidak punya KTP (NULL), yang bawa senjata (ERROR flag), yang membeli 0 barang (ZERO quantity), dsb. Mereka dicatat dan dikeluarkan.
2. **Manajer toko** (`Action_Report`) — setelah pengunjung lolos, manajer mengecek stok barang dan memberi laporan: barang A perlu di-restok, barang B aman, barang C jumlahnya aneh (Anomaly), barang D tidak dikenal sistem (Invalid Data).

**Keduanya saling melengkapi**: Karantina menjawab **"data mana yang kami tolak dan kenapa"**, Action Report menjawab **"setelah data bersih, apa yang harus kami lakukan?"**.

---

## Fakta Penting dari Run Ini

| Metrik | Nilai | Arti |
|---|---|---|
| Waktu eksekusi | **14,08 detik** | Pipeline cepat, bahkan untuk 270rb baris |
| Data karantina | **74.970 (27,7%)** | Hampir sepertiga data mentah adalah sampah |
| Ghost Menu_ID | **19.714 transaksi** | 10 Menu_ID palsu lolos karantina tapi gagal di rekonsiliasi |
| Ghost Employee_ID | **16.840 transaksi** | Karyawan palsu lolos — perlu investigasi lanjutan |
| Stok negatif di warehouse | **269 entri** | Data stok gudang juga bermasalah → dikoreksi ke 0 |
| BOM Explode | **856.639 baris** | Setiap menu kopi dipecah jadi bahan baku (kopi, susu, gula, dll) |
| POS tanpa warehouse | **919 hari, 23,5 juta unit** | BUG: pipeline tidak bisa rekonsiliasi hari tanpa data gudang |
| Estimasi kerugian | **Rp 264,8 Miliar** | Total nilai barang hilang dari 2.839 item anomali shrinkage |
| Total baris Action | **9.179** | Dari 270.400 transaksi → hanya 9.179 keputusan bisnis |

---

## Navigasi

- [Penjelasan `quarantine_log.csv` →](quarantine_log.md) — Detail lengkap data karantina
- [Penjelasan `Action_Report.csv` →](Action_Report.md) — Detail lengkap laporan aksi
- [Hubungan & statistik lengkap →](relationship.md) — Bagaimana kedua file saling terkait

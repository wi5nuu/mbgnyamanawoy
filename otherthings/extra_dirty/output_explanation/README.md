# Output Pipeline Kopikita — Penjelasan Lengkap

Kedua file ini adalah **hasil akhir** dari proses ETL (Extract, Transform, Load) yang membersihkan dan menganalisis data penjualan Kopikita.

---

## Analogi Besar: "Dapur Restoran"

Bayangkan pipeline ini seperti **proses menerima bahan makanan di dapur restoran**:

| Tahap | Analogi Dapur | File Output |
|---|---|---|
| **Quarantine** (Karantina) | Bahan makanan yang **rusak, kadaluarsa, atau mencurigakan** disisihkan ke tempat karantina sebelum masuk dapur | `quarantine_log.csv` |
| **Action Report** (Laporan Aksi) | Setelah bahan lolos karantina, koki mengecek **stok kulkas** dan memutuskan: stok aman, perlu restok, atau ada keanehan | `Action_Report.csv` |

**Alur lengkap:**

```
270.400 transaksi mentah
        │
        ▼
    ┌─────────────────────┐
    │   QUARANTINE        │──→ 74.970 transaksi dibuang (karantina)
    │   (Penyaringan)     │
    └─────────┬───────────┘
              │
              ▼
      200.230 transaksi bersih
              │
              ▼
    ┌─────────────────────┐
    │   RECONCILIATION    │──→ 9.179 baris Action_Report
    │   (Stok vs Penjualan)│
    └─────────────────────┘
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

## Navigasi

- [Penjelasan `quarantine_log.csv` →](quarantine_log.md)
- [Penjelasan `Action_Report.csv` →](Action_Report.md)
- [Hubungan & statistik lengkap →](relationship.md)

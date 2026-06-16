# Hubungan Antara `quarantine_log.csv` dan `Action_Report.csv`

---

## 1. Diagram Alur Data

```
270.400 transaksi mentah (sales_history.csv)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                   PIPELINE — TAHAP 1                        │
│                Pembersihan & Validasi                       │
│                                                             │
│   ┌──────────────────────────────────┐                      │
│   │  Apakah baris ini VALID?         │                      │
│   │  • TRX_ID tidak kosong?          │──TIDAK──┐            │
│   │  • Quantity > 0 & numerik?       │         │            │
│   │  • Format tanggal dikenal?       │         ▼            │
│   │  • Additional_Info bersih?       │    QUARANTINE        │
│   │  • Employee_ID, Menu_ID valid?   │  (74.970 baris)      │
│   └──────────────────────────────────┘         │            │
│              │YA                                │            │
│              ▼                                  │            │
│      200.230 baris BERSIH                      │            │
└─────────────────────────────────────────────────┘            │
        │                                                      │
        ▼                                                      │
┌─────────────────────────────────────────────────┐            │
│            PIPELINE — TAHAP 2                    │            │
│         Rekonsiliasi Stok                        │            │
│                                                  │            │
│   • BOM Explode: menu → bahan baku               │            │
│   • Hitung pemakaian stok dari POS               │            │
│   • Bandingkan dengan stok fisik di gudang       │            │
│   • Klasifikasi: Safe / Restock / Anomaly / Invalid│           │
│                                                  │            │
│         ▼                                        │            │
│   ACTION_REPORT.csv (9.179 baris)                │            │
└─────────────────────────────────────────────────┘            │
        │                                                      │
        ▼                                                      ▼
   KEPUTUSAN BISNIS                                    AUDIT DATA
   • Restock 12 item                                  • 16.931 null fields
   • Investigasi 6.444 anomali                        • 14.253 error flags
   • Pantau 159 item safe                              • 11.091 duplikat
   • Hapus 2.564 invalid                              • dll.
```

---

## 2. Hubungan Langsung

### a. Baris di Sales → Karantina → TIDAK muncul di Action

```
sales_history (270.400)
    ├──→ quarantine_log (74.970) ──→ ✗ Tidak diproses ke Action
    └──→ pipeline lanjut (200.230) ──→ Action_Report (9.179)
```

Baris yang masuk karantina **tidak ikut** dalam rekonsiliasi stok. Ini penting: **data kotor tidak mempengaruhi keputusan bisnis**.

### b. Status Invalid Data di Action = Ghost ID dari dataset kotor

| Di quarantine_log | Di Action_Report |
|---|---|
| Baris dengan `Menu_ID` seperti `MENU-000`, `PROMO-01`, `TEST`, dll. | Status `Invalid Data` — karena ID tersebut tidak ada di master data |

Ghost ID ini **lolos karantina** (punya TRX_ID, qty valid, tanggal valid) tapi **gagal di rekonsiliasi** karena tidak dikenal sistem. Dua lapis pengamanan.

### c. Anomaly di Action → Kualitas data tetap bersih

6.444 anomali bukan karena data kotor — ini **data bersih yang menunjukkan masalah nyata** (shrinkage, salah catat stok, dll). Perbedaan penting:

| Karantina | Anomali |
|---|---|
| Data **salah format** | Data **benar format tapi nilainya janggal** |
| Contoh: qty = `"eight"` | Contoh: stok fisik 17.653 vs ekspektasi 149.674 |
| Solusi: buang/null-kan | Solusi: investigasi lapangan |

---

## 3. Statistik Gabungan

### Distribusi 270.400 transaksi

```
                        ┌──────────────────────┐
                        │   TOTAL TRANSACTIONS  │
                        │       270.400         │
                        │       100%            │
                        └──────────┬───────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
              ▼                                         ▼
┌─────────────────────────┐             ┌─────────────────────────┐
│      QUARANTINED        │             │     PIPELINE LANJUT     │
│       74.970            │             │       200.230           │
│       27,7%             │             │       72,3%            │
│                         │             │                         │
│  Alasan terbanyak:      │             │  Hasil Action_Report:   │
│  • NULL_CRITICAL: 16.931│             │  • Anomaly:     6.444   │
│  • ERROR_FLAG:   14.253│             │  • Invalid:     2.564   │
│  • ZERO_QTY:     11.256│             │  • Safe:          159   │
│  • DUPLICATE:    11.091│             │  • Restock:        12   │
│  • NEGATIVE_QTY:  6.696│             │                         │
│  • UNPARSE_QTY:   4.756│             │  Rasio bersih: 9.179    │
│  • UNPARSE_DATE:  4.302│             │  dari 200.230 = 4,6%    │
└─────────────────────────┘             └─────────────────────────┘
```

### Persentase terhadap dataset asli

```
Dari 270.400 transaksi:
  ████████████████████████████████████████████░ 27,7% karantina
  ████████████████████████████████████████████████████████████████ 72,3% lanjut
  └→ Dari yang lanjut:
     ██████████████████████████████████████████████████████████████ 70,2% anomaly
     ██████████████████████████████████████████░░ 27,9% invalid data
     ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 1,7% safe
     ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0,1% restock
```

---

## 4. Aliran Data per Item_ID (Contoh)

Ambil contoh **Item_ID = INV-0020**:

| Tahap | Jumlah | Status |
|---|---|---|
| Muncul di `sales_history` | ~50 transaksi | 📦 Mentah |
| Karantina (qty=0, duplikat, dll) | ~8 transaksi | ❌ Masuk `quarantine_log` |
| Lolos ke rekonsiliasi | ~42 transaksi | ✅ Diproses |
| Hasil di `Action_Report` | 1 baris | `Safe` — stok aman (49.795,8 dari minimal 3.000) |

**Kesimpulan**: 42 transaksi INV-0020 diringkas jadi **1 baris** di Action_Report. Inilah kekuatan ETL — ribuan transaksi jadi satu keputusan.

---

## 5. Contoh Penggunaan Bersama

### Skenario: Manajer ingin tahu kenapa stok INV-0025 anomali

**Langkah 1**: Cek `Action_Report.csv` → filter `Item_ID=INV-0025`

```
Date,Item_ID,Action_Status,Physical_Stock,Expected_Stock,Variance,Variance_Direction,Estimated_Loss_IDR
2025-01-01,INV-0025,Anomaly,17653.5,149674.6,-132021.1,UNDER,6601055.0
```

→ Stok fisik 17.653 vs ekspektasi 149.674 — selisih **132.021 unit** = kerugian **Rp6,6 juta**.

**Langkah 2**: Cek apakah data INV-0025 banyak dikarantina?

Cari di `quarantine_log.csv` → cari `INV-0025`:
- Mungkin banyak transaksi INV-0025 dikarantina (qty negatif, error flag dll.)
- Jika iya → anomali mungkin karena **data penjualan tidak lengkap** (banyak dibuang)
- Jika tidak → anomali karena **masalah fisik** (benar-benar hilang)

**Langkah 3**: Kesimpulan

| Jika karantina INV-0025 tinggi | Jika karantina INV-0025 rendah |
|---|---|
| Anomali karena data tidak lengkap | Anomali karena barang benar-benar hilang |
| Solusi: perbaiki kualitas data entry | Solusi: investigasi gudang, cek pencurian |

---

## 6. Ringkasan Perbedaan

| Aspek | `quarantine_log.csv` | `Action_Report.csv` |
|---|---|---|
| **Fokus** | Kualitas data | Kesehatan stok |
| **Target pengguna** | Data engineer, analis data | Manajer operasional, pemilik toko |
| **Pertanyaan yang dijawab** | "Data mana yang rusak dan kenapa?" | "Apa yang harus saya lakukan?" |
| **Jumlah baris** | 74.970 | 9.179 |
| **Tindak lanjut** | Perbaiki sumber data, update validasi | Restok, investigasi anomali, pantau rutin |
| **Frekuensi** | Setiap kali ETL dijalankan | Setiap kali ETL dijalankan |
| **Nilai bisnis** | Memastikan data bersih sebelum diproses | Memberi rekomendasi aksi nyata |

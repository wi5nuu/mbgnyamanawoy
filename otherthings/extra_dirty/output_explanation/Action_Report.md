# `Action_Report.csv` — Laporan Aksi Stok

**Jumlah baris: 9.179** — hasil rekonsiliasi stok dari 195.430 transaksi valid.

---

## Bagaimana Pipeline Menghasilkan Action_Report? (Cara Kerja Sistem)

Ada 3 tahap besar **setelah karantina** sebelum Action_Report terbentuk:

```
195.430 transaksi valid (setelah karantina)
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 3 — BOM EXPANSION                                         │
│                                                                  │
│ Setiap transaksi menu → dipecah ke bahan baku (resep)           │
│ Contoh: 1 "Iced Latte" = 10g kopi + 200ml susu + 15g sirup      │
│                                                                  │
│ 175.716 transaksi (19.714 ghost ditandai, tidak diexpand)       │
│ → 856.639 baris ingredient-level                                │
│ → Daily consumption: 23.562 baris | 1.086 hari | 34 item unik   │
└──────────────────────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 4 — STOCK RECONCILIATION                                  │
│                                                                  │
│ Bandingkan: "Stok hari ini" vs "Stok kemarin - konsumsi hari ini"│
│                                                                  │
│ Rumus:                                                           │
│   Expected_Stock = Yesterday_Stock - POS_Consumed + Delivery_In  │
│   Variance = Physical_Stock - Expected_Stock                     │
│                                                                  │
│ Stok gudang: 6.615 baris | 167 hari | 45 item                    │
│ ● 6.570 bisa dianalisis                                          │
│ ● 45 skip (hari pertama / tidak ada baseline)                    │
│ ● 919 hari tanpa data gudang → dibuang (BUG2)                   │
└──────────────────────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 5 — CLASSIFICATION                                        │
│                                                                  │
│ Untuk setiap item per hari, pipeline memutuskan:                 │
│                                                                  │
│ Apakah Item_ID dikenal? ──Tidak──→ Invalid Data                  │
│ Ya                                                               │
│   ↓                                                              │
│ Apakah Physical_Stock < Min_Threshold? ──Ya──→ Restock           │
│ Tidak                                                            │
│   ↓                                                              │
│ Apakah Physical_Stock ≈ Expected_Stock? ──Ya──→ Safe             │
│ Tidak (selisih besar)                                            │
│   ↓                                                              │
│ Apakah Physical_Stock < Expected? ──Ya──→ Anomaly (Shrinkage)    │
│                                   ──Tidak→ Anomaly (POS_Overcount)│
└──────────────────────────────────────────────────────────────────┘
```

---

## 1. Format Baris & Struktur — Penjelasan Detail

### a. Kolom Identitas

| Kolom | Contoh | Cara Sistem Mendapatkan Nilai Ini |
|---|---|---|
| `Date` | `2025-01-01` | Tanggal rekonsiliasi — berasal dari data warehouse stock. Setiap tanggal di sini adalah tanggal di mana kita punya catatan stok gudang. |
| `Item_ID` | `INV-0000`, `MENU-010` | ID item inventory atau menu. Jika ID ini berasal dari menu (MENU-XXX) ghost → masuk Invalid Data. Jika dari inventory (INV-XXXX) → diproses rekonsiliasi. |

**Bagaimana sistem menentukan Item_ID?** `Item_ID` bisa berasal dari dua sumber:
1. **Master_Inventory.csv** — item fisik yang ada stoknya (INV-0000 sampai INV-0049+)
2. **Menu_ID** — jika Menu_ID tidak cocok dengan BOM atau Inventory, dia masuk Invalid Data

### b. Kolom Status — Yang Paling Penting

| Kolom | Contoh | Cara Sistem Mendapatkan Nilai Ini |
|---|---|---|
| `Action_Status` | `Anomaly` / `Safe` / `Restock` / `Invalid Data` | Lihat diagram klasifikasi di atas. Keputusan final dari semua perhitungan. |

### c. Kolom Stok

| Kolom | Contoh | Cara Sistem Mendapatkan Nilai Ini |
|---|---|---|
| `Physical_Stock` | `16152.3` | **Langsung dari warehouse_stock.json**. Stok fisik yang tercatat di gudang pada tanggal tersebut. Jika negatif → dikoreksi ke 0 (ada 269 kasus seperti ini). |
| `Min_Threshold` | `20000.0` | **Dari Master_Inventory.csv**. Batas minimal stok yang ditentukan oleh manajemen. Misalnya untuk INV-0001, threshold = 99.000g. |
| `Expected_Stock` | `149674.6` | **Hasil perhitungan**: `Stock_Kemarin - POS_Consumed + Delivery_In`. Ini adalah stok yang "seharusnya ada" berdasarkan data penjualan. Hanya terisi untuk status Anomaly. |
| `Variance` | `-132021.1` | **Hasil perhitungan**: `Physical_Stock - Expected_Stock`. Negatif = fisik kurang dari ekspektasi (barang hilang). Positif = fisik lebih dari ekspektasi (barang bertambah misterius). |
| `Variance_Direction` | `UNDER` / `OVER` | **UNDER** jika `Variance < 0` (stok kurang). **OVER** jika `Variance > 0` (stok lebih). |
| `Estimated_Loss_IDR` | `6601055.0` | **Hanya untuk UNDER**: `abs(Variance) × Harga_per_unit`. Total kerugian rupiah akibat barang hilang. Dari run ini: **Rp 264,8 Miliar** dari 2.839 item shrinkage. |

### d. Kolom Konsumsi

| Kolom | Contoh | Cara Sistem Mendapatkan Nilai Ini |
|---|---|---|
| `POS_Consumed` | `61210.188` | **Hasil BOM Explode + agregasi harian**. Total bahan baku yang terpakai dari penjualan menu pada hari itu. Misalnya: hari ini terjual 100 porsi Kopi Susu → 100 × 200ml susu = 20.000ml susu terpakai. |
| `Avg_7d_Consumption` | `61210.188` | **Rata-rata POS_Consumed 7 hari terakhir** untuk item ini. Digunakan untuk menghitung Days_to_Stockout. |
| `Delivery_In` | `4392.7` | **Dari warehouse_stock.json**. Stok yang sedang dalam pengiriman (in transit) dan akan tiba. Jika barang datang, stok bertambah. |

### e. Kolom Analisis

| Kolom | Contoh | Cara Sistem Mendapatkan Nilai Ini |
|---|---|---|
| `Days_to_Stockout` | `0.0` atau (kosong) | **Perhitungan**: `Physical_Stock / Avg_7d_Consumption`. Berapa hari lagi stok akan habis jika konsumsi tetap rata-rata. |
| `Restock_Urgency` | `CRITICAL` | Berdasarkan `Days_to_Stockout`: ≤ 0 = CRITICAL, 1-3 = URGENT, 4-14 = PLAN_ORDER, > 14 = SUFFICIENT |
| `Item_Note` | `Menu_ID tidak terdaftar...` | Catatan khusus — biasanya untuk Invalid Data menjelaskan kenapa ID tidak dikenal. |

---

## 2. Empat Status Aksi — Diperkaya dengan Data Run

### a. `Anomaly` — 6.444 baris (70,2% dari Action_Report)

**Arti**: Stok fisik tidak cocok dengan stok yang dihitung dari penjualan.

**Sub-kategori**:

| Sub-kategori | Jumlah | Penjelasan |
|---|---|---|
| **Shrinkage** | 2.861 | Stok fisik **kurang** dari ekspektasi — barang hilang, rusak, atau dicuri. Total kerugian: Rp 264,8 Miliar. |
| **POS_Overcount** | 3.583 | Stok fisik **lebih** dari ekspektasi — mungkin ada barang masuk tidak tercatat, atau pencatatan penjualan kurang. |

**Analogi**: Buku catatan bilang stok gula **100 kg**, di gudang hanya **60 kg** (Shrinkage — 40kg hilang). Atau buku catatan bilang stok **50 kg**, di gudang ada **80 kg** (POS_Overcount — 30kg tidak tercatat masuknya).

**Dampak ke bisnis**: Anomali adalah yang paling perlu ditindaklanjuti. 6.444 baris anomali berarti ada **ribuan kejadian stok tidak sinkron** yang perlu investigasi.

**Kolom yang terisi untuk Anomaly:**
- `Expected_Stock` → terisi (ada perhitungan)
- `Variance` → terisi (selisih)
- `Variance_Direction` → terisi (UNDER/OVER)
- `Estimated_Loss_IDR` → terisi jika UNDER

### b. `Invalid Data` — 2.564 baris (27,9% dari Action_Report)

**Arti**: Item_ID tidak dikenal di Master_Inventory atau BOM — tidak bisa diproses.

**Ghost Menu_ID yang lolos karantina:**
| Ghost ID | Status di Action | Alasan |
|---|---|---|
| `MENU-000` | Invalid Data | ID tidak ada di master |
| `MENU-999` | Invalid Data | ID tidak ada di master |
| `PROMO-01` | Invalid Data | Menu promo palsu |
| `SPECIAL-01` | Invalid Data | Menu spesial palsu |
| `BUNDL-01` | Invalid Data | Menu bundle palsu |
| `FREE-ITEM` | Invalid Data | Item gratis palsu |
| `TEST` | Invalid Data | Data testing |
| `VOID` | Invalid Data | Data void |
| `DELETED` | Invalid Data | Data terhapus |

**Total: 19.714 transaksi dengan ghost ID → 2.564 baris di Action_Report** (aggregasi per-item per-hari).

**Analogi**: Menu "Alien Coffee" muncul di laporan penjualan — tidak ada di daftar menu resmi, tidak tahu resepnya, tidak bisa dihitung stoknya. Dicatat sebagai Invalid.

**Penting:** Data Invalid di Action_Report **BUKAN dari karantina**. Ghost Menu_ID lolos karantina karena data per-barisan valid (ada TRX_ID, qty bagus, tanggal bagus). Tapi begitu masuk rekonsiliasi, ID tidak dikenal. Ini adalah **lapis keamanan kedua**.

### c. `Safe` — 159 baris (1,7% dari Action_Report)

**Arti**: Stok aman — physical_stock > min_threshold DAN variance dalam batas wajar.

**Analogi**: Stok gula **50 kg**, batas aman **10 kg**, pemakaian **2 kg/hari**, kiriman **10 kg dalam perjalanan** — masih cukup untuk 30+ hari. Tidak perlu khawatir.

**Dampak**: Tidak perlu tindakan. Tapi tetap perlu dipantau secara berkala.

### d. `Restock` — 12 baris (0,1% dari Action_Report)

**Arti**: Stok di bawah batas minimal — harus segera di-restok.

**Data dari run:**
```
INV-0000: Physical=16.152 | Threshold=20.000 | Kekurangan=4.393
INV-0001: Physical=29.935 | Threshold=99.000 | Kekurangan=61.210 | CRITICAL
INV-0004: Physical=18.409 | Threshold=40.000 | Kekurangan=8.531 | CRITICAL
INV-0019: Physical=0      | Threshold=3.000  | Kekurangan=4.131 | CRITICAL
...dan 8 item lainnya
```

**Analogi**: Stok gula tinggal **1 kg**, batas aman **20 kg**, pemakaian **2 kg/hari** → besok habis! Telepon supplier sekarang!

---

## 3. Inovasi BI: Days-to-Stockout

Pipeline V2 punya **2 inovasi** yang memperkaya Action_Report:

### a. Days-to-Stockout

**Rumus:**
```
Days_to_Stockout = Physical_Stock / Avg_7d_Consumption
```

**Contoh:**
- Stok: 50.000 unit
- Konsumsi 7 hari: [2.000, 2.100, 1.900, 2.200, 2.000, 1.800, 2.000] → rata-rata: 2.000/hari
- Days_to_Stockout = 50.000 / 2.000 = **25 hari**

**Dari run ini**: 1.489 item-hari masuk kategori CRITICAL/URGENT — artinya ada 1.489 momen di mana stok suatu item sangat menipis.

### b. Urgensi Restok

| Label | Days_to_Stockout | Tindakan |
|---|---|---|
| `CRITICAL` | ≤ 0 (sudah habis) | Restok segera (telepon supplier hari ini) |
| `URGENT` | 1 - 3 hari | Restok minggu ini |
| `PLAN_ORDER` | 4 - 14 hari | Rencanakan pemesanan |
| `SUFFICIENT` | > 14 hari | Tidak perlu restok |
| `N/A` | Tidak bisa dihitung | Invalid Data atau data kurang |

### c. Estimasi Kerugian Finansial

**Rumus:**
```
Estimated_Loss_IDR = abs(Variance) × Harga_Satuan
```

**Hanya untuk shrinkage (UNDER)** — stok fisik kurang dari ekspektasi.

**Dari run ini**: 2.839 item shrinkage → **Total estimated loss: Rp 264.835.215.086**.

Ini adalah angka **sangat besar** karena dataset stress test sengaja dibuat ekstrim. Dalam data nyata, angka ini akan lebih kecil. Tapi menunjukkan bahwa pipeline bisa mengkuantifikasi dampak finansial dari anomali stok.

---

## 4. Urutan Kolom yang Logis

Pipeline merapikan 15 kolom Action_Report dalam urutan yang logis:

```
[DATE] → [ITEM] → [STATUS] → [STOK] → [THRESHOLD] → [ANALISIS] → [FINANSIAL] → [KONSUMSI] → [CATATAN]
```

Artinya: setelah tanggal dan item, pembaca langsung lihat **status** (yang paling penting), lalu **data stok** (angka), lalu **analisis** (days-to-stockout, urgensi), lalu **dampak finansial**, lalu **konsumsi**, lalu **catatan**.

---

## 5. Penggunaan Bisnis Action_Report

| Peran | Cara Menggunakan Action_Report |
|---|---|
| **Manajer Toko** | Filter `Restock` → lihat item CRITICAL → pesan barang. Filter `Anomaly` → investigasi barang hilang. |
| **Purchasing** | Filter `Restock` + `Plan_Order` → buat purchase order untuk minggu depan |
| **Finance** | Lihat `Estimated_Loss_IDR` → hitung kerugian shrinkage untuk laporan keuangan |
| **Operasional** | Filter `Anomaly (Shrinkage)` → cek fisik gudang, cari barang yang hilang |
| **Data Analyst** | Filter `Invalid Data` → audit data master, update inventory/BOM |

---

## 6. Perbandingan: Dengan vs Tanpa Action_Report

| Tanpa Action_Report | Dengan Action_Report |
|---|---|
| Manajer harus cek 195.430 transaksi SATU PER SATU | Langsung dapat 9.179 ringkasan — hanya 4 kategori |
| Tidak tahu barang mana yang urgent | Status `CRITICAL` langsung sorot barang bahaya |
| Tidak sadar ada anomali stok | 6.444 anomali terdeteksi, siap investigasi |
| Data invalid bercampur dengan data valid | 2.564 invalid dipisahkan, tidak mengotori analisis |
| Hitung days-to-stockout manual | Langsung dapat estimasi |
| Tidak tahu kerugian shrinkage | Rp 264,8 Miliar terkuantifikasi |

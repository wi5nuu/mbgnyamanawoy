# `Action_Report.csv` — Laporan Aksi Stok

**Jumlah baris: 9.179** — hasil rekonsiliasi stok dari 200.230 transaksi bersih.

---

## 1. Format Baris & Struktur

| Kolom | Contoh | Arti |
|---|---|---|
| `Date` | `2025-01-01` | Tanggal laporan |
| `Item_ID` | `INV-0000`, `MENU-010` | ID item (bisa inventory atau menu) |
| `Action_Status` | `Restock`, `Safe`, `Anomaly`, `Invalid Data` | **Klasifikasi status — kolom paling penting** |
| `Physical_Stock` | `16152.3` | Stok fisik saat ini di gudang |
| `Min_Threshold` | `20000.0` | Batas minimal stok yang harus dijaga |
| `Days_to_Stockout` | `0.0` atau (kosong) | Estimasi hari sampai stok habis |
| `Restock_Urgency` | `CRITICAL`, `URGENT`, `SUFFICIENT`, `PLAN_ORDER`, atau `N/A` | **Tingkat urgensi restok** |
| `Expected_Stock` | (kosong) | Stok yang diharapkan (hanya untuk Anomaly) |
| `Variance` | (kosong) | Selisih stok aktual vs ekspektasi (hanya untuk Anomaly) |
| `Variance_Direction` | `OVER` / `UNDER` | Arah selisih (hanya untuk Anomaly) |
| `Estimated_Loss_IDR` | (angka) atau `N/A` | Estimasi kerugian dalam Rupiah |
| `POS_Consumed` | `0.0` | Jumlah stok terpakai berdasarkan transaksi POS |
| `Avg_7d_Consumption` | `61210.188` | Rata-rata konsumsi 7 hari terakhir |
| `Delivery_In` | `4392.7` atau `0.0` | Stok yang sedang dalam pengiriman |
| `Item_Note` | `Menu_ID tidak terdaftar...` | Catatan tambahan |

---

## 2. Empat Status Aksi

### a. `Anomaly` — 6.444 baris (70,2%)

| 🕵️ | Penjelasan |
|---|---|
| **Arti** | Stok fisik **tidak cocok** dengan stok yang dihitung dari penjualan — ada keanehan |
| **Analogi** | Di buku catatan tercatat punya **100 gelas**, tapi di rak hanya ada **60** — ada 40 gelas hilang entah ke mana |
| **Penyebab** | Kemungkinan: barang rusak tidak tercatat, pencurian, salah catat, atau stok awal salah |
| **Dampak** | Perlu investigasi lapangan — bisa jadi **kebocoran stok** (shrinkage) |
| **Sub-kolom relevan** | `Expected_Stock`, `Variance`, `Variance_Direction`, `Estimated_Loss_IDR` — semua **terisi** untuk status ini |

**Contoh baris Anomaly:**

```
Date,Item_ID,Action_Status,Physical_Stock,Min_Threshold,Days_to_Stockout,Restock_Urgency,Expected_Stock,Variance,Variance_Direction,Estimated_Loss_IDR,...
2025-01-01,INV-0025,Anomaly,17653.5,3000.0,,N/A,149674.6,-132021.1,UNDER,6601055.0,...
```

Artinya: Stok fisik INV-0025 = **17.653**, tapi seharusnya **149.674** berdasarkan penjualan. Selisih **-132.021 (UNDER)** dengan estimasi kerugian **Rp6.601.055**. Ini **banyak barang hilang**.

### b. `Invalid Data` — 2.564 baris (27,9%)

| ❌ | Penjelasan |
|---|---|
| **Arti** | Item_ID **tidak dikenal** di master data (Master_Inventory atau BOM) — tidak bisa diproses lebih lanjut |
| **Analogi** | Di laporan penjualan tercantum **"Menu Alien"** — tidak ada di menu manapun, tidak bisa dihitung stoknya |
| **Penyebab** | Ghost Menu_ID sengaja dimasukkan: `MENU-000`, `MENU-999`, `PROMO-01`, `SPECIAL-01`, `BUNDL-01`, `FREE-ITEM`, `TEST`, `VOID`, `DELETED` |
| **Dampak** | Data tidak berguna untuk analisis stok, tapi tetap dicatat untuk transparansi |
| **Sub-kolom relevan** | `Item_Note` terisi: `"Menu_ID tidak terdaftar di BOM/Master_Inventory"`. Hampir semua kolom lain kosong |

### c. `Safe` — 159 baris (1,7%)

| ✅ | Penjelasan |
|---|---|
| **Arti** | Stok **aman** — jumlah cukup, konsumsi normal, tidak perlu restok segera |
| **Analogi** | Stok kopi di gudang masih **50 kg**, pemakaian **2 kg/hari**, kiriman datang **10 kg lagi** — masih cukup untuk 30+ hari |
| **Dampak** | Tidak perlu tindakan. Pantau rutin. |
| **Sub-kolom relevan** | `Days_to_Stockout` > 5 biasanya. `Restock_Urgency` = `SUFFICIENT`. |

### d. `Restock` — 12 baris (0,1%)

| 🔴 | Penjelasan |
|---|---|
| **Arti** | Stok **di bawah batas minimal** — harus segera restok |
| **Analogi** | Stok gula tinggal **1 kg**, batas aman **20 kg** — besok bisa habis! |
| **Dampak** | **TINDAKAN SEGERA**: pesan barang sekarang |
| **Sub-kolom relevan** | `Days_to_Stockout` = `0` atau angka kecil. `Restock_Urgency` = `CRITICAL`. `POS_Consumed`, `Avg_7d_Consumption` terisi. |

---

## 3. Tabel Urgensi Restok

| Label | Arti | Tindakan |
|---|---|---|
| `CRITICAL` | Stok **hari ini juga** akan habis | Restok segera (telepon supplier) |
| `URGENT` | Stok habis dalam **1-3 hari** | Restok minggu ini |
| `PLAN_ORDER` | Stok habis dalam **3-14 hari** | Rencanakan pemesanan |
| `SUFFICIENT` | Stok masih cukup untuk **14+ hari** | Tidak perlu restok |
| `N/A` | Tidak bisa dihitung (Invalid Data) | Abaikan |

---

## 4. Kolom Estimasi Kerugian

`Estimated_Loss_IDR` hanya terisi untuk status **Anomaly** (khususnya yang `UNDER` — stok kurang dari ekspektasi).

Rumus logika:
- **UNDER** (stok fisik < stok ekspektasi) → perbedaan dianggap **kehilangan** → dikali harga → estimasi kerugian Rp
- **OVER** (stok fisik > stok ekspektasi) → tidak dihitung rugi, mungkin ada barang masuk tidak tercatat

---

## 5. Kenapa Action_Report Penting?

| Tanpa Action_Report | Dengan Action_Report |
|---|---|
| Manajer harus cek 200.230 transaksi SATU PER SATU | Langsung dapat 9.179 ringkasan — hanya 4 kategori |
| Tidak tahu barang mana yang urgent | Status `CRITICAL` langsung sorot barang bahaya |
| Tidak sadar ada anomali stok | 6.444 anomali terdeteksi, siap investigasi |
| Data invalid bercampur dengan data valid | 2.564 invalid dipisahkan, tidak mengotori analisis |

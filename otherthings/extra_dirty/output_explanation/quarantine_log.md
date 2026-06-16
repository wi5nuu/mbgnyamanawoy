# `quarantine_log.csv` — Log Karantina Data Kotor

**Jumlah baris: 74.970** dari 270.400 total transaksi mentah (27,7%).

---

## 1. Format Baris & Struktur

| Kolom | Contoh | Arti |
|---|---|---|
| `Transaction_ID` | (kosong) | ID transaksi — banyak yang kosong karena duplikat atau tidak ada |
| `DateTime` | `2025-02-14 05:29:20` | Waktu transaksi asli (mentah, belum tentu valid) |
| `Employee_ID` | `EMP-05`, `INTERN`, `MANAGER` | ID karyawan — bisa berisi nilai liar |
| `Menu_ID` | `MENU-010` | ID menu yang dibeli |
| `Item_Name` | `Kopi Susu Gula Aren` | Nama item |
| `Quantity` | `5`, `eight`, `-7`, `0 cups` | Jumlah beli — **bisa berisi teks, negatif, atau aneh** |
| `Additional_Info` | `; DROP--`, `<script>xss</script>` | Info tambahan — sering berisi **Error flag buatan** |
| `Quarantine_Reason` | `DUPLICATE_TRANSACTION_ID` | **Alasan kenapa baris ini dikarantina** (paling penting) |
| `DateTime_Parsed` | (kosong) | Hasil parsing tanggal — kosong karena ditolak |
| `Date` | (kosong) | Tanggal bersih — kosong karena ditolak |
| `Quantity_Clean` | (kosong) | Jumlah bersih — kosong karena ditolak |

> Kolom `DateTime_Parsed`, `Date`, `Quantity_Clean` kosong karena baris ini **gagal di-transform** → menunjukkan bahwa karantina terjadi **sebelum** proses pembersihan selesai.

---

## 2. Daftar Alasan Karantina & Artinya

### a. `NULL_CRITICAL_FIELD` — 16.931 baris (22,6%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Kolom penting (`Transaction_ID`, `Quantity`, `Menu_ID`) bernilai kosong/null |
| **Analogi** | Pelanggan datang tapi **tidak bawa dompet + tidak kasih nama** — tidak bisa diproses |
| **Dampak** | Data tidak memiliki identitas atau jumlah, tidak bisa direkonsiliasi |
| **Penyebab di dataset** | Baris dengan `Transaction_ID` kosong, `Quantity` kosong, atau `Menu_ID` hilang |

### b. `ERROR_FLAG_IN_ADDINFO` — 14.253 baris (19,0%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Kolom `Additional_Info` berisi **kata-kata error palsu** yang sengaja dimasukkan sebagai "kotoran" |
| **Analogi** | Pelanggan kasih catatan pesanan yang isinya **"ERROR", "INVALID", "NaN", "undefined", "SYSERR"** — jelas bukan pesanan valid |
| **Dampak** | Flag ini sengaja dibuat untuk menguji apakah pipeline bisa mendeteksi error semu |
| **Variasi yang terdeteksi** | `ERROR`, `Err0r`, `EROR`, `INVALID`, `inv4lid`, `#REF!`, `#VALUE`, `#DIV/0!`, `#NAME?`, `ROER`, `TIMEOUT`, `SYSERR`, `UNKNOWN`, `N/A`, `None`, `nan`, `undefined`, `'; DROP--`, `<script>xss</script>`, dll — **25+ varian** |

### c. `DUPLICATE_TRANSACTION_ID` — 11.091 baris (14,8%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | `Transaction_ID` sama persis dengan baris lain (duplikat) |
| **Analogi** | Dua orang datang dengan **tiket yang sama** — salah satu pasti palsu |
| **Dampak** | Jika tidak dibuang, akan menggandakan stok yang terpakai |
| **Penyebab di dataset** | Kami sengaja menduplikat transaksi dengan `Transaction_ID` yang sama |

### d. `ZERO_QUANTITY` — 11.256 baris (15,0%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Quantity = 0 — menjual 0 barang tidak masuk akal |
| **Analogi** | Pelanggan beli **0 kopi** — transaksi ini tidak berguna |
| **Dampak** | Baris dengan qty=0 mengotori data tapi tidak mempengaruhi stok |

### e. `NEGATIVE_QUANTITY` — 6.696 baris (8,9%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Quantity negatif (misal: `-7`, `-164`) — tidak masuk akal untuk transaksi penjualan |
| **Analogi** | Pelanggan membeli **minus 7 kopi** = secara logika menjual kembali ke toko? Tidak masuk akal |
| **Dampak** | Jika lolos, akan menambah stok (salah arah) |

### f. `UNPARSEABLE_QUANTITY` — 4.756 baris (6,3%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Quantity berisi teks yang tidak bisa diubah jadi angka (misal: `eight`, `0 cups`, `1,6`, ` `, `#DIV/0!`) |
| **Analogi** | Kasir menulis **"delapan"** di kolom jumlah — komputer bingung, harusnya angka `8` |
| **Dampak** | Tidak bisa dihitung kontribusinya terhadap stok |

### g. `UNPARSEABLE_DATE` — 4.302 baris (5,7%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Format tanggal **tidak dikenali** oleh parser pipeline |
| **Analogi** | Tiket masuk bertuliskan **"nanti sore"** sebagai tanggal — tidak jelas kapan |
| **Dampak** | Data tidak punya referensi waktu, tidak bisa dianalisis tren penjualan |

### h. Lain-lain (Error Flag dengan kutip) — ~5.374 baris (7,2%)
| ⚠️ | Penjelasan |
|---|---|
| **Arti** | Kolom `Additional_Info` berisi error flag yang **terbungkus kutip** (misal: `"ERROR"`, `"INVALID"`) |
| **Alasan terpisah** | Pipeline mendeteksinya sebagai **string berbeda** karena ada kutip tambahan |
| **Dampak** | Ini adalah **test coverage gap** — pipeline mendeteksi error flag bersih tapi tidak yang berkutip |

> **Total 7 kategori besar + ~25 sub-kategori** = pipeline berhasil mendeteksi banyak jenis kotoran data.

---

## 3. Kenapa Karantina Itu Penting?

**Tanpa karantina**: Data kotor masuk ke perhitungan stok → stok terhitung salah → keputusan bisnis salah (restok kelebihan/kekurangan).

**Dengan karantina**: Data kotor dipisahkan → hanya data bersih yang diproses → laporan akurat.

### Contoh nyata dampak:

| Skenario | Tanpa Karantina | Dengan Karantina |
|---|---|---|
| Ada 1.000 transaksi qty = 0 | Stok terpakai dihitung 0 (aman), tapi 1.000 baris sampah memenuhi sistem | 1.000 baris dibuang, perhitungan stok akurat |
| Ada 500 transaksi dengan qty negatif | Stok **bertambah** secara salah (seolah-olah ada pengembalian) | 500 baris dibuang, stok tidak terpengaruh |
| Ada 200 EMPLOYEE_ID "INTERN" | Data penjualan tercatat atas nama "INTERN" yang tidak dikenal sistem | 200 baris dibuang, karena karyawan tidak valid |

---

## 4. Status Kolom di Karantina

Perhatikan bahwa di karantina, kolom hasil parsing (`DateTime_Parsed`, `Date`, `Quantity_Clean`) **semua kosong**:

```
Transaction_ID,DateTime,Employee_ID,Menu_ID,Item_Name,Quantity,Additional_Info,Quarantine_Reason,DateTime_Parsed,Date,Quantity_Clean
              ,2025-02-14...,EMP-05,MENU-010,Kopi Susu...,5,'; DROP--,DUPLICATE_TRANSACTION_ID,,,
```

Ini penting: **karantina terjadi di tengah-tengah pipeline** — data sudah dibaca tapi belum selesai dibersihkan. Pipeline menghentikan pemrosesan begitu menemukan alasan untuk menolak baris tersebut.

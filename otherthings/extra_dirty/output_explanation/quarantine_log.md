# `quarantine_log.csv` — Log Karantina Data Kotor

**Jumlah baris: 74.970** dari 270.400 total transaksi mentah (27,7%).

---

## Bagaimana Pipeline Memutuskan Karantina? (Cara Kerja Sistem)

Pipeline memeriksa setiap baris **satu per satu, berurutan** dengan 7 lapis validasi. Begitu satu pelanggaran ditemukan, baris langsung dikarantina dan **tidak diperiksa lapis berikutnya**.

```
Baris mentah masuk
       │
       ▼
┌── Lapis 1: Apakah Transaction_ID duplikat? ──→ Ya ──→ DUPLICATE_TRANSACTION_ID
└── Tidak
       │
       ▼
┌── Lapis 2: Apakah Additional_Info berisi error flag? ──→ Ya ──→ ERROR_FLAG_IN_ADDINFO
└── Tidak
       │
       ▼
┌── Lapis 3: Apakah ada field kritis yang NULL? ──→ Ya ──→ NULL_CRITICAL_FIELD
└── Tidak
       │
       ▼
┌── Lapis 4: Apakah DateTime bisa diparse? ──→ Tidak ──→ UNPARSEABLE_DATE
└── Ya
       │
       ▼
┌── Lapis 5: Apakah Quantity valid? (numerik / > 0) ──→ Negatif ──→ NEGATIVE_QUANTITY
│                                                     ──→ Teks ──→ UNPARSEABLE_QUANTITY
│                                                     ──→ Nol ──→ ZERO_QUANTITY
└── Ya
       │
       ▼
   ✅ Baris lolos → diproses ke rekonsiliasi stok
```

**Konsep penting**: Setiap baris hanya punya **satu alasan karantina**, yaitu pelanggaran pertama yang ditemukan. Jika suatu baris punya Transaction_ID duplikat DAN Quantity negatif, hanya `DUPLICATE_TRANSACTION_ID` yang tercatat.

---

## 1. Format Baris & Struktur — Penjelasan Detail

### a. Kolom Input (Data Mentah)

Kolom-kolom ini adalah data **asli dari file CSV**, sebelum diproses:

| Kolom | Contoh | Penjelasan | Cara Kerja Sistem |
|---|---|---|---|
| `Transaction_ID` | `TRX-001234` atau `(kosong)` | Nomor unik setiap transaksi. | Sistem mengecek: apakah ID ini sudah pernah muncul sebelumnya? Jika ya → duplikat. Jika kosong → masuk NULL_CRITICAL_FIELD. |
| `DateTime` | `2025-02-14 05:29:20` | Waktu transaksi terjadi. | Sistem mencoba 6 format parser berbeda (ISO, DD/MM/YYYY, Month name, dll). Jika semua gagal → UNPARSEABLE_DATE. |
| `Employee_ID` | `EMP-05`, `INTERN`, `MANAGER` | ID karyawan yang melayani. | Tidak dikarantina di tahap ini, hanya dicatat. Tapi jika ada di daftar Employee.json? Tidak dicek — ini kelemahan pipeline. |
| `Menu_ID` | `MENU-010` | ID menu yang dibeli. | Tidak dikarantina di tahap ini. Ghost ID lolos dulu, baru ditandai sebagai Invalid Data di Action_Report. |
| `Item_Name` | `Kopi Susu Gula Aren` | Nama item untuk human-readable. | Tidak divalidasi — hanya referensi. |
| `Quantity` | `5`, `eight`, `-7`, `0 cups` | Jumlah item yang dibeli. | Sistem mencoba 3 metode parsing: (1) langsung numerik? (2) regex ambil angka? (3) fallback manual. Hasilnya menentukan NEGATIVE, ZERO, UNPARSEABLE, atau valid. |
| `Additional_Info` | `; DROP--`, `<script>xss</script>` | Kolom bebas untuk catatan tambahan. | Sistem punya daftar 25+ kata terlarang (ERROR, INVALID, NaN, dll). Jika cocok → ERROR_FLAG_IN_ADDINFO. |

#### Analogi: Petugas Penerimaan Tamu

Bayangkan pipeline sebagai **petugas penerimaan tamu di mal**:

| Kolom | Analogi |
|---|---|
| `Transaction_ID` = **KTP Tamu** | Tanpa KTP = tidak dikenal. KTP duplikat = ada yang palsu |
| `DateTime` = **Jam Kedatangan** | "Nanti sore" tidak jelas — harus format standar |
| `Employee_ID` = **Karyawan yang menyapa** | Dicatat saja, tidak dicek |
| `Menu_ID` = **Tujuan toko** | Tidak dicek di pintu masuk |
| `Quantity` = **Jumlah barang belanja** | Beli 0 = iseng. Beli -7 = tidak masuk akal. "Delapan" = komputer bingung |
| `Additional_Info` = **Catatan Satpam** | Jika catatannya "BOM WARNING" → curiga! |

### b. Kolom Output Pipeline

Kolom-kolom ini adalah **hasil kerja pipeline**, yang **akan terisi jika baris lolos**:

| Kolom | Penjelasan | Kenapa di Karantina Kosong? |
|---|---|---|
| `Quarantine_Reason` | Alasan kenapa baris ini ditolak. | Ini satu-satunya kolom output yang TERISI di karantina. |
| `DateTime_Parsed` | Hasil parsing DateTime ke format datetime Python. | **Kosong** karena baris sudah ditolak sebelum parsing selesai (kecuali untuk alasan UNPARSEABLE_DATE — parsing gagal). |
| `Date` | Tanggal (tanpa jam) hasil parsing. | **Kosong** karena baris ditolak. |
| `Quantity_Clean` | Quantity yang sudah dibersihkan jadi angka. | **Kosong** karena baris ditolak. |

#### Mengapa kolom output kosong? Ini kunci penting:

Pipeline bekerja **berurutan**: validasi → parsing → transformasi. Begitu validasi gagal di salah satu lapis, pipeline **berhenti memproses baris itu**. Kolom `DateTime_Parsed`, `Date`, `Quantity_Clean` tidak pernah diisi karena baris sudah dikeluarkan sebelum sampai ke tahap itu.

```
Baris masuk → Validasi Transaction_ID → ❌ Gagal → STOP → Tulis Quarantine_Reason, kolom lain kosong
Baris masuk → Validasi Transaction_ID → ✅ Lolos → Validasi Additional_Info → ❌ Gagal → STOP → Tulis Quarantine_Reason
...dan seterusnya
```

---

## 2. Daftar Alasan Karantina & Artinya — Diperkaya dengan Data Run

### a. `NULL_CRITICAL_FIELD` — 17.532 baris (23,4% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Sistem memeriksa apakah `Transaction_ID`, `Quantity`, atau `Menu_ID` kosong/null |
| **Contoh data** | Baris dengan `Transaction_ID` = `""`, `Quantity` = `""`, atau `Menu_ID` = `""` |
| **Cara sistem mendeteksi** | `if pd.isna(row[col]) or str(row[col]).strip() == '':` → untuk setiap field kritis |
| **Analogi** | Pelanggan datang ke kasir tapi **tidak punya KTP, tidak bawa dompet, dan tidak kasih nama** — mustahil diproses |
| **Dampak ke Action_Report** | Baris ini **tidak masuk** Action_Report sama sekali. Seolah tidak pernah terjadi. |
| **Dari mana di dataset?** | Kami sengaja membuat baris dengan Transaction_ID kosong, Quantity kosong, dan Menu_ID kosong untuk menguji deteksi null. |

**Mengapa ini kategori terbesar?** Karena `NULL` adalah bentuk kerusakan data yang paling mudah dibuat dan paling banyak kami injeksikan. Hampir 1 dari 4 baris karantina adalah karena field kritis tidak diisi.

### b. `ERROR_FLAG_IN_ADDINFO` — 17.920 baris (23,9% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Sistem memeriksa apakah kolom `Additional_Info` berisi kata-kata dalam daftar hitam (blacklist) |
| **Contoh data** | `Additional_Info` = `"ERROR"`, `"INVALID"`, `"#REF!"`, `"NaN"`, `"undefined"` |
| **Cara sistem mendeteksi** | Pipeline punya list: `['ERROR', 'INVALID', '#REF!', '#VALUE!', '#DIV/0!', '#NAME?', 'N/A', 'NaN', 'None', 'undefined', 'null', 'EROR', 'Err0r', 'inv4lid', 'ROER', 'TIMEOUT', 'SYSERR', 'UNKNOWN', '; DROP--', '<script>xss</script>', ...]` dan lainnya → jika cocok (case-insensitive) → karantina |
| **Analogi** | Kasir menulis catatan pesanan: **"Pesanan ini ERROR"** — bukan pesanan, ini testing |
| **Dampak ke Action_Report** | Tidak masuk Action_Report. Data ini dianggap tidak valid dari awal. |
| **25+ varian terdeteksi** | Termasuk variasi kreatif: `EROR` (salah ketik), `inv4lid` (leet speak), `ROER` (acak), `'; DROP--` (SQL injection), `<script>xss</script>` (XSS attack) |

**Yang menarik**: Ada ~5.374 baris tambahan dengan **error flag berkutip** (`"ERROR"`, `"INVALID"`) yang **terdeteksi terpisah**. Ini adalah celah — pipeline mendeteksi `ERROR` tapi tidak `"ERROR"` (dengan kutip). Keduanya harusnya diperlakukan sama.

### c. `DUPLICATE_TRANSACTION_ID` — 11.827 baris (15,8% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Apakah `Transaction_ID` sudah pernah muncul sebelumnya dalam dataset |
| **Cara sistem mendeteksi** | `df.duplicated(subset='Transaction_ID', keep='first')` — baris pertama dipertahankan, sisanya dikarantina |
| **Contoh** | Transaksi `TRX-001` muncul 3x — hanya baris pertama yang lolos, 2 sisanya dikarantina |
| **Analogi** | Dua orang datang dengan **tiket nomor antrian yang sama** — salah satu pasti tiruan |
| **Dampak ke Action_Report** | Jika tidak dibuang, transaksi duplikat akan **menggandakan stok terpakai** → salah hitung stok |

**Penting**: Ini adalah duplikat **sengaja** dibuat di dataset. Dalam data nyata, duplikat bisa terjadi karena bug sistem POS atau resubmit transaksi.

### d. `ZERO_QUANTITY` — 11.464 baris (15,3% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Apakah quantity = 0 setelah parsing |
| **Cara sistem mendeteksi** | `if qty_clean == 0:` setelah quantity berhasil diparse |
| **Analogi** | Pelanggan **pulang tanpa membeli apapun** — transaksi tidak berguna untuk analisis stok |
| **Dampak ke Action_Report** | Quantity 0 tidak mempengaruhi stok, tapi mengotori data. Lebih baik dibuang. |

### e. `NEGATIVE_QUANTITY` — 6.828 baris (9,1% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Apakah quantity negatif setelah parsing |
| **Cara sistem mendeteksi** | `if qty_clean < 0:` |
| **Analogi** | Pelanggan membeli **minus 7 kopi** = secara matematis dia menjual 7 kopi ke toko — tidak masuk akal untuk sistem POS |
| **Dampak ke Action_Report** | **BERBAHAYA**: Jika lolos, stok akan **BERTAMBAH** (qty negatif = stok kembali) — seolah ada barang balik tanpa alasan |
| **Sumber di dataset** | Quantity negatif seperti `-7`, `-164`, `-12` sengaja dibuat untuk menguji deteksi |

### f. `UNPARSEABLE_QUANTITY` — 4.840 baris (6,5% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Apakah quantity bisa diubah dari teks ke angka |
| **Cara sistem mendeteksi** | 3 lapis parsing: (1) `pd.to_numeric` langsung, (2) regex ekstrak angka (3) fallback manual. Jika semua gagal → karantina |
| **Contoh** | `"eight"`, `"0 cups"`, `"1,6"`, `" "` (spasi), `"#DIV/0!"`, `"<script>xss</script>"` |
| **Analogi** | Kasir menulis **"delapan"** atau **"secangkir"** di kolom jumlah — komputer bingung, seharusnya `8` |
| **Dampak ke Action_Report** | Tidak bisa dihitung kontribusinya terhadap stok — sama seperti tidak ada datanya |

### g. `UNPARSEABLE_DATE` — 4.559 baris (6,1% dari karantina)

| Aspek | Detail |
|---|---|
| **Apa yang dicek?** | Apakah format DateTime dikenali oleh 6 parser bertingkat |
| **Cara sistem mendeteksi** | Pipeline mencoba 6 format secara berurutan: (1) ISO `YYYY-MM-DD HH:MM:SS`, (2) `DD/MM/YYYY`, (3) `MM/DD/YYYY`, (4) Month name `Mar 20 2025`, (5) compact `YYYYMMDDHHMM`, (6) fallback `pd.to_datetime(errors='coerce')`. Jika semua gagal → `parse_datetime()` return None → karantina |
| **Contoh** | Tanggal kosong, tanggal dengan karakter aneh |
| **Analogi** | Tiket masuk bertuliskan **"nanti malam"** atau **"besok"** — tidak bisa ditentukan tanggalnya |
| **Dampak ke Action_Report** | Data tidak punya referensi waktu — tidak bisa di-aggregate per hari, tidak bisa dianalisis tren |

**⚠️ Catatan Bug Kritis**: Di `utils.py:347`, ada baris `result[mask] = series[mask].apply(parse_datetime)`. Fungsi `parse_datetime` bisa return `None` untuk data yang tidak terparsing. Jika terlalu banyak data dengan `None`, pandas mengubah kolom datetime jadi `object` dtype → error `Can only use .dt accessor with datetimelike values` di pipeline. Bug ini TIDAK muncul di V3 karena hanya 4.559 dari 270.400 (1,7%) yang tidak terparsing — tidak cukup besar untuk mengubah dtype.

---

## 3. Sistem Deteksi: Cara Pipeline Memvalidasi Quantity

Pipeline menggunakan **3 lapis parsing** untuk quantity, bekerja seperti ini:

```
Quantity mentah (string/float)
       │
       ▼
Lapis 1: pd.to_numeric(quantity, errors='coerce')
       ├──→ Berhasil (angka) → lanjut ke validasi negatif/zero
       └──→ Gagal (NaN)
               │
               ▼
Lapis 2: Regex ekstrak angka ──→ r'(-?\d+)' ambil digit pertama
       ├──→ Berhasil → lanjut
       └──→ Gagal
               │
               ▼
Lapis 3: Manual parsing untuk bentuk khusus
       ├──→ "eight" → 8
       ├──→ "0 cups" → 0 (ambil digit pertama)
       ├──→ "#DIV/0!" → NaN → UNPARSEABLE
       ├──→ "1,6" → NaN karena koma bukan desimal → UNPARSEABLE
       └──→ Sisa → NaN → UNPARSEABLE
```

**Contoh konkret:**

| Input | Lapis 1 | Lapis 2 | Lapis 3 | Hasil | Status |
|---|---|---|---|---|---|
| `5` | ✅ 5 | — | — | 5 | ✅ Valid |
| `-7` | ✅ -7 | — | — | -7 | ❌ Negatif |
| `0` | ✅ 0 | — | — | 0 | ❌ Zero |
| `"eight"` | ❌ NaN | ❌ NaN | ✅ 8 | 8 | ✅ Valid (Lapis 3 rescues) |
| `"0 cups"` | ❌ NaN | ✅ 0 | — | 0 | ❌ Zero |
| `"1,6"` (koma) | ❌ NaN | ✅ 1 | — | 1 | ✅ Valid (tapi kehilangan ,6) |
| `"<script>...</script>"` | ❌ NaN | ❌ NaN | ❌ NaN | NaN | ❌ Unparseable |
| `"#DIV/0!"` | ❌ NaN | ❌ NaN | ❌ NaN | NaN | ❌ Unparseable |

---

## 4. Sistem Deteksi: Cara Pipeline Memvalidasi DateTime

Pipeline mencoba **6 format parser** secara berurutan:

```
DateTime mentah
    │
    ▼
Parser 1: format ISO ──→ "2025-02-14 05:29:20" → ✅
Parser 2: DD/MM/YYYY ──→ "27/03/2025 02:33" → ✅
Parser 3: MM/DD/YYYY ──→ "03-26-2025 05:09 PM" → ✅
Parser 4: Month DD YYYY ──→ "Mar 20 2025" → ✅
Parser 5: compact 12 digit ──→ "202501170135" → ✅
Parser 6: pd.to_datetime coerce ──→ fallback terakhir
    │
    └──→ Semua gagal → return None → UNPARSEABLE_DATE
```

**Kenapa pipeline tidak pake `pd.to_datetime` langsung?** Karena `pd.to_datetime` dengan `errors='coerce'` akan mengubah string aneh jadi `NaT` (Not a Time) diam-diam. Dengan parser bertahap, pipeline bisa tahu **mana** yang gagal parsing dan mencatatnya sebagai `UNPARSEABLE_DATE` di karantina.

---

## 5. Kenapa Karantina Itu Penting? — Skenario Nyata

### Tanpa karantina (yang terjadi jika pipeline tidak mem-filter):

Data kotor masuk ke perhitungan stok → stok terhitung salah → keputusan bisnis salah.

**Contoh skenario:**

| Skenario | Tanpa Karantina | Dengan Karantina |
|---|---|---|
| 11.464 transaksi qty = 0 | Sistem diisi 11.464 baris sampah — memperlambat dan membingungkan | 11.464 baris dibuang, perhitungan stok akurat |
| 6.828 transaksi qty negatif | Stok **naik** secara salah (seolah ada 6.828 pengembalian) → restok jadi kurang | 6.828 baris dibuang, stok tidak terpengaruh |
| 17.920 error flag | Stok berkurang untuk "transaksi" yang isinya `ERROR` — tidak masuk akal | 17.920 baris dibuang — hanya transaksi riil yang diproses |
| 11.827 duplikat | Setiap item dihitung 2x stok terpakai → stok terkoreksi lebih rendah dari realita | Hanya 1 baris per transaksi unik yang diproses |
| 16.840 Ghost Employee_ID | Transaksi oleh "INTERN" atau "MANAGER" (yang tidak dikenal) ikut dihitung | 16.840 ditandai, perlu investigasi |

### Efek Domino Tanpa Karantina:

```
Data kotor masuk
    → Stok terhitung salah
        → Action_Report salah (Restock padahal tidak perlu, Safe padahal stok menipis)
            → Keputusan bisnis salah (beli barang Rp 50 juta padahal tidak perlu)
                → Kerugian finansial
```

### Efek Dengan Karantina:

```
Data kotor disaring
    → Hanya data bersih diproses
        → Action_Report akurat
            → Keputusan bisnis tepat
                → Efisiensi biaya
```

---

## 6. Catatan Khusus: Ghost Employee_ID

Pipeline mencatat **16.840 transaksi** dengan Employee_ID yang tidak dikenal di daftar Employee.json (seperti `INTERN`, `MANAGER`, `GUEST`, `OWNER`, dll).

Namun, tidak seperti Ghost Menu_ID, **Ghost Employee_ID TIDAK dikarantina**. Pipeline hanya memberi peringatan:

```
[⚠] Ghost Employee_ID: 16,840 transaksi (diproses, perlu investigasi)
```

Ini adalah **keputusan desain**: karyawan tidak dikenal tidak mempengaruhi perhitungan stok, jadi data tetap diproses. Tapi ini perlu diinvestigasi terpisah — mungkin ada karyawan baru yang belum terdaftar, atau ada penyalahgunaan akun.

---

## 7. Status Kolom di Karantina — Visual

Perhatikan pola berikut. Setiap baris di karantina memiliki kolom `DateTime_Parsed`, `Date`, `Quantity_Clean` yang **kosong**:

```
Transaction_ID | DateTime         | Employee_ID | Menu_ID  | Quantity | Additional_Info | Quarantine_Reason        | DateTime_Parsed | Date | Quantity_Clean
               | 2025-02-14 05:29 | EMP-05      | MENU-010 | 5        | ; DROP--        | DUPLICATE_TRANSACTION_ID |                 |      |
```

**Kolom kosong = petunjuk kuat bahwa pipeline berhenti di tengah jalan.** Ini membedakan karantina dari data normal: data normal memiliki semua kolom terisi, data karantina hanya memiliki kolom input + alasan karantina.

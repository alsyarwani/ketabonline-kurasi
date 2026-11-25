# ketabonline-kurasi

Metadata katalog [ketabonline.com](https://ketabonline.com) dan pencocokannya dengan koleksi **Syamilah 4**
(Excel seleksi v4) dan **GoldenShamela** (tabel `kitab_golden` dari ekstraktor-epub), plus GUI baca-saja untuk
menelusuri hasilnya. Alat ini **tidak mengunduh isi kitab**; isi kitab (`{id}.data.zip`) menyusul setelah
analisa menentukan kitab mana yang perlu.

Terpisah dari stack `shamela` (shamela-kurasi): tidak berbagi volume maupun database.

## Isi

| | |
|---|---|
| `ketab/sensus.py` | tarik metadata `books`, `categories`, `authors` dari API ketabonline (item APA ADANYA → `*.jsonl`), bisa dilanjutkan |
| `ketab/cocok.py` | bandingkan judul (dinormalisasi seperti ekstraktor-epub) → `hasil.db` (SQLite) + `hasil.csv` |
| `ketab/unduh.py` | unduh `{id}.data.zip` terpilih (status/sumber/daftar ID) ke `zip/<NNN>/`, lewati yang sudah ada, simpan versi lama |
| `ketab/gui.py` | GUI Flask: ringkasan sumber × status, saringan, detail kitab, ekspor Excel |
| `jalankan-server.sh` | pemasangan sekali jalan di server (repo, ekspor golden, build, cocok, GUI) |

## Status pencocokan

| status | arti |
|---|---|
| `syamilah4` | judul sama persis (setelah normalisasi) dengan kitab Syamilah 4, pengarang tidak bertentangan |
| `golden` | judul sama persis dengan kitab GoldenShamela (dan tidak ada di Syamilah 4) |
| `mirip` | hanya cocok setelah keterangan kurung / ekor judul (`- مخطوط`, `ت فلان`) dibuang, atau judul sama tetapi pengarang berbeda → tinjau manual |
| `baru` | tidak ditemukan di keduanya |

Normalisasi: harakat & tatwil dibuang, أ إ آ ٱ → ا, ى → ي, ة → ه, tanda baca → spasi. Pengarang dibandingkan per
token nama (tanpa بن/ابن/أبو/ال). Pencocokan judul hanyalah saringan awal: edisi/tahqiq berbeda dengan judul sama
akan tercatat sebagai `syamilah4`/`golden`.

## Data (server)

```
/disk6/shamela/ketabonline/
    kitab.jsonl  kategori.jsonl  pengarang.jsonl  *.selesai     hasil sensus (25–26 Nov 2026: 30.093 kitab)
    golden.csv                                                   ekspor kitab_golden
    hasil.db  hasil.csv                                          hasil pencocokan
    contoh/                                                      contoh {id}.data.zip untuk parser isi nanti
/disk6/shamela/excel/Seleksi_Buku_Syamilah4_v4.xlsx               hanya dibaca
```

## Menjalankan

```bash
docker compose build
docker compose run --rm alat cocok        # ulangi setelah Excel/golden/sensus berubah
docker compose up -d gui                  # layanan ketabonline-gui:8000 di jaringan jalurgateway
docker compose run --rm alat sensus       # sensus ulang/lanjutkan (butuh internet; ±20 menit untuk 30 rb kitab)
```

### Unduh isi kitab

```bash
docker compose run --rm alat unduh --perkiraan                       # status 'baru' (bawaan): jumlah, MB, waktu
docker compose run --rm alat unduh --status baru,mirip --perkiraan
docker compose run -d --name ketabonline-unduh alat unduh --status baru   # jalan di latar belakang
docker logs -f ketabonline-unduh
docker compose run --rm alat unduh --daftar /data/pilihan.xlsx       # ID dari Ekspor Excel GUI (kolom id)
```

Arsip: `zip/<NNN>/<id>.data.zip` (NNN = tiga digit terakhir ID) + catatan `unduhan.jsonl`. Hanya ditambah: yang sudah
terunduh dengan `updated_at` sama dilewati; bila `updated_at` berubah, file lama disimpan sebagai
`<id>.data.<updated_at>.zip`. ZIP diperiksa (utuh, satu `.json` yang valid) sebelum disimpan. Bisa dihentikan dan
dijalankan ulang kapan saja; 404 dicatat dan dicoba lagi di putaran berikutnya.

Ekspor golden secara manual:

```bash
docker exec shamela-golden-pg psql -U golden -d golden -c "\copy (SELECT golden_id, shamela_id, judul, pengarang, wafat_h, kategori, jumlah_halaman, dup_syamilah_id FROM kitab_golden) TO STDOUT WITH CSV HEADER" > /disk6/shamela/ketabonline/golden.csv
```

**GUI tanpa login.** Buat rute di gateway dengan autentikasi sebelum dibuka ke luar.

## Tes

```bash
pip install flask waitress openpyxl pytest
python -m pytest -q tests
```

## Catatan API ketabonline (dari sensus & contoh)

- `GET backend.ketabonline.com/api/v2/books?page=&limit=` → `{code, data[], meta{total,last_page}, links}`; item daftar
  sudah memuat `meta` (المؤلف, المصدر), `source`, `bibliography`, `authors`, `categories`, `parts`, `files`.
- Isi kitab: `s2.ketabonline.com/books/{id}/{id}.data.zip` → satu `{id}.data.json` (metadata + `index` bertingkat + `pages[]`).
  Kitab `is_active=0` menjawab 404 di `/books/{id}`, tetapi ZIP-nya tetap ada.
- Hasil pencarian `q=` memberi judul bertanda `<em>`.
- Sumber (26 Nov 2026): الشاملة الذهبية 21.758 · الشاملة 7.699 · الشاملة أردو 386 · قرآن ويب 228 · lain 22.

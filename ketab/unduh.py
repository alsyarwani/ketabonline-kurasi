"""Unduh isi kitab ketabonline ({id}.data.zip) ke arsip lokal, terpilih dari hasil.db.

    <data>/zip/<NNN>/<id>.data.zip        NNN = tiga digit terakhir ID (pola sama dengan windows.py)
    <data>/unduhan.jsonl                  catatan per unduhan: id, updated_at, byte, sha256, waktu, hasil

Arsip diperlakukan HANYA DITAMBAH: kitab yang sudah terunduh dengan updated_at sama dilewati; bila updated_at
di katalog berubah, file lama diganti nama menjadi <id>.data.<updated_at-lama>.zip (tidak dihapus).
Setiap ZIP diperiksa (zip utuh, berisi satu .json yang bisa di-parse) sebelum diberi nama akhir.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

POLA_URL = "https://s2.ketabonline.com/books/{id}/{id}.data.zip"


def berkas(data: Path, kid: int) -> Path:
    return data / "zip" / f"{kid % 1000:03d}" / f"{kid}.data.zip"


def baca_daftar(path: Path) -> list[int]:
    """ID dari file: .xlsx (kolom 'id', mis. hasil Ekspor Excel GUI), .csv (kolom 'id'), atau teks satu ID per baris."""
    if path.suffix.lower() == ".xlsx":
        import openpyxl

        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        baris = ws.iter_rows(values_only=True)
        kepala = [str(x or "").strip().lower() for x in next(baris)]
        i = kepala.index("id")
        return [int(r[i]) for r in baris if r[i] not in (None, "")]
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return [int(r["id"]) for r in csv.DictReader(f) if (r.get("id") or "").strip()]
    return [int(x) for x in re.findall(r"\d+", path.read_text())]


def pilih(data: Path, status: list[str] | None, sumber: str | None, ids: list[int] | None) -> list[dict]:
    con = sqlite3.connect(f"file:{data / 'hasil.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    syarat, nilai = [], []
    if ids:
        syarat.append(f"id IN ({','.join('?' * len(ids))})")
        nilai += ids
    if status:
        syarat.append(f"status IN ({','.join('?' * len(status))})")
        nilai += status
    if sumber:
        syarat.append("sumber = ?")
        nilai.append(sumber)
    where = ("WHERE " + " AND ".join(syarat)) if syarat else ""
    hasil = []
    for r in con.execute(f"SELECT id, judul, status, halaman, zip_mb, diperbarui, mentah FROM kitab {where} ORDER BY id", nilai):
        m = json.loads(r["mentah"])
        url = (((m.get("files") or {}).get("data") or {}).get("url")) or POLA_URL.format(id=r["id"])
        hasil.append({"id": r["id"], "judul": r["judul"], "status": r["status"], "halaman": r["halaman"] or 0,
                      "zip_mb": r["zip_mb"] or 0, "diperbarui": r["diperbarui"], "url": url})
    con.close()
    return hasil


def catatan(data: Path) -> dict[int, dict]:
    """Catatan terakhir per ID dari unduhan.jsonl."""
    p = data / "unduhan.jsonl"
    hasil: dict[int, dict] = {}
    if p.is_file():
        with p.open(encoding="utf-8") as f:
            for b in f:
                if b.strip():
                    d = json.loads(b)
                    hasil[d["id"]] = d
    return hasil


def periksa_zip(isi: bytes) -> str:
    """Kembalikan nama file .json di dalam ZIP; lempar ValueError bila rusak."""
    try:
        z = zipfile.ZipFile(io.BytesIO(isi))
    except zipfile.BadZipFile as e:
        raise ValueError(f"bukan ZIP: {e}") from e
    rusak = z.testzip()
    if rusak:
        raise ValueError(f"entri rusak: {rusak}")
    nama = [n for n in z.namelist() if n.endswith(".json")]
    if len(nama) != 1:
        raise ValueError(f"isi ZIP tidak terduga: {z.namelist()[:5]}")
    json.loads(z.read(nama[0]))
    return nama[0]


def _get(url: str, batas_waktu: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=batas_waktu).read()


def perlu(k: dict, lama: dict | None, data: Path) -> bool:
    return not (lama and lama.get("hasil") == "ok" and lama.get("updated_at") == k["diperbarui"]
                and berkas(data, k["id"]).is_file())


def jalankan(data: Path, daftar: list[dict], jeda: float = 1.5, ambil=_get, cetak=print) -> dict:
    lama = catatan(data)
    antre = [k for k in daftar if perlu(k, lama.get(k["id"]), data)]
    hitung = {"dipilih": len(daftar), "sudah_ada": len(daftar) - len(antre), "ok": 0, "tidak_ada": 0, "gagal": 0,
              "byte": 0}
    cetak(f"{len(daftar)} kitab dipilih, {hitung['sudah_ada']} sudah terunduh, {len(antre)} akan diunduh "
          f"(±{sum(k['zip_mb'] for k in antre):.0f} MB)")
    with (data / "unduhan.jsonl").open("a", encoding="utf-8") as log:
        for n, k in enumerate(antre, 1):
            tujuan = berkas(data, k["id"])
            d = {"id": k["id"], "updated_at": k["diperbarui"], "url": k["url"],
                 "waktu": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            for coba in range(4):
                try:
                    isi = ambil(k["url"])
                    periksa_zip(isi)
                    tujuan.parent.mkdir(parents=True, exist_ok=True)
                    if tujuan.exists():   # versi lama: simpan, jangan ditimpa
                        cap = re.sub(r"\D", "", str((lama.get(k["id"]) or {}).get("updated_at") or "lama"))
                        tujuan.rename(tujuan.with_name(f"{k['id']}.data.{cap or 'lama'}.zip"))
                    sementara = tujuan.with_suffix(".zip.sebagian")
                    sementara.write_bytes(isi)
                    sementara.rename(tujuan)
                    d.update(hasil="ok", byte=len(isi), sha256=hashlib.sha256(isi).hexdigest())
                    hitung["ok"] += 1
                    hitung["byte"] += len(isi)
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        d.update(hasil="tidak_ada", galat="HTTP 404")
                        hitung["tidak_ada"] += 1
                        break
                    d.update(hasil="gagal", galat=f"HTTP {e.code}")
                except Exception as e:  # noqa: BLE001 - jaringan / ZIP rusak: ulang dengan jeda
                    d.update(hasil="gagal", galat=f"{type(e).__name__}: {e}")
                time.sleep(jeda * 10 * (coba + 1))
            else:
                hitung["gagal"] += 1
            log.write(json.dumps(d, ensure_ascii=False) + "\n")
            log.flush()
            if n % 25 == 0 or n == len(antre):
                cetak(f"{n}/{len(antre)}  ok {hitung['ok']}  404 {hitung['tidak_ada']}  gagal {hitung['gagal']}  "
                      f"{hitung['byte'] / 1e6:.0f} MB")
            time.sleep(jeda)
    return hitung

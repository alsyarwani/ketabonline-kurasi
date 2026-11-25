"""Cocokkan katalog ketabonline dengan Syamilah 4 (Excel seleksi, sheet Buku) dan GoldenShamela (kitab_golden).

Masukan (semua hanya dibaca):
    <data>/kitab.jsonl, kategori.jsonl, pengarang.jsonl   hasil sensus
    Excel seleksi v4 (sheet "Buku": ID Syamilah, Judul, Pengarang, Keputusan, Kategori, Wafat (H))
    <data>/golden.csv   ekspor kitab_golden (golden_id, judul, pengarang, wafat_h, kategori, jumlah_halaman,
                        dup_syamilah_id); boleh tidak ada -> pencocokan Golden dilewati

Keluaran: <data>/hasil.db (SQLite; ditulis ke file sementara lalu diganti sekaligus, aman dibaca GUI saat jalan)
dan <data>/hasil.csv.

Status per kitab ketabonline:
    syamilah4  judul sama persis (setelah normalisasi) dengan kitab Syamilah 4, pengarang tidak bertentangan
    golden     judul sama persis dengan kitab GoldenShamela (dan tidak ada di Syamilah 4)
    mirip      hanya cocok longgar, atau judul sama tetapi pengarang berbeda -> perlu ditinjau
    baru       tidak ditemukan di keduanya
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .normal import bersih, longgar, norm, pengarang_sama
from .sensus import sumber

STATUS = ("baru", "mirip", "golden", "syamilah4")


@dataclass
class Calon:
    id: int
    judul: str
    pengarang: str | None
    keterangan: str | None = None   # keputusan seleksi (S4) / dup_syamilah_id (Golden)


class Indeks:
    """Indeks judul -> calon, dua tingkat: persis (norm) dan longgar."""

    def __init__(self, calon: list[Calon]):
        self.persis: dict[str, list[Calon]] = {}
        self.longgar: dict[str, list[Calon]] = {}
        for c in calon:
            for kunci, tempat in ((norm(c.judul), self.persis), (longgar(c.judul), self.longgar)):
                if kunci:
                    tempat.setdefault(kunci, []).append(c)
        self.jumlah = len(calon)

    def cari(self, judul: str, pengarang: str | None) -> tuple[Calon | None, str | None, bool | None]:
        """(calon terbaik, cara 'persis'/'longgar', pengarang_sama)."""
        for cara, kunci, tempat in (("persis", norm(judul), self.persis), ("longgar", longgar(judul), self.longgar)):
            daftar = tempat.get(kunci) if kunci else None
            if not daftar:
                continue
            nilai = [(c, pengarang_sama(pengarang, c.pengarang)) for c in daftar]
            # urutan: pengarang cocok > tidak bisa dinilai > berbeda
            nilai.sort(key=lambda x: {True: 0, None: 1, False: 2}[x[1]])
            return nilai[0][0], cara, nilai[0][1]
        return None, None, None


# ---------------------------------------------------------------- masukan

def baca_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(b) for b in f if b.strip()]


def peta_kategori(data: Path) -> dict[int, str]:
    hasil: dict[int, str] = {}

    def jalan(xs, induk=None):
        for x in xs or []:
            nama = bersih(x.get("name"))
            hasil[x["id"]] = f"{induk} › {nama}" if induk else nama
            jalan(x.get("children"), nama)

    jalan(baca_jsonl(data / "kategori.jsonl"))
    return hasil


def baca_excel(path: Path | None) -> list[Calon]:
    if not path or not path.is_file():
        return []
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    baris = wb["Buku"].iter_rows(values_only=True)
    kepala = [str(x or "").strip() for x in next(baris)]
    i = {k: kepala.index(k) for k in ("ID Syamilah", "Judul", "Pengarang", "Keputusan") if k in kepala}
    hasil = []
    for r in baris:
        if r[i["ID Syamilah"]] in (None, "") or not r[i["Judul"]]:
            continue
        hasil.append(Calon(int(r[i["ID Syamilah"]]), str(r[i["Judul"]]),
                           str(r[i["Pengarang"]] or "") if "Pengarang" in i else None,
                           str(r[i["Keputusan"]] or "") if "Keputusan" in i else None))
    return hasil


def baca_golden(path: Path | None) -> list[Calon]:
    if not path or not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [Calon(int(r["golden_id"]), r.get("judul") or "", r.get("pengarang") or None,
                      r.get("dup_syamilah_id") or None)
                for r in csv.DictReader(f) if r.get("golden_id")]


def pengarang_ketab(b: dict) -> str | None:
    nama = [bersih(a.get("name")) for a in b.get("authors") or [] if a.get("name")]
    if nama:
        return " ، ".join(nama)
    for m in b.get("meta") or []:
        if m.get("name") in ("المؤلف", "Author", "المؤلفون"):
            return bersih(m.get("value")) or None
    return None


# ---------------------------------------------------------------- proses

SKEMA = """
CREATE TABLE kitab (
    id integer PRIMARY KEY, judul text, pengarang text, sumber text, kategori text, bahasa text,
    halaman integer, jilid integer, zip_mb real, aktif integer, diperbarui text,
    deskripsi text, bibliografi text, status text,
    s4_id integer, s4_judul text, s4_pengarang text, s4_keputusan text, s4_cara text, s4_pengarang_sama integer,
    golden_id integer, golden_judul text, golden_pengarang text, golden_dup_s4 text, golden_cara text,
    golden_pengarang_sama integer, cari text, mentah text
);
CREATE INDEX kitab_status ON kitab (status);
CREATE INDEX kitab_sumber ON kitab (sumber);
CREATE TABLE info (kunci text PRIMARY KEY, nilai text);
"""


def _b(x: bool | None):
    return None if x is None else int(x)


def nilai_status(s4: tuple, gd: tuple) -> str:
    (c4, cara4, sama4), (cg, carag, samag) = s4, gd
    if c4 and cara4 == "persis" and sama4 is not False:
        return "syamilah4"
    if cg and carag == "persis" and samag is not False:
        return "golden"
    if c4 or cg:
        return "mirip"
    return "baru"


def baris_kitab(b: dict, kategori: dict[int, str], s4: Indeks, golden: Indeks) -> tuple:
    judul = bersih(b.get("title")) or f"#{b.get('id')}"
    peng = pengarang_ketab(b)
    h4, hg = s4.cari(judul, peng), golden.cari(judul, peng)
    c4, cg = h4[0], hg[0]
    kat = " · ".join(kategori.get(c.get("id"), str(c.get("id"))) for c in b.get("categories") or [])
    ukuran = ((b.get("files") or {}).get("data") or {}).get("size") or 0
    return (
        b.get("id"), judul, peng, sumber(b), kat, b.get("lang"),
        b.get("pages_count"), b.get("parts_count"), round(ukuran / 1e6, 2), b.get("is_active"), b.get("updated_at"),
        bersih(b.get("description") or b.get("info")) or None, (b.get("bibliography") or "").strip() or None,
        nilai_status(h4, hg),
        c4.id if c4 else None, c4.judul if c4 else None, c4.pengarang if c4 else None,
        c4.keterangan if c4 else None, h4[1], _b(h4[2]),
        cg.id if cg else None, cg.judul if cg else None, cg.pengarang if cg else None,
        cg.keterangan if cg else None, hg[1], _b(hg[2]),
        norm(f"{b.get('id')} {judul} {peng or ''}"),
        json.dumps(b, ensure_ascii=False),
    )


def jalankan(data: Path, excel: Path | None, golden_csv: Path | None) -> dict:
    t0 = time.time()
    mentah = {}
    for b in baca_jsonl(data / "kitab.jsonl"):
        mentah[b.get("id")] = b          # baris terakhir menang bila sensus diulang
    if not mentah:
        raise SystemExit(f"{data / 'kitab.jsonl'} kosong atau tidak ada: jalankan sensus dulu")
    kategori = peta_kategori(data)
    s4 = Indeks(baca_excel(excel))
    golden = Indeks(baca_golden(golden_csv))
    print(f"ketabonline {len(mentah)} kitab | Syamilah 4 {s4.jumlah} | GoldenShamela {golden.jumlah}", flush=True)

    sementara = data / "hasil.db.baru"
    sementara.unlink(missing_ok=True)
    con = sqlite3.connect(sementara)
    con.executescript(SKEMA)
    baris = [baris_kitab(b, kategori, s4, golden) for b in mentah.values()]
    con.executemany(f"INSERT INTO kitab VALUES ({','.join('?' * len(baris[0]))})", baris)
    ringkasan = {
        "waktu": time.strftime("%Y-%m-%d %H:%M:%S"),
        "jumlah_ketab": len(baris), "jumlah_s4": s4.jumlah, "jumlah_golden": golden.jumlah,
        "excel": str(excel) if s4.jumlah else "(tidak ada)", "golden": str(golden_csv) if golden.jumlah else "(tidak ada)",
        "detik": round(time.time() - t0, 1),
    }
    for st in STATUS:
        ringkasan[f"status_{st}"] = sum(1 for r in baris if r[13] == st)
    con.executemany("INSERT INTO info VALUES (?, ?)", [(k, str(v)) for k, v in ringkasan.items()])
    con.commit()
    con.close()
    os.replace(sementara, data / "hasil.db")

    with (data / "hasil.csv.baru").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(KOLOM_EKSPOR)
        for r in baris:
            w.writerow(r[:len(KOLOM_EKSPOR)])
    os.replace(data / "hasil.csv.baru", data / "hasil.csv")
    return ringkasan


KOLOM_EKSPOR = [
    "id", "judul", "pengarang", "sumber", "kategori", "bahasa", "halaman", "jilid", "zip_mb", "aktif", "diperbarui",
    "deskripsi", "bibliografi", "status",
    "s4_id", "s4_judul", "s4_pengarang", "s4_keputusan", "s4_cara", "s4_pengarang_sama",
    "golden_id", "golden_judul", "golden_pengarang", "golden_dup_s4", "golden_cara", "golden_pengarang_sama",
]

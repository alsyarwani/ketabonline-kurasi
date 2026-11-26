import io
import json
import urllib.error
import zipfile

import openpyxl
import pytest

from ketab import cocok, unduh
from tests.test_cocok import _k, _tulis


def _zip(kid: int, isi: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{kid}.data.json", json.dumps(isi or {"id": kid, "pages": []}))
    return buf.getvalue()


@pytest.fixture
def data(tmp_path):
    baru = _k(5, "حاشية الباجوري", "إبراهيم الباجوري")
    baru["updated_at"] = "2024-01-01 00:00:00"
    baru["files"] = {"data": {"url": "https://s2.ketabonline.com/books/5/5.data.zip?1", "size": 1000}}
    _tulis(tmp_path, [baru, _k(1, "بلوغ المرام من أدلة الأحكام", "ابن حجر"), _k(1005, "كتاب نادر"),
                      _k(9, "مفقود")])
    cocok.jalankan(tmp_path, tmp_path / "seleksi.xlsx", tmp_path / "golden.csv")
    return tmp_path


def test_pilih_dan_url(data):
    d = unduh.pilih(data, ["baru"], None, None)
    assert [k["id"] for k in d] == [5, 9, 1005]
    assert d[0]["url"].endswith("5.data.zip?1")                    # URL dari katalog
    assert d[1]["url"] == unduh.POLA_URL.format(id=9)               # cadangan pola URL


def test_unduh_lewati_dan_versi(data):
    panggil = []

    def ambil(url):
        panggil.append(url)
        if "/9/" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _zip(int(url.split("/books/")[1].split("/")[0]))

    daftar = unduh.pilih(data, ["baru"], None, None)
    h = unduh.jalankan(data, daftar, jeda=0, ambil=ambil, cetak=lambda *_: None)
    assert (h["ok"], h["tidak_ada"], h["gagal"]) == (2, 1, 0)
    assert unduh.berkas(data, 1005) == data / "zip" / "005" / "1005.data.zip" and unduh.berkas(data, 1005).is_file()

    # kedua kali: yang ok dilewati, yang 404 dicoba lagi
    panggil.clear()
    unduh.jalankan(data, daftar, jeda=0, ambil=ambil, cetak=lambda *_: None)
    assert len(panggil) == 1 and "/9/" in panggil[0]

    # updated_at berubah -> unduh ulang, file lama disimpan dengan nama lain
    for k in daftar:
        if k["id"] == 5:
            k["diperbarui"] = "2025-02-02 00:00:00"
    unduh.jalankan(data, [k for k in daftar if k["id"] == 5], jeda=0, ambil=ambil, cetak=lambda *_: None)
    assert (data / "zip" / "005" / "5.data.20240101000000.zip").is_file()
    assert (data / "zip" / "005" / "5.data.zip").is_file()


def test_zip_rusak_tidak_disimpan(data, monkeypatch):
    monkeypatch.setattr(unduh.time, "sleep", lambda *_: None)
    daftar = [k for k in unduh.pilih(data, ["baru"], None, None) if k["id"] == 5]
    h = unduh.jalankan(data, daftar, jeda=0, ambil=lambda url: b"bukan zip", cetak=lambda *_: None)
    assert h["gagal"] == 1 and not unduh.berkas(data, 5).exists()
    assert json.loads((data / "unduhan.jsonl").read_text().splitlines()[-1])["hasil"] == "gagal"


def test_baca_daftar(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["id", "judul"])
    wb.active.append([5, "x"])
    wb.active.append([1005, "y"])
    wb.save(tmp_path / "d.xlsx")
    assert unduh.baca_daftar(tmp_path / "d.xlsx") == [5, 1005]
    (tmp_path / "d.txt").write_text("5\n1005, 9")
    assert unduh.baca_daftar(tmp_path / "d.txt") == [5, 1005, 9]


def test_json_rusak_tetap_diarsipkan(data):
    def ambil(url):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("5.data.json", '{"id": 5, "pages": [{"content": "terpotong')
        return buf.getvalue()

    daftar = [k for k in unduh.pilih(data, ["baru"], None, None) if k["id"] == 5]
    h = unduh.jalankan(data, daftar, jeda=0, ambil=ambil, cetak=lambda *_: None)
    assert h["json_rusak"] == 1 and h["gagal"] == 0 and unduh.berkas(data, 5).is_file()
    c = json.loads((data / "unduhan.jsonl").read_text().splitlines()[-1])
    assert c["hasil"] == "json_rusak" and "panjang" in c["galat"]
    # putaran berikutnya tidak mengunduh ulang
    panggil = []
    unduh.jalankan(data, daftar, jeda=0, ambil=lambda u: panggil.append(u) or b"", cetak=lambda *_: None)
    assert panggil == []

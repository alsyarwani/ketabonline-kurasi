import csv
import json
import sqlite3

import openpyxl
import pytest

from ketab import cocok
from ketab.normal import bersih, longgar, norm, pengarang_sama


def test_norm_sama_dengan_ekstraktor_epub():
    assert norm("الأَرْبَعُونَ النَّوَوِيَّة") == "الاربعون النوويه"
    assert norm("فتاوى") == norm("فتاوي")


def test_bersih_buang_em():
    assert bersih("<em>بلوغ</em> <em>المرام</em>") == "بلوغ المرام"


def test_longgar_buang_keterangan():
    assert longgar("الأربعون على البلدان - مخطوط") == norm("الأربعون على البلدان")
    assert longgar("بلوغ المرام من أدلة الأحكام ت فحل") == norm("بلوغ المرام من أدلة الأحكام")
    assert longgar("كتاب الأربعين (ط. دار كذا)") == norm("الأربعين")


def test_pengarang_sama():
    assert pengarang_sama("يحيى بن شرف النووي", "النووي") is True
    assert pengarang_sama("ابن حجر العسقلاني", "النووي") is False
    assert pengarang_sama(None, "النووي") is None


def _tulis(data, kitab, golden=True):
    with (data / "kitab.jsonl").open("w", encoding="utf-8") as f:
        for b in kitab:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    (data / "kategori.jsonl").write_text(json.dumps(
        {"id": 1, "name": "الفقه", "children": [{"id": 2, "name": "الفقه الشافعي"}]}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Buku"
    ws.append(["Keputusan", "ID Syamilah", "Judul", "Pengarang"])
    ws.append(["Mu'tabarah", 100, "بلوغ المرام من أدلة الأحكام", "ابن حجر العسقلاني"])
    ws.append(["Tidak", 200, "الأربعون", "الرهاوي"])
    wb.save(data / "seleksi.xlsx")
    if golden:
        with (data / "golden.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["golden_id", "shamela_id", "judul", "pengarang", "wafat_h", "kategori", "jumlah_halaman",
                        "dup_syamilah_id"])
            w.writerow([7, 10000007, "الأربعون على البلدان", "عبد القادر الرهاوي", 612, "", 19, ""])


def _k(i, judul, pengarang=None, src="المكتبة الشاملة", kat=(2,)):
    return {"id": i, "title": judul, "authors": [{"name": pengarang}] if pengarang else [],
            "source": src, "categories": [{"id": c} for c in kat], "lang": "ar", "pages_count": 10,
            "parts_count": 1, "is_active": 1, "files": {"data": {"size": 2_000_000}}, "meta": []}


@pytest.fixture
def hasil(tmp_path):
    _tulis(tmp_path, [
        _k(1, "بُلُوغ المرام من أدلة الأحكام", "ابن حجر العسقلاني"),           # persis S4
        _k(2, "الأربعون على البلدان", None, "المكتبة الشاملة الذهبية"),        # persis Golden
        _k(3, "بلوغ المرام من أدلة الأحكام ت فحل"),                           # longgar S4 -> mirip
        _k(4, "الأربعون", "النووي"),                                          # S4 persis tapi pengarang beda -> mirip
        _k(5, "حاشية الباجوري على شرح ابن قاسم", "إبراهيم الباجوري"),          # baru
        {**_k(6, "<em>كتاب</em> غريب"), "authors": [], "meta": [{"name": "المؤلف", "value": "فلان"}],
         "source": None},
    ])
    ringkas = cocok.jalankan(tmp_path, tmp_path / "seleksi.xlsx", tmp_path / "golden.csv")
    con = sqlite3.connect(tmp_path / "hasil.db")
    con.row_factory = sqlite3.Row
    return ringkas, {r["id"]: r for r in con.execute("SELECT * FROM kitab")}, tmp_path


def test_status(hasil):
    ringkas, r, _ = hasil
    assert r[1]["status"] == "syamilah4" and r[1]["s4_id"] == 100 and r[1]["s4_keputusan"] == "Mu'tabarah"
    assert r[2]["status"] == "golden" and r[2]["golden_id"] == 7
    assert r[3]["status"] == "mirip" and r[3]["s4_cara"] == "longgar"
    assert r[4]["status"] == "mirip" and r[4]["s4_pengarang_sama"] == 0
    assert r[5]["status"] == "baru" and r[5]["s4_id"] is None
    assert ringkas["status_baru"] == 2 and ringkas["jumlah_ketab"] == 6


def test_metadata(hasil):
    _, r, data = hasil
    assert r[1]["kategori"] == "الفقه › الفقه الشافعي"
    assert r[6]["judul"] == "كتاب غريب" and r[6]["pengarang"] == "فلان"
    assert r[1]["zip_mb"] == 2.0
    assert (data / "hasil.csv").read_text(encoding="utf-8-sig").startswith("id,judul")


def test_tanpa_golden(tmp_path):
    _tulis(tmp_path, [_k(2, "الأربعون على البلدان")], golden=False)
    ringkas = cocok.jalankan(tmp_path, tmp_path / "seleksi.xlsx", tmp_path / "golden.csv")
    assert ringkas["jumlah_golden"] == 0 and ringkas["status_baru"] == 1


def test_gui(hasil, monkeypatch):
    _, _, data = hasil
    from ketab import gui

    monkeypatch.setattr(gui, "DATA", data)
    c = gui.app.test_client()
    t = c.get("/")
    assert t.status_code == 200 and "الباجوري" in t.get_data(as_text=True)
    t = c.get("/?status=baru&q=باجوري")
    assert "الباجوري" in t.get_data(as_text=True) and "بلوغ" not in t.get_data(as_text=True)
    assert c.get("/kitab/5").status_code == 200
    assert c.get("/kitab/999").status_code == 404
    x = c.get("/ekspor.xlsx?status=baru")
    assert x.status_code == 200 and x.data[:2] == b"PK"

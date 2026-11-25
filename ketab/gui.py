"""GUI baca-saja untuk hasil.db: tabel kitab ketabonline + status pencocokan, filter, detail, ekspor Excel.

Tidak ada login: pasang autentikasi di gateway (jalurgateway) sebelum dibuka ke luar.
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file

from .cocok import KOLOM_EKSPOR, STATUS
from .normal import norm

DATA = Path(os.environ.get("KETAB_DATA", "/data"))
PER_HALAMAN = 100
URUT = {
    "id": "id", "judul": "judul", "halaman": "halaman DESC", "zip": "zip_mb DESC",
    "diperbarui": "diperbarui DESC", "status": "status, id",
}
LABEL_STATUS = {"baru": "Baru", "mirip": "Mirip — tinjau", "golden": "Ada di GoldenShamela",
                "syamilah4": "Ada di Syamilah 4"}

app = Flask(__name__)


@app.context_processor
def _bantu():
    def tautan(titik: str = "beranda", **ubah) -> str:
        from flask import url_for

        q = request.args.to_dict()
        q.update({k: v for k, v in ubah.items()})
        q = {k: v for k, v in q.items() if v not in (None, "")}
        return url_for(titik, **q)

    return {"tautan": tautan}


def db() -> sqlite3.Connection:
    p = DATA / "hasil.db"
    if not p.is_file():
        abort(503, "hasil.db belum ada: jalankan 'python -m ketab cocok' dulu")
    # immutable=1: file tidak pernah diubah di tempat (cocok menggantinya utuh), aman di mount :ro
    con = sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    return con


def saringan(a) -> tuple[str, list]:
    syarat, nilai = [], []
    if a.get("q"):
        for kata in norm(a["q"]).split():
            syarat.append("cari LIKE ?")
            nilai.append(f"%{kata}%")
    for kolom in ("status", "sumber", "bahasa"):
        if a.get(kolom):
            syarat.append(f"{kolom} = ?")
            nilai.append(a[kolom])
    if a.get("kategori"):
        syarat.append("kategori LIKE ?")
        nilai.append(f"%{a['kategori']}%")
    if a.get("min_hal"):
        syarat.append("halaman >= ?")
        nilai.append(int(a["min_hal"]))
    if a.get("aktif") in ("0", "1"):
        syarat.append("aktif = ?")
        nilai.append(int(a["aktif"]))
    return ("WHERE " + " AND ".join(syarat)) if syarat else "", nilai


@app.get("/")
def beranda():
    a = request.args
    where, nilai = saringan(a)
    urut = URUT.get(a.get("urut", "id"), "id")
    hal = max(1, int(a.get("hal", 1) or 1))
    with db() as con:
        total = con.execute(f"SELECT count(*) FROM kitab {where}", nilai).fetchone()[0]
        baris = con.execute(
            f"SELECT id, judul, pengarang, sumber, kategori, bahasa, halaman, jilid, zip_mb, aktif, status, "
            f"s4_id, s4_judul, s4_keputusan, s4_cara, s4_pengarang_sama, golden_id, golden_judul, golden_cara, "
            f"golden_pengarang_sama FROM kitab {where} ORDER BY {urut} LIMIT ? OFFSET ?",
            [*nilai, PER_HALAMAN, (hal - 1) * PER_HALAMAN]).fetchall()
        info = dict(con.execute("SELECT kunci, nilai FROM info").fetchall())
        matriks = con.execute(
            "SELECT COALESCE(sumber,'(tanpa sumber)') s, status, count(*) n, COALESCE(sum(halaman),0) h "
            "FROM kitab GROUP BY 1, 2").fetchall()
        sumber = [r[0] for r in con.execute("SELECT sumber FROM kitab WHERE sumber IS NOT NULL "
                                            "GROUP BY 1 ORDER BY count(*) DESC")]
        bahasa = [r[0] for r in con.execute("SELECT bahasa FROM kitab WHERE bahasa IS NOT NULL "
                                            "GROUP BY 1 ORDER BY count(*) DESC")]
    tabel: dict[str, dict] = {}
    for r in matriks:
        tabel.setdefault(r["s"], {})[r["status"]] = (r["n"], r["h"])
    return render_template("index.html", baris=baris, total=total, hal=hal, per=PER_HALAMAN, a=a, info=info,
                           tabel=tabel, status=STATUS, label=LABEL_STATUS, sumber=sumber, bahasa=bahasa,
                           urut=list(URUT))


@app.get("/kitab/<int:kid>")
def detail(kid: int):
    with db() as con:
        r = con.execute("SELECT * FROM kitab WHERE id = ?", (kid,)).fetchone()
    if r is None:
        abort(404)
    mentah = json.loads(r["mentah"])
    return render_template("detail.html", r=r, label=LABEL_STATUS,
                           mentah=json.dumps(mentah, ensure_ascii=False, indent=1))


@app.get("/ekspor.xlsx")
def ekspor():
    import openpyxl

    where, nilai = saringan(request.args)
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("ketabonline")
    ws.append(KOLOM_EKSPOR)
    with db() as con:
        for r in con.execute(f"SELECT {', '.join(KOLOM_EKSPOR)} FROM kitab {where} ORDER BY id", nilai):
            ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="ketabonline_saringan.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/sehat")
def sehat():
    return {"ok": (DATA / "hasil.db").is_file()}


def mulai(host: str = "0.0.0.0", port: int = 8000) -> None:
    from waitress import serve

    print(f"GUI ketabonline di http://{host}:{port} (data {DATA})", flush=True)
    serve(app, host=host, port=port, threads=8)

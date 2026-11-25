"""python -m ketab <perintah>

    sensus [kitab|kategori|pengarang]   tarik metadata katalog ketabonline ke KETAB_DATA (bisa dilanjutkan)
    ringkas                             ringkasan per sumber dari kitab.jsonl
    cocok                               bandingkan dengan Syamilah 4 (KETAB_EXCEL) & GoldenShamela (KETAB_GOLDEN)
    gui [--port 8000]                   jalankan GUI baca-saja
    unduh [--status baru,mirip] [--sumber S] [--daftar file.xlsx] [--jeda 1.5] [--perkiraan]
                                        unduh {id}.data.zip terpilih ke <data>/zip/ (lewati yang sudah ada)

Lingkungan: KETAB_DATA (bawaan /data), KETAB_EXCEL, KETAB_GOLDEN (bawaan <data>/golden.csv).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(prog="ketab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("perintah", choices=["sensus", "ringkas", "cocok", "gui", "unduh"])
    p.add_argument("jenis", nargs="?", choices=["kitab", "kategori", "pengarang"])
    p.add_argument("--status", default="baru", help="unduh: status dipisah koma (baru,mirip,golden,syamilah4) atau 'semua'")
    p.add_argument("--sumber", help="unduh: hanya sumber ini (mis. 'المكتبة الشاملة')")
    p.add_argument("--daftar", help="unduh: file ID (.xlsx hasil Ekspor GUI, .csv kolom id, atau teks)")
    p.add_argument("--jeda", type=float, default=1.5, help="unduh: detik antar-kitab")
    p.add_argument("--perkiraan", action="store_true", help="unduh: hanya hitung jumlah & ukuran, tidak mengunduh")
    p.add_argument("--data", default=os.environ.get("KETAB_DATA", "/data"))
    p.add_argument("--excel", default=os.environ.get("KETAB_EXCEL"))
    p.add_argument("--golden", default=os.environ.get("KETAB_GOLDEN"))
    p.add_argument("--port", type=int, default=int(os.environ.get("KETAB_PORT", "8000")))
    a = p.parse_args()
    a.status_diberikan = any(x == "--status" or x.startswith("--status=") for x in sys.argv[1:])
    data = Path(a.data)

    if a.perintah == "sensus":
        from . import sensus

        for j in ([a.jenis] if a.jenis else ["kategori", "pengarang", "kitab"]):
            sensus.tarik(data, j)
        sensus.ringkas(data)
    elif a.perintah == "ringkas":
        from . import sensus

        sensus.ringkas(data)
    elif a.perintah == "cocok":
        from . import cocok

        golden = Path(a.golden) if a.golden else data / "golden.csv"
        hasil = cocok.jalankan(data, Path(a.excel) if a.excel else None, golden)
        for k, v in hasil.items():
            print(f"{k:16} {v}")
    elif a.perintah == "unduh":
        from . import unduh

        status = None if a.status == "semua" else [s.strip() for s in a.status.split(",") if s.strip()]
        ids = unduh.baca_daftar(Path(a.daftar)) if a.daftar else None
        if a.daftar and not a.status_diberikan:
            status = None   # --daftar tanpa --status: ambil semua ID di daftar apa pun statusnya
        daftar = unduh.pilih(data, status, a.sumber, ids)
        lama = unduh.catatan(data)
        antre = [k for k in daftar if unduh.perlu(k, lama.get(k["id"]), data)]
        print(f"dipilih {len(daftar)} kitab, {sum(k['halaman'] for k in daftar):,} halaman, "
              f"{sum(k['zip_mb'] for k in daftar):,.0f} MB | belum terunduh {len(antre)} kitab, "
              f"{sum(k['zip_mb'] for k in antre):,.0f} MB | perkiraan waktu ±{len(antre) * (a.jeda + 1) / 60:,.0f} menit")
        if not a.perkiraan:
            for k, v in unduh.jalankan(data, daftar, a.jeda).items():
                print(f"{k:10} {v}")
    else:
        os.environ["KETAB_DATA"] = str(data)
        from . import gui

        gui.mulai(port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

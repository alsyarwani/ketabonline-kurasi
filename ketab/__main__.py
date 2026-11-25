"""python -m ketab <perintah>

    sensus [kitab|kategori|pengarang]   tarik metadata katalog ketabonline ke KETAB_DATA (bisa dilanjutkan)
    ringkas                             ringkasan per sumber dari kitab.jsonl
    cocok                               bandingkan dengan Syamilah 4 (KETAB_EXCEL) & GoldenShamela (KETAB_GOLDEN)
    gui [--port 8000]                   jalankan GUI baca-saja

Lingkungan: KETAB_DATA (bawaan /data), KETAB_EXCEL, KETAB_GOLDEN (bawaan <data>/golden.csv).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(prog="ketab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("perintah", choices=["sensus", "ringkas", "cocok", "gui"])
    p.add_argument("jenis", nargs="?", choices=["kitab", "kategori", "pengarang"])
    p.add_argument("--data", default=os.environ.get("KETAB_DATA", "/data"))
    p.add_argument("--excel", default=os.environ.get("KETAB_EXCEL"))
    p.add_argument("--golden", default=os.environ.get("KETAB_GOLDEN"))
    p.add_argument("--port", type=int, default=int(os.environ.get("KETAB_PORT", "8000")))
    a = p.parse_args()
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
    else:
        os.environ["KETAB_DATA"] = str(data)
        from . import gui

        gui.mulai(port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Sensus metadata katalog ketabonline (tanpa mengunduh isi kitab).

Menyimpan item API APA ADANYA (ditambah "_halaman_api") ke <data>/kitab.jsonl, kategori.jsonl, pengarang.jsonl.
Bisa dihentikan & dilanjutkan: nomor halaman API yang sudah tersimpan dicatat di <jenis>.selesai.
Untuk sensus ulang dari nol, pindahkan dulu ketiga file .jsonl & .selesai ke folder lain.
"""
from __future__ import annotations

import collections
import json
import time
import urllib.request
from pathlib import Path

API = "https://backend.ketabonline.com/api/v2"
TITIK = {"kitab": "books", "kategori": "categories", "pengarang": "authors"}
BATAS = 50     # item per halaman API
JEDA = 1.0     # detik antar-request


def _get(url: str) -> dict:
    for coba in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception as e:  # noqa: BLE001 - jaringan: ulang dengan jeda makin lama
            print("ulang", coba + 1, url, e, flush=True)
            time.sleep(15 * (coba + 1))
    raise SystemExit(f"gagal terus: {url}")


def tarik(data: Path, jenis: str) -> None:
    out, cat = data / f"{jenis}.jsonl", data / f"{jenis}.selesai"
    sudah = set(cat.read_text().split()) if cat.exists() else set()
    r = _get(f"{API}/{TITIK[jenis]}?page=1&limit={BATAS}")
    meta = r.get("meta") or {}
    akhir = int(meta.get("last_page") or 1)
    print(f"[{jenis}] total {meta.get('total')}, {akhir} halaman API", flush=True)
    with out.open("a", encoding="utf-8") as f, cat.open("a") as s:
        for n in range(1, akhir + 1):
            if str(n) in sudah:
                continue
            isi = (r if n == 1 else _get(f"{API}/{TITIK[jenis]}?page={n}&limit={BATAS}")).get("data") or []
            for b in isi:
                b["_halaman_api"] = n
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
            f.flush()
            s.write(f"{n}\n")
            s.flush()
            if n % 50 == 0 or n == akhir:
                print(f"[{jenis}] {n}/{akhir}", flush=True)
            time.sleep(JEDA)


def sumber(b: dict) -> str | None:
    if b.get("source"):
        return b["source"]
    for m in b.get("meta") or []:
        if m.get("name") in ("المصدر", "Source"):
            return m.get("value")
    return None


def ringkas(data: Path) -> None:
    kitab = {}
    with (data / "kitab.jsonl").open(encoding="utf-8") as f:
        for baris in f:
            b = json.loads(baris)
            kitab[b.get("id")] = b
    n_src, n_hal, n_mb = collections.Counter(), collections.Counter(), collections.Counter()
    for b in kitab.values():
        k = sumber(b) or "(tanpa sumber)"
        n_src[k] += 1
        n_hal[k] += b.get("pages_count") or 0
        n_mb[k] += (((b.get("files") or {}).get("data") or {}).get("size") or 0) / 1e6
    print(f"\n{len(kitab)} kitab unik")
    print(f"{'sumber':40} {'kitab':>7} {'halaman':>11} {'zip MB':>8}")
    for k, n in n_src.most_common(30):
        print(f"{k[:40]:40} {n:7} {n_hal[k]:11} {n_mb[k]:8.0f}")
    print("bahasa:", collections.Counter(b.get("lang") for b in kitab.values()).most_common(10))

"""Normalisasi judul/nama untuk pencocokan.

`norm` SAMA dengan `_norm` di ekstraktor-epub dan alat/pilah_pdf.py (abaikan harakat, tatwil, variasi
hamzah/ya/ta marbutah, tanda baca), supaya hasil pencocokan konsisten di semua alat.
"""
from __future__ import annotations

import re

_EM = re.compile(r"</?em>", re.I)
_TAG = re.compile(r"<[^>]+>")
# Keterangan di akhir/di dalam judul yang sering beda antar-edisi: (…) […] «…», "- مخطوط", "ت فحل", "ط 2"
_KURUNG = re.compile(r"\([^)]*\)|\[[^\]]*\]|«[^»]*»|\{[^}]*\}")
_EKOR = re.compile(r"\s[-–ـ]\s.*$|\s(?:ت|ط|تحقيق|بتحقيق|ط\.)\s.*$")
_KATA_UMUM = {"كتاب", "رساله", "متن", "الكتاب", "جزء", "ج"}


def bersih(t: str | None) -> str:
    """Buang tag sorotan <em> dari hasil pencarian API dan tag HTML lain."""
    return _TAG.sub("", _EM.sub("", t or "")).strip()


def norm(t: str | None) -> str:
    t = re.sub(r"[ً-ٰٟـ]", "", t or "")
    t = re.sub(r"[أإآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def longgar(t: str | None) -> str:
    """Kunci pencocokan longgar: tanpa isi kurung, tanpa ekor "- …"/"ت …", tanpa kata umum di depan.
    Hasilnya hanya dipakai sebagai kandidat 'mirip' yang perlu ditinjau manusia."""
    t = bersih(t)
    t = _KURUNG.sub(" ", t)
    t = _EKOR.sub("", f" {t.strip()}").strip()
    kata = norm(t).split()
    while kata and kata[0] in _KATA_UMUM:
        kata = kata[1:]
    return " ".join(kata)


def token(t: str | None) -> set[str]:
    """Token nama untuk membandingkan pengarang (buang kata sambung dan "ال")."""
    hasil = set()
    for k in norm(t).split():
        if k in {"بن", "ابن", "ابو", "ابي", "عبد", "بنت", "ام", "د", "الشيخ", "الامام"}:
            continue
        if k.startswith("ال") and len(k) > 3:
            k = k[2:]
        if len(k) > 1:
            hasil.add(k)
    return hasil


def pengarang_sama(a: str | None, b: str | None) -> bool | None:
    """True/False bila keduanya ada; None bila salah satu kosong (tidak bisa dinilai)."""
    ta, tb = token(a), token(b)
    if not ta or not tb:
        return None
    return len(ta & tb) >= 1

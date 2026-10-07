"""
adapter.py -- jembatan format.

Mengembalikan hasil MESIN GABUNGAN (matcher kriteria SDKI mayor/minor +
deteksi konteks kardiovaskular & boost numerik) dalam bentuk dict yang SAMA
seperti `analyze_clinical_trends_improved()` CDSS 2.0 lama, sehingga UI
dashboard tidak perlu diubah.

Bedanya: seluruh data (diagnosa, KODE yang benar, luaran SLKI, intervensi
SIKI) berasal dari SATU sumber -- master JSON di `data/sdki_slki_siki.json` --
bukan lagi tabel keyword tertanam di dashboard yang kodenya sempat keliru.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Any, Dict, List

from .repository import SdkiRepository
# Pencocok kriteria milik mesin itu sendiri, dipakai ulang HANYA untuk menandai
# kriteria mana yang terpenuhi (tampilan) -- supaya tanda ✓ selalu sama dengan
# pencocokan yang masuk ke skor, bukan pencocok kedua yang bisa berbeda.
from .repository import _ekstrak_vital, _nilai_kelompok, _tokenize

_log = logging.getLogger(__name__)

_REPO: SdkiRepository | None = None
_LOCK = threading.Lock()


def get_repository() -> SdkiRepository:
    """Singleton repository (cache master data & bobot di proses)."""
    global _REPO
    if _REPO is None:
        with _LOCK:
            if _REPO is None:
                _REPO = SdkiRepository()
    return _REPO


_KAT = (("observasi", "Observasi"), ("terapeutik", "Terapeutik"),
        ("edukasi", "Edukasi"), ("kolaborasi", "Kolaborasi"))


def _prioritas(skor: float) -> str:
    """Peta skor relatif -> label prioritas untuk pewarnaan/urutan UI."""
    if skor >= 8:
        return "CRITICAL"
    if skor >= 4:
        return "HIGH"
    if skor >= 2:
        return "MEDIUM"
    return "LOW"


_KELOMPOK_KRITERIA = ("mayor", "minor", "faktor_risiko")


def _cek_kriteria(repo: SdkiRepository, teks: str,
                  entry: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Tandai tiap kriteria SDKI (mayor / minor / faktor risiko): terpenuhi oleh
    data S/O atau belum.

    Memakai `_nilai_kelompok` milik mesin per kriteria, sehingga hasilnya
    identik dengan pencocokan yang dihitung ke skor (termasuk penjaga arah
    vital & anti-negasi). Murni tampilan: skor dan urutan tidak berubah.
    Kembar dengan `DiagnosisService.cek_kriteria()` di aplikasi asuhan.
    """
    kriteria = entry.get("kriteria") or {}
    hasil = {
        kunci: [{"teks": str(k), "cocok": False} for k in (kriteria.get(kunci) or [])]
        for kunci in _KELOMPOK_KRITERIA
    }
    try:
        tokens = _tokenize(teks)
        if tokens:
            vital = _ekstrak_vital(teks)
            bobot = repo._bobot_kata()
            bawaan = math.log(1 + len(repo._entries()))
            for daftar in hasil.values():
                for k in daftar:
                    k["cocok"] = _nilai_kelompok(
                        [k["teks"]], tokens, vital, bobot, bawaan)[3] > 0
    except Exception:  # tampilan saja -- jangan gagalkan CDSS
        _log.warning("Gagal menandai kriteria SDKI", exc_info=True)
    return hasil


def _rencana_intervensi(intervensi: Dict[str, list]) -> Dict[str, str]:
    """{observasi/terapeutik/edukasi/kolaborasi:[...]} -> dict 4 kolom (string)."""
    out: Dict[str, str] = {}
    for src, label in _KAT:
        items = intervensi.get(src) or []
        out[label] = "; ".join(str(i) for i in items) if items else "-"
    return out


def analyze_clinical_trends_improved(s_input: str, o_input: str) -> Dict[str, Any]:
    """
    Drop-in pengganti fungsi CDSS 2.0. Menerima Subjektif & Objektif,
    mengembalikan dict: status, analisis (ringkasan konteks), clinical_context,
    numeric_findings, recommendations[ {code, name, score, priority, luaran,
    kode_diagnosa, diagnosa_keperawatan, luaran_keperawatan, rencana_intervensi,
    jenis, mayor_cocok, mayor_total, kriteria_cek} ].

    `kriteria_cek` = kriteria mayor/minor/faktor risiko dari master, masing-
    masing ditandai terpenuhi/belum oleh S/O (untuk tampilan ranking CDSS).
    """
    repo = get_repository()
    s_input = (s_input or "").strip()
    o_input = (o_input or "").strip()
    teks = (s_input + "\n" + o_input).strip()

    if not teks:
        return {"status": "success", "engine": "SmartCarePlan-gabungan",
                "analisis": "", "numeric_findings": {}, "numeric_interpretation": {},
                "clinical_context": {}, "recommendations": []}

    kk = repo.konteks_klinis(teks)
    usulan = repo.suggest(teks, limit=8)

    recs: List[Dict[str, Any]] = []
    for u in usulan:
        kode = u["kode"]
        skor = float(u.get("skor", 0.0))
        luaran = repo.get_luaran(kode) or {}
        intervensi = repo.get_intervensi(kode) or {}
        luaran_str = (f"{luaran.get('nama', '')} ({luaran.get('kode', '')})".strip()
                      if luaran.get("nama") else "")
        entry = u.get("diagnosis") or repo.find(kode) or {}
        recs.append({
            "code": kode,
            "name": u.get("nama", ""),
            "score": round(skor, 2),
            "priority": _prioritas(skor),
            "base_keywords": bool(u.get("mayor_cocok")),
            "numeric_boost": u.get("numerik_boost", 0),
            "cardiac_context_boost": u.get("konteks_boost", 0),
            "dari_konteks": bool(u.get("dari_konteks")),
            "alasan": u.get("kata_cocok", []),
            "jenis": entry.get("jenis", ""),
            "mayor_cocok": int(u.get("mayor_cocok") or 0),
            "mayor_total": int(u.get("mayor_total") or 0),
            "kriteria_cek": _cek_kriteria(repo, teks, entry),
            "luaran": {"kode": luaran.get("kode", ""), "nama": luaran.get("nama", "")},
            # Field yang dulu diisi bridge_engine dari tabel lokal kode-lama;
            # kini dari master JSON (satu sumber kebenaran):
            "kode_diagnosa": kode,
            "diagnosa_keperawatan": u.get("nama", ""),
            "luaran_keperawatan": luaran_str,
            "rencana_intervensi": _rencana_intervensi(intervensi),
        })

    return {
        "status": "success",
        "engine": "SmartCarePlan gabungan (kriteria SDKI + konteks kardiovaskular)",
        "analisis": kk.get("ringkasan", ""),
        "numeric_findings": kk.get("numerik", {}),
        "numeric_interpretation": kk.get("numerik", {}),
        "clinical_context": kk.get("konteks", {}),
        "recommendations": recs,
    }

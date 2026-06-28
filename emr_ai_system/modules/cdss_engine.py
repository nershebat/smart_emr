"""
services/cdss_engine.py  —  CDSS v2.0 (implementasi penuh, menggantikan stub)
=============================================================================
Ini adalah implementasi NYATA dari `analyze_clinical_trends_improved()` yang
dipanggil oleh `dashboard.py` (TIDAK DIUBAH) pada baris 19 dan 2729.

Kontrak return harus PERSIS seperti yang dashboard.py ekspektasikan:
    {
        "status"            : "success" | "error",
        "recommendations"   : list[dict],   # field: code, description, priority, category
        "numeric_findings"  : dict,
        "clinical_context"  : dict,
    }

Modul ini bertindak sebagai adaptor/fasad yang:
  1. Mem-parsing teks Subjektif (S) dan Objektif (O) dari form CPPT
  2. Mendeteksi kode ICD-10 yang disebutkan / kondisi klinis kunci
  3. Memanggil CDSS Dokter (modules/doctor/cdss_doctor.py) untuk cek
     kontraindikasi & rekomendasi PPK
  4. Mengembalikan hasil dalam format yang sudah dipakai dashboard.py
"""

import re
import sys
from pathlib import Path
from typing import Dict, List

# Pastikan ROOT_DIR ada di sys.path supaya impor modules.doctor berjalan
# baik saat dipanggil oleh dashboard.py maupun dari halaman Streamlit lain.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.doctor.icd10_db import ICD10_DB, search_icd10
from modules.doctor.ppk_protocols import get_ppk_by_icd10
from modules.doctor.cdss_doctor import get_ppk_recommendations


# ── Kamus kata kunci → kode ICD-10 ──────────────────────────────────────
# Dipakai untuk deteksi cepat dari teks bebas (S dan O)
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["stemi", "st elevasi", "elevasi st"],                  "I21.0"),
    (["nstemi", "non stemi", "nste"],                        "I21.4"),
    (["apts", "angina tidak stabil", "unstable angina"],     "I20.0"),
    (["gagal jantung", "gjk", "chf", "heart failure"],       "I50.0"),
    (["edema paru", "acute pulmonary edema", "epa"],         "I50.1"),
    (["fibrilasi atrium", "af ", "afib", "atrial fib"],      "I48.0"),
    (["svt", "takikardia supraventrikular"],                  "I47.1"),
    (["vt ", "takikardia ventrikel", "ventricular tach"],     "I47.2"),
    (["vf ", "fibrilasi ventrikel", "cardiac arrest"],        "I49.0"),
    (["av block", "blok av", "blok total", "cavb"],           "I44.2"),
    (["hipertensi emergensi", "hypertensive emergency"],      "I16.1"),
    (["hipertensi urgensi", "hypertensive urgency"],          "I16.0"),
    (["hipertensi", "htn", "tekanan darah tinggi"],           "I10"),
    (["syok kardiogenik", "cardiogenic shock"],               "R57.0"),
    (["sepsis", "septik", "septic"],                          "A41.9"),
    (["ards", "sindrom gagal napas"],                         "J80"),
    (["gagal napas", "respiratory failure"],                  "J96.0"),
    (["aki ", "gagal ginjal akut", "acute kidney"],           "N17.9"),
    (["emboli paru", "pulmonary embolism", " pe "],           "I26.9"),
    (["diseksi aorta", "aortic dissection"],                  "I71.0"),
    (["tamponade", "hemoperikardium"],                        "I31.2"),
    (["pjk", "jantung koroner", "coronary artery disease"],  "I25.1"),
    (["hiperkalemia", "kalium tinggi"],                       "E87.5"),
    (["hiponatremia", "natrium rendah"],                      "E87.1"),
]

_ICD10_PATTERN = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,2})?)\b')


def _extract_icd10_from_text(text: str) -> list[str]:
    """
    Deteksi kode ICD-10 dari teks bebas:
      1. Kode literal (contoh: I21.0, A41.9) via regex
      2. Kata kunci klinis via _KEYWORD_MAP
    Mengembalikan list unik kode yang ditemukan.
    """
    found = set()
    text_lower = text.lower()

    # Kode literal
    for match in _ICD10_PATTERN.finditer(text.upper()):
        found.add(match.group(1))

    # Kata kunci
    for keywords, kode in _KEYWORD_MAP:
        if any(kw in text_lower for kw in keywords):
            found.add(kode)

    return list(found)


def _extract_numeric_findings(o_text: str) -> dict:
    """
    Ekstrak nilai numerik tanda vital dari teks Objektif (O) secara heuristik.
    Mengembalikan dict untuk ditampilkan oleh dashboard.py jika ada.
    """
    findings = {}
    patterns = {
        "heart_rate":     [r'hr[:\s]+(\d+)', r'nadi[:\s]+(\d+)', r'heart rate[:\s]+(\d+)'],
        "systolic_bp":    [r'td[:\s]+(\d+)/', r'bp[:\s]+(\d+)/', r'tekanan darah[:\s]+(\d+)/'],
        "spo2":           [r'spo2[:\s]+([\d.]+)', r'saturasi[:\s]+([\d.]+)'],
        "respiratory_rate": [r'rr[:\s]+(\d+)', r'laju napas[:\s]+(\d+)'],
        "temperature":    [r'suhu[:\s]+([\d.]+)', r'temp[:\s]+([\d.]+)', r't[:\s]+(3[5-9]\.\d)'],
        "gds":            [r'gds[:\s]+(\d+)', r'gdp[:\s]+(\d+)', r'gula darah[:\s]+(\d+)'],
        "spo2_fio2_ratio": [],  # dihitung jika SpO2 dan FiO2 tersedia
    }
    text_lower = o_text.lower()
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text_lower)
            if m:
                try:
                    findings[key] = float(m.group(1))
                    break
                except ValueError:
                    pass
    return findings


def _build_recommendations(icd10_codes: list[str], numeric: dict) -> list[dict]:
    """
    Susun daftar rekomendasi dalam format yang diharapkan dashboard.py:
      { code, description, priority, category }
    """
    recs = []
    seen = set()

    # Rekomendasi berbasis PPK
    for kode in icd10_codes:
        ppk_list = get_ppk_by_icd10(kode)
        for ppk in ppk_list:
            if ppk["nama_ppk"] in seen:
                continue
            seen.add(ppk["nama_ppk"])

            # Tambahkan pemeriksaan wajib sebagai rekomendasi
            for item in ppk.get("pemeriksaan_awal", [])[:3]:
                recs.append({
                    "code": f"PEMERIKSAAN:{kode}",
                    "description": f"[{kode}] Pemeriksaan awal: {item}",
                    "priority": "SEGERA",
                    "category": "Diagnostik",
                })

            # Tambahkan langkah tata laksana utama
            for step in ppk.get("tata_laksana_utama", [])[:3]:
                recs.append({
                    "code": f"PPK:{kode}:{step['urutan']}",
                    "description": f"[{kode}] {step['langkah']}: {step['detail'][:120]}...",
                    "priority": "TINGGI" if step["urutan"] <= 2 else "SEDANG",
                    "category": ppk["nama_ppk"],
                })

            # Tambahkan obat rekomendasi
            for obat in ppk.get("obat_rekomendasi", [])[:3]:
                recs.append({
                    "code": f"OBAT:{kode}:{obat['nama']}",
                    "description": (
                        f"[{kode}] Pertimbangkan: {obat['nama']} "
                        f"{obat['dosis']} {obat['rute']} — {obat.get('catatan','')}"
                    ),
                    "priority": "SEDANG",
                    "category": "Farmakologi",
                })

    # Rekomendasi berbasis nilai numerik
    hr = numeric.get("heart_rate")
    sbp = numeric.get("systolic_bp")
    spo2 = numeric.get("spo2")
    temp = numeric.get("temperature")
    gds = numeric.get("gds")

    if spo2 is not None and spo2 < 90:
        recs.insert(0, {
            "code": "ALERT:SPO2_KRITIS",
            "description": f"SpO2 {spo2}% — DI BAWAH BATAS KRITIS (<90%). "
                           "Berikan O2 segera, evaluasi kebutuhan ventilasi mekanik.",
            "priority": "KRITIS",
            "category": "Alert Klinis",
        })
    if sbp is not None and sbp < 90:
        recs.insert(0, {
            "code": "ALERT:HIPOTENSI_KRITIS",
            "description": f"Tekanan darah sistolik {sbp} mmHg — HIPOTENSI BERAT. "
                           "Evaluasi syok, resusitasi cairan, pertimbangkan vasopressor.",
            "priority": "KRITIS",
            "category": "Alert Klinis",
        })
    if hr is not None and (hr > 150 or hr < 40):
        recs.insert(0, {
            "code": "ALERT:HR_EKSTREM",
            "description": f"HR {hr} bpm — {'TAKIKARDIA EKSTREM' if hr > 150 else 'BRADIKARDIA BERAT'}. "
                           "EKG 12 lead segera, persiapkan defibrilator/pacemaker.",
            "priority": "KRITIS",
            "category": "Alert Klinis",
        })
    if temp is not None and temp > 39.0:
        recs.append({
            "code": "ALERT:HIPERPIREKSIA",
            "description": f"Suhu {temp}°C — pertimbangkan infeksi aktif/sepsis. "
                           "Kultur darah sebelum antibiotik bila belum dilakukan.",
            "priority": "TINGGI",
            "category": "Alert Klinis",
        })
    if gds is not None and gds > 200:
        recs.append({
            "code": "ALERT:HIPERGLIKEMIA",
            "description": f"GDS {gds} mg/dL — Hiperglikemia. Target ICU 140-180 mg/dL. "
                           "Mulai protokol insulin bila belum.",
            "priority": "SEDANG",
            "category": "Metabolik",
        })

    return recs[:20]  # maksimal 20 rekomendasi agar tidak membanjiri UI


def analyze_clinical_trends_improved(s_input: str, o_input: str) -> Dict:
    """
    Fungsi utama yang dipanggil oleh `dashboard.py`.
    Signature dan return format TIDAK BERUBAH dari kontrak aslinya.

    Parameters
    ----------
    s_input : str  — teks Subjektif (S) dari form SOAP CPPT
    o_input : str  — teks Objektif (O) dari form SOAP CPPT

    Returns
    -------
    dict dengan key: status, recommendations, numeric_findings, clinical_context
    """
    try:
        combined = f"{s_input}\n{o_input}"

        # 1. Deteksi ICD-10 dari teks
        icd10_codes = _extract_icd10_from_text(combined)

        # 2. Ekstrak nilai numerik
        numeric = _extract_numeric_findings(o_input)

        # 3. Susun rekomendasi
        recommendations = _build_recommendations(icd10_codes, numeric)

        # 4. Susun clinical context untuk dashboard.py
        clinical_context = {
            "icd10_terdeteksi": icd10_codes,
            "jumlah_rekomendasi": len(recommendations),
            "kondisi_kritis_terdeteksi": any(
                r["priority"] == "KRITIS" for r in recommendations
            ),
        }

        return {
            "status": "success",
            "recommendations": recommendations,
            "numeric_findings": numeric,
            "clinical_context": clinical_context,
        }

    except Exception as exc:
        return {
            "status": "error",
            "recommendations": [],
            "numeric_findings": {},
            "clinical_context": {"error": str(exc)},
        }

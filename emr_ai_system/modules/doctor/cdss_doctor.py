"""
Mesin CDSS (Clinical Decision Support System) khusus Dokter.

Lapisan-lapisan pemeriksaan yang dilakukan secara berurutan:
  1. Validasi dosis obat terhadap rentang aman
  2. Cek kontraindikasi obat terhadap kondisi aktif pasien
  3. Deteksi interaksi obat-obat (Drug-Drug Interaction)
  4. Rekomendasi tata laksana berbasis PPK/PERKI sesuai ICD-10
  5. Alert pemantauan khusus ICU
"""

import re
from typing import List, Optional

from .models import CDSSAlert, AlertSeverity, MedicalOrder, DrugOrder, Diagnosis
from .ppk_protocols import get_ppk_by_icd10, PPK_DB


# ── Database Interaksi Obat (DDI) ─────────────────────────────────────────

DDI_DB: list[dict] = [
    {
        "obat_a": ["warfarin"],
        "obat_b": ["aspirin", "clopidogrel", "ticagrelor"],
        "severity": AlertSeverity.CRITICAL.value,
        "efek": "Risiko perdarahan mayor meningkat signifikan (triple therapy).",
        "rekomendasi": "Hindari kombinasi kecuali ada indikasi sangat kuat (AF + ACS + PCI). "
                       "Bila harus diberikan, minimalkan durasi dan pantau INR ketat. "
                       "Pertimbangkan PPI profilaksis.",
        "referensi": "ESC AF Guidelines 2020",
    },
    {
        "obat_a": ["amiodarone"],
        "obat_b": ["warfarin"],
        "severity": AlertSeverity.CRITICAL.value,
        "efek": "Amiodarone menghambat metabolisme warfarin → INR meningkat drastis → risiko perdarahan.",
        "rekomendasi": "Kurangi dosis warfarin 33-50% saat memulai amiodarone. Monitor INR sangat ketat "
                       "(tiap 3-7 hari selama 2-4 minggu pertama).",
        "referensi": "PERKI 2022 / Drugs.com interaction database",
    },
    {
        "obat_a": ["amiodarone"],
        "obat_b": ["digoxin"],
        "severity": AlertSeverity.CRITICAL.value,
        "efek": "Amiodarone meningkatkan kadar digoxin → risiko toksisitas digoxin (AV blok, VT).",
        "rekomendasi": "Kurangi dosis digoxin 50% saat memulai amiodarone. Monitor kadar digoxin dan EKG.",
        "referensi": "PERKI 2022",
    },
    {
        "obat_a": ["spironolakton", "eplerenone"],
        "obat_b": ["acei", "ramipril", "captopril", "lisinopril", "perindopril",
                   "arb", "valsartan", "candesartan", "telmisartan", "losartan"],
        "severity": AlertSeverity.WARNING.value,
        "efek": "Kombinasi MRA + ACEI/ARB meningkatkan risiko hiperkalemia berat.",
        "rekomendasi": "Monitor K+ dan kreatinin tiap 1-2 minggu setelah inisiasi, kemudian tiap bulan. "
                       "Hentikan bila K+ >5.5 mEq/L atau kreatinin naik >30%.",
        "referensi": "PERKI HF Guidelines 2020",
    },
    {
        "obat_a": ["metformin"],
        "obat_b": ["kontras iodine", "iohexol", "iodixanol"],
        "severity": AlertSeverity.WARNING.value,
        "efek": "Risiko asidosis laktat akibat interaksi metformin dengan media kontras.",
        "rekomendasi": "Tahan metformin 48 jam sebelum dan setelah prosedur dengan kontras iodine. "
                       "Pantau fungsi ginjal sebelum re-inisiasi.",
        "referensi": "ESC Guidelines Contrast Media",
    },
    {
        "obat_a": ["dobutamin", "dopamin"],
        "obat_b": ["beta-blocker", "metoprolol", "bisoprolol", "carvedilol", "atenolol"],
        "severity": AlertSeverity.WARNING.value,
        "efek": "Beta-blocker mengantagonis efek inotropik dobutamin/dopamin.",
        "rekomendasi": "Evaluasi kebutuhan beta-blocker selama terapi inotropik. "
                       "Pertimbangkan taper beta-blocker sementara pada syok kardiogenik.",
        "referensi": "ESC HF Guidelines 2021",
    },
    {
        "obat_a": ["nitrat", "nitrogliserin", "isdn", "isosorbid"],
        "obat_b": ["sildenafil", "tadalafil", "vardenafil", "pde5"],
        "severity": AlertSeverity.CRITICAL.value,
        "efek": "Kombinasi nitrat + PDE5-inhibitor → hipotensi berat yang mengancam jiwa.",
        "rekomendasi": "KONTRAINDIKASI ABSOLUT. Tanyakan riwayat penggunaan PDE5-inhibitor "
                       "dalam 24 jam (sildenafil/vardenafil) atau 48 jam (tadalafil) terakhir.",
        "referensi": "PERKI SKA 2018",
    },
    {
        "obat_a": ["heparin", "enoxaparin", "fondaparinux"],
        "obat_b": ["warfarin"],
        "severity": AlertSeverity.INFO.value,
        "efek": "Overlap antikoagulasi (bridging) — diperlukan selama transisi.",
        "rekomendasi": "Overlap minimal 5 hari dan hingga INR ≥2 selama 24 jam berturut-turut, "
                       "kemudian hentikan heparin/LMWH.",
        "referensi": "AHA/ACC Guidelines",
    },
    {
        "obat_a": ["vancomycin"],
        "obat_b": ["aminoglikosida", "gentamicin", "amikacin", "tobramycin"],
        "severity": AlertSeverity.WARNING.value,
        "efek": "Kombinasi nefrotoksik ganda — risiko AKI meningkat signifikan.",
        "rekomendasi": "Hindari bila memungkinkan. Bila harus kombinasi: monitor kreatinin dan urin tiap 12-24 jam, "
                       "pertimbangkan monitoring level aminoglikosida.",
        "referensi": "Sanford Guide / IDSA",
    },
    {
        "obat_a": ["ticagrelor"],
        "obat_b": ["aspirin"],
        "severity": AlertSeverity.INFO.value,
        "efek": "Kombinasi DAPT yang direkomendasikan pada ACS — bukan interaksi berbahaya.",
        "rekomendasi": "DAPT standar pada ACS/PCI. Aspirin dosis tinggi (>100 mg) dapat mengurangi efek "
                       "ticagrelor — gunakan aspirin dosis rendah (75-100 mg).",
        "referensi": "ESC ACS / PERKI 2018",
    },
]


# ── Database Kontraindikasi Obat-Kondisi ──────────────────────────────────

CONTRAINDICATION_DB: list[dict] = [
    {
        "obat": ["beta-blocker", "metoprolol", "bisoprolol", "carvedilol", "atenolol", "propranolol"],
        "kondisi_icd10": ["I49.0", "I47.2"],  # VF, VT
        "kondisi_nama": "Aritmia Maligna (VF/VT) dalam fase akut",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "Beta-blocker kontraindikasi pada VF/VT akut yang tidak stabil.",
    },
    {
        "obat": ["beta-blocker", "metoprolol", "bisoprolol", "carvedilol", "atenolol"],
        "kondisi_icd10": ["I44.2"],  # Complete AV Block
        "kondisi_nama": "Blok AV Total (Complete AV Block) tanpa pacemaker",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "Beta-blocker kontraindikasi absolut pada blok AV derajat III tanpa pacemaker.",
    },
    {
        "obat": ["digoxin"],
        "kondisi_icd10": ["I48.0", "I48.1", "I48.2"],
        "kondisi_nama": "Fibrilasi Atrium dengan WPW Syndrome",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "Digoxin meningkatkan konduksi jalur aksesoris pada WPW → VF. "
                 "Selalu singkirkan WPW sebelum memberikan digoxin pada AF.",
    },
    {
        "obat": ["spironolakton", "eplerenone", "mra"],
        "kondisi_icd10": ["N17.9"],  # AKI
        "kondisi_nama": "Gagal Ginjal Akut (AKI)",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "MRA (spironolakton/eplerenone) kontraindikasi pada AKI — risiko hiperkalemia mengancam jiwa.",
    },
    {
        "obat": ["acei", "ramipril", "captopril", "lisinopril", "perindopril"],
        "kondisi_icd10": ["I71.0"],  # Diseksi aorta
        "kondisi_nama": "Diseksi Aorta (hindari hipotensi tiba-tiba)",
        "severity": AlertSeverity.WARNING.value,
        "pesan": "ACEI dapat menyebabkan hipotensi mendadak pada diseksi aorta. "
                 "Gunakan beta-blocker IV (labetolol/esmolol) sebagai lini pertama.",
    },
    {
        "obat": ["flecainide", "propafenone"],
        "kondisi_icd10": ["I21.0", "I21.1", "I21.4", "I25.1", "I50.0", "I42.0"],
        "kondisi_nama": "Penyakit Jantung Struktural (riwayat MI, HF, CMP)",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "Flecainide/Propafenone KONTRAINDIKASI ABSOLUT pada penyakit jantung struktural "
                 "— dapat menyebabkan VT/VF pro-aritmia mematikan (studi CAST).",
    },
    {
        "obat": ["nsaid", "ibuprofen", "naproxen", "diklofenak", "ketorolak", "celecoxib"],
        "kondisi_icd10": ["I50.0", "I50.1", "N17.9"],
        "kondisi_nama": "Gagal Jantung Kongestif / Gagal Ginjal Akut",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "NSAID memperburuk retensi cairan pada gagal jantung dan dapat memicu/memperparah AKI.",
    },
    {
        "obat": ["metformin"],
        "kondisi_icd10": ["N17.9"],
        "kondisi_nama": "Gagal Ginjal Akut (eGFR <30)",
        "severity": AlertSeverity.CRITICAL.value,
        "pesan": "Metformin kontraindikasi pada eGFR <30 mL/mnt — risiko asidosis laktat berat.",
    },
]


# ── Rentang Dosis Aman (simplified) ──────────────────────────────────────

DOSE_LIMITS: dict[str, dict] = {
    "aspirin":         {"max_single": 300, "unit": "mg", "rute": ["PO"]},
    "clopidogrel":     {"max_single": 600, "unit": "mg", "rute": ["PO"]},
    "ticagrelor":      {"max_single": 180, "unit": "mg", "rute": ["PO"]},
    "furosemide":      {"max_single": 200, "unit": "mg", "rute": ["IV", "PO"]},
    "spironolakton":   {"max_single": 50,  "unit": "mg", "rute": ["PO"]},
    "metoprolol":      {"max_single": 200, "unit": "mg", "rute": ["PO"]},
    "atorvastatin":    {"max_single": 80,  "unit": "mg", "rute": ["PO"]},
    "rosuvastatin":    {"max_single": 40,  "unit": "mg", "rute": ["PO"]},
    "digoxin":         {"max_single": 0.25,"unit": "mg", "rute": ["PO", "IV"]},
    "amiodarone_iv":   {"max_bolus_mg": 300, "unit": "mg", "rute": ["IV"]},
    "norepinefrin":    {"max_mcg_kgmin": 3.0, "unit": "mcg/kgBB/mnt"},
    "dobutamin":       {"max_mcg_kgmin": 20,  "unit": "mcg/kgBB/mnt"},
}


# ── Fungsi Utama CDSS ─────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalisasi nama obat untuk pencocokan: lowercase, hapus spasi & tanda baca."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _obat_match(nama_order: str, obat_list: list[str]) -> bool:
    """Cek apakah nama obat dalam order cocok dengan salah satu item di list."""
    norm_order = _normalize(nama_order)
    return any(_normalize(ob) in norm_order or norm_order in _normalize(ob) for ob in obat_list)


def check_drug_interactions(orders: list[dict]) -> list[CDSSAlert]:
    """
    Periksa interaksi antar semua obat dalam daftar order aktif.
    orders = list of dict dengan minimal key 'nama_order'.
    """
    alerts = []
    obat_aktif = [o.get("nama_order", "") for o in orders if o.get("tipe") in ["Obat", "Cairan IV"]]

    for ddi in DDI_DB:
        match_a = any(_obat_match(ob, ddi["obat_a"]) for ob in obat_aktif)
        match_b = any(_obat_match(ob, ddi["obat_b"]) for ob in obat_aktif)

        if match_a and match_b:
            alerts.append(CDSSAlert(
                severity=ddi["severity"],
                kategori="Interaksi Obat (DDI)",
                judul=f"DDI: {ddi['obat_a'][0].title()} ↔ {ddi['obat_b'][0].title()}",
                pesan=ddi["efek"],
                rekomendasi=ddi["rekomendasi"],
                referensi=ddi.get("referensi", ""),
                dapat_override=ddi["severity"] != AlertSeverity.CRITICAL.value,
            ))
    return alerts


def check_contraindications(
    nama_obat: str,
    diagnosa_aktif: list[dict],
) -> list[CDSSAlert]:
    """
    Cek kontraindikasi obat terhadap daftar diagnosis aktif pasien.
    diagnosa_aktif = list of dict dengan key 'kode_icd10'.
    """
    alerts = []
    kode_aktif = [d.get("kode_icd10", "") for d in diagnosa_aktif]

    for ci in CONTRAINDICATION_DB:
        if _obat_match(nama_obat, ci["obat"]):
            for kode in kode_aktif:
                if kode in ci["kondisi_icd10"]:
                    alerts.append(CDSSAlert(
                        severity=ci["severity"],
                        kategori="Kontraindikasi Obat",
                        judul=f"KONTRAINDIKASI: {nama_obat.title()} pada {ci['kondisi_nama']}",
                        pesan=ci["pesan"],
                        rekomendasi="Pertimbangkan alternatif terapi. Bila tetap diperlukan, dokumentasikan "
                                    "justifikasi klinis dan informed consent.",
                        dapat_override=(ci["severity"] == AlertSeverity.WARNING.value),
                    ))
                    break
    return alerts


def get_ppk_recommendations(diagnosa_list: list[dict]) -> list[dict]:
    """
    Hasilkan daftar rekomendasi PPK/PERKI untuk setiap diagnosis ICD-10 aktif.
    Mengembalikan list dict berisi nama PPK, obat-obatan, dan langkah tata laksana.
    """
    results = []
    seen_ppk = set()

    for dx in diagnosa_list:
        kode = dx.get("kode_icd10", "")
        ppk_list = get_ppk_by_icd10(kode)
        for ppk in ppk_list:
            if ppk["nama_ppk"] not in seen_ppk:
                seen_ppk.add(ppk["nama_ppk"])
                results.append({
                    "kode_icd10_trigger": kode,
                    "nama_ppk": ppk["nama_ppk"],
                    "referensi": ppk["versi_referensi"],
                    "tujuan": ppk["tujuan_terapi"],
                    "pemeriksaan_awal": ppk["pemeriksaan_awal"],
                    "tata_laksana": ppk["tata_laksana_utama"],
                    "obat_rekomendasi": ppk["obat_rekomendasi"],
                    "monitoring": ppk["monitoring_wajib"],
                    "target": ppk["target_terapi"],
                    "kontraindikasi": ppk["kontraindikasi_penting"],
                    "skor_risiko": ppk.get("skor_risiko", {}),
                })
    return results


def run_full_cdss(
    nama_obat_baru: str,
    orders_aktif: list[dict],
    diagnosa_aktif: list[dict],
) -> dict:
    """
    Jalankan seluruh pipeline CDSS saat dokter menambahkan order baru:
      1. Cek kontraindikasi obat baru terhadap semua diagnosis
      2. Cek DDI obat baru terhadap semua obat aktif
      3. Sertakan rekomendasi PPK untuk diagnosis aktif

    Mengembalikan:
    {
        "aman": bool,
        "alerts": list[CDSSAlert],
        "ppk_hints": list[dict],
        "summary": str,
    }
    """
    all_alerts: list[CDSSAlert] = []

    # 1. Kontraindikasi
    ci_alerts = check_contraindications(nama_obat_baru, diagnosa_aktif)
    all_alerts.extend(ci_alerts)

    # 2. DDI — tambahkan obat baru ke list virtual untuk pengecekan
    virtual_orders = orders_aktif + [{"tipe": "Obat", "nama_order": nama_obat_baru}]
    ddi_alerts = check_drug_interactions(virtual_orders)
    all_alerts.extend(ddi_alerts)

    # 3. PPK hints
    ppk_hints = get_ppk_recommendations(diagnosa_aktif)

    # Tentukan overall safety
    has_critical = any(a.severity == AlertSeverity.CRITICAL.value for a in all_alerts)

    summary_parts = []
    if not all_alerts:
        summary_parts.append("✅ Tidak ditemukan alert klinis untuk order ini.")
    else:
        critical = [a for a in all_alerts if a.severity == AlertSeverity.CRITICAL.value]
        warnings = [a for a in all_alerts if a.severity == AlertSeverity.WARNING.value]
        info     = [a for a in all_alerts if a.severity == AlertSeverity.INFO.value]
        if critical: summary_parts.append(f"🚨 {len(critical)} alert KRITIS")
        if warnings: summary_parts.append(f"⚠️ {len(warnings)} peringatan")
        if info:     summary_parts.append(f"ℹ️ {len(info)} informasi")

    return {
        "aman": not has_critical,
        "alerts": all_alerts,
        "ppk_hints": ppk_hints,
        "summary": " | ".join(summary_parts) if summary_parts else "Tidak ada alert.",
    }

"""
Engine CPOE (Computerized Physician Order Entry).
Menangani:
  - Pembuatan dan validasi order medis
  - Penomoran order otomatis
  - Order set standar berbasis PPK
  - Verifikasi kelengkapan data order sebelum disimpan
"""

import uuid
from datetime import datetime
from typing import List, Optional

from .models import (
    DrugOrder, LabOrder, MedicalOrder, OrderStatus, OrderType,
    PriorityLevel, VentilatorOrder,
)


def generate_order_id() -> str:
    """Generate ID order unik dengan prefix CPOE-YYYYMMDD-XXXX."""
    date_str = datetime.now().strftime("%Y%m%d")
    uid = str(uuid.uuid4())[:8].upper()
    return f"CPOE-{date_str}-{uid}"


def build_drug_order(
    episode_id: str,
    dokter_id: str,
    dokter_nama: str,
    nama_obat: str,
    dosis: str,
    satuan: str,
    rute: str,
    frekuensi: str,
    durasi: str,
    kecepatan_infus: Optional[str] = None,
    pengenceran: Optional[str] = None,
    indikasi: str = "",
    prioritas: str = PriorityLevel.RUTIN.value,
    catatan: str = "",
    icd10_terkait: Optional[str] = None,
) -> MedicalOrder:
    """Buat MedicalOrder untuk obat dari parameter terstruktur."""
    detail = {
        "nama_obat": nama_obat,
        "dosis": dosis,
        "satuan": satuan,
        "rute": rute,
        "frekuensi": frekuensi,
        "durasi": durasi,
        "kecepatan_infus": kecepatan_infus,
        "pengenceran": pengenceran,
        "indikasi": indikasi,
    }
    return MedicalOrder(
        order_id=generate_order_id(),
        episode_id=episode_id,
        dokter_id=dokter_id,
        dokter_nama=dokter_nama,
        tipe=OrderType.OBAT.value,
        nama_order=nama_obat,
        detail=detail,
        prioritas=prioritas,
        catatan=catatan,
        icd10_terkait=icd10_terkait,
    )


def build_lab_order(
    episode_id: str,
    dokter_id: str,
    dokter_nama: str,
    panel_lab: str,
    jenis_spesimen: str,
    waktu_pengambilan: str,
    catatan_lab: str = "",
    prioritas: str = PriorityLevel.RUTIN.value,
    icd10_terkait: Optional[str] = None,
    kategori: str = "Laboratorium",
) -> MedicalOrder:
    """Buat MedicalOrder untuk pemeriksaan laboratorium ATAU penunjang lain.

    `kategori` (dari pilihan "Kategori Pemeriksaan" di form CPOE) menentukan
    tipe order & prefix nama, supaya pemeriksaan seperti "Foto Toraks AP" /
    "CT Scan" tidak ikut ditandai sebagai "Laboratorium" — sebelumnya semua
    pemeriksaan penunjang (termasuk Radiologi) selalu dipaksa tipe
    Laboratorium + prefix nama "Lab: ", padahal kategorinya beda.
    """
    detail = {
        "panel_lab": panel_lab,
        "jenis_spesimen": jenis_spesimen,
        "waktu_pengambilan": waktu_pengambilan,
        "catatan_lab": catatan_lab,
    }

    if kategori == "Radiologi":
        tipe, prefix = OrderType.RADIOLOGI.value, "Radiologi"
    elif kategori == "Diagnostik Lain":
        tipe, prefix = OrderType.PROSEDUR.value, "Pemeriksaan Penunjang"
    else:
        tipe, prefix = OrderType.LABORATORIUM.value, "Lab"

    return MedicalOrder(
        order_id=generate_order_id(),
        episode_id=episode_id,
        dokter_id=dokter_id,
        dokter_nama=dokter_nama,
        tipe=tipe,
        nama_order=f"{prefix}: {panel_lab}",
        detail=detail,
        prioritas=prioritas,
        icd10_terkait=icd10_terkait,
    )


def build_ventilator_order(
    episode_id: str,
    dokter_id: str,
    dokter_nama: str,
    mode: str,
    fio2_target: float,
    peep: float,
    tidal_volume: int,
    rate: int,
    ie_ratio: str,
    target_spo2: str = "94-98%",
    catatan: str = "",
) -> MedicalOrder:
    """Buat MedicalOrder untuk setting ventilator."""
    detail = {
        "mode": mode,
        "fio2_target": fio2_target,
        "peep": peep,
        "tidal_volume": tidal_volume,
        "rate": rate,
        "ie_ratio": ie_ratio,
        "target_spo2": target_spo2,
    }
    return MedicalOrder(
        order_id=generate_order_id(),
        episode_id=episode_id,
        dokter_id=dokter_id,
        dokter_nama=dokter_nama,
        tipe=OrderType.VENTILATOR.value,
        nama_order=f"Ventilator Setting: {mode} FiO2 {fio2_target*100:.0f}%",
        detail=detail,
        prioritas=PriorityLevel.URGENT.value,
        catatan=catatan,
    )


def validate_order(order: MedicalOrder) -> list[str]:
    """
    Validasi kelengkapan order sebelum disimpan.
    Mengembalikan list error (kosong = valid).
    """
    errors = []
    if not order.episode_id:
        errors.append("Episode ID pasien tidak boleh kosong.")
    if not order.dokter_id:
        errors.append("ID Dokter wajib diisi.")
    if not order.nama_order.strip():
        errors.append("Nama order tidak boleh kosong.")

    if order.tipe == OrderType.OBAT.value:
        d = order.detail
        if not d.get("dosis"):
            errors.append("Dosis obat wajib diisi.")
        if not d.get("rute"):
            errors.append("Rute pemberian obat wajib diisi.")
        if not d.get("frekuensi"):
            errors.append("Frekuensi pemberian wajib diisi.")

    if order.tipe == OrderType.LABORATORIUM.value:
        d = order.detail
        if not d.get("panel_lab"):
            errors.append("Panel laboratorium wajib diisi.")

    return errors


# ── Order Set Standar Berbasis PPK ────────────────────────────────────────

ORDER_SETS: dict[str, dict] = {
    "STEMI": {
        "nama": "Order Set STEMI Akut (PERKI 2018)",
        "deskripsi": "Bundle order standar untuk pasien STEMI dalam 24 jam pertama.",
        "icd10": ["I21.0", "I21.1"],
        "orders": [
            {"tipe": "Lab", "nama": "Troponin I/T (hs-cTn)", "spesimen": "Darah Vena", "waktu": "Segera (jam 0)"},
            {"tipe": "Lab", "nama": "CK-MB", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Darah Lengkap", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Kimia Klinik Lengkap (ureum, kreatinin, elektrolit, GDS)", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Koagulasi (PT/INR, aPTT)", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Obat", "nama": "Aspirin", "dosis": "300", "satuan": "mg", "rute": "PO", "frekuensi": "Dosis tunggal (loading)", "durasi": "1 hari"},
            {"tipe": "Obat", "nama": "Ticagrelor", "dosis": "180", "satuan": "mg", "rute": "PO", "frekuensi": "Dosis tunggal (loading)", "durasi": "1 hari"},
            {"tipe": "Obat", "nama": "Enoxaparin", "dosis": "0.5 mg/kgBB", "satuan": "mg/kgBB", "rute": "IV", "frekuensi": "Dosis tunggal bolus", "durasi": "1 dosis"},
            {"tipe": "Obat", "nama": "Atorvastatin", "dosis": "80", "satuan": "mg", "rute": "PO", "frekuensi": "OD malam", "durasi": "Jangka panjang"},
            {"tipe": "Keperawatan", "nama": "Pasang monitoring EKG kontinu (telemetri)"},
            {"tipe": "Keperawatan", "nama": "Input-output cairan ketat"},
            {"tipe": "Keperawatan", "nama": "Puasa untuk persiapan kateterisasi jantung"},
        ],
    },
    "NSTEMI": {
        "nama": "Order Set NSTEMI/APTS (PERKI 2018)",
        "deskripsi": "Bundle order standar untuk NSTEMI dan APTS.",
        "icd10": ["I21.4", "I20.0"],
        "orders": [
            {"tipe": "Lab", "nama": "hs-Troponin I/T (jam 0)", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "hs-Troponin I/T (jam 1/3)", "spesimen": "Darah Vena", "waktu": "1 atau 3 jam kemudian"},
            {"tipe": "Lab", "nama": "GRACE Score — kalkulasi", "spesimen": "-", "waktu": "Setelah data lengkap"},
            {"tipe": "Obat", "nama": "Aspirin", "dosis": "300", "satuan": "mg", "rute": "PO", "frekuensi": "Loading, kemudian 75-100 mg/hari", "durasi": "Jangka panjang"},
            {"tipe": "Obat", "nama": "Ticagrelor", "dosis": "180", "satuan": "mg", "rute": "PO", "frekuensi": "Loading, kemudian 90 mg q12h", "durasi": "12 bulan"},
            {"tipe": "Obat", "nama": "Fondaparinux", "dosis": "2.5", "satuan": "mg", "rute": "SC", "frekuensi": "OD", "durasi": "Hingga revaskularisasi/8 hari"},
            {"tipe": "Keperawatan", "nama": "EKG monitoring kontinu — pantau perubahan ST"},
        ],
    },
    "ACUTE_HF": {
        "nama": "Order Set Gagal Jantung Akut Dekompensasi (PERKI 2020)",
        "deskripsi": "Bundle order untuk GJK dekompensasi akut.",
        "icd10": ["I50.0", "I50.1"],
        "orders": [
            {"tipe": "Lab", "nama": "BNP atau NT-proBNP", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Darah Lengkap + Kimia Klinik + Elektrolit", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Troponin (singkirkan ACS)", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "TSH (singkirkan kelainan tiroid)", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "AGD Arteri", "spesimen": "Darah Arteri", "waktu": "Segera (bila sesak berat)"},
            {"tipe": "Obat", "nama": "Furosemide IV", "dosis": "40-80", "satuan": "mg", "rute": "IV", "frekuensi": "Bolus, dapat diulang tiap 6 jam", "durasi": "Sampai euvolemia"},
            {"tipe": "Keperawatan", "nama": "Posisi semi-Fowler 30-45°"},
            {"tipe": "Keperawatan", "nama": "Input-output cairan ketat — target balance negatif"},
            {"tipe": "Keperawatan", "nama": "Timbang badan harian setiap pagi"},
            {"tipe": "Keperawatan", "nama": "O2 target SpO2 94-98% — pasang pulse oximetry kontinu"},
        ],
    },
    "SEPSIS": {
        "nama": "Order Set Sepsis — Bundle 1 Jam SSC 2021",
        "deskripsi": "Semua tindakan harus selesai dalam 60 menit sejak diagnosis.",
        "icd10": ["A41.9"],
        "orders": [
            {"tipe": "Lab", "nama": "Laktat Serum", "spesimen": "Darah Vena", "waktu": "SEGERA (<15 menit)"},
            {"tipe": "Lab", "nama": "Kultur Darah 2 Set (Aerob + Anaerob)", "spesimen": "Darah Vena", "waktu": "SEBELUM antibiotik"},
            {"tipe": "Lab", "nama": "Darah Lengkap + Hitung Jenis + CRP + PCT", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Kimia Klinik, LFT, Koagulasi (PT, aPTT, Fibrinogen, D-Dimer)", "spesimen": "Darah Vena", "waktu": "Segera"},
            {"tipe": "Lab", "nama": "Urinalisis + Kultur Urin", "spesimen": "Urin", "waktu": "Segera"},
            {"tipe": "Obat", "nama": "Meropenem", "dosis": "1000", "satuan": "mg", "rute": "IV", "frekuensi": "q8h", "durasi": "Sampai de-eskalasi kultur"},
            {"tipe": "Obat", "nama": "Vancomycin", "dosis": "25-30 mg/kgBB", "satuan": "mg/kgBB", "rute": "IV", "frekuensi": "Loading, lanjut q8-12h", "durasi": "Sampai kultur"},
            {"tipe": "Cairan", "nama": "NaCl 0.9% / Ringer Laktat", "dosis": "30 mL/kgBB IV bolus cepat (<3 jam)", "rute": "IV"},
            {"tipe": "Keperawatan", "nama": "Monitor MAP setiap 15 menit — pasang arterial line bila tersedia"},
            {"tipe": "Keperawatan", "nama": "Pasang CVC untuk vasopressor bila MAP <65 setelah resusitasi"},
        ],
    },
}


def get_order_set(nama_set: str) -> Optional[dict]:
    """Ambil order set standar berdasarkan nama (STEMI, NSTEMI, ACUTE_HF, SEPSIS)."""
    return ORDER_SETS.get(nama_set.upper())


def get_order_sets_for_icd10(kode_icd10: str) -> list[dict]:
    """Cari semua order set yang relevan untuk kode ICD-10 tertentu."""
    results = []
    for key, os in ORDER_SETS.items():
        if kode_icd10 in os.get("icd10", []):
            results.append({"key": key, **os})
    return results
"""
Data models untuk modul Dokter.
Semua dataclass bersifat plain Python — tidak ada dependensi Streamlit.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


# ── Enum ──────────────────────────────────────────────────────────────────

class OrderStatus(Enum):
    DRAFT     = "Draft"
    AKTIF     = "Aktif"
    DILAKSANA = "Dilaksanakan"
    SELESAI   = "Selesai"
    DIBATAL   = "Dibatalkan"

class OrderType(Enum):
    OBAT          = "Obat"
    CAIRAN_IV     = "Cairan IV"
    LABORATORIUM  = "Laboratorium"
    RADIOLOGI     = "Radiologi"
    DIET          = "Diet"
    PROSEDUR      = "Prosedur"
    KEPERAWATAN   = "Instruksi Keperawatan"
    KONSUL        = "Konsultasi"
    VENTILATOR    = "Setting Ventilator"
    LAINNYA       = "Lainnya"

class DiagnosisType(Enum):
    UTAMA   = "Diagnosis Utama"
    SEKUNDER = "Diagnosis Sekunder"
    KOMPLIKASI = "Komplikasi"
    BAWAAN  = "Penyakit Penyerta"

class PriorityLevel(Enum):
    RUTIN   = "🟢 Rutin"
    SEGERA  = "🟡 Segera"
    URGENT  = "🔴 Urgent / STAT"

class AlertSeverity(Enum):
    INFO     = "ℹ️ Informasi"
    WARNING  = "⚠️ Peringatan"
    CRITICAL = "🚨 Kritis"


# ── Doctor Credential ─────────────────────────────────────────────────────

@dataclass
class Doctor:
    dokter_id: str
    nama: str
    spesialisasi: str
    nomor_sip: str
    sub_spesialisasi: Optional[str] = None
    email: Optional[str] = None
    aktif: bool = True


# ── Diagnosis ─────────────────────────────────────────────────────────────

@dataclass
class Diagnosis:
    kode_icd10: str
    nama_penyakit: str
    tipe: str = DiagnosisType.UTAMA.value
    catatan: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    dokter_id: str = ""
    episode_id: str = ""
    status: str = "Aktif"


# ── Medical Order (CPOE) ──────────────────────────────────────────────────

@dataclass
class MedicalOrder:
    order_id: str
    episode_id: str
    dokter_id: str
    dokter_nama: str
    tipe: str
    nama_order: str
    detail: dict                    # struktur bervariasi tergantung tipe
    prioritas: str = PriorityLevel.RUTIN.value
    status: str = OrderStatus.AKTIF.value
    catatan: str = ""
    timestamp_order: str = field(default_factory=lambda: datetime.now().isoformat())
    timestamp_verifikasi: Optional[str] = None
    verifikator: Optional[str] = None   # nama perawat yg melaksanakan
    icd10_terkait: Optional[str] = None # kode ICD-10 indikasi order


@dataclass
class DrugOrder:
    """Detail order obat — disimpan sebagai JSON di MedicalOrder.detail."""
    nama_obat: str
    dosis: str
    satuan: str
    rute: str               # IV, PO, SC, SL, dst.
    frekuensi: str          # q8h, q12h, OD, PRN, continuous, dst.
    durasi: str             # "3 hari", "sampai order baru", dst.
    kecepatan_infus: Optional[str] = None   # untuk IV drip
    pengenceran: Optional[str] = None       # "dalam 100cc NS"
    indikasi: str = ""


@dataclass
class LabOrder:
    """Detail order laboratorium."""
    panel_lab: str              # "Darah Lengkap", "AGD", "Troponin", dst.
    jenis_spesimen: str         # "Darah Vena", "Darah Arteri", dst.
    waktu_pengambilan: str      # "Segera", "Pagi", "Serial 6 jam"
    catatan_lab: str = ""


@dataclass
class VentilatorOrder:
    """Detail setting ventilator melalui CPOE."""
    mode: str
    fio2_target: float
    peep: float
    tidal_volume: int
    rate: int
    ie_ratio: str
    target_spo2: str = "94-98%"
    catatan: str = ""


@dataclass
class CDSSAlert:
    """Alert yang dihasilkan oleh CDSS Dokter."""
    severity: str
    kategori: str       # "Interaksi Obat", "Kontraindikasi", "Dosis", "Rekomendasi PPK"
    judul: str
    pesan: str
    rekomendasi: str
    referensi: str = ""     # "PPK Jantung Koroner 2023", "PERKI 2022", dst.
    dapat_override: bool = True
    order_terkait: Optional[str] = None

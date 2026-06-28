"""
DICOM Gateway — WADO-RS REST Client & Structured Report Parser
==============================================================
Integrasi dengan PACS / VNA yang mendukung DICOMweb (WADO-RS / QIDO-RS)
untuk mengambil data vital signs yang tersimpan dalam DICOM Structured Reports
yang dikirim oleh bedside monitor / monitoring station.

Skenario di RSJPDHK:
  1. Bedside monitor (GE, Philips) mengirim SR ke PACS setiap interval tertentu
  2. Gateway ini query PACS via QIDO-RS → ambil SR terbaru → parse vital signs
  3. Data dikembalikan sebagai dict yang kompatibel dengan VitalSigns model

SOP Classes yang didukung:
  • 1.2.840.10008.5.1.4.1.1.88.11  — Basic Text SR
  • 1.2.840.10008.5.1.4.1.1.88.22  — Enhanced SR
  • 1.2.840.10008.5.1.4.1.1.88.33  — Comprehensive SR
  • 1.2.840.10008.5.1.4.1.1.9.2.1  — Hemodynamic Waveform Storage

PACS yang umum dipakai di RS Indonesia yang mendukung DICOMweb:
  • Orthanc (open-source, banyak dipakai rumah sakit pendidikan)
  • dcm4chee 5.x (HIPAA-compliant)
  • Sectra IDS7
  • Fujifilm Synapse

Dependensi opsional:
  pip install requests pydicom
  (app tetap jalan tanpa keduanya — fitur DICOM nonaktif graceful)
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Opsional dependencies ──────────────────────────────────────────────────────
try:
    import requests
    from requests.auth import HTTPBasicAuth
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import pydicom
    PYDICOM_OK = True
except ImportError:
    PYDICOM_OK = False


# ── DICOM SOP Class UIDs ───────────────────────────────────────────────────────
SOP_BASIC_SR      = "1.2.840.10008.5.1.4.1.1.88.11"
SOP_ENHANCED_SR   = "1.2.840.10008.5.1.4.1.1.88.22"
SOP_COMP_SR       = "1.2.840.10008.5.1.4.1.1.88.33"
SOP_HEMODYNAMIC   = "1.2.840.10008.5.1.4.1.1.9.2.1"

SR_SOP_SET = {SOP_BASIC_SR, SOP_ENHANCED_SR, SOP_COMP_SR, SOP_HEMODYNAMIC}

# ── SNOMED CT concept codes untuk vital signs (paling umum di DICOM SR) ────────
SR_CONCEPT_MAP: Dict[str, str] = {
    # SNOMED CT
    "364075005":   "heart_rate",
    "72313002":    "systolic_bp",
    "1091811000":  "diastolic_bp",
    "431314004":   "spo2",
    "86290005":    "respiratory_rate",
    "386725007":   "body_temp",
    "1036531000":  "map",
    "250076000":   "cvp",
    # LOINC dalam SR (Philips IntelliVue, kadang embed LOINC)
    "8867-4":  "heart_rate",
    "8480-6":  "systolic_bp",
    "8462-4":  "diastolic_bp",
    "59408-5": "spo2",
    "9279-1":  "respiratory_rate",
    "8310-5":  "body_temp",
    "8478-0":  "map",
    "8591-3":  "cvp",
}

# ── Keyword fallback (CodeMeaning → field) ────────────────────────────────────
CONCEPT_MEANING_MAP: Dict[str, str] = {
    "HEART RATE":          "heart_rate",
    "PULSE RATE":          "heart_rate",
    "SYSTOLIC":            "systolic_bp",
    "SYSTOLIC BP":         "systolic_bp",
    "SYSTOLIC BLOOD":      "systolic_bp",
    "DIASTOLIC":           "diastolic_bp",
    "DIASTOLIC BP":        "diastolic_bp",
    "OXYGEN SATURATION":   "spo2",
    "SPO2":                "spo2",
    "SAO2":                "spo2",
    "RESPIRATORY RATE":    "respiratory_rate",
    "BREATH RATE":         "respiratory_rate",
    "RR":                  "respiratory_rate",
    "BODY TEMPERATURE":    "body_temp",
    "TEMPERATURE":         "body_temp",
    "TEMP":                "body_temp",
    "MEAN ARTERIAL":       "map",
    "MAP":                 "map",
    "CENTRAL VENOUS":      "cvp",
    "CVP":                 "cvp",
    "RAP":                 "cvp",
}


# =============================================================================
# Config
# =============================================================================

@dataclass
class DICOMConfig:
    """
    Konfigurasi koneksi ke PACS via DICOMweb.

    Contoh untuk Orthanc lokal:
        base_url = "http://pacs.rsjpdhk.local:8042"
        username = "admin"
        password = "orthanc"
        wado_prefix = "/wado"    # atau "" untuk Orthanc DICOMweb plugin
        qido_prefix = "/dicom-web"
    """
    base_url: str            = "http://localhost:8042"
    username: str            = ""
    password: str            = ""
    wado_prefix: str         = ""          # prefix endpoint WADO-RS
    qido_prefix: str         = "/dicom-web"  # prefix endpoint QIDO-RS
    verify_ssl: bool         = True
    timeout: int             = 10          # detik per request

    @property
    def qido_base(self) -> str:
        return self.base_url.rstrip("/") + self.qido_prefix

    @property
    def wado_base(self) -> str:
        return self.base_url.rstrip("/") + self.wado_prefix

    @property
    def auth(self) -> Optional[Tuple[str, str]]:
        return (self.username, self.password) if self.username else None


# =============================================================================
# QIDO-RS Client — query / cari study di PACS
# =============================================================================

@dataclass
class DICOMStudyInfo:
    study_uid: str
    study_date: str
    study_time: str
    patient_id: str
    patient_name: str
    modality: str
    description: str = ""
    sop_class: str   = ""


class QIDOClient:
    """Query PACS menggunakan QIDO-RS (JSON response)."""

    def __init__(self, cfg: DICOMConfig):
        self.cfg = cfg
        if not REQUESTS_OK:
            raise ImportError(
                "Modul 'requests' tidak tersedia. "
                "Install: pip install requests"
            )

    def _get(self, path: str, params: dict) -> Optional[list]:
        url = self.cfg.qido_base + path
        try:
            r = requests.get(
                url, params=params,
                auth=self.cfg.auth,
                headers={"Accept": "application/dicom+json"},
                timeout=self.cfg.timeout,
                verify=self.cfg.verify_ssl,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.error("QIDO GET %s error: %s", url, exc)
            return None

    def search_studies(
        self,
        patient_id: Optional[str] = None,
        study_date: Optional[str] = None,
        modality:   Optional[str] = None,
        limit: int = 5,
    ) -> List[DICOMStudyInfo]:
        params: Dict[str, Any] = {"limit": limit}
        if patient_id:
            params["PatientID"] = patient_id
        if study_date:
            params["StudyDate"] = study_date
        if modality:
            params["ModalitiesInStudy"] = modality

        data = self._get("/studies", params)
        if not data:
            return []
        return [self._parse_study(d) for d in data if d]

    def search_sr_today(self, patient_id: str) -> List[DICOMStudyInfo]:
        """Shortcut: cari Structured Report hari ini untuk pasien tertentu."""
        today = datetime.now().strftime("%Y%m%d")
        return self.search_studies(patient_id=patient_id, study_date=today, modality="SR")

    def get_series_list(self, study_uid: str) -> List[Dict]:
        data = self._get(f"/studies/{study_uid}/series", {})
        return data or []

    def get_instance_list(self, study_uid: str, series_uid: str) -> List[Dict]:
        data = self._get(
            f"/studies/{study_uid}/series/{series_uid}/instances", {}
        )
        return data or []

    @staticmethod
    def _parse_study(d: dict) -> DICOMStudyInfo:
        def _v(tag: str, default: str = "") -> str:
            val = d.get(tag, {}).get("Value", [default])
            if isinstance(val[0], dict):
                # PatientName adalah dict dengan 'Alphabetic' key
                return val[0].get("Alphabetic", default) if val else default
            return val[0] if val else default

        return DICOMStudyInfo(
            study_uid    = _v("0020000D"),
            study_date   = _v("00080020"),
            study_time   = _v("00080030"),
            patient_id   = _v("00100020"),
            patient_name = _v("00100010"),
            modality     = _v("00080061"),
            description  = _v("00081030"),
            sop_class    = _v("00080016"),
        )


# =============================================================================
# WADO-RS Client — download instance DICOM
# =============================================================================

class WADOClient:
    """Download DICOM instance dari PACS via WADO-RS."""

    def __init__(self, cfg: DICOMConfig):
        self.cfg = cfg
        if not REQUESTS_OK:
            raise ImportError("Butuh 'requests': pip install requests")
        if not PYDICOM_OK:
            raise ImportError("Butuh 'pydicom': pip install pydicom")

    def retrieve(
        self, study_uid: str, series_uid: str, instance_uid: str
    ) -> Optional[Any]:
        """Ambil satu instance sebagai pydicom Dataset."""
        url = (
            f"{self.cfg.wado_base}"
            f"/studies/{study_uid}"
            f"/series/{series_uid}"
            f"/instances/{instance_uid}"
        )
        try:
            r = requests.get(
                url,
                auth=self.cfg.auth,
                headers={"Accept": "application/dicom"},
                timeout=self.cfg.timeout,
                verify=self.cfg.verify_ssl,
            )
            r.raise_for_status()
            return pydicom.dcmread(io.BytesIO(r.content), force=True)
        except Exception as exc:
            logger.error("WADO-RS retrieve error (%s): %s", instance_uid, exc)
            return None


# =============================================================================
# DICOM SR Parser — ekstrak vital signs dari dataset
# =============================================================================

class DICOMSRParser:
    """
    Parse pydicom Dataset (Structured Report) dan kembalikan dict vital signs.
    Mendukung TID 1340 (Hemodynamic Measurement), TID 1500 (Measurement Report).
    """

    @classmethod
    def extract_vitals(cls, ds: Any) -> Optional[Dict[str, float]]:
        if not PYDICOM_OK:
            return None

        sop = str(getattr(ds, "SOPClassUID", ""))
        if sop not in SR_SOP_SET:
            logger.debug("Instance bukan SR (SOP=%s)", sop)
            return None

        content = getattr(ds, "ContentSequence", None)
        if content is None:
            return None

        vitals: Dict[str, float] = {}
        cls._walk(content, vitals)
        return vitals if vitals else None

    @classmethod
    def _walk(cls, seq: Any, out: dict) -> None:
        for item in seq:
            concept_seq = getattr(item, "ConceptNameCodeSequence", None)
            if concept_seq:
                code    = str(getattr(concept_seq[0], "CodeValue",  ""))
                meaning = str(getattr(concept_seq[0], "CodeMeaning", "")).upper()
                fname   = (
                    SR_CONCEPT_MAP.get(code)
                    or cls._meaning_to_field(meaning)
                )
                if fname:
                    val = cls._numeric(item)
                    if val is not None:
                        out[fname] = val

            child = getattr(item, "ContentSequence", None)
            if child:
                cls._walk(child, out)

    @staticmethod
    def _numeric(item: Any) -> Optional[float]:
        mvs = getattr(item, "MeasuredValueSequence", None)
        if mvs and len(mvs) > 0:
            num = getattr(mvs[0], "NumericValue", None)
            if num is not None:
                try:
                    return float(num)
                except (TypeError, ValueError):
                    pass
        text = getattr(item, "TextValue", None)
        if text:
            try:
                return float(str(text).strip())
            except ValueError:
                pass
        return None

    @staticmethod
    def _meaning_to_field(meaning: str) -> Optional[str]:
        for key, fname in CONCEPT_MEANING_MAP.items():
            if key in meaning:
                return fname
        return None


# =============================================================================
# High-level Gateway — dipakai oleh device_connector.py
# =============================================================================

class DICOMGateway:
    """
    Fasad tunggal untuk semua operasi DICOM dari Monitor_Device.py.
    Menggabungkan QIDO (query), WADO-RS (retrieve), dan SR parsing.
    """

    def __init__(self, cfg: DICOMConfig):
        self.cfg = cfg
        self._qido: Optional[QIDOClient] = None
        self._wado: Optional[WADOClient] = None
        self._init_clients()

    def _init_clients(self) -> None:
        if not REQUESTS_OK:
            logger.warning("DICOMGateway: 'requests' tidak tersedia — QIDO/WADO dinonaktifkan.")
            return
        try:
            self._qido = QIDOClient(self.cfg)
        except ImportError:
            pass
        if PYDICOM_OK:
            try:
                self._wado = WADOClient(self.cfg)
            except ImportError:
                pass

    @property
    def available(self) -> bool:
        return bool(self._qido and self._wado)

    def ping(self) -> Tuple[bool, str]:
        """Cek konektivitas ke PACS endpoint."""
        if not REQUESTS_OK:
            return False, "Library 'requests' tidak terinstall."
        try:
            r = requests.get(
                self.cfg.qido_base + "/studies",
                params={"limit": "1"},
                auth=self.cfg.auth,
                timeout=5,
                verify=self.cfg.verify_ssl,
            )
            if r.status_code < 500:
                return True, f"PACS OK — HTTP {r.status_code}"
            return False, f"PACS error — HTTP {r.status_code}"
        except Exception as exc:
            return False, f"Koneksi gagal: {exc}"

    def get_latest_vitals(self, patient_id: str) -> Optional[Dict[str, float]]:
        """
        Pipeline: QIDO cari SR hari ini → WADO download instance pertama
        → parse SR → return dict vital signs.
        Return None jika tidak ada data atau error.
        """
        if not self.available:
            return None

        studies = self._qido.search_sr_today(patient_id)
        if not studies:
            logger.info("DICOM: tidak ada SR hari ini untuk %s", patient_id)
            return None

        # Ambil study terbaru
        study = studies[0]
        series_list = self._qido.get_series_list(study.study_uid)
        if not series_list:
            return None

        for series in series_list:
            s_uid = series.get("0020000E", {}).get("Value", [""])[0]
            instances = self._qido.get_instance_list(study.study_uid, s_uid)
            if not instances:
                continue

            i_uid = instances[0].get("00080018", {}).get("Value", [""])[0]
            ds = self._wado.retrieve(study.study_uid, s_uid, i_uid)
            if ds is None:
                continue

            vitals = DICOMSRParser.extract_vitals(ds)
            if vitals:
                logger.info("DICOM: berhasil ekstrak %d vital dari SR %s", len(vitals), i_uid)
                return vitals

        return None


# =============================================================================
# Dependency checker — untuk diagnostik di UI
# =============================================================================

def check_dicom_dependencies() -> Dict[str, bool]:
    return {
        "requests": REQUESTS_OK,
        "pydicom":  PYDICOM_OK,
        "dicom_full": REQUESTS_OK and PYDICOM_OK,
    }

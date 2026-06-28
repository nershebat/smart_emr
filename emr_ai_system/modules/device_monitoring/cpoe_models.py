"""
CPOE Models — Computerized Physician Order Entry
=================================================
Entry point sistem order elektronik RSJPDHK.
Mencakup semua jenis order (bukan hanya medikasi) yang dibuat DPJP/residen:

  MedicationOrder  → route ke CLMA pipeline
  LabOrder         → route ke LIS (Laboratory Information System)
  ImagingOrder     → route ke RIS/PACS
  NursingOrder     → route ke CPPT / asuhan keperawatan
  DietOrder        → route ke Instalasi Gizi
  ConsultOrder     → route ke SMF tujuan
  ProcedureOrder   → route ke Kamar Operasi / Kateterisasi

FHIR R4 compliance:
  MedicationRequest   (medikasi)
  ServiceRequest      (lab, imaging, nursing, prosedur)
  NutritionOrder      (diet)
  ReferralRequest     (konsul)

Referensi:
  • HL7 FHIR R4 — https://hl7.org/fhir/R4/
  • SATUSEHAT FHIR API — https://satusehat.kemkes.go.id/
  • Permenkes No. 269/MENKES/PER/III/2008 — Rekam Medis
  • SNOMED CT + LOINC + RxNorm coding
  • KFN (Komite Farmasi & Terapi) RSJPDHK — Formularium 2024
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


# =============================================================================
# Enumerations
# =============================================================================

class CPOEOrderType(Enum):
    MEDICATION  = "Medikasi"
    LAB         = "Laboratorium"
    IMAGING     = "Radiologi / Imaging"
    NURSING     = "Keperawatan"
    DIET        = "Diet / Nutrisi"
    CONSULT     = "Konsultasi"
    PROCEDURE   = "Prosedur / Tindakan"
    ACTIVITY    = "Aktivitas"
    MONITORING  = "Monitoring Khusus"


class CPOEPriority(Enum):
    STAT    = "STAT (Segera)"
    URGENT  = "URGENT (<1 jam)"
    ASAP    = "ASAP (<4 jam)"
    ROUTINE = "RUTIN"
    PRN     = "PRN (Jika Perlu)"


class CPOEOrderStatus(Enum):
    DRAFT       = "Draft"
    ACTIVE      = "Aktif"
    PENDING     = "Pending"
    IN_PROGRESS = "Dalam Proses"
    COMPLETED   = "Selesai"
    CANCELLED   = "Dibatalkan"
    HELD        = "Ditahan"
    EXPIRED     = "Kedaluwarsa"


class LabPriority(Enum):
    STAT    = "STAT"
    URGENT  = "URGENT"
    ROUTINE = "RUTIN"


class NursingOrderType(Enum):
    VITAL_SIGNS    = "Pemantauan Tanda Vital"
    FLUID_BALANCE  = "Balans Cairan"
    WOUND_CARE     = "Perawatan Luka"
    POSITIONING    = "Posisi / Mobilisasi"
    ORAL_CARE      = "Perawatan Mulut"
    EYE_CARE       = "Perawatan Mata"
    SUCTION        = "Suctioning"
    NGT            = "Pemasangan/Perawatan NGT"
    CATHETER       = "Kateterisasi Urin"
    IV_CARE        = "Perawatan Akses IV"
    RESTRAINT      = "Restrain Fisik"
    FALL_PREVENTION= "Pencegahan Jatuh"
    EDUCATION      = "Edukasi Pasien/Keluarga"
    CUSTOM         = "Tindakan Keperawatan Lainnya"


class DietType(Enum):
    CARDIAC_LOW_SODIUM = "Diet Jantung Rendah Garam"
    CARDIAC_LOW_FAT    = "Diet Jantung Rendah Lemak"
    CARDIAC_DM         = "Diet Jantung DM"
    ENTERAL_NASOGASTRIC= "Nutrisi Enteral via NGT"
    PARENTERAL_TPN     = "Nutrisi Parenteral (TPN)"
    NPO                = "Puasa Total (NPO)"
    CLEAR_LIQUID       = "Cairan Jernih"
    SOFT               = "Makanan Lunak"
    LOW_POTASSIUM      = "Rendah Kalium"
    HIGH_PROTEIN       = "Tinggi Protein"
    CUSTOM             = "Diet Lainnya"


class ImagingModality(Enum):
    XRAY       = "Rontgen"
    ECG        = "EKG"
    ECHO       = "Ekokardiografi"
    CT         = "CT Scan"
    MRI        = "MRI"
    NUCLEAR    = "Kedokteran Nuklir"
    CATH       = "Kateterisasi Jantung"
    ANGIO      = "Angiografi"
    USG        = "USG"
    FLUOROSCOPY= "Fluoroskopi"


# =============================================================================
# Base Order
# =============================================================================

@dataclass
class CPOEBaseOrder:
    """Base class untuk semua jenis order CPOE."""
    order_id:    str
    episode_id:  str
    order_type:  CPOEOrderType
    priority:    CPOEPriority
    status:      CPOEOrderStatus
    ordered_by:        str   # nama DPJP/residen
    ordered_by_nip:    str
    ordered_by_role:   str   # "DPJP" | "Residen" | "Perawat" (BPDO)
    ordered_at:        str
    start_time:        str
    end_time:          str = ""
    notes:             str = ""
    diagnosis_code:    str = ""   # ICD-10 terkait
    diagnosis_name:    str = ""
    reviewed_by:       str = ""   # DPJP verifikator (untuk order residen)
    reviewed_at:       str = ""
    cancelled_by:      str = ""
    cancelled_at:      str = ""
    cancel_reason:     str = ""
    fhir_resource_id:  str = ""
    satusehat_id:      str = ""

    @property
    def is_active(self) -> bool:
        return self.status in (CPOEOrderStatus.ACTIVE, CPOEOrderStatus.IN_PROGRESS)

    @property
    def priority_badge(self) -> str:
        return {
            CPOEPriority.STAT:    "🔴 STAT",
            CPOEPriority.URGENT:  "🟠 URGENT",
            CPOEPriority.ASAP:    "🟡 ASAP",
            CPOEPriority.ROUTINE: "🟢 RUTIN",
            CPOEPriority.PRN:     "⚪ PRN",
        }.get(self.priority, "⚪")


# =============================================================================
# Medication CPOE Order
# =============================================================================

@dataclass
class MedicationCPOEOrder(CPOEBaseOrder):
    """
    CPOE order untuk medikasi — otomatis di-route ke CLMA pipeline.
    Menyimpan semua info yang dibutuhkan CLMAEngine.create_order().
    """
    drug_name:             str   = ""
    drug_generic:          str   = ""
    drug_class:            str   = ""
    drug_formulary_code:   str   = ""   # kode Formularium RSJPDHK
    rxnorm_code:           str   = ""   # RxNorm untuk FHIR

    dose_value:            float = 0.0
    dose_unit:             str   = ""   # dari DoseUnit.value
    route:                 str   = ""   # dari RouteCode.value
    frequency:             str   = ""   # dari FrequencyCode.value

    concentration_mcg_ml:  float = 0.0
    concentration_mg_ml:   float = 0.0
    syringe_size_ml:       float = 50.0
    diluent:               str   = ""
    rate_ml_h:             float = 0.0
    total_volume_ml:       float = 0.0
    duration_hours:        float = 0.0

    patient_weight_kg:     float = 0.0
    is_high_alert:         bool  = False
    is_double_check:       bool  = False

    indication:            str   = ""
    titration_target:      str   = ""   # "MAP ≥65 mmHg", "SpO2 ≥95%"

    # Link ke CLMA setelah diroute
    clma_order_id:         str   = ""
    clma_status:           str   = ""

    @property
    def order_summary(self) -> str:
        return (
            f"{self.drug_name} {self.dose_value} {self.dose_unit} "
            f"via {self.route} | Rate {self.rate_ml_h:.2f} ml/h"
        )


# =============================================================================
# Lab Order
# =============================================================================

@dataclass
class LabOrder(CPOEBaseOrder):
    """
    Order pemeriksaan laboratorium.
    Di-route ke LIS (Laboratory Information System).
    """
    panel_name:      str = ""   # "Panel Jantung Akut", "BGA", dst.
    tests:           List[str] = field(default_factory=list)   # list nama test
    loinc_codes:     List[str] = field(default_factory=list)
    specimen_type:   str = "Darah Vena"
    lab_priority:    LabPriority = LabPriority.STAT
    fasting_required: bool = False
    collection_time: str = ""
    special_instruction: str = ""
    lis_order_id:    str = ""   # ID dari LIS setelah dikirim

    @property
    def test_count(self) -> int:
        return len(self.tests)


# Paket lab kardiovaskular standar RSJPDHK
LAB_PANELS: Dict[str, List[str]] = {
    "Panel Jantung Akut (ACS)": [
        "Troponin I hs", "CK-MB", "BNP/NT-proBNP",
        "Darah Lengkap", "Elektrolit (Na, K, Cl)", "Ureum/Kreatinin",
        "GDS", "Laktat", "APTT", "PT/INR",
    ],
    "BGA (Blood Gas Analysis)": [
        "pH", "pCO2", "pO2", "HCO3", "BE", "SaO2",
        "Laktat", "Elektrolit (iCa, Na, K)",
    ],
    "Panel Heart Failure": [
        "BNP / NT-proBNP", "Troponin I hs",
        "Darah Lengkap", "Ureum/Kreatinin", "SGOT/SGPT",
        "Albumin", "Elektrolit lengkap", "TSH",
    ],
    "Panel Koagulasi Lengkap": [
        "PT/INR", "APTT", "Fibrinogen", "D-Dimer", "Anti-Xa",
    ],
    "Panel Infeksi / Sepsis": [
        "Darah Lengkap + Diff", "CRP", "Prokalsitonin",
        "Laktat", "Kultur Darah (2x)", "Urinalisis + Kultur Urin",
    ],
    "Monitoring Rutin ICCU": [
        "Darah Lengkap", "Elektrolit (Na, K, Cl)", "Ureum/Kreatinin",
        "GDS", "APTT", "BGA",
    ],
    "Panel Hematologi Lengkap": [
        "Darah Lengkap + Retikulosit",
        "Golongan Darah & Cross Match",
        "PT/INR", "APTT",
    ],
    "Panel Ginjal": [
        "Ureum", "Kreatinin", "Asam Urat",
        "Elektrolit", "Urinalisis", "eGFR",
    ],
    "Tiroid": ["TSH", "FT4", "FT3"],
    "Lipid Panel": [
        "Total Kolesterol", "LDL", "HDL", "Trigliserida",
        "ApoB", "Lp(a)",
    ],
}


# =============================================================================
# Imaging Order
# =============================================================================

@dataclass
class ImagingOrder(CPOEBaseOrder):
    """Order radiologi/imaging — di-route ke RIS/PACS."""
    modality:       ImagingModality = ImagingModality.XRAY
    body_region:    str = ""
    clinical_info:  str = ""
    specific_views: str = ""
    contrast:       bool = False
    contrast_type:  str = ""
    portable:       bool = False   # True = bedside (ICCU)
    sedation_req:   bool = False
    ris_order_id:   str = ""
    pacs_study_uid: str = ""

    @property
    def modality_emoji(self) -> str:
        return {
            ImagingModality.XRAY:  "🩻",
            ImagingModality.ECG:   "📈",
            ImagingModality.ECHO:  "❤️",
            ImagingModality.CT:    "🔬",
            ImagingModality.MRI:   "🧲",
            ImagingModality.CATH:  "🫀",
            ImagingModality.ANGIO: "🔭",
            ImagingModality.USG:   "〰️",
        }.get(self.modality, "📷")


# Paket imaging kardiovaskular
IMAGING_PRESETS: Dict[str, dict] = {
    "Rontgen Toraks Bedside": {
        "modality": ImagingModality.XRAY,
        "body_region": "Thorax",
        "specific_views": "AP Supine",
        "portable": True,
        "clinical_info": "Evaluasi cardiomegaly, edema paru, efusi pleura",
    },
    "Ekokardiografi Bedside": {
        "modality": ImagingModality.ECHO,
        "body_region": "Jantung",
        "specific_views": "TTE (Transthoracic) + Doppler",
        "portable": True,
        "clinical_info": "Evaluasi fungsi LV, RWMA, efusi perikardium, TR/MR",
    },
    "CT Angiografi Koroner": {
        "modality": ImagingModality.CT,
        "body_region": "Koroner",
        "contrast": True,
        "contrast_type": "Kontras IV non-ionik",
        "clinical_info": "Evaluasi stenosis koroner, plak, bypass graft",
    },
    "EKG 12 Lead": {
        "modality": ImagingModality.ECG,
        "body_region": "Jantung",
        "specific_views": "12 Lead standard",
        "portable": True,
        "clinical_info": "Evaluasi ritme, ST segmen, iskemia",
    },
    "Kateterisasi Jantung Diagnostik": {
        "modality": ImagingModality.CATH,
        "body_region": "Koroner + LV",
        "contrast": True,
        "sedation_req": True,
        "clinical_info": "Evaluasi stenosis koroner, ventrikulografi kiri",
    },
    "Angiografi Koroner + PCI": {
        "modality": ImagingModality.CATH,
        "body_region": "Koroner",
        "contrast": True,
        "sedation_req": True,
        "clinical_info": "Primary PCI / rescue PCI",
    },
}


# =============================================================================
# Nursing Order
# =============================================================================

@dataclass
class NursingOrder(CPOEBaseOrder):
    """Order keperawatan — langsung ke CPPT/asuhan keperawatan."""
    nursing_type:   NursingOrderType = NursingOrderType.VITAL_SIGNS
    instruction:    str = ""
    frequency_text: str = ""   # "Setiap 1 jam", "Setiap shift", dst.
    duration_text:  str = ""   # "Sampai kondisi stabil", "24 jam"
    target:         str = ""   # "MAP ≥65 mmHg", "SpO2 ≥95%"
    sdki_code:      str = ""   # diagnosis keperawatan terkait
    siki_code:      str = ""   # intervensi terkait


# Order keperawatan baku ICCU Jantung
NURSING_ORDER_PRESETS: Dict[str, dict] = {
    "Monitoring TTV Ketat (per jam)": {
        "nursing_type": NursingOrderType.VITAL_SIGNS,
        "instruction": "Ukur TD, Nadi, RR, SpO2, Suhu setiap 1 jam. Catat di lembar monitoring.",
        "frequency_text": "Setiap 1 jam",
        "target": "TD sistol 90-140 mmHg, MAP ≥65 mmHg, SpO2 ≥95%, Nadi 60-100x/mnt",
        "siki_code": "I.01014",
    },
    "Balans Cairan per Jam": {
        "nursing_type": NursingOrderType.FLUID_BALANCE,
        "instruction": "Hitung input-output cairan setiap jam. Ukur urine output via kateter urin.",
        "frequency_text": "Setiap jam",
        "target": "UO ≥0.5 mL/kg/jam, target 30-50 mL/jam",
        "siki_code": "I.03121",
    },
    "Suction ETT sesuai indikasi": {
        "nursing_type": NursingOrderType.SUCTION,
        "instruction": "Lakukan suctioning ETT jika ada sekret, stridor, atau SpO2 menurun. "
                       "Teknik aseptik. Dokumentasikan jumlah, warna, konsistensi sekret.",
        "frequency_text": "Sesuai indikasi",
        "siki_code": "I.01019",
    },
    "Perawatan Luka CVP / CVC": {
        "nursing_type": NursingOrderType.IV_CARE,
        "instruction": "Ganti dressing CVC setiap 3 hari atau jika kotor/basah. "
                       "Observasi tanda infeksi (kemerahan, pus, bengkak). Catat bundle CVC.",
        "frequency_text": "Setiap 3 hari / sesuai indikasi",
        "siki_code": "I.14545",
    },
    "Posisi Kepala 30-45 Derajat": {
        "nursing_type": NursingOrderType.POSITIONING,
        "instruction": "Pertahankan posisi Head of Bed 30-45 derajat untuk pencegahan VAP "
                       "dan optimasi preload. Alih baring setiap 2 jam.",
        "frequency_text": "Kontinu / alih baring setiap 2 jam",
        "siki_code": "I.01011",
    },
    "Pencegahan Dekubitus": {
        "nursing_type": NursingOrderType.POSITIONING,
        "instruction": "Alih baring setiap 2 jam. Gunakan kasur anti-dekubitus. "
                       "Kaji skala Braden setiap hari. Lindungi area tulang penonjol.",
        "frequency_text": "Setiap 2 jam",
        "siki_code": "I.14571",
    },
    "Oral Care / Mouth Care": {
        "nursing_type": NursingOrderType.ORAL_CARE,
        "instruction": "Oral hygiene dengan chlorhexidine 0.12% setiap 4-6 jam "
                       "(VAP prevention bundle). Dokumentasikan kondisi mukosa oral.",
        "frequency_text": "Setiap 4-6 jam",
        "siki_code": "I.08238",
    },
    "Monitoring CVP": {
        "nursing_type": NursingOrderType.VITAL_SIGNS,
        "instruction": "Ukur CVP setiap 1-2 jam. Zero-balance setiap shift. "
                       "Catat nilai dan lapor jika <5 atau >15 cmH2O.",
        "frequency_text": "Setiap 1-2 jam",
        "target": "CVP 5-12 cmH2O",
        "siki_code": "I.02044",
    },
    "Edukasi Pasien/Keluarga": {
        "nursing_type": NursingOrderType.EDUCATION,
        "instruction": "Berikan edukasi kepada pasien/keluarga mengenai kondisi, "
                       "tatalaksana, dan rencana perawatan. Evaluasi pemahaman.",
        "frequency_text": "Minimal 1x/hari atau sesuai kebutuhan",
        "siki_code": "I.12383",
    },
}


# =============================================================================
# Diet Order
# =============================================================================

@dataclass
class DietOrder(CPOEBaseOrder):
    """Order diet/nutrisi — di-route ke Instalasi Gizi."""
    diet_type:      DietType = DietType.CARDIAC_LOW_SODIUM
    calorie_target: int = 0       # kkal/hari, 0 = default gizi
    protein_g_kg:   float = 0.0   # g/kg/hari
    sodium_mg_day:  int = 0       # mg/hari, 0 = default
    fluid_ml_day:   int = 0       # restriksi cairan (0 = bebas)
    route_nutrition: str = "Oral" # "Oral" | "NGT" | "TPN"
    texture:        str = ""      # "Biasa" | "Lunak" | "Cair"
    allergy_note:   str = ""
    gizi_order_id:  str = ""

    @property
    def nutrition_summary(self) -> str:
        parts = [self.diet_type.value]
        if self.calorie_target:
            parts.append(f"{self.calorie_target} kkal/hari")
        if self.sodium_mg_day:
            parts.append(f"Na <{self.sodium_mg_day} mg/hari")
        if self.fluid_ml_day:
            parts.append(f"cairan ≤{self.fluid_ml_day} mL/hari")
        return " | ".join(parts)


# =============================================================================
# Consult Order
# =============================================================================

@dataclass
class ConsultOrder(CPOEBaseOrder):
    """Order konsultasi antar SMF."""
    to_department:  str = ""   # "SMF Penyakit Dalam", "SMF Neurologi", dst.
    to_doctor:      str = ""   # nama dokter konsulen (opsional)
    question:       str = ""   # pertanyaan konsul
    urgency_reason: str = ""
    consult_reply:  str = ""
    replied_by:     str = ""
    replied_at:     str = ""


# =============================================================================
# Order Set — bundle of orders for a protocol
# =============================================================================

@dataclass
class OrderSetItem:
    """Satu item dalam order set."""
    order_type: CPOEOrderType
    template:   dict          # parameter default untuk jenis order ini
    required:   bool = True   # True = otomatis tercentang di UI
    rationale:  str = ""      # alasan klinis


@dataclass
class OrderSet:
    """
    Kumpulan order standar untuk protokol klinis tertentu di ICCU Jantung.
    Diaktivasi sekali klik oleh DPJP, lalu bisa dikustomisasi per item.
    """
    set_id:      str
    name:        str
    description: str
    indication:  str
    icd10_code:  str
    items:       List[OrderSetItem] = field(default_factory=list)
    author:      str = "KFT RSJPDHK"
    version:     str = "2024.1"
    evidence_level: str = ""   # "ACC/AHA IA", "ESC IB", dst.


# =============================================================================
# FHIR R4 Resource Models (simplified)
# =============================================================================

@dataclass
class FHIRMedicationRequest:
    """Simplified FHIR R4 MedicationRequest untuk SATUSEHAT."""
    resource_type: str = "MedicationRequest"
    id: str = ""
    status: str = "active"
    intent: str = "order"
    medication_display: str = ""
    rxnorm_code: str = ""
    subject_id: str = ""         # SATUSEHAT Patient ID
    encounter_id: str = ""       # SATUSEHAT Encounter ID
    authored_on: str = ""
    requester_id: str = ""       # SATUSEHAT Practitioner ID
    dose_value: float = 0.0
    dose_unit: str = ""
    rate_value: float = 0.0
    rate_unit: str = "mL/h"
    route_code: str = ""
    route_display: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "resourceType": self.resource_type,
            "id": self.id or str(uuid.uuid4()),
            "status": self.status,
            "intent": self.intent,
            "medicationCodeableConcept": {
                "coding": [{
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "code": self.rxnorm_code,
                    "display": self.medication_display,
                }],
                "text": self.medication_display,
            },
            "subject": {"reference": f"Patient/{self.subject_id}"},
            "encounter": {"reference": f"Encounter/{self.encounter_id}"},
            "authoredOn": self.authored_on,
            "requester": {"reference": f"Practitioner/{self.requester_id}"},
            "dosageInstruction": [{
                "doseAndRate": [{
                    "doseQuantity": {"value": self.dose_value, "unit": self.dose_unit},
                    "rateQuantity": {"value": self.rate_value, "unit": self.rate_unit},
                }],
                "route": {
                    "coding": [{
                        "system": "http://snomed.info/sct",
                        "code": self.route_code,
                        "display": self.route_display,
                    }]
                },
            }],
            "note": [{"text": self.note}] if self.note else [],
        }


@dataclass
class FHIRServiceRequest:
    """Simplified FHIR R4 ServiceRequest untuk lab/imaging/nursing."""
    resource_type: str = "ServiceRequest"
    id: str = ""
    status: str = "active"
    intent: str = "order"
    category_code: str = ""       # "108252007" = lab, "363679005" = imaging
    category_display: str = ""
    code_display: str = ""
    loinc_code: str = ""
    subject_id: str = ""
    encounter_id: str = ""
    authored_on: str = ""
    requester_id: str = ""
    priority: str = "routine"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "resourceType": self.resource_type,
            "id": self.id or str(uuid.uuid4()),
            "status": self.status,
            "intent": self.intent,
            "category": [{"coding": [{
                "system": "http://snomed.info/sct",
                "code": self.category_code,
                "display": self.category_display,
            }]}],
            "code": {"coding": [{
                "system": "http://loinc.org",
                "code": self.loinc_code,
                "display": self.code_display,
            }], "text": self.code_display},
            "subject": {"reference": f"Patient/{self.subject_id}"},
            "encounter": {"reference": f"Encounter/{self.encounter_id}"},
            "authoredOn": self.authored_on,
            "requester": {"reference": f"Practitioner/{self.requester_id}"},
            "priority": self.priority,
            "note": [{"text": self.note}] if self.note else [],
        }

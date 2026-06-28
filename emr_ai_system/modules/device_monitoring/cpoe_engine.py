"""
CPOE Engine — Order Set Library, FHIR Generator, SATUSEHAT Bridge
==================================================================
Business logic layer CPOE:
  1. OrderSetLibrary   — protokol ICU jantung baku (6 protokol)
  2. CPOEValidator     — validasi order + auth check
  3. FHIRGenerator     — konversi order ke FHIR R4 resource
  4. SATUSEHATBridge   — submit ke SATUSEHAT HIE (Kemkes)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .cpoe_models import (
    CPOEBaseOrder, CPOEOrderStatus, CPOEOrderType, CPOEPriority,
    ConsultOrder, DietOrder, DietType, FrequencyCode as FreqCode,
    FHIRMedicationRequest, FHIRServiceRequest,
    ImagingModality, ImagingOrder, LabOrder,
    LAB_PANELS, IMAGING_PRESETS, NURSING_ORDER_PRESETS,
    MedicationCPOEOrder, NursingOrder, NursingOrderType,
    OrderSet, OrderSetItem,
)
from .cpoe_auth import (
    CPOEAuthChecker, CPOEUser, CPOERole,
    Permission, AuthorizationError,
)
from .clma_models import (
    DoseUnit, FrequencyCode, RouteCode,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Order Set Library — Protokol ICCU Jantung RSJPDHK
# =============================================================================

class OrderSetLibrary:
    """
    Kumpulan order set berbasis evidence untuk ICCU Jantung.
    Semua set bisa dikustomisasi per pasien sebelum diaktivasi.
    """

    @staticmethod
    def get_all() -> Dict[str, OrderSet]:
        return {
            "STEMI_PRIMARY_PCI":     OrderSetLibrary.stemi_primary_pci(),
            "CARDIOGENIC_SHOCK":     OrderSetLibrary.cardiogenic_shock(),
            "ADHF_ACUTE":            OrderSetLibrary.adhf_acute(),
            "POST_PCI_MONITORING":   OrderSetLibrary.post_pci_monitoring(),
            "HEPARIN_PROTOCOL":      OrderSetLibrary.heparin_protocol(),
            "SEPTIC_SHOCK_CARDIAC":  OrderSetLibrary.septic_shock_cardiac(),
        }

    @staticmethod
    def stemi_primary_pci() -> OrderSet:
        return OrderSet(
            set_id="STEMI_PRIMARY_PCI",
            name="🫀 STEMI — Primary PCI Protocol",
            description="Order set standar untuk pasien STEMI yang akan/sudah menjalani Primary PCI",
            indication="STEMI onset <12 jam, planned/post primary PCI",
            icd10_code="I21.0 / I21.1 / I21.2",
            evidence_level="ACC/AHA 2022 — IA",
            items=[
                # ── Lab ──────────────────────────────────────────────────────
                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Jantung Akut (ACS)",
                    "tests": LAB_PANELS["Panel Jantung Akut (ACS)"],
                    "lab_priority": "STAT",
                    "frequency": "Baseline, ulang 6 jam, 12 jam",
                }, required=True, rationale="Troponin serial + biomarker nekrosis"),

                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "BGA (Blood Gas Analysis)",
                    "tests": LAB_PANELS["BGA (Blood Gas Analysis)"],
                    "lab_priority": "STAT",
                    "frequency": "Setiap 4-6 jam atau sesuai kondisi",
                }, required=True, rationale="Evaluasi status asam-basa dan oksigenasi"),

                # ── Imaging ───────────────────────────────────────────────────
                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["EKG 12 Lead"],
                    "frequency": "Setiap 6 jam × 24 jam, lalu setiap hari",
                }, required=True, rationale="Monitor ST segmen post PCI"),

                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["Rontgen Toraks Bedside"],
                    "frequency": "Hari 1 post PCI, ulang jika ada perubahan klinis",
                }, required=True, rationale="Evaluasi edema paru, posisi IABP jika ada"),

                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["Ekokardiografi Bedside"],
                    "frequency": "Post PCI hari 1, evaluasi LVEF dan komplikasi mekanik",
                }, required=True, rationale="RWMA, LVEF, komplikasi mekanik"),

                # ── Medikasi ──────────────────────────────────────────────────
                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Aspirin",
                    "drug_generic": "Asam Asetilsalisilat",
                    "dose_value": 160, "dose_unit": "mg",
                    "route": RouteCode.PO.value, "frequency": FrequencyCode.QD.value,
                    "indication": "Antiplatelet loading + maintenance post PCI",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Ticagrelor",
                    "drug_generic": "Ticagrelor",
                    "dose_value": 90, "dose_unit": "mg",
                    "route": RouteCode.PO.value,
                    "frequency": FrequencyCode.Q12H.value,
                    "indication": "DAPT post PCI (preferred over Clopidogrel — ESC 2023)",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Heparin UFH",
                    "drug_generic": "Unfractionated Heparin",
                    "dose_value": 60, "dose_unit": DoseUnit.UNIT_KG_H.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "is_high_alert": True,
                    "indication": "Antikoagulasi peri-PCI",
                    "titration_target": "APTT 60-80 detik",
                    "concentration_mg_ml": 20.0,  # 500u/mL ≈ 20u/mL
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Atorvastatin",
                    "drug_generic": "Atorvastatin",
                    "dose_value": 80, "dose_unit": "mg",
                    "route": RouteCode.PO.value, "frequency": FrequencyCode.QD.value,
                    "indication": "Statin high-intensity post ACS",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Bisoprolol",
                    "drug_generic": "Bisoprolol fumarate",
                    "dose_value": 2.5, "dose_unit": "mg",
                    "route": RouteCode.PO.value, "frequency": FrequencyCode.QD.value,
                    "indication": "Beta-blocker post MI (mulai jika stabil)",
                }, required=False),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Ramipril",
                    "drug_generic": "Ramipril",
                    "dose_value": 2.5, "dose_unit": "mg",
                    "route": RouteCode.PO.value, "frequency": FrequencyCode.Q12H.value,
                    "indication": "ACE inhibitor post MI + LVEF <40%",
                }, required=False),

                # ── Nursing ───────────────────────────────────────────────────
                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Monitoring TTV Ketat (per jam)"],
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Balans Cairan per Jam"],
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Monitoring CVP"],
                }, required=True),

                # ── Diet ──────────────────────────────────────────────────────
                OrderSetItem(CPOEOrderType.DIET, {
                    "diet_type": DietType.CARDIAC_LOW_SODIUM.value,
                    "calorie_target": 1800,
                    "sodium_mg_day": 2000,
                    "fluid_ml_day": 1500,
                    "texture": "Lunak",
                }, required=True),
            ]
        )

    @staticmethod
    def cardiogenic_shock() -> OrderSet:
        return OrderSet(
            set_id="CARDIOGENIC_SHOCK",
            name="⚡ Cardiogenic Shock Protocol",
            description="Manajemen syok kardiogenik — vasopressor + inotrope + monitoring invasif",
            indication="MAP <65 mmHg, CI <2.2 L/min/m², PCWP >18 mmHg, tanda hipoperfusi",
            icd10_code="R57.0",
            evidence_level="ESC Heart Failure 2021 — IIa C / ACC/AHA 2022",
            items=[
                # Lab STAT
                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Jantung Akut (ACS)",
                    "tests": LAB_PANELS["Panel Jantung Akut (ACS)"],
                    "lab_priority": "STAT",
                }, required=True),

                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "BGA STAT",
                    "tests": LAB_PANELS["BGA (Blood Gas Analysis)"],
                    "lab_priority": "STAT",
                    "frequency": "Setiap 2-4 jam",
                }, required=True),

                # Vasopressor UTAMA
                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Norepinephrine",
                    "drug_generic": "Norepinephrine bitartrate",
                    "drug_class": "Vasopressor",
                    "dose_value": 0.1, "dose_unit": DoseUnit.MCG_KG_MIN.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "concentration_mcg_ml": 80.0,
                    "syringe_size_ml": 50.0,
                    "diluent": "NaCl 0.9% total 50 mL",
                    "is_high_alert": True,
                    "titration_target": "MAP ≥65 mmHg. Titrasi 0.05 mcg/kg/min tiap 5-10 mnt",
                    "indication": "Vasopressor pilihan pertama syok kardiogenik (ESC 2021)",
                }, required=True),

                # Inotrope (opsional, pertimbangkan tambahan)
                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Dobutamine",
                    "drug_generic": "Dobutamine HCl",
                    "drug_class": "Inotrope",
                    "dose_value": 5.0, "dose_unit": DoseUnit.MCG_KG_MIN.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "concentration_mcg_ml": 1000.0,
                    "syringe_size_ml": 50.0,
                    "diluent": "NaCl 0.9% total 50 mL",
                    "is_high_alert": True,
                    "titration_target": "CI target ≥2.2 L/min/m²",
                    "indication": "Inotrope jika hipoperfusi menetap meski MAP tercapai",
                }, required=False),

                # Diuretik
                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Furosemide",
                    "drug_generic": "Furosemide",
                    "dose_value": 5.0, "dose_unit": DoseUnit.MG_H.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "concentration_mg_ml": 2.0,
                    "syringe_size_ml": 50.0,
                    "diluent": "NaCl 0.9%",
                    "titration_target": "UO target ≥1 mL/kg/jam",
                    "indication": "Kongesti paru / overload cairan",
                }, required=False),

                # Imaging
                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["Ekokardiografi Bedside"],
                    "clinical_info": "EMERGENT — evaluasi LVEF, RWMA, tamponade, VSD, MR akut",
                }, required=True),

                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["EKG 12 Lead"],
                    "frequency": "Segera + setiap 2 jam",
                }, required=True),

                # Nursing
                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Monitoring TTV Ketat (per jam)"],
                    "frequency_text": "Setiap 30 menit sampai stabil, lalu setiap jam",
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Balans Cairan per Jam"],
                }, required=True),

                # Konsul
                OrderSetItem(CPOEOrderType.CONSULT, {
                    "to_department": "SMF Kardiologi Intervensi",
                    "question": "Evaluasi untuk kemungkinan MCS (IABP/Impella) dan revaskularisasi",
                    "urgency_reason": "Syok kardiogenik refrakter",
                }, required=True),

                # Diet
                OrderSetItem(CPOEOrderType.DIET, {
                    "diet_type": DietType.NPO.value,
                    "route_nutrition": "NGT jika intubasi",
                    "calorie_target": 0,
                }, required=True),
            ]
        )

    @staticmethod
    def adhf_acute() -> OrderSet:
        return OrderSet(
            set_id="ADHF_ACUTE",
            name="💧 ADHF — Acute Decompensated Heart Failure",
            description="Tatalaksana gagal jantung akut dekompensasi",
            indication="Dyspnea berat, edema paru, ADHF NYHA IV",
            icd10_code="I50.0 / I50.1 / I50.9",
            evidence_level="ESC Heart Failure 2021 — I A",
            items=[
                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Heart Failure",
                    "tests": LAB_PANELS["Panel Heart Failure"],
                    "lab_priority": "STAT",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Furosemide",
                    "drug_generic": "Furosemide",
                    "dose_value": 40, "dose_unit": "mg",
                    "route": RouteCode.IV_BOLUS.value,
                    "frequency": FrequencyCode.Q12H.value,
                    "indication": "Dekongestif — sesuaikan berdasarkan UO dan status cairan",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Spironolactone",
                    "drug_generic": "Spironolactone",
                    "dose_value": 25, "dose_unit": "mg",
                    "route": RouteCode.PO.value,
                    "frequency": FrequencyCode.QD.value,
                    "indication": "MRA pada HFrEF (EF <40%)",
                }, required=False),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Nitroglycerin",
                    "drug_generic": "Nitroglycerin",
                    "dose_value": 1.0, "dose_unit": DoseUnit.MCG_KG_MIN.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "concentration_mcg_ml": 200.0,
                    "syringe_size_ml": 50.0,
                    "diluent": "D5W 50 mL",
                    "is_high_alert": False,
                    "titration_target": "Titrasi sampai keluhan dyspnea berkurang; MAP ≥60 mmHg",
                    "indication": "Vasodilator pada ADHF dengan TD ≥110 mmHg",
                }, required=False),

                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["Rontgen Toraks Bedside"],
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Balans Cairan per Jam"],
                    "target": "UO ≥1 mL/kg/jam; target negatif 500-1000 mL/hari",
                }, required=True),

                OrderSetItem(CPOEOrderType.DIET, {
                    "diet_type": DietType.CARDIAC_LOW_SODIUM.value,
                    "calorie_target": 1800,
                    "sodium_mg_day": 1500,
                    "fluid_ml_day": 1000,
                    "texture": "Lunak",
                }, required=True),
            ]
        )

    @staticmethod
    def post_pci_monitoring() -> OrderSet:
        return OrderSet(
            set_id="POST_PCI_MONITORING",
            name="🔬 Post-PCI Monitoring Protocol",
            description="Monitoring dan medikasi standar post prosedur PCI elektif/urgent",
            indication="Post PCI 0-24 jam",
            icd10_code="Z98.61 / Z95.5",
            evidence_level="ACC/AHA PCI Guidelines 2021",
            items=[
                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Koagulasi Lengkap",
                    "tests": LAB_PANELS["Panel Koagulasi Lengkap"],
                    "lab_priority": "URGENT",
                    "frequency": "Post PCI 4 jam",
                }, required=True),

                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Ginjal (kontras nefropati)",
                    "tests": LAB_PANELS["Panel Ginjal"],
                    "lab_priority": "URGENT",
                    "frequency": "Post PCI 24 jam",
                }, required=True),

                OrderSetItem(CPOEOrderType.IMAGING, {
                    **IMAGING_PRESETS["EKG 12 Lead"],
                    "frequency": "Post PCI segera, 6 jam, 24 jam",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Aspirin",
                    "dose_value": 100, "dose_unit": "mg",
                    "route": RouteCode.PO.value,
                    "frequency": FrequencyCode.QD.value,
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Ticagrelor",
                    "dose_value": 90, "dose_unit": "mg",
                    "route": RouteCode.PO.value,
                    "frequency": FrequencyCode.Q12H.value,
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Monitoring TTV Ketat (per jam)"],
                    "frequency_text": "Setiap 30 menit × 4 jam, lalu setiap 1 jam",
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Perawatan Luka CVP / CVC"],
                    "instruction": "Observasi akses femoral/radial — hematom, perdarahan, denyut.",
                    "nursing_type": NursingOrderType.IV_CARE,
                }, required=True),
            ]
        )

    @staticmethod
    def heparin_protocol() -> OrderSet:
        return OrderSet(
            set_id="HEPARIN_PROTOCOL",
            name="🩸 Heparin Weight-Based Protocol",
            description="Antikoagulasi Heparin UFH berbasis berat badan + monitoring APTT",
            indication="AF baru, DVT/PE, ACS-NSTEMI, bridging antikoagulan",
            icd10_code="Z79.01",
            evidence_level="CHEST Guidelines 2022",
            items=[
                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Koagulasi Lengkap",
                    "tests": LAB_PANELS["Panel Koagulasi Lengkap"],
                    "lab_priority": "STAT",
                    "special_instruction": "Baseline pre-heparin. Ulang APTT 6 jam post bolus, lalu setiap 6 jam sampai terapeutik.",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Heparin UFH",
                    "drug_generic": "Unfractionated Heparin",
                    "dose_value": 80, "dose_unit": DoseUnit.UNIT_KG_H.value,
                    "route": RouteCode.IV_BOLUS.value,
                    "frequency": FrequencyCode.STAT.value,
                    "concentration_mg_ml": 100.0,
                    "is_high_alert": True,
                    "indication": "Loading dose IV bolus",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Heparin UFH",
                    "drug_generic": "Unfractionated Heparin",
                    "dose_value": 18, "dose_unit": DoseUnit.UNIT_KG_H.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "concentration_mg_ml": 100.0,
                    "syringe_size_ml": 50.0,
                    "is_high_alert": True,
                    "titration_target": "APTT 60-100 detik (1.5-2.5× normal)",
                    "indication": "Maintenance dose kontinu",
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    "nursing_type": NursingOrderType.VITAL_SIGNS,
                    "instruction": "Observasi tanda perdarahan setiap 4 jam: hematom, hemoptisis, hematuria, feses hitam.",
                    "frequency_text": "Setiap 4 jam",
                    "target": "APTT 60-100 detik",
                }, required=True),
            ]
        )

    @staticmethod
    def septic_shock_cardiac() -> OrderSet:
        return OrderSet(
            set_id="SEPTIC_SHOCK_CARDIAC",
            name="🦠 Septic Shock (Cardiac ICU Protocol)",
            description="Manajemen septic shock pada pasien cardiac ICU — bundle Surviving Sepsis Campaign",
            indication="Suspek sepsis + MAP <65 mmHg + laktat >2 mmol/L",
            icd10_code="A41.9 / R65.21",
            evidence_level="Surviving Sepsis Campaign 2021 — Strong Recommendation",
            items=[
                OrderSetItem(CPOEOrderType.LAB, {
                    "panel_name": "Panel Infeksi / Sepsis",
                    "tests": LAB_PANELS["Panel Infeksi / Sepsis"],
                    "lab_priority": "STAT",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "Norepinephrine",
                    "drug_generic": "Norepinephrine bitartrate",
                    "dose_value": 0.1, "dose_unit": DoseUnit.MCG_KG_MIN.value,
                    "route": RouteCode.IV_CONTINUOUS.value,
                    "frequency": FrequencyCode.CONTINUOUS.value,
                    "concentration_mcg_ml": 80.0,
                    "is_high_alert": True,
                    "titration_target": "MAP ≥65 mmHg — first-line vasopressor septic shock",
                }, required=True),

                OrderSetItem(CPOEOrderType.MEDICATION, {
                    "drug_name": "NaCl 0.9%",
                    "drug_generic": "Sodium Chloride",
                    "dose_value": 500, "dose_unit": "mL",
                    "route": RouteCode.IV_DRIP.value,
                    "frequency": FrequencyCode.STAT.value,
                    "indication": "Fluid resuscitation 30 mL/kg dalam 3 jam pertama. Evaluasi setiap bolus.",
                }, required=True),

                OrderSetItem(CPOEOrderType.NURSING, {
                    **NURSING_ORDER_PRESETS["Balans Cairan per Jam"],
                    "target": "Laktat clearance ≥10%/2 jam; UO ≥0.5 mL/kg/jam; CVP 8-12 mmHg",
                }, required=True),

                OrderSetItem(CPOEOrderType.CONSULT, {
                    "to_department": "Tim DPJP Infeksi / Penyakit Dalam",
                    "question": "Mohon konsultasi pemilihan antibiotik empiris dan sumber infeksi",
                    "urgency_reason": "Septic shock — antibiotik harus diberikan dalam 1 jam",
                }, required=True),
            ]
        )


# =============================================================================
# 2. CPOE Validator
# =============================================================================

class CPOEValidator:
    """Validasi order sebelum tersimpan — auth check + drug check + clinical logic."""

    @staticmethod
    def validate_medication(
        user: CPOEUser,
        drug_name: str,
        is_high_alert: bool,
        is_narcotic: bool,
        dose_value: float,
        dose_unit: str,
        session=None,
    ) -> Tuple[bool, str, str]:
        """Return (can_proceed, message, action_required)."""
        return CPOEAuthChecker.check_medication_order(
            user, drug_name, is_high_alert, is_narcotic, session
        )

    @staticmethod
    def validate_order_set_activation(
        user: CPOEUser,
        order_set: OrderSet,
    ) -> Tuple[bool, str]:
        if not user.can(Permission.ORDER_SET_ACTIVATE):
            return False, (
                f"🚫 {user.role.value} tidak berwenang mengaktivasi Order Set. "
                f"Hanya DPJP / Residen Senior yang dapat melakukan ini."
            )
        return True, f"✓ {user.display_name} berwenang mengaktivasi Order Set."

    @staticmethod
    def validate_lab(user: CPOEUser) -> Tuple[bool, str]:
        if not user.can(Permission.LAB_ORDER):
            return False, f"🚫 {user.role.value} tidak berwenang membuat order lab."
        return True, ""

    @staticmethod
    def validate_imaging(user: CPOEUser) -> Tuple[bool, str]:
        if not user.can(Permission.IMAGING_ORDER):
            return False, f"🚫 {user.role.value} tidak berwenang membuat order imaging."
        return True, ""

    @staticmethod
    def validate_nursing(user: CPOEUser) -> Tuple[bool, str]:
        if not user.can(Permission.NURSING_ORDER):
            return False, f"🚫 {user.role.value} tidak berwenang membuat order keperawatan."
        return True, ""


# =============================================================================
# 3. FHIR Generator
# =============================================================================

# RxNorm codes untuk obat umum ICCU
_RXNORM_MAP: Dict[str, str] = {
    "norepinephrine": "7512",  "epinephrine": "3992",
    "dopamine": "3616",        "dobutamine": "3616",
    "milrinone": "42355",      "vasopressin": "11149",
    "heparin": "5224",         "alteplase": "33692",
    "furosemide": "4603",      "spironolactone": "9997",
    "amiodarone": "703",       "ticagrelor": "1116632",
    "aspirin": "1191",         "atorvastatin": "83367",
    "bisoprolol": "19484",     "ramipril": "35208",
    "nitroglycerin": "4917",   "nitroprusside": "7454",
    "midazolam": "41493",      "propofol": "309004",
    "fentanyl": "37464",       "dexmedetomidine": "854873",
}

# SNOMED CT route codes
_ROUTE_SNOMED: Dict[str, Tuple[str, str]] = {
    "IV Kontinyu":  ("47625008", "Intravenous route"),
    "IV Bolus":     ("47625008", "Intravenous route"),
    "IV Drip":      ("47625008", "Intravenous route"),
    "Per Oral":     ("26643006", "Oral route"),
    "Subkutan":     ("34206005", "Subcutaneous route"),
    "Intramuskular":("78421000", "Intramuscular route"),
    "Inhalasi":     ("18679011000001101", "Inhalation route"),
}


class FHIRGenerator:
    """Konversi CPOE order → FHIR R4 resources."""

    @staticmethod
    def medication_request(
        order: MedicationCPOEOrder,
        patient_satusehat_id: str = "",
        encounter_satusehat_id: str = "",
        practitioner_satusehat_id: str = "",
    ) -> FHIRMedicationRequest:
        rxnorm = _RXNORM_MAP.get(order.drug_name.lower(), "")
        route_code, route_display = _ROUTE_SNOMED.get(order.route, ("", order.route))
        return FHIRMedicationRequest(
            id                = order.order_id,
            status            = "active" if order.status == CPOEOrderStatus.ACTIVE else "draft",
            medication_display= order.drug_name,
            rxnorm_code       = rxnorm,
            subject_id        = patient_satusehat_id or order.episode_id,
            encounter_id      = encounter_satusehat_id or order.episode_id,
            authored_on       = order.ordered_at,
            requester_id      = practitioner_satusehat_id or order.ordered_by_nip,
            dose_value        = order.dose_value,
            dose_unit         = order.dose_unit,
            rate_value        = order.rate_ml_h,
            rate_unit         = "mL/h",
            route_code        = route_code,
            route_display     = route_display,
            note              = order.notes,
        )

    @staticmethod
    def service_request_lab(
        order: LabOrder,
        patient_satusehat_id: str = "",
        encounter_satusehat_id: str = "",
        practitioner_satusehat_id: str = "",
    ) -> FHIRServiceRequest:
        return FHIRServiceRequest(
            id               = order.order_id,
            status           = "active",
            category_code    = "108252007",
            category_display = "Laboratory procedure",
            code_display     = order.panel_name,
            loinc_code       = order.loinc_codes[0] if order.loinc_codes else "",
            subject_id       = patient_satusehat_id or order.episode_id,
            encounter_id     = encounter_satusehat_id or order.episode_id,
            authored_on      = order.ordered_at,
            requester_id     = practitioner_satusehat_id or order.ordered_by_nip,
            priority         = order.lab_priority.value.lower(),
            note             = order.special_instruction,
        )

    @staticmethod
    def service_request_imaging(
        order: ImagingOrder,
        patient_satusehat_id: str = "",
        encounter_satusehat_id: str = "",
        practitioner_satusehat_id: str = "",
    ) -> FHIRServiceRequest:
        return FHIRServiceRequest(
            id               = order.order_id,
            status           = "active",
            category_code    = "363679005",
            category_display = "Imaging",
            code_display     = f"{order.modality.value} — {order.body_region}",
            loinc_code       = "",
            subject_id       = patient_satusehat_id or order.episode_id,
            encounter_id     = encounter_satusehat_id or order.episode_id,
            authored_on      = order.ordered_at,
            requester_id     = practitioner_satusehat_id or order.ordered_by_nip,
            priority         = "stat" if order.priority == CPOEPriority.STAT else "routine",
            note             = order.clinical_info,
        )

    @staticmethod
    def bundle(resources: List) -> dict:
        """Bungkus beberapa resource menjadi FHIR Bundle."""
        return {
            "resourceType": "Bundle",
            "id": str(uuid.uuid4()),
            "type": "transaction",
            "timestamp": datetime.now().isoformat(),
            "entry": [
                {
                    "resource": r.to_dict() if hasattr(r, "to_dict") else r,
                    "request": {
                        "method": "POST",
                        "url": r.resource_type if hasattr(r, "resource_type") else "Resource",
                    }
                }
                for r in resources
            ]
        }

"""
CLMA Engine — 5-Rights Verification, DDI Check, Dose Calculator
================================================================
Core logic layer — tidak ada Streamlit di sini, murni business logic.

Modul ini bertanggung jawab atas:
  1. DoseCalculator   — CPOE order → rate ml/h yang aman
  2. DDIChecker       — Drug-Drug Interaction detection (cardiac ICU specific)
  3. CLMAEngine       — Orchestrator: 5-Rights + DDI + barcode verify + eMAR
  4. PumpProgrammer   — Generate HL7 PCD-03 command ke BeneFusion nDS ex

Referensi klinis:
  • Micromedex Drug Interactions (critical/contraindicated categories)
  • ASHP Guidelines on Preventing Medication Errors
  • ACC/AHA STEMI Guidelines 2023 — Vasopressor dosing
  • ESC Heart Failure Guidelines 2021 — Inotrope dosing
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .clma_models import (
    AlertSeverity, CLMAWorkflowState, DoseUnit, DrugBarcode,
    DrugInteractionAlert, FiveRightsCheck, FrequencyCode,
    MedicationOrder, OrderStatus, PumpProgramCommand,
    RouteCode, ScanResult, eMAR_Record,
)


# =============================================================================
# 1. Dose Calculator
# =============================================================================

@dataclass
class DoseCalculationResult:
    order_id: str
    drug_name: str
    dose_value: float
    dose_unit: DoseUnit
    patient_weight_kg: float
    concentration_mcg_ml: float
    concentration_mg_ml: float
    syringe_size_ml: float
    rate_ml_h: float           # HASIL UTAMA
    dose_mcg_kg_min: float     # normalized untuk VIS
    total_drug_mg: float
    hours_duration: float      # berapa lama syringe bertahan di rate ini
    is_within_range: bool
    safe_range_str: str
    warning: str = ""


# Safe dose ranges (mcg/kg/min kecuali dinyatakan lain)
_SAFE_RANGES: Dict[str, Tuple[float, float, str]] = {
    # drug_key: (min, max, unit)
    "norepinephrine":  (0.01, 3.0,    "mcg/kg/min"),
    "norepinefrin":    (0.01, 3.0,    "mcg/kg/min"),
    "epinephrine":     (0.01, 1.0,    "mcg/kg/min"),
    "epinefrin":       (0.01, 1.0,    "mcg/kg/min"),
    "dopamine":        (2.0,  20.0,   "mcg/kg/min"),
    "dobutamine":      (2.0,  20.0,   "mcg/kg/min"),
    "dobutamin":       (2.0,  20.0,   "mcg/kg/min"),
    "milrinone":       (0.375, 0.75,  "mcg/kg/min"),
    "milrinon":        (0.375, 0.75,  "mcg/kg/min"),
    "vasopressin":     (0.01, 0.04,   "unit/min"),
    "nitroglycerin":   (0.5,  10.0,   "mcg/kg/min"),
    "nitrogliserin":   (0.5,  10.0,   "mcg/kg/min"),
    "nitroprusside":   (0.3,  10.0,   "mcg/kg/min"),
    "nitroprusid":     (0.3,  10.0,   "mcg/kg/min"),
    "heparin":         (12.0, 30.0,   "unit/kg/h"),
    "dexmedetomidine": (0.2,  1.5,    "mcg/kg/h"),
    "dexmedetomidin":  (0.2,  1.5,    "mcg/kg/h"),
    "propofol":        (5.0,  50.0,   "mcg/kg/min"),
    "midazolam":       (0.02, 0.1,    "mg/kg/h"),
    "fentanyl":        (0.5,  2.0,    "mcg/kg/h"),
    "fentanil":        (0.5,  2.0,    "mcg/kg/h"),
    "amiodarone":      (0.5,  1.0,    "mg/min"),
    "amiodaron":       (0.5,  1.0,    "mg/min"),
    "furosemide":      (1.0,  40.0,   "mg/h"),
    "furosemid":       (1.0,  40.0,   "mg/h"),
}


class DoseCalculator:
    """
    Kalkulasi rate ml/h dari berbagai unit dosis untuk continuous IV infusion.
    Semua formula validated terhadap standar KimsMed / RSJPDHK protocol.
    """

    @classmethod
    def calculate(cls, order: MedicationOrder) -> DoseCalculationResult:
        w  = order.patient_weight_kg
        dv = order.dose_value
        du = order.dose_unit
        c_mcg = order.concentration_mcg_ml
        c_mg  = order.concentration_mg_ml
        syr   = order.syringe_size_ml
        drug_key = order.drug_name.lower()

        rate_ml_h      = 0.0
        dose_mcg_kg_min = 0.0

        # ── mcg/kg/min (vasopressor/inotrope — paling umum di ICCU) ──────────
        if du == DoseUnit.MCG_KG_MIN and c_mcg > 0 and w > 0:
            # mcg/kg/min × kg × 60 min/h ÷ mcg/ml = ml/h
            rate_ml_h       = (dv * w * 60) / c_mcg
            dose_mcg_kg_min = dv

        # ── mcg/kg/h ──────────────────────────────────────────────────────────
        elif du == DoseUnit.MCG_KG_H and c_mcg > 0 and w > 0:
            rate_ml_h       = (dv * w) / c_mcg
            dose_mcg_kg_min = dv / 60

        # ── mcg/min ───────────────────────────────────────────────────────────
        elif du == DoseUnit.MCG_MIN and c_mcg > 0:
            rate_ml_h       = (dv * 60) / c_mcg
            dose_mcg_kg_min = dv / w if w > 0 else 0

        # ── mcg/h ─────────────────────────────────────────────────────────────
        elif du == DoseUnit.MCG_H and c_mcg > 0:
            rate_ml_h       = dv / c_mcg
            dose_mcg_kg_min = (dv / 60) / w if w > 0 else 0

        # ── mg/h ──────────────────────────────────────────────────────────────
        elif du == DoseUnit.MG_H and c_mg > 0:
            rate_ml_h       = dv / c_mg

        # ── mg/kg/h ───────────────────────────────────────────────────────────
        elif du == DoseUnit.MG_KG_H and c_mg > 0 and w > 0:
            rate_ml_h       = (dv * w) / c_mg

        # ── unit/h (Heparin) ──────────────────────────────────────────────────
        elif du == DoseUnit.UNIT_H:
            # order.concentration_mg_ml digunakan sebagai unit/ml untuk heparin
            unit_per_ml = c_mg  # repurpose field: unit/ml
            if unit_per_ml > 0:
                rate_ml_h = dv / unit_per_ml

        # ── unit/kg/h (Heparin weight-based) ─────────────────────────────────
        elif du == DoseUnit.UNIT_KG_H and w > 0:
            unit_per_ml = c_mg
            if unit_per_ml > 0:
                rate_ml_h = (dv * w) / unit_per_ml

        # ── ml/h (sudah dalam ml/h) ───────────────────────────────────────────
        elif du == DoseUnit.ML_H:
            rate_ml_h = dv

        # Round ke 2 desimal
        rate_ml_h = round(rate_ml_h, 2)

        # Hitung durasi syringe
        hours_dur = syr / rate_ml_h if rate_ml_h > 0 else 0.0

        # Cek safe range
        total_drug_mg = (c_mcg * syr / 1000) if c_mcg > 0 else (c_mg * syr)
        is_within, safe_str, warning = cls._check_range(drug_key, dose_mcg_kg_min, du, dv, w)

        return DoseCalculationResult(
            order_id             = order.order_id,
            drug_name            = order.drug_name,
            dose_value           = dv,
            dose_unit            = du,
            patient_weight_kg    = w,
            concentration_mcg_ml = c_mcg,
            concentration_mg_ml  = c_mg,
            syringe_size_ml      = syr,
            rate_ml_h            = rate_ml_h,
            dose_mcg_kg_min      = dose_mcg_kg_min,
            total_drug_mg        = total_drug_mg,
            hours_duration       = hours_dur,
            is_within_range      = is_within,
            safe_range_str       = safe_str,
            warning              = warning,
        )

    @staticmethod
    def _check_range(drug_key, dose_n, du, dv, w) -> Tuple[bool, str, str]:
        data = _SAFE_RANGES.get(drug_key)
        if not data:
            return True, "Tidak ada data rentang", ""
        lo, hi, unit = data

        # Normalize ke nilai yang tepat untuk range check
        if unit == "mcg/kg/min":
            val = dose_n   # dose_mcg_kg_min
        elif unit == "mcg/kg/h":
            val = dose_n * 60
        elif unit in ("mg/min", "mg/h", "unit/min", "unit/kg/h"):
            val = dv
        else:
            val = dv

        safe_str = f"{lo}–{hi} {unit}"
        if val < lo:
            return False, safe_str, f"⚠️ Dosis terlalu rendah ({val:.3f} {unit})"
        if val > hi:
            return False, safe_str, f"🔴 DOSIS BERLEBIH! {val:.3f} {unit} (max {hi})"
        return True, safe_str, ""


# =============================================================================
# 2. DDI Checker — Drug-Drug Interaction (Cardiac ICU)
# =============================================================================

# Format: (drug_a, drug_b): (severity, mechanism, effect, recommendation, is_contraindicated)
_DDI_DB: Dict[Tuple[str, str], Tuple[AlertSeverity, str, str, str, bool]] = {

    # ── KONTRAINDIKASI ─────────────────────────────────────────────────────────
    ("vasopressin", "epinephrine"): (
        AlertSeverity.CRITICAL,
        "Aditivitas vasokonstriksi berlebihan",
        "Iskemia organ berat, nekrosis akral, gagal ginjal akut",
        "Hindari kombinasi. Jika mutlak perlu: monitor ketat perfusi perifer.",
        True,
    ),
    ("nitroprusside", "sildenafil"): (
        AlertSeverity.CRITICAL,
        "Potensiasi efek NO-cGMP → vasodilatasi massif",
        "Hipotensi berat tidak terkontrol",
        "KONTRAINDIKASI ABSOLUT. Hentikan sildenafil ≥48 jam sebelum SNP.",
        True,
    ),
    ("amiodarone", "procainamide"): (
        AlertSeverity.CRITICAL,
        "Blok kanal Na+ + K+ additif → QT prolongation massif",
        "Risiko Torsades de Pointes / Fibrilasi Ventrikel",
        "Hindari kombinasi antiaritmia Kelas I + III. Monitor QTc.",
        True,
    ),

    # ── INTERAKSI BERAT ────────────────────────────────────────────────────────
    ("amiodarone", "digoxin"): (
        AlertSeverity.HIGH,
        "Amiodarone inhibisi P-gp dan CYP2D6 → peningkatan kadar digoxin",
        "Toksisitas digoxin: bradikardia, blok AV, aritmia ventrikel",
        "Kurangi dosis digoxin 50%. Monitor kadar serum digoxin dan EKG.",
        False,
    ),
    ("amiodarone", "warfarin"): (
        AlertSeverity.HIGH,
        "Amiodarone inhibisi CYP2C9 → peningkatan efek antikoagulan",
        "Perdarahan mayor",
        "Kurangi dosis warfarin 30-50%. Monitor INR ketat setiap 2-3 hari.",
        False,
    ),
    ("heparin", "alteplase"): (
        AlertSeverity.HIGH,
        "Aditivitas efek antikoagulan + fibrinolisis",
        "Perdarahan mayor / intrakranial",
        "Stop heparin selama infus alteplase. Restart hanya jika aPTT <80 detik.",
        False,
    ),
    ("milrinone", "dobutamine"): (
        AlertSeverity.HIGH,
        "Aditivitas inotropik + kronotropik berlebihan",
        "Takiaritmia, peningkatan konsumsi O2 miokard, risiko VT",
        "Monitor EKG kontinu, batasi dosis masing-masing. Pertimbangkan alternatif.",
        False,
    ),
    ("norepinephrine", "epinephrine"): (
        AlertSeverity.HIGH,
        "Aditivitas vasokonstriksi alfa-1",
        "Hipertensi berat, iskemia perifer, gagal ginjal",
        "Hindari kombinasi. Jika terpaksa: titrasi ketat, monitor MAP dan urine output.",
        False,
    ),
    ("dopamine", "monoamine_oxidase"): (
        AlertSeverity.HIGH,
        "MAOI inhibisi degradasi katekolamin",
        "Krisis hipertensi, aritmia fatal",
        "Kurangi dosis dopamine 1/10 dari dosis biasa. Monitor ketat.",
        False,
    ),
    ("furosemide", "amiodarone"): (
        AlertSeverity.HIGH,
        "Hipokalemia akibat furosemide → meningkatkan toksisitas amiodarone",
        "QT prolongation, Torsades de Pointes",
        "Monitor K+ dan Mg2+ serum ketat. Koreksi elektrolit sebelum amiodarone.",
        False,
    ),
    ("kcl", "spironolactone"): (
        AlertSeverity.HIGH,
        "Aditivitas retensi kalium",
        "Hiperkalemia berat (K+ >6 mEq/L): aritmia fatal",
        "Monitor K+ serum setiap 6 jam. Hindari kombinasi bila K+ >5 mEq/L.",
        False,
    ),

    # ── INTERAKSI SEDANG ───────────────────────────────────────────────────────
    ("furosemide", "kcl"): (
        AlertSeverity.MODERATE,
        "Furosemide meningkatkan ekskresi K+ — KCl sebagai pengganti",
        "Kalau KCl melebihi kompensasi kehilangan → hiperkalemia",
        "Titrasi KCl berdasarkan kadar serum. Monitor EKG untuk peaked T-wave.",
        False,
    ),
    ("heparin", "aspirin"): (
        AlertSeverity.MODERATE,
        "Aditivitas antikoagulan + antiplatelet",
        "Peningkatan risiko perdarahan (tidak fatal pada dosis terapi)",
        "Kombinasi lazim di ICCU jantung. Monitor tanda perdarahan.",
        False,
    ),
    ("propofol", "midazolam"): (
        AlertSeverity.MODERATE,
        "Sinergisme CNS depression",
        "Sedasi berlebihan, apnea, hipotensi",
        "Kurangi dosis masing-masing. Monitor RASS score dan tanda vital.",
        False,
    ),
    ("dexmedetomidine", "propofol"): (
        AlertSeverity.MODERATE,
        "Sinergisme sedatif + bradikardi",
        "Bradikardia berat, hipotensi",
        "Titrasi hati-hati. Dexmedetomidine cenderung sparing propofol.",
        False,
    ),
    ("amiodarone", "metoprolol"): (
        AlertSeverity.MODERATE,
        "Aditivitas blok simpatis + konduksi AV",
        "Bradikardia, blok AV derajat tinggi",
        "Monitor HR dan PR interval. Siapkan atropin / transcutaneous pacing.",
        False,
    ),
    ("nitroglycerin", "sildenafil"): (
        AlertSeverity.CRITICAL,
        "Potensiasi efek NO → vasodilatasi massif",
        "Hipotensi berat, sinkop, iskemia miokard rebound",
        "KONTRAINDIKASI. Interval minimal: sildenafil 48 jam, tadalafil 72 jam.",
        True,
    ),
    ("alteplase", "heparin"): (
        AlertSeverity.HIGH,
        "Aditivitas fibrinolisis + antikoagulan",
        "Perdarahan mayor",
        "Jika sequential: tunggu 4 jam post-tPA sebelum restart heparin.",
        False,
    ),
    ("fentanyl", "midazolam"): (
        AlertSeverity.MODERATE,
        "Sinergisme opioid + benzodiazepin pada depresi napas",
        "Apnea, desaturasi",
        "Titrasi ketat. Siapkan nalokson dan flumazenil. Monitor SpO2 kontinu.",
        False,
    ),
    ("levosimendan", "dobutamine"): (
        AlertSeverity.MODERATE,
        "Aditivitas inotropik melalui mekanisme berbeda",
        "Takikardia, hipotensi, konsumsi O2 meningkat",
        "Umumnya aman. Pertimbangkan henti dobutamine saat mulai levosimendan.",
        False,
    ),
}


def _normalize(name: str) -> str:
    return name.strip().lower().replace("-", "").replace(" ", "")


class DDIChecker:
    """Periksa interaksi obat baru terhadap semua obat yang sedang berjalan."""

    @classmethod
    def check(
        cls,
        new_drug: str,
        active_drugs: List[str],
        order_id: str = "",
    ) -> List[DrugInteractionAlert]:
        alerts: List[DrugInteractionAlert] = []
        new_key = _normalize(new_drug)

        for active in active_drugs:
            active_key = _normalize(active)
            pair = cls._find_pair(new_key, active_key)
            if pair:
                sev, mech, effect, rec, contra = pair
                alerts.append(DrugInteractionAlert(
                    order_id       = order_id,
                    perpetrator    = new_drug,
                    victim         = active,
                    mechanism      = mech,
                    effect         = effect,
                    severity       = sev,
                    recommendation = rec,
                    is_contraindicated = contra,
                ))

        # Sort: CRITICAL → HIGH → MODERATE → LOW
        sev_order = {
            AlertSeverity.CRITICAL: 0, AlertSeverity.HIGH: 1,
            AlertSeverity.MODERATE: 2, AlertSeverity.LOW: 3, AlertSeverity.INFO: 4,
        }
        alerts.sort(key=lambda a: sev_order.get(a.severity, 5))
        return alerts

    @staticmethod
    def _find_pair(a: str, b: str) -> Optional[tuple]:
        for (ka, kb), data in _DDI_DB.items():
            if (_normalize(ka) in a or a in _normalize(ka)) and \
               (_normalize(kb) in b or b in _normalize(kb)):
                return data
            if (_normalize(kb) in a or a in _normalize(kb)) and \
               (_normalize(ka) in b or b in _normalize(ka)):
                return data
        return None


# =============================================================================
# 3. Allergy Checker
# =============================================================================

_CROSS_ALLERGY: Dict[str, List[str]] = {
    "sulfa":        ["furosemide", "hydrochlorothiazide"],
    "penicillin":   ["ampicillin", "amoxicillin", "piperacillin"],
    "cephalosporin":["cefazolin", "ceftriaxone", "cefepime"],
    "aspirin":      ["ibuprofen", "naproxen", "ketorolac"],
    "contrast":     ["iodine"],
}


class AllergyChecker:

    @staticmethod
    def check(new_drug: str, allergies: List[str]) -> List[str]:
        """Return list of allergy warnings."""
        warnings = []
        new_key = _normalize(new_drug)
        for allergy in allergies:
            allergy_key = _normalize(allergy)
            # Direct match
            if allergy_key in new_key or new_key in allergy_key:
                warnings.append(f"🚫 ALERGI LANGSUNG: {new_drug} vs {allergy}")
            # Cross-reactivity
            for group, members in _CROSS_ALLERGY.items():
                if allergy_key in _normalize(group) or \
                   any(allergy_key in _normalize(m) for m in members):
                    if any(_normalize(m) in new_key for m in members):
                        warnings.append(
                            f"⚠️ CROSS-ALERGI: {new_drug} ↔ {allergy} (grup {group})"
                        )
        return warnings


# =============================================================================
# 4. CLMA Engine — Orchestrator
# =============================================================================

class CLMAEngine:
    """
    Main engine untuk seluruh pipeline CLMA.
    Stateless — state disimpan di CLMAWorkflowState (atau database via clma_gateway).
    """

    # ── Order creation ─────────────────────────────────────────────────────────

    @staticmethod
    def create_order(
        episode_id: str,
        patient_name: str,
        patient_no_rm: str,
        patient_weight_kg: float,
        drug_name: str,
        drug_generic: str,
        drug_class: str,
        dose_value: float,
        dose_unit: DoseUnit,
        route: RouteCode,
        frequency: FrequencyCode,
        concentration_mcg_ml: float,
        concentration_mg_ml: float,
        syringe_size_ml: float,
        diluent: str,
        ordered_by: str,
        ordered_by_nip: str,
        total_volume_ml: float = 0.0,
        notes: str = "",
    ) -> Tuple[MedicationOrder, DoseCalculationResult]:
        """
        Buat MedicationOrder baru + hitung rate ml/h.
        Return (order, calc_result).
        """
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

        order = MedicationOrder(
            order_id=order_id,
            episode_id=episode_id,
            patient_name=patient_name,
            patient_no_rm=patient_no_rm,
            patient_weight_kg=patient_weight_kg,
            drug_name=drug_name,
            drug_generic=drug_generic,
            drug_class=drug_class,
            dose_value=dose_value,
            dose_unit=dose_unit,
            route=route,
            frequency=frequency,
            concentration_mcg_ml=concentration_mcg_ml,
            concentration_mg_ml=concentration_mg_ml,
            syringe_size_ml=syringe_size_ml,
            diluent=diluent,
            rate_ml_h=0.0,          # akan diisi setelah kalkulasi
            total_volume_ml=total_volume_ml or syringe_size_ml,
            ordered_by=ordered_by,
            ordered_by_nip=ordered_by_nip,
            ordered_at=datetime.now().isoformat(),
            is_high_alert=CLMAEngine._is_high_alert(drug_name),
            is_double_check_required=CLMAEngine._needs_double_check(drug_name),
            scheduled_time=datetime.now().isoformat(),
            valid_until=(datetime.now() + timedelta(hours=1)).isoformat(),
            notes=notes,
        )

        calc = DoseCalculator.calculate(order)
        order.rate_ml_h = calc.rate_ml_h

        return order, calc

    # ── 5-Rights Verification ──────────────────────────────────────────────────

    @staticmethod
    def verify_five_rights(
        order: MedicationOrder,
        barcode: DrugBarcode,
        scanned_patient_id: str,
        nurse_nip: str,
        current_active_drugs: Optional[List[str]] = None,
        patient_allergies: Optional[List[str]] = None,
    ) -> FiveRightsCheck:
        """
        Verifikasi 5+1 Rights:
          1. Right Patient  — barcode episode_id == order episode_id
          2. Right Drug     — barcode drug_name ≈ order drug_name
          3. Right Dose     — barcode dose_label ≈ order dose
          4. Right Route    — barcode route == order route
          5. Right Time     — sekarang dalam ±30 menit dari scheduled_time
          6. Right Doc      — order sudah verified farmasi + tidak ada DDI kritis
        """
        now = datetime.now().isoformat()
        check_id = f"5R-{now[:19].replace(':', '').replace('-', '')}"

        # 1 — Right Patient
        r_patient = (barcode.order_id == order.order_id and
                     scanned_patient_id == order.episode_id)
        rp_note = ("✓" if r_patient else
                   f"Mismatch: scan={scanned_patient_id}, order={order.episode_id}")

        # 2 — Right Drug
        r_drug = _normalize(barcode.drug_name) in _normalize(order.drug_name) or \
                 _normalize(order.drug_name) in _normalize(barcode.drug_name)
        rd_note = ("✓" if r_drug else
                   f"Barcode: {barcode.drug_name}, Order: {order.drug_name}")

        # 3 — Right Dose
        # Ekstrak angka dari label dan bandingkan (toleransi ±5%)
        r_dose = True
        dose_note = "✓ Dosis sesuai label"
        try:
            nums = re.findall(r"[\d.]+", barcode.dose_label)
            if nums:
                label_dose = float(nums[0])
                tol = abs(label_dose - order.dose_value) / max(order.dose_value, 0.001)
                if tol > 0.05:
                    r_dose = False
                    dose_note = f"Label: {barcode.dose_label}, Order: {order.dose_value}"
        except Exception:
            dose_note = "Tidak dapat verifikasi dosis — cek manual"

        # 4 — Right Route
        r_route = (barcode.route == order.route)
        rr_note = ("✓" if r_route else
                   f"Barcode: {barcode.route.value}, Order: {order.route.value}")

        # 5 — Right Time
        r_time = order.is_scheduled_now or order.is_continuous
        rt_note = ("✓ Waktu sesuai" if r_time else
                   f"Scheduled: {order.scheduled_time}")

        # 6 — Right Doc (verifikasi farmasi + cek DDI + alergi)
        pharmacy_ok = order.status in (OrderStatus.VERIFIED, OrderStatus.DISPENSED,
                                        OrderStatus.READY)
        ddi_alerts = []
        if current_active_drugs:
            ddi_alerts = DDIChecker.check(order.drug_name, current_active_drugs, order.order_id)
        allergy_warns = []
        if patient_allergies:
            allergy_warns = AllergyChecker.check(order.drug_name, patient_allergies)

        has_critical_ddi     = any(a.severity == AlertSeverity.CRITICAL for a in ddi_alerts)
        has_critical_allergy = len(allergy_warns) > 0

        r_doc = pharmacy_ok and not has_critical_ddi and not has_critical_allergy
        rdoc_note = "✓"
        if not pharmacy_ok:
            rdoc_note = "⚠️ Order belum diverifikasi farmasi"
        elif has_critical_allergy:
            rdoc_note = f"🚫 ALERGI: {'; '.join(allergy_warns)}"
        elif has_critical_ddi:
            rdoc_note = f"🚫 DDI KRITIS: {ddi_alerts[0].perpetrator} ↔ {ddi_alerts[0].victim}"

        # Barcode expired?
        if barcode.is_expired:
            r_drug = False
            rd_note = f"🔴 OBAT KADALUARSA sejak {barcode.expires_at}"

        # Determine overall result
        all_pass = all([r_patient, r_drug, r_dose, r_route, r_time, r_doc])
        if all_pass:
            result = ScanResult.PASS
        elif not r_patient:
            result = ScanResult.FAIL_PATIENT
        elif barcode.is_expired:
            result = ScanResult.FAIL_EXPIRED
        elif has_critical_allergy:
            result = ScanResult.FAIL_ALLERGY
        elif has_critical_ddi:
            result = ScanResult.FAIL_DDI
        elif not r_drug:
            result = ScanResult.FAIL_DRUG
        elif not r_dose:
            result = ScanResult.FAIL_DOSE
        elif not r_route:
            result = ScanResult.FAIL_ROUTE
        elif not r_time:
            result = ScanResult.FAIL_TIME
        else:
            result = ScanResult.FAIL_DRUG

        return FiveRightsCheck(
            order_id         = order.order_id,
            checked_at       = now,
            checked_by       = nurse_nip,
            scan_result      = result,
            right_patient    = r_patient,
            right_drug       = r_drug,
            right_dose       = r_dose,
            right_route      = r_route,
            right_time       = r_time,
            right_doc        = r_doc,
            right_patient_note = rp_note,
            right_drug_note    = rd_note,
            right_dose_note    = dose_note,
            right_route_note   = rr_note,
            right_time_note    = rt_note,
            right_doc_note     = rdoc_note,
        )

    # ── eMAR Documentation ────────────────────────────────────────────────────

    @staticmethod
    def create_emar(
        order: MedicationOrder,
        five_rights: FiveRightsCheck,
        nurse_nip: str,
        nurse_name: str,
        rate_actual: float,
        pump_id: str = "",
        pump_programmed: bool = False,
        site: str = "",
        witness_nip: str = "",
        notes: str = "",
    ) -> eMAR_Record:
        emar_id = f"EMAR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        return eMAR_Record(
            emar_id              = emar_id,
            order_id             = order.order_id,
            episode_id           = order.episode_id,
            drug_name            = order.drug_name,
            dose_given           = order.dose_value,
            dose_unit            = order.dose_unit.value,
            rate_ml_h_actual     = rate_actual,
            route                = order.route.value,
            administered_by      = nurse_nip,
            administered_by_name = nurse_name,
            administered_at      = datetime.now().isoformat(),
            witness_by           = witness_nip,
            scan_result          = five_rights.scan_result.value,
            five_rights_score    = five_rights.score,
            pump_id              = pump_id,
            pump_programmed      = pump_programmed,
            site                 = site,
            notes                = notes,
        )

    # ── Pump Auto-Program Command ──────────────────────────────────────────────

    @staticmethod
    def create_pump_command(
        order: MedicationOrder,
        pump_id: str,
        commanded_by: str,
    ) -> PumpProgramCommand:
        return PumpProgramCommand(
            pump_id         = pump_id,
            order_id        = order.order_id,
            drug_name       = order.drug_name,
            rate_ml_h       = order.rate_ml_h,
            vtbi_ml         = order.total_volume_ml,
            concentration_str = order.concentration_display,
            commanded_by    = commanded_by,
            commanded_at    = datetime.now().isoformat(),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_high_alert(drug: str) -> bool:
        high_alert_list = [
            "heparin", "warfarin", "insulin", "alteplase", "streptokinase",
            "tenecteplase", "potassium", "kcl", "concentrated electrolyte",
            "neuromuscular blocker", "vecuronium", "rocuronium", "pancuronium",
            "epinephrine", "epinefrin", "norepinephrine", "vasopressin",
            "nitroprusside", "nitroprusid", "magnesium", "concentrated nacl",
        ]
        d = drug.lower()
        return any(ha in d or d in ha for ha in high_alert_list)

    @staticmethod
    def _needs_double_check(drug: str) -> bool:
        double_check_list = [
            "insulin", "heparin", "alteplase", "kcl", "nitroprusside",
            "epinephrine", "norepinephrine", "vasopressin", "magnesium",
        ]
        d = drug.lower()
        return any(dc in d or d in dc for dc in double_check_list)

    # ── Demo order helper ──────────────────────────────────────────────────────

    @staticmethod
    def make_demo_order(episode_id: str, patient_name: str, weight_kg: float = 60.0) -> Tuple:
        """Demo order Norepinephrine 0.1 mcg/kg/min — sesuai foto ICCU."""
        return CLMAEngine.create_order(
            episode_id           = episode_id,
            patient_name         = patient_name,
            patient_no_rm        = "00-12-34-56",
            patient_weight_kg    = weight_kg,
            drug_name            = "Norepinephrine",
            drug_generic         = "Norepinephrine bitartrate",
            drug_class           = "Vasopressor",
            dose_value           = 0.1,
            dose_unit            = DoseUnit.MCG_KG_MIN,
            route                = RouteCode.IV_CONTINUOUS,
            frequency            = FrequencyCode.CONTINUOUS,
            concentration_mcg_ml = 80.0,   # 4 mg/50 mL
            concentration_mg_ml  = 0.0,
            syringe_size_ml      = 50.0,
            diluent              = "NaCl 0.9% — total 50 mL",
            ordered_by           = "dr. Budi, Sp.JP",
            ordered_by_nip       = "198501010001",
            notes                = "Titrasi target MAP ≥65 mmHg",
        )

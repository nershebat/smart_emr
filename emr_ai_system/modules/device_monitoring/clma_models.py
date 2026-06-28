"""
CLMA Models — Closed Loop Medication Administration
====================================================
Data models lengkap untuk seluruh pipeline CLMA:
  CPOE (Order) → Pharmacy Verify → Dispense → Scan → 5-Rights → Administer → eMAR

Referensi:
  • IHE PCD TF-2: ACM Profile (Alert Communication Management)
  • IHE PCD TF-2: IPEC Profile (Infusion Pump Event Communication)
  • HIMSS EMRAM Level 7 — Closed Loop Medication requirement
  • Permenkes No. 72 Tahun 2016 — Standar Pelayanan Kefarmasian di RS
  • SDKI / SLKI / SIKI — Standar Asuhan Keperawatan Indonesia
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


# =============================================================================
# Enumerations
# =============================================================================

class OrderStatus(Enum):
    DRAFT         = "Draft"
    PENDING       = "Menunggu Verifikasi Farmasi"
    VERIFIED      = "Terverifikasi Farmasi"
    DISPENSED     = "Disiapkan / Dispensing"
    READY         = "Siap Diberikan"
    ADMINISTERED  = "Sudah Diberikan"
    HOLD          = "Ditahan"
    CANCELLED     = "Dibatalkan"
    COMPLETED     = "Selesai"


class RouteCode(Enum):
    IV_CONTINUOUS = "IV Kontinyu"
    IV_BOLUS      = "IV Bolus"
    IV_DRIP       = "IV Drip"
    SC            = "Subkutan"
    IM            = "Intramuskular"
    PO            = "Per Oral"
    SL            = "Sublingual"
    INHALASI      = "Inhalasi"
    TOPIKAL       = "Topikal"
    NG            = "Nasogastrik"


class FrequencyCode(Enum):
    CONTINUOUS = "Kontinyu"
    STAT       = "Segera (STAT)"
    QH         = "Setiap 1 jam"
    Q2H        = "Setiap 2 jam"
    Q4H        = "Setiap 4 jam"
    Q6H        = "Setiap 6 jam"
    Q8H        = "Setiap 8 jam"
    Q12H       = "Setiap 12 jam"
    QD         = "Sehari sekali"
    PRN        = "Jika perlu (PRN)"


class DoseUnit(Enum):
    MCG_KG_MIN  = "mcg/kg/menit"
    MCG_KG_H    = "mcg/kg/jam"
    MCG_MIN     = "mcg/menit"
    MCG_H       = "mcg/jam"
    MG_H        = "mg/jam"
    MG_KG_H     = "mg/kg/jam"
    UNIT_H      = "unit/jam"
    UNIT_KG_H   = "unit/kg/jam"
    ML_H        = "ml/jam"
    MG          = "mg"
    MCG         = "mcg"
    UNIT        = "unit"
    MEQ         = "mEq"


class ScanResult(Enum):
    PASS          = "PASS"
    FAIL_PATIENT  = "GAGAL - Pasien tidak sesuai"
    FAIL_DRUG     = "GAGAL - Obat tidak sesuai"
    FAIL_DOSE     = "GAGAL - Dosis tidak sesuai"
    FAIL_ROUTE    = "GAGAL - Rute tidak sesuai"
    FAIL_TIME     = "GAGAL - Waktu tidak sesuai (>30 menit)"
    FAIL_EXPIRED  = "GAGAL - Obat kadaluarsa"
    FAIL_ALLERGY  = "GAGAL - Alergi terdeteksi"
    FAIL_DDI      = "GAGAL - Interaksi obat berbahaya"
    OVERRIDE      = "OVERRIDE - Diizinkan dengan alasan"


class AlertSeverity(Enum):
    CRITICAL  = "KRITIS"
    HIGH      = "TINGGI"
    MODERATE  = "SEDANG"
    LOW       = "RENDAH"
    INFO      = "INFORMASI"


class VerificationStep(Enum):
    RIGHT_PATIENT = "Pasien Benar"
    RIGHT_DRUG    = "Obat Benar"
    RIGHT_DOSE    = "Dosis Benar"
    RIGHT_ROUTE   = "Rute Benar"
    RIGHT_TIME    = "Waktu Benar"
    RIGHT_DOC     = "Dokumentasi Benar"   # 6th right


# =============================================================================
# Core Models
# =============================================================================

@dataclass
class PatientAllergy:
    drug_name: str
    reaction: str
    severity: AlertSeverity = AlertSeverity.HIGH
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DrugBarcode:
    """Representasi label barcode yang ditempel Farmasi pada obat."""
    barcode_id: str              # unique ID per unit/syringe
    order_id: str
    drug_name: str
    drug_generic: str
    concentration_str: str       # "4 mg/50 mL = 80 mcg/mL"
    dose_label: str              # "0.1 mcg/kg/min"
    route: RouteCode
    prepared_by: str             # NIP apoteker
    prepared_at: str
    expires_at: str              # tanggal/jam kadaluarsa (max 24 jam IV)
    lot_number: str = ""
    ndc_code: str = ""           # Nomor Dagang / kode BPOM
    is_dispensed: bool = True

    @property
    def is_expired(self) -> bool:
        try:
            return datetime.now() > datetime.fromisoformat(self.expires_at)
        except Exception:
            return False


@dataclass
class MedicationOrder:
    """
    CPOE — Order dari DPJP/residen. Entry point CLMA pipeline.
    """
    order_id: str
    episode_id: str
    patient_name: str
    patient_no_rm: str
    patient_weight_kg: float

    # Drug identity
    drug_name: str
    drug_generic: str
    drug_class: str              # dari DrugCategory.value

    # Dose specification
    dose_value: float
    dose_unit: DoseUnit
    route: RouteCode
    frequency: FrequencyCode

    # Preparation / concentration
    concentration_mcg_ml: float  # untuk obat mcg-based
    concentration_mg_ml: float   # untuk obat mg-based
    syringe_size_ml: float
    diluent: str                 # "NaCl 0.9% 50 mL", "D5W 250 mL"

    # Calculated delivery
    rate_ml_h: float             # dihitung otomatis oleh engine
    total_volume_ml: float

    # Ordering info
    ordered_by: str              # nama DPJP
    ordered_by_nip: str
    ordered_at: str

    # Workflow status
    status: OrderStatus = OrderStatus.PENDING
    verified_by: str = ""
    verified_at: str = ""
    dispensed_by: str = ""
    dispensed_at: str = ""
    administered_by: str = ""
    administered_at: str = ""

    # Timing
    scheduled_time: str = ""
    valid_until: str = ""

    # Flags
    is_high_alert: bool = False
    is_double_check_required: bool = False
    barcode_id: str = ""
    notes: str = ""
    override_reason: str = ""

    @property
    def is_continuous(self) -> bool:
        return self.frequency == FrequencyCode.CONTINUOUS

    @property
    def is_scheduled_now(self) -> bool:
        if not self.scheduled_time:
            return True
        try:
            sched = datetime.fromisoformat(self.scheduled_time)
            return abs((datetime.now() - sched).total_seconds()) <= 1800
        except Exception:
            return True

    @property
    def concentration_display(self) -> str:
        if self.concentration_mcg_ml > 0:
            total_mcg = self.concentration_mcg_ml * self.syringe_size_ml
            total_mg  = total_mcg / 1000
            return (f"{total_mg:.1f} mg / {self.syringe_size_ml:.0f} mL "
                    f"= {self.concentration_mcg_ml:.1f} mcg/mL")
        elif self.concentration_mg_ml > 0:
            total_mg = self.concentration_mg_ml * self.syringe_size_ml
            return (f"{total_mg:.1f} mg / {self.syringe_size_ml:.0f} mL "
                    f"= {self.concentration_mg_ml:.2f} mg/mL")
        return "—"

    @property
    def order_summary(self) -> str:
        return (
            f"{self.drug_name} {self.dose_value} {self.dose_unit.value} "
            f"via {self.route.value} | Rate: {self.rate_ml_h:.2f} ml/h"
        )


@dataclass
class FiveRightsCheck:
    """
    Hasil verifikasi 5+1 Rights sebelum administrasi.
    Dibuat oleh CLMAEngine.verify_five_rights().
    """
    order_id: str
    checked_at: str
    checked_by: str           # NIP perawat
    scan_result: ScanResult

    # Per-right detail
    right_patient: bool = False
    right_drug:    bool = False
    right_dose:    bool = False
    right_route:   bool = False
    right_time:    bool = False
    right_doc:     bool = False

    right_patient_note: str = ""
    right_drug_note:    str = ""
    right_dose_note:    str = ""
    right_route_note:   str = ""
    right_time_note:    str = ""
    right_doc_note:     str = ""

    # Override
    override_allowed: bool = False
    override_reason:  str  = ""
    double_checked_by: str = ""

    @property
    def all_pass(self) -> bool:
        return all([
            self.right_patient, self.right_drug, self.right_dose,
            self.right_route, self.right_time, self.right_doc,
        ])

    @property
    def failed_rights(self) -> List[str]:
        mapping = {
            "Pasien":  self.right_patient,
            "Obat":    self.right_drug,
            "Dosis":   self.right_dose,
            "Rute":    self.right_route,
            "Waktu":   self.right_time,
            "Dokumen": self.right_doc,
        }
        return [k for k, v in mapping.items() if not v]

    @property
    def score(self) -> int:
        return sum([
            self.right_patient, self.right_drug, self.right_dose,
            self.right_route, self.right_time, self.right_doc,
        ])


@dataclass
class DrugInteractionAlert:
    """Hasil pemeriksaan Drug-Drug Interaction (DDI)."""
    order_id: str
    perpetrator: str       # obat yang dipesan (baru)
    victim: str            # obat yang sudah jalan
    mechanism: str         # mekanisme interaksi
    effect: str            # efek klinis
    severity: AlertSeverity
    recommendation: str
    references: str = ""
    is_contraindicated: bool = False

    @property
    def display_badge(self) -> str:
        return {
            AlertSeverity.CRITICAL: "🚫 KONTRAINDIKASI",
            AlertSeverity.HIGH:     "🔴 INTERAKSI BERAT",
            AlertSeverity.MODERATE: "🟠 INTERAKSI SEDANG",
            AlertSeverity.LOW:      "🟡 INTERAKSI RINGAN",
            AlertSeverity.INFO:     "ℹ️ PERHATIAN",
        }.get(self.severity, "⚠️")


@dataclass
class eMAR_Record:
    """
    Electronic Medication Administration Record — dokumentasi administrasi.
    Titik akhir CLMA pipeline.
    """
    emar_id: str
    order_id: str
    episode_id: str
    drug_name: str
    dose_given: float
    dose_unit: str
    rate_ml_h_actual: float
    route: str
    administered_by: str      # NIP perawat
    administered_by_name: str
    administered_at: str
    witness_by: str = ""      # untuk high-alert drug
    scan_result: str = ScanResult.PASS.value
    five_rights_score: int = 6
    pump_id: str = ""         # pump yang dipakai (dari infusion_gateway)
    pump_programmed: bool = False
    site: str = ""            # lokasi IV (CVC, lumen proksimal, dst.)
    notes: str = ""
    adverse_event: str = ""

    @property
    def is_high_alert_verified(self) -> bool:
        return bool(self.witness_by)

    @property
    def formatted_time(self) -> str:
        try:
            return datetime.fromisoformat(self.administered_at).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return self.administered_at


@dataclass
class PumpProgramCommand:
    """
    Perintah auto-program ke Mindray BeneFusion — dikirim via HL7 PCD-01 / BCISLink.
    """
    pump_id: str
    order_id: str
    drug_name: str
    rate_ml_h: float
    vtbi_ml: float
    concentration_str: str
    commanded_by: str
    commanded_at: str
    status: str = "PENDING"      # PENDING | SENT | ACK | REJECTED
    ack_message: str = ""

    def to_hl7_pcd03(self) -> str:
        """
        Generate HL7 PCD-03 Infusion Order Programming command.
        Dikirim ke nDS ex yang kemudian mem-program eSP ex terkait.
        """
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        return (
            f"MSH|^~\\&|SMARTEMR|RSJPDHK|BENEFUSION_NDS|ICCU|{now}||"
            f"RAS^O17^RAS_O17|CMD{now}|P|2.6\r"
            f"PID|1||{self.order_id}\r"
            f"ORC|RE|{self.order_id}||{self.pump_id}\r"
            f"RXR|IV\r"
            f"TQ1|1|||{self.rate_ml_h}^mL/h\r"
            f"OBX|1|NM|158480^MDC_FLOW_FLUID_PUMP^MDC||{self.rate_ml_h}|mL/h\r"
            f"OBX|2|NM|157985^MDC_VOL_FLUID_TBI^MDC||{self.vtbi_ml}|mL\r"
            f"OBX|3|TX|157976^MDC_DEV_PUMP_INFUS_DRUG_NAME^MDC||{self.drug_name}\r"
        )


@dataclass
class CLMAWorkflowState:
    """
    State machine satu siklus CLMA per order.
    Dipakai sebagai context object yang berjalan sepanjang pipeline.
    """
    order: MedicationOrder
    barcode: Optional[DrugBarcode] = None
    five_rights: Optional[FiveRightsCheck] = None
    ddi_alerts: List[DrugInteractionAlert] = field(default_factory=list)
    emar: Optional[eMAR_Record] = None
    pump_command: Optional[PumpProgramCommand] = None

    @property
    def current_stage(self) -> str:
        if self.emar:
            return "✅ SELESAI — eMAR Terdokumentasi"
        if self.five_rights and self.five_rights.all_pass:
            return "💉 Siap Administrasi"
        if self.five_rights:
            return "⚠️ 5-Rights Gagal"
        if self.barcode:
            return "📱 Barcode Terpindai — Menunggu Verifikasi 5-Rights"
        if self.order.status == OrderStatus.DISPENSED:
            return "📦 Obat Disiapkan — Menunggu Scan Barcode"
        if self.order.status == OrderStatus.VERIFIED:
            return "✓ Terverifikasi Farmasi — Menunggu Dispensing"
        return "⏳ Menunggu Verifikasi Farmasi"

    @property
    def can_administer(self) -> bool:
        if self.five_rights and self.five_rights.scan_result == ScanResult.PASS:
            return True
        # Override diizinkan untuk kondisi darurat ICCU
        if (self.five_rights and self.five_rights.override_allowed
                and self.five_rights.override_reason):
            return True
        return False

    @property
    def has_critical_ddi(self) -> bool:
        return any(a.severity == AlertSeverity.CRITICAL or a.is_contraindicated
                   for a in self.ddi_alerts)

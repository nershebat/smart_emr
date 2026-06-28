"""
Infusion Pump Gateway — Mindray BeneFusion eSP ex / nDS ex
===========================================================
Integrasi syringe pump & volumetric pump ke Smart EMR via:
  1. HL7 v2.6 IHE PCD-01 (Infusion Pump Event Communication) — dari nDS ex
  2. Input manual (fallback jika network belum tersedia)
  3. CDSS Bridge — deteksi vasopressor aktif & generate konteks untuk cdss_engine

Alur data dari foto (RSJPDHK ICCU):
  Mindray BeneFusion nDS ex (Network Drug Station)
       │  HL7 PCD-01 · TCP/IP
       ▼
  HL7PumpParser → InfusionPump objects
       │
       ├─▶ VasopressorIndex.calculate() → VIS Score
       ├─▶ InfusionCDSSBridge.generate_context() → teks untuk cdss_engine
       └─▶ Monitor_Device.py (UI)

Referensi:
  • IHE PCD Technical Framework Vol.2 — PCD-01 Profile
  • Mindray BeneFusion eSP ex / nDS ex Connectivity Guide
  • Vasoactive-Inotropic Score (VIS) — McIntosh et al., Pediatr Crit Care Med 2012
  • SDKI D.0019 Penurunan Curah Jantung, D.0142 Syok Kardiogenik
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

# ── Drug category ─────────────────────────────────────────────────────────────

class DrugCategory(Enum):
    VASOPRESSOR    = "Vasopressor"
    INOTROPE       = "Inotrope"
    ANTIARRHYTHMIC = "Antiaritmia"
    ANTICOAGULANT  = "Antikoagulan"
    DIURETIC       = "Diuretik"
    VASODILATOR    = "Vasodilator"
    SEDATION       = "Sedasi"
    ANALGESIC      = "Analgesik"
    THROMBOLYTIC   = "Trombolitik"
    ELECTROLYTE    = "Elektrolit"
    OTHER          = "Lainnya"


class PumpStatus(Enum):
    RUNNING   = "Running"
    STOPPED   = "Stopped"
    KVO       = "KVO"          # Keep Vein Open
    ALARMING  = "Alarm"
    OCCLUSION = "Oklusi"
    EMPTY     = "Habis"
    PAUSED    = "Pause"
    STANDBY   = "Standby"
    UNKNOWN   = "Tidak Diketahui"


# ── Drug database — obat umum kardiovaskular ICU Indonesia ────────────────────

@dataclass
class DrugInfo:
    category: DrugCategory
    cdss_code: str
    critical: bool = False          # wajib flagging ke CDSS
    vis_weight: float = 0.0         # bobot di VIS Score
    normal_range_mlh: Tuple[float, float] = (0.0, 999.0)

_DRUG_DB: Dict[str, DrugInfo] = {
    # ── Vasopressors ───────────────────────────────────────────────────────────
    "norepinephrine":  DrugInfo(DrugCategory.VASOPRESSOR, "NOREPI",  True,  100.0),
    "noradrenaline":   DrugInfo(DrugCategory.VASOPRESSOR, "NOREPI",  True,  100.0),
    "norepinefrin":    DrugInfo(DrugCategory.VASOPRESSOR, "NOREPI",  True,  100.0),
    "nor":             DrugInfo(DrugCategory.VASOPRESSOR, "NOREPI",  True,  100.0),
    "ne":              DrugInfo(DrugCategory.VASOPRESSOR, "NOREPI",  True,  100.0),
    "dopamine":        DrugInfo(DrugCategory.VASOPRESSOR, "DOPA",    True,    1.0),
    "epinephrine":     DrugInfo(DrugCategory.VASOPRESSOR, "EPI",     True,  100.0),
    "adrenaline":      DrugInfo(DrugCategory.VASOPRESSOR, "EPI",     True,  100.0),
    "epinefrin":       DrugInfo(DrugCategory.VASOPRESSOR, "EPI",     True,  100.0),
    "vasopressin":     DrugInfo(DrugCategory.VASOPRESSOR, "AVP",     True, 10000.0),
    "phenylephrine":   DrugInfo(DrugCategory.VASOPRESSOR, "PHE",     False,   0.0),
    "phenilefrin":     DrugInfo(DrugCategory.VASOPRESSOR, "PHE",     False,   0.0),
    # ── Inotropes ──────────────────────────────────────────────────────────────
    "dobutamine":      DrugInfo(DrugCategory.INOTROPE,    "DOBU",    True,    1.0),
    "dobutamin":       DrugInfo(DrugCategory.INOTROPE,    "DOBU",    True,    1.0),
    "milrinone":       DrugInfo(DrugCategory.INOTROPE,    "MILRI",   True,   10.0),
    "milrinon":        DrugInfo(DrugCategory.INOTROPE,    "MILRI",   True,   10.0),
    "levosimendan":    DrugInfo(DrugCategory.INOTROPE,    "LEVO",    True,    0.0),
    "digoxin":         DrugInfo(DrugCategory.INOTROPE,    "DIGO",    False,   0.0),
    # ── Antiarrhythmics ────────────────────────────────────────────────────────
    "amiodarone":      DrugInfo(DrugCategory.ANTIARRHYTHMIC, "AMIO", True,   0.0),
    "amiodaron":       DrugInfo(DrugCategory.ANTIARRHYTHMIC, "AMIO", True,   0.0),
    "lidocaine":       DrugInfo(DrugCategory.ANTIARRHYTHMIC, "LIDO", False,  0.0),
    "esmolol":         DrugInfo(DrugCategory.ANTIARRHYTHMIC, "ESMOL",False,  0.0),
    "adenosine":       DrugInfo(DrugCategory.ANTIARRHYTHMIC, "ADO",  False,  0.0),
    "verapamil":       DrugInfo(DrugCategory.ANTIARRHYTHMIC, "VERA", False,  0.0),
    "diltiazem":       DrugInfo(DrugCategory.ANTIARRHYTHMIC, "DILT", False,  0.0),
    # ── Anticoagulants ─────────────────────────────────────────────────────────
    "heparin":         DrugInfo(DrugCategory.ANTICOAGULANT, "UFH",   True,   0.0),
    "bivalirudin":     DrugInfo(DrugCategory.ANTICOAGULANT, "BIVAL", True,   0.0),
    "argatroban":      DrugInfo(DrugCategory.ANTICOAGULANT, "ARGA",  True,   0.0),
    # ── Vasodilators ───────────────────────────────────────────────────────────
    "nitroglycerin":   DrugInfo(DrugCategory.VASODILATOR,  "NTG",    False,  0.0),
    "nitrogliserin":   DrugInfo(DrugCategory.VASODILATOR,  "NTG",    False,  0.0),
    "ntg":             DrugInfo(DrugCategory.VASODILATOR,  "NTG",    False,  0.0),
    "nitroprusside":   DrugInfo(DrugCategory.VASODILATOR,  "SNP",    True,   0.0),
    "nitroprusid":     DrugInfo(DrugCategory.VASODILATOR,  "SNP",    True,   0.0),
    # ── Diuretics ──────────────────────────────────────────────────────────────
    "furosemide":      DrugInfo(DrugCategory.DIURETIC,     "FURO",   False,  0.0),
    "furosemid":       DrugInfo(DrugCategory.DIURETIC,     "FURO",   False,  0.0),
    "lasix":           DrugInfo(DrugCategory.DIURETIC,     "FURO",   False,  0.0),
    # ── Sedation/Analgesia ─────────────────────────────────────────────────────
    "midazolam":       DrugInfo(DrugCategory.SEDATION,     "MDZ",    False,  0.0),
    "propofol":        DrugInfo(DrugCategory.SEDATION,     "PROP",   False,  0.0),
    "dexmedetomidine": DrugInfo(DrugCategory.SEDATION,     "DEX",    False,  0.0),
    "dexmedetomidin":  DrugInfo(DrugCategory.SEDATION,     "DEX",    False,  0.0),
    "fentanyl":        DrugInfo(DrugCategory.ANALGESIC,    "FENT",   False,  0.0),
    "fentanil":        DrugInfo(DrugCategory.ANALGESIC,    "FENT",   False,  0.0),
    "morphine":        DrugInfo(DrugCategory.ANALGESIC,    "MORPH",  False,  0.0),
    "morfin":          DrugInfo(DrugCategory.ANALGESIC,    "MORPH",  False,  0.0),
    # ── Thrombolytics ──────────────────────────────────────────────────────────
    "alteplase":       DrugInfo(DrugCategory.THROMBOLYTIC,  "TPA",   True,   0.0),
    "streptokinase":   DrugInfo(DrugCategory.THROMBOLYTIC,  "SK",    True,   0.0),
    "tenecteplase":    DrugInfo(DrugCategory.THROMBOLYTIC,  "TNK",   True,   0.0),
    # ── Electrolytes ───────────────────────────────────────────────────────────
    "kcl":             DrugInfo(DrugCategory.ELECTROLYTE,   "KCL",   False,  0.0),
    "magnesium":       DrugInfo(DrugCategory.ELECTROLYTE,   "MGS",   False,  0.0),
    "magnesium sulfate":DrugInfo(DrugCategory.ELECTROLYTE,  "MGS",   False,  0.0),
    "insulin":         DrugInfo(DrugCategory.OTHER,         "INSUL", False,  0.0),
}

# ── HL7 PCD-01 MDC codes (IHE PCD TF-2) ─────────────────────────────────────
MDC_PUMP_MAP: Dict[str, str] = {
    # MDC code         → internal field
    "158480":  "rate_mlh",
    "157985":  "vtbi_ml",
    "157986":  "volume_infused_ml",
    "157942":  "line_pressure_mmhg",
    "157976":  "drug_name",
    "157977":  "dose_rate",           # mcg/kg/min jika tersedia
    "157978":  "concentration",       # mcg/ml
    "69965":   "device_id",
    # Mindray proprietary (BeneFusion nDS ex)
    "MDR-PUMP-RATE":   "rate_mlh",
    "MDR-PUMP-VTBI":   "vtbi_ml",
    "MDR-PUMP-VOL":    "volume_infused_ml",
    "MDR-PUMP-PRES":   "line_pressure_mmhg",
    "MDR-PUMP-DRUG":   "drug_name",
    "MDR-PUMP-STATUS": "status_raw",
    "MDR-PUMP-TIME":   "run_time_seconds",
    "MDR-PUMP-SYR":    "syringe_size_ml",
    "MDR-PUMP-MODE":   "rate_mode",
}

# Map status string dari device → PumpStatus enum
PUMP_STATUS_MAP: Dict[str, PumpStatus] = {
    "1": PumpStatus.RUNNING,  "RUNNING": PumpStatus.RUNNING,
    "RUN": PumpStatus.RUNNING, "INFUSING": PumpStatus.RUNNING,
    "0": PumpStatus.STOPPED,  "STOPPED": PumpStatus.STOPPED,
    "STOP": PumpStatus.STOPPED,
    "2": PumpStatus.ALARMING, "ALARM": PumpStatus.ALARMING,
    "KVO": PumpStatus.KVO,    "3": PumpStatus.KVO,
    "OCC": PumpStatus.OCCLUSION, "OCCLUSION": PumpStatus.OCCLUSION,
    "EMPTY": PumpStatus.EMPTY, "4": PumpStatus.EMPTY,
    "PAUSED": PumpStatus.PAUSED, "PAUSE": PumpStatus.PAUSED,
    "STANDBY": PumpStatus.STANDBY,
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PumpAlarm:
    pump_id: str
    timestamp: str
    alarm_type: str
    level: str            # "CRITICAL" | "WARNING" | "INFO"
    message: str


@dataclass
class InfusionPump:
    """
    Representasi satu syringe/volumetric pump dari BeneFusion eSP ex / nDS ex.
    """
    pump_id: str                         # "PUMP-01", "PUMP-02", dst.
    timestamp: str
    drug_name: str                       # "Norepinephrine"
    drug_category: DrugCategory
    cdss_code: str                       # "NOREPI", "DOBU", dst.
    rate_mlh: float                      # ml/h
    volume_infused_ml: float             # ml sudah terinfus
    vtbi_ml: float                       # ml sisa (Volume To Be Infused)
    line_pressure_mmhg: float            # mmHg
    status: PumpStatus
    syringe_size_ml: float               # 20 | 30 | 50 ml
    run_time_seconds: int
    rate_mode: str                       # "50ml-KimsMed", "20ml-KimsMed", dst.
    is_critical: bool = False
    source: str = "manual"               # "manual" | "hl7_pcd01" | "mindray_bcis"
    concentration_mcg_ml: float = 0.0   # opsional, untuk VIS score
    dose_rate_mcg_kg_min: float = 0.0   # opsional
    patient_weight_kg: float = 0.0      # opsional
    notes: str = ""

    @property
    def run_time_str(self) -> str:
        h, rem = divmod(self.run_time_seconds, 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def remaining_hours(self) -> float:
        if self.rate_mlh > 0 and self.vtbi_ml > 0:
            return self.vtbi_ml / self.rate_mlh
        return 0.0

    @property
    def is_vasopressor(self) -> bool:
        return self.drug_category == DrugCategory.VASOPRESSOR

    @property
    def is_inotrope(self) -> bool:
        return self.drug_category in (DrugCategory.INOTROPE, DrugCategory.VASOPRESSOR)

    @property
    def is_running(self) -> bool:
        return self.status == PumpStatus.RUNNING

    @property
    def status_emoji(self) -> str:
        return {
            PumpStatus.RUNNING:   "🟢",
            PumpStatus.STOPPED:   "⚫",
            PumpStatus.KVO:       "🔵",
            PumpStatus.ALARMING:  "🔴",
            PumpStatus.OCCLUSION: "🟠",
            PumpStatus.EMPTY:     "🟡",
            PumpStatus.PAUSED:    "⚪",
            PumpStatus.STANDBY:   "⚪",
        }.get(self.status, "❓")


# =============================================================================
# Drug Resolver
# =============================================================================

class DrugResolver:
    """Resolve nama obat (case-insensitive, alias) → DrugInfo."""

    @staticmethod
    def resolve(name: str) -> DrugInfo:
        key = name.strip().lower()
        # Exact match dulu
        if key in _DRUG_DB:
            return _DRUG_DB[key]
        # Partial match (nama di kamus ada di string obat, atau sebaliknya)
        for k, v in _DRUG_DB.items():
            if k in key or key in k:
                return v
        # Default: unknown
        return DrugInfo(DrugCategory.OTHER, "UNK", False)

    @staticmethod
    def category_emoji(cat: DrugCategory) -> str:
        return {
            DrugCategory.VASOPRESSOR:    "💉",
            DrugCategory.INOTROPE:       "🫀",
            DrugCategory.ANTIARRHYTHMIC: "⚡",
            DrugCategory.ANTICOAGULANT:  "🩸",
            DrugCategory.DIURETIC:       "💧",
            DrugCategory.VASODILATOR:    "🔽",
            DrugCategory.SEDATION:       "😴",
            DrugCategory.ANALGESIC:      "🩹",
            DrugCategory.THROMBOLYTIC:   "🧬",
            DrugCategory.ELECTROLYTE:    "⚗️",
        }.get(cat, "💊")


# =============================================================================
# HL7 PCD-01 Parser
# =============================================================================

class HL7PumpParser:
    """
    Parse HL7 v2.6 IHE PCD-01 message dari Mindray BeneFusion nDS ex.

    Struktur pesan PCD-01 (simplified):
      MSH|^~\\&|BENEFUSION_NDS|RSJPDHK_ICCU||SMARTEMR|timestamp||ORU^R01|...|2.6
      PID|1||episode_id^^^RSJPDHK
      PV1|1|I|ICCU^BED^SLOT
      OBR|1|||69965^MDC_DEV_PUMP_INFUS^MDC
      OBX|1|TX|157976^MDC_DEV_PUMP_INFUS_DRUG_NAME^MDC||Norepinephrine
      OBX|2|NM|158480^MDC_FLOW_FLUID_PUMP^MDC||0.75|mL/h
      OBX|3|NM|157985^MDC_VOL_FLUID_TBI^MDC||1068|mL
      OBX|4|NM|157942^MDC_PRESS_LINE^MDC||28|mmHg
      OBX|5|NM|MDR-PUMP-TIME^RunTime^MDR||111860|s
      OBX|6|TX|MDR-PUMP-STATUS^Status^MDR||1
      OBX|7|NM|MDR-PUMP-SYR^SyringeSize^MDR||50|mL
    """

    @classmethod
    def parse_pcd01(cls, raw: str, pump_id: str = "PUMP-01") -> Optional[InfusionPump]:
        """
        Parse raw HL7 string → InfusionPump.
        Return None jika bukan PCD-01 valid atau tidak ada data pump.
        """
        raw = raw.strip()
        if not raw.startswith("MSH"):
            return None

        # Parse semua OBX ke dict field → value
        parsed: Dict[str, str] = {}
        for line in re.split(r"[\r\n]+", raw):
            line = line.strip()
            if not line.startswith("OBX"):
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue
            obs_id  = parts[3].split("^")[0].strip()   # MDC code
            raw_val = parts[5].strip()                  # OBX-5 value

            field_name = MDC_PUMP_MAP.get(obs_id)
            if field_name:
                parsed[field_name] = raw_val

        if not parsed:
            return None

        # Resolve drug
        drug_raw = parsed.get("drug_name", "Unknown")
        drug_info = DrugResolver.resolve(drug_raw)

        # Parse numerics
        def _f(key: str, dflt: float = 0.0) -> float:
            try:
                return float(re.sub(r"[^\d.\-]", "", parsed.get(key, str(dflt))))
            except (ValueError, TypeError):
                return dflt

        # Parse status
        status_raw = parsed.get("status_raw", "1").upper().strip()
        status = PUMP_STATUS_MAP.get(status_raw, PumpStatus.RUNNING)

        return InfusionPump(
            pump_id             = pump_id,
            timestamp           = datetime.now().isoformat(),
            drug_name           = drug_raw,
            drug_category       = drug_info.category,
            cdss_code           = drug_info.cdss_code,
            rate_mlh            = _f("rate_mlh"),
            volume_infused_ml   = _f("volume_infused_ml"),
            vtbi_ml             = _f("vtbi_ml"),
            line_pressure_mmhg  = _f("line_pressure_mmhg"),
            status              = status,
            syringe_size_ml     = _f("syringe_size_ml", 50.0),
            run_time_seconds    = int(_f("run_time_seconds")),
            rate_mode           = parsed.get("rate_mode", ""),
            is_critical         = drug_info.critical,
            source              = "hl7_pcd01",
            concentration_mcg_ml= _f("concentration"),
            dose_rate_mcg_kg_min= _f("dose_rate"),
        )


# =============================================================================
# Vasoactive-Inotropic Score (VIS)
# =============================================================================

class VasopressorIndex:
    """
    Hitung Vasoactive-Inotropic Score (VIS) dari daftar pump aktif.

    Formula (McIntosh et al., 2012):
      VIS = Dopamine + Dobutamine + 100×Epinephrine + 10×Milrinone
            + 10000×Vasopressin + 100×Norepinephrine
      (semua dalam mcg/kg/min, Vasopressin dalam unit/kg/min)

    Karena kita hanya punya ml/h dan bukan mcg/kg/min:
      - Kalau concentration + weight tersedia → hitung VIS formal
      - Kalau tidak → VIS Surrogate (jumlah dan kelas vasopressor)
    """

    @staticmethod
    def calculate(pumps: List[InfusionPump]) -> Dict:
        active    = [p for p in pumps if p.is_running]
        vasopres  = [p for p in active if p.is_vasopressor]
        inotropes = [p for p in active if p.drug_category == DrugCategory.INOTROPE]
        critical  = [p for p in active if p.is_critical]

        # VIS formal (jika dose_rate tersedia)
        vis_score = sum(p.dose_rate_mcg_kg_min * p.vis_weight_factor
                        for p in active if p.dose_rate_mcg_kg_min > 0)

        # VIS surrogate (berdasarkan jumlah vasopressor)
        n_vp = len(vasopres)
        if n_vp == 0:
            burden = "Tidak Ada"
            burden_color = "green"
        elif n_vp == 1 and all(p.rate_mlh < 2 for p in vasopres):
            burden = "Ringan"
            burden_color = "yellow"
        elif n_vp == 1:
            burden = "Sedang"
            burden_color = "orange"
        elif n_vp == 2:
            burden = "Berat"
            burden_color = "red"
        else:
            burden = "Refrakter"
            burden_color = "darkred"

        cdss_codes = list({p.cdss_code for p in critical})

        return {
            "active_pumps":    len(active),
            "vasopressors":    vasopres,
            "inotropes":       inotropes,
            "critical_drugs":  critical,
            "vis_score":       vis_score,
            "vis_formal":      vis_score > 0,
            "burden":          burden,
            "burden_color":    burden_color,
            "cdss_codes":      cdss_codes,
            "n_vasopressor":   n_vp,
            "has_vasopressor": n_vp > 0,
            "has_inotrope":    len(inotropes) > 0,
        }

    @staticmethod
    def cdss_context_text(pumps: List[InfusionPump]) -> str:
        """
        Generate teks konteks untuk cdss_engine dan CPPT Objective.
        Contoh output:
          VASOAKTIF: Norepinephrine 0.75 ml/h (31:04:20, P=28 mmHg) [RUNNING]
          INOTROPIK: -
          BURDEN: Sedang (1 vasopressor aktif)
        """
        active = [p for p in pumps if p.is_running]
        if not active:
            return "INFUSION PUMP: Tidak ada obat vasoaktif/inotropik aktif."

        lines = ["=== INFUSION PUMP (Mindray BeneFusion) ==="]

        vasopres = [p for p in active if p.is_vasopressor]
        inotropes = [p for p in active if p.drug_category == DrugCategory.INOTROPE]
        others    = [p for p in active if not p.is_vasopressor
                     and p.drug_category != DrugCategory.INOTROPE]

        def fmt(p: InfusionPump) -> str:
            return (
                f"{p.drug_name} {p.rate_mlh:.2f} ml/h "
                f"(Run: {p.run_time_str}, P: {p.line_pressure_mmhg:.0f} mmHg) "
                f"[{p.status.value}]"
            )

        lines.append("VASOAKTIF  : " + (
            " | ".join(fmt(p) for p in vasopres) if vasopres else "-"
        ))
        lines.append("INOTROPIK  : " + (
            " | ".join(fmt(p) for p in inotropes) if inotropes else "-"
        ))
        if others:
            lines.append("OBAT LAIN  : " + " | ".join(fmt(p) for p in others))

        n_vp = len(vasopres)
        burden = VasopressorIndex.calculate(pumps)["burden"]
        lines.append(f"BURDEN     : {burden} ({n_vp} vasopressor aktif)")
        lines.append(
            f"TOTAL PUMP : {len(active)} running dari {len(pumps)} terdaftar"
        )
        return "\n".join(lines)


# Helper: vis_weight_factor property untuk InfusionPump
def _vis_weight(pump: InfusionPump) -> float:
    return _DRUG_DB.get(pump.drug_name.lower(), DrugInfo(DrugCategory.OTHER, "UNK")).vis_weight

# Monkey-patch (agar tidak perlu ubah frozen dataclass)
InfusionPump.vis_weight_factor = property(lambda self: _vis_weight(self))  # type: ignore


# =============================================================================
# Alarm Generator
# =============================================================================

class InfusionAlarmChecker:
    """Cek kondisi alarm dari daftar pump aktif."""

    @staticmethod
    def check(pumps: List[InfusionPump]) -> List[PumpAlarm]:
        alarms: List[PumpAlarm] = []
        now = datetime.now().isoformat()

        for p in pumps:
            # Alarm status device
            if p.status == PumpStatus.ALARMING:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="DEVICE_ALARM", level="CRITICAL",
                    message=f"🔴 {p.pump_id} [{p.drug_name}] — Device ALARM!",
                ))
            if p.status == PumpStatus.OCCLUSION:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="OCCLUSION", level="CRITICAL",
                    message=f"🟠 {p.pump_id} [{p.drug_name}] — OKLUSI line!",
                ))
            if p.status == PumpStatus.EMPTY:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="EMPTY", level="WARNING",
                    message=f"🟡 {p.pump_id} [{p.drug_name}] — Syringe HABIS!",
                ))

            # High line pressure
            if p.is_running and p.line_pressure_mmhg > 400:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="HIGH_PRESSURE", level="CRITICAL",
                    message=f"🔴 {p.pump_id} [{p.drug_name}] — Tekanan line {p.line_pressure_mmhg:.0f} mmHg (oklusi?)",
                ))
            elif p.is_running and p.line_pressure_mmhg > 250:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="HIGH_PRESSURE", level="WARNING",
                    message=f"🟠 {p.pump_id} [{p.drug_name}] — Tekanan line tinggi {p.line_pressure_mmhg:.0f} mmHg",
                ))

            # Sisa cairan hampir habis
            if p.is_running and 0 < p.remaining_hours < 1:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="LOW_VOLUME", level="WARNING",
                    message=f"🟡 {p.pump_id} [{p.drug_name}] — Sisa {p.vtbi_ml:.0f} ml, "
                            f"habis ~{p.remaining_hours*60:.0f} menit",
                ))

            # Critical drug stopped unexpectedly
            if p.is_critical and p.status == PumpStatus.STOPPED and p.run_time_seconds > 300:
                alarms.append(PumpAlarm(
                    pump_id=p.pump_id, timestamp=now,
                    alarm_type="CRITICAL_STOPPED", level="CRITICAL",
                    message=f"🔴 {p.pump_id} [{p.drug_name}] — OBAT KRITIS BERHENTI!",
                ))

        return alarms


# =============================================================================
# Manual Input Helper (factory function)
# =============================================================================

def create_manual_pump(
    pump_id: str,
    drug_name: str,
    rate_mlh: float,
    syringe_size_ml: float = 50.0,
    volume_infused_ml: float = 0.0,
    vtbi_ml: float = 0.0,
    line_pressure_mmhg: float = 0.0,
    run_time_hms: str = "00:00:00",
    status: PumpStatus = PumpStatus.RUNNING,
    rate_mode: str = "",
    concentration_mcg_ml: float = 0.0,
    patient_weight_kg: float = 0.0,
) -> InfusionPump:
    """Factory untuk membuat InfusionPump dari input manual UI."""
    drug_info = DrugResolver.resolve(drug_name)

    # Parse HH:MM:SS → detik
    try:
        parts = [int(x) for x in run_time_hms.split(":")]
        run_secs = parts[0]*3600 + parts[1]*60 + (parts[2] if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        run_secs = 0

    # Hitung dose rate jika concentration dan weight tersedia
    dose_rate = 0.0
    if concentration_mcg_ml > 0 and patient_weight_kg > 0 and rate_mlh > 0:
        # ml/h × mcg/ml ÷ 60 ÷ kg = mcg/kg/min
        dose_rate = (rate_mlh * concentration_mcg_ml) / 60 / patient_weight_kg

    return InfusionPump(
        pump_id              = pump_id,
        timestamp            = datetime.now().isoformat(),
        drug_name            = drug_name,
        drug_category        = drug_info.category,
        cdss_code            = drug_info.cdss_code,
        rate_mlh             = rate_mlh,
        volume_infused_ml    = volume_infused_ml,
        vtbi_ml              = vtbi_ml,
        line_pressure_mmhg   = line_pressure_mmhg,
        status               = status,
        syringe_size_ml      = syringe_size_ml,
        run_time_seconds     = run_secs,
        rate_mode            = rate_mode,
        is_critical          = drug_info.critical,
        source               = "manual",
        concentration_mcg_ml = concentration_mcg_ml,
        dose_rate_mcg_kg_min = dose_rate,
        patient_weight_kg    = patient_weight_kg,
    )


# =============================================================================
# Demo Data — mereplikasi kondisi di foto ICCU
# =============================================================================

def create_demo_pumps() -> List[InfusionPump]:
    """
    Replika kondisi pump di foto RSJPDHK ICCU:
      • PUMP-01: Norepinephrine 0.75 ml/h, 50ml, running 31:04:20, P=28 mmHg
      • PUMP-02: Undefined 1.0 ml/h, 20ml, running 01:14, P=7 mmHg
    """
    return [
        InfusionPump(
            pump_id="PUMP-01", timestamp=datetime.now().isoformat(),
            drug_name="Norepinephrine",
            drug_category=DrugCategory.VASOPRESSOR, cdss_code="NOREPI",
            rate_mlh=0.75, volume_infused_ml=1072.74, vtbi_ml=1068.0,
            line_pressure_mmhg=28.0, status=PumpStatus.RUNNING,
            syringe_size_ml=50.0, run_time_seconds=111860,
            rate_mode="50ml-KimsMed", is_critical=True, source="demo",
        ),
        InfusionPump(
            pump_id="PUMP-02", timestamp=datetime.now().isoformat(),
            drug_name="Undefined",
            drug_category=DrugCategory.OTHER, cdss_code="UNK",
            rate_mlh=1.0, volume_infused_ml=253.0, vtbi_ml=253.0,
            line_pressure_mmhg=7.0, status=PumpStatus.RUNNING,
            syringe_size_ml=20.0, run_time_seconds=4484,
            rate_mode="20ml-KimsMed", is_critical=False, source="demo",
        ),
    ]

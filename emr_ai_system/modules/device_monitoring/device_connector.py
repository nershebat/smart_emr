"""
Device Connector v2 — tambahan infusion pump support
Diff dari v1: tambah _infusion_pumps, _cb_infusion, get_infusion_pumps,
add_pump_manual, remove_pump, get_vasopressor_context.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st

from .hl7_gateway import (
    HL7MLLPServer, HL7VitalExtractor, HL7Message,
    DeviceConnectionStatus, make_demo_oru,
)
from .dicom_gateway import DICOMGateway, DICOMConfig, check_dicom_dependencies  # noqa
from .models import VitalSigns, VentilatorParams, VentilatorMode
from .infusion_gateway import (
    InfusionPump, PumpStatus, DrugResolver,
    HL7PumpParser, VasopressorIndex, InfusionAlarmChecker,
    create_demo_pumps, create_manual_pump,
)

_SESSION_KEY = "rl_device_connector"

_DEFAULT_VITALS = {
    "heart_rate": 80.0, "systolic_bp": 120.0, "diastolic_bp": 80.0,
    "spo2": 97.0, "respiratory_rate": 16.0, "body_temp": 36.8,
    "cvp": 8.0, "map": 93.0,
}
_DEFAULT_VENT = {
    "tidal_volume": 450.0, "fio2": 0.55, "peep": 5.0,
    "peak_pressure": 22.0, "mean_airway_pressure": 14.0,
    "rate_set": 14.0, "mode": "SIMV", "ie_ratio": "1:2",
}


class RealDeviceConnector:
    def __init__(
        self,
        hl7_host: str = "0.0.0.0",
        hl7_port: int = 2575,
        dicom_cfg: Optional[DICOMConfig] = None,
    ):
        self._lock = threading.Lock()
        self._vitals_dict: Optional[dict] = None
        self._vent_dict:   Optional[dict] = None
        self._raw_hl7:     Optional[str]  = None

        # ── BARU: infusion pumps (pump_id → InfusionPump) ──────────────────
        self._infusion_pumps: Dict[str, InfusionPump] = {}

        self._hl7_server = HL7MLLPServer(
            host=hl7_host, port=hl7_port,
            on_vitals=self._cb_vitals,
            on_vent=self._cb_vent,
            on_raw=self._cb_raw,
        )
        self._dicom: Optional[DICOMGateway] = (
            DICOMGateway(dicom_cfg) if dicom_cfg else None
        )
        self.hl7_host  = hl7_host
        self.hl7_port  = hl7_port
        self.dicom_cfg = dicom_cfg

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start_hl7(self): return self._hl7_server.start()
    def stop_hl7(self):  self._hl7_server.stop()
    def is_hl7_running(self): return self._hl7_server.is_running()

    @property
    def status_hl7(self) -> DeviceConnectionStatus:
        return self._hl7_server.status

    def has_vitals(self) -> bool:
        with self._lock: return self._vitals_dict is not None
    def has_vent(self) -> bool:
        with self._lock: return self._vent_dict is not None

    # ── Vitals / Vent getters (sama seperti v1) ───────────────────────────────
    def get_vitals_dict(self) -> Optional[dict]:
        with self._lock:
            return dict(self._vitals_dict) if self._vitals_dict else None

    def get_vent_dict(self) -> Optional[dict]:
        with self._lock:
            return dict(self._vent_dict) if self._vent_dict else None

    def get_raw_hl7(self) -> Optional[str]:
        with self._lock: return self._raw_hl7

    def as_vital_signs(self, fallback_to_default: bool = False) -> Optional[VitalSigns]:
        d = self.get_vitals_dict()
        if d is None:
            if not fallback_to_default: return None
            d = dict(_DEFAULT_VITALS)
        def _i(k, df=0): v=d.get(k); return int(v) if v is not None else df
        def _f(k, df=0.): v=d.get(k); return float(v) if v is not None else df
        return VitalSigns(
            timestamp=datetime.now().isoformat(),
            heart_rate=_i("heart_rate",80), systolic_bp=_i("systolic_bp",120),
            diastolic_bp=_i("diastolic_bp",80), spo2=_f("spo2",97.),
            respiratory_rate=_i("respiratory_rate",16), body_temp=_f("body_temp",36.8),
            cvp=_f("cvp",8.), map=_f("map",93.), source="hl7_device",
        )

    def as_vent_params(self, fallback_to_default: bool = False) -> Optional[VentilatorParams]:
        d = self.get_vent_dict()
        if d is None:
            if not fallback_to_default: return None
            d = dict(_DEFAULT_VENT)
        def _i(k, df=0): v=d.get(k); return int(v) if v is not None else df
        def _f(k, df=0.): v=d.get(k); return float(v) if v is not None else df
        def _s(k, df=""): v=d.get(k); return str(v) if v is not None else df
        raw_mode = _s("mode","CMV").upper()
        try:    mode_val = VentilatorMode(raw_mode).value
        except: mode_val = raw_mode
        return VentilatorParams(
            timestamp=datetime.now().isoformat(), mode=mode_val,
            fio2=_f("fio2",0.5), peep=_f("peep",5.), tidal_volume=_i("tidal_volume",450),
            rate_set=_i("rate_set",14), ie_ratio=_s("ie_ratio","1:2"),
            mean_airway_pressure=_f("mean_airway_pressure",14.), peak_pressure=_f("peak_pressure",22.),
            source="hl7_device",
        )

    # ── BARU: Infusion Pump API ────────────────────────────────────────────────

    def get_infusion_pumps(self) -> List[InfusionPump]:
        """Kembalikan semua pump terdaftar (sorted by pump_id)."""
        with self._lock:
            return sorted(self._infusion_pumps.values(), key=lambda p: p.pump_id)

    def add_pump_manual(self, pump: InfusionPump) -> None:
        """Tambah/update pump dari input manual UI."""
        with self._lock:
            self._infusion_pumps[pump.pump_id] = pump

    def remove_pump(self, pump_id: str) -> None:
        with self._lock:
            self._infusion_pumps.pop(pump_id, None)

    def update_pump_status(self, pump_id: str, status: PumpStatus) -> None:
        with self._lock:
            if pump_id in self._infusion_pumps:
                p = self._infusion_pumps[pump_id]
                self._infusion_pumps[pump_id] = InfusionPump(
                    **{**p.__dict__, "status": status,
                       "timestamp": datetime.now().isoformat()},
                )

    def get_vasopressor_context(self) -> dict:
        """Return VIS index dict untuk ditampilkan di UI dan dikirim ke CDSS."""
        pumps = self.get_infusion_pumps()
        return VasopressorIndex.calculate(pumps)

    def get_infusion_alarms(self):
        return InfusionAlarmChecker.check(self.get_infusion_pumps())

    def get_cdss_context_text(self) -> str:
        return VasopressorIndex.cdss_context_text(self.get_infusion_pumps())

    def has_pumps(self) -> bool:
        with self._lock: return bool(self._infusion_pumps)

    # ── DICOM ─────────────────────────────────────────────────────────────────
    def fetch_dicom_vitals(self, patient_id: str) -> Optional[dict]:
        if not self._dicom or not self._dicom.available: return None
        result = self._dicom.get_latest_vitals(patient_id)
        if result:
            with self._lock:
                merged = dict(result)
                if self._vitals_dict:
                    for k, v in self._vitals_dict.items():
                        if v is not None: merged[k] = v
                self._vitals_dict = merged
        return result

    def ping_dicom(self): return self._dicom.ping() if self._dicom else (False, "Tidak dikonfigurasi.")
    @property
    def dicom_available(self) -> bool: return bool(self._dicom and self._dicom.available)

    # ── Demo ─────────────────────────────────────────────────────────────────
    def inject_demo_data(self, patient_id: str = "EP-DEMO-001") -> None:
        from .hl7_gateway import make_demo_oru, HL7VitalExtractor
        demo_msg = make_demo_oru(patient_id)
        vitals = HL7VitalExtractor.extract_vitals(demo_msg)
        vent   = HL7VitalExtractor.extract_vent(demo_msg)
        with self._lock:
            if vitals: self._vitals_dict = vitals
            if vent:   self._vent_dict   = vent
            self._raw_hl7 = demo_msg.raw
        st_ref = self._hl7_server.status
        st_ref.total_received += 1
        st_ref.last_msg_at = datetime.now()

    def inject_demo_pumps(self) -> None:
        """Inject pump demo dari foto ICCU (Norepinephrine 0.75 ml/h)."""
        for p in create_demo_pumps():
            with self._lock:
                self._infusion_pumps[p.pump_id] = p

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _cb_vitals(self, vitals: dict, msg: HL7Message) -> None:
        with self._lock:
            if not self._vitals_dict: self._vitals_dict = {}
            for k, v in vitals.items():
                if v is not None: self._vitals_dict[k] = v

    def _cb_vent(self, vent: dict, msg: HL7Message) -> None:
        with self._lock:
            if not self._vent_dict: self._vent_dict = {}
            for k, v in vent.items():
                if v is not None: self._vent_dict[k] = v

    def _cb_raw(self, raw: str) -> None:
        # Coba parse sebagai PCD-01 pump message
        pump = HL7PumpParser.parse_pcd01(raw)
        if pump:
            with self._lock:
                self._infusion_pumps[pump.pump_id] = pump
        with self._lock:
            self._raw_hl7 = raw


# =============================================================================
# Session-state factory
# =============================================================================

def get_or_create_connector(
    hl7_host: str = "0.0.0.0",
    hl7_port: int = 2575,
    dicom_cfg: Optional[DICOMConfig] = None,
) -> RealDeviceConnector:
    existing: Optional[RealDeviceConnector] = st.session_state.get(_SESSION_KEY)
    if existing is None or (
        existing.hl7_host != hl7_host or existing.hl7_port != hl7_port
    ):
        if existing and existing.is_hl7_running():
            existing.stop_hl7()
        conn = RealDeviceConnector(hl7_host, hl7_port, dicom_cfg)
        st.session_state[_SESSION_KEY] = conn
        return conn
    return existing


def clear_connector() -> None:
    if _SESSION_KEY in st.session_state:
        conn: RealDeviceConnector = st.session_state[_SESSION_KEY]
        conn.stop_hl7()
        del st.session_state[_SESSION_KEY]
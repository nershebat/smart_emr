"""
Data models untuk modul Device Monitoring.
Diporting apa adanya (logika tidak diubah) dari `dashboard_enhanced_v2.py`,
hanya dipindah ke file tersendiri supaya modular & mudah dipakai ulang oleh
halaman lain tanpa import siklik.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AlertLevel(Enum):
    LOW = "🟡 LOW"
    MEDIUM = "🟠 MEDIUM"
    CRITICAL = "🔴 CRITICAL"


class VentilatorMode(Enum):
    AC = "AC/CV"
    SIMV = "SIMV"
    PS = "PS"
    PC = "PC"
    PRVC = "PRVC"
    ASV = "ASV"


@dataclass
class VitalSigns:
    timestamp: str
    heart_rate: int
    systolic_bp: int
    diastolic_bp: int
    spo2: float
    respiratory_rate: int
    body_temp: float
    cvp: Optional[float] = None
    map: Optional[float] = None
    source: str = "manual"  # manual, monitor, api


@dataclass
class VentilatorParams:
    timestamp: str
    mode: str
    fio2: float
    peep: float
    tidal_volume: int
    rate_set: int
    ie_ratio: str
    mean_airway_pressure: float
    peak_pressure: float
    source: str = "manual"


@dataclass
class Alert:
    timestamp: str
    alert_type: str
    level: str
    message: str
    patient_id: str
    resolved: bool = False


# Normal ranges for vital signs
VITAL_RANGES = {
    "heart_rate": {"min": 40, "low": 60, "normal_max": 100, "high": 120, "max": 180},
    "systolic_bp": {"min": 90, "low": 100, "normal_max": 140, "high": 180, "max": 220},
    "spo2": {"critical": 90, "normal": 95, "max": 100},
    "respiratory_rate": {"min": 10, "low": 12, "normal_max": 20, "high": 30, "max": 40},
    "body_temp": {"min": 35, "low": 36.5, "normal_max": 37.5, "high": 39, "max": 41},
}

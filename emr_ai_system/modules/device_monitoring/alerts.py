"""
Alert engine untuk modul Device Monitoring.
Logika ambang batas (threshold) diporting apa adanya dari `dashboard_enhanced_v2.py`.
"""

from datetime import datetime
from typing import List

from .models import Alert, AlertLevel, VentilatorParams, VitalSigns


def check_vital_alerts(patient_id: str, vs: VitalSigns) -> List[Alert]:
    """Generate alerts based on vital signs thresholds"""
    alerts = []

    # SpO2 Critical
    if vs.spo2 < 90:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="SpO2_CRITICAL",
            level=AlertLevel.CRITICAL.value,
            message=f"SpO2 RENDAH: {vs.spo2}% (Alert <90%)",
            patient_id=patient_id
        ))

    # Heart Rate
    if vs.heart_rate > 120:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="HR_HIGH",
            level=AlertLevel.MEDIUM.value,
            message=f"HR TINGGI: {vs.heart_rate} bpm (Alert >120)",
            patient_id=patient_id
        ))
    elif vs.heart_rate < 40:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="HR_LOW",
            level=AlertLevel.CRITICAL.value,
            message=f"HR SANGAT RENDAH: {vs.heart_rate} bpm (Alert <40)",
            patient_id=patient_id
        ))

    # Blood Pressure
    if vs.systolic_bp > 180:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="BP_HIGH",
            level=AlertLevel.MEDIUM.value,
            message=f"BP TINGGI: {vs.systolic_bp}/{vs.diastolic_bp} mmHg",
            patient_id=patient_id
        ))
    elif vs.systolic_bp < 90:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="BP_LOW",
            level=AlertLevel.MEDIUM.value,
            message=f"BP RENDAH: {vs.systolic_bp}/{vs.diastolic_bp} mmHg",
            patient_id=patient_id
        ))

    # Temperature
    if vs.body_temp > 39:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="TEMP_HIGH",
            level=AlertLevel.MEDIUM.value,
            message=f"Suhu TINGGI: {vs.body_temp}°C",
            patient_id=patient_id
        ))

    return alerts


def check_ventilator_alerts(patient_id: str, vp: VentilatorParams) -> List[Alert]:
    """Generate alerts based on ventilator parameters"""
    alerts = []

    if vp.peak_pressure > 30:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="PRESSURE_HIGH",
            level=AlertLevel.CRITICAL.value,
            message=f"Peak Pressure TINGGI: {vp.peak_pressure} cmH2O (Alert >30)",
            patient_id=patient_id
        ))

    if vp.fio2 > 0.9:
        alerts.append(Alert(
            timestamp=datetime.now().isoformat(),
            alert_type="FIO2_HIGH",
            level=AlertLevel.MEDIUM.value,
            message=f"FiO2 TINGGI: {vp.fio2*100}%",
            patient_id=patient_id
        ))

    return alerts

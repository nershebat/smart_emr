"""
Auto-generator bagian Objective (O) dari data device monitoring.

PERBAIKAN dari `dashboard_enhanced_v2.py` (sengaja didokumentasikan supaya
transparan — bukan diam-diam): versi asli memakai `"\\\\n"` (backslash ganda)
di dalam string biasa, sehingga karakter yang muncul di layar adalah teks
literal `\\n`, bukan baris baru. Di sini dipakai newline asli (`\n`) supaya
hasilnya benar-benar berbaris saat ditampilkan via `st.markdown()` atau saat
disalin ke kolom Objective (O) Dashboard CPPT utama.
"""
import streamlit as st
from modules.bridge_updated import require_role, display_user_badge
  
  # ✅ Guard: Perawat, Dokter, Admin bisa akses
if not require_role("Perawat", "Dokter", "Admin"):
      st.stop()
  
display_user_badge()

from typing import Optional

from .models import VentilatorParams, VitalSigns


def generate_objective_section(
    patient_id: str,
    vital_signs: VitalSigns,
    ventilator_params: Optional[VentilatorParams] = None,
) -> str:
    """Auto-generate Objective section from device data"""

    lines = ["### OBJECTIVE (Data dari Device Monitoring)", ""]

    lines.append("**Tanda Vital:**")
    lines.append(f"- HR: {vital_signs.heart_rate} bpm")
    lines.append(f"- BP: {vital_signs.systolic_bp}/{vital_signs.diastolic_bp} mmHg (MAP: {vital_signs.map:.0f})")
    lines.append(f"- RR: {vital_signs.respiratory_rate} x/menit")
    lines.append(f"- SpO2: {vital_signs.spo2:.1f}%")
    lines.append(f"- Temp: {vital_signs.body_temp:.1f}°C")

    if vital_signs.cvp is not None:
        lines.append(f"- CVP: {vital_signs.cvp:.1f} cmH2O")

    lines.append("")

    if ventilator_params:
        lines.append("**Parameter Ventilator:**")
        lines.append(f"- Mode: {ventilator_params.mode}")
        lines.append(f"- FiO2: {ventilator_params.fio2*100:.0f}%")
        lines.append(f"- PEEP: {ventilator_params.peep:.1f} cmH2O")
        lines.append(f"- Tidal Volume: {ventilator_params.tidal_volume} mL")
        lines.append(f"- RR set: {ventilator_params.rate_set} x/menit")
        lines.append(f"- I:E: {ventilator_params.ie_ratio}")
        lines.append(f"- Peak Pressure: {ventilator_params.peak_pressure:.1f} cmH2O")
        lines.append(f"- Mean Airway Pressure: {ventilator_params.mean_airway_pressure:.1f} cmH2O")

    return "\n".join(lines)

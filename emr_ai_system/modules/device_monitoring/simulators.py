"""
Simulator data Bedside Monitor & Ventilator.
Diporting apa adanya dari `dashboard_enhanced_v2.py`.

Catatan produksi (sudah ada di docstring asli): pada implementasi nyata,
kelas-kelas ini diganti dengan koneksi aktual ke device lewat gateway
HL7v2 / DICOM, bukan data acak.
"""

from datetime import datetime

import numpy as np

from .models import VentilatorMode, VentilatorParams, VitalSigns


class BedisideMonitorSimulator:
    """Simulate bedside monitor data (production: replace with actual HL7/DICOM connection)"""

    @staticmethod
    def get_live_vitals() -> VitalSigns:
        """Simulate live vital signs from bedside monitor"""
        base_hr = np.random.normal(80, 10)
        base_bp_sys = np.random.normal(130, 15)
        base_bp_dia = np.random.normal(85, 10)

        return VitalSigns(
            timestamp=datetime.now().isoformat(),
            heart_rate=int(np.clip(base_hr, 40, 180)),
            systolic_bp=int(np.clip(base_bp_sys, 80, 200)),
            diastolic_bp=int(np.clip(base_bp_dia, 50, 120)),
            spo2=float(np.clip(np.random.normal(97, 2), 85, 100)),
            respiratory_rate=int(np.clip(np.random.normal(16, 3), 8, 35)),
            body_temp=float(np.clip(np.random.normal(36.8, 0.5), 35, 39)),
            cvp=float(np.random.normal(8, 2)),
            map=float(np.random.normal(105, 10)),
            source="monitor"
        )


class VentilatorSimulator:
    """Simulate ventilator data (production: replace with actual device connection)"""

    @staticmethod
    def get_live_params() -> VentilatorParams:
        """Simulate live ventilator parameters"""
        modes = [m.value for m in VentilatorMode]
        return VentilatorParams(
            timestamp=datetime.now().isoformat(),
            mode=str(np.random.choice(modes)),
            fio2=float(np.clip(np.random.normal(0.6, 0.15), 0.21, 1.0)),
            peep=float(np.random.normal(5, 2)),
            tidal_volume=int(np.random.normal(450, 50)),
            rate_set=int(np.random.normal(14, 2)),
            ie_ratio="1:2",
            mean_airway_pressure=float(np.random.normal(15, 3)),
            peak_pressure=float(np.clip(np.random.normal(22, 4), 10, 35)),
            source="ventilator"
        )

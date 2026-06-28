"""
Lapisan database untuk modul Device Monitoring.

Sengaja memakai file SQLite TERPISAH (`device_monitoring.db`) dari database
Dashboard CPPT utama (`rsjpdhk_emr.db`, dipakai oleh `dashboard-3__1_.py`).
Alasannya:
  1) `dashboard-3__1_.py` tidak boleh diubah sama sekali — termasuk skema
     tabelnya — sehingga modul baru ini tidak menumpangi tabel yang sudah ada.
  2) Data device (vital signs, ventilator, alert mentah per-detik/menit) jauh
     lebih granular/frequent dibanding catatan CPPT, jadi wajar dipisah.
  3) Penautan ke pasien yang sama tetap terjaga karena `patient_id` yang
     dipakai di sini diisi dengan `episode_id` aktif dari Dashboard CPPT
     (lihat `modules/bridge.py`), bukan ID bebas/manual.
"""

import sqlite3
from typing import List

import pandas as pd

from .models import Alert, VentilatorParams, VitalSigns

DEVICE_DB_PATH = "device_monitoring.db"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DEVICE_DB_PATH)


def init_database() -> None:
    """Buat tabel jika belum ada. Aman dipanggil berulang kali (idempotent)."""
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vital_signs_log (
            id INTEGER PRIMARY KEY,
            patient_id TEXT,
            timestamp TEXT,
            heart_rate INTEGER,
            systolic_bp INTEGER,
            diastolic_bp INTEGER,
            spo2 REAL,
            respiratory_rate INTEGER,
            body_temp REAL,
            cvp REAL,
            map REAL,
            source TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventilator_log (
            id INTEGER PRIMARY KEY,
            patient_id TEXT,
            timestamp TEXT,
            mode TEXT,
            fio2 REAL,
            peep REAL,
            tidal_volume INTEGER,
            rate_set INTEGER,
            ie_ratio TEXT,
            mean_airway_pressure REAL,
            peak_pressure REAL,
            source TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY,
            patient_id TEXT,
            timestamp TEXT,
            alert_type TEXT,
            level TEXT,
            message TEXT,
            resolved BOOLEAN DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def save_vital_signs(patient_id: str, vs: VitalSigns) -> None:
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vital_signs_log
        (patient_id, timestamp, heart_rate, systolic_bp, diastolic_bp, spo2,
         respiratory_rate, body_temp, cvp, map, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, vs.timestamp, vs.heart_rate, vs.systolic_bp, vs.diastolic_bp,
          vs.spo2, vs.respiratory_rate, vs.body_temp, vs.cvp, vs.map, vs.source))
    conn.commit()
    conn.close()


def save_ventilator_params(patient_id: str, vp: VentilatorParams) -> None:
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ventilator_log
        (patient_id, timestamp, mode, fio2, peep, tidal_volume, rate_set,
         ie_ratio, mean_airway_pressure, peak_pressure, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, vp.timestamp, vp.mode, vp.fio2, vp.peep, vp.tidal_volume,
          vp.rate_set, vp.ie_ratio, vp.mean_airway_pressure, vp.peak_pressure, vp.source))
    conn.commit()
    conn.close()


def get_vital_signs_history(patient_id: str, hours: int = 24) -> pd.DataFrame:
    conn = _connect()
    query = f"""
        SELECT * FROM vital_signs_log
        WHERE patient_id = ? AND timestamp > datetime('now', '-{int(hours)} hours')
        ORDER BY timestamp DESC
    """
    df = pd.read_sql_query(query, conn, params=(patient_id,))
    conn.close()
    return df


def get_ventilator_history(patient_id: str, hours: int = 24) -> pd.DataFrame:
    conn = _connect()
    query = f"""
        SELECT * FROM ventilator_log
        WHERE patient_id = ? AND timestamp > datetime('now', '-{int(hours)} hours')
        ORDER BY timestamp DESC
    """
    df = pd.read_sql_query(query, conn, params=(patient_id,))
    conn.close()
    return df


def save_alert(patient_id: str, alert: Alert) -> None:
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts (patient_id, timestamp, alert_type, level, message, resolved)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (patient_id, alert.timestamp, alert.alert_type, alert.level, alert.message, alert.resolved))
    conn.commit()
    conn.close()


def get_alerts(patient_id: str, hours: int = 24) -> List[dict]:
    conn = _connect()
    query = f"""
        SELECT * FROM alerts
        WHERE patient_id = ? AND timestamp > datetime('now', '-{int(hours)} hours')
        ORDER BY timestamp DESC
    """
    df = pd.read_sql_query(query, conn, params=(patient_id,))
    conn.close()
    return df.to_dict("records") if not df.empty else []

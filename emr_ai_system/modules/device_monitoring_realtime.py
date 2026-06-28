"""
═══════════════════════════════════════════════════════════════════════════
🏥 DEVICE MONITORING - 3 TABS REALTIME
TTV | Ventilator | Infus Pump
Dengan Update Realtime & Database Sync (Tanpa CDSS)
═══════════════════════════════════════════════════════════════════════════

Features:
✅ Tabel per satuan waktu (per jam)
✅ Input form realtime untuk setiap parameter
✅ Auto-save ke database
✅ Edit/Update data
✅ Sync database
✅ Simple & clean UI
✅ Tanpa algoritme CDSS

═════════════════════════════════════════════════════════════════════════════
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

try:
    from modules.device_monitoring.infusion_gateway import PumpStatus
except ImportError:
    PumpStatus = None  # fallback aman jika modul tidak tersedia (mis. saat testing standalone)


# ═════════════════════════════════════════════════════════════════════════
# DATABASE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════

class DeviceMonitoringDB:
    """Database operations untuk Device Monitoring"""
    
    def __init__(self, db_path="device_monitoring.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table: TTV Monitoring
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ttv_monitoring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal DATE,
                jam TIME,
                episode_id TEXT,
                blood_pressure_sys INTEGER,
                blood_pressure_dias INTEGER,
                heart_rate INTEGER,
                saturasi INTEGER,
                respiratory_rate INTEGER,
                temperature REAL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        
        # Table: Ventilator Monitoring
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ventilator_monitoring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal DATE,
                jam TIME,
                episode_id TEXT,
                mode TEXT,
                fio2 INTEGER,
                peep INTEGER,
                tidal_volume INTEGER,
                rr_set INTEGER,
                rr_actual INTEGER,
                ie_ratio TEXT,
                peak_pressure INTEGER,
                compliance INTEGER,
                status TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        
        # Table: Infus Pump Monitoring
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS infus_pump_monitoring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal DATE,
                jam TIME,
                episode_id TEXT,
                line_number INTEGER,
                nama_obat TEXT,
                rate_ml_jam REAL,
                volume_ml REAL,
                iv_access TEXT,
                status TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def insert_ttv(self, tanggal, jam, episode_id, data_dict) -> bool:
        """Insert atau update TTV data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if already exists
            cursor.execute("""
                SELECT id FROM ttv_monitoring 
                WHERE tanggal=? AND jam=? AND episode_id=?
            """, (tanggal, jam, episode_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update
                cursor.execute("""
                    UPDATE ttv_monitoring 
                    SET blood_pressure_sys=?, blood_pressure_dias=?, heart_rate=?,
                        saturasi=?, respiratory_rate=?, temperature=?, updated_at=?
                    WHERE id=?
                """, (
                    data_dict.get('blood_pressure_sys'),
                    data_dict.get('blood_pressure_dias'),
                    data_dict.get('heart_rate'),
                    data_dict.get('saturasi'),
                    data_dict.get('respiratory_rate'),
                    data_dict.get('temperature'),
                    datetime.now().isoformat(),
                    existing[0]
                ))
            else:
                # Insert
                cursor.execute("""
                    INSERT INTO ttv_monitoring 
                    (tanggal, jam, episode_id, blood_pressure_sys, blood_pressure_dias,
                     heart_rate, saturasi, respiratory_rate, temperature, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tanggal, jam, episode_id,
                    data_dict.get('blood_pressure_sys'),
                    data_dict.get('blood_pressure_dias'),
                    data_dict.get('heart_rate'),
                    data_dict.get('saturasi'),
                    data_dict.get('respiratory_rate'),
                    data_dict.get('temperature'),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            st.error(f"❌ Error saving TTV: {str(e)}")
            return False
    
    def get_ttv_by_date(self, tanggal, episode_id) -> pd.DataFrame:
        """Get semua TTV data untuk satu tanggal"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
                SELECT jam, blood_pressure_sys, blood_pressure_dias, heart_rate,
                       saturasi, respiratory_rate, temperature
                FROM ttv_monitoring
                WHERE tanggal=? AND episode_id=?
                ORDER BY jam
            """
            df = pd.read_sql_query(query, conn, params=(tanggal, episode_id))
            conn.close()
            return df
        except Exception as e:
            st.error(f"❌ Error fetching TTV: {str(e)}")
            return pd.DataFrame()
    
    def insert_ventilator(self, tanggal, jam, episode_id, data_dict) -> bool:
        """Insert atau update Ventilator data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM ventilator_monitoring
                WHERE tanggal=? AND jam=? AND episode_id=?
            """, (tanggal, jam, episode_id))
            
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE ventilator_monitoring
                    SET mode=?, fio2=?, peep=?, tidal_volume=?, rr_set=?,
                        rr_actual=?, ie_ratio=?, peak_pressure=?, compliance=?,
                        status=?, updated_at=?
                    WHERE id=?
                """, (
                    data_dict.get('mode'),
                    data_dict.get('fio2'),
                    data_dict.get('peep'),
                    data_dict.get('tidal_volume'),
                    data_dict.get('rr_set'),
                    data_dict.get('rr_actual'),
                    data_dict.get('ie_ratio'),
                    data_dict.get('peak_pressure'),
                    data_dict.get('compliance'),
                    data_dict.get('status'),
                    datetime.now().isoformat(),
                    existing[0]
                ))
            else:
                cursor.execute("""
                    INSERT INTO ventilator_monitoring
                    (tanggal, jam, episode_id, mode, fio2, peep, tidal_volume,
                     rr_set, rr_actual, ie_ratio, peak_pressure, compliance, status,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tanggal, jam, episode_id,
                    data_dict.get('mode'),
                    data_dict.get('fio2'),
                    data_dict.get('peep'),
                    data_dict.get('tidal_volume'),
                    data_dict.get('rr_set'),
                    data_dict.get('rr_actual'),
                    data_dict.get('ie_ratio'),
                    data_dict.get('peak_pressure'),
                    data_dict.get('compliance'),
                    data_dict.get('status'),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            st.error(f"❌ Error saving Ventilator: {str(e)}")
            return False
    
    def get_ventilator_by_date(self, tanggal, episode_id) -> pd.DataFrame:
        """Get semua Ventilator data untuk satu tanggal"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
                SELECT jam, mode, fio2, peep, tidal_volume, rr_set, rr_actual,
                       ie_ratio, peak_pressure, compliance, status
                FROM ventilator_monitoring
                WHERE tanggal=? AND episode_id=?
                ORDER BY jam
            """
            df = pd.read_sql_query(query, conn, params=(tanggal, episode_id))
            conn.close()
            return df
        except Exception as e:
            st.error(f"❌ Error fetching Ventilator: {str(e)}")
            return pd.DataFrame()
    
    def insert_infus(self, tanggal, jam, episode_id, line_number, data_dict) -> bool:
        """Insert atau update Infus Pump data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM infus_pump_monitoring
                WHERE tanggal=? AND jam=? AND episode_id=? AND line_number=?
            """, (tanggal, jam, episode_id, line_number))
            
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE infus_pump_monitoring
                    SET nama_obat=?, rate_ml_jam=?, volume_ml=?, iv_access=?, status=?, updated_at=?
                    WHERE id=?
                """, (
                    data_dict.get('nama_obat'),
                    data_dict.get('rate_ml_jam'),
                    data_dict.get('volume_ml'),
                    data_dict.get('iv_access'),
                    data_dict.get('status'),
                    datetime.now().isoformat(),
                    existing[0]
                ))
            else:
                cursor.execute("""
                    INSERT INTO infus_pump_monitoring
                    (tanggal, jam, episode_id, line_number, nama_obat, rate_ml_jam,
                     volume_ml, iv_access, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tanggal, jam, episode_id, line_number,
                    data_dict.get('nama_obat'),
                    data_dict.get('rate_ml_jam'),
                    data_dict.get('volume_ml'),
                    data_dict.get('iv_access'),
                    data_dict.get('status'),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            st.error(f"❌ Error saving Infus: {str(e)}")
            return False
    
    def get_infus_by_date(self, tanggal, episode_id) -> pd.DataFrame:
        """Get semua Infus data untuk satu tanggal"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
                SELECT jam, line_number, nama_obat, rate_ml_jam, volume_ml, iv_access, status
                FROM infus_pump_monitoring
                WHERE tanggal=? AND episode_id=?
                ORDER BY jam, line_number
            """
            df = pd.read_sql_query(query, conn, params=(tanggal, episode_id))
            conn.close()
            return df
        except Exception as e:
            st.error(f"❌ Error fetching Infus: {str(e)}")
            return pd.DataFrame()


# ═════════════════════════════════════════════════════════════════════════
# TAB 1: TTV (VITAL SIGN) MONITORING
# ═════════════════════════════════════════════════════════════════════════

def render_tab_ttv(db: DeviceMonitoringDB, tanggal: str, episode_id: str, connector=None):
    """Tab untuk TTV Monitoring - Input Realtime
    
    `connector`: instance RealDeviceConnector (opsional). Jika diberikan dan
    sedang menerima data HL7 live, tombol "📥 Tarik dari Device" akan muncul
    untuk mengisi form secara otomatis dari data device, tanpa menghilangkan
    opsi input manual.
    """
    
    st.markdown("### 🩺 Monitoring Vital Sign (TTV)")
    st.markdown(f"**Tanggal:** {tanggal} | **Episode ID:** {episode_id}")
    st.markdown("---")
    
    # Input form untuk TTV
    st.markdown("#### 📝 Input Data TTV")
    
    # ── Tarik dari Device (opsional, hanya muncul jika connector tersedia) ────
    if connector is not None:
        col_pull1, col_pull2 = st.columns([1, 3])
        with col_pull1:
            pull_clicked = st.button(
                "📥 Tarik dari Device", key="ttv_pull_device",
                use_container_width=True,
                help="Isi form di bawah otomatis dari data HL7 device live terakhir.",
            )
        with col_pull2:
            if connector.has_vitals():
                st.caption("🟢 Data live tersedia dari device — siap ditarik.")
            else:
                st.caption("⚪ Belum ada data live dari device. Form tetap bisa diisi manual.")
        
        if pull_clicked:
            vs_live = connector.as_vital_signs()
            if vs_live is None:
                st.warning("⚠️ Belum ada data vital signs dari device. Pastikan HL7 Server aktif & sudah menerima data.")
            else:
                st.session_state["ttv_bp_sys"] = int(vs_live.systolic_bp)
                st.session_state["ttv_bp_dias"] = int(vs_live.diastolic_bp)
                st.session_state["ttv_hr"] = int(vs_live.heart_rate)
                st.session_state["ttv_saturasi"] = int(vs_live.spo2)
                st.session_state["ttv_rr"] = int(vs_live.respiratory_rate)
                st.session_state["ttv_temp"] = float(vs_live.body_temp)
                st.toast("✅ Form TTV terisi dari data device.", icon="📥")
                st.rerun()
        st.markdown("")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        jam = st.time_input("Jam Pengukuran", key="ttv_jam")
    
    with col2:
        st.write("")  # Spacing
    
    # Parameter inputs
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        bp_sys = st.number_input("BP Systolic (mmHg)", min_value=0, max_value=300, 
                                 key="ttv_bp_sys", step=1)
    
    with col2:
        bp_dias = st.number_input("BP Diastolic (mmHg)", min_value=0, max_value=200,
                                  key="ttv_bp_dias", step=1)
    
    with col3:
        hr = st.number_input("Heart Rate (bpm)", min_value=0, max_value=200,
                            key="ttv_hr", step=1)
    
    with col4:
        saturasi = st.number_input("Saturasi (%)", min_value=0, max_value=100,
                                   key="ttv_saturasi", step=1)
    
    col1, col2 = st.columns(2)
    
    with col1:
        rr = st.number_input("Respiratory Rate (x/menit)", min_value=0, max_value=100,
                            key="ttv_rr", step=1)
    
    with col2:
        temp = st.number_input("Temperature (°C)", min_value=35.0, max_value=42.0,
                              key="ttv_temp", step=0.1)
    
    # Save button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        if st.button("💾 Save TTV", type="primary", use_container_width=True):
            data = {
                'blood_pressure_sys': bp_sys,
                'blood_pressure_dias': bp_dias,
                'heart_rate': hr,
                'saturasi': saturasi,
                'respiratory_rate': rr,
                'temperature': temp
            }
            
            if db.insert_ttv(tanggal, jam.strftime("%H:%M"), episode_id, data):
                st.success(f"✅ TTV data saved at {jam.strftime('%H:%M')}")
                st.rerun()
            else:
                st.error("❌ Failed to save TTV data")
    
    # Display table
    st.markdown("---")
    st.markdown("#### 📊 Data TTV Today")
    
    df_ttv = db.get_ttv_by_date(tanggal, episode_id)
    
    if not df_ttv.empty:
        # Format display
        df_display = df_ttv.copy()
        df_display.columns = ['Jam', 'SBP', 'DBP', 'HR', 'SpO2 (%)', 'RR', 'Temp (°C)']
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # Export button
        csv_ttv = df_display.to_csv(index=False)
        st.download_button(
            label="📥 Download TTV Data",
            data=csv_ttv,
            file_name=f"ttv_{tanggal}.csv",
            mime="text/csv"
        )
    else:
        st.info("📭 No TTV data recorded yet for this date")


# ═════════════════════════════════════════════════════════════════════════
# TAB 2: VENTILATOR MONITORING
# ═════════════════════════════════════════════════════════════════════════

def render_tab_ventilator(db: DeviceMonitoringDB, tanggal: str, episode_id: str, connector=None):
    """Tab untuk Ventilator Monitoring - Input Realtime
    
    `connector`: instance RealDeviceConnector (opsional). Jika diberikan dan
    sedang menerima data HL7 live, tombol "📥 Tarik dari Device" akan muncul
    untuk mengisi form secara otomatis dari parameter ventilator device,
    tanpa menghilangkan opsi input manual.
    """
    
    st.markdown("### 🫁 Monitoring Ventilator")
    st.markdown(f"**Tanggal:** {tanggal} | **Episode ID:** {episode_id}")
    st.markdown("---")
    
    # Input form
    st.markdown("#### 📝 Input Data Ventilator")
    
    # ── Tarik dari Device (opsional, hanya muncul jika connector tersedia) ────
    _VENT_MODE_OPTIONS = ["AC/CV", "SIMV", "CPAP", "PSV", "PCV"]
    if connector is not None:
        col_pull1, col_pull2 = st.columns([1, 3])
        with col_pull1:
            pull_clicked = st.button(
                "📥 Tarik dari Device", key="vent_pull_device",
                use_container_width=True,
                help="Isi form di bawah otomatis dari parameter ventilator HL7 live terakhir.",
            )
        with col_pull2:
            if connector.has_vent():
                st.caption("🟢 Data ventilator live tersedia dari device — siap ditarik.")
            else:
                st.caption("⚪ Belum ada data live dari device. Form tetap bisa diisi manual.")
        
        if pull_clicked:
            vp_live = connector.as_vent_params()
            if vp_live is None:
                st.warning("⚠️ Belum ada data ventilator dari device. Pastikan HL7 Server aktif & sudah menerima data.")
            else:
                mode_str = getattr(vp_live.mode, "value", vp_live.mode)
                # Map mode dari device ke opsi selectbox lokal; fallback ke mode pertama jika tak cocok
                mode_norm = mode_str.upper().replace("PC", "PCV") if mode_str.upper() == "PC" else mode_str.upper()
                st.session_state["vent_mode"] = mode_str if mode_str in _VENT_MODE_OPTIONS else (
                    mode_norm if mode_norm in _VENT_MODE_OPTIONS else _VENT_MODE_OPTIONS[0]
                )
                st.session_state["vent_fio2"] = int(round(vp_live.fio2 * 100))
                st.session_state["vent_peep"] = int(round(vp_live.peep))
                st.session_state["vent_tv"] = int(vp_live.tidal_volume)
                st.session_state["vent_rr_set"] = int(vp_live.rate_set)
                st.session_state["vent_rr_actual"] = int(vp_live.rate_set)
                st.session_state["vent_ie"] = vp_live.ie_ratio if vp_live.ie_ratio in ["1:1", "1:2", "1:3", "1:4"] else "1:2"
                st.session_state["vent_peak"] = int(round(vp_live.peak_pressure))
                st.toast("✅ Form Ventilator terisi dari data device.", icon="📥")
                st.rerun()
        st.markdown("")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        jam = st.time_input("Jam Pengukuran", key="vent_jam")
    
    with col2:
        status = st.selectbox("Status", ["✅ Normal", "⚠️ Alert", "❌ Critical"],
                             key="vent_status")
    
    # Ventilator parameters
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        mode = st.selectbox("Mode", _VENT_MODE_OPTIONS,
                           key="vent_mode")
    
    with col2:
        fio2 = st.number_input("FiO2 (%)", min_value=21, max_value=100,
                              key="vent_fio2", step=1)
    
    with col3:
        peep = st.number_input("PEEP (cmH2O)", min_value=0, max_value=30,
                              key="vent_peep", step=1)
    
    with col4:
        tv = st.number_input("Tidal Volume (mL)", min_value=200, max_value=1000,
                            key="vent_tv", step=50)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        rr_set = st.number_input("RR Set (x/min)", min_value=0, max_value=40,
                                key="vent_rr_set", step=1)
    
    with col2:
        rr_actual = st.number_input("RR Actual (x/min)", min_value=0, max_value=60,
                                   key="vent_rr_actual", step=1)
    
    with col3:
        ie_ratio = st.selectbox("I:E Ratio", ["1:1", "1:2", "1:3", "1:4"],
                               key="vent_ie")
    
    with col4:
        peak_pressure = st.number_input("Peak Pressure (cmH2O)", min_value=10, max_value=50,
                                       key="vent_peak", step=1)
    
    col1, col2 = st.columns([2, 2])
    
    with col1:
        compliance = st.number_input("Compliance (mL/cmH2O)", min_value=10, max_value=100,
                                    key="vent_compliance", step=1)
    
    with col2:
        st.write("")  # Spacing
    
    # Save button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        if st.button("💾 Save Ventilator", type="primary", use_container_width=True):
            data = {
                'mode': mode,
                'fio2': fio2,
                'peep': peep,
                'tidal_volume': tv,
                'rr_set': rr_set,
                'rr_actual': rr_actual,
                'ie_ratio': ie_ratio,
                'peak_pressure': peak_pressure,
                'compliance': compliance,
                'status': status
            }
            
            if db.insert_ventilator(tanggal, jam.strftime("%H:%M"), episode_id, data):
                st.success(f"✅ Ventilator data saved at {jam.strftime('%H:%M')}")
                st.rerun()
            else:
                st.error("❌ Failed to save Ventilator data")
    
    # Display table
    st.markdown("---")
    st.markdown("#### 📊 Data Ventilator Today")
    
    df_vent = db.get_ventilator_by_date(tanggal, episode_id)
    
    if not df_vent.empty:
        df_display = df_vent.copy()
        df_display.columns = ['Jam', 'Mode', 'FiO2', 'PEEP', 'TV', 'RR Set', 'RR Act', 
                             'I:E', 'Peak Pr', 'Compl', 'Status']
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        csv_vent = df_display.to_csv(index=False)
        st.download_button(
            label="📥 Download Ventilator Data",
            data=csv_vent,
            file_name=f"ventilator_{tanggal}.csv",
            mime="text/csv"
        )
    else:
        st.info("📭 No ventilator data recorded yet for this date")


# ═════════════════════════════════════════════════════════════════════════
# TAB 3: INFUS PUMP MONITORING
# ═════════════════════════════════════════════════════════════════════════

def render_tab_infus(db: DeviceMonitoringDB, tanggal: str, episode_id: str, connector=None):
    """Tab untuk Infus Pump Monitoring - Input Realtime
    
    `connector`: instance RealDeviceConnector (opsional). Jika diberikan dan
    ada infusion pump terdaftar (HL7 PCD-01 atau demo), tombol
    "📥 Tarik dari Device" akan muncul untuk mengisi form otomatis sesuai
    jalur infus (Line) yang dipilih, tanpa menghilangkan opsi input manual.
    """
    
    st.markdown("### 💉 Monitoring Infus Pump")
    st.markdown(f"**Tanggal:** {tanggal} | **Episode ID:** {episode_id}")
    st.markdown("---")
    
    # Input form
    st.markdown("#### 📝 Input Data Infus Pump")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        jam = st.time_input("Jam Pengukuran", key="infus_jam")
    
    with col2:
        line_number = st.selectbox("Jalur Infus", [1, 2, 3], key="infus_line")
    
    with col3:
        iv_access = st.selectbox("Lokasi IV", 
                                ["PIK Tangan Kanan", "PIK Tangan Kiri", 
                                 "CVL Leher", "CVL Dada"],
                                key="infus_iv")
    
    # ── Tarik dari Device (opsional, hanya muncul jika connector tersedia) ────
    if connector is not None:
        pumps = connector.get_infusion_pumps() if connector.has_pumps() else []
        col_pull1, col_pull2 = st.columns([1, 3])
        with col_pull1:
            pull_clicked = st.button(
                "📥 Tarik dari Device", key="infus_pull_device",
                use_container_width=True,
                help=f"Isi form otomatis dari data pump Line {line_number} (urutan pump ke-{line_number} terdaftar).",
            )
        with col_pull2:
            if pumps:
                st.caption(f"🟢 {len(pumps)} pump terdaftar dari device — pilih Line sesuai urutan pump, lalu tarik.")
            else:
                st.caption("⚪ Belum ada pump terdaftar dari device. Form tetap bisa diisi manual.")
        
        if pull_clicked:
            idx = int(line_number) - 1
            if not pumps or idx >= len(pumps):
                st.warning(
                    f"⚠️ Tidak ada data pump untuk Line {line_number} dari device. "
                    "Pastikan HL7 Server aktif & pump sudah terdaftar (atau gunakan Demo Data)."
                )
            else:
                p = pumps[idx]
                st.session_state["infus_nama"] = p.drug_name
                st.session_state["infus_rate"] = float(p.rate_mlh)
                st.session_state["infus_volume"] = int(p.vtbi_ml)
                if PumpStatus is not None:
                    if p.status in (PumpStatus.STOPPED, PumpStatus.EMPTY):
                        status_label = "❌ Stop"
                    elif p.status in (PumpStatus.ALARMING, PumpStatus.OCCLUSION):
                        status_label = "⚠️ Alert"
                    else:
                        status_label = "✅ Normal"
                else:
                    status_label = "✅ Normal"
                st.session_state["infus_status"] = status_label
                st.toast(f"✅ Form Infus Line {line_number} terisi dari data device ({p.drug_name}).", icon="📥")
                st.rerun()
        st.markdown("")
    
    # Infus parameters
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        nama_obat = st.text_input("Nama Obat/Cairan", placeholder="e.g., Propofol 1%",
                                 key="infus_nama")
    
    with col2:
        rate = st.number_input("Rate (mL/jam)", min_value=0.0, max_value=500.0,
                              key="infus_rate", step=0.5)
    
    with col3:
        volume = st.number_input("Volume Total (mL)", min_value=0, max_value=5000,
                               key="infus_volume", step=50)
    
    with col4:
        status = st.selectbox("Status", ["✅ Normal", "⚠️ Alert", "❌ Stop"],
                             key="infus_status")
    
    # Save button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        if st.button("💾 Save Infus", type="primary", use_container_width=True):
            data = {
                'nama_obat': nama_obat,
                'rate_ml_jam': rate,
                'volume_ml': volume,
                'iv_access': iv_access,
                'status': status
            }
            
            if db.insert_infus(tanggal, jam.strftime("%H:%M"), episode_id, line_number, data):
                st.success(f"✅ Infus data saved at {jam.strftime('%H:%M')}")
                st.rerun()
            else:
                st.error("❌ Failed to save Infus data")
    
    # Display table
    st.markdown("---")
    st.markdown("#### 📊 Data Infus Pump Today")
    
    df_infus = db.get_infus_by_date(tanggal, episode_id)
    
    if not df_infus.empty:
        df_display = df_infus.copy()
        df_display.columns = ['Jam', 'Line', 'Nama Obat', 'Rate (mL/jam)', 'Volume (mL)', 
                             'IV Access', 'Status']
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        csv_infus = df_display.to_csv(index=False)
        st.download_button(
            label="📥 Download Infus Data",
            data=csv_infus,
            file_name=f"infus_{tanggal}.csv",
            mime="text/csv"
        )
    else:
        st.info("📭 No infus data recorded yet for this date")


# ═════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION - CALL THIS DI HALAMAN MONITOR_DEVICE.PY
# ═════════════════════════════════════════════════════════════════════════

def render_device_monitoring_realtime(episode_id: str = "EP-2026-00001"):
    """
    Render 3 tabs monitoring device dengan realtime input
    
    Call ini di Monitor_Device.py dengan:
    from modules.device_monitoring_realtime import render_device_monitoring_realtime
    render_device_monitoring_realtime(episode_id="EP-2026-00001")
    """
    
    # Initialize database
    db = DeviceMonitoringDB()
    
    # Date picker
    st.markdown("### 📊 Device Monitoring - Realtime Input")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        tanggal = st.date_input("Tanggal Operasional", value=datetime.now().date())
    
    with col2:
        shift = st.selectbox("Shift", ["Pagi (07:00-14:00)", "Siang (14:00-22:00)", 
                                       "Malam (22:00-07:00)"])
    
    st.markdown("---")
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs([
        "🩺 Vital Sign (TTV)",
        "🫁 Ventilator",
        "💉 Infus Pump"
    ])
    
    with tab1:
        render_tab_ttv(db, str(tanggal), episode_id)
    
    with tab2:
        render_tab_ventilator(db, str(tanggal), episode_id)
    
    with tab3:
        render_tab_infus(db, str(tanggal), episode_id)


# ═════════════════════════════════════════════════════════════════════════
# CARA MENGGUNAKAN (Copy ke Monitor_Device.py)
# ═════════════════════════════════════════════════════════════════════════

"""
Di halaman Monitor_Device.py (pages/Monitor_Device.py):

---

import streamlit as st
from modules.device_monitoring_realtime import render_device_monitoring_realtime

# Get episode_id dari session state
episode_id = st.session_state.get("episode_id", "EP-2026-00001")

# Render monitoring tabs
render_device_monitoring_realtime(episode_id=episode_id)

---

Features:
✅ Input realtime per satuan waktu (per jam)
✅ Auto-save ke SQLite database (device_monitoring.db)
✅ Tabel data terupdate otomatis
✅ Download CSV untuk setiap tab
✅ Simple UI tanpa CDSS algorithm
✅ Update/Replace data jika sudah ada untuk jam yang sama
✅ Support multiple infus lines (Line 1, 2, 3)

Database Tables:
- ttv_monitoring: untuk vital sign data
- ventilator_monitoring: untuk ventilator settings
- infus_pump_monitoring: untuk infus pump data

Setiap insert otomatis membuat timestamp created_at & updated_at
"""
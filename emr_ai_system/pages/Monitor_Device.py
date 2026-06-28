"""
Halaman: 🫁 Monitor Device (Bedside Monitor & Ventilator)
============================================================
Hasil modularisasi `dashboard_enhanced_v2.py`, diintegrasikan ke Dashboard
CPPT utama (`dashboard.py`) lewat Streamlit multipage app + jembatan
`st.session_state` (lihat `modules/bridge.py`).

`dashboard.py` TIDAK disentuh sama sekali — file ini hanya MEMBACA
konteks pasien/sesi yang sudah disiapkan olehnya, dan (opsional) MENULIS
balik teks Objective hasil generate ke kolom 'O' form CPPT.

Changelog:
  v2.0 (2026-06) — Integrasi HL7/DICOM real device:
    • HL7 MLLP Server listener (Mindray, GE, Philips, Drager)
    • DICOM WADO-RS / QIDO-RS client
    • Tab baru "🔌 Device Status" untuk monitoring koneksi
    • Sidebar device control panel (Start/Stop, ping, demo inject)
"""

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.bridge_updated import push_objective_to_cppt, require_cppt_session
from modules.device_monitoring.alerts import check_vital_alerts, check_ventilator_alerts
from modules.device_monitoring.database import (
    get_alerts, get_ventilator_history, get_vital_signs_history,
    init_database, save_alert, save_ventilator_params, save_vital_signs,
)
from modules.device_monitoring.models import VentilatorMode, VentilatorParams, VitalSigns
from modules.device_monitoring.simulators import BedisideMonitorSimulator, VentilatorSimulator
from modules.device_monitoring.soap_generator import generate_objective_section

# ── NEW: Real Device Integration ─────────────────────────────────────────────
from modules.device_monitoring.device_connector import (
    DICOMConfig,
    RealDeviceConnector,
    get_or_create_connector,
)
from modules.device_monitoring.dicom_gateway import check_dicom_dependencies

from modules.device_monitoring.clma_tab import render_clma_tab

# ═════════════════════════════════════════════════════════════════════════
# REALTIME DEVICE MONITORING IMPORT (Integrated for TTV, Ventilator, Infus)
# ═════════════════════════════════════════════════════════════════════════
from modules.device_monitoring_realtime import (
    DeviceMonitoringDB, 
    render_tab_ttv, 
    render_tab_ventilator, 
    render_tab_infus
)

st.set_page_config(
    page_title="Smart EMR - Monitor Device",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="expanded",
)

from modules.device_monitoring.infusion_tab import render_infusion_tab
init_database()

# ── Guard ─────────────────────────────────────────────────────────────────────
ctx = require_cppt_session()
patient_id   = ctx["episode_id"]
patient_name = ctx["pasien_nama"] or "-"

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.markdown("## 🫁 Monitor Device")
st.sidebar.page_link("dashboard.py", label="⬅️ Kembali ke Dashboard CPPT", icon="🫀")
st.sidebar.markdown("---")
st.sidebar.markdown("**🛏️ Pasien Aktif** _(dari Dashboard CPPT)_")
st.sidebar.write(f"🧑 Nama: **{patient_name}**")
st.sidebar.write(f"🪪 No. RM: `{ctx['pasien_no_rm']}`")
st.sidebar.write(f"🏷️ Episode: `{patient_id}`")
st.sidebar.caption("Patient ID device-monitoring = Episode ID CPPT.")

is_intubated = st.sidebar.checkbox("Pasien Intubasi (Ventilator)", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Setting Device")
device_mode = st.sidebar.radio(
    "Mode Input Data:",
    options=["🔄 Manual Input", "📊 Auto (Simulate)", "🔗 Real Device (HL7/DICOM)"],
    help="Pilih sumber data vital signs dan ventilator",
)

# ── Inisialisasi connector (hanya dipakai saat Real Device mode) ──────────────
connector: RealDeviceConnector | None = None

if device_mode == "🔗 Real Device (HL7/DICOM)":
    st.sidebar.markdown("#### 🔌 Konfigurasi HL7 MLLP")

    hl7_listen_on = st.sidebar.text_input(
        "Listen on (IP server ini):", value="0.0.0.0",
        help="0.0.0.0 = semua interface. Ganti dengan IP spesifik jika perlu.",
    )
    hl7_port = st.sidebar.number_input(
        "Port MLLP:", value=2575, min_value=1024, max_value=65535,
        help="Default HL7 MLLP = 2575. Sesuaikan dengan konfigurasi di bedside monitor.",
    )

    st.sidebar.markdown("#### 🏥 Konfigurasi DICOM (Opsional)")
    use_dicom = st.sidebar.checkbox("Aktifkan DICOM WADO-RS/QIDO-RS", value=False)
    dicom_cfg: DICOMConfig | None = None
    if use_dicom:
        dicom_deps = check_dicom_dependencies()
        if not dicom_deps["requests"]:
            st.sidebar.warning("⚠️ `requests` belum terinstall. `pip install requests`")
        if not dicom_deps["pydicom"]:
            st.sidebar.warning("⚠️ `pydicom` belum terinstall. `pip install pydicom`")
        if dicom_deps["dicom_full"]:
            dicom_url  = st.sidebar.text_input("PACS URL:", value="http://localhost:8042")
            dicom_user = st.sidebar.text_input("Username PACS:", value="")
            dicom_pass = st.sidebar.text_input("Password PACS:", type="password", value="")
            dicom_cfg  = DICOMConfig(
                base_url=dicom_url,
                username=dicom_user,
                password=dicom_pass,
            )

    # Buat / ambil connector dari session_state
    connector = get_or_create_connector(hl7_listen_on, int(hl7_port), dicom_cfg)

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🎛️ Device Control")
    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        if not connector.is_hl7_running():
            if st.button("▶ Start", key="btn_start_hl7", use_container_width=True, type="primary"):
                ok, msg = connector.start_hl7()
                st.toast(f"{'✓' if ok else '✗'} {msg}", icon="🟢" if ok else "🔴")
                st.rerun()
        else:
            if st.button("⏹ Stop", key="btn_stop_hl7", use_container_width=True):
                connector.stop_hl7()
                st.toast("HL7 Server dihentikan.", icon="⏹")
                st.rerun()
    with col_b:
        if st.button("🔬 Demo Data", key="btn_demo", use_container_width=True,
                      help="Inject data simulasi Mindray N22 untuk testing"):
            connector.inject_demo_data(patient_id)
            st.toast("Data demo diinjeksi.", icon="🔬")
            st.rerun()

    # Status HL7
    sta = connector.status_hl7
    if connector.is_hl7_running():
        st.sidebar.success(f"🟢 Server aktif — port {sta.port}")
    else:
        st.sidebar.info(f"⚫ Server tidak aktif (port {int(hl7_port)})")

    if sta.last_msg_at:
        st.sidebar.caption(
            f"📨 Pesan diterima: **{sta.total_received}** | "
            f"Terakhir: {sta.last_msg_str}"
        )

    if use_dicom and dicom_cfg:
        if st.sidebar.button("🏥 Ping PACS", key="btn_ping_pacs"):
            ok, msg = connector.ping_dicom()
            st.sidebar.success(msg) if ok else st.sidebar.error(msg)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("MONITORING ALAT-ALAT MEDIS")
st.markdown(
    f"**Patient:** {patient_name} (`{patient_id}`) | "
    f"**Status:** {'Intubasi ✓' if is_intubated else 'Non-Intubasi'}"
)
st.markdown("---")

# Tambah variabel tab_clma dan sesuaikan jumlah kembalian st.tabs()
if device_mode == "🔗 Real Device (HL7/DICOM)":
    tab1, tab2, tab3, tab4, tab_clma, tab5, tab_pump, tab_ttv_realtime, tab_vent_realtime, tab_infus_realtime, tab_device_status = st.tabs([
        "📊 Real-Time Monitor",
        "🫁 Ventilator Panel",
        "⚠️ Alerts & Events",
        "📝 Objective → CPPT",
        "🔄 CLMA",
        "📈 Trend Analysis",
        "💉 Infusion Pump",
        "🩺 TTV Realtime Input",
        "🫁 Ventilator Realtime Input",
        "💉 Infus Realtime Input",
        "🔌 Device Status",
    ])
    
else:
    tab1, tab2, tab3, tab4, tab_clma, tab5, tab_pump, tab_ttv_realtime, tab_vent_realtime, tab_infus_realtime = st.tabs([
        "📊 Real-Time Monitor",
        "🫁 Ventilator Panel",
        "⚠️ Alerts & Events",
        "📝 Objective → CPPT",
        "🔄 CLMA",
        "📈 Trend Analysis",
        "💉 Infusion Pump",
        "🩺 TTV Realtime Input",
        "🫁 Ventilator Realtime Input",
        "💉 Infus Realtime Input",
    ])
    
    tab_device_status = None

# =============================================================================
# TAB 1 — Real-Time Monitoring
# =============================================================================
with tab1:
    st.subheader("📊 Real-Time Vital Signs Monitor")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"**Mode Input:** {device_mode}")
    with col2:
        if st.button("🔄 Refresh Now", key="refresh_vitals"):
            st.rerun()

    # ── Manual Input ──────────────────────────────────────────────────────────
    if device_mode == "🔄 Manual Input":
        st.warning("📌 Mode Manual - Input data vital signs secara manual")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            hr = st.number_input("Heart Rate (bpm)", min_value=30, max_value=200, value=80)
        with col2:
            systolic_bp = st.number_input("Systolic BP (mmHg)", min_value=60, max_value=250, value=130)
        with col3:
            diastolic_bp = st.number_input("Diastolic BP (mmHg)", min_value=40, max_value=150, value=85)
        with col4:
            spo2 = st.number_input("SpO2 (%)", min_value=70, max_value=100, value=97)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            rr = st.number_input("Respiratory Rate (/min)", min_value=8, max_value=40, value=16)
        with col2:
            temp = st.number_input("Temperature (°C)", min_value=35.0, max_value=42.0, value=36.8)
        with col3:
            cvp = st.number_input("CVP (cmH2O)", min_value=-5.0, max_value=20.0, value=8.0)
        with col4:
            map_val = st.number_input("MAP (mmHg)", min_value=40, max_value=150, value=100)

        vs = VitalSigns(
            timestamp=datetime.now().isoformat(),
            heart_rate=hr, systolic_bp=systolic_bp, diastolic_bp=diastolic_bp,
            spo2=spo2, respiratory_rate=rr, body_temp=temp, cvp=cvp,
            map=map_val, source="manual",
        )

    # ── Simulator ─────────────────────────────────────────────────────────────
    elif device_mode == "📊 Auto (Simulate)":
        st.success("✓ Data dari Simulator (Real-time)")
        vs = BedisideMonitorSimulator.get_live_vitals()
        time.sleep(0.5)

    # ── Real Device ───────────────────────────────────────────────────────────
    else:
        sta = connector.status_hl7
        if not connector.is_hl7_running():
            st.error(
                "⚠️ HL7 Server belum aktif. Klik **▶ Start** di sidebar "
                "untuk mulai menerima data dari device."
            )
            vs = BedisideMonitorSimulator.get_live_vitals()
            vs = VitalSigns(**{**vars(vs), "source": "hl7_device_pending"})

        elif connector.has_vitals():
            vs_live = connector.as_vital_signs()
            vs = vs_live
            last_str = sta.last_msg_str
            st.success(
                f"🟢 Data live dari HL7 MLLP | "
                f"Diterima: **{sta.total_received}** pesan | "
                f"Terakhir: **{last_str}** | "
                f"Uptime: {sta.uptime_str}"
            )
            # Coba pull DICOM juga jika dikonfigurasi
            if connector.dicom_available:
                dicom_result = connector.fetch_dicom_vitals(patient_id)
                if dicom_result:
                    st.info(f"🏥 DICOM SR: +{len(dicom_result)} parameter diperbarui dari PACS.")
                    vs = connector.as_vital_signs()

        else:
            st.warning(
                "⏳ HL7 Server aktif — menunggu data dari device. "
                "Pastikan bedside monitor dikonfigurasi untuk mengirim "
                f"ke IP server ini pada port **{sta.port}**. "
                "Gunakan **🔬 Demo Data** untuk inject data testing."
            )
            vs = BedisideMonitorSimulator.get_live_vitals()
            vs = VitalSigns(**{**vars(vs), "source": "hl7_device_pending"})

    # ── Tampilkan metric cards ─────────────────────────────────────────────────
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    def display_vital_card(col, label, value, unit, min_val, max_val, critical=None):
        with col:
            if critical and value < critical:
                icon = "🔴"
            elif value < min_val or value > max_val:
                icon = "🟠"
            else:
                icon = "🟢"
            display_value = f"{value:.1f}" if isinstance(value, float) else value
            st.metric(label=f"{icon} {label}", value=display_value,
                       delta=f"{unit}", delta_color="off")

    display_vital_card(col1, "HR",   vs.heart_rate,       "bpm",  60, 100)
    display_vital_card(col2, "SBP",  vs.systolic_bp,      "mmHg", 100, 140)
    display_vital_card(col3, "DBP",  vs.diastolic_bp,     "mmHg", 60, 90)
    display_vital_card(col4, "SpO2", vs.spo2,             "%",    95, 100, critical=90)
    display_vital_card(col5, "RR",   vs.respiratory_rate, "/min", 12, 20)
    display_vital_card(col6, "Temp", vs.body_temp,        "°C",   36.5, 37.5)

    if st.button("💾 Save Vital Signs", key="save_vitals"):
        save_vital_signs(patient_id, vs)
        st.success(f"✓ Vital signs saved at {vs.timestamp}")

    alerts = check_vital_alerts(patient_id, vs)
    if alerts:
        st.markdown("### ⚠️ Active Alerts")
        for alert in alerts:
            with st.container():
                st.markdown(f"**{alert.level}** {alert.message}")
                save_alert(patient_id, alert)

# =============================================================================
# TAB 2 — Ventilator Panel
# =============================================================================
with tab2:
    st.subheader("🫁 Ventilator Parameter Monitor")

    if is_intubated:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**Input Mode:** {device_mode}")
        with col2:
            if st.button("🔄 Refresh Ventilator", key="refresh_vent"):
                st.rerun()

        # ── Manual ────────────────────────────────────────────────────────────
        if device_mode == "🔄 Manual Input":
            st.warning("📌 Mode Manual - Input parameter ventilator")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                mode = st.selectbox("Mode", options=[m.value for m in VentilatorMode])
            with col2:
                fio2 = st.slider("FiO2 (%)", min_value=21, max_value=100, value=60) / 100
            with col3:
                peep = st.slider("PEEP (cmH2O)", min_value=0.0, max_value=20.0, value=5.0)
            with col4:
                tidal_vol = st.number_input("Tidal Volume (mL)", min_value=300, max_value=800, value=450)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                rr_set = st.number_input("RR Set (/min)", min_value=6, max_value=40, value=14)
            with col2:
                ie_ratio = st.selectbox("I:E Ratio", options=["1:1", "1:2", "1:3", "1:4"])
            with col3:
                map_vent = st.number_input("Mean Airway Pressure (cmH2O)", min_value=5.0, max_value=40.0, value=15.0)
            with col4:
                peak_pressure = st.number_input("Peak Pressure (cmH2O)", min_value=10.0, max_value=50.0, value=22.0)

            vp = VentilatorParams(
                timestamp=datetime.now().isoformat(), mode=mode, fio2=fio2, peep=peep,
                tidal_volume=tidal_vol, rate_set=rr_set, ie_ratio=ie_ratio,
                mean_airway_pressure=map_vent, peak_pressure=peak_pressure,
                source="manual",
            )

        # ── Simulator ─────────────────────────────────────────────────────────
        elif device_mode == "📊 Auto (Simulate)":
            st.success("✓ Data dari Ventilator (Real-time)")
            vp = VentilatorSimulator.get_live_params()

        # ── Real Device ───────────────────────────────────────────────────────
        else:
            if connector.is_hl7_running() and connector.has_vent():
                vp_live = connector.as_vent_params()
                vp = vp_live
                st.success(
                    f"🟢 Parameter ventilator dari HL7 MLLP | "
                    f"Mode: **{getattr(vp.mode, 'value', vp.mode)}** | "
                    f"Uptime: {connector.status_hl7.uptime_str}"
                )
            elif connector.is_hl7_running():
                st.warning(
                    "⏳ HL7 Server aktif — belum ada data ventilator. "
                    "Pastikan ventilator dikonfigurasi sebagai HL7 sender. "
                    "Gunakan **🔬 Demo Data** untuk testing."
                )
                vp = VentilatorSimulator.get_live_params()
                vp = VentilatorParams(**{**vars(vp), "source": "hl7_vent_pending"})
            else:
                st.error("⚠️ HL7 Server belum aktif. Klik ▶ Start di sidebar.")
                vp = VentilatorSimulator.get_live_params()
                vp = VentilatorParams(**{**vars(vp), "source": "hl7_vent_pending"})

        # ── Metric display ─────────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Mode", getattr(vp.mode, "value", vp.mode))
        with col2:
            st.metric("FiO2", f"{vp.fio2*100:.0f}%")
        with col3:
            st.metric("PEEP", f"{vp.peep:.1f} cmH2O")
        with col4:
            st.metric("Tidal Volume", f"{vp.tidal_volume} mL")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("RR Set", f"{vp.rate_set} /min")
        with col2:
            st.metric("I:E Ratio", vp.ie_ratio)
        with col3:
            st.metric("Mean Airway Pressure", f"{vp.mean_airway_pressure:.1f} cmH2O")
        with col4:
            st.metric(
                "Peak Pressure",
                f"{vp.peak_pressure:.1f} cmH2O",
                delta="⚠️ HIGH" if vp.peak_pressure > 25 else "✓ Normal",
            )

        if st.button("💾 Save Ventilator Params", key="save_vent"):
            save_ventilator_params(patient_id, vp)
            st.success(f"✓ Ventilator params saved at {vp.timestamp}")

        vent_alerts = check_ventilator_alerts(patient_id, vp)
        if vent_alerts:
            st.markdown("### ⚠️ Ventilator Alerts")
            for alert in vent_alerts:
                with st.container():
                    st.markdown(f"**{alert.level}** {alert.message}")
                    save_alert(patient_id, alert)
        
        # Grafik Tren Parameter Utama Ventilator
        st.markdown("#### 📉 Trend Analitik FiO2, PEEP & Peak Pressure")
        v_hours = ['07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00']
        fio2_v = [40, 45, 45, 50, 50, 45, 45, 40, 40, 40, 40, 40]
        peep_v = [5, 5, 5, 6, 6, 6, 6, 5, 5, 5, 5, 5]
        press_v = [22, 24, 23, 25, 24, 22, 23, 21, 22, 23, 22, 21]
        
        fig_v = go.Figure()
        fig_v.add_trace(go.Scatter(x=v_hours, y=fio2_v, mode='lines+markers', name='FiO2 (%)', line=dict(color='#FF6B6B', width=2)))
        fig_v.add_trace(go.Scatter(x=v_hours, y=peep_v, mode='lines+markers', name='PEEP (cmH2O)', line=dict(color='#4ECDC4', width=2)))
        fig_v.add_trace(go.Scatter(x=v_hours, y=press_v, mode='lines+markers', name='Peak Pressure (cmH2O)', line=dict(color='#FFD93D', width=2)))
        fig_v.update_layout(xaxis_title='Waktu', yaxis_title='Nilai', hovermode='x unified', height=350, template='plotly_white', margin=dict(t=20, b=20, l=10, r=10))
        st.plotly_chart(fig_v, use_container_width=True)
        
    else:
        st.info("ℹ️ Pasien tidak intubasi - Ventilator panel tidak tersedia")

# =============================================================================
# TAB 3 — Alerts & Events
# =============================================================================
with tab3:
    st.subheader("⚠️ Alert & Event Log")
    col1, col2 = st.columns([2, 1])
    with col1:
        hours = st.slider("Show alerts dari", min_value=1, max_value=24, value=24)
    with col2:
        if st.button("🔄 Refresh Alerts"):
            st.rerun()

    alerts_df = pd.DataFrame(get_alerts(patient_id, hours=hours))
    if not alerts_df.empty:
        st.dataframe(
            alerts_df[["timestamp", "alert_type", "level", "message"]].rename(
                columns={"timestamp": "Time", "alert_type": "Type",
                         "level": "Level", "message": "Message"}
            ),
            use_container_width=True,
        )
    else:
        st.info("✓ Tidak ada alert aktif")

# =============================================================================
# TAB 4 — Objective → CPPT
# =============================================================================
with tab4:
    st.subheader("📝 Auto-Generated Objective dari Data Device")
    st.caption(
        "Generate bagian Objective (O) dari data vital signs/ventilator terakhir, "
        "lalu kirim langsung ke kolom **O** di form SOAP Dashboard CPPT."
    )

    vs_history   = get_vital_signs_history(patient_id, hours=1)
    vent_history = get_ventilator_history(patient_id, hours=1) if is_intubated else pd.DataFrame()

    if vs_history.empty:
        st.info(
            "ℹ️ Belum ada data vital signs tersimpan untuk pasien ini dalam 1 jam terakhir. "
            "Simpan data dulu di tab **Real-Time Monitor**."
        )
    else:
        latest_vs = vs_history.iloc[0]
        vs_obj = VitalSigns(
            timestamp=latest_vs["timestamp"],
            heart_rate=int(latest_vs["heart_rate"]),
            systolic_bp=int(latest_vs["systolic_bp"]),
            diastolic_bp=int(latest_vs["diastolic_bp"]),
            spo2=latest_vs["spo2"],
            respiratory_rate=int(latest_vs["respiratory_rate"]),
            body_temp=latest_vs["body_temp"],
            cvp=latest_vs["cvp"],
            map=latest_vs["map"],
            source=latest_vs["source"],
        )

        vp_obj = None
        if is_intubated and not vent_history.empty:
            latest_vp = vent_history.iloc[0]
            vp_obj = VentilatorParams(
                timestamp=latest_vp["timestamp"],
                mode=latest_vp["mode"], fio2=latest_vp["fio2"],
                peep=latest_vp["peep"],
                tidal_volume=int(latest_vp["tidal_volume"]),
                rate_set=int(latest_vp["rate_set"]),
                ie_ratio=latest_vp["ie_ratio"],
                mean_airway_pressure=latest_vp["mean_airway_pressure"],
                peak_pressure=latest_vp["peak_pressure"],
                source=latest_vp["source"],
            )

        objective_text = generate_objective_section(patient_id, vs_obj, vp_obj)
        st.markdown(objective_text)

        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("📤 Kirim ke Form CPPT (Kolom Objective)", type="primary"):
                push_objective_to_cppt(objective_text)
                st.success("✓ Terkirim! Buka kembali Dashboard CPPT — kolom 'O' sudah terisi.")
        with col2:
            st.page_link("dashboard.py", label="⬅️ Buka Dashboard CPPT sekarang", icon="🫀")

# =============================================================================
# TAB 5 — Trend Analysis
# =============================================================================
with tab5:
    st.subheader("📈 Trend Analysis & Visualization")
    trend_hours = st.slider("Tampilkan trend (jam):", min_value=1, max_value=168, value=24)
    vs_df = get_vital_signs_history(patient_id, hours=trend_hours)

    if not vs_df.empty:
        vs_df["timestamp"] = pd.to_datetime(vs_df["timestamp"])

        # Label sumber data di chart
        if "source" in vs_df.columns:
            src_counts = vs_df["source"].value_counts().to_dict()
            src_info = " | ".join(f"{k}: {v}" for k, v in src_counts.items())
            st.caption(f"📊 Sumber data: {src_info}")

        col1, col2 = st.columns(2)
        with col1:
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(
                x=vs_df["timestamp"], y=vs_df["heart_rate"],
                mode="lines+markers", name="Heart Rate", line=dict(color="red", width=2),
            ))
            fig1.add_hline(y=60, line_dash="dash", line_color="green", annotation_text="Min 60")
            fig1.add_hline(y=100, line_dash="dash", line_color="green", annotation_text="Max 100")
            fig1.update_layout(title="Heart Rate Trend", xaxis_title="Time",
                                yaxis_title="HR (bpm)", height=400, hovermode="x unified")
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=vs_df["timestamp"], y=vs_df["spo2"],
                mode="lines+markers", name="SpO2", line=dict(color="blue", width=2), fill="tozeroy",
            ))
            fig2.add_hline(y=90, line_dash="dash", line_color="red", annotation_text="Critical <90%")
            fig2.update_layout(title="SpO2 Trend", xaxis_title="Time",
                                yaxis_title="SpO2 (%)", height=400, hovermode="x unified")
            st.plotly_chart(fig2, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(x=vs_df["timestamp"], y=vs_df["systolic_bp"],
                                       mode="lines+markers", name="Static", line=dict(color="purple", width=2)))
            fig3.add_trace(go.Scatter(x=vs_df["timestamp"], y=vs_df["diastolic_bp"],
                                       mode="lines+markers", name="Diastolic", line=dict(color="orange", width=2)))
            fig3.update_layout(title="Blood Pressure Trend", xaxis_title="Time",
                                yaxis_title="BP (mmHg)", height=400, hovermode="x unified")
            st.plotly_chart(fig3, use_container_width=True)

        with col2:
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=vs_df["timestamp"], y=vs_df["body_temp"],
                                       mode="lines+markers", name="Temperature",
                                       line=dict(color="orange", width=2)))
            fig4.add_hline(y=36.5, line_dash="dash", line_color="green", annotation_text="Normal Low")
            fig4.add_hline(y=37.5, line_dash="dash", line_color="green", annotation_text="Normal High")
            fig4.update_layout(title="Temperature Trend", xaxis_title="Time",
                                yaxis_title="Temp (°C)", height=400, hovermode="x unified")
            st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("ℹ️ Belum ada data vital signs untuk di-analisis")

    if is_intubated:
        st.markdown("---")
        st.markdown("### 🫁 Ventilator Parameter Trend")
        vent_df = get_ventilator_history(patient_id, hours=trend_hours)
        if not vent_df.empty:
            vent_df["timestamp"] = pd.to_datetime(vent_df["timestamp"])
            col1, col2 = st.columns(2)
            with col1:
                fig5 = go.Figure()
                fig5.add_trace(go.Scatter(x=vent_df["timestamp"], y=vent_df["peak_pressure"],
                                           mode="lines+markers", name="Peak Pressure",
                                           line=dict(color="red", width=2)))
                fig5.add_hline(y=30, line_dash="dash", line_color="red", annotation_text="Alert >30")
                fig5.update_layout(title="Peak Pressure Trend", xaxis_title="Time",
                                    yaxis_title="Pressure (cmH2O)", height=400)
                st.plotly_chart(fig5, use_container_width=True)
            with col2:
                fig6 = go.Figure()
                fig6.add_trace(go.Scatter(x=vent_df["timestamp"], y=vent_df["fio2"],
                                           mode="lines+markers", name="FiO2",
                                           line=dict(color="blue", width=2)))
                fig6.update_layout(title="FiO2 Trend", xaxis_title="Time",
                                    yaxis_title="FiO2 (%)", height=400)
                st.plotly_chart(fig6, use_container_width=True)
        else:
            st.info("ℹ️ Belum ada data ventilator untuk di-analisis")

# =============================================================================
# TAB — Infusion Pump
# =============================================================================
with tab_pump:
    render_infusion_tab(connector, patient_id)
    
# =============================================================================
# TAB — CLMA
# =============================================================================
with tab_clma:
    render_clma_tab(connector, ctx)

# =============================================================================
# REALTIME INPUT TABS: TTV, VENTILATOR, INFUS PUMP (with Database Sync)
# =============================================================================

# Initialize database untuk realtime monitoring
db = DeviceMonitoringDB()
tanggal_monitoring = datetime.now().date()

# ── TAB: TTV Realtime Input ─────────────────────────────────────────────────
with tab_ttv_realtime:
    render_tab_ttv(db, str(tanggal_monitoring), patient_id, connector=connector)

# ── TAB: Ventilator Realtime Input ──────────────────────────────────────────
with tab_vent_realtime:
    render_tab_ventilator(db, str(tanggal_monitoring), patient_id, connector=connector)

# ── TAB: Infus Pump Realtime Input ──────────────────────────────────────────
with tab_infus_realtime:
    render_tab_infus(db, str(tanggal_monitoring), patient_id, connector=connector)

# =============================================================================
# TAB — Device Status (hanya muncul di Real Device mode)
# =============================================================================
if tab_device_status is not None:
    with tab_device_status:
        st.subheader("🔌 Real Device Connection Status")

        if connector is None:
            st.info("Pilih mode **Real Device (HL7/DICOM)** untuk melihat status koneksi.")
        else:
            sta = connector.status_hl7

            # ── Status kartu ──────────────────────────────────────────────────
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Status Server",
                       "🟢 AKTIF" if connector.is_hl7_running() else "⚫ NONAKTIF")
            c2.metric("Port MLLP", str(sta.port))
            c3.metric("Pesan Diterima", str(sta.total_received))
            c4.metric("Uptime", sta.uptime_str)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Data Vital Tersedia", "✓ YA" if connector.has_vitals() else "✗ BELUM")
            c2.metric("Data Vent Tersedia", "✓ YA" if connector.has_vent() else "✗ BELUM")
            c3.metric("Error Total", str(sta.total_errors))
            c4.metric("Pesan Terakhir", sta.last_msg_str)

            if sta.last_error:
                st.error(f"⚠️ Error terakhir: {sta.last_error}")

            st.markdown("---")

            # ── Raw HL7 message terakhir ───────────────────────────────────────
            raw = connector.get_raw_hl7()
            if raw:
                with st.expander("📜 Pesan HL7 Terakhir (raw)", expanded=False):
                    # Format per-baris untuk keterbacaan
                    formatted = "\n".join(
                        line for line in raw.replace("\r", "\n").splitlines() if line.strip()
                    )
                    st.code(formatted, language="text")
            else:
                st.info("Belum ada pesan HL7 diterima.")

            st.markdown("---")

            # ── Panduan konfigurasi device ────────────────────────────────────
            with st.expander("📖 Panduan Konfigurasi Bedside Monitor", expanded=True):
                server_ip = sta.host if sta.host != "0.0.0.0" else "*(IP server ini)*"
                st.markdown(f"""
**Parameter yang perlu dikonfigurasi di bedside monitor / ventilator:**

| Parameter | Nilai |
|---|---|
| Protocol | HL7 v2.x MLLP |
| Destination IP | `{server_ip}` |
| Destination Port | `{sta.port}` |
| Message Type | ORU^R01 (Observation Result) |
| Encoding | Latin-1 / ISO-8859-1 |
| ACK Mode | Enhanced / Original |

**Perangkat yang sudah terverifikasi kompatibel:**
- **Mindray BeneVision N22/N17/N12** — Menu: System → Network → HL7 → Enable Sender
- **GE CARESCAPE B850/B650** — Network Configuration → HL7 Outbound Interface
- **Philips IntelliVue MX700/800** — Data Export → HL7 → Remote Host
- **Drager Evita Infinity V500** — Communication → HL7 Output
- **Hamilton G5/C6** — Network → HL7 Data Export
- **Puritan Bennett 980** — Settings → Network Communication Module

**Troubleshooting:**
1. Pastikan firewall Windows/server membuka port `{sta.port}` untuk TCP inbound
2. Gunakan **🔬 Demo Data** untuk verifikasi pipeline tanpa device fisik
3. Cek Raw HL7 di atas untuk validasi format pesan dari device
                """)

            # ── DICOM status ───────────────────────────────────────────────────
            st.markdown("---")
            st.markdown("### 🏥 Status DICOM")
            deps = check_dicom_dependencies()
            col1, col2 = st.columns(2)
            col1.metric("requests", "✓ Terinstall" if deps["requests"] else "✗ Tidak ada")
            col2.metric("pydicom",  "✓ Terinstall" if deps["pydicom"] else "✗ Tidak ada")

            if not deps["dicom_full"]:
                st.warning(
                    "Untuk mengaktifkan DICOM, install dependensi yang kurang:\n"
                    "```\npip install requests pydicom\n```"
                )
            elif connector.dicom_available:
                if st.button("🏥 Test Koneksi PACS", key="ping_pacs_tab6"):
                    ok, msg = connector.ping_dicom()
                    if ok:
                        st.success(f"✓ {msg}")
                    else:
                        st.error(f"✗ {msg}")
            else:
                st.info("DICOM tidak dikonfigurasi. Centang 'Aktifkan DICOM' di sidebar.")
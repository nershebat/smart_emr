"""
PATCH: Tambahkan tab 💉 Infusion Pump ke 1___Monitor_Device.py
==============================================================
Petunjuk integrasi:
  1. Copy file ini ke app/modules/device_monitoring/infusion_tab.py
  2. Di 1___Monitor_Device.py, import dan panggil render_infusion_tab()
  3. Tambah tab "💉 Infusion Pump" di daftar st.tabs()

Import yang perlu ditambahkan di 1___Monitor_Device.py:
  from modules.device_monitoring.infusion_gateway import (
      PumpStatus, DrugCategory, DrugResolver,
      create_manual_pump, InfusionAlarmChecker, VasopressorIndex,
  )
  from modules.device_monitoring.infusion_tab import render_infusion_tab

Contoh penggunaan di 1___Monitor_Device.py:

  tab1, tab2, tab_pump, tab3, tab4, tab5, tab6 = st.tabs([
      "📊 Real-Time Monitor", "🫁 Ventilator Panel",
      "💉 Infusion Pump",
      "⚠️ Alerts & Events", "📝 Objective → CPPT",
      "📈 Trend Analysis", "🔌 Device Status",
  ])

  with tab_pump:
      render_infusion_tab(connector, patient_id)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from .infusion_gateway import (
    DrugCategory, DrugResolver, InfusionAlarmChecker,
    InfusionPump, PumpStatus, VasopressorIndex,
    create_manual_pump,
)


def render_infusion_tab(connector, patient_id: str) -> None:
    """
    Render lengkap tab 💉 Infusion Pump.
    connector = RealDeviceConnector instance (atau None jika mode simulator/manual).
    """
    st.subheader("💉 Infusion Pump Monitor — Mindray BeneFusion")
    st.caption(
        "Data pump dari HL7 IHE PCD-01 (nDS ex) atau input manual. "
        "Vasopressor aktif otomatis muncul di konteks CDSS & Objective CPPT."
    )

    # ── Tombol aksi ──────────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        if connector and st.button("📡 Demo Pump (foto ICCU)", key="btn_demo_pump",
                                    use_container_width=True):
            connector.inject_demo_pumps()
            st.toast("Demo pump diinjeksi (Norepinephrine + Undefined)", icon="💉")
            st.rerun()
    with col_b:
        if st.button("🔄 Refresh", key="btn_refresh_pump", use_container_width=True):
            st.rerun()

    # ── Ambil daftar pump ─────────────────────────────────────────────────────
    if connector:
        pumps = connector.get_infusion_pumps()
    else:
        pumps = []

    if pumps:
        pumps_by_id = {p.pump_id: p for p in pumps}
    else:
        pumps_by_id = {}

    # ── Vasopressor Index Banner ───────────────────────────────────────────────
    if pumps:
        vis = VasopressorIndex.calculate(pumps)
        n_vp = vis["n_vasopressor"]
        burden = vis["burden"]

        color_map = {
            "Tidak Ada": "🟢", "Ringan": "🟡",
            "Sedang": "🟠", "Berat": "🔴", "Refrakter": "🆘",
        }
        icon = color_map.get(burden, "⚪")

        banner_cols = st.columns(5)
        banner_cols[0].metric("Total Pump", f"{vis['active_pumps']} aktif / {len(pumps)}")
        banner_cols[1].metric("Vasopressor", str(n_vp))
        banner_cols[2].metric("Inotrope", str(len(vis["inotropes"])))
        banner_cols[3].metric("Burden", f"{icon} {burden}")
        banner_cols[4].metric("Obat Kritis", str(len(vis["critical_drugs"])))

        if vis["has_vasopressor"]:
            st.warning(
                f"⚠️ **Vasopressor Aktif** — "
                f"{', '.join(p.drug_name for p in vis['vasopressors'])} | "
                f"Burden: **{burden}**"
            )

    st.markdown("---")

    # ── Pump Cards ────────────────────────────────────────────────────────────
    st.markdown("### 🏥 Pump Aktif")

    if not pumps:
        st.info(
            "Belum ada pump terdaftar. "
            "Gunakan **📡 Demo Pump** untuk testing, atau tambah manual di bawah."
        )
    else:
        for pump in pumps:
            _render_pump_card(pump, connector)

    # ── Infusion Alarms ───────────────────────────────────────────────────────
    if pumps:
        alarms = InfusionAlarmChecker.check(pumps)
        if alarms:
            st.markdown("---")
            st.markdown("### 🚨 Infusion Alarms")
            for a in alarms:
                if a.level == "CRITICAL":
                    st.error(a.message)
                elif a.level == "WARNING":
                    st.warning(a.message)
                else:
                    st.info(a.message)

    # ── Tambah Pump Manual ────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("➕ Tambah / Edit Pump Manual", expanded=not bool(pumps)):
        _render_add_pump_form(connector)

    # ── CDSS Context Preview ──────────────────────────────────────────────────
    if pumps and connector:
        st.markdown("---")
        with st.expander("🧠 Preview Konteks untuk CDSS & CPPT Objective", expanded=False):
            ctx = connector.get_cdss_context_text()
            st.code(ctx, language="text")
            if st.button("📤 Tambahkan ke Objective CPPT", key="btn_pump_to_cppt"):
                # Append ke o_text_area yang sudah ada
                existing = st.session_state.get("o_text_area", "")
                st.session_state["o_text_area"] = (
                    (existing + "\n\n" if existing else "") + ctx
                )
                st.success("✓ Konteks infusion pump ditambahkan ke kolom O di Dashboard CPPT.")


# =============================================================================
# Helper: render satu pump card
# =============================================================================

def _render_pump_card(pump: InfusionPump, connector) -> None:
    cat_emoji  = DrugResolver.category_emoji(pump.drug_category)
    crit_badge = "🔴 KRITIS" if pump.is_critical else ""

    with st.container(border=True):
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(
                f"**{pump.status_emoji} {pump.pump_id}** — "
                f"{cat_emoji} **{pump.drug_name}** {crit_badge}"
            )
        with h2:
            st.caption(f"Sumber: `{pump.source}`")

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Rate", f"{pump.rate_mlh:.2f} ml/h")
        m2.metric("VTBI Sisa", f"{pump.vtbi_ml:.0f} ml")
        m3.metric("Terinfus", f"{pump.volume_infused_ml:.0f} ml")
        m4.metric("Line Pressure", f"{pump.line_pressure_mmhg:.0f} mmHg",
                   delta="⚠️ HIGH" if pump.line_pressure_mmhg > 250 else None,
                   delta_color="inverse")
        m5.metric("Run Time", pump.run_time_str)
        m6.metric("Sisa ±", f"{pump.remaining_hours:.1f} jam" if pump.remaining_hours > 0 else "—")

        d1, d2, d3 = st.columns([2, 2, 1])
        d1.caption(f"Mode: `{pump.rate_mode or '—'}`  |  Syringe: {pump.syringe_size_ml:.0f} ml")
        d2.caption(f"Kategori: {pump.drug_category.value}  |  Status: {pump.status.value}")

        with d3:
            if connector and st.button(
                "🗑 Hapus", key=f"del_{pump.pump_id}", use_container_width=True
            ):
                connector.remove_pump(pump.pump_id)
                st.rerun()

        if pump.dose_rate_mcg_kg_min > 0:
            st.caption(
                f"💊 Dose rate: **{pump.dose_rate_mcg_kg_min:.4f} mcg/kg/min** "
                f"(konsentrasi: {pump.concentration_mcg_ml:.1f} mcg/ml, "
                f"BB: {pump.patient_weight_kg:.0f} kg)"
            )


# =============================================================================
# Helper: form tambah pump manual
# =============================================================================

def _render_add_pump_form(connector) -> None:
    # Existing pump IDs untuk auto-increment
    existing = connector.get_infusion_pumps() if connector else []
    next_num = len(existing) + 1
    default_id = f"PUMP-{next_num:02d}"

    col1, col2 = st.columns(2)
    with col1:
        pump_id  = st.text_input("Pump ID:", value=default_id, key="form_pump_id")
        drug_name = st.text_input(
            "Nama Obat:",
            value="Norepinephrine",
            key="form_drug_name",
            help="Ketik nama obat — sistem auto-detect kategori & CDSS code",
        )
        # Preview resolusi obat
        if drug_name:
            info = DrugResolver.resolve(drug_name)
            emoji = DrugResolver.category_emoji(info.category)
            st.caption(
                f"Terdeteksi: {emoji} **{info.category.value}** | "
                f"CDSS: `{info.cdss_code}` | "
                f"{'🔴 KRITIS' if info.critical else '✓ Reguler'}"
            )

        rate_mlh  = st.number_input("Rate (ml/h):", min_value=0.0, value=0.75,
                                     step=0.05, format="%.2f", key="form_rate")
        syringe   = st.selectbox("Ukuran Syringe (ml):", [10, 20, 30, 50], index=3,
                                  key="form_syringe")

    with col2:
        vtbi      = st.number_input("VTBI Sisa (ml):", min_value=0.0, value=1068.0,
                                     key="form_vtbi")
        vol_infus = st.number_input("Volume Terinfus (ml):", min_value=0.0, value=0.0,
                                     key="form_vol")
        line_pres = st.number_input("Line Pressure (mmHg):", min_value=0.0, value=28.0,
                                     key="form_pres")
        run_time  = st.text_input("Run Time (HH:MM:SS):", value="00:00:00", key="form_time")
        status_sel = st.selectbox(
            "Status:", options=[s.value for s in PumpStatus],
            index=0, key="form_status",
        )

    st.markdown("**Optional — Kalkulasi Dose Rate (VIS Score)**")
    oc1, oc2 = st.columns(2)
    with oc1:
        conc = st.number_input("Konsentrasi (mcg/ml):", min_value=0.0, value=0.0,
                                key="form_conc", help="contoh NE 4mg/50ml = 80 mcg/ml")
    with oc2:
        bb   = st.number_input("Berat Badan Pasien (kg):", min_value=0.0, value=0.0,
                                key="form_bb")

    if st.button("💾 Simpan Pump", key="btn_save_pump", type="primary"):
        if not drug_name.strip():
            st.error("Nama obat tidak boleh kosong.")
            return
        status_enum = next(
            (s for s in PumpStatus if s.value == status_sel), PumpStatus.RUNNING
        )
        pump = create_manual_pump(
            pump_id=pump_id.strip(), drug_name=drug_name.strip(),
            rate_mlh=rate_mlh, syringe_size_ml=float(syringe),
            volume_infused_ml=vol_infus, vtbi_ml=vtbi,
            line_pressure_mmhg=line_pres, run_time_hms=run_time,
            status=status_enum, concentration_mcg_ml=conc, patient_weight_kg=bb,
        )
        if connector:
            connector.add_pump_manual(pump)
            st.success(f"✓ {pump.pump_id} [{pump.drug_name}] ditambahkan.")
            st.rerun()
        else:
            # Mode tanpa connector — simpan ke session_state langsung
            key = f"manual_pump_{pump_id}"
            st.session_state[key] = pump
            st.success(f"✓ Tersimpan di session (mode non-real-device).")
            st.rerun()

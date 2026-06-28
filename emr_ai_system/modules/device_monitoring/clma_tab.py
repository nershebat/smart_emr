"""
CLMA Tab — Complete Streamlit UI: CPOE → Farmasi → Scan → 5-Rights → eMAR
============================================================================
Cara integrasi ke 1___Monitor_Device.py:

    from modules.device_monitoring.clma_tab import render_clma_tab

    with tab_clma:
        render_clma_tab(connector, ctx)

Tab ini menampilkan 5 sub-tab:
  📋 CPOE Order    — DPJP input & kalkulasi dosis
  💊 Farmasi       — verifikasi + dispensing + generate barcode
  📱 Scan & Verify — scan pasien + barcode → 5-Rights check + DDI alert
  💉 Administrasi  — konfirmasi pemberian + auto-program pump
  📄 eMAR & Audit  — riwayat administrasi + audit trail
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import streamlit as st

from .clma_models import (
    AlertSeverity, DoseUnit, FrequencyCode, OrderStatus,
    RouteCode, ScanResult,
)
from .clma_engine import CLMAEngine, DDIChecker, DoseCalculator
from .clma_gateway import (
    CLMAStore, CLMAWorkflowManager, HL7PumpCommander,
    BarcodeFactory, init_clma_database,
)


# ── Konstanta UI ──────────────────────────────────────────────────────────────
_HIGH_ALERT_DRUGS = [
    "Norepinephrine", "Epinephrine", "Vasopressin", "Heparin",
    "Alteplase", "KCl", "Nitroprusside", "Insulin", "Milrinone",
]
_COMMON_DRUGS_ICU = [
    "Norepinephrine", "Dopamine", "Dobutamine", "Epinephrine",
    "Vasopressin", "Milrinone", "Levosimendan", "Amiodarone",
    "Heparin", "Furosemide", "Nitroglycerin", "Nitroprusside",
    "Midazolam", "Propofol", "Dexmedetomidine", "Fentanyl",
    "Alteplase", "KCl", "Magnesium Sulfate",
]


def render_clma_tab(connector, ctx: dict) -> None:
    """
    Render lengkap tab 🔄 CLMA.
    connector = RealDeviceConnector (untuk auto-program pump).
    ctx       = dict dari require_cppt_session().
    """
    init_clma_database()

    episode_id   = ctx.get("episode_id", "")
    patient_name = ctx.get("pasien_nama", "-")
    patient_rm   = ctx.get("pasien_no_rm", "-")
    nurse_id     = ctx.get("user_id", "NURSE01")

    # Load orders dari DB ke session
    CLMAWorkflowManager.load_from_db(episode_id)

    st.markdown("## 🔄 Closed Loop Medication Administration (CLMA)")
    st.caption(
        "Pipeline: **CPOE** → **Verifikasi Farmasi** → **Scan & 5-Rights** "
        "→ **Administrasi** → **eMAR** | "
        f"Pasien: **{patient_name}** · RM `{patient_rm}` · Episode `{episode_id}`"
    )

    # ── Status bar aktif orders ───────────────────────────────────────────────
    _render_order_status_bar(episode_id)

    st.divider()

    # ── Sub-tab CLMA ──────────────────────────────────────────────────────────
    ct1, ct2, ct3, ct4, ct5 = st.tabs([
        "📋 CPOE Order",
        "💊 Verifikasi Farmasi",
        "📱 Scan & 5-Rights",
        "💉 Administrasi",
        "📄 eMAR & Audit",
    ])

    with ct1:
        _render_cpoe_tab(episode_id, patient_name, patient_rm, nurse_id)
    with ct2:
        _render_pharmacy_tab(episode_id, nurse_id)
    with ct3:
        _render_scan_tab(episode_id, patient_name, nurse_id, connector)
    with ct4:
        _render_administration_tab(episode_id, nurse_id, connector)
    with ct5:
        _render_emar_tab(episode_id)


# =============================================================================
# Sub-tab 1 — CPOE Order
# =============================================================================

def _render_cpoe_tab(episode_id, patient_name, patient_rm, nurse_id):
    st.subheader("📋 CPOE — Entry Order Obat")

    # ── Guard akses: hanya role dengan permission 'create_cpoe_orders'
    #    (Dokter & Admin, sesuai PERMISSION_MATRIX di modules/auth_system.py)
    #    yang boleh membuat order baru & menghentikan terapi. Role lain
    #    (Perawat, Apoteker, dst.) hanya melihat status read-only —
    #    konsisten dengan akses CPOE resmi di pages/2______CPOE_Dokter.py,
    #    tanpa men-stop seluruh halaman CLMA. ──────────────────────────────
    from modules.auth_system import has_permission, get_auth_context

    auth = get_auth_context()
    is_dokter = has_permission("create_cpoe_orders")

    # ── Daftar Terapi (Aktif / Belum Aktif / Dihentikan) — selalu tampil
    #    untuk semua role, tombol Stop Terapi hanya aktif untuk Dokter. ────
    _render_terapi_list(
        episode_id, can_stop=is_dokter,
        stopped_by=auth.get("user_id", "") or nurse_id,
    )
    st.divider()

    if not is_dokter:
        st.warning(
            "🔒 **Akses terbatas.** Entry order obat baru hanya dapat dilakukan oleh "
            "**Dokter (DPJP)**. "
            f"Role Anda saat ini: **{auth.get('role', '-')}**."
        )
        st.caption(
            "Anda tetap dapat meninjau terapi di atas, atau menindaklanjutinya pada "
            "sub-tab **💊 Verifikasi Farmasi**, **📱 Scan & 5-Rights**, atau "
            "**💉 Administrasi**."
        )
        return

    col_demo, col_blank = st.columns([1, 3])
    with col_demo:
        if st.button("🔬 Demo: Norepinephrine Order", key="btn_demo_order"):
            wf, calc = CLMAEngine.make_demo_order(episode_id, patient_name, 60.0)
            CLMAStore.save_order(wf[0] if isinstance(wf, tuple) else wf)
            # Gunakan create_order path yang tepat
            _order, _calc = CLMAEngine.make_demo_order(episode_id, patient_name, 60.0)
            CLMAStore.save_order(_order)
            from .clma_models import CLMAWorkflowState
            CLMAWorkflowManager._workflows()[_order.order_id] = CLMAWorkflowState(order=_order)
            CLMAWorkflowManager.set_active(_order.order_id)
            st.success(f"✓ Demo order dibuat: {_order.order_id}")
            st.rerun()

    with st.form("form_cpoe", clear_on_submit=False):
        st.markdown("### Identitas Pasien")
        c1, c2, c3 = st.columns(3)
        p_name   = c1.text_input("Nama Pasien", value=patient_name)
        p_rm     = c2.text_input("No. RM", value=patient_rm)
        p_weight = c3.number_input("Berat Badan (kg)", min_value=1.0, value=60.0, step=0.5)

        st.markdown("### Data Obat")
        c1, c2, c3 = st.columns(3)
        drug_name = c1.selectbox("Nama Obat", options=_COMMON_DRUGS_ICU, index=0)
        drug_generic = c2.text_input("Generik / Kandungan", value="Norepinephrine bitartrate")
        drug_class   = c3.text_input("Kelas Obat", value="Vasopressor")

        st.markdown("### Dosis & Rute")
        c1, c2, c3, c4 = st.columns(4)
        dose_val  = c1.number_input("Dosis", min_value=0.0, value=0.1, step=0.01, format="%.3f")
        dose_unit = c2.selectbox("Satuan Dosis", options=[du.value for du in DoseUnit],
                                  index=0)
        route_sel = c3.selectbox("Rute", options=[r.value for r in RouteCode], index=0)
        freq_sel  = c4.selectbox("Frekuensi", options=[f.value for f in FrequencyCode], index=0)

        st.markdown("### Sediaan / Konsentrasi")
        c1, c2, c3, c4 = st.columns(4)
        conc_mcg  = c1.number_input("Konsentrasi (mcg/mL)", min_value=0.0, value=80.0,
                                     help="contoh: 4mg/50mL = 80 mcg/mL")
        conc_mg   = c2.number_input("Konsentrasi (mg/mL)", min_value=0.0, value=0.0,
                                     help="Isi jika satuan mg/h atau mg/kg/h")
        syringe   = c3.selectbox("Ukuran Syringe (mL)", options=[10, 20, 30, 50], index=3)
        diluent   = c4.text_input("Pelarut / Diluent", value="NaCl 0.9%")

        st.markdown("### Pemesan")
        c1, c2 = st.columns(2)
        ordered_by     = c1.text_input("Nama DPJP", value="dr. Budi Santoso, Sp.JP")
        ordered_by_nip = c2.text_input("NIP DPJP", value="198501010001")
        notes          = st.text_area("Catatan", value="Target MAP ≥65 mmHg")

        submitted = st.form_submit_button("📋 Buat Order", type="primary")

    if submitted:
        du_enum = next((du for du in DoseUnit if du.value == dose_unit), DoseUnit.ML_H)
        rt_enum = next((r for r in RouteCode if r.value == route_sel), RouteCode.IV_CONTINUOUS)
        fr_enum = next((f for f in FrequencyCode if f.value == freq_sel), FrequencyCode.CONTINUOUS)

        wf, calc = CLMAWorkflowManager.create_order(
            episode_id=episode_id, patient_name=p_name, patient_no_rm=p_rm,
            weight_kg=p_weight, drug_name=drug_name, drug_generic=drug_generic,
            drug_class=drug_class, dose_value=dose_val, dose_unit=du_enum,
            route=rt_enum, frequency=fr_enum, conc_mcg_ml=conc_mcg,
            conc_mg_ml=conc_mg, syringe_ml=float(syringe), diluent=diluent,
            ordered_by=ordered_by, ordered_by_nip=ordered_by_nip, notes=notes,
        )

        # Tampilkan hasil kalkulasi
        st.success(f"✓ Order **{wf.order.order_id}** berhasil dibuat!")

        if drug_name in _HIGH_ALERT_DRUGS:
            st.error(f"🔴 **HIGH ALERT MEDICATION** — {drug_name} memerlukan double-check!")

        _render_calc_result(calc)

        # DDI preview terhadap pump aktif
        if wf.order.drug_name:
            _preview_ddi(wf.order.drug_name, wf.order.order_id)

        st.rerun()


def _render_calc_result(calc):
    st.markdown("#### 🧮 Hasil Kalkulasi Dosis")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rate Terkalkulasi", f"{calc.rate_ml_h:.2f} ml/h")
        c2.metric("Durasi Syringe", f"{calc.hours_duration:.1f} jam")
        c3.metric("Rentang Aman", calc.safe_range_str)
        c4.metric("Status Dosis",
                   "✓ Dalam Rentang" if calc.is_within_range else "⚠️ Di Luar Rentang",
                   delta=calc.warning if calc.warning else None,
                   delta_color="inverse" if not calc.is_within_range else "off")

        if calc.concentration_mcg_ml > 0 and calc.patient_weight_kg > 0:
            st.caption(
                f"Konsentrasi: {calc.concentration_mcg_ml} mcg/mL | "
                f"BB: {calc.patient_weight_kg} kg | "
                f"Dosis normalized: {calc.dose_mcg_kg_min:.4f} mcg/kg/min"
            )
        if calc.warning:
            st.warning(calc.warning)


def _preview_ddi(drug_name, order_id):
    """Cek DDI terhadap semua pump aktif dari infusion_gateway."""
    try:
        from .infusion_gateway import _DRUG_DB
        # Simulasikan active drugs dari session_state jika ada connector
        active = ["Furosemide", "Midazolam", "Heparin"]  # placeholder
        alerts = DDIChecker.check(drug_name, active, order_id)
        if alerts:
            st.markdown("#### ⚠️ Potensi Interaksi Obat")
            for a in alerts:
                fn = st.error if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH) \
                     else st.warning
                fn(f"{a.display_badge} **{a.perpetrator} ↔ {a.victim}**\n\n"
                   f"_{a.mechanism}_\n\n**Efek:** {a.effect}\n\n**Rekomendasi:** {a.recommendation}")
    except Exception:
        pass


# =============================================================================
# Sub-tab 2 — Farmasi
# =============================================================================

def _render_pharmacy_tab(episode_id, nurse_id):
    st.subheader("💊 Verifikasi Farmasi & Dispensing")

    workflows = CLMAWorkflowManager.get_all()
    pending = [wf for wf in workflows.values()
               if wf.order.episode_id == episode_id
               and wf.order.status == OrderStatus.PENDING]

    if not pending:
        st.info("✓ Tidak ada order menunggu verifikasi farmasi.")
        _show_existing_orders(episode_id)
        return

    for wf in pending:
        order = wf.order
        with st.container(border=True):
            badge = "🔴 HIGH ALERT" if order.is_high_alert else ""
            st.markdown(f"**{order.order_id}** — {order.drug_name} {badge}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Dosis", f"{order.dose_value} {order.dose_unit.value}")
            c2.metric("Rate", f"{order.rate_ml_h:.2f} ml/h")
            c3.metric("Konsentrasi", order.concentration_display)
            c4.metric("Pelarut", order.diluent)
            st.caption(f"Diorder oleh: {order.ordered_by} | {order.ordered_at[:16]}")
            st.caption(f"Catatan: {order.notes}")

            if order.is_double_check_required:
                st.warning("⚠️ Obat ini memerlukan **Double Check** oleh 2 apoteker/perawat.")

            col_a, col_b = st.columns([2, 1])
            with col_a:
                pharmacist_nip  = st.text_input("NIP Apoteker", value="APT001",
                                                 key=f"pharm_nip_{order.order_id}")
                pharmacist_name = st.text_input("Nama Apoteker", value="Apt. Sari, S.Farm",
                                                 key=f"pharm_name_{order.order_id}")
            with col_b:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Verifikasi & Dispensing",
                              key=f"btn_pharm_{order.order_id}", type="primary"):
                    barcode = CLMAWorkflowManager.pharmacy_verify(
                        order.order_id, pharmacist_nip, pharmacist_name
                    )
                    st.success(f"✓ Order diverifikasi! Barcode: **{barcode.barcode_id}**")
                    _render_barcode_label(barcode)
                    st.rerun()


def _render_barcode_label(barcode):
    """Tampilkan label barcode digital yang siap dicetak."""
    exp = datetime.fromisoformat(barcode.expires_at).strftime("%d/%m/%Y %H:%M")
    with st.expander("🏷️ Label Barcode (klik untuk print)", expanded=True):
        st.code(f"""
╔══════════════════════════════════════════╗
║  RSJPDHK — ICCU                         ║
║  MEDICATION LABEL                        ║
╠══════════════════════════════════════════╣
║  Obat    : {barcode.drug_name:<30} ║
║  Generik : {barcode.drug_generic:<30} ║
║  Sediaan : {barcode.concentration_str:<30} ║
║  Dosis   : {barcode.dose_label:<30} ║
║  Rute    : {barcode.route.value:<30} ║
╠══════════════════════════════════════════╣
║  Barcode : {barcode.barcode_id:<30} ║
║  Order   : {barcode.order_id:<30} ║
║  LOT     : {barcode.lot_number:<30} ║
║  Dibuat  : {barcode.prepared_at[:16]:<30} ║
║  Exp     : {exp:<30} ║
║  Oleh    : {barcode.prepared_by:<30} ║
╚══════════════════════════════════════════╝
        """, language="text")
        st.caption("Scan barcode ini dengan scanner atau input manual di tab Scan & 5-Rights")


# =============================================================================
# Sub-tab 3 — Scan & 5-Rights
# =============================================================================

def _render_scan_tab(episode_id, patient_name, nurse_id, connector):
    st.subheader("📱 Scan Barcode & Verifikasi 5+1 Rights")

    # Pilih order yang siap di-scan
    workflows = CLMAWorkflowManager.get_all()
    ready = {oid: wf for oid, wf in workflows.items()
             if wf.order.episode_id == episode_id
             and wf.order.status in (OrderStatus.DISPENSED, OrderStatus.READY)
             and wf.five_rights is None}

    if not ready:
        verified = [wf for wf in workflows.values()
                    if wf.order.episode_id == episode_id and wf.five_rights]
        if verified:
            st.success("✓ Semua order sudah diverifikasi 5-Rights.")
            for wf in verified:
                _render_five_rights_badge(wf.five_rights)
        else:
            st.info("Tidak ada order siap scan. Selesaikan verifikasi farmasi terlebih dahulu.")
        return

    order_choices = {oid: f"{wf.order.drug_name} — {oid}" for oid, wf in ready.items()}
    selected_oid  = st.selectbox("Pilih Order:", options=list(order_choices.keys()),
                                  format_func=lambda x: order_choices[x])
    wf = ready[selected_oid]
    order = wf.order

    st.info(
        f"📦 **{order.drug_name}** | Barcode: `{order.barcode_id}` | "
        f"Rate: **{order.rate_ml_h:.2f} ml/h** | "
        f"{'🔴 HIGH ALERT' if order.is_high_alert else '✓ Regular'}"
    )

    with st.container(border=True):
        st.markdown("#### Scan Input")
        c1, c2 = st.columns(2)
        with c1:
            scanned_patient = st.text_input(
                "📱 Scan Gelang Pasien (Episode ID):",
                value=episode_id, key="scan_patient",
                help="Scanner otomatis isi field ini. Atau ketik Episode ID secara manual.",
            )
        with c2:
            scanned_barcode = st.text_input(
                "📱 Scan Barcode Obat:",
                value=order.barcode_id if order.barcode_id else "",
                key="scan_barcode",
                help="Scan label yang dicetak farmasi.",
            )

        st.markdown("#### Informasi Perawat")
        c1, c2, c3 = st.columns(3)
        nurse_nip    = c1.text_input("NIP Perawat", value=nurse_id, key="scan_nip")
        nurse_name   = c2.text_input("Nama Perawat", value="Rudi Haryanto, S.Kep. Ners.",
                                      key="scan_name")
        allergies_raw = c3.text_input("Alergi Pasien (pisah koma)",
                                       value="", key="scan_allergy",
                                       placeholder="contoh: Penicillin, Aspirin")

        # Active drugs dari infusion_gateway jika connector tersedia
        active_drugs: List[str] = []
        if connector and hasattr(connector, 'get_infusion_pumps'):
            pumps = connector.get_infusion_pumps()
            active_drugs = [p.drug_name for p in pumps if p.is_running]
            if active_drugs:
                st.caption(f"🔌 Obat aktif terdeteksi dari pump: {', '.join(active_drugs)}")

        if st.button("🔍 Verifikasi 5-Rights", key="btn_verify", type="primary"):
            allergies = [a.strip() for a in allergies_raw.split(",") if a.strip()]
            check = CLMAWorkflowManager.scan_and_verify(
                order_id=selected_oid,
                scanned_patient_id=scanned_patient,
                nurse_nip=nurse_nip,
                active_drugs=active_drugs,
                allergies=allergies,
            )
            st.rerun()

    # Tampilkan hasil 5-Rights jika sudah ada
    if wf.five_rights:
        _render_five_rights_result(wf)


def _render_five_rights_result(wf):
    check = wf.five_rights
    st.markdown("---")
    st.markdown("### Hasil Verifikasi 5+1 Rights")

    if check.scan_result == ScanResult.PASS:
        st.success(f"✅ **5+1 RIGHTS PASS** — Score: {check.score}/6 — Siap Administrasi")
    else:
        st.error(f"🚫 **GAGAL** — {check.scan_result.value} — Score: {check.score}/6")

    rights = [
        ("1️⃣ Pasien Benar",    check.right_patient, check.right_patient_note),
        ("2️⃣ Obat Benar",      check.right_drug,    check.right_drug_note),
        ("3️⃣ Dosis Benar",     check.right_dose,    check.right_dose_note),
        ("4️⃣ Rute Benar",      check.right_route,   check.right_route_note),
        ("5️⃣ Waktu Benar",     check.right_time,    check.right_time_note),
        ("6️⃣ Dokumentasi Benar", check.right_doc,   check.right_doc_note),
    ]
    for label, passed, note in rights:
        icon = "✅" if passed else "❌"
        col1, col2 = st.columns([2, 4])
        col1.markdown(f"{icon} **{label}**")
        col2.caption(note)

    # DDI Alerts
    if wf.ddi_alerts:
        st.markdown("---")
        st.markdown("### ⚠️ Drug Interaction Alerts")
        for a in wf.ddi_alerts:
            fn = st.error if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH) \
                 else st.warning
            fn(
                f"{a.display_badge} **{a.perpetrator} ↔ {a.victim}**  \n"
                f"Mekanisme: _{a.mechanism}_  \n"
                f"Efek: {a.effect}  \n"
                f"**Rekomendasi:** {a.recommendation}"
            )

    # Override untuk kondisi emergensi
    if not check.all_pass and not wf.has_critical_ddi:
        st.markdown("---")
        st.warning("⚠️ Terdapat ketidaksesuaian. Untuk kondisi **emergensi ICCU**, "
                   "override dapat dilakukan dengan dokumentasi alasan.")
        with st.expander("🔓 Override 5-Rights (Emergensi)"):
            override_reason = st.text_area("Alasan Override:", key="override_reason")
            double_check_by = st.text_input("NIP Perawat Kedua (Double Check):", key="override_dc")
            if st.button("⚠️ Konfirmasi Override", key="btn_override"):
                if override_reason and double_check_by:
                    check.override_allowed  = True
                    check.override_reason   = override_reason
                    check.double_checked_by = double_check_by
                    CLMAStore.audit(
                        wf.order.episode_id, wf.order.order_id,
                        "5RIGHTS_OVERRIDE", double_check_by, override_reason
                    )
                    st.success("Override dikonfirmasi. Lanjutkan ke tab Administrasi.")
                else:
                    st.error("Alasan dan NIP perawat kedua wajib diisi.")


def _render_five_rights_badge(check):
    icon = "✅" if check.all_pass else "⚠️"
    st.caption(
        f"{icon} Order `{check.order_id}` — "
        f"{check.scan_result.value} — Score {check.score}/6 — "
        f"{check.checked_at[:16]}"
    )


# =============================================================================
# Sub-tab 4 — Administrasi
# =============================================================================

def _render_administration_tab(episode_id, nurse_id, connector):
    st.subheader("💉 Administrasi Obat")

    workflows = CLMAWorkflowManager.get_all()
    administrable = {
        oid: wf for oid, wf in workflows.items()
        if wf.order.episode_id == episode_id
        and wf.can_administer
        and wf.emar is None
    }

    if not administrable:
        done = [wf for wf in workflows.values()
                if wf.order.episode_id == episode_id and wf.emar]
        if done:
            st.success(f"✅ {len(done)} obat sudah diadministrasikan hari ini.")
            for wf in done[:3]:
                st.caption(
                    f"✓ {wf.order.drug_name} | {wf.emar.administered_at[:16]} | "
                    f"Rate: {wf.emar.rate_ml_h_actual:.2f} ml/h | "
                    f"oleh: {wf.emar.administered_by_name}"
                )
        else:
            st.info("Tidak ada obat siap diadministrasikan. Selesaikan verifikasi 5-Rights terlebih dahulu.")
        return

    order_choices = {oid: f"{wf.order.drug_name} — {oid}" for oid, wf in administrable.items()}
    selected_oid  = st.selectbox("Pilih Order:", options=list(order_choices.keys()),
                                  format_func=lambda x: order_choices[x], key="adm_select")
    wf    = administrable[selected_oid]
    order = wf.order

    # Info card
    with st.container(border=True):
        st.markdown(f"### 💉 {order.drug_name}")
        if order.is_high_alert:
            st.error("🔴 **HIGH ALERT MEDICATION** — Konfirmasi identitas pasien sekali lagi!")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rate Order",     f"{order.rate_ml_h:.2f} ml/h")
        c2.metric("Dosis",          f"{order.dose_value} {order.dose_unit.value}")
        c3.metric("Konsentrasi",    order.concentration_display)
        c4.metric("5-Rights Score", f"{wf.five_rights.score}/6 ✅")

    st.markdown("### Detail Pemberian")
    c1, c2 = st.columns(2)
    with c1:
        nurse_nip_adm  = c1.text_input("NIP Perawat", value=nurse_id, key="adm_nip")
        nurse_name_adm = st.text_input("Nama Perawat", value="Rudi Haryanto, S.Kep. Ners.",
                                        key="adm_name")
        rate_actual = st.number_input(
            "Rate Aktual (ml/h):", min_value=0.0, value=order.rate_ml_h,
            step=0.05, format="%.2f", key="adm_rate",
            help="Biasanya sama dengan rate order. Ubah jika ada penyesuaian."
        )
        deviation = abs(rate_actual - order.rate_ml_h)
        if deviation > 0.1:
            st.warning(f"⚠️ Deviasi rate: {deviation:.2f} ml/h dari order. Dokumentasikan alasan.")

    with c2:
        site = st.text_input("Lokasi IV (Site)", value="CVC Lumen Proksimal", key="adm_site")
        witness_nip = st.text_input(
            "NIP Saksi/Double Check", key="adm_witness",
            help="Wajib untuk High Alert Medication",
        )

        # Pump selection
        pump_id = ""
        pump_commander = None
        if connector and hasattr(connector, 'get_infusion_pumps'):
            pumps = connector.get_infusion_pumps()
            pump_options = ["— Tidak Auto-Program —"] + [
                f"{p.pump_id} ({p.drug_name} {p.status.value})" for p in pumps
            ]
            pump_sel = st.selectbox("Target Pump (Auto-Program)", pump_options, key="adm_pump")
            if pump_sel != pump_options[0]:
                pump_id = pump_sel.split(" ")[0]

            # nDS ex connection config
            with st.expander("⚙️ Konfigurasi nDS ex (Auto-Program)"):
                nds_host = st.text_input("IP BeneFusion nDS ex", value="192.168.1.200",
                                          key="nds_host")
                nds_port = st.number_input("Port PCD-03", value=2576, key="nds_port")
                if st.button("📡 Ping nDS ex", key="ping_nds"):
                    pc = HL7PumpCommander(nds_host, int(nds_port))
                    up = pc.ping()
                    (st.success if up else st.error)(
                        f"{'✓ nDS ex online' if up else '✗ nDS ex tidak terjangkau'} "
                        f"({nds_host}:{nds_port})"
                    )
                if pump_id:
                    pump_commander = HL7PumpCommander(nds_host, int(nds_port))

        notes_adm = st.text_area("Catatan Administrasi", key="adm_notes")

    st.markdown("---")
    if order.is_high_alert and not witness_nip:
        st.error("🔴 High Alert Medication memerlukan NIP Saksi/Double Check!")
        return

    col_confirm, col_info = st.columns([1, 2])
    with col_confirm:
        if st.button("✅ KONFIRMASI PEMBERIAN", key="btn_administer",
                      type="primary", use_container_width=True):
            emar = CLMAWorkflowManager.administer(
                order_id=selected_oid,
                nurse_nip=nurse_nip_adm,
                nurse_name=nurse_name_adm,
                rate_actual=rate_actual,
                pump_id=pump_id,
                pump_commander=pump_commander,
                site=site,
                witness_nip=witness_nip,
                notes=notes_adm,
            )
            st.success(
                f"✅ **{order.drug_name}** berhasil diadministrasikan!\n\n"
                f"eMAR ID: `{emar.emar_id}` | "
                f"Rate: {emar.rate_ml_h_actual:.2f} ml/h | "
                f"{'Pump auto-programmed ✓' if emar.pump_programmed else 'Pump manual'}"
            )

            # Push ke CPPT Objective
            pump_ctx = f"\n\nINFUSION ADMINISTERED ({emar.administered_at[:16]}):\n"
            pump_ctx += f"  {order.drug_name} {rate_actual:.2f} ml/h via {order.route.value}\n"
            pump_ctx += f"  Konsentrasi: {order.concentration_display}\n"
            pump_ctx += f"  Site: {site} | eMAR: {emar.emar_id}"
            existing = st.session_state.get("o_text_area", "")
            st.session_state["o_text_area"] = existing + pump_ctx

            st.rerun()

    with col_info:
        if pump_id and pump_commander:
            st.info(
                f"🤖 Pump **{pump_id}** akan di-auto-program via HL7 PCD-03\n"
                f"→ Rate: **{rate_actual:.2f} ml/h** | VTBI: **{order.total_volume_ml:.0f} mL**"
            )


# =============================================================================
# Sub-tab 5 — eMAR & Audit
# =============================================================================

def _render_emar_tab(episode_id):
    st.subheader("📄 eMAR — Electronic Medication Administration Record")

    col1, col2 = st.columns([2, 1])
    with col1:
        hours = st.slider("Tampilkan eMAR (jam terakhir):", 1, 72, 24, key="emar_hours")
    with col2:
        if st.button("🔄 Refresh", key="btn_refresh_emar"):
            st.rerun()

    emar_rows = CLMAStore.get_emar(episode_id, hours=hours)

    if emar_rows:
        import pandas as pd
        df = pd.DataFrame(emar_rows)
        df["administered_at"] = pd.to_datetime(df["administered_at"]).dt.strftime("%d/%m %H:%M")
        df["pump_programmed"] = df["pump_programmed"].apply(lambda x: "✓ Auto" if x else "Manual")
        df["five_rights_score"] = df["five_rights_score"].apply(lambda x: f"{x}/6")

        st.dataframe(
            df[[
                "administered_at", "drug_name", "dose_given", "dose_unit",
                "rate_ml_h_actual", "route", "administered_by_name",
                "five_rights_score", "scan_result", "pump_id", "pump_programmed", "site",
            ]].rename(columns={
                "administered_at": "Waktu",
                "drug_name": "Obat",
                "dose_given": "Dosis",
                "dose_unit": "Satuan",
                "rate_ml_h_actual": "Rate (ml/h)",
                "route": "Rute",
                "administered_by_name": "Perawat",
                "five_rights_score": "5-Rights",
                "scan_result": "Scan",
                "pump_id": "Pump",
                "pump_programmed": "Program",
                "site": "Site",
            }),
            use_container_width=True, hide_index=True,
        )
        st.caption(f"Total {len(emar_rows)} record dalam {hours} jam terakhir")
    else:
        st.info("Belum ada eMAR dalam periode ini.")

    st.divider()
    st.subheader("🔍 Audit Trail CLMA")
    audit_rows = CLMAStore.get_audit(episode_id, limit=30)
    if audit_rows:
        import pandas as pd
        df_a = pd.DataFrame(audit_rows)
        df_a["timestamp"] = pd.to_datetime(df_a["timestamp"]).dt.strftime("%d/%m %H:%M:%S")
        st.dataframe(
            df_a[["timestamp", "action", "performed_by", "order_id", "detail"]].rename(columns={
                "timestamp": "Waktu", "action": "Aksi",
                "performed_by": "Dilakukan Oleh",
                "order_id": "Order ID", "detail": "Detail",
            }),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Belum ada audit trail.")


# =============================================================================
# Helper — order status bar
# =============================================================================

def _render_order_status_bar(episode_id):
    workflows = CLMAWorkflowManager.get_all()
    ep_wf = [wf for wf in workflows.values() if wf.order.episode_id == episode_id]

    if not ep_wf:
        st.caption("Belum ada order aktif untuk episode ini.")
        return

    cols = st.columns(min(len(ep_wf), 5))
    for i, wf in enumerate(ep_wf[:5]):
        with cols[i]:
            stage_emoji = {
                OrderStatus.PENDING:      "⏳",
                OrderStatus.VERIFIED:     "✓",
                OrderStatus.DISPENSED:    "📦",
                OrderStatus.READY:        "📋",
                OrderStatus.ADMINISTERED: "✅",
                OrderStatus.CANCELLED:    "✗",
                OrderStatus.HOLD:         "⏸",
            }.get(wf.order.status, "❓")
            st.metric(
                wf.order.drug_name[:14],
                f"{stage_emoji} {wf.order.status.value[:12]}",
                f"Rate: {wf.order.rate_ml_h:.1f} ml/h",
            )


def _show_existing_orders(episode_id):
    """Tampilkan semua order yang sudah ada, bukan hanya yang pending."""
    workflows = CLMAWorkflowManager.get_all()
    existing = [wf for wf in workflows.values() if wf.order.episode_id == episode_id]
    if existing:
        st.markdown("#### Order Terdaftar")
        for wf in existing:
            st.caption(
                f"📋 `{wf.order.order_id}` — **{wf.order.drug_name}** "
                f"| {wf.order.status.value} | {wf.current_stage}"
            )


# ── Pengelompokan status order untuk tampilan Terapi List ─────────────────────
_STATUS_AKTIF = (OrderStatus.VERIFIED, OrderStatus.DISPENSED,
                 OrderStatus.READY, OrderStatus.ADMINISTERED)
_STATUS_DIHENTIKAN = (OrderStatus.CANCELLED, OrderStatus.COMPLETED)
# Sisanya (DRAFT, PENDING, HOLD) dianggap "Belum Aktif" — order sudah dibuat
# tapi belum berjalan/dipakai (masih menunggu farmasi atau ditahan).


def _render_terapi_list(episode_id: str, can_stop: bool, stopped_by: str = "") -> None:
    """
    Tampilkan daftar terapi/order obat episode ini, dikelompokkan menjadi:
      🟢 Terapi Aktif      — Verified / Dispensed / Ready / Administered
      🟡 Belum Aktif       — Draft / Pending / Hold (belum berjalan)
      ⚪ Terapi Dihentikan — Cancelled / Completed

    `can_stop`   : True jika user (Dokter) boleh menekan tombol "⏹ Stop Terapi"
                   pada baris Terapi Aktif.
    `stopped_by` : NIP/ID user yang menghentikan, dicatat ke audit log & kolom
                   administered_by sebagai jejak siapa yang menghentikan.
    """
    workflows = CLMAWorkflowManager.get_all()
    existing = [wf for wf in workflows.values() if wf.order.episode_id == episode_id]

    if not existing:
        st.caption("Belum ada order/terapi untuk episode ini.")
        return

    aktif      = [wf for wf in existing if wf.order.status in _STATUS_AKTIF]
    dihentikan = [wf for wf in existing if wf.order.status in _STATUS_DIHENTIKAN]
    belum_aktif = [wf for wf in existing if wf not in aktif and wf not in dihentikan]

    # ── 🟢 Terapi Aktif ─────────────────────────────────────────────────────
    st.markdown("#### 🟢 Terapi Aktif")
    if not aktif:
        st.caption("Tidak ada terapi aktif saat ini.")
    for wf in aktif:
        o = wf.order
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"📋 `{o.order_id}` — **{o.drug_name}** ({o.drug_generic}) "
                f"| {o.dose_value} {o.dose_unit.value} via {o.route.value}\n\n"
                f"_Status: {o.status.value} · {wf.current_stage}_"
            )
        with col_btn:
            if can_stop:
                if st.button("⏹ Stop Terapi", key=f"stop_{o.order_id}",
                              use_container_width=True):
                    now_iso = datetime.now().isoformat()
                    by_value = stopped_by or o.ordered_by
                    CLMAStore.update_order_status(
                        o.order_id, OrderStatus.COMPLETED,
                        by_field="administered_by", by_value=by_value,
                        at_field="administered_at", at_value=now_iso,
                    )
                    CLMAStore.audit(
                        episode_id, o.order_id, "THERAPY_STOPPED", by_value,
                        f"Terapi {o.drug_name} dihentikan via CLMA CPOE Order.",
                    )
                    # Sinkronkan juga objek in-memory agar langsung
                    # terpencerminkan tanpa perlu reload dari DB.
                    o.status = OrderStatus.COMPLETED
                    o.administered_by = by_value
                    o.administered_at = now_iso
                    st.toast(f"⏹ Terapi {o.drug_name} dihentikan.", icon="⏹")
                    st.rerun()
        st.divider()

    # ── 🟡 Belum Aktif ──────────────────────────────────────────────────────
    if belum_aktif:
        st.markdown("#### 🟡 Belum Aktif")
        st.caption("Order sudah dibuat, masih menunggu verifikasi farmasi / ditahan.")
        for wf in belum_aktif:
            o = wf.order
            st.caption(
                f"📋 `{o.order_id}` — **{o.drug_name}** | {o.status.value} | {wf.current_stage}"
            )
        st.divider()

    # ── ⚪ Terapi Dihentikan ────────────────────────────────────────────────
    if dihentikan:
        with st.expander(f"⚪ Terapi Dihentikan ({len(dihentikan)})", expanded=False):
            for wf in dihentikan:
                o = wf.order
                st.caption(
                    f"📋 `{o.order_id}` — **{o.drug_name}** | {o.status.value} "
                    f"| Dihentikan oleh: {o.administered_by or '-'} "
                    f"pada {o.administered_at or '-'}"
                )

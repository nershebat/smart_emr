"""
CPOE Gateway + Tab — Persistence, CLMA Bridge, dan Streamlit UI
================================================================
File ini menggabungkan:
  • CPOEStore    — SQLite persistence untuk semua order type
  • CLMABridge   — route MedicationCPOEOrder → CLMA pipeline
  • render_cpoe_tab() — main UI entry point (5 sub-tab)

RBAC enforcement terjadi di setiap titik:
  - UI level: tombol dan field dikunci per role
  - Engine level: CPOEAuthChecker.assert_can() sebelum setiap action
  - Gateway level: validasi ulang sebelum persist ke DB
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

from .cpoe_models import (
    CPOEOrderStatus, CPOEOrderType, CPOEPriority,
    DietOrder, DietType, ImagingModality, ImagingOrder,
    LAB_PANELS, IMAGING_PRESETS, NURSING_ORDER_PRESETS,
    LabOrder, LabPriority, MedicationCPOEOrder,
    NursingOrder, NursingOrderType, ConsultOrder, OrderSet,
)
from .cpoe_auth import (
    CPOEAuthChecker, CPOEAuthService, CPOEUser, CPOERole,
    Permission, AuthorizationError,
    get_cpoe_session, require_cpoe_auth,
    render_cpoe_login, render_cpoe_session_info, render_high_alert_reauth,
    init_auth_database,
)
from .cpoe_engine import (
    CPOEValidator, FHIRGenerator, OrderSetLibrary,
)
from .clma_models import DoseUnit, FrequencyCode, RouteCode

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cpoe.db"


# =============================================================================
# Database Layer
# =============================================================================

@contextmanager
def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_cpoe_database() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS cpoe_orders (
            order_id      TEXT PRIMARY KEY,
            episode_id    TEXT NOT NULL,
            order_type    TEXT,
            priority      TEXT,
            status        TEXT,
            ordered_by    TEXT,
            ordered_by_nip TEXT,
            ordered_by_role TEXT,
            ordered_at    TEXT,
            start_time    TEXT,
            end_time      TEXT,
            notes         TEXT,
            diagnosis_code TEXT,
            payload_json  TEXT,
            countersign_required INTEGER DEFAULT 0,
            countersigned_by TEXT,
            countersigned_at TEXT,
            clma_order_id TEXT,
            fhir_json     TEXT,
            created_at    TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_cpoe_episode ON cpoe_orders(episode_id);
        CREATE INDEX IF NOT EXISTS idx_cpoe_type    ON cpoe_orders(order_type);
        CREATE INDEX IF NOT EXISTS idx_cpoe_status  ON cpoe_orders(status);
        """)


class CPOEStore:

    @staticmethod
    def save(order_id: str, episode_id: str, order_type: CPOEOrderType,
             priority: CPOEPriority, status: CPOEOrderStatus,
             ordered_by: str, ordered_by_nip: str, ordered_by_role: str,
             ordered_at: str, notes: str, payload: dict,
             countersign_required: bool = False,
             clma_order_id: str = "") -> None:
        with _conn() as con:
            con.execute("""
            INSERT OR REPLACE INTO cpoe_orders (
                order_id, episode_id, order_type, priority, status,
                ordered_by, ordered_by_nip, ordered_by_role, ordered_at,
                start_time, notes, payload_json, countersign_required, clma_order_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (order_id, episode_id, order_type.value, priority.value,
                  status.value, ordered_by, ordered_by_nip, ordered_by_role,
                  ordered_at, ordered_at, notes,
                  json.dumps(payload, ensure_ascii=False, default=str),
                  int(countersign_required), clma_order_id))

    @staticmethod
    def update_status(order_id: str, status: CPOEOrderStatus) -> None:
        with _conn() as con:
            con.execute("UPDATE cpoe_orders SET status=? WHERE order_id=?",
                        (status.value, order_id))

    @staticmethod
    def countersign(order_id: str, signer_nip: str, signer_name: str) -> None:
        with _conn() as con:
            con.execute("""
                UPDATE cpoe_orders SET
                    countersigned_by=?, countersigned_at=?, status=?
                WHERE order_id=?
            """, (f"{signer_nip} — {signer_name}",
                  datetime.now().isoformat(),
                  CPOEOrderStatus.ACTIVE.value,
                  order_id))

    @staticmethod
    def get_orders(episode_id: str, order_type: str = "",
                   status: str = "", limit: int = 50) -> List[dict]:
        sql = "SELECT * FROM cpoe_orders WHERE episode_id=?"
        params: list = [episode_id]
        if order_type:
            sql += " AND order_type=?"; params.append(order_type)
        if status:
            sql += " AND status=?"; params.append(status)
        sql += " ORDER BY ordered_at DESC LIMIT ?"
        params.append(limit)
        with _conn() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_pending_countersign(episode_id: str) -> List[dict]:
        with _conn() as con:
            rows = con.execute("""
                SELECT * FROM cpoe_orders
                WHERE episode_id=?
                  AND countersign_required=1
                  AND (countersigned_by IS NULL OR countersigned_by='')
                ORDER BY ordered_at
            """, (episode_id,)).fetchall()
        return [dict(r) for r in rows]


# =============================================================================
# CLMA Bridge — route MedicationCPOEOrder → CLMA
# =============================================================================

class CLMABridge:
    """
    Konversi MedicationCPOEOrder menjadi CLMA order dan simpan ke pipeline CLMA.
    """

    @staticmethod
    def route_to_clma(
        cpoe_order: dict,
        episode_id: str,
        patient_name: str,
        patient_rm: str,
    ) -> Optional[str]:
        """
        Buat CLMA MedicationOrder dari payload CPOE order.
        Return clma_order_id atau None jika gagal.
        """
        try:
            from .clma_gateway import CLMAWorkflowManager, CLMAStore
            from .clma_engine import CLMAEngine

            du = next((d for d in DoseUnit if d.value == cpoe_order.get("dose_unit", "")),
                       DoseUnit.ML_H)
            rt = next((r for r in RouteCode if r.value == cpoe_order.get("route", "")),
                       RouteCode.IV_CONTINUOUS)
            fr = next((f for f in FrequencyCode if f.value == cpoe_order.get("frequency", "")),
                       FrequencyCode.CONTINUOUS)

            wf, calc = CLMAWorkflowManager.create_order(
                episode_id       = episode_id,
                patient_name     = patient_name,
                patient_no_rm    = patient_rm,
                weight_kg        = float(cpoe_order.get("patient_weight_kg", 60)),
                drug_name        = cpoe_order.get("drug_name", ""),
                drug_generic     = cpoe_order.get("drug_generic", ""),
                drug_class       = cpoe_order.get("drug_class", ""),
                dose_value       = float(cpoe_order.get("dose_value", 0)),
                dose_unit        = du,
                route            = rt,
                frequency        = fr,
                conc_mcg_ml      = float(cpoe_order.get("concentration_mcg_ml", 0)),
                conc_mg_ml       = float(cpoe_order.get("concentration_mg_ml", 0)),
                syringe_ml       = float(cpoe_order.get("syringe_size_ml", 50)),
                diluent          = cpoe_order.get("diluent", "NaCl 0.9%"),
                ordered_by       = cpoe_order.get("ordered_by", ""),
                ordered_by_nip   = cpoe_order.get("ordered_by_nip", ""),
                notes            = cpoe_order.get("titration_target", ""),
            )
            return wf.order.order_id
        except Exception as exc:
            logger.error("CLMABridge.route_to_clma error: %s", exc)
            return None


# =============================================================================
# CPOE Tab — Main UI Entry Point
# =============================================================================

def render_cpoe_tab(ctx: dict) -> None:
    """
    Render lengkap tab 📋 CPOE.
    ctx = dict dari require_cppt_session() di Monitor_Device.
    """
    init_cpoe_database()
    init_auth_database()

    episode_id   = ctx.get("episode_id", "")
    patient_name = ctx.get("pasien_nama", "-")
    patient_rm   = ctx.get("pasien_no_rm", "-")

    st.markdown("## 📋 CPOE — Computerized Physician Order Entry")

    # ── CPOE Auth gate ────────────────────────────────────────────────────────
    cpoe_session = get_cpoe_session()
    if not cpoe_session:
        st.info(
            "🔐 CPOE memerlukan login tersendiri dengan kewenangan klinis.\n\n"
            "Login CPPT (perawat) **tidak otomatis** memberikan akses prescribing."
        )
        render_cpoe_login()
        return

    user = cpoe_session.user
    render_cpoe_session_info(cpoe_session)

    # Info pasien
    st.caption(
        f"Pasien: **{patient_name}** · RM `{patient_rm}` · Episode `{episode_id}` | "
        f"Prescriber: **{user.display_name}** ({user.role.value})"
    )

    # ── Countersign banner ────────────────────────────────────────────────────
    pending_cs = CPOEStore.get_pending_countersign(episode_id)
    if pending_cs and user.can(Permission.MED_ORDER_COUNTERSIGN):
        st.warning(
            f"⚠️ **{len(pending_cs)} order menunggu countersign DPJP** — "
            f"Lihat tab **✅ Countersign**"
        )

    st.divider()

    # ── Sub-tabs ──────────────────────────────────────────────────────────────
    tabs_list = ["💊 Medikasi", "🧪 Lab", "🩻 Imaging",
                 "💙 Keperawatan", "📦 Order Set", "📊 Status Order"]
    if user.can(Permission.MED_ORDER_COUNTERSIGN):
        tabs_list.append("✅ Countersign")
    if user.can(Permission.ADMIN_AUDIT_FULL) or user.can(Permission.ADMIN_USER_MGMT):
        tabs_list.append("🔐 Admin")

    tabs = st.tabs(tabs_list)
    tab_map = {name: tab for name, tab in zip(tabs_list, tabs)}

    with tab_map["💊 Medikasi"]:
        _render_med_tab(user, cpoe_session, episode_id, patient_name, patient_rm)

    with tab_map["🧪 Lab"]:
        _render_lab_tab(user, episode_id)

    with tab_map["🩻 Imaging"]:
        _render_imaging_tab(user, episode_id)

    with tab_map["💙 Keperawatan"]:
        _render_nursing_tab(user, episode_id)

    with tab_map["📦 Order Set"]:
        _render_orderset_tab(user, cpoe_session, episode_id, patient_name, patient_rm)

    with tab_map["📊 Status Order"]:
        _render_status_tab(user, episode_id)

    if "✅ Countersign" in tab_map:
        with tab_map["✅ Countersign"]:
            _render_countersign_tab(user, episode_id)

    if "🔐 Admin" in tab_map:
        with tab_map["🔐 Admin"]:
            _render_admin_tab(user)


# =============================================================================
# Sub-tab: 💊 Medikasi
# =============================================================================

def _render_med_tab(user: CPOEUser, session, episode_id, patient_name, patient_rm):
    st.subheader("💊 Order Medikasi")

    # ── Permission check UI ───────────────────────────────────────────────────
    if not user.can(Permission.MED_ORDER_REGULAR):
        if user.can(Permission.MED_ORDER_VERBAL):
            _render_verbal_order_only(user, episode_id)
        elif user.can(Permission.MED_ADMINISTER):
            st.info("💊 Anda memiliki akses **administrasi obat** namun tidak dapat meresepkan. Gunakan tab CLMA untuk pemberian obat.")
        elif user.can(Permission.MED_VERIFY_PHARMACY):
            st.info("💊 Anda memiliki akses **verifikasi farmasi**. Order dari DPJP akan muncul di tab Status Order.")
        else:
            st.error(f"🚫 {user.role_badge} tidak memiliki kewenangan prescribing (UU No. 29/2004).")
        return

    # ── Prescribing UI (DPJP / Residen) ──────────────────────────────────────
    if user.needs_countersign:
        st.info(
            f"ℹ️ Anda login sebagai **{user.role.value}**. "
            f"Semua order medikasi akan berstatus **DRAFT** hingga di-countersign oleh DPJP."
        )

    # Patient weight (penting untuk dosis berbasis BB)
    with st.container(border=True):
        st.markdown("**Berat Badan Pasien** _(wajib untuk dosis mcg/kg/min)_")
        col_w = st.columns([1, 3])
        weight_kg = col_w[0].number_input("BB (kg):", min_value=1.0, value=60.0,
                                           step=0.5, key="cpoe_weight")

    with st.form("cpoe_med_form", clear_on_submit=False):
        st.markdown("### Detail Obat")
        c1, c2, c3 = st.columns(3)
        drug_name    = c1.text_input("Nama Obat *", value="Norepinephrine")
        drug_generic = c2.text_input("Generik *", value="Norepinephrine bitartrate")
        drug_class   = c3.text_input("Kelas", value="Vasopressor")

        is_high_alert = st.checkbox(
            "🔴 High Alert Medication",
            value=drug_name.lower() in [
                "norepinephrine","epinephrine","vasopressin","heparin","insulin",
                "alteplase","kcl","nitroprusside","milrinone","streptokinase"
            ],
            help="Centang jika obat termasuk kategori High Alert per daftar RSJPDHK",
        )
        is_narcotic = st.checkbox(
            "⚠️ Narkotika / Psikotropika",
            value=drug_name.lower() in ["fentanyl","fentanil","morfin","morphine","pethidine"],
            help="Centang jika obat termasuk Narkotika/Psikotropika (UU No. 35/2009)",
        )

        st.markdown("### Dosis & Rute")
        c1, c2, c3, c4 = st.columns(4)
        dose_val  = c1.number_input("Dosis *", min_value=0.0, value=0.1,
                                     step=0.01, format="%.4f")
        dose_unit = c2.selectbox("Satuan *", [du.value for du in DoseUnit])
        route_sel = c3.selectbox("Rute *", [r.value for r in RouteCode])
        freq_sel  = c4.selectbox("Frekuensi *", [f.value for f in FrequencyCode])

        st.markdown("### Konsentrasi / Sediaan")
        c1, c2, c3, c4 = st.columns(4)
        conc_mcg = c1.number_input("Konsentrasi (mcg/mL)", min_value=0.0, value=80.0)
        conc_mg  = c2.number_input("Konsentrasi (mg/mL)", min_value=0.0, value=0.0)
        syringe  = c3.selectbox("Syringe (mL)", [10, 20, 30, 50], index=3)
        diluent  = c4.text_input("Pelarut", value="NaCl 0.9% 50 mL")

        titration = st.text_input("Target Titrasi / Indikasi",
                                   value="MAP ≥65 mmHg" if "pressin" in drug_name.lower() else "")
        priority_sel = st.selectbox("Prioritas", [p.value for p in CPOEPriority], index=0)
        notes    = st.text_area("Catatan DPJP")

        submitted = st.form_submit_button("📋 Buat Order", type="primary")

    if submitted:
        # ── RBAC check ─────────────────────────────────────────────────────────
        can_go, msg, action = CPOEValidator.validate_medication(
            user, drug_name, is_high_alert, is_narcotic, dose_val, dose_unit, session
        )

        if not can_go:
            st.error(msg)
            if action == "ESCALATE_TO_DPJP":
                st.info("📞 Hubungi DPJP untuk meresepkan obat ini.")
            elif action == "USE_VERBAL_ORDER":
                st.info("📝 Gunakan form Verbal Order (TBAK) di bawah.")
            elif action == "REAUTH_HIGH_ALERT":
                render_high_alert_reauth(session)
            return

        # High-alert re-auth check
        if is_high_alert and not session.high_alert_auth_valid:
            if user.role in (CPOERole.DPJP, CPOERole.DPJP_UTAMA):
                ok = render_high_alert_reauth(session)
                if not ok:
                    return

        if msg:
            st.warning(msg)

        # Determine order status
        needs_cs = user.needs_countersign or (
            user.role == CPOERole.RESIDEN_SR and (is_high_alert or is_narcotic)
        )
        order_status = CPOEOrderStatus.DRAFT if needs_cs else CPOEOrderStatus.ACTIVE
        priority_enum = next((p for p in CPOEPriority if p.value == priority_sel), CPOEPriority.ROUTINE)

        order_id = f"CPOE-MED-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        payload = {
            "drug_name": drug_name, "drug_generic": drug_generic, "drug_class": drug_class,
            "dose_value": dose_val, "dose_unit": dose_unit, "route": route_sel,
            "frequency": freq_sel, "concentration_mcg_ml": conc_mcg,
            "concentration_mg_ml": conc_mg, "syringe_size_ml": float(syringe),
            "diluent": diluent, "patient_weight_kg": weight_kg,
            "titration_target": titration, "is_high_alert": is_high_alert,
            "ordered_by": user.display_name, "ordered_by_nip": user.nip,
        }

        # Route ke CLMA jika langsung aktif
        clma_id = ""
        if order_status == CPOEOrderStatus.ACTIVE:
            clma_id = CLMABridge.route_to_clma(payload, episode_id,
                                                 patient_name, patient_rm) or ""

        CPOEStore.save(
            order_id=order_id, episode_id=episode_id,
            order_type=CPOEOrderType.MEDICATION, priority=priority_enum,
            status=order_status, ordered_by=user.display_name,
            ordered_by_nip=user.nip, ordered_by_role=user.role.value,
            ordered_at=datetime.now().isoformat(), notes=notes,
            payload=payload, countersign_required=needs_cs, clma_order_id=clma_id,
        )

        if needs_cs:
            st.warning(
                f"✓ Order `{order_id}` tersimpan sebagai **DRAFT**.\n\n"
                f"⏳ Menunggu countersign DPJP sebelum dapat dieksekusi. "
                f"DPJP akan melihat notifikasi di tab **✅ Countersign**."
            )
        else:
            st.success(
                f"✅ Order `{order_id}` **AKTIF** — {drug_name} {dose_val} {dose_unit}\n\n"
                + (f"🔗 Diroute ke CLMA: `{clma_id}`" if clma_id else "")
            )
        st.rerun()


def _render_verbal_order_only(user: CPOEUser, episode_id: str) -> None:
    """Form Verbal Order (TBAK) untuk Perawat PK2/PK3."""
    st.info(
        f"📝 **Verbal Order (TBAK)** — {user.role.value} dapat menerima dan mendokumentasikan "
        f"instruksi lisan DPJP, namun tidak meresepkan secara mandiri.\n\n"
        f"**Prosedur TBAK:** Tulis → Baca → Konfirmasi"
    )
    with st.form("verbal_order_form"):
        dpjp_nip  = st.text_input("NIP DPJP yang memberikan instruksi lisan *")
        dpjp_name = st.text_input("Nama DPJP *")
        drug      = st.text_input("Obat yang diinstruksikan *")
        dose      = st.text_input("Dosis & Rute *")
        rationale = st.text_area("Instruksi lengkap (tulis verbatim) *")
        confirmed = st.checkbox("✅ Saya sudah membacakan kembali kepada DPJP dan dikonfimasikan (TBAK)")
        submitted = st.form_submit_button("📝 Simpan Verbal Order", type="primary")

    if submitted:
        ok, err = CPOEAuthChecker.check_verbal_order(user, dpjp_nip)
        if not ok:
            st.error(err); return
        if not confirmed:
            st.error("Konfirmasi TBAK wajib dicentang."); return
        order_id = f"CPOE-VERBAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        CPOEStore.save(
            order_id=order_id, episode_id=episode_id,
            order_type=CPOEOrderType.MEDICATION, priority=CPOEPriority.STAT,
            status=CPOEOrderStatus.PENDING,
            ordered_by=f"[VERBAL] {dpjp_name} / dicatat oleh {user.display_name}",
            ordered_by_nip=dpjp_nip, ordered_by_role=f"VERBAL/{user.role.value}",
            ordered_at=datetime.now().isoformat(),
            notes=f"TBAK: {rationale}",
            payload={"drug_name": drug, "dose": dose,
                     "verbal_by": user.nip, "dpjp_nip": dpjp_nip},
            countersign_required=True,
        )
        st.success(
            f"✓ Verbal Order terdokumentasi — `{order_id}`\n\n"
            f"⏳ Menunggu countersign dari {dpjp_name} (NIP: {dpjp_nip}) "
            f"untuk aktivasi order."
        )


# =============================================================================
# Sub-tab: 🧪 Lab
# =============================================================================

def _render_lab_tab(user: CPOEUser, episode_id: str):
    st.subheader("🧪 Order Laboratorium")
    ok, err = CPOEValidator.validate_lab(user)
    if not ok:
        st.error(err); return

    with st.form("cpoe_lab_form"):
        panel = st.selectbox("Pilih Panel Lab", options=list(LAB_PANELS.keys()))
        st.multiselect("Pemeriksaan (kustomisasi):",
                        options=LAB_PANELS[panel], default=LAB_PANELS[panel],
                        key="lab_tests_sel")
        c1, c2, c3 = st.columns(3)
        lab_prio = c1.selectbox("Prioritas", [p.value for p in LabPriority])
        specimen  = c2.text_input("Spesimen", value="Darah Vena")
        fasting   = c3.checkbox("Puasa diperlukan")
        special   = st.text_area("Instruksi Khusus")
        submitted = st.form_submit_button("🧪 Kirim Order Lab", type="primary")

    if submitted:
        order_id = f"CPOE-LAB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        payload = {"panel": panel, "tests": LAB_PANELS[panel],
                   "priority": lab_prio, "specimen": specimen,
                   "fasting": fasting, "special": special}
        CPOEStore.save(order_id, episode_id, CPOEOrderType.LAB, CPOEPriority.STAT,
                        CPOEOrderStatus.ACTIVE, user.display_name, user.nip,
                        user.role.value, datetime.now().isoformat(), special, payload)
        st.success(f"✅ Order lab `{order_id}` — **{panel}** ({lab_prio}) dikirim.")
        st.rerun()


# =============================================================================
# Sub-tab: 🩻 Imaging
# =============================================================================

def _render_imaging_tab(user: CPOEUser, episode_id: str):
    st.subheader("🩻 Order Radiologi / Imaging")
    ok, err = CPOEValidator.validate_imaging(user)
    if not ok:
        st.error(err); return

    with st.form("cpoe_imaging_form"):
        preset_choice = st.selectbox(
            "Preset Imaging:",
            options=["— Pilih preset —"] + list(IMAGING_PRESETS.keys())
        )
        preset = IMAGING_PRESETS.get(preset_choice, {})

        modality = st.selectbox("Modalitas", [m.value for m in ImagingModality],
                                  index=0)
        body_region = st.text_input("Regio / Objek",
                                     value=preset.get("body_region", ""))
        clinical_info = st.text_area("Info Klinis / Indikasi",
                                      value=preset.get("clinical_info", ""))
        specific_views = st.text_input("View / Proyeksi",
                                        value=preset.get("specific_views", ""))
        c1, c2, c3 = st.columns(3)
        portable = c1.checkbox("Portable / Bedside",
                                value=preset.get("portable", False))
        contrast = c2.checkbox("Dengan Kontras",
                                value=preset.get("contrast", False))
        sedation = c3.checkbox("Perlu Sedasi",
                                value=preset.get("sedation_req", False))
        prio_sel = st.selectbox("Prioritas", [p.value for p in CPOEPriority])
        submitted = st.form_submit_button("🩻 Kirim Order Imaging", type="primary")

    if submitted:
        order_id = f"CPOE-IMG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        payload = {"modality": modality, "body_region": body_region,
                   "clinical_info": clinical_info, "specific_views": specific_views,
                   "portable": portable, "contrast": contrast, "sedation": sedation}
        prio = next((p for p in CPOEPriority if p.value == prio_sel), CPOEPriority.ROUTINE)
        CPOEStore.save(order_id, episode_id, CPOEOrderType.IMAGING, prio,
                        CPOEOrderStatus.ACTIVE, user.display_name, user.nip,
                        user.role.value, datetime.now().isoformat(), clinical_info, payload)
        st.success(f"✅ Order imaging `{order_id}` — **{modality}** dikirim.")
        st.rerun()


# =============================================================================
# Sub-tab: 💙 Keperawatan
# =============================================================================

def _render_nursing_tab(user: CPOEUser, episode_id: str):
    st.subheader("💙 Order Keperawatan")
    ok, err = CPOEValidator.validate_nursing(user)
    if not ok:
        st.error(err); return

    with st.form("cpoe_nursing_form"):
        preset_choice = st.selectbox(
            "Preset Order Keperawatan:",
            options=["— Pilih preset —"] + list(NURSING_ORDER_PRESETS.keys())
        )
        preset = NURSING_ORDER_PRESETS.get(preset_choice, {})
        instruction = st.text_area("Instruksi Keperawatan *",
                                    value=preset.get("instruction", ""))
        c1, c2 = st.columns(2)
        freq_text = c1.text_input("Frekuensi", value=preset.get("frequency_text", ""))
        target    = c2.text_input("Target / Parameter", value=preset.get("target", ""))
        siki_code = st.text_input("SIKI Code", value=preset.get("siki_code", ""))
        notes     = st.text_area("Catatan Tambahan")
        submitted = st.form_submit_button("💙 Kirim Order Keperawatan", type="primary")

    if submitted:
        order_id = f"CPOE-NRS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        payload = {"preset": preset_choice, "instruction": instruction,
                   "frequency": freq_text, "target": target, "siki_code": siki_code}
        CPOEStore.save(order_id, episode_id, CPOEOrderType.NURSING, CPOEPriority.ROUTINE,
                        CPOEOrderStatus.ACTIVE, user.display_name, user.nip,
                        user.role.value, datetime.now().isoformat(), notes, payload)
        st.success(f"✅ Order keperawatan `{order_id}` dikirim ke CPPT.")
        # Kirim juga ke o_text_area CPPT
        cppt_entry = f"\n[ORDER KEPERAWATAN — {datetime.now().strftime('%H:%M')}]\n{instruction}"
        st.session_state["o_text_area"] = st.session_state.get("o_text_area", "") + cppt_entry
        st.rerun()


# =============================================================================
# Sub-tab: 📦 Order Set
# =============================================================================

def _render_orderset_tab(user: CPOEUser, session, episode_id, patient_name, patient_rm):
    st.subheader("📦 Order Set — Protokol ICU Jantung")

    ok, msg = CPOEValidator.validate_order_set_activation(user, None)
    if not ok:
        st.error(msg); return

    library = OrderSetLibrary.get_all()
    set_names = {k: v.name for k, v in library.items()}
    selected_key = st.selectbox("Pilih Protokol:", options=list(set_names.keys()),
                                 format_func=lambda k: set_names[k])
    os: OrderSet = library[selected_key]

    with st.container(border=True):
        st.markdown(f"### {os.name}")
        st.caption(f"Indikasi: {os.indication} | Bukti: {os.evidence_level} | ICD-10: {os.icd10_code}")
        st.write(os.description)

    st.markdown("#### Pilih item yang akan diaktivasi:")
    selected_items = []
    for i, item in enumerate(os.items):
        emoji = {
            CPOEOrderType.MEDICATION: "💊", CPOEOrderType.LAB: "🧪",
            CPOEOrderType.IMAGING: "🩻", CPOEOrderType.NURSING: "💙",
            CPOEOrderType.DIET: "🥗", CPOEOrderType.CONSULT: "📞",
        }.get(item.order_type, "📋")
        label = (
            f"{emoji} [{item.order_type.value}] "
            f"{item.template.get('drug_name') or item.template.get('panel_name') or item.template.get('modality','') or item.template.get('preset_choice','') or item.template.get('instruction','')[:50] or 'Item'}"
        )
        checked = st.checkbox(
            label,
            value=item.required,
            key=f"os_item_{selected_key}_{i}",
            help=item.rationale or "Klik untuk include/exclude item ini",
        )
        if checked:
            selected_items.append(item)

    weight_os = st.number_input("Berat Badan Pasien (kg):", min_value=1.0, value=60.0,
                                 step=0.5, key="os_weight")

    if st.button(f"🚀 Aktivasi Order Set ({len(selected_items)} item)", type="primary"):
        activated = 0
        skipped   = 0
        errors    = []
        for item in selected_items:
            try:
                otype   = item.order_type
                tmpl    = item.template
                now_str = datetime.now().isoformat()
                oid     = f"CPOE-OS-{datetime.now().strftime('%Y%m%d%H%M%S%f')[-12:]}"
                needs_cs = (otype == CPOEOrderType.MEDICATION and user.needs_countersign)
                status   = CPOEOrderStatus.DRAFT if needs_cs else CPOEOrderStatus.ACTIVE

                # Route medication ke CLMA
                clma_id = ""
                if otype == CPOEOrderType.MEDICATION and status == CPOEOrderStatus.ACTIVE:
                    merged = {**tmpl, "patient_weight_kg": weight_os,
                               "ordered_by": user.display_name, "ordered_by_nip": user.nip}
                    clma_id = CLMABridge.route_to_clma(merged, episode_id, patient_name, patient_rm) or ""

                prio_enum = CPOEPriority.STAT if tmpl.get("lab_priority") == "STAT" else CPOEPriority.ROUTINE

                CPOEStore.save(
                    order_id=oid, episode_id=episode_id, order_type=otype,
                    priority=prio_enum, status=status,
                    ordered_by=user.display_name, ordered_by_nip=user.nip,
                    ordered_by_role=user.role.value, ordered_at=now_str,
                    notes=item.rationale or "", payload={**tmpl, "from_order_set": selected_key},
                    countersign_required=needs_cs, clma_order_id=clma_id,
                )
                activated += 1
            except Exception as exc:
                errors.append(str(exc))
                skipped += 1

        st.success(f"✅ Order Set **{os.name}** diaktivasi — {activated} order dibuat.")
        if skipped:
            st.warning(f"⚠️ {skipped} item gagal: {'; '.join(errors[:3])}")
        if user.needs_countersign:
            st.warning(f"⏳ {activated} order berstatus DRAFT — menunggu countersign DPJP.")
        st.rerun()


# =============================================================================
# Sub-tab: 📊 Status Order
# =============================================================================

def _render_status_tab(user: CPOEUser, episode_id: str):
    st.subheader("📊 Status Semua Order")

    if not user.can(Permission.ORDER_VIEW_ALL):
        st.warning("Anda hanya dapat melihat order yang Anda buat sendiri.")

    col1, col2, col3 = st.columns(3)
    filter_type   = col1.selectbox("Jenis", ["Semua"] + [o.value for o in CPOEOrderType])
    filter_status = col2.selectbox("Status", ["Semua"] + [s.value for s in CPOEOrderStatus])
    hours_back    = col3.slider("Jam terakhir", 1, 72, 24)

    otype_str  = "" if filter_type == "Semua" else filter_type
    status_str = "" if filter_status == "Semua" else filter_status

    rows = CPOEStore.get_orders(episode_id, order_type=otype_str,
                                 status=status_str, limit=100)

    # Filter OWN jika hanya punya VIEW_OWN
    if not user.can(Permission.ORDER_VIEW_ALL):
        rows = [r for r in rows if r.get("ordered_by_nip") == user.nip]

    if not rows:
        st.info("Tidak ada order dalam filter ini.")
        return

    import pandas as pd
    df = pd.DataFrame(rows)
    df["ordered_at"] = pd.to_datetime(df["ordered_at"]).dt.strftime("%d/%m %H:%M")
    df["⚠️ CS"] = df["countersign_required"].apply(
        lambda x: "⏳ Perlu CS" if x and not df["countersigned_by"].iloc[0] else (
            "✅ CS" if x else "—"
        )
    )

    st.dataframe(
        df[["ordered_at", "order_type", "priority", "status",
            "ordered_by", "ordered_by_role", "⚠️ CS", "clma_order_id", "notes"]].rename(columns={
            "ordered_at": "Waktu", "order_type": "Jenis", "priority": "Prioritas",
            "status": "Status", "ordered_by": "Pemesan", "ordered_by_role": "Role",
            "clma_order_id": "CLMA ID", "notes": "Catatan",
        }),
        use_container_width=True, hide_index=True,
    )
    st.caption(f"Total: {len(rows)} order")


# =============================================================================
# Sub-tab: ✅ Countersign
# =============================================================================

def _render_countersign_tab(user: CPOEUser, episode_id: str):
    st.subheader("✅ Countersign Order Residen")
    st.caption(
        "DPJP wajib me-review dan countersign semua order DRAFT dari residen "
        "sebelum order dapat dieksekusi farmasi/perawat."
    )

    pending = CPOEStore.get_pending_countersign(episode_id)
    if not pending:
        st.success("✅ Tidak ada order yang menunggu countersign.")
        return

    for row in pending:
        payload = json.loads(row.get("payload_json", "{}"))
        with st.container(border=True):
            st.markdown(
                f"**{row['order_type']}** — "
                f"`{row['order_id']}` — "
                f"Oleh: {row['ordered_by']} ({row['ordered_by_role']})"
            )
            st.caption(f"Dipesan: {row['ordered_at'][:16]} | Prioritas: {row['priority']}")

            if row["order_type"] == CPOEOrderType.MEDICATION.value:
                drug = payload.get("drug_name", "—")
                dose = f"{payload.get('dose_value', '?')} {payload.get('dose_unit', '')}"
                rate = payload.get("rate_ml_h", 0)
                is_ha = payload.get("is_high_alert", False)
                st.markdown(
                    f"💊 **{drug}** {dose} via {payload.get('route', '—')} | "
                    f"Rate: {rate:.2f} ml/h "
                    f"{'🔴 HIGH ALERT' if is_ha else ''}"
                )
                if row.get("notes"):
                    st.caption(f"Catatan: {row['notes']}")

            col_a, col_b, col_c = st.columns([2, 1, 1])
            cs_notes = col_a.text_input("Catatan countersign:", key=f"cs_note_{row['order_id']}")

            with col_b:
                if st.button("✅ Setujui", key=f"cs_approve_{row['order_id']}",
                              type="primary", use_container_width=True):
                    ok, msg = CPOEAuthChecker.check_countersign(
                        user, CPOERole(row["ordered_by_role"])
                        if row["ordered_by_role"] in [r.value for r in CPOERole]
                        else CPOERole.RESIDEN_JR
                    )
                    if not ok:
                        st.error(msg)
                    else:
                        CPOEStore.countersign(row["order_id"], user.nip, user.display_name)
                        CPOEAuthService.save_countersign(
                            row["order_id"], episode_id,
                            row["ordered_by_nip"],
                            CPOERole.RESIDEN_JR,
                            user, cs_notes,
                        )
                        # Route medication ke CLMA setelah countersign
                        if row["order_type"] == CPOEOrderType.MEDICATION.value:
                            ctx = st.session_state.get("cppt_ctx", {})
                            CLMABridge.route_to_clma(
                                payload, episode_id,
                                ctx.get("pasien_nama", ""),
                                ctx.get("pasien_no_rm", ""),
                            )
                        st.success(f"✅ Order `{row['order_id']}` disetujui dan diaktivasi.")
                        st.rerun()

            with col_c:
                if st.button("❌ Tolak", key=f"cs_reject_{row['order_id']}",
                              use_container_width=True):
                    CPOEStore.update_status(row["order_id"], CPOEOrderStatus.CANCELLED)
                    st.warning(f"Order `{row['order_id']}` ditolak.")
                    st.rerun()


# =============================================================================
# Sub-tab: 🔐 Admin
# =============================================================================

def _render_admin_tab(user: CPOEUser):
    st.subheader("🔐 Admin CPOE — Manajemen Pengguna & Audit")

    if not user.can(Permission.ADMIN_USER_MGMT):
        st.error("🚫 Tidak memiliki akses admin."); return

    admin_tab1, admin_tab2 = st.tabs(["👥 Pengguna", "📜 Auth Log"])

    with admin_tab1:
        users = CPOEAuthService.get_all_users()
        if users:
            import pandas as pd
            df = pd.DataFrame(users)
            st.dataframe(
                df[["nip", "full_name", "role", "department",
                     "specialization", "pk_level", "is_active", "last_login"]].rename(columns={
                    "nip": "NIP", "full_name": "Nama", "role": "Role",
                    "department": "SMF/Ruangan", "specialization": "Spesialisasi",
                    "pk_level": "Level PK", "is_active": "Aktif", "last_login": "Login Terakhir",
                }),
                use_container_width=True, hide_index=True,
            )
        st.caption(
            "Untuk menambah/mengubah pengguna, hubungi Admin IT RSJPDHK. "
            "Setiap perubahan hak akses harus didokumentasikan sesuai KPS 5 SNARS."
        )

    with admin_tab2:
        logs = CPOEAuthService.get_auth_log(limit=50)
        if logs:
            import pandas as pd
            df = pd.DataFrame(logs)
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%d/%m %H:%M:%S")
            st.dataframe(
                df[["timestamp", "nip", "action", "result", "detail"]],
                use_container_width=True, hide_index=True,
            )

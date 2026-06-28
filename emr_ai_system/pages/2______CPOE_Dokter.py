"""
Halaman: 👨‍⚕️ CPOE Dokter — Order Medis & CDSS ICD-10 / PPK / PERKI
======================================================================
Modul khusus untuk pengguna berperan sebagai Dokter (DPJP / Dokter Jaga).

Fitur utama:
  Tab 1 — 🔍 Diagnosis (ICD-10): cari kode ICD-10, tambah/hapus diagnosis aktif
  Tab 2 — 📋 PPK / PERKI Guide: tata laksana otomatis sesuai diagnosis aktif
  Tab 3 — 💊 Order Obat CPOE: entry order obat + validasi CDSS real-time
  Tab 4 — 🧪 Order Lab & Penunjang: order laboratorium dan radiologi
  Tab 5 — 🫁 Order Ventilator: setting ventilator via CPOE
  Tab 6 — 📄 Daftar Order Aktif: ringkasan semua order + cancel
  Tab 7 — 📦 Order Set Standar: bundle order berbasis PPK sekali klik

INTEGRASI ke dashboard.py:
  - Membaca: episode_id, pasien_nama, pasien_no_rm, logged_in, pasien_dipilih
  - Menulis:  cpoe_orders (list order aktif siap dibaca oleh perawat),
              diagnosa_aktif (list ICD-10),
              a_text_area (isi Assessment/A dari diagnosis ICD-10),
              p_text_area (isi Plan/P dari rekomendasi PPK).
  Mekanisme: via st.session_state (tidak ada import dashboard.py).
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st
from modules.bridge_updated import (
    require_role, require_permission, require_cppt_session,
    get_auth_context, display_user_badge
)
  
  # ✅ Guard 1: Hanya Dokter
if not require_role("Dokter"):
    st.stop()
  
  # ✅ Guard 2: Pastikan pasien dipilih
cppt_ctx = require_cppt_session()
  
  # ✅ Guard 3: Optional, check specific permission
if not require_permission("create_cpoe_orders"):
    st.stop()
  
  # ✅ Display user info
display_user_badge()
  
  # ✅ Rest of page content...
st.write("CPOE content here")

from modules.bridge_updated import get_cppt_context, push_objective_to_cppt
from modules.doctor.icd10_db import (
    get_icd10_by_code, get_icu_priority_codes, list_kategori, search_icd10,
)
from modules.doctor.ppk_protocols import get_ppk_by_icd10
from modules.doctor.cdss_doctor import (
    check_contraindications, check_drug_interactions, get_ppk_recommendations,
    run_full_cdss,
)
from modules.doctor.cpoe_engine import (
    build_drug_order, build_lab_order, build_ventilator_order,
    get_order_set, get_order_sets_for_icd10, validate_order, ORDER_SETS,
)
from modules.doctor.database import (
    cancel_order, deactivate_diagnosis, get_active_diagnoses, get_active_orders,
    get_all_orders, get_audit_log, init_database,
    save_diagnosis, save_order, update_order_status,
)
from modules.doctor.models import (
    Diagnosis, DiagnosisType, MedicalOrder, OrderStatus, OrderType,
    PriorityLevel, AlertSeverity,
)

st.set_page_config(
    page_title="Smart EMR — CPOE Dokter",
    page_icon="👨‍⚕️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_database()

# ── Guard & Konteks ───────────────────────────────────────────────────────
ctx = get_cppt_context()

if not ctx["logged_in"]:
    st.warning("🔒 Belum login. Kembali ke Dashboard CPPT untuk login.")
    try:
        st.page_link("dashboard.py", label="➡️ Ke Halaman Login", icon="🫀")
    except Exception:
        pass
    st.stop()

if not ctx["pasien_dipilih"] or not ctx["episode_id"]:
    st.warning("⚠️ Belum ada pasien aktif. Pilih pasien di Dashboard CPPT terlebih dahulu.")
    try:
        st.page_link("dashboard.py", label="➡️ Pilih Pasien", icon="🫀")
    except Exception:
        pass
    st.stop()

episode_id   = ctx["episode_id"]
patient_name = ctx["pasien_nama"] or "—"
patient_rm   = ctx["pasien_no_rm"] or "—"
user_id      = ctx["user_id"] or "dokter"


# ── Inisialisasi session_state dokter ─────────────────────────────────────
def _ss_init(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

_ss_init("dokter_id", user_id)
_ss_init("dokter_nama", user_id)
_ss_init("dokter_spesialisasi", "Umum / Belum Dipilih")
_ss_init("cdss_override_log", [])     # log override alert kritis
_ss_init("order_set_preview", None)


# ── Sidebar ───────────────────────────────────────────────────────────────
st.sidebar.markdown("## 👨‍⚕️ CPOE Dokter")
try:
    st.sidebar.page_link("dashboard.py", label="⬅️ Kembali ke Dashboard CPPT", icon="🫀")
    st.sidebar.page_link("pages/1_🫁_Monitor_Device.py", label="🫁 Monitor Device", icon="🫁")
except Exception:
    pass

st.sidebar.markdown("---")
st.sidebar.markdown("**🛏️ Pasien Aktif**")
st.sidebar.write(f"🧑 **{patient_name}**")
st.sidebar.write(f"🪪 RM: `{patient_rm}`  |  Episode: `{episode_id}`")

st.sidebar.markdown("---")
st.sidebar.markdown("**👨‍⚕️ Profil Dokter**")
st.session_state["dokter_nama"] = st.sidebar.text_input(
    "Nama Dokter", value=st.session_state["dokter_nama"])
st.session_state["dokter_spesialisasi"] = st.sidebar.selectbox(
    "Spesialisasi",
    ["Umum / Jaga ICU", "Kardiologi", "Paru & Kritis", "Anestesiologi & Intensif",
     "Penyakit Dalam", "Neurologi", "Bedah", "Lainnya"],
    index=0,
)
st.session_state["dokter_id"] = st.sidebar.text_input(
    "No. SIP / ID Dokter", value=st.session_state["dokter_id"])

dokter_nama = st.session_state["dokter_nama"]
dokter_id   = st.session_state["dokter_id"]


# ── Header ────────────────────────────────────────────────────────────────
st.markdown("# 👨‍⚕️ CPOE Dokter — Order Medis & CDSS")
st.markdown(
    f"**Dokter:** {dokter_nama} ({st.session_state['dokter_spesialisasi']})  |  "
    f"**Pasien:** {patient_name} (`{episode_id}`)"
)

# Ringkasan cepat diagnosis + order aktif
col1, col2, col3 = st.columns(3)
dx_aktif = get_active_diagnoses(episode_id)
orders_aktif = get_active_orders(episode_id)
with col1:
    st.metric("Diagnosis Aktif", len(dx_aktif))
with col2:
    st.metric("Order Aktif", len(orders_aktif))
with col3:
    urgent = sum(1 for o in orders_aktif if "Urgent" in o.get("prioritas", ""))
    st.metric("Order Urgent/STAT", urgent)

st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "🔍 Diagnosis ICD-10",
    "📋 PPK / PERKI Guide",
    "💊 Order Obat",
    "🧪 Order Lab & Penunjang",
    "🫁 Order Ventilator",
    "📄 Semua Order Aktif",
    "📦 Order Set Standar",
])


# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — DIAGNOSIS ICD-10
# ══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("🔍 Pencarian & Penetapan Diagnosis ICD-10")

    col_search, col_kat = st.columns([3, 1])
    with col_search:
        query = st.text_input(
            "Ketik nama penyakit atau kode ICD-10:",
            placeholder="contoh: STEMI / I21.0 / fibrilasi atrium / gagal jantung",
        )
    with col_kat:
        kat_filter = st.selectbox("Filter Kategori", ["Semua"] + list_kategori())

    if query:
        results = search_icd10(query, limit=12)
        if kat_filter != "Semua":
            results = [r for r in results if r["kategori"] == kat_filter]

        if results:
            st.markdown(f"**Ditemukan {len(results)} hasil:**")
            for r in results:
                icu_tag = "🔴 ICU" if r["prioritas_icu"] else ""
                ppk_tag = "📋 ada PPK" if r["ppk_tersedia"] else ""
                with st.container():
                    col_info, col_btn = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"**`{r['kode']}`** — {r['nama_id']}  \n"
                            f"_EN: {r['nama_en']}_ | 📁 {r['kategori']} {icu_tag} {ppk_tag}"
                        )
                    with col_btn:
                        tipe_dx = st.selectbox(
                            "Tipe", [t.value for t in DiagnosisType],
                            key=f"tipe_{r['kode']}", label_visibility="collapsed"
                        )
                        if st.button("➕ Tambah", key=f"add_{r['kode']}"):
                            existing = [d["kode_icd10"] for d in dx_aktif]
                            if r["kode"] in existing:
                                st.warning(f"`{r['kode']}` sudah ada dalam daftar diagnosis aktif.")
                            else:
                                dx = Diagnosis(
                                    kode_icd10=r["kode"],
                                    nama_penyakit=r["nama_id"],
                                    tipe=tipe_dx,
                                    episode_id=episode_id,
                                    dokter_id=dokter_id,
                                )
                                save_diagnosis(dx)
                                # Sync ke session_state CPPT
                                st.session_state["diagnosa_aktif"] = get_active_diagnoses(episode_id)
                                st.success(f"✓ Diagnosis `{r['kode']}` — {r['nama_id']} ditambahkan.")
                                st.rerun()
        else:
            st.info("Tidak ditemukan hasil. Coba kata kunci lain.")

    st.markdown("---")
    st.subheader("📋 Daftar Diagnosis Aktif Episode Ini")
    dx_aktif = get_active_diagnoses(episode_id)

    if dx_aktif:
        for dx in dx_aktif:
            entry = get_icd10_by_code(dx["kode_icd10"])
            ppk_flag = "📋" if (entry and entry.get("ppk_tersedia")) else ""
            icu_flag = "🔴" if (entry and entry.get("prioritas_icu")) else ""
            col_dx, col_cat, col_rm = st.columns([5, 2, 1])
            with col_dx:
                st.write(f"{icu_flag}{ppk_flag} **`{dx['kode_icd10']}`** — {dx['nama_penyakit']}")
            with col_cat:
                st.caption(f"{dx['tipe']} | {dx['timestamp'][:10]}")
            with col_rm:
                if st.button("❌", key=f"rm_dx_{dx['id']}", help="Nonaktifkan diagnosis ini"):
                    deactivate_diagnosis(dx["id"])
                    st.session_state["diagnosa_aktif"] = get_active_diagnoses(episode_id)
                    st.rerun()

        # Catatan: tombol "Kirim Daftar Diagnosis ke Kolom A (Assessment) CPPT"
        # sudah dihapus — selalu tertimpa oleh panel otomatis
        # "Assessment Medis & Rencana Tatalaksana (A & P)" milik Dokter di
        # dashboard.py (keduanya menulis ke session_state["soap_A"] yang sama).
        # Panel di dashboard.py sudah mencakup diagnosis + tanda vital +
        # rekomendasi CDSS dan bisa diedit manual di sana.
    else:
        st.info("Belum ada diagnosis aktif. Cari dan tambahkan diagnosis di atas.")


# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — PPK / PERKI GUIDE
# ══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("📋 Panduan Tata Laksana PPK / PERKI")

    dx_aktif = get_active_diagnoses(episode_id)
    if not dx_aktif:
        st.info("Tambahkan diagnosis ICD-10 di tab **🔍 Diagnosis** terlebih dahulu.")
    else:
        ppk_results = get_ppk_recommendations(dx_aktif)
        if not ppk_results:
            st.info("Belum ada PPK/PERKI yang terdokumentasi untuk diagnosis aktif saat ini.")
        else:
            for ppk in ppk_results:
                with st.expander(f"📋 {ppk['nama_ppk']}", expanded=True):
                    st.caption(f"📖 Referensi: {ppk['referensi']} | Dipicu oleh: `{ppk['kode_icd10_trigger']}`")
                    st.markdown(f"**🎯 Tujuan Terapi:** {ppk['tujuan']}")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**🔬 Pemeriksaan Awal Wajib:**")
                        for item in ppk["pemeriksaan_awal"]:
                            st.markdown(f"- {item}")

                        st.markdown("**📊 Target Terapi:**")
                        for k, v in ppk["target"].items():
                            st.markdown(f"- **{k}:** {v}")

                    with col2:
                        st.markdown("**📈 Monitoring Wajib:**")
                        for m in ppk["monitoring"]:
                            st.markdown(f"- {m}")

                        if ppk.get("skor_risiko"):
                            st.markdown("**📐 Skor Risiko / Stratifikasi:**")
                            for sk, sv in ppk["skor_risiko"].items():
                                st.markdown(f"- **{sk}:** {sv}")

                    st.markdown("**⚠️ Kontraindikasi Penting:**")
                    for ki in ppk["kontraindikasi"]:
                        st.error(f"🚫 {ki}", icon="🚫")

                    st.markdown("**🗂️ Langkah Tata Laksana:**")
                    for step in ppk["tata_laksana"]:
                        st.markdown(
                            f"**{step['urutan']}. {step['langkah']}**  \n"
                            f"{step['detail']}"
                        )
                        st.divider()

                    st.markdown("**💊 Obat Rekomendasi PPK:**")
                    df_obat = pd.DataFrame(ppk["obat_rekomendasi"])
                    if not df_obat.empty:
                        st.dataframe(df_obat, use_container_width=True, hide_index=True)

        # Catatan: tombol "Kirim Ringkasan PPK ke Kolom P (Plan) CPPT" sudah
        # dihapus — selalu tertimpa oleh panel otomatis "Assessment Medis &
        # Rencana Tatalaksana (A & P)" milik Dokter di dashboard.py (keduanya
        # menulis ke session_state["soap_P"] yang sama).


# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — ORDER OBAT
# ══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("💊 Order Obat — CPOE dengan CDSS Real-Time")
    st.caption("CDSS akan otomatis memeriksa kontraindikasi dan interaksi obat saat Anda mengisi order.")

    col1, col2 = st.columns(2)
    with col1:
        nama_obat = st.text_input("Nama Obat *", placeholder="contoh: Furosemide, Ticagrelor, Norepinefrin")
        dosis     = st.text_input("Dosis *", placeholder="contoh: 40, 0.5 mg/kgBB, 5-20")
        satuan    = st.selectbox("Satuan", ["mg", "mcg", "mEq", "IU", "ml", "mg/kgBB", "mcg/kgBB/mnt", "IU/kgBB"])
        rute      = st.selectbox("Rute Pemberian *", ["IV", "IV Bolus", "IV Drip", "SC", "IM", "PO", "SL", "Inhalasi", "Topikal"])

    with col2:
        frekuensi = st.selectbox(
            "Frekuensi *",
            ["OD (1x/hari)", "BID / q12h (2x/hari)", "TID / q8h (3x/hari)", "QID / q6h (4x/hari)",
             "q4h", "q2h", "PRN (bila perlu)", "STAT (segera 1x)", "Infus kontinu", "Loading dose"]
        )
        durasi    = st.text_input("Durasi", placeholder="contoh: 3 hari, 1 minggu, jangka panjang, sampai order baru")
        prioritas = st.selectbox("Prioritas", [p.value for p in PriorityLevel])
        icd10_ind = st.selectbox(
            "ICD-10 Indikasi (opsional)",
            ["—"] + [f"{d['kode_icd10']} — {d['nama_penyakit']}" for d in dx_aktif]
        )

    with st.expander("Detail Tambahan (Infus Drip / Pengenceran)", expanded=False):
        kecepatan = st.text_input("Kecepatan Infus", placeholder="contoh: 5 mg/jam, 0.1 mcg/kgBB/mnt")
        pengencer = st.text_input("Pengenceran", placeholder="contoh: dalam 100cc NS 0.9%, dalam 50cc D5%")
        indikasi  = st.text_area("Indikasi Klinis", placeholder="Tulis indikasi klinis order ini", height=60)
        catatan   = st.text_area("Catatan tambahan untuk perawat", height=60)

    # ── CDSS Real-time ──
    if nama_obat.strip():
        st.markdown("---")
        st.markdown("### 🤖 Analisis CDSS Real-Time")
        cdss_result = run_full_cdss(nama_obat, orders_aktif, dx_aktif)

        # Tampilkan summary
        if cdss_result["aman"]:
            st.success(f"✅ {cdss_result['summary']}")
        else:
            st.error(f"🚨 {cdss_result['summary']}")

        # Tampilkan tiap alert
        for alert in cdss_result["alerts"]:
            if alert.severity == AlertSeverity.CRITICAL.value:
                st.error(f"**🚨 {alert.judul}**  \n{alert.pesan}  \n💡 *{alert.rekomendasi}*")
            elif alert.severity == AlertSeverity.WARNING.value:
                st.warning(f"**⚠️ {alert.judul}**  \n{alert.pesan}  \n💡 *{alert.rekomendasi}*")
            else:
                st.info(f"**ℹ️ {alert.judul}**  \n{alert.pesan}")

        has_critical = not cdss_result["aman"]
        override_ok = False
        if has_critical:
            override_ok = st.checkbox(
                "⚠️ Saya memahami risiko dan memiliki justifikasi klinis yang kuat untuk melanjutkan order ini.",
                key="override_critical"
            )
            if not override_ok:
                st.stop()

    # ── Tombol simpan ──
    st.markdown("---")
    col_save, col_clear = st.columns([1, 3])
    with col_save:
        if st.button("💾 Simpan Order Obat", type="primary", use_container_width=True):
            if not nama_obat.strip() or not dosis.strip():
                st.error("Nama obat dan dosis wajib diisi.")
            else:
                icd10_terkait = None
                if icd10_ind != "—":
                    icd10_terkait = icd10_ind.split("—")[0].strip()

                order = build_drug_order(
                    episode_id=episode_id,
                    dokter_id=dokter_id,
                    dokter_nama=dokter_nama,
                    nama_obat=nama_obat,
                    dosis=dosis,
                    satuan=satuan,
                    rute=rute,
                    frekuensi=frekuensi,
                    durasi=durasi,
                    kecepatan_infus=kecepatan if kecepatan else None,
                    pengenceran=pengencer if pengencer else None,
                    indikasi=indikasi,
                    prioritas=prioritas,
                    catatan=catatan,
                    icd10_terkait=icd10_terkait,
                )
                errs = validate_order(order)
                if errs:
                    for e in errs: st.error(e)
                else:
                    save_order(order)
                    # Sync ke session_state CPPT
                    st.session_state["cpoe_orders"] = get_active_orders(episode_id)
                    st.success(f"✓ Order `{order.order_id}` — **{nama_obat}** tersimpan.")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — ORDER LAB & PENUNJANG
# ══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("🧪 Order Laboratorium & Pemeriksaan Penunjang")

    col1, col2 = st.columns(2)
    with col1:
        lab_kategori = st.selectbox("Kategori Pemeriksaan", [
            "Hematologi", "Kimia Klinik", "Elektrolit & Analisa Gas Darah",
            "Koagulasi", "Enzim Jantung & Biomarker", "Mikrobiologi & Kultur",
            "Hormon & Imunologi", "Radiologi", "Diagnostik Lain",
        ])

        PANEL_OPTIONS = {
            "Hematologi": ["Darah Lengkap (CBC)", "Hitung Jenis (Diff Count)", "Retikulosit", "Apusan Darah Tepi"],
            "Kimia Klinik": ["Kimia Klinik Lengkap", "Ureum + Kreatinin", "LFT Lengkap", "GDS", "GDP + GD2PP", "HbA1c", "Asam Urat", "Albumin"],
            "Elektrolit & Analisa Gas Darah": ["AGD Arteri", "Elektrolit Lengkap (Na+, K+, Cl-)", "Kalsium Total", "Magnesium", "Laktat Serum", "Laktat Arteri"],
            "Koagulasi": ["PT / INR", "aPTT", "Fibrinogen", "D-Dimer", "Anti-Xa Level (bila LMWH)", "TEG / ROTEM"],
            "Enzim Jantung & Biomarker": ["hs-Troponin I (serial)", "hs-Troponin T (serial)", "CK-MB", "BNP", "NT-proBNP", "Mioglobin", "LDH"],
            "Mikrobiologi & Kultur": ["Kultur Darah 2 Set (Aerob + Anaerob)", "Kultur Urin", "Kultur Sputum / BAL", "Kultur Luka", "Prokalsitonin (PCT)", "CRP Kuantitatif"],
            "Hormon & Imunologi": ["TSH", "FT3 + FT4", "Kortisol Serum", "HIV Rapid", "HBsAg", "Anti-HCV"],
            "Radiologi": ["Foto Toraks AP (Portable)", "Foto Toraks PA", "USG Abdomen", "CT Scan Kepala Non-Kontras", "CT Angiografi Toraks (CTA PE)", "Ekokardiografi Transtoraks (TTE)", "Ekokardiografi Transesofageal (TEE)"],
            "Diagnostik Lain": ["EKG 12 Lead", "EEG", "Spirometri", "Holter Monitor 24 jam"],
        }
        panel_options = PANEL_OPTIONS.get(lab_kategori, [])
        panel_lab = st.selectbox("Pemeriksaan", panel_options)
        panel_custom = st.text_input("Atau ketik nama pemeriksaan manual:", placeholder="contoh: Amylase + Lipase")
        final_panel = panel_custom if panel_custom.strip() else panel_lab

    with col2:
        spesimen = st.selectbox("Jenis Spesimen", [
            "Darah Vena", "Darah Arteri", "Urin Kateter", "Urin Midstream",
            "Sputum", "BAL (Bronchoalveolar Lavage)", "Wound Swab", "Tidak Memerlukan Spesimen"
        ])
        waktu_lab = st.selectbox("Waktu Pengambilan", [
            "SEGERA / STAT", "Pagi (Jam 06.00)", "Siang (Jam 12.00)",
            "Malam (Jam 00.00)", "Serial (tiap 6 jam)", "Serial (tiap 12 jam)", "PRN (bila diperlukan)"
        ])
        prioritas_lab = st.selectbox("Prioritas", [p.value for p in PriorityLevel], key="lab_prio")
        catatan_lab   = st.text_area("Catatan untuk Laboratorium", height=80)
        icd10_lab     = st.selectbox(
            "ICD-10 Indikasi",
            ["—"] + [f"{d['kode_icd10']} — {d['nama_penyakit']}" for d in dx_aktif],
            key="icd10_lab"
        )

    if st.button("💾 Simpan Order Lab / Penunjang", type="primary"):
        if not final_panel:
            st.error("Nama pemeriksaan wajib diisi.")
        else:
            icd10_terkait = None if icd10_lab == "—" else icd10_lab.split("—")[0].strip()
            order = build_lab_order(
                episode_id=episode_id,
                dokter_id=dokter_id,
                dokter_nama=dokter_nama,
                panel_lab=final_panel,
                jenis_spesimen=spesimen,
                waktu_pengambilan=waktu_lab,
                catatan_lab=catatan_lab,
                prioritas=prioritas_lab,
                icd10_terkait=icd10_terkait,
                kategori=lab_kategori,
            )
            save_order(order)
            st.session_state["cpoe_orders"] = get_active_orders(episode_id)
            st.success(f"✓ Order Lab `{order.order_id}` — **{final_panel}** tersimpan.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB 5 — ORDER VENTILATOR
# ══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("🫁 Order Setting Ventilator via CPOE")
    st.info("Order ini akan diteruskan ke perawat dan teknisi elektromedis yang bertugas.")

    col1, col2, col3 = st.columns(3)
    with col1:
        vent_mode    = st.selectbox("Mode Ventilasi", ["AC/CV", "SIMV", "PS/CPAP", "PC", "PRVC", "APRV", "HFOV"])
        fio2_val     = st.slider("FiO2 Target (%)", min_value=21, max_value=100, value=50, step=1)
        peep_val     = st.number_input("PEEP (cmH2O)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)
    with col2:
        tv_val       = st.number_input("Tidal Volume (mL)", min_value=200, max_value=900, value=450, step=10)
        rr_val       = st.number_input("Respiratory Rate Set (/mnt)", min_value=6, max_value=40, value=14)
        ie_ratio     = st.selectbox("I:E Ratio", ["1:1", "1:1.5", "1:2", "1:2.5", "1:3", "1:4"])
    with col3:
        spo2_target  = st.text_input("Target SpO2", value="94-98%")
        catatan_vent = st.text_area("Catatan Klinis", placeholder="Indikasi setting, tujuan terapi ventilasi", height=100)

    # Proteksi lungprotective ventilation check
    bb_kg = st.number_input("Berat Badan Ideal / Prediksi (kg) — untuk cek TV protektif", min_value=30, max_value=120, value=60)
    tv_per_kg = tv_val / bb_kg if bb_kg > 0 else 0
    if tv_per_kg > 8:
        st.error(f"⚠️ Tidal Volume {tv_val} mL = **{tv_per_kg:.1f} mL/kgBB** — melebihi batas lung-protective ventilation (<6-8 mL/kgBB). Pertimbangkan kurangi TV untuk mencegah VILI.")
    elif tv_per_kg > 6:
        st.warning(f"Tidal Volume = {tv_per_kg:.1f} mL/kgBB — masih dalam batas toleran, namun pertimbangkan 6 mL/kgBB pada ARDS.")
    else:
        st.success(f"✅ Tidal Volume = {tv_per_kg:.1f} mL/kgBB — Lung-protective ventilation ✓")

    if st.button("💾 Simpan Order Ventilator", type="primary"):
        order = build_ventilator_order(
            episode_id=episode_id,
            dokter_id=dokter_id,
            dokter_nama=dokter_nama,
            mode=vent_mode,
            fio2_target=fio2_val / 100,
            peep=peep_val,
            tidal_volume=tv_val,
            rate=rr_val,
            ie_ratio=ie_ratio,
            target_spo2=spo2_target,
            catatan=catatan_vent,
        )
        save_order(order)
        st.session_state["cpoe_orders"] = get_active_orders(episode_id)
        st.success(f"✓ Order Ventilator `{order.order_id}` tersimpan → diteruskan ke perawat.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB 6 — SEMUA ORDER AKTIF
# ══════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("📄 Daftar Order Aktif Episode Ini")

    col_refresh, col_filter = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()
    with col_filter:
        filter_tipe = st.multiselect(
            "Filter Tipe Order",
            [t.value for t in OrderType],
            default=[],
        )

    all_orders = get_all_orders(episode_id)
    if filter_tipe:
        all_orders = [o for o in all_orders if o.get("tipe") in filter_tipe]

    if all_orders:
        for order in all_orders:
            status = order.get("status", "")
            status_color = {
                "Aktif": "🟢",
                "Dilaksanakan": "🔵",
                "Selesai": "✅",
                "Dibatalkan": "❌",
                "Draft": "🟡",
            }.get(status, "⚪")

            with st.container():
                col_info, col_action = st.columns([5, 1])
                with col_info:
                    prio = order.get("prioritas", "")
                    icd = f" | 🏷️ `{order['icd10_terkait']}`" if order.get("icd10_terkait") else ""
                    st.markdown(
                        f"{status_color} **{order.get('tipe','?')} — {order.get('nama_order','?')}** "
                        f"| {prio} | `{order['order_id']}`{icd}  \n"
                        f"🕐 {order.get('timestamp_order','')[:16]} | 👨‍⚕️ {order.get('dokter_nama','')}"
                    )
                    d = order.get("detail", {})
                    if order.get("tipe") == OrderType.OBAT.value:
                        st.caption(
                            f"Dosis: {d.get('dosis','')} {d.get('satuan','')} | "
                            f"Rute: {d.get('rute','')} | Frek: {d.get('frekuensi','')} | "
                            f"Durasi: {d.get('durasi','')}"
                        )

                with col_action:
                    if status == OrderStatus.AKTIF.value:
                        if st.button("❌ Batal", key=f"cancel_{order['order_id']}"):
                            cancel_order(order["order_id"], dokter_id)
                            st.session_state["cpoe_orders"] = get_active_orders(episode_id)
                            st.rerun()
                st.divider()
    else:
        st.info("Belum ada order untuk episode ini.")


# ══════════════════════════════════════════════════════════════════════════
# TAB 7 — ORDER SET STANDAR
# ══════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("📦 Order Set Standar (Satu Klik — Berbasis PPK)")
    st.caption("Pilih bundle order sesuai diagnosis, review, lalu konfirmasi untuk menyimpan semua order sekaligus.")

    col1, col2 = st.columns([2, 3])
    with col1:
        # Tampilkan order set yang relevan untuk diagnosis aktif
        relevant_sets = []
        for dx in dx_aktif:
            for key, os_data in ORDER_SETS.items():
                if dx["kode_icd10"] in os_data.get("icd10", []) and key not in [r[0] for r in relevant_sets]:
                    relevant_sets.append((key, os_data))

        if relevant_sets:
            st.success(f"💡 {len(relevant_sets)} order set tersedia sesuai diagnosis aktif:")
            for key, os_data in relevant_sets:
                st.markdown(f"- **{os_data['nama']}** — `{key}`")

        selected_set = st.selectbox(
            "Pilih Order Set",
            list(ORDER_SETS.keys()),
            format_func=lambda k: ORDER_SETS[k]["nama"],
        )

    with col2:
        os_data = ORDER_SETS.get(selected_set)
        if os_data:
            st.markdown(f"**📋 {os_data['nama']}**")
            st.caption(os_data["deskripsi"])
            st.markdown(f"ICD-10: {', '.join(os_data['icd10'])}")
            st.markdown(f"Jumlah order dalam bundle: **{len(os_data['orders'])}**")

    if os_data:
        st.markdown("---")
        st.markdown("**Preview order yang akan dibuat:**")
        for i, item in enumerate(os_data["orders"]):
            tipe = item.get("tipe", "?")
            nama = item.get("nama", "?")
            icon = {"Obat": "💊", "Lab": "🧪", "Cairan": "💉", "Keperawatan": "📋"}.get(tipe, "📄")
            col_chk, col_text = st.columns([1, 8])
            with col_chk:
                checked = st.checkbox("", value=True, key=f"os_check_{selected_set}_{i}")
            with col_text:
                detail = ""
                if tipe == "Obat":
                    detail = f" | {item.get('dosis','')} {item.get('satuan','')} {item.get('rute','')} {item.get('frekuensi','')}"
                elif tipe == "Lab":
                    detail = f" | {item.get('spesimen','')} — {item.get('waktu','')}"
                st.write(f"{icon} **{tipe}**: {nama}{detail}")

        st.markdown("---")
        if st.button(f"✅ Simpan Semua Order Bundle '{os_data['nama']}'", type="primary"):
            saved_count = 0
            for i, item in enumerate(os_data["orders"]):
                if not st.session_state.get(f"os_check_{selected_set}_{i}", True):
                    continue
                tipe = item.get("tipe", "")
                if tipe == "Obat":
                    ord_obj = build_drug_order(
                        episode_id=episode_id, dokter_id=dokter_id, dokter_nama=dokter_nama,
                        nama_obat=item["nama"],
                        dosis=item.get("dosis", "—"), satuan=item.get("satuan", "mg"),
                        rute=item.get("rute", "PO"), frekuensi=item.get("frekuensi", "OD"),
                        durasi=item.get("durasi", "—"), prioritas=PriorityLevel.SEGERA.value,
                    )
                elif tipe == "Lab":
                    ord_obj = build_lab_order(
                        episode_id=episode_id, dokter_id=dokter_id, dokter_nama=dokter_nama,
                        panel_lab=item["nama"],
                        jenis_spesimen=item.get("spesimen", "Darah Vena"),
                        waktu_pengambilan=item.get("waktu", "Segera"),
                        prioritas=PriorityLevel.SEGERA.value,
                    )
                else:
                    ord_obj = MedicalOrder(
                        order_id=__import__("modules.doctor.cpoe_engine", fromlist=["generate_order_id"]).generate_order_id() if False else f"CPOE-{datetime.now().strftime('%Y%m%d')}-{i:04d}",
                        episode_id=episode_id, dokter_id=dokter_id, dokter_nama=dokter_nama,
                        tipe=OrderType.KEPERAWATAN.value if tipe == "Keperawatan" else OrderType.CAIRAN_IV.value,
                        nama_order=item["nama"], detail={},
                        prioritas=PriorityLevel.SEGERA.value,
                    )
                save_order(ord_obj)
                saved_count += 1

            st.session_state["cpoe_orders"] = get_active_orders(episode_id)
            st.success(f"✓ {saved_count} order dari bundle '{os_data['nama']}' berhasil disimpan!")
            st.balloons()
            st.rerun()
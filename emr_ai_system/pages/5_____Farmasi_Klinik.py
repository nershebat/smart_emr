"""
Halaman Farmasi Klinik — Rekonsiliasi, Visite, DRP & Konseling
File: pages/5_💊_Farmasi_Klinik.py

Halaman mandiri untuk Apoteker Klinik.
Form di cppt_table._form_apoteker adalah versi ringkas (entry cepat).
Halaman ini menyediakan alur farmasi klinik lengkap:

ALUR:
  1. Guard: login + pasien aktif + role Apoteker/Admin
  2. Header pasien + ringkasan catatan farmasi sebelumnya
  3. Tab Rekonsiliasi Obat:
       - Obat sebelum masuk RS (home medication list)
       - Obat yang diorder dokter (CPOE — ditarik dari session)
       - Identifikasi discrepancy (intentional / unintentional)
  4. Tab Visite Farmasi & DRP:
       - Drug Related Problems (DRP) classification
       - Rekomendasi ke dokter
       - Tindak lanjut DRP
  5. Tab Drug Interaction & Safety:
       - Cek interaksi antar obat (input manual)
       - Kontraindikasi berdasarkan kondisi pasien
       - Monitoring parameter farmakologi
  6. Tab Konseling & Dispensing:
       - Status dispensing tiap obat
       - Materi KIE pasien/keluarga
  7. Tab Monitoring & Simpan → CPPT universal

REFERENSI:
  - PCNE DRP Classification v9.1 (Pharmaceutical Care Network Europe)
  - WHO Medication Reconciliation Guidelines
  - ISFI Panduan Visite Farmasi Klinik 2022
  - Standar Pelayanan Kefarmasian di RS (PMK 72/2016)
"""

import streamlit as st
import pandas as pd
import time
from datetime import datetime

# ── Import path fix: cppt_table ada di modules/components/, bukan root components/
try:
    from components.cppt_table import save_cppt_record, get_cppt_records, init_cppt_table
except ImportError:
    from components.cppt_table import save_cppt_record, get_cppt_records, init_cppt_table

from modules.bridge_cpoe_sync import CPOESyncManager


# ── Constants ─────────────────────────────────────────────────────────────────

# PCNE DRP Classification v9.1
DRP_PROBLEMS = {
    "P1": "Efek terapi yang tidak optimal",
    "P2": "Efek yang tidak diinginkan / adverse event",
    "P3": "Efek yang tidak perlu / pengobatan tidak diperlukan",
}

DRP_CAUSES = {
    "C1": {
        "label": "C1 — Pemilihan Obat",
        "items": [
            ("C1.1", "Obat tidak tepat sesuai panduan/formularium"),
            ("C1.2", "Kontraindikasi ada (absolut / relatif)"),
            ("C1.3", "Kombinasi obat-obat tidak tepat"),
            ("C1.4", "Kombinasi obat-penyakit tidak tepat"),
            ("C1.5", "Duplikasi terapi / bahan aktif sama"),
            ("C1.6", "Indikasi tidak jelas / tanpa indikasi"),
            ("C1.7", "Obat tidak aman pada pasien ini (alergi/kondisi)"),
            ("C1.8", "Obat sinergistik / preventif diperlukan tapi tidak diberikan"),
        ],
    },
    "C2": {
        "label": "C2 — Dosis",
        "items": [
            ("C2.1", "Dosis terlalu rendah"),
            ("C2.2", "Dosis terlalu tinggi"),
            ("C2.3", "Frekuensi pemberian tidak tepat"),
            ("C2.4", "Durasi terapi tidak tepat (terlalu pendek/panjang)"),
            ("C2.5", "Penyesuaian dosis perlu (fungsi ginjal/hati)"),
        ],
    },
    "C3": {
        "label": "C3 — Bentuk Sediaan & Rute",
        "items": [
            ("C3.1", "Rute pemberian tidak tepat"),
            ("C3.2", "Bentuk sediaan tidak tepat"),
            ("C3.3", "Kecepatan infus/pemberian tidak tepat"),
        ],
    },
    "C4": {
        "label": "C4 — Logistik & Dispensing",
        "items": [
            ("C4.1", "Obat tidak tersedia / stok habis"),
            ("C4.2", "Kesalahan dispensing / labeling"),
            ("C4.3", "Penyimpanan obat tidak tepat"),
        ],
    },
    "C5": {
        "label": "C5 — Kepatuhan Pasien",
        "items": [
            ("C5.1", "Pasien tidak minum/menggunakan obat"),
            ("C5.2", "Pasien menggunakan obat tidak tepat"),
            ("C5.3", "Pasien tidak menyetujui terapi"),
        ],
    },
    "C6": {
        "label": "C6 — Lain-lain",
        "items": [
            ("C6.1", "Tidak ada atau tidak jelas penyebabnya"),
            ("C6.2", "Faktor lain"),
        ],
    },
}

INTERAKSI_SEVERITY = {
    "Kontraindikasi (hindari kombinasi)": "🔴",
    "Mayor (risiko serius, hindari jika mungkin)": "🟠",
    "Moderat (monitor ketat, pertimbangkan alternatif)": "🟡",
    "Minor (observasi, risiko kecil)": "🟢",
    "Tidak signifikan": "⚪",
}

STATUS_DISPENSING = [
    "Belum disiapkan",
    "Sedang disiapkan",
    "Siap — belum diserahkan",
    "Sudah diserahkan ke perawat",
    "Sudah diserahkan ke pasien",
    "Ditunda (pending DPJP)",
    "Dibatalkan / stop order",
]

KIE_TEMPLATE = {
    "Antikoagulan (Warfarin/Heparin)": (
        "Jelaskan pentingnya INR monitoring rutin. "
        "Pantang: sayuran hijau berlebih (vitamin K). "
        "Hindari NSAID/aspirin tanpa rekomendasi dokter. "
        "Laporkan segera jika ada tanda perdarahan."
    ),
    "Antihipertensi": (
        "Minum obat teratur, jangan dihentikan tiba-tiba. "
        "Monitor TD mandiri setiap pagi. "
        "Batasi garam <5 g/hari. "
        "Hindari alkohol dan kafein berlebih."
    ),
    "Diuretik": (
        "Minum pagi hari untuk hindari nokturia. "
        "Monitor berat badan harian (kenaikan >1 kg/hari → lapor). "
        "Asupan kalium jika loop diuretik (pisang, jeruk). "
        "Monitor tanda dehidrasi."
    ),
    "Antiaritmia": (
        "Jangan lewatkan dosis. "
        "Laporkan segera: palpitasi, sinkop, sesak baru. "
        "Hindari kafein dan stimulan. "
        "Bawa kartu obat ke setiap kunjungan dokter."
    ),
    "Statin (kolesterol)": (
        "Minum malam hari (kecuali rosuvastatin fleksibel). "
        "Laporkan nyeri/lemah otot → kemungkinan myopathy. "
        "Hindari alkohol berlebih. "
        "Cek enzim hati berkala."
    ),
    "Antibiotik": (
        "Habiskan seluruh antibiotik sesuai resep. "
        "Jangan berbagi dengan orang lain. "
        "Minum bersama makanan jika mual. "
        "Laporkan jika diare hebat atau ruam."
    ),
    "Insulin / OHO": (
        "Rotasi tempat suntik insulin. "
        "Simpan insulin terbuka pada suhu ruang (<28°C, max 28 hari). "
        "Kenali tanda hipoglikemi: pusing, lemas, keringat dingin → minum gula. "
        "Monitor GDS sesuai jadwal."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_session() -> dict:
    logged_in = (
        st.session_state.get("logged_in", False)
        or st.session_state.get("authenticated", False)
    )
    if not logged_in:
        st.error("🔒 Anda harus login terlebih dahulu.")
        st.page_link("dashboard.py", label="➡️ Ke Halaman Login", icon="🫀")
        st.stop()

    if not st.session_state.get("pasien_dipilih") or not st.session_state.get("episode_id"):
        st.warning("⚠️ Belum ada pasien aktif.")
        st.page_link("dashboard.py", label="➡️ Pilih Pasien di Dashboard", icon="🫀")
        st.stop()

    role = st.session_state.get("role", "")
    if role not in ("Apoteker", "Admin"):
        st.error(f"❌ Halaman ini untuk Apoteker Klinik. Role Anda: **{role}**")
        st.page_link("dashboard.py", label="⬅️ Kembali ke Dashboard", icon="🫀")
        st.stop()

    return {
        "episode_id":     st.session_state.get("episode_id", ""),
        "user_id":        st.session_state.get("user_id", ""),
        "nama_lengkap":   st.session_state.get("nama_lengkap", ""),
        "pasien_nama":    st.session_state.get("pasien_nama", ""),
        "pasien_no_rm":   st.session_state.get("pasien_no_rm", ""),
        "pasien_ruangan": st.session_state.get("pasien_ruangan", ""),
        "pasien_dpjp":    st.session_state.get("pasien_dpjp", ""),
    }


def _get_cpoe_obat(episode_id: str) -> list[dict]:
    """Ambil order obat dari CPOE (dikirim dokter via CPOESyncManager)."""
    try:
        # FIX: CPOESyncManager adalah instance class, harus di-instantiate dulu
        mgr = CPOESyncManager()
        all_orders = mgr.get_orders_by_episode(episode_id)
        # DB memakai field 'order_type'; session_state memakai 'tipe' — handle keduanya
        return [
            o for o in all_orders
            if o.get("order_type") == "obat" or o.get("tipe") == "obat"
        ]
    except Exception:
        # Fallback: baca langsung dari cpoe_orders session
        return [
            o for o in st.session_state.get("cpoe_orders", [])
            if o.get("tipe") == "obat"
        ]


def _add_home_med():
    """Tambah baris obat rumah ke session list."""
    meds = st.session_state.get("fm_home_meds", [])
    meds.append({
        "nama":      st.session_state.get("fm_new_med_nama", ""),
        "dosis":     st.session_state.get("fm_new_med_dosis", ""),
        "frekuensi": st.session_state.get("fm_new_med_frek", ""),
        "rute":      st.session_state.get("fm_new_med_rute", "Oral"),
        "status_rekonsiliasi": "Belum direkonsiliasi",
    })
    st.session_state["fm_home_meds"] = meds
    for k in ["fm_new_med_nama", "fm_new_med_dosis", "fm_new_med_frek"]:
        st.session_state[k] = ""


def _remove_home_med(idx: int):
    meds = st.session_state.get("fm_home_meds", [])
    if 0 <= idx < len(meds):
        meds.pop(idx)
    st.session_state["fm_home_meds"] = meds


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Farmasi Klinik — Smart EMR",
        page_icon="💊",
        layout="wide",
    )

    # ── Pastikan tabel cppt_records sudah ada di database ─────────────────────
    try:
        init_cppt_table()
    except Exception as _e:
        st.error(f"❌ Gagal inisialisasi database CPPT: {_e}")
        st.stop()

    ctx = _require_session()
    episode_id   = ctx["episode_id"]
    user_id      = ctx["user_id"]
    nama_lengkap = ctx["nama_lengkap"]

    # ── Sidebar ───────────────────────────────────────────────────────────────
    try:
        from modules.bridge_updated import display_user_badge
        display_user_badge()
    except ImportError:
        st.sidebar.write(f"👤 {nama_lengkap or user_id}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**🛏️ Pasien Aktif**")
    st.sidebar.write(f"🧑 **{ctx['pasien_nama']}**")
    st.sidebar.caption(f"RM: `{ctx['pasien_no_rm']}`")
    if ctx["pasien_ruangan"]:
        st.sidebar.write(f"🛌 {ctx['pasien_ruangan']}")
    st.sidebar.write(f"🏷️ Episode: `{episode_id}`")
    if ctx["pasien_dpjp"]:
        st.sidebar.caption(f"DPJP: {ctx['pasien_dpjp']}")
    st.sidebar.markdown("---")
    st.sidebar.page_link("dashboard.py", label="⬅️ Dashboard CPPT", icon="🫀")

    # ── Init session keys ─────────────────────────────────────────────────────
    if "fm_home_meds" not in st.session_state:
        st.session_state["fm_home_meds"] = []
    if "fm_drp_list" not in st.session_state:
        st.session_state["fm_drp_list"] = []
    if "fm_interactions" not in st.session_state:
        st.session_state["fm_interactions"] = []

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("💊 Farmasi Klinik — Visite & Rekonsiliasi Obat")
    st.caption(
        f"Pasien: **{ctx['pasien_nama']}** | "
        f"RM: `{ctx['pasien_no_rm']}` | "
        f"Episode: `{episode_id}`"
    )

    # Riwayat catatan farmasi
    prev_records = [
        r for r in get_cppt_records(episode_id)
        if r.get("ppa_role") == "Apoteker"
    ]
    if prev_records:
        with st.expander(
            f"📋 Riwayat Catatan Farmasi ({len(prev_records)} catatan)",
            expanded=False,
        ):
            df_prev = pd.DataFrame([{
                "Waktu": (r.get("tgl_jam") or "")[:16],
                "Oleh":  r.get("ppa_nama", "-"),
                "A (DRP)":          (r.get("soap_a") or "")[:120],
                "P (Rekomendasi)":  (r.get("soap_p") or "")[:120],
            } for r in prev_records])
            st.dataframe(df_prev, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── TABS ──────────────────────────────────────────────────────────────────
    tab_rekon, tab_drp, tab_interaksi, tab_dispensing, tab_simpan = st.tabs([
        "🔄 Rekonsiliasi Obat",
        "⚠️ DRP & Visite",
        "🔗 Drug Interaction",
        "📦 Dispensing & KIE",
        "📊 Monitoring & Simpan",
    ])

    # =====================================================================
    # TAB 1 — REKONSILIASI OBAT
    # =====================================================================
    with tab_rekon:
        st.subheader("🔄 Rekonsiliasi Obat")
        st.caption(
            "Bandingkan obat sebelum masuk RS (home meds) dengan order dokter "
            "saat ini. Identifikasi discrepancy intentional vs unintentional."
        )

        col_r1, col_r2 = st.columns(2)

        # ── Obat rumah (home medication list) ────────────────────────────
        with col_r1:
            st.markdown("#### 🏠 Obat Sebelum Masuk RS")

            with st.expander("➕ Tambah Obat Rumah", expanded=len(st.session_state["fm_home_meds"]) == 0):
                st.text_input("Nama Obat:", key="fm_new_med_nama",
                              placeholder="Bisoprolol, Ramipril, Aspirin...")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.text_input("Dosis:", key="fm_new_med_dosis",
                                  placeholder="5 mg, 10 mg...")
                with c2:
                    st.text_input("Frekuensi:", key="fm_new_med_frek",
                                  placeholder="1x1, 2x1...")
                with c3:
                    st.selectbox("Rute:", ["Oral", "IV", "SC", "Topikal", "Inhaler", "Lain"],
                                 key="fm_new_med_rute")
                st.button("➕ Tambahkan", on_click=_add_home_med,
                          use_container_width=True, key="btn_add_home_med")

            home_meds = st.session_state.get("fm_home_meds", [])
            if home_meds:
                for i, med in enumerate(home_meds):
                    col_m, col_s, col_del = st.columns([3, 2, 1])
                    with col_m:
                        st.caption(
                            f"💊 **{med['nama']}** {med['dosis']} — "
                            f"{med['frekuensi']} ({med['rute']})"
                        )
                    with col_s:
                        new_status = st.selectbox(
                            "Status:",
                            ["Dilanjutkan", "Dihold sementara", "Dihentikan",
                             "Diganti obat lain", "Belum direkonsiliasi"],
                            index=["Dilanjutkan", "Dihold sementara", "Dihentikan",
                                   "Diganti obat lain", "Belum direkonsiliasi"].index(
                                       med.get("status_rekonsiliasi", "Belum direkonsiliasi")
                                   ),
                            key=f"fm_med_status_{i}",
                            label_visibility="collapsed",
                        )
                        st.session_state["fm_home_meds"][i]["status_rekonsiliasi"] = new_status
                    with col_del:
                        if st.button("🗑️", key=f"del_med_{i}", help="Hapus"):
                            _remove_home_med(i)
                            st.rerun()
            else:
                st.info("Belum ada obat rumah. Tambahkan di atas.")

        # ── Obat dari CPOE dokter ─────────────────────────────────────────
        with col_r2:
            st.markdown("#### 🏥 Order Obat Dokter (CPOE)")
            cpoe_obat = _get_cpoe_obat(episode_id)

            if cpoe_obat:
                for o in cpoe_obat:
                    status_icon = {
                        "pending":    "⏳",
                        "integrated": "✅",
                        "rejected":   "❌",
                    }.get(o.get("status", ""), "❓")
                    with st.container(border=True):
                        st.markdown(
                            f"{status_icon} **{o.get('nama_order', '-')}**  \n"
                            f"Dosis: `{o.get('dosis', '-')}` | "
                            f"Rute: `{o.get('rute', '-')}` | "
                            f"Frekuensi: `{o.get('frekuensi', '-')}`  \n"
                            f"Status: `{o.get('status', '-')}`"
                        )
                        # Verifikasi farmasi inline
                        col_v1, col_v2 = st.columns(2)
                        with col_v1:
                            if st.button(
                                "✅ Verifikasi",
                                key=f"fm_verify_{o.get('order_id','')}",
                                use_container_width=True,
                            ):
                                try:
                                    # FIX: gunakan instance, bukan class method
                                    import sqlite3 as _sq
                                    with _sq.connect("rsjpdhk_emr.db") as _conn:
                                        _conn.execute(
                                            "UPDATE cpoe_orders SET status='verified_pharmacy' "
                                            "WHERE order_id=?",
                                            (o["order_id"],)
                                        )
                                    st.success("Terverifikasi")
                                    st.rerun()
                                except Exception as _ve:
                                    st.warning(f"⚠️ Verifikasi gagal: {_ve}")
                        with col_v2:
                            if st.button(
                                "⚠️ Tandai DRP",
                                key=f"fm_drp_{o.get('order_id','')}",
                                use_container_width=True,
                            ):
                                drp = {
                                    "order_id":   o.get("order_id", ""),
                                    "nama_obat":  o.get("nama_order", ""),
                                    "problem":    "P1",
                                    "cause":      "",
                                    "keterangan": "",
                                    "rekomendasi": "",
                                    "status":     "Belum ditindaklanjuti",
                                }
                                st.session_state["fm_drp_list"].append(drp)
                                st.warning(f"DRP ditambahkan untuk {o.get('nama_order','')}. Lengkapi di tab DRP.")
            else:
                st.info(
                    "📭 Belum ada order obat dari dokter (CPOE). "
                    "Order akan muncul setelah dokter input di halaman CPOE."
                )

        st.markdown("---")

        # ── Discrepancy summary ───────────────────────────────────────────
        st.markdown("#### 📝 Catatan Discrepancy Rekonsiliasi")
        discrepancy_notes = st.text_area(
            "Temuan discrepancy (intentional / unintentional):",
            height=90,
            key="fm_discrepancy_notes",
            placeholder=(
                "Intentional: Warfarin dihold pre-prosedur (sesuai instruksi DPJP).\n"
                "Unintentional: Bisoprolol 5mg/hari tidak dilanjutkan tanpa keterangan → "
                "sudah dikonfirmasi ke DPJP, dilanjutkan."
            ),
        )
        st.session_state["fm_discrepancy"] = discrepancy_notes

    # =====================================================================
    # TAB 2 — DRP & VISITE FARMASI
    # =====================================================================
    with tab_drp:
        st.subheader("⚠️ Drug Related Problems (DRP) — PCNE v9.1")

        # ── Tambah DRP baru ───────────────────────────────────────────────
        with st.expander("➕ Identifikasi DRP Baru", expanded=True):
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                drp_obat = st.text_input(
                    "Obat yang terlibat:",
                    key="fm_drp_new_obat",
                    placeholder="Nama obat / semua obat...",
                )
                drp_problem = st.selectbox(
                    "Klasifikasi Problem (PCNE):",
                    list(DRP_PROBLEMS.items()),
                    format_func=lambda x: f"{x[0]} — {x[1]}",
                    key="fm_drp_new_problem",
                )
            with col_d2:
                drp_cause_domain = st.selectbox(
                    "Domain Penyebab:",
                    list(DRP_CAUSES.keys()),
                    format_func=lambda k: DRP_CAUSES[k]["label"],
                    key="fm_drp_cause_domain",
                )
                drp_cause_item = st.selectbox(
                    "Penyebab Spesifik:",
                    DRP_CAUSES[drp_cause_domain]["items"],
                    format_func=lambda x: f"{x[0]} — {x[1]}",
                    key="fm_drp_cause_item",
                )

            drp_keterangan = st.text_area(
                "Keterangan klinis:",
                height=80,
                key="fm_drp_keterangan",
                placeholder="Deskripsi DRP yang ditemukan saat visite...",
            )
            drp_rekomendasi = st.text_area(
                "Rekomendasi ke DPJP:",
                height=80,
                key="fm_drp_rekomendasi",
                placeholder="Sarankan penyesuaian dosis / penggantian obat / monitoring parameter...",
            )

            if st.button("➕ Tambahkan DRP", type="primary", key="btn_add_drp"):
                if drp_obat.strip():
                    st.session_state["fm_drp_list"].append({
                        "nama_obat":   drp_obat,
                        "problem":     f"{drp_problem[0]} — {drp_problem[1]}",
                        "cause":       f"{drp_cause_item[0]} — {drp_cause_item[1]}",
                        "keterangan":  drp_keterangan,
                        "rekomendasi": drp_rekomendasi,
                        "status":      "Belum ditindaklanjuti",
                    })
                    for k in ["fm_drp_keterangan", "fm_drp_rekomendasi", "fm_drp_new_obat"]:
                        st.session_state[k] = ""
                    st.success("DRP ditambahkan.")
                    st.rerun()
                else:
                    st.warning("Isi nama obat terlebih dahulu.")

        # ── Daftar DRP ────────────────────────────────────────────────────
        drp_list = st.session_state.get("fm_drp_list", [])
        if drp_list:
            st.markdown(f"#### 📋 Daftar DRP ({len(drp_list)} item)")
            for i, drp in enumerate(drp_list):
                with st.expander(
                    f"{'🔴' if 'P2' in drp['problem'] else '🟡'} "
                    f"DRP {i+1}: {drp['nama_obat']} — {drp['problem'][:30]}",
                    expanded=True,
                ):
                    col_info, col_status = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"**Obat:** {drp['nama_obat']}")
                        st.markdown(f"**Problem:** {drp['problem']}")
                        st.markdown(f"**Penyebab:** {drp['cause']}")
                        if drp.get("keterangan"):
                            st.caption(f"Keterangan: {drp['keterangan']}")
                        if drp.get("rekomendasi"):
                            st.info(f"💬 Rekomendasi: {drp['rekomendasi']}")
                    with col_status:
                        new_status = st.selectbox(
                            "Status tindak lanjut:",
                            ["Belum ditindaklanjuti",
                             "Disampaikan ke DPJP",
                             "Diterima — diimplementasi",
                             "Diterima sebagian",
                             "Ditolak DPJP",
                             "Resolved"],
                            index=["Belum ditindaklanjuti", "Disampaikan ke DPJP",
                                   "Diterima — diimplementasi", "Diterima sebagian",
                                   "Ditolak DPJP", "Resolved"].index(
                                       drp.get("status", "Belum ditindaklanjuti")
                                   ),
                            key=f"drp_status_{i}",
                        )
                        st.session_state["fm_drp_list"][i]["status"] = new_status
                        if st.button("🗑️ Hapus", key=f"del_drp_{i}"):
                            st.session_state["fm_drp_list"].pop(i)
                            st.rerun()
        else:
            st.info("Belum ada DRP yang diidentifikasi.")

    # =====================================================================
    # TAB 3 — DRUG INTERACTION
    # =====================================================================
    with tab_interaksi:
        st.subheader("🔗 Drug Interaction & Safety Monitoring")

        # ── Input pasangan interaksi ──────────────────────────────────────
        with st.expander("➕ Tambah Temuan Interaksi", expanded=True):
            col_i1, col_i2, col_i3 = st.columns(3)
            with col_i1:
                obat_a = st.text_input("Obat A:", key="fm_int_obat_a",
                                       placeholder="Warfarin")
            with col_i2:
                obat_b = st.text_input("Obat B:", key="fm_int_obat_b",
                                       placeholder="Aspirin")
            with col_i3:
                severity = st.selectbox(
                    "Tingkat Keparahan:",
                    list(INTERAKSI_SEVERITY.keys()),
                    key="fm_int_severity",
                )
            mekanisme = st.text_input(
                "Mekanisme / Deskripsi:",
                key="fm_int_mekanisme",
                placeholder="Warfarin + Aspirin: peningkatan risiko perdarahan (efek aditif antikoagulan)...",
            )
            tindakan = st.text_area(
                "Tindakan yang Disarankan:",
                height=70,
                key="fm_int_tindakan",
                placeholder="Monitor INR ketat, perhatikan tanda perdarahan, pertimbangkan PPI profilaksis...",
            )
            if st.button("➕ Catat Interaksi", key="btn_add_interaksi"):
                if obat_a.strip() and obat_b.strip():
                    st.session_state["fm_interactions"].append({
                        "obat_a":    obat_a,
                        "obat_b":    obat_b,
                        "severity":  severity,
                        "mekanisme": mekanisme,
                        "tindakan":  tindakan,
                    })
                    for k in ["fm_int_obat_a", "fm_int_obat_b", "fm_int_mekanisme", "fm_int_tindakan"]:
                        st.session_state[k] = ""
                    st.rerun()
                else:
                    st.warning("Isi minimal Obat A dan Obat B.")

        # ── Tabel interaksi ───────────────────────────────────────────────
        interactions = st.session_state.get("fm_interactions", [])
        if interactions:
            st.markdown(f"#### 📋 Temuan Interaksi ({len(interactions)} pasangan)")
            df_int = pd.DataFrame([{
                "Obat A":     i["obat_a"],
                "Obat B":     i["obat_b"],
                "Severity":   f"{INTERAKSI_SEVERITY.get(i['severity'], '❓')} {i['severity']}",
                "Mekanisme":  i["mekanisme"][:80],
                "Tindakan":   i["tindakan"][:80],
            } for i in interactions])
            st.dataframe(df_int, use_container_width=True, hide_index=True)

            if any("Kontraindikasi" in i["severity"] or "Mayor" in i["severity"]
                   for i in interactions):
                st.error(
                    "🚨 **Ditemukan interaksi Kontraindikasi atau Mayor!** "
                    "Segera konfirmasi ke DPJP sebelum obat diberikan."
                )
        else:
            st.info("Belum ada interaksi yang dicatat.")

        st.markdown("---")

        # ── Parameter monitoring farmakologi ─────────────────────────────
        st.markdown("#### 🧪 Parameter Monitoring Farmakologi")
        monitoring_param = st.text_area(
            "Parameter yang perlu dimonitor:",
            height=90,
            key="fm_monitoring_param",
            placeholder=(
                "- INR: target 2.0–3.0 (antikoagulan) → cek 2x/minggu\n"
                "- Kalium: target 3.5–5.0 mEq/L (diuretik) → cek harian\n"
                "- Kreatinin/eGFR: sebelum & sesudah kontras/NSAID\n"
                "- Kadar digoxin: 0.5–0.9 ng/mL → toksisitas jika >2.0"
            ),
        )
        # Catatan: nilai widget di atas (key fm_monitoring_param) sudah otomatis
        # tersimpan ke session_state oleh Streamlit. Jangan menulis ulang
        # session_state untuk key yang sama setelah widget dibuat — itulah
        # yang menyebabkan StreamlitAPIException pada versi sebelumnya.

    # =====================================================================
    # TAB 4 — DISPENSING & KIE
    # =====================================================================
    with tab_dispensing:
        st.subheader("📦 Status Dispensing & Konseling Pasien (KIE)")

        # ── Status dispensing per obat ────────────────────────────────────
        st.markdown("#### 📤 Status Dispensing")
        cpoe_obat = _get_cpoe_obat(episode_id)
        home_meds = st.session_state.get("fm_home_meds", [])
        all_obat  = (
            [{"nama": o.get("nama_order", ""), "sumber": "CPOE Dokter"} for o in cpoe_obat]
            + [{"nama": m.get("nama", ""), "sumber": "Obat Rumah"} for m in home_meds]
        )

        dispensing_status = {}
        if all_obat:
            for o in all_obat:
                if not o["nama"]:
                    continue
                col_ob, col_st = st.columns([3, 2])
                with col_ob:
                    st.caption(f"💊 {o['nama']} `[{o['sumber']}]`")
                with col_st:
                    status_disp = st.selectbox(
                        f"Status {o['nama']}:",
                        STATUS_DISPENSING,
                        key=f"fm_disp_{o['nama']}",
                        label_visibility="collapsed",
                    )
                    dispensing_status[o["nama"]] = status_disp
        else:
            st.info("Belum ada data obat. Isi di tab Rekonsiliasi terlebih dahulu.")

        st.session_state["fm_dispensing_status"] = dispensing_status

        st.markdown("---")

        # ── KIE Konseling ─────────────────────────────────────────────────
        st.markdown("#### 💬 Konseling Pasien / Keluarga (KIE)")

        kie_template_pilih = st.selectbox(
            "Template KIE (opsional — pilih untuk prefill):",
            ["— Tulis manual —"] + list(KIE_TEMPLATE.keys()),
            key="fm_kie_template",
        )

        prefill_kie = ""
        if kie_template_pilih != "— Tulis manual —":
            prefill_kie = KIE_TEMPLATE[kie_template_pilih]

        kie_content = st.text_area(
            "Materi Konseling yang Diberikan:",
            value=prefill_kie,
            height=130,
            key="fm_kie_content",
            placeholder="Penjelasan manfaat obat, cara minum, efek samping yang perlu diwaspadai...",
        )
        st.session_state["fm_kie"] = kie_content

        # Pemahaman pasien
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            pemahaman = st.select_slider(
                "Tingkat pemahaman pasien/keluarga:",
                options=["Tidak paham", "Kurang paham", "Cukup paham", "Paham", "Sangat paham"],
                value="Cukup paham",
                key="fm_pemahaman",
            )
        with col_p2:
            media_kie = st.multiselect(
                "Media KIE yang digunakan:",
                ["Lisan", "Leaflet", "Lembar informasi", "Video", "Demonstrasi langsung"],
                default=["Lisan"],
                key="fm_media_kie",
            )
        # NOTE: fm_pemahaman & fm_media_kie sudah otomatis tersimpan ke
        # session_state lewat key widget masing-masing — tidak perlu ditulis
        # ulang manual (menyebabkan StreamlitAPIException jika dilakukan).

    # =====================================================================
    # TAB 5 — MONITORING & SIMPAN
    # =====================================================================
    with tab_simpan:
        st.subheader("📊 Review & Simpan Catatan Farmasi ke CPPT")

        # ── Auto-generate SOAP ────────────────────────────────────────────
        home_meds    = st.session_state.get("fm_home_meds", [])
        drp_list     = st.session_state.get("fm_drp_list", [])
        interactions = st.session_state.get("fm_interactions", [])
        discrepancy  = st.session_state.get("fm_discrepancy", "")
        monitoring   = st.session_state.get("fm_monitoring_param", "")
        kie          = st.session_state.get("fm_kie", "")

        # S — riwayat obat & keluhan terkait medikasi
        soap_s_lines = ["Visite farmasi klinik. "]
        if home_meds:
            soap_s_lines.append(
                f"Home medication: {', '.join(m['nama'] for m in home_meds if m.get('nama'))}."
            )
        alergi = st.session_state.get("fm_alergi", "")
        if alergi:
            soap_s_lines.append(f"Riwayat alergi: {alergi}.")
        soap_s_auto = " ".join(soap_s_lines)

        # O — data rekonsiliasi & CPOE
        soap_o_lines = []
        cpoe_obat = _get_cpoe_obat(episode_id)
        if cpoe_obat:
            soap_o_lines.append(
                f"Order obat aktif (CPOE): {len(cpoe_obat)} item — "
                + ", ".join(o.get("nama_order", "") for o in cpoe_obat[:5])
                + ("..." if len(cpoe_obat) > 5 else "")
            )
        if discrepancy:
            soap_o_lines.append(f"Rekonsiliasi: {discrepancy}")
        if interactions:
            soap_o_lines.append(
                f"Drug interaction check: {len(interactions)} pasangan ditemukan "
                f"({sum(1 for i in interactions if 'Kontraindikasi' in i['severity'] or 'Mayor' in i['severity'])} "
                f"kontraindikasi/mayor)."
            )
        soap_o_auto = "\n".join(soap_o_lines) if soap_o_lines else "Tidak ada temuan bermakna."

        # A — DRP
        if drp_list:
            soap_a_auto = f"Drug Related Problem (DRP) — {len(drp_list)} temuan:\n"
            for i, drp in enumerate(drp_list, 1):
                soap_a_auto += (
                    f"{i}. {drp['nama_obat']}: {drp['problem']} "
                    f"[{drp['cause']}] → Status: {drp['status']}\n"
                )
        else:
            soap_a_auto = "Tidak ditemukan Drug Related Problem yang bermakna pada visite ini."

        # P — rekomendasi & monitoring
        soap_p_lines = []
        rekom_drp = [d for d in drp_list if d.get("rekomendasi")]
        if rekom_drp:
            soap_p_lines.append("Rekomendasi ke DPJP:")
            for d in rekom_drp:
                soap_p_lines.append(f"- {d['nama_obat']}: {d['rekomendasi']}")
        if monitoring:
            soap_p_lines.append(f"\nParameter monitoring:\n{monitoring}")
        if kie:
            pemahaman  = st.session_state.get("fm_pemahaman", "")
            media_kie  = st.session_state.get("fm_media_kie", [])
            soap_p_lines.append(
                f"\nKIE diberikan kepada pasien/keluarga ({', '.join(media_kie)}). "
                f"Tingkat pemahaman: {pemahaman}."
            )
        disp_status = st.session_state.get("fm_dispensing_status", {})
        belum = [k for k, v in disp_status.items() if "belum" in v.lower() or "sedang" in v.lower()]
        if belum:
            soap_p_lines.append(f"\nObat pending dispensing: {', '.join(belum)}")
        soap_p_auto = "\n".join(soap_p_lines) if soap_p_lines else "Tidak ada rencana khusus."

        # ── Edit final ────────────────────────────────────────────────────
        st.markdown("#### ✏️ Review & Edit Sebelum Disimpan")

        # Riwayat alergi (di simpan dulu sebelum dipakai di S)
        fm_alergi = st.text_input(
            "Riwayat Alergi Obat:",
            key="fm_alergi",
            placeholder="Penisilin (rash), Sulfa (anafilaksis), NSAID (bronkospasme)...",
        )

        col_so, col_ap = st.columns(2)
        with col_so:
            final_s = st.text_area("S — Subjektif (riwayat medikasi):",
                                   value=soap_s_auto, height=110, key="fm_final_s")
            final_o = st.text_area("O — Objektif (rekonsiliasi & CPOE):",
                                   value=soap_o_auto, height=140, key="fm_final_o")
        with col_ap:
            final_a = st.text_area("A — Assessment (DRP):",
                                   value=soap_a_auto, height=110, key="fm_final_a")
            final_p = st.text_area("P — Plan (rekomendasi & monitoring):",
                                   value=soap_p_auto, height=140, key="fm_final_p")

        waktu_catatan = st.text_input(
            "⏰ Waktu Catatan:",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            key="fm_waktu_catatan",
        )

        st.markdown("---")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button(
                "💾 Simpan Permanen ke CPPT",
                type="primary",
                use_container_width=True,
                key="fm_btn_simpan",
            ):
                record_id = save_cppt_record(
                    episode_id=episode_id,
                    ppa_role="Apoteker",
                    ppa_nama=nama_lengkap or user_id,
                    soap_s=final_s,
                    soap_o=final_o,
                    soap_a=final_a,
                    soap_p=final_p,
                    waktu_catatan=waktu_catatan + ":00",
                )
                if record_id:
                    st.success(
                        f"✅ Catatan Farmasi tersimpan ke CPPT (ID #{record_id}) — "
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                    st.balloons()
                    time.sleep(0.8)
                    st.rerun()

        with col_btn2:
            if st.button(
                "🔄 Reset Semua Data Farmasi",
                use_container_width=True,
                key="fm_btn_reset",
            ):
                keys_to_clear = [k for k in st.session_state if k.startswith("fm_")]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()


main()
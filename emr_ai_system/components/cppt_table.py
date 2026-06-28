"""
Komponen Tabel CPPT Universal — Multi-PPA
File: components/cppt_table.py

Tabel CPPT standar RS: setiap baris = 1 catatan PPA (Dokter/Perawat/Gizi/Apoteker).
Komponen ini HANYA mengelola tampilan & penyimpanan tabel CPPT,
tidak berisi logik CDSS (tetap di halaman masing-masing PPA).

CARA PAKAI di main_app():
    from components.cppt_table import render_cppt_table, render_input_ppa
    render_cppt_table(episode_id)
    render_input_ppa(episode_id, role, user_id, nama_lengkap)
"""

import sqlite3
import streamlit as st
import pandas as pd
from datetime import datetime
from contextlib import contextmanager

# ── Konstanta ─────────────────────────────────────────────────────────────────

DB_PATH = "rsjpdhk_emr.db"

# Warna badge per PPA (untuk tampilan tabel)
PPA_CONFIG = {
    "Dokter":    {"icon": "👨‍⚕️", "color": "#1a6fc4", "label": "Dokter"},
    "Perawat":   {"icon": "👩‍⚕️", "color": "#0f9c6a", "label": "Perawat"},
    "Gizi":      {"icon": "🥗",   "color": "#d97706", "label": "Gizi / Dietisien"},
    "Apoteker":  {"icon": "💊",   "color": "#7c3aed", "label": "Apoteker / Farmasi"},
}

# Alias ikon & grup per profesi — dipakai oleh pages/6___CPPT_Terintegrasi.py
# untuk menampilkan ikon dan label grup PPA di tabel terintegrasi.
_PROFESI_ICON = {role: cfg["icon"] for role, cfg in PPA_CONFIG.items()}

_PROFESI_GRUP = {
    "Dokter":   "Medis",
    "Perawat":  "Keperawatan",
    "Gizi":     "Penunjang Gizi",
    "Apoteker": "Penunjang Farmasi",
}

KOLOM_TABEL = [
    "Waktu", "PPA", "S (Subjektif)", "O (Objektif)",
    "A (Assessment)", "P (Plan)", "Dibuat Oleh", "Verifikasi"
]


# ── Database ──────────────────────────────────────────────────────────────────
# CATATAN SKEMA: tabel `cppt_records` di rsjpdhk_emr.db memakai kolom
# tgl_jam / grup / ruangan / notasi_dpjp / verified / created_at.
# (Versi lama komponen ini memakai nama kolom yang berbeda — waktu_catatan /
#  verifikasi / dibuat_pada — yang TIDAK PERNAH cocok dengan tabel sungguhan,
#  sehingga setiap penyimpanan CPPT selalu gagal dengan "no such column".
#  Nama parameter publik (mis. `waktu_catatan` di save_cppt_record) tetap
#  dipertahankan agar seluruh pemanggil yang sudah ada — Farmasi Klinik,
#  Gizi Klinik, dll — tidak perlu diubah.)

@contextmanager
def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_cppt_table() -> None:
    """Buat tabel cppt_records jika belum ada (skema sesuai DB produksi)."""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cppt_records (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id    TEXT    NOT NULL,
                tgl_jam       TEXT    NOT NULL,
                ppa_role      TEXT    NOT NULL,
                ppa_nama      TEXT    NOT NULL,
                grup          TEXT    NOT NULL DEFAULT '',
                ruangan       TEXT    NOT NULL DEFAULT '',
                soap_s        TEXT    NOT NULL DEFAULT '',
                soap_o        TEXT    NOT NULL DEFAULT '',
                soap_a        TEXT    NOT NULL DEFAULT '',
                soap_p        TEXT    NOT NULL DEFAULT '',
                notasi_dpjp   TEXT    NOT NULL DEFAULT '',
                verified      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cppt_episode
            ON cppt_records(episode_id, tgl_jam DESC)
        """)


def save_cppt_record(
    episode_id: str,
    ppa_role: str,
    ppa_nama: str,
    soap_s: str = "",
    soap_o: str = "",
    soap_a: str = "",
    soap_p: str = "",
    waktu_catatan: str = None,
    grup: str = "",
    ruangan: str = None,
    notasi_dpjp: str = "",
) -> int | None:
    """
    Simpan satu baris catatan CPPT ke database.

    `waktu_catatan` ditulis ke kolom `tgl_jam` (nama parameter dipertahankan
    demi kompatibilitas dengan pemanggil yang sudah ada). `grup` dan
    `ruangan` otomatis terisi dari profesi PPA / pasien aktif bila tidak
    diberikan secara eksplisit.

    Returns: id record baru, atau None jika gagal.
    """
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tgl_jam = waktu_catatan or now
        if not grup:
            grup = _PROFESI_GRUP.get(ppa_role, "")
        if ruangan is None:
            ruangan = st.session_state.get("pasien_ruangan", "")
        with _get_db() as conn:
            cur = conn.execute(
                """INSERT INTO cppt_records
                   (episode_id, tgl_jam, ppa_role, ppa_nama,
                    grup, ruangan, soap_s, soap_o, soap_a, soap_p, notasi_dpjp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (episode_id, tgl_jam, ppa_role, ppa_nama,
                 grup, ruangan, soap_s, soap_o, soap_a, soap_p, notasi_dpjp),
            )
            return cur.lastrowid
    except Exception as e:
        st.error(f"❌ Gagal menyimpan CPPT: {e}")
        return None


def get_cppt_records(episode_id: str) -> list[dict]:
    """Ambil semua catatan CPPT untuk 1 episode, urut waktu terbaru."""
    try:
        with _get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM cppt_records
                   WHERE episode_id = ?
                   ORDER BY tgl_jam DESC""",
                (episode_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def toggle_verifikasi(record_id: int, status: bool) -> None:
    """Set status verifikasi (paraf digital) pada satu record."""
    with _get_db() as conn:
        conn.execute(
            "UPDATE cppt_records SET verified = ? WHERE id = ?",
            (1 if status else 0, record_id)
        )


def set_verified(record_id: int, episode_id: str = None) -> None:
    """
    Tandai 1 record CPPT sebagai terverifikasi (paraf digital DPJP).
    Dipakai oleh pages/6___CPPT_Terintegrasi.py. `episode_id` tidak
    dipakai untuk query (record sudah unik via `record_id`) — parameter
    ini hanya dipertahankan agar tanda tangan fungsi sesuai pemanggilnya.
    """
    toggle_verifikasi(record_id, True)


def delete_cppt_record(record_id: int) -> None:
    """Hapus 1 record (hanya untuk admin / testing)."""
    with _get_db() as conn:
        conn.execute("DELETE FROM cppt_records WHERE id = ?", (record_id,))


# ── Render Tabel ──────────────────────────────────────────────────────────────

def _badge_ppa(role: str) -> str:
    cfg = PPA_CONFIG.get(role, {"icon": "👤", "color": "#666", "label": role})
    return (
        f"<span style='background:{cfg['color']};color:white;"
        f"padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600'>"
        f"{cfg['icon']} {cfg['label']}</span>"
    )


def render_cppt_table(episode_id: str, role_filter: str = "Semua") -> None:
    """
    Render tabel CPPT universal untuk 1 episode.
    Dipanggil dari main_app() setelah header pasien.

    Args:
        episode_id:   ID episode aktif
        role_filter:  "Semua" | "Dokter" | "Perawat" | "Gizi" | "Apoteker"
    """
    init_cppt_table()

    st.markdown("### 📋 Catatan Perkembangan Pasien Terintegrasi")

    # ── Filter controls ───────────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
    with col_f1:
        filter_ppa = st.selectbox(
            "Filter PPA:",
            ["Semua", "Dokter", "Perawat", "Gizi", "Apoteker"],
            index=["Semua", "Dokter", "Perawat", "Gizi", "Apoteker"].index(role_filter)
            if role_filter in ["Semua", "Dokter", "Perawat", "Gizi", "Apoteker"] else 0,
            key="cppt_table_filter_ppa",
        )
    with col_f2:
        tampilan = st.selectbox(
            "Tampilan:",
            ["Ringkas (tabel)", "Detail (per baris)"],
            key="cppt_table_view_mode",
        )
    with col_f3:
        st.caption(f"Episode aktif: `{episode_id}`")

    # ── Ambil data ────────────────────────────────────────────────────────────
    records = get_cppt_records(episode_id)

    if filter_ppa != "Semua":
        records = [r for r in records if r["ppa_role"] == filter_ppa]

    if not records:
        st.info(
            "📭 Belum ada catatan CPPT untuk episode ini. "
            "Gunakan form di bawah untuk menambahkan catatan."
        )
        return

    st.caption(f"Total catatan: **{len(records)}** entri")

    # ── Mode Ringkas: DataFrame ───────────────────────────────────────────────
    if "Ringkas" in tampilan:
        df_data = []
        for r in records:
            cfg = PPA_CONFIG.get(r["ppa_role"], {"icon": "👤"})
            df_data.append({
                "Waktu":       (r.get("tgl_jam") or "")[:16],
                "PPA":         f"{cfg['icon']} {r['ppa_role']}",
                "Nama":        r["ppa_nama"],
                "S":           (r["soap_s"] or "")[:80] + ("…" if len(r["soap_s"] or "") > 80 else ""),
                "O":           (r["soap_o"] or "")[:80] + ("…" if len(r["soap_o"] or "") > 80 else ""),
                "A":           (r["soap_a"] or "")[:80] + ("…" if len(r["soap_a"] or "") > 80 else ""),
                "P":           (r["soap_p"] or "")[:80] + ("…" if len(r["soap_p"] or "") > 80 else ""),
                "Verifikasi":  "✅" if r["verified"] else "⏳",
            })
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Mode Detail: Expandable card per catatan ──────────────────────────────
    else:
        for r in records:
            cfg = PPA_CONFIG.get(r["ppa_role"], {"icon": "👤", "color": "#666", "label": r["ppa_role"]})
            label_exp = (
                f"{cfg['icon']} **{r['ppa_role']}** — {r['ppa_nama']} "
                f"| {(r.get('tgl_jam') or '')[:16]} "
                f"{'✅' if r['verified'] else '⏳'}"
            )
            with st.expander(label_exp):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**S (Subjektif)**")
                    st.markdown(r["soap_s"] or "_Tidak diisi_")
                    st.markdown(f"**A (Assessment)**")
                    st.markdown(r["soap_a"] or "_Tidak diisi_")
                with c2:
                    st.markdown(f"**O (Objektif)**")
                    st.markdown(r["soap_o"] or "_Tidak diisi_")
                    st.markdown(f"**P (Plan)**")
                    st.markdown(r["soap_p"] or "_Tidak diisi_")

                st.caption(
                    f"Dibuat: {r.get('created_at', '-')} | "
                    f"ID Record: #{r['id']}"
                )

                # Verifikasi (paraf digital)
                col_v, col_d = st.columns([3, 1])
                with col_v:
                    is_verified = bool(r["verified"])
                    new_val = st.checkbox(
                        "✅ Verifikasi / Paraf Digital",
                        value=is_verified,
                        key=f"verify_{r['id']}",
                    )
                    if new_val != is_verified:
                        toggle_verifikasi(r["id"], new_val)
                        st.rerun()
                with col_d:
                    # Tombol hapus hanya untuk admin
                    current_role = st.session_state.get("role", "")
                    if current_role == "Admin":
                        if st.button("🗑️ Hapus", key=f"del_{r['id']}", type="secondary"):
                            delete_cppt_record(r["id"])
                            st.success("Record dihapus.")
                            st.rerun()


# Alias — pages/6___CPPT_Terintegrasi.py mengimpor nama ini.
render_tabel_cppt = render_cppt_table


# ── Form Input Per PPA ────────────────────────────────────────────────────────

def render_input_ppa(
    episode_id: str,
    role: str,
    user_id: str,
    nama_lengkap: str,
) -> None:
    """
    Form input CPPT yang disesuaikan per role.
    Dipanggil dari main_app() setelah render_cppt_table().

    - Dokter: A & P klinis lengkap + link ke CPOE
    - Perawat: ringkas S/O + redirect ke CDSS
    - Gizi: form nutrisi + A/P diet
    - Apoteker: rekonsiliasi obat + konseling
    """
    init_cppt_table()

    cfg = PPA_CONFIG.get(role, {"icon": "👤", "label": role, "color": "#666"})

    st.markdown(
        f"<h4 style='color:{cfg['color']}'>"
        f"{cfg['icon']} Input Catatan — {cfg['label']}</h4>",
        unsafe_allow_html=True,
    )

    # ── DOKTER ────────────────────────────────────────────────────────────────
    if role == "Dokter":
        _form_dokter(episode_id, user_id, nama_lengkap)

    # ── PERAWAT ───────────────────────────────────────────────────────────────
    elif role == "Perawat":
        _form_perawat(episode_id, user_id, nama_lengkap)

    # ── GIZI ──────────────────────────────────────────────────────────────────
    elif role == "Gizi":
        _form_gizi(episode_id, user_id, nama_lengkap)

    # ── APOTEKER ──────────────────────────────────────────────────────────────
    elif role == "Apoteker":
        _form_apoteker(episode_id, user_id, nama_lengkap)

    # ── Role tidak dikenal ────────────────────────────────────────────────────
    else:
        st.info(f"ℹ️ Role `{role}` belum dikonfigurasi untuk input CPPT mandiri.")


# ── Sub-form per PPA ──────────────────────────────────────────────────────────

def _form_dokter(episode_id: str, user_id: str, nama_lengkap: str) -> None:
    """Form CPPT untuk Dokter — fokus pada A & P klinis medis."""

    # Tarik pre-fill dari bridge (jika CDSS CPOE sudah push ke session)
    prefill_a = st.session_state.pop("soap_A", "")
    prefill_p = st.session_state.pop("soap_P", "")

    # Tarik diagnosa aktif dari sesi dokter (diset oleh CPOE page)
    diagnosa_aktif = st.session_state.get("diagnosa_aktif", [])
    if diagnosa_aktif:
        with st.expander("🩺 Diagnosa Aktif (dari CPOE)", expanded=True):
            for dx in diagnosa_aktif:
                tipe_icon = "🔴" if dx.get("tipe") == "Diagnosis Utama" else "◦"
                st.markdown(
                    f"{tipe_icon} `{dx.get('kode_icd10', '-')}` — "
                    f"{dx.get('nama_penyakit', '-')} ({dx.get('tipe', '-')})"
                )

    # Tarik CPOE orders ringkas
    cpoe_orders = st.session_state.get("cpoe_orders", [])
    if cpoe_orders:
        with st.expander(f"📋 CPOE Orders ({len(cpoe_orders)} aktif)"):
            for o in cpoe_orders[:5]:
                st.caption(
                    f"• [{o.get('tipe','?')}] {o.get('nama_order','-')} "
                    f"— {o.get('status','-')}"
                )
            if len(cpoe_orders) > 5:
                st.caption(f"… dan {len(cpoe_orders)-5} order lainnya")

    with st.form("form_cppt_dokter", clear_on_submit=False):
        col_s, col_o = st.columns(2)
        with col_s:
            soap_s = st.text_area(
                "📋 S — Keluhan & Anamnesis",
                placeholder="Pasien mengeluh...",
                height=110,
                key="dokter_soap_s",
            )
        with col_o:
            soap_o = st.text_area(
                "📊 O — Pemeriksaan Fisik & Penunjang",
                placeholder="TTV: HR ... BP ... | Pemeriksaan...",
                height=110,
                key="dokter_soap_o",
            )

        soap_a = st.text_area(
            "🎯 A — Assessment / Diagnosis Klinis",
            value=prefill_a,
            placeholder="Diagnosis utama...\nKomorbiditas...",
            height=120,
            key="dokter_soap_a",
        )
        soap_p = st.text_area(
            "📝 P — Plan / Tata Laksana",
            value=prefill_p,
            placeholder="1. Medikamentosa: ...\n2. Prosedur: ...\n3. Monitoring: ...",
            height=120,
            key="dokter_soap_p",
        )

        waktu_input = st.text_input(
            "⏰ Waktu Catatan (default: sekarang)",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            key="dokter_waktu",
        )

        col_submit, col_cpoe = st.columns([2, 1])
        with col_submit:
            submitted = st.form_submit_button(
                "💾 Simpan Catatan Dokter ke CPPT",
                type="primary",
                use_container_width=True,
            )
        with col_cpoe:
            st.form_submit_button(
                "🏥 Buka CPOE →",
                on_click=lambda: st.switch_page("pages/2_👨‍⚕️_CPOE_Dokter.py"),
                use_container_width=True,
            )

    if submitted:
        if not soap_a.strip() and not soap_p.strip():
            st.warning("⚠️ Isi minimal kolom A atau P sebelum menyimpan.")
        else:
            record_id = save_cppt_record(
                episode_id=episode_id,
                ppa_role="Dokter",
                ppa_nama=nama_lengkap or user_id,
                soap_s=soap_s,
                soap_o=soap_o,
                soap_a=soap_a,
                soap_p=soap_p,
                waktu_catatan=waktu_input + ":00",
            )
            if record_id:
                st.success(f"✅ Catatan Dokter tersimpan (ID #{record_id})")
                st.rerun()


def _form_perawat(episode_id: str, user_id: str, nama_lengkap: str) -> None:
    """
    Form CPPT ringkas untuk Perawat.
    CDSS lengkap ada di halaman Perawat (CDSS Kompleks).
    Di sini hanya input S/O singkat + tarik hasil dari sesi CDSS.
    """
    st.info(
        "📎 Catatan asuhan lengkap (SDKI→SIKI→SLKI) ada di modul **CDSS Perawat**. "
        "Simpan hasil di sana, lalu kembali ke sini untuk finalisasi entri CPPT."
    )

    # Tarik hasil CDSS dari session jika ada
    prefill_a = st.session_state.get("soap_A", "")
    prefill_p = st.session_state.get("soap_P", "")
    prefill_s = st.session_state.get("s_text_area", "")
    prefill_o = st.session_state.get("o_text_area", "")

    if prefill_a or prefill_p:
        st.success("✅ Data dari modul CDSS Perawat telah terbaca — siap disimpan ke CPPT.")

    with st.form("form_cppt_perawat", clear_on_submit=False):
        col_s, col_o = st.columns(2)
        with col_s:
            soap_s = st.text_area(
                "📋 S — Keluhan Pasien",
                value=prefill_s,
                height=100,
                key="perwt_soap_s",
            )
        with col_o:
            soap_o = st.text_area(
                "📊 O — Observasi & TTV",
                value=prefill_o,
                height=100,
                key="perwt_soap_o",
            )

        soap_a = st.text_area(
            "🎯 A — Diagnosa Keperawatan (SDKI)",
            value=prefill_a,
            placeholder="D.0008 Penurunan Curah Jantung...",
            height=100,
            key="perwt_soap_a",
        )
        soap_p = st.text_area(
            "📝 P — Intervensi Keperawatan (SIKI)",
            value=prefill_p,
            placeholder="I.02075 Perawatan Jantung: ...",
            height=100,
            key="perwt_soap_p",
        )

        waktu_input = st.text_input(
            "⏰ Waktu Catatan",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            key="perwt_waktu",
        )

        col_sub, col_cdss = st.columns(2)
        with col_sub:
            submitted = st.form_submit_button(
                "💾 Simpan ke CPPT",
                type="primary",
                use_container_width=True,
            )
        with col_cdss:
            st.form_submit_button(
                "🧠 Buka CDSS Perawat →",
                use_container_width=True,
            )

    if submitted:
        record_id = save_cppt_record(
            episode_id=episode_id,
            ppa_role="Perawat",
            ppa_nama=nama_lengkap or user_id,
            soap_s=soap_s,
            soap_o=soap_o,
            soap_a=soap_a,
            soap_p=soap_p,
            waktu_catatan=waktu_input + ":00",
        )
        if record_id:
            # Bersihkan prefill setelah disimpan
            for k in ["soap_A", "soap_P", "s_text_area", "o_text_area"]:
                st.session_state.pop(k, None)
            st.success(f"✅ Catatan Perawat tersimpan (ID #{record_id})")
            st.rerun()


def _form_gizi(episode_id: str, user_id: str, nama_lengkap: str) -> None:
    """Form CPPT untuk Dietisien / Gizi Klinik."""

    with st.form("form_cppt_gizi", clear_on_submit=False):
        col_s, col_o = st.columns(2)
        with col_s:
            soap_s = st.text_area(
                "📋 S — Keluhan Gizi & Riwayat Makan",
                placeholder="Pasien mengeluh tidak nafsu makan...",
                height=100,
                key="gizi_soap_s",
            )
        with col_o:
            # O untuk gizi: antropometri & skrining nutrisi
            bb = st.number_input("BB (kg):", min_value=0.0, value=0.0, step=0.5, key="gizi_bb")
            tb = st.number_input("TB (cm):", min_value=0.0, value=0.0, step=0.5, key="gizi_tb")
            nrs = st.selectbox(
                "NRS 2002 Score:",
                ["0 — Tidak berisiko", "1 — Risiko rendah",
                 "2 — Risiko sedang", "3+ — Risiko tinggi / Malnutrisi"],
                key="gizi_nrs",
            )
            soap_o = (
                f"BB: {bb} kg | TB: {tb} cm | "
                f"IMT: {bb/(tb/100)**2:.1f} kg/m² | NRS 2002: {nrs}"
            ) if bb and tb else st.text_area(
                "📊 O — Data Antropometri & Lab",
                height=100, key="gizi_soap_o_manual"
            )

        soap_a = st.text_area(
            "🎯 A — Diagnosis Gizi",
            placeholder="NI-2.1 Asupan Oral Tidak Adekuat...\nNC-3.1 Berat Badan Kurang...",
            height=100,
            key="gizi_soap_a",
        )
        soap_p = st.text_area(
            "📝 P — Intervensi Diet & Monitoring",
            placeholder="Diet jantung 1700 kkal/hari, protein 1.2 g/kgBB...\nEdukasi: ...",
            height=100,
            key="gizi_soap_p",
        )

        waktu_input = st.text_input(
            "⏰ Waktu Catatan",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            key="gizi_waktu",
        )

        submitted = st.form_submit_button(
            "💾 Simpan Catatan Gizi ke CPPT",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        record_id = save_cppt_record(
            episode_id=episode_id,
            ppa_role="Gizi",
            ppa_nama=nama_lengkap or user_id,
            soap_s=soap_s,
            soap_o=soap_o if isinstance(soap_o, str) else str(soap_o),
            soap_a=soap_a,
            soap_p=soap_p,
            waktu_catatan=waktu_input + ":00",
        )
        if record_id:
            st.success(f"✅ Catatan Gizi tersimpan (ID #{record_id})")
            st.rerun()


def _form_apoteker(episode_id: str, user_id: str, nama_lengkap: str) -> None:
    """Form CPPT untuk Apoteker / Farmasi Klinik."""

    # Tarik CPOE orders obat dari sesi (dikirim oleh CPOE Dokter)
    cpoe_orders = [
        o for o in st.session_state.get("cpoe_orders", [])
        if o.get("tipe") == "obat"
    ]

    if cpoe_orders:
        with st.expander(f"💊 Order Obat dari Dokter ({len(cpoe_orders)} item) — perlu verifikasi"):
            for o in cpoe_orders:
                st.markdown(
                    f"- **{o.get('nama_order','-')}** | "
                    f"Dosis: {o.get('dosis','-')} | "
                    f"Rute: {o.get('rute','-')} | "
                    f"Status: `{o.get('status','-')}`"
                )

    with st.form("form_cppt_apoteker", clear_on_submit=False):
        soap_s = st.text_area(
            "📋 S — Keluhan & Riwayat Obat",
            placeholder="Riwayat alergi: ...\nObat rutin di rumah: ...",
            height=90,
            key="apt_soap_s",
        )

        col_o1, col_o2 = st.columns(2)
        with col_o1:
            rekonsiliasi = st.text_area(
                "📊 O — Rekonsiliasi Obat",
                placeholder="Obat masuk: ...\nObat sebelumnya: ...\nKeterangan perbedaan: ...",
                height=110,
                key="apt_rekonsiliasi",
            )
        with col_o2:
            interaksi = st.selectbox(
                "Drug Interaction Check:",
                ["Tidak ditemukan interaksi signifikan",
                 "Interaksi minor (perlu perhatian)",
                 "Interaksi mayor (perlu tindak lanjut)",
                 "Kontraindikasi ditemukan (harus stop/ganti)"],
                key="apt_interaksi",
            )
            soap_o = f"{rekonsiliasi}\n\nDrug Interaction: {interaksi}"

        soap_a = st.text_area(
            "🎯 A — Identifikasi DRP (Drug Related Problem)",
            placeholder="DRP-1: Dosis tidak sesuai...\nDRP-2: Duplikasi terapi...",
            height=90,
            key="apt_soap_a",
        )
        soap_p = st.text_area(
            "📝 P — Rekomendasi & Konseling",
            placeholder="1. Rekomendasi ke Dokter: ...\n2. Dispensing: ...\n3. KIE ke pasien: ...",
            height=90,
            key="apt_soap_p",
        )

        waktu_input = st.text_input(
            "⏰ Waktu Catatan",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            key="apt_waktu",
        )

        submitted = st.form_submit_button(
            "💾 Simpan Catatan Farmasi ke CPPT",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        record_id = save_cppt_record(
            episode_id=episode_id,
            ppa_role="Apoteker",
            ppa_nama=nama_lengkap or user_id,
            soap_s=soap_s,
            soap_o=soap_o,
            soap_a=soap_a,
            soap_p=soap_p,
            waktu_catatan=waktu_input + ":00",
        )
        if record_id:
            st.success(f"✅ Catatan Apoteker tersimpan (ID #{record_id})")
            st.rerun()

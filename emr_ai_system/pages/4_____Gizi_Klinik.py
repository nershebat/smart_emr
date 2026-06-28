"""
Halaman Gizi Klinik — Asuhan Nutrisi Berbasis Evidence
File: pages/4_🥗_Gizi_Klinik.py

Halaman mandiri untuk Dietisien / Ahli Gizi Klinik.
Form di cppt_table._form_gizi adalah versi ringkas (entry cepat dari dashboard).
Halaman ini menyediakan asesmen nutrisi lengkap:

ALUR:
  1. Guard: harus login + pasien aktif + role Gizi
  2. Header pasien + ringkasan catatan gizi sebelumnya
  3. Asesmen Nutrisi:
     - Skrining: NRS 2002 / MNA / MUST (pilih per kondisi)
     - Antropometri: BB, TB, LILA, IMT, IBW, % IBW
     - Kebutuhan energi: Harris-Benedict / Mifflin / Ireton-Jones
     - Lab nutri: albumin, prealbumin, Hb, TLC
  4. Diagnosis Gizi (terminologi IDNT / PES statement)
  5. Intervensi Diet: jenis diet, tekstur, rute, kebutuhan kkal+protein
  6. Monitoring & Evaluasi (ADIME format)
  7. Simpan ke CPPT universal

REFERENSI:
  - IDNT (International Dietetics & Nutrition Terminology)
  - NRS 2002 (Nutritional Risk Screening)
  - ESPEN Guidelines 2023
  - Konsensus PGIZIKLI (Perhimpunan Gizi Klinik Indonesia)
"""

import streamlit as st
import math
import time
import pandas as pd
from datetime import datetime

# ── Import path fix: cppt_table ada di modules/components/, bukan root components/
try:
    from components.cppt_table import save_cppt_record, get_cppt_records, init_cppt_table
except ImportError:
    from components.cppt_table import save_cppt_record, get_cppt_records, init_cppt_table


# ── Constants ─────────────────────────────────────────────────────────────────

DIAGNOSIS_GIZI_IDNT = {
    "NI": {
        "label": "NI — Asupan (Nutrition Intake)",
        "items": [
            ("NI-1.1", "Peningkatan kebutuhan energi"),
            ("NI-1.2", "Asupan energi tidak adekuat"),
            ("NI-1.3", "Kelebihan asupan energi"),
            ("NI-2.1", "Asupan oral tidak adekuat"),
            ("NI-2.2", "Asupan oral berlebih"),
            ("NI-2.3", "Asupan enteral tidak adekuat"),
            ("NI-2.4", "Asupan parenteral tidak adekuat"),
            ("NI-3.1", "Asupan cairan tidak adekuat"),
            ("NI-3.2", "Asupan cairan berlebih"),
            ("NI-4.1", "Asupan lemak berlebih"),
            ("NI-4.2", "Asupan lemak tidak adekuat"),
            ("NI-5.1", "Asupan protein tidak adekuat"),
            ("NI-5.2", "Asupan protein berlebih"),
            ("NI-5.3", "Asupan asam amino tidak adekuat"),
            ("NI-5.6.1", "Asupan vitamin A tidak adekuat"),
            ("NI-5.7.1", "Asupan zat besi tidak adekuat"),
            ("NI-5.8.1", "Asupan kalium tidak adekuat"),
            ("NI-5.10.1", "Asupan kalsium tidak adekuat"),
        ],
    },
    "NC": {
        "label": "NC — Klinis (Nutrition Clinical)",
        "items": [
            ("NC-1.1", "Kesulitan menelan / disfagia"),
            ("NC-1.2", "Kesulitan mengunyah / menggigit"),
            ("NC-1.3", "Gangguan fungsi GI"),
            ("NC-1.4", "Gangguan fungsi gastrointestinal"),
            ("NC-2.1", "Gangguan utilisasi nutrisi"),
            ("NC-2.2", "Perubahan nilai laboratorium terkait nutrisi"),
            ("NC-3.1", "Berat badan kurang / underweight"),
            ("NC-3.2", "Berat badan lebih / overweight"),
            ("NC-3.3", "Obesitas"),
            ("NC-3.4", "Penurunan berat badan yang tidak diinginkan"),
            ("NC-3.5", "Kenaikan berat badan yang tidak diinginkan"),
            ("NC-4.1", "Malnutrisi terkait penyakit (DRM)"),
        ],
    },
    "NB": {
        "label": "NB — Perilaku/Lingkungan (Nutrition Behavioral)",
        "items": [
            ("NB-1.1", "Pengetahuan gizi kurang"),
            ("NB-1.2", "Kepercayaan atau sikap yang salah tentang makanan"),
            ("NB-1.3", "Tidak siap mengubah perilaku makan"),
            ("NB-1.5", "Kurang patuh terhadap rekomendasi gizi"),
            ("NB-2.1", "Kemampuan persiapan makanan terbatas"),
            ("NB-2.2", "Keterbatasan akses makanan"),
        ],
    },
}

JENIS_DIET = [
    "Diet Jantung I (1500 kkal)",
    "Diet Jantung II (1700 kkal)",
    "Diet Jantung III (2000 kkal)",
    "Diet DM — ADA (sesuai kebutuhan)",
    "Diet Rendah Garam I (<200 mg Na/hari)",
    "Diet Rendah Garam II (<400 mg Na/hari)",
    "Diet Rendah Garam III (<600 mg Na/hari)",
    "Diet Rendah Protein (0.6 g/kgBB)",
    "Diet Tinggi Protein (1.5–2.0 g/kgBB)",
    "Diet Rendah Lemak (<30% total energi)",
    "Diet DASH",
    "Diet Pasca Operasi / Cair Penuh",
    "Diet Saring / Blenderisasi",
    "Diet Lunak",
    "Diet Biasa / TKTP",
    "Nutrisi Enteral (via NGT/OGT)",
    "Nutrisi Parenteral (TPN/PPN)",
    "Diet Khusus (sesuai kondisi — tulis manual)",
]

TEKSTUR_MAKANAN = [
    "Biasa",
    "Lunak",
    "Saring / Blenderisasi",
    "Cair penuh",
    "Cair jernih",
    "Puree (IDDSI Level 4)",
    "Minced & Moist (IDDSI Level 5)",
    "Soft & Bite-Sized (IDDSI Level 6)",
    "NPO (Puasa)",
]

RUTE_NUTRISI = [
    "Oral",
    "Enteral — NGT",
    "Enteral — OGT",
    "Enteral — PEG",
    "Enteral — NJ/NE",
    "Parenteral — Central (TPN)",
    "Parenteral — Perifer (PPN)",
    "Kombinasi Oral + Enteral",
    "Kombinasi Enteral + Parenteral",
]


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
    # UserRole.GIZI = "Ahli Gizi" (auth_system.py ln 31) — terima keduanya
    if role not in ("Gizi", "Ahli Gizi", "Admin"):
        st.error(f"❌ Halaman ini untuk Dietisien / Gizi Klinik. Role Anda: **{role}**")
        st.page_link("dashboard.py", label="⬅️ Kembali ke Dashboard", icon="🫀")
        st.stop()

    return {
        "episode_id":    st.session_state.get("episode_id", ""),
        "user_id":       st.session_state.get("user_id", ""),
        "nama_lengkap":  st.session_state.get("nama_lengkap", ""),
        "pasien_nama":   st.session_state.get("pasien_nama", ""),
        "pasien_no_rm":  st.session_state.get("pasien_no_rm", ""),
        "pasien_ruangan":st.session_state.get("pasien_ruangan", ""),
        "pasien_dpjp":   st.session_state.get("pasien_dpjp", ""),
    }


def _imt(bb: float, tb_cm: float) -> float | None:
    if bb > 0 and tb_cm > 0:
        return round(bb / (tb_cm / 100) ** 2, 1)
    return None


def _ibw_broca(tb_cm: float, jenis_kelamin: str) -> float:
    """IBW formula Broca."""
    base = tb_cm - 100
    if jenis_kelamin == "Perempuan":
        return round(base * 0.85, 1)
    return round(base * 0.90, 1)


def _harris_benedict(bb: float, tb_cm: float, usia: int, jk: str) -> float:
    """Harris-Benedict REE (kcal/hari)."""
    if jk == "Laki-laki":
        return round(66.5 + (13.75 * bb) + (5.003 * tb_cm) - (6.775 * usia), 0)
    return round(655.1 + (9.563 * bb) + (1.850 * tb_cm) - (4.676 * usia), 0)


def _mifflin_st_jeor(bb: float, tb_cm: float, usia: int, jk: str) -> float:
    """Mifflin-St Jeor REE (kcal/hari)."""
    if jk == "Laki-laki":
        return round((10 * bb) + (6.25 * tb_cm) - (5 * usia) + 5, 0)
    return round((10 * bb) + (6.25 * tb_cm) - (5 * usia) - 161, 0)


def _kategori_imt(imt: float, jk: str) -> tuple[str, str]:
    """Return (kategori, warna) berdasarkan IMT Asia Pasifik."""
    if imt < 18.5:
        return "Kurang (Underweight)", "🔵"
    elif imt < 23.0:
        return "Normal", "🟢"
    elif imt < 25.0:
        return "Lebih (Overweight)", "🟡"
    elif imt < 30.0:
        return "Obesitas I", "🟠"
    else:
        return "Obesitas II", "🔴"


def _nrs2002_score(skor_status: int, skor_penyakit: int, usia: int) -> tuple[int, str]:
    """Hitung NRS 2002 total dan interpretasi."""
    total = skor_status + skor_penyakit + (1 if usia >= 70 else 0)
    if total < 3:
        risk = "✅ Tidak berisiko malnutrisi — Re-skrining 1 minggu"
    elif total == 3:
        risk = "🟡 Risiko sedang — Buat rencana nutrisi"
    else:
        risk = "🔴 Berisiko tinggi malnutrisi — Intervensi nutrisi segera"
    return total, risk


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Gizi Klinik — Smart EMR",
        page_icon="🥗",
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

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("🥗 Gizi Klinik — Asuhan Nutrisi")
    st.caption(
        f"Pasien: **{ctx['pasien_nama']}** | "
        f"RM: `{ctx['pasien_no_rm']}` | "
        f"Episode: `{episode_id}`"
    )

    # ── Riwayat catatan gizi sebelumnya ───────────────────────────────────────
    prev_records = [
        r for r in get_cppt_records(episode_id)
        if r.get("ppa_role") == "Gizi"
    ]
    if prev_records:
        with st.expander(
            f"📋 Riwayat Catatan Gizi ({len(prev_records)} catatan sebelumnya)",
            expanded=False,
        ):
            df = pd.DataFrame([{
                "Waktu":  (r.get("tgl_jam") or "")[:16],
                "Oleh":   r.get("ppa_nama", "-"),
                "A (Diagnosis Gizi)": (r.get("soap_a") or "")[:120],
                "P (Intervensi)":     (r.get("soap_p") or "")[:120],
            } for r in prev_records])
            st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── TABS ──────────────────────────────────────────────────────────────────
    tab_asesmen, tab_diagnosis, tab_intervensi, tab_monitoring = st.tabs([
        "📏 Asesmen Nutrisi",
        "🔬 Diagnosis Gizi (IDNT)",
        "🍽️ Intervensi Diet",
        "📊 Monitoring & Simpan",
    ])

    # =====================================================================
    # TAB 1 — ASESMEN NUTRISI
    # =====================================================================
    with tab_asesmen:
        st.subheader("📏 Asesmen Nutrisi Lengkap")

        # ── Data demografis (ambil dari session, bisa override) ───────────
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            jk = st.selectbox(
                "Jenis Kelamin:",
                ["Laki-laki", "Perempuan"],
                index=0 if st.session_state.get("pasien_jk", "").startswith("L") else 1,
                key="gz_jk",
            )
        with col_d2:
            tgl_lahir_str = st.session_state.get("pasien_tgl_lahir", "")
            usia_default = 0
            if tgl_lahir_str:
                try:
                    tgl = datetime.strptime(tgl_lahir_str, "%Y-%m-%d")
                    usia_default = (datetime.now() - tgl).days // 365
                except Exception:
                    pass
            usia = st.number_input("Usia (tahun):", min_value=0, max_value=120,
                                   value=usia_default, key="gz_usia")
        with col_d3:
            diagnosis_medis = st.text_input(
                "Diagnosis Medis Utama:",
                value=st.session_state.get("pasien_diagnosis_medis", ""),
                key="gz_dx_medis",
                placeholder="STEMI, HF, CKD...",
            )

        st.markdown("---")

        # ── Antropometri ──────────────────────────────────────────────────
        st.markdown("#### 📐 Antropometri")
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        with col_a1:
            bb = st.number_input("BB Aktual (kg):", min_value=0.0, max_value=300.0,
                                 value=0.0, step=0.1, key="gz_bb")
        with col_a2:
            tb = st.number_input("TB (cm):", min_value=0.0, max_value=250.0,
                                 value=0.0, step=0.5, key="gz_tb")
        with col_a3:
            lila = st.number_input("LILA (cm):", min_value=0.0, max_value=50.0,
                                   value=0.0, step=0.1, key="gz_lila",
                                   help="Lingkar Lengan Atas — digunakan jika TB sulit diukur")
        with col_a4:
            bb_usual = st.number_input("BB Biasa (kg):", min_value=0.0, max_value=300.0,
                                       value=0.0, step=0.1, key="gz_bb_usual",
                                       help="BB sebelum sakit / 6 bulan lalu")

        # Kalkulasi otomatis
        imt_val = _imt(bb, tb)
        ibw_val = _ibw_broca(tb, jk) if tb > 0 else None
        pct_ibw = round((bb / ibw_val) * 100, 1) if ibw_val and bb > 0 else None
        pct_bb_loss = (
            round(((bb_usual - bb) / bb_usual) * 100, 1)
            if bb_usual > 0 and bb > 0 else None
        )

        if imt_val:
            kat_imt, ikon_imt = _kategori_imt(imt_val, jk)
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            col_r1.metric("IMT (kg/m²)", f"{imt_val}", f"{ikon_imt} {kat_imt}")
            col_r2.metric("IBW Broca (kg)", f"{ibw_val}" if ibw_val else "—",
                          f"{pct_ibw}% IBW" if pct_ibw else "")
            col_r3.metric("% Penurunan BB",
                          f"{pct_bb_loss}%" if pct_bb_loss else "—",
                          "⚠️ Bermakna" if pct_bb_loss and pct_bb_loss > 5 else "")
            col_r4.metric("LILA", f"{lila} cm" if lila > 0 else "—")

        st.markdown("---")

        # ── Skrining Nutrisi NRS 2002 ─────────────────────────────────────
        st.markdown("#### 🔍 Skrining Risiko Nutrisi — NRS 2002")
        st.caption("European Society for Parenteral and Enteral Nutrition (ESPEN)")

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            st.markdown("**Skor Status Nutrisi:**")
            skor_status = st.radio(
                "Status Nutrisi:",
                options=[
                    (0, "0 — Status gizi normal"),
                    (1, "1 — Penurunan BB >5% dalam 3 bulan ATAU asupan 50–75% kebutuhan"),
                    (2, "2 — Penurunan BB >5% dalam 2 bulan ATAU IMT 18.5–20.5 + kondisi umum buruk"),
                    (3, "3 — Penurunan BB >5% dalam 1 bulan (>15% dalam 3 bln) ATAU IMT <18.5 + kondisi buruk"),
                ],
                format_func=lambda x: x[1],
                key="gz_nrs_status",
            )[0]

        with col_n2:
            st.markdown("**Skor Keparahan Penyakit:**")
            skor_penyakit = st.radio(
                "Keparahan Penyakit:",
                options=[
                    (0, "0 — Kebutuhan nutrisi normal"),
                    (1, "1 — Fraktur panggul, kemoterapi, stroke, DM, PPOK"),
                    (2, "2 — Operasi besar abdomen, stroke berat, pneumonia, kanker hematologi"),
                    (3, "3 — Cedera kepala, transplantasi sumsum, ICU (APACHE >10)"),
                ],
                format_func=lambda x: x[1],
                key="gz_nrs_penyakit",
            )[0]

        nrs_total, nrs_interpretasi = _nrs2002_score(skor_status, skor_penyakit, usia)
        st.info(f"**NRS 2002 Total Score: {nrs_total}** — {nrs_interpretasi}")

        # Simpan ke session untuk dipakai tab lain
        st.session_state["gz_nrs_total"] = nrs_total
        st.session_state["gz_nrs_interp"] = nrs_interpretasi

        st.markdown("---")

        # ── Kebutuhan Energi ──────────────────────────────────────────────
        st.markdown("#### ⚡ Estimasi Kebutuhan Energi")

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            metode_energi = st.selectbox(
                "Metode Kalkulasi:",
                ["Harris-Benedict (1919)", "Mifflin-St Jeor (1990)",
                 "Ireton-Jones (ICU)", "Manual (tulis langsung)"],
                key="gz_metode_energi",
            )
            faktor_aktivitas = st.selectbox(
                "Faktor Aktivitas:",
                [("1.2", "1.2 — Bedrest total"),
                 ("1.3", "1.3 — Bedrest dengan gerak ringan"),
                 ("1.5", "1.5 — Ambulasi terbatas"),
                 ("1.7", "1.7 — Aktif (mobilisasi penuh)")],
                format_func=lambda x: x[1],
                key="gz_faktor_aktivitas",
            )[0]
            faktor_stres = st.selectbox(
                "Faktor Stres:",
                [("1.0", "1.0 — Tanpa stres"),
                 ("1.1", "1.1 — Operasi elektif / stres ringan"),
                 ("1.2", "1.2 — Infeksi sedang"),
                 ("1.3", "1.3 — Sepsis / operasi mayor"),
                 ("1.5", "1.5 — Luka bakar / trauma berat")],
                format_func=lambda x: x[1],
                key="gz_faktor_stres",
            )[0]

        with col_e2:
            if bb > 0 and tb > 0 and usia > 0 and "Manual" not in metode_energi:
                ree = (
                    _harris_benedict(bb, tb, usia, jk)
                    if "Harris" in metode_energi
                    else _mifflin_st_jeor(bb, tb, usia, jk)
                )
                tee = round(ree * float(faktor_aktivitas) * float(faktor_stres), 0)
                protein_kebutuhan = round(bb * 1.2, 1)

                st.metric("REE (Resting Energy Expenditure)", f"{ree:.0f} kkal/hari")
                st.metric("TEE (Total Energy Expenditure)", f"{tee:.0f} kkal/hari",
                          f"× {faktor_aktivitas} aktivitas × {faktor_stres} stres")
                st.metric("Estimasi Kebutuhan Protein", f"{protein_kebutuhan} g/hari",
                          "1.2 g/kgBB/hari (standar umum)")

                st.session_state["gz_tee_calc"] = tee
                st.session_state["gz_protein_calc"] = protein_kebutuhan
            else:
                tee_manual = st.number_input("Kebutuhan Energi Manual (kkal/hari):",
                                             min_value=0, value=1800, step=50,
                                             key="gz_tee_manual")
                protein_manual = st.number_input("Kebutuhan Protein (g/hari):",
                                                 min_value=0.0, value=60.0, step=1.0,
                                                 key="gz_protein_manual")
                st.session_state["gz_tee_calc"] = tee_manual
                st.session_state["gz_protein_calc"] = protein_manual

        st.markdown("---")

        # ── Data Lab Nutrisi ──────────────────────────────────────────────
        st.markdown("#### 🧪 Data Laboratorium Nutrisional")
        col_l1, col_l2, col_l3, col_l4 = st.columns(4)
        with col_l1:
            albumin = st.number_input("Albumin (g/dL):", 0.0, 6.0, 0.0, 0.1, key="gz_albumin")
            if albumin > 0:
                kat = "Normal" if albumin >= 3.5 else ("Ringan" if albumin >= 3.0 else ("Sedang" if albumin >= 2.5 else "Berat"))
                st.caption(f"{'✅' if albumin >= 3.5 else '⚠️'} Hipoalbuminemia: {kat}" if albumin < 3.5 else "✅ Normal")
        with col_l2:
            hb = st.number_input("Hemoglobin (g/dL):", 0.0, 20.0, 0.0, 0.1, key="gz_hb")
        with col_l3:
            gds = st.number_input("GDS (mg/dL):", 0, 600, 0, 1, key="gz_gds")
        with col_l4:
            cholesterol = st.number_input("Kolesterol Total (mg/dL):", 0, 500, 0, 1, key="gz_chol")

        # Simpan semua nilai asesmen ke session
        st.session_state["gz_asesmen"] = {
            "jk": jk, "usia": usia, "bb": bb, "tb": tb, "lila": lila,
            "bb_usual": bb_usual, "imt": imt_val, "ibw": ibw_val,
            "pct_ibw": pct_ibw, "pct_bb_loss": pct_bb_loss,
            "nrs_total": nrs_total, "nrs_interp": nrs_interpretasi,
            "albumin": albumin, "hb": hb, "gds": gds, "cholesterol": cholesterol,
            "diagnosis_medis": diagnosis_medis,
        }

    # =====================================================================
    # TAB 2 — DIAGNOSIS GIZI
    # =====================================================================
    with tab_diagnosis:
        st.subheader("🔬 Diagnosis Gizi — Terminologi IDNT")
        st.caption(
            "Pilih diagnosis gizi menggunakan terminologi IDNT "
            "(International Dietetics & Nutrition Terminology). "
            "Format: **Problem** (P) → **Etiologi** (E) → **Signs & Symptoms** (S) = PES Statement."
        )

        selected_dx = []

        for domain_key, domain in DIAGNOSIS_GIZI_IDNT.items():
            with st.expander(f"**{domain['label']}**", expanded=(domain_key == "NC")):
                for kode, nama in domain["items"]:
                    if st.checkbox(f"`{kode}` — {nama}", key=f"gz_dx_{kode}"):
                        selected_dx.append({"kode": kode, "nama": nama})

        if selected_dx:
            st.markdown("---")
            st.markdown("#### ✍️ PES Statements")
            pes_statements = []
            for dx in selected_dx:
                st.markdown(f"**{dx['kode']} — {dx['nama']}**")
                col_p, col_e, col_s = st.columns(3)
                with col_p:
                    etiologi = st.text_input(
                        "Berkaitan dengan (Etiologi):",
                        key=f"gz_eti_{dx['kode']}",
                        placeholder="nafsu makan menurun, disfagia...",
                    )
                with col_e:
                    tanda = st.text_input(
                        "Dibuktikan oleh (Signs/Symptoms):",
                        key=f"gz_tanda_{dx['kode']}",
                        placeholder="asupan <60%, penurunan BB...",
                    )
                with col_s:
                    prioritas = st.selectbox(
                        "Prioritas:",
                        ["Utama", "Sekunder", "Tambahan"],
                        key=f"gz_prio_{dx['kode']}",
                    )
                pes = (
                    f"{dx['kode']} {dx['nama']}"
                    + (f" berkaitan dengan {etiologi}" if etiologi else "")
                    + (f" dibuktikan oleh {tanda}" if tanda else "")
                )
                pes_statements.append({"pes": pes, "prioritas": prioritas})
                st.caption(f"📝 PES: *{pes}*")

            st.session_state["gz_pes_statements"] = pes_statements
            st.session_state["gz_selected_dx"]    = selected_dx
        else:
            st.info("ℹ️ Pilih minimal satu diagnosis gizi di atas.")
            st.session_state["gz_pes_statements"] = []
            st.session_state["gz_selected_dx"]    = []

    # =====================================================================
    # TAB 3 — INTERVENSI DIET
    # =====================================================================
    with tab_intervensi:
        st.subheader("🍽️ Rencana Intervensi Gizi")

        tee   = st.session_state.get("gz_tee_calc", 1800)
        prot  = st.session_state.get("gz_protein_calc", 60.0)

        col_i1, col_i2 = st.columns(2)
        with col_i1:
            jenis_diet_pilih = st.selectbox("Jenis Diet:", JENIS_DIET, key="gz_jenis_diet")
            tekstur_pilih    = st.selectbox("Tekstur / Konsistensi:", TEKSTUR_MAKANAN, key="gz_tekstur")
            rute_pilih       = st.selectbox("Rute Pemberian:", RUTE_NUTRISI, key="gz_rute")

        with col_i2:
            energi_order = st.number_input(
                "Energi yang Diorder (kkal/hari):",
                min_value=0, value=int(tee), step=50, key="gz_energi_order",
                help=f"Estimasi TEE: {tee:.0f} kkal/hari",
            )
            protein_order = st.number_input(
                "Protein yang Diorder (g/hari):",
                min_value=0.0, value=float(prot), step=1.0, key="gz_protein_order",
            )
            cairan_order = st.number_input(
                "Cairan (mL/hari):",
                min_value=0, value=1500, step=100, key="gz_cairan_order",
            )

        st.markdown("---")

        # Suplemen / Formula enteral
        with st.expander("➕ Suplemen / Formula Enteral (opsional)"):
            supp_nama = st.text_input(
                "Nama Formula/Suplemen:", key="gz_supp_nama",
                placeholder="Ensure, Peptamen, Fresubin...",
            )
            supp_vol  = st.number_input("Volume (mL/hari):", 0, 3000, 0, 50, key="gz_supp_vol")
            supp_frek = st.text_input("Frekuensi:", key="gz_supp_frek",
                                      placeholder="3x/hari, continuous drip 40 mL/jam...")

        # Edukasi gizi
        st.markdown("#### 📚 Edukasi Gizi")
        edukasi = st.text_area(
            "Materi Edukasi yang Diberikan:",
            height=90,
            key="gz_edukasi",
            placeholder=(
                "Penjelasan diet jantung, pembatasan natrium & lemak jenuh, "
                "anjuran konsumsi buah & sayur, pantangan makanan..."
            ),
        )

        # Simpan ke session
        st.session_state["gz_intervensi"] = {
            "jenis_diet": jenis_diet_pilih,
            "tekstur":    tekstur_pilih,
            "rute":       rute_pilih,
            "energi":     energi_order,
            "protein":    protein_order,
            "cairan":     cairan_order,
            "suplemen":   f"{supp_nama} {supp_vol}mL/hari {supp_frek}".strip() if supp_nama else "",
            "edukasi":    edukasi,
        }

    # =====================================================================
    # TAB 4 — MONITORING & SIMPAN
    # =====================================================================
    with tab_monitoring:
        st.subheader("📊 Monitoring, Evaluasi & Simpan ke CPPT")

        # ── Auto-generate SOAP dari data yang sudah diisi ─────────────────
        asesmen  = st.session_state.get("gz_asesmen", {})
        interv   = st.session_state.get("gz_intervensi", {})
        pes_list = st.session_state.get("gz_pes_statements", [])

        # S
        soap_s_auto = (
            f"Keluhan gizi: nafsu makan {'menurun' if asesmen.get('bb_usual', 0) > asesmen.get('bb', 0) else 'cukup'}. "
            f"Dx medis: {asesmen.get('diagnosis_medis', '-')}. "
            f"Riwayat BB: BB biasa {asesmen.get('bb_usual', '-')} kg → BB kini {asesmen.get('bb', '-')} kg."
        )

        # O
        soap_o_lines = []
        if asesmen.get("bb"):
            soap_o_lines.append(
                f"BB: {asesmen['bb']} kg | TB: {asesmen.get('tb', '-')} cm | "
                f"IMT: {asesmen.get('imt', '-')} kg/m² ({_kategori_imt(asesmen['imt'], asesmen.get('jk', 'Laki-laki'))[0] if asesmen.get('imt') else '-'})"
            )
        if asesmen.get("nrs_total") is not None:
            soap_o_lines.append(f"NRS 2002: {asesmen['nrs_total']} — {asesmen.get('nrs_interp', '')}")
        if asesmen.get("albumin"):
            soap_o_lines.append(f"Albumin: {asesmen['albumin']} g/dL | Hb: {asesmen.get('hb', '-')} g/dL")
        if asesmen.get("pct_bb_loss"):
            soap_o_lines.append(f"Penurunan BB: {asesmen['pct_bb_loss']}% dari BB biasa")
        soap_o_auto = "\n".join(soap_o_lines)

        # A
        soap_a_auto = "Diagnosis Gizi (IDNT):\n"
        if pes_list:
            for p in pes_list:
                soap_a_auto += f"[{p['prioritas']}] {p['pes']}\n"
        else:
            soap_a_auto += "— (belum dipilih di tab Diagnosis Gizi)\n"

        # P
        soap_p_auto = ""
        if interv:
            soap_p_auto = (
                f"Jenis Diet: {interv.get('jenis_diet', '-')}\n"
                f"Tekstur: {interv.get('tekstur', '-')}\n"
                f"Rute: {interv.get('rute', '-')}\n"
                f"Energi: {interv.get('energi', '-')} kkal/hari | "
                f"Protein: {interv.get('protein', '-')} g/hari | "
                f"Cairan: {interv.get('cairan', '-')} mL/hari\n"
            )
            if interv.get("suplemen"):
                soap_p_auto += f"Suplemen: {interv['suplemen']}\n"
            if interv.get("edukasi"):
                soap_p_auto += f"Edukasi: {interv['edukasi']}\n"

        # ── Edit final sebelum simpan ─────────────────────────────────────
        st.markdown("#### ✏️ Review & Edit Narasi CPPT Sebelum Disimpan")
        st.caption("Narasi di-generate otomatis dari asesmen. Edit sesuai kebutuhan.")

        col_s_o, col_a_p = st.columns(2)
        with col_s_o:
            final_s = st.text_area("S — Subjektif:",     value=soap_s_auto, height=120, key="gz_final_s")
            final_o = st.text_area("O — Objektif:",      value=soap_o_auto, height=150, key="gz_final_o")
        with col_a_p:
            final_a = st.text_area("A — Diagnosis Gizi:", value=soap_a_auto, height=120, key="gz_final_a")
            final_p = st.text_area("P — Intervensi:",    value=soap_p_auto, height=150, key="gz_final_p")

        st.markdown("---")

        # ── Monitoring plan ───────────────────────────────────────────────
        st.markdown("#### 🔄 Rencana Monitoring")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            monitoring_bb   = st.checkbox("Monitor BB harian", value=True, key="gz_mon_bb")
            monitoring_asup = st.checkbox("Monitor asupan makan 24 jam", value=True, key="gz_mon_asup")
            monitoring_lab  = st.checkbox("Cek lab nutrisional ulang", value=False, key="gz_mon_lab")
        with col_m2:
            monitoring_tgl  = st.date_input("Jadwal evaluasi ulang:", key="gz_mon_tgl")
            st.caption(
                "Kunjungan ulang: "
                + ("BB, " if monitoring_bb else "")
                + ("Asupan, " if monitoring_asup else "")
                + ("Lab, " if monitoring_lab else "")
                + f"pada {monitoring_tgl}"
            )

        waktu_catatan = st.text_input(
            "⏰ Waktu Catatan:",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            key="gz_waktu_catatan",
        )

        st.markdown("---")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button(
                "💾 Simpan Permanen ke CPPT",
                type="primary",
                use_container_width=True,
                key="gz_btn_simpan",
            ):
                if not final_a.strip():
                    st.warning("⚠️ Isi minimal kolom A (Diagnosis Gizi) sebelum menyimpan.")
                else:
                    record_id = save_cppt_record(
                        episode_id=episode_id,
                        ppa_role="Gizi",
                        ppa_nama=nama_lengkap or user_id,
                        soap_s=final_s,
                        soap_o=final_o,
                        soap_a=final_a,
                        soap_p=final_p,
                        waktu_catatan=waktu_catatan + ":00",
                    )
                    if record_id:
                        st.success(
                            f"✅ Catatan Gizi tersimpan ke CPPT (ID #{record_id}) — "
                            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        )
                        st.balloons()
                        time.sleep(0.8)
                        st.rerun()

        with col_btn2:
            if st.button(
                "🔄 Reset Form",
                use_container_width=True,
                key="gz_btn_reset",
            ):
                keys_to_clear = [k for k in st.session_state if k.startswith("gz_")]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()


main()
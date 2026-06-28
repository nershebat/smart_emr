"""
Halaman CPPT Terintegrasi — Catatan Perkembangan Pasien Lintas PPA
File: pages/6_📋_CPPT_Terintegrasi.py

Halaman baca-saja (semua profesi bisa akses) yang menampilkan seluruh
catatan CPPT dari semua PPA dalam satu tabel terintegrasi, persis
seperti tampilan EMR RSJPDHK pada foto referensi.

ALUR:
  1. Guard: harus login + pasien aktif (semua role boleh baca)
  2. Header pasien lengkap + ringkasan tanda vital terakhir
  3. Filter: per profesi, per tanggal, per status verifikasi
  4. Tabel CPPT terintegrasi (komponen dari components/cppt_table.py)
     Kolom: No · Verif. · Tgl/Jam · S · O · A · P ·
            Notasi DPJP · Ruangan · Grup · Profesi · Insert By
  5. Detail view: klik baris → expand SOAP lengkap
  6. Ekspor CSV

CATATAN:
  - Penulisan catatan dilakukan di masing-masing halaman profesi
    (dashboard Perawat, CPOE Dokter, Farmasi, Gizi, dll)
  - Halaman ini murni read + verifikasi, tidak ada form input
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from components.cppt_table import (
    get_cppt_records,
    render_tabel_cppt,
    set_verified,
    _PROFESI_ICON,
    _PROFESI_GRUP,
)


# ── Guard & session ───────────────────────────────────────────────────────────

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
        st.warning("⚠️ Belum ada pasien aktif. Pilih pasien di Dashboard terlebih dahulu.")
        st.page_link("dashboard.py", label="➡️ Pilih Pasien", icon="🫀")
        st.stop()

    return {
        "episode_id":    st.session_state.get("episode_id", ""),
        "role":          st.session_state.get("role", ""),
        "user_id":       st.session_state.get("user_id", ""),
        "nama_lengkap":  st.session_state.get("nama_lengkap", ""),
        "pasien_nama":   st.session_state.get("pasien_nama", "-"),
        "pasien_no_rm":  st.session_state.get("pasien_no_rm", "-"),
        "pasien_ruangan":st.session_state.get("pasien_ruangan", "-"),
        "pasien_dpjp":   st.session_state.get("pasien_dpjp", "-"),
        "pasien_tgl_lahir": st.session_state.get("pasien_tgl_lahir", "-"),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_tgl(tgl_str: str) -> date | None:
    """Parse tgl_jam string ke date object untuk filter."""
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(tgl_str, fmt).date()
        except ValueError:
            continue
    return None


def _filter_records(
    records: list[dict],
    profesi_filter: list[str],
    date_start: date,
    date_end: date,
    verif_filter: str,
) -> list[dict]:
    out = []
    for r in records:
        # Filter profesi
        if profesi_filter and r.get("ppa_role") not in profesi_filter:
            continue
        # Filter tanggal
        tgl = _parse_tgl(r.get("tgl_jam", ""))
        if tgl and not (date_start <= tgl <= date_end):
            continue
        # Filter verifikasi
        if verif_filter == "Terverifikasi" and not r.get("verified"):
            continue
        if verif_filter == "Belum Diverifikasi" and r.get("verified"):
            continue
        out.append(r)
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ctx = _require_session()
    episode_id  = ctx["episode_id"]
    role        = ctx["role"]
    nama_user   = ctx["nama_lengkap"] or ctx["user_id"]

    st.set_page_config(
        page_title="CPPT Terintegrasi — Smart EMR RSJPDHK",
        page_icon="📋",
        layout="wide",
    )

    # ── Header ───────────────────────────────────────────────────────────────
    st.markdown("# 📋 Catatan Perkembangan Pasien Terintegrasi")

    col_p1, col_p2, col_p3, col_p4 = st.columns([2, 1.5, 1.5, 1])
    col_p1.markdown(
        f"**{ctx['pasien_nama']}**  \n"
        f"No. RM `{ctx['pasien_no_rm']}` · {ctx['pasien_tgl_lahir']}"
    )
    col_p2.markdown(
        f"🛌 **{ctx['pasien_ruangan']}**  \n"
        f"ID Episode: `{episode_id}`"
    )
    col_p3.markdown(
        f"👨‍⚕️ DPJP: **{ctx['pasien_dpjp'] or '-'}**"
    )
    with col_p4:
        st.page_link("dashboard.py", label="⬅️ Dashboard", icon="🫀")

    st.markdown("---")

    # ── Ambil semua records ───────────────────────────────────────────────────
    all_records = get_cppt_records(episode_id)

    # ── Sidebar filter ────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔍 Filter Catatan")

        # Filter profesi
        profesi_tersedia = sorted({r.get("ppa_role", "") for r in all_records if r.get("ppa_role")})
        profesi_filter = st.multiselect(
            "Profesi PPA:",
            options=profesi_tersedia,
            default=[],
            placeholder="Semua profesi",
            key="cppt_filter_profesi",
        )

        # Filter tanggal
        st.markdown("**Rentang Tanggal:**")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            date_start = st.date_input(
                "Dari:",
                value=date.today() - timedelta(days=7),
                key="cppt_date_start",
            )
        with col_d2:
            date_end = st.date_input(
                "Sampai:",
                value=date.today(),
                key="cppt_date_end",
            )

        # Filter verifikasi
        verif_filter = st.radio(
            "Status Verifikasi:",
            ["Semua", "Terverifikasi", "Belum Diverifikasi"],
            key="cppt_filter_verif",
        )

        st.markdown("---")

        # Ringkasan per profesi
        st.markdown("**📊 Ringkasan Catatan:**")
        if all_records:
            counts: dict[str, int] = {}
            for r in all_records:
                p = r.get("ppa_role", "?")
                counts[p] = counts.get(p, 0) + 1
            for p, c in sorted(counts.items()):
                icon = _PROFESI_ICON.get(p, "👤")
                st.write(f"{icon} {p}: **{c}** catatan")
        else:
            st.caption("Belum ada catatan.")

        st.markdown("---")
        st.caption(f"👤 {nama_user} · {role}")

    # ── Terapkan filter ───────────────────────────────────────────────────────
    records = _filter_records(
        all_records,
        profesi_filter=profesi_filter,
        date_start=date_start,
        date_end=date_end,
        verif_filter=verif_filter,
    )

    # ── Metric summary row ────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Catatan", len(all_records))
    m2.metric("Ditampilkan", len(records))
    m3.metric(
        "Terverifikasi",
        sum(1 for r in all_records if r.get("verified")),
    )
    m4.metric(
        "Belum Verifikasi",
        sum(1 for r in all_records if not r.get("verified")),
    )
    profesi_aktif = len({r.get("ppa_role") for r in all_records})
    m5.metric("Profesi PPA", profesi_aktif)

    st.markdown("---")

    if not records:
        st.info(
            "📭 Tidak ada catatan yang sesuai filter. "
            "Coba perluas rentang tanggal atau ubah filter profesi."
        )
        return

    # ── Tabel utama ───────────────────────────────────────────────────────────
    _COL_WIDTHS  = [0.30, 0.38, 0.65, 1.55, 1.55, 2.0, 2.15, 0.95, 0.65, 0.55, 0.75, 0.90]
    _COL_HEADERS = [
        "No", "Verif.", "Tgl/Jam",
        "Subjektif (S)", "Objektif (O)", "Asesmen (A)", "Perencanaan (P)",
        "Notasi DPJP", "Ruangan", "Grup", "Profesi", "Insert By",
    ]

    def _trunc(txt: str, n: int) -> str:
        txt = (txt or "").strip()
        return txt[:n] + "…" if len(txt) > n else txt

    # Header
    h_cols = st.columns(_COL_WIDTHS)
    for hc, ht in zip(h_cols, _COL_HEADERS):
        hc.markdown(f"<small><b>{ht}</b></small>", unsafe_allow_html=True)
    st.markdown(
        "<hr style='margin:2px 0 4px 0; border-color:#1565C0; border-width:2px;'>",
        unsafe_allow_html=True,
    )

    # Baris data
    for i, rec in enumerate(records, 1):
        role_rec = rec.get("ppa_role", "")
        icon     = _PROFESI_ICON.get(role_rec, "👤")
        v_key    = f"cppt_page_verif_{rec['id']}"
        exp_key  = f"cppt_page_expand_{rec['id']}"

        row = st.columns(_COL_WIDTHS)

        row[0].write(str(i))

        # Verifikasi — hanya Dokter yang bisa verifikasi
        with row[1]:
            if rec.get("verified"):
                st.success("✅")
            elif role in ("Dokter", "Admin"):
                if st.button("☑", key=v_key, help="Klik untuk verifikasi"):
                    set_verified(rec["id"], episode_id)
                    st.rerun()
            else:
                st.caption("—")

        row[2].caption(rec.get("tgl_jam", "-"))
        row[3].write(_trunc(rec.get("soap_s", "—"), 160))
        row[4].write(_trunc(rec.get("soap_o", "—"), 160))
        row[5].write(_trunc(rec.get("soap_a", "—"), 240))
        row[6].write(_trunc(rec.get("soap_p", "—"), 240))
        row[7].write(rec.get("notasi_dpjp", "") or "—")
        row[8].caption(rec.get("ruangan", "-"))
        row[9].caption(rec.get("grup", "-"))
        row[10].write(f"{icon} {role_rec}")
        row[11].caption(rec.get("ppa_nama", "-"))

        st.markdown(
            "<hr style='margin:2px 0 3px 0; border-color:#e0e0e0;'>",
            unsafe_allow_html=True,
        )

        # ── Detail Expander — SOAP lengkap ───────────────────────────────────
        with st.expander(
            f"🔍 Detail — {icon} {role_rec} · {rec.get('tgl_jam','')} · {rec.get('ppa_nama','')}",
            expanded=False,
        ):
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**📝 Subjektif (S)**")
                st.write(rec.get("soap_s", "—") or "—")
                st.markdown("**🔬 Asesmen (A)**")
                st.write(rec.get("soap_a", "—") or "—")
            with d2:
                st.markdown("**📊 Objektif (O)**")
                st.write(rec.get("soap_o", "—") or "—")
                st.markdown("**📋 Perencanaan (P)**")
                st.write(rec.get("soap_p", "—") or "—")
            if rec.get("notasi_dpjp"):
                st.info(f"📌 **Notasi DPJP:** {rec['notasi_dpjp']}")
            st.caption(
                f"Profesi: {role_rec} · Grup: {rec.get('grup','-')} · "
                f"Ruangan: {rec.get('ruangan','-')} · "
                f"Insert By: {rec.get('ppa_nama','-')} · "
                f"Verifikasi: {'✅ Ya' if rec.get('verified') else '⏳ Belum'}"
            )

    # ── Ekspor CSV ────────────────────────────────────────────────────────────
    st.markdown("---")
    col_exp1, col_exp2 = st.columns([1, 3])
    with col_exp1:
        if st.button("⬇️ Ekspor ke CSV", use_container_width=True, key="cppt_page_export"):
            df_exp = pd.DataFrame(records).rename(columns={
                "id": "No DB", "tgl_jam": "Tgl/Jam",
                "ppa_role": "Profesi", "ppa_nama": "Insert By",
                "grup": "Grup", "ruangan": "Ruangan",
                "soap_s": "Subjektif (S)", "soap_o": "Objektif (O)",
                "soap_a": "Asesmen (A)", "soap_p": "Perencanaan (P)",
                "notasi_dpjp": "Notasi DPJP", "verified": "Terverifikasi",
                "episode_id": "ID Episode",
            })
            csv_bytes = df_exp.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 Download CSV",
                data=csv_bytes,
                file_name=(
                    f"CPPT_{episode_id}_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                ),
                mime="text/csv",
                key="cppt_page_dl",
            )


main()

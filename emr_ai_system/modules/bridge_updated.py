"""
Jembatan integrasi ke Dashboard CPPT utama (`dashboard.py`).
UPDATED VERSION: dengan dukungan autentikasi & role-based access control.

PENTING — kenapa via `st.session_state`, bukan `import`:
`dashboard.py` adalah skrip top-level yang langsung menjalankan UI-nya
begitu dieksekusi. Mengimpornya dari modul lain akan ikut me-render seluruh
UI login di tempat yang salah. Solusinya: Streamlit multipage app berbagi
satu `st.session_state` antar semua halaman dalam satu sesi browser.

KEY SESSION_STATE YANG DIBACA/DITULIS:
  Dari dashboard.py (dibaca oleh modul ini):
    logged_in, user_id, shift, pasien_dipilih, episode_id,
    pasien_nama, pasien_no_rm, pasien_ruangan

  Ke dashboard.py (ditulis oleh modul ini):
    o_text_area     — kolom Objective (O) form SOAP
    soap_A          — kolom Assessment (A) form SOAP
    soap_P          — kolom Plan (P) form SOAP

  Tambahan khusus modul Dokter (dibaca & ditulis antar-halaman):
    dokter_login        — bool
    dokter_id           — str
    dokter_nama         — str
    dokter_spesialisasi — str
    cpoe_orders         — list[dict], antrian order aktif
    diagnosa_aktif      — list[dict], daftar ICD-10 episode

  AUTH SESSION KEYS:
    authenticated       — bool, user sudah login
    user_id             — str, ID user
    nama_lengkap        — str, nama lengkap user
    role                — str, role user (Dokter, Perawat, Admin, dst)
    profesi             — str, profesi detail (Dokter Jantung, Perawat ICU, dst)
    department          — str, departemen/unit user
    login_time          — str, ISO timestamp login
"""

import streamlit as st

MAIN_CPPT_PAGE = "dashboard.py"


# ── Konteks Autentikasi ────────────────────────────────────────────────────

def get_auth_context() -> dict:
    """Ambil konteks autentikasi dari session_state"""
    return {
        "authenticated": bool(st.session_state.get("authenticated", False)),
        "user_id": st.session_state.get("user_id", ""),
        "nama_lengkap": st.session_state.get("nama_lengkap", ""),
        "role": st.session_state.get("role", "Guest"),
        "profesi": st.session_state.get("profesi", ""),
        "department": st.session_state.get("department", ""),
        "login_time": st.session_state.get("login_time", ""),
    }


def require_auth(redirect_to_main: bool = True) -> bool:
    """
    Guard: wajib sudah login. Jika tidak: tampilkan peringatan.
    
    Args:
        redirect_to_main: jika True, show link ke halaman login
    
    Returns:
        True jika authenticated, False sebaliknya
    """
    auth = get_auth_context()
    if not auth["authenticated"]:
        st.error("🔒 Anda harus login terlebih dahulu.")
        if redirect_to_main:
            _link_to_main_page("➡️ Ke Halaman Login")
        st.stop()
        return False
    return True


def require_role(*allowed_roles: str) -> bool:
    """
    Guard: pastikan user punya salah satu role yang diberikan.
    
    Args:
        allowed_roles: tuple dari role names (e.g., "Dokter", "Perawat")
    
    Returns:
        True jika authorized, False sebaliknya (+ tampilkan error)
    """
    auth = get_auth_context()
    
    if not auth["authenticated"]:
        st.error("🔒 Anda harus login terlebih dahulu.")
        _link_to_main_page("➡️ Ke Halaman Login")
        st.stop()
        return False
    
    if auth["role"] not in allowed_roles:
        role_list = ", ".join(allowed_roles)
        st.error(
            f"❌ Akses ditolak. Halaman ini hanya untuk: **{role_list}**\n\n"
            f"Role Anda: **{auth['role']}** — {auth['profesi']}"
        )
        st.stop()
        return False
    
    return True


def require_permission(permission_key: str) -> bool:
    """
    Guard: cek permission user untuk action tertentu.
    
    Args:
        permission_key: permission key (e.g., "create_cpoe_orders")
    
    Returns:
        True jika punya permission, False sebaliknya
    """
    from .auth_system import has_permission
    
    if not has_permission(permission_key):
        st.error(f"❌ Anda tidak memiliki permission untuk: `{permission_key}`")
        st.stop()
        return False
    
    return True


# ── Konteks CPPT ──────────────────────────────────────────────────────────

def get_cppt_context() -> dict:
    """Ambil konteks sesi & pasien aktif dari Dashboard CPPT secara aman."""
    return {
        "logged_in":      bool(st.session_state.get("logged_in", False)),
        "user_id":        st.session_state.get("user_id"),
        "shift":          st.session_state.get("shift"),
        "pasien_dipilih": bool(st.session_state.get("pasien_dipilih", False)),
        "episode_id":     st.session_state.get("episode_id"),
        "pasien_nama":    st.session_state.get("pasien_nama", ""),
        "pasien_no_rm":   st.session_state.get("pasien_no_rm", ""),
        "pasien_ruangan": st.session_state.get("pasien_ruangan", ""),
    }


def require_cppt_session() -> dict:
    """Guard: wajib sudah login & pasien aktif. Jika tidak: tampilkan peringatan + st.stop()."""
    ctx = get_cppt_context()
    if not ctx["logged_in"]:
        st.warning(
            "🔒 Anda belum login. Silakan login terlebih dahulu lewat "
            "halaman **Dashboard CPPT** (menu di sidebar)."
        )
        _link_to_main_page("➡️ Ke Halaman Login")
        st.stop()
    if not ctx["pasien_dipilih"] or not ctx["episode_id"]:
        st.warning(
            "⚠️ Belum ada pasien aktif. Pilih pasien di halaman "
            "**Dashboard CPPT** terlebih dahulu."
        )
        _link_to_main_page("➡️ Pilih Pasien di Dashboard CPPT")
        st.stop()
    return ctx


# ── Push ke kolom SOAP Dashboard CPPT ────────────────────────────────────

def push_objective_to_cppt(text: str) -> None:
    """
    Tulis teks Objective (O) ke key `o_text_area` yang dipakai
    st.text_area(key='o_text_area') di dashboard.py (baris ~3373).
    """
    st.session_state["o_text_area"] = text


def push_assessment_to_cppt(text: str) -> None:
    """
    Tulis teks Assessment (A) ke `soap_A`.
    dashboard.py membaca key ini untuk pra-isi kolom A form SOAP.
    """
    st.session_state["soap_A"] = text


def push_plan_to_cppt(text: str) -> None:
    """
    Tulis teks Plan (P) ke `soap_P`.
    dashboard.py membaca key ini untuk pra-isi kolom P form SOAP.
    """
    st.session_state["soap_P"] = text


# ── Kredensial Dokter ─────────────────────────────────────────────────────

def get_doctor_context() -> dict:
    """
    Ambil konteks dokter aktif dari session_state.
    Key ini diset oleh `pages/2_👨‍⚕️_CPOE_Dokter.py` (sidebar profil dokter).
    """
    return {
        "dokter_login":        bool(st.session_state.get("dokter_login", False)),
        "dokter_id":           st.session_state.get("dokter_id", ""),
        "dokter_nama":         st.session_state.get("dokter_nama", ""),
        "dokter_spesialisasi": st.session_state.get("dokter_spesialisasi", ""),
    }


def set_doctor_session(dokter_id: str, dokter_nama: str, spesialisasi: str) -> None:
    """Tandai bahwa sesi dokter aktif (dipanggil setelah verifikasi kredensial)."""
    st.session_state["dokter_login"]        = True
    st.session_state["dokter_id"]           = dokter_id
    st.session_state["dokter_nama"]         = dokter_nama
    st.session_state["dokter_spesialisasi"] = spesialisasi


def clear_doctor_session() -> None:
    """Hapus sesi dokter (logout dokter tanpa logout dari CPPT)."""
    for key in ["dokter_login", "dokter_id", "dokter_nama", "dokter_spesialisasi"]:
        st.session_state.pop(key, None)


# ── CPOE Orders ───────────────────────────────────────────────────────────

def get_cpoe_orders() -> list:
    """Ambil antrian CPOE aktif yang dikirim dokter (dibaca oleh perawat di CPPT)."""
    return st.session_state.get("cpoe_orders", [])


def get_active_diagnoses_ss() -> list:
    """Ambil daftar diagnosis ICD-10 aktif dari session_state."""
    return st.session_state.get("diagnosa_aktif", [])


# ── Helper ────────────────────────────────────────────────────────────────

def _link_to_main_page(label: str) -> None:
    try:
        st.page_link(MAIN_CPPT_PAGE, label=label, icon="🫀")
    except Exception:
        st.info("Gunakan menu navigasi di sidebar untuk kembali ke **Dashboard CPPT**.")


def display_user_badge() -> None:
    """
    Tampilkan badge user profile di sidebar.
    Gunakan ini di setiap page untuk konsistensi.
    """
    auth = get_auth_context()
    
    if not auth["authenticated"]:
        st.sidebar.info("👤 Belum Login")
        return
    
    with st.sidebar.container():
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(
                f"""
                **👤 {auth['nama_lengkap']}**  
                `{auth['role']}` • {auth['profesi']}  
                Dept: {auth['department']}
                """
            )
        
        with col2:
            if st.button("🚪", key="btn_logout_badge", help="Logout"):
                from .auth_system import clear_auth_session
                clear_auth_session()
                st.success("✅ Logout berhasil.")
                st.rerun()

"""
Sistem Autentikasi & Role-Based Access Control (RBAC) untuk EMR AI System.

Fitur:
  - Role-based access control (Dokter, Perawat, Admin, Radiolog, Laboratorium, Guest)
  - Session management via Streamlit st.session_state
  - Satu sumber kebenaran: users.db via AuthProvider
  - Password hashing SHA-256
  - Sync session state terpusat (unified session)

CATATAN: Semua session key AUTH ada di sini. Dashboard & sub-modul
cukup import fungsi dari file ini — tidak boleh menulis session key
auth secara langsung di tempat lain.
"""

import hashlib
import time
from datetime import datetime
from enum import Enum
from typing import Optional, List
import streamlit as st

# ── Role Definition ────────────────────────────────────────────────────────

class UserRole(Enum):
    """Enum untuk role pengguna sistem EMR."""
    ADMIN    = "Admin"
    DOKTER   = "Dokter"
    PERAWAT  = "Perawat"
    APOTEKER = "Apoteker"      # BARU — profesi farmasi klinis (4 profesi inti CPPT)
    GIZI     = "Ahli Gizi"     # BARU — profesi gizi klinis (4 profesi inti CPPT)
    RADIOLOG = "Radiolog"
    LABORAT  = "Laboratorium"
    GUEST    = "Guest"

    @classmethod
    def profesi_cppt(cls) -> list["UserRole"]:
        """
        4 profesi inti yang mengisi CPPT multidisiplin: Dokter, Perawat,
        Apoteker, Ahli Gizi. Dipakai oleh halaman login sidik jari agar
        daftar pilihan profesi selalu sinkron dengan algoritma RBAC —
        tambah/kurangi di sini otomatis tercermin di form login.
        """
        return [cls.DOKTER, cls.PERAWAT, cls.APOTEKER, cls.GIZI]


class Profesi(Enum):
    """Enum untuk profesi detail per user."""
    # Dokter
    DOKTER_UMUM               = "Dokter Umum"
    DOKTER_SPESIALIS_JP       = "Dokter Spesialis Jantung & Pembuluh Darah"
    DOKTER_SPESIALIS_PD       = "Dokter Spesialis Penyakit Dalam"
    DOKTER_SPESIALIS_ANESTESI = "Dokter Spesialis Anestesiologi"
    DOKTER_SPESIALIS_BEDAH    = "Dokter Spesialis Bedah Thoraks Kardiovaskular"
    DOKTER_SPESIALIS_PARU     = "Dokter Spesialis Paru"
    DOKTER_SPESIALIS_SARAF    = "Dokter Spesialis Saraf"
    DOKTER_RESIDEN            = "Dokter Residen"
    # Perawat
    PERAWAT_ICU               = "Perawat ICU"
    PERAWAT_ICCU              = "Perawat ICCU"
    PERAWAT_OK                = "Perawat Kamar Operasi"
    PERAWAT_IGD               = "Perawat IGD"
    PERAWAT_RUANG_RAWAT       = "Perawat Ruang Rawat Inap"
    PERAWAT_KATLAB            = "Perawat Kateterisasi Jantung"
    PERAWAT_REHABILITASI      = "Perawat Rehabilitasi Kardiak"
    PERAWAT_LABORATORY        = "Analis Laboratorium"
    # Apoteker
    APOTEKER_KLINIS           = "Apoteker Klinis"
    APOTEKER_RAWAT_INAP       = "Apoteker Rawat Inap"
    # Ahli Gizi
    AHLI_GIZI_KLINIS          = "Ahli Gizi Klinis"
    AHLI_GIZI_RAWAT_INAP      = "Ahli Gizi Rawat Inap"
    # Spesialis
    RADIOLOG                  = "Dokter Spesialis Radiologi"
    ADMINISTRATOR             = "Administrator Sistem"


# ── Permission Matrix ──────────────────────────────────────────────────────

PERMISSION_MATRIX: dict[UserRole, dict[str, bool]] = {
    UserRole.ADMIN: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    True,
        "view_cpoe":            True,
        "create_cpoe_orders":   True,
        "verify_cpoe_orders":   True,
        "generate_diagnosis":   True,
        "generate_soap":        True,
        "view_device_monitoring": True,
        "manage_users":         True,
        "view_audit_log":       True,
        "export_reports":       True,
    },
    UserRole.DOKTER: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    True,
        "view_cpoe":            True,
        "create_cpoe_orders":   True,
        "verify_cpoe_orders":   False,
        "generate_diagnosis":   True,
        "generate_soap":        True,
        "view_device_monitoring": True,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       True,
    },
    UserRole.PERAWAT: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    False,
        "view_cpoe":            True,
        "create_cpoe_orders":   False,
        "verify_cpoe_orders":   True,
        "generate_diagnosis":   False,
        "generate_soap":        True,
        "view_device_monitoring": True,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       False,
    },
    UserRole.APOTEKER: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    False,
        "view_cpoe":            True,    # tinjau resep/order obat dokter
        "create_cpoe_orders":   False,
        "verify_cpoe_orders":   True,    # verifikasi farmasi (interaksi & dosis obat)
        "generate_diagnosis":   False,
        "generate_soap":        True,    # catatan pelayanan kefarmasian (CPPT Farmasi)
        "view_device_monitoring": False,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       False,
    },
    UserRole.GIZI: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    False,
        "view_cpoe":            True,
        "create_cpoe_orders":   False,
        "verify_cpoe_orders":   False,
        "generate_diagnosis":   False,
        "generate_soap":        True,    # catatan asuhan gizi (CPPT Gizi)
        "view_device_monitoring": False,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       False,
    },
    UserRole.RADIOLOG: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    False,
        "view_cpoe":            True,
        "create_cpoe_orders":   False,
        "verify_cpoe_orders":   False,
        "generate_diagnosis":   True,
        "generate_soap":        False,
        "view_device_monitoring": False,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       False,
    },
    UserRole.LABORAT: {
        "view_dashboard":       True,
        "view_patient_data":    True,
        "edit_patient_data":    False,
        "view_cpoe":            True,
        "create_cpoe_orders":   False,
        "verify_cpoe_orders":   False,
        "generate_diagnosis":   False,
        "generate_soap":        False,
        "view_device_monitoring": False,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       False,
    },
    UserRole.GUEST: {
        "view_dashboard":       False,
        "view_patient_data":    False,
        "edit_patient_data":    False,
        "view_cpoe":            False,
        "create_cpoe_orders":   False,
        "verify_cpoe_orders":   False,
        "generate_diagnosis":   False,
        "generate_soap":        False,
        "view_device_monitoring": False,
        "manage_users":         False,
        "view_audit_log":       False,
        "export_reports":       False,
    },
}


# ── Auth Keys Registry ─────────────────────────────────────────────────────
# Satu tempat yang mendefinisikan SEMUA session key terkait auth.
# Gunakan ini sebagai referensi saat set atau clear session.

AUTH_SESSION_KEYS = [
    "authenticated",   # bool
    "user_id",         # str — username sekaligus ID internal
    "nama_lengkap",    # str
    "role",            # str (nilai dari UserRole.value)
    "profesi",         # str
    "department",      # str
    "login_time",      # str ISO
    "login_at",        # datetime object (untuk SESSION_TTL)
    "login_method",    # "BIOMETRIK" atau "DARURAT" — BARU
    "shift",           # str shift tugas
    # Compat keys untuk sub-modul lama:
    "logged_in",       # bool — alias authenticated, dipakai cppt lama
    # Dokter-specific:
    "dokter_login",
    "dokter_id",
    "dokter_nama",
    "dokter_spesialisasi",
]


# ── Password Utilities ─────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password dengan SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verifikasi password terhadap hash yang tersimpan."""
    import hmac as _hmac
    return _hmac.compare_digest(hash_password(password), hashed)


# ── Unified Session Management ─────────────────────────────────────────────

def set_auth_session(
    user_id: str,
    nama_lengkap: str,
    role: UserRole,
    profesi: str,
    department: str = "",
    shift: str = "",
) -> None:
    """
    Set session autentikasi terpusat setelah login berhasil.

    Menulis SEMUA key yang diperlukan oleh dashboard maupun sub-modul
    (termasuk key kompatibilitas untuk kode lama) dalam satu operasi.
    """
    now = datetime.now()

    # ── Key utama (sistem baru) ──────────────────────────────────────────
    st.session_state["authenticated"] = True
    st.session_state["user_id"]       = user_id
    st.session_state["nama_lengkap"]  = nama_lengkap
    st.session_state["role"]          = role.value
    st.session_state["profesi"]       = profesi
    st.session_state["department"]    = department
    st.session_state["login_time"]    = now.isoformat()
    st.session_state["login_at"]      = now        # datetime object untuk TTL check
    st.session_state["shift"]         = shift

    # ── Key kompatibilitas (sub-modul CPPT lama) ────────────────────────
    st.session_state["logged_in"]     = True

    # ── Dokter-specific keys ─────────────────────────────────────────────
    if role == UserRole.DOKTER:
        st.session_state["dokter_login"]        = True
        st.session_state["dokter_id"]           = user_id
        st.session_state["dokter_nama"]         = nama_lengkap
        st.session_state["dokter_spesialisasi"] = profesi
    else:
        # Pastikan key dokter tidak "sisa" dari session sebelumnya
        for k in ["dokter_login", "dokter_id", "dokter_nama", "dokter_spesialisasi"]:
            st.session_state.pop(k, None)


def clear_auth_session() -> None:
    """Logout — hapus seluruh session auth dari registry AUTH_SESSION_KEYS."""
    for key in AUTH_SESSION_KEYS:
        st.session_state.pop(key, None)


def get_auth_context() -> dict:
    """Ambil context autentikasi saat ini dari session_state."""
    return {
        "authenticated": bool(st.session_state.get("authenticated", False)),
        "user_id":       st.session_state.get("user_id", ""),
        "nama_lengkap":  st.session_state.get("nama_lengkap", ""),
        "role":          st.session_state.get("role", UserRole.GUEST.value),
        "profesi":       st.session_state.get("profesi", ""),
        "department":    st.session_state.get("department", ""),
        "login_time":    st.session_state.get("login_time", ""),
        "shift":         st.session_state.get("shift", ""),
    }


# ── Permission Checking ────────────────────────────────────────────────────

def has_permission(permission: str) -> bool:
    """Cek apakah user yang sedang login punya permission tertentu."""
    ctx = get_auth_context()
    if not ctx["authenticated"]:
        return False
    try:
        role = UserRole(ctx["role"])
    except ValueError:
        return False
    return PERMISSION_MATRIX.get(role, {}).get(permission, False)


def require_role(*allowed_roles: UserRole) -> bool:
    """
    Guard: pastikan user sudah login dan rolenya termasuk yang diizinkan.
    Jika gagal, tampilkan st.error dan return False.
    """
    ctx = get_auth_context()
    if not ctx["authenticated"]:
        st.error("🔒 Anda harus login terlebih dahulu.")
        return False
    try:
        user_role = UserRole(ctx["role"])
    except ValueError:
        st.error("⚠️ Role user tidak valid.")
        return False
    if user_role not in allowed_roles:
        role_names = ", ".join(r.value for r in allowed_roles)
        st.error(
            f"❌ Akses ditolak. Halaman ini hanya untuk: **{role_names}**\n\n"
            f"Role Anda: **{ctx['role']}**"
        )
        return False
    return True


def require_permission(permission: str, message: str = "") -> bool:
    """Guard: pastikan user punya permission tertentu."""
    if not has_permission(permission):
        st.error(message or f"❌ Anda tidak memiliki permission: **{permission}**")
        return False
    return True


# ── Login Form Renderer ────────────────────────────────────────────────────

def _finalize_login(user: dict, shift_clean: str, metode: str, on_login_callback=None) -> bool:
    """
    Helper bersama: tuliskan sesi terpusat (set_auth_session) setelah
    otentikasi sukses, baik lewat jalur biometrik maupun darurat.
    """
    try:
        role_enum = UserRole(user["role"])
    except ValueError:
        role_enum = UserRole.GUEST

    set_auth_session(
        user_id      = user["user_id"],
        nama_lengkap = user["nama_lengkap"],
        role         = role_enum,
        profesi      = user["profesi"],
        department   = user.get("department", ""),
        shift        = shift_clean,
    )
    st.session_state["login_method"] = metode

    if on_login_callback:
        on_login_callback(user)

    st.success(f"✅ Selamat datang, **{user['nama_lengkap']}**!")
    st.rerun()
    return True


def render_login_form(auth_provider: "AuthProvider", on_login_callback=None) -> bool:
    """
    Render UI otentikasi — satu-satunya titik masuk autentikasi dashboard.

    Dua jalur, keduanya berakhir di set_auth_session() yang sama:
      1) Sidik Jari per Profesi — 4 profesi inti CPPT (Dokter/Perawat/
         Apoteker/Ahli Gizi). Daftar nama ditarik langsung dari users.db
         lewat auth_provider.get_users_by_role(), bukan hardcode.
      2) Mode Darurat — login manual username+password, berlaku untuk
         SEMUA role (termasuk Admin/Radiolog/Laborat), wajib isi alasan,
         tercatat sebagai EMERGENCY_BYPASS di auth_audit_log.

    Returns True jika login baru saja berhasil (sebelum rerun).
    """
    shift = st.selectbox(
        "⏰ Shift Tugas:",
        ["Pagi (07:00 - 14:00)", "Sore (14:00 - 21:00)", "Malam (21:00 - 07:00)"],
        key="login_shift",
    )
    shift_clean = shift.split()[0]

    st.write("")
    st.markdown("🎯 **Otentikasi Utama — Sidik Jari per Profesi**")

    # Pilihan profesi SELALU sinkron dengan algoritma RBAC lewat
    # UserRole.profesi_cppt() — tambah/kurangi role di sana otomatis
    # tercermin di sini, tidak ada daftar profesi yang ditulis dobel.
    profesi_icon = {
        UserRole.DOKTER:   "👨‍⚕️ Dokter",
        UserRole.PERAWAT:  "👩‍⚕️ Perawat",
        UserRole.APOTEKER: "💊 Apoteker",
        UserRole.GIZI:     "🥗 Ahli Gizi",
    }
    roles_cppt = UserRole.profesi_cppt()
    profesi_pilihan = st.selectbox(
        "Pilih Profesi:",
        roles_cppt,
        format_func=lambda r: profesi_icon.get(r, r.value),
        key="login_role_pilihan",
    )

    daftar_pegawai = auth_provider.get_users_by_role(profesi_pilihan)

    login_sukses = False

    if not daftar_pegawai:
        st.warning(f"⚠️ Belum ada pegawai aktif terdaftar untuk profesi **{profesi_pilihan.value}**.")
    else:
        opsi_nama = [f"Sentuh Jari: {p['nama_lengkap']}" for p in daftar_pegawai]
        opsi_nama.append("Sidik Jari Tidak Terdaftar")
        # Key dibuat dinamis per profesi (bukan key statis) — supaya saat profesi
        # diganti, widget ini dianggap baru oleh Streamlit (reset ke index 0)
        # alih-alih mencoba mencocokkan value lama ke daftar opsi yang sudah berubah.
        mock_finger = st.selectbox(
            "Simulasi Perangkat USB Scanner:", opsi_nama,
            key=f"login_mock_finger_{profesi_pilihan.name}",
        )

        if st.button(
            "👆 PINDAI SIDIK JARI SEKARANG",
            type="primary",
            use_container_width=True,
            key="btn_scan_finger",
        ):
            if mock_finger == "Sidik Jari Tidak Terdaftar":
                st.error("❌ Gagal Otentikasi: Sidik jari tidak cocok dengan registri SIMRS.")
            else:
                user = daftar_pegawai[opsi_nama.index(mock_finger)]
                with st.spinner("🔄 Membaca enkripsi template biometrik..."):
                    time.sleep(0.8)
                st.toast("Biometrik Terverifikasi via Hardware!", icon="🔑")
                # Identitas sudah diverifikasi hardware -> tidak perlu password,
                # tapi tetap melalui AuthProvider supaya tercatat di audit log resmi.
                verified_user = auth_provider.authenticate_biometric(user["user_id"])
                if verified_user:
                    login_sukses = _finalize_login(
                        verified_user, shift_clean, "BIOMETRIK", on_login_callback
                    )
                else:
                    st.error("❌ Profil pegawai tidak ditemukan di users.db. Hubungi Admin.")

    st.write("")
    with st.expander("⚠️ MODE DARURAT (Bypass Sensor Rusak / Akses Non-CPPT)"):
        st.warning(
            "Perhatian: login manual berlaku untuk **semua role** (termasuk Admin, "
            "Radiolog, Laboratorium) — dipantau ketat. Setiap akses tercatat permanen "
            "di Audit Log dengan alasan yang Anda isi."
        )
        u = st.text_input(
            "👤 Username:", placeholder="contoh: dr_salma", key="login_username_darurat"
        )
        p = st.text_input(
            "🔒 Password:", type="password", placeholder="Masukkan password",
            key="login_password_darurat",
        )
        alasan = st.text_area(
            "📝 Alasan Akses Darurat (wajib):",
            placeholder="Contoh: sensor fingerprint rusak / login dari luar modul CPPT",
            key="login_alasan_darurat",
        )

        if st.button(
            "Konfirmasi Override & Masuk", type="secondary",
            use_container_width=True, key="btn_override_darurat",
        ):
            if not alasan.strip():
                st.error("Gagal Akses: Alasan darurat wajib diisi!")
            else:
                user, error = auth_provider.authenticate(u.strip(), p)
                if error:
                    st.error(f"Kredensial darurat salah: {error}")
                else:
                    auth_provider.log_emergency_access(
                        user["user_id"], user["username"], alasan.strip()
                    )
                    st.session_state.setdefault("emergency_logs", []).append({
                        "Waktu Kejadian":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "NIP Pelaku":         user["username"],
                        "Profesi":            user["role"],
                        "Sif Kerja":          shift_clean,
                        "Alasan Kedaruratan": alasan.strip(),
                        "Metode Akses":       "BYPASS_MANUAL_OVERRIDE",
                        "Status":             "TEREKAM",
                    })
                    login_sukses = _finalize_login(user, shift_clean, "DARURAT", on_login_callback)

    with st.expander("ℹ️ Daftar Akun Demo (untuk testing)"):
        st.markdown(
            """
            <div style="font-size:12px;">
            <b>Dokter:</b> dr_salma / dr_ahmad / dr_bintang — pass: <code>123</code><br>
            <b>Perawat:</b> perawat_budi / perawat_siti / perawat_rani — pass: <code>123</code><br>
            <b>Apoteker:</b> apt_dewi / apt_hendra — pass: <code>123</code><br>
            <b>Ahli Gizi:</b> gizi_putri / gizi_anjani — pass: <code>123</code><br>
            <b>Radiolog:</b> dr_rudi_rad — pass: <code>123</code><br>
            <b>Lab:</b> analis_lab — pass: <code>123</code><br>
            <b>Admin:</b> admin — pass: <code>admin123</code>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return login_sukses


# ── Display Helpers ────────────────────────────────────────────────────────

def display_permission_status() -> None:
    """Debug: tampilkan matrix permission user yang sedang login."""
    ctx = get_auth_context()
    if not ctx["authenticated"]:
        st.warning("User belum login.")
        return
    st.markdown(f"### Permission Matrix — {ctx['nama_lengkap']} ({ctx['role']})")
    try:
        role = UserRole(ctx["role"])
        perms = PERMISSION_MATRIX.get(role, {})
    except ValueError:
        st.error("Role tidak valid")
        return
    cols = st.columns(2)
    for idx, (key, val) in enumerate(perms.items()):
        with cols[idx % 2]:
            st.write(f"{'✅' if val else '❌'} `{key}`")

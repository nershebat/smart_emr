"""
AuthProvider — Implementasi lengkap sistem autentikasi.

Satu-satunya sumber kebenaran untuk user data.
Menghubungkan auth_system.py (logic) dan auth_database.py (persistensi).

PERUBAHAN dari versi lama:
  - Hapus semua referensi ke KREDENSIAL hardcoded (rudi/jule)
  - Mock users diperluas sesuai profesi nyata RSJPDHK
  - user_id menggunakan format konsisten: ROLE_username
  - _seed_demo_users() idempotent: cek via username, bukan asumsi
"""

import uuid
from typing import Tuple, Optional, Dict, List
import streamlit as st

from .auth_system import (
    UserRole, Profesi,
    verify_password, get_auth_context, set_auth_session, hash_password,
)
from .auth_database import (
    init_auth_database, get_user_by_username, get_user_by_id,
    create_user, get_all_users, log_auth_activity, update_last_login,
    change_password as db_change_password,
)


# ── Demo User Registry ─────────────────────────────────────────────────────
# Satu-satunya tempat mendefinisikan akun demo/seed.
# Format user_id: {ROLE_PREFIX}_{username} — deterministik, tidak random,
# sehingga seed idempoten meski dijalankan berulang kali.

DEMO_USERS: list[dict] = [

    # ══════════════════════════════════════════════════════════
    # DOKTER (6 user)
    # ══════════════════════════════════════════════════════════
    {
        "username":      "dr_salma",
        "password":      "123",
        "nama_lengkap":  "dr. Salma Husna, Sp.JP(K)",
        "role":          UserRole.DOKTER,
        "profesi":       Profesi.DOKTER_SPESIALIS_JP.value,
        "department":    "Kardiologi Intervensi",
        "email":         "salma.husna@rsjpdhk.go.id",
        "telepon":       "08111000001",
        "nomor_sip_nik": "SIP-JP-001/10101980/DKI",
    },
    {
        "username":      "dr_ahmad",
        "password":      "123",
        "nama_lengkap":  "dr. Ahmad Wijaya, Sp.PD-KKV",
        "role":          UserRole.DOKTER,
        "profesi":       Profesi.DOKTER_SPESIALIS_PD.value,
        "department":    "Penyakit Dalam Kardiovaskular",
        "email":         "ahmad.wijaya@rsjpdhk.go.id",
        "telepon":       "08111000002",
        "nomor_sip_nik": "SIP-PD-002/10101975/DKI",
    },
    {
        "username":      "dr_bintang",
        "password":      "123",
        "nama_lengkap":  "dr. Bintang Pratama, Sp.An-KIC",
        "role":          UserRole.DOKTER,
        "profesi":       Profesi.DOKTER_SPESIALIS_ANESTESI.value,
        "department":    "Anestesiologi & Terapi Intensif",
        "email":         "bintang.pratama@rsjpdhk.go.id",
        "telepon":       "08111000003",
        "nomor_sip_nik": "SIP-AN-003/10101982/DKI",
    },
    {
        "username":      "dr_larasati",
        "password":      "123",
        "nama_lengkap":  "dr. Larasati Dewi, Sp.BTKV",
        "role":          UserRole.DOKTER,
        "profesi":       Profesi.DOKTER_SPESIALIS_BEDAH.value,
        "department":    "Bedah Thoraks Kardiovaskular",
        "email":         "larasati.dewi@rsjpdhk.go.id",
        "telepon":       "08111000004",
        "nomor_sip_nik": "SIP-BTKV-004/10101978/DKI",
    },
    {
        "username":      "dr_hendra",
        "password":      "123",
        "nama_lengkap":  "dr. Hendra Gunawan, Sp.JP",
        "role":          UserRole.DOKTER,
        "profesi":       Profesi.DOKTER_SPESIALIS_JP.value,
        "department":    "Kardiologi Non-Invasif",
        "email":         "hendra.gunawan@rsjpdhk.go.id",
        "telepon":       "08111000005",
        "nomor_sip_nik": "SIP-JP-005/10101985/DKI",
    },
    {
        "username":      "dr_residen1",
        "password":      "123",
        "nama_lengkap":  "dr. Fajar Nugroho (Residen JP)",
        "role":          UserRole.DOKTER,
        "profesi":       Profesi.DOKTER_RESIDEN.value,
        "department":    "Kardiologi – Program Residensi",
        "email":         "fajar.nugroho@rsjpdhk.go.id",
        "telepon":       "08111000006",
        "nomor_sip_nik": "STR-RES-006/2024/RSJPDHK",
    },

    # ══════════════════════════════════════════════════════════
    # PERAWAT (8 user)
    # ══════════════════════════════════════════════════════════
    {
        "username":      "perawat_budi",
        "password":      "123",
        "nama_lengkap":  "Budi Santoso, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_ICU.value,
        "department":    "ICU Jantung",
        "email":         "budi.santoso@rsjpdhk.go.id",
        "telepon":       "08111000010",
        "nomor_sip_nik": "SIPP-ICU-010/10101990/DKI",
    },
    {
        "username":      "perawat_siti",
        "password":      "123",
        "nama_lengkap":  "Siti Nurhaliza, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_ICCU.value,
        "department":    "ICCU",
        "email":         "siti.nurhaliza@rsjpdhk.go.id",
        "telepon":       "08111000011",
        "nomor_sip_nik": "SIPP-ICCU-011/10101992/DKI",
    },
    {
        "username":      "perawat_rani",
        "password":      "123",
        "nama_lengkap":  "Rani Kusuma, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_RUANG_RAWAT.value,
        "department":    "Ruang Rawat Inap Mawar",
        "email":         "rani.kusuma@rsjpdhk.go.id",
        "telepon":       "08111000012",
        "nomor_sip_nik": "SIPP-RR-012/10101993/DKI",
    },
    {
        "username":      "perawat_dedi",
        "password":      "123",
        "nama_lengkap":  "Dedi Kurniawan, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_OK.value,
        "department":    "Kamar Operasi",
        "email":         "dedi.kurniawan@rsjpdhk.go.id",
        "telepon":       "08111000013",
        "nomor_sip_nik": "SIPP-OK-013/10101988/DKI",
    },
    {
        "username":      "perawat_maya",
        "password":      "123",
        "nama_lengkap":  "Maya Anggraini, S.Kep., Ns., M.Kep.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_IGD.value,
        "department":    "IGD Kardiovaskular",
        "email":         "maya.anggraini@rsjpdhk.go.id",
        "telepon":       "08111000014",
        "nomor_sip_nik": "SIPP-IGD-014/10101991/DKI",
    },
    {
        "username":      "perawat_rudi",
        "password":      "123",
        "nama_lengkap":  "Rudi Hartono, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_ICU.value,
        "department":    "ICU Jantung",
        "email":         "rudi.hartono@rsjpdhk.go.id",
        "telepon":       "08111000015",
        "nomor_sip_nik": "SIPP-ICU-015/10101989/DKI",
    },
    {
        "username":      "perawat_juleha",
        "password":      "123",
        "nama_lengkap":  "Juleha Permata, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_KATLAB.value,
        "department":    "Kateterisasi Jantung",
        "email":         "juleha.permata@rsjpdhk.go.id",
        "telepon":       "08111000016",
        "nomor_sip_nik": "SIPP-KAT-016/10101994/DKI",
    },
    {
        "username":      "perawat_rehab",
        "password":      "123",
        "nama_lengkap":  "Suryani Putri, S.Kep., Ns.",
        "role":          UserRole.PERAWAT,
        "profesi":       Profesi.PERAWAT_REHABILITASI.value,
        "department":    "Rehabilitasi Kardiak",
        "email":         "suryani.putri@rsjpdhk.go.id",
        "telepon":       "08111000017",
        "nomor_sip_nik": "SIPP-REH-017/10101995/DKI",
    },

    # ══════════════════════════════════════════════════════════
    # APOTEKER (2 user) — BARU, profesi inti CPPT ke-3
    # ══════════════════════════════════════════════════════════
    {
        "username":      "apt_dewi",
        "password":      "123",
        "nama_lengkap":  "Dewi Lestari, S.Farm., Apt.",
        "role":          UserRole.APOTEKER,
        "profesi":       Profesi.APOTEKER_KLINIS.value,
        "department":    "Farmasi Klinis",
        "email":         "dewi.lestari@rsjpdhk.go.id",
        "telepon":       "08111000040",
        "nomor_sip_nik": "SIPA-001/10101990/DKI",
    },
    {
        "username":      "apt_hendra",
        "password":      "123",
        "nama_lengkap":  "Hendra Saputra, S.Farm., Apt.",
        "role":          UserRole.APOTEKER,
        "profesi":       Profesi.APOTEKER_RAWAT_INAP.value,
        "department":    "Farmasi Rawat Inap",
        "email":         "hendra.saputra@rsjpdhk.go.id",
        "telepon":       "08111000041",
        "nomor_sip_nik": "SIPA-002/10101989/DKI",
    },

    # ══════════════════════════════════════════════════════════
    # AHLI GIZI (2 user) — BARU, profesi inti CPPT ke-4
    # ══════════════════════════════════════════════════════════
    {
        "username":      "gizi_putri",
        "password":      "123",
        "nama_lengkap":  "Putri Ayu, S.Gz., RD.",
        "role":          UserRole.GIZI,
        "profesi":       Profesi.AHLI_GIZI_KLINIS.value,
        "department":    "Gizi Klinik",
        "email":         "putri.ayu@rsjpdhk.go.id",
        "telepon":       "08111000042",
        "nomor_sip_nik": "STR-GZ-001/10101993/DKI",
    },
    {
        "username":      "gizi_anjani",
        "password":      "123",
        "nama_lengkap":  "Anjani Kartika, S.Gz., RD.",
        "role":          UserRole.GIZI,
        "profesi":       Profesi.AHLI_GIZI_RAWAT_INAP.value,
        "department":    "Instalasi Gizi Rawat Inap",
        "email":         "anjani.kartika@rsjpdhk.go.id",
        "telepon":       "08111000043",
        "nomor_sip_nik": "STR-GZ-002/10101995/DKI",
    },

    # ══════════════════════════════════════════════════════════
    # RADIOLOG (2 user)
    # ══════════════════════════════════════════════════════════
    {
        "username":      "dr_rudi_rad",
        "password":      "123",
        "nama_lengkap":  "dr. Rudi Hermawan, Sp.Rad.",
        "role":          UserRole.RADIOLOG,
        "profesi":       Profesi.RADIOLOG.value,
        "department":    "Radiologi & Pencitraan Kardiak",
        "email":         "rudi.hermawan@rsjpdhk.go.id",
        "telepon":       "08111000020",
        "nomor_sip_nik": "SIP-RAD-020/10101983/DKI",
    },
    {
        "username":      "dr_nina_rad",
        "password":      "123",
        "nama_lengkap":  "dr. Nina Puspita, Sp.Rad.",
        "role":          UserRole.RADIOLOG,
        "profesi":       Profesi.RADIOLOG.value,
        "department":    "Radiologi Intervensional",
        "email":         "nina.puspita@rsjpdhk.go.id",
        "telepon":       "08111000021",
        "nomor_sip_nik": "SIP-RAD-021/10101986/DKI",
    },

    # ══════════════════════════════════════════════════════════
    # LABORATORIUM (2 user)
    # ══════════════════════════════════════════════════════════
    {
        "username":      "analis_lab",
        "password":      "123",
        "nama_lengkap":  "Teguh Prasetyo, A.Md.AK.",
        "role":          UserRole.LABORAT,
        "profesi":       Profesi.PERAWAT_LABORATORY.value,
        "department":    "Laboratorium Patologi Klinik",
        "email":         "teguh.prasetyo@rsjpdhk.go.id",
        "telepon":       "08111000030",
        "nomor_sip_nik": "SIKTTK-LAB-030/10101991/DKI",
    },
    {
        "username":      "analis_lab2",
        "password":      "123",
        "nama_lengkap":  "Dewi Fitriani, A.Md.AK.",
        "role":          UserRole.LABORAT,
        "profesi":       Profesi.PERAWAT_LABORATORY.value,
        "department":    "Laboratorium Hematologi",
        "email":         "dewi.fitriani@rsjpdhk.go.id",
        "telepon":       "08111000031",
        "nomor_sip_nik": "SIKTTK-LAB-031/10101993/DKI",
    },

    # ══════════════════════════════════════════════════════════
    # ADMIN (1 user)
    # ══════════════════════════════════════════════════════════
    {
        "username":      "admin",
        "password":      "admin123",
        "nama_lengkap":  "Administrator EMR RSJPDHK",
        "role":          UserRole.ADMIN,
        "profesi":       Profesi.ADMINISTRATOR.value,
        "department":    "IT & Sistem Informasi",
        "email":         "admin@rsjpdhk.go.id",
        "telepon":       "08111000099",
        "nomor_sip_nik": "",
    },
]


# ── AuthProvider ───────────────────────────────────────────────────────────

class AuthProvider:
    """Provider tunggal untuk semua operasi autentikasi EMR."""

    def __init__(self):
        init_auth_database()
        self._seed_demo_users()

    # ── Autentikasi ────────────────────────────────────────────────────────

    def authenticate(
        self,
        username: str,
        password: str,
        log_activity: bool = True,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Autentikasi user.

        Returns:
            (user_dict, None)  — sukses
            (None, error_msg)  — gagal
        """
        if not username or not password:
            return None, "Username dan password harus diisi."

        user = get_user_by_username(username)
        if not user:
            if log_activity:
                log_auth_activity("UNKNOWN", username, "LOGIN_ATTEMPT", "FAILED",
                                  "User tidak ditemukan")
            return None, f"Username '{username}' tidak ditemukan."

        if not verify_password(password, user["password_hash"]):
            if log_activity:
                log_auth_activity(user["user_id"], username, "LOGIN_ATTEMPT", "FAILED",
                                  "Password tidak sesuai")
            return None, "Password tidak sesuai."

        if log_activity:
            log_auth_activity(user["user_id"], username, "LOGIN", "SUCCESS",
                              f"Role: {user['role']}")
            update_last_login(user["user_id"])

        return {
            "user_id":      user["user_id"],
            "username":     user["username"],
            "nama_lengkap": user["nama_lengkap"],
            "role":         user["role"],
            "profesi":      user["profesi"],
            "department":   user.get("department", ""),
            "email":        user.get("email", ""),
        }, None

    def authenticate_biometric(self, user_id: str) -> Optional[Dict]:
        """
        Otentikasi via simulasi sidik jari: identitas sudah diverifikasi oleh
        hardware (tidak perlu password). Tetap melalui AuthProvider agar
        tercatat di audit log resmi yang sama dengan jalur password.
        """
        user = get_user_by_id(user_id)
        if not user:
            return None

        log_auth_activity(
            user["user_id"], user["username"], "LOGIN", "SUCCESS",
            f"Biometrik (Simulasi) | Role: {user['role']}"
        )
        update_last_login(user["user_id"])

        return {
            "user_id":      user["user_id"],
            "username":     user["username"],
            "nama_lengkap": user["nama_lengkap"],
            "role":         user["role"],
            "profesi":      user["profesi"],
            "department":   user.get("department", ""),
            "email":        user.get("email", ""),
        }

    def log_emergency_access(self, user_id: str, username: str, alasan: str) -> None:
        """Catat akses darurat (bypass sidik jari) ke audit log terpusat."""
        log_auth_activity(user_id, username, "EMERGENCY_BYPASS", "SUCCESS", alasan)

    # ── Registrasi ─────────────────────────────────────────────────────────

    def register_user(
        self,
        username: str,
        password: str,
        nama_lengkap: str,
        role: UserRole,
        profesi: str,
        department: str = "",
        email: str = "",
        telepon: str = "",
        nomor_sip_nik: str = "",
    ) -> Tuple[bool, str]:
        """Register user baru. user_id dibuat deterministik dari role+username."""
        role_prefix = role.name[:3].upper()          # DOK / PER / ADM / RAD / LAB
        user_id     = f"{role_prefix}_{username}"    # mis. DOK_dr_salma

        success, message = create_user(
            user_id       = user_id,
            username      = username,
            password      = password,
            nama_lengkap  = nama_lengkap,
            role          = role,
            profesi       = profesi,
            department    = department,
            email         = email,
            telepon       = telepon,
            nomor_sip_nik = nomor_sip_nik,
        )
        if success:
            log_auth_activity(user_id, username, "USER_CREATED", "SUCCESS",
                              f"Role: {role.value}")
        return success, message

    # ── Query ──────────────────────────────────────────────────────────────

    def get_current_user(self) -> Optional[Dict]:
        """Ambil data lengkap user yang sedang login."""
        ctx = get_auth_context()
        if not ctx["authenticated"]:
            return None
        return get_user_by_id(ctx["user_id"])

    def get_users_by_role(self, role: UserRole) -> List[Dict]:
        """Ambil semua user aktif dengan role tertentu."""
        return get_all_users(role=role)

    def get_all_active_users(self) -> List[Dict]:
        """Ambil semua user aktif tanpa filter role."""
        return get_all_users()

    # ── Password ───────────────────────────────────────────────────────────

    def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str,
    ) -> Tuple[bool, str]:
        """Ganti password user setelah verifikasi password lama."""
        success, message = db_change_password(user_id, old_password, new_password)
        aksi = "PASSWORD_CHANGED" if success else "PASSWORD_CHANGE_FAILED"
        status = "SUCCESS" if success else "FAILED"
        log_auth_activity(user_id, "", aksi, status, message)
        return success, message

    # ── Seed ───────────────────────────────────────────────────────────────

    def _seed_demo_users(self) -> None:
        """
        Buat akun demo jika belum ada. Idempoten — aman dipanggil berulang.
        Cek per-username; jika sudah ada, skip tanpa error.
        """
        for user_data in DEMO_USERS:
            if get_user_by_username(user_data["username"]):
                continue  # Sudah ada, skip
            data = {k: v for k, v in user_data.items() if k != "password"}
            success, msg = self.register_user(
                password=user_data["password"], **data
            )
            if not success:
                # Hanya log ke stderr, jangan crash
                import sys
                print(f"[SEED WARNING] {user_data['username']}: {msg}", file=sys.stderr)


# ── Singleton ──────────────────────────────────────────────────────────────

_instance: Optional[AuthProvider] = None


def get_auth_provider() -> AuthProvider:
    """Dapatkan singleton AuthProvider. Inisialisasi satu kali per proses."""
    global _instance
    if _instance is None:
        _instance = AuthProvider()
    return _instance


# ── Shortcut Functions ─────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> Tuple[Optional[Dict], Optional[str]]:
    return get_auth_provider().authenticate(username, password)


def register_user(username: str, password: str, nama_lengkap: str,
                  role: UserRole, profesi: str, **kwargs) -> Tuple[bool, str]:
    return get_auth_provider().register_user(
        username, password, nama_lengkap, role, profesi, **kwargs
    )


def get_current_user() -> Optional[Dict]:
    return get_auth_provider().get_current_user()

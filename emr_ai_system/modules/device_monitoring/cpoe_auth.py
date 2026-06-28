"""
CPOE Authorization & RBAC Engine
=================================
Role-Based Access Control untuk Computerized Physician Order Entry.

Landasan hukum & regulasi:
  • UU No. 29 Tahun 2004 — Praktik Kedokteran (Pasal 35, 36)
  • UU No. 38 Tahun 2014 — Keperawatan
  • Permenkes No. 72 Tahun 2016 — Pelayanan Kefarmasian di RS
  • Permenkes No. 26 Tahun 2019 — Apoteker
  • Permenkes No. 755/MENKES/PER/IV/2011 — Komite Medik
  • SNARS Ed.2 TKRS 11 — Kewenangan Klinis (KKF/KKP)
  • SNARS KPS 5 — Penetapan dan pemantauan kewenangan klinis
  • HIMSS EMRAM L6/7 — Role-based access control on CPOE

Hierarki kewenangan meresepkan (Prescribing Authority Matrix):
  DPJP          → Full prescribing (semua obat termasuk high-alert)
  DPJP_UTAMA    → Sama + dapat verifikasi order konsulen
  RESIDEN_SR    → Prescribing dengan countersign DPJP (PGY3+, SpJP muda)
  RESIDEN_JR    → Draft only → wajib countersign DPJP sebelum aktif
  CO_ASS        → Tidak boleh prescribe — hanya bisa lihat order
  PERAWAT_PK3   → Nursing orders + verbal order (TBAK) + emergency protocol
  PERAWAT_PK2   → Nursing orders standard + TBAK
  PERAWAT_PK1   → Nursing orders sederhana saja
  APOTEKER      → Verify + dispense + substitusi generik
  FARMASI_KLINIK→ Rekomendasi + DUE, tidak meresepkan
  GIZI_KLINIK   → Diet order saja
  RADIOGRAFER   → Tidak ada order access
  ADMIN_KLINIK  → View-only
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import streamlit as st

logger = logging.getLogger(__name__)

_AUTH_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cpoe_auth.db"
_SESSION_KEY_AUTH = "cpoe_auth_session"

# Token TTL (menit) — sesuai kebijakan keamanan RS
_TOKEN_TTL_MINUTES = 480   # 8 jam (1 shift)
_HIGH_ALERT_TTL_MINUTES = 15  # re-auth setiap 15 menit untuk high-alert


# =============================================================================
# Role Definitions
# =============================================================================

class CPOERole(Enum):
    DPJP           = "DPJP"
    DPJP_UTAMA     = "DPJP Utama"
    RESIDEN_SR     = "Residen Senior (PGY3+)"
    RESIDEN_JR     = "Residen Junior"
    CO_ASS         = "Co-Assistensi"
    PERAWAT_PK3    = "Perawat PK III"
    PERAWAT_PK2    = "Perawat PK II"
    PERAWAT_PK1    = "Perawat PK I"
    APOTEKER       = "Apoteker"
    FARMASI_KLINIK = "Farmasi Klinik"
    GIZI_KLINIK    = "Ahli Gizi Klinik"
    RADIOGRAFER    = "Radiografer"
    ADMIN_KLINIK   = "Admin Klinik"
    SISTEM         = "Sistem (Otomatis)"


class Permission(Enum):
    # ── Medication Orders ───────────────────────────────────────────────────
    MED_ORDER_REGULAR     = "Meresepkan obat reguler"
    MED_ORDER_HIGH_ALERT  = "Meresepkan obat high-alert"
    MED_ORDER_NARCOTICS   = "Meresepkan narkotika/psikotropika"
    MED_ORDER_VERBAL      = "Menerima/menulis verbal order"
    MED_ORDER_COUNTERSIGN = "Countersign order residen"
    MED_VERIFY_PHARMACY   = "Verifikasi farmasi"
    MED_DISPENSE          = "Dispensing obat"
    MED_ADMINISTER        = "Administrasi obat"
    MED_SUBSTITUTION      = "Substitusi generik"
    # ── Non-Medication Orders ───────────────────────────────────────────────
    LAB_ORDER             = "Order laboratorium"
    IMAGING_ORDER         = "Order radiologi/imaging"
    NURSING_ORDER         = "Order keperawatan"
    DIET_ORDER            = "Order diet/nutrisi"
    CONSULT_ORDER         = "Order konsultasi"
    PROCEDURE_ORDER       = "Order prosedur/tindakan"
    # ── Order Management ────────────────────────────────────────────────────
    ORDER_CANCEL          = "Batalkan order"
    ORDER_HOLD            = "Tahan order"
    ORDER_SET_ACTIVATE    = "Aktivasi order set"
    ORDER_VIEW_ALL        = "Lihat semua order"
    ORDER_VIEW_OWN        = "Lihat order sendiri"
    # ── Clinical Data ───────────────────────────────────────────────────────
    VIEW_EMAR             = "Lihat eMAR"
    VIEW_CPPT             = "Lihat CPPT"
    EDIT_CPPT             = "Edit/tambah CPPT"
    VIEW_AUDIT            = "Lihat audit trail"
    # ── CLMA Pipeline ───────────────────────────────────────────────────────
    CLMA_SCAN             = "Scan barcode CLMA"
    CLMA_FIVE_RIGHTS      = "Verifikasi 5-Rights"
    CLMA_ADMINISTER       = "Konfirmasi pemberian via CLMA"
    CLMA_OVERRIDE         = "Override 5-Rights (emergensi)"
    # ── System ──────────────────────────────────────────────────────────────
    ADMIN_USER_MGMT       = "Manajemen pengguna"
    ADMIN_AUDIT_FULL      = "Audit trail penuh"
    PUMP_PROGRAM          = "Auto-program infusion pump"

# =============================================================================
# Permission Matrix — per Role
# =============================================================================

ROLE_PERMISSIONS: Dict[CPOERole, Set[Permission]] = {

    CPOERole.DPJP: {
        Permission.MED_ORDER_REGULAR, Permission.MED_ORDER_HIGH_ALERT,
        Permission.MED_ORDER_NARCOTICS, Permission.MED_ORDER_VERBAL,
        Permission.MED_ORDER_COUNTERSIGN, Permission.MED_ADMINISTER,
        Permission.LAB_ORDER, Permission.IMAGING_ORDER,
        Permission.NURSING_ORDER, Permission.DIET_ORDER,
        Permission.CONSULT_ORDER, Permission.PROCEDURE_ORDER,
        Permission.ORDER_CANCEL, Permission.ORDER_HOLD,
        Permission.ORDER_SET_ACTIVATE, Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
        Permission.VIEW_AUDIT, Permission.PUMP_PROGRAM,
        Permission.CLMA_SCAN, Permission.CLMA_FIVE_RIGHTS,
        Permission.CLMA_ADMINISTER, Permission.CLMA_OVERRIDE,
    },

    CPOERole.DPJP_UTAMA: {
        # Sama dengan DPJP + lihat audit penuh
        Permission.MED_ORDER_REGULAR, Permission.MED_ORDER_HIGH_ALERT,
        Permission.MED_ORDER_NARCOTICS, Permission.MED_ORDER_VERBAL,
        Permission.MED_ORDER_COUNTERSIGN, Permission.MED_ADMINISTER,
        Permission.LAB_ORDER, Permission.IMAGING_ORDER,
        Permission.NURSING_ORDER, Permission.DIET_ORDER,
        Permission.CONSULT_ORDER, Permission.PROCEDURE_ORDER,
        Permission.ORDER_CANCEL, Permission.ORDER_HOLD,
        Permission.ORDER_SET_ACTIVATE, Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
        Permission.VIEW_AUDIT, Permission.ADMIN_AUDIT_FULL, Permission.PUMP_PROGRAM,
        Permission.CLMA_SCAN, Permission.CLMA_FIVE_RIGHTS,
        Permission.CLMA_ADMINISTER, Permission.CLMA_OVERRIDE,
    },

    CPOERole.RESIDEN_SR: {
        # Prescribe reguler + high-alert DENGAN countersign DPJP
        Permission.MED_ORDER_REGULAR, Permission.MED_ORDER_HIGH_ALERT,
        Permission.MED_ORDER_VERBAL,
        Permission.LAB_ORDER, Permission.IMAGING_ORDER,
        Permission.NURSING_ORDER, Permission.DIET_ORDER,
        Permission.CONSULT_ORDER, Permission.PROCEDURE_ORDER,
        Permission.ORDER_CANCEL, Permission.ORDER_SET_ACTIVATE,
        Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
        Permission.CLMA_SCAN, Permission.CLMA_FIVE_RIGHTS,
    },

    CPOERole.RESIDEN_JR: {
        # Draft only — semua order butuh countersign DPJP/Residen Sr sebelum aktif
        Permission.MED_ORDER_REGULAR,   # draft only
        Permission.LAB_ORDER, Permission.IMAGING_ORDER,
        Permission.NURSING_ORDER, Permission.DIET_ORDER,
        Permission.CONSULT_ORDER,
        Permission.ORDER_VIEW_OWN,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
    },

    CPOERole.CO_ASS: {
        # View only + CPPT entry
        Permission.ORDER_VIEW_OWN,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
    },

    CPOERole.PERAWAT_PK3: {
        Permission.MED_ORDER_VERBAL,    # TBAK verbal order
        Permission.MED_ADMINISTER,
        Permission.NURSING_ORDER,
        Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
        Permission.CLMA_SCAN, Permission.CLMA_FIVE_RIGHTS,
        Permission.CLMA_ADMINISTER, Permission.CLMA_OVERRIDE,
        Permission.PUMP_PROGRAM,
    },

    CPOERole.PERAWAT_PK2: {
        Permission.MED_ORDER_VERBAL,
        Permission.MED_ADMINISTER,
        Permission.NURSING_ORDER,
        Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT, Permission.EDIT_CPPT,
        Permission.CLMA_SCAN, Permission.CLMA_FIVE_RIGHTS,
        Permission.CLMA_ADMINISTER,
        Permission.PUMP_PROGRAM,
    },

    CPOERole.PERAWAT_PK1: {
        Permission.MED_ADMINISTER,
        Permission.NURSING_ORDER,
        Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_CPPT,
        Permission.CLMA_SCAN, Permission.CLMA_FIVE_RIGHTS,
        Permission.CLMA_ADMINISTER,
    },

    CPOERole.APOTEKER: {
        Permission.MED_VERIFY_PHARMACY, Permission.MED_DISPENSE,
        Permission.MED_SUBSTITUTION,
        Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR,
    },

    CPOERole.FARMASI_KLINIK: {
        Permission.MED_VERIFY_PHARMACY,
        Permission.ORDER_VIEW_ALL,
        Permission.VIEW_EMAR, Permission.VIEW_AUDIT,
    },

    CPOERole.GIZI_KLINIK: {
        Permission.DIET_ORDER,
        Permission.ORDER_VIEW_OWN,
        Permission.VIEW_CPPT,
    },

    CPOERole.RADIOGRAFER: {
        Permission.ORDER_VIEW_OWN,
    },

    CPOERole.ADMIN_KLINIK: {
        Permission.ORDER_VIEW_ALL,
        Permission.ADMIN_USER_MGMT,
        Permission.ADMIN_AUDIT_FULL,
    },
}

# Order yang membutuhkan COUNTERSIGN DPJP
REQUIRES_COUNTERSIGN: Set[CPOERole] = {
    CPOERole.RESIDEN_JR,
    CPOERole.RESIDEN_SR,   # untuk high-alert & narkotika
}

# Obat HIGH-ALERT yang hanya boleh di-order oleh DPJP / Residen Sr
HIGH_ALERT_RESTRICTED_ROLES: Set[CPOERole] = {
    CPOERole.DPJP,
    CPOERole.DPJP_UTAMA,
    CPOERole.RESIDEN_SR,
}

# Narkotika/psikotropika — hanya DPJP
NARCOTICS_RESTRICTED_ROLES: Set[CPOERole] = {
    CPOERole.DPJP,
    CPOERole.DPJP_UTAMA,
}


# =============================================================================
# User & Session Models
# =============================================================================

@dataclass
class CPOEUser:
    """Pengguna CPOE yang sudah ter-authentikasi."""
    user_id:      str
    nip:          str
    full_name:    str
    role:         CPOERole
    sip_number:   str = ""    # Surat Izin Praktik
    str_number:   str = ""    # Surat Tanda Registrasi
    department:   str = ""    # SMF / Ruangan
    specialization: str = ""  # SpJP, SpPD, dst.
    is_active:    bool = True
    last_login:   str = ""
    pk_level:     str = ""    # PK I/II/III untuk perawat

    @property
    def permissions(self) -> Set[Permission]:
        return ROLE_PERMISSIONS.get(self.role, set())

    def can(self, perm: Permission) -> bool:
        return perm in self.permissions

    def can_any(self, *perms: Permission) -> bool:
        return any(p in self.permissions for p in perms)

    def can_all(self, *perms: Permission) -> bool:
        return all(p in self.permissions for p in perms)

    @property
    def can_prescribe_regular(self) -> bool:
        return self.can(Permission.MED_ORDER_REGULAR)

    @property
    def can_prescribe_high_alert(self) -> bool:
        return (self.can(Permission.MED_ORDER_HIGH_ALERT)
                and self.role in HIGH_ALERT_RESTRICTED_ROLES)

    @property
    def needs_countersign(self) -> bool:
        return self.role in REQUIRES_COUNTERSIGN

    @property
    def countersign_required_for_high_alert(self) -> bool:
        return self.role == CPOERole.RESIDEN_SR

    @property
    def role_badge(self) -> str:
        return {
            CPOERole.DPJP:          "🩺 DPJP",
            CPOERole.DPJP_UTAMA:    "🩺✨ DPJP Utama",
            CPOERole.RESIDEN_SR:    "👨‍⚕️ Residen Senior",
            CPOERole.RESIDEN_JR:    "👩‍⚕️ Residen Junior",
            CPOERole.CO_ASS:        "🎓 Co-Ass",
            CPOERole.PERAWAT_PK3:   "💙 Perawat PK III",
            CPOERole.PERAWAT_PK2:   "💙 Perawat PK II",
            CPOERole.PERAWAT_PK1:   "💙 Perawat PK I",
            CPOERole.APOTEKER:      "💊 Apoteker",
            CPOERole.FARMASI_KLINIK:"💊 Farmasi Klinik",
            CPOERole.GIZI_KLINIK:   "🥗 Gizi Klinik",
            CPOERole.ADMIN_KLINIK:  "🖥️ Admin",
        }.get(self.role, "👤 Pengguna")

    @property
    def display_name(self) -> str:
        title = ""
        if self.role in (CPOERole.DPJP, CPOERole.DPJP_UTAMA,
                          CPOERole.RESIDEN_SR, CPOERole.RESIDEN_JR,
                          CPOERole.CO_ASS):
            title = "dr. "
        elif self.role in (CPOERole.PERAWAT_PK1, CPOERole.PERAWAT_PK2,
                            CPOERole.PERAWAT_PK3):
            title = ""
        elif self.role == CPOERole.APOTEKER:
            title = "Apt. "
        return f"{title}{self.full_name}"


@dataclass
class CPOEAuthSession:
    """Session aktif — disimpan di st.session_state."""
    session_id:    str
    user:          CPOEUser
    created_at:    str
    expires_at:    str
    last_activity: str
    high_alert_auth_at: str = ""   # kapan terakhir re-auth untuk high-alert
    ip_address:    str = ""
    device_info:   str = ""

    @property
    def is_valid(self) -> bool:
        try:
            return datetime.now() < datetime.fromisoformat(self.expires_at)
        except Exception:
            return False

    @property
    def high_alert_auth_valid(self) -> bool:
        if not self.high_alert_auth_at:
            return False
        try:
            cutoff = datetime.fromisoformat(self.high_alert_auth_at) + \
                     timedelta(minutes=_HIGH_ALERT_TTL_MINUTES)
            return datetime.now() < cutoff
        except Exception:
            return False

    @property
    def remaining_minutes(self) -> int:
        try:
            delta = datetime.fromisoformat(self.expires_at) - datetime.now()
            return max(0, int(delta.total_seconds() / 60))
        except Exception:
            return 0

    def touch(self) -> None:
        """Perpanjang session pada aktivitas."""
        self.last_activity = datetime.now().isoformat()


# =============================================================================
# Authorization Checker
# =============================================================================

class AuthorizationError(Exception):
    """Raised ketika akses ditolak."""
    def __init__(self, message: str, required_role: str = "", user_role: str = ""):
        self.message = message
        self.required_role = required_role
        self.user_role = user_role
        super().__init__(message)


class CPOEAuthChecker:
    """
    Pure logic checker — tidak ada Streamlit dependency.
    Dipakai oleh engine dan gateway untuk gate-keeping setiap action.
    """

    @staticmethod
    def assert_can(user: CPOEUser, perm: Permission, context: str = "") -> None:
        """Raise AuthorizationError jika user tidak memiliki permission."""
        if not user.can(perm):
            raise AuthorizationError(
                message=(
                    f"Akses ditolak: {user.display_name} ({user.role.value}) "
                    f"tidak memiliki izin '{perm.value}'"
                    + (f" — {context}" if context else "")
                ),
                required_role=perm.value,
                user_role=user.role.value,
            )

    @staticmethod
    def check_medication_order(
        user: CPOEUser,
        drug_name: str,
        is_high_alert: bool,
        is_narcotic: bool,
        session: Optional[CPOEAuthSession] = None,
    ) -> Tuple[bool, str, str]:
        """
        Cek apakah user boleh meresepkan obat ini.
        Return: (allowed, warning_message, action_required)
        """
        drug_display = drug_name.upper()

        # ── Narkotika / psikotropika ──────────────────────────────────────────
        if is_narcotic:
            if user.role not in NARCOTICS_RESTRICTED_ROLES:
                return False, (
                    f"🚫 {drug_display} termasuk narkotika/psikotropika. "
                    f"Hanya DPJP yang berwenang meresepkan (UU No. 35/2009)."
                ), "ESCALATE_TO_DPJP"

        # ── High-Alert — role check ───────────────────────────────────────────
        if is_high_alert:
            if user.role not in HIGH_ALERT_RESTRICTED_ROLES:
                return False, (
                    f"🚫 {drug_display} adalah HIGH ALERT MEDICATION. "
                    f"Role {user.role.value} tidak memiliki kewenangan meresepkan. "
                    f"Hubungi DPJP atau Residen Senior."
                ), "ESCALATE_TO_DPJP"

            # Residen Sr → boleh order high-alert TAPI wajib countersign DPJP
            if user.role == CPOERole.RESIDEN_SR:
                # Re-auth setiap 15 menit untuk high-alert
                if session and not session.high_alert_auth_valid:
                    return False, (
                        f"⚠️ {drug_display} adalah high-alert. "
                        f"Re-autentikasi diperlukan (timeout {_HIGH_ALERT_TTL_MINUTES} menit)."
                    ), "REAUTH_HIGH_ALERT"
                return True, (
                    f"⚠️ {drug_display} (HIGH ALERT) — order ini akan aktif setelah "
                    f"countersign DPJP. Pastikan DPJP mengetahui order ini."
                ), "NEEDS_COUNTERSIGN"

        # ── Residen Jr — semua order butuh countersign ────────────────────────
        if user.role == CPOERole.RESIDEN_JR:
            if not user.can(Permission.MED_ORDER_REGULAR):
                return False, (
                    f"🚫 Residen Junior tidak memiliki kewenangan prescribing mandiri."
                ), "ESCALATE_TO_DPJP"
            return True, (
                f"ℹ️ Order sebagai Residen Junior akan tersimpan sebagai DRAFT. "
                f"DPJP atau Residen Senior wajib melakukan countersign sebelum order aktif."
            ), "NEEDS_COUNTERSIGN"

        # ── Co-Ass — tidak boleh sama sekali ──────────────────────────────────
        if user.role == CPOERole.CO_ASS:
            return False, (
                f"🚫 Co-Assistensi tidak memiliki kewenangan prescribing. "
                f"Sampaikan ke Residen atau DPJP."
            ), "ESCALATE_TO_DPJP"

        # ── Perawat — hanya verbal order dengan TBAK ──────────────────────────
        if user.role in (CPOERole.PERAWAT_PK1, CPOERole.PERAWAT_PK2, CPOERole.PERAWAT_PK3):
            if not user.can(Permission.MED_ORDER_VERBAL):
                return False, (
                    f"🚫 {user.role.value} tidak memiliki kewenangan prescribing. "
                    f"Gunakan Verbal Order (TBAK) jika mendapat instruksi lisan DPJP."
                ), "USE_VERBAL_ORDER"
            # PK3 boleh verbal order tapi bukan prescribing mandiri
            return False, (
                f"🚫 Perawat tidak memiliki kewenangan meresepkan secara mandiri "
                f"(UU No. 38/2014 Pasal 30). "
                f"Gunakan form Verbal Order (TBAK) jika ada instruksi lisan DPJP."
            ), "USE_VERBAL_ORDER"

        # ── Apoteker/Farmasi — tidak boleh prescribe ──────────────────────────
        if user.role in (CPOERole.APOTEKER, CPOERole.FARMASI_KLINIK):
            return False, (
                f"🚫 {user.role.value} tidak memiliki kewenangan prescribing. "
                f"Gunakan fitur Rekomendasi Farmasi."
            ), "USE_RECOMMENDATION"

        # ── Default: DPJP / DPJP_UTAMA ───────────────────────────────────────
        if not user.can(Permission.MED_ORDER_REGULAR):
            return False, (
                f"🚫 Kewenangan prescribing tidak ditemukan untuk {user.role.value}."
            ), "ESCALATE_TO_DPJP"

        return True, "", ""

    @staticmethod
    def check_verbal_order(user: CPOEUser, dpjp_nip: str) -> Tuple[bool, str]:
        """Validasi prasyarat Verbal Order (TBAK)."""
        if not user.can(Permission.MED_ORDER_VERBAL):
            return False, (
                f"🚫 {user.role.value} tidak berwenang menerima verbal order."
            )
        if not dpjp_nip.strip():
            return False, "NIP DPJP yang memberikan instruksi lisan wajib diisi."
        return True, ""

    @staticmethod
    def check_countersign(signer: CPOEUser, order_role: CPOERole) -> Tuple[bool, str]:
        """Cek apakah signer berwenang countersign order dari order_role."""
        if not signer.can(Permission.MED_ORDER_COUNTERSIGN):
            return False, (
                f"🚫 {signer.role.value} tidak memiliki kewenangan countersign. "
                f"Hanya DPJP yang dapat countersign order residen."
            )
        if order_role == CPOERole.RESIDEN_JR and signer.role == CPOERole.RESIDEN_SR:
            return True, "✓ Residen Senior dapat countersign order Residen Junior."
        if signer.role in (CPOERole.DPJP, CPOERole.DPJP_UTAMA):
            return True, "✓ DPJP memiliki kewenangan countersign penuh."
        return False, f"🚫 {signer.role.value} tidak dapat countersign order {order_role.value}."


# =============================================================================
# Database Layer
# =============================================================================

@contextmanager
def _conn():
    _AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_AUTH_DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_auth_database() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS cpoe_users (
            user_id       TEXT PRIMARY KEY,
            nip           TEXT UNIQUE NOT NULL,
            full_name     TEXT NOT NULL,
            role          TEXT NOT NULL,
            sip_number    TEXT,
            str_number    TEXT,
            department    TEXT,
            specialization TEXT,
            pk_level      TEXT,
            is_active     INTEGER DEFAULT 1,
            password_hash TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now','localtime')),
            last_login    TEXT
        );

        CREATE TABLE IF NOT EXISTS cpoe_sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            nip           TEXT NOT NULL,
            created_at    TEXT,
            expires_at    TEXT,
            last_activity TEXT,
            high_alert_auth_at TEXT,
            is_active     INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS cpoe_countersigns (
            cs_id         TEXT PRIMARY KEY,
            order_id      TEXT NOT NULL,
            episode_id    TEXT,
            original_nip  TEXT,
            original_role TEXT,
            signer_nip    TEXT NOT NULL,
            signer_name   TEXT,
            signer_role   TEXT,
            signed_at     TEXT,
            notes         TEXT
        );

        CREATE TABLE IF NOT EXISTS cpoe_auth_log (
            log_id     TEXT PRIMARY KEY,
            timestamp  TEXT,
            nip        TEXT,
            action     TEXT,
            result     TEXT,
            detail     TEXT,
            ip_address TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_nip ON cpoe_users(nip);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON cpoe_sessions(user_id);
        """)
        # Seed user default jika tabel kosong
        count = con.execute("SELECT COUNT(*) FROM cpoe_users").fetchone()[0]
        if count == 0:
            _seed_default_users(con)


def _hash_password(password: str, salt: str = "RSJPDHK_CPOE_2024") -> str:
    return hmac.new(
        salt.encode(), password.encode(), hashlib.sha256
    ).hexdigest()



# =============================================================================
# Auth Service
# =============================================================================

class CPOEAuthService:
    """Service autentikasi + session management."""

    @staticmethod
    def login(nip: str, password: str) -> Tuple[Optional[CPOEAuthSession], str]:
        """
        Autentikasi NIP + password.
        Return (session, error_message). Session=None jika gagal.
        """
        pwd_hash = _hash_password(password)
        with _conn() as con:
            row = con.execute("""
                SELECT * FROM cpoe_users
                WHERE nip=? AND password_hash=? AND is_active=1
            """, (nip.strip(), pwd_hash)).fetchone()

            if not row:
                CPOEAuthService._log(nip, "LOGIN_FAILED", "DENIED",
                                      "NIP/password tidak sesuai atau akun nonaktif", con)
                return None, "NIP atau password salah, atau akun tidak aktif."

            user = CPOEAuthService._row_to_user(dict(row))
            now = datetime.now()
            sess_id = str(uuid.uuid4())
            expires = (now + timedelta(minutes=_TOKEN_TTL_MINUTES)).isoformat()

            con.execute("""
                INSERT INTO cpoe_sessions
                (session_id, user_id, nip, created_at, expires_at, last_activity, is_active)
                VALUES (?,?,?,?,?,?,1)
            """, (sess_id, user.user_id, user.nip, now.isoformat(), expires, now.isoformat()))

            con.execute("UPDATE cpoe_users SET last_login=? WHERE nip=?",
                        (now.isoformat(), nip))

            CPOEAuthService._log(nip, "LOGIN_SUCCESS", "GRANTED",
                                  f"Role: {user.role.value}", con)

        session = CPOEAuthSession(
            session_id=sess_id, user=user,
            created_at=now.isoformat(), expires_at=expires,
            last_activity=now.isoformat(),
        )
        return session, ""

    @staticmethod
    def verify_high_alert(
        session: CPOEAuthSession, nip: str, password: str
    ) -> Tuple[bool, str]:
        """Re-autentikasi khusus untuk high-alert medication."""
        _, err = CPOEAuthService.login(nip, password)
        if err:
            return False, f"Re-autentikasi gagal: {err}"
        if nip != session.user.nip:
            return False, "NIP tidak sesuai dengan session aktif."
        session.high_alert_auth_at = datetime.now().isoformat()
        return True, "✓ Re-autentikasi high-alert berhasil."

    @staticmethod
    def save_countersign(
        order_id: str, episode_id: str,
        original_nip: str, original_role: CPOERole,
        signer: CPOEUser, notes: str = "",
    ) -> str:
        cs_id = f"CS-{uuid.uuid4().hex[:8].upper()}"
        with _conn() as con:
            con.execute("""
                INSERT INTO cpoe_countersigns VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (cs_id, order_id, episode_id, original_nip, original_role.value,
                  signer.nip, signer.display_name, signer.role.value,
                  datetime.now().isoformat(), notes))
            CPOEAuthService._log(signer.nip, "COUNTERSIGN", "GRANTED",
                                  f"Order {order_id} by {original_nip}", con)
        return cs_id

    @staticmethod
    def get_all_users() -> List[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM cpoe_users ORDER BY role, full_name"
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_auth_log(nip: str = "", limit: int = 50) -> List[dict]:
        with _conn() as con:
            if nip:
                rows = con.execute("""
                    SELECT * FROM cpoe_auth_log WHERE nip=?
                    ORDER BY timestamp DESC LIMIT ?
                """, (nip, limit)).fetchall()
            else:
                rows = con.execute("""
                    SELECT * FROM cpoe_auth_log
                    ORDER BY timestamp DESC LIMIT ?
                """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_user(row: dict) -> CPOEUser:
        role = next((r for r in CPOERole if r.value == row["role"]), CPOERole.ADMIN_KLINIK)
        return CPOEUser(
            user_id       = row["user_id"],
            nip           = row["nip"],
            full_name     = row["full_name"],
            role          = role,
            sip_number    = row.get("sip_number", ""),
            str_number    = row.get("str_number", ""),
            department    = row.get("department", ""),
            specialization= row.get("specialization", ""),
            pk_level      = row.get("pk_level", ""),
            is_active     = bool(row.get("is_active", 1)),
            last_login    = row.get("last_login", ""),
        )

    @staticmethod
    def _log(nip: str, action: str, result: str, detail: str, con=None) -> None:
        log_id = f"AL-{uuid.uuid4().hex[:8].upper()}"
        entry = (log_id, datetime.now().isoformat(), nip, action, result, detail, "")
        if con:
            con.execute("INSERT INTO cpoe_auth_log VALUES (?,?,?,?,?,?,?)", entry)
        else:
            with _conn() as c:
                c.execute("INSERT INTO cpoe_auth_log VALUES (?,?,?,?,?,?,?)", entry)


# =============================================================================
# Streamlit Session Helpers
# =============================================================================

def get_cpoe_session() -> Optional[CPOEAuthSession]:
    """Ambil session aktif dari st.session_state. None jika belum login."""
    sess = st.session_state.get(_SESSION_KEY_AUTH)
    if sess and sess.is_valid:
        sess.touch()
        return sess
    return None


def set_cpoe_session(session: CPOEAuthSession) -> None:
    st.session_state[_SESSION_KEY_AUTH] = session


def clear_cpoe_session() -> None:
    st.session_state.pop(_SESSION_KEY_AUTH, None)


def require_cpoe_auth(
    permission: Optional[Permission] = None,
    show_login: bool = True,
) -> Optional[CPOEAuthSession]:
    """
    Guard function — pastikan ada session valid.
    Tampilkan login form jika belum ada.
    Return session atau None.
    """
    init_auth_database()
    session = get_cpoe_session()

    if not session:
        if show_login:
            render_cpoe_login()
        return None

    if permission and not session.user.can(permission):
        st.error(
            f"🚫 Akses ditolak — {session.user.role_badge} tidak memiliki "
            f"kewenangan: **{permission.value}**"
        )
        return None

    return session


# =============================================================================
# Login UI Component
# =============================================================================

def render_cpoe_login() -> None:
    """
    Login form CPOE — standalone Streamlit component.
    Menampilkan tabel demo user yang dikelompokkan per kategori role.
    """
    st.markdown("### 🔐 Login CPOE — Smart EMR RSJPDHK")
    st.caption(
        "Login CPPT (perawat) **tidak** otomatis memberi akses prescribing. "
        "Setiap PPA login CPOE dengan NIP masing-masing sesuai kewenangan klinis."
    )

    with st.form("cpoe_login_form", clear_on_submit=False):
        nip      = st.text_input("NIP:", placeholder="Nomor Induk Pegawai")
        password = st.text_input("Password:", type="password")
        col1, col2 = st.columns([1, 3])
        submitted = col1.form_submit_button(
            "🔑 Login", type="primary", use_container_width=True
        )

    if submitted:
        if not nip or not password:
            st.error("NIP dan password wajib diisi.")
            return
        session, err = CPOEAuthService.login(nip, password)
        if session:
            set_cpoe_session(session)
            st.success(
                f"✓ Login berhasil — {session.user.role_badge} "
                f"**{session.user.display_name}**"
            )
            st.rerun()
        else:
            st.error(f"🚫 {err}")
            st.caption("Akses gagal dicatat di audit log keamanan.")

    # ── Demo credentials — dikelompokkan per kategori ─────────────────────────
    with st.expander("👥 Demo User CPOE — semua 13 role (klik untuk lihat)"):
        st.caption("Password semua user: **1234**")

        groups = {
            "🩺 Dokter": [
                ("198501010001", "dr. Budi Santoso, Sp.JP",
                 "DPJP",
                 "Prescribing penuh, countersign, order set"),
                ("198903070007", "dr. Hana Putri, Sp.JP(K)",
                 "DPJP Utama",
                 "Sama + audit trail penuh + verifikasi konsulen"),
                ("199001020002", "dr. Dewi Rahayu",
                 "Residen Senior",
                 "Prescribing reguler & high-alert → wajib countersign DPJP"),
                ("199503030003", "dr. Ahmad Fauzi",
                 "Residen Junior",
                 "Draft only → semua order wajib countersign DPJP"),
                ("200001080008", "dr. Anisa Pratiwi",
                 "Co-Ass",
                 "View-only + input CPPT — tidak bisa meresepkan"),
            ],
            "💙 Perawat": [
                ("199201040004", "Rudi Haryanto, S.Kep. Ners. M.M.",
                 "Perawat PK III",
                 "Verbal order TBAK + administrasi + 5-Rights + override darurat"),
                ("199405050005", "Sari Indah, S.Kep. Ners.",
                 "Perawat PK II",
                 "Verbal order TBAK + administrasi + 5-Rights"),
                ("200002090009", "Bima Sakti, A.Md.Kep.",
                 "Perawat PK I",
                 "Administrasi obat + scan 5-Rights — tidak bisa verbal order"),
            ],
            "💊 Farmasi": [
                ("199107060006", "Apt. Maya Sari, S.Farm. M.Farm.",
                 "Apoteker",
                 "Verifikasi + dispensing + substitusi generik"),
                ("199208100010", "Apt. Dian Puspita, S.Farm. Klin.",
                 "Farmasi Klinik",
                 "Verifikasi + rekomendasi DUE — tidak bisa dispense"),
            ],
            "🥗 Non-Medis Klinis": [
                ("199310110011", "Novi Rahmawati, S.Gz.",
                 "Ahli Gizi Klinik",
                 "Order diet/nutrisi saja"),
                ("199612120012", "Hendra Wijaya, A.Md.Rad.",
                 "Radiografer",
                 "View-only — tidak bisa membuat order apapun"),
            ],
            "🖥️ Admin": [
                ("199001130013", "Dewi Anggraeni, S.Kom.",
                 "Admin Klinik",
                 "Manajemen user + audit trail — tanpa akses klinis"),
            ],
        }

        for group_name, users in groups.items():
            st.markdown(f"**{group_name}**")
            import pandas as pd
            df = pd.DataFrame(
                users,
                columns=["NIP", "Nama", "Role", "Kewenangan Utama"],
            )
            st.dataframe(df, hide_index=True, use_container_width=True)


def render_cpoe_session_info(session: CPOEAuthSession) -> None:
    """Tampilkan info session di sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🔐 CPOE Session")
    st.sidebar.write(f"{session.user.role_badge}")
    st.sidebar.write(f"**{session.user.display_name}**")
    st.sidebar.caption(
        f"NIP: {session.user.nip}  \n"
        f"SMF: {session.user.department}  \n"
        f"Session: {session.remaining_minutes} mnt tersisa"
    )
    if st.sidebar.button("🔓 Logout CPOE", key="cpoe_logout"):
        clear_cpoe_session()
        st.rerun()


def render_high_alert_reauth(session: CPOEAuthSession) -> bool:
    """
    Re-autentikasi popup untuk high-alert medication.
    Return True jika berhasil.
    """
    st.warning(
        f"🔴 **RE-AUTENTIKASI DIPERLUKAN**\n\n"
        f"Obat ini termasuk HIGH ALERT MEDICATION. "
        f"Re-autentikasi berlaku selama {_HIGH_ALERT_TTL_MINUTES} menit."
    )
    with st.form("high_alert_reauth", clear_on_submit=True):
        nip_reauth = st.text_input("NIP:", value=session.user.nip)
        pwd_reauth = st.text_input("Password:", type="password")
        submit = st.form_submit_button("🔑 Konfirmasi Identitas", type="primary")
    if submit:
        ok, msg = CPOEAuthService.verify_high_alert(session, nip_reauth, pwd_reauth)
        if ok:
            st.success(msg)
            return True
        st.error(msg)
    return False

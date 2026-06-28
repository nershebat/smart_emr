"""
Auth Database — Persistensi user credentials, profil, dan audit log.

Database terpisah (`users.db`) dari database CPPT utama.
Berisi:
  - user_accounts: credentials & profil dasar
  - user_audit_log: log login/logout & aktivitas sensitif
  - roles_permissions: referensi role & permissions (opsional)
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List, Dict

import pandas as pd

from .auth_system import hash_password, UserRole

AUTH_DB_PATH = "users.db"


def _connect() -> sqlite3.Connection:
    """Buat koneksi ke database auth"""
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
    return conn


def init_auth_database() -> None:
    """Inisialisasi tabel auth — idempotent"""
    conn = _connect()
    cur = conn.cursor()

    # ── Tabel User Accounts ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_accounts (
            user_id          TEXT PRIMARY KEY,
            username         TEXT UNIQUE NOT NULL,
            password_hash    TEXT NOT NULL,
            nama_lengkap     TEXT NOT NULL,
            role             TEXT NOT NULL,
            profesi          TEXT NOT NULL,
            department       TEXT,
            email            TEXT,
            telepon          TEXT,
            nomor_sip_nik    TEXT,
            aktif            BOOLEAN DEFAULT 1,
            created_at       TEXT,
            updated_at       TEXT,
            last_login       TEXT
        )
    """)

    # ── Tabel Audit Log ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT,
            username         TEXT,
            aksi             TEXT,
            status           TEXT,
            ip_address       TEXT,
            detail           TEXT,
            timestamp        TEXT
        )
    """)

    conn.commit()
    conn.close()


# ── Create/Read/Update User ────────────────────────────────────────────────

def create_user(
    user_id: str,
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
    """
    Buat user baru.
    
    Returns:
        (success: bool, message: str)
    """
    conn = _connect()
    cur = conn.cursor()
    
    try:
        # Cek duplicate username
        cur.execute("SELECT user_id FROM user_accounts WHERE username = ?", (username,))
        if cur.fetchone():
            return False, f"Username '{username}' sudah terdaftar."
        
        password_hash = hash_password(password)
        now = datetime.now().isoformat()
        
        cur.execute("""
            INSERT INTO user_accounts
            (user_id, username, password_hash, nama_lengkap, role, profesi,
             department, email, telepon, nomor_sip_nik, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, username, password_hash, nama_lengkap,
            role.value, profesi, department, email, telepon, nomor_sip_nik,
            now, now
        ))
        
        conn.commit()
        conn.close()
        return True, f"User '{nama_lengkap}' berhasil dibuat."
    
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"


def get_user_by_username(username: str) -> Optional[Dict]:
    """Ambil data user berdasarkan username"""
    conn = _connect()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT * FROM user_accounts WHERE username = ? AND aktif = 1",
        (username,)
    )
    row = cur.fetchone()
    conn.close()
    
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Ambil data user berdasarkan user_id"""
    conn = _connect()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT * FROM user_accounts WHERE user_id = ? AND aktif = 1",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    
    return dict(row) if row else None


def get_all_users(role: Optional[UserRole] = None) -> List[Dict]:
    """
    Ambil semua user, opsional filter by role.
    """
    conn = _connect()
    
    if role:
        df = pd.read_sql_query(
            "SELECT * FROM user_accounts WHERE aktif = 1 AND role = ? ORDER BY nama_lengkap",
            conn,
            params=(role.value,)
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM user_accounts WHERE aktif = 1 ORDER BY nama_lengkap",
            conn
        )
    
    conn.close()
    return df.to_dict("records") if not df.empty else []


def update_user(
    user_id: str,
    **kwargs
) -> Tuple[bool, str]:
    """
    Update field user (email, telepon, nama_lengkap, dst).
    
    Jangan gunakan untuk update password — pakai change_password().
    """
    conn = _connect()
    cur = conn.cursor()
    
    # Fields yang boleh di-update
    allowed_fields = {
        "nama_lengkap", "email", "telepon", "department", "nomor_sip_nik"
    }
    
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return False, "Tidak ada field untuk diupdate."
    
    updates["updated_at"] = datetime.now().isoformat()
    
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [user_id]
    
    try:
        cur.execute(
            f"UPDATE user_accounts SET {set_clause} WHERE user_id = ?",
            values
        )
        conn.commit()
        conn.close()
        return True, "Update user berhasil."
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"


def change_password(
    user_id: str,
    old_password: str,
    new_password: str,
) -> Tuple[bool, str]:
    """
    Ubah password user. Verifikasi old_password terlebih dahulu.
    """
    conn = _connect()
    cur = conn.cursor()
    
    # Ambil hash password saat ini
    cur.execute("SELECT password_hash FROM user_accounts WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    
    if not row:
        return False, "User tidak ditemukan."
    
    current_hash = row[0]
    
    # Verifikasi old_password
    from .auth_system import verify_password
    if not verify_password(old_password, current_hash):
        return False, "Password lama tidak sesuai."
    
    # Update password
    new_hash = hash_password(new_password)
    try:
        cur.execute(
            "UPDATE user_accounts SET password_hash = ?, updated_at = ? WHERE user_id = ?",
            (new_hash, datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        return True, "Password berhasil diubah."
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"


def deactivate_user(user_id: str) -> Tuple[bool, str]:
    """Nonaktifkan user (soft delete)"""
    conn = _connect()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "UPDATE user_accounts SET aktif = 0, updated_at = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        return True, "User berhasil dinonaktifkan."
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"


def activate_user(user_id: str) -> Tuple[bool, str]:
    """Aktifkan kembali user yang sudah nonaktif"""
    conn = _connect()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "UPDATE user_accounts SET aktif = 1, updated_at = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        return True, "User berhasil diaktifkan."
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"


# ── Audit Log ──────────────────────────────────────────────────────────────

def log_auth_activity(
    user_id: str,
    username: str,
    aksi: str,
    status: str,
    detail: str = "",
    ip_address: str = "",
) -> None:
    """
    Log aktivitas auth (login, logout, failed_login, password_change, dst).
    
    Args:
        aksi: "LOGIN", "LOGOUT", "FAILED_LOGIN", "PASSWORD_CHANGE", dst
        status: "SUCCESS", "FAILED"
    """
    conn = _connect()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO auth_audit_log
        (user_id, username, aksi, status, ip_address, detail, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, username, aksi, status, ip_address, detail,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()


def update_last_login(user_id: str) -> None:
    """Update timestamp last_login untuk user"""
    conn = _connect()
    cur = conn.cursor()
    
    cur.execute(
        "UPDATE user_accounts SET last_login = ? WHERE user_id = ?",
        (datetime.now().isoformat(), user_id)
    )
    
    conn.commit()
    conn.close()


def get_audit_log(
    user_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict]:
    """Ambil auth audit log, opsional filter by user_id"""
    conn = _connect()
    
    if user_id:
        df = pd.read_sql_query(
            "SELECT * FROM auth_audit_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            conn,
            params=(user_id, limit)
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM auth_audit_log ORDER BY timestamp DESC LIMIT ?",
            conn,
            params=(limit,)
        )
    
    conn.close()
    return df.to_dict("records") if not df.empty else []

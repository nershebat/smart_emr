"""
Persistensi data order CPOE dan diagnosis dokter ke SQLite.
Memakai file terpisah (`doctor_orders.db`) — tidak mengganggu
database CPPT utama (`rsjpdhk_emr.db` milik dashboard.py).

FIXED: Juga sync orders ke rsjpdhk_emr.db cpoe_orders table
"""

import json
import sqlite3
from typing import List, Optional
from datetime import datetime

import pandas as pd

from .models import Diagnosis, MedicalOrder, OrderStatus

DOCTOR_DB_PATH = "doctor_orders.db"
MAIN_DB_PATH = "rsjpdhk_emr.db"  # ← ADD THIS

# ─────────────────────────────────────────────────────────────────────────
# Dashboard CPPT (dashboard.py) membaca order lewat tabel `cpoe_orders`
# (via CPOESyncManager) dan memfilter HANYA dengan kode pendek huruf kecil:
#   order_type in {"obat", "lab", "ventilator", "bundle"}
# Sementara `OrderType` di modules/doctor/models.py memakai label tampilan
# yang readable untuk dokter, misal "Obat", "Laboratorium", "Setting
# Ventilator". Tanpa mapping ini, order_type yang ditulis ke cpoe_orders
# TIDAK PERNAH cocok dengan filter dashboard ("Obat" != "obat", dst), jadi
# order yang dibuat dokter tidak pernah muncul di tab Perawat/Apoteker —
# inilah akar masalah "CPOE tidak sinkron ke dashboard utama".
# ─────────────────────────────────────────────────────────────────────────
_ORDER_TYPE_TO_DASHBOARD_CODE = {
    "Obat":                  "obat",
    "Cairan IV":              "obat",
    "Laboratorium":           "lab",
    "Radiologi":              "lab",
    "Diet":                   "bundle",
    "Prosedur":               "bundle",
    "Instruksi Keperawatan":  "bundle",
    "Konsultasi":             "bundle",
    "Setting Ventilator":     "ventilator",
    "Lainnya":                "bundle",
}


def _to_dashboard_order_type(tipe: str) -> str:
    """Normalisasi label OrderType ke kode pendek yang dipakai filter tab
    di dashboard.py. Default ke 'bundle' jika tidak dikenali, supaya order
    tetap terlihat (bukan hilang diam-diam)."""
    return _ORDER_TYPE_TO_DASHBOARD_CODE.get(tipe, "bundle")


def _to_dashboard_status(status: str) -> str:
    """Normalisasi status lokal (Indonesia) ke vocabulary yang dipakai
    CPOESyncManager/dashboard.py. Hanya status 'Dibatalkan' yang KRITIS
    untuk dipetakan, karena dashboard.py menyembunyikan order dengan
    `WHERE status != 'cancelled'`. Status lain (Aktif/Dilaksanakan/Selesai)
    diteruskan apa adanya — tetap lolos filter, dan tetap informatif."""
    if status == OrderStatus.DIBATAL.value:
        return "cancelled"
    return status


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DOCTOR_DB_PATH)


def _connect_main() -> sqlite3.Connection:
    """Connect ke main database untuk sync CPOE"""
    return sqlite3.connect(MAIN_DB_PATH)


def init_database() -> None:
    """Inisialisasi tabel — idempotent (aman dipanggil berulang kali)."""
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medical_orders (
            order_id            TEXT PRIMARY KEY,
            episode_id          TEXT NOT NULL,
            dokter_id           TEXT,
            dokter_nama         TEXT,
            tipe                TEXT,
            nama_order          TEXT,
            detail_json         TEXT,
            prioritas           TEXT,
            status              TEXT,
            catatan             TEXT,
            timestamp_order     TEXT,
            timestamp_verifikasi TEXT,
            verifikator         TEXT,
            icd10_terkait       TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS diagnoses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id      TEXT NOT NULL,
            kode_icd10      TEXT,
            nama_penyakit   TEXT,
            tipe            TEXT,
            catatan         TEXT,
            timestamp       TEXT,
            dokter_id       TEXT,
            status          TEXT DEFAULT 'Aktif'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cpoe_audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT,
            episode_id      TEXT,
            aksi            TEXT,
            user_id         TEXT,
            timestamp       TEXT,
            detail          TEXT
        )
    """)

    conn.commit()
    conn.close()
    
    # Also init main database CPOE table
    _init_main_db()


def _init_main_db() -> None:
    """Initialize cpoe_orders table in main database"""
    try:
        conn = _connect_main()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cpoe_orders (
                order_id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL,
                patient_no_rm TEXT,
                order_type TEXT,
                order_name TEXT,
                order_content TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not initialize main DB: {e}")


# ── Orders ─────────────────────────────────────────────────────────────────

def save_order(order: MedicalOrder) -> None:
    """Save order to doctor_orders.db AND sync to main rsjpdhk_emr.db"""
    
    # 1. Save to doctor_orders.db (original)
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO medical_orders
        (order_id, episode_id, dokter_id, dokter_nama, tipe, nama_order,
         detail_json, prioritas, status, catatan, timestamp_order,
         timestamp_verifikasi, verifikator, icd10_terkait)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        order.order_id, order.episode_id, order.dokter_id, order.dokter_nama,
        order.tipe, order.nama_order, json.dumps(order.detail, ensure_ascii=False),
        order.prioritas, order.status, order.catatan, order.timestamp_order,
        order.timestamp_verifikasi, order.verifikator, order.icd10_terkait,
    ))
    conn.commit()
    conn.close()
    
    # 2. ALSO sync to main database cpoe_orders (NEW!)
    try:
        conn_main = _connect_main()
        cur_main = conn_main.cursor()
        
        cur_main.execute("""
            INSERT OR REPLACE INTO cpoe_orders
            (order_id, episode_id, patient_no_rm, order_type, order_name, 
             order_content, status, created_by, updated_by)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            order.order_id,
            order.episode_id,
            getattr(order, 'patient_no_rm', ''),
            _to_dashboard_order_type(order.tipe),  # FIX: kode pendek, bukan label asli
            order.nama_order,  # order_name
            json.dumps(order.detail, ensure_ascii=False),  # order_content
            _to_dashboard_status(order.status),
            order.dokter_id,  # created_by
            order.dokter_id   # updated_by
        ))
        
        conn_main.commit()
        conn_main.close()
    except Exception as e:
        print(f"Warning: Could not sync to main DB: {e}")


def get_active_orders(episode_id: str) -> list[dict]:
    conn = _connect()
    df = pd.read_sql_query(
        "SELECT * FROM medical_orders WHERE episode_id=? AND status=? ORDER BY timestamp_order DESC",
        conn, params=(episode_id, OrderStatus.AKTIF.value)
    )
    conn.close()
    if df.empty:
        return []
    rows = df.to_dict("records")
    for r in rows:
        try:
            r["detail"] = json.loads(r.get("detail_json", "{}"))
        except Exception:
            r["detail"] = {}
    return rows


def get_all_orders(episode_id: str) -> list[dict]:
    conn = _connect()
    df = pd.read_sql_query(
        "SELECT * FROM medical_orders WHERE episode_id=? ORDER BY timestamp_order DESC",
        conn, params=(episode_id,)
    )
    conn.close()
    if df.empty:
        return []
    rows = df.to_dict("records")
    for r in rows:
        try:
            r["detail"] = json.loads(r.get("detail_json", "{}"))
        except Exception:
            r["detail"] = {}
    return rows


def update_order_status(order_id: str, status: str, verifikator: str = "") -> None:
    """Update order status in BOTH databases"""
    ts = datetime.now().isoformat()
    
    # Update in doctor_orders.db
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE medical_orders SET status=?, verifikator=?, timestamp_verifikasi=? WHERE order_id=?",
        (status, verifikator, ts, order_id)
    )
    conn.commit()
    conn.close()
    
    # Also update in main database (NEW!)
    try:
        conn_main = _connect_main()
        cur_main = conn_main.cursor()
        cur_main.execute(
            "UPDATE cpoe_orders SET status=?, updated_at=? WHERE order_id=?",
            (_to_dashboard_status(status), ts, order_id)
        )
        conn_main.commit()
        conn_main.close()
    except Exception as e:
        print(f"Warning: Could not update main DB: {e}")


def cancel_order(order_id: str, cancelled_by: str) -> None:
    update_order_status(order_id, OrderStatus.DIBATAL.value, cancelled_by)
    _log_audit(order_id, "", "BATAL", cancelled_by, "Order dibatalkan")


# ── Diagnoses ──────────────────────────────────────────────────────────────

def save_diagnosis(dx: Diagnosis) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO diagnoses
        (episode_id, kode_icd10, nama_penyakit, tipe, catatan, timestamp, dokter_id, status)
        VALUES (?,?,?,?,?,?,?,?)
    """, (dx.episode_id, dx.kode_icd10, dx.nama_penyakit, dx.tipe,
          dx.catatan, dx.timestamp, dx.dokter_id, dx.status))
    conn.commit()
    conn.close()


def get_active_diagnoses(episode_id: str) -> list[dict]:
    conn = _connect()
    df = pd.read_sql_query(
        "SELECT * FROM diagnoses WHERE episode_id=? AND status='Aktif' ORDER BY id",
        conn, params=(episode_id,)
    )
    conn.close()
    return df.to_dict("records") if not df.empty else []


def get_all_diagnoses(episode_id: str) -> list[dict]:
    conn = _connect()
    df = pd.read_sql_query(
        "SELECT * FROM diagnoses WHERE episode_id=? ORDER BY id",
        conn, params=(episode_id,)
    )
    conn.close()
    return df.to_dict("records") if not df.empty else []


def deactivate_diagnosis(dx_id: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE diagnoses SET status='Tidak Aktif' WHERE id=?", (dx_id,))
    conn.commit()
    conn.close()


# ── Audit Log ──────────────────────────────────────────────────────────────

def _log_audit(order_id: str, episode_id: str, aksi: str, user_id: str, detail: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cpoe_audit_log (order_id, episode_id, aksi, user_id, timestamp, detail) "
        "VALUES (?,?,?,?,?,?)",
        (order_id, episode_id, aksi, user_id, datetime.now().isoformat(), detail)
    )
    conn.commit()
    conn.close()


def get_audit_log(episode_id: str) -> list[dict]:
    conn = _connect()
    df = pd.read_sql_query(
        "SELECT * FROM cpoe_audit_log WHERE episode_id=? ORDER BY timestamp DESC",
        conn, params=(episode_id,)
    )
    conn.close()
    return df.to_dict("records") if not df.empty else []
"""
services/database.py
====================
Semua operasi database untuk Smart EMR: pasien, SLKI scores, CPPT records.
"""

import logging
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

# Inisialisasi logger
logger = logging.getLogger(__name__)

DB_PATH = Path("rsjpdhk_emr.db")


@contextmanager
def _get_db():
    """Context manager koneksi SQLite dengan autocommit."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Inisialisasi semua tabel database jika belum ada."""
    # Mencegah eksekusi berulang di setiap rerun Streamlit
    if st.session_state.get("db_initialized", False):
        return

    try:
        with _get_db() as conn:
            # Tabel pasien
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pasien (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id      TEXT    NOT NULL UNIQUE,
                    no_rm           TEXT    NOT NULL,
                    nama_pasien     TEXT    NOT NULL,
                    tanggal_lahir   TEXT,
                    jenis_kelamin   TEXT,
                    ruangan         TEXT,
                    dpjp            TEXT,
                    dibuat_pada     TEXT    NOT NULL,
                    status          TEXT    NOT NULL DEFAULT 'AKTIF'
                )
            """)
            
            # Tabel SLKI evaluation scores
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pelayanan_slki_evaluasi (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id      TEXT    NOT NULL,
                    waktu_evaluasi  TEXT    NOT NULL,
                    nama_indikator  TEXT    NOT NULL,
                    skor_indikator  INTEGER NOT NULL CHECK(skor_indikator BETWEEN 1 AND 5),
                    oleh_pegawai    TEXT    NOT NULL
                )
            """)
            
            # Indices
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pasien_episode "
                "ON pasien(episode_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slki_episode "
                "ON pelayanan_slki_evaluasi(episode_id, waktu_evaluasi DESC)"
            )
        
        # Log sukses di console, jangan di UI
        logger.info("✅ Database initialized successfully")
        
        # Set flag agar fungsi ini tidak dieksekusi lagi di sesi ini
        st.session_state.db_initialized = True
        
    except Exception as exc:
        # Log error di console
        logger.error(f"❌ Database initialization failed: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════
# PASIEN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════


def generate_episode_id() -> str:
    """Generate unique episode ID dengan format EP-YYYY-XXXXX."""
    with _get_db() as conn:
        while True:
            kandidat = f"EP-{datetime.now().year}-{random.randint(10000, 99999)}"
            cek = conn.execute(
                "SELECT 1 FROM pasien WHERE episode_id = ?", (kandidat,)
            ).fetchone()
            if not cek:
                return kandidat


def insert_pasien(
    no_rm: str,
    nama_pasien: str,
    tanggal_lahir: str = "",
    jenis_kelamin: str = "",
    ruangan: str = "",
    dpjp: str = "",
) -> str:
    """
    Daftarkan pasien baru dan return episode_id.
    
    Returns:
        Episode ID pasien yang baru didaftarkan
    """
    episode_id = generate_episode_id()
    
    with _get_db() as conn:
        conn.execute(
            """INSERT INTO pasien
               (episode_id, no_rm, nama_pasien, tanggal_lahir, jenis_kelamin,
                ruangan, dpjp, dibuat_pada, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'AKTIF')""",
            (
                episode_id, no_rm.strip(), nama_pasien.strip(),
                tanggal_lahir.strip(), jenis_kelamin,
                ruangan.strip(), dpjp.strip(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    
    return episode_id


def get_pasien_by_episode(episode_id: str) -> Optional[Dict]:
    """Ambil data pasien berdasarkan episode_id."""
    try:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT * FROM pasien WHERE episode_id = ?", (episode_id,)
            ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        logger.warning(f"⚠️ Error fetching patient: {exc}")
        return None


def get_all_pasien(hanya_aktif: bool = True) -> List[Dict]:
    """Ambil daftar pasien untuk dropdown selection."""
    try:
        with _get_db() as conn:
            query = "SELECT * FROM pasien"
            params = ()
            
            if hanya_aktif:
                query += " WHERE status = ?"
                params = ("AKTIF",)
            
            query += " ORDER BY dibuat_pada DESC"
            rows = conn.execute(query, params).fetchall()
        
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"⚠️ Error fetching patients: {exc}")
        return []


# ═══════════════════════════════════════════════════════════════════════
# SLKI SCORES
# ═══════════════════════════════════════════════════════════════════════


def insert_slki_score(
    episode_id: str,
    indikator: str,
    skor: int,
    pegawai: str,
) -> bool:
    """
    Simpan skor evaluasi SLKI untuk pasien.
    
    Returns:
        True jika berhasil, False jika gagal
    """
    try:
        with _get_db() as conn:
            conn.execute(
                """INSERT INTO pelayanan_slki_evaluasi
                   (episode_id, waktu_evaluasi, nama_indikator, skor_indikator, oleh_pegawai)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    indikator,
                    skor,
                    pegawai,
                ),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ Gagal menyimpan skor SLKI: {exc}")
        return False


def get_latest_slki_scores(episode_id: str) -> List[tuple]:
    """
    Ambil skor SLKI terakhir untuk setiap indikator pasien.
    
    Returns:
        List of tuples: (nama_indikator, skor_indikator)
    """
    try:
        with _get_db() as conn:
            rows = conn.execute(
                """SELECT nama_indikator, skor_indikator
                   FROM pelayanan_slki_evaluasi
                   WHERE id IN (
                       SELECT MAX(id)
                       FROM pelayanan_slki_evaluasi
                       WHERE episode_id = ?
                       GROUP BY nama_indikator
                   )""",
                (episode_id,),
            ).fetchall()
        
        return [(r["nama_indikator"], r["skor_indikator"]) for r in rows]
    except Exception as exc:
        logger.warning(f"⚠️ Error fetching SLKI scores: {exc}")
        return []


def fetch_slki_trends(episode_id: str) -> pd.DataFrame:
    """
    Ambil data tren SLKI untuk grafik.
    
    Returns:
        DataFrame dengan columns: Waktu Evaluasi, Skor Indikator, Kriteria Hasil (SLKI)
    """
    try:
        with _get_db() as conn:
            df = pd.read_sql_query(
                """SELECT
                       strftime('%d/%m %H:%M', waktu_evaluasi) AS "Waktu Evaluasi",
                       skor_indikator                           AS "Skor Indikator",
                       nama_indikator                           AS "Kriteria Hasil (SLKI)"
                   FROM pelayanan_slki_evaluasi
                   WHERE episode_id = ?
                   ORDER BY waktu_evaluasi ASC""",
                conn,
                params=(episode_id,),
            )
        return df
    except Exception as exc:
        logger.error(f"⚠️ Error fetching SLKI trends: {exc}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════


def is_database_available() -> bool:
    """Check apakah database dapat diakses."""
    try:
        with _get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False
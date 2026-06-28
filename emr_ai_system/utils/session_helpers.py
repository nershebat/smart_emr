"""
utils/session_helpers.py
========================
Helper functions untuk mengelola Streamlit session state.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

import streamlit as st


def init_session() -> None:
    """
    Inisialisasi session state klinis (idempoten).
    Aman dipanggil berulang kali tanpa side effects.
    """
    defaults = {
        # Pasien & Episode
        "episode_id":       None,
        "pasien_dipilih":   False,
        "pasien_no_rm":     "",
        "pasien_nama":      "",
        "pasien_tgl_lahir": "",
        "pasien_jk":        "",
        "pasien_ruangan":   "",
        "pasien_dpjp":      "",
        
        # CPPT & Asuhan
        "daftar_asuhan":    None,
        "draft_cppt":       None,
        "order_list":       {},
        "logbook_payload":  [],
        "checked_items":    {},
        "hasil_cdss":       None,
        "sumber_cdss_terakhir": "",
        "daftar_diagnosis": [],
        "selected_dx_codes": set(),
        "soap_A":           "",
        "soap_P":           "",
        
        # Voice-to-Text
        "s_text_area":      "",
        "o_text_area":      "",
        "last_audio_s_id":  None,
        "last_audio_o_id":  None,
        
        # Audit
        "emergency_logs":   [],
        
        # Dokter-specific
        "diagnosa_aktif":   [],
        "hasil_cdss_dokter": None,
        "soap_A_dokter":    "",
        "soap_P_dokter":    "",
        "draft_cppt_dokter": None,
        
        # Apoteker & Gizi
        "draft_cppt_apoteker": None,
        "draft_cppt_gizi":     None,
    }
    
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def set_active_patient(episode_id: str, pasien_data: Optional[Dict] = None) -> None:
    """
    Terapkan pasien terpilih ke session_state dan reset working-state klinis
    pasien sebelumnya.
    
    Args:
        episode_id: ID episode pasien yang akan diaktifkan
        pasien_data: Dict data pasien (optional, akan di-fetch jika None)
    """
    if pasien_data is None:
        # Import here untuk avoid circular imports
        from services.database import get_pasien_by_episode
        pasien_data = get_pasien_by_episode(episode_id) or {}

    st.session_state.update({
        "episode_id":       episode_id,
        "pasien_no_rm":     pasien_data.get("no_rm", ""),
        "pasien_nama":      pasien_data.get("nama_pasien", ""),
        "pasien_tgl_lahir": pasien_data.get("tanggal_lahir", ""),
        "pasien_jk":        pasien_data.get("jenis_kelamin", ""),
        "pasien_ruangan":   pasien_data.get("ruangan", ""),
        "pasien_dpjp":      pasien_data.get("dpjp", ""),
        "pasien_dipilih":   True,
        
        # Reset working-state klinis
        "daftar_asuhan":       None,
        "draft_cppt":          None,
        "order_list":          {},
        "logbook_payload":     [],
        "checked_items":       {},
        "hasil_cdss":          None,
        "sumber_cdss_terakhir": "",
        "daftar_diagnosis":    [],
        "selected_dx_codes":   set(),
        "soap_A":              "",
        "soap_P":              "",
        "s_text_area":         "",
        "o_text_area":         "",
        "last_audio_s_id":     None,
        "last_audio_o_id":     None,
        
        # Reset role-specific drafts
        "draft_cppt_apoteker": None,
        "draft_cppt_gizi":     None,
        "draft_cppt_dokter":   None,
        "soap_A_dokter":       "",
        "soap_P_dokter":       "",
    })


def is_session_expired(ttl_minutes: int = 60) -> bool:
    """
    Kembalikan True jika sesi sudah melewati TTL (Time-To-Live).
    
    Args:
        ttl_minutes: Durasi sesi dalam menit (default: 60)
        
    Returns:
        True jika sesi expired, False jika masih valid
    """
    if not st.session_state.get("login_at"):
        return False
    
    elapsed = datetime.now() - st.session_state.login_at
    return elapsed > timedelta(minutes=ttl_minutes)


def get_session_ttl_remaining(ttl_minutes: int = 60) -> int:
    """
    Hitung sisa waktu sesi dalam menit.
    
    Args:
        ttl_minutes: Total durasi sesi dalam menit
        
    Returns:
        Jumlah menit yang tersisa (minimal 0)
    """
    if not st.session_state.get("login_at"):
        return ttl_minutes
    
    elapsed = int((datetime.now() - st.session_state.login_at).total_seconds() / 60)
    remaining = ttl_minutes - elapsed
    return max(0, remaining)


def clear_clinical_state() -> None:
    """Hapus semua clinical working state (untuk reset pasien baru)."""
    clinical_keys = [
        "episode_id", "pasien_dipilih", "pasien_no_rm", "pasien_nama",
        "pasien_tgl_lahir", "pasien_jk", "pasien_ruangan", "pasien_dpjp",
        "daftar_asuhan", "draft_cppt", "order_list", "logbook_payload",
        "checked_items", "hasil_cdss", "sumber_cdss_terakhir",
        "daftar_diagnosis", "selected_dx_codes", "soap_A", "soap_P",
        "s_text_area", "o_text_area", "last_audio_s_id", "last_audio_o_id",
        "emergency_logs", "diagnosa_aktif", "hasil_cdss_dokter",
        "soap_A_dokter", "soap_P_dokter", "draft_cppt_dokter",
        "draft_cppt_apoteker", "draft_cppt_gizi",
    ]
    
    for key in clinical_keys:
        st.session_state.pop(key, None)


def get_auth_context() -> Dict:
    """
    Ambil context autentikasi lengkap dari session_state.
    
    Returns:
        Dict dengan keys: user_id, role, nama_lengkap, shift, login_at
    """
    return {
        "user_id": st.session_state.get("user_id", ""),
        "role": st.session_state.get("role", "Perawat"),
        "nama_lengkap": st.session_state.get("nama_lengkap", ""),
        "shift": st.session_state.get("shift", ""),
        "login_at": st.session_state.get("login_at"),
        "authenticated": st.session_state.get("authenticated", False),
    }


def is_authenticated() -> bool:
    """Check apakah user sudah terautentikasi."""
    return st.session_state.get("authenticated", False) or st.session_state.get("logged_in", False)


def is_user_role(expected_role: str) -> bool:
    """
    Check apakah user memiliki role yang diharapkan.
    
    Args:
        expected_role: Role yang dicek (e.g., "Dokter", "Perawat", "Apoteker")
        
    Returns:
        True jika user memiliki role tersebut
    """
    current_role = st.session_state.get("role", "").lower()
    return current_role == expected_role.lower()

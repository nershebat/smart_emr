"""
Centralized Session State Manager
File: modules/session_manager.py
"""

import streamlit as st
from typing import Any


class SessionManager:
    """Centralized manager untuk session_state keys"""
    
    # Auth Keys
    AUTH_AUTHENTICATED = "authenticated"
    AUTH_USER_ID = "user_id"
    AUTH_NAMA_LENGKAP = "nama_lengkap"
    AUTH_ROLE = "role"
    AUTH_PROFESI = "profesi"
    AUTH_DEPARTMENT = "department"
    AUTH_LOGIN_TIME = "login_time"
    
    # CPPT Keys
    CPPT_LOGGED_IN = "logged_in"
    CPPT_PASIEN_DIPILIH = "pasien_dipilih"
    CPPT_EPISODE_ID = "episode_id"
    CPPT_PASIEN_NAMA = "pasien_nama"
    CPPT_PASIEN_NO_RM = "pasien_no_rm"
    CPPT_PASIEN_RUANGAN = "pasien_ruangan"
    CPPT_SHIFT = "shift"
    CPPT_USER_ID = "user_id"
    
    # SOAP Keys (Standardized)
    SOAP_S = "s_text_area"
    SOAP_O = "o_text_area"
    SOAP_A = "a_text_area"
    SOAP_P = "p_text_area"
    
    # CPOE Keys
    CPOE_ORDERS = "cpoe_orders"
    CPOE_DIAGNOSES = "diagnosa_aktif"
    CPOE_DOKTER_ID = "dokter_id"
    CPOE_DOKTER_NAMA = "dokter_nama"
    
    @staticmethod
    def initialize_all() -> None:
        """Initialize semua session keys"""
        SessionManager.set_default(SessionManager.AUTH_AUTHENTICATED, False)
        SessionManager.set_default(SessionManager.AUTH_USER_ID, "")
        SessionManager.set_default(SessionManager.AUTH_ROLE, "Guest")
        SessionManager.set_default(SessionManager.CPPT_LOGGED_IN, False)
        SessionManager.set_default(SessionManager.CPPT_PASIEN_DIPILIH, False)
        SessionManager.set_default(SessionManager.CPPT_EPISODE_ID, "")
        SessionManager.set_default(SessionManager.SOAP_S, "")
        SessionManager.set_default(SessionManager.SOAP_O, "")
        SessionManager.set_default(SessionManager.SOAP_A, "")
        SessionManager.set_default(SessionManager.SOAP_P, "")
        SessionManager.set_default(SessionManager.CPOE_ORDERS, [])
        SessionManager.set_default(SessionManager.CPOE_DIAGNOSES, [])
    
    @staticmethod
    def set_default(key: str, default_value: Any) -> None:
        """Set default value jika key belum ada"""
        if key not in st.session_state:
            st.session_state[key] = default_value
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get value dari session"""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key: str, value: Any) -> None:
        """Set value di session"""
        st.session_state[key] = value
    
    @staticmethod
    def clear_auth() -> None:
        """Clear auth keys"""
        auth_keys = [
            SessionManager.AUTH_AUTHENTICATED,
            SessionManager.AUTH_USER_ID,
            SessionManager.AUTH_NAMA_LENGKAP,
            SessionManager.AUTH_ROLE,
        ]
        for key in auth_keys:
            st.session_state.pop(key, None)
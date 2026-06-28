import streamlit as st
from modules.device_monitoring.clma_tab import render_clma_tab

# 1. Pastikan pengguna sudah login ke sistem
if "logged_in" in st.session_state and st.session_state["logged_in"]:
    
    # 2. Ambil objek connector dari session_state (jika sudah di-inisialisasi oleh sistem)
    connector = st.session_state.get("device_connector", None)
    
    # 3. Susun 'ctx' (context dictionary) berdasarkan pasien aktif di session state
    # Kita sesuaikan dengan parameter yang dibutuhkan oleh fungsi clma_tab
    ctx = {
        "episode_id": st.session_state.get("episode_id", ""),
        "no_rm": st.session_state.get("no_rm", ""),
        "nama_pasien": st.session_state.get("nama", ""),
    }
    
    # 4. Validasi apakah pasien sudah dipilih di dashboard utama
    if ctx["episode_id"]:
        # Tampilkan judul halaman
        st.title("🔂 Closed Loop Medication Administration (CLMA)")
        
        # Panggil fungsi utama CLMA dengan parameter yang sudah siap
        render_clma_tab(connector, ctx)
    else:
        st.warning("⚠️ Belum ada pasien yang dipilih. Silakan kembali ke Dashboard Utama untuk memilih pasien terlebih dahulu.")

else:
    st.error("🔒 Akses Ditolak. Silakan lakukan otentikasi/login terlebih dahulu di halaman utama.")
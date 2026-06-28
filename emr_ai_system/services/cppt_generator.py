"""
services/cppt_generator.py
==========================
Service untuk generate CPPT (Catatan Perkembangan Pasien Terintegrasi)
dan dokumentasi per profesi (Perawat, Dokter, Apoteker, Gizi).
"""

from datetime import datetime
from typing import List, Dict, Optional

import streamlit as st

from config.sdki_mappings import SDKI_NAME_MAPPING, DX_TO_SLKI_MAPPING
from utils.text_helpers import parse_intervensi
from services.database import get_latest_slki_scores


def generate_cppt_perawat(
    daftar_asuhan: List[Dict],
    subjektif: str,
    objektif: str,
) -> tuple[str, List[Dict]]:
    """
    Generate CPPT untuk Perawat dengan SDKI/SLKI/SIKI framework.
    
    Args:
        daftar_asuhan: Daftar diagnosis keperawatan yang dipilih
        subjektif: Data S dari input
        objektif: Data O dari input
        
    Returns:
        Tuple of (cppt_text, logbook_entries)
    """
    episode_id = st.session_state.get("episode_id", "-")
    pasien_nama = st.session_state.get("pasien_nama", "-")
    pasien_rm = st.session_state.get("pasien_no_rm", "-")
    pasien_ruang = st.session_state.get("pasien_ruangan", "-")
    user_id = st.session_state.get("user_id", "Perawat")
    shift = st.session_state.get("shift", "-")
    
    # Header CPPT
    cppt = "CATATAN PERKEMBANGAN PASIEN TERINTEGRASI (CPPT) — PERAWAT\n"
    cppt += "=" * 70 + "\n"
    cppt += f"ID Episode : {episode_id} | Shift: {shift}\n"
    cppt += f"Tanggal    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    cppt += f"Pasien     : {pasien_nama} | No. RM: {pasien_rm} | Ruangan: {pasien_ruang}\n"
    cppt += "=" * 70 + "\n\n"
    
    # SOAP S & O
    cppt += f"S: {subjektif.strip()}\n"
    cppt += f"O: {objektif.strip()}\n\n"
    
    # Assessment - Diagnosis
    cppt += "A (Assessment / Diagnosa Keperawatan):\n"
    latest_slki = get_latest_slki_scores(episode_id)
    
    for idx, asuhan in enumerate(daftar_asuhan, 1):
        kode_dx = asuhan.get("kode_diagnosa", "ERR").strip()
        nama_dx = SDKI_NAME_MAPPING.get(kode_dx, "Diagnosa Tidak Diketahui")
        
        status_rekomendasi = " | Terkini -> Belum ada skor perkembangan terbaru."
        mapping_info = DX_TO_SLKI_MAPPING.get(kode_dx)
        
        if latest_slki and mapping_info:
            for slki_nama, skor in latest_slki:
                if mapping_info["kode_luaran"] in slki_nama:
                    status_rekomendasi = f" | Terkini -> {mapping_info['narasi']} [Skor Akhir: {skor}/5]"
                    break
        
        cppt += f"   {idx}. ({kode_dx}) {nama_dx}{status_rekomendasi}\n"
    
    cppt += "\n"
    
    # Plan - Intervensi terpilih
    cppt += "P (Perencanaan / Tindakan Keperawatan):\n"
    logbook_entries = []
    checked = st.session_state.get("checked_items", {})
    
    for asuhan in daftar_asuhan:
        kode = asuhan.get("kode_diagnosa", "N/A").strip()
        nama_diag = SDKI_NAME_MAPPING.get(kode, "Diagnosa Keperawatan")
        
        intervensi_raw = asuhan.get("rencana_intervensi", {})
        tindakan_dipilih = []
        
        for pilar in ["Observasi", "Terapeutik", "Edukasi", "Kolaborasi"]:
            if pilar not in intervensi_raw:
                continue
            
            items_teks = parse_intervensi(intervensi_raw[pilar])
            statuses = checked.get(kode, {}).get(pilar, [])
            
            for i, item_text in enumerate(items_teks):
                if isinstance(item_text, dict):
                    item_text = item_text.get("nama", "")
                item_text = str(item_text).strip()
                
                if i < len(statuses) and statuses[i] and item_text not in tindakan_dipilih:
                    tindakan_dipilih.append(item_text)
                    logbook_entries.append({
                        "timestamp": datetime.now().isoformat(),
                        "nip_pegawai": st.session_state.get("user_id", "-"),
                        "shift": shift,
                        "episode_id": episode_id,
                        "kode_siki": item_text,
                        "kode_diagnosa": kode,
                    })
        
        if tindakan_dipilih:
            cppt += f"- ({kode}) {nama_diag}: {', '.join(tindakan_dipilih)}.\n"
        else:
            cppt += f"- ({kode}) {nama_diag}: Lanjutkan intervensi sesuai rencana dasar.\n"
    
    cppt += f"\nDivalidasi oleh: {user_id.upper()} (Perawat)\n"
    
    return cppt, logbook_entries


def generate_catatan_dokter(
    subjektif: str,
    objektif: str,
) -> str:
    """
    Generate catatan untuk Dokter (Assessment Medis & Plan Tatalaksana).
    
    Note: Ini BUKAN CDSS — hanya dokumentasi untuk diedit manual sesuai
    hasil analisis CDSS ICD-10.
    """
    episode_id = st.session_state.get("episode_id", "-")
    pasien_nama = st.session_state.get("pasien_nama", "-")
    pasien_rm = st.session_state.get("pasien_no_rm", "-")
    pasien_ruang = st.session_state.get("pasien_ruangan", "-")
    user_id = st.session_state.get("user_id", "Dokter")
    shift = st.session_state.get("shift", "-")
    
    draft = "CATATAN PERKEMBANGAN PASIEN TERINTEGRASI (CPPT) — DOKTER\n"
    draft += "=" * 70 + "\n"
    draft += f"ID Episode : {episode_id} | Shift: {shift}\n"
    draft += f"Tanggal    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    draft += f"Pasien     : {pasien_nama} | No. RM: {pasien_rm} | Ruangan: {pasien_ruang}\n"
    draft += "=" * 70 + "\n\n"
    
    draft += f"S: {subjektif.strip()}\n"
    draft += f"O: {objektif.strip()}\n\n"
    
    draft += (
        "A (Assessment / Diagnosis Medis):\n"
        "   Lengkapi diagnosis ICD-10 berdasarkan analisis CDSS (tombol 'Analisis ICD-10')\n\n"
    )
    
    draft += (
        "P (Plan / Tatalaksana Medis):\n"
        "   Lengkapi rencana tatalaksana berdasarkan rekomendasi CDSS.\n"
        "   Tentukan prioritas tindakan (KRITIS, SEGERA, TINGGI, SEDANG).\n\n"
    )
    
    draft += f"Divalidasi oleh: {user_id.upper()} (DPJP)\n"
    
    return draft


def generate_catatan_farmasi(
    subjektif: str,
    objektif: str,
) -> str:
    """
    Generate catatan untuk Apoteker (Tinjauan Farmasi Klinis).
    
    Note: Murni dokumentasi manual — tinjau interaksi obat, dosis, dll.
    dari order CPOE yang ditampilkan di halaman.
    """
    episode_id = st.session_state.get("episode_id", "-")
    pasien_nama = st.session_state.get("pasien_nama", "-")
    pasien_rm = st.session_state.get("pasien_no_rm", "-")
    pasien_ruang = st.session_state.get("pasien_ruangan", "-")
    user_id = st.session_state.get("user_id", "Apoteker")
    shift = st.session_state.get("shift", "-")
    
    draft = "CATATAN PELAYANAN KEFARMASIAN (CPPT) — APOTEKER\n"
    draft += "=" * 70 + "\n"
    draft += f"ID Episode : {episode_id} | Shift: {shift}\n"
    draft += f"Tanggal    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    draft += f"Pasien     : {pasien_nama} | No. RM: {pasien_rm} | Ruangan: {pasien_ruang}\n"
    draft += "=" * 70 + "\n\n"
    
    draft += f"S: {subjektif.strip()}\n"
    draft += f"O: {objektif.strip()}\n\n"
    
    draft += (
        "A (Tinjauan Farmasi):\n"
        "   - Interaksi Obat: [Lengkapi]\n"
        "   - Duplikasi Terapi: [Lengkapi]\n"
        "   - Kesesuaian Dosis: [Lengkapi]\n"
        "   - Kontraindikasi: [Lengkapi]\n\n"
    )
    
    draft += (
        "P (Rencana Farmasi):\n"
        "   - Rekomendasi Penyesuaian Obat: [Lengkapi]\n"
        "   - Follow-up: [Lengkapi]\n\n"
    )
    
    draft += f"Divalidasi oleh: {user_id.upper()} (Apoteker)\n"
    
    return draft


def generate_catatan_gizi(
    subjektif: str,
    objektif: str,
) -> str:
    """
    Generate catatan untuk Ahli Gizi (Asuhan Gizi Klinis).
    
    Note: Murni dokumentasi manual — asesmen status gizi & rencana diet.
    """
    episode_id = st.session_state.get("episode_id", "-")
    pasien_nama = st.session_state.get("pasien_nama", "-")
    pasien_rm = st.session_state.get("pasien_no_rm", "-")
    pasien_ruang = st.session_state.get("pasien_ruangan", "-")
    user_id = st.session_state.get("user_id", "Ahli Gizi")
    shift = st.session_state.get("shift", "-")
    
    draft = "CATATAN ASUHAN GIZI (CPPT) — AHLI GIZI\n"
    draft += "=" * 70 + "\n"
    draft += f"ID Episode : {episode_id} | Shift: {shift}\n"
    draft += f"Tanggal    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    draft += f"Pasien     : {pasien_nama} | No. RM: {pasien_rm} | Ruangan: {pasien_ruang}\n"
    draft += "=" * 70 + "\n\n"
    
    draft += f"S: {subjektif.strip()}\n"
    draft += f"O: {objektif.strip()}\n\n"
    
    draft += (
        "A (Asesmen Gizi):\n"
        "   - Status Gizi (BB/TB/IMT): [Lengkapi]\n"
        "   - Riwayat Diet: [Lengkapi]\n"
        "   - Kebutuhan Kalori/Protein: [Lengkapi]\n"
        "   - Diagnosis Gizi: [Lengkapi]\n\n"
    )
    
    draft += (
        "P (Rencana Diet):\n"
        "   - Jenis Diet: [Lengkapi]\n"
        "   - Intervensi Gizi: [Lengkapi]\n"
        "   - Edukasi Nutrisi: [Lengkapi]\n\n"
    )
    
    draft += f"Divalidasi oleh: {user_id.upper()} (Ahli Gizi)\n"
    
    return draft

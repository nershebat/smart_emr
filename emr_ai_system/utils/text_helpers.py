"""
utils/text_helpers.py
=====================
Fungsi helper untuk text processing, parsing, dan truncation.
"""

import re
from typing import List


def clean_text(text: str) -> str:
    """
    Bersihkan teks dari markdown formatting dan whitespace berlebih.
    
    Args:
        text: Text dengan markdown formatting
        
    Returns:
        Text yang sudah dibersihkan
    """
    text = re.sub(r"#{1,3}\s?", "", text)  # Hapus markdown headers
    text = re.sub(r"\*\*", "", text)        # Hapus bold markers
    text = re.sub(r"^- ", "", text, flags=re.MULTILINE)  # Hapus bullet points
    text = re.sub(r"\n\s*\n", "\n\n", text)  # Normalize whitespace
    return text.strip()


def parse_intervensi(detail: str) -> List[str]:
    """
    Pisahkan teks intervensi berdasarkan titik-koma atau newline.
    
    Args:
        detail: Teks intervensi dengan delimiter ; atau \n
        
    Returns:
        List of intervensi items (trimmed)
        
    Example:
        >>> parse_intervensi("Monitor HR; Monitor BP; Monitor SpO2")
        ['Monitor HR', 'Monitor BP', 'Monitor SpO2']
    """
    return [t.strip() for t in re.split(r"[;\n]", detail) if t.strip()]


def truncate_text(txt: str, max_length: int) -> str:
    """
    Potong teks jika melebihi max_length, tambahkan ellipsis.
    
    Args:
        txt: Teks yang ingin dipotong
        max_length: Maksimal jumlah karakter
        
    Returns:
        Teks yang sudah dipotong (atau original jika lebih pendek)
        
    Example:
        >>> truncate_text("Monitor jantung dan tekanan darah", 20)
        'Monitor jantung dan …'
    """
    txt = (txt or "").strip()
    return txt[:max_length] + "…" if len(txt) > max_length else txt


def normalize_role_name(role: str) -> str:
    """
    Normalkan nama role ke format standar.
    
    Args:
        role: Role name (case-insensitive)
        
    Returns:
        Normalized role name
        
    Example:
        >>> normalize_role_name("dokter")
        'Dokter'
        >>> normalize_role_name("PERAWAT")
        'Perawat'
    """
    mapping = {
        "dokter": "Dokter",
        "perawat": "Perawat",
        "apoteker": "Apoteker",
        "ahli gizi": "Ahli Gizi",
        "gizi": "Gizi",
        "fisioterapi": "Fisioterapi",
    }
    role_lower = role.lower().strip()
    return mapping.get(role_lower, role.title())


def format_episode_id() -> str:
    """Generate unique episode ID dengan format EP-YYYY-XXXXX."""
    from datetime import datetime
    import random
    
    year = datetime.now().year
    random_part = random.randint(10000, 99999)
    return f"EP-{year}-{random_part}"


def parse_timestamp(timestamp_str: str, format_str: str = "%d/%m/%Y %H:%M") -> str:
    """
    Parse timestamp string dan return formatted.
    
    Args:
        timestamp_str: Timestamp string
        format_str: Format output yang diinginkan
        
    Returns:
        Formatted timestamp or original if parsing fails
    """
    from datetime import datetime
    
    formats_to_try = [
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]
    
    for fmt in formats_to_try:
        try:
            dt = datetime.strptime(timestamp_str, fmt)
            return dt.strftime(format_str)
        except ValueError:
            continue
    
    return timestamp_str  # Return original jika tidak bisa di-parse

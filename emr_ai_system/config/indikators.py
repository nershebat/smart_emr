"""
config/indikators.py
====================
Master data indikator SLKI (Standar Luaran Keperawatan Indonesia)
untuk evaluasi perkembangan pasien di ICU Surgical Dewasa RSJPDHK.
"""

INDIKATOR_SLKI = [
    # ── Respirasi (7 indikator) ──────────────────────────────────────────
    "Bersihan Jalan Napas (L.01001)",
    "Penyapihan Ventilator (L.01002)",
    "Pertukaran Gas (L.01003)",
    "Pola Napas (L.01004)",
    "Respons Ventilasi Mekanik (L.01005)",
    "Tingkat Aspirasi (L.01006)",
    "Ventilasi Spontan (L.01007)",

    # ── Sirkulasi & Jantung (10 indikator) ───────────────────────────────
    "Curah Jantung (L.02008)",
    "Keseimbangan Asam Basa (L.02009)",
    "Perfusi Miokard (L.02010)",
    "Perfusi Perifer (L.02011)",
    "Tingkat Perdarahan (L.02012)",
    "Perfusi Pulmonal (L.02013)",
    "Perfusi Serebral (L.02014)",
    "Sirkulasi Spontan (L.02015)",
    "Status Kardiopulmonal (L.02016)",

    # ── Nutrisi & Cairan (6 indikator) ───────────────────────────────────
    "Status Cairan (L.03028)",
    "Status Nutrisi (L.03030)",
    "Berat Badan (L.03018)",
    "Fungsi Gastrointestinal (L.03019)",
    "Nafsu Makan (L.03024)",
    "Keseimbangan Elektrolit (L.03021)",

    # ── Eliminasi (3 indikator) ──────────────────────────────────────────
    "Eliminasi Fekal (L.04033)",
    "Eliminasi Urin (L.04034)",
    "Kontinensia Urin (L.04036)",

    # ── Aktivitas & Istirahat (6 indikator) ──────────────────────────────
    "Ambulasi (L.05001)",
    "Konservasi Energi (L.05040)",
    "Mobilitas Fisik (L.05042)",
    "Toleransi Aktivitas (L.05047)",
    "Status Tidur (L.05045)",

    # ── Persepsi Kognisi (4 indikator) ───────────────────────────────────
    "Komunikasi Verbal (L.13118)",
    "Orientasi Kognitif (L.09082)",
    "Status Neurologis (L.06053)",
    "Memori (L.09074)",

    # ── Kenyamanan (3 indikator) ─────────────────────────────────────────
    "Kontrol Nyeri (L.08065)",
    "Tingkat Nyeri (L.08066)",
    "Tingkat Kenyamanan (L.08064)",

    # ── Integritas Ego / Psikologis (4 indikator) ────────────────────────
    "Tingkat Ansietas (L.09093)",
    "Tingkat Depresi (L.09096)",
    "Tingkat Stres (L.09092)",
    "Harga Diri (L.09069)",

    # ── Keamanan & Proteksi (6 indikator) ────────────────────────────────
    "Integritas Kulit dan Jaringan (L.14125)",
    "Pemulihan Pascabedah (L.14129)",
    "Tingkat Cedera (L.14136)",
    "Tingkat Infeksi (L.14137)",
    "Tingkat Jatuh (L.14138)",

    # ── Pertumbuhan & Perkembangan (2 indikator) ─────────────────────────
    "Ketahanan Personal (L.09074)",
    "Penyesuaian Sosial (L.13121)",
]

# Mapping indikator ke kategori klinis
INDIKATOR_KATEGORI = {
    # Respirasi
    "L.01001": "Respirasi",
    "L.01002": "Respirasi",
    "L.01003": "Respirasi",
    "L.01004": "Respirasi",
    "L.01005": "Respirasi",
    "L.01006": "Respirasi",
    "L.01007": "Respirasi",
    # Sirkulasi & Jantung
    "L.02008": "Sirkulasi",
    "L.02009": "Sirkulasi",
    "L.02010": "Sirkulasi",
    "L.02011": "Sirkulasi",
    "L.02012": "Sirkulasi",
    "L.02013": "Sirkulasi",
    "L.02014": "Sirkulasi",
    "L.02015": "Sirkulasi",
    "L.02016": "Sirkulasi",
    # Nutrisi & Cairan
    "L.03018": "Nutrisi",
    "L.03019": "Nutrisi",
    "L.03021": "Nutrisi",
    "L.03028": "Nutrisi",
    "L.03024": "Nutrisi",
    "L.03030": "Nutrisi",
    # Eliminasi
    "L.04033": "Eliminasi",
    "L.04034": "Eliminasi",
    "L.04036": "Eliminasi",
    # Aktivitas & Istirahat
    "L.05001": "Aktivitas",
    "L.05040": "Aktivitas",
    "L.05042": "Aktivitas",
    "L.05045": "Aktivitas",
    "L.05047": "Aktivitas",
    # Persepsi Kognisi
    "L.06053": "Kognisi",
    "L.09074": "Kognisi",
    "L.09082": "Kognisi",
    "L.13118": "Kognisi",
    # Kenyamanan
    "L.08064": "Kenyamanan",
    "L.08065": "Kenyamanan",
    "L.08066": "Kenyamanan",
    # Psikologis
    "L.09069": "Psikologis",
    "L.09092": "Psikologis",
    "L.09093": "Psikologis",
    "L.09096": "Psikologis",
    # Keamanan & Proteksi
    "L.14125": "Keamanan",
    "L.14129": "Keamanan",
    "L.14136": "Keamanan",
    "L.14137": "Keamanan",
    "L.14138": "Keamanan",
    # Pertumbuhan
    "L.13121": "Sosial",
}

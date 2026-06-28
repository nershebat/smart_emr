"""
config/sdki_mappings.py
=======================
Master data SDKI (Standar Diagnosis Keperawatan Indonesia),
SLKI (Standar Luaran Keperawatan Indonesia),
dan SIKI (Standar Intervensi Keperawatan Indonesia).

Format: SDKI_CODE -> {
    'nama': nama diagnosis,
    'luaran': SLKI outcome code + narasi,
    'intervensi': dict of SIKI intervensi per pilar
}
"""

# Nama diagnosis SDKI (untuk reference)
SDKI_NAME_MAPPING = {
    "D.0001": "Bersihan Jalan Napas Tidak Efektif",
    "D.0002": "Gangguan Penyapihan Ventilator",
    "D.0003": "Gangguan Pertukaran Gas",
    "D.0004": "Gangguan Ventilasi Spontan",
    "D.0005": "Pola Napas Tidak Efektif",
    "D.0006": "Risiko Aspirasi",
    "D.0007": "Gangguan Sirkulasi Spontan",
    "D.0008": "Penurunan Curah Jantung",
    "D.0009": "Perfusi Perifer Tidak Efektif",
    "D.0010": "Risiko Gangguan Sirkulasi Spontan",
    "D.0011": "Risiko Penurunan Curah Jantung",
    "D.0012": "Risiko Perdarahan",
    "D.0013": "Risiko Perfusi Pulmonal Tidak Efektif",
    "D.0014": "Gangguan Perfusi Serebral",
    "D.0015": "Risiko Perfusi Miokard Tidak Efektif",
    "D.0016": "Gangguan Status Kardiopulmonal",
    "D.0017": "Risiko Perfusi Serebral Tidak Efektif",
    "D.0018": "Risiko Perfusi Pulmonal Tidak Efektif",
    "D.0019": "Risiko Perfusi Perifer Tidak Efektif",
    "D.0020": "Defisit Nutrisi",
    "D.0021": "Ketidakseimbangan Asam Basa",
    "D.0022": "Hipervolemia",
    "D.0023": "Hipovolemia",
    "D.0024": "Gangguan Menelan",
    "D.0025": "Ketidakstabilan Kadar Glukosa Darah",
    "D.0026": "Risiko Defisit Nutrisi",
    "D.0037": "Risiko Ketidakseimbangan Elektrolit",
    "D.0038": "Konstipasi",
    "D.0039": "Gangguan Eliminasi Urin",
    "D.0040": "Diare",
    "D.0041": "Inkontinensia Urin Fungsional",
    "D.0043": "Retensi Urin",
    "D.0054": "Gangguan Mobilitas Fisik",
    "D.0055": "Gangguan Pola Tidur",
    "D.0056": "Intoleransi Aktivitas",
    "D.0057": "Keletihan",
    "D.0058": "Hambatan Ambulasi",
    "D.0062": "Gangguan Komunikasi Verbal",
    "D.0063": "Konfusi Akut",
    "D.0064": "Gangguan Memori",
    "D.0077": "Nyeri Akut",
    "D.0078": "Nyeri Kronis",
    "D.0079": "Sindrom Nyeri Kronis",
    "D.0080": "Ansietas",
    "D.0081": "Berduka",
    "D.0082": "Gangguan Citra Tubuh",
    "D.0087": "Ketidakberdayaan",
    "D.0109": "Risiko Syok",
    "D.0129": "Gangguan Integritas Kulit/Jaringan",
    "D.0130": "Risiko Gangguan Integritas Kulit/Jaringan",
    "D.0131": "Risiko Komplikasi Pascabedah",
    "D.0136": "Risiko Jatuh",
    "D.0137": "Risiko Cedera",
    "D.0142": "Risiko Infeksi",
    "D.0143": "Infeksi",
}

# Mapping SDKI -> SLKI outcome
DX_TO_SLKI_MAPPING = {
    # Respirasi
    "D.0001": {"kode_luaran": "L.01001", "narasi": "Bersihan Jalan Napas Meningkat (L.01001)"},
    "D.0002": {"kode_luaran": "L.01002", "narasi": "Penyapihan Ventilator Meningkat (L.01002)"},
    "D.0003": {"kode_luaran": "L.01003", "narasi": "Pertukaran Gas Meningkat (L.01003)"},
    "D.0004": {"kode_luaran": "L.01007", "narasi": "Ventilasi Spontan Meningkat (L.01007)"},
    "D.0005": {"kode_luaran": "L.01004", "narasi": "Pola Napas Membaik (L.01004)"},
    "D.0006": {"kode_luaran": "L.01006", "narasi": "Tingkat Aspirasi Menurun (L.01006)"},
    
    # Sirkulasi
    "D.0007": {"kode_luaran": "L.02015", "narasi": "Sirkulasi Spontan Meningkat (L.02015)"},
    "D.0008": {"kode_luaran": "L.02008", "narasi": "Curah Jantung Meningkat (L.02008)"},
    "D.0009": {"kode_luaran": "L.02011", "narasi": "Perfusi Perifer Meningkat (L.02011)"},
    "D.0010": {"kode_luaran": "L.02015", "narasi": "Sirkulasi Spontan Meningkat (L.02015)"},
    "D.0011": {"kode_luaran": "L.02008", "narasi": "Curah Jantung Meningkat (L.02008)"},
    "D.0012": {"kode_luaran": "L.02012", "narasi": "Tingkat Perdarahan Menurun (L.02012)"},
    "D.0013": {"kode_luaran": "L.02013", "narasi": "Perfusi Pulmonal Meningkat (L.02013)"},
    "D.0014": {"kode_luaran": "L.02014", "narasi": "Perfusi Serebral Meningkat (L.02014)"},
    "D.0015": {"kode_luaran": "L.02010", "narasi": "Perfusi Miokard Meningkat (L.02010)"},
    "D.0016": {"kode_luaran": "L.02016", "narasi": "Status Kardiopulmonal Membaik (L.02016)"},
    "D.0017": {"kode_luaran": "L.02014", "narasi": "Perfusi Serebral Meningkat (L.02014)"},
    "D.0018": {"kode_luaran": "L.02013", "narasi": "Perfusi Pulmonal Meningkat (L.02013)"},
    "D.0019": {"kode_luaran": "L.02011", "narasi": "Perfusi Perifer Meningkat (L.02011)"},
    
    # Nutrisi & Cairan
    "D.0020": {"kode_luaran": "L.03030", "narasi": "Status Nutrisi Membaik (L.03030)"},
    "D.0021": {"kode_luaran": "L.02009", "narasi": "Keseimbangan Asam Basa Membaik (L.02009)"},
    "D.0022": {"kode_luaran": "L.03028", "narasi": "Status Cairan Membaik (L.03028)"},
    "D.0023": {"kode_luaran": "L.03028", "narasi": "Status Cairan Membaik (L.03028)"},
    "D.0024": {"kode_luaran": "L.03019", "narasi": "Fungsi Gastrointestinal Membaik (L.03019)"},
    "D.0025": {"kode_luaran": "L.03028", "narasi": "Status Cairan Membaik (L.03028)"},
    "D.0026": {"kode_luaran": "L.03030", "narasi": "Status Nutrisi Membaik (L.03030)"},
    "D.0037": {"kode_luaran": "L.03021", "narasi": "Keseimbangan Elektrolit Membaik (L.03021)"},
    
    # Eliminasi
    "D.0038": {"kode_luaran": "L.04033", "narasi": "Eliminasi Fekal Membaik (L.04033)"},
    "D.0039": {"kode_luaran": "L.04034", "narasi": "Eliminasi Urin Membaik (L.04034)"},
    "D.0040": {"kode_luaran": "L.04033", "narasi": "Eliminasi Fekal Membaik (L.04033)"},
    "D.0041": {"kode_luaran": "L.04036", "narasi": "Kontinensia Urin Meningkat (L.04036)"},
    "D.0043": {"kode_luaran": "L.04034", "narasi": "Eliminasi Urin Membaik (L.04034)"},
    
    # Aktivitas & Istirahat
    "D.0054": {"kode_luaran": "L.05042", "narasi": "Mobilitas Fisik Meningkat (L.05042)"},
    "D.0055": {"kode_luaran": "L.05045", "narasi": "Status Tidur Membaik (L.05045)"},
    "D.0056": {"kode_luaran": "L.05047", "narasi": "Toleransi Aktivitas Meningkat (L.05047)"},
    "D.0057": {"kode_luaran": "L.05040", "narasi": "Konservasi Energi Meningkat (L.05040)"},
    "D.0058": {"kode_luaran": "L.05001", "narasi": "Ambulasi Meningkat (L.05001)"},
    
    # Persepsi Kognisi
    "D.0062": {"kode_luaran": "L.13118", "narasi": "Komunikasi Verbal Meningkat (L.13118)"},
    "D.0063": {"kode_luaran": "L.09082", "narasi": "Orientasi Kognitif Meningkat (L.09082)"},
    "D.0064": {"kode_luaran": "L.09074", "narasi": "Memori Membaik (L.09074)"},
    "D.0067": {"kode_luaran": "L.06053", "narasi": "Status Neurologis Membaik (L.06053)"},
    
    # Nyeri & Kenyamanan
    "D.0077": {"kode_luaran": "L.08066", "narasi": "Tingkat Nyeri Menurun (L.08066)"},
    "D.0078": {"kode_luaran": "L.08066", "narasi": "Tingkat Nyeri Menurun (L.08066)"},
    "D.0079": {"kode_luaran": "L.08064", "narasi": "Tingkat Kenyamanan Meningkat (L.08064)"},
    
    # Psikologis
    "D.0080": {"kode_luaran": "L.09093", "narasi": "Tingkat Ansietas Menurun (L.09093)"},
    "D.0081": {"kode_luaran": "L.09096", "narasi": "Tingkat Depresi Menurun (L.09096)"},
    "D.0082": {"kode_luaran": "L.09069", "narasi": "Harga Diri Meningkat (L.09069)"},
    "D.0085": {"kode_luaran": "L.09069", "narasi": "Harga Diri Meningkat (L.09069)"},
    "D.0086": {"kode_luaran": "L.09069", "narasi": "Harga Diri Meningkat (L.09069)"},
    "D.0087": {"kode_luaran": "L.09092", "narasi": "Tingkat Stres Menurun (L.09092)"},
    
    # Keamanan & Proteksi
    "D.0109": {"kode_luaran": "L.02016", "narasi": "Status Kardiopulmonal Membaik (L.02016)"},
    "D.0129": {"kode_luaran": "L.14125", "narasi": "Integritas Kulit dan Jaringan Meningkat (L.14125)"},
    "D.0130": {"kode_luaran": "L.14125", "narasi": "Integritas Kulit dan Jaringan Meningkat (L.14125)"},
    "D.0131": {"kode_luaran": "L.14129", "narasi": "Pemulihan Pascabedah Meningkat (L.14129)"},
    "D.0136": {"kode_luaran": "L.14138", "narasi": "Tingkat Jatuh Menurun (L.14138)"},
    "D.0137": {"kode_luaran": "L.14136", "narasi": "Tingkat Cedera Menurun (L.14136)"},
    "D.0142": {"kode_luaran": "L.14137", "narasi": "Tingkat Infeksi Menurun (L.14137)"},
    "D.0143": {"kode_luaran": "L.14137", "narasi": "Tingkat Infeksi Menurun (L.14137)"},
}

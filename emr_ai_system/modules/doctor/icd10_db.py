"""
Database ICD-10 (Revisi 10 — CM edisi Indonesia).
Fokus pada kondisi yang lazim dijumpai di ICU/rawat intensif dan
kardiologi klinis (sesuai panduan PERKI).

Struktur setiap entri:
{
    "kode"      : str,          # kode ICD-10 resmi
    "nama_en"   : str,          # nama Inggris (standar WHO)
    "nama_id"   : str,          # nama Indonesia (terjemahan resmi Kemenkes)
    "kategori"  : str,          # kelompok penyakit
    "keywords"  : list[str],    # kata kunci untuk pencarian bebas
    "ppk_tersedia": bool,       # apakah ada PPK/PERKI untuk kondisi ini
    "prioritas_icu": bool,      # apakah kondisi ini khusus dimonitor ketat di ICU
}
"""

from typing import List, Optional

ICD10_DB: list[dict] = [

    # ─── PENYAKIT JANTUNG KORONER ────────────────────────────────────────
    {
        "kode": "I20.0", "nama_en": "Unstable angina",
        "nama_id": "Angina Pektoris Tidak Stabil (APTS)",
        "kategori": "Sindrom Koroner Akut",
        "keywords": ["angina", "tidak stabil", "apts", "uas", "chest pain", "nyeri dada"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I21.0", "nama_en": "Acute transmural myocardial infarction of anterior wall",
        "nama_id": "Infark Miokard Akut Anterior (STEMI Anterior)",
        "kategori": "Sindrom Koroner Akut",
        "keywords": ["stemi", "infark", "anterior", "ami", "serangan jantung", "st elevasi"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I21.1", "nama_en": "Acute transmural myocardial infarction of inferior wall",
        "nama_id": "Infark Miokard Akut Inferior (STEMI Inferior)",
        "kategori": "Sindrom Koroner Akut",
        "keywords": ["stemi", "inferior", "ami", "infark inferior", "st elevasi inferior"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I21.4", "nama_en": "Acute subendocardial myocardial infarction (NSTEMI)",
        "nama_id": "Infark Miokard Non-ST-Elevasi (NSTEMI)",
        "kategori": "Sindrom Koroner Akut",
        "keywords": ["nstemi", "non stemi", "subendokardial", "troponin", "nste-acs"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I22.0", "nama_en": "Subsequent acute myocardial infarction of anterior wall",
        "nama_id": "Infark Miokard Berulang Dinding Anterior",
        "kategori": "Sindrom Koroner Akut",
        "keywords": ["reinfarction", "infark berulang", "stemi berulang"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I25.1", "nama_en": "Atherosclerotic heart disease of native coronary artery",
        "nama_id": "Penyakit Jantung Koroner Aterosklerotik",
        "kategori": "Penyakit Jantung Koroner",
        "keywords": ["pjk", "cad", "koroner", "aterosklerosis", "jantung koroner"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },

    # ─── GAGAL JANTUNG ───────────────────────────────────────────────────
    {
        "kode": "I50.0", "nama_en": "Congestive heart failure",
        "nama_id": "Gagal Jantung Kongestif",
        "kategori": "Gagal Jantung",
        "keywords": ["gjk", "chf", "gagal jantung", "kongestif", "edema", "sesak", "hfref"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I50.1", "nama_en": "Left ventricular failure",
        "nama_id": "Gagal Jantung Kiri (Akut)",
        "kategori": "Gagal Jantung",
        "keywords": ["lvf", "gagal jantung kiri", "edema paru akut", "epa"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I50.9", "nama_en": "Heart failure, unspecified",
        "nama_id": "Gagal Jantung, Tidak Spesifik",
        "kategori": "Gagal Jantung",
        "keywords": ["heart failure", "hf", "gagal jantung"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },

    # ─── ARITMIA ─────────────────────────────────────────────────────────
    {
        "kode": "I48.0", "nama_en": "Paroxysmal atrial fibrillation",
        "nama_id": "Fibrilasi Atrium Paroksismal",
        "kategori": "Aritmia",
        "keywords": ["af", "afib", "fibrilasi atrium", "paroksismal", "fa paroksismal"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I48.1", "nama_en": "Persistent atrial fibrillation",
        "nama_id": "Fibrilasi Atrium Persisten",
        "kategori": "Aritmia",
        "keywords": ["af persisten", "fibrilasi persisten", "atrial fibrillation"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I48.2", "nama_en": "Chronic atrial fibrillation (permanent)",
        "nama_id": "Fibrilasi Atrium Permanen",
        "kategori": "Aritmia",
        "keywords": ["af permanen", "fibrilasi permanen", "kronik af"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I47.1", "nama_en": "Supraventricular tachycardia",
        "nama_id": "Takikardia Supraventrikular (SVT)",
        "kategori": "Aritmia",
        "keywords": ["svt", "takikardia supraventrikular", "psvt", "avnrt"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I47.2", "nama_en": "Ventricular tachycardia",
        "nama_id": "Takikardia Ventrikel (VT)",
        "kategori": "Aritmia",
        "keywords": ["vt", "ventrikel takikardi", "vtach", "takikardia ventrikel"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I49.0", "nama_en": "Ventricular fibrillation",
        "nama_id": "Fibrilasi Ventrikel (VF)",
        "kategori": "Aritmia",
        "keywords": ["vf", "fibrilasi ventrikel", "cardiac arrest", "henti jantung"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I44.2", "nama_en": "Atrioventricular block, complete",
        "nama_id": "Blok Atrioventrikular Derajat III (Complete AV Block)",
        "kategori": "Aritmia",
        "keywords": ["av block", "complete block", "blok total", "blok av lengkap", "cavb"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I45.1", "nama_en": "Right bundle branch block",
        "nama_id": "Blok Berkas Kanan (RBBB)",
        "kategori": "Aritmia",
        "keywords": ["rbbb", "right bundle branch", "blok berkas kanan"],
        "ppk_tersedia": False, "prioritas_icu": False,
    },
    {
        "kode": "I44.7", "nama_en": "Left bundle branch block",
        "nama_id": "Blok Berkas Kiri (LBBB)",
        "kategori": "Aritmia",
        "keywords": ["lbbb", "left bundle branch", "blok berkas kiri"],
        "ppk_tersedia": False, "prioritas_icu": False,
    },

    # ─── HIPERTENSI ──────────────────────────────────────────────────────
    {
        "kode": "I10", "nama_en": "Essential (primary) hypertension",
        "nama_id": "Hipertensi Esensial (Primer)",
        "kategori": "Hipertensi",
        "keywords": ["hipertensi", "htn", "tekanan darah tinggi", "hipertensi primer"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I11.0", "nama_en": "Hypertensive heart disease with heart failure",
        "nama_id": "Penyakit Jantung Hipertensif dengan Gagal Jantung",
        "kategori": "Hipertensi",
        "keywords": ["hipertensi gagal jantung", "hypertensive heart disease", "hhd"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I16.0", "nama_en": "Hypertensive urgency",
        "nama_id": "Urgensi Hipertensi",
        "kategori": "Hipertensi",
        "keywords": ["hypertensive urgency", "urgensi hipertensi", "hipertensi urgensi"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I16.1", "nama_en": "Hypertensive emergency",
        "nama_id": "Emergensi Hipertensi",
        "kategori": "Hipertensi",
        "keywords": ["hypertensive emergency", "emergensi hipertensi", "hipertensi emergensi", "krisis hipertensi"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },

    # ─── KARDIOMIOPATI ───────────────────────────────────────────────────
    {
        "kode": "I42.0", "nama_en": "Dilated cardiomyopathy",
        "nama_id": "Kardiomiopati Dilatasi (DCMP)",
        "kategori": "Kardiomiopati",
        "keywords": ["dcmp", "dilated cardiomyopathy", "kardiomiopati dilatasi"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I42.1", "nama_en": "Obstructive hypertrophic cardiomyopathy",
        "nama_id": "Kardiomiopati Hipertrofik Obstruktif (HOCM)",
        "kategori": "Kardiomiopati",
        "keywords": ["hcm", "hocm", "hipertrofik", "kardiomiopati hipertrofik"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },

    # ─── PERIKARDIUM ─────────────────────────────────────────────────────
    {
        "kode": "I30.0", "nama_en": "Acute nonspecific idiopathic pericarditis",
        "nama_id": "Perikarditis Akut Idiopatik",
        "kategori": "Penyakit Perikardium",
        "keywords": ["perikarditis", "pericarditis", "nyeri dada pleuritik"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I31.1", "nama_en": "Chronic constrictive pericarditis",
        "nama_id": "Perikarditis Konstriktif Kronik",
        "kategori": "Penyakit Perikardium",
        "keywords": ["perikarditis konstriktif", "constrictive pericarditis"],
        "ppk_tersedia": False, "prioritas_icu": False,
    },
    {
        "kode": "I31.2", "nama_en": "Hemopericardium",
        "nama_id": "Hemoperikardium",
        "kategori": "Penyakit Perikardium",
        "keywords": ["hemoperikardium", "tamponade", "cardiac tamponade"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },

    # ─── PENYAKIT KATUP JANTUNG ──────────────────────────────────────────
    {
        "kode": "I34.0", "nama_en": "Mitral valve regurgitation",
        "nama_id": "Regurgitasi Katup Mitral",
        "kategori": "Penyakit Katup",
        "keywords": ["mr", "mitral regurgitasi", "regurgitasi mitral", "kebocoran mitral"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I35.0", "nama_en": "Aortic valve stenosis",
        "nama_id": "Stenosis Katup Aorta",
        "kategori": "Penyakit Katup",
        "keywords": ["as", "aortic stenosis", "stenosis aorta"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "I35.1", "nama_en": "Aortic valve regurgitation",
        "nama_id": "Regurgitasi Katup Aorta (Insufisiensi Aorta)",
        "kategori": "Penyakit Katup",
        "keywords": ["ar", "ai", "aortic regurgitation", "regurgitasi aorta"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },

    # ─── KONDISI VASKULAR ────────────────────────────────────────────────
    {
        "kode": "I26.0", "nama_en": "Pulmonary embolism with mention of acute cor pulmonale",
        "nama_id": "Emboli Paru dengan Kor Pulmonale Akut",
        "kategori": "Tromboembolisme Vena",
        "keywords": ["pe", "emboli paru", "pulmonary embolism", "kor pulmonale"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I26.9", "nama_en": "Pulmonary embolism without mention of acute cor pulmonale",
        "nama_id": "Emboli Paru (tanpa Kor Pulmonale)",
        "kategori": "Tromboembolisme Vena",
        "keywords": ["pe", "emboli paru", "pulmonary embolism"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "I71.0", "nama_en": "Dissection of aorta",
        "nama_id": "Diseksi Aorta (Aortic Dissection)",
        "kategori": "Vaskular",
        "keywords": ["diseksi aorta", "aortic dissection", "aorta robek"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },

    # ─── KONDISI KRITIS ICU NON-KARDIAK ──────────────────────────────────
    {
        "kode": "J96.0", "nama_en": "Acute respiratory failure",
        "nama_id": "Gagal Napas Akut",
        "kategori": "Gagal Napas",
        "keywords": ["arf", "gagal napas akut", "respiratory failure", "acute respiratory failure"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "J80", "nama_en": "Acute respiratory distress syndrome (ARDS)",
        "nama_id": "Sindrom Gagal Napas Akut (ARDS)",
        "kategori": "Gagal Napas",
        "keywords": ["ards", "sindrom gagal napas", "distres pernapasan", "acute respiratory distress"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "R57.0", "nama_en": "Cardiogenic shock",
        "nama_id": "Syok Kardiogenik",
        "kategori": "Syok",
        "keywords": ["syok kardiogenik", "cardiogenic shock", "cs", "syok"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "R57.9", "nama_en": "Shock, unspecified",
        "nama_id": "Syok, Tidak Spesifik",
        "kategori": "Syok",
        "keywords": ["syok", "shock", "hipotensi berat"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "A41.9", "nama_en": "Sepsis, unspecified organism",
        "nama_id": "Sepsis, organisme tidak spesifik",
        "kategori": "Sepsis",
        "keywords": ["sepsis", "infeksi berat", "septicemia"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "A41.0", "nama_en": "Sepsis due to Staphylococcus aureus",
        "nama_id": "Sepsis akibat Staphylococcus aureus",
        "kategori": "Sepsis",
        "keywords": ["sepsis stafilokokus", "staph aureus", "mrsa"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "N17.9", "nama_en": "Acute kidney failure, unspecified",
        "nama_id": "Gagal Ginjal Akut (AKI)",
        "kategori": "Gagal Ginjal",
        "keywords": ["aki", "gagal ginjal akut", "acute kidney injury", "renal failure"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "E11.65", "nama_en": "Type 2 diabetes mellitus with hyperglycemia",
        "nama_id": "Diabetes Melitus Tipe 2 dengan Hiperglikemia",
        "kategori": "Metabolik",
        "keywords": ["dm", "diabetes", "hiperglikemia", "gdp tinggi"],
        "ppk_tersedia": True, "prioritas_icu": False,
    },
    {
        "kode": "E87.1", "nama_en": "Hypo-osmolality and hyponatraemia",
        "nama_id": "Hiponatremia",
        "kategori": "Metabolik / Elektrolit",
        "keywords": ["hiponatremia", "natrium rendah", "hyponatremia"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
    {
        "kode": "E87.5", "nama_en": "Hyperkalemia",
        "nama_id": "Hiperkalemia",
        "kategori": "Metabolik / Elektrolit",
        "keywords": ["hiperkalemia", "kalium tinggi", "hyperkalemia", "k+ tinggi"],
        "ppk_tersedia": True, "prioritas_icu": True,
    },
]


def search_icd10(query: str, limit: int = 10) -> list[dict]:
    """
    Cari kode ICD-10 berdasarkan kode langsung atau kata kunci bebas.
    Mengembalikan list entri yang cocok, diurutkan berdasarkan relevansi.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    results = []
    for entry in ICD10_DB:
        score = 0
        # Kode persis
        if entry["kode"].lower() == query_lower:
            score += 100
        # Kode awalan
        elif entry["kode"].lower().startswith(query_lower):
            score += 60
        # Nama Indonesia
        if query_lower in entry["nama_id"].lower():
            score += 40
        # Nama Inggris
        if query_lower in entry["nama_en"].lower():
            score += 30
        # Kategori
        if query_lower in entry["kategori"].lower():
            score += 20
        # Keywords
        for kw in entry["keywords"]:
            if query_lower in kw.lower():
                score += 15
                break

        if score > 0:
            results.append({**entry, "_score": score})

    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:limit]


def get_icd10_by_code(kode: str) -> Optional[dict]:
    """Ambil satu entri ICD-10 berdasarkan kode persis."""
    for entry in ICD10_DB:
        if entry["kode"].upper() == kode.upper():
            return entry
    return None


def get_icd10_by_kategori(kategori: str) -> list[dict]:
    """Ambil semua kode ICD-10 dalam satu kategori."""
    return [e for e in ICD10_DB if kategori.lower() in e["kategori"].lower()]


def list_kategori() -> list[str]:
    """Daftar semua kategori ICD-10 yang tersedia."""
    return sorted(set(e["kategori"] for e in ICD10_DB))


def get_icu_priority_codes() -> list[dict]:
    """Daftar kode yang memerlukan pemantauan intensif ICU."""
    return [e for e in ICD10_DB if e["prioritas_icu"]]

"""
services/cdss_dokter.py  —  CDSS Dokter v1.0 (self-contained, tanpa dependensi eksternal)
===========================================================================================
Modul CDSS khusus Dokter yang TIDAK bergantung pada modules/doctor/* (yang sering berupa
stub kosong). Seluruh knowledge base PPK, ICD-10, dan tatalaksana tertanam langsung di sini.

Arsitektur paralel dengan CDSS Keperawatan v2.0:
  - Knowledge base embedded (seperti MASTER_DX_TO_SLKI, SDKI_NAME_MAPPING pada nursing)
  - Keyword detection dari teks bebas S/O
  - Numeric findings parser (tanda vital)
  - Protocol-based recommendations (setara checklist SIKI)
  - Structured output untuk dashboard.py

Dipanggil dari dashboard.py via:
    from services.cdss_dokter import analyze_icd10_dan_tatalaksana

Return format:
    {
        "status"            : "success" | "error",
        "diagnosa_list"     : list[dict],   # {kode, nama, kategori, prioritas}
        "rekomendasi"       : list[dict],   # {kode, kategori, deskripsi, prioritas, detail}
        "numeric_findings"  : dict,
        "clinical_context"  : dict,
    }
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Dict, List, Tuple


# =============================================================================
# A. KNOWLEDGE BASE ICD-10  —  NAMA & KATEGORI
# =============================================================================

ICD10_NAMA: dict[str, dict] = {
    # ── Jantung & Pembuluh Darah ──────────────────────────────────────────────
    "I10":    {"nama": "Hipertensi Esensial",                          "kategori": "Kardiovaskular"},
    "I16.0":  {"nama": "Urgensi Hipertensi",                           "kategori": "Kardiovaskular"},
    "I16.1":  {"nama": "Emergensi Hipertensi",                         "kategori": "Kardiovaskular"},
    "I20.0":  {"nama": "Angina Tidak Stabil (APTS)",                   "kategori": "Kardiovaskular"},
    "I21.0":  {"nama": "STEMI (ST-Elevation Myocardial Infarction)",   "kategori": "Kardiovaskular"},
    "I21.4":  {"nama": "NSTEMI (Non-ST-Elevation MI)",                 "kategori": "Kardiovaskular"},
    "I25.1":  {"nama": "Penyakit Jantung Koroner (PJK)",               "kategori": "Kardiovaskular"},
    "I31.2":  {"nama": "Tamponade Jantung / Hemoperikardium",          "kategori": "Kardiovaskular"},
    "I44.2":  {"nama": "Blok AV Total (CAVB)",                         "kategori": "Kardiovaskular"},
    "I47.1":  {"nama": "Takikardia Supraventrikular (SVT)",            "kategori": "Kardiovaskular"},
    "I47.2":  {"nama": "Takikardia Ventrikel (VT)",                    "kategori": "Kardiovaskular"},
    "I48.0":  {"nama": "Fibrilasi Atrium (AF)",                        "kategori": "Kardiovaskular"},
    "I49.0":  {"nama": "Fibrilasi Ventrikel / Cardiac Arrest",         "kategori": "Kardiovaskular"},
    "I50.0":  {"nama": "Gagal Jantung Kongestif (CHF)",                "kategori": "Kardiovaskular"},
    "I50.1":  {"nama": "Edema Paru Akut (EPA)",                        "kategori": "Kardiovaskular"},
    "I71.0":  {"nama": "Diseksi Aorta",                                "kategori": "Kardiovaskular"},
    "I26.9":  {"nama": "Emboli Paru (PE)",                             "kategori": "Kardiovaskular"},
    "R57.0":  {"nama": "Syok Kardiogenik",                             "kategori": "Kardiovaskular"},
    # ── Respirasi ─────────────────────────────────────────────────────────────
    "J80":    {"nama": "ARDS (Acute Respiratory Distress Syndrome)",   "kategori": "Respirasi"},
    "J96.0":  {"nama": "Gagal Napas Akut",                             "kategori": "Respirasi"},
    "J18.9":  {"nama": "Pneumonia",                                    "kategori": "Respirasi"},
    "J44.1":  {"nama": "PPOK Eksaserbasi Akut",                        "kategori": "Respirasi"},
    "J45.5":  {"nama": "Status Asmatikus",                             "kategori": "Respirasi"},
    # ── Infeksi & Sepsis ──────────────────────────────────────────────────────
    "A41.9":  {"nama": "Sepsis (tidak spesifik)",                      "kategori": "Infeksi"},
    "A41.0":  {"nama": "Sepsis akibat Staphylococcus aureus",          "kategori": "Infeksi"},
    "R65.2":  {"nama": "Syok Septik",                                  "kategori": "Infeksi"},
    # ── Ginjal ────────────────────────────────────────────────────────────────
    "N17.9":  {"nama": "Gagal Ginjal Akut (AKI)",                      "kategori": "Ginjal"},
    "N18.5":  {"nama": "Penyakit Ginjal Kronik St. 5 (CKD 5)",        "kategori": "Ginjal"},
    # ── Metabolik & Endokrin ──────────────────────────────────────────────────
    "E87.5":  {"nama": "Hiperkalemia",                                  "kategori": "Metabolik"},
    "E87.1":  {"nama": "Hiponatremia",                                  "kategori": "Metabolik"},
    "E11.0":  {"nama": "Diabetes Mellitus Tipe 2 dengan Ketoasidosis", "kategori": "Metabolik"},
    "E10.1":  {"nama": "Diabetes Mellitus Tipe 1 (DKA)",               "kategori": "Metabolik"},
    "E16.0":  {"nama": "Hipoglikemia",                                  "kategori": "Metabolik"},
    # ── Neurologi ─────────────────────────────────────────────────────────────
    "I63.9":  {"nama": "Stroke Iskemik",                               "kategori": "Neurologi"},
    "I61.9":  {"nama": "Stroke Hemoragik",                             "kategori": "Neurologi"},
    "G40.9":  {"nama": "Epilepsi / Status Epileptikus",                "kategori": "Neurologi"},
}


# =============================================================================
# B. KNOWLEDGE BASE PPK  —  PROTOKOL TATALAKSANA PER ICD-10
# =============================================================================

PPK_PROTOKOL: dict[str, dict] = {

    # ── I21.0 STEMI ───────────────────────────────────────────────────────────
    "I21.0": {
        "nama_ppk": "PPK STEMI",
        "target_waktu": "Door-to-balloon < 90 menit",
        "pemeriksaan_awal": [
            "EKG 12 lead segera (< 10 menit sejak kontak medis pertama)",
            "Enzim jantung: Troponin I/T, CK-MB (serial 0, 6, 12 jam)",
            "Darah lengkap, PT/APTT, fungsi ginjal, elektrolit",
            "Foto toraks portable",
            "Ekokardiografi bedside (jika tersedia)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Reperfusi",     "aksi": "Aktifkan protokol kateterisasi (primary PCI) segera — target D2B < 90 menit"},
            {"prioritas": "KRITIS",  "kategori": "Antiplatelet",  "aksi": "Loading Aspirin 320 mg PO + Ticagrelor 180 mg PO (atau Clopidogrel 600 mg jika Ticagrelor KI)"},
            {"prioritas": "KRITIS",  "kategori": "Antikoagulan",  "aksi": "UFH bolus 60-100 IU/kg IV atau Fondaparinux 2,5 mg SC (jika PCI tidak tersedia dalam 120 mnt)"},
            {"prioritas": "TINGGI",  "kategori": "Oksigen",       "aksi": "O2 nasal kanul 2-4 LPM jika SpO2 < 90%; hindari hiperoksigenasi"},
            {"prioritas": "TINGGI",  "kategori": "Analgetik",     "aksi": "Morfin 2-4 mg IV titrasi jika nyeri dada persisten (monitor tekanan darah)"},
            {"prioritas": "TINGGI",  "kategori": "Nitrat",        "aksi": "ISDN sublingual 5 mg jika TD sistolik > 90 mmHg (hindari jika suspect RV infarct)"},
            {"prioritas": "SEDANG",  "kategori": "Beta-blocker",  "aksi": "Bisoprolol 2,5-5 mg PO (mulai 24 jam post-stabil, KI pada gagal jantung akut/syok)"},
            {"prioritas": "SEDANG",  "kategori": "Statin",        "aksi": "Atorvastatin 40-80 mg PO malam hari (mulai segera, tanpa menunggu profil lipid)"},
            {"prioritas": "SEDANG",  "kategori": "ACE-I/ARB",    "aksi": "Ramipril 2,5 mg PO 2x/hari (mulai 24-48 jam post-stabil jika TD stabil)"},
        ],
        "monitoring": [
            "Monitor EKG kontinu 24 jam pertama",
            "Pantau TD, HR, SpO2 tiap 15 menit dalam 2 jam pertama",
            "Ulangi EKG 60-90 menit setelah tatalaksana (evaluasi resolusi ST)",
            "Serial enzim jantung tiap 6 jam",
            "Balance cairan ketat",
        ],
        "kontraindikasi_perhatian": [
            "Morfin: hindari jika BP < 90 atau bradikardia berat",
            "Nitrat: KONTRAINDIKASI pada suspect RV infarction (ST elevasi V3R/V4R)",
            "Beta-blocker: tunda jika ada tanda gagal jantung akut, syok, PR > 240 ms, HR < 60",
        ],
    },

    # ── I21.4 NSTEMI ─────────────────────────────────────────────────────────
    "I21.4": {
        "nama_ppk": "PPK NSTEMI/APTS",
        "target_waktu": "Stratifikasi risiko GRACE/TIMI dalam 2 jam",
        "pemeriksaan_awal": [
            "EKG 12 lead (baseline dan serial tiap 6 jam atau jika gejala berulang)",
            "Troponin serial 0, 1, 3 jam (high-sensitivity) atau 0, 6 jam",
            "Darah lengkap, PT/APTT, fungsi ginjal, lipid profile, GDS",
            "Foto toraks, Ekokardiografi (evaluasi fungsi sistolik)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Antiplatelet",  "aksi": "Aspirin 320 mg loading, lanjut 100 mg/hari + Ticagrelor 180 mg loading, lanjut 90 mg 2x/hari"},
            {"prioritas": "KRITIS",  "kategori": "Antikoagulan",  "aksi": "Enoxaparin 1 mg/kg SC 2x/hari atau UFH IV (target aPTT 50-70 detik)"},
            {"prioritas": "TINGGI",  "kategori": "Anti-iskemia",  "aksi": "Nitrat IV (NTG 10-200 mcg/menit titrasi) jika nyeri persisten, TD stabil"},
            {"prioritas": "TINGGI",  "kategori": "Beta-blocker",  "aksi": "Bisoprolol 2,5-5 mg PO atau Metoprolol 25-50 mg PO jika HR > 70 dan hemodinamik stabil"},
            {"prioritas": "SEDANG",  "kategori": "Statin",        "aksi": "Atorvastatin 40-80 mg PO malam — mulai segera"},
            {"prioritas": "SEDANG",  "kategori": "Evaluasi Invasif", "aksi": "Angiografi koroner dalam 2-24 jam (risiko tinggi) atau < 72 jam (risiko sedang)"},
        ],
        "monitoring": [
            "Bed rest dengan monitor EKG kontinu",
            "Troponin serial hingga puncak terdeteksi",
            "Pantau tanda perdarahan (komplikasi antikoagulan)",
        ],
        "kontraindikasi_perhatian": [
            "Hindari NSAID/COX-2 inhibitor selama perawatan ACS",
            "Sesuaikan dosis enoxaparin pada AKI (GFR < 30: gunakan UFH)",
        ],
    },

    # ── I20.0 ANGINA TIDAK STABIL ─────────────────────────────────────────────
    "I20.0": {
        "nama_ppk": "PPK Angina Tidak Stabil",
        "target_waktu": "Evaluasi risiko dalam 2 jam",
        "pemeriksaan_awal": [
            "EKG 12 lead saat onset dan serial",
            "Troponin hs-cTnI/T serial (0, 1, 3 jam)",
            "Darah lengkap, fungsi ginjal, elektrolit, lipid",
        ],
        "tatalaksana": [
            {"prioritas": "TINGGI",  "kategori": "Antiplatelet",  "aksi": "Aspirin 320 mg loading, lanjut 100 mg/hari"},
            {"prioritas": "TINGGI",  "kategori": "Anti-iskemia",  "aksi": "ISDN 5 mg sublingual saat nyeri; pertimbangkan nitrat IV jika berulang"},
            {"prioritas": "TINGGI",  "kategori": "Antikoagulan",  "aksi": "Fondaparinux 2,5 mg SC/hari atau enoxaparin 1 mg/kg SC 2x/hari"},
            {"prioritas": "SEDANG",  "kategori": "Beta-blocker",  "aksi": "Bisoprolol 2,5-5 mg PO jika HR > 70 dan hemodinamik stabil"},
            {"prioritas": "SEDANG",  "kategori": "Statin",        "aksi": "Atorvastatin 40 mg PO malam"},
        ],
        "monitoring": ["Monitor EKG kontinu 12-24 jam", "Serial troponin", "Pantau TD dan gejala"],
        "kontraindikasi_perhatian": ["Nitrat KI jika TD < 90 mmHg atau suspect RV infarct"],
    },

    # ── I50.0 GAGAL JANTUNG ───────────────────────────────────────────────────
    "I50.0": {
        "nama_ppk": "PPK Gagal Jantung Akut Dekompensasi (ADHF)",
        "target_waktu": "Stabilisasi hemodinamik dalam 1 jam",
        "pemeriksaan_awal": [
            "EKG 12 lead (cari penyebab: AF, iskemia, blok)",
            "Foto toraks (edema paru, kardiomegali)",
            "Ekokardiografi segera (EF, regional wall motion abnormality)",
            "BNP/NT-proBNP, troponin, fungsi ginjal, elektrolit",
            "Saturasi O2 dan gas darah (AGD)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Oksigen",        "aksi": "O2 via NRM hingga SpO2 > 95%; pertimbangkan NIV (CPAP/BiPAP) jika refrakter"},
            {"prioritas": "KRITIS",  "kategori": "Diuretik",       "aksi": "Furosemid IV 40-80 mg bolus (atau 2,5x dosis oral harian); lanjut infus jika perlu"},
            {"prioritas": "TINGGI",  "kategori": "Vasodilator",    "aksi": "NTG infus 10-200 mcg/mnt jika TD > 110 mmHg dan tidak ada syok"},
            {"prioritas": "TINGGI",  "kategori": "Posisi",         "aksi": "Posisi duduk tegak (90°), kaki menggantung untuk kurangi preload"},
            {"prioritas": "SEDANG",  "kategori": "Inotropik",      "aksi": "Dobutamin 2-20 mcg/kg/mnt IV jika tanda low output (TD < 90, akral dingin)"},
            {"prioritas": "SEDANG",  "kategori": "Pembatasan",     "aksi": "Restriksi cairan 1-1,5 L/hari; restriksi garam < 2 g/hari"},
            {"prioritas": "SEDANG",  "kategori": "Antikoagulan",   "aksi": "Pertimbangkan UFH/LMWH jika AF atau imobilisasi prolonged"},
        ],
        "monitoring": [
            "Monitor urine output tiap jam (target > 0,5 mL/kg/jam)",
            "Timbang badan harian; target penurunan 0,5-1 kg/hari",
            "Pantau elektrolit (K+, Mg++) tiap 6-12 jam selama diuretik IV",
            "Monitor kreatinin (risiko AKI akibat diuretik agresif)",
        ],
        "kontraindikasi_perhatian": [
            "Vasodilator KI jika TD < 90 mmHg",
            "Beta-blocker: TUNDA atau kurangi dosis saat fase akut dekompensasi",
            "NSAID: HINDARI (retensi Na, perburukan fungsi ginjal)",
        ],
    },

    # ── I50.1 EDEMA PARU AKUT ────────────────────────────────────────────────
    "I50.1": {
        "nama_ppk": "PPK Edema Paru Akut (EPA)",
        "target_waktu": "Stabilisasi dalam 30 menit",
        "pemeriksaan_awal": [
            "AGD segera (evaluasi hipoksemia dan hiperkapnia)",
            "Foto toraks (batwing, Kerley B lines)",
            "EKG (cari STEMI, AF, blok sebagai penyebab)",
            "Ekokardiografi bedside, BNP, troponin",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Ventilasi",     "aksi": "NIV (CPAP 5-10 cmH2O atau BiPAP) segera — kurangi kebutuhan intubasi hingga 50%"},
            {"prioritas": "KRITIS",  "kategori": "Oksigen",       "aksi": "O2 konsentrasi tinggi via NRM 15 LPM; siapkan intubasi jika GCS turun"},
            {"prioritas": "KRITIS",  "kategori": "Diuretik",      "aksi": "Furosemid IV 80-120 mg bolus cepat; ulangi atau lanjut infus jika tidak respons"},
            {"prioritas": "KRITIS",  "kategori": "Vasodilator",   "aksi": "NTG sublingual 0,5 mg tiap 5 menit (maks 3x) lalu NTG IV jika TD stabil"},
            {"prioritas": "TINGGI",  "kategori": "Morfin",        "aksi": "Morfin 2-4 mg IV (mengurangi afterload dan ansietas) — perhatian pada hipotensi"},
            {"prioritas": "SEDANG",  "kategori": "Inotropik",     "aksi": "Dobutamin jika TD < 90 mmHg dengan tanda low output"},
        ],
        "monitoring": [
            "SpO2 kontinu; AGD ulang 30-60 menit setelah intervensi",
            "Pantau TD tiap 15 menit (vasodilator dapat menyebabkan hipotensi mendadak)",
            "Siapkan ETT dan fasilitas intubasi di samping tempat tidur",
        ],
        "kontraindikasi_perhatian": [
            "Morfin: gunakan hati-hati pada hiperkapnia (SpO2 < 90 + pCO2 > 45)",
            "Vasodilator: KI absolut jika TD < 90 mmHg",
        ],
    },

    # ── I48.0 FIBRILASI ATRIUM ───────────────────────────────────────────────
    "I48.0": {
        "nama_ppk": "PPK Fibrilasi Atrium",
        "target_waktu": "Rate control < 110 bpm dalam 1 jam",
        "pemeriksaan_awal": [
            "EKG 12 lead (konfirmasi AF, cari iskemia, WPW)",
            "Ekokardiografi (thrombus LAA, fungsi LV, valvular)",
            "Fungsi tiroid (TSH), elektrolit, CBC, fungsi ginjal",
            "Skor CHA2DS2-VASc dan HAS-BLED",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Kardioversif",  "aksi": "KARDIOVERSIF ELEKTRIK segera jika hemodinamik tidak stabil (sinkronized 200J biphasic)"},
            {"prioritas": "TINGGI",  "kategori": "Rate Control",  "aksi": "Bisoprolol 2,5-10 mg PO atau Metoprolol 25-100 mg PO (target HR < 110 bpm istirahat)"},
            {"prioritas": "TINGGI",  "kategori": "Rate Control",  "aksi": "Diltiazem IV 0,25 mg/kg bolus (jika BB tidak bisa); hindari pada EF < 40%"},
            {"prioritas": "TINGGI",  "kategori": "Antikoagulan",  "aksi": "DOAC (Rivaroxaban/Apixaban) jika CHA2DS2-VASc >= 2 (pria) atau >= 3 (wanita)"},
            {"prioritas": "SEDANG",  "kategori": "Rhythm Control","aksi": "Amiodarone 150 mg IV 10 menit, lanjut 1 mg/mnt 6 jam jika AF < 48 jam + terapi antikoagulan"},
        ],
        "monitoring": [
            "Monitor EKG kontinu — pantau ventricular rate dan perubahan irama",
            "TD tiap 30 menit selama rate control IV",
            "Fungsi ginjal berkala selama DOAC",
        ],
        "kontraindikasi_perhatian": [
            "Verapamil/Diltiazem: KONTRAINDIKASI pada WPW-AF (risiko VF)",
            "Digoxin: tidak untuk rate control akut pada AF simtomatik aktif",
            "Amiodaron oral: awasi toksisitas tiroid, paru, hati jangka panjang",
        ],
    },

    # ── I47.2 TAKIKARDIA VENTRIKEL ───────────────────────────────────────────
    "I47.2": {
        "nama_ppk": "PPK Takikardia Ventrikel (VT)",
        "target_waktu": "Defibrilasi dalam 3 menit jika pulseless VT",
        "pemeriksaan_awal": [
            "EKG 12 lead segera (konfirmasi VT, morphology, QRS duration)",
            "Monitor kontinu, siapkan defibrilator",
            "Elektrolit (K+, Mg++), gas darah",
            "Troponin (cari iskemia sebagai trigger)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Defibrilasi",   "aksi": "PULSELESS VT: Defibrilasi non-sinkronized 200J (biphasic) + CPR segera — ikuti algoritma ACLS"},
            {"prioritas": "KRITIS",  "kategori": "Kardioversi",   "aksi": "VT dengan nadi + hemodinamik tidak stabil: Kardioversi tersinkronisasi 100J"},
            {"prioritas": "TINGGI",  "kategori": "Antiaritmia",   "aksi": "VT stabil: Amiodarone 150 mg IV dalam 10 menit, lanjut 1 mg/mnt 6 jam"},
            {"prioritas": "TINGGI",  "kategori": "Koreksi",       "aksi": "Koreksi hipokalemia (K+ > 4,0 mEq/L) dan hipomagnesemia (Mg++ 1-2 g IV) segera"},
            {"prioritas": "SEDANG",  "kategori": "Lidokain",      "aksi": "Lidokain 1-1,5 mg/kg IV bolus sebagai alternatif Amiodarone pada VT stabil"},
        ],
        "monitoring": [
            "Monitor EKG kontinu — siapkan defibrilator dalam jangkauan",
            "Pantau K+, Mg++ tiap 4-6 jam",
            "Evaluasi penyebab reversibel: iskemia, hipoksia, gangguan elektrolit",
        ],
        "kontraindikasi_perhatian": [
            "Torsades de Pointes: Mg-sulfat 2 g IV — BUKAN Amiodarone",
            "Hindari antiaritmia yang memperpanjang QT pada Torsades",
        ],
    },

    # ── I49.0 FIBRILASI VENTRIKEL / CARDIAC ARREST ──────────────────────────
    "I49.0": {
        "nama_ppk": "PPK Cardiac Arrest / VF",
        "target_waktu": "Defibrilasi dalam 3 menit",
        "pemeriksaan_awal": [
            "Konfirmasi cardiac arrest: tidak responsif, tidak bernapas normal, tidak ada nadi",
            "EKG (identifikasi irama: VF, pVT, Asistol, PEA)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "CPR",           "aksi": "Mulai CPR berkualitas tinggi: kompresi 100-120x/mnt, kedalaman 5-6 cm, recoil penuh"},
            {"prioritas": "KRITIS",  "kategori": "Defibrilasi",   "aksi": "Defibrilasi 200J (biphasic) segera untuk VF/pVT — minimalisir interruption CPR"},
            {"prioritas": "KRITIS",  "kategori": "Epinefrin",     "aksi": "Epinefrin 1 mg IV tiap 3-5 menit (mulai setelah siklus CPR ke-2 jika VF/pVT)"},
            {"prioritas": "TINGGI",  "kategori": "Airway",        "aksi": "Airway management: BVM dulu, intubasi endotrakeal atau supraglottic airway"},
            {"prioritas": "TINGGI",  "kategori": "Antiaritmia",   "aksi": "Amiodarone 300 mg IV bolus setelah defibrilasi ke-3 (VF/pVT refrakter)"},
            {"prioritas": "TINGGI",  "kategori": "Koreksi 5H5T",  "aksi": "Identifikasi dan koreksi penyebab reversibel: Hipoksia, Hipovolemia, Hipo/Hiperkalemia, Hipotermia, Tension PTX, Tamponade, Trombosis, Toksin"},
        ],
        "monitoring": [
            "EtCO2 untuk monitoring efektivitas CPR (target > 10 mmHg)",
            "Cek irama tiap 2 menit",
            "Pertimbangkan ECMO-CPR (eCPR) jika fasilitas tersedia",
        ],
        "kontraindikasi_perhatian": [
            "Jangan gunakan Atropine untuk Asistol atau PEA (tidak ada bukti manfaat)",
            "Sodium bikarbonat: hanya jika hiperkalemia terdokumentasi atau OD TCA",
        ],
    },

    # ── R57.0 SYOK KARDIOGENIK ───────────────────────────────────────────────
    "R57.0": {
        "nama_ppk": "PPK Syok Kardiogenik",
        "target_waktu": "Stabilisasi awal dalam 30 menit, revaskularisasi dalam 2 jam",
        "pemeriksaan_awal": [
            "EKG (cari STEMI sebagai penyebab)",
            "Ekokardiografi segera (EF, regional WMA, efusi)",
            "AGD (asidosis metabolik), laktat darah",
            "Troponin, BNP, fungsi ginjal, hepatik (end-organ damage)",
            "Foto toraks (edema paru, kardiomegali)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Vasopressor",   "aksi": "Norepinefrin 0,1-2 mcg/kg/mnt IV (vasopressor PILIHAN pada syok kardiogenik)"},
            {"prioritas": "KRITIS",  "kategori": "Inotropik",     "aksi": "Dobutamin 2-20 mcg/kg/mnt IV (tambahkan jika CO rendah meski TD sudah stabil dengan NE)"},
            {"prioritas": "KRITIS",  "kategori": "Revaskularisasi","aksi": "Primary PCI segera jika penyebab STEMI/ACS — jangan ditunda"},
            {"prioritas": "TINGGI",  "kategori": "Ventilasi",     "aksi": "Intubasi + ventilasi mekanik jika ada edema paru berat atau kesadaran turun"},
            {"prioritas": "TINGGI",  "kategori": "MCS",           "aksi": "Pertimbangkan IABP atau Impella jika tersedia (mechanical circulatory support)"},
            {"prioritas": "SEDANG",  "kategori": "Cairan",        "aksi": "Fluid challenge hati-hati 250 mL kristaloid jika tanda hipovolemia (JVP rendah, PAWP < 12)"},
        ],
        "monitoring": [
            "Arterial line untuk monitoring TD invasif kontinu",
            "Kateter urin — target UO > 0,5 mL/kg/jam",
            "Serial laktat tiap 2-4 jam (target < 2 mmol/L)",
            "Evaluasi tanda end-organ: kreatinin, SGOT/SGPT, kesadaran",
        ],
        "kontraindikasi_perhatian": [
            "Dopamin: tidak lebih unggul dari NE, risiko aritmia lebih tinggi",
            "Hindari loading cairan berlebihan pada syok kardiogenik murni",
        ],
    },

    # ── A41.9 SEPSIS ──────────────────────────────────────────────────────────
    "A41.9": {
        "nama_ppk": "PPK Sepsis & Syok Septik (Surviving Sepsis Campaign)",
        "target_waktu": "Bundle 1 jam: darah kultur + antibiotik + resusitasi",
        "pemeriksaan_awal": [
            "Kultur darah (2 set, aerob + anaerob) SEBELUM antibiotik",
            "Laktat darah (syok septik jika laktat > 2 mmol/L)",
            "Darah lengkap, PCT, CRP, fungsi ginjal, hepatik, koagulasi (DIC screen)",
            "AGD, urin rutin, dan kultur urin",
            "Foto toraks (cari fokus infeksi)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Antibiotik",    "aksi": "Antibiotik broad-spectrum IV dalam 1 jam: Meropenem 1g tiap 8 jam atau Piperacillin-Tazobactam 4,5g tiap 6 jam"},
            {"prioritas": "KRITIS",  "kategori": "Resusitasi",    "aksi": "Kristaloid 30 mL/kg IV dalam 3 jam (target MAP > 65 mmHg, UO > 0,5 mL/kg/jam)"},
            {"prioritas": "KRITIS",  "kategori": "Vasopressor",   "aksi": "Norepinefrin 0,1-2 mcg/kg/mnt jika MAP < 65 setelah resusitasi adekuat"},
            {"prioritas": "TINGGI",  "kategori": "Source Control","aksi": "Identifikasi dan kontrol sumber infeksi (drainase abses, cabut kateter terinfeksi, dll)"},
            {"prioritas": "TINGGI",  "kategori": "Steroid",       "aksi": "Hidrokortison 200 mg/hari IV infus kontinu jika vasopresor-refrakter"},
            {"prioritas": "SEDANG",  "kategori": "Glukosa",       "aksi": "Protokol insulin IV: target GDS 140-180 mg/dL (hindari hipoglikemia)"},
            {"prioritas": "SEDANG",  "kategori": "DVT Profilaksis","aksi": "LMWH profilaksis + stoking kompresi (jika tidak ada KI perdarahan)"},
        ],
        "monitoring": [
            "Pantau MAP tiap 15-30 menit selama resusitasi",
            "Serial laktat tiap 2 jam (target clearance > 10%/2 jam)",
            "Balance cairan ketat tiap 6 jam",
            "Kultutivasi ulang 48-72 jam (atau jika klinis memburuk)",
            "De-eskalasi antibiotik berdasarkan hasil kultur dan respons klinis",
        ],
        "kontraindikasi_perhatian": [
            "Hindari loading cairan berlebihan (> 30 mL/kg) jika ada tanda overload",
            "Albumin: pertimbangkan jika resusitasi kristaloid > 5 L",
        ],
    },

    # ── J80 ARDS ──────────────────────────────────────────────────────────────
    "J80": {
        "nama_ppk": "PPK ARDS (Lung Protective Ventilation)",
        "target_waktu": "Intubasi dan lung protective strategy dalam 2 jam",
        "pemeriksaan_awal": [
            "AGD serial (PaO2/FiO2 ratio — ARDS jika < 300)",
            "Foto toraks (bilateral infiltrate, bukan karena gagal jantung semata)",
            "Ekokardiografi (eksklusi kardiogenik edema paru)",
            "BAL (bronchoalveolar lavage) jika penyebab belum jelas",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Ventilasi",     "aksi": "Lung Protective Ventilation: TV 6 mL/kg IBW, Plateau pressure < 30 cmH2O, PEEP sesuai FiO2 tabel ARDSnet"},
            {"prioritas": "KRITIS",  "kategori": "Prone Position","aksi": "Prone positioning 16-18 jam/hari jika P/F ratio < 150 — terbukti turunkan mortalitas"},
            {"prioritas": "TINGGI",  "kategori": "Sedasi",        "aksi": "Sedasi ringan (RASS -1 hingga -2) + analgesia first approach (fentanyl/morfin)"},
            {"prioritas": "TINGGI",  "kategori": "NMBA",          "aksi": "Cisatracurium 37,5 mg/jam IV 48 jam jika P/F < 150 pada awal (ACURASYS/ROSE)"},
            {"prioritas": "SEDANG",  "kategori": "Cairan",        "aksi": "Konservative fluid strategy: target balance nol atau negatif setelah resusitasi inisial"},
            {"prioritas": "SEDANG",  "kategori": "ECMO",          "aksi": "Pertimbangkan VV-ECMO jika P/F < 80 refrakter setelah optimasi (rujuk ke center)"},
        ],
        "monitoring": [
            "AGD dan ventilator parameter tiap 4-6 jam",
            "Plateau pressure dan driving pressure setiap shift",
            "Cek posisi ETT harian (foto toraks)",
        ],
        "kontraindikasi_perhatian": [
            "HINDARI TV tinggi (> 8 mL/kg) — volutrauma memperburuk ARDS",
            "Steroid: Deksametason 6 mg/hari 10 hari menurunkan mortalitas (RECOVERY trial) — pertimbangkan pada ARDS moderate-berat",
        ],
    },

    # ── N17.9 GAGAL GINJAL AKUT ──────────────────────────────────────────────
    "N17.9": {
        "nama_ppk": "PPK Acute Kidney Injury (AKI)",
        "target_waktu": "Identifikasi dan koreksi penyebab dalam 6 jam",
        "pemeriksaan_awal": [
            "Kreatinin, BUN serial (bandingkan dengan baseline)",
            "Urin output hourly; urin rutin + sedimen",
            "Elektrolit lengkap (K+, Na+, bikarbonat)",
            "USG ginjal (eksklusi obstruksi post-renal)",
            "Stagefing AKI KDIGO (Cr ratio, UO, kebutuhan RRT)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Koreksi K+",    "aksi": "Hiperkalemia K+ > 6: Kalsium glukonat 10% 10 mL IV, Insulin 10 IU + D40% 100 mL IV, Kayexalate PO/enema"},
            {"prioritas": "TINGGI",  "kategori": "Resusitasi",    "aksi": "Kristaloid 500 mL bolus jika AKI pre-renal (urin osmolalitas > 500, BUN/Cr > 20)"},
            {"prioritas": "TINGGI",  "kategori": "Stop Nefrotoksin","aksi": "Hentikan NSAID, ACE-I/ARB, aminoglikosida, kontras iodine jika mungkin"},
            {"prioritas": "TINGGI",  "kategori": "RRT",           "aksi": "Indikasi dialisis AEIOU: Acidosis pH < 7,1; Elektrolit (K+ > 6,5 refrakter); Intoksikasi; Overload refrakter; Uremia (BUN > 100 + gejala)"},
            {"prioritas": "SEDANG",  "kategori": "Nutrisi",       "aksi": "Nutrisi enteral dini; sesuaikan protein 1,2-1,7 g/kg/hari jika RRT, 0,8-1,0 jika non-RRT"},
        ],
        "monitoring": [
            "Urin output tiap jam (kateter urin wajib)",
            "Elektrolit tiap 6-12 jam (risiko hiperkalemia mendadak)",
            "Pantau kelebihan cairan: timbang harian, foto toraks",
            "Hindari pemeriksaan dengan kontras iodine jika GFR < 30",
        ],
        "kontraindikasi_perhatian": [
            "Hindari furosemid untuk 'memaksa' diuresis pada AKI oliguria tanpa overload",
            "Sesuaikan dosis obat berdasarkan eGFR (vancomycin, beta-laktam, LMWH)",
        ],
    },

    # ── E87.5 HIPERKALEMIA ────────────────────────────────────────────────────
    "E87.5": {
        "nama_ppk": "PPK Hiperkalemia",
        "target_waktu": "Stabilisasi jantung dalam 10 menit jika K+ > 6,5",
        "pemeriksaan_awal": [
            "EKG segera (peaked T wave, QRS wide, sine wave pattern)",
            "Kalium ulang cito (eksklusi pseudohiperkalemia: hemolisis)",
            "Fungsi ginjal, asam basa (pH, HCO3)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Stabilisasi Membran","aksi": "Kalsium glukonat 10% 10-20 mL IV dalam 2-3 menit (onset 1-3 mnt, durasi 30-60 mnt) — ulangi jika EKG belum membaik"},
            {"prioritas": "KRITIS",  "kategori": "Redistribusi",  "aksi": "Insulin reguler 10 IU IV + D40% 100 mL IV (onset 10-20 mnt); Salbutamol nebulisasi 10-20 mg"},
            {"prioritas": "TINGGI",  "kategori": "Eliminasi",     "aksi": "Furosemid IV jika fungsi ginjal masih ada; Kayexalate (sodium polystyrenesulfonate) 15-30 g PO/enema"},
            {"prioritas": "TINGGI",  "kategori": "Koreksi Asidosis","aksi": "Bikarbonat IV 50 mEq jika asidosis metabolik berat (pH < 7,2) — efek lambat pada hiperkalemia"},
            {"prioritas": "SEDANG",  "kategori": "Dialisis",      "aksi": "Hemodialisis jika K+ > 6,5 refrakter atau AKI berat (paling efektif dalam menurunkan K+)"},
        ],
        "monitoring": [
            "Monitor EKG kontinu selama tatalaksana",
            "Cek kalium ulang tiap 1-2 jam",
            "Waspadai hipoglikemia pasca pemberian insulin + dextrose",
        ],
        "kontraindikasi_perhatian": [
            "Jangan tunda tatalaksana menunggu konfirmasi laboratorium jika EKG sudah abnormal",
            "Kalsium glukonat: jangan berikan ke jalur IV yang sama dengan bikarbonat (presipitasi)",
        ],
    },

    # ── I16.1 HIPERTENSI EMERGENSI ────────────────────────────────────────────
    "I16.1": {
        "nama_ppk": "PPK Hipertensi Emergensi",
        "target_waktu": "Penurunan TD 25% dalam 1 jam pertama",
        "pemeriksaan_awal": [
            "Funduskopi (papilledema — menunjukkan urgensi penurunan TD lebih cepat)",
            "Urin rutin + protein (cari AKI hipertensif)",
            "Troponin, BNP (cari end-organ damage jantung)",
            "CT scan kepala tanpa kontras (eksklusi stroke hemoragik)",
            "EKG (cari hipertrofi LV, iskemia, aritmia)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "Vasodilatasi IV","aksi": "NTG infus 5-200 mcg/mnt (pilihan jika ada ACS/edema paru); atau Nikardipin 5-15 mg/jam IV"},
            {"prioritas": "KRITIS",  "kategori": "Target TD",     "aksi": "Turunkan MAP 25% dalam 1 jam; lanjut ke 160/100 dalam 2-6 jam BERIKUTNYA (penurunan terlalu cepat berbahaya)"},
            {"prioritas": "TINGGI",  "kategori": "Labetolol",     "aksi": "Labetalol 20 mg IV bolus, ulangi tiap 10 mnt (max 300 mg); atau infus 1-2 mg/mnt"},
            {"prioritas": "SEDANG",  "kategori": "Klonidin",      "aksi": "Klonidin 0,1-0,3 mg PO tiap 1 jam (alternatif oral jika akses IV belum tersedia)"},
        ],
        "monitoring": [
            "Monitor TD tiap 15 menit selama titrasi IV",
            "Pantau neurologis (penurunan kesadaran = tanda overdose penurunan TD)",
            "Monitor fungsi ginjal dan kreatinin tiap 6-12 jam",
        ],
        "kontraindikasi_perhatian": [
            "HINDARI penurunan TD terlalu cepat — risiko iskemia otak, ginjal, jantung",
            "Nifedipin sublingual DILARANG (penurunan TD tidak terkontrol, fatal)",
            "Labetalol KI pada asma berat, bradikardia, dan blok AV derajat tinggi",
        ],
    },

    # ── I63.9 STROKE ISKEMIK ──────────────────────────────────────────────────
    "I63.9": {
        "nama_ppk": "PPK Stroke Iskemik Akut",
        "target_waktu": "IV tPA: door-to-needle < 60 menit (window < 4,5 jam)",
        "pemeriksaan_awal": [
            "CT scan kepala TANPA kontras segera (eksklusi perdarahan)",
            "GDS cito (eksklusi hipoglikemia yang mimik stroke)",
            "EKG 12 lead (cari AF sebagai penyebab)",
            "Darah lengkap, PT/INR, aPTT, fungsi ginjal",
            "Skor NIHSS (National Institutes of Health Stroke Scale)",
        ],
        "tatalaksana": [
            {"prioritas": "KRITIS",  "kategori": "tPA",           "aksi": "Alteplase 0,9 mg/kg IV (maks 90 mg): 10% bolus 1 mnt, sisa 90% infus 60 mnt — JIKA memenuhi kriteria inklusi"},
            {"prioritas": "KRITIS",  "kategori": "TD Control",    "aksi": "TD < 185/110 sebelum tPA (gunakan Labetalol IV); jika tidak tPA: turunkan hanya jika TD > 220/120"},
            {"prioritas": "TINGGI",  "kategori": "Trombektomi",   "aksi": "Pertimbangkan mechanical thrombectomy (NIHSS > 6, large vessel occlusion, window < 24 jam pada kasus tertentu)"},
            {"prioritas": "TINGGI",  "kategori": "Neuroproteksi", "aksi": "Hindari hiperglikemia (GDS > 180), hipotermia, hiperoksigenasi; cegah hipertermia"},
            {"prioritas": "SEDANG",  "kategori": "Antiplatelet",  "aksi": "Aspirin 300 mg PO dalam 24-48 jam setelah tPA (atau segera jika tidak tPA)"},
        ],
        "monitoring": [
            "Pemeriksaan neurologis tiap 15 menit selama dan 2 jam setelah tPA",
            "TD tiap 15 menit dalam 2 jam, lalu tiap 30 menit 6 jam, lalu tiap jam 16 jam",
            "CT scan ulang 24 jam pasca tPA (eksklusi HT)",
            "GDS tiap 1-2 jam (target 140-180 mg/dL)",
        ],
        "kontraindikasi_perhatian": [
            "tPA KONTRAINDIKASI: perdarahan aktif, stroke/operasi kepala < 3 bulan, TD > 185/110 yang tidak turun, INR > 1,7, trombosit < 100.000",
            "HINDARI antikoagulan 24 jam pertama pasca tPA",
        ],
    },
}


# =============================================================================
# C. KEYWORD MAP  —  DETEKSI KONDISI DARI TEKS BEBAS
# =============================================================================

_KEYWORD_MAP: list[tuple[list[str], str]] = [
    # Jantung
    (["stemi", "st elevasi", "elevasi st", "infark anterior", "infark inferior"],     "I21.0"),
    (["nstemi", "non stemi", "nste-acs"],                                              "I21.4"),
    (["apts", "angina tidak stabil", "unstable angina", "acs", "sindrom koroner akut"], "I20.0"),
    (["gagal jantung", "gjk", "chf", "heart failure", "adhf", "hfref", "hfpef"],     "I50.0"),
    (["edema paru akut", "epa", "acute pulmonary edema", "ronki basah bilateral"],     "I50.1"),
    (["fibrilasi atrium", " af ", "afib", "atrial fibrilasi", "atrial fibrillation"], "I48.0"),
    (["svt", "takikardia supraventrikular", "supraventricular tachycardia"],           "I47.1"),
    (["vt ", " vt,", "takikardia ventrikel", "ventricular tachycardia"],              "I47.2"),
    (["vf ", "fibrilasi ventrikel", "ventricular fibrillation", "cardiac arrest", "henti jantung"], "I49.0"),
    (["av block", "blok av", "blok total", "complete av block", "cavb", "av blok"],   "I44.2"),
    (["hipertensi emergensi", "hypertensive emergency", "htn emergency"],              "I16.1"),
    (["hipertensi urgensi", "hypertensive urgency", "htn urgency"],                   "I16.0"),
    (["hipertensi", "htn", "tekanan darah tinggi", "td tinggi"],                      "I10"),
    (["syok kardiogenik", "cardiogenic shock", "syok kardiogen"],                      "R57.0"),
    (["pjk", "jantung koroner", "coronary artery disease", "cad", "iskemia"],         "I25.1"),
    (["tamponade", "hemoperikardium", "pericardial tamponade"],                        "I31.2"),
    (["emboli paru", "pulmonary embolism", " pe ", "tromboemboli paru", "dvt"],        "I26.9"),
    (["diseksi aorta", "aortic dissection", "diseksi"],                                "I71.0"),
    # Napas
    (["ards", "acute respiratory distress", "sindrom gagal napas akut"],               "J80"),
    (["gagal napas", "respiratory failure", "napas", "ventilasi mekanik", "intubasi"], "J96.0"),
    (["pneumonia", "pnemonia", "community acquired", "cap ", "hap ", "vap "],         "J18.9"),
    (["ppok", "copd", "eksaserbasi ppok", "copd exacerbation"],                        "J44.1"),
    (["asma", "status asmatikus", "bronkospasme"],                                     "J45.5"),
    # Infeksi
    (["sepsis", "septik", "septic", "septicemia", "urosepsis"],                        "A41.9"),
    (["syok septik", "septic shock", "syok sepsis"],                                   "R65.2"),
    # Ginjal
    (["aki ", "gagal ginjal akut", "acute kidney injury", "acute renal failure"],      "N17.9"),
    (["ckd", "penyakit ginjal kronik", "cronic kidney", "hemodialisis"],               "N18.5"),
    # Metabolik
    (["hiperkalemia", "kalium tinggi", "k+ tinggi", "hyperkalemia"],                   "E87.5"),
    (["hiponatremia", "natrium rendah", "sodium rendah", "hyponatremia"],              "E87.1"),
    (["dka", "ketoasidosis diabetik", "diabetic ketoacidosis"],                         "E10.1"),
    (["hipoglikemia", "gds rendah", "gula darah rendah", "hypoglycemia"],              "E16.0"),
    # Neurologi
    (["stroke iskemik", "cerebral infarction", "tia", "ischemic stroke"],              "I63.9"),
    (["stroke hemoragik", "perdarahan otak", "ich", "subarachnoid"],                   "I61.9"),
    (["epilepsi", "kejang", "status epileptikus", "seizure"],                          "G40.9"),
]

_ICD10_PATTERN = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,2})?)\b')


# =============================================================================
# D. PARSER TEKS  —  ICD-10 & NUMERIK
# =============================================================================

def _extract_icd10(text: str) -> list[str]:
    """Deteksi kode ICD-10 dari teks bebas (literal + keyword)."""
    found: set[str] = set()
    text_lower = text.lower()

    for match in _ICD10_PATTERN.finditer(text.upper()):
        kode = match.group(1)
        if kode in ICD10_NAMA:
            found.add(kode)

    for keywords, kode in _KEYWORD_MAP:
        if any(kw in text_lower for kw in keywords):
            found.add(kode)

    return sorted(found)


def _extract_numeric(o_text: str) -> dict:
    """Ekstrak nilai numerik tanda vital dari teks Objektif (O)."""
    findings: dict[str, float] = {}
    text_lower = o_text.lower()

    patterns: dict[str, list[str]] = {
        "heart_rate":       [r'hr[:\s]+(\d+)', r'nadi[:\s]+(\d+)', r'heart rate[:\s]+(\d+)', r'hr\s*=\s*(\d+)'],
        "systolic_bp":      [r'td[:\s]+(\d+)/', r'bp[:\s]+(\d+)/', r'tekanan darah[:\s]+(\d+)/', r'sistol[:\s]+(\d+)', r'td\s*=\s*(\d+)/'],
        "diastolic_bp":     [r'td[:\s]+\d+/(\d+)', r'bp[:\s]+\d+/(\d+)', r'tekanan darah[:\s]+\d+/(\d+)'],
        "spo2":             [r'spo2[:\s]+([\d.]+)', r'saturasi[:\s]+([\d.]+)', r'sat\s*o2[:\s]+([\d.]+)', r'spo2\s*=\s*([\d.]+)'],
        "respiratory_rate": [r'rr[:\s]+(\d+)', r'laju napas[:\s]+(\d+)', r'frekuensi napas[:\s]+(\d+)', r'rr\s*=\s*(\d+)'],
        "temperature":      [r'suhu[:\s]+([\d.,]+)', r'temp[:\s]+([\d.,]+)', r's[:\s]+(3[5-9][.,]\d)', r'suhu\s*=\s*([\d.,]+)'],
        "gds":              [r'gds[:\s]+(\d+)', r'gdp[:\s]+(\d+)', r'gula darah[:\s]+(\d+)', r'glukosa[:\s]+(\d+)'],
        "spo2_fio2":        [r'p/f[:\s]+([\d.]+)', r'pf ratio[:\s]+([\d.]+)', r'spo2/fio2[:\s]+([\d.]+)'],
        "laktat":           [r'laktat[:\s]+([\d.]+)', r'lactate[:\s]+([\d.]+)'],
        "creatinine":       [r'kreatinin[:\s]+([\d.]+)', r'creatinine[:\s]+([\d.]+)', r'cr[:\s]+([\d.]+)'],
        "kalium":           [r'kalium[:\s]+([\d.]+)', r'k\+[:\s]+([\d.]+)', r'k[:\s]+([\d.]+)\s*meq'],
    }

    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text_lower)
            if m:
                try:
                    val_str = m.group(1).replace(',', '.')
                    findings[key] = float(val_str)
                    break
                except (ValueError, AttributeError):
                    pass

    return findings


# =============================================================================
# E. ALERT GENERATOR  —  BERBASIS NILAI NUMERIK
# =============================================================================

def _build_vital_alerts(numeric: dict) -> list[dict]:
    """Hasilkan alert klinis prioritas KRITIS berdasarkan nilai tanda vital."""
    alerts: list[dict] = []

    hr  = numeric.get("heart_rate")
    sbp = numeric.get("systolic_bp")
    spo2 = numeric.get("spo2")
    rr  = numeric.get("respiratory_rate")
    temp = numeric.get("temperature")
    gds = numeric.get("gds")
    laktat = numeric.get("laktat")
    kr  = numeric.get("creatinine")
    k   = numeric.get("kalium")

    if spo2 is not None:
        if spo2 < 88:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Respirasi",    "deskripsi": f"SpO2 {spo2}% — HIPOKSEMIA BERAT. Berikan O2 segera, evaluasi indikasi intubasi/NIV"})
        elif spo2 < 94:
            alerts.append({"prioritas": "TINGGI",  "kategori": "Respirasi",    "deskripsi": f"SpO2 {spo2}% — hipoksemia sedang. Tingkatkan suplementasi O2, monitoring ketat"})

    if sbp is not None:
        if sbp < 80:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Sirkulasi",    "deskripsi": f"TD sistolik {sbp} mmHg — SYOK. Resusitasi cairan, pertimbangkan vasopressor segera"})
        elif sbp < 90:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Sirkulasi",    "deskripsi": f"TD sistolik {sbp} mmHg — HIPOTENSI BERAT. Evaluasi volume status, siapkan vasopressor"})
        elif sbp > 200:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Hipertensi",   "deskripsi": f"TD sistolik {sbp} mmHg — HIPERTENSI BERAT. Evaluasi end-organ damage, tatalaksana segera"})

    if hr is not None:
        if hr > 150:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Irama Jantung","deskripsi": f"HR {int(hr)} bpm — TAKIKARDIA EKSTREM. EKG 12 lead segera, evaluasi VT/SVT/AF dengan RVR"})
        elif hr < 40:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Irama Jantung","deskripsi": f"HR {int(hr)} bpm — BRADIKARDIA BERAT. EKG segera, siapkan transcutaneous pacing"})
        elif hr > 120:
            alerts.append({"prioritas": "TINGGI",  "kategori": "Irama Jantung","deskripsi": f"HR {int(hr)} bpm — takikardia signifikan. Evaluasi penyebab (nyeri, demam, hipovolemia, aritmia)"})

    if rr is not None:
        if rr > 30:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Respirasi",    "deskripsi": f"RR {int(rr)} x/mnt — TAKIPNEA BERAT. Evaluasi gagal napas, pertimbangkan NIV/intubasi"})
        elif rr < 8:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Respirasi",    "deskripsi": f"RR {int(rr)} x/mnt — BRADIPNEA. Risiko gagal napas, siapkan BVM dan dukungan airway"})

    if temp is not None:
        if temp > 39.5:
            alerts.append({"prioritas": "TINGGI",  "kategori": "Infeksi",      "deskripsi": f"Suhu {temp}°C — HIPERPIREKSIA. Pertimbangkan sepsis, kultur darah SEBELUM antibiotik"})
        elif temp < 36.0:
            alerts.append({"prioritas": "TINGGI",  "kategori": "Infeksi",      "deskripsi": f"Suhu {temp}°C — hipotermi. Evaluasi sepsis (tanda dingin), atau hipotermia accidental"})

    if gds is not None:
        if gds > 400:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Metabolik",    "deskripsi": f"GDS {int(gds)} mg/dL — HIPERGLIKEMIA BERAT. Evaluasi DKA/HHS, mulai insulin protokol segera"})
        elif gds < 60:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Metabolik",    "deskripsi": f"GDS {int(gds)} mg/dL — HIPOGLIKEMIA. Bolus D40% 50 mL IV segera, pantau GDS tiap 15 mnt"})
        elif gds > 200:
            alerts.append({"prioritas": "SEDANG",  "kategori": "Metabolik",    "deskripsi": f"GDS {int(gds)} mg/dL — hiperglikemia. Target ICU 140-180 mg/dL; mulai insulin infus jika perlu"})

    if laktat is not None and laktat > 2.0:
        alerts.append({"prioritas": "KRITIS",      "kategori": "Metabolik",    "deskripsi": f"Laktat {laktat} mmol/L — HIPERLAKTATEMIA. Curiga hipoperfusi/sepsis; resusitasi dan evaluasi penyebab"})

    if k is not None:
        if k > 6.0:
            alerts.append({"prioritas": "KRITIS",  "kategori": "Elektrolit",   "deskripsi": f"Kalium {k} mEq/L — HIPERKALEMIA BERAT. EKG segera, kalsium glukonat IV, koreksi emergensi"})
        elif k < 3.0:
            alerts.append({"prioritas": "TINGGI",  "kategori": "Elektrolit",   "deskripsi": f"Kalium {k} mEq/L — HIPOKALEMIA. Suplementasi K+ IV, risiko aritmia ventrikel"})

    if kr is not None and kr > 3.0:
        alerts.append({"prioritas": "TINGGI",      "kategori": "Ginjal",       "deskripsi": f"Kreatinin {kr} mg/dL — AKI signifikan. Stop nefrotoksin, evaluasi kebutuhan dialisis"})

    return alerts


# =============================================================================
# F. REKOMENDASI BUILDER  —  BERBASIS PROTOKOL PPK
# =============================================================================

def _build_protocol_recs(icd10_codes: list[str]) -> list[dict]:
    """Susun rekomendasi tatalaksana terstruktur per kode ICD-10 dari PPK."""
    recs: list[dict] = []

    for kode in icd10_codes:
        ppk = PPK_PROTOKOL.get(kode)
        if not ppk:
            # Fallback: informasi dasar dari ICD10_NAMA saja
            info = ICD10_NAMA.get(kode, {})
            recs.append({
                "kode": kode,
                "kategori": "Umum",
                "deskripsi": f"Tata laksana sesuai panduan {info.get('nama', kode)}",
                "prioritas": "SEDANG",
                "detail": "Konsultasi PPK RS dan panduan terkini untuk kondisi ini.",
            })
            continue

        # Pemeriksaan awal
        for i, item in enumerate(ppk.get("pemeriksaan_awal", [])[:5]):
            recs.append({
                "kode": f"PEMERIKSAAN:{kode}:{i}",
                "kategori": "Pemeriksaan Awal",
                "deskripsi": f"[{kode}] {item}",
                "prioritas": "SEGERA",
                "detail": ppk.get("nama_ppk", ""),
            })

        # Tatalaksana utama
        for tl in ppk.get("tatalaksana", []):
            recs.append({
                "kode": f"TL:{kode}:{tl['kategori']}",
                "kategori": tl["kategori"],
                "deskripsi": f"[{kode}] {tl['aksi']}",
                "prioritas": tl["prioritas"],
                "detail": ppk.get("nama_ppk", ""),
            })

        # Monitoring
        for i, item in enumerate(ppk.get("monitoring", [])[:3]):
            recs.append({
                "kode": f"MONITORING:{kode}:{i}",
                "kategori": "Monitoring",
                "deskripsi": f"[{kode}] {item}",
                "prioritas": "SEDANG",
                "detail": ppk.get("nama_ppk", ""),
            })

        # Perhatian / kontraindikasi
        for i, item in enumerate(ppk.get("kontraindikasi_perhatian", [])[:2]):
            recs.append({
                "kode": f"KI:{kode}:{i}",
                "kategori": "Perhatian / KI",
                "deskripsi": f"[{kode}] {item}",
                "prioritas": "PERHATIAN",
                "detail": ppk.get("nama_ppk", ""),
            })

    return recs


# =============================================================================
# G. FUNGSI UTAMA  —  ENTRY POINT UNTUK DASHBOARD.PY
# =============================================================================

def analyze_icd10_dan_tatalaksana(s_input: str, o_input: str) -> dict:
    """
    Entry point CDSS Dokter v1.0.

    Dipanggil oleh dashboard.py (role Dokter) dengan data S dan O dari form SOAP.

    Parameters
    ----------
    s_input : str  —  teks Subjektif (S)
    o_input : str  —  teks Objektif (O)

    Returns
    -------
    dict:
        status           : "success" | "error"
        diagnosa_list    : list[dict] — {kode, nama, kategori, prioritas_ppk}
        rekomendasi      : list[dict] — {kode, kategori, deskripsi, prioritas, detail}
        numeric_findings : dict       — tanda vital terdeteksi
        clinical_context : dict       — ringkasan konteks klinis
    """
    try:
        combined = f"{s_input}\n{o_input}"

        # 1. Deteksi ICD-10
        icd10_codes = _extract_icd10(combined)

        # 2. Ekstrak numerik
        numeric = _extract_numeric(o_input)

        # 3. Alert vital signs (prioritas KRITIS/TINGGI)
        vital_alerts = _build_vital_alerts(numeric)

        # 4. Rekomendasi PPK per diagnosa
        protocol_recs = _build_protocol_recs(icd10_codes)

        # 5. Merge: alert dahulu (lebih urgent), lalu protokol
        semua_recs: list[dict] = vital_alerts + protocol_recs

        # 6. Susun diagnosa_list dengan info PPK
        diagnosa_list = []
        for kode in icd10_codes:
            info = ICD10_NAMA.get(kode, {"nama": kode, "kategori": "Lainnya"})
            ppk  = PPK_PROTOKOL.get(kode, {})
            diagnosa_list.append({
                "kode":        kode,
                "nama":        info["nama"],
                "kategori":    info["kategori"],
                "nama_ppk":    ppk.get("nama_ppk", ""),
                "target_waktu": ppk.get("target_waktu", ""),
            })

        # 7. Clinical context
        ada_kritis = any(r.get("prioritas") in ("KRITIS",) for r in semua_recs)
        clinical_context = {
            "icd10_terdeteksi":           icd10_codes,
            "jumlah_diagnosa":            len(icd10_codes),
            "jumlah_rekomendasi":         len(semua_recs),
            "kondisi_kritis_terdeteksi":  ada_kritis,
            "timestamp_analisis":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ppk_digunakan":              [PPK_PROTOKOL[k]["nama_ppk"] for k in icd10_codes if k in PPK_PROTOKOL],
        }

        return {
            "status":           "success",
            "diagnosa_list":    diagnosa_list,
            "rekomendasi":      semua_recs,
            "numeric_findings": numeric,
            "clinical_context": clinical_context,
        }

    except Exception as exc:
        return {
            "status":           "error",
            "diagnosa_list":    [],
            "rekomendasi":      [],
            "numeric_findings": {},
            "clinical_context": {"error": str(exc)},
        }

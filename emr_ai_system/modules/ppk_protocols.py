"""
Database Protokol Tata Laksana Klinis (PPK).
Referensi utama:
  - Panduan Praktik Klinis (PPK) RS (internal)
  - Pedoman Tata Laksana Sindrom Koroner Akut — PERKI 2018 / Update 2022
  - Pedoman Tata Laksana Gagal Jantung — PERKI 2020
  - Pedoman Tata Laksana Fibrilasi Atrium — PERKI 2022
  - Pedoman Tata Laksana Hipertensi — InaSH / ISH 2019
  - Panduan Sepsis-3 — Surviving Sepsis Campaign 2021
  - ARDS Berlin Definition & ARDSNet Protocol

Struktur setiap entri PPK:
{
    "icd10_codes"           : list[str],      # kode ICD-10 yang dicakup
    "nama_ppk"              : str,
    "versi_referensi"       : str,
    "tujuan_terapi"         : str,
    "kriteria_masuk_icu"    : list[str],       # kapan pasien harus ICU
    "pemeriksaan_awal"      : list[str],       # workup diagnostik wajib
    "tata_laksana_utama"    : list[dict],      # langkah-langkah terapi
    "obat_rekomendasi"      : list[dict],      # formularium + dosis
    "monitoring_wajib"      : list[str],       # parameter yang dipantau
    "target_terapi"         : dict,
    "kontraindikasi_penting": list[str],
    "kriteria_rujuk_eskalasi": list[str],
    "skor_risiko"           : dict,            # tool stratifikasi risiko
}
"""

PPK_DB: list[dict] = [

    # ─────────────────────────────────────────────────────────────────────
    # STEMI — Infark Miokard dengan ST-Elevasi
    # ─────────────────────────────────────────────────────────────────────
    {
        "icd10_codes": ["I21.0", "I21.1", "I22.0"],
        "nama_ppk": "Tata Laksana Sindrom Koroner Akut — STEMI",
        "versi_referensi": "PERKI 2018 / Update ESC 2022 — Disesuaikan RS",
        "tujuan_terapi": "Reperfusi miokard secepat mungkin (target D2B <90 menit / D2N <30 menit), "
                         "minimalisasi area nekrosis, prevensi komplikasi akut.",
        "kriteria_masuk_icu": [
            "Semua pasien STEMI wajib dirawat ICU atau ICCU",
            "Hemodinamik tidak stabil (syok kardiogenik)",
            "Aritmia maligna (VT/VF)",
            "Komplikasi mekanik (regurgitasi mitral akut, ruptur septum ventrikel)",
        ],
        "pemeriksaan_awal": [
            "EKG 12 lead SEGERA (dalam 10 menit sejak tiba)",
            "Foto Toraks AP",
            "Darah Lengkap + Hitung Jenis",
            "Kimia Klinik: ureum, kreatinin, elektrolit, GDS",
            "Enzim Jantung: Troponin I/T (high-sensitivity), CK-MB",
            "Koagulasi: PT/INR, aPTT",
            "AGD (bila ada distres napas)",
            "Ekokardiografi urgent bila diagnosis meragukan",
        ],
        "tata_laksana_utama": [
            {
                "urutan": 1, "langkah": "MONA-B Protocol",
                "detail": "Morphine IV (2-4 mg bila nyeri hebat), Oksigen (target SpO2 >94%), "
                          "Nitrat sublingual (bila tidak ada kontraindikasi), Aspirin loading 300 mg PO.",
            },
            {
                "urutan": 2, "langkah": "Antiplatelet Dual (DAPT) Loading",
                "detail": "Aspirin 300 mg PO (single dose) + Ticagrelor 180 mg PO ATAU "
                          "Clopidogrel 600 mg PO (bila Ticagrelor tidak tersedia / dikontraindikasikan).",
            },
            {
                "urutan": 3, "langkah": "Antikoagulan",
                "detail": "UFH IV bolus 70-100 IU/kgBB + infus kontinyu ATAU Enoxaparin 0.5 mg/kgBB IV bolus "
                          "(kemudian 1 mg/kgBB SC q12h).",
            },
            {
                "urutan": 4, "langkah": "Strategi Reperfusi",
                "detail": "PILIHAN UTAMA: Primary PCI (intervensi koroner perkutan primer) — target D2B <90 mnt. "
                          "BILA PCI tidak tersedia: Fibrinolisis dalam 12 jam onset (alteplase / streptokinase).",
            },
            {
                "urutan": 5, "langkah": "Beta-Blocker (dalam 24 jam pertama bila stabil)",
                "detail": "Metoprolol 12.5-25 mg PO q12h. KONTRAINDIKASI: HR <60, SBP <100, AV blok, "
                          "bronkospasme aktif, syok kardiogenik.",
            },
            {
                "urutan": 6, "langkah": "ACEI / ARB (dalam 24 jam pertama bila EF <40% atau DM/HT)",
                "detail": "Ramipril 2.5 mg PO OD (titrasi bertahap) ATAU Valsartan 40 mg PO BID. "
                          "Mulai dosis rendah, pantau tekanan darah dan fungsi ginjal.",
            },
            {
                "urutan": 7, "langkah": "Statin Intensitas Tinggi",
                "detail": "Atorvastatin 40-80 mg PO malam hari ATAU Rosuvastatin 20-40 mg PO malam hari. "
                          "Mulai dalam 24 jam pertama tanpa menunggu hasil lab lipid.",
            },
        ],
        "obat_rekomendasi": [
            {"nama": "Aspirin", "dosis": "300 mg loading → 75-100 mg/hari maintenance", "rute": "PO", "catatan": "DAPT bersama Ticagrelor/Clopidogrel"},
            {"nama": "Ticagrelor", "dosis": "180 mg loading → 90 mg q12h", "rute": "PO", "catatan": "Pilihan P2Y12 inhibitor utama pada STEMI"},
            {"nama": "Clopidogrel", "dosis": "600 mg loading → 75 mg/hari", "rute": "PO", "catatan": "Alternatif bila Ticagrelor kontraindikasi"},
            {"nama": "Enoxaparin (LMWH)", "dosis": "0.5 mg/kgBB IV bolus → 1 mg/kgBB SC q12h", "rute": "IV/SC", "catatan": "Sesuaikan dosis pada CrCl <30 mL/mnt"},
            {"nama": "Heparin Tidak Terfraksi (UFH)", "dosis": "70-100 IU/kgBB IV bolus → infus 12-15 IU/kgBB/jam", "rute": "IV", "catatan": "Pantau aPTT target 50-70 detik"},
            {"nama": "Metoprolol", "dosis": "25-50 mg q12h (titrasi)", "rute": "PO", "catatan": "Mulai 24-48 jam bila hemodinamik stabil"},
            {"nama": "Ramipril", "dosis": "2.5 mg OD (titrasi hingga 10 mg OD)", "rute": "PO", "catatan": "Mulai dosis rendah, pantau kreatin/kalium"},
            {"nama": "Atorvastatin", "dosis": "40-80 mg malam hari", "rute": "PO", "catatan": "Statin intensitas tinggi, pertahankan jangka panjang"},
            {"nama": "Morfin", "dosis": "2-4 mg IV pelan (dapat diulang q5-10 mnt bila perlu)", "rute": "IV", "catatan": "Hanya bila nyeri tidak tertahankan, perhatikan efek hipotensi"},
            {"nama": "ISDN Sublingual", "dosis": "5 mg SL", "rute": "SL", "catatan": "KONTRAINDIKASI: SBP <90, penggunaan PDE5 inhibitor 48 jam terakhir"},
        ],
        "monitoring_wajib": [
            "EKG monitoring kontinu (telemetri) minimal 24 jam",
            "Tanda vital tiap 1 jam (periode akut), tiap 4 jam (stabil)",
            "Troponin serial: jam 0, 3, 6 (atau sesuai protokol hs-cTn)",
            "CK-MB serial: jam 0, 6, 12",
            "Ekokardiografi: dalam 24 jam untuk penilaian LVEF dan komplikasi",
            "Input-output cairan ketat",
            "Elektrolit (K+, Mg2+) tiap 12-24 jam",
            "Fungsi ginjal (ureum, kreatinin) tiap 24 jam",
        ],
        "target_terapi": {
            "HR": "50-70 bpm (bila tanpa syok)",
            "SBP": ">90 mmHg, idealnya 90-130 mmHg",
            "SpO2": ">94%",
            "K+": "3.5-5.0 mEq/L",
            "Mg2+": ">0.8 mmol/L",
            "GDS": "140-180 mg/dL (hindari hipoglikemia)",
        },
        "kontraindikasi_penting": [
            "NITRAT: Penggunaan PDE5-inhibitor (sildenafil, tadalafil) dalam 48 jam, SBP <90 mmHg",
            "BETA-BLOCKER: Syok kardiogenik, AV blok derajat II-III, HR <60, bronkospasme aktif",
            "FIBRINOLISIS: Riwayat stroke 3 bulan terakhir, perdarahan aktif, operasi besar <3 minggu",
            "TICAGRELOR: Riwayat perdarahan intrakranial, gangguan fungsi hati berat",
            "ACEI/ARB: Kehamilan, hiperkalemia berat (K+ >5.5), stenosis arteri renalis bilateral",
        ],
        "kriteria_rujuk_eskalasi": [
            "Syok kardiogenik refrakter: pertimbangkan IABP / ECMO",
            "VT/VF berulang: pertimbangkan ICD atau ablasi",
            "Komplikasi mekanik: rujuk bedah jantung emergensi",
            "LVEF <35% pasca-STEMI: evaluasi ICD profilaksis dalam 40 hari",
        ],
        "skor_risiko": {
            "TIMI Risk Score": "Skor 0-14: mortalitas 30 hari (0-1%: risiko rendah, ≥5: risiko tinggi)",
            "GRACE Score": "Skor mortalitas rawat inap dan 6 bulan pasca-ACS",
            "Killip Classification": "I: tanpa gagal jantung, II: ronki basah, III: edema paru, IV: syok",
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # NSTEMI / APTS
    # ─────────────────────────────────────────────────────────────────────
    {
        "icd10_codes": ["I21.4", "I20.0"],
        "nama_ppk": "Tata Laksana Sindrom Koroner Akut — NSTEMI / APTS",
        "versi_referensi": "PERKI 2018 / ESC NSTE-ACS Guidelines 2020",
        "tujuan_terapi": "Stabilisasi plak, prevensi infark, stratifikasi risiko, "
                         "dan penentuan strategi invasif (PCI/CABG) vs konservatif.",
        "kriteria_masuk_icu": [
            "GRACE Score ≥140 (risiko tinggi)",
            "Troponin positif (NSTEMI terkonfirmasi)",
            "Perubahan ST dinamis atau iskemia berulang",
            "Ketidakstabilan hemodinamik",
            "Gagal jantung akut",
        ],
        "pemeriksaan_awal": [
            "EKG 12 lead segera (dalam 10 menit)",
            "hs-Troponin I/T: jam 0 dan 1 jam (atau 0 dan 3 jam protokol ESC)",
            "Darah Lengkap, Kimia Klinik, Koagulasi",
            "Ekokardiografi untuk penilaian fungsi LV",
            "GRACE Score untuk stratifikasi risiko",
        ],
        "tata_laksana_utama": [
            {
                "urutan": 1, "langkah": "Stabilisasi Awal",
                "detail": "Aspirasi/nyeri: Nitrat SL + Morfin PRN. O2 bila SpO2 <94%. "
                          "Akses IV 2 jalur. Monitoring EKG kontinu.",
            },
            {
                "urutan": 2, "langkah": "Antiplatelet Dual (DAPT)",
                "detail": "Aspirin 300 mg PO loading → 75-100 mg/hari + Ticagrelor 180 mg loading → 90 mg q12h. "
                          "Berikan segera setelah diagnosis ditegakkan.",
            },
            {
                "urutan": 3, "langkah": "Antikoagulan",
                "detail": "Fondaparinux 2.5 mg SC OD (pilihan pertama, risiko perdarahan lebih rendah) ATAU "
                          "Enoxaparin 1 mg/kgBB SC q12h ATAU UFH infus.",
            },
            {
                "urutan": 4, "langkah": "Strategi Invasif",
                "detail": "RISIKO SANGAT TINGGI: invasif <2 jam (syok, VT/VF, gagal jantung akut). "
                          "RISIKO TINGGI: invasif <24 jam (Troponin naik, GRACE>140). "
                          "RISIKO SEDANG: invasif <72 jam. RISIKO RENDAH: tes non-invasif dulu.",
            },
            {
                "urutan": 5, "langkah": "Terapi Jangka Panjang",
                "detail": "Sama dengan STEMI: Beta-blocker, ACEI/ARB (bila EF <40% atau DM/HT), "
                          "Statin intensitas tinggi.",
            },
        ],
        "obat_rekomendasi": [
            {"nama": "Aspirin", "dosis": "300 mg loading → 75-100 mg/hari", "rute": "PO", "catatan": "Seumur hidup"},
            {"nama": "Ticagrelor", "dosis": "180 mg loading → 90 mg q12h × 12 bulan", "rute": "PO", "catatan": "Pilihan P2Y12 utama"},
            {"nama": "Fondaparinux", "dosis": "2.5 mg SC OD", "rute": "SC", "catatan": "Hindari bila GFR <20"},
            {"nama": "Enoxaparin", "dosis": "1 mg/kgBB SC q12h", "rute": "SC", "catatan": "Kurangi dosis 50% bila GFR <30"},
            {"nama": "Atorvastatin", "dosis": "40-80 mg malam hari", "rute": "PO", "catatan": "Intensitas tinggi"},
        ],
        "monitoring_wajib": [
            "Troponin serial sampai plateau/puncak",
            "EKG monitoring kontinu minimal 24 jam",
            "GRACE Score ulang setiap 24 jam",
        ],
        "target_terapi": {
            "SpO2": ">94%", "HR": "50-70 bpm", "SBP": ">90 mmHg",
        },
        "kontraindikasi_penting": [
            "FONDAPARINUX: GFR <20 mL/mnt/1.73m2",
            "Hindari NSAID/COX-2 inhibitor selama fase akut",
        ],
        "kriteria_rujuk_eskalasi": [
            "GRACE Score sangat tinggi dengan kateterisasi jantung tidak tersedia",
            "VT/VF refrakter",
        ],
        "skor_risiko": {
            "GRACE Score": "Kalkulasi online: risk.predict.dk — Low <108, Intermediate 109-140, High >140",
            "TIMI Risk Score NSTEMI": "0-2: rendah, 3-4: sedang, 5-7: tinggi",
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # GAGAL JANTUNG AKUT / DEKOMPENSASI
    # ─────────────────────────────────────────────────────────────────────
    {
        "icd10_codes": ["I50.0", "I50.1", "I50.9"],
        "nama_ppk": "Tata Laksana Gagal Jantung Akut Dekompensasi",
        "versi_referensi": "PERKI 2020 / ESC Heart Failure Guidelines 2021",
        "tujuan_terapi": "Dekongesti cepat, optimalisasi preload-afterload, koreksi penyebab yang "
                         "dapat diobati (CHAMP: koroner akut, hipertensi, aritmia, mekanik, emboli paru).",
        "kriteria_masuk_icu": [
            "SpO2 <90% dengan terapi oksigen konvensional",
            "Edema paru akut dengan distres napas berat",
            "Syok kardiogenik (SBP <90 mmHg)",
            "Butuh ventilasi mekanik (invasif/non-invasif)",
            "Aritmia maligna penyebab dekompensasi",
        ],
        "pemeriksaan_awal": [
            "EKG 12 lead",
            "Foto Toraks AP",
            "Ekokardiografi (prioritas tinggi untuk menilai LVEF)",
            "BNP atau NT-proBNP",
            "Darah Lengkap, Kimia Klinik lengkap",
            "Troponin (singkirkan ACS sebagai pencetus)",
            "TSH (singkirkan hipotiroid/hipertiroid)",
            "AGD bila distres napas",
        ],
        "tata_laksana_utama": [
            {
                "urutan": 1, "langkah": "Posisi dan Oksigenasi",
                "detail": "Posisi duduk/semi-duduk 45-90°. Oksigen target SpO2 94-98%. "
                          "Bila SpO2 tidak membaik: pertimbangkan NIV (CPAP/BiPAP). "
                          "Bila gagal NIV atau exhausted: intubasi dan ventilasi mekanik.",
            },
            {
                "urutan": 2, "langkah": "Diuretik IV (Dekongesti)",
                "detail": "Furosemide IV bolus 40-80 mg (bila naive diuretik) ATAU 1-2x dosis oral harian (bila sudah rutin). "
                          "Dapat diulang tiap 6 jam atau diberikan infus kontinyu 5-40 mg/jam. "
                          "Target: diuresis 100-200 mL/jam.",
            },
            {
                "urutan": 3, "langkah": "Vasodilatasi (bila SBP >110 mmHg)",
                "detail": "Isosorbid Dinitrat (ISDN) infus: mulai 1-2 mg/jam, titrasi sesuai respons tekanan darah.",
            },
            {
                "urutan": 4, "langkah": "Inotropik (bila Syok Kardiogenik / CO rendah)",
                "detail": "Dobutamin infus: mulai 2 mcg/kgBB/mnt, titrasi 2-20 mcg/kgBB/mnt. "
                          "Norepinefrin (bila MAP <65): mulai 0.1 mcg/kgBB/mnt, titrasi sesuai MAP.",
            },
            {
                "urutan": 5, "langkah": "Optimalisasi GDMT (Guided Medical Therapy) Post-Stabilisasi",
                "detail": "Setelah hemodinamik stabil: mulai/titrasi ACEI/ARB, Beta-blocker, MRA "
                          "(mineralocorticoid receptor antagonist), SGLT2-inhibitor (Dapagliflozin/Empagliflozin).",
            },
        ],
        "obat_rekomendasi": [
            {"nama": "Furosemide", "dosis": "40-80 mg IV bolus, dapat diulang/infus kontinyu", "rute": "IV", "catatan": "Pantau diuresis, elektrolit, kreatinin ketat"},
            {"nama": "ISDN (Isosorbid Dinitrat)", "dosis": "Infus 1-10 mg/jam", "rute": "IV", "catatan": "KONTRAINDIKASI: SBP <110 mmHg, stenosis aorta berat"},
            {"nama": "Dobutamin", "dosis": "2-20 mcg/kgBB/mnt infus kontinyu", "rute": "IV", "catatan": "Dapat memperburuk iskemia dan aritmia"},
            {"nama": "Norepinefrin", "dosis": "0.1-1 mcg/kgBB/mnt", "rute": "IV", "catatan": "Via CVC, untuk syok dengan vasodilatasi"},
            {"nama": "Dapagliflozin", "dosis": "10 mg OD", "rute": "PO", "catatan": "Mulai setelah stabilisasi, terbukti kurangi readmisi HF"},
            {"nama": "Spironolakton", "dosis": "25-50 mg OD", "rute": "PO", "catatan": "MRA: monitor K+ dan fungsi ginjal ketat"},
            {"nama": "Bisoprolol", "dosis": "Mulai 1.25 mg OD, titrasi bertahap", "rute": "PO", "catatan": "JANGAN mulai saat fase akut dekomensasi"},
        ],
        "monitoring_wajib": [
            "Input-output cairan ketat (target: balance negatif 1-2L/hari)",
            "Tanda vital tiap 1-2 jam fase akut",
            "SpO2 dan upaya pernapasan kontinu",
            "Elektrolit (K+, Na+) tiap 6-12 jam saat diuresis aktif",
            "Fungsi ginjal tiap 12-24 jam",
            "BNP/NT-proBNP untuk respons terapi",
            "Berat badan harian",
        ],
        "target_terapi": {
            "SpO2": "94-98%",
            "MAP": ">65 mmHg",
            "HR": "60-100 bpm",
            "K+": "3.5-5.0 mEq/L",
            "Kreatinin": "Pantau ketat — toleransi peningkatan 20-30% dari baseline",
            "Diuresis": "0.5-1 mL/kgBB/jam",
        },
        "kontraindikasi_penting": [
            "BETA-BLOCKER: JANGAN mulai saat fase akut dekompensasi",
            "NSAID: Hindari — memperburuk retensi cairan dan fungsi ginjal",
            "VERAPAMIL/DILTIAZEM: Kontraindikasi pada HFrEF",
            "METFORMIN: Tahan sementara bila eGFR <30 atau hemodinamik tidak stabil",
        ],
        "kriteria_rujuk_eskalasi": [
            "Refrakter terhadap terapi maksimal: pertimbangkan IABP, ECMO, LVAD",
            "Pertimbangan transplantasi jantung (EF <25%, kapasitas fungsional sangat buruk)",
        ],
        "skor_risiko": {
            "LVEF Classification": "HFrEF: EF <40%, HFmrEF: 40-49%, HFpEF: ≥50%",
            "NYHA Functional Class": "I-IV: menentukan intensitas terapi GDMT",
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # FIBRILASI ATRIUM
    # ─────────────────────────────────────────────────────────────────────
    {
        "icd10_codes": ["I48.0", "I48.1", "I48.2"],
        "nama_ppk": "Tata Laksana Fibrilasi Atrium",
        "versi_referensi": "PERKI 2022 / ESC AF Guidelines 2020",
        "tujuan_terapi": "Pencegahan tromboemboli (stroke), kontrol laju (rate control), "
                         "dan — bila diperlukan — konversi irama (rhythm control).",
        "kriteria_masuk_icu": [
            "AF dengan respons ventrikel sangat cepat dan hemodinamik tidak stabil",
            "AF dengan Wolff-Parkinson-White (WPW syndrome)",
            "AF baru dengan penyakit penyerta berat (ACS, gagal jantung akut)",
        ],
        "pemeriksaan_awal": [
            "EKG 12 lead",
            "Ekokardiografi (nilai fungsi LV, katup, trombus)",
            "Darah Lengkap, Elektrolit (K+, Mg2+), Fungsi Ginjal, Fungsi Hati",
            "TSH (singkirkan hipertiroid)",
            "Troponin (singkirkan ACS pencetus)",
            "Skor CHA2DS2-VASc untuk stratifikasi risiko stroke",
            "Skor HAS-BLED untuk estimasi risiko perdarahan",
        ],
        "tata_laksana_utama": [
            {
                "urutan": 1, "langkah": "Kontrol Laju Jantung (Rate Control)",
                "detail": "Target HR: 60-110 bpm (target <80 bila gejala). "
                          "Beta-blocker (pilihan pertama, terutama bila gagal jantung EF normal) ATAU "
                          "Digoxin (pilihan pada gagal jantung EF rendah) ATAU "
                          "Amiodarone IV (bila hemodinamik tidak stabil).",
            },
            {
                "urutan": 2, "langkah": "Antikoagulasi — WAJIB bila CHA2DS2-VASc ≥2 (laki-laki) / ≥3 (perempuan)",
                "detail": "NOAC (pilihan utama): Rivaroxaban 20 mg OD makan malam, ATAU Apixaban 5 mg q12h, "
                          "ATAU Dabigatran 150 mg q12h. "
                          "Warfarin (bila NOAC tidak tersedia/tidak bisa): target INR 2-3.",
            },
            {
                "urutan": 3, "langkah": "Konversi Irama (Rhythm Control) — Pilihan selektif",
                "detail": "Kardioversi Elektrik (DC Cardioversion): bila onset <48 jam ATAU sudah antikoagulasi adekuat ≥3 minggu. "
                          "Kardioversi Farmakologis: Amiodaron IV/PO (aman bila ada disfungsi LV). "
                          "Flecainide/Propafenone: JANGAN bila ada penyakit jantung struktural.",
            },
            {
                "urutan": 4, "langkah": "Koreksi Faktor Presipitasi",
                "detail": "Koreksi hipertiroid, hipokalemia, hipomagnesemia, infeksi, hipertensi tidak terkontrol.",
            },
        ],
        "obat_rekomendasi": [
            {"nama": "Metoprolol (rate control)", "dosis": "25-200 mg/hari (dibagi 2x)", "rute": "PO", "catatan": "Atau Bisoprolol 2.5-10 mg OD"},
            {"nama": "Digoxin (rate control)", "dosis": "0.125-0.25 mg OD", "rute": "PO/IV", "catatan": "Pantau level digoksin, K+; hindari pada WPW"},
            {"nama": "Amiodarone (rate/rhythm)", "dosis": "150 mg IV dalam 10 mnt → 1 mg/mnt × 6 jam → 0.5 mg/mnt × 18 jam", "rute": "IV", "catatan": "Pantau fungsi tiroid, hati; flebitis via vena perifer"},
            {"nama": "Rivaroxaban", "dosis": "20 mg OD bersama makan malam (15 mg bila CrCl 15-50)", "rute": "PO", "catatan": "NOAC pilihan utama"},
            {"nama": "Apixaban", "dosis": "5 mg q12h (2.5 mg q12h bila ≥2 dari: usia ≥80, BB ≤60 kg, Cr ≥1.5)", "rute": "PO", "catatan": "Risiko perdarahan lebih rendah"},
            {"nama": "Warfarin", "dosis": "Dosis individual, target INR 2-3", "rute": "PO", "catatan": "Banyak interaksi obat-makanan; INR bulanan"},
        ],
        "monitoring_wajib": [
            "EKG dan telemetri monitoring",
            "HR kontrol tiap 6-8 jam",
            "Elektrolit (K+, Mg2+) tiap 12-24 jam",
            "INR (bila warfarin): awal tiap 3-7 hari",
            "Fungsi ginjal (bila NOAC): tiap 3-6 bulan",
        ],
        "target_terapi": {
            "HR": "60-110 bpm (lenient rate control)",
            "INR": "2-3 (bila warfarin)",
            "K+": "3.5-5.0 mEq/L",
        },
        "kontraindikasi_penting": [
            "FLECAINIDE/PROPAFENONE: Kontraindikasi pada penyakit jantung struktural (LVEF <40%, riwayat MI)",
            "DIGOXIN: Hindari pada AF dengan WPW — dapat mempercepat konduksi aksesoris → VF",
            "VERAPAMIL/DILTIAZEM: Kontraindikasi pada HFrEF (EF <40%)",
            "NOAC: Tidak dipakai pada stenosis mitral reumatik berat atau katup jantung mekanik (gunakan warfarin)",
        ],
        "kriteria_rujuk_eskalasi": [
            "AF berulang dengan gagal terapi medis: pertimbangkan ablasi kateter",
            "AF dengan WPW: ablasi jalur aksesoris",
        ],
        "skor_risiko": {
            "CHA2DS2-VASc": "C=CHF(1), H=HTN(1), A2=Usia≥75(2), D=DM(1), S2=Stroke/TIA(2), V=Penyakit Vaskular(1), A=Usia 65-74(1), Sc=Perempuan(1). Antikoagulasi bila ≥2(L) atau ≥3(P).",
            "HAS-BLED": "Hipertensi, fungsi ginjal/hati abnormal, Stroke, Perdarahan, INR labil, Usia>65, Obat/Alkohol. Skor ≥3 = risiko tinggi perdarahan",
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # KRISIS HIPERTENSI
    # ─────────────────────────────────────────────────────────────────────
    {
        "icd10_codes": ["I16.0", "I16.1"],
        "nama_ppk": "Tata Laksana Krisis Hipertensi",
        "versi_referensi": "InaSH / ISH 2019 / PPK RS",
        "tujuan_terapi": "Urgensi: turunkan TD bertahap dalam 24-48 jam. "
                         "Emergensi: turunkan MAP 10-15% dalam 1 jam, kemudian bertahap dalam 24 jam.",
        "kriteria_masuk_icu": [
            "Hipertensi emergensi dengan kerusakan organ target",
            "Ensefalopati hipertensif",
            "Edema paru hipertensif",
            "ACS pencetus hipertensi",
            "Diseksi aorta",
        ],
        "pemeriksaan_awal": [
            "TD kedua lengan (nilai selisih >20 mmHg: curiga diseksi)",
            "EKG 12 lead",
            "Funduskopi (papilledema, perdarahan retina)",
            "Darah Lengkap, Kimia Klinik, Urinalisis (proteinuria, silinder eritrosit)",
            "CT Kepala tanpa kontras (bila gejala neurologis)",
            "Foto Toraks (edema paru, pelebaran mediastinum)",
            "BNP bila suspek gagal jantung",
        ],
        "tata_laksana_utama": [
            {
                "urutan": 1, "langkah": "Emergensi Hipertensi (dengan kerusakan organ target)",
                "detail": "Rawat ICU. Antihipertensi IV: "
                          "Nikardipin infus 5 mg/jam (titrasi 2.5 mg/jam tiap 5-15 mnt, maks 15 mg/jam) ATAU "
                          "Labetolol IV 20 mg bolus (dapat diulang 40-80 mg tiap 10 mnt, maks 300 mg) ATAU "
                          "NTG infus 5-100 mcg/mnt (terutama bila disertai ACS/edema paru).",
            },
            {
                "urutan": 2, "langkah": "Target Penurunan TD (Emergensi)",
                "detail": "Jam 1: Turunkan MAP ≤25% (jangan lebih). "
                          "Jam 2-6: TD ≤160/100-110 mmHg. "
                          "Jam 24-48: TD target <140/90 mmHg. "
                          "JANGAN turunkan terlalu cepat (risiko iskemia serebral/koroner).",
            },
            {
                "urutan": 3, "langkah": "Urgensi Hipertensi (tanpa kerusakan organ target)",
                "detail": "Turunkan TD secara bertahap dalam 24-48 jam. "
                          "Obat oral: Amlodipine 5-10 mg, Captopril 12.5-25 mg, atau Klonidin 0.075-0.15 mg. "
                          "HINDARI Nifedipine SL (turun terlalu cepat → iskemia).",
            },
        ],
        "obat_rekomendasi": [
            {"nama": "Nikardipin IV", "dosis": "5 mg/jam, titrasi hingga 15 mg/jam", "rute": "IV infus", "catatan": "Pilihan utama emergensi; tidak tersedia di semua RS"},
            {"nama": "Labetolol IV", "dosis": "20 mg IV bolus pelan, dapat diulang", "rute": "IV", "catatan": "Kontraindikasi: asma berat, AV blok, gagal jantung akut"},
            {"nama": "NTG IV (Nitrogliserin)", "dosis": "5-100 mcg/mnt infus", "rute": "IV", "catatan": "Pilihan bila ada ACS atau edema paru"},
            {"nama": "Amlodipine", "dosis": "5-10 mg OD", "rute": "PO", "catatan": "Untuk urgensi dan pemeliharaan"},
            {"nama": "Captopril", "dosis": "12.5-25 mg q8h", "rute": "PO", "catatan": "Untuk urgensi; pantau fungsi ginjal"},
        ],
        "monitoring_wajib": [
            "TD setiap 5-15 menit (emergensi) atau 30-60 menit (urgensi)",
            "Input-output cairan",
            "Pemeriksaan neurologis berkala",
            "EKG monitoring (emergensi)",
            "Fungsi ginjal tiap 12-24 jam",
        ],
        "target_terapi": {
            "Emergensi Jam 1": "Turunkan MAP ≤25% dari baseline",
            "Emergensi Jam 6": "TD ≤160/110 mmHg",
            "Emergensi Jam 24": "TD <140/90 mmHg",
            "Urgensi 24-48 jam": "TD <160/100 mmHg",
        },
        "kontraindikasi_penting": [
            "NIFEDIPINE SUBLINGUAL: Dilarang — turun terlalu cepat → stroke / infark",
            "Penurunan TD terlalu agresif pada ensefalopati: risiko infark watershed",
        ],
        "kriteria_rujuk_eskalasi": [
            "Diseksi aorta: rujuk bedah vaskular segera, target SBP 100-120 mmHg",
            "Ensefalopati refrakter: neurologi dan ICU tersier",
        ],
        "skor_risiko": {},
    },

    # ─────────────────────────────────────────────────────────────────────
    # SEPSIS & SYOK SEPTIK
    # ─────────────────────────────────────────────────────────────────────
    {
        "icd10_codes": ["A41.9", "A41.0", "R57.9"],
        "nama_ppk": "Tata Laksana Sepsis dan Syok Septik",
        "versi_referensi": "Surviving Sepsis Campaign (SSC) Guidelines 2021 / Bundle 1 Jam",
        "tujuan_terapi": "Early goal-directed therapy: resusitasi agresif, source control, "
                         "antibiotik tepat waktu.",
        "kriteria_masuk_icu": [
            "Semua syok septik wajib ICU",
            "Sepsis dengan disfungsi organ (Sepsis-3: SOFA ≥2)",
            "Kebutuhan vasopressor",
            "Butuh ventilasi mekanik",
        ],
        "pemeriksaan_awal": [
            "Kultur darah 2 set (aerob+anaerob) SEBELUM antibiotik",
            "Kultur urin, sputum, wound sesuai sumber",
            "Laktat serum (bila ≥2: resusitasi agresif; ≥4: syok)",
            "Darah Lengkap, Kimia Klinik, LFT, Koagulasi (PT/INR, aPTT, Fibrinogen, D-Dimer)",
            "Prokalsitonin (PCT)",
            "AGD",
            "EKG, Foto Toraks, USG Bedside (FAST)",
            "Skor SOFA dan qSOFA",
        ],
        "tata_laksana_utama": [
            {
                "urutan": 1, "langkah": "BUNDLE 1 JAM SSC (Selesai dalam 60 menit)",
                "detail": "1) Ukur laktat. 2) Ambil kultur darah. "
                          "3) Berikan antibiotik spektrum luas. "
                          "4) Resusitasi cairan: kristaloid 30 mL/kgBB IV cepat bila laktat ≥4 atau hipotensi. "
                          "5) Vasopressor bila MAP <65 setelah resusitasi.",
            },
            {
                "urutan": 2, "langkah": "Resusitasi Cairan",
                "detail": "NS 0.9% atau RL 30 mL/kgBB dalam 3 jam. "
                          "Evaluasi fluid responsiveness setelah tiap bolus (PLR test, variasi pulse pressure). "
                          "Hindari overloading: target CVP 8-12, laktat menurun.",
            },
            {
                "urutan": 3, "langkah": "Vasopressor",
                "detail": "Norepinefrin (pilihan pertama): 0.01-3 mcg/kgBB/mnt, target MAP ≥65 mmHg. "
                          "Vasopressin 0.03 IU/mnt (add-on bila norepinefrin >0.25 mcg/kgBB/mnt). "
                          "Dopamin: TIDAK direkomendasikan sebagai pilihan pertama.",
            },
            {
                "urutan": 4, "langkah": "Antibiotik Empiris (dalam 1 jam!)",
                "detail": "Sumber tidak diketahui: Meropenem 1g IV q8h + Vancomycin 15-20 mg/kgBB IV q8-12h. "
                          "Paru: Meropenem + Levofloxacin IV. "
                          "Abdomen: Meropenem + Metronidazol. "
                          "De-eskalasi dalam 48-72 jam setelah hasil kultur.",
            },
            {
                "urutan": 5, "langkah": "Kontrol Glukosa",
                "detail": "Mulai protokol insulin bila GDS >180 mg/dL. Target: 140-180 mg/dL. "
                          "Monitor GDS setiap 1-2 jam awal, setiap 4 jam setelah stabil. "
                          "Hindari hipoglikemia (<80 mg/dL).",
            },
            {
                "urutan": 6, "langkah": "Hidrokortison (bila syok refrakter)",
                "detail": "Hidrokortison IV 200 mg/hari (infus kontinu atau 50 mg q6h) "
                          "bila norepinefrin >0.25 mcg/kgBB/mnt setelah resusitasi adekuat.",
            },
        ],
        "obat_rekomendasi": [
            {"nama": "Meropenem", "dosis": "1 g IV q8h (2 g q8h bila suspek Pseudomonas berat)", "rute": "IV", "catatan": "Sesuaikan dosis GFR"},
            {"nama": "Vancomycin", "dosis": "25-30 mg/kgBB IV loading → 15-20 mg/kgBB q8-12h", "rute": "IV", "catatan": "Pantau AUC/MIC atau trough level; nephrotoxic"},
            {"nama": "Norepinefrin", "dosis": "0.01-3 mcg/kgBB/mnt infus", "rute": "IV via CVC", "catatan": "Vasopressor lini pertama syok septik"},
            {"nama": "Vasopressin", "dosis": "0.03 IU/mnt (dosis tetap)", "rute": "IV", "catatan": "Add-on vasopressor, bukan titrasi"},
            {"nama": "Hidrokortison", "dosis": "200 mg/hari infus kontinu", "rute": "IV", "catatan": "Bila vasopressor refrakter; tapering setelah syok teratasi"},
            {"nama": "Insulin Regular", "dosis": "Protokol sliding scale atau infus 0.01-0.1 IU/kgBB/jam", "rute": "IV", "catatan": "Target GDS 140-180 mg/dL"},
        ],
        "monitoring_wajib": [
            "Laktat serial: tiap 2 jam hingga <2 mmol/L",
            "MAP tiap 15 menit (fase akut)",
            "Input-output cairan ketat (target urin >0.5 mL/kgBB/jam)",
            "GDS tiap 1-2 jam (fase akut), tiap 4 jam (stabil)",
            "SOFA score tiap 24 jam",
            "Kultul ulang bila tidak ada perbaikan 48-72 jam",
        ],
        "target_terapi": {
            "MAP": "≥65 mmHg",
            "Laktat": "<2 mmol/L",
            "Diuresis": ">0.5 mL/kgBB/jam",
            "GDS": "140-180 mg/dL",
            "ScvO2": ">70%",
        },
        "kontraindikasi_penting": [
            "Antibiotik tunggal sempit: tidak adekuat untuk sepsis berat",
            "Starck fluid restriction awal: tidak direkomendasikan pada fase syok",
        ],
        "kriteria_rujuk_eskalasi": [
            "ARDS: protokol ARDSNet ventilasi protektif",
            "AKI berat (KDIGO stadium 3): pertimbangkan CRRT",
            "DIC: koreksi koagulopati, FFP/trombosit sesuai indikasi",
        ],
        "skor_risiko": {
            "SOFA Score": "Sequential Organ Failure Assessment — skor ≥2 = sepsis",
            "qSOFA": "RR≥22, GCS<15, SBP≤100 — skrining cepat di luar ICU",
            "APACHE II": "Prediksi mortalitas ICU",
        },
    },
]


def get_ppk_by_icd10(kode_icd10: str) -> list[dict]:
    """Cari PPK berdasarkan kode ICD-10."""
    return [p for p in PPK_DB if kode_icd10 in p["icd10_codes"]]


def get_all_ppk_names() -> list[str]:
    """Daftar semua nama PPK yang tersedia."""
    return [p["nama_ppk"] for p in PPK_DB]


def get_ppk_by_name(nama: str) -> dict | None:
    """Cari PPK berdasarkan nama (partial match)."""
    for p in PPK_DB:
        if nama.lower() in p["nama_ppk"].lower():
            return p
    return None

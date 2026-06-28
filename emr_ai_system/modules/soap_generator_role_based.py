"""
Role-Based SOAP Generation untuk Dokter dan Perawat.
File: modules/soap_generator_role_based.py
"""

from datetime import datetime
from typing import List, Dict, Optional


class SOAPGeneratorDokter:
    """SOAP Generator untuk Dokter - Analytical format"""
    
    @staticmethod
    def generate_assessment(diagnoses: List[Dict]) -> str:
        if not diagnoses:
            return ""
        
        lines = ["## ASSESSMENT (A) — CLINICAL DIAGNOSIS & ANALYSIS", ""]
        
        primary_dx = next(
            (d for d in diagnoses if d.get("tipe") == "Diagnosis Utama"),
            diagnoses[0] if diagnoses else None
        )
        
        if primary_dx:
            lines.append("### 🎯 PRIMARY DIAGNOSIS")
            lines.append(f"**Code:** `{primary_dx['kode_icd10']}`")
            lines.append(f"**Disease:** {primary_dx['nama_penyakit']}")
            lines.append(f"**Status:** ACUTE | HIGH PRIORITY ⚠️")
            lines.append("")
        
        secondary = [d for d in diagnoses if d.get("tipe") != "Diagnosis Utama"]
        if secondary:
            lines.append("### 📋 COMORBIDITIES")
            for dx in secondary:
                lines.append(f"- `{dx['kode_icd10']}` — {dx['nama_penyakit']}")
            lines.append("")
        
        lines.append("### 📊 CLINICAL ASSESSMENT")
        lines.append("**Severity Level:** 🔴 CRITICAL / 🟡 HIGH / 🟢 MODERATE")
        lines.append("**Risk Stratification:** [TIMI/GRACE Score]")
        lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_objective(vital_signs: Dict = None, clinical_findings: str = "") -> str:
        lines = ["## OBJECTIVE (O) — CLINICAL FINDINGS & INTERPRETATION", ""]
        
        if vital_signs:
            lines.append("### 💓 VITAL SIGNS")
            lines.append(f"- **HR:** {vital_signs.get('hr', '—')} bpm")
            lines.append(f"- **BP:** {vital_signs.get('sbp', '—')}/{vital_signs.get('dbp', '—')} mmHg")
            lines.append(f"- **RR:** {vital_signs.get('rr', '—')} x/menit")
            lines.append(f"- **SpO2:** {vital_signs.get('spo2', '—')}%")
            lines.append("")
        
        if clinical_findings:
            lines.append("### 🏥 CLINICAL FINDINGS")
            lines.append(clinical_findings)
            lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_plan(diagnoses: List[Dict], ppk_recommendations: Dict = None) -> str:
        lines = ["## PLAN (P) — MANAGEMENT & THERAPEUTIC PLAN", ""]
        
        lines.append("### 🎯 THERAPEUTIC GOALS")
        lines.append("- Stabilize hemodynamics")
        lines.append("- Implement reperfusion strategy")
        lines.append("- Prevent complications")
        lines.append("")
        
        lines.append("### 💊 IMMEDIATE INTERVENTIONS")
        lines.append("1. **Pharmacological:** [Medications as per PPK]")
        lines.append("2. **Procedural:** [Procedures if needed]")
        lines.append("3. **Monitoring:** Continuous cardiac monitoring")
        lines.append("")
        
        return "\n".join(lines)


class SOAPGeneratorPerawat:
    """SOAP Generator untuk Perawat - Care-focused format"""
    
    @staticmethod
    def generate_assessment(diagnoses: List[Dict]) -> str:
        if not diagnoses:
            return ""
        
        lines = ["## ASSESSMENT (A) — DIAGNOSES & NURSING CONCERNS", ""]
        
        for dx in diagnoses:
            status_icon = "🔴" if dx.get("tipe") == "Diagnosis Utama" else "◦"
            lines.append(f"{status_icon} **{dx['tipe']}:** `{dx['kode_icd10']}` — {dx['nama_penyakit']}")
        
        lines.append("")
        return "\n".join(lines)
    
    @staticmethod
    def generate_objective(vital_signs: Dict = None, monitoring_data: str = "") -> str:
        lines = ["## OBJECTIVE (O) — VITAL SIGNS & MONITORING DATA", ""]
        
        if vital_signs:
            lines.append("**Vital Signs:**")
            lines.append(f"- HR: {vital_signs.get('hr', '—')} bpm")
            lines.append(f"- BP: {vital_signs.get('sbp', '—')}/{vital_signs.get('dbp', '—')} mmHg")
            lines.append(f"- RR: {vital_signs.get('rr', '—')} x/menit")
            lines.append(f"- SpO2: {vital_signs.get('spo2', '—')}%")
            lines.append("")
        
        if monitoring_data:
            lines.append("**Monitoring:**")
            lines.append(monitoring_data)
            lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_plan(nursing_interventions: List[str] = None) -> str:
        lines = ["## PLAN (P) — NURSING INTERVENTIONS & MONITORING", ""]
        
        if nursing_interventions:
            lines.append("**Nursing Interventions:**")
            for i, intervention in enumerate(nursing_interventions, 1):
                lines.append(f"{i}. {intervention}")
        else:
            lines.append("**Standard Nursing Care:**")
            lines.append("1. Monitor vital signs every 15-30 minutes")
            lines.append("2. Maintain IV access & administer medications")
            lines.append("3. Monitor intake/output")
            lines.append("4. Patient education")
        
        lines.append("")
        return "\n".join(lines)


def generate_soap_by_role(
    role: str,
    diagnoses: List[Dict],
    vital_signs: Dict = None,
    clinical_findings: str = "",
    ppk_recommendations: Dict = None,
    nursing_interventions: List[str] = None,
) -> Dict[str, str]:
    """Generate SOAP based on user role"""
    
    if role == "Dokter":
        generator = SOAPGeneratorDokter()
    else:
        generator = SOAPGeneratorPerawat()
    
    subjective = """## SUBJECTIVE (S)
[Patient complaints & history]
"""
    
    objective = generator.generate_objective(vital_signs, clinical_findings)
    assessment = generator.generate_assessment(diagnoses)
    plan = generator.generate_plan(
        diagnoses,
        ppk_recommendations if role == "Dokter" else None
    )
    
    return {
        "S": subjective,
        "O": objective,
        "A": assessment,
        "P": plan,
    }
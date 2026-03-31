"""Application-wide constants — CEZIH document types, LOINC codes, enums."""

from __future__ import annotations

# ============================================================
# Medical Record Types (tip)
# ============================================================
# All allowed values for MedicalRecord.tip field.
# Types prefixed with CEZIH_ comment are mandatory for CEZIH submission
# per Zakon o podacima i informacijama u zdravstvu (NN 14/2019), čl. 23/28.

RECORD_TIP_ALLOWED: set[str] = {
    # --- CEZIH mandatory document types (čl. 23, NN 14/2019) ---
    "ambulantno_izvjesce",   # Izvješće nakon ambulantnog pregleda
    "specijalisticki_nalaz", # Nalaz iz specijalističke ordinacije
    "otpusno_pismo",         # Otpusno pismo

    # --- Internal / general types ---
    "nalaz",
    "dijagnoza",
    "misljenje",
    "preporuka",
    "epikriza",
    "anamneza",
}

# Types that MUST be sent to CEZIH when created
CEZIH_MANDATORY_TYPES: set[str] = {
    "ambulantno_izvjesce",
    "specijalisticki_nalaz",
    "otpusno_pismo",
}

# Types eligible for CEZIH submission (mandatory + optional sendable)
CEZIH_ELIGIBLE_TYPES: set[str] = {
    "ambulantno_izvjesce",
    "specijalisticki_nalaz",
    "otpusno_pismo",
    "nalaz",
    "epikriza",
}


# ============================================================
# CEZIH Document Type → LOINC Code Mapping
# ============================================================
# Used when building FHIRDocumentReference for ITI-65 submission.
# System: http://fhir.cezih.hr/specifikacije/vrste-dokumenata
# Codes follow LOINC standard (https://loinc.org).

CEZIH_DOCUMENT_TYPE_MAP: dict[str, dict[str, str]] = {
    "ambulantno_izvjesce": {
        "code": "34764-1",
        "display": "General medicine Consult note",
        "display_hr": "Ambulantno izvješće",
    },
    "specijalisticki_nalaz": {
        "code": "11488-4",
        "display": "Consultation note",
        "display_hr": "Specijalistički nalaz",
    },
    "otpusno_pismo": {
        "code": "18842-5",
        "display": "Discharge summary",
        "display_hr": "Otpusno pismo",
    },
    "nalaz": {
        "code": "47045-0",
        "display": "Study report Document",
        "display_hr": "Nalaz",
    },
    "epikriza": {
        "code": "28570-0",
        "display": "Procedure note",
        "display_hr": "Epikriza",
    },
    # Fallback for types not directly mapped
    "dijagnoza": {
        "code": "29308-4",
        "display": "Diagnosis",
        "display_hr": "Dijagnoza",
    },
    "misljenje": {
        "code": "51848-0",
        "display": "Evaluation note",
        "display_hr": "Mišljenje",
    },
    "preporuka": {
        "code": "18776-5",
        "display": "Plan of care note",
        "display_hr": "Preporuka",
    },
    "anamneza": {
        "code": "10164-2",
        "display": "History of Present illness Narrative",
        "display_hr": "Anamneza",
    },
}

# FHIR system URI for CEZIH document types
CEZIH_DOCUMENT_TYPE_SYSTEM = "http://fhir.cezih.hr/specifikacije/vrste-dokumenata"


def get_cezih_document_coding(tip: str) -> dict[str, str]:
    """Return CEZIH FHIR coding for a given record tip.

    Returns dict with keys: system, code, display.
    Falls back to generic 'nalaz' if tip is not mapped.
    """
    mapping = CEZIH_DOCUMENT_TYPE_MAP.get(tip, CEZIH_DOCUMENT_TYPE_MAP["nalaz"])
    return {
        "system": CEZIH_DOCUMENT_TYPE_SYSTEM,
        "code": mapping["code"],
        "display": mapping["display_hr"],
    }

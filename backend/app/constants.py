"""Application-wide constants — CEZIH document types, enums."""

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

# Types that MUST be sent to CEZIH when created.
# Codes 011-013 are specifically for private healthcare institutions (privatnici).
CEZIH_MANDATORY_TYPES: set[str] = {
    "specijalisticki_nalaz",
    "nalaz",
}

# Types eligible for CEZIH submission (maps to HRTipDokumenta codes 011-013).
CEZIH_ELIGIBLE_TYPES: set[str] = {
    "ambulantno_izvjesce",
    "specijalisticki_nalaz",
    "otpusno_pismo",
    "nalaz",
    "epikriza",
}


# ============================================================
# CEZIH Document Type → HRTipDokumenta Code Mapping
# ============================================================
# Used when building FHIR DocumentReference for ITI-65 submission.
# Official CodeSystem: HRTipDokumenta (cezih.hr.cezih-osnova FHIR package v0.2.9)
# System URI: http://fhir.cezih.hr/specifikacije/CodeSystem/document-type
#
# Codes 011-013 are for private healthcare institutions (privatnici):
#   011 = Izvješće nakon pregleda u ambulanti privatne zdravstvene ustanove
#   012 = Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove
#   013 = Otpusno pismo iz privatne zdravstvene ustanove
#
# Codes 001-010 are for public/contracted institutions (ugovorni partneri HZZO):
#   001 = Onkološki relevantni podaci
#   002 = SGP Nalaz
#   003 = PD-L1 dokument
#   004 = Opći nalaz na internu uputnicu
#   005 = Nalaz nakon hitnog prijema u bolnicu
#   006 = Otpusno pismo nakon hitnog prijema u bolnicu
#   007 = Izvješće nakon intervencije hitne pomoći
#   008 = Crvena uputnica
#   009 = Nestrukturirani SGP nalaz
#   010 = Administrirana onkološka terapija

CEZIH_DOCUMENT_TYPE_MAP: dict[str, dict[str, str]] = {
    "ambulantno_izvjesce": {
        "code": "011",
        "display": "Izvješće nakon pregleda u ambulanti privatne zdravstvene ustanove",
    },
    "specijalisticki_nalaz": {
        "code": "012",
        "display": "Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove",
    },
    "otpusno_pismo": {
        "code": "013",
        "display": "Otpusno pismo iz privatne zdravstvene ustanove",
    },
    # Generic "nalaz" falls back to specijalisticki (012) — most common for privatnici
    "nalaz": {
        "code": "012",
        "display": "Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove",
    },
    # Epikriza is a summary — closest match is ambulantno izvješće (011)
    "epikriza": {
        "code": "011",
        "display": "Izvješće nakon pregleda u ambulanti privatne zdravstvene ustanove",
    },
}

# FHIR system URI for CEZIH document types (HRTipDokumenta CodeSystem)
CEZIH_DOCUMENT_TYPE_SYSTEM = "http://fhir.cezih.hr/specifikacije/CodeSystem/document-type"


def get_cezih_document_coding(tip: str) -> dict[str, str]:
    """Return CEZIH FHIR coding for a given record tip.

    Returns dict with keys: system, code, display.
    Falls back to generic 'nalaz' if tip is not mapped.
    """
    mapping = CEZIH_DOCUMENT_TYPE_MAP.get(tip, CEZIH_DOCUMENT_TYPE_MAP["nalaz"])
    return {
        "system": CEZIH_DOCUMENT_TYPE_SYSTEM,
        "code": mapping["code"],
        "display": mapping["display"],
    }

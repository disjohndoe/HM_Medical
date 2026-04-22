"""CEZIH identifier system constants and patient-identifier resolution."""

from __future__ import annotations

from app.services.cezih.exceptions import CezihError

# CEZIH identifier systems
SYS_MBO = "http://fhir.cezih.hr/specifikacije/identifikatori/MBO"
SYS_OIB = "http://fhir.cezih.hr/specifikacije/identifikatori/oib"
SYS_PUTOVNICA = "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica"
SYS_EUROPSKA = "http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica"
SYS_JEDINSTVENI = "http://fhir.cezih.hr/specifikacije/identifikatori/jedinstveni-identifikator-pacijenta"

_IDENTIFIER_SYSTEM_MAP = {
    "mbo": SYS_MBO,
    "putovnica": SYS_PUTOVNICA,
    "ehic": SYS_EUROPSKA,
}

_IDENTIFIER_LABEL_MAP = {
    SYS_MBO: "MBO",
    SYS_PUTOVNICA: "Putovnica",
    SYS_EUROPSKA: "EHIC",
    SYS_JEDINSTVENI: "CEZIH ID",
    SYS_OIB: "OIB",
}


def _require_identifier_system(patient_data: dict) -> str:
    """Extract identifier_system from patient_data. Raises if missing.

    Prevents silent fallback to MBO for foreign patients. Callers must populate
    patient_data['identifier_system'] from resolve_cezih_identifier().
    """
    system = patient_data.get("identifier_system")
    if not system:
        raise CezihError(
            "patient_data missing 'identifier_system' — caller must pass resolve_cezih_identifier() output"
        )
    return system


def _require_identifier_value(patient_data: dict) -> str:
    """Extract identifier_value from patient_data. Raises if missing.

    Falls back to patient_data['mbo'] only if it was already populated as a
    legacy alias (dispatcher writes the resolved identifier into both keys).
    """
    value = patient_data.get("identifier_value") or patient_data.get("mbo")
    if not value:
        raise CezihError("patient_data missing 'identifier_value' — caller must pass resolve_cezih_identifier() output")
    return value


def resolve_cezih_identifier(patient) -> tuple[str, str]:
    """Return (system_uri, value) for CEZIH FHIR identifier queries.

    Priority: MBO (Croatian insured) > jedinstveni-id (PMIR-registered foreigner)
    > EHIC > putovnica. Raises CezihError if the patient carries none of these.
    """
    if patient.mbo:
        return (SYS_MBO, patient.mbo)
    if getattr(patient, "cezih_patient_id", None):
        return (SYS_JEDINSTVENI, patient.cezih_patient_id)
    if getattr(patient, "ehic_broj", None):
        return (SYS_EUROPSKA, patient.ehic_broj)
    if getattr(patient, "broj_putovnice", None):
        return (SYS_PUTOVNICA, patient.broj_putovnice)
    raise CezihError("Pacijent nema CEZIH identifikator (MBO, CEZIH ID, EHIC ili putovnica)")


__all__ = [
    "SYS_MBO",
    "SYS_OIB",
    "SYS_PUTOVNICA",
    "SYS_EUROPSKA",
    "SYS_JEDINSTVENI",
    "_IDENTIFIER_SYSTEM_MAP",
    "_IDENTIFIER_LABEL_MAP",
    "_require_identifier_system",
    "_require_identifier_value",
    "resolve_cezih_identifier",
]

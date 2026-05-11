"""CEZIH identifier system constants and patient-identifier resolution.

Identifier system URIs (`ID_MBO`, `ID_OIB`, `ID_EHIC`, `ID_PUTOVNICA`,
`ID_JEDINSTVENI`) are owned by `app.services.cezih.builders.common`.
This module exposes resolution helpers + the friendly-label/short-key
maps the API + dispatcher layers use, and re-exports the canonical
URI names for callers that import via the `service.py` shim.
"""

from __future__ import annotations

from app.services.cezih.builders.common import (
    ID_EHIC,
    ID_JEDINSTVENI,
    ID_MBO,
    ID_OIB,
    ID_PUTOVNICA,
)
from app.services.cezih.exceptions import CezihError

_IDENTIFIER_SYSTEM_MAP = {
    "mbo": ID_MBO,
    "oib": ID_OIB,
    "putovnica": ID_PUTOVNICA,
    "ehic": ID_EHIC,
}

_IDENTIFIER_LABEL_MAP = {
    ID_MBO: "MBO",
    ID_PUTOVNICA: "Putovnica",
    ID_EHIC: "EHIC",
    ID_JEDINSTVENI: "CEZIH ID",
    ID_OIB: "OIB",
}


def _require_identifier_system(patient_data: dict) -> str:
    """Extract identifier_system from patient_data. Raises if missing.

    Prevents silent fallback to MBO for foreign patients. Callers must populate
    patient_data['identifier_system'] from resolve_cezih_identifier().
    """
    system = patient_data.get("identifier_system")
    if not system:
        raise CezihError(
            "patient_data missing 'identifier_system' - caller must pass resolve_cezih_identifier() output"
        )
    return system


def _require_identifier_value(patient_data: dict) -> str:
    """Extract identifier_value from patient_data. Raises if missing.

    Falls back to patient_data['mbo'] only if it was already populated as a
    legacy alias (dispatcher writes the resolved identifier into both keys).
    """
    value = patient_data.get("identifier_value") or patient_data.get("mbo")
    if not value:
        raise CezihError("patient_data missing 'identifier_value' - caller must pass resolve_cezih_identifier() output")
    return value


def resolve_cezih_identifier(patient) -> tuple[str, str]:
    """Return (system_uri, value) for CEZIH FHIR identifier queries.

    Priority: MBO (Croatian insured) > jedinstveni-id (PMIR-registered foreigner)
    > OIB (Croatian resident without MBO on hand) > EHIC > putovnica.
    Raises CezihError if the patient carries none of these.

    JID strict-shape guard: HZZO Provjera Spremnosti rejected 2026-05-11 because
    a CUID-shaped value was being sent as jedinstveni-identifikator-pacijenta.
    Reject any non-numeric cezih_patient_id here before it reaches CEZIH; fall
    through to the next identifier (or final raise) so a stale-CUID row does
    not silently fail every action.
    """
    if patient.mbo:
        return (ID_MBO, patient.mbo)
    jid = getattr(patient, "cezih_patient_id", None)
    if jid:
        if jid.isdigit():
            return (ID_JEDINSTVENI, jid)
        # Non-numeric JID = stale local value, never came from CEZIH PMIR.
        # Skip it and try other identifiers; if none, the final raise will
        # tell the doctor to re-register the foreigner via TC11.
    if getattr(patient, "oib", None):
        return (ID_OIB, patient.oib)
    if getattr(patient, "ehic_broj", None):
        return (ID_EHIC, patient.ehic_broj)
    if getattr(patient, "broj_putovnice", None):
        return (ID_PUTOVNICA, patient.broj_putovnice)
    if jid and not jid.isdigit():
        raise CezihError(
            "Pacijent ima nevažeći CEZIH identifikator (nije numerički). "
            "Molim Vas ponovno registrirajte pacijenta u CEZIH (Stranci → Registriraj)."
        )
    raise CezihError("Pacijent nema CEZIH identifikator (MBO, CEZIH ID, OIB, EHIC ili putovnica)")


__all__ = [
    "ID_MBO",
    "ID_OIB",
    "ID_PUTOVNICA",
    "ID_EHIC",
    "ID_JEDINSTVENI",
    "_IDENTIFIER_SYSTEM_MAP",
    "_IDENTIFIER_LABEL_MAP",
    "_require_identifier_system",
    "_require_identifier_value",
    "resolve_cezih_identifier",
]

"""Shared CEZIH FHIR constants and reference helpers."""
# ruff: noqa: N815 — FHIR spec requires camelCase field names
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

MESSAGE_TYPE_SYSTEM = "http://ent.hr/fhir/CodeSystem/ehe-message-types"

# --- Identifier systems ---
ID_MBO = "http://fhir.cezih.hr/specifikacije/identifikatori/MBO"
ID_JEDINSTVENI = "http://fhir.cezih.hr/specifikacije/identifikatori/jedinstveni-identifikator-pacijenta"
ID_EHIC = "http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica"
ID_PUTOVNICA = "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica"
ID_ORG = "http://fhir.cezih.hr/specifikacije/identifikatori/HZZO-sifra-zdravstvene-organizacije"
ID_PRACTITIONER = "http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika"
ID_CASE_GLOBAL = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja"
ID_CASE_REF = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja"
ID_CASE_LOCAL = "http://fhir.cezih.hr/specifikacije/identifikatori/lokalni-identifikator-slucaja"
ID_ENCOUNTER = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-posjete"

# --- Code systems ---
CS_ICD10_HR = "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"
CS_ANNOTATION_TYPE = "http://fhir.cezih.hr/specifikacije/CodeSystem/annotation-type"
CS_CONDITION_VER_STATUS = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CS_CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"

EXT_ANNOTATION_TYPE = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-annotation-type"
EXT_TROSKOVI_SUDJELovanje = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-troskovi-sudjelovanje"
CS_SUDJELOVANJE_U_TROSKOVIMA = "http://fhir.cezih.hr/specifikacije/CodeSystem/sudjelovanje-u-troskovima"
CS_SIFRA_OSLOBODJENJA = "http://fhir.cezih.hr/specifikacije/CodeSystem/sifra-oslobodjenja-od-sudjelovanja-u-troskovima"


def patient_ref(value: str, system: str = ID_MBO) -> dict[str, Any]:
    """Build a FHIR identifier-based Patient reference.

    Defaults to MBO for Croatian insured patients. For PMIR-registered
    foreigners pass system=ID_JEDINSTVENI (or ID_EHIC / ID_PUTOVNICA)
    with the matching identifier value.
    """
    return {"type": "Patient", "identifier": {"system": system, "value": value}}


def org_ref(org_code: str) -> dict[str, Any]:
    return {"type": "Organization", "identifier": {"system": ID_ORG, "value": org_code}}


def practitioner_ref(hzjz_id: str) -> dict[str, Any]:
    return {"type": "Practitioner", "identifier": {"system": ID_PRACTITIONER, "value": hzjz_id}}


_TZ_ZAGREB = ZoneInfo("Europe/Zagreb")


def _now_iso() -> str:
    return datetime.now(_TZ_ZAGREB).isoformat()


__all__ = [
    "MESSAGE_TYPE_SYSTEM",
    "ID_MBO", "ID_JEDINSTVENI", "ID_EHIC", "ID_PUTOVNICA",
    "ID_ORG", "ID_PRACTITIONER",
    "ID_CASE_GLOBAL", "ID_CASE_REF", "ID_CASE_LOCAL", "ID_ENCOUNTER",
    "CS_ICD10_HR", "CS_ANNOTATION_TYPE",
    "CS_CONDITION_VER_STATUS", "CS_CONDITION_CLINICAL",
    "EXT_ANNOTATION_TYPE", "EXT_TROSKOVI_SUDJELovanje",
    "CS_SUDJELOVANJE_U_TROSKOVIMA", "CS_SIFRA_OSLOBODJENJA",
    "patient_ref", "org_ref", "practitioner_ref",
    "_now_iso",
    "_TZ_ZAGREB",
]

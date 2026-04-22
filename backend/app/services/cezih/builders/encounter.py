"""FHIR Encounter resource builders (CEZIH Visit messages 1.1–1.5).

Contains encounter builders and VISIT_ACTION_MAP for visit lifecycle operations.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.cezih.builders.common import (
    CS_SIFRA_OSLOBODJENJA,
    CS_SUDJELOVANJE_U_TROSKOVIMA,
    ID_CASE_REF,
    ID_ENCOUNTER,
    ID_MBO,
    EXT_TROSKOVI_SUDJELovanje,
    _now_iso,
    org_ref,
    patient_ref,
    practitioner_ref,
)

logger = logging.getLogger(__name__)

# CEZIH Croatian CodeSystems (NOT standard HL7 v3-ActCode)
CS_NACIN_PRIJEMA = "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"
CS_VRSTA_POSJETE = "http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete"
CS_TIP_POSJETE = "http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete"

NACIN_PRIJEMA_MAP = {
    "1": "Hitni prijem",
    "2": "Uputnica PZZ",
    "3": "Premještaj iz druge ustanove",
    "4": "Nastavno liječenje",
    "5": "Premještaj unutar ustanove",
    "6": "Ostalo",
    "7": "Poziv na raniji termin",
    "8": "Telemedicina",
    "9": "Interna uputnica",
    "10": "Program+",
}

VRSTA_POSJETE_MAP = {
    "1": "Pacijent prisutan",
    "2": "Pacijent udaljeno prisutan",
    "3": "Pacijent nije prisutan",
}

TIP_POSJETE_MAP = {
    "1": "Posjeta LOM",
    "2": "Posjeta SKZZ",
    "3": "Hospitalizacija",
}

# FHIR Profile URLs for Encounter messages (meta.profile)
_PROFILE_BASE = "http://fhir.cezih.hr/specifikacije/StructureDefinition"
PROFILE_ENCOUNTER = f"{_PROFILE_BASE}/hr-encounter"
PROFILE_ENCOUNTER_MSG_HEADER = f"{_PROFILE_BASE}/hr-encounter-management-message-header"

ENCOUNTER_EVENT_PROFILE_MAP = {
    "1.1": f"{_PROFILE_BASE}/hr-create-encounter-message",
    "1.2": f"{_PROFILE_BASE}/hr-update-encounter-message",
    "1.3": f"{_PROFILE_BASE}/hr-close-encounter-message",
    "1.4": f"{_PROFILE_BASE}/hr-cancel-encounter-message",
    "1.5": f"{_PROFILE_BASE}/hr-reopen-encounter-message",
}

VISIT_ACTION_MAP: dict[str, dict[str, str]] = {
    "close": {"code": "1.3", "status": "finished"},
    "storno": {"code": "1.4", "status": "entered-in-error"},
    "reopen": {"code": "1.5", "status": "in-progress"},
}


def build_encounter_create(
    *,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    practitioner_id: str = "",
    org_code: str = "",
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit creation (event code 1.1).

    Uses CEZIH Croatian CodeSystems:
      - Encounter.class: nacin-prijema (method of admission)
    """
    # Match official CEZIH example — field order matches spec
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "extension": [
            {
                "extension": [
                    {"url": "oznaka", "valueCoding": {"system": CS_SUDJELOVANJE_U_TROSKOVIMA, "code": "N"}},
                    {"url": "sifra-oslobodjenja", "valueCoding": {"system": CS_SIFRA_OSLOBODJENJA, "code": "55"}},
                ],
                "url": EXT_TROSKOVI_SUDJELovanje,
            },
        ],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "subject": patient_ref(patient_mbo, identifier_system),
        "type": [],
    }
    if vrsta_posjete:
        encounter["type"].append(
            {
                "coding": [{"system": CS_VRSTA_POSJETE, "code": vrsta_posjete}],
            }
        )
    if tip_posjete:
        encounter["type"].append(
            {
                "coding": [{"system": CS_TIP_POSJETE, "code": tip_posjete}],
            }
        )
    if not encounter["type"]:
        del encounter["type"]
    if practitioner_id:
        encounter["participant"] = [
            {
                "individual": practitioner_ref(practitioner_id),
            }
        ]
    encounter["period"] = {"start": _now_iso()}
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if reason:
        encounter["reasonCode"] = [{"text": reason}]
    return encounter


def build_encounter_update(
    *,
    encounter_id: str,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    practitioner_id: str = "",
    additional_practitioner_id: str | None = None,
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit update (event code 1.2).

    CEZIH example includes: extension, identifier, class, type, subject, participant,
    period, diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "extension": [
            {
                "extension": [
                    {"url": "oznaka", "valueCoding": {"system": CS_SUDJELOVANJE_U_TROSKOVIMA, "code": "N"}},
                    {"url": "sifra-oslobodjenja", "valueCoding": {"system": CS_SIFRA_OSLOBODJENJA, "code": "55"}},
                ],
                "url": EXT_TROSKOVI_SUDJELovanje,
            },
        ],
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "type": [],
        "subject": patient_ref(patient_mbo, identifier_system),
        "period": {"start": period_start if period_start else _now_iso()},
    }
    if vrsta_posjete:
        encounter["type"].append(
            {
                "coding": [{"system": CS_VRSTA_POSJETE, "code": vrsta_posjete}],
            }
        )
    if tip_posjete:
        encounter["type"].append(
            {
                "coding": [{"system": CS_TIP_POSJETE, "code": tip_posjete}],
            }
        )
    if not encounter["type"]:
        del encounter["type"]
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if practitioner_id:
        participants = [{"individual": practitioner_ref(practitioner_id)}]
        if additional_practitioner_id and additional_practitioner_id != practitioner_id:
            participants.append({"individual": practitioner_ref(additional_practitioner_id)})
        encounter["participant"] = participants
    if reason:
        encounter["reasonCode"] = [{"text": reason}]
    if diagnosis_case_id:
        encounter["diagnosis"] = [
            {
                "condition": {
                    "type": "Condition",
                    "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
                },
            }
        ]
    return encounter


def build_encounter_close(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    practitioner_id: str = "",
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit close (event code 1.3).

    CEZIH example includes: identifier, status, class, period (start+end),
    diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    period: dict[str, str] = {"start": period_start or _now_iso(), "end": _now_iso()}

    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "finished",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "period": period,
        "serviceProvider": org_ref(org_code) if org_code else {},
    }
    if diagnosis_case_id:
        encounter["diagnosis"] = [
            {
                "condition": {
                    "type": "Condition",
                    "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
                },
            }
        ]
    if not org_code:
        encounter.pop("serviceProvider", None)
    return encounter


def build_encounter_cancel(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    reason: str | None = None,
    practitioner_id: str = "",
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit cancellation/storno (event code 1.4).

    CEZIH example includes: identifier, status, class, period (start+end),
    diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "entered-in-error",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
    }
    period: dict[str, str] = {"start": period_start or _now_iso(), "end": _now_iso()}
    encounter["period"] = period
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if diagnosis_case_id:
        encounter["diagnosis"] = [
            {
                "condition": {
                    "type": "Condition",
                    "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
                },
            }
        ]
    return encounter


def build_encounter_reopen(
    *,
    encounter_id: str,
    nacin_prijema: str = "6",
    org_code: str = "",
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit reopen (event code 1.5).

    Per CEZIH official example: identifier, status, class, serviceProvider only.
    No subject, participant, period, or id fields.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
    }
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    return encounter


__all__ = [
    # CodeSystems
    "CS_NACIN_PRIJEMA",
    "CS_VRSTA_POSJETE",
    "CS_TIP_POSJETE",
    # Profiles
    "PROFILE_ENCOUNTER",
    "PROFILE_ENCOUNTER_MSG_HEADER",
    # Maps
    "NACIN_PRIJEMA_MAP",
    "VRSTA_POSJETE_MAP",
    "TIP_POSJETE_MAP",
    "ENCOUNTER_EVENT_PROFILE_MAP",
    "VISIT_ACTION_MAP",
    # Builders
    "build_encounter_create",
    "build_encounter_update",
    "build_encounter_close",
    "build_encounter_cancel",
    "build_encounter_reopen",
]

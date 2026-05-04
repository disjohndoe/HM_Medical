"""Inner FHIR Document Bundle builder for ITI-65 clinical documents (privatnici 011/012/013).

Produces a FHIR Bundle.type=document conforming to:
- HRDocument profile (signature 1..1, identifier=urn:oid, type=document)
- One of three Composition profiles: 011 izvjesce-nakon-pregleda,
  012 nalaz-iz-specijalisticke-ordinacije, 013 otpusno-pismo (all share the
  same author/attester/section structure)

The inner bundle is base64-embedded into the outer ITI-65 transaction Binary
(application/fhir+json), referenced by DocumentReference.content.attachment.

Per HRDocument DOC-4: docs 011/012/013 must be signed by attester:professional
Practitioner (the "odgovorna osoba"). signature.who.reference is a literal
urn:uuid: pointer to that Practitioner's bundle entry (not an identifier ref).

Sections that are emitted:
- djelatnost (1..1) -> HealthcareService
- medicinska-informacija (1..1) with entries:
    - anamneza (1..1) -> Observation
    - slucaj (1..N) -> Condition (dokumentirani-slucaj)
    - ishodPregleda (1..1) -> Observation

Sections deliberately skipped from MVP (max=N, optional):
- prilozeni-dokumenti (PDF attachments) - separate feature
- postupci, preporuceniPostupci - require ValueSet bindings we don't have yet
"""

# ruff: noqa: N815 - FHIR spec uses camelCase

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.services.cezih.builders.common import (
    ID_CASE_GLOBAL,
    ID_EHIC,
    ID_ENCOUNTER,
    ID_JEDINSTVENI,
    ID_MBO,
    ID_OIB,
    ID_ORG,
    ID_PRACTITIONER,
    ID_PUTOVNICA,
    _now_iso,
)
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)


SYS_DOC_TYPE = "http://fhir.cezih.hr/specifikacije/CodeSystem/document-type"
SYS_DOC_SECTION = "http://fhir.cezih.hr/specifikacije/CodeSystem/document-section"
SYS_OBSERVATIONS = "http://fhir.cezih.hr/specifikacije/CodeSystem/observations"
SYS_DJELATNOSTI_ZZ = "http://fhir.cezih.hr/specifikacije/CodeSystem/djelatnosti-zz"
SYS_NACIN_PRIJEMA = "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"
SYS_DJELATNOSTI_ID = "http://fhir.cezih.hr/specifikacije/identifikatori/ID-djelatnosti"
SYS_ZAVRSETAK_PREGLEDA = "http://fhir.cezih.hr/specifikacije/CodeSystem/sifrarnik-zavrsetaka-pregleda"


# Composition.title is fixed per profile - exact string match required.
_TITLE_BY_TYPE_CODE = {
    "011": "Izvješće nakon pregleda u ambulanti privatne zdravstvene ustanove",
    "012": "Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove",
    "013": "Otpusno pismo iz privatne zdravstvene ustanove",
}


def _patient_identifier_for_inner_bundle(patient_data: dict) -> dict[str, Any]:
    """Build Patient.identifier matching one of hr-pacijent slices.

    Slice is determined by the system URI from the resolved identifier
    (set by dispatcher via resolve_cezih_identifier).
    """
    system = patient_data.get("identifier_system")
    value = patient_data.get("identifier_value") or patient_data.get("mbo")
    if not system or not value:
        raise CezihError(
            "patient_data missing identifier_system/identifier_value - caller must "
            "pass output of resolve_cezih_identifier()"
        )
    if system not in {ID_MBO, ID_JEDINSTVENI, ID_OIB, ID_EHIC, ID_PUTOVNICA}:
        raise CezihError(
            f"Patient identifier system {system!r} not in HR-pacijent slice list "
            "(MBO/jedinstveni/OIB/EHIC/putovnica)"
        )
    return {"system": system, "value": value}


def _build_patient_resource(patient_data: dict) -> dict[str, Any]:
    """Build hr-pacijent Patient resource for inner bundle entry."""
    identifier = _patient_identifier_for_inner_bundle(patient_data)
    given = (patient_data.get("ime") or "").strip()
    family = (patient_data.get("prezime") or "").strip()
    name = {}
    if family:
        name["family"] = family
    if given:
        name["given"] = [given]
    if not name:
        raise CezihError("Patient name (ime/prezime) is required for inner Document Bundle")

    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "identifier": [identifier],
        "name": [name],
    }
    if patient_data.get("spol"):
        gender_map = {"M": "male", "Z": "female", "Ž": "female", "F": "female"}
        spol = patient_data["spol"].upper() if isinstance(patient_data["spol"], str) else ""
        if gender_map.get(spol):
            resource["gender"] = gender_map[spol]
    if patient_data.get("datum_rodjenja"):
        resource["birthDate"] = str(patient_data["datum_rodjenja"])[:10]
    return resource


def _build_practitioner_resource(practitioner_id: str, practitioner_name: str) -> dict[str, Any]:
    """Build hr-practitioner Practitioner resource for inner bundle entry.

    HZJZ broj is the only mandatory identifier slice (1..1).
    """
    if not practitioner_id:
        raise CezihError("HZJZ practitioner_id is required for clinical document signer")
    if not practitioner_name:
        raise CezihError("Practitioner name is required for clinical document author/attester")
    return {
        "resourceType": "Practitioner",
        "identifier": [
            {
                "system": ID_PRACTITIONER,
                "value": practitioner_id,
            }
        ],
        "name": [{"text": practitioner_name}],
    }


def _build_organization_resource(org_code: str, org_name: str) -> dict[str, Any]:
    """Build hr-organizacija Organization resource for inner bundle entry."""
    if not org_code:
        raise CezihError("HZZO sifra ustanove (org_code) is required for clinical document author/attester")
    return {
        "resourceType": "Organization",
        "identifier": [
            {
                "system": ID_ORG,
                "value": org_code,
            }
        ],
        "active": True,
        "name": org_name or f"Ustanova {org_code}",
    }


def _build_encounter_resource(
    *,
    encounter_id: str,
    patient_full_url: str,
    practitioner_full_url: str,
    organization_full_url: str,
    period_start: str,
    period_end: str,
    case_full_url: str,
) -> dict[str, Any]:
    """Build hr-encounter Encounter resource referenced from Composition.encounter."""
    if not encounter_id:
        raise CezihError("CEZIH encounter_id is required for clinical document encounter reference")
    return {
        "resourceType": "Encounter",
        "identifier": [
            {
                "system": ID_ENCOUNTER,
                "value": encounter_id,
            }
        ],
        "status": "finished",
        "class": {
            "system": SYS_NACIN_PRIJEMA,
            "code": "5",
            "display": "Redovni prijem",
        },
        "subject": {"reference": patient_full_url},
        "participant": [{"individual": {"reference": practitioner_full_url}}],
        "period": {"start": period_start, "end": period_end},
        "diagnosis": [{"condition": {"reference": case_full_url}}],
        "serviceProvider": {"reference": organization_full_url},
    }


def _build_condition_resource(
    *,
    case_id: str,
    patient_full_url: str,
    encounter_full_url: str,
    practitioner_full_url: str,
    icd10_code: str | None,
    icd10_text: str | None,
    onset: str,
) -> dict[str, Any]:
    """Build dokumentirani-slucaj Condition resource for medicinska-informacija/slucaj entry."""
    if not case_id:
        raise CezihError("CEZIH case_id is required for slucaj entry in clinical document")

    resource: dict[str, Any] = {
        "resourceType": "Condition",
        "identifier": [
            {
                "system": ID_CASE_GLOBAL,
                "value": case_id,
            }
        ],
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                }
            ]
        },
        "subject": {"reference": patient_full_url},
        "encounter": {"reference": encounter_full_url},
        "recorder": {"reference": practitioner_full_url},
        "asserter": {"reference": practitioner_full_url},
        "onsetDateTime": onset,
    }
    if icd10_code:
        resource["code"] = {
            "coding": [
                {
                    "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr",
                    "code": icd10_code,
                    **({"display": icd10_text} if icd10_text else {}),
                }
            ],
            **({"text": icd10_text} if icd10_text else {}),
        }
    return resource


def _build_anamneza_observation(
    *,
    sadrzaj: str,
    patient_full_url: str,
    encounter_full_url: str,
    practitioner_full_url: str,
    effective: str,
) -> dict[str, Any]:
    """Build anamneza Observation resource for medicinska-informacija/anamneza entry."""
    if not sadrzaj or not sadrzaj.strip():
        raise CezihError("Anamneza tekst (record sadrzaj) is required for clinical document")
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": SYS_OBSERVATIONS,
                    "code": "15",
                    "display": "Anamneza",
                }
            ]
        },
        "subject": {"reference": patient_full_url},
        "encounter": {"reference": encounter_full_url},
        "effectiveDateTime": effective,
        "performer": [{"reference": practitioner_full_url}],
        "valueString": sadrzaj.strip(),
    }


def _build_ishod_observation(
    *,
    patient_full_url: str,
    encounter_full_url: str,
    practitioner_full_url: str,
    effective: str,
) -> dict[str, Any]:
    """Build ishod-pregleda Observation resource for medicinska-informacija/ishodPregleda entry.

    sifrarnik-zavrsetaka-pregleda has only one code: "1" = "Pregled završen uspješno".
    """
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": SYS_OBSERVATIONS,
                    "code": "24",
                    "display": "Ishod pregleda",
                }
            ]
        },
        "subject": {"reference": patient_full_url},
        "encounter": {"reference": encounter_full_url},
        "effectiveDateTime": effective,
        "performer": [{"reference": practitioner_full_url}],
        "valueCodeableConcept": {
            "coding": [
                {
                    "system": SYS_ZAVRSETAK_PREGLEDA,
                    "code": "1",
                    "display": "Pregled završen uspješno",
                }
            ]
        },
    }


def _build_djelatnost_resource(
    *,
    djelatnost_code: str,
    djelatnost_display: str,
    organization_full_url: str,
) -> dict[str, Any]:
    """Build djelatnost HealthcareService for djelatnost section entry."""
    if not djelatnost_code:
        raise CezihError("Djelatnost code is required for clinical document djelatnost section")
    if not djelatnost_display:
        raise CezihError("Djelatnost display name is required for clinical document djelatnost section")
    return {
        "resourceType": "HealthcareService",
        "identifier": [
            {
                "system": SYS_DJELATNOSTI_ID,
                "value": djelatnost_code,
            }
        ],
        "providedBy": {"reference": organization_full_url},
        "name": djelatnost_display,
    }


def _build_composition(
    *,
    document_type_code: str,
    document_type_display: str,
    patient_full_url: str,
    encounter_full_url: str,
    practitioner_full_url: str,
    organization_full_url: str,
    djelatnost_full_url: str,
    anamneza_full_url: str,
    case_full_url: str,
    ishod_full_url: str,
    composition_date: str,
) -> dict[str, Any]:
    """Build Composition resource matching nalaz/izvjesce/otpusno profile."""
    if document_type_code not in _TITLE_BY_TYPE_CODE:
        raise CezihError(
            f"Unsupported document type code {document_type_code!r} - "
            f"expected one of 011/012/013"
        )
    title = _TITLE_BY_TYPE_CODE[document_type_code]

    return {
        "resourceType": "Composition",
        "status": "final",
        "type": {
            "coding": [
                {
                    "system": SYS_DOC_TYPE,
                    "code": document_type_code,
                    "display": document_type_display,
                }
            ]
        },
        "subject": {"reference": patient_full_url},
        "encounter": {"reference": encounter_full_url},
        "date": composition_date,
        # author: Practitioner first, Organization second (slicing ordered=true)
        "author": [
            {"reference": practitioner_full_url},
            {"reference": organization_full_url},
        ],
        "title": title,
        "attester": [
            {
                "mode": "professional",
                "party": {"reference": practitioner_full_url},
            },
            {
                "mode": "official",
                "party": {"reference": organization_full_url},
            },
        ],
        "section": [
            {
                "title": "Djelatnost",
                "code": {
                    "coding": [
                        {
                            "system": SYS_DOC_SECTION,
                            "code": "12",
                            "display": "Djelatnost",
                        }
                    ]
                },
                "entry": [{"reference": djelatnost_full_url}],
            },
            {
                "title": "Medicinska informacija",
                "code": {
                    "coding": [
                        {
                            "system": SYS_DOC_SECTION,
                            "code": "18",
                            "display": "Medicinska informacija",
                        }
                    ]
                },
                "entry": [
                    {"reference": anamneza_full_url},
                    {"reference": case_full_url},
                    {"reference": ishod_full_url},
                ],
            },
        ],
    }


def build_clinical_document_bundle(
    *,
    patient_data: dict,
    record_data: dict,
    practitioner_id: str,
    practitioner_name: str,
    org_code: str,
    org_name: str,
    encounter_id: str,
    case_id: str,
    document_oid: str,
    document_type_code: str,
    document_type_display: str,
    djelatnost_code: str,
    djelatnost_display: str,
) -> tuple[dict, str]:
    """Build inner FHIR Document Bundle (HRDocument profile) for ITI-65 Binary content.

    Returns (unsigned_bundle, attester_practitioner_full_url).

    The returned bundle has Bundle.type=document, identifier=urn:oid:<doc_oid>,
    timestamp set, but NO signature - caller must sign via sign_document_bundle()
    using the returned practitioner_full_url for signature.who.reference.

    Per HRDocument DOC-4 constraint, signer must be the attester:professional
    Practitioner for doc types 011/012/013. The attester urn:uuid is what we
    return (and what the caller must use as signature.who.reference).
    """
    # Pre-allocate fullUrls so all cross-references resolve within the bundle.
    patient_full_url = f"urn:uuid:{uuid.uuid4()}"
    practitioner_full_url = f"urn:uuid:{uuid.uuid4()}"
    organization_full_url = f"urn:uuid:{uuid.uuid4()}"
    encounter_full_url = f"urn:uuid:{uuid.uuid4()}"
    case_full_url = f"urn:uuid:{uuid.uuid4()}"
    djelatnost_full_url = f"urn:uuid:{uuid.uuid4()}"
    anamneza_full_url = f"urn:uuid:{uuid.uuid4()}"
    ishod_full_url = f"urn:uuid:{uuid.uuid4()}"
    composition_full_url = f"urn:uuid:{uuid.uuid4()}"

    composition_date = _now_iso()
    period_start = record_data.get("created_at") or composition_date
    period_end = composition_date
    onset = record_data.get("created_at") or composition_date

    composition = _build_composition(
        document_type_code=document_type_code,
        document_type_display=document_type_display,
        patient_full_url=patient_full_url,
        encounter_full_url=encounter_full_url,
        practitioner_full_url=practitioner_full_url,
        organization_full_url=organization_full_url,
        djelatnost_full_url=djelatnost_full_url,
        anamneza_full_url=anamneza_full_url,
        case_full_url=case_full_url,
        ishod_full_url=ishod_full_url,
        composition_date=composition_date,
    )

    patient = _build_patient_resource(patient_data)
    practitioner = _build_practitioner_resource(practitioner_id, practitioner_name)
    organization = _build_organization_resource(org_code, org_name)
    djelatnost = _build_djelatnost_resource(
        djelatnost_code=djelatnost_code,
        djelatnost_display=djelatnost_display,
        organization_full_url=organization_full_url,
    )
    condition = _build_condition_resource(
        case_id=case_id,
        patient_full_url=patient_full_url,
        encounter_full_url=encounter_full_url,
        practitioner_full_url=practitioner_full_url,
        icd10_code=record_data.get("dijagnoza_mkb"),
        icd10_text=record_data.get("dijagnoza_tekst"),
        onset=onset,
    )
    encounter = _build_encounter_resource(
        encounter_id=encounter_id,
        patient_full_url=patient_full_url,
        practitioner_full_url=practitioner_full_url,
        organization_full_url=organization_full_url,
        period_start=period_start,
        period_end=period_end,
        case_full_url=case_full_url,
    )
    anamneza_text = (record_data.get("sadrzaj") or record_data.get("dijagnoza_tekst") or "").strip()
    anamneza = _build_anamneza_observation(
        sadrzaj=anamneza_text,
        patient_full_url=patient_full_url,
        encounter_full_url=encounter_full_url,
        practitioner_full_url=practitioner_full_url,
        effective=composition_date,
    )
    ishod = _build_ishod_observation(
        patient_full_url=patient_full_url,
        encounter_full_url=encounter_full_url,
        practitioner_full_url=practitioner_full_url,
        effective=composition_date,
    )

    # Composition MUST be the first entry in a Bundle.type=document per FHIR R4.
    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "identifier": {
            "system": "urn:ietf:rfc:3986",
            "value": f"urn:oid:{document_oid}",
        },
        "type": "document",
        "timestamp": composition_date,
        "entry": [
            {"fullUrl": composition_full_url, "resource": composition},
            {"fullUrl": patient_full_url, "resource": patient},
            {"fullUrl": encounter_full_url, "resource": encounter},
            {"fullUrl": practitioner_full_url, "resource": practitioner},
            {"fullUrl": organization_full_url, "resource": organization},
            {"fullUrl": djelatnost_full_url, "resource": djelatnost},
            {"fullUrl": anamneza_full_url, "resource": anamneza},
            {"fullUrl": case_full_url, "resource": condition},
            {"fullUrl": ishod_full_url, "resource": ishod},
        ],
    }

    logger.info(
        "Built inner Document Bundle: type=document doc_oid=%s entries=%d practitioner=%s",
        document_oid,
        len(bundle["entry"]),
        practitioner_full_url,
    )
    return bundle, practitioner_full_url


__all__ = ["build_clinical_document_bundle"]

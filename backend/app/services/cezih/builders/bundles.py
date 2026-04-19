"""FHIR Bundle constructors for CEZIH.

- build_message_bundle:  Bundle type='message' for $process-message (Case/Visit)
- build_iti65_transaction_bundle: Bundle type='transaction' for IHE MHD document submission
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.services.cezih.builders.common import (
    MESSAGE_TYPE_SYSTEM,
    _now_iso,
    org_ref,
    practitioner_ref,
)
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)


async def build_message_bundle(
    event_code: str,
    resource: dict[str, Any],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    source_oid: str | None = None,
    profile_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='message' with MessageHeader and resource.

    Does NOT add signature — call add_signature() separately for real mode.
    profile_urls: optional {"bundle": url, "header": url, "resource": url} for meta.profile.
    """

    if not sender_org_code:
        raise CezihError(
            "Šifra zdravstvene ustanove (org_code) nije konfigurirana za ovog zakupca. "
            "Postavite je u Postavke > Organizacija."
        )
    if not source_oid:
        raise CezihError(
            "OID informacijskog sustava nije konfiguriran za ovog zakupca. "
            "Postavite ga u Postavke > Organizacija."
        )

    resource_uuid = str(uuid.uuid4())
    header_uuid = str(uuid.uuid4())

    message_header: dict[str, Any] = {
        "resourceType": "MessageHeader",
        "eventCoding": {
            "system": MESSAGE_TYPE_SYSTEM,
            "code": event_code,
        },
    }

    # Field order matches official CEZIH example: sender, author, source, focus
    if sender_org_code:
        message_header["sender"] = org_ref(sender_org_code)

    if author_practitioner_id:
        message_header["author"] = practitioner_ref(author_practitioner_id)

    message_header["source"] = {"endpoint": f"urn:oid:{source_oid}" if source_oid else "urn:oid:0.0.0.0"}
    message_header["focus"] = [{"reference": f"urn:uuid:{resource_uuid}"}]

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "message",
        "timestamp": _now_iso(),
        "entry": [
            {
                "fullUrl": f"urn:uuid:{header_uuid}",
                "resource": message_header,
            },
            {
                "fullUrl": f"urn:uuid:{resource_uuid}",
                "resource": resource,
            },
        ],
    }

    # Inject meta.profile if profile URLs are provided
    if profile_urls:
        if profile_urls.get("bundle"):
            bundle["meta"] = {"profile": [profile_urls["bundle"]]}
        if profile_urls.get("header"):
            message_header["meta"] = {"profile": [profile_urls["header"]]}
        if profile_urls.get("resource"):
            resource["meta"] = {"profile": [profile_urls["resource"]]}

    return bundle


def build_iti65_transaction_bundle(
    entries: list[dict[str, Any]],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    bundle_profile: str | None = None,
    submission_set_profile: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='transaction' for IHE MHD ITI-65 document submission.

    IHE MHD ITI-65 requires type="transaction" (NOT type="message").
    Each entry must have a `request` with method and url.
    Optionally includes a SubmissionSet (List) as the first entry.
    """

    # Build SubmissionSet (List) — required by IHE MHD ITI-65
    # HRMinimalSubmissionSet requires 2 identifiers: uniqueId + entryUUID
    submission_set_uuid = str(uuid.uuid4())
    unique_id = str(uuid.uuid4())
    submission_set: dict[str, Any] = {
        "resourceType": "List",
        "meta": {
            "profile": [submission_set_profile or "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRMinimalSubmissionSet"],
        },
        "identifier": [
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{unique_id}",
            },
            {
                "use": "usual",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{submission_set_uuid}",
            },
        ],
        "status": "current",
        "mode": "working",
        "code": {
            "coding": [{
                "system": "https://profiles.ihe.net/ITI/MHD/CodeSystem/MHDlistTypes",
                "code": "submissionset",
            }]
        },
        "date": _now_iso(),
    }
    # Copy subject from the first DocumentReference (mustSupport on SubmissionSet)
    if entries and entries[0].get("subject"):
        submission_set["subject"] = entries[0]["subject"]
    # List.source only accepts Practitioner/Patient/Device — NOT Organization
    if author_practitioner_id:
        submission_set["source"] = practitioner_ref(author_practitioner_id)
    # Extensions: sourceId (required, min:1) + ihe-authorOrg
    extensions: list[dict[str, Any]] = [
        {
            "url": "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-sourceId",
            "valueIdentifier": {
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:oid:{sender_org_code}" if sender_org_code else "urn:oid:2.16.840.1.113883.2.7",
            },
        },
    ]
    if sender_org_code:
        extensions.append({
            "url": "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-authorOrg",
            "valueReference": org_ref(sender_org_code),
        })
    submission_set["extension"] = extensions

    # Pre-assign UUIDs to entries without _uuid to ensure consistency
    for e in entries:
        if "_uuid" not in e:
            e["_uuid"] = str(uuid.uuid4())

    # SubmissionSet entry references only DocumentReference entries (NOT Binary)
    doc_ref_entries = [e for e in entries if e.get("resourceType") == "DocumentReference"]
    doc_ref_uuids = [e["_uuid"] for e in doc_ref_entries]
    all_uuids = [e["_uuid"] for e in entries]
    submission_set["entry"] = [
        {"item": {"reference": f"urn:uuid:{u}"}} for u in doc_ref_uuids
    ]

    bundle_entries: list[dict[str, Any]] = [
        {
            "fullUrl": f"urn:uuid:{submission_set_uuid}",
            "resource": submission_set,
            "request": {"method": "POST", "url": "List"},
        }
    ]

    for i, entry_resource in enumerate(entries):
        entry_uuid = all_uuids[i]
        # Remove internal _uuid marker if present
        resource = {k: v for k, v in entry_resource.items() if k != "_uuid"}
        resource_type = resource.get("resourceType", "DocumentReference")
        resource_id = resource.get("id")

        # Use PUT for existing resources (cancel/update), POST for new ones
        if resource_id:
            request_entry = {"method": "PUT", "url": f"{resource_type}/{resource_id}"}
            full_url = f"urn:uuid:{entry_uuid}"
        else:
            request_entry = {"method": "POST", "url": resource_type}
            full_url = f"urn:uuid:{entry_uuid}"

        bundle_entries.append({
            "fullUrl": full_url,
            "resource": resource,
            "request": request_entry,
        })

    return {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "meta": {
            "profile": [bundle_profile or "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRMinimalProvideDocumentBundle"],
        },
        "type": "transaction",
        "timestamp": _now_iso(),
        "entry": bundle_entries,
    }


__all__ = [
    "build_message_bundle",
    "build_iti65_transaction_bundle",
]

"""Parse HRPrilog DocumentReference entries out of a signed FHIR Document Bundle.

Used by the import-cezih flow to extract attachments from an ITI-68-retrieved
clinical document and surface them as local Document rows linked to the
imported nalaz.

A prilog entry is identified either by:
- meta.profile containing the HRPrilog StructureDefinition URL, OR
- being referenced from Composition.section with code=16 (prilozeni-dokumenti)

Both checks are applied; either matching is enough. This keeps the parser
robust against bundles built by other CEZIH participants that may omit
meta.profile but always populate the section code.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PRILOG_PROFILE_URL = "http://fhir.cezih.hr/specifikacije/StructureDefinition/prilog"
DOC_SECTION_CODE_PRILOZI = "16"


def _entry_resource(entry: dict) -> dict:
    res = entry.get("resource")
    return res if isinstance(res, dict) else {}


def _collect_prilog_refs_from_composition(bundle: dict) -> set[str]:
    """Return the set of references targeted by the prilozeni-dokumenti section."""
    refs: set[str] = set()
    for entry in bundle.get("entry", []) or []:
        res = _entry_resource(entry)
        if res.get("resourceType") != "Composition":
            continue
        for section in res.get("section", []) or []:
            section_codes = {
                c.get("code")
                for coding_block in [section.get("code", {})]
                for c in coding_block.get("coding", []) or []
            }
            if DOC_SECTION_CODE_PRILOZI not in section_codes:
                continue
            for sec_entry in section.get("entry", []) or []:
                ref = sec_entry.get("reference")
                if isinstance(ref, str):
                    refs.add(ref)
    return refs


def _resource_is_prilog(resource: dict, prilog_refs: set[str], full_url: str) -> bool:
    """Match by HRPrilog meta.profile OR by Composition section linkage."""
    profiles = resource.get("meta", {}).get("profile", []) or []
    if PRILOG_PROFILE_URL in profiles:
        return True
    if full_url and full_url in prilog_refs:
        return True
    # Server-style references like "DocumentReference/<id>"
    res_id = resource.get("id")
    if res_id and f"DocumentReference/{res_id}" in prilog_refs:
        return True
    return False


def _first_attachment(resource: dict) -> dict:
    contents = resource.get("content") or []
    for content in contents:
        att = content.get("attachment") or {}
        if att.get("data"):
            return att
    return {}


def extract_prilozi_from_bundle(bundle: dict) -> list[dict[str, Any]]:
    """Walk a FHIR Document Bundle and return all HRPrilog attachments.

    Returns a list of dicts:
        {
            "title": str,
            "content_type": str,
            "data_b64": str,
            "doc_ref_id": str | None,
        }

    Entries lacking attachment.data are skipped (CEZIH HRPrilog requires data
    1..1 but other-participant bundles may use URL-only DocumentReferences -
    those are out of scope for import since the bytes aren't inline).
    """
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return []

    prilog_refs = _collect_prilog_refs_from_composition(bundle)
    results: list[dict[str, Any]] = []

    for entry in bundle.get("entry", []) or []:
        res = _entry_resource(entry)
        if res.get("resourceType") != "DocumentReference":
            continue
        full_url = entry.get("fullUrl") or ""
        if not _resource_is_prilog(res, prilog_refs, full_url):
            continue
        att = _first_attachment(res)
        data_b64 = att.get("data")
        if not data_b64:
            logger.info(
                "Skipping HRPrilog DocumentReference without inline data (fullUrl=%s)",
                full_url,
            )
            continue
        results.append({
            "title": att.get("title") or "prilog",
            "content_type": att.get("contentType") or "application/octet-stream",
            "data_b64": data_b64,
            "doc_ref_id": res.get("id"),
        })

    return results


__all__ = ["extract_prilozi_from_bundle", "PRILOG_PROFILE_URL", "DOC_SECTION_CODE_PRILOZI"]

"""CEZIH pre-flight validators — block invalid submissions before they reach CEZIH.

Validators here run AFTER local data resolution (e.g. _resolve_djelatnost) but
BEFORE the FHIR bundle is built and signed. The goal is to catch the kinds of
mismatches that HZZO Provjera Spremnosti flagged as rejection reasons, so the
doctor sees a clear 422 message in the UI instead of a CEZIH validation error
or a silent acceptance by the test environment.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.constants import CEZIH_DOC_TYPE_DJELATNOST_RULES


def validate_doc_type_djelatnost(doc_type_code: str, djelatnost_code: str) -> None:
    """Raise HTTP 422 if the CEZIH document type does not match djelatnost.

    Rules per HZZO Provjera Spremnosti spec (see CEZIH_DOC_TYPE_DJELATNOST_RULES).
    Unknown doc types pass through (forward-compat with future codes added to
    CEZIH_DOCUMENT_TYPE_MAP but not yet here).
    """
    rule = CEZIH_DOC_TYPE_DJELATNOST_RULES.get(doc_type_code)
    if not rule:
        return

    if "allowed_codes" in rule and djelatnost_code not in rule["allowed_codes"]:
        allowed = ", ".join(sorted(rule["allowed_codes"]))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Tip dokumenta {doc_type_code} ne odgovara šifri djelatnosti "
                f"{djelatnost_code}. Dozvoljene šifre djelatnosti za tip {doc_type_code}: "
                f"{allowed}. Promijenite šifru djelatnosti u Postavke → Korisnici "
                f"ili odaberite zapis čiji tip odgovara djelatnosti."
            ),
        )

    if "prefix" in rule and not djelatnost_code.startswith(rule["prefix"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Tip dokumenta {doc_type_code} zahtijeva šifru djelatnosti koja "
                f"počinje znamenkom {rule['prefix']} (trenutna: {djelatnost_code}). "
                f"Promijenite šifru djelatnosti u Postavke → Korisnici ili "
                f"odaberite zapis čiji tip odgovara djelatnosti."
            ),
        )


__all__ = ["validate_doc_type_djelatnost"]

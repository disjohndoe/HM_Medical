"""CEZIH pre-flight validators — block invalid submissions before they reach CEZIH.

Validators here run AFTER local data resolution (e.g. _resolve_djelatnost) but
BEFORE the FHIR bundle is built and signed. The goal is to catch the kinds of
mismatches that HZZO Provjera Spremnosti flagged as rejection reasons, so the
doctor sees a clear 422 message in the UI instead of a CEZIH validation error
or a silent acceptance by the test environment.

Exam-tenant bypass: the HZZO test ordinacija (`is_exam_tenant=True`) needs to
demo all three doc types (011/012/013) on one djelatnost so the certification
sweep can be run in a single session. In exam mode we log the mismatch but do
not raise; production tenants still get the hard 422.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.constants import CEZIH_DOC_TYPE_DJELATNOST_RULES

logger = logging.getLogger(__name__)


def validate_doc_type_djelatnost(
    doc_type_code: str,
    djelatnost_code: str,
    *,
    is_exam_tenant: bool = False,
) -> None:
    """Raise HTTP 422 if the CEZIH document type does not match djelatnost.

    Rules per HZZO Provjera Spremnosti spec (see CEZIH_DOC_TYPE_DJELATNOST_RULES).
    Unknown doc types pass through (forward-compat with future codes added to
    CEZIH_DOCUMENT_TYPE_MAP but not yet here).

    When ``is_exam_tenant`` is True, mismatches are logged at WARNING and the
    submission proceeds. The frontend surfaces a label so the doctor knows the
    same payload would be rejected in production.
    """
    rule = CEZIH_DOC_TYPE_DJELATNOST_RULES.get(doc_type_code)
    if not rule:
        return

    mismatch_detail: str | None = None

    if "allowed_codes" in rule and djelatnost_code not in rule["allowed_codes"]:
        allowed = ", ".join(sorted(rule["allowed_codes"]))
        mismatch_detail = (
            f"Tip dokumenta {doc_type_code} ne odgovara šifri djelatnosti "
            f"{djelatnost_code}. Dozvoljene šifre djelatnosti za tip {doc_type_code}: "
            f"{allowed}. Promijenite šifru djelatnosti u Postavke → Korisnici "
            f"ili odaberite zapis čiji tip odgovara djelatnosti."
        )
    elif "prefix" in rule and not djelatnost_code.startswith(rule["prefix"]):
        mismatch_detail = (
            f"Tip dokumenta {doc_type_code} zahtijeva šifru djelatnosti koja "
            f"počinje znamenkom {rule['prefix']} (trenutna: {djelatnost_code}). "
            f"Promijenite šifru djelatnosti u Postavke → Korisnici ili "
            f"odaberite zapis čiji tip odgovara djelatnosti."
        )

    if mismatch_detail is None:
        return

    if is_exam_tenant:
        logger.warning(
            "exam-tenant bypass: doc_type=%s djelatnost=%s mismatch (would 422 in prod)",
            doc_type_code,
            djelatnost_code,
        )
        return

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=mismatch_detail,
    )


__all__ = ["validate_doc_type_djelatnost"]

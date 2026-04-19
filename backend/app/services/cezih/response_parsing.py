"""Parse CEZIH $process-message responses + translate raw errors to Croatian.

Every CEZIH action that returns a Bundle goes through parse_message_response.
Error codes are looked up in a small table; diagnostics are pattern-matched.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Local copy to avoid circular import during refactor (will be removed in Task 4)
_ID_CASE_GLOBAL = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja"

# Croatian user-friendly messages for known CEZIH error codes and patterns.
# Keys are either exact CEZIH error codes (from OperationOutcome.details.coding[0].code)
# or substrings of the English diagnostics text for pattern matches.
_CEZIH_ERROR_MESSAGES_HR: dict[str, str] = {
    "ERR_HEALTH_ISSUE_2004": (
        "CEZIH ne dopušta ovu tranziciju stanja. Provjerite je li slučaj u "
        "ispravnom stanju za ovu akciju (Zatvori — aktivni/potvrđeni, "
        "Relaps — u remisiji, Ponovno otvori — zatvoreni slučaj)."
    ),
    "ERR_DS_1002": (
        "Digitalni potpis ili struktura poruke nije prošla validaciju. "
        "Provjerite da je pametna kartica ispravna i obratite se podršci."
    ),
    "ERR_DOM_10057": (
        "CEZIH ne prihvaća traženi status dokumenta. "
        "Dokument se može otkazati samo kroz zamjenu (replace)."
    ),
    "ERR_EHE_1099": (
        "CEZIH odbija korišteni profil poruke. Koristite standardni "
        "profil umjesto privatnog (npr. HRExternalMinimal)."
    ),
}

_CEZIH_DIAGNOSTIC_PATTERNS_HR: dict[str, str] = {
    "must be 'resolved'": (
        "CEZIH traži status 'Zatvoren' umjesto trenutnog. "
        "Provjerite slijed akcija (neke tranzicije nisu podržane u test okruženju)."
    ),
}


def _translate_cezih_error(error_code: str | None, diagnostics: str | None) -> str:
    """Translate a raw CEZIH error into a Croatian user-friendly message."""
    if error_code and error_code in _CEZIH_ERROR_MESSAGES_HR:
        return _CEZIH_ERROR_MESSAGES_HR[error_code]
    if diagnostics:
        for pattern, hr_msg in _CEZIH_DIAGNOSTIC_PATTERNS_HR.items():
            if pattern in diagnostics:
                return hr_msg
        return diagnostics
    if error_code:
        return f"CEZIH greška ({error_code}). Provjerite log servera za detalje."
    return "Nepoznata CEZIH greška. Provjerite log servera."


def parse_message_response(response_body: dict[str, Any]) -> dict[str, Any]:
    """Parse a CEZIH $process-message response Bundle.

    Returns dict with: success, response_code, identifier (if assigned), error_message.
    error_message is translated to Croatian when the code or diagnostic matches a
    known pattern; otherwise falls back to the raw CEZIH diagnostic.
    """
    result: dict[str, Any] = {
        "success": False,
        "response_code": None,
        "identifier": None,
        "error_message": None,
        "raw": response_body,
    }

    entries = response_body.get("entry", [])
    if not entries:
        result["error_message"] = "CEZIH nije vratio valjan odgovor (prazan Bundle)."
        return result

    for entry in entries:
        resource = entry.get("resource", {})
        rt = resource.get("resourceType")

        if rt == "MessageHeader":
            resp_info = resource.get("response", {})
            result["response_code"] = resp_info.get("code")
            result["success"] = resp_info.get("code") == "ok"

        elif rt == "OperationOutcome":
            for issue in resource.get("issue", []):
                if issue.get("severity") in ("error", "fatal"):
                    codings = issue.get("details", {}).get("coding") or [{}]
                    details = codings[0]
                    error_code = details.get("code")
                    diagnostics = issue.get("diagnostics")
                    issue_code = issue.get("code")
                    logger.warning(
                        "CEZIH ERROR DETAIL: code=%s issue_code=%s diagnostics=%s details=%s",
                        error_code, issue_code, diagnostics,
                        json.dumps(details, ensure_ascii=False)[:500],
                    )
                    result["error_message"] = _translate_cezih_error(error_code, diagnostics)
                    result["success"] = False
                    break

        elif rt == "Condition":
            for ident in resource.get("identifier", []):
                if ident.get("system", "") == _ID_CASE_GLOBAL:
                    result["identifier"] = ident.get("value")
                    break

    return result


__all__ = [
    "_CEZIH_DIAGNOSTIC_PATTERNS_HR",
    "_CEZIH_ERROR_MESSAGES_HR",
    "_translate_cezih_error",
    "parse_message_response",
]

from __future__ import annotations

from fastapi import status


class CezihError(Exception):
    """Base exception for all CEZIH-related errors."""

    default_http_status: int = status.HTTP_502_BAD_GATEWAY
    default_code: str = "CEZIH_ERROR"
    default_display: str = "Greška na CEZIH-u"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(self.message)

    @property
    def http_status_code(self) -> int:
        return self.default_http_status

    def to_operation_outcome(self) -> dict[str, str]:
        """Return the structured {code, display, diagnostics} payload the
        frontend's CezihApiError parser expects. Subclasses override to pull
        real codes out of the upstream response where available."""
        return {
            "code": self.default_code,
            "display": self.default_display,
            "diagnostics": self.detail or self.message,
        }


class CezihConnectionError(CezihError):
    """Network/VPN connectivity failure (cannot reach CEZIH servers)."""

    default_http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "CEZIH_CONNECTION_ERROR"
    default_display = "Nije moguće doći do CEZIH poslužitelja"


class CezihAuthError(CezihError):
    """OAuth2 token acquisition or refresh failure."""

    default_http_status = status.HTTP_401_UNAUTHORIZED
    default_code = "CEZIH_AUTH_FAILED"
    default_display = "CEZIH prijava nije uspjela"


class CezihFhirError(CezihError):
    """FHIR API returned an OperationOutcome error or unexpected response."""

    default_code = "CEZIH_FHIR_ERROR"
    default_display = "CEZIH je odbio zahtjev"

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        operation_outcome: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.operation_outcome = operation_outcome
        super().__init__(message, detail=str(operation_outcome) if operation_outcome else None)

    @property
    def http_status_code(self) -> int:
        # Surface upstream server errors as 502 (bad gateway) regardless of the
        # exact 5xx CEZIH returned — keeps the proxy-error semantics consistent
        # for the frontend. Only pass through 4xx classes that carry actionable
        # detail (e.g. 400 validation) as-is.
        if 400 <= self.status_code < 500:
            return self.status_code
        return status.HTTP_502_BAD_GATEWAY

    def to_operation_outcome(self) -> dict[str, str]:
        if self.operation_outcome:
            for issue in self.operation_outcome.get("issue", []):
                if issue.get("severity") not in ("error", "fatal"):
                    continue
                codings = issue.get("details", {}).get("coding", [])
                coding = codings[0] if codings else {}
                return {
                    "code": coding.get("code", "") or self.default_code,
                    "display": coding.get("display", "") or self.default_display,
                    "diagnostics": issue.get("diagnostics", "") or self.message,
                }
        return super().to_operation_outcome()


class CezihTimeoutError(CezihError):
    """Request to CEZIH timed out."""

    default_http_status = status.HTTP_504_GATEWAY_TIMEOUT
    default_code = "CEZIH_TIMEOUT"
    default_display = "CEZIH nije odgovorio na vrijeme"


class CezihSigningError(CezihError):
    """Remote signing service failure (Certilia cloud cert / certpubws)."""

    default_code = "CEZIH_SIGNING_FAILED"
    default_display = "Potpisivanje nije uspjelo"

    def __init__(
        self,
        message: str,
        *,
        signing_service_error: str | None = None,
    ) -> None:
        self.signing_service_error = signing_service_error
        super().__init__(message, detail=signing_service_error)

    def to_operation_outcome(self) -> dict[str, str]:
        return {
            "code": self.default_code,
            "display": self.default_display,
            "diagnostics": self.signing_service_error or self.message,
        }

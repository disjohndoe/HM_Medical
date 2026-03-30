# ruff: noqa: N815 — FHIR spec requires camelCase field names
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Primitive FHIR Types ---


class FHIRIdentifier(BaseModel):
    system: str | None = None
    value: str | None = None


class FHIRHumanName(BaseModel):
    family: str | None = None
    given: list[str] = Field(default_factory=list)
    prefix: list[str] = Field(default_factory=list)
    use: str | None = None  # "official", "usual"
    text: str | None = None


class FHIRCoding(BaseModel):
    system: str | None = None
    code: str | None = None
    display: str | None = None
    version: str | None = None


class FHIRCodeableConcept(BaseModel):
    coding: list[FHIRCoding] = Field(default_factory=list)
    text: str | None = None


class FHIRReference(BaseModel):
    reference: str | None = None
    display: str | None = None
    identifier: FHIRIdentifier | None = None
    type: str | None = None  # "Patient", "Practitioner", "Organization"


class FHIRPeriod(BaseModel):
    start: str | None = None
    end: str | None = None


# --- Core FHIR Resources ---


class FHIRPatient(BaseModel):
    resourceType: Literal["Patient"] = "Patient"
    id: str | None = None
    identifier: list[FHIRIdentifier] = Field(default_factory=list)
    name: list[FHIRHumanName] = Field(default_factory=list)
    birthDate: str | None = None
    gender: str | None = None
    active: bool | None = None
    address: list[dict[str, Any]] = Field(default_factory=list)
    telecom: list[dict[str, Any]] = Field(default_factory=list)


class FHIREncounter(BaseModel):
    resourceType: Literal["Encounter"] = "Encounter"
    id: str | None = None
    identifier: list[FHIRIdentifier] = Field(default_factory=list)
    extension: list[dict[str, Any]] = Field(default_factory=list)
    status: str | None = None  # "in-progress", "finished", "cancelled"
    class_fhir: FHIRCoding | None = Field(default=None, alias="class")
    subject: FHIRReference | None = None
    period: FHIRPeriod | None = None
    participant: list[dict[str, Any]] = Field(default_factory=list)
    reasonCode: list[FHIRCodeableConcept] = Field(default_factory=list)
    diagnosis: list[dict[str, Any]] = Field(default_factory=list)
    serviceProvider: FHIRReference | None = None

    model_config = {"populate_by_name": True}


class FHIRCondition(BaseModel):
    resourceType: Literal["Condition"] = "Condition"
    id: str | None = None
    identifier: list[FHIRIdentifier] = Field(default_factory=list)
    clinicalStatus: FHIRCodeableConcept | None = None
    verificationStatus: FHIRCodeableConcept | None = None
    severity: FHIRCodeableConcept | None = None
    code: FHIRCodeableConcept | None = None
    bodySite: list[FHIRCodeableConcept] = Field(default_factory=list)
    subject: FHIRReference | None = None
    encounter: FHIRReference | None = None
    onsetDateTime: str | None = None
    abatementDateTime: str | None = None
    asserter: FHIRReference | None = None
    note: list[dict[str, Any]] = Field(default_factory=list)


class FHIRDocumentReferenceContent(BaseModel):
    attachment: dict[str, Any] = Field(default_factory=dict)


class FHIRDocumentReference(BaseModel):
    resourceType: Literal["DocumentReference"] = "DocumentReference"
    id: str | None = None
    status: str | None = None  # "current", "superseded", "entered-in-error"
    type: FHIRCodeableConcept | None = None
    subject: FHIRReference | None = None
    date: str | None = None
    content: list[FHIRDocumentReferenceContent] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class FHIRBundleEntry(BaseModel):
    fullUrl: str | None = None
    resource: dict[str, Any] | None = None
    request: dict[str, Any] | None = None


class FHIRBundleSignature(BaseModel):
    type: list[FHIRCoding] = Field(default_factory=list)
    when: str | None = None  # ISO datetime
    who: FHIRReference | None = None
    data: str | None = None  # base64 encoded signature


class FHIRBundle(BaseModel):
    resourceType: Literal["Bundle"] = "Bundle"
    type: str | None = None  # "transaction", "searchset", "message", "collection"
    timestamp: str | None = None
    entry: list[FHIRBundleEntry] = Field(default_factory=list)
    total: int | None = None
    signature: FHIRBundleSignature | None = None


class FHIRMessageHeaderDestination(BaseModel):
    endpoint: str | None = None
    name: str | None = None


class FHIRMessageHeader(BaseModel):
    resourceType: Literal["MessageHeader"] = "MessageHeader"
    id: str | None = None
    eventCoding: FHIRCoding | None = None
    eventUri: str | None = Field(default=None, alias="eventUri")
    sender: FHIRReference | None = None
    author: FHIRReference | None = None
    source: dict[str, Any] | None = None
    destination: list[FHIRMessageHeaderDestination] = Field(default_factory=list)
    focus: list[FHIRReference] = Field(default_factory=list)
    response: dict[str, Any] | None = None  # {"identifier": "...", "code": "ok"}

    model_config = {"populate_by_name": True}


# --- Error Handling ---


class OperationOutcomeIssue(BaseModel):
    severity: str | None = None
    code: str | None = None
    details: FHIRCodeableConcept | None = None
    diagnostics: str | None = None
    location: list[str] = Field(default_factory=list)


class OperationOutcome(BaseModel):
    resourceType: Literal["OperationOutcome"] = "OperationOutcome"
    issue: list[OperationOutcomeIssue] = Field(default_factory=list)

    @property
    def first_error_message(self) -> str:
        for issue in self.issue:
            if issue.severity == "error":
                if issue.diagnostics:
                    return issue.diagnostics
                if issue.details and issue.details.text:
                    return issue.details.text
        return "Unknown FHIR error"


# --- OAuth2 Token Response ---


class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 300
    refresh_expires_in: int = 1800
    scope: str | None = None

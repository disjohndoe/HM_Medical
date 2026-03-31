"""Tests for new CEZIH modules (Phase 11) — no database required.

Tests the mock service functions, message builder, and FHIR model correctness
directly without needing the API layer or database.
"""
import pytest

from app.services.cezih.message_builder import (
    CASE_ACTION_MAP,
    ID_CASE_GLOBAL,
    ID_CASE_LOCAL,
    ID_VISIT,
    MESSAGE_TYPE_SYSTEM,
    build_condition_create,
    build_condition_data_update,
    build_condition_delete,
    build_condition_status_update,
    build_encounter_cancel,
    build_encounter_close,
    build_encounter_create,
    build_encounter_reopen,
    build_encounter_update,
    build_message_bundle,
    parse_message_response,
)
from app.services.cezih.models import (
    FHIRBundle,
    FHIRBundleSignature,
    FHIRCoding,
    FHIRCondition,
    FHIREncounter,
    FHIRMessageHeader,
)
from app.services.cezih_mock_service import (
    mock_cancel_document,
    mock_cancel_visit,
    mock_close_visit,
    mock_create_case,
    mock_create_visit,
    mock_expand_value_set,
    mock_find_organizations,
    mock_find_practitioners,
    mock_lookup_oid,
    mock_query_code_system,
    mock_register_foreigner,
    mock_reopen_visit,
    mock_replace_document,
    mock_retrieve_cases,
    mock_retrieve_document,
    mock_search_documents,
    mock_update_case,
    mock_update_case_data,
)

# ============================================================
# FHIR Models
# ============================================================


def test_encounter_model_class_is_coding():
    """Encounter.class must be FHIRCoding, not CodeableConcept."""
    enc = FHIREncounter(
        status="in-progress",
        class_fhir=FHIRCoding(system="test", code="9"),
    )
    assert enc.class_fhir.code == "9"
    dumped = enc.model_dump(by_alias=True)
    assert "class" in dumped
    assert dumped["class"]["code"] == "9"
    assert "coding" not in dumped["class"]  # NOT CodeableConcept


def test_message_header_has_event_coding():
    mh = FHIRMessageHeader(eventCoding=FHIRCoding(system=MESSAGE_TYPE_SYSTEM, code="1.1"))
    assert mh.eventCoding.code == "1.1"
    assert mh.eventCoding.system == MESSAGE_TYPE_SYSTEM


def test_bundle_signature_model():
    sig = FHIRBundleSignature(
        type=[FHIRCoding(system="urn:test", code="sig")],
        when="2026-03-30T12:00:00Z",
        data="base64data",
    )
    bundle = FHIRBundle(type="message", signature=sig)
    assert bundle.signature.data == "base64data"
    assert len(bundle.signature.type) == 1


def test_condition_model_new_fields():
    cond = FHIRCondition(
        onsetDateTime="2026-01-15",
        abatementDateTime="2026-03-30",
        severity={"coding": [{"code": "mild"}]},
        bodySite=[{"coding": [{"code": "123"}]}],
    )
    assert cond.onsetDateTime == "2026-01-15"
    assert cond.severity is not None
    assert len(cond.bodySite) == 1


# ============================================================
# Message Builder — Encounter
# ============================================================


def test_encounter_create_no_identifier():
    enc = build_encounter_create(
        patient_mbo="999990260", practitioner_id="1234567",
        org_code="1234", period_start="2026-03-30T10:00:00+02:00",
    )
    assert enc["resourceType"] == "Encounter"
    assert enc["status"] == "in-progress"
    assert "identifier" not in enc
    assert enc["subject"]["identifier"]["value"] == "999990260"
    assert enc["serviceProvider"]["identifier"]["value"] == "1234"


def test_encounter_update_requires_identifier():
    enc = build_encounter_update(visit_identifier="visit-123")
    assert enc["identifier"][0]["system"] == ID_VISIT
    assert enc["identifier"][0]["value"] == "visit-123"
    assert enc["status"] == "in-progress"


def test_encounter_close_finished_with_period_end():
    enc = build_encounter_close(
        visit_identifier="visit-123",
        period_start="2026-03-30T10:00:00Z", period_end="2026-03-30T11:00:00Z",
        diagnosis_case_id="case-456",
    )
    assert enc["status"] == "finished"
    assert enc["period"]["end"] == "2026-03-30T11:00:00Z"
    assert len(enc["diagnosis"]) == 1
    assert enc["diagnosis"][0]["condition"]["identifier"]["value"] == "case-456"


def test_encounter_cancel_entered_in_error():
    enc = build_encounter_cancel(
        visit_identifier="visit-123", period_start="2026-03-30T10:00:00Z",
    )
    assert enc["status"] == "entered-in-error"
    assert enc["identifier"][0]["value"] == "visit-123"


def test_encounter_reopen_in_progress():
    enc = build_encounter_reopen(visit_identifier="visit-123", org_code="1234")
    assert enc["status"] == "in-progress"
    assert enc["identifier"][0]["value"] == "visit-123"
    assert enc["serviceProvider"]["identifier"]["value"] == "1234"


# ============================================================
# Message Builder — Condition
# ============================================================


def test_condition_create_local_identifier():
    cond = build_condition_create(
        patient_mbo="999990260", icd_code="M54", icd_display="Dorsopatija",
        onset_date="2026-03-30", practitioner_id="1234567",
    )
    assert cond["identifier"][0]["system"] == ID_CASE_LOCAL
    assert cond["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    assert cond["code"]["coding"][0]["code"] == "M54"
    assert cond["onsetDateTime"] == "2026-03-30"
    assert "clinicalStatus" not in cond  # Server sets this


def test_condition_create_with_note():
    cond = build_condition_create(
        patient_mbo="999990260", icd_code="J45", icd_display="Astma",
        onset_date="2026-01-01", practitioner_id="1234567", note_text="Test napomena",
    )
    assert len(cond["note"]) == 1
    assert cond["note"][0]["text"] == "Test napomena"
    assert cond["note"][0]["extension"][0]["url"].endswith("hr-annotation-type")


def test_condition_status_update_global_identifier():
    cond = build_condition_status_update(
        case_identifier="global-case-123", patient_mbo="999990260",
        clinical_status="remission",
    )
    assert cond["identifier"][0]["system"] == ID_CASE_GLOBAL
    assert cond["identifier"][0]["value"] == "global-case-123"
    assert cond["clinicalStatus"]["coding"][0]["code"] == "remission"


def test_condition_data_update_preserves_clinical_status():
    cond = build_condition_data_update(
        case_identifier="global-case-123", patient_mbo="999990260",
        current_clinical_status="active", verification_status="confirmed",
        icd_code="I10", note_text="Updated",
    )
    # Must echo current status (cannot change via 2.6)
    assert cond["clinicalStatus"]["coding"][0]["code"] == "active"
    assert cond["verificationStatus"]["coding"][0]["code"] == "confirmed"
    assert cond["code"]["coding"][0]["code"] == "I10"


def test_condition_delete_minimal_payload():
    cond = build_condition_delete(case_identifier="global-case-123", patient_mbo="999990260")
    assert cond["identifier"][0]["system"] == ID_CASE_GLOBAL
    assert "clinicalStatus" not in cond
    assert "code" not in cond


# ============================================================
# Message Builder — Bundle & Response Parsing
# ============================================================


@pytest.mark.asyncio
async def test_build_message_bundle_structure():
    resource = {"resourceType": "Encounter", "status": "in-progress"}
    bundle = await build_message_bundle("1.1", resource, sender_org_code="1234", source_oid="1.2.3.4")
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "message"
    assert len(bundle["entry"]) == 2
    header = bundle["entry"][0]["resource"]
    assert header["resourceType"] == "MessageHeader"
    assert header["eventCoding"]["code"] == "1.1"
    assert header["eventCoding"]["system"] == MESSAGE_TYPE_SYSTEM
    assert bundle["entry"][1]["resource"]["resourceType"] == "Encounter"


def test_case_action_map_completeness():
    assert len(CASE_ACTION_MAP) == 8
    assert CASE_ACTION_MAP["create"]["code"] == "2.1"
    assert CASE_ACTION_MAP["remission"]["clinical_status"] == "remission"
    assert CASE_ACTION_MAP["resolve"]["clinical_status"] == "resolved"
    assert CASE_ACTION_MAP["update_data"]["code"] == "2.6"
    assert CASE_ACTION_MAP["update_data"]["clinical_status"] is None
    assert CASE_ACTION_MAP["delete"]["code"] == "2.8"


def test_parse_message_response_success():
    response = {
        "entry": [
            {"resource": {"resourceType": "MessageHeader", "response": {"code": "ok"}}},
            {"resource": {"resourceType": "Encounter", "identifier": [{"system": ID_VISIT, "value": "new-visit-id"}]}},
        ]
    }
    result = parse_message_response(response)
    assert result["success"] is True
    assert result["identifier"] == "new-visit-id"


def test_parse_message_response_error():
    response = {
        "entry": [
            {"resource": {"resourceType": "MessageHeader", "response": {"code": "fatal-error"}}},
            {"resource": {"resourceType": "OperationOutcome", "issue": [
                {"severity": "fatal", "code": "required", "diagnostics": "Missing field X"}
            ]}},
        ]
    }
    result = parse_message_response(response)
    assert result["success"] is False
    assert result["error_message"] == "Missing field X"


# ============================================================
# Mock Service — Registry & Terminology
# ============================================================


@pytest.mark.asyncio
async def test_mock_lookup_oid():
    result = await mock_lookup_oid("2.16.840.1.113883.2.22")
    assert result["mock"] is True
    assert result["oid"] == "2.16.840.1.113883.2.22"
    assert result["name"] == "CEZIH"


@pytest.mark.asyncio
async def test_mock_query_code_system_icd10():
    results = await mock_query_code_system("icd10-hr", "astma")
    assert len(results) > 0
    assert results[0]["code"] == "J45"
    assert results[0]["mock"] is True


@pytest.mark.asyncio
async def test_mock_expand_value_set():
    result = await mock_expand_value_set("http://test", "potvrđ")
    assert result["mock"] is True
    assert result["total"] > 0
    assert any(c["code"] == "confirmed" for c in result["concepts"])


@pytest.mark.asyncio
async def test_mock_find_organizations():
    results = await mock_find_organizations("Zagreb")
    assert len(results) > 0
    assert results[0]["mock"] is True


@pytest.mark.asyncio
async def test_mock_find_practitioners():
    results = await mock_find_practitioners("Horvat")
    assert len(results) > 0
    assert results[0]["family"] == "Horvat"


# ============================================================
# Mock Service — Foreigner Registration
# ============================================================


@pytest.mark.asyncio
async def test_mock_register_foreigner():
    result = await mock_register_foreigner({"ime": "John", "prezime": "Smith", "datum_rodjenja": "1985-01-01"})
    assert result["mock"] is True
    assert result["success"] is True
    assert result["mbo"].startswith("F")


# ============================================================
# Mock Service — Visit Management
# ============================================================


@pytest.mark.asyncio
async def test_mock_create_visit():
    result = await mock_create_visit("999990260", "2026-03-30T10:00:00Z")
    assert result["mock"] is True
    assert result["success"] is True
    assert result["visit_id"].startswith("MOCK-V-")
    assert result["status"] == "in-progress"


@pytest.mark.asyncio
async def test_mock_close_visit():
    result = await mock_close_visit("MOCK-V-123", "2026-03-30T11:00:00Z")
    assert result["success"] is True
    assert result["status"] == "finished"


@pytest.mark.asyncio
async def test_mock_reopen_visit():
    result = await mock_reopen_visit("MOCK-V-123")
    assert result["success"] is True
    assert result["status"] == "in-progress"


@pytest.mark.asyncio
async def test_mock_cancel_visit():
    result = await mock_cancel_visit("MOCK-V-123")
    assert result["success"] is True
    assert result["status"] == "entered-in-error"


# ============================================================
# Mock Service — Case Management
# ============================================================


@pytest.mark.asyncio
async def test_mock_retrieve_cases():
    results = await mock_retrieve_cases("999990260")
    assert len(results) == 3
    assert results[0]["mock"] is True
    assert results[0]["icd_code"] == "M54"


@pytest.mark.asyncio
async def test_mock_create_case():
    result = await mock_create_case("999990260", "M54", "Dorsopatija", "2026-03-30")
    assert result["mock"] is True
    assert result["success"] is True
    assert result["cezih_case_id"].startswith("MOCK-C-")


@pytest.mark.asyncio
async def test_mock_update_case():
    result = await mock_update_case("MOCK-C-001", "remission")
    assert result["success"] is True
    assert result["action"] == "remission"


@pytest.mark.asyncio
async def test_mock_update_case_data():
    result = await mock_update_case_data("MOCK-C-001", {"icd_code": "I10"})
    assert result["success"] is True


# ============================================================
# Mock Service — Document Operations
# ============================================================


@pytest.mark.asyncio
async def test_mock_search_documents():
    results = await mock_search_documents(patient_mbo="999990260")
    assert len(results) > 0
    assert results[0]["mock"] is True


@pytest.mark.asyncio
async def test_mock_search_documents_by_type():
    results = await mock_search_documents(document_type="uputnica")
    assert all(r["type"] == "uputnica" for r in results)


@pytest.mark.asyncio
async def test_mock_replace_document():
    result = await mock_replace_document("DOC-001")
    assert result["success"] is True
    assert result["replaced_reference_id"] == "DOC-001"


@pytest.mark.asyncio
async def test_mock_cancel_document():
    result = await mock_cancel_document("DOC-001")
    assert result["success"] is True
    assert result["status"] == "entered-in-error"


@pytest.mark.asyncio
async def test_mock_retrieve_document():
    content = await mock_retrieve_document("DOC-001")
    assert isinstance(content, bytes)
    assert b"DOC-001" in content

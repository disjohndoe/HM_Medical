"""Tests for CEZIH modules — message builder and FHIR model correctness.

Tests run directly without needing the API layer or database.
"""
import pytest

from app.services.cezih.message_builder import (
    CASE_ACTION_MAP,
    ID_CASE_GLOBAL,
    ID_CASE_LOCAL,
    MESSAGE_TYPE_SYSTEM,
    build_condition_create,
    build_condition_data_update,
    build_condition_status_update,
    build_message_bundle,
    parse_message_response,
)
from app.services.cezih.models import (
    FHIRBundle,
    FHIRBundleSignature,
    FHIRCoding,
    FHIRCondition,
    FHIRMessageHeader,
)

# ============================================================
# FHIR Models
# ============================================================


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
    assert len(CASE_ACTION_MAP) == 7
    assert "delete" not in CASE_ACTION_MAP  # Product rule: never ship CEZIH delete
    assert CASE_ACTION_MAP["create"]["code"] == "2.1"
    assert CASE_ACTION_MAP["remission"]["clinical_status"] == "remission"
    assert CASE_ACTION_MAP["resolve"]["code"] == "2.4"
    assert CASE_ACTION_MAP["resolve"]["clinical_status"] == "resolved"
    assert CASE_ACTION_MAP["relapse"]["code"] == "2.5"
    assert CASE_ACTION_MAP["relapse"]["clinical_status"] == "relapse"
    assert CASE_ACTION_MAP["update_data"]["code"] == "2.6"
    assert CASE_ACTION_MAP["update_data"]["clinical_status"] is None
    assert CASE_ACTION_MAP["reopen"]["code"] == "2.9"


def test_parse_message_response_success():
    response = {
        "entry": [
            {"resource": {"resourceType": "MessageHeader", "response": {"code": "ok"}}},
            {
                "resource": {
                    "resourceType": "Condition",
                    "identifier": [{"system": ID_CASE_GLOBAL, "value": "new-case-id"}],
                }
            },
        ]
    }
    result = parse_message_response(response)
    assert result["success"] is True
    assert result["identifier"] == "new-case-id"


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

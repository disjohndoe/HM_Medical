"""Tests for CEZIH service helper functions — now in fhir_api subpackage."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.cezih.models import FHIRHumanName, FHIRPatient
from app.services.cezih.fhir_api.patient import _extract_name
from app.services.cezih.fhir_api.documents import (
    _extract_codeable_text,
    _extract_reference_display,
    _map_fhir_status,
)

# --- Pure helper tests (no mocking needed) ---


class TestExtractName:
    def test_official_priority(self):
        p = FHIRPatient(name=[
            FHIRHumanName(family="Marić", given=["Marko"], use="usual"),
            FHIRHumanName(family="Horvat", given=["Ivan"], use="official"),
        ])
        family, given = _extract_name(p)
        assert family == "Horvat"
        assert given == "Ivan"

    def test_first_name_fallback(self):
        p = FHIRPatient(name=[
            FHIRHumanName(family="Test", given=["A", "B"]),
        ])
        family, given = _extract_name(p)
        assert family == "Test"
        assert given == "A B"

    def test_empty_list(self):
        p = FHIRPatient(name=[])
        family, given = _extract_name(p)
        assert family == ""
        assert given == ""


class TestExtractCodeableText:
    def test_text_priority(self):
        assert _extract_codeable_text({"text": "My text", "coding": [{"display": "Other"}]}) == "My text"

    def test_coding_display(self):
        assert _extract_codeable_text({"coding": [{"display": "Code display"}]}) == "Code display"

    def test_coding_code_fallback(self):
        assert _extract_codeable_text({"coding": [{"code": "ABC"}]}) == "ABC"

    def test_none(self):
        assert _extract_codeable_text(None) == ""

    def test_empty_dict(self):
        assert _extract_codeable_text({}) == ""


class TestExtractReferenceDisplay:
    def test_display(self):
        assert _extract_reference_display({"display": "Dr. Test"}) == "Dr. Test"

    def test_reference_fallback(self):
        assert _extract_reference_display({"reference": "Patient/1"}) == "Patient/1"

    def test_none(self):
        assert _extract_reference_display(None) == ""

    def test_string(self):
        assert _extract_reference_display("Patient/1") == ""


class TestMapFhirStatus:
    def test_current(self):
        assert _map_fhir_status("current") == "Otvoreni"

    def test_superseded(self):
        assert _map_fhir_status("superseded") == "Zatvoreni"

    def test_entered_in_error(self):
        assert _map_fhir_status("entered-in-error") == "Pogreška"

    def test_unknown(self):
        assert _map_fhir_status("unknown") == "unknown"


# --- Service function tests (need mocking) ---


class TestCheckInsurance:
    @pytest.mark.asyncio
    async def test_patient_found(self):
        """ITI-78 returns a Bundle with a matching Patient resource."""
        from app.services.cezih.fhir_api.patient import ID_MBO

        mock_client = AsyncMock()
        mock_response = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "resourceType": "Patient",
                    "id": "1",
                    "name": [{"family": "Horvat", "given": ["Ivan"], "use": "official"}],
                    "birthDate": "1985-03-15",
                    "identifier": [
                        {
                            "system": "http://fhir.cezih.hr/specifikacije/identifikatori/osiguranje",
                            "value": "HR-123456",
                        },
                    ],
                },
            }],
        }

        with patch("app.services.cezih.fhir_api.patient.CezihFhirClient") as MockClient:
            mock_fhir = AsyncMock()
            mock_fhir.get = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_fhir

            from app.services.cezih.fhir_api.patient import check_insurance
            result = await check_insurance(mock_client, ID_MBO, "999990260")

        assert result["ime"] == "Ivan"
        assert result["prezime"] == "Horvat"
        assert result["status_osiguranja"] == "Aktivan"

    @pytest.mark.asyncio
    async def test_patient_not_found(self):
        mock_client = AsyncMock()
        mock_response = {"resourceType": "Bundle", "entry": []}

        with patch("app.services.cezih.fhir_api.patient.CezihFhirClient") as MockClient:
            mock_fhir = AsyncMock()
            mock_fhir.get = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_fhir

            from app.services.cezih.fhir_api.patient import check_insurance
            result = await check_insurance(mock_client, "http://example.com/mbo", "000000000")

        assert result["status_osiguranja"] == "Nije pronađen"
        assert result["ime"] == ""


class TestSendErecept:
    @pytest.mark.asyncio
    async def test_stub_raises(self):
        """e-Recept raises CezihError — not implemented for privatnici."""
        from app.services.cezih.exceptions import CezihError

        mock_client = AsyncMock()
        service = __import__("app.services.cezih.service", fromlist=["send_erecept"])
        with pytest.raises(CezihError, match="nije implementiran"):
            await service.send_erecept(mock_client, {"mbo": "123"}, [{"naziv": "Paracetamol"}])

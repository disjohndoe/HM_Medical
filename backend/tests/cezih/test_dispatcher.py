"""Tests for backend/app/services/cezih/dispatcher.py — re-export shim and routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cezih.exceptions import CezihError


class TestDispatcherReExports:
    """Verify the dispatcher shim re-exports from dispatchers subpackage."""

    def test_insurance_check_importable(self):
        disp = __import__("app.services.cezih.dispatcher", fromlist=["insurance_check"])
        assert callable(disp.insurance_check)


class TestInsuranceCheckRouting:
    """Test that dispatcher.insurance_check routes to the right inner functions."""

    @pytest.mark.asyncio
    async def test_insurance_check_success(self):
        """Dispatcher resolves identifier, calls real check_insurance, persists result."""
        from uuid import uuid4

        tenant_id = uuid4()
        user_id = uuid4()
        patient_id = uuid4()

        mock_patient = MagicMock()
        mock_patient.tenant_id = tenant_id
        mock_patient.id = patient_id

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_patient)

        mock_http = AsyncMock()

        with patch(
            "app.services.cezih.dispatchers.patient.real_service.resolve_cezih_identifier",
            return_value=("http://fhir.cezih.hr/specifikacije/identifikatori/osiguranje", "999990260"),
        ), patch(
            "app.services.cezih.dispatchers.patient.real_service.check_insurance",
            AsyncMock(return_value={
                "mbo": "999990260", "ime": "Goran", "prezime": "Pac",
                "datum_rodjenja": "1990-01-01", "osiguravatelj": "HZZO",
                "status_osiguranja": "Aktivan",
            }),
        ):
            disp = __import__("app.services.cezih.dispatcher", fromlist=["insurance_check"])
            result = await disp.insurance_check(
                patient_id, db=mock_db, user_id=user_id, tenant_id=tenant_id, http_client=mock_http,
            )

        assert result["ime"] == "Goran"
        assert result["status_osiguranja"] == "Aktivan"

    @pytest.mark.asyncio
    async def test_insurance_check_failure_raises_502(self):
        """CezihError from inner check_insurance becomes HTTP 502."""
        from uuid import uuid4
        from fastapi import HTTPException

        tenant_id = uuid4()
        user_id = uuid4()
        patient_id = uuid4()

        mock_patient = MagicMock()
        mock_patient.tenant_id = tenant_id
        mock_patient.id = patient_id

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_patient)

        mock_http = AsyncMock()

        with patch(
            "app.services.cezih.dispatchers.patient.real_service.resolve_cezih_identifier",
            return_value=("http://fhir.cezih.hr/specifikacije/identifikatori/osiguranje", "999990260"),
        ), patch(
            "app.services.cezih.dispatchers.patient.real_service.check_insurance",
            AsyncMock(side_effect=CezihError("VPN not connected")),
        ):
            disp = __import__("app.services.cezih.dispatcher", fromlist=["insurance_check"])
            with pytest.raises(HTTPException) as exc_info:
                await disp.insurance_check(
                    patient_id, db=mock_db, user_id=user_id, tenant_id=tenant_id, http_client=mock_http,
                )
            assert exc_info.value.status_code == 502

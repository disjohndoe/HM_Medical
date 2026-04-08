"""Tests for backend/app/services/cezih/dispatcher.py — real CEZIH routing."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.cezih.exceptions import CezihError


class TestDispatcherRealMode:

    @pytest.mark.asyncio
    async def test_insurance_check_real_success(self):
        mock_http = AsyncMock()

        mock_real = AsyncMock(return_value={
            "mbo": "999990260", "ime": "Goran", "prezime": "Pac",
            "datum_rodjenja": "1990-01-01", "osiguravatelj": "HZZO",
            "status_osiguranja": "Aktivan",
        })

        with patch("app.services.cezih.dispatcher.real_service.check_insurance", mock_real):
            disp = __import__("app.services.cezih.dispatcher", fromlist=["insurance_check"])
            result = await disp.insurance_check("999990260", http_client=mock_http)

        assert result["ime"] == "Goran"
        mock_real.assert_called_once_with(mock_http, "999990260")

    @pytest.mark.asyncio
    async def test_insurance_check_real_failure(self):
        mock_http = AsyncMock()

        mock_real = AsyncMock(side_effect=CezihError("VPN not connected"))

        with patch("app.services.cezih.dispatcher.real_service.check_insurance", mock_real):
            disp = __import__("app.services.cezih.dispatcher", fromlist=["insurance_check"])
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await disp.insurance_check("123", http_client=mock_http)
            assert exc_info.value.status_code == 502

"""Tests for backend/app/services/cezih/client.py — FHIR HTTP client."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import (
    CezihConnectionError,
    CezihFhirError,
    CezihTimeoutError,
)


def _make_mock_client(status_code=200, json_body=None, text=""):
    """Build a mock httpx.AsyncClient and a response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    response.text = text
    response.headers = {}

    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=response)
    return mock_http, response


@patch("app.services.cezih.client.get_oauth_token", new_callable=AsyncMock, return_value="test-token")
@patch("app.services.cezih.client.settings")
class TestCezihFhirClient:

    @pytest.mark.asyncio
    async def test_get_success(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        body = {"resourceType": "Bundle", "entry": []}
        mock_http, _ = _make_mock_client(200, body)

        client = CezihFhirClient(mock_http)
        result = await client.get("test/path")

        assert result["resourceType"] == "Bundle"
        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "GET"
        assert "test-token" in call_args[1]["headers"]["Authorization"]

    @pytest.mark.asyncio
    async def test_post_success(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        body = {"resourceType": "DocumentReference", "id": "doc-1"}
        mock_http, _ = _make_mock_client(201, body)

        client = CezihFhirClient(mock_http)
        result = await client.post("test/path", json_body={"key": "val"})

        assert result["id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        client = CezihFhirClient(mock_http)
        with pytest.raises(CezihConnectionError, match="Cannot connect"):
            await client.get("test")

    @pytest.mark.asyncio
    async def test_timeout_error(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=httpx.TimeoutException("Timed out"))

        client = CezihFhirClient(mock_http)
        with pytest.raises(CezihTimeoutError, match="timed out"):
            await client.get("test")

    @pytest.mark.asyncio
    async def test_fhir_operation_outcome_error(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        body = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "diagnostics": "Patient not found"}],
        }
        mock_http, _ = _make_mock_client(404, body)

        client = CezihFhirClient(mock_http)
        with pytest.raises(CezihFhirError, match="Patient not found"):
            await client.get("test")

    @pytest.mark.asyncio
    async def test_non_fhir_4xx_error(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        mock_http, _ = _make_mock_client(403, {}, text="Forbidden")

        client = CezihFhirClient(mock_http)
        with pytest.raises(CezihFhirError, match="403"):
            await client.get("test")

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_settings, mock_token):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

        mock_http, _ = _make_mock_client(200, {"resourceType": "Bundle"})

        client = CezihFhirClient(mock_http)
        assert await client.health_check() is True


@patch("app.services.cezih.client.get_oauth_token", new_callable=AsyncMock, return_value="test-token")
@patch("app.services.cezih.client.settings")
class TestRetrySemantics:
    """Agent-proxied path (production) and direct path retry rules:
    401 always retries after token invalidation; connection errors and 5xx
    retry only idempotent GETs — a re-POSTed document submission could
    duplicate a signed nalaz."""

    def _setup_settings(self, mock_settings):
        mock_settings.CEZIH_FHIR_BASE_URL = "https://certws2.cezih.hr"
        mock_settings.CEZIH_FHIR_AUX_URL = "https://certws2.cezih.hr:9443"
        mock_settings.CEZIH_FHIR_PUB_BASE_URL = ""
        mock_settings.CEZIH_FHIR_PUB_AUX_URL = ""
        mock_settings.CEZIH_TIMEOUT = 30
        mock_settings.CEZIH_RETRY_ATTEMPTS = 3

    def _proxy_agent(self, monkeypatch, handler):
        """Force the agent path on and route proxy_http_request to `handler`."""
        from app.services.agent_connection_manager import agent_manager

        calls: list[dict] = []

        async def fake_proxy(tenant_id, *, method, url, headers, body, timeout):
            calls.append({"method": method, "url": url})
            return handler(len(calls))

        monkeypatch.setattr(agent_manager, "is_connected", lambda tenant_id: True)
        monkeypatch.setattr(agent_manager, "proxy_http_request", fake_proxy)
        monkeypatch.setattr("app.services.cezih.client.asyncio.sleep", AsyncMock())
        return calls

    @pytest.mark.asyncio
    async def test_agent_401_invalidates_token_and_retries(self, mock_settings, mock_token, monkeypatch):
        self._setup_settings(mock_settings)
        invalidate = MagicMock()
        monkeypatch.setattr("app.services.cezih.client.invalidate_token", invalidate)

        ok_body = {"resourceType": "Bundle", "entry": []}

        def handler(n):
            if n == 1:
                return {"status_code": 401, "body": json.dumps({"error": "invalid_token"}), "headers": {}}
            return {"status_code": 200, "body": json.dumps(ok_body), "headers": {}}

        calls = self._proxy_agent(monkeypatch, handler)

        client = CezihFhirClient(AsyncMock(), tenant_id=uuid.uuid4())
        result = await client.get("test/path")

        assert result["resourceType"] == "Bundle"
        assert len(calls) == 2, "401 must be retried once after token invalidation"
        invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_connection_error_on_post_not_retried(self, mock_settings, mock_token, monkeypatch):
        self._setup_settings(mock_settings)

        def handler(n):
            raise RuntimeError("agent websocket gone")

        calls = self._proxy_agent(monkeypatch, handler)

        client = CezihFhirClient(AsyncMock(), tenant_id=uuid.uuid4())
        with pytest.raises(CezihConnectionError):
            await client.post("doc-mhd-svc/api/v1/iti-65-service", json_body={"bundle": True})

        assert len(calls) == 1, "POST must never be auto-retried on a connection error (duplicate risk)"

    @pytest.mark.asyncio
    async def test_agent_connection_error_on_get_retried_until_attempts_exhausted(
        self, mock_settings, mock_token, monkeypatch
    ):
        self._setup_settings(mock_settings)

        def handler(n):
            raise RuntimeError("agent websocket gone")

        calls = self._proxy_agent(monkeypatch, handler)

        client = CezihFhirClient(AsyncMock(), tenant_id=uuid.uuid4())
        with pytest.raises(CezihConnectionError):
            await client.get("test/path")

        assert len(calls) == 3, "GET must be retried up to CEZIH_RETRY_ATTEMPTS"

    @pytest.mark.asyncio
    async def test_direct_5xx_post_not_retried(self, mock_settings, mock_token):
        self._setup_settings(mock_settings)
        mock_http, _ = _make_mock_client(500, {}, text="upstream boom")

        client = CezihFhirClient(mock_http)
        with pytest.raises(CezihFhirError, match="500"):
            await client.post("doc-mhd-svc/api/v1/iti-65-service", json_body={"bundle": True})

        mock_http.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_direct_5xx_get_retried(self, mock_settings, mock_token, monkeypatch):
        self._setup_settings(mock_settings)
        monkeypatch.setattr("app.services.cezih.client.asyncio.sleep", AsyncMock())

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"resourceType": "Bundle"}
        ok_response.text = "{}"

        # No tenant context -> direct path.
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=[_make_mock_client(500)[1], ok_response])

        client = CezihFhirClient(mock_http)
        result = await client.get("test/path")

        assert result["resourceType"] == "Bundle"
        assert mock_http.request.await_count == 2

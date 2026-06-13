"""Tests for backend/app/services/cezih/oauth.py — OAuth2 token management."""

from unittest.mock import AsyncMock, patch

import pytest

import app.services.cezih.oauth as oauth_mod
from app.services.cezih.oauth import _TokenSlot, get_oauth_token, invalidate_token


def _reset_oauth_cache():
    oauth_mod._slots.clear()


class TestTokenSlotIsValid:
    def test_no_token(self):
        slot = _TokenSlot()
        assert slot.is_valid() is False

    @patch("app.services.cezih.oauth.time.monotonic", return_value=1000.0)
    def test_valid(self, mock_time):
        from app.services.cezih.models import OAuth2TokenResponse

        tok = OAuth2TokenResponse(access_token="tok", expires_in=300)
        slot = _TokenSlot(token=tok, acquired_at=800.0)
        assert slot.is_valid() is True

    @patch("app.services.cezih.oauth.time.monotonic", return_value=1000.0)
    def test_expired(self, mock_time):
        from app.services.cezih.models import OAuth2TokenResponse

        tok = OAuth2TokenResponse(access_token="tok", expires_in=300)
        slot = _TokenSlot(token=tok, acquired_at=700.0)
        assert slot.is_valid() is False


class TestGetOAuthToken:
    @pytest.mark.asyncio
    @patch("app.services.cezih.oauth.time.monotonic", return_value=1000.0)
    async def test_cached_token(self, mock_time):
        from app.services.cezih.models import OAuth2TokenResponse

        url = "https://test.example.com/token"
        tok = OAuth2TokenResponse(access_token="cached-tok", expires_in=300)
        oauth_mod._slots[url] = _TokenSlot(token=tok, acquired_at=800.0)

        mock_client = AsyncMock()
        token = await get_oauth_token(client=mock_client, oauth2_url=url)
        assert token == "cached-tok"
        mock_client.post.assert_not_called()
        _reset_oauth_cache()

    @pytest.mark.asyncio
    @patch("app.services.cezih.oauth.time.monotonic", return_value=1000.0)
    @patch.object(oauth_mod, "settings")
    async def test_fetch_new_token(self, mock_settings, mock_time):
        mock_settings.CEZIH_OAUTH2_URL = "https://example.com/token"
        mock_settings.CEZIH_CLIENT_ID = "test-id"
        mock_settings.CEZIH_CLIENT_SECRET = "test-secret"
        mock_settings.CEZIH_TIMEOUT = 10

        _reset_oauth_cache()

        url = "https://example.com/token"

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = '{"access_token":"new-tok","expires_in":300}'
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        token = await get_oauth_token(client=mock_client, oauth2_url=url)
        assert token == "new-tok"
        mock_client.post.assert_called_once()
        _reset_oauth_cache()


class TestInvalidateToken:
    def test_invalidate_specific_url(self):
        url = "https://test.example.com/token"
        from app.services.cezih.models import OAuth2TokenResponse

        tok = OAuth2TokenResponse(access_token="tok", expires_in=300)
        oauth_mod._slots[url] = _TokenSlot(token=tok, acquired_at=999.0)

        invalidate_token(oauth2_url=url)
        assert oauth_mod._slots[url].token is None
        assert oauth_mod._slots[url].acquired_at == 0.0
        _reset_oauth_cache()

    def test_invalidate_all(self):
        from app.services.cezih.models import OAuth2TokenResponse

        tok = OAuth2TokenResponse(access_token="tok", expires_in=300)
        oauth_mod._slots["url1"] = _TokenSlot(token=tok, acquired_at=100.0)
        oauth_mod._slots["url2"] = _TokenSlot(token=tok, acquired_at=200.0)

        invalidate_token()
        for s in oauth_mod._slots.values():
            assert s.token is None
            assert s.acquired_at == 0.0
        _reset_oauth_cache()

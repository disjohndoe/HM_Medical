"""Per-user signer OIB resolution for extsigner (Certilia) signing.

Historically the signer OIB was a global env var (CEZIH_SIGNER_OIB), which
made every doctor in every tenant sign as the same person — wrong the moment
a second doctor or client exists. These tests pin the per-user resolution:
the OIB comes from User.card_certificate_oib via the request contextvars,
with clear errors and no fallbacks.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services.cezih.client import current_db_session, current_user_id
from app.services.cezih.exceptions import CezihError, CezihSigningError
from app.services.cezih.signing import resolve_signer_oib

USER_ID = "11111111-1111-1111-1111-111111111111"


class _FakeScalarDb:
    """Minimal AsyncSession stand-in: returns a canned scalar."""

    def __init__(self, value):
        self._value = value

    async def scalar(self, *_args, **_kwargs):
        return self._value


@pytest.fixture(autouse=True)
def _clear_context():
    """Isolate contextvars between tests."""
    current_user_id.set(None)
    current_db_session.set(None)
    yield
    current_user_id.set(None)
    current_db_session.set(None)


async def test_returns_user_oib():
    current_user_id.set(USER_ID)
    current_db_session.set(_FakeScalarDb("15881939647"))
    assert await resolve_signer_oib() == "15881939647"


async def test_no_user_in_context():
    with pytest.raises(CezihError, match="prijavljenog korisnika"):
        await resolve_signer_oib()


async def test_no_db_session():
    current_user_id.set(USER_ID)
    with pytest.raises(CezihError, match="Baza podataka"):
        await resolve_signer_oib()


async def test_user_without_oib_raises_actionable_error():
    current_user_id.set(USER_ID)
    current_db_session.set(_FakeScalarDb(None))
    with pytest.raises(CezihError, match="OIB"):
        await resolve_signer_oib()


async def test_db_failure_raises_cleared_error():
    class _BrokenDb:
        async def scalar(self, *_a, **_k):
            raise RuntimeError("connection reset")

    current_user_id.set(USER_ID)
    current_db_session.set(_BrokenDb())
    with pytest.raises(CezihError, match="administratora"):
        await resolve_signer_oib()


@pytest.fixture()
def _offline_cezih_urls(monkeypatch):
    """Keep unit tests off the network: no extsigner base URLs."""
    monkeypatch.setattr(settings, "CEZIH_FHIR_PUB_BASE_URL", "")
    monkeypatch.setattr(settings, "CEZIH_FHIR_BASE_URL", "")


async def test_extsigner_requires_user_oib(monkeypatch, _offline_cezih_urls):
    """sign_bundle_via_extsigner must surface a missing per-user OIB as a
    CezihSigningError, not silently skip or fall back to a global value."""
    from app.services import cezih_signing

    monkeypatch.setattr(cezih_signing, "_should_use_agent", lambda: True)

    async def _fail_resolver():
        raise CezihError("Korisniku nije postavljen OIB za udaljeno potpisivanje (Certilia).")

    monkeypatch.setattr("app.services.cezih.signing.resolve_signer_oib", _fail_resolver)
    with pytest.raises(CezihSigningError, match="OIB"):
        await cezih_signing.sign_bundle_via_extsigner(b"{}", message_id="m1")


async def test_extsigner_accepts_resolved_oib(monkeypatch, _offline_cezih_urls):
    """With a resolved per-user OIB the flow proceeds past identity resolution
    (and stops at the intentionally blank base URL — proving no global
    fallback supplies identity or endpoints)."""
    from app.services import cezih_signing

    monkeypatch.setattr(cezih_signing, "_should_use_agent", lambda: True)

    async def _fake_resolver():
        return "12345678901"

    monkeypatch.setattr("app.services.cezih.signing.resolve_signer_oib", _fake_resolver)
    with pytest.raises(CezihSigningError, match="CEZIH_FHIR_BASE_URL"):
        await cezih_signing.sign_bundle_via_extsigner(b"{}", message_id="m1")

"""Unit tests for the shared CEZIH ownership classifier.

Cases, nalazi and visits all decide "Naša vs Vanjski/Ostalo" through this single
classifier (identity on the wire, not local-row presence). See ownership.py.
"""

from __future__ import annotations

from app.services.cezih.ownership import TenantCezihIdentity


def _identity() -> TenantCezihIdentity:
    return TenantCezihIdentity(
        sifra_ustanove="999001464",
        practitioner_ids=frozenset({"7659059", "7000000"}),
    )


class TestOwns:
    def test_own_org_code_matches(self) -> None:
        assert _identity().owns(org_codes=["999001464"]) is True

    def test_foreign_org_code_is_external(self) -> None:
        assert _identity().owns(org_codes=["123456789"]) is False

    def test_own_doctor_hzjz_matches_even_without_org(self) -> None:
        # The visit/nalaz bug class: serviceProvider blank/foreign but our doctor
        # authored it. Doctor-HZJZ match alone must classify it as ours.
        assert _identity().owns(org_codes=[None], practitioner_ids=["7659059"]) is True

    def test_foreign_org_and_foreign_doctor_is_external(self) -> None:
        assert (
            _identity().owns(org_codes=["123456789"], practitioner_ids=["9999999"])
            is False
        )

    def test_no_identifiers_present_is_external(self) -> None:
        # owns() makes no positive claim without evidence; the lenient "treat as
        # ours" default lives on the schema field, not here.
        assert _identity().owns() is False
        assert _identity().owns(org_codes=[None, ""], practitioner_ids=[None, ""]) is False

    def test_tenant_without_identity_owns_nothing(self) -> None:
        empty = TenantCezihIdentity(sifra_ustanove=None, practitioner_ids=frozenset())
        assert empty.owns(org_codes=["999001464"], practitioner_ids=["7659059"]) is False

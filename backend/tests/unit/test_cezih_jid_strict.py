"""JID (jedinstveni-identifikator-pacijenta) strict-shape guards.

HZZO Provjera Spremnosti rejected 2026-05-11 because a CUID-shaped value
('cmj70ejct00se5c85hg2eax6p') was being sent as the foreigner's JID. These
tests pin the two defensive layers: extraction (reject at PMIR response
parse) and resolution (skip at the moment we'd compose an outgoing payload).
"""

from __future__ import annotations

import types

import pytest

from app.services.cezih.builders.common import (
    ID_EHIC,
    ID_JEDINSTVENI,
    ID_MBO,
    ID_OIB,
    ID_PUTOVNICA,
)
from app.services.cezih.exceptions import CezihError
from app.services.cezih.fhir_api.identifiers import resolve_cezih_identifier
from app.services.cezih.fhir_api.pmir import _extract_cezih_patient_identifier


def _patient(**attrs):
    """Minimal duck-typed patient object for resolve_cezih_identifier tests."""
    defaults = dict(
        mbo=None,
        cezih_patient_id=None,
        oib=None,
        ehic_broj=None,
        broj_putovnice=None,
    )
    defaults.update(attrs)
    return types.SimpleNamespace(**defaults)


class TestExtractCezihPatientIdentifier:
    def test_accepts_numeric_jid_from_bundle(self) -> None:
        response = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [
                            {"system": ID_JEDINSTVENI, "value": "1500001"},
                        ],
                    }
                }
            ],
        }
        assert _extract_cezih_patient_identifier(response) == "1500001"

    def test_accepts_numeric_jid_from_patient(self) -> None:
        response = {
            "resourceType": "Patient",
            "identifier": [{"system": ID_JEDINSTVENI, "value": "1384733"}],
        }
        assert _extract_cezih_patient_identifier(response) == "1384733"

    def test_rejects_cuid_shaped_jid(self) -> None:
        # The exact CUID HZZO flagged on 2026-05-11.
        response = {
            "resourceType": "Patient",
            "identifier": [
                {"system": ID_JEDINSTVENI, "value": "cmj70ejct00se5c85hg2eax6p"},
            ],
        }
        assert _extract_cezih_patient_identifier(response) == ""

    def test_rejects_alphanumeric_jid(self) -> None:
        response = {
            "resourceType": "Patient",
            "identifier": [{"system": ID_JEDINSTVENI, "value": "ABC123"}],
        }
        assert _extract_cezih_patient_identifier(response) == ""

    def test_no_jid_returns_empty(self) -> None:
        response = {
            "resourceType": "Patient",
            "identifier": [{"system": ID_MBO, "value": "123456789"}],
        }
        assert _extract_cezih_patient_identifier(response) == ""

    def test_empty_response_returns_empty(self) -> None:
        assert _extract_cezih_patient_identifier({}) == ""
        assert _extract_cezih_patient_identifier({"resourceType": "Bundle", "entry": []}) == ""


class TestResolveCezihIdentifierJidGuard:
    def test_mbo_wins_even_if_jid_is_invalid(self) -> None:
        p = _patient(mbo="123456789", cezih_patient_id="cmcuid12345")
        assert resolve_cezih_identifier(p) == (ID_MBO, "123456789")

    def test_numeric_jid_used_when_no_mbo(self) -> None:
        p = _patient(cezih_patient_id="1384733")
        assert resolve_cezih_identifier(p) == (ID_JEDINSTVENI, "1384733")

    def test_cuid_jid_falls_through_to_oib(self) -> None:
        p = _patient(cezih_patient_id="cmj70ejct00se5c85hg2eax6p", oib="99999900162")
        assert resolve_cezih_identifier(p) == (ID_OIB, "99999900162")

    def test_cuid_jid_falls_through_to_ehic(self) -> None:
        p = _patient(cezih_patient_id="cmcuid12345", ehic_broj="HR12345")
        assert resolve_cezih_identifier(p) == (ID_EHIC, "HR12345")

    def test_cuid_jid_falls_through_to_putovnica(self) -> None:
        p = _patient(cezih_patient_id="cmcuid12345", broj_putovnice="TEST123")
        assert resolve_cezih_identifier(p) == (ID_PUTOVNICA, "TEST123")

    def test_cuid_jid_and_no_other_id_raises_clear_error(self) -> None:
        # Foreigner with stale CUID JID and no passport/EHIC — doctor must re-register.
        p = _patient(cezih_patient_id="cmj70ejct00se5c85hg2eax6p")
        with pytest.raises(CezihError) as exc:
            resolve_cezih_identifier(p)
        assert "ponovno registrirajte" in exc.value.message.lower()

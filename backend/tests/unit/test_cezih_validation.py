"""Unit tests for CEZIH pre-flight validators."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.cezih.validation import validate_doc_type_djelatnost


class TestDocTypeDjelatnost:
    """HZZO Provjera Spremnosti rejection (2026-05-11) — doc type ↔ djelatnost."""

    @pytest.mark.parametrize(
        "djelatnost",
        ["1010000", "1020000", "1090100", "1040000", "1050000"],
    )
    def test_011_accepts_allowed_codes(self, djelatnost: str) -> None:
        validate_doc_type_djelatnost("011", djelatnost)

    def test_011_rejects_other_code(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_doc_type_djelatnost("011", "2010000")
        assert exc.value.status_code == 422
        assert "011" in exc.value.detail
        assert "2010000" in exc.value.detail

    def test_012_accepts_prefix_2(self) -> None:
        validate_doc_type_djelatnost("012", "2010000")
        validate_doc_type_djelatnost("012", "2999999")

    def test_012_rejects_non_prefix(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_doc_type_djelatnost("012", "1010000")
        assert exc.value.status_code == 422
        assert "počinje znamenkom 2" in exc.value.detail

    def test_013_accepts_prefix_3(self) -> None:
        validate_doc_type_djelatnost("013", "3010000")

    def test_013_rejects_non_prefix(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_doc_type_djelatnost("013", "1010000")
        assert exc.value.status_code == 422
        assert "počinje znamenkom 3" in exc.value.detail

    def test_unknown_doc_type_passes_through(self) -> None:
        # Forward-compat: codes not yet in rules table must not block sending.
        validate_doc_type_djelatnost("099", "1010000")
        validate_doc_type_djelatnost("", "1010000")

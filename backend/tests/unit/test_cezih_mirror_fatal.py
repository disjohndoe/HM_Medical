"""Regression tests: CEZIH mirror-write helpers must propagate DB exceptions (no silent swallow)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.services.cezih.dispatchers.cases import (
    _persist_local_case_by_patient_id,
    _update_local_case,
)
from app.services.cezih.dispatchers.visits import (
    _persist_local_visit_by_patient_id,
    _update_local_visit,
    _upsert_cezih_visit_from_response,
)


def _make_db_flush_raises(exc_class):
    """Return a mock AsyncSession whose flush() raises exc_class."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=exc_class(None, None, Exception("mocked db error")))
    return db


def _make_db_select_row_flush_raises(exc_class):
    """Return a mock AsyncSession where execute() returns a row and flush() raises.

    Used for helpers that do SELECT ... then flush — they skip flush when row is None,
    so we must return a real-looking row to reach the flush call.
    """
    row = MagicMock()
    row.clinical_status = "active"
    row.visited_clinical_statuses = []
    row.status = "in-progress"
    row.period_start = None
    row.period_end = None
    row.service_provider_code = None

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=row)

    db = MagicMock()
    db.execute = AsyncMock(return_value=scalar_result)
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=exc_class(None, None, Exception("mocked db error")))
    return db


# ---------------------------------------------------------------------------
# _persist_local_case_by_patient_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_local_case_propagates_integrity_error():
    db = _make_db_flush_raises(IntegrityError)
    with pytest.raises(IntegrityError):
        await _persist_local_case_by_patient_id(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            patient_id=UUID("00000000-0000-0000-0000-000000000002"),
            identifier_value="123456789",
            local_case_id="lc1",
            cezih_case_id="cc1",
            icd_code="J06.9",
            icd_display="Test",
            onset_date="2026-01-01",
            verification_status="unconfirmed",
            note_text=None,
        )


@pytest.mark.asyncio
async def test_persist_local_case_propagates_operational_error():
    db = _make_db_flush_raises(OperationalError)
    with pytest.raises(OperationalError):
        await _persist_local_case_by_patient_id(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            patient_id=UUID("00000000-0000-0000-0000-000000000002"),
            identifier_value="123456789",
            local_case_id="lc1",
            cezih_case_id="cc1",
            icd_code="J06.9",
            icd_display="Test",
            onset_date="2026-01-01",
            verification_status="unconfirmed",
            note_text=None,
        )


# ---------------------------------------------------------------------------
# _update_local_case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_local_case_propagates_integrity_error():
    db = _make_db_select_row_flush_raises(IntegrityError)
    with pytest.raises(IntegrityError):
        await _update_local_case(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            case_id="cc1",
            clinical_status="resolved",
        )


@pytest.mark.asyncio
async def test_update_local_case_propagates_operational_error():
    db = _make_db_select_row_flush_raises(OperationalError)
    with pytest.raises(OperationalError):
        await _update_local_case(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            case_id="cc1",
            clinical_status="resolved",
        )


# ---------------------------------------------------------------------------
# _persist_local_visit_by_patient_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_local_visit_propagates_integrity_error():
    db = _make_db_flush_raises(IntegrityError)
    with pytest.raises(IntegrityError):
        await _persist_local_visit_by_patient_id(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            patient_id=UUID("00000000-0000-0000-0000-000000000002"),
            identifier_value="123456789",
            cezih_visit_id="cv1",
            status_str="in-progress",
            admission_type="6",
            tip_posjete="1",
            vrsta_posjete="1",
            reason=None,
            service_provider_code=None,
        )


@pytest.mark.asyncio
async def test_persist_local_visit_propagates_operational_error():
    db = _make_db_flush_raises(OperationalError)
    with pytest.raises(OperationalError):
        await _persist_local_visit_by_patient_id(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            patient_id=UUID("00000000-0000-0000-0000-000000000002"),
            identifier_value="123456789",
            cezih_visit_id="cv1",
            status_str="in-progress",
            admission_type="6",
            tip_posjete="1",
            vrsta_posjete="1",
            reason=None,
            service_provider_code=None,
        )


# ---------------------------------------------------------------------------
# _update_local_visit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_local_visit_propagates_integrity_error():
    db = _make_db_select_row_flush_raises(IntegrityError)
    with pytest.raises(IntegrityError):
        await _update_local_visit(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            visit_id="cv1",
            status_str="finished",
        )


@pytest.mark.asyncio
async def test_update_local_visit_propagates_operational_error():
    db = _make_db_select_row_flush_raises(OperationalError)
    with pytest.raises(OperationalError):
        await _update_local_visit(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            visit_id="cv1",
            status_str="finished",
        )


# ---------------------------------------------------------------------------
# _upsert_cezih_visit_from_response
# ---------------------------------------------------------------------------


def _make_db_execute_raises(exc_class):
    """Return a mock AsyncSession whose execute() raises exc_class.

    Used for helpers where the except block wraps db.execute (SELECT) rather
    than db.flush — i.e. _upsert_cezih_visit_from_response.
    """
    db = MagicMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=exc_class(None, None, Exception("mocked db error")))
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_upsert_cezih_visit_from_response_propagates_integrity_error():
    db = _make_db_execute_raises(IntegrityError)
    with pytest.raises(IntegrityError):
        await _upsert_cezih_visit_from_response(
            db=db,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            patient_id=UUID("00000000-0000-0000-0000-000000000002"),
            patient_mbo="123456789",
            remote={"visit_id": "cv1"},
        )

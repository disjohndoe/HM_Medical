"""Persist per-row CEZIH error state so the frontend badge survives page
refreshes. Each write happens in its own AsyncSession/transaction — the
dispatcher's main transaction may be in a rolled-back state when we need to
record the failure, and we don't want the rollback to erase the error record.

Non-fatal: if the persist itself fails (e.g. missing row, DB hiccup) we log
and continue rather than masking the original CEZIH error with a 500.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.cezih_case import CezihCase
from app.models.cezih_visit import CezihVisit
from app.models.medical_record import MedicalRecord
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)

ErrorTarget = Literal["visit", "case", "medical_record"]


def _target_columns(target: ErrorTarget) -> tuple:
    if target == "visit":
        return (
            CezihVisit,
            CezihVisit.last_error_code,
            CezihVisit.last_error_display,
            CezihVisit.last_error_diagnostics,
            CezihVisit.last_error_at,
        )
    if target == "case":
        return (
            CezihCase,
            CezihCase.last_error_code,
            CezihCase.last_error_display,
            CezihCase.last_error_diagnostics,
            CezihCase.last_error_at,
        )
    return (
        MedicalRecord,
        MedicalRecord.cezih_last_error_code,
        MedicalRecord.cezih_last_error_display,
        MedicalRecord.cezih_last_error_diagnostics,
        MedicalRecord.cezih_last_error_at,
    )


async def record_cezih_error(
    target: ErrorTarget,
    row_id: UUID | None,
    tenant_id: UUID | None,
    error: CezihError,
) -> None:
    """Persist error on the given row. Silently no-ops if row_id or tenant_id
    is missing (e.g. a create action that failed before the row was assigned
    an id — in that case the dialog + toast are the only feedback, which is
    fine)."""
    if row_id is None or tenant_id is None:
        return
    try:
        model, code_col, display_col, diag_col, at_col = _target_columns(target)
        payload = error.to_operation_outcome()
        async with async_session() as session:
            await session.execute(
                update(model)
                .where(model.id == row_id, model.tenant_id == tenant_id)
                .values(
                    {
                        code_col: (payload.get("code") or "CEZIH_ERROR")[:128],
                        display_col: payload.get("display") or "",
                        diag_col: payload.get("diagnostics") or "",
                        at_col: datetime.now(UTC),
                    }
                )
            )
            await session.commit()
    except Exception:
        logger.warning(
            "Failed to persist CEZIH row error for %s %s (tenant=%s): %s",
            target,
            row_id,
            tenant_id,
            error.__class__.__name__,
            exc_info=True,
        )


async def clear_cezih_error(
    target: ErrorTarget,
    row_id: UUID | None,
    tenant_id: UUID | None,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Clear error columns for the given row. When `session` is provided the
    UPDATE runs inside the caller's transaction — required when the caller has
    already modified the same row via `setattr` + `flush`, because opening a
    fresh session here would self-deadlock on the row lock held by the caller's
    uncommitted UPDATE (seen in TC19 retry-after-400 path on 2026-04-20)."""
    if row_id is None or tenant_id is None:
        return
    try:
        model, code_col, display_col, diag_col, at_col = _target_columns(target)
        stmt = (
            update(model)
            .where(
                model.id == row_id,
                model.tenant_id == tenant_id,
                code_col.isnot(None),
            )
            .values(
                {
                    code_col: None,
                    display_col: None,
                    diag_col: None,
                    at_col: None,
                }
            )
        )
        if session is not None:
            await session.execute(stmt)
            return
        async with async_session() as fresh:
            await fresh.execute(stmt)
            await fresh.commit()
    except Exception:
        logger.warning(
            "Failed to clear CEZIH row error for %s %s (tenant=%s)",
            target,
            row_id,
            tenant_id,
            exc_info=True,
        )

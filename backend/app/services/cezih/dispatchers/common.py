"""Common dispatcher utilities — audit helpers and context management."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)


def _raise_cezih_error(e: CezihError) -> None:
    """Convert any CezihError subclass to HTTPException with a structured detail
    body the frontend's CezihApiError parser can consume:

        {"detail": "<message>", "cezih_error": {"code", "display", "diagnostics"}}

    This replaces the older FHIR-only path — connection, timeout, auth and
    signing errors now surface the same shape so the UI badge/toast works
    uniformly for every failure mode."""
    raise HTTPException(
        status_code=e.http_status_code,
        detail={
            "message": e.message,
            "cezih_error": e.to_operation_outcome(),
        },
    ) from e


async def _write_audit(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    user_id: UUID | None,
    action: str,
    resource_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    """Write audit log for CEZIH operations (if DB session available)."""
    if not db or not tenant_id or not user_id:
        return
    from app.services.audit_service import write_audit

    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type="cezih",
        resource_id=resource_id,
        details=details,
    )


# Case clinical statuses a new posjeta/nalaz must NOT be linked to. Mirrors the
# eligible-status rule visit-create already enforces (active/remission/relapse/
# recurrence are linkable); a resolved/inactive/entered-in-error case is closed
# and CEZIH rejects authoring fresh clinical data against it.
TERMINAL_CASE_STATUSES = frozenset({"resolved", "inactive", "entered-in-error"})


async def assert_case_registered_on_cezih(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    case_id: str,
    *,
    require_active: bool = False,
) -> str:
    """Verify a case_id maps to a CEZIH-registered case before it is threaded
    into a posjeta↔slučaj or nalaz↔slučaj link.

    A ``CezihCase`` row exists only once the case has been dispatched to CEZIH;
    seed/local-only cases have no row at all. Emitting such an id into the FHIR
    link makes CEZIH unable to resolve the slučaj ("Posjeta nije povezana sa
    Slučajem") - the failure mode that sank patient #2 in the 2026-05-20
    provjera (seed CUID ``cmj2rchq5…``). Returns the id unchanged when valid so
    the verified-green identifier semantics are preserved; raises ``CezihError``
    otherwise (no silent fallback).

    When ``require_active`` is set (e-Nalaz send/replace), a registered case in a
    terminal clinical status (resolved/inactive/entered-in-error) is also
    rejected - authoring a fresh nalaz against a closed slučaj is invalid.
    """
    if not case_id:
        return case_id  # empty = "no linked case"; callers handle linkage rules
    from sqlalchemy import or_, select

    from app.models.cezih_case import CezihCase

    row = (
        await db.execute(
            select(CezihCase.clinical_status).where(
                CezihCase.tenant_id == tenant_id,
                CezihCase.patient_id == patient_id,
                or_(
                    CezihCase.local_case_id == case_id,
                    CezihCase.cezih_case_id == case_id,
                ),
            )
        )
    ).first()
    if not row:
        raise CezihError(
            "Odabrani slučaj nije registriran na CEZIH-u. Najprije otvorite "
            "slučaj na CEZIH-u, zatim povežite posjetu ili nalaz s njim."
        )
    if require_active and (row[0] or "").lower() in TERMINAL_CASE_STATUSES:
        raise CezihError(
            "Odabrani slučaj je zatvoren (riješen ili neaktivan). Otvorite "
            "slučaj ponovno ili odaberite aktivan slučaj prije slanja nalaza."
        )
    return case_id


async def assert_visit_registered_on_cezih(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    encounter_id: str,
) -> str:
    """Verify an encounter_id maps to a CEZIH-registered visit before it is
    threaded into a nalaz bundle - same fail-fast rule as
    ``assert_case_registered_on_cezih``: a stale/local-only id only fails at
    CEZIH after the ~14 s signing round-trip, producing a signed-but-rejected
    document. The local ``CezihVisit`` mirror is the source of truth for the
    visit list the UI offers, so an id without a mirror row was never offered.
    "finished" visits are fine (nalaz typically follows a concluded visit);
    only entered-in-error is terminal. Returns the id unchanged when valid,
    passes empty through (callers apply their own fallbacks)."""
    if not encounter_id:
        return encounter_id
    from sqlalchemy import select

    from app.models.cezih_visit import CezihVisit

    status = (
        await db.execute(
            select(CezihVisit.status).where(
                CezihVisit.tenant_id == tenant_id,
                CezihVisit.patient_id == patient_id,
                CezihVisit.cezih_visit_id == encounter_id,
            )
        )
    ).scalar_one_or_none()
    if status is None:
        raise CezihError(
            "Odabrana posjeta nije registrirana na CEZIH-u. Najprije otvorite "
            "posjetu na CEZIH-u, zatim povežite nalaz s njom."
        )
    if (status or "").lower() == "entered-in-error":
        raise CezihError(
            "Odabrana posjeta je stornirana na CEZIH-u. Odaberite aktivnu "
            "posjetu prije slanja nalaza."
        )
    return encounter_id


def _require_audit_params(
    db: AsyncSession | None,
    user_id: UUID | None,
    tenant_id: UUID | None,
) -> tuple[AsyncSession, UUID, UUID]:
    """Audit parameters are mandatory for traceability. Returns narrowed types.

    Also sets context so downstream helpers can:
    - route 8443 calls through the agent (tenant)
    - resolve per-user signing preference (user_id + db)
    """
    if not db or not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interna greška: nedostaju parametri za revizijski zapis CEZIH operacije.",
        )
    from app.services.cezih.client import (
        current_db_session,
        current_tenant_id,
        current_user_id,
    )

    current_tenant_id.set(tenant_id)
    current_user_id.set(user_id)
    current_db_session.set(db)
    return db, user_id, tenant_id


__all__ = [
    "_write_audit",
    "_require_audit_params",
    "_raise_cezih_error",
    "assert_case_registered_on_cezih",
    "assert_visit_registered_on_cezih",
]

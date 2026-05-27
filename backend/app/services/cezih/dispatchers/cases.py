"""CEZIH case dispatcher — case management with local DB mirror sync."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cezih import service as real_service
from app.services.cezih.dispatchers.common import _raise_cezih_error, _require_audit_params, _write_audit
from app.services.cezih.error_persistence import clear_cezih_error, record_cezih_error
from app.services.cezih.exceptions import CezihError
from app.services.cezih.ownership import load_tenant_cezih_identity

if TYPE_CHECKING:
    from app.services.cezih.ownership import TenantCezihIdentity


async def _lookup_local_case_id(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    case_id: str,
) -> UUID | None:
    """Resolve the CEZIH-side case identifier (or our local_case_id) to the
    local CezihCase.id so per-row error persistence can mark the right row."""
    if not db or not tenant_id or not case_id:
        return None
    try:
        from sqlalchemy import or_

        from app.models.cezih_case import CezihCase

        res = await db.execute(
            select(CezihCase.id).where(
                CezihCase.tenant_id == tenant_id,
                or_(
                    CezihCase.cezih_case_id == case_id,
                    CezihCase.local_case_id == case_id,
                ),
            )
        )
        row = res.first()
        return row[0] if row else None
    except SQLAlchemyError:
        return None


logger = logging.getLogger(__name__)


async def _lookup_patient_id(
    db: AsyncSession,
    tenant_id: UUID,
    patient_mbo: str,
) -> UUID | None:
    """Look up local Patient.id by any CEZIH identifier value.

    `patient_mbo` is now a misnomer — it holds whatever identifier value was used
    for the CEZIH call (MBO for Croatian, jedinstveni-id / EHIC / passport for
    foreigners). Try each column to find the owner.
    """
    from sqlalchemy import or_

    from app.models.patient import Patient

    result = await db.execute(
        select(Patient.id).where(
            Patient.tenant_id == tenant_id,
            or_(
                Patient.mbo == patient_mbo,
                Patient.cezih_patient_id == patient_mbo,
                Patient.ehic_broj == patient_mbo,
                Patient.broj_putovnice == patient_mbo,
            ),
        )
    )
    return result.scalar_one_or_none()


async def _persist_local_case_by_patient_id(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    patient_id: UUID,
    identifier_value: str,
    local_case_id: str,
    cezih_case_id: str,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str,
    note_text: str | None,
) -> None:
    """Persist a local CezihCase mirror row after successful CEZIH create."""
    if not db or not tenant_id:
        return
    try:
        from app.models.cezih_case import CezihCase

        db.add(
            CezihCase(
                tenant_id=tenant_id,
                patient_id=patient_id,
                patient_mbo=identifier_value,
                local_case_id=local_case_id,
                cezih_case_id=cezih_case_id or None,
                icd_code=icd_code,
                icd_display=icd_display or "",
                clinical_status="active",
                verification_status=verification_status or "unconfirmed",
                onset_date=onset_date,
                note=note_text,
            )
        )
        await db.flush()
    except (IntegrityError, OperationalError):
        logger.exception(
            "CezihCase mirror persist failed",
            extra={
                "tenant_id": str(tenant_id),
                "patient_id": str(patient_id),
                "cezih_case_id": cezih_case_id,
                "local_case_id": local_case_id,
            },
        )
        raise


def _serialize_case_row(row) -> dict:
    """Serialize a CezihCase ORM row to the CaseItem dict shape."""
    return {
        "case_id": row.cezih_case_id or row.local_case_id,
        "icd_code": row.icd_code,
        "icd_display": row.icd_display or "",
        "clinical_status": row.clinical_status or "",
        "verification_status": row.verification_status,
        "onset_date": row.onset_date,
        "abatement_date": row.abatement_date,
        "note": row.note,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_error_code": row.last_error_code,
        "last_error_display": row.last_error_display,
        "last_error_diagnostics": row.last_error_diagnostics,
        "last_error_at": row.last_error_at.isoformat() if row.last_error_at else None,
        "visited_clinical_statuses": row.visited_clinical_statuses or [],
        # True = this clinic created the case on CEZIH; False = mirrored from a
        # CEZIH read of a case created elsewhere (not eligible for visit linking).
        "registered": row.registered,
    }


async def _fetch_fresh_local_cases_by_patient(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    patient_id: UUID,
) -> list[dict]:
    """Fetch all local CezihCase mirror rows for this patient.

    No cutoff: CEZIH QEDm read-side indexing lag is often >30 minutes and
    sometimes indefinite in the test environment. Our DB is the authoritative
    record for cases this clinic created; CEZIH is merged in for cases
    created elsewhere.
    """
    if not db or not tenant_id:
        return []
    try:
        from app.models.cezih_case import CezihCase

        result = await db.execute(
            select(CezihCase)
            .where(
                CezihCase.tenant_id == tenant_id,
                CezihCase.patient_id == patient_id,
            )
            .order_by(CezihCase.created_at.desc())
        )
        rows = result.scalars().all()
        return [_serialize_case_row(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("Failed to read local CezihCase mirror: %s", exc)
        return []


async def _read_local_case_as_dict(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    case_id: str,
) -> dict | None:
    """Re-read a single CezihCase mirror row and return its CaseItem dict."""
    if not db or not tenant_id or not case_id:
        return None
    try:
        from sqlalchemy import or_

        from app.models.cezih_case import CezihCase

        row = (
            await db.execute(
                select(CezihCase).where(
                    CezihCase.tenant_id == tenant_id,
                    or_(
                        CezihCase.cezih_case_id == case_id,
                        CezihCase.local_case_id == case_id,
                    ),
                )
            )
        ).scalar_one_or_none()
        return _serialize_case_row(row) if row else None
    except SQLAlchemyError as exc:
        logger.warning("Failed to re-read local CezihCase row for response: %s", exc)
        return None


async def _upsert_cezih_case_from_response(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    identifier_value: str,
    remote: dict,
    identity: TenantCezihIdentity,
) -> None:
    """Insert or update a cezih_cases row from a CEZIH QEDm Condition response.

    Mirrors `_upsert_cezih_visit_from_response`: every case CEZIH returns is
    persisted so externally-created cases stay visible even when CEZIH's QEDm
    read side later lags or returns empty.

    `registered` ("ours") is decided by IDENTITY, not by local-row presence: a
    Condition has no organisation, so a case is ours when its recorder/asserter
    HZJZ matches one of the tenant's doctors (`identity.owns`). This is robust to
    lost mirror rows (DB resets) that previously mislabelled our own cases as
    external.

    Field ownership differs from visits, because for a case WE created the local
    mirror is authoritative (QEDm lags our own action messages by minutes):
    - Row exists & registered=True (ours): leave clinical_status/verification_
      status/icd/note untouched; only backfill NULL fields (e.g. abatement_date).
      Never demoted to external (we know we created it).
    - Row exists & registered=False (external): refresh all fields from CEZIH and
      re-classify `registered` from identity (self-heals a mislabelled own case).
    - No row: insert with `registered` = whether the case is ours by identity.

    Remote cases without a `case_id` (no `identifikator-slucaja`) cannot be
    tracked and are skipped.
    """
    case_id = (remote.get("case_id") or "").strip()
    if not case_id:
        logger.debug("Skipping CEZIH case with empty case_id: %r", remote)
        return
    is_ours = identity.owns(practitioner_ids=remote.get("practitioner_ids") or ())
    try:
        from sqlalchemy import or_

        from app.models.cezih_case import CezihCase

        result = await db.execute(
            select(CezihCase).where(
                CezihCase.tenant_id == tenant_id,
                or_(
                    CezihCase.cezih_case_id == case_id,
                    CezihCase.local_case_id == case_id,
                ),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            db.add(
                CezihCase(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    patient_mbo=identifier_value,
                    local_case_id=case_id,
                    cezih_case_id=case_id,
                    icd_code=remote.get("icd_code") or "",
                    icd_display=remote.get("icd_display") or "",
                    clinical_status=remote.get("clinical_status") or None,
                    verification_status=remote.get("verification_status") or "unconfirmed",
                    onset_date=remote.get("onset_date") or "",
                    abatement_date=remote.get("abatement_date") or None,
                    note=remote.get("note") or None,
                    registered=is_ours,
                )
            )
        elif not row.registered:
            # Mirrored case we did not create locally — CEZIH is authoritative,
            # refresh, and re-classify ownership from identity (an own case whose
            # local row was lost flips back to registered=True here).
            row.registered = is_ours
            if not row.cezih_case_id:
                row.cezih_case_id = case_id
            row.icd_code = remote.get("icd_code") or row.icd_code
            row.icd_display = remote.get("icd_display") or row.icd_display
            row.clinical_status = remote.get("clinical_status") or row.clinical_status
            if remote.get("verification_status"):
                row.verification_status = remote["verification_status"]
            row.onset_date = remote.get("onset_date") or row.onset_date
            row.abatement_date = remote.get("abatement_date") or None
            if remote.get("note"):
                row.note = remote["note"]
        else:
            # Case this clinic created — local is authoritative for status/note.
            # Only backfill the CEZIH-assigned id and NULL-only fields.
            if not row.cezih_case_id:
                row.cezih_case_id = case_id
            if not row.abatement_date and remote.get("abatement_date"):
                row.abatement_date = remote["abatement_date"]
    except (IntegrityError, OperationalError):
        logger.exception(
            "CezihCase mirror upsert failed",
            extra={
                "tenant_id": str(tenant_id),
                "patient_id": str(patient_id),
                "case_id": case_id,
            },
        )
        raise


# Map CEZIH case action (frontend keyword) → resulting clinical_status.
_CASE_ACTION_TO_STATUS: dict[str, str] = {
    "remission": "remission",
    "relapse": "relapse",
    "resolve": "resolved",
    "reopen": "active",
}


async def _update_local_case(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    case_id: str,
    *,
    clinical_status: str | None = None,
    verification_status: str | None = None,
    icd_code: str | None = None,
    icd_display: str | None = None,
    onset_date: str | None = None,
    abatement_date: str | None = None,
    clear_abatement: bool = False,
    note: str | None = None,
    visited_clinical_statuses: list[str] | None = None,
) -> None:
    """Patch the local CezihCase mirror if it exists."""
    if not db or not tenant_id or not case_id:
        return
    try:
        from sqlalchemy import or_

        from app.models.cezih_case import CezihCase

        result = await db.execute(
            select(CezihCase).where(
                CezihCase.tenant_id == tenant_id,
                or_(
                    CezihCase.cezih_case_id == case_id,
                    CezihCase.local_case_id == case_id,
                ),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        if clinical_status is not None:
            row.clinical_status = clinical_status
        if verification_status is not None:
            row.verification_status = verification_status
        if icd_code is not None:
            row.icd_code = icd_code
        if icd_display is not None:
            row.icd_display = icd_display
        if onset_date is not None:
            row.onset_date = onset_date
        if clear_abatement:
            row.abatement_date = None
        elif abatement_date is not None:
            row.abatement_date = abatement_date
        if note is not None:
            row.note = note
        if visited_clinical_statuses is not None:
            row.visited_clinical_statuses = visited_clinical_statuses
        await db.flush()
    except (IntegrityError, OperationalError):
        logger.exception(
            "CezihCase mirror update failed",
            extra={
                "tenant_id": str(tenant_id),
                "case_id": case_id,
            },
        )
        raise


async def dispatch_retrieve_cases(
    patient_id: UUID,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> list[dict]:
    """Retrieve cases for a patient from CEZIH (TC15)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    try:
        system_uri, value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    # Local-first, like dispatch_list_visits: query CEZIH, persist every returned
    # case into the mirror, then return the mirror. If CEZIH fails we still serve
    # the mirror so the table stays useful during a CEZIH/agent outage.
    remote: list[dict] = []
    try:
        remote = await real_service.retrieve_cases(http_client, system_uri, value)
    except CezihError as e:
        logger.warning(
            "CEZIH retrieve_cases failed for patient %s — serving local mirror only: %s",
            patient_id,
            e,
        )
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="case_retrieve",
        details={"patient_id": str(patient_id), "identifier_system": system_uri},
    )
    identity = await load_tenant_cezih_identity(db, tenant_id)
    for row in remote:
        await _upsert_cezih_case_from_response(db, tenant_id, patient_id, value, row, identity)
    try:
        await db.flush()
    except (IntegrityError, OperationalError):
        logger.exception(
            "CezihCase mirror flush failed after retrieve upsert",
            extra={"tenant_id": str(tenant_id), "patient_id": str(patient_id)},
        )
        raise
    return await _fetch_fresh_local_cases_by_patient(db, tenant_id, patient_id)


async def dispatch_create_case(
    patient_id: UUID,
    practitioner_id: str,
    org_code: str,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str = "unconfirmed",
    note_text: str | None = None,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    source_oid: str | None = None,
) -> dict:
    """Create a new case on CEZIH (TC16)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    try:
        identifier_system, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    try:
        result = await real_service.create_case(
            http_client,
            identifier_value,
            practitioner_id,
            org_code,
            icd_code,
            icd_display,
            onset_date,
            verification_status,
            note_text,
            source_oid=source_oid,
            identifier_system=identifier_system,
        )
    except CezihError as e:
        # create failed → no local CezihCase yet; dialog + toast are the signal.
        _raise_cezih_error(e)
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="case_create",
        details={"patient_id": str(patient_id), "icd": icd_code},
    )
    await _persist_local_case_by_patient_id(
        db,
        tenant_id,
        patient_id,
        identifier_value,
        local_case_id=result.get("local_case_id") or "",
        cezih_case_id=result.get("cezih_case_id") or "",
        icd_code=icd_code,
        icd_display=icd_display,
        onset_date=onset_date,
        verification_status=verification_status,
        note_text=note_text,
    )
    return result


async def dispatch_update_case(
    case_id: str,
    patient_id: UUID,
    practitioner_id: str,
    org_code: str,
    action: str,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    source_oid: str | None = None,
) -> dict:
    """Update a case on CEZIH (TC17) or create recurring case."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")
    try:
        identifier_system, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    # For create_recurring the parent case is the row where the doctor
    # initiated retry, so mark errors on it. For other transitions mark the
    # target case.
    local_case_id = await _lookup_local_case_id(db, tenant_id, case_id)

    try:
        if action == "create_recurring":
            # 2.2 Ponavljajući creates a NEW case inheriting the parent's ICD.
            # Parent data comes from our local DB mirror — CEZIH QEDm retrieve
            # is flaky on the test env and a local row is always authoritative
            # for fields we need (ICD + verification).
            from sqlalchemy import or_

            from app.models.cezih_case import CezihCase

            parent_row = (
                await db.execute(
                    select(CezihCase).where(
                        CezihCase.tenant_id == tenant_id,
                        or_(
                            CezihCase.cezih_case_id == case_id,
                            CezihCase.local_case_id == case_id,
                        ),
                    )
                )
            ).scalar_one_or_none()
            if parent_row is None:
                raise CezihError(f"Roditeljski slučaj {case_id} nije pronađen za pacijenta.")
            result = await real_service.create_recurring_case(
                http_client,
                identifier_value,
                practitioner_id,
                org_code,
                icd_code=parent_row.icd_code or "",
                icd_display=parent_row.icd_display or "",
                onset_date=datetime.now(UTC).strftime("%Y-%m-%d"),
                verification_status=parent_row.verification_status or "confirmed",
                source_oid=source_oid,
                identifier_system=identifier_system,
            )
        else:
            result = await real_service.update_case(
                http_client,
                case_id,
                identifier_value,
                practitioner_id,
                org_code,
                action,
                source_oid=source_oid,
                identifier_system=identifier_system,
            )
    except CezihError as e:
        await record_cezih_error("case", local_case_id, tenant_id, e)
        _raise_cezih_error(e)
    await clear_cezih_error("case", local_case_id, tenant_id, session=db)
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action=f"case_{action}",
        details={"case_id": case_id, "action": action, "patient_id": str(patient_id)},
    )
    if action == "create_recurring":
        assert parent_row is not None  # guarded by CezihError above
        new_cezih_id = result.get("cezih_case_id") or ""
        # ICD + verification come from parent_row (already fetched above);
        # create_recurring_case doesn't echo those in its return dict.
        await _persist_local_case_by_patient_id(
            db,
            tenant_id,
            patient_id,
            identifier_value,
            local_case_id=result.get("local_case_id") or "",
            cezih_case_id=new_cezih_id,
            icd_code=parent_row.icd_code or "",
            icd_display=parent_row.icd_display or "",
            onset_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            verification_status=parent_row.verification_status or "confirmed",
            note_text=None,
        )
        if new_cezih_id:
            await _update_local_case(
                db,
                tenant_id,
                new_cezih_id,
                clinical_status="recurrence",
            )
        child_case = await _read_local_case_as_dict(db, tenant_id, new_cezih_id) if new_cezih_id else None
        return {"success": True, "case_id": new_cezih_id or None, "action": "create_recurring", "case": child_case}
    else:
        new_status = _CASE_ACTION_TO_STATUS.get(action)
        if new_status:
            # Record the departing clinical status before overwriting.
            # Only statuses that are action targets (remission, relapse,
            # resolved) need tracking - they may be blocked on re-entry.
            visited: list[str] = []
            old_status: str | None = None
            recordable = {"remission", "relapse", "resolved"}
            if local_case_id:
                from sqlalchemy import or_

                from app.models.cezih_case import CezihCase

                cur = (
                    await db.execute(
                        select(CezihCase).where(
                            CezihCase.tenant_id == tenant_id,
                            or_(
                                CezihCase.cezih_case_id == case_id,
                                CezihCase.local_case_id == case_id,
                            ),
                        )
                    )
                ).scalar_one_or_none()
                if cur:
                    visited = list(cur.visited_clinical_statuses or [])
                    old_status = cur.clinical_status
            # For reopen: restore the status from before "resolved" was set.
            # visited at this point still contains the pre-resolve history.
            if action == "reopen":
                pre_resolve = [s for s in visited if s != "resolved"]
                if pre_resolve:
                    new_status = pre_resolve[-1]
            if old_status and old_status in recordable and old_status not in visited:
                visited.append(old_status)
            await _update_local_case(
                db,
                tenant_id,
                case_id,
                clinical_status=new_status,
                abatement_date=(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00") if action == "resolve" else None),
                clear_abatement=(action == "reopen"),
                visited_clinical_statuses=visited,
            )
    result["case"] = await _read_local_case_as_dict(db, tenant_id, case_id)
    return result


async def dispatch_update_case_data(
    case_id: str,
    patient_id: UUID,
    practitioner_id: str,
    org_code: str,
    *,
    current_clinical_status: str | None = None,
    verification_status: str | None = None,
    icd_code: str | None = None,
    icd_display: str | None = None,
    onset_date: str | None = None,
    abatement_date: str | None = None,
    note_text: str | None = None,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    source_oid: str | None = None,
) -> dict:
    """Update case data on CEZIH (2.6 Data update)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    try:
        identifier_system, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    local_case_id = await _lookup_local_case_id(db, tenant_id, case_id)

    try:
        result = await real_service.update_case_data(
            http_client,
            case_id,
            identifier_value,
            practitioner_id,
            org_code,
            current_clinical_status=current_clinical_status,
            verification_status=verification_status,
            icd_code=icd_code,
            icd_display=icd_display,
            onset_date=onset_date,
            abatement_date=abatement_date,
            note_text=note_text,
            source_oid=source_oid,
            identifier_system=identifier_system,
        )
    except CezihError as e:
        await record_cezih_error("case", local_case_id, tenant_id, e)
        _raise_cezih_error(e)

    await clear_cezih_error("case", local_case_id, tenant_id, session=db)
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="case_update_data",
        details={"case_id": case_id},
    )

    await _update_local_case(
        db,
        tenant_id,
        case_id,
        clinical_status=current_clinical_status,
        verification_status=verification_status,
        icd_code=icd_code,
        icd_display=icd_display,
        onset_date=onset_date,
        abatement_date=abatement_date,
        note=note_text,
    )
    return result


__all__ = [
    "_lookup_patient_id",
    "_lookup_local_case_id",
    "_persist_local_case_by_patient_id",
    "_fetch_fresh_local_cases_by_patient",
    "_upsert_cezih_case_from_response",
    "_update_local_case",
    "dispatch_retrieve_cases",
    "dispatch_create_case",
    "dispatch_update_case",
    "dispatch_update_case_data",
]

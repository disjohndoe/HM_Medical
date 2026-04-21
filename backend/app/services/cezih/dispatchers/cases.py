"""CEZIH case dispatcher — case management with local DB mirror sync."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cezih import service as real_service
from app.services.cezih.dispatchers.common import _raise_cezih_error, _require_audit_params, _write_audit
from app.services.cezih.error_persistence import clear_cezih_error, record_cezih_error
from app.services.cezih.exceptions import CezihError


async def _lookup_local_case_id(
    db: AsyncSession | None, tenant_id: UUID | None, case_id: str,
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
    db: AsyncSession, tenant_id: UUID, patient_mbo: str,
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
        db.add(CezihCase(
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
        ))
        await db.flush()
    except (IntegrityError, OperationalError) as exc:
        logger.warning("Failed to persist local CezihCase mirror: %s", exc)


async def _fetch_fresh_local_cases_by_patient(
    db: AsyncSession | None, tenant_id: UUID | None, patient_id: UUID,
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
            select(CezihCase).where(
                CezihCase.tenant_id == tenant_id,
                CezihCase.patient_id == patient_id,
            ).order_by(CezihCase.created_at.desc())
        )
        rows = result.scalars().all()
        return [
            {
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
            }
            for row in rows
        ]
    except SQLAlchemyError as exc:
        logger.warning("Failed to read local CezihCase mirror: %s", exc)
        return []


def _merge_with_local(
    remote: list[dict], local: list[dict], id_key: str,
) -> list[dict]:
    """Merge local mirror rows into the remote list (cases).

    - Rows present in both → prefer the *local* copy for fields it owns
      (clinical_status/verification_status for cases). CEZIH's QEDm read
      side lags action messages by minutes, so its cached state is often
      staler than our mirror.
    - Rows only in local → prepend (CEZIH hasn't caught up to the create yet).
    - Rows only in remote → pass through unchanged.
    """
    local_by_id = {row[id_key]: row for row in local if row.get(id_key)}
    merged: list[dict] = []
    seen_local = set()
    for row in remote:
        rid = row.get(id_key)
        lrow = local_by_id.get(rid) if rid else None
        if lrow is not None:
            merged.append({**row, **lrow})
            seen_local.add(rid)
        else:
            merged.append(row)
    extra = [row for rid, row in local_by_id.items() if rid not in seen_local]
    return extra + merged


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
) -> None:
    """Patch the local CezihCase mirror if it exists. Non-fatal on failure."""
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
        await db.flush()
    except (IntegrityError, OperationalError) as exc:
        logger.warning("Failed to update local CezihCase mirror: %s", exc)


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

    try:
        result = await real_service.retrieve_cases(http_client, system_uri, value)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(
        db, tenant_id, user_id, action="case_retrieve",
        details={"patient_id": str(patient_id), "identifier_system": system_uri},
    )
    local = await _fetch_fresh_local_cases_by_patient(db, tenant_id, patient_id)
    return _merge_with_local(result, local, id_key="case_id")


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
            http_client, identifier_value, practitioner_id, org_code,
            icd_code, icd_display, onset_date, verification_status, note_text,
            source_oid=source_oid,
            identifier_system=identifier_system,
        )
    except CezihError as e:
        # create failed → no local CezihCase yet; dialog + toast are the signal.
        _raise_cezih_error(e)
    await _write_audit(
        db, tenant_id, user_id, action="case_create",
        details={"patient_id": str(patient_id), "icd": icd_code},
    )
    await _persist_local_case_by_patient_id(
        db, tenant_id, patient_id, identifier_value,
        local_case_id=result.get("local_case_id") or "",
        cezih_case_id=result.get("cezih_case_id") or "",
        icd_code=icd_code, icd_display=icd_display,
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
            from app.models.cezih_case import CezihCase
            from sqlalchemy import or_
            parent_row = (await db.execute(
                select(CezihCase).where(
                    CezihCase.tenant_id == tenant_id,
                    or_(
                        CezihCase.cezih_case_id == case_id,
                        CezihCase.local_case_id == case_id,
                    ),
                )
            )).scalar_one_or_none()
            if parent_row is None:
                raise CezihError(f"Roditeljski slučaj {case_id} nije pronađen za pacijenta.")
            result = await real_service.create_recurring_case(
                http_client, identifier_value, practitioner_id, org_code,
                icd_code=parent_row.icd_code or "",
                icd_display=parent_row.icd_display or "",
                onset_date=datetime.now(UTC).strftime("%Y-%m-%d"),
                verification_status=parent_row.verification_status or "confirmed",
                source_oid=source_oid,
                identifier_system=identifier_system,
            )
        else:
            result = await real_service.update_case(
                http_client, case_id, identifier_value, practitioner_id, org_code, action,
                source_oid=source_oid,
                identifier_system=identifier_system,
            )
    except CezihError as e:
        await record_cezih_error("case", local_case_id, tenant_id, e)
        _raise_cezih_error(e)
    await clear_cezih_error("case", local_case_id, tenant_id, session=db)
    await _write_audit(
        db, tenant_id, user_id, action=f"case_{action}",
        details={"case_id": case_id, "action": action, "patient_id": str(patient_id)},
    )
    if action == "create_recurring":
        new_cezih_id = result.get("cezih_case_id") or ""
        # ICD + verification come from parent_row (already fetched above);
        # create_recurring_case doesn't echo those in its return dict.
        await _persist_local_case_by_patient_id(
            db, tenant_id, patient_id, identifier_value,
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
                db, tenant_id, new_cezih_id, clinical_status="recurrence",
            )
        return {"success": True, "case_id": new_cezih_id or None, "action": "create_recurring"}
    else:
        new_status = _CASE_ACTION_TO_STATUS.get(action)
        if new_status:
            await _update_local_case(
                db, tenant_id, case_id,
                clinical_status=new_status,
                abatement_date=(
                    datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    if action == "resolve" else None
                ),
                clear_abatement=(action == "reopen"),
            )
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
            http_client, case_id, identifier_value, practitioner_id, org_code,
            current_clinical_status=current_clinical_status,
            verification_status=verification_status,
            icd_code=icd_code, icd_display=icd_display,
            onset_date=onset_date, abatement_date=abatement_date, note_text=note_text,
            source_oid=source_oid,
            identifier_system=identifier_system,
        )
    except CezihError as e:
        await record_cezih_error("case", local_case_id, tenant_id, e)
        _raise_cezih_error(e)

    await clear_cezih_error("case", local_case_id, tenant_id, session=db)
    await _write_audit(
        db, tenant_id, user_id, action="case_update_data",
        details={"case_id": case_id},
    )

    await _update_local_case(
        db, tenant_id, case_id,
        clinical_status=current_clinical_status,
        verification_status=verification_status,
        icd_code=icd_code, icd_display=icd_display,
        onset_date=onset_date, abatement_date=abatement_date,
        note=note_text,
    )
    return result


__all__ = [
    "_lookup_patient_id",
    "_lookup_local_case_id",
    "_persist_local_case_by_patient_id",
    "_fetch_fresh_local_cases_by_patient",
    "_merge_with_local",
    "_update_local_case",
    "dispatch_retrieve_cases",
    "dispatch_create_case",
    "dispatch_update_case",
    "dispatch_update_case_data",
]

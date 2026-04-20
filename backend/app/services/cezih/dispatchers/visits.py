"""CEZIH visit dispatcher — visit management with local DB mirror sync."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cezih import service as real_service
from app.services.cezih.dispatchers.cases import _lookup_patient_id
from app.services.cezih.dispatchers.common import _raise_cezih_error, _require_audit_params, _write_audit
from app.services.cezih.error_persistence import clear_cezih_error, record_cezih_error
from app.services.cezih.exceptions import CezihError


async def _lookup_local_visit_id(
    db: AsyncSession | None, tenant_id: UUID | None, cezih_visit_id: str,
) -> UUID | None:
    """Resolve the CEZIH-side visit identifier to our local CezihVisit.id so
    per-row error persistence can mark the right row."""
    if not db or not tenant_id or not cezih_visit_id:
        return None
    try:
        from app.models.cezih_visit import CezihVisit
        res = await db.execute(
            select(CezihVisit.id).where(
                CezihVisit.tenant_id == tenant_id,
                CezihVisit.cezih_visit_id == cezih_visit_id,
            )
        )
        row = res.first()
        return row[0] if row else None
    except SQLAlchemyError:
        return None

logger = logging.getLogger(__name__)

# How long to keep local rows as "fresh" in the merge window.
_LOCAL_MIRROR_WINDOW_MINUTES = 10


async def _persist_local_visit_by_patient_id(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    patient_id: UUID,
    identifier_value: str,
    cezih_visit_id: str,
    status_str: str,
    admission_type: str | None,
    tip_posjete: str | None = None,
    vrsta_posjete: str | None = None,
    reason: str | None = None,
) -> None:
    """Persist a local CezihVisit mirror row after successful CEZIH create."""
    if not db or not tenant_id:
        return
    try:
        from app.models.cezih_visit import CezihVisit
        db.add(CezihVisit(
            tenant_id=tenant_id,
            patient_id=patient_id,
            patient_mbo=identifier_value,
            cezih_visit_id=cezih_visit_id or None,
            status=status_str or "in-progress",
            admission_type=admission_type,
            tip_posjete=tip_posjete,
            vrsta_posjete=vrsta_posjete,
            reason=reason,
            period_start=datetime.now(UTC),
        ))
        await db.flush()
    except (IntegrityError, OperationalError) as exc:
        logger.warning("Failed to persist local CezihVisit mirror: %s", exc)


# Tip posjete codes -> display label (mirrors TIP_POSJETE_MAP in message_builder)
_TIP_POSJETE_LABELS = {
    "1": "Posjeta LOM",
    "2": "Posjeta SKZZ",
    "3": "Hospitalizacija",
}
_VRSTA_POSJETE_LABELS = {
    "1": "Pacijent prisutan",
    "2": "Pacijent udaljeno prisutan",
    "3": "Pacijent nije prisutan",
}


async def _fetch_fresh_local_visits_by_patient(
    db: AsyncSession | None, tenant_id: UUID | None, patient_id: UUID,
) -> list[dict]:
    """Fetch local CezihVisit mirror rows.

    Returns ALL rows (no time window) — tip_posjete persists indefinitely
    because CEZIH QEDm strips Encounter.type on read, making our mirror the
    only source of truth for that field. Each row carries `_fresh` = True
    when created within _LOCAL_MIRROR_WINDOW_MINUTES so the merger knows
    whether to override CEZIH-authoritative fields (status, period_end).
    """
    if not db or not tenant_id:
        return []
    try:
        from datetime import timedelta

        from app.models.cezih_visit import CezihVisit

        cutoff = datetime.now(UTC) - timedelta(minutes=_LOCAL_MIRROR_WINDOW_MINUTES)
        result = await db.execute(
            select(CezihVisit).where(
                CezihVisit.tenant_id == tenant_id,
                CezihVisit.patient_id == patient_id,
            ).order_by(CezihVisit.created_at.desc())
        )
        rows = result.scalars().all()
        out = []
        for row in rows:
            created_at = row.created_at
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            fresh = created_at is not None and created_at >= cutoff
            tip = row.tip_posjete or ""
            vrsta = row.vrsta_posjete or ""
            out.append({
                "visit_id": row.cezih_visit_id or "",
                "patient_mbo": row.patient_mbo,
                "status": row.status,
                "visit_type": row.admission_type or "",
                "visit_type_display": None,
                "vrsta_posjete": vrsta,
                "vrsta_posjete_display": _VRSTA_POSJETE_LABELS.get(vrsta) if vrsta else None,
                "tip_posjete": tip,
                "tip_posjete_display": _TIP_POSJETE_LABELS.get(tip) if tip else None,
                "reason": row.reason,
                "period_start": row.period_start.isoformat() if row.period_start else None,
                "period_end": row.period_end.isoformat() if row.period_end else None,
                "_fresh": fresh,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "last_error_code": row.last_error_code,
                "last_error_display": row.last_error_display,
                "last_error_diagnostics": row.last_error_diagnostics,
                "last_error_at": row.last_error_at.isoformat() if row.last_error_at else None,
            })
        return out
    except SQLAlchemyError as exc:
        logger.warning("Failed to read local CezihVisit mirror: %s", exc)
        return []


# Visit fields that only exist locally (CEZIH never returns them)
_VISIT_LOCAL_ONLY_FIELDS = (
    "tip_posjete", "tip_posjete_display", "vrsta_posjete", "vrsta_posjete_display",
    "updated_at",
    "last_error_code", "last_error_display", "last_error_diagnostics", "last_error_at",
)
# Visit fields where CEZIH is authoritative, but we fall back to the mirror
# when CEZIH's QEDm response leaves the field empty. QEDm read-back regularly
# strips Encounter.reasonCode, so the user-entered reason is more reliable.
_VISIT_LOCAL_FALLBACK_FIELDS = ("reason",)
# Visit fields where CEZIH is authoritative, but our mirror overrides during
# the freshness window to mask QEDm read-side lag
_VISIT_FRESH_OVERRIDE_FIELDS = ("status", "period_end")


def _merge_visits_with_local(
    remote: list[dict], local: list[dict],
) -> list[dict]:
    """Merge local visit mirror into remote list with field-specific rules.

    Persistent fields (tip_posjete, updated_at) are overlaid from local for
    ALL matching rows — CEZIH never returns them. State fields (status,
    period_end) are overlaid only when the local row is fresh (<10 min old),
    to avoid masking changes made by other systems on older visits.
    Local-only rows are included only when fresh.
    """
    local_by_id = {row["visit_id"]: row for row in local if row.get("visit_id")}
    merged: list[dict] = []
    seen_local = set()
    for row in remote:
        rid = row.get("visit_id")
        lrow = local_by_id.get(rid) if rid else None
        if lrow is None:
            merged.append(row)
            continue
        seen_local.add(rid)
        combined = dict(row)
        for field in _VISIT_LOCAL_ONLY_FIELDS:
            if lrow.get(field) is not None:
                combined[field] = lrow[field]
        for field in _VISIT_LOCAL_FALLBACK_FIELDS:
            if not combined.get(field) and lrow.get(field):
                combined[field] = lrow[field]
        if lrow.get("_fresh"):
            for field in _VISIT_FRESH_OVERRIDE_FIELDS:
                if field in lrow:
                    combined[field] = lrow[field]
        merged.append(combined)
    # Local-only rows that CEZIH hasn't caught up on yet
    extra = [
        {k: v for k, v in row.items() if k != "_fresh"}
        for rid, row in local_by_id.items()
        if rid not in seen_local and row.get("_fresh")
    ]
    return extra + merged


async def _update_local_visit(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    visit_id: str,
    *,
    patient_mbo: str | None = None,
    status_str: str | None = None,
    tip_posjete: str | None = None,
    vrsta_posjete: str | None = None,
    admission_type: str | None = None,
    reason: str | None = None,
    set_period_end: bool = False,
    clear_period_end: bool = False,
) -> None:
    """Upsert the local CezihVisit mirror for this visit.

    If no row exists yet (e.g. the visit was created before migration 031
    recreated the mirror table, or before any mirror code ran), insert a
    fresh row so the edit is reflected. Non-fatal on failure.
    """
    if not db or not tenant_id or not visit_id:
        return
    try:
        from app.models.cezih_visit import CezihVisit

        result = await db.execute(
            select(CezihVisit).where(
                CezihVisit.tenant_id == tenant_id,
                CezihVisit.cezih_visit_id == visit_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            if not patient_mbo:
                return
            patient_id = await _lookup_patient_id(db, tenant_id, patient_mbo)
            if patient_id is None:
                return
            row = CezihVisit(
                tenant_id=tenant_id,
                patient_id=patient_id,
                patient_mbo=patient_mbo,
                cezih_visit_id=visit_id,
                status=status_str or "in-progress",
                admission_type=admission_type,
                tip_posjete=tip_posjete,
                vrsta_posjete=vrsta_posjete,
                reason=reason,
                period_start=datetime.now(UTC),
            )
            if set_period_end:
                row.period_end = datetime.now(UTC)
            db.add(row)
        else:
            if status_str is not None:
                row.status = status_str
            if admission_type is not None:
                row.admission_type = admission_type
            if tip_posjete is not None:
                row.tip_posjete = tip_posjete
            if vrsta_posjete is not None:
                row.vrsta_posjete = vrsta_posjete
            if reason is not None:
                row.reason = reason
            if set_period_end:
                row.period_end = datetime.now(UTC)
            if clear_period_end:
                row.period_end = None
        await db.flush()
    except (IntegrityError, OperationalError) as exc:
        logger.warning("Failed to update local CezihVisit mirror: %s", exc)


def _parse_visit_response(result: dict) -> dict:
    """Parse CEZIH FHIR Bundle response into VisitResponse format."""
    # Extract Encounter from response Bundle entries
    visit_id = ""
    encounter_status = "in-progress"
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Encounter":
            visit_id = resource.get("id", "")
            for ident in resource.get("identifier", []):
                if "identifikator-posjete" in (ident.get("system") or ""):
                    visit_id = ident.get("value", visit_id)
                    break
            encounter_status = resource.get("status", "in-progress")
            break
        if resource.get("resourceType") == "MessageHeader":
            for focus in resource.get("focus", []):
                ref = focus.get("reference", "")
                if "Encounter" in ref:
                    visit_id = ref.rsplit("/", 1)[-1]
    return {"success": True, "visit_id": visit_id, "status": encounter_status}


async def dispatch_create_visit(
    patient_id: UUID,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
) -> dict:
    """Create a new visit on CEZIH (TC12)."""
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
        from app.services.cezih.client import CezihFhirClient
        from app.services.cezih.message_builder import (
            add_signature,
            build_encounter_create,
            build_message_bundle,
        )
        fhir_client = CezihFhirClient(http_client)
        if not practitioner_id:
            raise CezihError("HZJZ ID djelatnika nije postavljen. Potrebno je za CEZIH potpisivanje.")
        encounter = build_encounter_create(
            patient_mbo=identifier_value, identifier_system=identifier_system,
            nacin_prijema=nacin_prijema,
            vrsta_posjete=vrsta_posjete, tip_posjete=tip_posjete,
            reason=reason, practitioner_id=practitioner_id, org_code=org_code or "",
        )
        bundle = await build_message_bundle(
            "1.1", encounter, sender_org_code=org_code, author_practitioner_id=practitioner_id,
            source_oid=source_oid, profile_urls=None,
        )
        bundle = await add_signature(bundle, practitioner_id, http_client=http_client)
        result = await fhir_client.process_message("encounter-services/api/v1", bundle)
    except CezihError as e:
        # create failed → no row exists yet, nothing to persist error on.
        # Toast + dialog-stays-open is the signal to the user.
        _raise_cezih_error(e)
    await _write_audit(
        db, tenant_id, user_id, action="visit_create",
        details={"patient_id": str(patient_id), "nacin_prijema": nacin_prijema},
    )
    resp = _parse_visit_response(result)
    resp["nacin_prijema"] = nacin_prijema
    resp["vrsta_posjete"] = vrsta_posjete
    resp["tip_posjete"] = tip_posjete
    await _persist_local_visit_by_patient_id(
        db, tenant_id, patient_id, identifier_value,
        cezih_visit_id=resp.get("visit_id") or "",
        status_str=resp.get("status") or "in-progress",
        admission_type=nacin_prijema,
        tip_posjete=tip_posjete,
        vrsta_posjete=vrsta_posjete,
        reason=reason,
    )
    return resp


async def dispatch_update_visit(
    visit_id: str,
    patient_id: UUID,
    reason: str | None = None,
    *,
    nacin_prijema: str | None = None,
    vrsta_posjete: str | None = None,
    tip_posjete: str | None = None,
    diagnosis_case_id: str | None = None,
    additional_practitioner_id: str | None = None,
    period_start: str | None = None,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
) -> dict:
    """Update a visit on CEZIH (TC13)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient
    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")
    try:
        identifier_system, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    local_visit_id = await _lookup_local_visit_id(db, tenant_id, visit_id)

    try:
        from app.services.cezih.client import CezihFhirClient
        from app.services.cezih.message_builder import (
            add_signature,
            build_encounter_update,
            build_message_bundle,
        )
        fhir_client = CezihFhirClient(http_client)
        if not practitioner_id:
            raise CezihError("HZJZ ID djelatnika nije postavljen. Potrebno je za CEZIH potpisivanje.")
        encounter = build_encounter_update(
            encounter_id=visit_id,
            patient_mbo=identifier_value,
            identifier_system=identifier_system,
            nacin_prijema=nacin_prijema or "6",
            vrsta_posjete=vrsta_posjete or "1",
            tip_posjete=tip_posjete or "1",
            reason=reason,
            practitioner_id=practitioner_id,
            additional_practitioner_id=additional_practitioner_id,
            org_code=org_code or "",
            diagnosis_case_id=diagnosis_case_id,
            period_start=period_start,
        )
        bundle = await build_message_bundle(
            "1.2", encounter,
            sender_org_code=org_code, author_practitioner_id=practitioner_id,
            source_oid=source_oid, profile_urls=None,
        )
        bundle = await add_signature(bundle, practitioner_id, http_client=http_client)
        result = await fhir_client.process_message("encounter-services/api/v1", bundle)
    except CezihError as e:
        await record_cezih_error("visit", local_visit_id, tenant_id, e)
        _raise_cezih_error(e)
    await clear_cezih_error("visit", local_visit_id, tenant_id, session=db)
    await _write_audit(
        db, tenant_id, user_id, action="visit_update",
        details={"visit_id": visit_id, "patient_id": str(patient_id)},
    )
    resp = _parse_visit_response(result)
    if nacin_prijema:
        resp["nacin_prijema"] = nacin_prijema
    if vrsta_posjete:
        resp["vrsta_posjete"] = vrsta_posjete
    if tip_posjete:
        resp["tip_posjete"] = tip_posjete
    await _update_local_visit(
        db, tenant_id, visit_id,
        patient_mbo=identifier_value,
        tip_posjete=tip_posjete,
        vrsta_posjete=vrsta_posjete,
        admission_type=nacin_prijema,
        reason=reason,
    )
    return resp


async def dispatch_visit_action(
    visit_id: str,
    action: str,
    patient_id: UUID,
    *,
    nacin_prijema: str = "6",
    period_start: str | None = None,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
) -> dict:
    """Perform an action on a visit (TC14): close, storno, reopen."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient
    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")
    try:
        _sys, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    local_visit_id = await _lookup_local_visit_id(db, tenant_id, visit_id)

    try:
        from app.services.cezih.client import CezihFhirClient
        from app.services.cezih.message_builder import (
            ENCOUNTER_EVENT_PROFILE_MAP,
            PROFILE_ENCOUNTER,
            PROFILE_ENCOUNTER_MSG_HEADER,
            VISIT_ACTION_MAP,
            add_signature,
            build_encounter_cancel,
            build_encounter_close,
            build_encounter_reopen,
            build_message_bundle,
        )
        fhir_client = CezihFhirClient(http_client)
        if not practitioner_id:
            raise CezihError("HZJZ ID djelatnika nije postavljen. Potrebno je za CEZIH potpisivanje.")
        action_info = VISIT_ACTION_MAP.get(action)
        if action_info is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Nepoznata akcija posjete: {action}. Dozvoljene: close, storno, reopen.",
            )
        event_code = action_info["code"]

        if event_code == "1.5":
            # Reopen has different fields — only identifier, status, class, serviceProvider
            encounter = build_encounter_reopen(
                encounter_id=visit_id,
                nacin_prijema=nacin_prijema,
                org_code=org_code or "",
            )
        else:
            builder_map: dict[str, Callable[..., dict]] = {
                "1.3": build_encounter_close,
                "1.4": build_encounter_cancel,
            }
            builder_fn = builder_map.get(event_code)
            if not builder_fn:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Nema builder funkcije za event code {event_code}",
                )
            encounter = builder_fn(
                encounter_id=visit_id,
                patient_mbo=identifier_value,
                nacin_prijema=nacin_prijema,
                practitioner_id=practitioner_id,
                org_code=org_code or "",
                period_start=period_start,
            )
        bundle_profile = ENCOUNTER_EVENT_PROFILE_MAP.get(event_code)
        profile_urls = {
            "bundle": bundle_profile,
            "header": PROFILE_ENCOUNTER_MSG_HEADER,
            "resource": PROFILE_ENCOUNTER,
        } if bundle_profile else None
        bundle = await build_message_bundle(
            event_code, encounter,
            sender_org_code=org_code, author_practitioner_id=practitioner_id,
            source_oid=source_oid, profile_urls=profile_urls,
        )
        bundle = await add_signature(bundle, practitioner_id, http_client=http_client)
        result = await fhir_client.process_message("encounter-services/api/v1", bundle)
    except CezihError as e:
        await record_cezih_error("visit", local_visit_id, tenant_id, e)
        _raise_cezih_error(e)
    await clear_cezih_error("visit", local_visit_id, tenant_id, session=db)
    await _write_audit(
        db, tenant_id, user_id, action=f"visit_{action}",
        details={"visit_id": visit_id, "action": action},
    )
    parsed = _parse_visit_response(result)
    # Mirror the new state onto our local CezihVisit row
    if action == "close":
        await _update_local_visit(
            db, tenant_id, visit_id,
            patient_mbo=identifier_value,
            status_str="finished", set_period_end=True,
        )
    elif action == "reopen":
        await _update_local_visit(
            db, tenant_id, visit_id,
            patient_mbo=identifier_value,
            status_str="in-progress", clear_period_end=True,
        )
    elif action == "storno":
        await _update_local_visit(
            db, tenant_id, visit_id,
            patient_mbo=identifier_value,
            status_str="entered-in-error",
        )
    return parsed


async def dispatch_list_visits(
    patient_id: UUID,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> list[dict]:
    """List visits for a patient from CEZIH (TC14)."""
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
        result = await real_service.list_visits(http_client, system_uri, value)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(
        db, tenant_id, user_id, action="visit_list",
        details={"patient_id": str(patient_id), "identifier_system": system_uri},
    )
    local = await _fetch_fresh_local_visits_by_patient(db, tenant_id, patient_id)
    return _merge_visits_with_local(result, local)


__all__ = [
    "_persist_local_visit_by_patient_id",
    "_fetch_fresh_local_visits_by_patient",
    "_merge_visits_with_local",
    "_update_local_visit",
    "_parse_visit_response",
    "dispatch_create_visit",
    "dispatch_update_visit",
    "dispatch_visit_action",
    "dispatch_list_visits",
]

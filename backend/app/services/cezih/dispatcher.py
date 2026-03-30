from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services import cezih_mock_service
from app.services.cezih import service as real_service
from app.services.cezih.exceptions import CezihError, CezihSigningError

logger = logging.getLogger(__name__)


def _is_mock() -> bool:
    return settings.CEZIH_MODE == "mock"


async def _write_audit(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    action: str,
    resource_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    from app.models.audit_log import AuditLog

    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type="cezih",
        resource_id=resource_id,
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(entry)
    await db.flush()


# --- Dispatch functions ---
# http_client is always passed but only used in real mode.


async def insurance_check(
    mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_insurance_check(mbo, db=db, user_id=user_id, tenant_id=tenant_id)

    try:
        result = await real_service.check_insurance(http_client, mbo)
    except CezihError as e:
        logger.error("CEZIH insurance check failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    result["mock"] = False

    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="insurance_check",
            details={"mbo": mbo, "result": result.get("status_osiguranja"), "mode": "real"},
        )

    return result


async def send_enalaz(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    record_id: UUID,
    *,
    user_id: UUID | None = None,
    uputnica_id: str | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_send_enalaz(
            db, tenant_id, patient_id, record_id,
            user_id=user_id, uputnica_id=uputnica_id,
        )

    from app.models.patient import Patient

    record = await _get_medical_record(db, tenant_id, patient_id, record_id)
    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    patient_data = {
        "mbo": patient.mbo or "",
        "ime": patient.ime,
        "prezime": patient.prezime,
    }
    record_data = {
        "tip": record.tip if record else "nalaz",
        "tip_display": record.tip if record else "Nalaz",
    }

    try:
        result = await real_service.send_enalaz(http_client, patient_data, record_data, uputnica_id)
    except CezihError as e:
        logger.error("CEZIH e-Nalaz send failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    ref = result["reference_id"]
    now = datetime.now(UTC)

    if record:
        record.cezih_sent = True
        record.cezih_sent_at = now
        record.cezih_reference_id = ref
        await db.flush()

    if uputnica_id:
        await _close_euputnica(db, tenant_id, uputnica_id)

    details: dict = {
        "patient_id": str(patient_id),
        "record_id": str(record_id),
        "reference_id": ref,
        "mode": "real",
    }
    if uputnica_id:
        details["uputnica_id"] = uputnica_id

    if user_id:
        await _write_audit(db, tenant_id, user_id, action="e_nalaz_send", resource_id=patient_id, details=details)

    result["mock"] = False
    return result


async def retrieve_euputnice(
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_retrieve_euputnice(db=db, user_id=user_id, tenant_id=tenant_id)

    if not db or not tenant_id:
        return {"mock": False, "items": []}

    try:
        items = await real_service.retrieve_euputnice(http_client)
    except CezihError as e:
        logger.error("CEZIH e-Uputnica retrieve failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    new_count = 0
    from app.models.cezih_euputnica import CezihEUputnica

    for item in items:
        ext_id = item.get("id", "")
        existing = await db.execute(
            select(CezihEUputnica).where(
                CezihEUputnica.tenant_id == tenant_id,
                CezihEUputnica.external_id == ext_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.status = item.get("status", row.status)
        else:
            db.add(CezihEUputnica(
                tenant_id=tenant_id,
                external_id=ext_id,
                datum_izdavanja=item.get("datum_izdavanja", ""),
                izdavatelj=item.get("izdavatelj", ""),
                svrha=item.get("svrha", ""),
                specijalist=item.get("specijalist", ""),
                status=item.get("status", "Otvorena"),
            ))
            new_count += 1

    await db.flush()

    if user_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_uputnica_retrieve",
            details={"count": len(items), "new": new_count, "mode": "real"},
        )

    return await get_stored_euputnice(db, tenant_id, mock=False)


async def get_stored_euputnice(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    mock: bool = True,
) -> dict:
    """Read all persisted e-Uputnice for the tenant."""
    if not db or not tenant_id:
        return {"mock": mock, "items": []}

    from app.models.cezih_euputnica import CezihEUputnica

    result = await db.execute(
        select(CezihEUputnica)
        .where(CezihEUputnica.tenant_id == tenant_id)
        .order_by(CezihEUputnica.datum_izdavanja.desc())
    )
    rows = result.scalars().all()

    items = [
        {
            "mock": mock,
            "id": r.external_id,
            "datum_izdavanja": r.datum_izdavanja,
            "izdavatelj": r.izdavatelj,
            "svrha": r.svrha,
            "specijalist": r.specijalist,
            "status": r.status,
        }
        for r in rows
    ]
    return {"mock": mock, "items": items}


async def send_erecept(
    patient_id: UUID,
    lijekovi: list[dict],
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_send_erecept(
            patient_id, lijekovi, db=db, user_id=user_id, tenant_id=tenant_id,
        )

    from app.models.patient import Patient

    patient = await db.get(Patient, patient_id) if db else None
    patient_data = {
        "mbo": patient.mbo or "" if patient else "",
        "ime": patient.ime if patient else "",
        "prezime": patient.prezime if patient else "",
    }

    try:
        result = await real_service.send_erecept(http_client, patient_data, lijekovi)
    except CezihError as e:
        logger.error("CEZIH e-Recept send failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    recept_id = result["recept_id"]

    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_recept_send",
            resource_id=patient_id,
            details={
                "patient_id": str(patient_id),
                "recept_id": recept_id,
                "lijekovi": [item.get("naziv", "") if isinstance(item, dict) else str(item) for item in lijekovi],
                "mode": "real",
            },
        )

    result["mock"] = False
    return result


async def cezih_status(tenant_id=None, *, http_client=None) -> dict:
    if _is_mock():
        mock_result = cezih_mock_service.mock_cezih_status(tenant_id)
        mock_result["mode"] = settings.CEZIH_MODE
        return mock_result

    # Real mode
    connected = False
    if http_client:
        try:
            status_result = await real_service.get_status(http_client)
            connected = status_result.get("connected", False)
        except CezihError:
            connected = False

    from app.services.agent_connection_manager import agent_manager

    agent_connected = False
    last_heartbeat = None
    if tenant_id:
        agent_connected = agent_manager.is_connected(tenant_id)
        conn = agent_manager.get(tenant_id)
        if conn:
            last_heartbeat = conn.last_heartbeat

    return {
        "mock": False,
        "connected": connected,
        "mode": "real",
        "agent_connected": agent_connected,
        "last_heartbeat": last_heartbeat,
    }


def drug_search(query: str) -> list[dict]:
    """Drug search — always mock (real needs local DB sync of code lists)."""
    return cezih_mock_service.mock_drug_search(query)


# --- Helpers ---


async def _get_medical_record(db: AsyncSession, tenant_id: UUID, patient_id: UUID, record_id: UUID):
    from app.models.medical_record import MedicalRecord

    result = await db.execute(
        select(MedicalRecord).where(
            MedicalRecord.id == record_id,
            MedicalRecord.tenant_id == tenant_id,
            MedicalRecord.patient_id == patient_id,
        )
    )
    return result.scalar_one_or_none()


async def _close_euputnica(db: AsyncSession, tenant_id: UUID, uputnica_id: str) -> None:
    from app.models.cezih_euputnica import CezihEUputnica

    result = await db.execute(
        select(CezihEUputnica).where(
            CezihEUputnica.tenant_id == tenant_id,
            CezihEUputnica.external_id == uputnica_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.status = "Zatvorena"
        await db.flush()


# --- Signing dispatch ---


async def sign_document(
    document_bytes: bytes | str,
    *,
    document_id: str | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return cezih_mock_service.mock_sign_document(document_id=document_id)

    if not http_client:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="HTTP client not available")

    from app.services.cezih_signing import sign_document as real_sign_document

    try:
        result = await real_sign_document(
            http_client, document_bytes, document_id=document_id,
        )
    except CezihSigningError as e:
        logger.error("CEZIH signing failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    result["mock"] = False
    return result


async def signing_health_check(*, http_client=None) -> dict:
    if _is_mock():
        return cezih_mock_service.mock_sign_health_check()

    if not http_client:
        return {"reachable": False, "reason": "HTTP client not available"}

    from app.services.cezih_signing import sign_health_check as real_health_check

    try:
        return await real_health_check(http_client)
    except Exception as e:
        logger.error("CEZIH signing health check failed: %s", e)
        return {"reachable": False, "reason": str(e)}


# ============================================================
# TC6: OID Registry Lookup
# ============================================================


async def oid_lookup(
    oid: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_lookup_oid(oid, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        result = await real_service.lookup_oid(http_client, oid)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


# ============================================================
# TC7: Code System Query
# ============================================================


async def code_system_query(
    system_name: str,
    query: str,
    count: int = 20,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    if _is_mock():
        return await cezih_mock_service.mock_query_code_system(
            system_name, query, count, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        return await real_service.query_code_system(http_client, system_name, query, count)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e


# ============================================================
# TC8: Value Set Expand
# ============================================================


async def value_set_expand(
    url: str,
    filter_text: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_expand_value_set(
            url, filter_text, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.expand_value_set(http_client, url, filter_text)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


# ============================================================
# TC9: Subject Registry
# ============================================================


async def organization_search(
    name: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    if _is_mock():
        return await cezih_mock_service.mock_find_organizations(name, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        return await real_service.find_organizations(http_client, name)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e


async def practitioner_search(
    name: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    if _is_mock():
        return await cezih_mock_service.mock_find_practitioners(name, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        return await real_service.find_practitioners(http_client, name)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e


# ============================================================
# TC11: Foreigner Registration
# ============================================================


async def foreigner_registration(
    patient_data: dict,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_register_foreigner(
            patient_data, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.register_foreigner(http_client, patient_data)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


# ============================================================
# TC12-14: Visit Management
# ============================================================


async def dispatch_create_visit(
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    admission_type_code: str = "9",
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_create_visit(
            patient_mbo, period_start, admission_type_code,
            db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.create_visit(
            http_client, patient_mbo, practitioner_id, org_code, period_start, admission_type_code,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_update_visit(
    visit_id: str,
    practitioner_id: str,
    org_code: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
    **updates: str,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_update_visit(visit_id, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        result = await real_service.update_visit(http_client, visit_id, practitioner_id, org_code, **updates)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_close_visit(
    visit_id: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    period_end: str,
    admission_type_code: str = "9",
    diagnosis_case_id: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_close_visit(
            visit_id, period_end, diagnosis_case_id,
            db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.close_visit(
            http_client, visit_id, practitioner_id, org_code,
            period_start, period_end, admission_type_code, diagnosis_case_id,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_reopen_visit(
    visit_id: str,
    practitioner_id: str,
    org_code: str,
    admission_type_code: str = "9",
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_reopen_visit(visit_id, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        result = await real_service.reopen_visit(
            http_client, visit_id, practitioner_id, org_code, admission_type_code,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_cancel_visit(
    visit_id: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    period_end: str | None = None,
    admission_type_code: str = "9",
    diagnosis_case_id: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_cancel_visit(visit_id, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        result = await real_service.cancel_visit(
            http_client, visit_id, practitioner_id, org_code,
            period_start, period_end, admission_type_code, diagnosis_case_id,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


# ============================================================
# TC15-17: Case Management
# ============================================================


async def dispatch_retrieve_cases(
    patient_mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    if _is_mock():
        return await cezih_mock_service.mock_retrieve_cases(patient_mbo, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        return await real_service.retrieve_cases(http_client, patient_mbo)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e


async def dispatch_create_case(
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str = "unconfirmed",
    note_text: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_create_case(
            patient_mbo, icd_code, icd_display, onset_date, verification_status, note_text,
            db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.create_case(
            http_client, patient_mbo, practitioner_id, org_code,
            icd_code, icd_display, onset_date, verification_status, note_text,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_update_case(
    case_id: str,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    action: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_update_case(case_id, action, db=db, user_id=user_id, tenant_id=tenant_id)
    try:
        result = await real_service.update_case(http_client, case_id, patient_mbo, practitioner_id, org_code, action)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_update_case_data(
    case_id: str,
    patient_mbo: str,
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
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        updates = {k: v for k, v in {
            "verification_status": verification_status, "icd_code": icd_code,
            "onset_date": onset_date, "abatement_date": abatement_date, "note_text": note_text,
        }.items() if v is not None}
        return await cezih_mock_service.mock_update_case_data(
            case_id, updates, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.update_case_data(
            http_client, case_id, patient_mbo, practitioner_id, org_code,
            current_clinical_status=current_clinical_status,
            verification_status=verification_status,
            icd_code=icd_code, icd_display=icd_display,
            onset_date=onset_date, abatement_date=abatement_date,
            note_text=note_text,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


# ============================================================
# TC19-20, 22: Document Operations
# ============================================================


async def dispatch_search_documents(
    *,
    patient_mbo: str | None = None,
    document_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_filter: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    if _is_mock():
        return await cezih_mock_service.mock_search_documents(
            patient_mbo, document_type, date_from, date_to, status_filter,
            db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        return await real_service.search_documents(
            http_client, patient_mbo=patient_mbo, document_type=document_type,
            date_from=date_from, date_to=date_to, status_filter=status_filter,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e


async def dispatch_replace_document(
    original_reference_id: str,
    patient_data: dict | None = None,
    record_data: dict | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_replace_document(
            original_reference_id, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.replace_document(
            http_client, original_reference_id, patient_data or {}, record_data or {},
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_cancel_document(
    reference_id: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_cancel_document(
            reference_id, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        result = await real_service.cancel_document(http_client, reference_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    return result


async def dispatch_retrieve_document(
    reference_id: str,
    document_url: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> bytes:
    if _is_mock():
        return await cezih_mock_service.mock_retrieve_document(
            reference_id, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    try:
        return await real_service.retrieve_document(http_client, document_url or reference_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

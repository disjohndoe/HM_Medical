from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import CEZIH_ELIGIBLE_TYPES
from app.services import cezih_mock_service
from app.services.cezih import service as real_service
from app.services.cezih.exceptions import CezihError, CezihSigningError

logger = logging.getLogger(__name__)


def _is_mock() -> bool:
    return settings.CEZIH_MODE == "mock"


async def _write_audit(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    user_id: UUID | None,
    action: str,
    resource_id: UUID | None = None,
    details: dict | None = None,
) -> None:
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


def _require_audit_params(
    db: AsyncSession | None, user_id: UUID | None, tenant_id: UUID | None,
) -> None:
    """In real mode, audit parameters are mandatory for traceability."""
    if _is_mock():
        return
    if not db or not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interna greška: nedostaju parametri za revizijski zapis CEZIH operacije.",
        )


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

    _require_audit_params(db, user_id, tenant_id)

    try:
        result = await real_service.check_insurance(http_client, mbo)
    except CezihError as e:
        logger.error("CEZIH insurance check failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    result["mock"] = False

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
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_send_enalaz(
            db, tenant_id, patient_id, record_id,
            user_id=user_id,
        )

    from app.models.patient import Patient

    record = await _get_medical_record(db, tenant_id, patient_id, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicinski zapis nije pronađen")

    if record.tip not in CEZIH_ELIGIBLE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tip zapisa '{record.tip}' nije predviđen za slanje na CEZIH. "
                   f"Dozvoljeni tipovi: {', '.join(sorted(CEZIH_ELIGIBLE_TYPES))}",
        )

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    if not patient.mbo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pacijent nema MBO broj. MBO je obavezan za slanje nalaza na CEZIH.",
        )

    patient_data = {
        "mbo": patient.mbo,
        "ime": patient.ime,
        "prezime": patient.prezime,
    }
    record_data = {
        "tip": record.tip,
        "dijagnoza_mkb": record.dijagnoza_mkb,
        "dijagnoza_tekst": record.dijagnoza_tekst,
        "sadrzaj": record.sadrzaj,
        "preporucena_terapija": record.preporucena_terapija,
    }

    # Get practitioner ID from the record's doktor_id for signing
    practitioner_id = str(record.doktor_id) if record and record.doktor_id else None

    try:
        result = await real_service.send_enalaz(http_client, patient_data, record_data, practitioner_id=practitioner_id)
    except CezihError as e:
        logger.error("CEZIH e-Nalaz send failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    ref = result["reference_id"]
    now = datetime.now(UTC)

    if record:
        record.cezih_sent = True
        record.cezih_sent_at = now
        record.cezih_reference_id = ref
        # Persist signature data if returned
        if result.get("signature_data"):
            record.cezih_signature_data = result["signature_data"]
        if result.get("signed_at"):
            record.cezih_signed_at = datetime.fromisoformat(result["signed_at"])
        await db.flush()

    details: dict = {
        "patient_id": str(patient_id),
        "record_id": str(record_id),
        "reference_id": ref,
        "mode": "real",
    }

    if user_id:
        await _write_audit(db, tenant_id, user_id, action="e_nalaz_send", resource_id=patient_id, details=details)

    result["mock"] = False
    return result


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

    _require_audit_params(db, user_id, tenant_id)

    from app.models.patient import Patient

    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interna greška: nedostaje veza s bazom podataka za CEZIH operaciju.",
        )
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pacijent nije pronađen.",
        )
    if not patient.mbo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pacijent nema MBO broj. MBO je obavezan za slanje e-Recepta na CEZIH.",
        )

    patient_data = {
        "mbo": patient.mbo,
        "ime": patient.ime,
        "prezime": patient.prezime,
    }

    try:
        result = await real_service.send_erecept(http_client, patient_data, lijekovi)
    except CezihError as e:
        logger.error("CEZIH e-Recept send failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    recept_id = result["recept_id"]

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


async def cancel_erecept(
    recept_id: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_cancel_erecept(
            recept_id, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.cancel_erecept(http_client, recept_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id,
        action="e_recept_cancel",
        details={"recept_id": recept_id, "mode": "real"},
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
        conn = agent_manager.get_any_connected(tenant_id)
        if conn:
            last_heartbeat = conn.last_heartbeat

    return {
        "mock": False,
        "connected": connected,
        "mode": "real",
        "agent_connected": agent_connected,
        "last_heartbeat": last_heartbeat,
    }


async def drug_search(query: str) -> list[dict]:
    """Drug search — uses local HZZO drug DB."""
    if _is_mock():
        return cezih_mock_service.mock_drug_search(query)

    from app.services.halmed_sync_service import search_drugs_db

    results = await search_drugs_db(query)
    return results


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


async def _get_medical_record_by_id(db: AsyncSession | None, tenant_id: UUID | None, record_id: UUID | None):
    if not db or not tenant_id or not record_id:
        return None
    from app.models.medical_record import MedicalRecord

    result = await db.execute(
        select(MedicalRecord).where(
            MedicalRecord.id == record_id,
            MedicalRecord.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.lookup_oid(http_client, oid)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(db, tenant_id, user_id, action="oid_lookup", details={"oid": oid, "mode": "real"})
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.query_code_system(http_client, system_name, query, count)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="code_system_query",
        details={"system": system_name, "query": query, "mode": "real"},
    )
    return result


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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.expand_value_set(http_client, url, filter_text)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(db, tenant_id, user_id, action="value_set_expand", details={"url": url, "mode": "real"})
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.find_organizations(http_client, name)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="organization_search", details={"name": name, "mode": "real"})
    return result


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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.find_practitioners(http_client, name)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="practitioner_search", details={"name": name, "mode": "real"})
    return result


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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.register_foreigner(http_client, patient_data)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    patient_name = f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}"
    await _write_audit(
        db, tenant_id, user_id, action="foreigner_register",
        details={"patient_name": patient_name, "mode": "real"},
    )
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.retrieve_cases(http_client, patient_mbo)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="case_retrieve", details={"mbo": patient_mbo, "mode": "real"})
    return result


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
    source_oid: str | None = None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_create_case(
            patient_mbo, icd_code, icd_display, onset_date, verification_status, note_text,
            db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.create_case(
            http_client, patient_mbo, practitioner_id, org_code,
            icd_code, icd_display, onset_date, verification_status, note_text,
            source_oid=source_oid,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(
        db, tenant_id, user_id, action="case_create",
        details={"mbo": patient_mbo, "icd": icd_code, "mode": "real"},
    )
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
    source_oid: str | None = None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_update_case(case_id, action, db=db, user_id=user_id, tenant_id=tenant_id)
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.update_case(
            http_client, case_id, patient_mbo, practitioner_id, org_code, action,
            source_oid=source_oid,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(
        db, tenant_id, user_id, action=f"case_{action}",
        details={"case_id": case_id, "action": action, "mode": "real"},
    )
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
    source_oid: str | None = None,
) -> dict:
    if _is_mock():
        updates = {k: v for k, v in {
            "verification_status": verification_status, "icd_code": icd_code,
            "onset_date": onset_date, "abatement_date": abatement_date, "note_text": note_text,
        }.items() if v is not None}
        return await cezih_mock_service.mock_update_case_data(
            case_id, updates, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.update_case_data(
            http_client, case_id, patient_mbo, practitioner_id, org_code,
            current_clinical_status=current_clinical_status,
            verification_status=verification_status,
            icd_code=icd_code, icd_display=icd_display,
            onset_date=onset_date, abatement_date=abatement_date,
            note_text=note_text,
            source_oid=source_oid,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(
        db, tenant_id, user_id, action="case_update_data",
        details={"case_id": case_id, "mode": "real"},
    )
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.search_documents(
            http_client, patient_mbo=patient_mbo, document_type=document_type,
            date_from=date_from, date_to=date_to, status_filter=status_filter,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="document_search",
        details={"mbo": patient_mbo or "", "type": document_type or "", "mode": "real"},
    )
    return result


async def dispatch_replace_document(
    original_reference_id: str,
    patient_data: dict | None = None,
    record_data: dict | None = None,
    record_id: UUID | None = None,
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
    _require_audit_params(db, user_id, tenant_id)

    # Get practitioner ID from the record for signing
    practitioner_id = None
    if record_id:
        record = await _get_medical_record_by_id(db, tenant_id, record_id)
        if record and record.doktor_id:
            practitioner_id = str(record.doktor_id)

    try:
        result = await real_service.replace_document(
            http_client, original_reference_id, patient_data or {}, record_data or {},
            practitioner_id=practitioner_id,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    # Persist signature data if we have a record
    if record_id and result.get("signature_data"):
        record = await _get_medical_record_by_id(db, tenant_id, record_id)
        if record and db:
            record.cezih_signature_data = result["signature_data"]
            if result.get("signed_at"):
                record.cezih_signed_at = datetime.fromisoformat(result["signed_at"])
            await db.flush()

    result["mock"] = False
    await _write_audit(
        db, tenant_id, user_id, action="e_nalaz_replace",
        details={"reference_id": original_reference_id, "mode": "real"},
    )
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.cancel_document(http_client, reference_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(
        db, tenant_id, user_id, action="e_nalaz_cancel",
        details={"reference_id": reference_id, "mode": "real"},
    )
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.retrieve_document(http_client, document_url or reference_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="document_retrieve",
        details={"reference_id": reference_id, "mode": "real"},
    )
    return result


# ============================================================
# TC12-14: Visit Management
# ============================================================


async def dispatch_create_visit(
    patient_mbo: str,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_create_visit(
            patient_mbo, nacin_prijema, reason, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    try:
        from app.services.cezih.message_builder import (
            build_encounter_create, build_message_bundle, ENCOUNTER_EVENT_PROFILE_MAP,
            PROFILE_ENCOUNTER, PROFILE_ENCOUNTER_MSG_HEADER,
        )
        encounter = build_encounter_create(
            patient_mbo=patient_mbo, nacin_prijema=nacin_prijema,
            vrsta_posjete=vrsta_posjete, tip_posjete=tip_posjete,
            reason=reason, practitioner_id=practitioner_id or "", org_code=org_code or "",
        )
        bundle_profile = ENCOUNTER_EVENT_PROFILE_MAP.get("1.1")
        profile_urls = {
            "bundle": bundle_profile,
            "header": PROFILE_ENCOUNTER_MSG_HEADER,
            "resource": PROFILE_ENCOUNTER,
        } if bundle_profile else None
        bundle = await build_message_bundle(
            "1.1", encounter, sender_org_code=org_code, author_practitioner_id=practitioner_id,
            source_oid=source_oid, profile_urls=profile_urls,
        )
        result = await http_client.process_message("encounter-services/api/v1", bundle)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    result["mock"] = False
    await _write_audit(
        db, tenant_id, user_id, action="visit_create",
        details={"mbo": patient_mbo, "nacin_prijema": nacin_prijema, "mode": "real"},
    )
    return result


async def dispatch_update_visit(
    visit_id: str,
    reason: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_update_visit(
            visit_id, reason, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    # TODO: Implement real visit update via encounter-services/api/v1/$process-message with code 1.2
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Real mode visit update not yet implemented",
    )


async def dispatch_visit_action(
    visit_id: str,
    action: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    if _is_mock():
        return await cezih_mock_service.mock_visit_action(
            visit_id, action, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    # TODO: Implement real visit close/reopen/storno via encounter-services/api/v1/$process-message
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Real mode visit action not yet implemented",
    )


async def dispatch_list_visits(
    patient_mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    if _is_mock():
        return await cezih_mock_service.mock_list_visits(
            patient_mbo, db=db, user_id=user_id, tenant_id=tenant_id,
        )
    _require_audit_params(db, user_id, tenant_id)
    # TODO: Implement real visit list via ihe-qedm-services/api/v1/Encounter
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Real mode visit list not yet implemented")

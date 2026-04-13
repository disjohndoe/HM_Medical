from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CEZIH_ELIGIBLE_TYPES
from app.services.cezih import service as real_service
from app.services.cezih.exceptions import CezihError, CezihSigningError
from app.services.cezih.message_builder import _now_iso

logger = logging.getLogger(__name__)


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
    """Audit parameters are mandatory for traceability."""
    if not db or not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interna greška: nedostaju parametri za revizijski zapis CEZIH operacije.",
        )
    # Set context so CezihFhirClient can route 8443 calls through the agent
    from app.services.cezih.client import current_tenant_id
    current_tenant_id.set(tenant_id)


# --- Dispatch functions ---
# http_client is always passed but only used in real mode.


async def import_patient_from_cezih(
    mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    """Fetch patient demographics from CEZIH and create a new local patient."""
    _require_audit_params(db, user_id, tenant_id)

    from datetime import date as date_type

    from sqlalchemy.exc import IntegrityError

    from app.models.patient import Patient

    # Check if patient with this MBO already exists
    result = await db.execute(
        select(Patient).where(
            Patient.tenant_id == tenant_id, Patient.mbo == mbo, Patient.is_active.is_(True),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pacijent s tim MBO-om već postoji",
        )

    try:
        cezih_data = await real_service.fetch_patient_demographics(http_client, mbo)
    except CezihError as e:
        logger.error("CEZIH patient import failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    # Parse date string to date object
    dob = None
    if cezih_data.get("datum_rodjenja"):
        try:
            dob = date_type.fromisoformat(cezih_data["datum_rodjenja"])
        except ValueError:
            pass

    patient = Patient(
        tenant_id=tenant_id,
        ime=cezih_data.get("ime") or "Nepoznato",
        prezime=cezih_data.get("prezime") or "Nepoznato",
        datum_rodjenja=dob,
        spol=cezih_data.get("spol"),
        oib=cezih_data.get("oib"),
        mbo=mbo,
        cezih_insurance_status="Aktivan",
        cezih_insurance_checked_at=datetime.now(UTC),
    )
    db.add(patient)

    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig)
        if "uq_patient_tenant_oib" in error_msg:
            raise HTTPException(status_code=409, detail="Pacijent s tim OIB-om već postoji") from e
        raise HTTPException(status_code=409, detail="Pacijent s tim podacima već postoji") from e

    await db.refresh(patient)

    await _write_audit(
        db, tenant_id, user_id,
        action="cezih_patient_import",
        resource_id=patient.id,
        details={"mbo": mbo, "ime": patient.ime, "prezime": patient.prezime},
    )

    return {
        "id": str(patient.id),
        "ime": patient.ime,
        "prezime": patient.prezime,
        "datum_rodjenja": patient.datum_rodjenja.isoformat() if patient.datum_rodjenja else None,
        "oib": patient.oib,
        "spol": patient.spol,
        "mbo": patient.mbo,
    }


async def _persist_insurance_to_patient(
    db: AsyncSession, tenant_id: UUID, mbo: str, status_osiguranja: str,
) -> UUID | None:
    """Update patient's cached insurance status. Returns patient ID for audit."""
    from app.models.patient import Patient

    result = await db.execute(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.mbo == mbo)
    )
    patient = result.scalar_one_or_none()
    if patient:
        patient.cezih_insurance_status = status_osiguranja
        patient.cezih_insurance_checked_at = datetime.now(UTC)
        await db.flush()
        return patient.id
    return None


async def insurance_check(
    mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    _require_audit_params(db, user_id, tenant_id)

    try:
        result = await real_service.check_insurance(http_client, mbo)
    except CezihError as e:
        logger.error("CEZIH insurance check failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    patient_id = None
    if db and tenant_id:
        patient_id = await _persist_insurance_to_patient(
            db, tenant_id, mbo, result.get("status_osiguranja", ""),
        )

    await _write_audit(
        db, tenant_id, user_id,
        action="insurance_check",
        resource_id=patient_id,
        details={"mbo": mbo, "result": result.get("status_osiguranja")},
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
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
) -> dict:
    from app.models.patient import Patient
    _require_audit_params(db, user_id, tenant_id)

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

    if not practitioner_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="HZJZ ID djelatnika nije postavljen. Potrebno je za CEZIH potpisivanje.",
        )

    record_data["created_at"] = record.created_at.isoformat() if record.created_at else _now_iso()

    try:
        result = await real_service.send_enalaz(
            http_client, patient_data, record_data,
            practitioner_id=practitioner_id,
            org_code=org_code or "", source_oid=source_oid or "",
            encounter_id=encounter_id, case_id=case_id,
            practitioner_name=practitioner_name,
        )
    except CezihError as e:
        logger.error("CEZIH e-Nalaz send failed: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    ref = result["reference_id"]
    now = datetime.now(UTC)

    if record:
        record.cezih_sent = True
        record.cezih_sent_at = now
        record.cezih_reference_id = ref
        if encounter_id:
            record.cezih_encounter_id = encounter_id
        if case_id:
            record.cezih_case_id = case_id
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
    }

    if user_id:
        await _write_audit(db, tenant_id, user_id, action="e_nalaz_send", resource_id=patient_id, details=details)

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
        },
    )

    return result


async def cancel_erecept(
    recept_id: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.cancel_erecept(http_client, recept_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id,
        action="e_recept_cancel",
        details={"recept_id": recept_id},
    )
    return result


async def cezih_status(tenant_id=None, *, http_client=None) -> dict:
    # Server cannot reach CEZIH directly (no VPN),
    # so derive connectivity from agent + VPN status.
    from app.services.agent_connection_manager import agent_manager

    agent_connected = False
    vpn_connected = False
    last_heartbeat = None
    if tenant_id:
        agent_connected = agent_manager.is_connected(tenant_id)
        conn = agent_manager.get_any_connected(tenant_id)
        if conn:
            last_heartbeat = conn.last_heartbeat
            vpn_connected = conn.vpn_connected

    # CEZIH is reachable when the agent is connected with an active VPN tunnel
    connected = agent_connected and vpn_connected

    return {
        "connected": connected,
        "agent_connected": agent_connected,
        "last_heartbeat": last_heartbeat,
    }


async def drug_search(query: str) -> list[dict]:
    """Drug search — uses local HZZO drug DB."""
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

    return result


async def signing_health_check(*, http_client=None) -> dict:
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


async def oid_generate(
    quantity: int = 1,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.generate_oid(http_client, quantity)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="oid_generate", details={"quantity": quantity})
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.query_code_system(http_client, system_name, query, count)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="code_system_query",
        details={"system": system_name, "query": query},
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.expand_value_set(http_client, url, filter_text)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="value_set_expand", details={"url": url})
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.find_organizations(http_client, name)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="organization_search", details={"name": name})
    return result


async def practitioner_search(
    name: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.find_practitioners(http_client, name)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="practitioner_search", details={"name": name})
    return result


# ============================================================
# TC11: Foreigner Registration
# ============================================================


async def foreigner_registration(
    patient_data: dict,
    *,
    org_code: str = "",
    source_oid: str = "",
    practitioner_id: str = "",
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.register_foreigner(
            http_client, patient_data, org_code=org_code, source_oid=source_oid,
            practitioner_id=practitioner_id,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    patient_name = f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}"
    await _write_audit(
        db, tenant_id, user_id, action="foreigner_register",
        details={"patient_name": patient_name},
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.retrieve_cases(http_client, patient_mbo)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="case_retrieve", details={"mbo": patient_mbo})
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.create_case(
            http_client, patient_mbo, practitioner_id, org_code,
            icd_code, icd_display, onset_date, verification_status, note_text,
            source_oid=source_oid,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="case_create",
        details={"mbo": patient_mbo, "icd": icd_code},
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.update_case(
            http_client, case_id, patient_mbo, practitioner_id, org_code, action,
            source_oid=source_oid,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action=f"case_{action}",
        details={"case_id": case_id, "action": action},
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
    await _write_audit(
        db, tenant_id, user_id, action="case_update_data",
        details={"case_id": case_id},
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
        details={"mbo": patient_mbo or "", "type": document_type or ""},
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
    org_code: str = "",
    practitioner_id: str | None = None,
    practitioner_name: str = "",
    encounter_id: str = "",
    case_id: str = "",
) -> dict:
    from app.models.patient import Patient
    _require_audit_params(db, user_id, tenant_id)

    # Load full record and patient data from DB (same pattern as send_enalaz)
    # Fallback: if no record_id, look up by cezih_reference_id (used when called from e-Nalazi tab)
    if not record_id and db and tenant_id and not (patient_data and record_data):
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(MedicalRecord).where(
                MedicalRecord.tenant_id == tenant_id,
                MedicalRecord.cezih_reference_id == original_reference_id,
            )
        )
        found = result.scalar_one_or_none()
        if found:
            record_id = found.id
    if record_id and not (patient_data and record_data):
        record = await _get_medical_record_by_id(db, tenant_id, record_id)
        if record:
            if not practitioner_id and record.doktor_id:
                practitioner_id = str(record.doktor_id)
            if not record_data:
                record_data = {
                    "tip": record.tip,
                    "dijagnoza_mkb": record.dijagnoza_mkb,
                    "dijagnoza_tekst": record.dijagnoza_tekst,
                    "sadrzaj": record.sadrzaj,
                    "preporucena_terapija": record.preporucena_terapija,
                    "created_at": record.created_at.isoformat() if record.created_at else _now_iso(),
                }
            if not patient_data and record.patient_id:
                patient = await db.get(Patient, record.patient_id)
                if patient:
                    patient_data = {
                        "mbo": patient.mbo,
                        "ime": patient.ime,
                        "prezime": patient.prezime,
                    }
            # Restore encounter and case from original send
            if not encounter_id and record.cezih_encounter_id:
                encounter_id = record.cezih_encounter_id
            if not case_id and record.cezih_case_id:
                case_id = record.cezih_case_id

    try:
        result = await real_service.replace_document(
            http_client, original_reference_id, patient_data or {}, record_data or {},
            practitioner_id=practitioner_id,
            org_code=org_code,
            encounter_id=encounter_id, case_id=case_id,
            practitioner_name=practitioner_name,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e

    # Update the DB record's reference_id to the new document created by replace
    new_ref = result.get("new_reference_id")
    if record_id and new_ref:
        record = await _get_medical_record_by_id(db, tenant_id, record_id)
        if record:
            record.cezih_reference_id = new_ref
            await db.flush()

    await _write_audit(
        db, tenant_id, user_id, action="e_nalaz_replace",
        details={"reference_id": original_reference_id, "new_reference_id": new_ref},
    )
    return result


async def dispatch_cancel_document(
    reference_id: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
    org_code: str = "",
    practitioner_id: str | None = None,
    practitioner_name: str = "",
) -> dict:
    from app.models.medical_record import MedicalRecord
    from app.models.patient import Patient
    from sqlalchemy import select as sa_select
    _require_audit_params(db, user_id, tenant_id)

    # Look up the record by cezih_reference_id to get patient/encounter/case context
    patient_data: dict = {}
    encounter_id = ""
    case_id = ""
    if db and tenant_id:
        result = await db.execute(
            sa_select(MedicalRecord).where(
                MedicalRecord.tenant_id == tenant_id,
                MedicalRecord.cezih_reference_id == reference_id,
            )
        )
        record = result.scalar_one_or_none()
        if record:
            if record.patient_id:
                patient = await db.get(Patient, record.patient_id)
                if patient:
                    patient_data = {"mbo": patient.mbo, "ime": patient.ime, "prezime": patient.prezime}
            encounter_id = record.cezih_encounter_id or ""
            case_id = record.cezih_case_id or ""

    try:
        result = await real_service.cancel_document(
            http_client, reference_id,
            org_code=org_code, practitioner_id=practitioner_id,
            patient_data=patient_data, encounter_id=encounter_id,
            case_id=case_id, practitioner_name=practitioner_name,
        )
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="e_nalaz_cancel",
        details={"reference_id": reference_id},
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.retrieve_document(http_client, document_url or reference_id)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="document_retrieve",
        details={"reference_id": reference_id},
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
    _require_audit_params(db, user_id, tenant_id)
    try:
        from app.services.cezih.client import CezihFhirClient
        from app.services.cezih.message_builder import (
            build_encounter_create, build_message_bundle, add_signature, ENCOUNTER_EVENT_PROFILE_MAP,
            PROFILE_ENCOUNTER, PROFILE_ENCOUNTER_MSG_HEADER,
        )
        fhir_client = CezihFhirClient(http_client)
        if not practitioner_id:
            raise CezihError("HZJZ ID djelatnika nije postavljen. Potrebno je za CEZIH potpisivanje.")
        encounter = build_encounter_create(
            patient_mbo=patient_mbo, nacin_prijema=nacin_prijema,
            vrsta_posjete=vrsta_posjete, tip_posjete=tip_posjete,
            reason=reason, practitioner_id=practitioner_id, org_code=org_code or "",
        )
        # NOTE: official CEZIH examples have NO meta.profile on any resource
        bundle = await build_message_bundle(
            "1.1", encounter, sender_org_code=org_code, author_practitioner_id=practitioner_id,
            source_oid=source_oid, profile_urls=None,
        )
        bundle = await add_signature(bundle, practitioner_id, http_client=http_client)
        result = await fhir_client.process_message("encounter-services/api/v1", bundle)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="visit_create",
        details={"mbo": patient_mbo, "nacin_prijema": nacin_prijema},
    )
    resp = _parse_visit_response(result)
    resp["nacin_prijema"] = nacin_prijema
    resp["vrsta_posjete"] = vrsta_posjete
    resp["tip_posjete"] = tip_posjete
    return resp


def _parse_visit_response(result: dict) -> dict:
    """Parse CEZIH FHIR Bundle response into VisitResponse format."""
    # Extract Encounter from response Bundle entries
    visit_id = ""
    encounter_status = "in-progress"
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Encounter":
            visit_id = resource.get("id", "")
            encounter_status = resource.get("status", "in-progress")
            break
        if resource.get("resourceType") == "MessageHeader":
            # Encounter ID from focus reference (e.g. "http://fhir.cezih.hr/fhir/Encounter/1469")
            for focus in resource.get("focus", []):
                ref = focus.get("reference", "")
                if "Encounter" in ref:
                    visit_id = ref.rsplit("/", 1)[-1]
    return {"success": True, "visit_id": visit_id, "status": encounter_status}


async def dispatch_update_visit(
    visit_id: str,
    patient_mbo: str,
    reason: str | None = None,
    *,
    nacin_prijema: str | None = None,
    vrsta_posjete: str | None = None,
    tip_posjete: str | None = None,
    diagnosis_case_id: str | None = None,
    additional_practitioner_id: str | None = None,
    period_start: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
) -> dict:
    _require_audit_params(db, user_id, tenant_id)
    try:
        from app.services.cezih.client import CezihFhirClient
        from app.services.cezih.message_builder import (
            build_encounter_update, build_message_bundle, add_signature,
        )
        fhir_client = CezihFhirClient(http_client)
        if not practitioner_id:
            raise CezihError("HZJZ ID djelatnika nije postavljen. Potrebno je za CEZIH potpisivanje.")
        encounter = build_encounter_update(
            encounter_id=visit_id,
            patient_mbo=patient_mbo,
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action="visit_update",
        details={"visit_id": visit_id},
    )
    resp = _parse_visit_response(result)
    if nacin_prijema:
        resp["nacin_prijema"] = nacin_prijema
    if vrsta_posjete:
        resp["vrsta_posjete"] = vrsta_posjete
    if tip_posjete:
        resp["tip_posjete"] = tip_posjete
    return resp


async def dispatch_visit_action(
    visit_id: str,
    action: str,
    patient_mbo: str,
    *,
    nacin_prijema: str = "6",
    period_start: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
    practitioner_id: str | None = None,
    org_code: str | None = None,
    source_oid: str | None = None,
) -> dict:
    _require_audit_params(db, user_id, tenant_id)
    try:
        from app.services.cezih.client import CezihFhirClient
        from app.services.cezih.message_builder import (
            build_encounter_close, build_encounter_cancel, build_encounter_reopen,
            build_message_bundle, add_signature, ENCOUNTER_EVENT_PROFILE_MAP, VISIT_ACTION_MAP,
            PROFILE_ENCOUNTER, PROFILE_ENCOUNTER_MSG_HEADER,
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
            builder_map = {
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
                patient_mbo=patient_mbo,
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(
        db, tenant_id, user_id, action=f"visit_{action}",
        details={"visit_id": visit_id, "action": action},
    )
    return _parse_visit_response(result)


async def dispatch_list_visits(
    patient_mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.list_visits(http_client, patient_mbo)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    await _write_audit(db, tenant_id, user_id, action="visit_list", details={"mbo": patient_mbo})
    return result

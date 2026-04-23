"""CEZIH document dispatcher — e-Nalazi, e-Recepti, signing, document operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CEZIH_ELIGIBLE_TYPES
from app.services.cezih import service as real_service
from app.services.cezih.builders.common import _now_iso
from app.services.cezih.dispatchers.common import _raise_cezih_error, _require_audit_params, _write_audit
from app.services.cezih.error_persistence import clear_cezih_error, record_cezih_error
from app.services.cezih.exceptions import CezihError, CezihFhirError, CezihSigningError

logger = logging.getLogger(__name__)


async def _get_medical_record(db: AsyncSession, tenant_id: UUID, patient_id: UUID, record_id: UUID):
    """Fetch medical record by ID with tenant/patient validation."""
    from app.models.medical_record import MedicalRecord

    result = await db.execute(
        sa_select(MedicalRecord).where(
            MedicalRecord.id == record_id,
            MedicalRecord.tenant_id == tenant_id,
            MedicalRecord.patient_id == patient_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_medical_record_by_id(db: AsyncSession | None, tenant_id: UUID | None, record_id: UUID | None):
    """Fetch medical record by ID with tenant validation only."""
    if not db or not tenant_id or not record_id:
        return None
    from app.models.medical_record import MedicalRecord

    result = await db.execute(
        sa_select(MedicalRecord).where(
            MedicalRecord.id == record_id,
            MedicalRecord.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


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
    """Send an e-Nalaz (finding) to CEZIH via ITI-65."""
    from app.models.patient import Patient

    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

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

    try:
        identifier_system, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    patient_data = {
        "mbo": identifier_value,
        "identifier_system": identifier_system,
        "identifier_value": identifier_value,
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
            http_client,
            patient_data,
            record_data,
            practitioner_id=practitioner_id,
            org_code=org_code or "",
            source_oid=source_oid or "",
            encounter_id=encounter_id,
            case_id=case_id,
            practitioner_name=practitioner_name,
        )
    except CezihError as e:
        logger.error("CEZIH e-Nalaz send failed: %s", e.message)
        await record_cezih_error("medical_record", record_id, tenant_id, e)
        _raise_cezih_error(e)

    await clear_cezih_error("medical_record", record_id, tenant_id, session=db)
    ref = result["reference_id"]
    doc_oid = result.get("document_oid", "")
    now = datetime.now(UTC)

    if record:
        record.cezih_sent = True
        record.cezih_sent_at = now
        record.cezih_reference_id = ref
        if doc_oid:
            record.cezih_document_oid = doc_oid
        if encounter_id:
            record.cezih_encounter_id = encounter_id
        if case_id:
            record.cezih_case_id = case_id
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

    await db.commit()
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
    """Send an e-Recept (prescription) to CEZIH."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

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
    try:
        identifier_system, identifier_value = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    patient_data = {
        "mbo": identifier_value,
        "identifier_system": identifier_system,
        "identifier_value": identifier_value,
        "ime": patient.ime,
        "prezime": patient.prezime,
    }

    try:
        result = await real_service.send_erecept(http_client, patient_data, lijekovi)
    except CezihError as e:
        logger.error("CEZIH e-Recept send failed: %s", e.message)
        _raise_cezih_error(e)

    recept_id = result["recept_id"]

    await _write_audit(
        db,
        tenant_id,
        user_id,
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
    """Cancel an e-Recept on CEZIH."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.cancel_erecept(http_client, recept_id)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="e_recept_cancel",
        details={"recept_id": recept_id},
    )
    return result


async def sign_document(
    document_bytes: bytes | str,
    *,
    document_id: str | None = None,
    http_client=None,
) -> dict:
    """Sign a document via CEZIH signing service."""
    if not http_client:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="HTTP client not available")

    from app.services.cezih_signing import sign_document as real_sign_document

    try:
        result = await real_sign_document(
            http_client,
            document_bytes,
            document_id=document_id,
        )
    except CezihSigningError as e:
        logger.error("CEZIH signing failed: %s", e.message)
        _raise_cezih_error(e)

    return result


async def dispatch_search_documents(
    *,
    patient_id: UUID | None = None,
    document_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_filter: str | None = None,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> list[dict]:
    """Search for documents on CEZIH (ITI-67)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    patient_system: str | None = None
    patient_value: str | None = None
    if patient_id is not None:
        from app.models.patient import Patient

        patient = await db.get(Patient, patient_id)
        if not patient or patient.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")
        try:
            patient_system, patient_value = real_service.resolve_cezih_identifier(patient)
        except CezihError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    try:
        result = await real_service.search_documents(
            http_client,
            patient_system=patient_system,
            patient_value=patient_value,
            document_type=document_type,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
        )
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="document_search",
        details={
            "patient_id": str(patient_id) if patient_id else "",
            "type": document_type or "",
        },
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
    """Replace a document on CEZIH (ITI-65 replace, used for cancel/storno)."""
    from app.models.patient import Patient

    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    # Load full record and patient data from DB (same pattern as send_enalaz)
    if not record_id and db and tenant_id and not (patient_data and record_data):
        from app.models.medical_record import MedicalRecord

        db_result = await db.execute(
            sa_select(MedicalRecord).where(
                MedicalRecord.tenant_id == tenant_id,
                MedicalRecord.cezih_reference_id == original_reference_id,
            )
        )
        found = db_result.scalar_one_or_none()
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
                    try:
                        id_sys, id_val = real_service.resolve_cezih_identifier(patient)
                    except CezihError as e:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e
                    patient_data = {
                        "mbo": id_val,
                        "identifier_system": id_sys,
                        "identifier_value": id_val,
                        "ime": patient.ime,
                        "prezime": patient.prezime,
                    }
            if not encounter_id and record.cezih_encounter_id:
                encounter_id = record.cezih_encounter_id
            if not case_id and record.cezih_case_id:
                case_id = record.cezih_case_id

    # Use stored OID if available — avoids unreliable ITI-67 lookup
    stored_oid = ""
    if record and hasattr(record, "cezih_document_oid"):
        stored_oid = record.cezih_document_oid or ""

    try:
        result = await real_service.replace_document(
            http_client,
            original_reference_id,
            patient_data or {},
            record_data or {},
            practitioner_id=practitioner_id,
            org_code=org_code,
            encounter_id=encounter_id,
            case_id=case_id,
            practitioner_name=practitioner_name,
            original_document_oid=stored_oid,
        )
    except CezihError as e:
        await record_cezih_error("medical_record", record_id, tenant_id, e)
        _raise_cezih_error(e)

    await clear_cezih_error("medical_record", record_id, tenant_id, session=db)
    # Update the DB record's reference_id and OID to the new document created by replace
    new_ref = result.get("new_reference_id")
    new_oid = result.get("new_document_oid", "")
    if record_id and new_ref:
        record = await _get_medical_record_by_id(db, tenant_id, record_id)
        if record:
            record.cezih_reference_id = new_ref
            if new_oid:
                record.cezih_document_oid = new_oid
            record.cezih_last_replaced_at = datetime.now(UTC)
            await db.flush()

    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="e_nalaz_replace",
        details={"reference_id": original_reference_id, "new_reference_id": new_ref},
    )
    if db:
        await db.commit()
    return result


async def dispatch_replace_document_with_edit(
    original_reference_id: str,
    record_id: UUID,
    patient_id: UUID,
    edits: dict,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
    org_code: str = "",
    practitioner_id: str | None = None,
    practitioner_name: str = "",
    encounter_id: str = "",
    case_id: str = "",
) -> dict:
    """Atomic edit-and-replace. Signs + calls CEZIH ITI-65 replace using the
    PROPOSED content, and only on 2xx applies the edits to the local
    medical_record + swaps cezih_reference_id/oid. On failure the record is
    untouched so local DB does not diverge from CEZIH — exactly the bug the
    old PATCH-then-PUT flow was causing."""
    from app.models.patient import Patient

    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    record = await _get_medical_record(db, tenant_id, patient_id, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicinski zapis nije pronađen")

    if record.cezih_reference_id != original_reference_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referenca e-Nalaza ne odgovara trenutnoj verziji zapisa. Osvježite prikaz i pokušajte ponovno.",
        )

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")
    try:
        id_sys, id_val = real_service.resolve_cezih_identifier(patient)
    except CezihError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    patient_data = {
        "mbo": id_val,
        "identifier_system": id_sys,
        "identifier_value": id_val,
        "ime": patient.ime,
        "prezime": patient.prezime,
    }

    # Merge proposed edits over current record state. Only non-None keys
    # override — so a partial edit still produces a complete FHIR bundle.
    def _pick(key: str, fallback):
        val = edits.get(key)
        return val if val is not None else fallback

    new_tip = _pick("tip", record.tip)
    new_dijagnoza_mkb = _pick("dijagnoza_mkb", record.dijagnoza_mkb)
    new_dijagnoza_tekst = _pick("dijagnoza_tekst", record.dijagnoza_tekst)
    new_sadrzaj = _pick("sadrzaj", record.sadrzaj)
    new_preporucena = _pick("preporucena_terapija", record.preporucena_terapija)

    record_data = {
        "tip": new_tip,
        "dijagnoza_mkb": new_dijagnoza_mkb,
        "dijagnoza_tekst": new_dijagnoza_tekst,
        "sadrzaj": new_sadrzaj,
        "preporucena_terapija": new_preporucena,
        "created_at": record.created_at.isoformat() if record.created_at else _now_iso(),
    }

    if not practitioner_id and record.doktor_id:
        practitioner_id = str(record.doktor_id)
    if not encounter_id and record.cezih_encounter_id:
        encounter_id = record.cezih_encounter_id
    if not case_id and record.cezih_case_id:
        case_id = record.cezih_case_id

    # Use stored OID if available — avoids unreliable ITI-67 lookup
    stored_oid = record.cezih_document_oid or "" if record else ""

    try:
        result = await real_service.replace_document(
            http_client,
            original_reference_id,
            patient_data,
            record_data,
            practitioner_id=practitioner_id,
            org_code=org_code,
            encounter_id=encounter_id,
            case_id=case_id,
            practitioner_name=practitioner_name,
            original_document_oid=stored_oid,
        )
    except CezihError as e:
        await record_cezih_error("medical_record", record_id, tenant_id, e)
        _raise_cezih_error(e)

    # CEZIH 2xx — apply the edits + swap reference. These happen in the
    # request's own transaction, so if commit fails the next read still shows
    # the pre-edit state AND CEZIH has the new document (acceptable
    # divergence, corrected by user retry — versus the worse old behavior
    # where local edits stuck but CEZIH was stale).
    new_ref = result.get("new_reference_id")
    new_oid = result.get("new_document_oid", "")

    for attr in ("tip", "dijagnoza_mkb", "dijagnoza_tekst", "sadrzaj", "preporucena_terapija"):
        val = edits.get(attr)
        if val is not None:
            setattr(record, attr, val)
    if edits.get("datum") is not None:
        record.datum = edits["datum"]
    if edits.get("sensitivity") is not None:
        record.sensitivity = edits["sensitivity"]
    if new_ref:
        record.cezih_reference_id = new_ref
    if new_oid:
        record.cezih_document_oid = new_oid
    record.cezih_last_replaced_at = datetime.now(UTC)
    await db.flush()

    await clear_cezih_error("medical_record", record_id, tenant_id, session=db)

    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="e_nalaz_replace_with_edit",
        details={
            "reference_id": original_reference_id,
            "new_reference_id": new_ref,
            "edited_fields": sorted(k for k, v in edits.items() if v is not None),
        },
    )
    await db.commit()
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
    """Cancel/storno a document on CEZIH (via ITI-65 replace)."""
    from app.models.medical_record import MedicalRecord
    from app.models.patient import Patient

    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    # Look up the record by cezih_reference_id — need full record data for ITI-65 bundle
    patient_data: dict = {}
    record_data: dict = {}
    encounter_id = ""
    case_id = ""
    record_id: UUID | None = None
    if db and tenant_id:
        query_result = await db.execute(
            sa_select(MedicalRecord).where(
                MedicalRecord.tenant_id == tenant_id,
                MedicalRecord.cezih_reference_id == reference_id,
            )
        )
        record = query_result.scalar_one_or_none()
        if record:
            record_id = record.id
            if record.patient_id:
                patient = await db.get(Patient, record.patient_id)
                if patient:
                    try:
                        id_sys, id_val = real_service.resolve_cezih_identifier(patient)
                    except CezihError as e:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e
                    patient_data = {
                        "mbo": id_val,
                        "identifier_system": id_sys,
                        "identifier_value": id_val,
                        "ime": patient.ime,
                        "prezime": patient.prezime,
                    }
            encounter_id = record.cezih_encounter_id or ""
            case_id = record.cezih_case_id or ""
            if not practitioner_id and record.doktor_id:
                practitioner_id = str(record.doktor_id)
            record_data = {
                "tip": record.tip,
                "dijagnoza_mkb": record.dijagnoza_mkb,
                "dijagnoza_tekst": record.dijagnoza_tekst,
                "sadrzaj": f"Storno dokumenta {reference_id}",
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

    # Use stored OID if available — avoids unreliable ITI-67 lookup
    stored_oid = ""
    if record:
        stored_oid = record.cezih_document_oid or ""

    try:
        result = await real_service.cancel_document(
            http_client,
            reference_id,
            patient_data=patient_data,
            record_data=record_data,
            org_code=org_code,
            practitioner_id=practitioner_id,
            encounter_id=encounter_id,
            case_id=case_id,
            practitioner_name=practitioner_name,
            original_document_oid=stored_oid,
        )
    except CezihError as e:
        await record_cezih_error("medical_record", record_id, tenant_id, e)
        _raise_cezih_error(e)

    await clear_cezih_error("medical_record", record_id, tenant_id, session=db)
    # Mark record as storniran in DB
    if db and tenant_id:
        rec_result = await db.execute(
            sa_select(MedicalRecord).where(
                MedicalRecord.tenant_id == tenant_id,
                MedicalRecord.cezih_reference_id == reference_id,
            )
        )
        rec = rec_result.scalar_one_or_none()
        if rec:
            rec.cezih_storno = True
            await db.flush()

    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="e_nalaz_cancel",
        details={"reference_id": reference_id, "new_reference_id": result.get("new_reference_id")},
    )
    if db:
        await db.commit()
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
    """Retrieve a document from CEZIH (ITI-68)."""
    from app.models.medical_record import MedicalRecord

    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    # Resolve reference_id to local MedicalRecord.id so we can mark row errors
    record_id: UUID | None = None
    lookup = await db.execute(
        sa_select(MedicalRecord.id).where(
            MedicalRecord.tenant_id == tenant_id,
            MedicalRecord.cezih_reference_id == reference_id,
        )
    )
    row = lookup.first()
    if row:
        record_id = row[0]

    try:
        result = await real_service.retrieve_document(http_client, document_url or reference_id)
    except CezihFhirError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nije pronađen na CEZIH-u.",
            ) from e
        await record_cezih_error("medical_record", record_id, tenant_id, e)
        _raise_cezih_error(e)
    except CezihError as e:
        await record_cezih_error("medical_record", record_id, tenant_id, e)
        _raise_cezih_error(e)

    await clear_cezih_error("medical_record", record_id, tenant_id, session=db)
    await _write_audit(
        db,
        tenant_id,
        user_id,
        action="document_retrieve",
        details={"reference_id": reference_id},
    )
    return result


__all__ = [
    "_get_medical_record",
    "_get_medical_record_by_id",
    "send_enalaz",
    "send_erecept",
    "cancel_erecept",
    "sign_document",
    "dispatch_search_documents",
    "dispatch_replace_document",
    "dispatch_replace_document_with_edit",
    "dispatch_cancel_document",
    "dispatch_retrieve_document",
]

"""CEZIH patient dispatcher — import, insurance checks, foreigner registration."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cezih import service as real_service
from app.services.cezih.dispatchers.common import _raise_cezih_error, _require_audit_params, _write_audit
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)


async def import_patient_from_cezih(
    mbo: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    """Fetch patient demographics from CEZIH and create a new local patient.

    Uses search_patient_by_identifier for full data (address, phone, email, all identifiers).
    """
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from datetime import date as date_type

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
        cezih_data = await real_service.search_patient_by_identifier(
            http_client, identifier_system="mbo", value=mbo, tenant_id=tenant_id,
        )
    except CezihError as e:
        logger.error("CEZIH patient import failed: %s", e.message)
        _raise_cezih_error(e)

    # Extract identifiers
    idents: dict[str, str] = {}
    for ident in cezih_data.get("identifikatori") or []:
        sys_uri = ident.get("system")
        val = ident.get("value")
        if sys_uri and val:
            idents[sys_uri] = val

    oib = idents.get(real_service.SYS_OIB)
    cezih_patient_id = idents.get(real_service.SYS_JEDINSTVENI) or cezih_data.get("cezih_id") or None

    # Parse date string to date object
    dob = None
    if cezih_data.get("datum_rodjenja"):
        try:
            dob = date_type.fromisoformat(cezih_data["datum_rodjenja"])
        except ValueError:
            pass

    spol_norm = cezih_data.get("spol") or None
    if spol_norm == "Ž":
        spol_norm = "Z"
    elif spol_norm not in ("M", "Z"):
        spol_norm = None

    addr = cezih_data.get("adresa") or {}

    patient = Patient(
        tenant_id=tenant_id,
        ime=cezih_data.get("ime") or "Nepoznato",
        prezime=cezih_data.get("prezime") or "Nepoznato",
        datum_rodjenja=dob,
        spol=spol_norm,
        oib=oib,
        mbo=mbo,
        cezih_patient_id=cezih_patient_id,
        adresa=addr.get("ulica") or None,
        grad=addr.get("grad") or None,
        postanski_broj=addr.get("postanski_broj") or None,
        telefon=cezih_data.get("telefon") or None,
        email=cezih_data.get("email") or None,
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


async def import_patient_by_identifier(
    identifier_type: str,
    identifier_value: str,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> dict:
    """Fetch patient demographics from CEZIH by any identifier and create locally.

    Works for both Croatian insured patients (MBO) and foreigners (EHIC, passport).
    Populates all identifier columns found in the PDQm response, so e-Karton flows
    can route subsequent queries through the priority resolver.
    """
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)

    from datetime import date as date_type

    from app.models.patient import Patient
    from app.services.cezih.service import (
        SYS_EUROPSKA,
        SYS_JEDINSTVENI,
        SYS_MBO,
        SYS_OIB,
        SYS_PUTOVNICA,
    )

    try:
        cezih_data = await real_service.search_patient_by_identifier(
            http_client, identifier_system=identifier_type, value=identifier_value,
            tenant_id=tenant_id,
        )
    except CezihError as e:
        logger.error("CEZIH patient import (%s) failed: %s", identifier_type, e.message)
        _raise_cezih_error(e)

    # Extract each CEZIH identifier from the response.
    idents: dict[str, str] = {}
    for ident in cezih_data.get("identifikatori") or []:
        sys_uri = ident.get("system")
        val = ident.get("value")
        if sys_uri and val:
            idents[sys_uri] = val

    mbo = idents.get(SYS_MBO)
    oib = idents.get(SYS_OIB)
    putovnica = idents.get(SYS_PUTOVNICA)
    ehic = idents.get(SYS_EUROPSKA)
    cezih_patient_id = idents.get(SYS_JEDINSTVENI) or (cezih_data.get("cezih_id") or None)

    # Duplicate check across all identifier columns — return 409 with the
    # existing patient so the UI can link to it instead of silently failing.
    dup_filters = []
    if mbo:
        dup_filters.append(Patient.mbo == mbo)
    if oib:
        dup_filters.append(Patient.oib == oib)
    if putovnica:
        dup_filters.append(Patient.broj_putovnice == putovnica)
    if ehic:
        dup_filters.append(Patient.ehic_broj == ehic)
    if cezih_patient_id:
        dup_filters.append(Patient.cezih_patient_id == cezih_patient_id)

    if dup_filters:
        from sqlalchemy import or_
        existing = await db.execute(
            select(Patient).where(
                Patient.tenant_id == tenant_id,
                Patient.is_active.is_(True),
                or_(*dup_filters),
            ).limit(1),
        )
        existing_patient = existing.scalar_one_or_none()
        if existing_patient:
            # Update CEZIH-synced fields with fresh data
            if mbo and not existing_patient.mbo:
                existing_patient.mbo = mbo
            if oib and not existing_patient.oib:
                existing_patient.oib = oib
            if putovnica and not existing_patient.broj_putovnice:
                existing_patient.broj_putovnice = putovnica
            if ehic and not existing_patient.ehic_broj:
                existing_patient.ehic_broj = ehic
            if cezih_patient_id and not existing_patient.cezih_patient_id:
                existing_patient.cezih_patient_id = cezih_patient_id
            addr = cezih_data.get("adresa") or {}
            if addr.get("ulica") and not existing_patient.adresa:
                existing_patient.adresa = addr["ulica"]
            if addr.get("grad") and not existing_patient.grad:
                existing_patient.grad = addr["grad"]
            if addr.get("postanski_broj") and not existing_patient.postanski_broj:
                existing_patient.postanski_broj = addr["postanski_broj"]
            if cezih_data.get("telefon") and not existing_patient.telefon:
                existing_patient.telefon = cezih_data["telefon"]
            if cezih_data.get("email") and not existing_patient.email:
                existing_patient.email = cezih_data["email"]
            existing_patient.cezih_insurance_status = "Aktivan" if mbo else None
            existing_patient.cezih_insurance_checked_at = datetime.now(UTC) if mbo else None
            await db.flush()

            return {
                "id": str(existing_patient.id),
                "ime": existing_patient.ime,
                "prezime": existing_patient.prezime,
                "datum_rodjenja": existing_patient.datum_rodjenja.isoformat()
                    if existing_patient.datum_rodjenja else None,
                "oib": existing_patient.oib,
                "spol": existing_patient.spol,
                "mbo": existing_patient.mbo,
                "broj_putovnice": existing_patient.broj_putovnice,
                "ehic_broj": existing_patient.ehic_broj,
                "cezih_patient_id": existing_patient.cezih_patient_id,
                "already_exists": True,
            }

    dob = None
    raw_dob = cezih_data.get("datum_rodjenja")
    if raw_dob:
        try:
            dob = date_type.fromisoformat(raw_dob)
        except ValueError:
            pass

    spol_norm = cezih_data.get("spol") or None
    if spol_norm == "Ž":
        spol_norm = "Z"  # patient.spol CHECK constraint allows only 'M' | 'Z'
    elif spol_norm not in ("M", "Z"):
        if spol_norm:
            logger.info("CEZIH patient gender %r cannot be stored (CHECK M|Z), setting None", spol_norm)
        spol_norm = None

    addr = cezih_data.get("adresa") or {}
    drzava = (addr.get("drzava") or "").upper() or None

    patient = Patient(
        tenant_id=tenant_id,
        ime=cezih_data.get("ime") or "Nepoznato",
        prezime=cezih_data.get("prezime") or "Nepoznato",
        datum_rodjenja=dob,
        spol=spol_norm,
        oib=oib,
        mbo=mbo,
        broj_putovnice=putovnica,
        ehic_broj=ehic,
        cezih_patient_id=cezih_patient_id,
        drzavljanstvo=drzava if drzava and len(drzava) <= 3 else None,
        adresa=addr.get("ulica") or None,
        grad=addr.get("grad") or None,
        postanski_broj=addr.get("postanski_broj") or None,
        telefon=cezih_data.get("telefon") or None,
        email=cezih_data.get("email") or None,
        cezih_insurance_status="Aktivan" if mbo else None,
        cezih_insurance_checked_at=datetime.now(UTC) if mbo else None,
    )
    db.add(patient)

    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pacijent s tim podacima već postoji",
        ) from e

    await db.refresh(patient)

    await _write_audit(
        db, tenant_id, user_id,
        action="cezih_patient_import",
        resource_id=patient.id,
        details={
            "identifier_type": identifier_type,
            "identifier_value": identifier_value,
            "ime": patient.ime,
            "prezime": patient.prezime,
        },
    )

    return {
        "id": str(patient.id),
        "ime": patient.ime,
        "prezime": patient.prezime,
        "datum_rodjenja": patient.datum_rodjenja.isoformat() if patient.datum_rodjenja else None,
        "oib": patient.oib,
        "spol": patient.spol,
        "mbo": patient.mbo,
        "broj_putovnice": patient.broj_putovnice,
        "ehic_broj": patient.ehic_broj,
        "cezih_patient_id": patient.cezih_patient_id,
        "already_exists": False,
    }


async def _persist_insurance_to_patient_by_id(
    db: AsyncSession, patient_id: UUID, status_osiguranja: str,
) -> None:
    """Update patient's cached insurance status by patient UUID."""
    from app.models.patient import Patient

    patient = await db.get(Patient, patient_id)
    if patient:
        patient.cezih_insurance_status = status_osiguranja
        patient.cezih_insurance_checked_at = datetime.now(UTC)
        await db.flush()


async def insurance_check_by_identifier(
    identifier_type: str,
    identifier_value: str,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> dict:
    """Ad-hoc insurance check for a walk-in by MBO, EHIC, or passport.

    Uses search_patient_by_identifier (richer PDQm) instead of check_insurance
    so the result is cached for subsequent import — avoids double CEZIH call.
    Also detects deceased patients via deceasedDateTime.
    """
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    system_uri = real_service._IDENTIFIER_SYSTEM_MAP.get(identifier_type)
    if not system_uri:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nepoznati tip identifikatora: {identifier_type}",
        )
    try:
        cezih_data = await real_service.search_patient_by_identifier(
            http_client, identifier_system=identifier_type, value=identifier_value,
            tenant_id=tenant_id,
        )
    except CezihError as e:
        logger.error("CEZIH ad-hoc insurance check (%s) failed: %s", identifier_type, e.message)
        _raise_cezih_error(e)

    # Build insurance-check response from richer PDQm data
    status_osiguranja = "Aktivan"
    if cezih_data.get("datum_smrti"):
        status_osiguranja = "Preminuo"

    oib = ""
    for ident in cezih_data.get("identifikatori") or []:
        if ident.get("system", "").endswith("/OIB") and ident.get("value"):
            oib = ident["value"]

    result = {
        "mbo": identifier_value,
        "ime": cezih_data.get("ime", ""),
        "prezime": cezih_data.get("prezime", ""),
        "datum_rodjenja": cezih_data.get("datum_rodjenja", ""),
        "oib": oib,
        "spol": cezih_data.get("spol", ""),
        "osiguravatelj": "HZZO" if status_osiguranja == "Aktivan" else "",
        "status_osiguranja": status_osiguranja,
        "datum_smrti": cezih_data.get("datum_smrti", ""),
    }

    await _write_audit(
        db, tenant_id, user_id,
        action="insurance_check",
        details={
            "identifier_type": identifier_type,
            "identifier_value": identifier_value,
            "result": result["status_osiguranja"],
        },
    )
    return result


async def insurance_check_by_mbo(
    mbo: str,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> dict:
    """Backward-compat wrapper — forwards to insurance_check_by_identifier('mbo', ...)."""
    return await insurance_check_by_identifier(
        "mbo", mbo, db=db, user_id=user_id, tenant_id=tenant_id, http_client=http_client,
    )


async def insurance_check(
    patient_id: UUID,
    *,
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    http_client=None,
) -> dict:
    """Check CEZIH insurance/demographics for a local patient.

    Resolves the best CEZIH identifier (MBO > jedinstveni-id > EHIC > passport)
    from the patient record and runs PDQm. Works for Croatian-insured and
    PMIR-registered foreigners alike.
    """
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
        result = await real_service.check_insurance(http_client, system_uri, value)
    except CezihError as e:
        logger.error("CEZIH insurance check failed: %s", e.message)
        _raise_cezih_error(e)

    await _persist_insurance_to_patient_by_id(
        db, patient_id, result.get("status_osiguranja", ""),
    )

    await _write_audit(
        db, tenant_id, user_id,
        action="insurance_check",
        resource_id=patient_id,
        details={
            "identifier_system": system_uri,
            "identifier_value": value,
            "result": result.get("status_osiguranja"),
        },
    )

    return result


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
    """Register a foreigner in CEZIH via PMIR (ITI-93)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.register_foreigner(
            http_client, patient_data, org_code=org_code, source_oid=source_oid,
            practitioner_id=practitioner_id,
        )
    except CezihError as e:
        if "ERR_FOREIGNPATIENT_1002" in e.message or "already exists" in e.message.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent je već registriran u CEZIH-u. Pretražite ga po putovnici ili EHIC-u i dodajte u kartoteku.",
            ) from e
        _raise_cezih_error(e)
    patient_name = f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}"
    await _write_audit(
        db, tenant_id, user_id, action="foreigner_register",
        details={"patient_name": patient_name},
    )
    return result


__all__ = [
    "import_patient_from_cezih",
    "import_patient_by_identifier",
    "_persist_insurance_to_patient_by_id",
    "insurance_check_by_identifier",
    "insurance_check_by_mbo",
    "insurance_check",
    "foreigner_registration",
]

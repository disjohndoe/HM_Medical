import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import RECORD_TIP_ALLOWED
from app.models.medical_record import MedicalRecord
from app.models.patient import Patient
from app.models.record_type import RecordType
from app.models.user import User
from app.schemas.medical_record import MedicalRecordCreate, MedicalRecordUpdate
from app.services import prescription_service


async def _validate_tip_for_tenant(db: AsyncSession, tenant_id: uuid.UUID, tip: str) -> None:
    """Raise 422 if tip is not an active record type for this tenant."""
    result = await db.execute(
        select(RecordType)
        .where(
            RecordType.tenant_id == tenant_id,
            RecordType.slug == tip,
            RecordType.is_active.is_(True),
        )
        .limit(1)
    )
    if not result.scalar_one_or_none() and tip not in RECORD_TIP_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nepoznat tip zapisa '{tip}'. Kontaktirajte administratora.",
        )


def _join_record_query(base):
    return (
        base.outerjoin(User, MedicalRecord.doktor_id == User.id)
        .outerjoin(Patient, MedicalRecord.patient_id == Patient.id)
        .add_columns(
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
            Patient.ime.label("patient_ime"),
            Patient.prezime.label("patient_prezime"),
            Patient.mbo.label("patient_mbo"),
            Patient.cezih_patient_id.label("patient_cezih_patient_id"),
            Patient.ehic_broj.label("patient_ehic_broj"),
            Patient.broj_putovnice.label("patient_broj_putovnice"),
        )
    )


def _record_row_to_dict(row) -> dict:
    rec = row[0]
    patient_has_cezih = bool(
        row.patient_mbo or row.patient_cezih_patient_id or row.patient_ehic_broj or row.patient_broj_putovnice
    )
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "patient_id": rec.patient_id,
        "doktor_id": rec.doktor_id,
        "appointment_id": rec.appointment_id,
        "datum": rec.datum,
        "tip": rec.tip,
        "dijagnoza_mkb": rec.dijagnoza_mkb,
        "dijagnoza_tekst": rec.dijagnoza_tekst,
        "sadrzaj": rec.sadrzaj,
        "cezih_sent": rec.cezih_sent,
        "cezih_sent_at": rec.cezih_sent_at,
        "cezih_reference_id": rec.cezih_reference_id,
        "cezih_storno": rec.cezih_storno,
        "cezih_encounter_id": rec.cezih_encounter_id,
        "cezih_case_id": rec.cezih_case_id,
        "sensitivity": rec.sensitivity,
        "preporucena_terapija": rec.preporucena_terapija,
        "doktor_ime": row.doktor_ime,
        "doktor_prezime": row.doktor_prezime,
        "patient_ime": row.patient_ime,
        "patient_prezime": row.patient_prezime,
        "patient_mbo": row.patient_mbo,
        "patient_has_cezih_identifier": patient_has_cezih,
        "cezih_last_error_code": rec.cezih_last_error_code,
        "cezih_last_error_display": rec.cezih_last_error_display,
        "cezih_last_error_diagnostics": rec.cezih_last_error_diagnostics,
        "cezih_last_error_at": rec.cezih_last_error_at,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }


async def list_records(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    tip: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cezih_sent: bool | None = None,
    skip: int = 0,
    limit: int = 20,
    user_role: str | None = None,
) -> tuple[list[dict], int]:
    conditions = [MedicalRecord.tenant_id == tenant_id]

    if patient_id:
        conditions.append(MedicalRecord.patient_id == patient_id)
    if tip:
        conditions.append(MedicalRecord.tip == tip)
    if date_from:
        conditions.append(MedicalRecord.datum >= date_from)
    if date_to:
        conditions.append(MedicalRecord.datum <= date_to)
    if cezih_sent is not None:
        conditions.append(MedicalRecord.cezih_sent == cezih_sent)

    # Nurse sensitivity filter
    if user_role == "nurse":
        conditions.append(MedicalRecord.sensitivity.in_(["standard", "nursing"]))

    base = select(MedicalRecord).where(and_(*conditions))
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = _join_record_query(base)
    result = await db.execute(query.order_by(MedicalRecord.datum.desc()).offset(skip).limit(limit))
    return [_record_row_to_dict(row) for row in result.all()], total


async def get_record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    user_role: str | None = None,
) -> dict:
    base = select(MedicalRecord).where(
        MedicalRecord.id == record_id,
        MedicalRecord.tenant_id == tenant_id,
    )
    query = _join_record_query(base)
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicinski zapis nije pronađen")

    record = row[0]
    # Nurse cannot view restricted records
    if user_role == "nurse" and record.sensitivity == "restricted":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nemate pristup ovom zapisu")

    return _record_row_to_dict(row)


async def create_record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: MedicalRecordCreate,
    doktor_id: uuid.UUID,
) -> dict:
    patient = await db.get(Patient, data.patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    await _validate_tip_for_tenant(db, tenant_id, data.tip)

    therapy_dump = [t.model_dump() for t in data.preporucena_terapija] if data.preporucena_terapija else None
    record = MedicalRecord(
        tenant_id=tenant_id,
        patient_id=data.patient_id,
        doktor_id=doktor_id,
        appointment_id=data.appointment_id,
        datum=data.datum,
        tip=data.tip,
        dijagnoza_mkb=data.dijagnoza_mkb,
        dijagnoza_tekst=data.dijagnoza_tekst,
        sadrzaj=data.sadrzaj,
        sensitivity=data.sensitivity,
        preporucena_terapija=therapy_dump,
    )
    db.add(record)
    await db.flush()

    if therapy_dump:
        await prescription_service.upsert_draft_from_record(
            db,
            tenant_id=tenant_id,
            patient_id=record.patient_id,
            medical_record_id=record.id,
            doktor_id=doktor_id,
            therapy_items=therapy_dump,
            user_id=doktor_id,
        )

    return await get_record(db, tenant_id, record.id)


async def update_record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    data: MedicalRecordUpdate,
    user_id: uuid.UUID | None = None,
) -> dict:
    record = await db.get(MedicalRecord, record_id)
    if not record or record.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicinski zapis nije pronađen")

    update_data = data.model_dump(exclude_unset=True)

    if "tip" in update_data:
        await _validate_tip_for_tenant(db, tenant_id, update_data["tip"])

    for field, value in update_data.items():
        setattr(record, field, value)

    await db.flush()

    # Sync linked draft recept when therapy changes and there are items to propagate.
    if "preporucena_terapija" in update_data and update_data["preporucena_terapija"]:
        await prescription_service.upsert_draft_from_record(
            db,
            tenant_id=tenant_id,
            patient_id=record.patient_id,
            medical_record_id=record.id,
            doktor_id=record.doktor_id,
            therapy_items=update_data["preporucena_terapija"],
            user_id=user_id or record.doktor_id,
        )

    return await get_record(db, tenant_id, record_id)

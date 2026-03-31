import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical_record import MedicalRecord
from app.models.user import User
from app.schemas.medical_record import MedicalRecordCreate, MedicalRecordUpdate


def _join_record_query(base):
    return (
        base.outerjoin(User, MedicalRecord.doktor_id == User.id)
        .add_columns(
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
        )
    )


def _record_row_to_dict(row) -> dict:
    rec = row[0]
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
        "sensitivity": rec.sensitivity,
        "doktor_ime": row.doktor_ime,
        "doktor_prezime": row.doktor_prezime,
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

    # Nurse sensitivity filter
    if user_role == "nurse":
        conditions.append(MedicalRecord.sensitivity.in_(["standard", "nursing"]))

    base = select(MedicalRecord).where(and_(*conditions))
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = _join_record_query(base)
    result = await db.execute(
        query.order_by(MedicalRecord.datum.desc()).offset(skip).limit(limit)
    )
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
    )
    db.add(record)
    await db.flush()

    return await get_record(db, tenant_id, record.id)


async def update_record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    data: MedicalRecordUpdate,
) -> dict:
    record = await db.get(MedicalRecord, record_id)
    if not record or record.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicinski zapis nije pronađen")

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(record, field, value)

    await db.flush()
    return await get_record(db, tenant_id, record_id)

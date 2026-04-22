import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.models.procedure import PerformedProcedure, Procedure
from app.models.user import User
from app.schemas.procedure import PerformedProcedureCreate, ProcedureCreate, ProcedureUpdate


async def list_procedures(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    kategorija: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Procedure], int]:
    base = select(Procedure).where(
        Procedure.tenant_id == tenant_id,
        Procedure.is_active.is_(True),
    )

    if kategorija:
        base = base.where(Procedure.kategorija == kategorija)

    if search:
        escaped = search.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        base = base.where(
            or_(
                Procedure.sifra.ilike(pattern),
                Procedure.naziv.ilike(pattern),
                Procedure.opis.ilike(pattern),
            )
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(base.order_by(Procedure.sifra).offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_procedure(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: ProcedureCreate,
) -> Procedure:
    existing = await db.execute(
        select(Procedure).where(
            Procedure.sifra == data.sifra,
            Procedure.tenant_id == tenant_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Postupak s tom šifrom već postoji",
        )

    procedure = Procedure(tenant_id=tenant_id, **data.model_dump())
    db.add(procedure)
    await db.flush()
    return procedure


async def update_procedure(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    procedure_id: uuid.UUID,
    data: ProcedureUpdate,
) -> Procedure:
    procedure = await db.get(Procedure, procedure_id)
    if not procedure or procedure.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postupak nije pronađen")

    update_data = data.model_dump(exclude_unset=True)

    if "sifra" in update_data and update_data["sifra"] != procedure.sifra:
        existing = await db.execute(
            select(Procedure).where(
                Procedure.sifra == update_data["sifra"],
                Procedure.tenant_id == tenant_id,
                Procedure.id != procedure_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Postupak s tom šifrom već postoji",
            )

    for field, value in update_data.items():
        setattr(procedure, field, value)

    await db.flush()
    await db.refresh(procedure)
    return procedure


async def delete_procedure(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    procedure_id: uuid.UUID,
) -> None:
    procedure = await db.get(Procedure, procedure_id)
    if not procedure or procedure.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postupak nije pronađen")
    procedure.is_active = False


def _join_performed_query(base):
    return (
        base.outerjoin(Procedure, PerformedProcedure.procedure_id == Procedure.id)
        .outerjoin(User, PerformedProcedure.doktor_id == User.id)
        .add_columns(
            Procedure.naziv.label("procedure_naziv"),
            Procedure.sifra.label("procedure_sifra"),
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
        )
    )


def _performed_row_to_dict(row) -> dict:
    pp = row[0]
    return {
        "id": pp.id,
        "tenant_id": pp.tenant_id,
        "patient_id": pp.patient_id,
        "appointment_id": pp.appointment_id,
        "medical_record_id": pp.medical_record_id,
        "procedure_id": pp.procedure_id,
        "doktor_id": pp.doktor_id,
        "lokacija": pp.lokacija,
        "datum": pp.datum,
        "cijena_cents": pp.cijena_cents,
        "napomena": pp.napomena,
        "procedure_naziv": row.procedure_naziv,
        "procedure_sifra": row.procedure_sifra,
        "doktor_ime": row.doktor_ime,
        "doktor_prezime": row.doktor_prezime,
        "created_at": pp.created_at,
        "updated_at": pp.updated_at,
    }


async def list_performed(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    appointment_id: uuid.UUID | None = None,
    medical_record_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[dict], int]:
    conditions = [PerformedProcedure.tenant_id == tenant_id]

    if patient_id:
        conditions.append(PerformedProcedure.patient_id == patient_id)
    if date_from:
        conditions.append(PerformedProcedure.datum >= date_from)
    if date_to:
        conditions.append(PerformedProcedure.datum <= date_to)
    if appointment_id:
        conditions.append(PerformedProcedure.appointment_id == appointment_id)
    if medical_record_id:
        conditions.append(PerformedProcedure.medical_record_id == medical_record_id)

    base = select(PerformedProcedure).where(and_(*conditions))
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = _join_performed_query(base)
    result = await db.execute(query.order_by(PerformedProcedure.datum.desc()).offset(skip).limit(limit))
    return [_performed_row_to_dict(row) for row in result.all()], total


async def create_performed(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: PerformedProcedureCreate,
    doktor_id: uuid.UUID,
) -> dict:
    procedure = await db.get(Procedure, data.procedure_id)
    if not procedure or procedure.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postupak nije pronađen")

    patient = await db.get(Patient, data.patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    cijena = data.cijena_cents if data.cijena_cents is not None else procedure.cijena_cents

    performed = PerformedProcedure(
        tenant_id=tenant_id,
        patient_id=data.patient_id,
        procedure_id=data.procedure_id,
        appointment_id=data.appointment_id,
        medical_record_id=data.medical_record_id,
        doktor_id=doktor_id,
        lokacija=data.lokacija,
        datum=data.datum,
        cijena_cents=cijena,
        napomena=data.napomena,
    )
    db.add(performed)
    await db.flush()

    # Fetch with joins
    base = select(PerformedProcedure).where(PerformedProcedure.id == performed.id)
    query = _join_performed_query(base)
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Greška pri dohvaćanju")
    return _performed_row_to_dict(row)

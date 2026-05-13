import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dts import DtsCode
from app.models.patient import Patient
from app.models.procedure import PerformedProcedure, Procedure
from app.models.user import User
from app.schemas.procedure import PerformedProcedureCreate, ProcedureCreate, ProcedureUpdate


async def list_procedures(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[dict], int]:
    base = (
        select(Procedure, DtsCode.display.label("dts_display"))
        .outerjoin(DtsCode, Procedure.dts_code_id == DtsCode.id)
        .where(
            Procedure.tenant_id == tenant_id,
            Procedure.is_active.is_(True),
        )
    )

    if search:
        escaped = search.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        base = base.where(
            or_(
                Procedure.sifra.ilike(pattern),
                Procedure.naziv.ilike(pattern),
                DtsCode.display.ilike(pattern),
            )
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(base.order_by(Procedure.sifra).offset(skip).limit(limit))
    rows = result.all()
    procedures = []
    for row in rows:
        p = row[0]
        d = {
            "id": p.id,
            "sifra": p.sifra,
            "naziv": p.naziv,
            "opis": p.opis,
            "cijena_cents": p.cijena_cents,
            "trajanje_minuta": p.trajanje_minuta,
            "kategorija": p.kategorija,
            "is_active": p.is_active,
            "tenant_id": p.tenant_id,
            "dts_code": p.dts_code,
            "dts_display": row.dts_display,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        procedures.append(d)
    return procedures, total


async def create_procedure(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: ProcedureCreate,
) -> Procedure:
    # Validate DTS code exists
    dts_result = await db.execute(select(DtsCode).where(DtsCode.code == data.dts_code))
    dts_code_row = dts_result.scalar_one_or_none()
    if not dts_code_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DTS šifra '{data.dts_code}' nije pronađena u šifrarniku",
        )

    # Check tenant doesn't already have this DTS code
    existing = await db.execute(
        select(Procedure).where(
            Procedure.dts_code == data.dts_code,
            Procedure.tenant_id == tenant_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Postupak s tom DTS šifrom već postoji",
        )

    procedure = Procedure(
        tenant_id=tenant_id,
        sifra=data.dts_code,
        naziv=dts_code_row.display,
        dts_code_id=dts_code_row.id,
        dts_code=data.dts_code,
        cijena_cents=data.cijena_cents,
        trajanje_minuta=data.trajanje_minuta,
        kategorija="",
    )
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


async def get_procedure_by_dts_code(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    dts_code: str,
) -> Procedure | None:
    result = await db.execute(
        select(Procedure).where(
            Procedure.tenant_id == tenant_id,
            Procedure.dts_code == dts_code,
            Procedure.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def ensure_procedure_for_dts(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    dts_code: str,
) -> Procedure:
    """Get or auto-create a procedure for the given DTS code."""
    existing = await get_procedure_by_dts_code(db, tenant_id, dts_code)
    if existing:
        return existing

    dts_result = await db.execute(select(DtsCode).where(DtsCode.code == dts_code))
    dts_row = dts_result.scalar_one_or_none()
    if not dts_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DTS šifra '{dts_code}' nije pronađena u šifrarniku",
        )

    procedure = Procedure(
        tenant_id=tenant_id,
        sifra=dts_code,
        naziv=dts_row.display,
        dts_code_id=dts_row.id,
        dts_code=dts_code,
        cijena_cents=0,
        trajanje_minuta=30,
        kategorija="",
    )
    db.add(procedure)
    await db.flush()
    return procedure


def _join_performed_query(base):
    return (
        base.outerjoin(Procedure, PerformedProcedure.procedure_id == Procedure.id)
        .outerjoin(DtsCode, Procedure.dts_code_id == DtsCode.id)
        .outerjoin(User, PerformedProcedure.doktor_id == User.id)
        .add_columns(
            Procedure.naziv.label("procedure_naziv"),
            Procedure.sifra.label("procedure_sifra"),
            DtsCode.code.label("dts_code"),
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
        "dts_code": row.dts_code,
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


async def delete_performed(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    performed_id: uuid.UUID,
) -> None:
    performed = await db.get(PerformedProcedure, performed_id)
    if not performed or performed.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Izvršeni postupak nije pronađen",
        )
    await db.delete(performed)


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

    base = select(PerformedProcedure).where(PerformedProcedure.id == performed.id)
    query = _join_performed_query(base)
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Greška pri dohvaćanju")
    return _performed_row_to_dict(row)

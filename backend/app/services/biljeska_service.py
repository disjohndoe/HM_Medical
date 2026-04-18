import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.biljeska import Biljeska
from app.models.patient import Patient
from app.models.user import User
from app.schemas.biljeska import BiljeskaCreate, BiljeskaUpdate


def _join_biljeska_query(base):
    return base.outerjoin(User, Biljeska.doktor_id == User.id).add_columns(
        User.ime.label("doktor_ime"),
        User.prezime.label("doktor_prezime"),
    )


def _biljeska_row_to_dict(row) -> dict:
    b = row[0]
    return {
        "id": b.id,
        "tenant_id": b.tenant_id,
        "patient_id": b.patient_id,
        "doktor_id": b.doktor_id,
        "datum": b.datum,
        "naslov": b.naslov,
        "sadrzaj": b.sadrzaj,
        "kategorija": b.kategorija,
        "is_pinned": b.is_pinned,
        "doktor_ime": row.doktor_ime,
        "doktor_prezime": row.doktor_prezime,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


async def list_biljeske(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    kategorija: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    conditions = [Biljeska.tenant_id == tenant_id]

    if patient_id:
        conditions.append(Biljeska.patient_id == patient_id)
    if kategorija:
        conditions.append(Biljeska.kategorija == kategorija)
    if date_from:
        conditions.append(Biljeska.datum >= date_from)
    if date_to:
        conditions.append(Biljeska.datum <= date_to)

    base = select(Biljeska).where(and_(*conditions))
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = _join_biljeska_query(base)
    result = await db.execute(
        query.order_by(Biljeska.is_pinned.desc(), Biljeska.datum.desc()).offset(skip).limit(limit)
    )
    return [_biljeska_row_to_dict(row) for row in result.all()], total


async def get_biljeska(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    biljeska_id: uuid.UUID,
) -> dict:
    base = select(Biljeska).where(
        Biljeska.id == biljeska_id,
        Biljeska.tenant_id == tenant_id,
    )
    query = _join_biljeska_query(base)
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilješka nije pronađena")
    return _biljeska_row_to_dict(row)


async def create_biljeska(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: BiljeskaCreate,
    doktor_id: uuid.UUID,
) -> dict:
    patient = await db.get(Patient, data.patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    biljeska = Biljeska(
        tenant_id=tenant_id,
        patient_id=data.patient_id,
        doktor_id=doktor_id,
        datum=data.datum,
        naslov=data.naslov,
        sadrzaj=data.sadrzaj,
        kategorija=data.kategorija,
    )
    db.add(biljeska)
    await db.flush()
    return await get_biljeska(db, tenant_id, biljeska.id)


async def update_biljeska(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    biljeska_id: uuid.UUID,
    data: BiljeskaUpdate,
) -> dict:
    biljeska = await db.get(Biljeska, biljeska_id)
    if not biljeska or biljeska.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilješka nije pronađena")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(biljeska, field, value)

    await db.flush()
    return await get_biljeska(db, tenant_id, biljeska_id)


async def delete_biljeska(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    biljeska_id: uuid.UUID,
) -> None:
    biljeska = await db.get(Biljeska, biljeska_id)
    if not biljeska or biljeska.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilješka nije pronađena")
    await db.delete(biljeska)
    await db.flush()

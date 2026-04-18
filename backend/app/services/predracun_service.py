import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.predracun import Predracun, PredracunCounter, PredracunStavka
from app.models.procedure import PerformedProcedure, Procedure


async def _next_broj(db: AsyncSession, tenant_id: uuid.UUID, year: int) -> str:
    """Get next sequential predračun number for tenant+year, with row-level lock."""
    # Ensure counter row exists
    existing = await db.execute(
        select(PredracunCounter).where(
            PredracunCounter.tenant_id == tenant_id,
            PredracunCounter.year == year,
        ).with_for_update()
    )
    counter = existing.scalar_one_or_none()

    if counter is None:
        counter = PredracunCounter(tenant_id=tenant_id, year=year, next_seq=1)
        db.add(counter)
        await db.flush()
        # Re-select with lock
        result = await db.execute(
            select(PredracunCounter).where(
                PredracunCounter.tenant_id == tenant_id,
                PredracunCounter.year == year,
            ).with_for_update()
        )
        counter = result.scalar_one()

    seq = counter.next_seq
    counter.next_seq = seq + 1
    return f"PRED-{year}-{seq:04d}"


async def create_predracun(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    performed_procedure_ids: list[uuid.UUID],
    napomena: str | None,
    created_by: uuid.UUID,
) -> dict:
    """Create a predračun from selected performed procedures."""
    # Fetch and validate all performed procedures
    result = await db.execute(
        select(PerformedProcedure, Procedure.sifra, Procedure.naziv)
        .outerjoin(Procedure, PerformedProcedure.procedure_id == Procedure.id)
        .where(
            PerformedProcedure.id.in_(performed_procedure_ids),
            PerformedProcedure.tenant_id == tenant_id,
        )
        .order_by(PerformedProcedure.datum)
    )
    rows = result.all()

    if len(rows) != len(performed_procedure_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jedan ili više postupaka nije pronađeno",
        )

    # Verify all belong to the same patient
    for row in rows:
        pp = row[0]
        if pp.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Svi postupci moraju pripadati istom pacijentu",
            )

    today = date.today()
    broj = await _next_broj(db, tenant_id, today.year)

    ukupno_cents = sum(row[0].cijena_cents for row in rows)

    predracun = Predracun(
        tenant_id=tenant_id,
        patient_id=patient_id,
        broj=broj,
        datum=today,
        ukupno_cents=ukupno_cents,
        napomena=napomena,
        created_by=created_by,
    )
    db.add(predracun)
    await db.flush()

    stavke = []
    for i, row in enumerate(rows):
        pp = row[0]
        stavka = PredracunStavka(
            tenant_id=tenant_id,
            predracun_id=predracun.id,
            performed_procedure_id=pp.id,
            sifra=row.sifra or "",
            naziv=row.naziv or "",
            datum=pp.datum,
            cijena_cents=pp.cijena_cents,
            sort_order=i,
        )
        db.add(stavka)
        stavke.append(stavka)

    await db.flush()

    return _to_dict(predracun, stavke)


async def get_predracun(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    predracun_id: uuid.UUID,
) -> dict:
    """Fetch a predračun with its line items."""
    predracun = await db.get(Predracun, predracun_id)
    if not predracun or predracun.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Predračun nije pronađen")

    result = await db.execute(
        select(PredracunStavka)
        .where(PredracunStavka.predracun_id == predracun_id)
        .order_by(PredracunStavka.sort_order)
    )
    stavke = result.scalars().all()

    return _to_dict(predracun, list(stavke))


async def list_predracuni(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    """List predračuni for a patient."""
    base = select(Predracun).where(
        Predracun.tenant_id == tenant_id,
        Predracun.patient_id == patient_id,
    )

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        base.order_by(Predracun.datum.desc()).offset(skip).limit(limit)
    )
    predracuni = result.scalars().all()

    if not predracuni:
        return [], total

    # Single query for all stavke instead of N+1
    predracun_ids = [p.id for p in predracuni]
    stavke_result = await db.execute(
        select(PredracunStavka)
        .where(PredracunStavka.predracun_id.in_(predracun_ids))
        .order_by(PredracunStavka.predracun_id, PredracunStavka.sort_order)
    )
    stavke_by_predracun: dict[uuid.UUID, list[PredracunStavka]] = {}
    for s in stavke_result.scalars().all():
        stavke_by_predracun.setdefault(s.predracun_id, []).append(s)

    items = [_to_dict(p, stavke_by_predracun.get(p.id, [])) for p in predracuni]

    return items, total


def _to_dict(predracun: Predracun, stavke: list) -> dict:
    return {
        "id": predracun.id,
        "tenant_id": predracun.tenant_id,
        "patient_id": predracun.patient_id,
        "broj": predracun.broj,
        "datum": predracun.datum,
        "ukupno_cents": predracun.ukupno_cents,
        "napomena": predracun.napomena,
        "created_by": predracun.created_by,
        "created_at": predracun.created_at,
        "updated_at": predracun.updated_at,
        "stavke": [
            {
                "id": s.id,
                "sifra": s.sifra,
                "naziv": s.naziv,
                "datum": s.datum,
                "cijena_cents": s.cijena_cents,
            }
            for s in stavke
        ],
    }

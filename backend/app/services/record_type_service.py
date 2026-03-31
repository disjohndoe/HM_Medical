import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record_type import RecordType
from app.schemas.record_type import RecordTypeCreate, RecordTypeUpdate

DEFAULT_COLORS = [
    "bg-slate-100 text-slate-800",
    "bg-orange-100 text-orange-800",
    "bg-lime-100 text-lime-800",
    "bg-sky-100 text-sky-800",
    "bg-violet-100 text-violet-800",
    "bg-fuchsia-100 text-fuchsia-800",
    "bg-pink-100 text-pink-800",
    "bg-teal-100 text-teal-800",
    "bg-zinc-100 text-zinc-800",
    "bg-stone-100 text-stone-800",
]

SYSTEM_TYPES_SEED = [
    # (slug, label, color, is_cezih_mandatory, is_cezih_eligible, sort_order)
    ("ambulantno_izvjesce", "Ambulantno izvješće", "bg-emerald-100 text-emerald-800", True, True, 0),
    ("specijalisticki_nalaz", "Specijalistički nalaz", "bg-indigo-100 text-indigo-800", True, True, 1),
    ("otpusno_pismo", "Otpusno pismo", "bg-rose-100 text-rose-800", True, True, 2),
    ("nalaz", "Nalaz", "bg-blue-100 text-blue-800", False, True, 3),
    ("epikriza", "Epikriza", "bg-amber-100 text-amber-800", False, True, 4),
    ("dijagnoza", "Dijagnoza", "bg-red-100 text-red-800", False, False, 5),
    ("misljenje", "Mišljenje", "bg-purple-100 text-purple-800", False, False, 6),
    ("preporuka", "Preporuka", "bg-green-100 text-green-800", False, False, 7),
    ("anamneza", "Anamneza", "bg-cyan-100 text-cyan-800", False, False, 8),
]


async def seed_system_record_types(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Seed default system record types for a new tenant. Idempotent."""
    existing = await db.execute(
        select(func.count()).select_from(
            select(RecordType).where(
                RecordType.tenant_id == tenant_id,
                RecordType.is_system.is_(True),
            ).subquery()
        )
    )
    if existing.scalar_one() > 0:
        return

    for slug, label, color, is_cezih_mandatory, is_cezih_eligible, sort_order in SYSTEM_TYPES_SEED:
        db.add(
            RecordType(
                tenant_id=tenant_id,
                slug=slug,
                label=label,
                color=color,
                is_system=True,
                is_cezih_mandatory=is_cezih_mandatory,
                is_cezih_eligible=is_cezih_eligible,
                is_active=True,
                sort_order=sort_order,
            )
        )
    await db.flush()


async def list_record_types(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    include_inactive: bool = False,
) -> list[RecordType]:
    query = select(RecordType).where(RecordType.tenant_id == tenant_id)
    if not include_inactive:
        query = query.where(RecordType.is_active.is_(True))
    query = query.order_by(RecordType.sort_order, RecordType.label)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_record_type(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: RecordTypeCreate,
) -> RecordType:
    existing = await db.execute(
        select(RecordType).where(
            RecordType.slug == data.slug,
            RecordType.tenant_id == tenant_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tip zapisa sa slug '{data.slug}' već postoji",
        )

    color = data.color
    if not color:
        count_result = await db.execute(
            select(func.count()).select_from(
                select(RecordType).where(
                    RecordType.tenant_id == tenant_id,
                    RecordType.is_system.is_(False),
                ).subquery()
            )
        )
        custom_count = count_result.scalar_one()
        color = DEFAULT_COLORS[custom_count % len(DEFAULT_COLORS)]

    record_type = RecordType(
        tenant_id=tenant_id,
        slug=data.slug,
        label=data.label,
        color=color,
        is_system=False,
        is_cezih_mandatory=False,
        is_cezih_eligible=False,
        is_active=True,
        sort_order=data.sort_order,
    )
    db.add(record_type)
    await db.flush()
    await db.refresh(record_type)
    return record_type


async def update_record_type(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    record_type_id: uuid.UUID,
    data: RecordTypeUpdate,
) -> RecordType:
    record_type = await db.get(RecordType, record_type_id)
    if not record_type or record_type.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tip zapisa nije pronađen")

    if record_type.is_cezih_mandatory:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CEZIH obavezni tipovi ne mogu se uređivati",
        )

    if record_type.is_system:
        update_data = data.model_dump(exclude_unset=True)
        allowed = {"is_active", "color", "sort_order"}
        for key in update_data:
            if key not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Sustavski tip zapisa: polje '{key}' se ne može promijeniti",
                )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record_type, field, value)
    await db.flush()
    await db.refresh(record_type)
    return record_type


async def delete_record_type(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    record_type_id: uuid.UUID,
) -> None:
    record_type = await db.get(RecordType, record_type_id)
    if not record_type or record_type.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tip zapisa nije pronađen")

    if record_type.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sustavski tip zapisa ne može se obrisati",
        )

    record_type.is_active = False
    await db.flush()

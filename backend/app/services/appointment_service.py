import uuid
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate


def _join_appointment_query(base):
    """Add patient and doctor name joins to a query."""
    return (
        base.outerjoin(Patient, Appointment.patient_id == Patient.id)
        .outerjoin(User, Appointment.doktor_id == User.id)
        .add_columns(
            Patient.ime.label("patient_ime"),
            Patient.prezime.label("patient_prezime"),
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
        )
    )


def _row_to_dict(row) -> dict:
    """Convert a joined row to a dict matching AppointmentRead."""
    apt = row[0]
    return {
        "id": apt.id,
        "tenant_id": apt.tenant_id,
        "patient_id": apt.patient_id,
        "doktor_id": apt.doktor_id,
        "datum_vrijeme": apt.datum_vrijeme,
        "trajanje_minuta": apt.trajanje_minuta,
        "status": apt.status,
        "vrsta": apt.vrsta,
        "napomena": apt.napomena,
        "patient_ime": row.patient_ime,
        "patient_prezime": row.patient_prezime,
        "doktor_ime": row.doktor_ime,
        "doktor_prezime": row.doktor_prezime,
        "created_at": apt.created_at,
        "updated_at": apt.updated_at,
    }


async def list_appointments(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    doktor_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    conditions = [Appointment.tenant_id == tenant_id]

    if date_from:
        conditions.append(Appointment.datum_vrijeme >= datetime.combine(date_from, time.min))
    if date_to:
        conditions.append(Appointment.datum_vrijeme < datetime.combine(date_to + timedelta(days=1), time.min))
    if doktor_id:
        conditions.append(Appointment.doktor_id == doktor_id)
    if status_filter:
        conditions.append(Appointment.status == status_filter)

    base = select(Appointment).where(and_(*conditions))
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = _join_appointment_query(base)
    result = await db.execute(
        query.order_by(Appointment.datum_vrijeme).offset(skip).limit(limit)
    )
    return [_row_to_dict(row) for row in result.all()], total


async def get_day_appointments(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    day: date,
    doktor_id: uuid.UUID | None = None,
) -> list[dict]:
    day_start = datetime.combine(day, time.min)
    day_end = datetime.combine(day, time(23, 59, 59, 999999))

    conditions = [
        Appointment.tenant_id == tenant_id,
        Appointment.datum_vrijeme >= day_start,
        Appointment.datum_vrijeme <= day_end,
    ]
    if doktor_id:
        conditions.append(Appointment.doktor_id == doktor_id)

    base = select(Appointment).where(and_(*conditions))
    query = _join_appointment_query(base)
    result = await db.execute(query.order_by(Appointment.datum_vrijeme))
    return [_row_to_dict(row) for row in result.all()]


async def get_appointment(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> dict:
    base = select(Appointment).where(
        Appointment.id == appointment_id,
        Appointment.tenant_id == tenant_id,
    )
    query = _join_appointment_query(base)
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Termin nije pronadjen")
    return _row_to_dict(row)


async def check_conflict(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    doktor_id: uuid.UUID,
    start_dt: datetime,
    duration_min: int,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    new_end = start_dt + timedelta(minutes=duration_min)

    q = select(Appointment).where(
        Appointment.tenant_id == tenant_id,
        Appointment.doktor_id == doktor_id,
        Appointment.status != "otkazan",
        Appointment.datum_vrijeme < new_end,
    ).with_for_update()
    if exclude_id:
        q = q.where(Appointment.id != exclude_id)

    result = await db.execute(q)
    for apt in result.scalars().all():
        existing_end = apt.datum_vrijeme + timedelta(minutes=apt.trajanje_minuta)
        if existing_end > start_dt:
            return True
    return False


async def create_appointment(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: AppointmentCreate,
) -> dict:
    conflict = await check_conflict(
        db, tenant_id, data.doktor_id, data.datum_vrijeme, data.trajanje_minuta
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doktor vec ima termin u tom vremenu",
        )

    appointment = Appointment(tenant_id=tenant_id, **data.model_dump())
    db.add(appointment)
    await db.flush()

    return await get_appointment(db, tenant_id, appointment.id)


async def update_appointment(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    data: AppointmentUpdate,
    user_id: uuid.UUID | None = None,
    http_client=None,
) -> dict:
    appointment = await db.get(Appointment, appointment_id)
    if not appointment or appointment.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Termin nije pronadjen")

    update_data = data.model_dump(exclude_unset=True)

    # If rescheduling, check conflict
    if "datum_vrijeme" in update_data or "doktor_id" in update_data or "trajanje_minuta" in update_data:
        new_start = update_data.get("datum_vrijeme", appointment.datum_vrijeme)
        new_doktor = update_data.get("doktor_id", appointment.doktor_id)
        new_duration = update_data.get("trajanje_minuta", appointment.trajanje_minuta)

        conflict = await check_conflict(
            db, tenant_id, new_doktor, new_start, new_duration, exclude_id=appointment_id
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Doktor vec ima termin u tom vremenu",
            )

    for field, value in update_data.items():
        setattr(appointment, field, value)

    await db.flush()
    return await get_appointment(db, tenant_id, appointment_id)


async def delete_appointment(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> None:
    appointment = await db.get(Appointment, appointment_id)
    if not appointment or appointment.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Termin nije pronadjen")

    if appointment.status != "zakazan":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Moguće obrisati samo zakazane termine",
        )

    await db.delete(appointment)
    await db.flush()


async def get_available_slots(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    doktor_id: uuid.UUID,
    day: date,
    duration_minutes: int = 30,
) -> list[dict]:
    work_start = time(8, 0)
    work_end = time(20, 0)
    slot_granularity = 15

    # Get all non-cancelled appointments for this doctor on this day
    day_start = datetime.combine(day, time.min)
    day_end = datetime.combine(day, time(23, 59, 59, 999999))

    result = await db.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.doktor_id == doktor_id,
            Appointment.status != "otkazan",
            Appointment.datum_vrijeme >= day_start,
            Appointment.datum_vrijeme <= day_end,
        ).order_by(Appointment.datum_vrijeme)
    )
    appointments = result.scalars().all()

    # Build busy intervals as (start_minutes, end_minutes) from midnight
    busy: list[tuple[int, int]] = []
    for apt in appointments:
        start_min = apt.datum_vrijeme.hour * 60 + apt.datum_vrijeme.minute
        end_min = start_min + apt.trajanje_minuta
        busy.append((start_min, end_min))

    work_start_min = work_start.hour * 60
    work_end_min = work_end.hour * 60

    slots = []
    current = work_start_min

    while current + duration_minutes <= work_end_min:
        slot_end = current + duration_minutes

        # Check if this slot overlaps any busy interval
        overlaps = False
        for busy_start, busy_end in busy:
            if current < busy_end and slot_end > busy_start:
                overlaps = True
                break

        if not overlaps:
            slots.append({
                "start": f"{current // 60:02d}:{current % 60:02d}",
                "end": f"{slot_end // 60:02d}:{slot_end % 60:02d}",
            })

        current += slot_granularity

    return slots

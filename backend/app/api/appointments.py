import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    AvailableSlot,
)
from app.services import appointment_service
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/available-slots", response_model=list[AvailableSlot])
async def get_available_slots(
    doktor_id: uuid.UUID = Query(...),
    date: date = Query(..., description="Date in YYYY-MM-DD format"),
    trajanje_minuta: int = Query(30, ge=15, le=240),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await appointment_service.get_available_slots(
        db, current_user.tenant_id, doktor_id, date, trajanje_minuta
    )


@router.get("/day/{day}", response_model=list[AppointmentRead])
async def get_day_appointments(
    day: date,
    doktor_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await appointment_service.get_day_appointments(
        db, current_user.tenant_id, day, doktor_id
    )


@router.get("", response_model=PaginatedResponse[AppointmentRead])
async def list_appointments(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    doktor_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await appointment_service.list_appointments(
        db, current_user.tenant_id, date_from, date_to, doktor_id, status_filter, skip, limit
    )
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse", "receptionist")),
    db: AsyncSession = Depends(get_db),
):
    return await appointment_service.create_appointment(db, current_user.tenant_id, data)


@router.get("/{appointment_id}", response_model=AppointmentRead)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await appointment_service.get_appointment(db, current_user.tenant_id, appointment_id)


@router.patch("/{appointment_id}", response_model=AppointmentRead)
async def update_appointment(
    appointment_id: uuid.UUID,
    data: AppointmentUpdate,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse", "receptionist")),
    db: AsyncSession = Depends(get_db),
):
    return await appointment_service.update_appointment(db, current_user.tenant_id, appointment_id, data)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    await appointment_service.delete_appointment(db, current_user.tenant_id, appointment_id)

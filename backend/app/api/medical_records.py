import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.medical_record import (
    MedicalRecordCreate,
    MedicalRecordRead,
    MedicalRecordUpdate,
)
from app.services import medical_record_service
from app.utils.pagination import PaginatedResponse

router = APIRouter(tags=["medical-records"])


@router.get("/medical-records", response_model=PaginatedResponse[MedicalRecordRead])
async def list_medical_records(
    patient_id: uuid.UUID | None = Query(None),
    tip: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await medical_record_service.list_records(
        db,
        current_user.tenant_id,
        patient_id=patient_id,
        tip=tip,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/medical-records", response_model=MedicalRecordRead, status_code=status.HTTP_201_CREATED)
async def create_medical_record(
    data: MedicalRecordCreate,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    return await medical_record_service.create_record(db, current_user.tenant_id, data, current_user.id)


@router.get("/medical-records/{record_id}", response_model=MedicalRecordRead)
async def get_medical_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await medical_record_service.get_record(db, current_user.tenant_id, record_id)


@router.patch("/medical-records/{record_id}", response_model=MedicalRecordRead)
async def update_medical_record(
    record_id: uuid.UUID,
    data: MedicalRecordUpdate,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    return await medical_record_service.update_record(db, current_user.tenant_id, record_id, data)

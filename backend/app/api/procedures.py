import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.procedure import (
    PerformedProcedureCreate,
    PerformedProcedureRead,
    ProcedureCreate,
    ProcedureRead,
    ProcedureUpdate,
)
from app.services import procedure_service
from app.utils.pagination import PaginatedResponse

router = APIRouter(tags=["procedures"])


@router.get("/procedures", response_model=PaginatedResponse[ProcedureRead])
async def list_procedures(
    kategorija: str | None = Query(None),
    search: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await procedure_service.list_procedures(
        db, current_user.tenant_id, kategorija=kategorija, search=search, skip=skip, limit=limit
    )
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/procedures", response_model=ProcedureRead, status_code=status.HTTP_201_CREATED)
async def create_procedure(
    data: ProcedureCreate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await procedure_service.create_procedure(db, current_user.tenant_id, data)


@router.patch("/procedures/{procedure_id}", response_model=ProcedureRead)
async def update_procedure(
    procedure_id: uuid.UUID,
    data: ProcedureUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await procedure_service.update_procedure(db, current_user.tenant_id, procedure_id, data)


@router.delete("/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_procedure(
    procedure_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    await procedure_service.delete_procedure(db, current_user.tenant_id, procedure_id)


@router.get("/performed-procedures", response_model=PaginatedResponse[PerformedProcedureRead])
async def list_performed_procedures(
    patient_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    appointment_id: uuid.UUID | None = Query(None),
    medical_record_id: uuid.UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await procedure_service.list_performed(
        db,
        current_user.tenant_id,
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        appointment_id=appointment_id,
        medical_record_id=medical_record_id,
        skip=skip,
        limit=limit,
    )
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/performed-procedures", response_model=PerformedProcedureRead, status_code=status.HTTP_201_CREATED)
async def create_performed_procedure(
    data: PerformedProcedureCreate,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    return await procedure_service.create_performed(db, current_user.tenant_id, data, current_user.id)

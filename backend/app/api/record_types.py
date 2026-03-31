import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.record_type import RecordTypeCreate, RecordTypeRead, RecordTypeUpdate
from app.services import record_type_service

router = APIRouter(tags=["record-types"])


@router.get("/record-types", response_model=list[RecordTypeRead])
async def list_record_types(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await record_type_service.list_record_types(
        db, current_user.tenant_id, include_inactive=include_inactive
    )


@router.post("/record-types", response_model=RecordTypeRead, status_code=status.HTTP_201_CREATED)
async def create_record_type(
    data: RecordTypeCreate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await record_type_service.create_record_type(db, current_user.tenant_id, data)


@router.patch("/record-types/{record_type_id}", response_model=RecordTypeRead)
async def update_record_type(
    record_type_id: uuid.UUID,
    data: RecordTypeUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await record_type_service.update_record_type(db, current_user.tenant_id, record_type_id, data)


@router.delete("/record-types/{record_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record_type(
    record_type_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    await record_type_service.delete_record_type(db, current_user.tenant_id, record_type_id)

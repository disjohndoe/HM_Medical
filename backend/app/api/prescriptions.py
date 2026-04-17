import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_enforcement import check_cezih_access, check_hzzo_access
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.prescription import (
    PrescriptionCreate,
    PrescriptionRead,
    PrescriptionSendResponse,
    PrescriptionUpdate,
)
from app.services import prescription_service
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


def _http_client(request: Request):
    return request.app.state.http_client


@router.get("", response_model=PaginatedResponse[PrescriptionRead])
async def list_prescriptions(
    request: Request,
    patient_id: uuid.UUID = Query(...),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await prescription_service.list_prescriptions(
        db, current_user.tenant_id, patient_id,
        status_filter=status_filter, skip=skip, limit=limit,
    )
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("", response_model=PrescriptionRead, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    data: PrescriptionCreate,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    return await prescription_service.create_prescription(
        db, current_user.tenant_id, data, current_user.id,
    )


@router.get("/{prescription_id}", response_model=PrescriptionRead)
async def get_prescription(
    prescription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await prescription_service.get_prescription(
        db, current_user.tenant_id, prescription_id,
    )


@router.patch("/{prescription_id}", response_model=PrescriptionRead)
async def update_prescription(
    prescription_id: uuid.UUID,
    data: PrescriptionUpdate,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    return await prescription_service.update_prescription(
        db, current_user.tenant_id, prescription_id, data, current_user.id,
    )


@router.delete("/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prescription(
    prescription_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await prescription_service.delete_prescription(
        db, current_user.tenant_id, prescription_id,
    )


@router.post("/{prescription_id}/send", response_model=PrescriptionSendResponse)
async def send_prescription(
    request: Request,
    prescription_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    await check_hzzo_access(db, current_user.tenant_id)
    return await prescription_service.send_to_cezih(
        db, current_user.tenant_id, prescription_id,
        user_id=current_user.id, http_client=_http_client(request),
    )


@router.post("/{prescription_id}/storno", response_model=PrescriptionSendResponse)
async def storno_prescription(
    request: Request,
    prescription_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    await check_hzzo_access(db, current_user.tenant_id)
    return await prescription_service.storno_prescription(
        db, current_user.tenant_id, prescription_id,
        user_id=current_user.id, http_client=_http_client(request),
    )

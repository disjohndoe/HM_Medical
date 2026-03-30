import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantRead, TenantUpdate
from app.services.agent_connection_manager import agent_manager
from app.services.card_verification import get_card_status

router = APIRouter(prefix="/settings", tags=["settings"])


class CezihStatusResponse(BaseModel):
    status: str
    sifra_ustanove: str | None
    oid: str | None
    agent_connected: bool
    last_heartbeat: datetime | None


@router.get("/clinic", response_model=TenantRead)
async def get_clinic_settings(
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    return tenant


@router.patch("/clinic", response_model=TenantRead)
async def update_clinic_settings(
    data: TenantUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)
    await db.flush()
    return tenant


@router.get("/cezih-status", response_model=CezihStatusResponse)
async def get_cezih_status(
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")
    conn = agent_manager.get(current_user.tenant_id)
    return CezihStatusResponse(
        status=tenant.cezih_status,
        sifra_ustanove=tenant.sifra_ustanove,
        oid=tenant.oid,
        agent_connected=agent_manager.is_connected(current_user.tenant_id),
        last_heartbeat=conn.last_heartbeat if conn else None,
    )


class AgentSecretResponse(BaseModel):
    agent_secret: str


@router.post("/generate-agent-secret", response_model=AgentSecretResponse)
async def generate_agent_secret(
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")
    secret = secrets.token_hex(32)
    tenant.agent_secret = secret
    await db.flush()
    return AgentSecretResponse(agent_secret=secret)


class CardStatusResponse(BaseModel):
    agent_connected: bool
    card_inserted: bool
    card_holder: str | None
    vpn_connected: bool
    matched_doctor_id: str | None = None
    matched_doctor_name: str | None = None


@router.get("/card-status", response_model=CardStatusResponse)
async def get_card_status_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current smart card and agent status, with matched doctor if card is inserted."""
    status_data = get_card_status(current_user.tenant_id)
    result = CardStatusResponse(**status_data)

    # Try to match inserted card to a doctor
    if status_data["card_inserted"] and status_data["card_holder"]:
        card_name = status_data["card_holder"].strip().upper()
        doctors = await db.execute(
            select(User).where(
                User.tenant_id == current_user.tenant_id,
                User.is_active.is_(True),
                User.card_holder_name.isnot(None),
            )
        )
        for doctor in doctors.scalars().all():
            if doctor.card_holder_name and doctor.card_holder_name.strip().upper() == card_name:
                result.matched_doctor_id = str(doctor.id)
                result.matched_doctor_name = f"{doctor.titula or ''} {doctor.ime} {doctor.prezime}".strip()
                break

    return result

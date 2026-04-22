from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_limits import get_plan_limits
from app.models.patient import Patient
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User


def check_trial_expiry(tenant: Tenant) -> None:
    """Raise 403 if tenant is on trial and the trial has expired."""
    if tenant.plan_tier == "trial" and tenant.trial_expires_at:
        if datetime.now(UTC) >= tenant.trial_expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Vaše pokusno razdoblje je isteklo. "
                    "Obratite nam se na 097/7120-800 ili "
                    "medical@hmdigital.hr radi produljenja Vašeg plana."
                ),
            )


async def _get_tenant(db: AsyncSession, tenant_id) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Klinika nije pronadjena")
    return tenant


async def check_user_limit(db: AsyncSession, tenant_id) -> None:
    tenant = await _get_tenant(db, tenant_id)
    limits = get_plan_limits(tenant.plan_tier)

    count_q = select(func.count()).select_from(
        select(User).where(User.tenant_id == tenant_id, User.is_active.is_(True)).subquery()
    )
    count = (await db.execute(count_q)).scalar_one()

    if count >= limits.max_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Dosegnut ograničenje od {limits.max_users} korisnika za "
                f"{tenant.plan_tier} plan. Nadogradite plan za više korisnika."
            ),
        )


async def check_patient_limit(db: AsyncSession, tenant_id) -> None:
    tenant = await _get_tenant(db, tenant_id)
    limits = get_plan_limits(tenant.plan_tier)

    if limits.max_patients is None:
        return

    count_q = select(func.count()).select_from(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.is_active.is_(True)).subquery()
    )
    count = (await db.execute(count_q)).scalar_one()

    if count >= limits.max_patients:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Dosegnut ograničenje od {limits.max_patients} pacijenata za "
                f"{tenant.plan_tier} plan. Nadogradite plan za više pacijenata."
            ),
        )


async def check_cezih_access(db: AsyncSession, tenant_id) -> None:
    tenant = await _get_tenant(db, tenant_id)
    limits = get_plan_limits(tenant.plan_tier)

    if not limits.cezih_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CEZIH pristup nije dostupan na vašem planu.",
        )


async def check_hzzo_access(db: AsyncSession, tenant_id) -> None:
    """Verify tenant has an HZZO contract. Required for e-Recept and e-Uputnica."""
    tenant = await _get_tenant(db, tenant_id)
    if not tenant.has_hzzo_contract:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ova akcija zahtijeva ugovor s HZZO-om.",
        )


async def get_current_usage(db: AsyncSession, tenant_id) -> dict:
    tenant = await _get_tenant(db, tenant_id)
    limits = get_plan_limits(tenant.plan_tier)

    users_q = select(func.count()).select_from(
        select(User).where(User.tenant_id == tenant_id, User.is_active.is_(True)).subquery()
    )
    patients_q = select(func.count()).select_from(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.is_active.is_(True)).subquery()
    )
    # Admin sessions don't count toward the limit
    sessions_q = select(func.count()).select_from(
        select(RefreshToken)
        .where(
            RefreshToken.user_id.in_(
                select(User.id).where(User.tenant_id == tenant_id, User.is_active.is_(True), User.role != "admin")
            ),
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .subquery()
    )

    users_count, patients_count, sessions_count = (
        (await db.execute(users_q)).scalar_one(),
        (await db.execute(patients_q)).scalar_one(),
        (await db.execute(sessions_q)).scalar_one(),
    )

    trial_days_remaining = None
    if tenant.plan_tier == "trial" and tenant.trial_expires_at:
        remaining_seconds = (tenant.trial_expires_at - datetime.now(UTC)).total_seconds()
        trial_days_remaining = max(0, remaining_seconds / 86400)

    return {
        "plan_tier": tenant.plan_tier,
        "users": {"current": users_count, "max": limits.max_users},
        "patients": {
            "current": patients_count,
            "max": limits.max_patients,  # None means unlimited
        },
        "sessions": {"current": sessions_count, "max": limits.max_concurrent_sessions},
        "cezih_access": limits.cezih_access,
        "trial_days_remaining": trial_days_remaining,
    }

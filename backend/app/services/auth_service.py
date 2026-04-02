from __future__ import annotations

import struct
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.plan_limits import get_plan_limits
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.tenant import TenantRead
from app.schemas.user import UserRead, UserReadWithTenant
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

if TYPE_CHECKING:
    from app.schemas.auth import RegisterRequest


async def register(db: AsyncSession, data: RegisterRequest) -> TokenResponse:
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email je vec registriran")

    # Create tenant
    tenant = Tenant(
        naziv=data.naziv_klinike,
        vrsta=data.vrsta,
        email=data.email,
        plan_tier="trial",
        trial_expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    db.add(tenant)
    await db.flush()

    # Create admin user
    user = User(
        tenant_id=tenant.id,
        email=data.email,
        hashed_password=hash_password(data.password),
        ime=data.ime,
        prezime=data.prezime,
        role="admin",
    )
    db.add(user)
    await db.flush()

    # Seed default procedures for new tenant
    from app.utils.seed_data import seed_default_procedures
    await seed_default_procedures(db, tenant.id)

    # Seed default record types for new tenant
    from app.services.record_type_service import seed_system_record_types
    await seed_system_record_types(db, tenant.id)

    # Create tokens
    token_response = await _create_token_pair(db, user)

    return token_response


def _tenant_lock_id(tenant_id) -> int:
    """Convert UUID to int64 for pg_advisory_xact_lock."""
    return struct.unpack("q", tenant_id.bytes[:8])[0]


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neispravni podaci za prijavu")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Korisnik je deaktiviran")

    # Check tenant active
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Klinika je deaktivirana")

    # Check trial expiry
    if tenant.plan_tier == "trial" and tenant.trial_expires_at:
        if datetime.now(UTC) >= tenant.trial_expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vaše pokusno razdoblje je isteklo. Obratite nam se na 097/7120-800 ili medical@hmdigital.hr radi produljenja Vašeg plana.",
            )

    # Update last login
    user.last_login_at = datetime.now(UTC)
    await db.flush()

    # RACE 1 fix: acquire advisory lock per tenant to prevent TOCTOU on session count
    lock_id = _tenant_lock_id(tenant.id)
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

    # Session limit enforcement
    limits = get_plan_limits(tenant.plan_tier)
    now = datetime.now(UTC)

    # Auto-cleanup expired/revoked tokens for this tenant
    tenant_user_ids = select(User.id).where(User.tenant_id == tenant.id)
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id.in_(tenant_user_ids),
            or_(RefreshToken.is_revoked.is_(True), RefreshToken.expires_at <= now),
        )
    )

    # Admin sessions don't count toward the limit — only non-admin users
    non_admin_user_ids = select(User.id).where(
        User.tenant_id == tenant.id, User.is_active.is_(True), User.role != "admin"
    )

    active_sessions_q = select(func.count()).select_from(
        select(RefreshToken).where(
            RefreshToken.user_id.in_(non_admin_user_ids),
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > now,
        ).subquery()
    )
    active_sessions = (await db.execute(active_sessions_q)).scalar_one()

    if user.role != "admin" and active_sessions >= limits.max_concurrent_sessions:
        if limits.max_concurrent_sessions == 1:
            # Solo/trial: kick ALL tenant sessions (BUG 3 fix: tenant-wide, not just this user)
            revoke_result = await db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id.in_(non_admin_user_ids),
                    RefreshToken.is_revoked.is_(False),
                )
            )
            for token in revoke_result.scalars().all():
                token.is_revoked = True
        else:
            # Multi-session plan: reject if tenant-wide limit reached
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Dosegnuto ograničenje od {limits.max_concurrent_sessions} "
                    "istovremenih sesija. Odjavite se s drugog uređaja."
                ),
            )

    return await _create_token_pair(db, user)


async def refresh(db: AsyncSession, raw_token: str) -> TokenResponse:
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.is_revoked.is_(False))
    )
    token = result.scalar_one_or_none()

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neispravan refresh token")

    if token.expires_at < datetime.now(UTC):
        # Revoke expired token
        token.is_revoked = True
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token je istekao")

    # Rotate: revoke old, issue new
    token.is_revoked = True
    await db.flush()

    user = await db.get(User, token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Korisnik nije pronadjen")

    # GAP 2 fix: re-check session limits on refresh (catches plan downgrades)
    # Admin is exempt from session limits
    tenant = await db.get(Tenant, user.tenant_id)

    # Check trial expiry on refresh
    if tenant and tenant.plan_tier == "trial" and tenant.trial_expires_at:
        if datetime.now(UTC) >= tenant.trial_expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vaše pokusno razdoblje je isteklo. Obratite nam se na 097/7120-800 ili medical@hmdigital.hr radi produljenja Vašeg plana.",
            )

    if tenant and user.role != "admin":
        limits = get_plan_limits(tenant.plan_tier)
        now = datetime.now(UTC)
        active_sessions_q = select(func.count()).select_from(
            select(RefreshToken).where(
                RefreshToken.user_id.in_(
                    select(User.id).where(
                        User.tenant_id == tenant.id, User.is_active.is_(True), User.role != "admin"
                    )
                ),
                RefreshToken.is_revoked.is_(False),
                RefreshToken.expires_at > now,
            ).subquery()
        )
        active_sessions = (await db.execute(active_sessions_q)).scalar_one()
        if active_sessions >= limits.max_concurrent_sessions:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Dosegnuto ograničenje od {limits.max_concurrent_sessions} "
                    "istovremenih sesija. Odjavite se s drugog uređaja."
                ),
            )

    return await _create_token_pair(db, user)


async def logout(db: AsyncSession, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token = result.scalar_one_or_none()
    if token:
        token.is_revoked = True


async def get_active_sessions(db: AsyncSession, tenant_id) -> list[dict]:
    """List all active sessions for a tenant."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(RefreshToken, User.ime, User.prezime, User.email).join(
            User, RefreshToken.user_id == User.id
        ).where(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > now,
        ).order_by(RefreshToken.created_at.desc())
    )
    sessions = []
    for token, ime, prezime, email in result.all():
        sessions.append({
            "id": str(token.id),
            "user_id": str(token.user_id),
            "user_ime": ime,
            "user_prezime": prezime,
            "user_email": email,
            "created_at": token.created_at.isoformat(),
            "expires_at": token.expires_at.isoformat(),
        })
    return sessions


async def revoke_session(db: AsyncSession, tenant_id, session_id: str) -> bool:
    """Revoke a specific session by its refresh token ID. Only within the same tenant."""
    result = await db.execute(
        select(RefreshToken).join(User, RefreshToken.user_id == User.id).where(
            RefreshToken.id == session_id,
            User.tenant_id == tenant_id,
            RefreshToken.is_revoked.is_(False),
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        return False
    token.is_revoked = True
    return True


async def revoke_other_sessions(db: AsyncSession, tenant_id, current_refresh_hash: str) -> int:
    """Revoke all tenant sessions except the caller's current one."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(RefreshToken).join(User, RefreshToken.user_id == User.id).where(
            User.tenant_id == tenant_id,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > now,
            RefreshToken.token_hash != current_refresh_hash,
        )
    )
    count = 0
    for token in result.scalars().all():
        token.is_revoked = True
        count += 1
    return count


async def revoke_user_sessions(db: AsyncSession, tenant_id, user_id) -> int:
    """Revoke all active sessions for a specific user within a tenant."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(RefreshToken).join(User, RefreshToken.user_id == User.id).where(
            User.tenant_id == tenant_id,
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > now,
        )
    )
    count = 0
    for token in result.scalars().all():
        token.is_revoked = True
        count += 1
    return count


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """Delete revoked and expired refresh tokens. Returns count of removed rows."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(func.count()).select_from(
            select(RefreshToken).where(
                (RefreshToken.is_revoked) | (RefreshToken.expires_at < now)
            ).subquery()
        )
    )
    count = result.scalar_one()

    if count > 0:
        await db.execute(
            delete(RefreshToken).where(
                (RefreshToken.is_revoked) | (RefreshToken.expires_at < now)
            )
        )

    return count


async def _create_token_pair(db: AsyncSession, user: User) -> TokenResponse:
    access_token = create_access_token(
        {"user_id": str(user.id), "tenant_id": str(user.tenant_id), "role": user.role}
    )

    raw_refresh = create_refresh_token()
    refresh_token_obj = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_token_obj)
    await db.flush()

    # Build response with tenant
    tenant = await db.get(Tenant, user.tenant_id)
    tenant_read = TenantRead.model_validate(tenant)
    user_data = UserRead.model_validate(user).model_dump()
    user_data["tenant"] = tenant_read
    user_read = UserReadWithTenant.model_validate(user_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_read,
    )

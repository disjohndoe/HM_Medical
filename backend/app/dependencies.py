from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    access_token_cookie: str | None = Cookie(default=None, alias="access_token"),
    bearer_token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Dual-source: try cookie first, then Authorization header (backward compat)
    token = access_token_cookie or bearer_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nije autentificiran")

    payload = decode_access_token(token)

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neispravan token")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Korisnik nije pronadjen")

    # Verify tenant match using proper UUID comparison
    token_tenant_id = payload.get("tenant_id")
    try:
        token_tenant_uuid = UUID(token_tenant_id) if token_tenant_id else None
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neispravan token")
    if user.tenant_id != token_tenant_uuid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neispravan token")

    # GAP 1 fix: reject if user has no active refresh tokens (kicked/revoked session)
    now = datetime.now(UTC)
    has_active = await db.execute(
        select(RefreshToken.id).where(
            RefreshToken.user_id == user.id,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > now,
        ).limit(1)
    )
    if not has_active.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesija je istekla")

    return user


def require_roles(*roles: str) -> Callable:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nemate dozvolu za ovu akciju",
            )
        return current_user

    return role_checker

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.terms import CURRENT_TERMS_VERSION, requires_terms_acceptance
from app.database import get_db
from app.dependencies import get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.tenant import TenantRead
from app.schemas.user import UserRead, UserReadWithTenant
from app.services import auth_service
from app.utils.security import hash_password, hash_refresh_token, verify_password

limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)
router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly cookies for JWT tokens."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/auth",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear httpOnly auth cookies."""
    response.delete_cookie("access_token", path="/api")
    response.delete_cookie("refresh_token", path="/api/auth")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
async def register(request: Request, response: Response, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await auth_service.register(db, data)
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return result


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/5minutes")
async def login(request: Request, response: Response, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await auth_service.login(db, data.email, data.password)
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return result


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, response: Response, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    # Dual-source: try cookie first, then request body (backward compat)
    refresh_token = request.cookies.get("refresh_token") or data.refresh_token
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nedostaje refresh token")
    result = await auth_service.refresh(db, refresh_token)
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    # Dual-source: try cookie first, then request body
    refresh_token = request.cookies.get("refresh_token") or data.refresh_token
    if refresh_token:
        await auth_service.logout(db, refresh_token)
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserReadWithTenant)
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, current_user.tenant_id)
    user_data = UserRead.model_validate(current_user).model_dump()
    user_data["tenant"] = TenantRead.model_validate(tenant)
    return user_data


@router.get("/terms-status")
async def get_terms_status(current_user: User = Depends(get_current_user)):
    """Returns whether the current user needs to (re-)accept the Terms of Service.

    Frontend polls this after login and renders a blocking modal when
    `requires_terms_acceptance` is true. Also returned inline on login,
    but exposed here so the auth context can recover it without re-login.
    """
    return {
        "requires_terms_acceptance": requires_terms_acceptance(current_user),
        "current_version": CURRENT_TERMS_VERSION,
        "accepted_version": current_user.terms_version,
        "accepted_at": current_user.terms_accepted_at.isoformat() if current_user.terms_accepted_at else None,
    }


@router.post("/accept-terms", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour")
async def accept_terms(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record the current user's acceptance of the latest Terms + Privacy Policy.

    Called by the blocking consent modal on next login for users whose
    stored terms_version is older than CURRENT_TERMS_VERSION.
    """
    current_user.terms_accepted_at = datetime.now(UTC)
    current_user.terms_version = CURRENT_TERMS_VERSION
    await db.flush()


@router.post("/change-password")
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neispravna stara lozinka")

    if data.old_password == data.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nova lozinka mora biti drugačija od stare")

    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()
    return {"message": "Lozinka uspješno promijenjena"}


@router.get("/sessions")
@limiter.limit("30/minute")
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the current user's tenant."""
    return await auth_service.get_active_sessions(db, current_user.tenant_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def revoke_session(
    request: Request,
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Samo admin može ukinuti sesije")
    revoked = await auth_service.revoke_session(db, current_user.tenant_id, session_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesija nije pronađena")


@router.post("/sessions/revoke-others", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def revoke_other_sessions(
    request: Request,
    data: RefreshRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all sessions except the caller's current one."""
    refresh_token = data.refresh_token
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token je obavezan")
    current_hash = hash_refresh_token(refresh_token)
    count = await auth_service.revoke_other_sessions(db, current_user.tenant_id, current_hash)
    return {"revoked_count": count}


@router.post("/sessions/cleanup", status_code=status.HTTP_200_OK)
@limiter.limit("6/hour")
async def cleanup_tokens(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clean up expired/revoked tokens (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Samo admin može pokrenuti čišćenje")
    count = await auth_service.cleanup_expired_tokens(db)
    return {"cleaned_count": count}

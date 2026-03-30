from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.tenant import TenantRead
from app.schemas.user import UserRead, UserReadWithTenant
from app.services import auth_service
from app.utils.security import hash_password, hash_refresh_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.register(db, data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.login(db, data.email, data.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.refresh(db, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.logout(db, data.refresh_token)


@router.get("/me", response_model=UserReadWithTenant)
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, current_user.tenant_id)
    user_data = UserRead.model_validate(current_user).model_dump()
    user_data["tenant"] = TenantRead.model_validate(tenant)
    return user_data


@router.post("/change-password")
async def change_password(
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
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the current user's tenant."""
    return await auth_service.get_active_sessions(db, current_user.tenant_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
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
async def revoke_other_sessions(
    data: RefreshRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all sessions except the caller's current one."""
    current_hash = hash_refresh_token(data.refresh_token)
    count = await auth_service.revoke_other_sessions(db, current_user.tenant_id, current_hash)
    return {"revoked_count": count}


@router.post("/sessions/cleanup", status_code=status.HTTP_200_OK)
async def cleanup_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clean up expired/revoked tokens (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Samo admin može pokrenuti čišćenje")
    count = await auth_service.cleanup_expired_tokens(db)
    return {"cleaned_count": count}

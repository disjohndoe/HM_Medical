import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_enforcement import check_user_limit
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.user import CardBindingRequest, UserCreate, UserRead, UserUpdate
from app.services.agent_connection_manager import agent_manager
from app.utils.pagination import PaginatedResponse
from app.utils.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/doctors", response_model=PaginatedResponse[UserRead])
async def list_doctors(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List doctors for the current tenant. Includes admins (clinic owners who also practice)."""
    base = select(User).where(
        User.tenant_id == current_user.tenant_id,
        User.role.in_(["doctor", "admin"]),
        User.is_active.is_(True),
    )
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(base.offset(skip).limit(limit).order_by(User.prezime, User.ime))
    users = result.scalars().all()

    return PaginatedResponse(items=list(users), total=total, skip=skip, limit=limit)


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = Query(None),
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    base = select(User).where(User.tenant_id == current_user.tenant_id)
    if role:
        base = base.where(User.role == role)
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(base.offset(skip).limit(limit).order_by(User.created_at))
    users = result.scalars().all()

    return PaginatedResponse(items=list(users), total=total, skip=skip, limit=limit)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    await check_user_limit(db, current_user.tenant_id)

    existing = await db.execute(
        select(User).where(User.email == data.email, User.tenant_id == current_user.tenant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email vec postoji u ovoj klinici")

    user = User(
        tenant_id=current_user.tenant_id,
        email=data.email,
        hashed_password=hash_password(data.password),
        ime=data.ime,
        prezime=data.prezime,
        titula=data.titula,
        telefon=data.telefon,
        role=data.role,
    )
    db.add(user)
    await db.flush()
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Korisnik nije pronadjen")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Korisnik nije pronadjen")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Korisnik nije pronadjen")

    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ne mozete deaktivirati vlastiti racun")

    user.is_active = False
    await db.flush()


@router.post("/{user_id}/card-binding", response_model=UserRead)
async def bind_card(
    user_id: uuid.UUID,
    data: CardBindingRequest,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Manually bind a smart card identity to a doctor."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Korisnik nije pronadjen")

    user.card_holder_name = data.card_holder_name
    user.card_certificate_oib = data.card_certificate_oib
    await db.flush()
    return user


@router.delete("/{user_id}/card-binding", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_card(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Remove smart card binding from a doctor."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Korisnik nije pronadjen")

    user.card_holder_name = None
    user.card_certificate_oib = None
    await db.flush()


@router.post("/{user_id}/card-binding/auto", response_model=UserRead)
async def auto_bind_card(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Bind the currently inserted smart card to a doctor."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Korisnik nije pronadjen")

    conn = agent_manager.get(current_user.tenant_id)
    if not conn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent nije spojen")

    if not conn.card_inserted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kartica nije umetnuta u čitač")

    if not conn.card_holder:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kartica nema podatke o nositelju")

    user.card_holder_name = conn.card_holder
    await db.flush()
    return user

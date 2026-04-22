import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
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


_CARD_CONFLICT_DETAIL = (
    "Ova kartica je već povezana s drugim korisnikom. Prethodni korisnik mora odspojiti karticu prije povezivanja."
)


_USERS_CONSTRAINT_MESSAGES = {
    "ux_users_tenant_mbo_lijecnika": "MBO liječnika je već dodijeljen drugom korisniku u ovoj klinici.",
    "ux_users_tenant_practitioner_id": "HZJZ broj je već dodijeljen drugom korisniku u ovoj klinici.",
    "users_email_key": "Korisnik s tom email adresom već postoji.",
    "ck_user_role_can_hold_doctor_ids": (
        "HZJZ broj i MBO mogu se dodijeliti samo doktorima, adminima i medicinskim sestrama."
    ),
}


def _extract_constraint_name(err: IntegrityError) -> str | None:
    orig = err.orig
    name = getattr(orig, "constraint_name", None)
    if name:
        return name
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag else None
    if name:
        return name
    message = str(orig or err)
    for constraint in _USERS_CONSTRAINT_MESSAGES:
        if constraint in message:
            return constraint
    return None


def _translate_integrity_error(err: IntegrityError) -> HTTPException:
    constraint = _extract_constraint_name(err)
    detail = _USERS_CONSTRAINT_MESSAGES.get(constraint or "")
    if detail:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Zapis krši ograničenje baze. Provjerite unos i pokušajte ponovno.",
    )


async def _assert_card_unique(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    card_holder_name: str | None,
    card_certificate_serial: str | None,
) -> None:
    """Ensure no other active user holds this card (by serial OR normalized name) within the same tenant."""
    conditions = []
    if card_certificate_serial:
        conditions.append(User.card_certificate_serial == card_certificate_serial)
    if card_holder_name:
        conditions.append(func.upper(func.trim(User.card_holder_name)) == card_holder_name.strip().upper())
    if not conditions:
        return
    result = await db.execute(
        select(User.id)
        .where(
            or_(*conditions),
            User.id != user_id,
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
        )
        .limit(1)
    )
    if result.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CARD_CONFLICT_DETAIL,
        )


async def _flush_or_conflict(db: AsyncSession) -> None:
    """Commit card-binding changes, mapping unique-index violations to 409."""
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CARD_CONFLICT_DETAIL,
        )


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

    existing = await db.execute(select(User).where(User.email == data.email, User.tenant_id == current_user.tenant_id))
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
        practitioner_id=data.practitioner_id,
        mbo_lijecnika=data.mbo_lijecnika,
        cezih_signing_method=data.cezih_signing_method,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise _translate_integrity_error(e) from e
    return user


@router.post("/me/card-binding", response_model=UserRead)
async def self_bind_card(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bind the currently inserted smart card to the calling user's account."""
    agents = agent_manager.get_all(current_user.tenant_id)
    if not agents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent nije spojen")

    conn = next((a for a in agents if a.card_inserted and a.card_holder), None)
    if not conn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kartica nije umetnuta ni u jednom agentu")

    await _assert_card_unique(
        db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        card_holder_name=conn.card_holder,
        card_certificate_serial=conn.card_serial,
    )

    current_user.card_holder_name = conn.card_holder
    current_user.card_certificate_serial = conn.card_serial
    current_user.card_certificate_oib = conn.card_subject_oib
    await _flush_or_conflict(db)
    await db.refresh(current_user)
    return current_user


@router.delete("/me/card-binding", status_code=status.HTTP_204_NO_CONTENT)
async def self_unbind_card(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove card binding from the calling user's account."""
    current_user.card_holder_name = None
    current_user.card_certificate_oib = None
    current_user.card_certificate_serial = None
    await db.flush()


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

    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise _translate_integrity_error(e) from e
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
    user.card_holder_name = None
    user.card_certificate_oib = None
    user.card_certificate_serial = None
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

    await _assert_card_unique(
        db,
        user_id=user.id,
        tenant_id=current_user.tenant_id,
        card_holder_name=data.card_holder_name,
        card_certificate_serial=None,
    )

    user.card_holder_name = data.card_holder_name
    user.card_certificate_oib = data.card_certificate_oib
    await _flush_or_conflict(db)
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
    user.card_certificate_serial = None
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

    # Find any agent that has a card inserted
    agents = agent_manager.get_all(current_user.tenant_id)
    if not agents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent nije spojen")

    conn = next((a for a in agents if a.card_inserted and a.card_holder), None)
    if not conn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kartica nije umetnuta ni u jednom agentu")

    await _assert_card_unique(
        db,
        user_id=user.id,
        tenant_id=current_user.tenant_id,
        card_holder_name=conn.card_holder,
        card_certificate_serial=conn.card_serial,
    )

    user.card_holder_name = conn.card_holder
    user.card_certificate_serial = conn.card_serial
    user.card_certificate_oib = conn.card_subject_oib
    await _flush_or_conflict(db)
    return user

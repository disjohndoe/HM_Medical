import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate
from app.utils.croatian import validate_mbo, validate_oib


async def list_patients(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Patient], int]:
    base = select(Patient).where(
        Patient.tenant_id == tenant_id,
        Patient.is_active.is_(True),
    )

    if search:
        # Escape SQL wildcards to prevent wildcard injection
        escaped = search.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        base = base.where(
            or_(
                Patient.ime.ilike(pattern),
                Patient.prezime.ilike(pattern),
                Patient.oib.ilike(pattern),
                Patient.mbo.ilike(pattern),
                Patient.broj_putovnice.ilike(pattern),
                Patient.ehic_broj.ilike(pattern),
                Patient.cezih_patient_id.ilike(pattern),
                Patient.telefon.ilike(pattern),
                Patient.mobitel.ilike(pattern),
            )
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(base.order_by(Patient.prezime, Patient.ime).offset(skip).limit(limit))
    patients = list(result.scalars().all())

    return patients, total


async def get_patient(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> Patient:
    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id or not patient.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronadjen")
    return patient


async def create_patient(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: PatientCreate,
) -> Patient:
    if data.oib:
        existing = await db.execute(
            select(Patient).where(
                Patient.oib == data.oib,
                Patient.tenant_id == tenant_id,
                Patient.is_active.is_(True),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent s tim OIB-om vec postoji",
            )

    if data.mbo:
        existing = await db.execute(
            select(Patient).where(
                Patient.mbo == data.mbo,
                Patient.tenant_id == tenant_id,
                Patient.is_active.is_(True),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent s tim MBO-om vec postoji",
            )

    patient = Patient(tenant_id=tenant_id, **data.model_dump())
    db.add(patient)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig)
        if "uq_patient_tenant_oib" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent s tim OIB-om vec postoji",
            )
        elif "uq_patient_tenant_mbo" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent s tim MBO-om vec postoji",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pacijent s tim podacima vec postoji",
        ) from None
    await db.refresh(patient)
    return patient


async def update_patient(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    data: PatientUpdate,
) -> Patient:
    patient = await get_patient(db, tenant_id, patient_id)

    update_data = data.model_dump(exclude_unset=True)

    # Validate OIB/MBO only when actually changing the value
    new_oib = update_data.get("oib")
    if new_oib and new_oib != patient.oib and not validate_oib(new_oib):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Neispravan OIB",
        )
    new_mbo = update_data.get("mbo")
    if new_mbo and new_mbo != patient.mbo and not validate_mbo(new_mbo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Neispravan MBO",
        )

    if "oib" in update_data and update_data["oib"]:
        existing = await db.execute(
            select(Patient).where(
                Patient.oib == update_data["oib"],
                Patient.tenant_id == tenant_id,
                Patient.id != patient_id,
                Patient.is_active.is_(True),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent s tim OIB-om vec postoji",
            )

    if "mbo" in update_data and update_data["mbo"]:
        existing = await db.execute(
            select(Patient).where(
                Patient.mbo == update_data["mbo"],
                Patient.tenant_id == tenant_id,
                Patient.id != patient_id,
                Patient.is_active.is_(True),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pacijent s tim MBO-om vec postoji",
            )

    for field, value in update_data.items():
        setattr(patient, field, value)

    await db.flush()
    await db.refresh(patient)
    return patient


async def delete_patient(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> None:
    patient = await get_patient(db, tenant_id, patient_id)
    patient.is_active = False

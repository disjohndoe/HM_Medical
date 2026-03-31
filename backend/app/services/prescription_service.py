import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prescription import Prescription
from app.models.user import User
from app.schemas.prescription import PrescriptionCreate
from app.services.cezih import dispatcher as cezih


def _join_query(base):
    return (
        base.outerjoin(User, Prescription.doktor_id == User.id)
        .add_columns(
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
        )
    )


def _row_to_dict(row) -> dict:
    rec = row[0]
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "patient_id": rec.patient_id,
        "doktor_id": rec.doktor_id,
        "medical_record_id": rec.medical_record_id,
        "lijekovi": rec.lijekovi,
        "cezih_sent": rec.cezih_sent,
        "cezih_sent_at": rec.cezih_sent_at,
        "cezih_recept_id": rec.cezih_recept_id,
        "cezih_storno": rec.cezih_storno,
        "cezih_storno_at": rec.cezih_storno_at,
        "napomena": rec.napomena,
        "doktor_ime": row.doktor_ime,
        "doktor_prezime": row.doktor_prezime,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }


async def list_prescriptions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[dict], int]:
    conditions = [
        Prescription.tenant_id == tenant_id,
        Prescription.patient_id == patient_id,
    ]

    if status_filter == "nacrt":
        conditions.append(Prescription.cezih_sent == False)  # noqa: E712
    elif status_filter == "aktivan":
        conditions.append(Prescription.cezih_sent == True)  # noqa: E712
        conditions.append(Prescription.cezih_storno == False)  # noqa: E712
    elif status_filter == "storniran":
        conditions.append(Prescription.cezih_storno == True)  # noqa: E712

    base = select(Prescription).where(and_(*conditions))
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = _join_query(base)
    result = await db.execute(
        query.order_by(Prescription.created_at.desc()).offset(skip).limit(limit)
    )
    return [_row_to_dict(row) for row in result.all()], total


async def get_prescription(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
) -> dict:
    base = select(Prescription).where(
        Prescription.id == prescription_id,
        Prescription.tenant_id == tenant_id,
    )
    query = _join_query(base)
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recept nije pronađen")
    return _row_to_dict(row)


async def create_prescription(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    data: PrescriptionCreate,
    doktor_id: uuid.UUID,
) -> dict:
    prescription = Prescription(
        tenant_id=tenant_id,
        patient_id=data.patient_id,
        doktor_id=doktor_id,
        medical_record_id=data.medical_record_id,
        lijekovi=[lijek.model_dump() for lijek in data.lijekovi],
        napomena=data.napomena,
    )
    db.add(prescription)
    await db.flush()

    base = select(Prescription).where(Prescription.id == prescription.id)
    query = _join_query(base)
    result = await db.execute(query)
    row = result.one()
    await db.commit()
    return _row_to_dict(row)


async def delete_prescription(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.tenant_id == tenant_id,
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recept nije pronađen")
    if prescription.cezih_sent:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Poslan recept se ne može obrisati — koristite storno",
        )
    await db.delete(prescription)
    await db.commit()


async def send_to_cezih(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    user_id: uuid.UUID,
    http_client=None,
) -> dict:
    result = await db.execute(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.tenant_id == tenant_id,
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recept nije pronađen")
    if prescription.cezih_sent:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recept je već poslan na CEZIH")

    cezih_result = await cezih.send_erecept(
        prescription.patient_id,
        prescription.lijekovi,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        http_client=http_client,
    )

    prescription.cezih_sent = True
    prescription.cezih_sent_at = datetime.now(UTC)
    prescription.cezih_recept_id = cezih_result.get("recept_id", "")
    await db.commit()

    return {
        "prescription_id": prescription.id,
        "cezih_recept_id": prescription.cezih_recept_id,
        "success": cezih_result.get("success", True),
        "mock": cezih_result.get("mock", True),
    }


async def storno_prescription(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    user_id: uuid.UUID,
    http_client=None,
) -> dict:
    result = await db.execute(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.tenant_id == tenant_id,
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recept nije pronađen")
    if not prescription.cezih_sent:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recept nije poslan — ne može se stornirati")
    if prescription.cezih_storno:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recept je već storniran")

    cezih_result = await cezih.cancel_erecept(
        prescription.cezih_recept_id,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        http_client=http_client,
    )

    prescription.cezih_storno = True
    prescription.cezih_storno_at = datetime.now(UTC)
    await db.commit()

    return {
        "prescription_id": prescription.id,
        "cezih_recept_id": prescription.cezih_recept_id,
        "success": cezih_result.get("success", True),
        "mock": cezih_result.get("mock", True),
    }

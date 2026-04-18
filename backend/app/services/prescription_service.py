import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical_record import MedicalRecord
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.user import User
from app.schemas.prescription import PrescriptionCreate, PrescriptionUpdate
from app.services import audit_service
from app.services.cezih import dispatcher as cezih


def _join_query(base):
    return (
        base.outerjoin(User, Prescription.doktor_id == User.id)
        .outerjoin(MedicalRecord, Prescription.medical_record_id == MedicalRecord.id)
        .add_columns(
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
            MedicalRecord.datum.label("medical_record_datum"),
            MedicalRecord.tip.label("medical_record_tip"),
            MedicalRecord.dijagnoza_tekst.label("medical_record_dijagnoza_tekst"),
            MedicalRecord.dijagnoza_mkb.label("medical_record_dijagnoza_mkb"),
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
        "medical_record_datum": row.medical_record_datum,
        "medical_record_tip": row.medical_record_tip,
        "medical_record_dijagnoza_tekst": row.medical_record_dijagnoza_tekst,
        "medical_record_dijagnoza_mkb": row.medical_record_dijagnoza_mkb,
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
    patient = await db.get(Patient, data.patient_id)
    if not patient or patient.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

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
    return _row_to_dict(row)


async def update_prescription(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    data: PrescriptionUpdate,
    user_id: uuid.UUID,
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Poslan recept se ne može uređivati — koristite storno",
        )

    update_payload = data.model_dump(exclude_unset=True)
    lijekovi_changed = False

    if "lijekovi" in update_payload and update_payload["lijekovi"] is not None:
        if len(update_payload["lijekovi"]) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Recept mora sadržavati barem jedan lijek",
            )
        prescription.lijekovi = update_payload["lijekovi"]
        lijekovi_changed = True

    if "napomena" in update_payload:
        prescription.napomena = update_payload["napomena"]

    await db.flush()

    # Reverse sync: if lijekovi changed AND recept is linked to an unsent nalaz,
    # rewrite the nalaz's preporucena_terapija from the new recept lijekovi.
    if lijekovi_changed and prescription.medical_record_id:
        nalaz = await db.get(MedicalRecord, prescription.medical_record_id)
        if nalaz and nalaz.tenant_id == tenant_id and not nalaz.cezih_sent:
            nalaz.preporucena_terapija = [
                {
                    "atk": lijek.get("atk", ""),
                    "naziv": lijek.get("naziv", ""),
                    "jacina": lijek.get("jacina", ""),
                    "oblik": lijek.get("oblik", ""),
                    "doziranje": lijek.get("doziranje", ""),
                    "napomena": lijek.get("napomena", ""),
                }
                for lijek in prescription.lijekovi
            ]
            await db.flush()
            await audit_service.write_audit(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="medical_record_therapy_sync_from_prescription",
                resource_type="medical_record",
                resource_id=nalaz.id,
                details={"prescription_id": str(prescription.id)},
            )

    await audit_service.write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="prescription_update",
        resource_type="prescription",
        resource_id=prescription.id,
        details={"lijekovi_changed": lijekovi_changed},
    )

    base = select(Prescription).where(Prescription.id == prescription.id)
    query = _join_query(base)
    result = await db.execute(query)
    row = result.one()
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
    await db.flush()


async def upsert_draft_from_record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    medical_record_id: uuid.UUID,
    doktor_id: uuid.UUID,
    therapy_items: list[dict],
    user_id: uuid.UUID,
) -> Prescription | None:
    """Create or sync a draft Prescription from a nalaz's preporucena_terapija.

    If a draft (cezih_sent=False, cezih_storno=False) linked to this nalaz exists,
    overwrite its lijekovi. Otherwise insert a new draft. If only sent/stornirani
    prescriptions are linked, do nothing — sent recepts are immutable on CEZIH side.
    """
    if not therapy_items:
        return None

    lijekovi = [
        {
            "atk": t.get("atk", ""),
            "naziv": t.get("naziv", ""),
            "oblik": t.get("oblik", ""),
            "jacina": t.get("jacina", ""),
            "kolicina": 1,
            "doziranje": t.get("doziranje", ""),
            "napomena": t.get("napomena", ""),
        }
        for t in therapy_items
    ]

    existing = await db.execute(
        select(Prescription)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.medical_record_id == medical_record_id,
            Prescription.cezih_sent == False,  # noqa: E712
            Prescription.cezih_storno == False,  # noqa: E712
        )
        .order_by(Prescription.created_at.desc())
        .limit(1)
    )
    draft = existing.scalar_one_or_none()

    if draft:
        draft.lijekovi = lijekovi
        await db.flush()
        await audit_service.write_audit(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            action="prescription_draft_from_record",
            resource_type="prescription",
            resource_id=draft.id,
            details={"medical_record_id": str(medical_record_id), "created": False},
        )
        return draft

    # Check whether a sent/stornirani prescription exists for this nalaz — if so, don't auto-spawn new drafts.
    any_linked = await db.execute(
        select(func.count())
        .select_from(Prescription)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.medical_record_id == medical_record_id,
        )
    )
    if any_linked.scalar_one() > 0:
        return None

    new_draft = Prescription(
        tenant_id=tenant_id,
        patient_id=patient_id,
        doktor_id=doktor_id,
        medical_record_id=medical_record_id,
        lijekovi=lijekovi,
    )
    db.add(new_draft)
    await db.flush()
    await audit_service.write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="prescription_draft_from_record",
        resource_type="prescription",
        resource_id=new_draft.id,
        details={"medical_record_id": str(medical_record_id), "created": True},
    )
    return new_draft


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

    # CEZIH succeeded — persist locally. If DB fails after CEZIH success,
    # log enough detail for manual reconciliation.
    prescription.cezih_sent = True
    prescription.cezih_sent_at = datetime.now(UTC)
    prescription.cezih_recept_id = cezih_result.get("recept_id", "")
    try:
        await db.flush()
    except Exception:
        logger.critical(
            "CEZIH e-Recept sent but DB update FAILED — manual reconciliation needed. "
            "prescription_id=%s recept_id=%s tenant_id=%s",
            prescription_id, prescription.cezih_recept_id, tenant_id,
        )
        raise

    return {
        "prescription_id": prescription.id,
        "cezih_recept_id": prescription.cezih_recept_id,
        "success": cezih_result.get("success", True),
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
    if not prescription.cezih_recept_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CEZIH recept ID nije pronađen")

    cezih_result = await cezih.cancel_erecept(
        prescription.cezih_recept_id,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        http_client=http_client,
    )

    prescription.cezih_storno = True
    prescription.cezih_storno_at = datetime.now(UTC)
    try:
        await db.flush()
    except Exception:
        logger.critical(
            "CEZIH storno sent but DB update FAILED — manual reconciliation needed. "
            "prescription_id=%s recept_id=%s tenant_id=%s",
            prescription_id, prescription.cezih_recept_id, tenant_id,
        )
        raise

    return {
        "prescription_id": prescription.id,
        "cezih_recept_id": prescription.cezih_recept_id,
        "success": cezih_result.get("success", True),
    }

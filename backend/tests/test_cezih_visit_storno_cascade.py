"""Unit tests for visit storno cascade preflight.

CEZIH rejects Encounter cancel (event 1.4, ERR_ENCOUNTER_2001) while any active
DocumentReference still references it. dispatch_visit_action preflights the local
mirror and either raises 409 cascade_required (so the UI can confirm with the
doctor) or cascades the storno through dispatch_cancel_document.

These tests cover only the preflight branch — the full cascade execution is
covered by E2E on prod (CLAUDE.md mandatory testing workflow).
"""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical_record import MedicalRecord
from app.models.patient import Patient
from app.models.tenant import Tenant
from app.models.user import User
from app.services.cezih.dispatchers.visits import (
    _list_active_cezih_docs_for_visit,
    dispatch_visit_action,
)

pytestmark = pytest.mark.asyncio


async def _seed(db: AsyncSession) -> tuple[Tenant, Patient, User]:
    tenant = Tenant(
        id=uuid.uuid4(),
        naziv="Cascade Test Klinika",
        email=f"cascade-{uuid.uuid4().hex[:8]}@test.hr",
        sifra_ustanove="999001999",
    )
    db.add(tenant)
    await db.flush()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"doc-{uuid.uuid4().hex[:8]}@test.hr",
        hashed_password="x",
        ime="Test",
        prezime="Doktor",
        role="doctor",
        practitioner_id="7659059",
    )
    patient = Patient(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        ime="Ana",
        prezime="Testić",
        mbo="500604936",
        datum_rodjenja=date(1990, 1, 1),
        spol="F",
    )
    db.add(user)
    db.add(patient)
    await db.flush()
    return tenant, patient, user


async def test_list_active_docs_returns_empty_when_no_links(db_session: AsyncSession):
    tenant, _, _ = await _seed(db_session)
    docs = await _list_active_cezih_docs_for_visit(db_session, tenant.id, "VISIT-NONE")
    assert docs == []


async def test_list_active_docs_filters_storno_missing_ref_and_other_visits(
    db_session: AsyncSession,
):
    tenant, patient, user = await _seed(db_session)

    # Active doc on visit — should be returned
    db_session.add(
        MedicalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            doktor_id=user.id,
            datum=date(2026, 5, 1),
            tip="specijalisticki_nalaz",
            sadrzaj="x",
            cezih_encounter_id="VISIT-1",
            cezih_reference_id="DOC-1",
            cezih_storno=False,
        )
    )
    # Already storniran — excluded
    db_session.add(
        MedicalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            doktor_id=user.id,
            datum=date(2026, 5, 2),
            tip="nalaz",
            sadrzaj="x",
            cezih_encounter_id="VISIT-1",
            cezih_reference_id="DOC-2",
            cezih_storno=True,
        )
    )
    # Never sent to CEZIH (no reference_id) — excluded
    db_session.add(
        MedicalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            doktor_id=user.id,
            datum=date(2026, 5, 3),
            tip="nalaz",
            sadrzaj="x",
            cezih_encounter_id="VISIT-1",
            cezih_reference_id=None,
            cezih_storno=False,
        )
    )
    # On a different visit — excluded
    db_session.add(
        MedicalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            doktor_id=user.id,
            datum=date(2026, 5, 4),
            tip="nalaz",
            sadrzaj="x",
            cezih_encounter_id="VISIT-OTHER",
            cezih_reference_id="DOC-3",
            cezih_storno=False,
        )
    )
    await db_session.flush()

    docs = await _list_active_cezih_docs_for_visit(db_session, tenant.id, "VISIT-1")

    assert len(docs) == 1
    assert docs[0]["reference_id"] == "DOC-1"
    assert docs[0]["tip"] == "specijalisticki_nalaz"
    assert docs[0]["datum"] == "2026-05-01"


async def test_storno_with_active_docs_unconfirmed_raises_409(db_session: AsyncSession):
    tenant, patient, user = await _seed(db_session)
    db_session.add(
        MedicalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            doktor_id=user.id,
            datum=date(2026, 5, 1),
            tip="nalaz",
            sadrzaj="x",
            cezih_encounter_id="VISIT-X",
            cezih_reference_id="DOC-X",
            cezih_storno=False,
        )
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await dispatch_visit_action(
            "VISIT-X",
            "storno",
            patient.id,
            db=db_session,
            user_id=user.id,
            tenant_id=tenant.id,
            practitioner_id="7659059",
            org_code="999001464",
            confirm_cascade_docs=False,
        )

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["cascade_required"] is True
    assert len(detail["documents"]) == 1
    assert detail["documents"][0]["reference_id"] == "DOC-X"
    assert "stornirati" in detail["message"]

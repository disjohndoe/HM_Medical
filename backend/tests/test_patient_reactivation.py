"""Re-adding a soft-deleted patient must reactivate the existing row, not 409.

Covers the bug: a patient deleted from the UI (soft delete, is_active=False) still
holds its OIB/MBO via the unique constraints. Re-importing from CEZIH or manually
re-creating used to skip the dead row in the dedup check, attempt an INSERT, and hit
the unique constraint -> 409 with no way to recover the patient.

These exercise the service / dispatcher layer directly against the DB (the HTTP
test harness in conftest does not commit between requests, so cross-request flows
can't be tested through it).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.patient import Patient
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services import patient_service
from app.services.cezih import service as real_service
from app.services.cezih.builders.common import ID_MBO, ID_OIB
from app.services.cezih.dispatchers import patient as patient_dispatcher

# Genuinely valid OIBs (ISO 7064 Mod 11,10); 99999900873 is the one from the bug report.
OIB_A = "99999900873"
OIB_B = "99999900162"
MBO_A = "123456789"


async def _make_tenant_user(db) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a committed Tenant + admin User, return (tenant_id, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(naziv="Reactivate Test", email=f"clinic-{suffix}@test.hr")
    db.add(tenant)
    await db.flush()
    user = User(
        email=f"admin-{suffix}@test.hr",
        hashed_password="x",
        ime="Test",
        prezime="Admin",
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.commit()
    return tenant.id, user.id


# --------------------------------------------------------------------------
# Manual create / update (patient_service)
# --------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_manual_create_reactivates_deleted_oib(db_session):
    tenant_id, _ = await _make_tenant_user(db_session)

    created = await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="Stari", prezime="Pacijent", oib=OIB_A, mbo=MBO_A)
    )
    await db_session.commit()
    pid = created.id
    assert created.is_active is True

    await patient_service.delete_patient(db_session, tenant_id, pid)
    await db_session.commit()
    assert (await db_session.get(Patient, pid)).is_active is False

    # Re-create with the SAME OIB -> must reactivate the same row, not raise 409.
    again = await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="Novi", prezime="Podaci", oib=OIB_A)
    )
    await db_session.commit()
    assert again.id == pid  # same underlying row reactivated
    assert again.ime == "Novi"  # new data applied
    assert again.is_active is True


@pytest.mark.asyncio(loop_scope="session")
async def test_manual_create_reactivates_by_mbo(db_session):
    tenant_id, _ = await _make_tenant_user(db_session)

    created = await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="Stari", prezime="MBO", mbo=MBO_A)
    )
    await db_session.commit()
    pid = created.id

    await patient_service.delete_patient(db_session, tenant_id, pid)
    await db_session.commit()

    again = await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="Novi", prezime="MBO", mbo=MBO_A)
    )
    await db_session.commit()
    assert again.id == pid
    assert again.is_active is True


@pytest.mark.asyncio(loop_scope="session")
async def test_active_duplicate_oib_still_conflicts(db_session):
    tenant_id, _ = await _make_tenant_user(db_session)
    await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="Prvi", prezime="Aktivan", oib=OIB_A)
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await patient_service.create_patient(
            db_session, tenant_id, PatientCreate(ime="Drugi", prezime="Aktivan", oib=OIB_A)
        )
    assert exc.value.status_code == 409  # active holder is a real duplicate


@pytest.mark.asyncio(loop_scope="session")
async def test_update_to_deleted_patient_identifier_gives_clear_409(db_session):
    tenant_id, _ = await _make_tenant_user(db_session)
    a = await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="A", prezime="Brise", oib=OIB_A)
    )
    b = await patient_service.create_patient(
        db_session, tenant_id, PatientCreate(ime="B", prezime="Ostaje", oib=OIB_B)
    )
    await db_session.commit()

    await patient_service.delete_patient(db_session, tenant_id, a.id)
    await db_session.commit()

    # Editing B's OIB to the soft-deleted A's OIB must give a clear 409, not a 500.
    with pytest.raises(HTTPException) as exc:
        await patient_service.update_patient(
            db_session, tenant_id, b.id, PatientUpdate(oib=OIB_A)
        )
    assert exc.value.status_code == 409
    assert "Uvoz iz CEZIH" in exc.value.detail


# --------------------------------------------------------------------------
# CEZIH import dispatchers (CEZIH service monkeypatched)
# --------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_import_by_identifier_reactivates(db_session, monkeypatch):
    tenant_id, user_id = await _make_tenant_user(db_session)

    dead = Patient(
        tenant_id=tenant_id, ime="Stari", prezime="Uvoz", oib=OIB_A, mbo=MBO_A, is_active=False
    )
    db_session.add(dead)
    await db_session.commit()
    dead_id = dead.id

    async def fake_search(http_client, *, identifier_system, value, tenant_id):
        return {
            "ime": "Svjezi",
            "prezime": "Uvoz",
            "identifikatori": [
                {"system": ID_OIB, "value": OIB_A},
                {"system": ID_MBO, "value": MBO_A},
            ],
        }

    monkeypatch.setattr(real_service, "search_patient_by_identifier", fake_search)

    result = await patient_dispatcher.import_patient_by_identifier(
        "oib", OIB_A, db=db_session, user_id=user_id, tenant_id=tenant_id, http_client=None
    )
    await db_session.commit()
    assert result["reactivated"] is True
    assert result["already_exists"] is True
    assert result["id"] == str(dead_id)
    assert (await db_session.get(Patient, dead_id)).is_active is True


@pytest.mark.asyncio(loop_scope="session")
async def test_import_by_mbo_reactivates(db_session, monkeypatch):
    tenant_id, user_id = await _make_tenant_user(db_session)

    dead = Patient(
        tenant_id=tenant_id, ime="Stari", prezime="MBO", oib=OIB_B, mbo=MBO_A, is_active=False
    )
    db_session.add(dead)
    await db_session.commit()
    dead_id = dead.id

    async def fake_search(http_client, *, identifier_system, value, tenant_id):
        return {
            "ime": "Svjezi",
            "prezime": "MBO",
            "identifikatori": [
                {"system": ID_OIB, "value": OIB_B},
                {"system": ID_MBO, "value": MBO_A},
            ],
        }

    monkeypatch.setattr(real_service, "search_patient_by_identifier", fake_search)

    result = await patient_dispatcher.import_patient_from_cezih(
        MBO_A, db=db_session, user_id=user_id, tenant_id=tenant_id, http_client=None
    )
    await db_session.commit()
    assert result["reactivated"] is True
    assert result["id"] == str(dead_id)
    assert (await db_session.get(Patient, dead_id)).is_active is True

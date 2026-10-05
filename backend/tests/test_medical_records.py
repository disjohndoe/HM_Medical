import uuid
from datetime import date

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_medical_record(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    me_resp.json()["id"]

    payload = {
        "patient_id": test_patient_id,
        "datum": date.today().isoformat(),
        "tip": "nalaz",
        "dijagnoza_mkb": "J06.9",
        "dijagnoza_tekst": "Akutna infekcija gornjih dišnih putova",
        "sadrzaj": "Pacijent se javlja zbog kašlja i temperature. Faringijski zid hiperemičan.",
    }
    resp = await client.post("/api/medical-records", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tip"] == "nalaz"
    assert data["dijagnoza_mkb"] == "J06.9"
    assert data["cezih_sent"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_create_medical_record_short_sadrzaj(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str,
):
    payload = {
        "patient_id": test_patient_id,
        "datum": date.today().isoformat(),
        "tip": "nalaz",
        "sadrzaj": "kratko",  # < 10 chars after strip
    }
    resp = await client.post("/api/medical-records", json=payload, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_medical_record(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    payload = {
        "patient_id": test_patient_id,
        "datum": date.today().isoformat(),
        "tip": "nalaz",
        "sadrzaj": "Detaljan nalaz pregleda pacijenta s opisom nalaza.",
    }
    create_resp = await client.post("/api/medical-records", json=payload, headers=auth_headers)
    record_id = create_resp.json()["id"]

    resp = await client.get(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tip"] == "nalaz"


@pytest.mark.asyncio
async def test_update_medical_record(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    payload = {
        "patient_id": test_patient_id,
        "datum": date.today().isoformat(),
        "tip": "nalaz",
        "sadrzaj": "Inicijalni nalaz pregleda pacijenta.",
    }
    create_resp = await client.post("/api/medical-records", json=payload, headers=auth_headers)
    record_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/medical-records/{record_id}",
        json={"dijagnoza_mkb": "M54.5", "dijagnoza_tekst": "Bol u donjem dijelu leđa"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["dijagnoza_mkb"] == "M54.5"


@pytest.mark.asyncio
async def test_list_medical_records(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    resp = await client.get("/api/medical-records", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_filter_medical_records_by_patient(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str,
):
    # Create a record
    payload = {
        "patient_id": test_patient_id,
        "datum": date.today().isoformat(),
        "tip": "epikriza",
        "sadrzaj": "epikriza akutnog bronhitisa mukolitičkom terapijom.",
    }
    await client.post("/api/medical-records", json=payload, headers=auth_headers)

    resp = await client.get(f"/api/medical-records?patient_id={test_patient_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert all(r["patient_id"] == test_patient_id for r in data["items"])


@pytest.mark.asyncio
async def test_procedure_catalog_seeded(client: AsyncClient, auth_headers: dict[str, str]):
    """Procedures are auto-seeded on registration."""
    resp = await client.get("/api/procedures", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    codes = [p["sifra"] for p in data["items"]]
    assert "D001" in codes  # Opći pregled
    assert "P002" in codes  # Specijalistički pregled


async def _create_record(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str) -> str:
    payload = {
        "patient_id": test_patient_id,
        "datum": date.today().isoformat(),
        "tip": "nalaz",
        "sadrzaj": "Nalaz koji će biti obrisan.",
    }
    resp = await client.post("/api/medical-records", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_delete_medical_record(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    record_id = await _create_record(client, auth_headers, test_patient_id)

    resp = await client.delete(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_medical_record_sent_to_cezih_rejected(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    record_id = await _create_record(client, auth_headers, test_patient_id)

    from sqlalchemy import update
    from app.models.medical_record import MedicalRecord
    await db_session.execute(
        update(MedicalRecord).where(MedicalRecord.id == record_id).values(cezih_sent=True)
    )
    await db_session.commit()

    resp = await client.delete(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 409

    resp = await client.get(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_medical_record_other_tenant(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str
):
    # Register sets httpOnly cookies that take precedence over Bearer headers,
    # so clear the jar before each authed call to control which tenant acts.
    client.cookies.clear()
    record_id = await _create_record(client, auth_headers, test_patient_id)

    other_payload = {
        "naziv_klinike": "Druga Ordinacija",
        "email": "druga@test.hr",
        "password": "Test1234!",
        "ime": "Druga",
        "prezime": "Klinika",
        "terms_accepted": True,
    }
    reg = await client.post("/api/auth/register", json=other_payload)
    other_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    client.cookies.clear()
    resp = await client.delete(f"/api/medical-records/{record_id}", headers=other_headers)
    assert resp.status_code == 404

    client.cookies.clear()
    resp = await client.get(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_medical_record_unlinks_dependents(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    from sqlalchemy import select
    from app.models.document import Document
    from app.models.medical_record import MedicalRecord
    from app.models.prescription import Prescription
    from app.models.procedure import PerformedProcedure, Procedure
    from app.models.user import User

    record_id = await _create_record(client, auth_headers, test_patient_id)

    me = (await client.get("/api/auth/me", headers=auth_headers)).json()
    record = (await db_session.execute(select(MedicalRecord).where(MedicalRecord.id == record_id))).scalar_one()
    procedure = (await db_session.execute(select(Procedure).limit(1))).scalar_one()

    doc = Document(
        tenant_id=me["tenant_id"],
        patient_id=record.patient_id,
        medical_record_id=record.id,
        naziv="Prilog nalaza",
        kategorija="nalaz",
        file_path="/tmp/prilog.pdf",
        file_size=100,
        mime_type="application/pdf",
        uploaded_by=me["id"],
    )
    rx = Prescription(
        tenant_id=me["tenant_id"],
        patient_id=record.patient_id,
        doktor_id=record.doktor_id,
        medical_record_id=record.id,
        lijekovi=[{"atk": "N05BA01", "naziv": "Diazepam", "kolicina": 1, "doziranje": "1x1"}],
    )
    performed = PerformedProcedure(
        tenant_id=me["tenant_id"],
        patient_id=record.patient_id,
        medical_record_id=record.id,
        procedure_id=procedure.id,
        doktor_id=record.doktor_id,
        datum=date.today(),
        cijena_cents=10000,
    )
    db_session.add_all([doc, rx, performed])
    await db_session.commit()
    doc_id, rx_id, performed_id = doc.id, rx.id, performed.id

    resp = await client.delete(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Dependents survive, unlinked from the deleted record.
    # The unlinking happened in the request's session; expire our identity
    # map so the assertions re-read current column values.
    db_session.sync_session.expire_all()
    doc_after = (await db_session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
    rx_after = (await db_session.execute(select(Prescription).where(Prescription.id == rx_id))).scalar_one()
    performed_after = (
        await db_session.execute(select(PerformedProcedure).where(PerformedProcedure.id == performed_id))
    ).scalar_one()
    assert doc_after.medical_record_id is None
    assert rx_after.medical_record_id is None
    assert performed_after.medical_record_id is None

    record_after = (
        await db_session.execute(select(MedicalRecord).where(MedicalRecord.id == record_id))
    ).scalar_one_or_none()
    assert record_after is None


@pytest.mark.asyncio
async def test_delete_medical_record_audit_logged(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    from sqlalchemy import select
    from app.models.audit_log import AuditLog

    record_id = await _create_record(client, auth_headers, test_patient_id)

    resp = await client.delete(f"/api/medical-records/{record_id}", headers=auth_headers)
    assert resp.status_code == 204

    entries = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "medical_record_delete",
                AuditLog.resource_id == uuid.UUID(record_id),
            )
        )
    ).scalars().all()
    assert len(entries) == 1

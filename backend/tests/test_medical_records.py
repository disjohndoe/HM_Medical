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

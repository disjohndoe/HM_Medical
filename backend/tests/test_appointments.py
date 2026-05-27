from datetime import date, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_appointment(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    # Get the current user (doctor) id from /me
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    doctor_id = me_resp.json()["id"]

    tomorrow = date.today() + timedelta(days=1)
    payload = {
        "patient_id": test_patient_id,
        "doktor_id": doctor_id,
        "datum_vrijeme": f"{tomorrow.isoformat()}T10:00:00Z",
        "trajanje_minuta": 30,
        "vrsta": "pregled",
    }
    resp = await client.post("/api/appointments", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "zakazan"
    assert data["vrsta"] == "pregled"
    assert data["trajanje_minuta"] == 30


@pytest.mark.asyncio
async def test_appointment_conflict(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    doctor_id = me_resp.json()["id"]

    tomorrow = date.today() + timedelta(days=1)
    base_dt = f"{tomorrow.isoformat()}T10:00:00Z"

    payload = {
        "patient_id": test_patient_id,
        "doktor_id": doctor_id,
        "datum_vrijeme": base_dt,
        "trajanje_minuta": 30,
        "vrsta": "pregled",
    }
    resp1 = await client.post("/api/appointments", json=payload, headers=auth_headers)
    assert resp1.status_code == 201

    # Overlapping: 10:15 (overlaps with 10:00-10:30)
    payload2 = {
        **payload,
        "datum_vrijeme": f"{tomorrow.isoformat()}T10:15:00Z",
        "patient_id": test_patient_id,
    }
    resp2 = await client.post("/api/appointments", json=payload2, headers=auth_headers)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_get_appointment(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    doctor_id = me_resp.json()["id"]

    tomorrow = date.today() + timedelta(days=1)
    payload = {
        "patient_id": test_patient_id,
        "doktor_id": doctor_id,
        "datum_vrijeme": f"{tomorrow.isoformat()}T11:00:00Z",
        "trajanje_minuta": 30,
        "vrsta": "kontrola",
    }
    create_resp = await client.post("/api/appointments", json=payload, headers=auth_headers)
    appt_id = create_resp.json()["id"]

    resp = await client.get(f"/api/appointments/{appt_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["vrsta"] == "kontrola"


@pytest.mark.asyncio
async def test_update_appointment(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    doctor_id = me_resp.json()["id"]

    tomorrow = date.today() + timedelta(days=1)
    payload = {
        "patient_id": test_patient_id,
        "doktor_id": doctor_id,
        "datum_vrijeme": f"{tomorrow.isoformat()}T12:00:00Z",
        "trajanje_minuta": 30,
        "vrsta": "pregled",
    }
    create_resp = await client.post("/api/appointments", json=payload, headers=auth_headers)
    appt_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/appointments/{appt_id}",
        json={"status": "potvrdjen", "napomena": "Potvrđen termin"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "potvrdjen"
    assert resp.json()["napomena"] == "Potvrđen termin"


@pytest.mark.asyncio
async def test_delete_appointment_only_zakazan(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    doctor_id = me_resp.json()["id"]

    tomorrow = date.today() + timedelta(days=1)
    payload = {
        "patient_id": test_patient_id,
        "doktor_id": doctor_id,
        "datum_vrijeme": f"{tomorrow.isoformat()}T13:00:00Z",
        "trajanje_minuta": 30,
        "vrsta": "pregled",
    }
    create_resp = await client.post("/api/appointments", json=payload, headers=auth_headers)
    appt_id = create_resp.json()["id"]

    # Delete zakazan appointment — should succeed
    resp = await client.delete(f"/api/appointments/{appt_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Create another and change status, then try to delete
    payload2 = {
        **payload,
        "datum_vrijeme": f"{tomorrow.isoformat()}T14:00:00Z",
    }
    create2 = await client.post("/api/appointments", json=payload2, headers=auth_headers)
    appt_id2 = create2.json()["id"]

    await client.patch(f"/api/appointments/{appt_id2}", json={"status": "zavrsen"}, headers=auth_headers)
    del_resp = await client.delete(f"/api/appointments/{appt_id2}", headers=auth_headers)
    assert del_resp.status_code == 400  # can't delete non-zakazan (service returns 400)


@pytest.mark.asyncio
async def test_available_slots(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    doctor_id = me_resp.json()["id"]

    tomorrow = date.today() + timedelta(days=1)
    resp = await client.get(
        "/api/appointments/available-slots",
        params={"doktor_id": doctor_id, "date": tomorrow.isoformat(), "trajanje_minuta": 30},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    slots = resp.json()
    assert isinstance(slots, list)
    # Each slot should have start and end
    if slots:
        assert "start" in slots[0]
        assert "end" in slots[0]


@pytest.mark.asyncio
async def test_list_appointments(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    resp = await client.get("/api/appointments", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data

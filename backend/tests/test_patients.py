import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_patient(client: AsyncClient, auth_headers: dict[str, str]):
    payload = {
        "ime": "Ana",
        "prezime": "Testić",
        "oib": "99999900162",
        "mbo": "123456789",
        "datum_rodjenja": "1995-05-20",
        "spol": "Z",
        "telefon": "01/234-5678",
        "grad": "Zagreb",
    }
    resp = await client.post("/api/patients", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["ime"] == "Ana"
    assert data["prezime"] == "Testić"
    assert data["oib"] == "99999900162"
    assert data["mbo"] == "123456789"
    assert data["spol"] == "Z"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_patient_invalid_oib(client: AsyncClient, auth_headers: dict[str, str]):
    payload = {
        "ime": "Bad",
        "prezime": "OIB",
        "oib": "00000000000",  # invalid checksum
        "mbo": "123456789",
    }
    resp = await client.post("/api/patients", json=payload, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_patient_invalid_mbo(client: AsyncClient, auth_headers: dict[str, str]):
    payload = {
        "ime": "Bad",
        "prezime": "MBO",
        "oib": "99999900162",
        "mbo": "123",  # wrong length
    }
    resp = await client.post("/api/patients", json=payload, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_patient_duplicate_oib(client: AsyncClient, auth_headers: dict[str, str]):
    payload = {
        "ime": "Prvi",
        "prezime": "Pacijent",
        "oib": "99999900162",
        "mbo": "111111111",
    }
    resp1 = await client.post("/api/patients", json=payload, headers=auth_headers)
    assert resp1.status_code == 201

    payload2 = {**payload, "ime": "Drugi", "prezime": "Pacijent", "mbo": "222222222"}
    resp2 = await client.post("/api/patients", json=payload2, headers=auth_headers)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_get_patient(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    resp = await client.get(f"/api/patients/{test_patient_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ime"] == "Ivan"
    assert data["prezime"] == "Testić"


@pytest.mark.asyncio
async def test_update_patient(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    resp = await client.patch(
        f"/api/patients/{test_patient_id}",
        json={"napomena": "Alergija na penicilin"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["napomena"] == "Alergija na penicilin"


@pytest.mark.asyncio
async def test_delete_patient(client: AsyncClient, auth_headers: dict[str, str]):
    # Create a patient to delete
    payload = {
        "ime": "Za",
        "prezime": "Brisanje",
        "oib": "99999900162",
    }
    create_resp = await client.post("/api/patients", json=payload, headers=auth_headers)
    patient_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/patients/{patient_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify it's gone
    get_resp = await client.get(f"/api/patients/{patient_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_patients(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    resp = await client.get("/api/patients", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_search_patients(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    resp = await client.get("/api/patients?search=Testić", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(p["prezime"] == "Testić" for p in data["items"])


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str):
    """Patient from tenant A should be invisible to tenant B."""
    # Register a second tenant
    reg = await client.post(
        "/api/auth/register",
        json={
            "naziv_klinike": "Druga Ordinacija",
            "email": "other@test.hr",
            "password": "Other1234!",
            "ime": "Drugi",
            "prezime": "Admin",
            "terms_accepted": True,
        },
    )
    other_token = reg.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Try to access the patient from tenant A
    resp = await client.get(f"/api/patients/{test_patient_id}", headers=other_headers)
    assert resp.status_code == 404

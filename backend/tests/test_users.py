"""User deletion semantics: hard delete + identifier release.

Regression (prod issue 2026-10): deleting a user soft-deactivated the row but
kept practitioner_id (HZJZ šifra djelatnika) and mbo_lijecnika on it, so the
partial unique indexes blocked onboarding a replacement user with the same
codes. Deletion must free those identifiers in every case.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.models.tenant import Tenant


async def _raise_plan_limit(db_session) -> None:
    """Allow more users so creation tests don't trip the trial plan limit."""
    await db_session.execute(update(Tenant).values(plan_tier="poliklinika_plus"))
    await db_session.commit()


DOCTOR = {
    "email": "testni55@hmdigital.hr",
    "password": "Demo1234!",
    "ime": "TESTNI55",
    "prezime": "TESTNIPREZIME55",
    "role": "doctor",
    "practitioner_id": "7659059",
    "mbo_lijecnika": "500604936",
    "cezih_signing_method": "extsigner",
}


async def _create_user(client: AsyncClient, headers: dict, payload: dict) -> dict:
    resp = await client.post("/api/users", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_delete_user_without_history_hard_deletes_row_and_frees_identifiers(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    await _raise_plan_limit(db_session)
    doctor = await _create_user(client, auth_headers, DOCTOR)

    resp = await client.delete(f"/api/users/{doctor['id']}", headers=auth_headers)
    assert resp.status_code == 204

    # Hard delete: the row is gone entirely.
    resp = await client.get(f"/api/users/{doctor['id']}", headers=auth_headers)
    assert resp.status_code == 404

    resp = await client.get("/api/users", headers=auth_headers)
    listed_ids = [u["id"] for u in resp.json()["items"]]
    assert doctor["id"] not in listed_ids

    # HZJZ + MBO immediately reusable by a replacement user.
    replacement = {**DOCTOR, "email": "replacement@hmdigital.hr"}
    created = await _create_user(client, auth_headers, replacement)
    assert created["practitioner_id"] == "7659059"
    assert created["mbo_lijecnika"] == "500604936"

    # Email freed as well — same address can be re-registered.
    await _create_user(client, auth_headers, {**DOCTOR, "practitioner_id": None, "mbo_lijecnika": None})


@pytest.mark.asyncio
async def test_delete_user_with_history_frees_hzjz_but_keeps_clinical_rows(
    client: AsyncClient, auth_headers: dict[str, str], db_session, test_patient_id: str
):
    await _raise_plan_limit(db_session)
    doctor = await _create_user(client, auth_headers, DOCTOR)

    tomorrow = date.today() + timedelta(days=1)
    appointment_payload = {
        "patient_id": test_patient_id,
        "doktor_id": doctor["id"],
        "datum_vrijeme": f"{tomorrow.isoformat()}T10:00:00Z",
        "trajanje_minuta": 30,
        "vrsta": "pregled",
    }
    resp = await client.post("/api/appointments", json=appointment_payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    appointment_id = resp.json()["id"]

    resp = await client.delete(f"/api/users/{doctor['id']}", headers=auth_headers)
    assert resp.status_code == 204

    # The row survives as an inactive tombstone (NOT NULL author FKs on clinical
    # tables) but holds no reusable identifier anymore.
    resp = await client.get(f"/api/users/{doctor['id']}", headers=auth_headers)
    assert resp.status_code == 200
    tombstone = resp.json()
    assert tombstone["is_active"] is False
    assert tombstone["practitioner_id"] is None
    assert tombstone["mbo_lijecnika"] is None
    assert tombstone["email"].startswith("deleted+")

    # Tombstones are not listed in the admin user list.
    resp = await client.get("/api/users", headers=auth_headers)
    listed_ids = [u["id"] for u in resp.json()["items"]]
    assert doctor["id"] not in listed_ids

    # HZJZ immediately reusable by a replacement user.
    replacement = {**DOCTOR, "email": "replacement@hmdigital.hr"}
    created = await _create_user(client, auth_headers, replacement)
    assert created["practitioner_id"] == "7659059"

    # The historical appointment still resolves its author.
    resp = await client.get(f"/api/appointments/{appointment_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["doktor_ime"] == "TESTNI55"


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    me_id = resp.json()["id"]

    resp = await client.delete(f"/api/users/{me_id}", headers=auth_headers)
    assert resp.status_code == 400

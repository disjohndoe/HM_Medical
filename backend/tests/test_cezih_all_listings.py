"""Tenant-isolation tests for the tenant-wide mirror listings.

GET /api/cezih/visits/all and /api/cezih/cases/all read the local
CezihVisit/CezihCase mirrors across all patients of the CALLER's tenant
(mirror-only, no live CEZIH call). These tests seed rows in two tenants
and verify only the caller's rows come back, with the patient name
denormalized so the global tables can link to the patient.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cezih_case import CezihCase
from app.models.cezih_visit import CezihVisit
from app.models.patient import Patient
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _tenant_id_for_email(db: AsyncSession, email: str):
    result = await db.execute(select(User.tenant_id).where(User.email == email))
    return result.scalar_one()


async def _seed_patient_with_mirror_rows(
    db: AsyncSession,
    tenant_id,
    *,
    ime: str,
    mbo: str,
    visits: int = 0,
    cases: int = 0,
) -> Patient:
    patient = Patient(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ime=ime,
        prezime="Testić",
        mbo=mbo,
        datum_rodjenja=date(1990, 1, 1),
        spol="Z",
    )
    db.add(patient)
    await db.flush()
    for i in range(visits):
        db.add(
            CezihVisit(
                tenant_id=tenant_id,
                patient_id=patient.id,
                patient_mbo=mbo,
                cezih_visit_id=f"VISIT-{mbo}-{i}",
                status="in-progress",
                period_start=datetime(2026, 10, 1, 9 + i, 0, tzinfo=UTC),
            )
        )
    for i in range(cases):
        db.add(
            CezihCase(
                tenant_id=tenant_id,
                patient_id=patient.id,
                patient_mbo=mbo,
                local_case_id=f"LOCAL-{mbo}-{i}",
                cezih_case_id=f"CASE-{mbo}-{i}",
                icd_code="J06.9",
                icd_display="Akutna infekcija gornjih dišnih puteova",
                clinical_status="active",
                onset_date="2026-10-01",
            )
        )
    await db.commit()
    return patient


async def test_visits_all_returns_only_caller_tenant_rows(
    client: AsyncClient, auth_headers: dict, auth_headers_doctor: dict, db_session: AsyncSession
):
    tenant_a = await _tenant_id_for_email(db_session, "admin@test.hr")
    tenant_b = await _tenant_id_for_email(db_session, "doctor@test.hr")
    await _seed_patient_with_mirror_rows(
        db_session, tenant_a, ime="Ana", mbo="100000001", visits=2
    )
    await _seed_patient_with_mirror_rows(
        db_session, tenant_b, ime="Ivan", mbo="100000002", visits=5
    )

    resp = await client.get("/api/cezih/visits/all", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(v["patient_ime"] == "Ana" for v in body["items"])
    assert all(v["patient_id"] for v in body["items"])

    resp_b = await client.get("/api/cezih/visits/all", headers=auth_headers_doctor)
    assert resp_b.status_code == 200
    assert resp_b.json()["total"] == 5
    assert all(v["patient_ime"] == "Ivan" for v in resp_b.json()["items"])


async def test_cases_all_returns_only_caller_tenant_rows(
    client: AsyncClient, auth_headers: dict, auth_headers_doctor: dict, db_session: AsyncSession
):
    tenant_a = await _tenant_id_for_email(db_session, "admin@test.hr")
    tenant_b = await _tenant_id_for_email(db_session, "doctor@test.hr")
    await _seed_patient_with_mirror_rows(
        db_session, tenant_a, ime="Ana", mbo="100000001", cases=1
    )
    await _seed_patient_with_mirror_rows(
        db_session, tenant_b, ime="Ivan", mbo="100000002", cases=3
    )

    resp = await client.get("/api/cezih/cases/all", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["patient_ime"] == "Ana"
    assert body["items"][0]["registered"] is True
    assert body["items"][0]["icd_code"] == "J06.9"

    resp_b = await client.get("/api/cezih/cases/all", headers=auth_headers_doctor)
    assert resp_b.status_code == 200
    assert resp_b.json()["total"] == 3


async def test_visits_all_pagination(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    tenant_a = await _tenant_id_for_email(db_session, "admin@test.hr")
    await _seed_patient_with_mirror_rows(
        db_session, tenant_a, ime="Ana", mbo="100000001", visits=3
    )

    resp = await client.get(
        "/api/cezih/visits/all", params={"skip": 1, "limit": 2}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["skip"] == 1 and body["limit"] == 2
    # period_start desc ordering: page 2 starts at the second-newest visit
    starts = [v["period_start"] for v in body["items"]]
    assert starts == sorted(starts, reverse=True)

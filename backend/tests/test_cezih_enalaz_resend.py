"""e-Nalaz send/resend backend behaviour: idempotency guard, row lock,
error persistence, failure audit and the missing-reference-id hard fail.

The dispatcher boundary (`app.services.cezih.service.send_enalaz` — the FHIR
layer entry) is monkeypatched so no real CEZIH/signing call ever happens; the
tests exercise the dispatcher's state transitions against the test database.
"""
import asyncio
import json
import os
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_log import AuditLog
from app.models.cezih_visit import CezihVisit
from app.models.medical_record import MedicalRecord
from app.models.tenant import Tenant
from app.models.user import User
from app.services.cezih.exceptions import CezihConnectionError, CezihFhirError, CezihLocalPersistError

_test_session_factory: async_sessionmaker | None = None


def _get_test_session_factory() -> async_sessionmaker:
    global _test_session_factory
    if _test_session_factory is None:
        url = os.getenv(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5433/medical_mvp_test",
        )
        _test_session_factory = async_sessionmaker(
            create_async_engine(url), class_=AsyncSession, expire_on_commit=False
        )
    return _test_session_factory


@pytest.fixture(autouse=True)
def _own_session_writes_go_to_test_db(monkeypatch):
    """record_cezih_error/_write_send_failed_audit open their own sessions via
    app.database.async_session, which resolves to the DEV database from .env —
    rebind them to the test session factory so writes land in medical_mvp_test
    instead of polluting the dev DB."""
    factory = _get_test_session_factory()
    monkeypatch.setattr("app.services.cezih.error_persistence.async_session", factory)
    monkeypatch.setattr("app.database.async_session", factory)
    yield


@pytest.fixture(autouse=True)
def _app_http_client():
    """The ASGI test transport never runs the lifespan that sets
    app.state.http_client; /api/cezih/e-nalaz reads it before dispatching.
    The send itself is mocked in these tests, so an inert placeholder is fine."""
    from app.main import app

    app.state.http_client = object()
    yield
    del app.state.http_client


async def _setup_sendable_tenant(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> dict:
    """Tenant sifra/OID + practitioner/djelatnost so a send passes pre-flight
    checks. Set via db_session because PATCH /settings/clinic ignores `oid`."""
    me = (await client.get("/api/auth/me", headers=auth_headers)).json()
    tenant = await db_session.get(Tenant, me["tenant_id"])
    tenant.sifra_ustanove = "12345"
    tenant.oid = "1.2.3.4.5"
    user = await db_session.get(User, me["id"])
    user.practitioner_id = "12345678"
    # tip "nalaz" maps to HRTipDokumenta 012 -> djelatnost must start with "2"
    user.djelatnost_code = "2010000"
    user.djelatnost_display = "Specijalistička ordinacija"
    await db_session.commit()
    return {"user_id": me["id"], "tenant_id": me["tenant_id"]}


async def _create_record(
    client: AsyncClient, auth_headers: dict[str, str], patient_id: str
) -> str:
    resp = await client.post(
        "/api/medical-records",
        json={
            "patient_id": patient_id,
            "datum": date.today().isoformat(),
            "tip": "nalaz",
            "dijagnoza_mkb": "J06.9",
            "dijagnoza_tekst": "Akutna infekcija gornjih dišnih putova",
            "sadrzaj": "Pacijent se javlja zbog kašlja i temperature, faringijski zid hiperemičan.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _get_record(db_session, record_id: str) -> MedicalRecord:
    record = await db_session.get(MedicalRecord, record_id)
    await db_session.refresh(record)
    return record


async def _send(client: AsyncClient, auth_headers: dict[str, str], patient_id: str, record_id: str):
    return await client.post(
        "/api/cezih/e-nalaz",
        json={"patient_id": patient_id, "record_id": record_id},
        headers=auth_headers,
    )


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_rejected_when_already_sent(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_sent = True
    record.cezih_reference_id = "CEZIH-REF-1"
    await db_session.commit()

    resp = await _send(client, auth_headers, test_patient_id, record_id)

    assert resp.status_code == 409, resp.text
    assert "već poslan" in resp.json()["detail"]
    assert "CEZIH-REF-1" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_rejected_when_storno(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_storno = True
    await db_session.commit()

    resp = await _send(client, auth_headers, test_patient_id, record_id)

    assert resp.status_code == 409, resp.text
    assert "storniran" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# CEZIH_LOCAL_PERSIST_FAILED: resend blocked by default, force_resend overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_blocked_after_local_persist_failure_without_force(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    """After a sent-but-unpersisted attempt the row still reads unsent while a
    signed document may exist on CEZIH - a blind resend would duplicate it."""
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_last_error_code = CezihLocalPersistError.default_code
    await db_session.commit()

    calls = []

    async def tracking_send(*args, **kwargs):
        calls.append(args)
        return {"success": True, "reference_id": "R", "sent_at": "2026-10-06T12:00:00+00:00"}

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", tracking_send)

    resp = await _send(client, auth_headers, test_patient_id, record_id)

    assert resp.status_code == 409, resp.text
    assert "duplikat" in resp.json()["detail"].lower()
    assert calls == [], "blocked resend must not reach the FHIR layer"


@pytest.mark.asyncio
async def test_send_after_local_persist_failure_with_force_overrides_and_audits(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    ctx = await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_last_error_code = CezihLocalPersistError.default_code
    await db_session.commit()

    async def ok_send(*args, **kwargs):
        return {
            "success": True,
            "reference_id": "CEZIH-REF-FORCE",
            "document_oid": "2.999.3.1",
            "sent_at": "2026-10-06T12:00:00+00:00",
        }

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", ok_send)

    resp = await client.post(
        "/api/cezih/e-nalaz",
        json={"patient_id": test_patient_id, "record_id": record_id, "force_resend": True},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["reference_id"] == "CEZIH-REF-FORCE"
    record = await _get_record(db_session, record_id)
    assert record.cezih_sent is True
    assert record.cezih_last_error_code is None

    sends = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == ctx["tenant_id"],
                AuditLog.action == "e_nalaz_send",
            )
        )
    ).scalars().all()
    assert len(sends) == 1
    details = json.loads(sends[0].details)
    assert details["retry"] is True
    assert details["forced_retry"] is True


# ---------------------------------------------------------------------------
# Failure -> error columns + failure audit, then retry -> success + retry audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_send_persists_error_and_writes_failure_audit(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    ctx = await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)

    async def failing_send(*args, **kwargs):
        raise CezihConnectionError("Nije moguće doći do CEZIH poslužitelja")

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", failing_send)

    resp = await _send(client, auth_headers, test_patient_id, record_id)

    assert resp.status_code == 503
    record = await _get_record(db_session, record_id)
    assert record.cezih_sent is False
    assert record.cezih_last_error_code == "CEZIH_CONNECTION_ERROR"
    assert record.cezih_last_error_at is not None

    audits = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == ctx["tenant_id"],
                AuditLog.action == "e_nalaz_send_failed",
            )
        )
    ).scalars().all()
    assert len(audits) == 1
    details = json.loads(audits[0].details)
    assert details["record_id"] == record_id
    assert details["error_code"] == "CEZIH_CONNECTION_ERROR"


@pytest.mark.asyncio
async def test_resend_after_failure_succeeds_and_audits_retry(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    ctx = await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)

    attempts = {"n": 0}

    async def flaky_send(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise CezihConnectionError("Nije moguće doći do CEZIH poslužitelja")
        return {
            "success": True,
            "reference_id": "CEZIH-REF-RETRY",
            "document_oid": "2.999.1.1",
            "sent_at": "2026-10-06T12:00:00+00:00",
            "signed_at": "2026-10-06T12:00:00+00:00",
            "signature_data": "sig",
        }

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", flaky_send)

    first = await _send(client, auth_headers, test_patient_id, record_id)
    assert first.status_code == 503

    second = await _send(client, auth_headers, test_patient_id, record_id)
    assert second.status_code == 200, second.text
    assert second.json()["reference_id"] == "CEZIH-REF-RETRY"

    record = await _get_record(db_session, record_id)
    assert record.cezih_sent is True
    assert record.cezih_reference_id == "CEZIH-REF-RETRY"
    assert record.cezih_last_error_code is None
    assert record.cezih_last_error_at is None

    sends = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == ctx["tenant_id"],
                AuditLog.action == "e_nalaz_send",
            )
        )
    ).scalars().all()
    assert len(sends) == 1
    assert json.loads(sends[0].details)["retry"] is True

    # Idempotency: a third attempt now hits the 409 guard.
    third = await _send(client, auth_headers, test_patient_id, record_id)
    assert third.status_code == 409


# ---------------------------------------------------------------------------
# Row lock: two concurrent sends -> exactly one success, one 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_sends_serialized_by_row_lock(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)

    async def slow_send(*args, **kwargs):
        # Hold the FOR UPDATE row lock long enough for the second request to
        # pile up on it, like a real ~seconds-long signing round-trip would.
        await asyncio.sleep(0.3)
        return {
            "success": True,
            "reference_id": "CEZIH-REF-RACE",
            "document_oid": "2.999.1.2",
            "sent_at": "2026-10-06T12:00:00+00:00",
        }

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", slow_send)

    resp_a, resp_b = await asyncio.gather(
        _send(client, auth_headers, test_patient_id, record_id),
        _send(client, auth_headers, test_patient_id, record_id),
    )
    statuses = sorted([resp_a.status_code, resp_b.status_code])

    assert statuses == [200, 409], f"expected one success and one 409, got {statuses}"
    record = await _get_record(db_session, record_id)
    assert record.cezih_sent is True


@pytest.mark.asyncio
async def test_concurrent_send_lock_timeout_fails_fast_with_409(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    """When the lock is held longer than CEZIH_SEND_LOCK_TIMEOUT, the losing
    request aborts with a 'send in progress' 409 instead of queueing on a pooled
    connection for the whole signing round-trip."""
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)

    monkeypatch.setattr("app.config.settings.CEZIH_SEND_LOCK_TIMEOUT", 1)

    async def slow_send(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {
            "success": True,
            "reference_id": "CEZIH-REF-LOCKTIMEOUT",
            "document_oid": "2.999.4.1",
            "sent_at": "2026-10-06T12:00:00+00:00",
        }

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", slow_send)

    resp_a, resp_b = await asyncio.gather(
        _send(client, auth_headers, test_patient_id, record_id),
        _send(client, auth_headers, test_patient_id, record_id),
    )

    loser = resp_a if resp_a.status_code == 409 else resp_b
    winner = resp_b if resp_a.status_code == 409 else resp_a
    assert winner.status_code == 200, winner.text
    assert loser.status_code == 409, loser.text
    assert "već u tijeku" in loser.json()["detail"]
    record = await _get_record(db_session, record_id)
    assert record.cezih_sent is True


# ---------------------------------------------------------------------------
# FHIR layer: no fabricated reference id on unparseable ITI-65 response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fhir_send_missing_reference_id_raises_instead_of_fabricating(monkeypatch):
    import app.services.cezih.fhir_api.documents as fhir_documents

    async def fake_build_bundle(*args, **kwargs):
        return ({}, "1.2.3.4.5.6")

    async def fake_post(self, path, json_body=None, **kwargs):
        # Valid transaction bundle shape but without any DocumentReference
        # location — the case that used to fabricate "FHIR-<timestamp>".
        return {"resourceType": "Bundle", "entry": []}

    monkeypatch.setattr(fhir_documents, "_build_document_bundle", fake_build_bundle)
    monkeypatch.setattr("app.services.cezih.client.CezihFhirClient.post", fake_post)

    with pytest.raises(CezihFhirError) as exc_info:
        await fhir_documents.send_enalaz(
            None,
            {
                "mbo": "123456789",
                "identifier_system": "http://example.org/mbo",
                "identifier_value": "123456789",
                "identifiers": [],
                "ime": "Ivan",
                "prezime": "Testić",
            },
            {
                "tip": "nalaz",
                "dijagnoza_mkb": "J06.9",
                "dijagnoza_tekst": "",
                "sadrzaj": "sadržaj nalaza",
                "preporucena_terapija": "",
                "created_at": "2026-10-06T00:00:00+00:00",
            },
            djelatnost_code="2010000",
            djelatnost_display="Specijalistička ordinacija",
        )

    outcome = exc_info.value.to_operation_outcome()
    assert outcome["code"] == "CEZIH_MISSING_REFERENCE_ID"
    assert "duplikat" in exc_info.value.message


def _fhir_patient_data() -> dict:
    return {
        "mbo": "123456789",
        "identifier_system": "http://example.org/mbo",
        "identifier_value": "123456789",
        "identifiers": [],
        "ime": "Ivan",
        "prezime": "Testić",
    }


def _fhir_record_data() -> dict:
    return {
        "tip": "nalaz",
        "dijagnoza_mkb": "J06.9",
        "dijagnoza_tekst": "",
        "sadrzaj": "sadržaj nalaza",
        "preporucena_terapija": "",
        "created_at": "2026-10-06T00:00:00+00:00",
    }


async def _fake_live_head_current(fhir_client, original_reference_id, identifier_system, identifier_value):
    return {"state": "current", "reference_id": original_reference_id, "oid": "2.999.9.9"}


@pytest.mark.asyncio
@pytest.mark.parametrize("fhir_fn_name", ["replace_document", "amend_document"])
async def test_fhir_replace_and_amend_missing_reference_id_raise_instead_of_fabricating(
    monkeypatch, fhir_fn_name
):
    """Same rule as the send path: a 2xx ITI-65 response without a parsable
    DocumentReference id must hard-fail, never fabricate FHIR-R-/FHIR-A-."""
    import app.services.cezih.fhir_api.documents as fhir_documents

    async def fake_build_bundle(*args, **kwargs):
        return ({}, "1.2.3.4.5.7")

    async def fake_post(self, path, json_body=None, **kwargs):
        # Valid transaction bundle shape but without any DocumentReference
        # location — the case that used to fabricate "FHIR-R-<timestamp>" /
        # "FHIR-A-<timestamp>".
        return {"resourceType": "Bundle", "entry": []}

    monkeypatch.setattr(fhir_documents, "_build_document_bundle", fake_build_bundle)
    monkeypatch.setattr(fhir_documents, "_resolve_live_document_head", _fake_live_head_current)
    monkeypatch.setattr("app.services.cezih.client.CezihFhirClient.post", fake_post)

    with pytest.raises(CezihFhirError) as exc_info:
        await getattr(fhir_documents, fhir_fn_name)(
            None,
            "CEZIH-REF-OLD",
            _fhir_patient_data(),
            _fhir_record_data(),
            djelatnost_code="2010000",
            djelatnost_display="Specijalistička ordinacija",
            original_document_oid="2.999.9.9",
        )

    outcome = exc_info.value.to_operation_outcome()
    assert outcome["code"] == "CEZIH_MISSING_REFERENCE_ID"
    assert "duplikat" in exc_info.value.message


# ---------------------------------------------------------------------------
# Visit-mirror validation: encounter ids CEZIH can't resolve fail fast,
# before the ~14 s signing round-trip
# ---------------------------------------------------------------------------


async def _add_visit_mirror(db_session, tenant_id: str, patient_id: str, cezih_visit_id: str, status: str):
    db_session.add(
        CezihVisit(
            tenant_id=tenant_id,
            patient_id=patient_id,
            patient_mbo="123456789",
            cezih_visit_id=cezih_visit_id,
            status=status,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_send_rejects_encounter_without_visit_mirror(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)

    calls = []

    async def tracking_send(*args, **kwargs):
        calls.append(args)
        return {"success": True, "reference_id": "R", "sent_at": "2026-10-06T12:00:00+00:00"}

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", tracking_send)

    resp = await client.post(
        "/api/cezih/e-nalaz",
        json={"patient_id": test_patient_id, "record_id": record_id, "encounter_id": "VIS-NOT-MIRRORED"},
        headers=auth_headers,
    )

    assert resp.status_code == 422, resp.text
    assert "posjeta nije registrirana" in resp.json()["detail"].lower()
    assert calls == [], "send must fail fast before any CEZIH call/signing"


@pytest.mark.asyncio
async def test_send_rejects_stornirana_visit_mirror(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    ctx = await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    await _add_visit_mirror(db_session, ctx["tenant_id"], test_patient_id, "VIS-EIE", "entered-in-error")

    calls = []

    async def tracking_send(*args, **kwargs):
        calls.append(args)
        return {"success": True, "reference_id": "R", "sent_at": "2026-10-06T12:00:00+00:00"}

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", tracking_send)

    resp = await client.post(
        "/api/cezih/e-nalaz",
        json={"patient_id": test_patient_id, "record_id": record_id, "encounter_id": "VIS-EIE"},
        headers=auth_headers,
    )

    assert resp.status_code == 422, resp.text
    assert "stornirana" in resp.json()["detail"].lower()
    assert calls == []


@pytest.mark.asyncio
async def test_send_accepts_finished_visit_mirror(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    """A finished visit is the normal state when writing a nalaz - must pass."""
    ctx = await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    await _add_visit_mirror(db_session, ctx["tenant_id"], test_patient_id, "VIS-DONE", "finished")

    async def ok_send(*args, **kwargs):
        return {"success": True, "reference_id": "CEZIH-REF-VIS", "sent_at": "2026-10-06T12:00:00+00:00"}

    monkeypatch.setattr("app.services.cezih.service.send_enalaz", ok_send)

    resp = await client.post(
        "/api/cezih/e-nalaz",
        json={"patient_id": test_patient_id, "record_id": record_id, "encounter_id": "VIS-DONE"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    record = await _get_record(db_session, record_id)
    assert record.cezih_sent is True
    assert record.cezih_encounter_id == "VIS-DONE"


# ---------------------------------------------------------------------------
# Edit-after-send guard: PATCH /medical-records must not diverge local content
# from the signed CEZIH document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_sent_record_rejected(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_sent = True
    record.cezih_reference_id = "CEZIH-REF-1"
    await db_session.commit()

    resp = await client.patch(
        f"/api/medical-records/{record_id}",
        json={"sadrzaj": "uređani sadržaj koji bi odstupao od potpisanog dokumenta"},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert "Uredi i zamijeni" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_stornoed_record_rejected(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session
):
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_sent = True
    record.cezih_storno = True
    await db_session.commit()

    resp = await client.patch(
        f"/api/medical-records/{record_id}",
        json={"sadrzaj": "uređani sadržaj"},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert "stornirani" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Replace-with-edit: visit validation on a NEW link + regression for the
# shared payload helpers (partial edits, ref/OID swap)
# ---------------------------------------------------------------------------


async def _sent_record_with_ref(client, auth_headers, test_patient_id, db_session) -> str:
    await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_sent = True
    record.cezih_reference_id = "CEZIH-REF-OLD"
    record.cezih_document_oid = "2.999.9.9"
    record.cezih_encounter_id = "VIS-ORIGINAL"
    await db_session.commit()
    return record_id


@pytest.mark.asyncio
async def test_replace_with_edit_rejects_unregistered_new_encounter(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    record_id = await _sent_record_with_ref(client, auth_headers, test_patient_id, db_session)

    calls = []

    async def tracking_replace(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr("app.services.cezih.service.replace_document", tracking_replace)

    resp = await client.put(
        "/api/cezih/e-nalaz/CEZIH-REF-OLD/replace-with-edit",
        json={
            "record_id": record_id,
            "patient_id": test_patient_id,
            "encounter_id": "VIS-BOGUS",
            "sadrzaj": "novi sadržaj zamjene",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 422, resp.text
    assert "posjeta nije registrirana" in resp.json()["detail"].lower()
    assert calls == []


@pytest.mark.asyncio
async def test_replace_with_edit_success_swaps_ref_and_applies_edits(
    client: AsyncClient, auth_headers: dict[str, str], test_patient_id: str, db_session, monkeypatch
):
    ctx = await _setup_sendable_tenant(client, auth_headers, db_session)
    record_id = await _create_record(client, auth_headers, test_patient_id)
    record = await _get_record(db_session, record_id)
    record.cezih_sent = True
    record.cezih_reference_id = "CEZIH-REF-OLD"
    record.cezih_document_oid = "2.999.9.9"
    record.cezih_encounter_id = "VIS-ORIGINAL"
    await db_session.commit()
    await _add_visit_mirror(db_session, ctx["tenant_id"], test_patient_id, "VIS-NEW", "in-progress")

    seen: dict = {}

    async def fake_replace(http_client, original_ref, patient_data, record_data, **kwargs):
        seen["original_ref"] = original_ref
        seen["patient_data"] = patient_data
        seen["record_data"] = record_data
        seen["encounter_id"] = kwargs.get("encounter_id")
        return {"success": True, "new_reference_id": "CEZIH-REF-NEW", "new_document_oid": "2.999.9.10"}

    monkeypatch.setattr("app.services.cezih.service.replace_document", fake_replace)

    resp = await client.put(
        "/api/cezih/e-nalaz/CEZIH-REF-OLD/replace-with-edit",
        json={
            "record_id": record_id,
            "patient_id": test_patient_id,
            "encounter_id": "VIS-NEW",
            "sadrzaj": "novi sadržaj zamjene",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    # Partial edit: only sadrzaj overridden, other fields keep record values.
    assert seen["record_data"]["sadrzaj"] == "novi sadržaj zamjene"
    assert seen["record_data"]["tip"] == "nalaz"
    assert "dijagnoza_mkb" in seen["record_data"]
    assert seen["patient_data"]["mbo"] == "123456789"
    assert seen["encounter_id"] == "VIS-NEW"

    record = await _get_record(db_session, record_id)
    assert record.cezih_reference_id == "CEZIH-REF-NEW"
    assert record.cezih_document_oid == "2.999.9.10"
    assert record.cezih_encounter_id == "VIS-NEW"
    assert record.sadrzaj == "novi sadržaj zamjene"
    assert record.cezih_last_replaced_at is not None

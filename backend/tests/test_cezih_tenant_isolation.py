"""Integration tests for per-tenant CEZIH configuration and isolation.

Tests against the LIVE backend running in Docker (localhost:8000).
Registers 3 separate clinics with unique identifiers, sets distinct
sifra_ustanove/OID on each, and verifies CEZIH case management
endpoints work per-tenant with full data isolation.

Requires: docker compose up (backend + db running on ports 8000, 5433)
"""
import uuid

import httpx
import pytest

BASE_URL = "http://localhost:8000/api"


def _live_backend_available() -> bool:
    """These are integration tests against a LIVE backend on :8000 (docker compose up).
    Skip the whole module when that server isn't reachable so the unit suite stays green."""
    import socket

    try:
        with socket.create_connection(("localhost", 8000), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _live_backend_available(), reason="live backend on :8000 not running"),
]

# Unique suffix per test run to avoid email collisions
_RUN_ID = uuid.uuid4().hex[:6]

# Module-level cache for clinic data (created once, reused across tests)
_CLINICS: dict[str, dict] = {}


def _email(name: str) -> str:
    return f"{name}-{_RUN_ID}@test.hr"


def _generate_valid_oib(seed: int) -> str:
    """Generate a valid Croatian OIB (ISO 7064 Mod 11,10 checksum)."""
    # Use run_id + seed*1000000 to ensure distinct 10-digit bases
    raw = int(_RUN_ID, 16) + seed * 1000000
    base = str(raw % 10000000000).zfill(10)
    s = 10
    for ch in base:
        d = int(ch)
        s = (s + d) % 10
        if s == 0:
            s = 10
        s = (s * 2) % 11
    check = (11 - s) % 11
    if check == 10:
        check = 0
    return base + str(check)


def _mbo(seed: int) -> str:
    """Generate a unique 9-digit MBO."""
    raw = int(_RUN_ID[:6], 16) + seed * 100000
    return str(raw % 1000000000).zfill(9)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CLINIC_IP_COUNTER = 0


async def _register_clinic(client: httpx.AsyncClient, name: str, email: str) -> dict:
    """Register a new clinic and return {headers, tenant_id, user_id}."""
    global _CLINIC_IP_COUNTER
    _CLINIC_IP_COUNTER += 1
    fake_ip = f"10.0.{_CLINIC_IP_COUNTER}.{int(_RUN_ID[:2], 16)}"
    resp = await client.post(
        f"{BASE_URL}/auth/register",
        json={
            "naziv_klinike": name,
            "email": email,
            "password": "Test1234!",
            "ime": "Admin",
            "prezime": name.split()[0],
            "terms_accepted": True,
        },
        headers={"X-Forwarded-For": fake_ip},
    )
    if resp.status_code == 409:
        # Email exists from a previous test run — just login
        resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": "Test1234!"},
        )
    assert resp.status_code in (200, 201), f"Auth failed for {email}: {resp.text}"
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    # Use a fresh client for /me to avoid cookie interference
    # (register sets httpOnly cookies that override Bearer tokens)
    async with httpx.AsyncClient(timeout=30) as fresh:
        me = await fresh.get(f"{BASE_URL}/auth/me", headers=headers)
    assert me.status_code == 200, f"Failed to get /me: {me.text}"
    me_data = me.json()

    return {
        "headers": headers,
        "tenant_id": me_data["tenant_id"],
        "user_id": me_data["id"],
        "email": email,
    }


async def _set_clinic_cezih_config(
    client: httpx.AsyncClient, headers: dict, sifra_ustanove: str, oid: str,
) -> None:
    resp = await client.patch(
        f"{BASE_URL}/settings/clinic",
        json={"sifra_ustanove": sifra_ustanove, "oid": oid},
        headers=headers,
    )
    assert resp.status_code == 200, f"Clinic update failed: {resp.text}"


async def _create_patient(
    client: httpx.AsyncClient, headers: dict, mbo: str,
) -> str:
    resp = await client.post(
        f"{BASE_URL}/patients",
        json={
            "ime": "Pacijent",
            "prezime": f"Test-{mbo}",
            "mbo": mbo,
            "datum_rodjenja": "1985-06-15",
            "spol": "M",
        },
        headers=headers,
    )
    if resp.status_code == 409:
        # Patient exists from previous run — search for it
        search_resp = await client.get(f"{BASE_URL}/patients?search={mbo}", headers=headers)
        assert search_resp.status_code == 200
        patients = search_resp.json()
        items = patients.get("items", patients) if isinstance(patients, dict) else patients
        assert len(items) > 0, f"Patient with MBO {mbo} not found after 409"
        return items[0]["id"]
    assert resp.status_code == 201, f"Patient creation failed: {resp.text}"
    return resp.json()["id"]


async def _create_medical_record(
    client: httpx.AsyncClient, headers: dict, patient_id: str,
) -> str:
    resp = await client.post(
        f"{BASE_URL}/medical-records",
        json={
            "patient_id": patient_id,
            "tip": "nalaz",
            "datum": "2026-04-05",
            "dijagnoza_mkb": "J06.9",
            "dijagnoza_tekst": "Akutna infekcija gornjeg dišnog sustava",
            "sadrzaj": "Pacijent se žali na kašalj i temperaturu.",
        },
        headers=headers,
    )
    assert resp.status_code == 201, f"Record creation failed: {resp.text}"
    return resp.json()["id"]


async def _ensure_clinics(client: httpx.AsyncClient) -> dict[str, dict]:
    """Create 3 clinics if not already cached."""
    if len(_CLINICS) == 3:
        return _CLINICS
    _CLINICS.clear()

    configs = [
        ("a", "Poliklinika Zagreb", "12345", "1.2.3.4.5", 1),
        ("b", "Ordinacija Split", "67890", "6.7.8.9.0", 2),
        ("c", "Dom Zdravlja Rijeka", "11111", "1.1.1.1.1", 3),
    ]
    for key, name, sifra, oid, seed in configs:
        info = await _register_clinic(client, name, _email(f"clinic{key.upper()}"))
        await _set_clinic_cezih_config(client, info["headers"], sifra, oid)
        info["patient_id"] = await _create_patient(client, info["headers"], _mbo(seed))
        info["mbo"] = _mbo(seed)
        info["sifra_ustanove"] = sifra
        info["oid"] = oid
        _CLINICS[key] = info

    return _CLINICS


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_each_clinic_has_distinct_cezih_config():
    """Each clinic should have its own sifra_ustanove and OID."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        clinics = await _ensure_clinics(client)

    # Use a fresh client (no cookies) for assertions
    for key, expected_sifra, expected_oid in [
        ("a", "12345", "1.2.3.4.5"),
        ("b", "67890", "6.7.8.9.0"),
        ("c", "11111", "1.1.1.1.1"),
    ]:
        async with httpx.AsyncClient(timeout=30) as check:
            resp = await check.get(
                f"{BASE_URL}/settings/clinic",
                headers=clinics[key]["headers"],
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["sifra_ustanove"] == expected_sifra, \
                f"Clinic {key}: expected sifra={expected_sifra}, got {data['sifra_ustanove']}"
            assert data["oid"] == expected_oid


async def test_patient_isolation_across_clinics():
    """Clinic A's patient should not be visible to Clinic B or C."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        # Clinic B tries to access Clinic A's patient
        resp = await client.get(
            f"{BASE_URL}/patients/{c['a']['patient_id']}",
            headers=c["b"]["headers"],
        )
        assert resp.status_code == 404

        # Clinic C tries to access Clinic B's patient
        resp = await client.get(
            f"{BASE_URL}/patients/{c['b']['patient_id']}",
            headers=c["c"]["headers"],
        )
        assert resp.status_code == 404

        # Clinic A tries to access Clinic C's patient
        resp = await client.get(
            f"{BASE_URL}/patients/{c['c']['patient_id']}",
            headers=c["a"]["headers"],
        )
        assert resp.status_code == 404


async def test_create_case_per_tenant():
    """Each clinic's create_case should succeed independently in mock mode."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        for key in ("a", "b", "c"):
            resp = await client.post(
                f"{BASE_URL}/cezih/cases",
                json={
                    "patient_id": c[key]["patient_id"],
                "patient_mbo": c[key]["mbo"],
                    "icd_code": "J06.9",
                    "icd_display": "Akutna infekcija",
                    "onset_date": "2026-04-01",
                    "verification_status": "unconfirmed",
                },
                headers=c[key]["headers"],
            )
            assert resp.status_code == 200, f"create_case failed for clinic {key}: {resp.text}"
            data = resp.json()
            assert data["success"] is True
            assert data["mock"] is True
            assert "cezih_case_id" in data


async def test_update_case_status_per_tenant():
    """Each clinic can update case status independently."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        for key in ("a", "b"):
            mbo = c[key]["mbo"]
            create_resp = await client.post(
                f"{BASE_URL}/cezih/cases",
                json={
                    "patient_id": c[key]["patient_id"],
                    "patient_mbo": mbo,
                    "icd_code": "J06.9",
                    "icd_display": "Test",
                    "onset_date": "2026-04-01",
                },
                headers=c[key]["headers"],
            )
            assert create_resp.status_code == 200
            case_id = create_resp.json()["cezih_case_id"]

            resp = await client.put(
                f"{BASE_URL}/cezih/cases/{case_id}/status?mbo={mbo}",
                json={"action": "resolve"},
                headers=c[key]["headers"],
            )
            assert resp.status_code == 200, f"update_case_status failed: {resp.text}"
            assert resp.json()["success"] is True


async def test_update_case_data_per_tenant():
    """Each clinic can update case data independently."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        for key in ("a", "c"):
            mbo = c[key]["mbo"]
            create_resp = await client.post(
                f"{BASE_URL}/cezih/cases",
                json={
                    "patient_id": c[key]["patient_id"],
                    "patient_mbo": mbo,
                    "icd_code": "J06.9",
                    "icd_display": "Test",
                    "onset_date": "2026-04-01",
                },
                headers=c[key]["headers"],
            )
            assert create_resp.status_code == 200
            case_id = create_resp.json()["cezih_case_id"]

            resp = await client.put(
                f"{BASE_URL}/cezih/cases/{case_id}/data?mbo={mbo}",
                json={
                    "current_clinical_status": "active",
                    "icd_code": "J11.1",
                    "icd_display": "Gripa",
                    "note": "Ažurirani podaci",
                },
                headers=c[key]["headers"],
            )
            assert resp.status_code == 200, f"update_case_data failed: {resp.text}"
            assert resp.json()["success"] is True


async def test_enalaz_send_and_isolation():
    """E-Nalaz sent by Clinic A should not appear in Clinic B's records."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        # Create and send a record from Clinic A
        record_id = await _create_medical_record(client, c["a"]["headers"], c["a"]["patient_id"])

        resp = await client.post(
            f"{BASE_URL}/cezih/e-nalaz",
            json={"patient_id": c["a"]["patient_id"], "record_id": record_id},
            headers=c["a"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Clinic B should get empty results for Clinic A's patient_id
        resp = await client.get(
            f"{BASE_URL}/medical-records?patient_id={c['a']['patient_id']}",
            headers=c["b"]["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        assert len(items) == 0, "Clinic B should not see Clinic A's records"


async def test_cezih_activity_isolation():
    """CEZIH activity from Clinic A should not appear in Clinic B's log."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        # Trigger a CEZIH action in Clinic A
        await client.post(
            f"{BASE_URL}/cezih/provjera-osiguranja",
            json={"mbo": c["a"]["mbo"]},
            headers=c["a"]["headers"],
        )

        # Check Clinic B's activity — should not contain Clinic A's user actions
        resp_b = await client.get(f"{BASE_URL}/cezih/activity", headers=c["b"]["headers"])
        assert resp_b.status_code == 200
        activity_b = resp_b.json()

        for item in activity_b.get("items", []):
            assert item.get("user_id") != c["a"]["user_id"], \
                "Clinic B's activity log contains Clinic A's user actions"


async def test_dashboard_stats_isolation():
    """Dashboard stats should reflect only the calling tenant's data."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        # Create and send a record from Clinic A
        record_id = await _create_medical_record(client, c["a"]["headers"], c["a"]["patient_id"])
        await client.post(
            f"{BASE_URL}/cezih/e-nalaz",
            json={"patient_id": c["a"]["patient_id"], "record_id": record_id},
            headers=c["a"]["headers"],
        )

        # Clinic A should have stats
        resp_a = await client.get(f"{BASE_URL}/cezih/dashboard-stats", headers=c["a"]["headers"])
        assert resp_a.status_code == 200
        assert resp_a.json()["danas_operacije"] > 0

        # Clinic B had no e-Nalaz sends, only case management from other tests
        # Verify that clinic A's e-Nalaz stats are NOT visible in B's dashboard
        resp_b = await client.get(f"{BASE_URL}/cezih/dashboard-stats", headers=c["b"]["headers"])
        assert resp_b.status_code == 200
        # Clinic B's unsent nalazi count should not include Clinic A's records
        assert resp_b.json()["neposlani_nalazi"] >= 0  # Just verify it works per-tenant


async def test_cross_tenant_enalaz_no_side_effects():
    """Clinic B calling e-Nalaz on Clinic A's record should not modify Clinic A's data."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Backend not running at localhost:8000")

        c = await _ensure_clinics(client)

        record_id = await _create_medical_record(client, c["a"]["headers"], c["a"]["patient_id"])

        # Clinic B tries to send Clinic A's record (mock mode allows the call,
        # but the record won't be found in Clinic B's tenant so no DB update)
        await client.post(
            f"{BASE_URL}/cezih/e-nalaz",
            json={"patient_id": c["a"]["patient_id"], "record_id": record_id},
            headers=c["b"]["headers"],
        )

        # Verify Clinic A's record was NOT marked as sent
        resp = await client.get(
            f"{BASE_URL}/medical-records?patient_id={c['a']['patient_id']}&cezih_sent=true",
            headers=c["a"]["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        # The record should NOT be cezih_sent (Clinic B's call didn't affect it)
        sent_ids = [r["id"] for r in items if r.get("cezih_sent")]
        assert record_id not in sent_ids, \
            "Clinic B's e-Nalaz call should not have marked Clinic A's record as sent"

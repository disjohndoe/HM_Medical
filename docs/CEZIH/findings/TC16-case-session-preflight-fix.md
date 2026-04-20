---
date: 2026-04-20
topic: session | case-lifecycle | health-issue-services
status: resolved
related: TC11-PMIR-auth-blocker.md
---

# TC16 case create via extsigner — RESOLVED (2026-04-20)

**Result:** TC16 returns 200 from `health-issue-services/api/v1/$process-message` for both signing methods. Case `cmo75rsp4020chb85g10k5bv0` (J00) created live on `app.hmdigital.hr`.

Extension of the TC11 pattern — CEZIH's gateway establishes session cookies **per service-domain**, so every POST-first path on a cold domain needs its own pre-flight GET.

## Symptom

- 2026-04-20: `POST health-issue-services/$process-message` → `ERR_DS_1002` with `code: "business-rule"` when signed via Certilia mobile (extsigner on `certpubws.cezih.hr:8443`).
- Same user, same bundle, smartcard path (`certws2.cezih.hr:8443`) → 200.
- TC10 / TC12 / TC13 / TC14 via extsigner same session → 200.
- TC16 bundle structure identical to what succeeded earlier via smartcard — NOT a profile/body problem.

## Root cause

Same as TC11 Issue 1, on a different service-domain.

CEZIH's gateway sets session cookies **per service-domain**, not per user:

| Service | Cookie scope |
|---|---|
| `patient-registry-services` | independent |
| `encounter-services` | independent |
| `health-issue-services` | independent |
| `ihe-qedm-services` | independent |

Extsigner users on `certpubws` hit the gateway "cold" for each new service. Flow when the first request to a cold domain is a POST:

1. `POST health-issue-services/$process-message` (Content-Type: application/fhir+json)
2. Gateway → 302 to Keycloak
3. POST body forwarded to Keycloak (agent has `CURLOPT_POSTREDIR` via Rust client, Python httpx also follows 302 with body when explicitly told to)
4. Keycloak rejects `application/fhir+json` → 415
5. Session cookie never set. CEZIH surfaces as `ERR_DS_1002`.

Smartcard users don't hit this because `agent_ws.py` warms up `patient-registry-services` on connect AND the smart card path cross-domain cookies appear to share. Extsigner path has no such warmup for `health-issue-services`.

**`fhir_api/condition.py` had no pre-flight GET on any of its four entry points** (`create_case`, `create_recurring_case`, `update_case`, `update_case_data`). This was the missing fix.

## Fix

Mirror the `fhir_api/pmir.py:131-144` pattern in `fhir_api/condition.py` with a bare `?_count=0` GET. QEDm rejects this with 400 "Missing mandatory parameter 'patient'" — but the 400 still goes through Keycloak and sets the session cookie, so the subsequent POST to `health-issue-services` succeeds.

```python
async def _ensure_case_session(fhir_client: CezihFhirClient) -> None:
    """Pre-flight GET before POST to health-issue-services.

    CEZIH's gateway establishes session cookies per service-domain.
    A GET goes through the Keycloak redirect cleanly (no body) and sets the cookie.
    A POST body gets rejected by Keycloak (415) and the cookie is never set.
    """
    try:
        await fhir_client.get(
            "ihe-qedm-services/api/v1/Condition",
            params={"_count": "0"},
            timeout=10,
        )
        logger.info("Case: gateway session established via pre-flight GET")
    except CezihError as e:
        logger.warning("Case: pre-flight GET failed (%s), POST may also fail", str(e)[:100])
```

Called before each `fhir_client.process_message("health-issue-services/api/v1", bundle)` — 4 sites total.

Commits:
- `b602342` — initial pre-flight fix (bare `?_count=0`, 400 response, cookie still set) — VERIFIED
- `5e4ca23` — attempted refinement to valid `patient.identifier=MBO|xxx&_count=0` for clean 200 — **REGRESSED** (see rollback below)
- rollback 2026-04-20 — restored bare `?_count=0`

## Verification (live prod, 2026-04-20 12:15 UTC)

Server log sequence for a TC16 create via the now-fixed path:

```
12:15:43  GET  ihe-qedm-services/api/v1/Condition?_count=0 → 400 (135ms)
12:15:43  WARNING Case: pre-flight GET failed (Missing mandatory parameter "patient" in the query.)
12:15:43  POST health-issue-services/api/v1/$process-message → 200 (1656ms)
```

UI: toast "Slučaj kreiran: cmo75rsp4020chb85g10k5bv0". New row visible at top of Slučajevi table.

## Why the pre-flight returns 400, not 200 (and why that's the right tradeoff)

QEDm's `Condition` search requires `patient` (or `patient.identifier`) — a bare `?_count=0` is rejected with 400 by the FHIR service. **The 400 is returned AFTER going through Keycloak and the gateway**, so the cookie still gets set and the POST succeeds. The downside is misleading noise in logs/metrics.

The obvious "cleanup" is to supply the known patient MBO so the pre-flight returns a clean 200:

```python
params={"patient.identifier": f"{ID_MBO}|{patient_mbo}", "_count": "0"}
```

**We tried this in commit `5e4ca23` — it regressed the flow.** CEZIH's HAPI interprets `patient.identifier` as a chained search (`patient:Patient.identifier`) and forwards to its internal upstream at `http://localhost:8080/fhir/...`. That upstream is broken in the test env (`NoHttpResponseException: localhost:8080 failed to respond`), so the pre-flight returns **500**, not 200.

Empirically — and this is the non-obvious bit — **a 500 does NOT warm the session cookie the way a 400 does.** The subsequent POST to `health-issue-services/$process-message` then fails with `ERR_DS_1002 / code: "business-rule"`, no diagnostics. Probably the 500 short-circuits somewhere in the gateway pipeline before the Set-Cookie is issued; the 400 (which is a real FHIR-service OperationOutcome) completes the pipeline.

Observed live on prod 2026-04-20 12:38 UTC:
```
GET  Condition?patient.identifier=MBO|999999476&_count=0 → 500 (HAPI-1361 upstream)
POST health-issue-services/$process-message              → 400 ERR_DS_1002
```

Rolled back immediately.

**PMIR's pre-flight** uses `patient-registry-services/api/v1/Patient?_count=0` which returns 200 naturally because Patient search is less restrictive — and PMIR is for foreigners who don't yet have a patient record, so there's no MBO to pass anyway.

**Rules for future services:**
1. When adding a pre-flight GET on a new service-domain, don't assume "valid query = better." Test it. CEZIH test-env HAPI has broken upstream chained-search for at least the Condition endpoint.
2. A noisy-but-working 400 from the FHIR service beats a clean 500 that bypasses cookie-setting. Optimize for the POST working, not for clean logs.
3. If you must silence the 400 for metrics, silence it at the log layer — don't rewrite the query.

## Lessons

1. **The TC11 pattern applies to every new service-domain you POST to.** If you add a new CEZIH POST endpoint that isn't preceded by a GET, you'll re-hit this. Before calling `$process-message` / `POST` on any cold service path, run a throwaway GET on that service-domain first.

2. **`ERR_DS_1002 code=business-rule` is overloaded.** We've now seen it for: missing Encounter.type slices (encounters), wrong signature algorithm (PMIR), and cold-domain Keycloak rejection (case create). First triage step: grep backend logs for `/auth/realms/CEZIH/` in the OperationOutcome `path` — that's the session-establishment signal. If absent, look at bundle structure / signing method next.

3. **Symmetric fix to TC11.** The code shape is literally the same helper with a different URL. Any future case-like POST-first service (e.g., a new immunization-services, prescription-services) is probably going to need the same thing. Consider factoring into a single helper that takes the service base URL if this happens a third time.

## Files changed

| File | Change |
|---|---|
| `backend/app/services/cezih/fhir_api/condition.py` | Added `_ensure_case_session()`; called before all 4 `process_message` sites (create, create_recurring, update, update_data) |

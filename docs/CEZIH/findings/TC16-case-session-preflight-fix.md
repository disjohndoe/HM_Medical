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

Mirror the `fhir_api/pmir.py:131-144` pattern in `fhir_api/condition.py`, with one refinement: use a **valid** Condition search (patient-scoped) so the pre-flight returns 200 instead of a noisy 400.

```python
async def _ensure_case_session(
    fhir_client: CezihFhirClient,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
) -> None:
    """Pre-flight GET before POST to health-issue-services.

    CEZIH's gateway establishes session cookies per service-domain.
    A GET goes through the Keycloak redirect cleanly (no body) and sets the cookie.
    A POST body gets rejected by Keycloak (415) and the cookie is never set.

    QEDm requires `patient` (or `patient.identifier`) — passing the known MBO
    yields 200 with an empty Bundle. A bare `?_count=0` also warms the cookie
    but returns 400, which pollutes logs and metrics.
    """
    try:
        await fhir_client.get(
            "ihe-qedm-services/api/v1/Condition",
            params={
                "patient.identifier": f"{identifier_system}|{patient_mbo}",
                "_count": "0",
            },
            timeout=10,
        )
        logger.info("Case: gateway session established via pre-flight GET")
    except CezihError as e:
        logger.warning("Case: pre-flight GET failed (%s), POST may also fail", str(e)[:100])
```

Called before each `fhir_client.process_message("health-issue-services/api/v1", bundle)` — 4 sites total. All four entry points (`create_case`, `create_recurring_case`, `update_case`, `update_case_data`) already have `patient_mbo` in scope, so threading it through is free.

Commits:
- `b602342` — initial pre-flight fix (bare `?_count=0`, 400 response, cookie still set)
- follow-up 2026-04-20 — patient-scoped search, 200 response, no log noise

## Verification (live prod, 2026-04-20 12:15 UTC)

Server log sequence for a TC16 create via the now-fixed path:

```
12:15:43  GET  ihe-qedm-services/api/v1/Condition?_count=0 → 400 (135ms)
12:15:43  WARNING Case: pre-flight GET failed (Missing mandatory parameter "patient" in the query.)
12:15:43  POST health-issue-services/api/v1/$process-message → 200 (1656ms)
```

UI: toast "Slučaj kreiran: cmo75rsp4020chb85g10k5bv0". New row visible at top of Slučajevi table.

## Nuance: pre-flight endpoint must be hit carefully per service

QEDm's `Condition` search requires `patient` (or `patient.identifier`) — a bare `?_count=0` is rejected with 400 by the FHIR service. **The 400 is returned AFTER going through Keycloak and the gateway**, so the cookie still gets set and the POST succeeds — but it leaves a misleading error trail in logs and metrics.

Since the call sites all have the patient MBO at hand, the cleaner pattern is to submit a valid patient-scoped search and get 200. Same session-warming behavior, no log noise, and as a bonus the response could be used for pre-submit duplicate detection later.

PMIR's pre-flight uses `patient-registry-services/api/v1/Patient?_count=0` which returns 200 naturally because Patient search is less restrictive — so no MBO threading needed there (and PMIR is specifically for patients who don't yet have one).

**Rule for future services:** when adding a pre-flight GET on a new service-domain, spend 30 seconds checking whether the FHIR search has mandatory params. If yes, supply a valid value — don't rely on "400 still sets the cookie" behavior.

## Lessons

1. **The TC11 pattern applies to every new service-domain you POST to.** If you add a new CEZIH POST endpoint that isn't preceded by a GET, you'll re-hit this. Before calling `$process-message` / `POST` on any cold service path, run a throwaway GET on that service-domain first.

2. **`ERR_DS_1002 code=business-rule` is overloaded.** We've now seen it for: missing Encounter.type slices (encounters), wrong signature algorithm (PMIR), and cold-domain Keycloak rejection (case create). First triage step: grep backend logs for `/auth/realms/CEZIH/` in the OperationOutcome `path` — that's the session-establishment signal. If absent, look at bundle structure / signing method next.

3. **Symmetric fix to TC11.** The code shape is literally the same helper with a different URL. Any future case-like POST-first service (e.g., a new immunization-services, prescription-services) is probably going to need the same thing. Consider factoring into a single helper that takes the service base URL if this happens a third time.

## Files changed

| File | Change |
|---|---|
| `backend/app/services/cezih/fhir_api/condition.py` | Added `_ensure_case_session()`; called before all 4 `process_message` sites (create, create_recurring, update, update_data) |

---
date: 2026-04-13
topic: endpoints | auth | errors | profiles | bundle-format | session
status: active
---

# TC11 PMIR ITI-93 — Investigation Log

## Current Status: Root cause found — session establishment bug (FIXED)

The 415 ERR_EHE_1099 was NOT a bundle format issue. The `"path"` field in the error
response (`/auth/realms/CEZIH/protocol/openid-connect/auth`) proved the request
was hitting Keycloak, never reaching the FHIR service.

## Root Cause (2026-04-13 — second investigation)

**The PMIR POST was the first gateway request without a session cookie.**

The auth flow on certws2:8443 (Apache mod_auth_openidc):
1. Request → no session cookie → 302 redirect to Keycloak auth
2. For GET: Keycloak mTLS auto-auth → 302 back → session cookie set → success
3. For POST: `CURLOPT_POSTREDIR=redirect_all` sends POST to Keycloak with
   `Content-Type: application/fhir+json` body → Keycloak rejects → **415**
4. Session cookie is NEVER set because the auth flow never completes
5. Agent retry also fails (no cookie → same redirect → same 415)

**Why other TCs work:** They always happen after a GET request (e.g., TC10 patient
lookup) has already established the session. The GET goes through Keycloak cleanly.

**Why warmup didn't help:** Warmup URL was `certws2:8443/metadata` which is NOT
behind the gateway auth — it only triggered the TLS handshake for PIN caching.

### Fixes Applied

1. **Backend warmup URL** (`agent_ws.py`): Changed from `/metadata` to
   `gateway/patient-registry-services/api/v1/Patient?_count=0` — this triggers
   the full Keycloak auth flow and establishes the session cookie on agent connect.

2. **Pre-flight GET** (`service.py`): Added GET to `patient-registry-services`
   before the PMIR POST — ensures session cookie is established even if the
   warmup didn't run or the session expired.

3. **Agent retry fix** (`websocket.rs`): When POST fails with Keycloak redirect,
   the agent now does a GET warmup first to establish the session, then retries
   the POST. Previously it just retried the POST immediately (same failure).

## Endpoint (confirmed from 2 CEZIH URL lists + internal example)

`POST https://certws2.cezih.hr:8443/services-router/gateway/patient-registry-services/api/iti93`

## Bundle Structure (matches official Simplifier example)

Bundle rebuilt in prior session to match `Bundle-register-patient-example.json`
from cezih.hr.cezih-osnova v1.0.1:
- Outer Bundle: meta.profile=HRRegisterPatient, type=message, plain UUID fullUrls
- MessageHeader: meta.profile=IHE.PMIR.MessageHeader, eventUri=patient-feed
- Inner Bundle: meta.profile=IHE.PMIR.Bundle.History, type=history
- Patient: urn:uuid: fullUrl, identifiers (putovnica+europska-kartica), address.country
- Digital signature: REQUIRED (min=1), JWS via smart card (ES384)

## Previous Attempts (all before session fix)

| Attempt | Content-Type | Result | Diagnosis |
|---------|-------------|--------|-----------|
| All variations of bundle format | application/fhir+json | 415 ERR_EHE_1099 | Keycloak, not FHIR service |
| With/without profiles | application/fhir+json | 415 ERR_EHE_1099 | Same — session issue |
| 3 endpoint URLs | application/fhir+json | All 415 | Same root cause |
| Raw Patient | application/json | 401 HTML | Keycloak login page |

## Ready for E2E test

With the session establishment fix, the POST should now reach the actual FHIR
service. If there are bundle format issues, we'll get a proper FHIR
OperationOutcome error instead of the generic 415 from Keycloak.

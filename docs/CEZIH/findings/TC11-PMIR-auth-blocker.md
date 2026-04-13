---
date: 2026-04-13
topic: endpoints | auth | errors
status: active
---

# TC11 PMIR ITI-93 — Auth Blocker

## Discovery

The PMIR endpoint (`patient-registry-services/api/iti93`) on port 8443 returns different errors
depending on Content-Type:

- `Content-Type: application/fhir+json` → HTTP 415 ERR_EHE_1099 (plain text, no FHIR OperationOutcome)
- `Content-Type: application/json` → HTTP 401 HTML page ("Cezih - greška 401")

The 401 response is CEZIH's web application HTML login page — NOT a REST API JSON error.
This is different from all other port-8443 endpoints that accept the service account Bearer token.

## Evidence

- URL confirmed from two CEZIH URL lists: `https://certws2.cezih.hr:8443/services-router/gateway/patient-registry-services/api/iti93`
- bundle has correct `meta.profile: HRRegisterPatient`
- Same Bearer token works for TC12-18 (encounter-services, health-issue-services, doc-mhd-svc)
- 401 HTML from CEZIH web app, not FHIR OperationOutcome

## Possible Causes

1. PMIR endpoint not enabled for test institution 999001464 (most likely)
2. Service account doesn't have PMIR scope in Keycloak
3. PMIR requires practitioner-level OAuth2 token (not just service account)
4. Endpoint uses different auth mechanism (form-based/cookie session)

## Action Items

Contact HZZO helpdesk (`helpdesk@hzzo.hr`) with:
1. Is PMIR/ITI-93 enabled for test institution 999001464?
2. Does the endpoint require a different OAuth2 scope than clinical services?
3. What auth mechanism does `patient-registry-services/api/iti93` use?

Ask for: example of a successful TC11 request to compare.

## Code Status

Bundle structure is correct per HRRegisterPatient v1.0.1 profile.
Auth is the only remaining blocker.

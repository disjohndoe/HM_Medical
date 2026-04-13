---
date: 2026-04-13
topic: endpoints | auth | errors | profiles
status: active
---

# TC11 PMIR ITI-93 — Investigation Log

## Current Status: 415 ERR_EHE_1099 (bundle format rejected)

The endpoint DOES accept our auth token (not a permission issue) — the 415 means
our FHIR bundle structure is rejected by CEZIH's gateway validator.

## Endpoint (confirmed from 2 CEZIH URL lists)

`POST https://certws2.cezih.hr:8443/services-router/gateway/patient-registry-services/api/iti93`

## What We've Tried (2026-04-13)

| Attempt | Content-Type | Body | Result |
|---------|-------------|------|--------|
| IHE PMIR message bundle | application/fhir+json | Bundle(message) + MessageHeader + Bundle(history) + Patient | 415 ERR_EHE_1099 |
| Same with HRRegisterPatient profile | application/fhir+json | meta.profile = cezih.hr v1.0.1 | 415 ERR_EHE_1099 |
| Same with IHE.PMIR.Bundle profile | application/fhir+json | meta.profile = IHE base | 415 ERR_EHE_1099 |
| Same with NO meta.profile | application/fhir+json | No profiles on any resource | 415 ERR_EHE_1099 |
| $process-message | application/fhir+json | patient-registry-services/api/v1/$process-message | 415 ERR_EHE_1099 |
| Raw Patient resource | application/json | Just the Patient resource | 401 HTML login page |
| Raw Patient resource | application/fhir+json | Just the Patient resource | 415 ERR_EHE_1099 |

## Key Observations

1. **415 = reaches CEZIH FHIR layer** — auth is working, bundle structure is wrong
2. **401 = gateway rejection** — happens only with `application/json` (non-FHIR)
3. **ERR_EHE_1099 is plain text** — no FHIR OperationOutcome, no detailed error
4. **Same error code as TC19** — External v1.0.1 profiles rejected with ERR_EHE_1099
5. **All profile variations fail** — not a profile issue, something else is wrong

## Simplifier Profile Analysis (cezih.hr.cezih-osnova v1.0.1)

HRRegisterPatient structure:
- Outer Bundle(message) with signature(min=1)
- entry[PMIRMessageHeaderEntry]: sender(hr-organizacija) + author(hr-practitioner)  
- entry[PMIRBundleHistoryEntry]: Bundle(history) with Patient
- Patient identifiers: europskaKartica + putovnica (rules=closed, max=2)
- address.country binding=ValueSet/drzave (required)

Also found PMIRBundleInternal — simpler structure (standard Bundle, not IHE nesting).
May be the format the endpoint actually expects.

## Next Steps to Try

1. Check if endpoint expects `pat-mhd-svc/api/v1/pmir-service` instead of `patient-registry-services/api/iti93`
2. Try PMIRBundleInternal structure (type=message, 2 entries: MessageHeaderInternal + History)
3. Get full HTTP response body (not just status) — currently only getting error code string
4. Check CEZIH workshop recordings (05.12.2025, 19.03.2026) for PMIR examples
5. Ask at exam — examiner may provide the correct bundle format

## Code Status

Bundle structure matches HRRegisterPatient profile v1.0.1.
Identifier systems correct (europska-kartica, putovnica).
Current code: tries bundle POST, falls back to raw Patient POST.

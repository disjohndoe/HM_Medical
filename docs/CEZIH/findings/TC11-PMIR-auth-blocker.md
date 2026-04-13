---
date: 2026-04-13
topic: endpoints | auth | errors | profiles | bundle-format
status: active
---

# TC11 PMIR ITI-93 — Investigation Log

## Current Status: Rebuilt to match official Simplifier example

Previous 415 ERR_EHE_1099 errors were likely caused by bundle format mismatch
against the HRRegisterPatient profile. The bundle has been rebuilt to exactly match
`Bundle-register-patient-example.json` from cezih.hr.cezih-osnova v1.0.1.

## Endpoint (confirmed from 2 CEZIH URL lists)

`POST https://certws2.cezih.hr:8443/services-router/gateway/patient-registry-services/api/iti93`

## Root Cause Analysis (2026-04-13)

Previous investigation assumed 415 = "CEZIH gateway routing issue". Re-analysis found
multiple code issues when comparing our bundle against the official Simplifier example:

### Issues Found and Fixed

1. **Missing meta.profiles on ALL resources** — The official example sets profiles on
   outer Bundle (HRRegisterPatient), MessageHeader (IHE.PMIR.MessageHeader), AND
   inner Bundle (IHE.PMIR.Bundle.History). Previous tests only tried one profile
   at a time, never the correct combination of all three.

2. **Placeholder signature** — If signing failed, code fell back to `"data": "placeholder"`
   instead of failing the request. The HRRegisterPatient profile requires `signature.data min=1`
   with actual JWS data. A "placeholder" string is not valid. Visit/case signing has no such
   fallback — it fails hard if signing fails. Fixed: removed try/except fallback.

3. **Wrong fullUrl format on outer entries** — Official example uses plain UUIDs for outer
   Bundle entries but `urn:uuid:` for inner Patient entry. Our code used `urn:uuid:` everywhere.
   Fixed: outer entries now use plain UUIDs, inner Patient keeps `urn:uuid:`.

4. **Missing focus reference format** — Focus reference should be plain UUID matching
   the inner bundle's fullUrl. Our code used `urn:uuid:` prefix.
   Fixed: plain UUID reference matching plain UUID fullUrl.

5. **Missing Bundle.id** — Official example has an `id` field on the outer Bundle.
   Our code omitted it. Fixed: added UUID as id.

### Previous Attempts (all failed — before fix)

| Attempt | Content-Type | Body | Result |
|---------|-------------|------|--------|
| IHE PMIR message bundle | application/fhir+json | Bundle(message) + MessageHeader + Bundle(history) + Patient | 415 ERR_EHE_1099 |
| Same with HRRegisterPatient profile | application/fhir+json | meta.profile = cezih.hr v1.0.1 (outer only) | 415 ERR_EHE_1099 |
| Same with IHE.PMIR.Bundle profile | application/fhir+json | meta.profile = IHE base (outer only) | 415 ERR_EHE_1099 |
| Same with NO meta.profile | application/fhir+json | No profiles on any resource | 415 ERR_EHE_1099 |
| $process-message | application/fhir+json | patient-registry-services/api/v1/$process-message | 415 ERR_EHE_1099 |
| Raw Patient resource | application/json | Just the Patient resource | 401 HTML login page |
| Raw Patient resource | application/fhir+json | Just the Patient resource | 415 ERR_EHE_1099 |

## Key Insights

1. **415 response "path" field** — Points to `/auth/realms/CEZIH/...` which is Keycloak's
   authorization endpoint. The agent follows HTTP redirects; when the CEZIH gateway
   can't validate the PMIR bundle format, it may redirect to Keycloak, and Keycloak
   returns 415 for `application/fhir+json` content type.

2. **Previous tests never matched the official example** — Each attempt changed ONE thing
   while the bundle had MULTIPLE structural differences from the required format.

## Official Example Structure (from Simplifier v1.0.1)

```json
{
  "resourceType": "Bundle",
  "id": "register-patient-example",
  "meta": {"profile": ["...StructureDefinition/HRRegisterPatient"]},
  "type": "message",
  "timestamp": "...",
  "entry": [
    {
      "fullUrl": "plain-uuid-1",           // <-- PLAIN UUID, no urn:uuid:
      "resource": {
        "resourceType": "MessageHeader",
        "meta": {"profile": ["...IHE.PMIR.MessageHeader"]},
        "eventUri": "urn:ihe:iti:pmir:2019:patient-feed",
        "focus": [{"reference": "plain-uuid-2"}]  // <-- matches inner bundle fullUrl
      }
    },
    {
      "fullUrl": "plain-uuid-2",           // <-- PLAIN UUID, no urn:uuid:
      "resource": {
        "resourceType": "Bundle",
        "meta": {"profile": ["...IHE.PMIR.Bundle.History"]},
        "type": "history",
        "entry": [{
          "fullUrl": "urn:uuid:...",       // <-- HAS urn:uuid: prefix
          "resource": {"resourceType": "Patient", ...},
          "request": {"method": "POST", "url": "Patient"},
          "response": {"status": "201"}
        }]
      }
    }
  ],
  "signature": {
    "type": [{"system": "urn:iso-astm:E1762-95:2013", "code": "1.2.840.10065.1.12.1.1"}],
    "when": "...",
    "who": {"type": "Practitioner", "identifier": {"system": "...HZJZ-...", "value": "..."}},
    "data": "real-base64-jws-signature"
  }
}
```

## Code Status

Bundle rebuilt to exactly match official example. Signature now fails hard (no placeholder).
Ready for E2E test.

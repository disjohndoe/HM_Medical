---
date: 2026-04-20
topic: endpoints
status: resolved
---

# CEZIH test env internal FHIR server intermittently down (ERR_DOCTRANSVAL_1000) — RESOLVED 2026-04-21

## Resolution — 2026-04-21

CEZIH's internal FHIR server (`localhost:8080` on their side) is back up.
Retry on TC20 storno against the same patient + environment now returns a
proper FHIR `OperationOutcome` in 2994.6ms instead of the
`NoHttpResponseException` stack trace. OID→DocumentReference lookup is
working again.

**Verification (2026-04-21 06:46 UTC, patient GORAN PACPRIVATNICI19):**
- DELETE `/api/cezih/e-nalaz/1401554` → `400` with
  `ERR_DOM_10035` "Target resource is not in valid status." — a
  well-formed CEZIH state-machine response, proving the OID lookup
  succeeded and CEZIH is evaluating the resource normally.
- This is NOT a recurrence of ERR_DOCTRANSVAL_1000. The infrastructure
  issue is closed.

**Secondary observation (NOT a blocker for TC20 as a capability):**
Ref 1401554 specifically cannot be cancelled now because after yesterday's
failed retries it appears to have been marked in a state that CEZIH
considers non-cancellable on their end. A fresh send→storno cycle on a new
nalaz is the correct way to verify the TC20 code path end-to-end; the
historical verification from 2026-04-13 (see `TC20-cancel-document-blocker.md`)
remains authoritative for the code path itself.

## Discovery

During E2E testing 2026-04-20 (mobile signing only, patient GORAN PACPRIVATNICI19),
TC20 (Storno nalaz) consistently failed with ERR_DOCTRANSVAL_1000 on multiple retries.

Error shown to the user (full server response):

```
Greška na CEZIH-u, pokušajte ponovno
Kod: ERR_DOCTRANSVAL_1000
Failed to parse response from server when performing GET to URL
http://localhost:8080/fhir/DocumentReference
  ?identifier=urn%3Aoid%3A2.16.840.1.113883.2.7.50.2.1.746528
  &status=current
  &_include%3Aiterate=DocumentReference%3Arelatesto%3ADocumentReference
- org.apache.http.NoHttpResponseException: localhost:8080 failed to respond
```

`localhost:8080` is on CEZIH's side. They proxy the OID→DocumentReference lookup
to an internal FHIR server, and that internal server is not responding in the
test environment right now.

## Evidence

- TC18 (Pošalji) and TC19 (Zamijeni) both succeeded on the same nalaz minutes
  earlier (Ref 1400821 → 1400853). Our signing, mTLS, and extsigner path are
  all working.
- Three consecutive TC20 storno attempts all failed with the exact same error
  body — consistent, not a one-off timeout on our side.
- Historical finding `TC20-cancel-document-blocker.md` (2026-04-13): TC20 was
  previously VERIFIED working end-to-end with ITI-65 replace + OID lookup. The
  code path is known-good.

## Impact

- TC20 is transiently blocked by the CEZIH test environment itself, not our
  code. We cannot make progress on storno until CEZIH operators bring their
  internal FHIR server back up.
- If this persists on the morning of the exam (2026-04-21), tell the examiner:
  *"TC20 code path is verified (see finding 2026-04-13), but CEZIH's internal
  FHIR lookup for OID resolution is currently returning NoHttpResponseException.
  Expected to recover."* Point them at the ERR_DOCTRANSVAL_1000 response text
  — it's CEZIH's own stack trace, not ours.

## Action Items

- [x] No code change needed on our side.
- [x] Re-check TC20 on 2026-04-21 — CEZIH is back up (verified 06:46 UTC).
      Infrastructure issue closed.
- [x] If still down during exam — N/A, infrastructure recovered.
- [ ] Optional: fresh TC18→TC20 cycle (send a new nalaz, then storno it)
      to reconfirm TC20 end-to-end on the current env. Historical
      verification from 2026-04-13 (`TC20-cancel-document-blocker.md`)
      still stands; this would just be belt-and-braces before any exam.

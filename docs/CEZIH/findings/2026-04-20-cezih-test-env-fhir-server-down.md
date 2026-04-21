---
date: 2026-04-20
topic: endpoints
status: resolved
---

# CEZIH test env internal FHIR server intermittent (ERR_DOCTRANSVAL_1000) — TC20 re-verified on fresh nalaz 2026-04-21

## Resolution — 2026-04-21

TC20 re-verified end-to-end via a fresh TC18→TC20 cycle on the prod app
against the real CEZIH test env:

| Time (UTC) | Op | Target Ref | OID suffix | Result |
|-----------:|----|----------:|------------|--------|
| 06:51:47 | ITI-65 send (new) | — | (new) | HTTP `200` → **Ref 1402943 created** |
| 06:52:09 | ITI-65 replace (storno #1) | 1402943 | `.1.746564` | HTTP `400 ERR_DOCTRANSVAL_1000` `NoHttpResponseException: localhost:8080 failed to respond` |
| 06:53:05 | ITI-65 replace (storno #2) | 1402943 | `.1.746564` | HTTP `200` → **cancelled** |

~55 seconds between the two storno attempts. Exact same bundle on the
wire (different OID for the replacement DocumentReference, but same
`relatesTo.target.identifier` pointing at the original OID). **Retry
makes it pass.** The intermittency is on CEZIH's internal FHIR server
and not on our side.

DB row reflects: Ref `1402943` status `Storniran`, izmjena `08:53`.

**Code path status:** verified again today. The historical finding
`TC20-cancel-document-blocker.md` (2026-04-13) remains authoritative
for the architecture (ITI-65 replace with `status=current` + `relatesTo`
pointing at the original OID); today's test confirms nothing has
regressed.

## Secondary — ITI-65 storno does NOT trigger Certilia push (as designed)

Observed during the retry: no Certilia push reaches the phone for any
of TC18 / TC19 / TC20. That is intentional — backend log shows:

```
app.services.cezih.signing: ITI-65 transaction bundle detected — skipping extsigner (unsigned send)
```

ITI-65 `$process-message` transaction bundles are sent **unsigned**.
Only `$process-message` event bundles (2.x case events, 1.x visit events,
PMIR) require Certilia signing. This matches CEZIH's expectation for
MHD and is covered in `project_cezih_iti65_profile.md` memory.

## Intermittency: what CEZIH is doing

Errors from failed attempts (2026-04-20, 2026-04-21 06:52) share the
same internal CEZIH stack trace:

```
Kod: ERR_DOCTRANSVAL_1000
Failed to parse response from server when performing GET to URL
http://localhost:8080/fhir/DocumentReference
  ?identifier=urn%3Aoid%3A2.16.840.1.113883.2.7.50.2.1.746564
  &status=current
  &_include%3Aiterate=DocumentReference%3Arelatesto%3ADocumentReference
- org.apache.http.NoHttpResponseException: localhost:8080 failed to respond
```

`localhost:8080` is an internal service on CEZIH's side that resolves
OID → DocumentReference to validate the replace target. It drops
connections intermittently — could be pool exhaustion, an upstream
reverse proxy, or a flaky HAPI FHIR backend. Nothing our code can do
about this; retry within ~1 minute is the current workaround.

## Discovery

During E2E testing 2026-04-20 (mobile signing only, patient GORAN PACPRIVATNICI19),
TC20 (Storno nalaz) consistently failed with ERR_DOCTRANSVAL_1000 on multiple
retries. All three retries were clustered within a few minutes; the env
stayed in a bad window.

## Impact

- TC20 code path is verified; CEZIH env intermittency is the only
  blocker, and retry resolves it.
- Before the exam or a demo, **always warm the env with a retry** if
  the first storno attempt gets `ERR_DOCTRANSVAL_1000`. Don't interpret
  a single failure as a code bug — check the error code.
- If the examiner hits this, show them the CEZIH-side stack trace
  (`org.apache.http.NoHttpResponseException: localhost:8080 failed to
  respond`). It is on CEZIH, not on privatnici software.

## Action Items

- [x] No code change needed on our side.
- [x] Verify TC20 on 2026-04-21 — passed on 2nd attempt (Ref 1402943,
      HTTP 200 at 06:53:06 UTC).
- [x] Confirmed ITI-65 is unsigned by design (no Certilia push
      expected for storno/replace/send).
- [ ] Consider backend retry-once on `ERR_DOCTRANSVAL_1000` — out of
      scope for certification, but would improve UX. Do NOT retry on
      any other CEZIH error code; this signature is specific to the
      CEZIH-side timeout.
- [ ] If still intermittent during live exam: escalate to HZZO operators
      (restart their internal doc-lookup FHIR service), and note that
      retry typically resolves within a minute.

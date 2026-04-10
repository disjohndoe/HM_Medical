---
date: 2026-04-10
topic: documents
status: resolved
---

# ITI-65 Document Submission — 403 Blocker (TC18-20)

## Discovery

POSTing a signed FHIR Bundle to `doc-mhd-svc/api/v1/iti-65-service` returns 403 with the full bundle echoed back and no OperationOutcome. This blocks TC18 (send document), TC19 (replace), and TC20 (cancel).

## Root Cause: Wrong Bundle Type

**We were sending `type="message"` bundles (with MessageHeader, event code "3.1"). IHE MHD ITI-65 requires `type="transaction"` bundles.**

Evidence from three sources:
1. **IHE MHD v4.2.3 spec** — ITI-65 "Provide Document Bundle" explicitly requires transaction bundles
2. **CEZIH HRMinimalProvideDocumentBundle** — Simplifier StructureDefinition has `Bundle.type` fixed to `"transaction"`
3. **CEZIH klinicki-dokumenti guide** — "Poruka je bazirana na specifikaciji IHE.MHD.Minimal.ProvideBundle" (which is a transaction bundle)

### Correct ITI-65 Bundle Structure

```json
{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {
      "fullUrl": "urn:uuid:<list-uuid>",
      "resource": {
        "resourceType": "List",
        "code": {"coding": [{"code": "submissionset"}]},
        ...SubmissionSet metadata...
      },
      "request": {"method": "POST", "url": "List"}
    },
    {
      "fullUrl": "urn:uuid:<docref-uuid>",
      "resource": {
        "resourceType": "DocumentReference",
        ...document metadata + content...
      },
      "request": {"method": "POST", "url": "DocumentReference"}
    }
  ]
}
```

Key differences from our message bundles (visits/cases):
- NO MessageHeader
- NO event code
- Each entry needs `request.method` + `request.url`
- First entry should be a SubmissionSet (List resource)
- Signature still goes on `Bundle.signature`

### Why Visits/Cases Use Message Bundles But Documents Don't

Visits use `encounter-services/api/v1/$process-message` — this is a FHIR messaging endpoint that expects `type="message"`.
Documents use `doc-mhd-svc/api/v1/iti-65-service` — this is an IHE MHD endpoint that expects `type="transaction"`.
Different CEZIH services, different FHIR paradigms.

## Impact

TC18, TC19, TC20 all blocked. TC22 (retrieve) also indirectly blocked because no documents exist in CEZIH to retrieve.

## Fix Applied

Rewrote `send_enalaz()`, `replace_document()`, and `cancel_document()` in `service.py` to build proper IHE MHD transaction bundles instead of message bundles. Added `build_iti65_transaction_bundle()` helper in `message_builder.py`.

## Action Items

- [x] Identify root cause (wrong bundle type)
- [x] Rewrite send_enalaz to use transaction bundle
- [x] Rewrite replace_document to use transaction bundle
- [x] Rewrite cancel_document to use transaction bundle
- [x] Live test TC18 against real CEZIH — **VERIFIED 2026-04-10, HTTP 200**
- [x] 403 resolved — was bundle type, then 24 more fixes for full profile compliance

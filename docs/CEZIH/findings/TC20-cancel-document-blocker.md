---
date: 2026-04-13
updated: 2026-05-13
topic: documents | cancel | storno | cascade
status: resolved
---

# TC20 Cancel Document — RESOLVED

## Two working methods

### Method 1: Replace-style cancel (standalone TC20, VERIFIED 2026-04-13)

ITI-65 replace (same bundle as TC18/TC19). Submit a new DocumentReference with
`relatesTo.code=replaces` targeting the original document by OID. The original
gets `status=superseded` automatically.

1. Look up document OID via ITI-67 search (extract from `content_url` base64 `data` param)
2. Build ITI-65 transaction bundle via `_build_document_bundle()` (same as TC18/TC19)
3. Add `relatesTo.code=replaces` with logical OID reference
4. `status = "current"` (NOT entered-in-error)
5. POST to `doc-mhd-svc/api/v1/iti-65-service`
6. Result: 200, original document superseded

### Method 2: Canonical cancel (HRCancelDocumentBundle, VERIFIED 2026-05-13)

2-entry ITI-65 bundle matching the official CEZIH `Bundle-ITI-65-Cancel.json` example.
SubmissionSet + DocumentReference only. No Binary, no signing, no relatesTo.

1. Look up document OID via ITI-67 search (same as Method 1)
2. Build 2-entry transaction bundle via `build_cancel_bundle()`
   - `masterIdentifier` = original doc OID (CEZIH resolves to existing doc)
   - `status = "entered-in-error"`
   - Profile: `HRMinimalProvideDocumentBundle`
   - Documents slice max=0, FhirDocuments max=0 (per HRCancelDocumentBundle profile)
3. POST to `doc-mhd-svc/api/v1/iti-65-service`
4. Result: 200, document marked entered-in-error

**Live verification (2026-05-13):**
- Patient: GORDANA PACPRIVATNICI17 (MBO 999999175)
- Document ref: 1590236, OID: `2.16.840.1.113883.2.7.50.2.1.752871`
- CEZIH response: 200 (1615ms)
- Used by cascade storno (visit cancel with attached nalazi)

### Why earlier ERR_DOM_10057 on entered-in-error was misleading

The original rejection was from a **3-entry replace bundle** (SubmissionSet + DocumentReference + Binary)
with `status=entered-in-error`, NOT from the canonical 2-entry cancel bundle.
The canonical `HRCancelDocumentBundle` profile explicitly requires `entered-in-error`
and has `Documents` slice max=0 (no Binary). The 3-entry bundle violated that profile.

### Cascade storno flow (visit cancel with attached nalazi)

When cancelling a visit (event 1.4) that has active DocumentReferences linked to it,
CEZIH rejects with ERR_ENCOUNTER_2001 ("encounter has active documents").
The cascade flow:

1. Query local DB for non-storniran nalazi linked to the visit encounter
2. For each: call `dispatch_cancel_document_canonical()` (Method 2) → CEZIH 200
3. Send encounter cancel (event 1.4, signed bundle) → CEZIH 200
4. All nalazi + visit marked stornirana

**Why the old cascade was broken:** It used Method 1 (replace-style) which creates a
NEW DocumentReference also linked to the same encounter. After cascade, CEZIH saw MORE
docs, not fewer, causing an infinite loop of ERR_ENCOUNTER_2001 rejections.

### What DOES NOT work:
| Attempt | Why it failed |
|---------|--------------|
| PUT (405) | ITI-65 endpoint only accepts POST |
| DELETE (404) | No FHIR base REST endpoint exists |
| JSON Patch (404) | No FHIR base REST endpoint exists |
| 3-entry ITI-65 + entered-in-error (ERR_DOM_10057) | Violates HRCancelDocumentBundle profile |
| ITI-65 + literal reference (ERR_DOM_10057) | CEZIH resolves by OID, not numeric ID |
| ITI-65 + relatesTo=transforms (403) | Wrong relatesTo code |
| Cascade with replace-style cancel | Creates new doc linked to same encounter |

### Key discoveries:
- **CEZIH resolves documents by OID** (masterIdentifier), NOT by server-assigned numeric ID
- **OID is in ITI-67 content_url**: base64-decoded `data` param contains `documentUniqueId=urn:ietf:rfc:3986|urn:oid:X.X.X`
- **No separate cancel endpoint exists** - only ITI-65 (POST), ITI-67 (GET), ITI-68 (GET)
- **Canonical cancel (entered-in-error) works** with the correct 2-entry bundle profile
- **Cascade must use canonical cancel** (not replace-style) to avoid creating new docs

## Files:
- `backend/app/services/cezih/fhir_api/documents.py` — `cancel_document()` (Method 1), `cancel_document_canonical()` (Method 2), `build_cancel_bundle()`
- `backend/app/services/cezih/dispatchers/documents.py` — `dispatch_cancel_document()`, `dispatch_cancel_document_canonical()`
- `backend/app/services/cezih/dispatchers/visits.py` — cascade logic uses `dispatch_cancel_document_canonical()`
- `docs/CEZIH/klinicki-dokumenti/Bundle-ITI-65-Cancel.json` — official CEZIH cancel example
- `docs/CEZIH/klinicki-dokumenti/StructureDefinition-HRCancelDocumentBundle.json` — canonical profile

## Commits:
- `8f498e9` — ITI-65 bundle approach with entered-in-error (discovered profile validation passes)
- `0a96f01` — OID lookup via ITI-67 content_url
- `19d5f5d` — VERIFIED: Method 1 (replace-style) works, status=current
- `8935c80` — Switch cascade to canonical cancel (dispatch_cancel_document_canonical)
- `3539d9f` — Fix __all__ export for cancel_document_canonical in fhir_api/documents.py

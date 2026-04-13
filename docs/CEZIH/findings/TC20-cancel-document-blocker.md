---
date: 2026-04-13
topic: documents | cancel | storno
status: resolved
---

# TC20 Cancel Document — RESOLVED

## Solution (2026-04-13)

Document cancel in CEZIH = ITI-65 replace (same bundle as TC18/TC19).
Submit a new DocumentReference with `relatesTo.code=replaces` targeting the
original document by OID. The original gets `status=superseded` automatically.

### Working approach:
1. Look up document OID via ITI-67 search (extract from `content_url` base64 `data` param)
2. Build ITI-65 transaction bundle via `_build_document_bundle()` (same as TC18/TC19)
3. Add `relatesTo.code=replaces` with logical OID reference
4. POST to `doc-mhd-svc/api/v1/iti-65-service`
5. Result: 200, original document superseded

### Key discoveries:
- **CEZIH rejects `entered-in-error` status** in ITI-65 → ERR_DOM_10057
- **CEZIH rejects literal references** (`DocumentReference/{id}`) in relatesTo → ERR_DOM_10057
- **CEZIH resolves relatesTo by OID** (masterIdentifier), NOT by server-assigned numeric ID
- **OID is in ITI-67 content_url**: base64-decoded `data` param contains `documentUniqueId=urn:ietf:rfc:3986|urn:oid:X.X.X`
- **No separate cancel endpoint exists** — only ITI-65 (POST), ITI-67 (GET), ITI-68 (GET) per official URL list

### Why earlier attempts failed:
| Attempt | Why it failed |
|---------|--------------|
| PUT (405) | ITI-65 endpoint only accepts POST |
| DELETE (404) | No FHIR base REST endpoint exists |
| JSON Patch (404) | No FHIR base REST endpoint exists |
| ITI-65 + entered-in-error (403→ERR_DOM_10057) | CEZIH rejects entered-in-error status |
| ITI-65 + literal reference (ERR_DOM_10057) | CEZIH resolves by OID, not numeric ID |
| ITI-65 + relatesTo=transforms (403) | Wrong relatesTo code |

## Files changed:
- `backend/app/services/cezih/service.py` — `_lookup_document_oid()`, `cancel_document()` rewritten
- `backend/app/services/cezih/dispatcher.py` — `dispatch_cancel_document()` enriched, sets `cezih_storno=True`

## Commits:
- `8f498e9` — ITI-65 bundle approach with entered-in-error (discovered profile validation passes)
- `0a96f01` — OID lookup via ITI-67 content_url
- `19d5f5d` — VERIFIED: status=current works, entered-in-error doesn't

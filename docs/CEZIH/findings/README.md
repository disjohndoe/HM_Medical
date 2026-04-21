# CEZIH Findings

Living knowledge base of discoveries from CEZIH/HZZO integration work. This directory grows over time as new findings are documented.

## How to Update

When you discover something new during CEZIH work:

1. **Create a new file** with the standard frontmatter format (see template below)
2. **Use a descriptive filename** — either dated (`2026-04-09-topic.md`) or topic-based (`ERR_DS_1002-signature-debugging.md`)
3. **Update this README.md** — add the new file to the index below
4. **If superseding an existing finding** — mark the old file as `status: superseded` and add `supersedes: old-file.md` to the new file

## File Template

```markdown
---
date: 2026-04-09
topic: signing | auth | endpoints | codesystems | certification | errors
status: active | resolved | superseded
supersedes: (optional — filename this replaces)
---

# Title

## Discovery
What was found...

## Evidence
Logs, HTTP responses, code references with file:line...

## Impact
What this means for the integration...

## Action Items
What needs to be done next...
```

## Findings Index

### Signing

| File | Date | Status | Summary |
|------|------|--------|---------|
| [smartcard-jws-format-fix.md](smartcard-jws-format-fix.md) | 2026-04-16 | resolved | **ROOT CAUSE FOUND** — two bugs: compact JSON (must be JCS) + attached JWS (must be detached + jwk with EC coords). VERIFIED working. |
| [ERR_DS_1002-signature-debugging.md](ERR_DS_1002-signature-debugging.md) | 2026-04-09 | resolved | Full history of signature debugging attempts — root cause was POST→GET redirect |
| [ERR_DS_1002-post-redirect-fix.md](ERR_DS_1002-post-redirect-fix.md) | 2026-04-08 | resolved | POST→GET redirect was the real cause of ERR_DS_1002 |

### Authentication

| File | Date | Status | Summary |
|------|------|--------|---------|
| [auth-discoveries.md](auth-discoveries.md) | 2026-04-09 | active | mTLS bypass, two-tier auth, POST session fix |

### CodeSystems

| File | Date | Status | Summary |
|------|------|--------|---------|
| [codesystem-mapping.md](codesystem-mapping.md) | 2026-04-09 | active | CEZIH-specific CodeSystems, encounter profiles |

### Signing (Digital Signature — Detached JWS)

| File | Date | Status | Summary |
|------|------|--------|---------|
| [signature-scope-clarification.md](signature-scope-clarification.md) | 2026-04-09 | active | Digital signature is for PDF documents only, NOT FHIR Bundles |
| [cezih-official-signature-format.md](cezih-official-signature-format.md) | 2026-04-09 | active | Definitive analysis: two conflicting formats — spec 3.4 (JWS, normative) vs Posjete example (raw, older) |

### Documents (ITI-65)

| File | Date | Status | Summary |
|------|------|--------|---------|
| [ITI-65-403-blocker.md](ITI-65-403-blocker.md) | 2026-04-10 | resolved | 403 on doc-mhd-svc — wrong bundle type (message vs transaction) — VERIFIED TC18 2026-04-10 |
| [ITI-65-document-profile.md](ITI-65-document-profile.md) | 2026-04-10 | active | HRMinimalDocumentReference — full profile field requirements, all CEZIHDR-* rules |
| [TC20-cancel-document-blocker.md](TC20-cancel-document-blocker.md) | 2026-04-13 | resolved | TC20 cancel = ITI-65 replace with OID. entered-in-error rejected; literal refs rejected. VERIFIED 2026-04-13 |
| [2026-04-20-cezih-test-env-fhir-server-down.md](2026-04-20-cezih-test-env-fhir-server-down.md) | 2026-04-20 | active | CEZIH test env internal FHIR server (localhost:8080 on their side) returning NoHttpResponseException — blocks TC20 storno on 2026-04-20. Our code path is verified-good. |
| [2026-04-20-clear-cezih-error-deadlock.md](2026-04-20-clear-cezih-error-deadlock.md) | 2026-04-20 | resolved | Backend self-deadlock in `clear_cezih_error` on retry-after-error path. Opened fresh session to UPDATE a row the dispatcher had already flushed. TC19 hang diagnosed + fixed (thread `session=db` through all 9 call sites). |

### Patient Registry (PMIR)

| File | Date | Status | Summary |
|------|------|--------|---------|
| [TC11-PMIR-auth-blocker.md](TC11-PMIR-auth-blocker.md) | 2026-04-13 | resolved | TC11 PMIR VERIFIED (Patient/1348216) — 4 stacked fixes: session establishment, extsigner-only signing, urn:uuid: refs, cezih_id extraction |

### Terminology

| File | Date | Status | Summary |
|------|------|--------|---------|
| [icd10-search-limitation.md](icd10-search-limitation.md) | 2026-04-13 | active | ICD-10 ValueSet/$expand returns empty in test env — manual fallback works, ValueSet URL confirmed correct |

### Case Lifecycle (health-issue-services)

| File | Date | Status | Summary |
|------|------|--------|---------|
| [TC16-case-session-preflight-fix.md](TC16-case-session-preflight-fix.md) | 2026-04-20 | resolved | TC16 via extsigner was hitting ERR_DS_1002 cold — Keycloak rejected POST body on cold `health-issue-services`. Added TC11-style pre-flight GET to all 4 condition.py entry points. VERIFIED live. |
| [2026-04-21-cases-dispatcher-datetime-import-regression.md](2026-04-21-cases-dispatcher-datetime-import-regression.md) | 2026-04-21 | resolved | Split-refactor (14377a3) lost `from datetime import UTC, datetime` in `dispatchers/cases.py`. TC17c Resolve (2.5) crashed with 500/NameError after successful CEZIH POST; 2.2 Ponavljajući also affected. Import restored. |
| [case-lifecycle-profile-matrix.md](case-lifecycle-profile-matrix.md) | 2026-04-16 | active | Full per-event matrix; 2.3/2.4/2.5/2.9 ALL VERIFIED (commit b314a4e); event codes were swapped in old code — 2.4=Resolve, 2.5=Relapse, 2.9=Reopen; 2.7=Delete NOT SHIPPING |
| [spec-research-2026-04-16.md](spec-research-2026-04-16.md) | 2026-04-16 | active | Simplifier cezih.hr.condition-management/0.2.1 ground truth — event code table, passport/EHIC identifier URIs, annotation-type CodeSystem |

### Specification Compliance

| File | Date | Status | Summary |
|------|------|--------|---------|
| [posjete-spec-audit.md](posjete-spec-audit.md) | 2026-04-09 | fixed | 6 mismatches found vs official Posjete examples — all fixed |

### Frontend UX

| File | Date | Status | Summary |
|------|------|--------|---------|
| [tempid-remount-race-fix.md](tempid-remount-race-fix.md) | 2026-04-20 | resolved | TC12→TC13 and TC16→TC17 back-to-back blocker — optimistic tempId row captured by edit dialog → 502 on PATCH. Fixed by disabling actions + guarding handlers on `temp-`/`pending-` rows. |

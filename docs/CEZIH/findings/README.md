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
| [2026-04-28-extsigner-bearer-token-required.md](2026-04-28-extsigner-bearer-token-required.md) | 2026-04-28 | resolved | **Resolves 4-day outage.** CEZIH unilaterally tightened auth on `extsigner/api/sign` on/around 2026-04-23 to require `Authorization: Bearer <token>` from `certpubsso.cezih.hr` IN ADDITION to mTLS. `_get_signing_token()` plumbing existed for ages but was never wired into `sign_bundle_via_extsigner`. EXP-3 wired it into both step 1 POST + step 2 GET poll. Commit `960cf3e`. End-to-end verified 2026-04-28 (visit-create 200 OK, ~26s incl. Certilia push). |
| [2026-04-28-multi-tenant-signing-oib.md](2026-04-28-multi-tenant-signing-oib.md) | 2026-04-28 | active | **P1 onboarding blocker** - `CEZIH_SIGNER_OIB` is a single global env var; every clinic would sign as TESTNI55. `User.card_certificate_oib` column already exists, signing layer just does not read it yet. ~1-2 day fix, post-cert sprint. `sourceSystem` correctly hardcoded (vendor-level). |
| [2026-04-27-extsigner-certilia-presign-unauthorized.md](2026-04-27-extsigner-certilia-presign-unauthorized.md) | 2026-04-27 | resolved | **RESOLVED 2026-04-28** — root cause was *our* missing Bearer header, not a CEZIH-side credential. Certilia and AKD were correct in saying they hadn't changed anything; CEZIH had silently flipped the auth requirement on extsigner. See `2026-04-28-extsigner-bearer-token-required.md`. Original investigation preserved as historical record (and as a lesson on misleading vendor error wording). |
| [2026-04-21-extsigner-akd-epotpis-down.md](2026-04-21-extsigner-akd-epotpis-down.md) | 2026-04-21 | active | CEZIH extsigner returns `ERROR_CODE_0020` "404 from POST http://lb-ifwproxy-akd:9170/api/v2/epotpis" — their internal AKD e-potpis proxy is down. Blocks ALL mobile-signed TCs. Not our code. |
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
| [2026-04-20-cezih-test-env-fhir-server-down.md](2026-04-20-cezih-test-env-fhir-server-down.md) | 2026-04-20 | resolved | CEZIH env intermittent on OID-lookup path — retry within ~1 min passes. **TC20 re-verified 2026-04-21 on fresh Ref 1402943 (send + storno HTTP 200).** Confirmed ITI-65 is unsigned by design (no Certilia push for storno/replace/send). |
| [2026-04-20-clear-cezih-error-deadlock.md](2026-04-20-clear-cezih-error-deadlock.md) | 2026-04-20 | resolved | Backend self-deadlock in `clear_cezih_error` on retry-after-error path. Opened fresh session to UPDATE a row the dispatcher had already flushed. TC19 hang diagnosed + fixed (thread `session=db` through all 9 call sites). |

### Patient Registry (PMIR)

| File | Date | Status | Summary |
|------|------|--------|---------|
| [TC11-PMIR-auth-blocker.md](TC11-PMIR-auth-blocker.md) | 2026-04-13 | resolved | TC11 PMIR VERIFIED (Patient/1348216) — 4 stacked fixes: session establishment, extsigner-only signing, urn:uuid: refs, cezih_id extraction |
| [2026-04-21-foreigner-visit-needs-pmir-first.md](2026-04-21-foreigner-visit-needs-pmir-first.md) | 2026-04-21 | active | Visit/case/nalaz on a local-only foreign patient → CEZIH returns `Reference_REF_CantResolve` (400) that surfaces as generic "retry in a few minutes" transient. Register flow is on `/cezih → Stranci` only; `/pacijenti → Uredi` passport does not trigger PMIR. TC11 itself verified 2026-04-21 (PMIR ID 1405304). |

### E2E Sweeps

| File | Date | Status | Summary |
|------|------|--------|---------|
| [2026-04-21-certilia-mobile-sweep-green.md](2026-04-21-certilia-mobile-sweep-green.md) | 2026-04-21 | active | First Certilia-mobile sweep — TC16/17/18/19/20/21/22/11 GREEN. TC18 Send Ref 1404239, TC19 Replace Ref 1404337, TC20 Storno verified. TC11 PMIR passport + EHIC. TC16 hit transient ERR_HEALTH_ISSUE_2000 (retry resolved). |
| [2026-04-21-handoff-tc16-and-e2e-sweep.md](2026-04-21-handoff-tc16-and-e2e-sweep.md) | 2026-04-21 | active | Handoff for TC16 ERR_HEALTH_ISSUE_2000 debugging + remaining E2E sweep. Resolved by asserter drop (544e31a); superseded by subsequent green sweeps. |
| [2026-04-22-certilia-mobile-sweep-green.md](2026-04-22-certilia-mobile-sweep-green.md) | 2026-04-22 | active | **Full Certilia-mobile sweep — 22/22 TC matrix GREEN.** Croatian GORAN full lifecycle incl. TC17 round-trip (2.1→2.3→2.5→2.4→2.9→2.6), TC18/19/20 on Refs 1415834→1415861→Storniran. Foreign ROGER ROG (EHIC) TC11/12/13/18 (Ref 1415986). |
| [2026-04-22-certilia-mobile-afternoon-reverify.md](2026-04-22-certilia-mobile-afternoon-reverify.md) | 2026-04-22 | active | Afternoon Certilia-mobile re-verification — Croatian GORAN full case lifecycle on `cmo9wpy1z02cshb85hi1hp2gz` (2.1→2.3→2.5→2.4→2.9→2.6, PUT 200). **Plus foreign ROGER ROG (EHIC) TC18→TC19→TC20 round-trip on Refs 1418944→1418960→Storniran** — closes same-day gap for foreign-storno-via-mobile evidence. Exam-ready, no gaps. |
| [2026-04-23-smartcard-sweep-green.md](2026-04-23-smartcard-sweep-green.md) | 2026-04-23 | active | **Pre-exam smart-card sweep — 22/22 TC matrix GREEN, second day running.** Croatian GORAN TC17 2.3→2.5→2.4→2.9→2.6 on J06.9 case `cmob5rm47…` + TC18/19/20 on Refs 1432176→1432212→Storniran. **Foreign ROGER ROG EHIC full TC12/13/18/19/20 on Refs 1432434→1432774→Storniran** — closes yesterday's foreign-storno-on-card gap. TC11 Passport path also re-verified. |
| [2026-04-22-smartcard-sweep-green.md](2026-04-22-smartcard-sweep-green.md) | 2026-04-22 | active | **Full smart-card sweep — 22/22 TC matrix GREEN.** Card #558299 JWS ES384. Croatian GORAN full lifecycle + TC17 round-trip + TC18/19/20 on Refs 1417551→1417628→Storniran. Foreign ROGER ROG (EHIC) TC11/12/13/18 (Ref 1418373, Potpis=Da). Dual-signing independence verified. |
| [2026-04-28-certilia-mobile-post-bearer-fix-sweep.md](2026-04-28-certilia-mobile-post-bearer-fix-sweep.md) | 2026-04-28 | active | **Post-Bearer-fix Certilia-mobile sweep, Croatian GORAN GREEN.** First mobile run after `extsigner` Bearer-token fix (commit `960cf3e`). Visit lifecycle on `cmoifxtaq03t5hb85lrebseav` (TC12/13/15/14), case lifecycle on `cmoig29m103t8hb854m0v65wf` (TC16 + TC17 2.3 -> 2.5 -> 2.4 -> 2.9 -> 2.6 PUT 200), e-Nalaz TC18/19/20 on Refs 1493569 -> 1493573 -> Storniran, TC21 ITI-67 search 20 docs. Foreign sweep deferred. |
| [2026-04-28-certilia-mobile-OIB-exam-dry-run.md](2026-04-28-certilia-mobile-OIB-exam-dry-run.md) | 2026-04-28 | active | **Exam dry-run Certilia-mobile sweep #2, Croatian GORAN GREEN.** Same day as morning post-Bearer sweep, fresh visit `cmoikd44503uzhb85gp0a580p` + case `cmoikp1dj03v1hb85sek2qr8k` (TC12/13/15/14 + TC16 + TC17 2.3 -> 2.5 -> 2.4 -> 2.9 -> 2.6), e-Nalaz TC18/19/20 on Refs 1495792 -> 1495803 -> Storniran, TC21 ITI-67 200 (2112ms, 20 docs). Every action cross-confirmed via BE API + prod backend logs (`PUT /replace-with-edit -> 200`, `DELETE /e-nalaz/1495803 -> 200`, `GET /documents -> 200`). Persistence verified via hard reload. One cosmetic 2.3 overlay non-clear noted, BE was correct. Foreign mobile deferred. |
| [2026-04-29-certilia-mobile-dual-patient-sweep.md](2026-04-29-certilia-mobile-dual-patient-sweep.md) | 2026-04-29 | active | **Dual-patient Certilia-mobile sweep, Croatian + Foreign GREEN same day.** Closes the foreign-mobile gap left open since the 2026-04-22 afternoon reverify (pre-Bearer-fix). Croatian GORAN: case `cmojp05kt03y5hb85qpwi0vnk` full TC12/13/15/14 + TC16 + TC17 2.3 -> 2.5 -> 2.4 -> 2.9 -> 2.6, e-Nalaz Refs 1501842 -> 1501883 -> Storniran. Foreign ROGER ROG (EHIC `TEST20251215113521HP`): visit `cmojpmcl703y7hb858bdgh641` + case `cmojpvykb03ybhb85qmajg7u8` full lifecycle, e-Nalaz Refs 1502553 -> 1502566 -> Storniran, TC21 ITI-67 20 docs. Persistence verified on both via hard reload. Exam-ready dual-class narrative on Certilia mobile end-to-end. |

### Terminology

| File | Date | Status | Summary |
|------|------|--------|---------|
| [2026-04-22-valueset-expand-fallback.md](2026-04-22-valueset-expand-fallback.md) | 2026-04-22 | active | TC8 ValueSet/$expand → 404 across all CodeSystems on test env; backend falls back to plain `ValueSet?url=` → 200 empty. Integration correct, data gap test-env only. |
| [icd10-search-limitation.md](icd10-search-limitation.md) | 2026-04-13 | active | ICD-10 ValueSet/$expand returns empty in test env — manual fallback works, ValueSet URL confirmed correct |

### Case Lifecycle (health-issue-services)

| File | Date | Status | Summary |
|------|------|--------|---------|
| [2026-04-28-case-storno-spec-impossible.md](2026-04-28-case-storno-spec-impossible.md) | 2026-04-28 | active | **Closes case-storno question.** Spec read of `cezih.hr.condition-management/0.2.1` (only published version): 2.6 profile binds `verificationStatus` `required` to `health-issue-management-verification-status-create` ValueSet, which contains only `unconfirmed/provisional/differential/confirmed`. `entered-in-error` is not in the ValueSet, so 2.6 + entered-in-error fails required-binding validation before reaching state-machine. FE picker filter is correct. No CEZIH-side case storno path exists; product gap is real but cert-irrelevant. |
| [TC16-case-session-preflight-fix.md](TC16-case-session-preflight-fix.md) | 2026-04-20 | resolved | TC16 via extsigner was hitting ERR_DS_1002 cold — Keycloak rejected POST body on cold `health-issue-services`. Added TC11-style pre-flight GET to all 4 condition.py entry points. VERIFIED live. |
| [2026-04-21-cezih-2.1-transient-state-machine-err.md](2026-04-21-cezih-2.1-transient-state-machine-err.md) | 2026-04-21 | resolved | `ERR_HEALTH_ISSUE_2000` on 2.1 create — CEZIH test-env transient (same family as ERR_DOCTRANSVAL_1000). Same payload retries to HTTP 200 within ~60s. Root cause: asserter field (fixed in 544e31a). |
| [2026-04-21-cases-dispatcher-datetime-import-regression.md](2026-04-21-cases-dispatcher-datetime-import-regression.md) | 2026-04-21 | resolved | Split-refactor (14377a3) lost `from datetime import UTC, datetime` in `dispatchers/cases.py`. TC17c Resolve (2.5) crashed with 500/NameError after successful CEZIH POST; 2.2 Ponavljajući also affected. Import restored. |
| [2026-04-21-cezih-2.2-recurrence-not-supported.md](2026-04-21-cezih-2.2-recurrence-not-supported.md) | 2026-04-21 | resolved | **FULLY RESOLVED** — wire fix via H2a (90ab916, keep `lokalni-identifikator`) + persistence/response-shape fix (77cf229, dispatcher reads parent_row + returns CaseActionResponse keys). FE "Ponovi slučaj" re-enabled. DB row populated with ICD + `recurrence` status. |
| [2026-04-21-cezih-2.6-data-update-not-supported.md](2026-04-21-cezih-2.6-data-update-not-supported.md) | 2026-04-21 | resolved | 2.6 Data update ERR_HEALTH_ISSUE_2000 — RESOLVED by dropping `asserter` (commit 5cb984c). State machine stricter than profile (which allows asserter max=1); working 2.4/2.9 never emit it. VERIFIED live CEZIH HTTP 200. |
| [2026-04-21-handoff-2.2-and-2.6-profile-fix.md](2026-04-21-handoff-2.2-and-2.6-profile-fix.md) | 2026-04-21 | resolved | Handoff closed: 2.6 fixed via H1 (drop asserter, commit 5cb984c); 2.2 fixed via H2a (keep `lokalni-identifikator`, commit 90ab916). Both verified live. |
| [2026-04-21-cezih-2.1-asserter-drop.md](2026-04-21-cezih-2.1-asserter-drop.md) | 2026-04-21 | resolved | TC16 2.1 Create case rejected with ERR_HEALTH_ISSUE_2000 — H1 mirror: `condition.pop("asserter", None)` in `create_case` (commit 544e31a). All three builder callers (2.1/2.2/2.6) now asserter-free. |
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

---
date: 2026-05-05
topic: visits | cases | pmir | meta-profile
status: active
---

# meta.profile sweep across visits, cases, PMIR (post 2026-05-04 rejection)

## Discovery

After HZZO Natalija Malkoč rejected provjera spremnosti on 2026-05-04 over plain text/PDF in ITI-65 Binary, the documents path was refactored to send signed FHIR Document Bundle (`082ca4b`), with a follow-up sweep adding `meta.profile` to every entry of the inner Document Bundle (`9211d1a`). The risk pattern - "CEZIH HAPI test env tolerates, HZZO manual review rejects" - is not specific to documents. Any submission missing IG-required `meta.profile` declarations exposes the same gap.

A 2026-05-05 audit of the OTHER CEZIH submission paths (visits, cases, PMIR) found three concrete cases of the same pattern that the document-bundle refactor did not cover.

## Evidence

### Visits TC1.1 (create) and TC1.2 (update)

`backend/app/services/cezih/dispatchers/visits.py:441` and `:548` literally pass `profile_urls=None` to `build_message_bundle`, so the produced Bundle has NO `meta.profile`, the `MessageHeader` has no profile, and the `Encounter` resource has no profile.

By contrast, the close/storno/reopen path at `:658-667` builds the dict from `ENCOUNTER_EVENT_PROFILE_MAP` correctly. The two highest-volume visit operations (create + update) were the unconforming ones.

### Cases 2.1, 2.2, 2.3-2.5, 2.6, 2.9

`backend/app/services/cezih/fhir_api/condition.py`:
- TC2.1 `create_case` at line 176-186 passed bundle + header profile but no Condition resource profile
- TC2.2 `create_recurring_case` at line 243-249 passed `profile_urls=` not at all (no kwarg)
- TC2.3-2.5 + 2.9 `update_case` at line 301-307 same omission
- TC2.6 `update_case_data` at line 353-359 same omission

There was no `CASE_EVENT_PROFILE_URLS` map mirroring the existing `ENCOUNTER_EVENT_PROFILE_MAP`. Every case lifecycle event was non-conformant on `meta.profile`.

### PMIR TC11 foreigner registration

`backend/app/services/cezih/fhir_api/pmir.py:102-116` had an explicit comment rationalizing the omission:

```
# NOTE: working encounters use NO meta.profile on individual resources.
# CEZIH knows expected profiles from the StructureDefinition, not meta.profile.
```

This is the same logic that just got rejected on documents. The outer Bundle had `meta.profile=HRRegisterPatient` correctly, but the inner `Bundle.type=history` and the `Patient` resource carried no profile declarations. TC11 was test-env-verified only via 4 stacked patches in April; never seen by HZZO certification review.

### IG profile URLs (verified from local Simplifier packages)

Cases - `cezih.hr.cezih-osnova` v1.0.1 + `case-lifecycle-profile-matrix.md` (2026-04-16):
- 2.1 create: `hr-create-health-issue-message`
- 2.2 recurrence: `hr-create-health-issue-recurrence-message`
- 2.3 remission: `hr-health-issue-remission-message`
- 2.4 resolve: `hr-health-issue-resolve-message`
- 2.5 relapse: `hr-health-issue-relapse-message`
- 2.6 data update: `hr-update-health-issue-data-message`
- 2.9 reopen: `hr-reopen-health-issue-message`
- MessageHeader: `hr-hi-management-message-header`
- Condition resource: `hr-condition`

Visits - already in `backend/app/services/cezih/builders/encounter.py:61-67` `ENCOUNTER_EVENT_PROFILE_MAP` (1.1-1.5).

PMIR (`StructureDefinition-hr-register-patient.json` and `StructureDefinition-HRPMIRBundleInternal.json`):
- Outer Bundle: `HRRegisterPatient` (already declared)
- Inner Bundle: `https://profiles.ihe.net/ITI/PMIR/StructureDefinition/IHE.PMIR.Bundle.History` (per slice `Bundle.entry:PMIRBundleHistoryEntry.resource.type[0].profile[0]`)
- Patient: `hr-pacijent` (no Patient profile constraint at HRRegisterPatient level, but `hr-pacijent` is the canonical Patient profile across the package and accommodates putovnica/europskaKartica identifiers used for foreigners)

## Impact

1. **22/22 green TC sweeps prior to 2026-05-04 do NOT prove conformance.** Every visit + case + PMIR submission in the matrix was missing or partial on `meta.profile`. CEZIH HAPI test env did not enforce - same failure mode as 2026-05-04.

2. **Re-running the 22 TC matrix is mandatory before requesting next provjera termin** on BOTH smartcard AND Certilia paths against pvsek.cezih.hr. Documents path was already verified post-082ca4b/9211d1a. Visits + cases + PMIR are all newly modified and require fresh end-to-end verification.

3. **No payload structure changes** - this is a strictly additive declaration sweep (meta.profile arrays). Bundle/MessageHeader/resource fields, identifier systems, signing logic all unchanged. CEZIH HAPI is expected to continue accepting the bundles. The only change visible to a manual reviewer is that conformance is now machine-verifiable.

## Action Items

- [x] Add `CASE_EVENT_PROFILE_MAP` + `PROFILE_CONDITION` constants in `backend/app/services/cezih/builders/condition.py`
- [x] Wire `profile_urls=` (bundle + header + resource) into all four call sites in `backend/app/services/cezih/fhir_api/condition.py` (create, recurring, update, update_data)
- [x] Wire `profile_urls=` into TC1.1 + TC1.2 sites in `backend/app/services/cezih/dispatchers/visits.py` (replace `profile_urls=None`)
- [x] Add `meta.profile` on inner Bundle + Patient in `backend/app/services/cezih/fhir_api/pmir.py`; remove rationalizing comment
- [x] ruff clean + builders produce expected 3-level meta.profile output (verified via direct `build_message_bundle` invocation)
- [ ] Live re-verification of all 22 TCs against pvsek.cezih.hr on smartcard path
- [ ] Live re-verification of all 22 TCs against pvsek.cezih.hr on Certilia mobile path
- [ ] Email Natalija Malkoč deferentially per `feedback_hr_institutional_register.md` requesting new provjera termin, attaching evidence of green TC refs
- [ ] Update memory `project_cezih_iti65_profile.md`, `project_cezih_certification_process.md` after new termin lands
- [ ] Update CLAUDE.md with Phase 21 row

## Deferred work (audited but not addressed in this commit)

These were identified in the same 2026-05-05 audit but are not in the same severity class as the meta.profile gap. They should be revisited in a separate commit, not bundled here.

### MED severity

1. **signature.who format divergence document vs message paths**
   - Document path (`signing.py:472-494`): `{"reference": "urn:uuid:..."}` literal per HRDocument DOC-3
   - Message path (`signing.py:156-192` via `practitioner_ref`): `{"type": "Practitioner", "identifier": {...}}`
   - DOC-3 applies to HRDocument profile. Message-bundle profiles may have similar constraint or none. Open the relevant `StructureDefinition-*.json` files for visit + case + PMIR message bundle profiles, find `Bundle.signature.who` constraints, decide if a fix is needed before next provjera.

2. **SVCM ValueSet $expand silent fallback**
   - `backend/app/services/cezih/fhir_api/registries.py:220-226` catches the exception on `$expand` and falls back to plain ValueSet search. Violates `feedback_no_fallbacks.md`. Affects TC6-9. Hides terminology-service errors and may return incomplete concept sets.

3. **Generated OIDs (TC6) not persisted with provenance**
   - `backend/app/services/cezih/fhir_api/registries.py:71-92` returns OIDs to caller without DB persistence. No audit trail tying batch to consuming submission. Add `cezih_oid_batch` table with tenant_id + generated_at + oid + consumed_by_submission_id.

### LOW severity

4. **Patient lookup (TC10 PDQm) lenient response parsing**
   - `backend/app/services/cezih/fhir_api/patient.py:56-68` does not strictly validate `entry[0].resource` is a Patient. Tighten.

5. **`ID_PUTOVNICA` defined in two modules**
   - `backend/app/services/cezih/builders/common.py` and `backend/app/services/cezih/fhir_api/identifiers.py` both define passport identifier system URI. DRY cleanup. Pick one canonical location.

## References

- HZZO rejection email 2026-05-04 10:59 from Natalija Malkoč (in `2026-05-04-iti65-inner-fhir-document-bundle.md`)
- Documents fix: commits `082ca4b`, `9211d1a`, `bbb2b2e`
- Working pattern reference: `backend/app/services/cezih/builders/encounter.py:61-67` `ENCOUNTER_EVENT_PROFILE_MAP`
- Documents reference: `backend/app/services/cezih/builders/clinical_document_bundle.py` lines 128, 153, 170, 197, 235, 290, 322, 566 for `meta.profile` pattern
- Case lifecycle profile sources: `case-lifecycle-profile-matrix.md` (2026-04-16, this folder)
- Local IG packages:
  - `docs/CEZIH/cezih.osnova-0.2.3/package/` (base profiles)
  - `docs/CEZIH/cezih.hr.cezih-osnova-1.0.1/package/` (PMIR + register-patient + base, downloaded 2026-05-05)
  - `docs/CEZIH/klinicki-dokumenti/` (HRDocument profile, downloaded 2026-05-04)

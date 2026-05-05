---
date: 2026-05-05
topic: signing | conformance | pmir | visits | cases
status: resolved
---

# Bundle.signature.who constraints across CEZIH message-bundle profiles

## Discovery

Per Stage 1 of the 2026-05-05 audit closeout plan, audited every CEZIH message-bundle profile to determine whether `Bundle.signature.who` requires literal `urn:uuid:` reference (mirroring HRDocument DOC-3, which caused the 2026-05-04 ITI-65 rejection) or whether identifier-based shape is acceptable.

Conclusion: identifier-based `practitioner_ref()` is correct for all visit + case + PMIR paths. No `signing.py` rewrite required.

Separately, while reading the condition-management package, found that the 2026-05-05 meta.profile fix (`Stage 0`) used the **wrong** profile URL for case event 2.6. Corrected in this commit.

## Evidence

Downloaded `cezih.hr.encounter-management/0.2.3` and `cezih.hr.condition-management/0.2.1` from Simplifier 2026-05-05. Inheritance walk for every per-event message profile:

### Encounter-management (visits)

All seven per-event profiles inherit directly from `hr-request-message`:

```
hr-create-encounter-message       -> hr-request-message
hr-update-encounter-message       -> hr-request-message
hr-close-encounter-message        -> hr-request-message
hr-cancel-encounter-message       -> hr-request-message
hr-reopen-encounter-message       -> hr-request-message
hr-encounter-response-message     -> hr-response-message
hr-encounter-management-message-header -> hr-message-header
```

### Condition-management (cases)

All per-event profiles inherit through one extra layer (`hr-health-issue-request-message`) which itself inherits from `hr-request-message`:

```
hr-create-health-issue-message               -> hr-health-issue-request-message -> hr-request-message
hr-create-health-issue-recurrence-message    -> hr-health-issue-request-message -> hr-request-message
hr-health-issue-remission-message            -> hr-health-issue-request-message -> hr-request-message
hr-health-issue-resolve-message              -> hr-health-issue-request-message -> hr-request-message
hr-health-issue-relapse-message              -> hr-health-issue-request-message -> hr-request-message
hr-health-issue-update-message               -> hr-health-issue-request-message -> hr-request-message
hr-reopen-health-issue-message               -> hr-health-issue-request-message -> hr-request-message
hr-delete-health-issue-message               -> hr-health-issue-request-message -> hr-request-message  (NOT shipped)
```

### Constraints in `hr-request-message` (the common base)

```
Bundle.signature                 min=1
Bundle.signature.type            fixedCoding=urn:iso-astm:E1762-95:2013/1.2.840.10065.1.12.1.1
Bundle.signature.who             type=Reference     (no further constraint)
Bundle.signature.onBehalfOf      max=0
Bundle.signature.targetFormat    max=0
Bundle.signature.sigFormat       max=0
Bundle.signature.data            min=1
```

`Bundle.signature.who` is required as a `Reference` but the base profile imposes neither `who.reference` nor `who.identifier` constraints. Both shapes are valid. Our `practitioner_ref(hzjz_id)` returns `{type: "Practitioner", identifier: {system: HZJZ-broj-zdravstvenog-djelatnika, value: <hzjz>}}`, which is a valid `Reference` with `type` + `identifier`.

### PMIR (HRPMIRBundle / hr-register-patient)

PMIR is the only path with explicit `signature.who` slicing:

```
Bundle.signature.who             type=Reference
Bundle.signature.who.type        min=1 fixedUri=Practitioner
Bundle.signature.who.identifier  min=1
Bundle.signature.who.identifier.system  min=1 patternUri=http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika
Bundle.signature.who.identifier.value   min=1
```

PMIR REQUIRES identifier-based `who` and explicitly forbids `who.reference` by mandating identifier slicing. Our current `practitioner_ref()` shape matches exactly:

| Constraint | Code value |
|---|---|
| `type` fixedUri=Practitioner | `"Practitioner"` (matches) |
| `identifier.system` patternUri=HZJZ-... | `ID_PRACTITIONER = "http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika"` (matches) |
| `identifier.value` min=1 | hzjz_id passed in (present) |

### HRDocument (the rejected 2026-05-04 path) - for contrast

HRDocument profile (in `cezih.hr.klinicki-dokumenti`) explicitly forbids `who.identifier` and `who.type`, and requires `who.reference` matching `^urn:uuid:.*` (DOC-3). That is why the documents path uses `_set_document_signature_skeleton` with literal `urn:uuid:`. Different profile, different constraint. Not a precedent for visit/case/PMIR signature.

## Decision

| Path | Profile | who shape | Code state |
|---|---|---|---|
| Visits 1.1-1.5 | hr-*-encounter-message via hr-request-message | identifier OR reference (no constraint) | `practitioner_ref()` identifier - correct, no change |
| Cases 2.1-2.6, 2.9 | hr-*-health-issue-* via hr-health-issue-request-message via hr-request-message | identifier OR reference (no constraint) | `practitioner_ref()` identifier - correct, no change |
| PMIR | HRPMIRBundle / hr-register-patient | identifier REQUIRED, reference forbidden via slicing | `practitioner_ref()` identifier - correct, no change |
| Documents (ITI-65 inner) | HRDocument | reference REQUIRED with urn:uuid pattern, identifier forbidden | `_set_document_signature_skeleton()` urn:uuid - correct (post-082ca4b) |

Audit MED #4 closed: no `signing.py` or `pmir.py` rewrite needed.

## Side discovery: wrong CASE_EVENT_PROFILE_MAP[2.6] URL

While reading the condition-management package, found that the Stage 0 CASE_EVENT_PROFILE_MAP added in `backend/app/services/cezih/builders/condition.py` mapped event code 2.6 to `hr-update-health-issue-data-message`, which does not exist in the IG package.

The actual profile is `hr-health-issue-update-message` (title: "Poruka zahtjeva za izmjenu podataka slučaja", event coding `2.6`). Verified by reading `Bundle.entry:MessageHeader.resource.event[x].fixedCoding` on every per-event profile - 2.6 binds to `hr-health-issue-update-message`.

Source of the typo: `case-lifecycle-profile-matrix.md` (2026-04-16) line 92 uses the wrong URL string (`hr-update-health-issue-data-message|0.1`). That doc was the reference when CASE_EVENT_PROFILE_MAP was constructed during Stage 0. The doc was wrong and propagated.

Corrected in same commit as this finding.

```diff
-    "2.6": f"{_PROFILE_BASE}/hr-update-health-issue-data-message",
+    "2.6": f"{_PROFILE_BASE}/hr-health-issue-update-message",
```

## Impact

1. **MED #4 from 2026-05-05 audit closes resolved** without code change. Document this in the audit findings README so future cert reviews don't re-open it.
2. **Stage 0 audit fix had a latent bug** - `meta.profile` declared on case 2.6 messages was a non-existent profile URL. CEZIH HAPI test env tolerates unknown meta.profile entries (does not fail validation, just ignores them), which is why prior 22/22 sweeps on the post-Stage-0 code never surfaced this. Manual review at HZZO would have caught it. Same risk class as the 2026-05-04 rejection. Fix applied here is essential before requesting next provjera termin.
3. The `case-lifecycle-profile-matrix.md` (2026-04-16) needs the same correction so future code generation is not seeded from a wrong URL again. To be done in Stage 5 documentation sync.

## Action Items

- [x] Download cezih.hr.encounter-management/0.2.3 + cezih.hr.condition-management/0.2.1 packages into docs/CEZIH/
- [x] Audit signature.who slicing in all message-bundle profiles via inheritance walk to hr-request-message base
- [x] Verify PMIR HRPMIRBundle slicing matches our practitioner_ref() output shape exactly
- [x] Correct CASE_EVENT_PROFILE_MAP[2.6] URL in `backend/app/services/cezih/builders/condition.py`
- [ ] Update `case-lifecycle-profile-matrix.md` to use correct 2.6 URL (Stage 5)
- [ ] Re-verify case 2.6 (data-update) on pvsek.cezih.hr in Stage 3 sweep with corrected meta.profile

## References

- Local IG packages (downloaded 2026-05-05):
  - `docs/CEZIH/cezih.hr.encounter-management-0.2.3/package/`
  - `docs/CEZIH/cezih.hr.condition-management-0.2.1/package/`
  - `docs/CEZIH/cezih.hr.cezih-osnova-1.0.1/package/` (HRPMIRBundle, hr-register-patient, hr-request-message base)
- HRDocument signature.who constraint (DOC-3): `backend/app/services/cezih/signing.py:472-494`
- Audit handoff: `docs/CEZIH/findings/2026-05-05-meta-profile-sweep-visits-cases-pmir.md`

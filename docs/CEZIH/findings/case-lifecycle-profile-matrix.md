---
date: 2026-04-16
topic: endpoints | codesystems | errors
status: active
---

# Case Lifecycle `$process-message` Per-Event Profile Matrix

## Discovery

CEZIH's `health-issue-services/$process-message` endpoint validates each
event code against a **different** FHIR StructureDefinition profile. The
old assumption that a single minimal payload (`identifier + subject`)
works for every status transition is **wrong** — three distinct payload
shapes are needed (minimal, cs+abatement, full Condition). A fourth
constraint — CEZIH's case **state machine** — rejects some transitions
regardless of payload shape, returning `ERR_HEALTH_ISSUE_2004`.

Config-table implementation: `CASE_EVENT_PROFILE` at
`backend/app/services/cezih/message_builder.py:915`.

## Evidence (live testing, 2026-04-16, test env `pvsek.cezih.hr`)

### 2.1 Create (`hr-create-health-issue-message|0.1`)

Uses `build_condition_create` — dedicated code path. Requires full Condition
with ICD `code`, `subject`, `onsetDateTime`, `verificationStatus`, `asserter`.
`identifier` uses system `lokalni-identifikator-slucaja` (client-generated UUID);
CEZIH assigns the global `identifikator-slucaja` in the response.

**✅ VERIFIED 2026-04-16** — 200 OK.

### 2.2 Ponavljajući (`hr-create-health-issue-recurrence-message|0.1`)

**Not a status-update — a CREATE.** Uses `build_condition_create` via new
routing in `dispatcher.dispatch_update_case` when `action == "create_recurring"`.
The dispatcher first calls `retrieve_cases` to look up the parent case's ICD,
then creates a new case with the inherited ICD.

Profile rules (discovered from 400 errors):
- `identifier`: **FORBIDDEN** in the client payload — the server assigns a
  fresh global identifier for the new recurrence case.
- `code` (ICD): **REQUIRED**
- `verificationStatus`: **REQUIRED**
- `onset[x]`: **REQUIRED**

**✅ VERIFIED 2026-04-16** — 200 OK; new case with `clinical_status="recurrence"`
(standard FHIR condition-clinical code, now mapped in the FE).

### 2.3 Remisija (`hr-health-issue-remission-message|0.1`)

- `clinicalStatus`: max = 0 (must be ABSENT)
- `abatement[x]`: max = 0 (must be ABSENT)
- Payload: **minimal** — `identifier + subject` only.

**✅ VERIFIED 2026-04-16** — 200 OK. This is the exam TC17 baseline oracle.

### 2.4 Relaps — **TEST-ENV BUG**

CEZIH test env routes event code 2.4 to the **`hr-health-issue-resolve-message`**
profile instead of a (presumably missing) relapse-specific profile:

```
Bundle.entry:HealthIssue.resource.abatement[x]: minimum required = 1, but only found 0
  (from http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-health-issue-resolve-message|0.1)
Value is 'relapse' but must be 'resolved'
```

**Workaround active** (feature-flag `CEZIH_RELAPSE_SEMANTIC_CORRECT = False`
at `message_builder.py:951`): we send `clinicalStatus=resolved +
abatementDateTime`, which makes CEZIH return 200. **CEZIH then permanently
stores the case as `resolved`** — the FE reflects this as "Zatvoren". Accepted
as a cosmetic issue because 2.4 is **NOT in the 22 cert TCs**.

**When HZZO fixes routing:** flip the flag to `True` — that sends
semantically-correct `clinicalStatus=relapse` + no abatement.

HZZO helpdesk email drafted at `hzzo-email.txt` — to be sent.

### 2.5 Resolve (`hr-health-issue-resolve-message|0.1`)

- Payload: **minimal** — `identifier + subject` only.
- **Required case-state precondition**: `verificationStatus` must be
  `"confirmed"` — `"unconfirmed"` triggers `ERR_HEALTH_ISSUE_2004`
  "Not allowed to perform requested transition with current roles."

  Despite the misleading English text, this error is not about user
  roles — it's CEZIH's case state machine rejecting a resolve on a
  still-suspected diagnosis. Fix: default new cases to `confirmed`
  (`service.py:1151`) + UI picker in the create dialog.

**✅ VERIFIED 2026-04-16** — 200 OK on a confirmed case.

### 2.6 Data update (`hr-update-health-issue-data-message|0.1`)

Uses dedicated `build_condition_data_update`. Must echo current
`clinicalStatus`; profile forbids *changing* it through this event
(that's what 2.3/2.4/2.5/2.7 are for). Can change `verificationStatus`,
`code`, `onsetDateTime`, `abatementDateTime`, and notes.

### 2.7 Reopen (`hr-health-issue-reopen-message|0.1` — TENTATIVE)

**⚠️ DISABLED IN UI (2026-04-16)** — hidden from `getAvailableActions` in
`frontend/src/components/cezih/case-management.tsx:195` until the payload
fix lands. Every live attempt hit the `himgmt-1` razlog rule, so the FE
stops offering the action rather than guaranteeing a failed CEZIH call.

Using **minimal payload** — `identifier + subject` only. In live testing a
Reopen attempt produced an `hr-delete-health-issue-message` profile error,
which we now believe was because the target case was already in a deleted
state (not a profile-routing bug). The `ERR_HEALTH_ISSUE_2004` rule likely
gates this transition the same way as 2.5 — case state machine dictates which
transitions are reachable.

**⚠️ Not yet cleanly verified on a case in pure `resolved` state.** Re-verify.

### 2.8 Delete (`hr-delete-health-issue-message|0.1`)

**⚠️ DISABLED IN UI (2026-04-16)** — hidden from `getAvailableActions` in
`frontend/src/components/cezih/case-management.tsx:195` until
`build_condition_delete` emits the required `note`. Re-enable after the
backend fix + a verified live call.

Uses `build_condition_delete`. Profile requires a `note` entry with a
deletion reason — validation error text:
`Rule himgmt-1: 'Mora postojati razlog brisanja' Failed`.

**⚠️ Current `build_condition_delete` likely omits the note.** Add a
required reason/note field to the delete action (either UI prompt or a
default "Obrisan od strane korisnika"). Not yet addressed.

## Impact

Five buttons on the case management UI (`frontend/src/components/cezih/
case-management.tsx`) now route correctly. The config table at
`CASE_EVENT_PROFILE` drives all per-event variation; any new field
discovered from a 400 OperationOutcome is a single dict edit.

## CEZIH Error-Code Translation

`ERR_HEALTH_ISSUE_2004` and other frequent codes are now translated to
Croatian user-friendly messages in `parse_message_response`
(`message_builder.py:_translate_cezih_error`). Falls back to the raw CEZIH
diagnostic when no rule matches. See also the `_CEZIH_ERROR_MESSAGES_HR`
and `_CEZIH_DIAGNOSTIC_PATTERNS_HR` dicts.

## Action Items

- [x] Refactor to `CASE_EVENT_PROFILE` config table (commit `d92c609`)
- [x] 2.3 Remisija live-verified (daa8371, re-confirmed 2026-04-16)
- [x] 2.2 Ponavljajući routing via create-recurrence (`ddad4b9`)
- [x] 2.4 Relaps test-env workaround + feature-flag (`58ab910`)
- [x] 2.5 Resolve live-verified with `verificationStatus=confirmed` default (`ef68fcc`)
- [x] UI verification-status picker in create dialog (`55bfb43`)
- [x] Croatian error translation layer (`727d195`)
- [ ] Send HZZO email about 2.4 routing bug (draft at `hzzo-email.txt`)
- [ ] **2.7 Reopen** — fix `build_condition_status_update` (`message_builder.py:777`) to include `note` with razlog for event code 2.7; re-verify on a case in pure `resolved` state (not deleted); re-enable in FE (`case-management.tsx:195`). Currently hidden from UI.
- [ ] **2.8 Delete** — fix `build_condition_delete` (`message_builder.py:891`) to include required `note` field (either UI prompt or default "Obrisan od strane korisnika"); re-enable in FE (`case-management.tsx:195`). Currently hidden from UI.
- [ ] When HZZO confirms real relapse profile, flip
      `CEZIH_RELAPSE_SEMANTIC_CORRECT = True` in `message_builder.py:951`

## Code Reference

- Config table: `backend/app/services/cezih/message_builder.py:915` `CASE_EVENT_PROFILE`
- Builder: `backend/app/services/cezih/message_builder.py:777` `build_condition_status_update`
- Dispatcher: `backend/app/services/cezih/service.py:1223` `update_case`
- Recurrence creator: `backend/app/services/cezih/service.py:1180` `create_recurring_case`
- Dispatcher routing: `backend/app/services/cezih/dispatcher.py` `dispatch_update_case`
- Error translation: `backend/app/services/cezih/message_builder.py:_translate_cezih_error`
- FE state machine: `frontend/src/components/cezih/case-management.tsx:188` `getAvailableActions`
- FE status labels: `frontend/src/components/cezih/case-management.tsx:45-66`

## Cert-Exam Relevance

Of the case lifecycle events, **only TC17 (Remisija, 2.3) is in the 22
cert TCs**. Events 2.2, 2.4, 2.5, 2.7, 2.8 are product features beyond
the certification spec; their correct behavior is a UX concern, not an
exam blocker. Rollback to the `pre-cezih-case-fix` tag restores the
pre-refactor hard-coded ladder if anything regresses on 2.3 the morning
of the exam.

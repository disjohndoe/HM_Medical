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

### 2.4 Resolve / Zatvori (`hr-health-issue-resolve-message|0.1`)

- `clinicalStatus`: **FIXED to `resolved`** (required, not optional)
- `abatementDateTime`: **[1..1] REQUIRED**
- `verificationStatus`: forbidden
- `note`: forbidden
- Payload: **cs+abatement shape** — `identifier + subject + clinicalStatus=resolved + abatementDateTime`
- **Required case-state precondition**: `verificationStatus` must be `"confirmed"` —
  `"unconfirmed"` triggers `ERR_HEALTH_ISSUE_2004` ("Not allowed to perform requested
  transition with current roles"). This error is NOT about user roles — it's the state
  machine rejecting a resolve on an unconfirmed diagnosis.

**✅ VERIFIED 2026-04-16** (extsigner, commit `b314a4e`) — 200 OK on active+confirmed S00.3 case.

> **Historical note:** Pre-fix, our `CASE_ACTION_MAP` had 2.4/2.5 swapped. We were
> sending event code 2.4 labelled as "Relaps" with `clinicalStatus=relapse` payload.
> CEZIH correctly routed 2.4 to the resolve-message profile, which rejected `relapse`
> and required `abatementDateTime`. We misread this as a "test-env routing bug". It was
> our code. Fixed in commit `b314a4e` (2026-04-16).

### 2.5 Relapse / Relaps (`hr-health-issue-relapse-message|0.1`)

- `clinicalStatus`: max = 0 (must be ABSENT)
- `abatement[x]`: max = 0 (must be ABSENT)
- Payload: **minimal** — `identifier + subject` only.
- **State precondition**: case must be in `remission` state.

**✅ VERIFIED 2026-04-16** (extsigner, commit `b314a4e`) — 200 OK on A57 case in Remisija state.

> **Historical note:** Pre-fix, we were sending event code 2.5 labelled as "Resolve"
> with minimal payload. CEZIH routed 2.5 to the relapse-message profile (minimal by
> spec), so it passed — but CEZIH stored the transition as a relapse. The fact that
> it "worked" masked the semantic error entirely. Fixed in `b314a4e`.

### 2.6 Data update (`hr-update-health-issue-data-message|0.1`)

Uses dedicated `build_condition_data_update`. Must echo current
`clinicalStatus`; profile forbids *changing* it through this event
(that's what 2.3/2.4/2.5/2.7 are for). Can change `verificationStatus`,
`code`, `onsetDateTime`, `abatementDateTime`, and notes.

### 2.7 Delete — NOT SHIPPING (hard product rule)

Spec profile: `hr-delete-health-issue-message|0.1`. Requires `note[annotation-type=1]`
with "Razlog brisanja podatka". CEZIH validates `himgmt-1` rule.

**HARD RULE (CLAUDE.md, `project_cezih_no_delete.md` memory): never ship this action.**
No `delete` entry in `CASE_ACTION_MAP`, no "Obriši" button in frontend. For "mistaken
entry" UX: use 2.6 data update with `verificationStatus=entered-in-error`.

### 2.8 Reopen-after-delete — NOT REACHABLE

Spec profile: `hr-reopen-health-issue-message`. Event code 2.8 = reopen a deleted case.
Since we never delete via CEZIH (hard rule above), 2.8 is never reachable. Not implemented.

### 2.9 Reopen / Ponovno otvori (`hr-reopen-health-issue-message`)

- Payload: **minimal** — `identifier + subject` only.
- **State precondition**: case must be in `resolved` state. FE shows "Ponovno otvori"
  only on `clinicalStatus=resolved` cases.

**✅ VERIFIED 2026-04-16** (extsigner, commit `b314a4e`) — 200 OK on S00.3 case
previously Zatvoren via 2.4 Resolve.

> **Historical note:** Pre-fix, we had `reopen` mapped to event code 2.7 (Delete by spec).
> Every reopen attempt hit CEZIH's delete-message profile and the `himgmt-1` razlog rule.
> Fixed in `b314a4e` to use 2.9 (Reopen-after-resolve).

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
- [x] 2.4 Resolve (Zatvori) live-verified — **correct code** (commit `b314a4e` 2026-04-16)
- [x] 2.5 Relapse (Relaps) live-verified — **correct code** (commit `b314a4e` 2026-04-16)
- [x] 2.9 Reopen (Ponovno otvori) live-verified — **correct code** (commit `b314a4e` 2026-04-16)
- [x] UI verification-status picker in create dialog (`55bfb43`)
- [x] Croatian error translation layer (`727d195`)
- [x] FE state machine gates: Zatvori on aktivan+potvrđen/nepotvrđen, Relaps on remisija, Reopen on resolved, Remisija on aktivan — all verified (commit `b314a4e`)
- [x] Remove stale `CEZIH_RELAPSE_SEMANTIC_CORRECT` feature-flag — codes are correct, no workaround needed

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

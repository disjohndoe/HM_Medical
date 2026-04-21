---
date: 2026-04-21
topic: errors
status: active
---

# Handoff — TC16 still blocked + remaining E2E sweep (Croatian + foreign)

## How to use this doc

You are resuming E2E certification testing of the 22 CEZIH test cases on
prod (`app.hmdigital.hr`) against the real CEZIH test environment. All
signing is **Certilia mobile only** in this pass (smart card sweep comes
later). Read this doc end-to-end, then resume from "Next actions". Use
Chrome DevTools MCP to drive the UI, and SSH into the prod server to
inspect backend logs when a TC fails.

**User preferences (persistent):**
- Both CEZIH signing methods (smart card + Certilia mobile) must work
  independently for ALL 22 TCs. No fallbacks. For THIS session, mobile only.
- Test on prod only, not localhost. Commit → push → auto-deploy → E2E via
  Chrome MCP → SSH logs if something breaks.
- For UI tables (Slučajevi / Nalazi / Posjete): after each CEZIH action,
  confirm the row updates (status, date, CEZIH ID). Then reload the page
  and confirm persistence.
- Skip TC6 (OID generation — always works).
- Croatian patient first, then foreign.
- Never add a CEZIH Condition delete (hard rule — local-only delete OK).

## Open blocker — TC16 2.1 Create Case still rejects with ERR_HEALTH_ISSUE_2000

### State

Commit `544e31a` applied the H1 mirror fix: `condition.pop("asserter", None)`
in `create_case` at `backend/app/services/cezih/fhir_api/condition.py:167`.
The asserter is verifiably gone from the wire — backend log
`2026-04-21 07:16:41` shows the signed bundle POSTed to
`certws2.cezih.hr:8443/services-router/gateway/health-issue-services/api/v1/$process-message`
contains only: identifier (lokalni-identifikator-slucaja), verificationStatus
(confirmed), code (J00), subject (MBO 999990260), onsetDateTime, note. No
asserter, no clinicalStatus.

CEZIH still returns HTTP 400 with:

```json
{
  "code": "ERR_HEALTH_ISSUE_2000",
  "display": "Unexpected error occurred while executing state machine perform."
}
```

Extsigner signing succeeded cleanly in all attempts (Certilia mobile push →
approve → signed bundle returned). The failure is strictly on CEZIH's
state-machine side after our POST.

### What's interesting — and what to investigate

**The failing 2.1 bundle shape is byte-for-byte comparable to the now-working
2.2 bundle shape** (2.2 was fixed earlier today by commits `6b29da4` H1 drop
asserter + `90ab916` H2a keep lokalni-identifikator + `77cf229` persistence).
Both go through the same `build_condition_create` helper and both end up
asserter-free. The only deltas are:

- `MessageHeader.eventCoding.code` — "2.1" vs "2.2"
- `2.2` path strips any global-identifier slice (defensive, not relevant here)

So whatever CEZIH's state machine rejects on 2.1 is **specific to the 2.1
event**, not to the Condition resource's shape. Ideas to chase, in order:

1. **Check what bundle shape a previously-working TC16 smart-card run used.**
   Phase 18 (2026-04-13) marked TC16 verified. Git blame
   `fhir_api/condition.py` + `builders/condition.py` for changes between
   2026-04-13 and now. Anything else besides asserter handling that might
   matter? The refactor at commit `14377a3` split the message_builder —
   maybe a field was dropped or a profile URL was lost in the split.
2. **Does 2.1 need meta.profile on the Condition or MessageHeader?**
   `build_message_bundle` accepts `profile_urls` but `create_case` does not
   pass any. Visits (1.1/1.2/1.3) do pass profile_urls for Encounter. Check
   if Simplifier `cezih.hr.condition-management/0.2.1` contains an
   `hr-create-health-issue-message` profile and whether it's slice-scoped on
   MessageHeader.meta.profile. See `backend/app/services/cezih/builders/common.py`
   for existing profile constants.
3. **`verificationStatus="confirmed"` at create time.** The default was
   changed to "confirmed" specifically because 2.5 resolve was rejecting
   "unconfirmed" cases. But maybe CEZIH's state machine no longer accepts
   `confirmed` at 2.1 create and wants `provisional`/`differential`/blank.
   Pull `hr-create-health-issue-message` from Simplifier and check the
   binding.
4. **`source.endpoint`** is `urn:oid:1.2.162.1.999001464` — the institution
   OID. Compare to what 2.2 (now working) sent. If identical, rule out.
5. **Pre-flight GET warning.** Every attempt logs
   `Case: pre-flight GET failed (FHIR error: Missing mandatory parameter
   "patient" in the query.), POST may also fail`. Known-harmless per
   `TC16-case-session-preflight-fix.md`, but sanity-check by hooking a
   patient-scoped GET temporarily to see if the 400 pre-flight is really
   warming the session.
6. **CEZIH test-env transient.** Per
   `2026-04-20-cezih-test-env-fhir-server-down.md`, the env has flaked
   before with this exact code. Retry the same request 30–60 s later before
   assuming the code is still wrong.

### Concrete diagnostic commands

```bash
# SSH tail (prod)
ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose logs backend --tail 300 | grep -E 'Case POST bundle|Case response|CEZIH response.*health-issue|ERR_HEALTH|pre-flight'"

# Verify the asserter-drop fix is actually running in the container
ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose exec -T backend grep -n 'H1 mirror' app/services/cezih/fhir_api/condition.py"

# Pull Simplifier profile package (for hypothesis 2+3)
curl -sL https://packages.simplifier.net/cezih.hr.condition-management/0.2.1 -o /tmp/cm.tgz && mkdir -p /tmp/cm && tar xzf /tmp/cm.tgz -C /tmp/cm && ls /tmp/cm/package | grep -i 'create-health-issue'
```

### Files most likely to touch

- `backend/app/services/cezih/fhir_api/condition.py` — `create_case` entry
  point; currently pops asserter (line 167). If the fix is a profile URL,
  pass `profile_urls={...}` to `build_message_bundle` here (like
  `dispatchers/visits.py:351` does for Encounter 1.1).
- `backend/app/services/cezih/builders/condition.py` — `build_condition_create`
  at line 29. If a field needs to be removed or changed from the Condition
  resource itself (e.g., drop `note`, change `verificationStatus` default),
  do it here.
- `backend/app/services/cezih/builders/common.py` — profile URL constants.
  May need to add `PROFILE_CONDITION_CREATE` or similar.

## What's complete vs pending in this E2E sweep

Sweep goal: every TC verified end-to-end on prod via Certilia mobile on
patient **GORAN PACPRIVATNICI19** (id `245ec690-a024-4c90-b6d3-62621eca4d47`,
MBO `999990260`), then repeat the clinical half (TC12–22) on the foreign
passport patient, then EHIC. Confirm UI table updates after each action and
persistence after page reload.

### Done (Croatian patient, Certilia mobile)

| TC | Description | Status |
|----|-------------|--------|
| TC1/2/3 | Auth (card/cloud/IS) | completed |
| TC4/5 | Signing (card/cloud) | completed (mobile path exercised implicitly) |
| TC7 | SVCM ITI-96 code list sync | completed |
| TC8 | SVCM ITI-95 concept set sync | completed |
| TC9 | mCSD ITI-90 subject registry | completed |
| TC10 | PDQm ITI-78 patient demographics | completed |
| TC12 | Create visit 1.1 | completed |
| TC13 | Update visit 1.2 | completed |
| TC14 | Close visit 1.3 | completed — but on reload the row appeared to revert from "Završena" to "U tijeku" without a Kraj timestamp. Re-verify before moving on. |
| TC15 | QEDm retrieve cases | completed |

### Pending

| TC | Description | Notes |
|----|-------------|-------|
| TC11 | PMIR foreigner registration (passport + EHIC) | Both identifiers in `testni_pacijent.txt`. Passport `TEST187229207429124774553873810518644589945`, EHIC `TEST20251215113521HP`. |
| TC16 | Create case 2.1 — Croatian | **BLOCKED — see Open blocker above** |
| TC17 | Case lifecycle 2.2-2.7 | 2.2 (Ponavljajući) and 2.6 (Data update) fixed today (77cf229, 5cb984c) but need a real live run-through. 2.4/2.5/2.9 verified earlier (b314a4e). 2.3 Remisija still needs a live check. 2.7 is intentionally not shipped. |
| TC18 | ITI-65 send clinical document | Requires a Nalaz on the patient — use existing one or create a new one first. |
| TC19 | ITI-65 replace clinical document | |
| TC20 | ITI-65 cancel clinical document (via replace with OID) | Per `TC20-cancel-document-blocker.md` — re-verified 2026-04-21 on fresh Ref 1402943. |
| TC21 | ITI-67 search clinical documents | |
| TC22 | ITI-68 retrieve clinical document | |
| Foreign sweep | Repeat TC12-22 on passport patient, then EHIC | Run after Croatian is fully green. |

### Croatian patient re-verification punch list

1. TC14: after reload, confirm the last-closed visit's status is "Završena"
   with a Kraj timestamp. If not, that close didn't persist — file a
   separate blocker.
2. TC16 — fix and verify per section above.
3. TC17 lifecycle, one click per action:
   - Use an existing "Potvrđen" case (e.g., J11 Aktivan cezih_case_id
     `cmo788c4o020rhb85dnikeniv` — confirm still there).
   - 2.3 Remisija → row flips to Remisija, reload persists.
   - 2.4 Resolve → row flips to Završen + Završetak date.
   - 2.5 Relapse → row flips back to Aktivan.
   - 2.6 Izmijeni podatke → change only `note`, submit. Expect HTTP 200.
   - 2.2 Ponavljajući → creates a NEW case row with the same ICD linked to
     parent. Expect HTTP 200 + new `cezih_case_id`.
   - 2.9 Ponovno otvori (Reopen) → from a resolved case, flips back to
     Aktivan.
4. TC18 Send Nalaz:
   - Go to Nalazi tab → "Novi nalaz" or pick existing.
   - Click "Pošalji e-Nalaze" → Certilia mobile not required for ITI-65
     (unsigned by design, per `2026-04-20-cezih-test-env-fhir-server-down.md`).
   - Confirm row shows "Poslano" with CEZIH refId + OID. Reload.
5. TC19 Replace: open a sent Nalaz, edit content, save, send replace.
   Confirm CEZIH HTTP 200 and UI updates.
6. TC20 Storno: on a sent Nalaz, click Storniraj. Confirm the OID-lookup
   path runs (finding 2026-04-20) and CEZIH accepts.
7. TC21/22: the e-Karton page for the patient lists CEZIH documents (ITI-67
   search). Click one to retrieve (ITI-68).
8. TC11 foreigner:
   - Create a new foreign patient with passport
     `TEST187229207429124774553873810518644589945`.
   - Go to CEZIH tab → "Registriraj stranca" (PMIR path).
   - Expect new cezih_id returned. Reload confirms persistence.
   - Delete the test patient afterwards or reuse.
   - Repeat with EHIC `TEST20251215113521HP`.

### Foreign patient sweep

Once Croatian is fully green (all TCs including TC11 passport + EHIC),
repeat TC12–TC22 (visits, cases, documents) on the foreign patient created
in TC11 passport. Then once more on EHIC. Key identifier note: foreign
patients use `jedinstveni-identifikator-pacijenta` instead of MBO — this is
already handled in the backend (see CLAUDE.md FHIR identifier systems).

## Environment / tools / credentials

- **App:** https://app.hmdigital.hr (logged-in user Admin Marko Kovačević).
- **SSH:** `ssh root@178.104.169.150` (key `~/.ssh/id_ed25519`). Project
  path `/opt/medical-mvp`.
- **Deploy:** push to `main` triggers `.github/workflows/deploy.yml`.
  Watch with `gh run watch <id> --exit-status` or
  `gh run list --limit 3 --workflow=deploy.yml`.
- **Chrome DevTools MCP:** use `list_pages`, `select_page`, `take_snapshot`,
  `click`, `fill`, `wait_for`, `list_console_messages`,
  `list_network_requests`, `navigate_page`. The page is usually already
  navigated to `app.hmdigital.hr` — `list_pages` first.
- **Test doctor:** MBO 500604936, HZJZ 7659059, TESTNI55 TESTNIPREZIME55.
- **Test institution:** 999001464 — HM DIGITAL ordinacija.
- **Croatian patient:** GORAN PACPRIVATNICI19h, id
  `245ec690-a024-4c90-b6d3-62621eca4d47`, OIB 99999900187, MBO 999990260,
  CEZIH client_id `d9fe4a5d-4ca2-4e21-8ad3-0016d78ce02f`.
- **Foreign:** passport `TEST187229207429124774553873810518644589945`,
  EHIC `TEST20251215113521HP`.
- **Mobile signing:** Certilia mobile already configured and ready on the
  user's phone — expect a push notification on each signed request; the
  user must approve within ~2 minutes.

## Memory entries relevant to this session

- `project_cezih_case_state_machine.md` — 2.5 on unconfirmed fails; 2.7
  minimal payload; fresh case preferred over 2.6 flip.
- `project_cezih_fhir_compliance.md` — identifier systems,
  clinicalStatus rules, ITI-67/68 quirks.
- `project_cezih_signing_rules.md` — both methods work for ALL actions.
- `project_cezih_session_establishment.md` — pre-flight GET required.
- `feedback_never_block_doctor_download.md` — PDF downloads must always
  succeed.
- `feedback_no_redundant_user_hints.md` — keep toast/error copy terse.

## Next actions (start here in new chat)

1. Read this handoff end-to-end. Don't retry TC16 until you've formed a
   hypothesis.
2. Pull the Simplifier `cezih.hr.condition-management/0.2.1` package and
   inspect `hr-create-health-issue-message.json`:
   - Is MessageHeader.meta.profile required for 2.1?
   - Is Condition.verificationStatus bound to a value set that excludes
     `confirmed` on create?
   - Is there an invariant on Condition.note or Condition.onsetDateTime
     slicing that we're violating?
3. Compare the current 2.1 wire payload (in backend logs at
   `2026-04-21 07:16:41`) to the most-recent successful 2.2 payload from
   today. If structurally identical save for event code, suspect MessageHeader
   profile first.
4. Make the smallest change you can justify, commit with a
   `fix(cezih): …` message, push, watch deploy, then rerun TC16 via
   Chrome MCP. User approves mobile signing.
5. If TC16 passes, continue down the pending list — don't stop to polish.
   Mark each task completed via TaskUpdate.
6. Don't mark TC14 complete without re-verifying the "Završena" status
   persists after reload. That flag in the summary was suspicious.
7. Do the foreign sweep last. Don't start it until Croatian TC11–TC22 are
   all live-verified.

## Don't

- Don't switch to smart card to "unblock" TC16. Mobile must work on its
  own for certification.
- Don't add a CEZIH Condition delete action (hard rule).
- Don't run destructive git commands or force-push.
- Don't bypass the pre-flight GET warning by rewriting it to patient-scoped
  — already tried, regressed to 500 (see
  `TC16-case-session-preflight-fix.md`).
- Don't use the TodoWrite tool for this — the task list is already set up,
  just update it with TaskUpdate.

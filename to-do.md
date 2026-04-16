# CEZIH Exam — Post-Failure TODO (2026-04-16)

Failed on-site exam at HZZO Zagreb. Examiner feedback → 4 blocking items below.

**Afternoon research (2026-04-16):** Downloaded + parsed Simplifier
`cezih.hr.condition-management/0.2.1` (all 10 StructureDefinitions + 11
example bundles) and `cezih.hr.cezih-osnova/1.0.1`. Full report in
`docs/CEZIH/findings/spec-research-2026-04-16.md`. Key findings:

- Our case-lifecycle **event codes have been swapped the entire time** — 2.4
  is Resolve (not Relapse), 2.5 is Relapse (not Resolve), 2.7 is Delete, 2.8/2.9
  are Reopen variants. Reshapes #5 entirely.
- Found exact identifier systems for passport (`.../putovnica`) and EHIC
  (`.../europska-kartica`). Unblocks #2.
- Confirmed annotation-type CodeSystem (code=1 "Razlog brisanja", etc.).
- **Delete stays OUT** per user directive — even though spec technically
  permits it. See `CLAUDE.md` "Case delete — HARD RULE" and memory
  `project_cezih_no_delete.md`.

---

## 1. Both signing options must work (card + mobile app) — IMPLEMENTED LOCALLY (2026-04-16), not yet deployed

**Implementation (uncommitted, local Docker only):**
- DB: `users.cezih_signing_method VARCHAR(20)` — nullable, check constraint
  `IN ('smartcard','extsigner')`. NULL = use system default. Migration
  `028_add_cezih_signing_method.py`.
- Backend dispatcher: new `current_user_id` + `current_db_session` ContextVars
  in `cezih/client.py`, set by `_require_audit_params`. New helper
  `_resolve_signing_method()` in `message_builder.py:269` reads the per-user
  column, falls back to `settings.CEZIH_SIGNING_METHOD`, then to `"extsigner"`.
- Smart card JWS root-cause fix in `_add_signature_smartcard()`
  (`message_builder.py:400`):
  - Built `signature` element WITHOUT `data` field (spec says it MUST be excluded
    from the canonical payload).
  - Switched payload serialization from plain `json.dumps(separators=(",",":"))`
    to `jcs.canonicalize()` (RFC 8785: recursive key sort, canonical numbers,
    spec-compliant string escapes). `jcs>=0.2.1` added to `pyproject.toml`.
  - The Rust agent (`local-agent/src-tauri/src/signing.rs`) needed no change —
    it already produces standard RFC 7515 compact JWS with `alg`, `kid`, `jwk`,
    `x5c` and double-base64 wrapping.
- Schemas: `UserRead` + `UserUpdate` expose `cezih_signing_method`.
- Frontend selector in `Postavke → Korisnici` edit dialog
  (`user-form-dialog.tsx`): "Zadano (sustav) / Mobitel (Certilia) / Kartica
  (AKD)". Sentinel `"default"` only in UI; null on the wire. Constants in
  `lib/constants.ts`. Type in `lib/types.ts`.

**Verified locally:**
- [x] Backend boots clean with new dependency, migration applied (column NULL for
  all existing users → preserves current production behavior).
- [x] `tsc --noEmit` clean for changed frontend files (one pre-existing error in
  `cezih/page.tsx` unrelated to this work).
- [x] DB column + check constraint inspected via `\d users`.

**Still to do (for this item):**
- [ ] Manual UI smoke: open `/postavke/korisnici`, edit a doctor, see the new
  selector, change to "Mobitel" → save → reopen → value persists.
- [ ] Live extsigner E2E with per-user pref set to "Mobitel" — must still work
  (regression check on the working path).
- [ ] Live smartcard E2E with per-user pref set to "Kartica" — primary
  pass/fail criterion for the JWS fix. Pass = CEZIH 200 OK / message
  processed. Fail = `ERR_DS_1002` again → capture canonical payload, JOSE
  header, JWS compact, OperationOutcome to memory and stop iterating
  (per plan).
- [ ] PMIR (TC11) re-run with smart card user — only if Encounter passes.
- [ ] Commit + push to `main` to trigger auto-deploy. Production
  (`app.hmdigital.hr`) currently has the OLD code — none of the above is live.

---

## 2. Foreigner search by passport or EHIC number

**Requirement (Croatian):**
> "Dodaj pretraživanje stranca po broju putovnice ili EHIC"

**Current state:**
- PMIR flow registers foreigners (TC11 verified) — creates `Patient/{id}` with `jedinstveni-identifikator-pacijenta`
- Patient search (PDQm / ITI-78) currently only by MBO
- No UI to search existing foreigners by passport number or EHIC card number

**Resolved (2026-04-16 research):**
- Passport system URI: `http://fhir.cezih.hr/specifikacije/identifikatori/putovnica`
- EHIC system URI: `http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica`
- No new endpoint needed — extend existing PDQm ITI-78 query with these
  `identifier={system}|{value}` variants. Source: `HRRegisterPatient` slice
  definitions in Simplifier `cezih.hr.cezih-osnova/1.0.1`.

**Need:**
- [ ] Backend: add the two identifier systems to the PDQm search path (same
  transaction already used for MBO lookup)
- [ ] Frontend: add passport / EHIC fields to foreigner search UI
- [ ] Verify against real CEZIH with test-env foreigner record created via TC11

---

## 3. AID per ordinacija — short code on FHIR messages alongside OID — DEFERRED (not important for now)

**Requirement (Croatian):**
> "AID svaku ordinaciju pod npr. HM-Medical-001 NOT OID"

**Confirmed scope (user answer: B/C):**
- This is a **FHIR-level** requirement, not internal-only
- Every CEZIH request must carry a short human-readable code for the ordinacija
- Goes on `Organization.identifier` **alongside** the existing OID-based identifier
- Example format: `HM-Medical-001` (unique per tenant/ordinacija)

**Current state:**
- Tenant has CEZIH OID (e.g. `999001464`) → single identifier entry on FHIR
- No short AID field, no second `Organization.identifier` entry emitted

**Need:**
- [ ] DB: add `aid` column on tenant (unique, `HM-Medical-NNN` format)
- [ ] Auto-generate on tenant creation (sequential, per-admin scope)
- [ ] Backfill existing tenants with deterministic codes
- [ ] message_builder: add second `Organization.identifier` entry carrying the AID
- [ ] Decide identifier `system` URI (check CEZIH Simplifier packages for the right one)
- [ ] Admin UI: display AID on tenant settings (read-only)
- [ ] Verify on real CEZIH request — ensure no `system`/`value` validation error

---

## 4. Cases table regression after recent FE changes — DONE (commit dd9f8bf, verified 2026-04-16)

**Root causes found (two independent bugs):**

1. `send-nalaz-dialog.tsx:63-64` — strict `=== "active"` / `=== "in-progress"` filters hid any case whose `clinical_status` was anything else (recurrence, remission, empty). Swapped to terminal-state exclusion.
2. `useCreateCase` — invalidated the cases query, which triggered a refetch against CEZIH `/ihe-qedm-services` (read replica). That replica is eventually consistent with `/health-issue-services` (write), so the just-created case wasn't yet indexed and vanished from the table. Now optimistically inserted into the cache using the returned `cezih_case_id`.

**Verified in prod:** created J00 case on patient MARINA PACPRIVATNICI47 → appeared at top of Slučajevi table immediately (19 → 20 rows), toast fired, no console errors.

---

## 5. Case actions — ROOT CAUSE FOUND, fix pending

**Status (2026-04-16 afternoon):** Our CASE_ACTION_MAP event codes are swapped
vs spec. Two live tests today (B26 pre-existing and J00 fresh same-session)
both returned `ERR_HEALTH_ISSUE_2004` on "Zatvori". Root cause is not state
machine, not roles — wrong event codes going out.

### Ground truth per Simplifier `cezih.hr.condition-management/0.2.1`

| Event code | Spec meaning | Our current code | Correct payload |
|------------|--------------|-----------------|-----------------|
| 2.1 | Create | 2.1 ✓ | vs + onset + code |
| 2.2 | Create recurrence | 2.2 ✓ | vs + onset + code |
| 2.3 | Remission | 2.3 ✓ | minimal (id + subject) |
| **2.4** | **Resolve** | 2.5 ❌ | cs=resolved FIXED + abatementDateTime[1..1] |
| **2.5** | **Relapse** | 2.4 ❌ | minimal (id + subject) |
| 2.6 | Data update | 2.6 ✓ | optional fields |
| 2.7 | Delete | (removed, was 2.8) | **DO NOT SHIP** — product rule |
| 2.8 | Reopen after delete | — | unreachable (we don't delete) |
| **2.9** | **Reopen after resolve** | reopen=2.7 ❌ | minimal (id + subject) |

Full differential + examples analyzed in
`docs/CEZIH/findings/spec-research-2026-04-16.md`.

### Why today's tests failed

- Our "Zatvori" sent event code **2.5** → CEZIH routed to the Relapse profile
  → state machine rejected "relapse on active case" → ERR_HEALTH_ISSUE_2004.
  Not a state-machine quirk; wrong code.
- Yesterday's "Relaps works" was our code **2.4** with resolve-shaped payload
  (cs=resolved + abatement) → CEZIH routed to Resolve profile → 200. We had
  been calling it Relaps in the UI but CEZIH accepted it as Resolve.
- Previously blaming CEZIH for a "2.4/2.5 profile swap" — wrong; we swapped
  them ourselves.

### Fixes to ship (single PR)

Backend `message_builder.py`:
- [ ] `CASE_ACTION_MAP`: swap 2.4/2.5; change reopen from 2.7 to 2.9. Keep
  delete OUT per hard rule.
- [ ] `CASE_EVENT_PROFILE`: rewrite —
  - 2.4: `cs_fixed="resolved"`, `abatement_required=True`
  - 2.3 / 2.5 / 2.9: `minimal=True`
  - 2.1 / 2.2: `vs_required=True`, `onset_required=True`
- [ ] `build_condition_update_status`: branch on event code — 2.4 sets
  `clinicalStatus.coding = {system: ".../condition-clinical", code: "resolved"}`
  + `abatementDateTime = now` (or user-supplied end date).
- [ ] `_CEZIH_ERROR_MESSAGES_HR` ERR_HEALTH_ISSUE_2004: stop blaming user for
  "unconfirmed" — new text should say the action was invalid in current case
  state.

Frontend `case-management.tsx`:
- [ ] `getAvailableActions` reopen rule: show only when
  `clinical_status === "resolved"` (since 2.9 is reopen-after-resolve only).
- [ ] Help text: drop the "only Potvrđen" gate — that was a symptom, not a
  real constraint. Add "Zatvaranje je moguće za aktivan i potvrđen slučaj
  kreiran kao Potvrđen" (pending live-verify).

Memory cleanup:
- [ ] Rewrite `project_cezih_case_state_machine.md` — no CEZIH 2.4/2.5 swap;
  our codes were swapped.
- [ ] Update `project_cezih_fhir_compliance.md` — "NO clinicalStatus in
  message body" is true for 2.3/2.5/2.9, FALSE for 2.4 (cs=resolved + abatement).

### Live-verify plan (post-deploy, each needs one mobile signing)

- [ ] 2.4 Resolve on fresh active+confirmed case → expect 200
- [ ] 2.5 Relapse on a `remission` case → expect 200
- [ ] 2.9 Reopen on the just-resolved case → expect 200
- [ ] 2.3 Remisija regression on active case → expect 200

---

## Priority order

1. **#1** — local impl done; needs UI smoke + live CEZIH verify (both methods)
   + commit/push to deploy
2. **#5** — case actions re-enabled; live verify against real CEZIH (test env)
3. **#2** — foreigner search by passport / EHIC (PDQm)
4. **#3** — DEFERRED (AID on FHIR Organization.identifier — scope confirmed, not urgent)

## Deployment status

**Production (`app.hmdigital.hr`):** still on commit `4f949db`
(`refactor(cezih): remove 2.8 Delete`). None of the #1 work above is live.
Push to `main` will auto-deploy backend + frontend; agent is unchanged so no
new agent release is triggered.

## Exam re-take

- Next available date: TBD with HZZO helpdesk
- Must re-verify all 17 previously passing TCs still green after changes

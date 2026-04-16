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

## 1. Both signing options must work (card + mobile app) — DEPLOYED + PARTIALLY VERIFIED

**HARD RULE: Both methods work independently for ALL CEZIH actions. No fallbacks. No "preferred" method.**

**Deployed:** Commit `b314a4e` pushed to `main`, auto-deployed to production
(`app.hmdigital.hr`). Per-user signing preference live.

**Implementation:**
- DB: `users.cezih_signing_method VARCHAR(20)` — nullable, check constraint
  `IN ('smartcard','extsigner')`. NULL = use system default. Migration
  `028_add_cezih_signing_method.py`.
- Backend dispatcher: `_resolve_signing_method()` in `message_builder.py:269`
  reads per-user column, falls back to `settings.CEZIH_SIGNING_METHOD`,
  then to `"extsigner"`.
- Smart card JWS: `_add_signature_smartcard()` uses `jcs.canonicalize()`
  (RFC 8785), excludes `data` from canonical payload.
- Frontend selector: "Zadano (sustav) / Mobitel (Certilia) / Kartica (AKD)"
  in Postavke → Korisnici edit dialog.

**Extsigner (Certilia mobile) — ALL PASS (regression-tested 2026-04-16 E2E):**

| Test | Action | Event Code | Result |
|------|--------|------------|--------|
| TC12 Create Visit | Create | — | ✅ Visit count 2→3 |
| TC16 Create Case (S00.3) | Create | 2.1 | ✅ Case appeared |
| 2.3 Remission (S00.3) | Remisija | 2.3 | ✅ Aktivan→Remisija |
| 2.5 Relaps (I10) | Relaps | 2.5 | ✅ Remisija→Relaps |
| 2.4 Resolve (J09) | Zatvori | 2.4 | ✅ Aktivan→Zatvoren |
| 2.9 Reopen (J09) | Ponovno otvori | 2.9 | ✅ Zatvoren→Aktivan |

**Smartcard (AKD) — STILL BROKEN (P0 — dual signing rule requires both methods to work):**

| Test | Action | Event Code | Result |
|------|--------|------------|--------|
| A57 Remisija | Remisija | 2.3 | ❌ ERR_DS_1002 |

Smartcard JWS flow completes (JCS→agent→JWS with kid/alg=ES384) but CEZIH
rejects signature verification with `ERR_DS_1002`. Same error as before the
JCS fix — canonical serialization didn't resolve it.

**Still to do:**
- [ ] Debug smartcard ERR_DS_1002 — capture full JWS (header, payload, sig),
  compare byte-for-byte with what extsigner produces. Possible causes:
  - ES384 vs RS256 algorithm mismatch (CEZIH may only accept RSA)
  - JWK/x5c format in JOSE header
  - Certificate chain validation failure
  - Kid format mismatch
- [ ] PMIR (TC11) re-run with smart card user — only if Encounter passes

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

## 5. Case actions — VERIFIED LIVE (commit b314a4e, E2E 2026-04-16)

**Status: DONE.** Case action event codes fixed and verified against live CEZIH
with all 4 transition types.

### Ground truth per Simplifier `cezih.hr.condition-management/0.2.1`

| Event code | Meaning | clinicalStatus | E2E Result |
|------------|---------|---------------|------------|
| 2.1 | Create | (new) | ✅ prior session |
| 2.2 | Create recurrence | active | ✅ prior session |
| 2.3 | Remission | remission | ✅ A57 Aktivan→Remisija |
| 2.4 | Resolve (Zatvori) | resolved | ✅ S00.3 Aktivan→Zatvoren |
| 2.5 | Relapse | relapse | ✅ A57 Remisija→Relaps |
| 2.6 | Data update | (preserved) | ✅ prior session |
| 2.7 | Delete | — | **DO NOT SHIP** per hard rule |
| 2.9 | Reopen after resolve | active | ✅ S00.3 Zatvoren→Aktivan |

### What was fixed (commit b314a4e)

Backend `message_builder.py`:
- `CASE_ACTION_MAP`: swapped 2.4/2.5; changed reopen from 2.7 to 2.9
- `CASE_EVENT_PROFILE`: 2.4 sets cs=resolved + abatementDateTime; others minimal
- `build_condition_status_update`: handles 2.4 resolve correctly
- `ERR_HEALTH_ISSUE_2004` error message: updated to be state-agnostic

Frontend `case-management.tsx`:
- `getAvailableActions`: reopen only on `resolved`; relaps on `remission`; correct gates
- Help text: removed misleading "only Potvrđen" constraint

Tests `test_cezih_new_modules.py`:
- Updated assertions for correct codes; added `"delete" not in CASE_ACTION_MAP` guard

### Frontend state machine (verified in UI)

| Case status | Available actions |
|-------------|-------------------|
| Aktivan + Potvrđen | Remisija, Zatvori |
| Remisija + Potvrđen | Relaps, Zatvori |
| Zatvoren + Potvrđen | Ponovno otvori |
| Aktivan + Nepotvrđen | Remisija, Zatvori |

---

## Priority order

1. **#1** — smartcard ERR_DS_1002 remains open; extsigner fully working
2. **#2** — foreigner search by passport / EHIC (PDQm)
3. **#3** — DEFERRED (AID on FHIR Organization.identifier — scope confirmed, not urgent)

## Deployment status

**Production (`app.hmdigital.hr`):** commit `b314a4e`
(`fix(cezih): correct case action event codes + signing infrastructure`).
All #1 and #5 changes are live and verified.

## Exam re-take

- Next available date: TBD with HZZO helpdesk
- Must re-verify all 17 previously passing TCs still green after changes
- Smartcard signing is the remaining blocker — examiner specifically requires both methods

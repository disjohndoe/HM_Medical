# CEZIH Exam — Post-Failure TODO (2026-04-16)

Failed on-site exam at HZZO Zagreb. Examiner feedback → 4 blocking items below.

---

## 1. Both signing options must work (card + mobile app)

**Current state:**
- `backend/app/config.py:64` — `CEZIH_SIGNING_METHOD` is a global env var (`extsigner` | `smartcard`)
- `extsigner` path (Certilia remote / mobile app) → **working**
- `smartcard` path (NCrypt JWS via local agent) → **broken** (CEZIH rejects the JWS format)
- No UI selector — user cannot choose per session/action

**Confirmed scope (user answer: B1):**
- Per-user default in Postavke — each doctor picks "kartica" or "mobitel" once
- Move `CEZIH_SIGNING_METHOD` from env-wide config → per-user column on `users` table
- Default for new users: `mobitel` (since that's what works today)

**Need:**
- [ ] DB: add `cezih_signing_method` on User (`smartcard` | `extsigner`, default `extsigner`)
- [ ] Backend: read user preference in `message_builder._add_signature`, fall back to env default
- [ ] Fix smart-card JWS so CEZIH accepts it (ES384 via AKD card) — root cause TBD
- [ ] Frontend: selector in Postavke (Settings → CEZIH → Potpisivanje) with helper text
- [ ] Verify both paths end-to-end against real CEZIH (Encounter + ITI-65 + PMIR)

---

## 2. Foreigner search by passport or EHIC number

**Requirement (Croatian):**
> "Dodaj pretraživanje stranca po broju putovnice ili EHIC"

**Current state:**
- PMIR flow registers foreigners (TC11 verified) — creates `Patient/{id}` with `jedinstveni-identifikator-pacijenta`
- Patient search (PDQm / ITI-78) currently only by MBO
- No UI to search existing foreigners by passport number or EHIC card number

**Need:**
- [ ] Backend: extend PDQm search (or add new endpoint) to query CEZIH by:
  - Passport number (`identifier` type = passport, system per CEZIH spec)
  - EHIC card number (identifier type = EHIC)
- [ ] Frontend: add passport / EHIC fields to foreigner search UI
- [ ] Verify against real CEZIH with test-env foreigner record

**Open questions:**
- Exact FHIR `identifier.system` URIs for passport + EHIC in CEZIH
- Is this a new PDQm identifier type, or a dedicated endpoint?

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

## 5. Case actions — normal doctor flow (UI + spec-compliant payloads)

**Fixes applied (2026-04-16, commit pending):**

Authoritative spec source: `cezih.hr.condition-management/0.2.1` on Simplifier
(separate package from `cezih.osnova`; contains all 8 message StructureDefinitions).

- **2.8 Delete** — `build_condition_delete` now emits `Condition.note` with razlog
  (annotation-type "4"); API schema + dispatcher thread `note` through; UI opens
  a required-razlog Dialog when Obriši is picked. Re-enabled in `getAvailableActions`.
- **2.7 Reopen** — current minimal payload already matches spec (no note required,
  only globalni-id + subject). Re-enabled in `getAvailableActions` for `resolved` cases.
- **2.5 Resolve / 2.8 Delete UI eligibility** — dropped the `_local`-only hack.
  Now shown on any case where `verification_status === "confirmed"` (plus session
  cases). CEZIH's Croatian error translation surfaces ERR_HEALTH_ISSUE_2004 rejections.

**Still to verify live:**
- [ ] E2E on real CEZIH: create active+confirmed → 2.8 Delete with razlog → 200
- [ ] E2E on real CEZIH: 2.5 Resolve on imported confirmed case (disambiguates H2)
- [ ] E2E on real CEZIH: 2.7 Reopen on resolved case
- [ ] E2E on real CEZIH: 2.5 Resolve on recurrence+confirmed case (disambiguates H1)

**Known test-env quirks (unchanged):**
- 2.4 Relaps sends resolve-shaped payload (cs=resolved + abatement) per test-env
  profile swap — flip `CEZIH_RELAPSE_SEMANTIC_CORRECT=True` once HZZO fixes routing.

---

## Priority order

1. **#5** — case actions re-enabled; live verify against real CEZIH (test env)
2. **#1** — fix smart card JWS + user-selectable signing method
3. **#2** — foreigner search by passport / EHIC (PDQm)
4. **#3** — DEFERRED (AID on FHIR Organization.identifier — scope confirmed, not urgent)

## Exam re-take

- Next available date: TBD with HZZO helpdesk
- Must re-verify all 17 previously passing TCs still green after changes

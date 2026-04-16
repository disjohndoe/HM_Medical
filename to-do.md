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

## 5. Case actions failing — Close / Remission / Recurring (investigation pending)

**Known issues (from `project_cezih_case_state_machine.md` + live testing 2026-04-16):**

- **2.5 Resolve (Zatvori)** — CEZIH rejects with `ERR_HEALTH_ISSUE_2004` on `unconfirmed` cases. Only verified working path: `create-as-confirmed → active+confirmed → 2.5 Resolve → 200`.
- **2.5 Resolve on a recurrence case** — fails even after 2.6 flip to `confirmed`. Open issue (H1: CEZIH blocks `recurrence→resolved` regardless; H2: state-machine view still sees original unconfirmed). Need controlled repro.
- **2.7 Reopen** — requires `razlog brisanja` in payload (`himgmt-1` rule). Current minimal payload rejected. UI hides it pending backend fix (commit `e8edd9c`).
- **2.8 Delete** — same ERR_HEALTH_ISSUE_2004 rule as 2.5; UI hidden pending backend fix.
- **2.3 Remisija** — ? (need to re-verify; memory file notes "Remisija profile requires MINIMAL payload (no cs, no abatement)")
- **2.2 Ponavljajući (create_recurring)** — ? (commit `ddad4b9` routed it via create-recurrence path; memory says profile `hr-create-health-issue-recurrence-message|0.1` forbids identifier)

**Need:**
- [ ] Reproduce each action against real CEZIH (test env) with explicit state: active+confirmed, active+unconfirmed, recurrence+confirmed
- [ ] Capture error payloads from backend logs per action
- [ ] Fix the failing ones — prefer payload changes over hiding actions from UI

---

## Priority order

1. **#4** — regression blocking normal flow, likely quick fix
2. **#1** — fix smart card JWS + user-selectable signing method
3. **#2** — foreigner search by passport / EHIC (PDQm)
4. **#3** — DEFERRED (AID on FHIR Organization.identifier — scope confirmed, not urgent)

## Exam re-take

- Next available date: TBD with HZZO helpdesk
- Must re-verify all 17 previously passing TCs still green after changes

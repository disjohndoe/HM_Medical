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

## 1. Both signing options must work (card + mobile app) — ✅ DONE (2026-04-16)

**HARD RULE: Both methods work independently for ALL CEZIH actions. No fallbacks. No "preferred" method.**

**Both methods VERIFIED on production 2026-04-16.**

### Root cause of ERR_DS_1002 (resolved)

Two combined bugs in smartcard JWS path:

1. **Canonicalization** — backend used `json.dumps` (compact, insertion order)
   instead of RFC 8785 JCS (sorted keys). CEZIH verifier reconstructs Bundle
   via JCS → hash mismatch → ERR_DS_1002.
   Fix: `jcs.canonicalize(bundle)` in `message_builder.py` (commit `ecc88ed`).

2. **JWS format** — sent attached JWS with top-level `x5c`, no `jwk`.
   CEZIH expects **detached JWS** (`header..sig`) with full EC `jwk` in JOSE
   header: `{kty, crv, x, y, kid, x5t#S256, nbf, exp, use, x5c}`.
   Fix: agent v0.13.0 — EC coords from SubjectPublicKeyInfo BLOB, detached
   output, jwk with nested x5c (commit `43393f7`).

See `docs/CEZIH/findings/smartcard-jws-format-fix.md` for full details.

### Extsigner (Certilia mobile) — ALL PASS

| Test | Action | Event Code | Result |
|------|--------|------------|--------|
| TC12 Create Visit | Create | — | ✅ |
| TC16 Create Case (S00.3) | Create | 2.1 | ✅ |
| 2.3 Remission (S00.3) | Remisija | 2.3 | ✅ |
| 2.5 Relaps (I10) | Relaps | 2.5 | ✅ |
| 2.4 Resolve (J09) | Zatvori | 2.4 | ✅ |
| 2.9 Reopen (J09) | Ponovno otvori | 2.9 | ✅ |

### Smartcard (AKD) — ALL PASS

| Test | Action | Event Code | Result |
|------|--------|------------|--------|
| TC12 Create Visit | Create | 1.1 | ✅ POST /visits → 200 (2026-04-16) |

---

## 2. Foreigner search by passport or EHIC number — ✅ DONE (2026-04-16)

**Requirement (Croatian):**
> "Dodaj pretraživanje stranca po broju putovnice ili EHIC"

**Implementation complete and deployed:**

- Backend (`service.py:32-38`): identifier system URIs mapped — `putovnica` →
  `.../identifikatori/putovnica`, `ehic` → `.../identifikatori/europska-kartica`.
  `search_patient_by_identifier()` sends `GET /patient-registry-services/api/v1/Patient?identifier={URI}|{value}`.
- Backend endpoint (`cezih.py:505`): `GET /cezih/patients/search?system=putovnica|ehic&value=...`
  returns `{cezih_id, ime, prezime, datum_rodjenja, spol}`.
- Frontend (`foreigner-registration.tsx`): `ForeignerSearch` component with
  dropdown (Putovnica / EHIC kartica), input, result card showing ime/prezime/dob/spol/cezih_id.
- Fixes deployed today: tenant_id passed through agent (commit `5d4c175`),
  proper HTTP errors (`f8ed30e`), `jedinstveni-identifikator-pacijenta` extracted as cezih_id (`9cd2bc0`).

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

1. **#2** — foreigner search by passport / EHIC (PDQm) — next up
2. **#3** — DEFERRED (AID on FHIR Organization.identifier — scope confirmed, not urgent)

## Deployment status

**Production (`app.hmdigital.hr`):** commit `99a9df3` (2026-04-16).
All items #1, #4, #5 resolved and live.

## Exam re-take

- Both signing methods now verified — examiner's requirement met
- Need to re-run full 22 TC checklist before rescheduling exam
- Schedule via helpdesk@hzzo.hr

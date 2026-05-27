---
date: 2026-05-27
topic: endpoints
status: active
---

# Cases & Nalazi now sourced from CEZIH like Visits (persist + graceful)

## Discovery

The patient CEZIH subtab showed **Posjete** (visits) sourced live from CEZIH (incl. visits
created at other providers) but **Slučajevi** (cases) and **e-Nalazi** effectively showed only
locally-created records. Root causes differed:

### Visits (the working reference) — `dispatchers/visits.py:dispatch_list_visits`
Query QEDm `Encounter` → on CEZIH error **catch + warn** (graceful) → **upsert every returned
Encounter into the `cezih_visits` mirror** → return the **full mirror**. Because remote rows
are persisted on each read, an externally-created visit stays visible even when QEDm later
lags/returns empty.

### Cases — `dispatchers/cases.py:dispatch_retrieve_cases` (BEFORE)
Queried QEDm `Condition` but did the **opposite**: hard-failed on CEZIH error
(`_raise_cezih_error`) and merged remote with local **at read time only** (`_merge_with_local`,
local-preferred), **never persisting** remote cases. With QEDm `Condition` read-side indexing
lag (">30 min, sometimes indefinite" in test env — `cases.py` comment), externally-created
cases surfaced sporadically or not at all, and any QEDm hiccup blanked the whole table. This is
why cases looked "broken" while visits worked, despite both querying the same QEDm family.

### Nalazi — `api/cezih.py:get_patient_cezih_summary` (BEFORE)
Built the e-Nalazi table **purely from the local `medical_records` table**; it never called
CEZIH. The reliable ITI-67 (MHD `DocumentReference`) search + ITI-68 retrieve paths already
existed (`fhir_api/documents.py`, `GET /cezih/documents`, `GET /cezih/e-nalaz/{ref}/document`)
but the tab didn't consume them.

## Fix

**Cases** — made `dispatch_retrieve_cases` structurally identical to `dispatch_list_visits`:
1. New `_upsert_cezih_case_from_response` persists every returned case into `cezih_cases`.
2. Graceful: CEZIH error → warn + serve mirror (no hard fail).
3. Returns the local mirror (`_fetch_fresh_local_cases_by_patient`), which now includes
   externals. `_merge_with_local` removed (persistence replaces read-time merge).
- New `CezihCase.registered` boolean column (migration `053_cezih_case_registered`, backfilled
  `true`): `True` = case this clinic created (local authoritative for clinical/verification
  status — QEDm lags our own actions; upsert only backfills NULLs + the CEZIH id); `False` =
  externally-created case mirrored from CEZIH (CEZIH-authoritative; not eligible for visit
  linking — `visit-management.tsx` already filters `c.registered !== false`).
- Remote cases without an `identifikator-slucaja` (empty `case_id`) are skipped (untrackable).
- Diagnostic log added in `retrieve_cases` (resolved identifier + entry count + parsed
  case_ids) to confirm what QEDm `Condition` actually returns. **Downgrade to debug / remove
  after prod confirmation.**

**Nalazi** — `get_patient_cezih_summary` now best-effort augments the local list with CEZIH
docs via ITI-67 (`dispatch_search_documents`, type=nalaz, status=current). Docs whose `id` is
not already a local `cezih_reference_id` are appended as **external read-only** rows
(`PatientCezihENalaz.external=True` + `content_url`); list re-sorted by date desc. Graceful:
CEZIH/agent failure → local-only list (tab never breaks). Frontend renders external rows with a
"Vanjski nalaz" badge and **only** a download action (ITI-68 via `content_url`); edit/send/
storno/replace are hidden (no local record/signature/PDF for other-provider docs).

## Evidence
- Files: `backend/app/models/cezih_case.py`, `alembic/versions/053_cezih_case_registered.py`,
  `services/cezih/dispatchers/cases.py`, `services/cezih/fhir_api/condition.py`,
  `schemas/cezih.py`, `api/cezih.py`, `frontend/src/lib/types.ts`,
  `frontend/src/components/cezih/patient-cezih-tab.tsx`.
- Local verification: ruff + eslint + `tsc --noEmit` clean; backend import/wiring asserts pass;
  migration applied + downgraded + re-applied on local DB (`registered BOOLEAN DEFAULT true NOT
  NULL`).

## Decision: graceful degradation (scoped exception to "no fallbacks")
For these read-only list views, a CEZIH outage serves the local mirror rather than erroring —
matching the established visits pattern. The local mirror is the same data, not a silent
substitute. Write/storno/sign paths keep the strict no-fallback behavior.

## Action Items / PENDING prod verification
- [ ] Confirm on prod (Croatian GORAN, ~67 cases per `2026-05-20` sweep) that QEDm `Condition`
      actually returns externally-created cases → if the diagnostic log shows 0 entries even
      for GORAN, the root cause is the QEDm query itself (identifier or missing param), not
      persistence; investigate `category`/`clinical-status` params or the consumer-portal path.
- [ ] Confirm external nalazi appear read-only + ITI-68 download works; local nalazi stay
      editable; just-sent nalaz never disappears during QEDm lag.
- [ ] Confirm both tables still render when the agent/VPN is down (graceful).
- [ ] Remove/downgrade the `retrieve_cases` diagnostic log once confirmed.

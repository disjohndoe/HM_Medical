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
- **Onset/abatement normalised to date-only at parse time** (`condition.py`). CEZIH returns a
  full ISO `onsetDateTime` (e.g. `2026-03-10T00:00:00+01:00`, 25 chars) but `cezih_cases.onset_date`
  is `String(20)` — sized for our date-only convention (locally-created cases store
  `strftime("%Y-%m-%d")`). The first external-case upsert on prod 500'd with
  `StringDataRightTruncationError` and blanked the whole tab. Slicing the FHIR date prefix
  (`[:10]`) fixes it with no schema migration and keeps the table format consistent; `icd_display`
  is also capped to its column width (300) as a boundary guard against untrusted CEZIH text.
- Diagnostic log in `retrieve_cases`/`retrieve_cases` parser kept at **debug** level
  (downgraded from info after prod confirmation 2026-05-27).

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
- **Prod E2E VERIFIED 2026-05-27** (GORAN PACPRIVATNICI19, MBO 999990260, via Chrome MCP +
  SSH logs; commits `4fb13cf` cases/nalazi + `71bdba3` onset-truncation fix):
  - `GET /cezih/cases` → 200, 94 cases (12 `registered=true` ours, 82 `registered=false`
    external mirrored from QEDm `Condition` — e.g. external `L52.0 Erythema nodosum`). Onset
    stored date-only. Slučajevi table renders, no console errors. **Confirms QEDm DOES return
    externally-created cases** — persistence approach is correct.
  - e-Nalazi: external CEZIH docs render with "Vanjski nalaz" badge + download-only action;
    issuer shown in Doktor column; local nalazi keep full edit/send/storno; no duplicates;
    sorted date desc. ITI-68 download of external ref `1620700` → 200 `application/pdf`, 43 KB,
    valid `%PDF`.

## Decision: graceful degradation (scoped exception to "no fallbacks")
For these read-only list views, a CEZIH outage serves the local mirror rather than erroring —
matching the established visits pattern. The local mirror is the same data, not a silent
substitute. Write/storno/sign paths keep the strict no-fallback behavior.

## Action Items
- [x] Confirm on prod (GORAN) that QEDm `Condition` returns externally-created cases — **YES**,
      94 entries incl. 82 externals (2026-05-27).
- [x] Confirm external nalazi appear read-only + ITI-68 download works; local nalazi stay
      editable — **DONE** (2026-05-27).
- [x] Downgrade the `retrieve_cases` diagnostic log — done (info → debug, 2026-05-27).
- [ ] (Open, non-blocking) GORAN shows 82/94 cases as `registered=false` because their local
      `cezih_cases` rows were lost across test-env DB resets while CEZIH accumulated them; they
      are correctly treated as external (CEZIH-authoritative, not visit-linkable). For a real
      clinic, self-created cases retain local rows and match → `registered=true`. Same pattern
      for the "Ordinacija Horvat"-issued docs surfacing as "Vanjski nalaz" in e-Nalazi. No code
      change needed; noted so the high external ratio for test patients isn't mistaken for a bug.
- [ ] (Optional UX parity) Visits show an "Izvor" (Naša/Ostalo) column + a "(N naše / M ostale)"
      count; the Slučajevi table does not yet visually flag `registered=false` cases. The plan
      only required externals to be non-linkable (satisfied). Adding an Izvor column to cases is
      a future nice-to-have, not in scope here.

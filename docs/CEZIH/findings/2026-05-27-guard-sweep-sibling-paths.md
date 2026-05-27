---
date: 2026-05-27
topic: documents | errors | certification
status: active
---

# Guard sweep — the 2026-05-20 fixes left sibling paths unprotected (G1–G6)

## Discovery

After the two same-day fixes for the 2026-05-20 provjera failure
(`1f5c681` live-version cancel, `b2924b0` `assert_case_registered_on_cezih`),
a review found the **same failure classes still reachable on sibling
operations** the commits did not touch. The backend is the real trust boundary
(per project game-theory rule: never trust a `case_id` or a stored OID just
because one sibling validated it). Six gaps, all now closed.

## The gaps and what was done

### G1 — Cancel/storno threaded an unvalidated case_id (P1)
`build_cancel_bundle` emits `case_id` as a slučaj link (`context["related"]`,
`fhir_api/documents.py` ~L473). `dispatch_cancel_document_canonical` fed it the
stored `record.cezih_case_id` (a possible seed CUID — the exact 2026-05-20 leak)
with no check. Send + replace-with-edit guarded it; cancel did not.
**Fix:** validate via `assert_case_registered_on_cezih` before dispatch; on an
unregistered/seed id **drop the link** (`case_id = ""`) and log — a storno must
never be blocked by an unrelated bad link (the nalaz is going away regardless).
`dispatchers/documents.py` (canonical cancel, before `_resolve_djelatnost`).

### G2 — REPLACE did not resolve the live version (P1, mirror of `1f5c681`)
`replace_document` built `relatesTo` from a stored OID with no live check; a
mirror that lagged CEZIH (external replace, or pre-`1f5c681` divergence) → replace
against a superseded version → **ERR_DOM_10035**, identical to the cancel bug.
**Fix:** `replace_document` now calls the shared resolver before building
`relatesTo`: `current` → use live OID/ref; `superseded` → resolve current head
(or clear "osvježite i uredite aktualni"); `entered-in-error` → refuse (cannot
edit a storno'd doc); `unknown` → degrade to stored OID / ITI-67 lookup (see G3).
Replaces against the live head when resolvable. `fhir_api/documents.py`.

### G3 — resolver was a dead GET-by-id no-op; reworked to search-based (P1, corrected 2026-05-27 E2E)
**First cut (WRONG, reverted same session):** made `state=unknown` **hard-fail**
both cancel and replace. Live E2E immediately exposed the flaw: the resolver
(both `1f5c681`'s original and the rename) resolved via
`GET doc-mhd-svc/.../DocumentReference/{numeric_id}`, which **CEZIH 404s for the
ids we store** (confirmed live on ref 1621712 → 404). So `state=unknown` was the
*normal* result for every document, not a rare outage — the hard-fail 502'd every
replace/storno on prod, and `1f5c681`'s entered-in-error no-op + superseded→head
walk had silently **never fired** since they too depended on the 404-ing GET.
**Correct fix:** `_resolve_live_document_head` now resolves via the **patient-scoped
ITI-67 search** (`patient.identifier` + `status=current,superseded`, then a
separate `status=entered-in-error` probe) — the same mechanism
`_lookup_document_oid` tier-3 and `_find_current_head` already use successfully.
It reads the real live status, walks `superseded → current head`, and detects
`entered-in-error` for the idempotent no-op. Only a genuine **search failure** or
an **unmatchable id** yields `state=unknown`, and on `unknown` both callers
**degrade to the stored OID / ITI-67 lookup** (the proven chain) rather than
block. The stale-OID ERR_DOM_10035 is now prevented by the search actually
resolving the current head, not by refusing the operation. Resolver renamed
`_resolve_live_document_for_cancel` → `_resolve_live_document_head` (shared by
cancel + replace).

### G4 — Deleted the legacy ITI-65 cancel path (P2, footgun removal)
`dispatch_cancel_document` / `cancel_document` (replace-style storno) had no live
resolution and, per the endpoint docstring, left the doc `current` on CEZIH while
our mirror said `cezih_storno=true` — silent divergence that triggers
ERR_ENCOUNTER_2001 on later visit storno. Reachable only via `?canonical=false`,
which the FE never sends.
**Fix:** removed both functions + their `__all__` exports; removed the
`canonical` query param and `dispatch_fn` branch in `api/cezih.py` — the
`DELETE /e-nalaz/{id}` endpoint now always uses the canonical path.

### G5 — Case-link guard ignored clinical status (P3)
`assert_case_registered_on_cezih` passed for any registered case regardless of
status; you could author a fresh nalaz against a resolved/inactive slučaj.
**Fix:** added `require_active: bool` (rejects `resolved`/`inactive`/
`entered-in-error` via new module-level `TERMINAL_CASE_STATUSES`); enabled on
e-Nalaz **send** and **replace-with-edit**. Cancel stays drop-link (G1), visit
links unchanged.

### G6 — Frontend stale case/visit selection (P3, defense-in-depth)
**Fix:** the auto-select effect now also clears a `selectedCaseId`/
`selectedEncounterId` that has fallen out of the eligible list.
`frontend/src/components/cezih/send-nalaz-dialog.tsx`.

### G6b — Case pickers were offering remote-only QEDm cases (P2, corrected 2026-05-27 E2E)
The original G6 note claimed the pickers "already list only registered cases from
the CezihCase mirror." **That was wrong.** `/cezih/cases` (`dispatch_retrieve_cases`)
returns the **QEDm read merged with the local mirror** (`_merge_with_local`), so
cases opened in a *prior session / other context* with **no local `CezihCase` row**
surfaced in every Slučaj dropdown (record-form auto-send, send-nalaz dialog, visit
create/update). Picking one → `assert_case_registered_on_cezih` 422 ("nije
registriran"); worse, in record-form the auto-select silently defaulted to
`activeCases[0]` (often such a remote case) and stamped its ICD on the new record.
In visit-management it also forced `caseRequired = true` for a case the doctor
could not actually satisfy.
**Fix:** `CaseItem` gained a server-provided durable `registered` flag — `True`
only for rows backed by a local `CezihCase` mirror (`_serialize_case_row`),
`False` for QEDm-only rows (`fhir_api/condition.py`); `_merge_with_local` promotes
a remote row to `True` when a local row matches. All three link-dropdowns now
filter to `registered !== false`, so remote-only cases are **not shown** (JUST
DON'T SHOW THEM). The full `/cezih/cases` list still returns both — the eKarton /
case-history view (`case-management.tsx`, `ekarton-view.tsx`) is unchanged and
keeps showing externally-opened cases. Backend guard stays the real trust boundary.
Files: `backend/app/schemas/cezih.py`, `dispatchers/cases.py`,
`fhir_api/condition.py`, `frontend/src/lib/types.ts`, `lib/hooks/use-cezih.ts`,
`components/medical-records/record-form.tsx`,
`components/cezih/send-nalaz-dialog.tsx`, `components/cezih/visit-management.tsx`.

## Verified SOUND (no action)
- `CezihCase` rows persist only after a successful CEZIH create (`cases.py:94`)
  → the registration guard correctly rejects seed CUIDs.
- Visit-storno cascade already routes through `dispatch_cancel_document_canonical`
  (`visits.py:883`) → inherits G2/G3 live resolution + idempotent no-op.
- Cancel idempotency (`entered-in-error` → no-op success, mirror self-heals)
  unchanged.
- `_find_current_head` stays conservative (single unambiguous match only).

## Action Items
- E2E on prod, both signing methods, before requesting the next provjera termin:
  TC18→19→20 plus a **second** replace (forces a superseded predecessor) then
  storno → expect no ERR_DOM_10035, doc ends `entered-in-error`, eKarton shows the
  active head. **DONE on smart card 2026-05-27** (Z11 chain `1647841→1647847→1647981`,
  storno req `6592c21a` clean). Mobile Certilia re-verify still owed.
- ~~Visit-storno cascade on a visit with a replaced nalaz.~~ **RESOLVED — confirmed
  CEZIH-side deadlock, not fixable in-app.** The 1.4 is blocked by `ERR_ENCOUNTER_2001`
  on the superseded predecessors, which CEZIH itself refuses to cancel (`ERR_DOM_10035`).
  Auto-cancel-retry was already tried + reverted 2026-05-20 (`ede1fdf`→`16f0247`). The
  visit-storno error message was corrected to be honest (no impossible "go storno them
  yourself" instruction). Full write-up:
  [2026-05-27-visit-storno-replaced-doc-deadlock.md](2026-05-27-visit-storno-replaced-doc-deadlock.md).
- Confirm send/replace against a seed/terminal case → clean 422; storno of a
  seed-linked record → succeeds with the slučaj link dropped.
- Note: a case opened at another clinic and surfaced via QEDm (no local CezihCase
  row) is now rejected by `assert_case_registered_on_cezih`. Out of exam scope
  (all exam cases are ours), but flagged for a future "link to externally-opened
  case" path.

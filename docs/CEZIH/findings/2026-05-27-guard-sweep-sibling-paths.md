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
edit a storno'd doc); `unknown` → hard-fail (see G3). Replaces against the live
head, not the caller's possibly-stale ref. `fhir_api/documents.py`.

### G3 — `state == unknown` silently degraded to the stale stored OID (P2→promoted)
The resolver returns `state="unknown"` on any CEZIH read failure; the cancel
caller used to fall back to `original_document_oid` — re-opening the exact
ERR_DOM_10035 window under the known-flaky test env.
**Fix:** on `unknown`, **hard-fail** both cancel and replace with
`"CEZIH trenutno nije dostupan za provjeru statusa dokumenta. Osvježite prikaz
i pokušajte ponovno."` — never write against a stale OID. Resolver renamed
`_resolve_live_document_for_cancel` → `_resolve_live_document_head` (now shared
by cancel + replace) and its docstring no longer promises a fallback.

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
The send-nalaz Slučaj/Posjeta pickers already list only registered, non-terminal
items from the CezihCase mirror, and send is blocked when none is selected — so a
seed/unregistered id cannot be picked. Remaining gap: a selection that goes
terminal (or drops on refetch) while the dialog is open kept its stale value.
**Fix:** the auto-select effect now also clears a `selectedCaseId`/
`selectedEncounterId` that has fallen out of the eligible list.
`frontend/src/components/cezih/send-nalaz-dialog.tsx`.

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
  active head. Visit-storno cascade on a visit with a replaced nalaz.
- Confirm send/replace against a seed/terminal case → clean 422; storno of a
  seed-linked record → succeeds with the slučaj link dropped.
- Note: a case opened at another clinic and surfaced via QEDm (no local CezihCase
  row) is now rejected by `assert_case_registered_on_cezih`. Out of exam scope
  (all exam cases are ours), but flagged for a future "link to externally-opened
  case" path.

---
date: 2026-05-27
topic: documents | errors | certification
status: resolved
supersedes: (none — companion to 2026-05-27-visit-storno-fix-no-relatesto-amend-verified.md)
---

# Visit storno deadlocked on an ORPHAN current doc — cascade must read CEZIH, not the local mirror

## Discovery

After the no-relatesTo amend fix (`ce0b81b`, see
`2026-05-27-visit-storno-fix-no-relatesto-amend-verified.md`), a **second**, distinct
storno failure was hit by editing a visit's nalaz more than once / re-linking it to
another case:

- Visit `cmpofvnn2008bpv8559gcjjly` (patient f3e1d061 / MBO 999990260) refused storno with
  `ERR_ENCOUNTER_2001` listing `DocumentReference/1649689/_history/1`, and the app then
  **silently reported success** (`suppressed:true`) — a false "Stornirana" while CEZIH still
  held the visit active with a live document.

## Root cause — local-mirror cascade vs CEZIH reality

The storno cascade picked the docs to cancel from our **local `medical_records` mirror**
(`_list_active_cezih_docs_for_visit`: rows where `cezih_encounter_id == visit` AND
`cezih_storno == False`). That mirror is **not** the source of truth for what blocks a
CEZIH visit-cancel (1.4):

- A doctor edit (amend) repoints the row's `cezih_reference_id` to the NEW doc. If the nalaz
  is edited again, re-linked to another case, or the new ref is otherwise not re-captured on
  that same row, an **earlier amended doc stays `status=current` on the Encounter with no
  local row pointing at it** — an orphan.
- The cascade therefore cancelled only the locally-known docs, the 1.4 then failed on the
  orphan, and the post-1.4 guard — which assumes any surviving `ERR_ENCOUNTER_2001` is the
  un-cancellable *superseded*-predecessor deadlock — swallowed it as success.

Audit trail confirmed the mechanism: two `e_nalaz_edit_via_amend` on the same source ref
`1649663` produced new docs **1649689** (19:17:49) then **1649700** (19:19:03). The mirror
ended pointing at `1649615` + `1649700`; **1649689 was orphaned** — `current` on CEZIH,
absent from every `medical_records` row.

`/_diag/doc-chains` on the encounter (live, pre-fix):
`{1649615: eie, 1649663: eie, 1649689: CURRENT, 1649700: eie}` — one orphan `current`.

## Fix — ask CEZIH which docs it ties to the Encounter, cancel all of them

1. **`list_active_documents_on_encounter`** (`fhir_api/documents.py`): ITI-67 search of the
   patient's `status=current` DocumentReferences, filtered to those whose
   `context.encounter[].identifier.value == visit_id`. Returns `{reference_id, oid, tip,
   case_id}` for **every type**, orphans included. Only `current` docs are returned — the
   cancellable blockers; `superseded` predecessors are excluded on purpose (CEZIH refuses to
   cancel them — `ERR_DOM_10035` — so they remain the separate legacy deadlock, untouched).
2. **`dispatch_cancel_document_for_storno`** (`dispatchers/documents.py`): cancels a ref that
   may not exist in the local mirror by building patient context from the `Patient` object
   (the canonical `dispatch_cancel_document_canonical` resolves everything from a
   `medical_records` row matched by `cezih_reference_id`, so it cannot cancel an orphan).
   Idempotent (underlying `cancel_document_canonical` no-ops an already-`eie` target);
   converges any matching mirror row to `cezih_storno=True`.
3. **`dispatch_visit_action` storno**: blockers = **CEZIH ∪ local mirror**, dedup by
   reference_id, cancel each. The 409 cascade-confirm payload is normalised to the FE
   `CascadeDoc` shape (`reference_id/tip/dijagnoza_mkb/datum`; orphans carry null
   dijagnoza/datum).

Why this is NOT the reverted 2026-05-20 self-heal (`ede1fdf`→`16f0247`): that one fired
*after* the 1.4 error and blindly canonical-cancelled the named refs — which back then were
`superseded` predecessors of an ITI-65 replace → `ERR_DOM_10035`, a futile loop. This fix
runs in the **preflight** off CEZIH's `status=current` list, so it only ever attempts to
cancel **current** (cancellable) docs. No superseded doc is ever targeted.

## Evidence (verified live, cert env, smart card)

Visit `cmpofvnn2008bpv8559gcjjly`, patient f3e1d061 / MBO 999990260:

- Pre-storno doc-chains: `1649689 = current` (orphan, `relatesTo:[]`, encounter matches),
  `1649615/1649663/1649700 = eie`.
- Storno preflight (no confirm) → **409 `cascade_required`** listing exactly `1649689`
  ("Izvješće nakon pregleda u ambulanti…") — proving CEZIH-sourced discovery finds the
  orphan the local mirror lost.
- Storno (confirm) → cancels `1649689` → eie, then visit 1.4 → **200, `suppressed:false`,
  visit `status=entered-in-error`** (Stornirana), `last_error_code=null`. One signature (the
  1.4 visit cancel; the 2-entry HRCancelDocumentBundle doc-cancel is unsigned).
- Post-storno doc-chains: `{1649615: eie, 1649663: eie, 1649689: eie, 1649700: eie}` — no
  `current`, no `superseded`. **No `ERR_ENCOUNTER_2001`.**

## Impact

- Visit storno is now driven by CEZIH's actual document topology, so multi-edit / re-linked
  visits storno correctly instead of silently faking success.
- The post-1.4 `ERR_ENCOUNTER_2001` suppression now fires **only** for the genuine
  `superseded`-predecessor deadlock (legacy ITI-65 replace), which is its intended scope.
- No new diagnostic routes added; reuses the kept read-only `GET /_diag/doc-chains`.

## Code

- `backend/app/services/cezih/fhir_api/documents.py` — `list_active_documents_on_encounter`.
- `backend/app/services/cezih/dispatchers/documents.py` — `dispatch_cancel_document_for_storno`.
- `backend/app/services/cezih/dispatchers/visits.py` — `dispatch_visit_action` storno cascade.
- Commit `eb9cb1b`.

## Action Items

- [x] Implement CEZIH-authoritative cascade + mirror-independent cancel.
- [x] Verify full E2E (orphan current doc → storno → Stornirana) on cert with smart card.
- [ ] Re-verify on Certilia mobile signing before the next provjera spremnosti.

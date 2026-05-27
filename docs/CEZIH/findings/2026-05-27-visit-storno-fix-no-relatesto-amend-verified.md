---
date: 2026-05-27
topic: certification | documents | errors
status: resolved
supersedes: (none — companion/resolution to 2026-05-27-visit-storno-replaced-doc-deadlock.md)
---

# Visit-storno deadlock RESOLVED — doctor edit = submit-new (no relatesTo) + cancel-old, verified E2E

## Discovery

The visit-storno deadlock (see `2026-05-27-visit-storno-replaced-doc-deadlock.md`) is fixed by
changing the doctor-facing e-Nalaz edit so it never leaves a `superseded` document on CEZIH.

**Root deadlock recap:** an ITI-65 *replace* (`relatesTo.code=replaces`) sets the predecessor
DocumentReference to `superseded`. Visit-cancel (msg 1.4) then demands every document version on the
encounter be `entered-in-error` (`ERR_ENCOUNTER_2001`), but cancelling a `superseded` doc is refused
(`ERR_DOM_10035` "Target resource is not in valid status"). CEZIH demands an operation it
simultaneously forbids → permanent deadlock for any visit whose finding was ever edited via replace.

**The fix — "entered-in-error line":** the edit submits the new content as a **standalone
`status=current` DocumentReference with NO `relatesTo` at all**, still linked to the same visit +
case via `context.encounter` + `context.related`, then cancels the old doc to `entered-in-error`.
End state: old=`entered-in-error`, new=`current` + case-linked, **no `superseded` anywhere**.

## Why NOT `appends` (the rejected intermediate hypothesis)

The plan first tried `relatesTo.code=appends` (IHE MHD says only `replaces` supersedes the target).
**Live cert test disproved it:** the appended NEW doc came back **`superseded`**, not `current` —
CEZIH files an `appends` document as a *non-current addendum* (the target keeps the "current" slot).
Combined with cancel-old→eie that produced old=eie + new=superseded + **no current doc**: both (a)
the 2026-05-20 provjera failure mode (patient #2 had zero active docs, auditor's eKarton showed
nothing — see `2026-05-27-exam-fail-patient2-storno-stale-ref.md`) AND (b) a leftover superseded doc
that still deadlocks storno. A retry also hit `ERR_DOM_10035` appending to a now-eie target.
Conclusion: **no `relatesTo` on the wire.** The doc-to-doc correction link is kept LOCAL-only
(audit `amended_from_oid`); the visit/case linkage that CEZIH/eKarton actually requires is carried by
`context.encounter` + `context.related`, which is independent of `relatesTo`.

## Evidence (verified live, cert env, smart card)

Patient f3e1d061 / MBO 999990260 (GORAN PACPRIVATNICI19). Fresh CLEAN chain:

- Case `cmpofcbg80089pv85xcgb185k` (J06.9), Visit `cmpofdlr4008apv85krhaqwfg`.
- TC18 send → DocumentReference **1649530**, `status=current`, **`relatesTo: []`**, oid …755026.
- Edit via `PUT /cezih/e-nalaz/1649530/amend-with-edit` (no-relatesTo amend):
  - submit-new → **1649545**, `status=current`, **`relatesTo: []`**, oid …755027, same encounter.
  - cancel-old → 1649530 → **`entered-in-error`**.
  - `/_diag/doc-chains` on the encounter: `{1649530: eie, 1649545: current}` — **no `superseded`**.
- Visit storno via FE (cascade): the "Storniraj" action was **present + enabled** in the visit
  "Akcija…" menu (silent-hide correctly NOT triggered — no `cezih_last_replaced_at`). Cascade
  cancelled active nalaz 1649545 → eie, then visit-cancel (1.4) → visit **Stornirana**.
  - Final doc-chains: `{1649530: eie, 1649545: eie}`, no superseded. **No `ERR_ENCOUNTER_2001` /
    `ERR_DOM_10035`.**

## Code

- `backend/app/services/cezih/fhir_api/documents.py` → `amend_document()`: builds the new doc with
  `relates_to=None`; still resolves the LIVE old head to return `old_reference_id` / `old_document_oid`
  for the caller's cancel-old.
- `backend/app/services/cezih/dispatchers/documents.py` → `dispatch_edit_document_via_amend()`:
  submit-new → repoint local record to new doc (no `cezih_last_replaced_at`, `cezih_storno=False`,
  audit `e_nalaz_edit_via_amend`) → cancel-old (`entered-in-error`, carrying encounter+case).
  Honest partial failure: repoint + coded error + HTTP 502, never fake success.
- `cancel_document_canonical()` already resolves the live head before cancel and is idempotent on
  already-`eie` targets (kills the retry `ERR_DOM_10035`).
- API: `PUT /cezih/e-nalaz/{ref}/amend-with-edit` (new). `replace_document` +
  `PUT /cezih/e-nalaz/{ref}/replace-with-edit` kept intact for the TC19 cert test.
- Commit `ce0b81b`.

## Impact

- Edited findings no longer deadlock visit storno. Visit lifecycle (create → case → e-Nalaz → edit →
  storno) is fully exercisable on real CEZIH.
- The doctor's everyday "Uredi i zamijeni" no longer creates `superseded` docs. The cert's TC19
  "Replace clinical document" is still demonstrable via the kept replace path.
- Legacy visits that already carry `superseded` predecessors (from past replaces) remain permanently
  un-stornoable — this is a forward-only prevention; FE keeps silently hiding storno for them
  (`has_replaced_document`).

## Action Items

- [x] Implement no-relatesTo amend + cancel-old (idempotent, live-resolved).
- [x] Verify full E2E (send → amend → storno) on cert with smart card.
- [ ] Re-verify on Certilia mobile signing before the next provjera spremnosti.
- [ ] Optional: HZZO escalation of the undocumented `ERR_ENCOUNTER_2001 ↔ ERR_DOM_10035`
      contradiction (legacy superseded-chain visits stay un-stornoable regardless of this fix).

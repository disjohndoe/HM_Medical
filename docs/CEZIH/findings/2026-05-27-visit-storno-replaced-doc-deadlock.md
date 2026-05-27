---
date: 2026-05-27
topic: documents | errors | cascade | visit-storno
status: active
tc: TC14, TC19, TC20
---

# Visit storno is a CEZIH-side deadlock when a document on it was REPLACED

## Discovery

A visit (Encounter) that carries an e-Nalaz which was **replaced** (ITI-65
replace, TC19) **cannot be storno'd on CEZIH**, even after the live document head
is correctly cancelled (TC20). CEZIH blocks the encounter cancel (1.4) with
`ERR_ENCOUNTER_2001` listing the **superseded predecessor** DocumentReferences,
but it **also refuses to cancel those predecessors** with `ERR_DOM_10035`. CEZIH
refuses both ends — there is no in-app remediation path. This is a CEZIH server
rule, not a bug in our code.

This is the result of the action item "visit-storno cascade on a visit with a
replaced nalaz" from [2026-05-27-guard-sweep-sibling-paths.md](2026-05-27-guard-sweep-sibling-paths.md).

## Evidence

Live smart-card chain on the exam tenant, 2026-05-27:
- Built Z11 chain `1647841 → 1647847 → 1647981` (two replaces → genuine superseded
  predecessors `1647841`, `1647847`; live head `1647981`).
- Storno of the live head `1647981` (req `6592c21a`): resolved the **live** head OID
  (`...755013`, `state=current`), `HRCancelDocumentBundle`, iti-65 → 200,
  `entered-in-error`, **no** ERR_DOM_10035. The 2026-05-20 exam failure mode is
  closed. ✓
- Visit storno of `cmpnwnl97007opv851694cqyi` (req `97d07f0a0ed649a8`): signed 1.4,
  POST `encounter-services $process-message` → **400**. CEZIH OperationOutcome:
  ```
  issue.code = not-supported
  details.coding[0].code = ERR_ENCOUNTER_2001
  details.coding[0].display = "Cannot cancel Encounter, following is the list of resources that must be cancelled."
  details.text = "Additional info: [DocumentReference/1647841/_history/2, DocumentReference/1647847/_history/2]"
  ```
  The blocking refs are the **superseded predecessors**, not the cancelled head.

### Close-first does NOT help (status is irrelevant)

A natural workaround — "close the visit first, then storno" — was tested live and
**fails identically**. Sequence on the same visit, 2026-05-27 ~11:02:
- 1.3 close (`status=finished`, req `77b9ff6b`) → **200 OK** (Završena).
- Storno is not offered on a closed visit, so the UI reopens it: 1.5 reopen
  (`status=in-progress`, req `f01b84bb`) → **200 OK**.
- 1.4 cancel (req `5ca244b6`) → **400**, same `ERR_ENCOUNTER_2001`, same blocking
  refs `[1647841, 1647847]`.

So the encounter's status (finished/in-progress) is irrelevant — the block is purely
the superseded document predecessors. **There is no precondition the doctor can
satisfy to unlock the storno**; the live head is already `entered-in-error` and the
predecessors are unreachable. Any "do X before storno" guidance is therefore wrong;
the only honest message is "this visit can't be storno'd — close it instead if it was
completed, or contact support if entered by mistake."

## What the Simplifier spec actually says (checked 2026-05-27)

Checked against the downloaded packages in `docs/CEZIH/`
(`cezih.hr.encounter-management-0.2.3`, `cezih.hr.cezih-osnova-1.0.1`,
`klinicki-dokumenti`). Two operational assumptions were tested:

1. **"Maybe visit storno isn't a supported operation, only close."** — **FALSE.**
   `StructureDefinition-hr-cancel-encounter-message` exists (title *"Poruka zahtjeva
   za brisanje posjeta"*) and the encounter-management package ships an **official
   example for event 1.4 with `Encounter.status=entered-in-error`**. All five
   lifecycle events are exampled: 1.1 create, 1.2 update, 1.3 close, 1.4 cancel,
   1.5 reopen. Visit storno is a first-class, fully-defined operation — and it works
   in the normal case (single non-replaced nalaz, verified 2026-05-13).
2. **"Maybe we just storno the e-Nalaz."** — document storno is indeed first-class
   (`HRCancelDocumentBundle`, *"kojom se stornira dokument ranije registriran u
   CEZIH"*, sets `DocumentReference.status=entered-in-error`) and always works on the
   live head. But it is **not a substitute** for visit storno — they neutralize
   different resources (the document vs the whole Encounter).

**Crucially, neither the deadlock rule nor its error codes are in the published
spec.** `CodeSystem-message-error-type` in all three packages contains only
placeholder concepts (`1`, `2`); `ERR_ENCOUNTER_2001` and `ERR_DOM_10035` appear
**nowhere** in the Simplifier specs — they are **undocumented CEZIH backend rules**.
So the spec says visit storno is supported with no documented document-precondition,
while the backend refuses it for replaced-document visits via undocumented codes.
That is a legitimate **spec-vs-implementation discrepancy** worth raising with HZZO.

## Why auto-cancel-and-retry does NOT work (already tried + reverted)

The obvious "self-heal" — parse the blocking refs, cancel each, retry the 1.4 —
was implemented and reverted on the same day, 2026-05-20:
- `ede1fdf` — *"self-heal visit storno when CEZIH lists predecessor DocumentRefs"*:
  added a retry loop + `dispatch_cancel_document_by_ref_from_cezih` (ITI-67 OID
  lookup for refs not in the local mirror), cancel each blocking ref, retry once.
- `16f0247` — **revert**, with the live finding:
  > the canonical cancel attempt comes back ERR_DOM_10035 'Target resource is not
  > in valid status'. There is no in-app remediation path - CEZIH refuses both ends.

A superseded DocumentReference is not in a `current` status, and CEZIH only accepts
the `entered-in-error` transition on a `current` document. So:
- Cancel the **head** → works (head is `current`).
- Cancel a **superseded predecessor** → `ERR_DOM_10035`.
- Cancel the **encounter** while a predecessor is still referenced →
  `ERR_ENCOUNTER_2001`.

Today's G3 live-head resolver makes this strictly worse for the auto-cancel idea:
`dispatch_cancel_document_canonical` resolves **any** predecessor ref to the live
head (now `entered-in-error`) and idempotently no-ops — it can no longer even
*target* the predecessor. Re-implementing the retry loop would re-create a path we
have already proven fails against the real test env.

### Re-confirmed empirically 2026-05-27 via a controlled own-OID probe

To remove any doubt that the reverted self-heal merely "targeted the wrong OID", a
throwaway probe (`POST /api/cezih/_debug/cancel-predecessor`, since removed) was
deployed that bypassed the G3 head resolver entirely and cancelled the **superseded
predecessor by its OWN master OID**, in a bundle structurally identical to a
verified-green head storno (same `build_cancel_bundle`, real patient name +
encounter + `context.related` case loaded from the head record). Live on the exam
tenant, smart-card chain `1647841 → 1647847 → 1647981`:

- Probe found predecessor `DocumentReference/1647847`, `status=superseded`, own OID
  `urn:oid:...755010` (req `096526e3`).
- Built the cancel bundle with that exact OID + full context
  (`encounter=cmpnwnl97007opv851694cqyi`, `case=cmpnwlnoc007npv85ehfuj3nm`).
- CEZIH OperationOutcome: **only** `ERR_DOM_10035` "Target resource is not in valid
  status." — no slice/content errors. The bundle passed profile validation and was
  rejected purely on the document's status.

(A first attempt with a context-less bundle was rejected earlier at profile
validation with `Validation_VAL_Profile_NotSlice` — a cascade of `CEZIHDR-003/005/008`
content-invariant failures from the missing patient name / encounter / case, **not**
the status check. That attempt was inconclusive; the second, context-complete attempt
is the definitive one.)

**Conclusion: the deadlock is fundamental.** A superseded `DocumentReference` cannot
be set `entered-in-error` by its own OID under any bundle shape — CEZIH accepts that
transition only on a `current` document. There is no client-side OID trick that
unlocks it; auto-cancel of the listed predecessors is impossible by construction.

## "But visit storno worked before" — yes, in a different configuration (NO regression)

Reconciled against our own sweep history:

| Scenario | When verified | Result |
|---|---|---|
| Visit storno, **zero** documents on the visit | 2026-04-22, 2026-04-23 (TC14 runs *before* TC18 in the matrix) | ✅ works |
| Visit storno, **one non-replaced** document (cascade cancels it, then 1.4) | 2026-05-13 | ✅ works |
| Document storno (TC20) on the live head | every green sweep | ✅ works |
| Visit storno where a document was **replaced** (superseded predecessor) | **2026-05-27 (first time exercised)** | ❌ deadlock |

In every "22/22 green" sweep, **TC14 (visit cancel) ran at step TC14 — before any
e-Nalaz was sent to that visit (TC18+)** — so the visit had no documents and nothing
could raise ERR_ENCOUNTER_2001. The replace-then-visit-storno combination was never in
the matrix; it was constructed for the first time on 2026-05-27 (the Z11 chain, per the
guard-sweep action item to do "a second replace then storno"). So this is a **new
scenario, not a regression** — the green sweeps are still valid for what they covered.

## Impact

- **The deadlock blocks ONLY storno (1.4 / `entered-in-error`).** The normal terminal
  lifecycle is unaffected: **close the visit (1.3 → Završena)** and **resolve the case
  (2.5 → Završen)** both work fine on a visit with a replaced document, because closing
  an Encounter does **not** require its documents to be cancelled first — that
  requirement is specific to *cancel*. Confirmed manually 2026-05-27. So a visit whose
  finding was legitimately replaced has a perfectly good terminal path; it just isn't
  storno. Storno is for "this visit never happened" (mistaken entry); for a visit that
  actually happened, close + resolve is the correct act anyway.
- **Normal storno cascade also still works** (verified [2026-05-13-cascade-storno-canonical-cancel-verified.md](2026-05-13-cascade-storno-canonical-cancel-verified.md)):
  a visit whose nalaz was **never replaced** stornos cleanly — preflight cancels the
  single `current` head, then 1.4 → 200. The deadlock is strictly the
  **replace-then-visit-storno** combination, and it is **not part of the standard exam
  happy-path** for TC14.
- Current handling (commit `16f0247`, still live) is correct and is the only viable
  behavior: surface a clear Croatian message and stop — no silent degradation, no
  doomed retry. The message now points the doctor at the action that works (close the
  visit) instead of a dead-end "contact support". We do **not** auto-convert
  storno → close: they mean different things and a silent substitution would be a
  forbidden fallback.

## Action Items

- **Do NOT re-implement the parse-and-retry self-heal.** It is a known dead end
  (`ede1fdf` → `16f0247`). This finding exists so it is not attempted a fourth time.
- For exam prep, verify TC14 visit storno on a visit with a **single, non-replaced**
  nalaz (the cascade path that works) — that is what the happy-path TC exercises.
- The Z11 test visit (`cmpnwnl97007opv851694cqyi`, "U tijeku") can be cleared the
  correct way: **close it (1.3 → Završena)** and resolve its case (2.5 → Završen).
  Storno is simply the wrong act for a visit that genuinely happened.
- *(Not an exam blocker — valid path exists.)* Worth raising with HZZO as a
  **spec-vs-implementation** clarification, now that we've confirmed the spec fully
  defines + examples visit storno (1.4) with no documented document-precondition,
  while the backend refuses it on replaced-document visits via the undocumented
  `ERR_ENCOUNTER_2001` ↔ `ERR_DOM_10035` pair: is visit storno intended to be
  possible after a document replace, or is close+resolve the only supported terminal
  state in that case? Deferential "molim Vas" register.

## Resolution (shipped 2026-05-27) — hide storno, BE silent no-op

Since the storno is unfixable client-side and ENT/HZZO has not responded, we stopped
surfacing the dead-end error and instead make the storno option simply **unavailable**
for affected visits — no message, badge, or explanation shown to the doctor.

- **Detection (local, no CEZIH call):** a visit has a replaced doc iff a `MedicalRecord`
  on its `cezih_encounter_id` has `cezih_last_replaced_at IS NOT NULL`
  (`cezih_storno` is *not* filtered — cancelling the head never clears the superseded
  predecessors). Surfaced as `VisitItem.has_replaced_document` via
  `_encounters_with_replaced_docs` / `_encounter_has_replaced_doc` in
  `dispatchers/visits.py`.
- **Frontend:** `getAvailableActions` (visit-management.tsx) drops `storno` when
  `has_replaced_document` is set; `Zatvori` (1.3, confirmed working) stays.
- **Backend net (stale tab / direct API):** the `action=="storno"` branch of
  `dispatch_visit_action` now short-circuits when `_encounter_has_replaced_doc` is true —
  logs, writes a `visit_storno_suppressed` audit row, and returns the unchanged visit
  **without calling CEZIH** (which also stops the old behaviour of cascading-cancel the
  live head doc and then failing the 1.4, leaving the visit half-changed). The previous
  honest-message handler for a runtime `ERR_ENCOUNTER_2001` (replaced doc we couldn't see
  locally, e.g. replaced by another system) was converted to the same silent no-op.

### Simplifier evidence that this is a backend-only rule (no spec basis)

- `Brisanje posjete` / `Storniranje dokumenata` / `Zamjena dokumenata` IG pages document
  only the happy path; **no document-precondition** for visit cancel, no mention of
  superseded/`_history`.
- `StructureDefinition-hr-cancel-encounter-message` has **zero invariants** about
  documents.
- `CodeSystem-message-error-type` (publisher Ericsson Nikola Tesla, last updated
  2023-01-26) is a **stub**: codes `1`/`2` only. **`ERR_ENCOUNTER_2001` and
  `ERR_DOM_10035` are absent from the published terminology entirely.**
- Latest published `cezih.hr.encounter-management` = 0.2.3 (= the local copy); nothing
  newer documents this.

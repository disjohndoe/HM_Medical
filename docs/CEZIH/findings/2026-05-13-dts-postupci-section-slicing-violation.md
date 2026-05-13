---
date: 2026-05-13
topic: codesystems
status: resolved
---

# DTS postupci must go INSIDE medicinska-informacija, not as a top-level section

## Discovery

Initial DTS implementation appended a 4th top-level `Composition.section` with `code="13"` titled "Primijenjeni postupci" to carry `primijenjen-postupak` Procedure references in 011/012/013 documents. This violates the Composition profile in two stacked ways.

## Evidence

`docs/CEZIH/klinicki-dokumenti/StructureDefinition-nalaz-iz-specijalisticke-ordinacije-privatne-ustanove.json` (and the parallel 011/013 profiles):

```json
{
  "id": "Composition.section",
  "slicing": {
    "discriminator": [{"type": "value", "path": "code"}],
    "ordered": false,
    "rules": "closed"
  },
  "min": 2,
  "max": "3"
}
```

Only three allowed slices: `djelatnost` (code=12), `prilozeni-dokumenti` (code=16), `medicinska-informacija` (code=18). Closed slicing means any other code fails profile validation.

`docs/CEZIH/klinicki-dokumenti/CodeSystem-document-section.json` confirms code "13" in this CodeSystem is **"SGP podaci"**, not "Primijenjeni postupci". So the violating block had both:

1. A code outside the allowed closed-slice set.
2. A `display` value that does not match the CodeSystem definition for that code.

The correct location is `Composition.section:medicinska-informacija.entry:postupci`, defined explicitly in the same profile:

```json
{
  "id": "Composition.section:medicinska-informacija.entry:postupci",
  "sliceName": "postupci",
  "type": [{"code": "Reference", "targetProfile": [".../primijenjen-postupak"]}]
}
```

## Impact

Would have caused a third HZZO provjera rejection on the same theme as 2026-05-04 (Binary plain-text) and 2026-05-11 (JID/djelatnost/visit-case) - profile non-compliance discovered by manual review. Caught before submission.

## Action Items

- [x] Move procedure refs into `mi_entries` alongside anamneza/slucaj/ishodPregleda/preporuceniPostupci in `backend/app/services/cezih/builders/clinical_document_bundle.py` `_build_composition()`.
- [x] Fix silent fallback in `app/services/dts_sync_service.py` per CLAUDE.md "No fallbacks" rule: split `sync_dts_codes()` (raises on CEZIH failure) and `seed_dts_from_bootstrap()` (one-shot first-boot only).
- [x] Fail-fast on missing `PerformedProcedure.datum` in `_get_procedures_for_record` - `Procedure.performedDateTime` is 1..1 in the profile.
- [ ] DTP-PZZ + DTP-SKZZ vocabulary coverage: `ValueSet/postupci` composes three CodeSystems but we only sync DTS. Profile-legal (any of the three is accepted) but coverage-incomplete. Blocked on CEZIH `ValueSet/$expand` returning data (404 today per `2026-04-22-valueset-expand-fallback.md`) - the per-CodeSystem packages in `cezih.hr.cezih-osnova-1.0.1` only have placeholder concepts.
- [ ] Re-verify 22 TC matrix after deploy. Specifically TC18/19/20 with at least one document carrying a `postupci` entry.

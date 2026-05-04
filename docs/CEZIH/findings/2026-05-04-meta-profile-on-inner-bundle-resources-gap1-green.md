---
date: 2026-05-04
topic: certification
status: active
---

# Inner Document Bundle meta.profile (Gap 1) accepted by CEZIH on first send - GREEN

## Discovery

After the post-082ca4b foreign-EHIC sweep (Ref 1532912) confirmed the new inner FHIR Document Bundle structure works, a slice-by-slice audit against the Simplifier `cezih.hr.klinicki-dokumenti` package found the most likely remaining cert risk: **none of the inner-bundle resources declared their CEZIH StructureDefinition URL via `meta.profile`**. CEZIH's HAPI test env was matching loosely on structure, but a profile-aware validator (and HZZO manual review) would not be able to bind the Bundle to the right profile without it.

Patch (commit `9211d1a`, `clinical_document_bundle.py`) added explicit `meta.profile` arrays on every inner resource: Bundle (`hr-document`), Composition (`nalaz-iz-specijalisticke-ordinacije-privatne-zdravstvene-ustanove` for type code 012; map covers 011/013 too), Patient (`hr-pacijent`), Practitioner (`hr-practitioner`), Organization (`hr-organizacija`), Encounter (`hr-encounter`), Condition (`dokumentirani-slucaj`), anamneza Observation (`anamneza`), ishod Observation (`ishod-pregleda`), HealthcareService (`djelatnost`).

CEZIH accepted it on first try, foreign EHIC + Certilia mobile, no validation issues.

ROGER ROG PACPRIVATNICISTRAN3 (UK, EHIC `TEST20251215113521HP`, CEZIH ID `cmj70pxqx00sg5c85kg429x8n`).

## Evidence

| Step | Endpoint | Status | Duration | Local ID / CEZIH Ref |
|------|----------|--------|----------|----------------------|
| 2.1 Create slučaj (J06.9) | `POST /api/cezih/cases` | 200 | ~22s | `cmorajjn104gshb854ge9fsd6` |
| 1.1 Create posjeta (Ostalo / Posjeta SKZZ) | `POST /api/cezih/visits` | 200 | ~17s | `cmorak6au04gthb85m5b3zben` |
| TC18 ITI-65 send e-Nalaz (inline from record creation) | `POST /api/cezih/e-nalaz` | 200 | 21.2s | **DocumentReference/1533184** (List/1533183, Binary/1533185) |

ITI-65 inner Document Bundle (`request_id=f4c0aaa86ed146f4`):

- Inner Bundle.meta.profile: `["http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-document"]`
- Composition.meta.profile: `["http://fhir.cezih.hr/specifikacije/StructureDefinition/nalaz-iz-specijalisticke-ordinacije-privatne-zdravstvene-ustanove"]`
- Doc OID: `urn:oid:2.16.840.1.113883.2.7.50.2.1.751508`
- DocumentReference type code: `012`
- Subject path: `http://fhir.cezih.hr/specifikacije/identifikatori/jedinstveni-identifikator-pacijenta` = `cmj70pxqx00sg5c85kg429x8n` (foreign branch, no MBO)
- Encounter identifier: `cmorak6au04gthb85m5b3zben`
- Related Condition: `cmorajjn104gshb854ge9fsd6`
- Extsigner signed-document size: 10649 bytes (vs 9763 in the 2026-05-04 pre-Gap-1 sweep - +886 bytes accounts for the ten meta.profile arrays)
- Outer ITI-65 transaction bundle: 18852 chars
- CEZIH HAPI response: 3x `201 Created` with `SUCCESSFUL_CREATE` outcome on every entry

Persistence not verified via hard reload (single sweep, focused on validating Gap 1 acceptance).

## Impact

- Gap 1 from the 2026-05-04 slice-by-slice audit closed. The most addressable spec-conformance gap (relative to the Simplifier `cezih.hr.klinicki-dokumenti` package) is now patched, deployed, and accepted by real CEZIH.
- Removes the risk that HZZO manual reviewers would flag the bundle for failing to declare which CEZIH profile each inner resource conforms to. Profile binding is now explicit on every resource.
- Confirms CEZIH HAPI tolerates explicit `meta.profile` declarations - it doesn't reject what it was previously accepting on structure alone. So this is a one-way ratchet upward in conformance, no breakage.
- Reproduces the placeholder `practiceSetting=2010000 "Internistička djelatnost"` flagged in `2026-05-04-djelatnost-per-doctor-handoff.md` - validates with HAPI but ships wrong specialty into a signed clinical document. Cert-irrelevant for this run, still owed as a follow-up.

## Action Items

- TC19 (Replace) and TC20 (Storno) on this same Ref 1533184 still owed for foreign-mobile to claim a full e-Nalaz round-trip post-Gap-1. Croatian-mobile + smart-card sweeps (both Croatian and foreign) on the new meta.profile bundle still owed - this is the first sweep with the patch.
- Gaps 2-5 from the same audit (cosmetic/clinical-completeness: inner Encounter.class binding, Encounter.type slice, multi-slice patient identifier for foreigners, Composition.text narrative) remain unfixed. Not cert-blockers per the Simplifier diff; can wait for the post-cert sprint.
- Per-user djelatnost work tracked in `2026-05-04-djelatnost-per-doctor-handoff.md`.

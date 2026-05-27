---
date: 2026-05-27
topic: endpoints
status: active
---

# CEZIH read-side identity fields — how to tell "ours vs external" per resource

## Why this matters

On the patient CEZIH subtab the tables (Posjete / Slučajevi / e-Nalazi) mix records this
clinic created with records other providers created for the same patient. We must label them
correctly ("Naša" vs "Vanjski/Ostalo"). The **reliable** signal is the **issuing identity on the
wire** (institution šifra ustanove + author/recorder HZJZ broj) compared against the tenant's own
identifiers — NOT whether a local mirror row happens to exist (mirror rows are lost across
test-env DB resets, and ids don't always line up, which mislabels our own records as external).

Captured live from prod CEZIH (test env) for GORAN PACPRIVATNICI19 (MBO 999990260) on
2026-05-27 via the temporary `GET /cezih/_diag/ownership` admin endpoint.

## Identifier systems

| Concept | System URI | Where defined |
|---|---|---|
| Institution (šifra ustanove) | `http://fhir.cezih.hr/specifikacije/identifikatori/HZZO-sifra-zdravstvene-organizacije` | `builders/common.py:ID_ORG` |
| Practitioner (HZJZ broj) | `http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika` | `builders/common.py:ID_PRACTITIONER` |

Tenant identity lives in: `tenants.sifra_ustanove` (institution code) and each doctor's
`users.practitioner_id` (HZJZ broj). Example tenant "Ordinacija Horvat"
(`be0c3681-…`): `sifra_ustanove = 999001464`, doctors' HZJZ = {`7659059`} (exam@horvat.hr).

## What each CEZIH read carries

### Visits — Encounter (QEDm) → `service_provider_code`
`Encounter.serviceProvider` Organization carries the HZZO šifra ustanove. Already mirrored to
`cezih_visits.service_provider_code` and the FE classifies Naša/Ostalo with
`v.service_provider_code !== tenant.sifra_ustanove` (`visit-management.tsx:157,173`). This is
the reference pattern. **Org-based.**

### Nalazi — DocumentReference (ITI-67 MHD) → `custodian` + `author`
- `custodian` = Organization with `identifier.value` = issuing šifra ustanove (the authoritative
  org signal). e.g. other providers `999001425` (WBS), `950595055` (Vegasoft), `079402127`
  (Dental Kod); our own docs come back as `999001464` (display "Ordinacija Horvat").
- `author[]` = Practitioner (HZJZ `identifier.value` + display name) and sometimes also an
  Organization (same šifra). e.g. author Practitioner HZJZ `4981825` "Ivan Prpić".
- **Org-based primary, doctor-based secondary.** Our doc ⇔ `custodian` šifra == tenant šifra
  (or author HZJZ ∈ our doctors). The previous parser only kept `author.display`, which is why
  our own "Ordinacija Horvat" docs (no surviving local row) showed as "Vanjski nalaz".

### Cases — Condition (QEDm) → `recorder` + `asserter` (NO organization!)
Conditions carry **no organization** — only Practitioner refs:
- `recorder` = Practitioner with HZJZ `identifier.value` (always present in the sample).
- `asserter` = Practitioner with HZJZ `identifier.value` (present; sometimes a different HZJZ
  than recorder — e.g. recorder `4981825` / asserter `7659059`).
- `identifier[]`: `identifikator-slucaja` (global case id, often a CUID like
  `cmmki35u702qo5c85l6uqvmv5`) and sometimes `lokalni-identifikator-slucaja`.
- `encounter` (link to the posjeta) present only on some.
- **Doctor-based only.** A case is ours ⇔ `recorder`/`asserter` HZJZ ∈ our doctors' HZJZ set.
  There is no org šifra on the Condition to compare, so org-based matching is impossible for
  cases — must use the doctor (HZJZ).

## Ownership rule (unified, used by the classifier)

A CEZIH record is **ours** when **either**:
1. its organization šifra ustanove (Encounter.serviceProvider / DocumentReference.custodian or
   author Organization) == `tenant.sifra_ustanove`, **or**
2. any of its practitioner HZJZ ids (DocumentReference.author / Condition.recorder|asserter) ∈
   the tenant's doctors' `practitioner_id` set.

Cases rely on (2) only (no org on the wire); visits rely on (1); nalazi can use both.

## Raw sample (abridged)

```
documents (custodian.identifier.value | author HZJZ):
  1252126  999001425 | 4981825 "Ivan Prpic"      (WBS — external)
  1288196  079402127 | 2702070                    (Dental Kod — external)
  1246189  950595055 | 9191739                    (Vegasoft — external)
conditions (identifikator-slucaja | recorder HZJZ | asserter HZJZ | encounter):
  cmmki35u702qo5c85l6uqvmv5 | 9191739 | 9191739 | cmmki2fqs02qn… (external)
  cmj2inkji00kv5c85pbl0bzc6 | 9090908 | 7659059 | null
  cmmnfmw1703155c85e3zjtle3 | 4981825 | 7659059 | null
```

## Evidence
- Temporary diagnostic: `GET /cezih/_diag/ownership?patient_id=…` (admin, read-only) in
  `api/cezih.py` — dumps raw `author`/`custodian` (docs) and `recorder`/`asserter`/`encounter`
  (conditions) + tenant šifra + ID systems. **Remove once the ownership classifier ships.**
- Builders that set these on the create side: `fhir_api/documents.py` (author/custodian),
  `message_builder` / `builders/condition.py` (recorder/asserter; note `asserter` is dropped for
  case 2.2/2.6 per `2026-04-21-cezih-2.1-asserter-drop.md`, but read-back still shows it).

---
date: 2026-04-29
topic: e2e | sweep | smartcard | foreign | ehic
status: active
---

# 2026-04-29 Smart-card sweep (Foreign ROGER ROG, EHIC-keyed)

## Context

Pre-exam re-verification on prod `app.hmdigital.hr` against `pvsek.cezih.hr`,
**AKD smart-card signing only** (card #558299, JWS ES384 detached). Run
covers the foreign-patient leg of the dual-method, dual-patient exam matrix
- mate to today's Croatian-patient card sweep documented in
`2026-04-29-card-sweep-croatian-oib.md`. Closes the smart-card half of the
exam matrix (Croatian + foreign on card; Croatian + foreign on Certilia
mobile already covered today by `2026-04-29-certilia-mobile-dual-patient-sweep.md`).

Patient: ROGER ROG PACPRIVATNICISTRAN3, EHIC `TEST20251215113521HP`,
drzavljanstvo UK, patient UUID `a2718e2b-dc35-463c-93e6-b9477e4fd5f9`,
CEZIH ID `cmj70pxqx00sg5c85kg429x8n`. PINs entered locally by user at each
card signing prompt.

Skipped per user direction: TC6 (OID gen), TC7 (PDQm raw), TC8/TC10
(SVCM ValueSet ITI-95), TC9 (mCSD), TC22 (ITI-68 retrieve - verified
prior). TC11 PMIR not re-exercised (patient already CEZIH-registered
from prior sweeps; re-running would duplicate). TC10 insurance
eligibility N/A for foreigners.

## Wire-verified TCs

All operations hit prod backend logs with `request_logger` 200 responses
and `SMARTCARD PRE-SIGN` payload assembly visible for every signed step.
Patient identifier path on every CEZIH call confirmed as
`jedinstveni-identifikator-pacijenta` (foreign) - NOT MBO.

| TC | Action | Wire evidence |
|---|---|---|
| TC1 Auth | smart-card mTLS | implicit on every clinical 8443 call |
| TC4 Signing | smart-card JWS | SMARTCARD PRE-SIGN visible on every signed op below |
| TC12 Create visit (1.1) | POST /api/cezih/visits 08:06:26 → 200 (12s) | visit `cmojrtuy003yuhb85mi5fv9so` |
| TC15 Update visit (1.2) | PATCH /api/cezih/visits/{id} 08:07:23 → 200 (13s) | razlog + Hitni prijem |
| TC13 Close visit (1.3) | POST /api/cezih/visits/{id}/action 08:10:26 → 200 | status → Završena |
| TC14 Reopen (1.5) | POST .../action 08:11:22 → 200 | status → U tijeku |
| TC14 Cancel (1.4) | POST .../action 08:12:13 → 200 | status → Stornirana (entered-in-error) |
| TC16 Create case (2.1) | POST /api/cezih/cases 08:13:18 → 200 | case `cmojs2oj203yvhb85k5mm1n2x` (J06.9) |
| TC17 Remission (2.3) | PUT /cases/{id}/status 08:13:59 → 200 | clinicalStatus → remission |
| TC17 Relapse (2.5) | PUT /cases/{id}/status 08:14:23 → 200 | clinicalStatus → relapse |
| TC17 Resolve (2.4) | PUT /cases/{id}/status 08:14:45 → 200 | clinicalStatus → resolved |
| TC17 Reopen (2.9) | PUT /cases/{id}/status 08:15:43 → 200 | clinicalStatus → active |
| TC17 Data update (2.6) | PUT /cases/{id}/data 08:16:15 → 200 | note → "TC17 2.6 foreign EHIC card data-update dry-run 2026-04-29" |
| TC18 Send e-Nalaz (ITI-65) | POST /api/cezih/e-nalaz 08:17:46 → 200 | **Ref 1504392**, Potpis=Da, Poslan |
| TC19 Replace (ITI-65 PUT) | PUT /e-nalaz/1504392/replace-with-edit 08:21:57 → 200 | **Ref 1504559**, Potpis=Da, Zamijenjen |
| TC20 Storno | DELETE /e-nalaz/1504559 08:22:32 → 200 | Ref 1504559 → Storniran (replace-with-OID-relatesTo pattern) |
| TC21 Search docs (ITI-67) | GET /api/cezih/documents 200 | 20 entries returned from CEZIH for this patient |

## UI persistence check

Hard reload after TC20:

- CEZIH → Posjete tab: today's TC15 visit row
  (`Stornirana / Hitni prijem`, 10:06 → 10:11, razlog "Foreign EHIC card
  sweep TC15 update — Hitni prijem 29.04.2026") visible and matches DB
  state.
- CEZIH → Slučajevi: case `cmojs2oj203yvhb85k5mm1n2x` clinical_status=`active`
  verification_status=`confirmed`, note "TC17 2.6 foreign EHIC card
  data-update dry-run 2026-04-29".
- CEZIH → e-Nalazi: Ref `1504559` row shows status `Storniran`, Potpis `Da`,
  created 10:16, Poslan 10:17, Datum izmjene 10:21.

## Card storno bundle inspected

Backend logged the full ITI-65 transaction Bundle for the storno step. Key
fields confirmed (foreign-patient path):

- `Bundle.type = transaction`, 3 entries (List submissionset / DocumentReference
  / Binary), profile `HRMinimalProvideDocumentBundle`.
- New DocumentReference: `masterIdentifier = urn:oid:2.16.840.1.113883.2.7.50.2.1.750018`,
  `status = current`.
- `relatesTo[].code = replaces`, `relatesTo[].target.identifier = urn:oid:2.16.840.1.113883.2.7.50.2.1.750017`
  (the OID for original Ref 1504559 retrieved via ITI-67 base64 data param).
- `subject.identifier.system = .../identifikatori/jedinstveni-identifikator-pacijenta`,
  `value = cmj70pxqx00sg5c85kg429x8n` (foreign path - Croatian path uses MBO
  `999990260`).
- `practiceSetting = 1010000 Opća/obiteljska medicina`.
- `subject.encounter[].identifier.value = cmobh4c3902i8hb85gv8gmvjp` (visit
  chosen in send dialog - the most-recent in-progress visit since today's
  cancelled TC14 visit was filtered out by the dialog), `related[].identifier.value = cmojs2oj203yvhb85k5mm1n2x`
  (case picked in dialog).
- DocumentReference `type.code = 012` "Nalazi iz specijalističke ordinacije
  privatne zdravstvene ustanove" (HRTipDokumenta privatnici).

CEZIH accepted the bundle and flipped 1504559 to Storniran via the
replace-with-`status=current`+OID-relatesTo pattern (NOT `entered-in-error`,
which CEZIH rejects with ERR_DOM_10057 - confirmed previous finding still
holds on this run for foreign patient too).

## Impact

- **Foreign-patient leg of the card sweep GREEN end-to-end** for all
  in-scope TCs (TC1/TC4 + TC12-21 minus the explicitly skipped ones).
  Mate to today's Croatian card sweep + today's dual-patient Certilia mobile
  sweep - dual-method dual-patient parity intact going into the exam.
- All wire ops timed by request_logger:
  - Visit lifecycle ops: 12-158s each (158s on TC13 close - wall-clock
    dominated by user PIN dwell, BE round-trip itself comfortable).
  - Case lifecycle 5x PUT: 10-46s.
  - e-Nalaz POST/PUT/DELETE: 11-20s each.
- No transients, no ERR_DS_*, no agent disconnects observed.
- ITI-65 TC18 send dialog correctly filters cancelled (entered-in-error)
  visits out of the Posjeta dropdown - same behaviour seen on Certilia
  mobile sweep this morning. Selecting an older in-progress visit from
  23.04.2026 was accepted by CEZIH without complaint.

## Action items

- [x] Foreign-patient card leg (ROGER ROG, EHIC) - executed today, full TC
      matrix GREEN, persistence verified. Closes the smart-card half of the
      dual-method, dual-patient exam matrix.
- [ ] No remaining gaps for exam-readiness on either patient class on
      either signing path. Both signing methods verified on Croatian + foreign
      within the same day:
  - Smart card Croatian: `2026-04-29-card-sweep-croatian-oib.md`
  - Smart card foreign: this finding
  - Certilia mobile Croatian + foreign: `2026-04-29-certilia-mobile-dual-patient-sweep.md`
- [ ] Keep wire-evidence pattern (request_logger 200 + SMARTCARD PRE-SIGN +
      UI persistence after reload) as the exam-day smoke-test contract.

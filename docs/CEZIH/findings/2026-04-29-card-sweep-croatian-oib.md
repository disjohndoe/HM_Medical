---
date: 2026-04-29
topic: e2e | sweep | smartcard | croatian
status: active
---

# 2026-04-29 Smart-card sweep (Croatian GORAN, OIB-keyed)

## Context

Pre-exam re-verification on prod `app.hmdigital.hr` against `pvsek.cezih.hr`,
**AKD smart-card signing only** (card #558299, JWS ES384 detached). Run
covers the Croatian-patient leg of the dual-method, dual-patient exam matrix
- mate to today's Certilia-mobile sweep documented in
`2026-04-29-certilia-mobile-dual-patient-sweep.md`.

Patient: GORAN PACPRIVATNICI19, OIB 99999900187, MBO 999990260, CEZIH ID
`cmj1txrtq00jx5c85z9znztob`. PINs entered locally by user at each card
signing prompt.

Skipped per user direction: TC6 (OID gen), TC7 (PDQm raw), TC8/TC10
(SVCM ValueSet ITI-95), TC9 (mCSD), TC22 (ITI-68 retrieve - verified
prior). TC11 PMIR not applicable for Croatian patient (MBO sufficient).
TC2/TC3/TC5 (cloud/Certilia paths) covered separately by today's
Certilia sweep.

## Wire-verified TCs

All operations hit prod backend logs with `request_logger` 200 responses
and `SMARTCARD PRE-SIGN` payload assembly visible for every signed step.

| TC | Action | Wire evidence |
|---|---|---|
| TC1 Auth | smart-card mTLS | implicit on every clinical 8443 call |
| TC4 Signing | smart-card JWS | SMARTCARD PRE-SIGN visible on every signed op below |
| TC12 Create visit (1.1) | POST /api/cezih/visits 07:29:48 → 200 (24s) | visit `cmojqiqgl03ykhb85v26fprfx` |
| TC15 Update visit (1.2) | PATCH /api/cezih/visits/{id} 07:33:03 → 200 | razlog + Hitni prijem |
| TC13 Close visit (1.3) | POST /api/cezih/visits/{id}/action 07:33:40 → 200 | status → Završena |
| TC14 Cancel (1.4) | POST .../action 07:34:47 → 200 | status → Stornirana |
| TC14 Reopen (1.5) | POST .../action 07:35:14 → 200 | status → U tijeku |
| TC16 Create case (2.1) | POST /api/cezih/cases 07:36:32 → 200 | case `cmojqreau03ylhb85am3ab367` (J06.9) |
| TC17 Remission (2.3) | PUT /cases/{id}/status 07:38:40 → 200 | clinicalStatus → remission |
| TC17 Relapse (2.5) | PUT /cases/{id}/status 07:39:15 → 200 | clinicalStatus → relapse |
| TC17 Resolve (2.4) | PUT /cases/{id}/status 07:39:39 → 200 | clinicalStatus → resolved |
| TC17 Reopen (2.9) | PUT /cases/{id}/status 07:40:02 → 200 | clinicalStatus → active |
| TC17 Data update (2.6) | PUT /cases/{id}/data 07:40:45 → 200 | note → "TC17 2.6 card data-update OIB exam dry-run 2026-04-29" |
| TC18 Send e-Nalaz (ITI-65) | POST /api/cezih/e-nalaz 07:51:41 → 200 | **Ref 1503283**, Potpis=Da, Poslan |
| TC19 Replace (ITI-65 PUT) | PUT /e-nalaz/1503283/replace-with-edit 07:52:39 → 200 | **Ref 1503302**, Potpis=Da, Zamijenjen |
| TC20 Storno | DELETE /e-nalaz/1503302 07:56:12 → 200 | Ref 1503302 → Storniran (replace-with-OID-relatesTo pattern) |
| TC21 Search docs (ITI-67) | GET /api/cezih/documents 200 | 20 entries returned from CEZIH for this patient |

## UI persistence check

Hard reload after TC20:

- CEZIH → Posjete tab: today's TC15 visit row (`Stornirana / Hitni prijem`,
  09:29 → 09:35, razlog "Exam dry-run TC15 card update — izmjena razloga
  + Hitni prijem 29.04.2026") visible and matches DB state.
- CEZIH → Slučajevi: case `cmojqreau03ylhb85am3ab367` clinical_status=`active`
  verification_status=`confirmed`, note "TC17 2.6 card data-update OIB exam
  dry-run 2026-04-29".
- CEZIH → e-Nalazi: Ref `1503302` row shows status `Storniran`, Potpis `Da`,
  created 09:41, Poslan 09:51, Datum izmjene 09:52.

## Card storno bundle inspected

Backend logged the full ITI-65 transaction Bundle for the storno step. Key
fields confirmed:

- `Bundle.type = transaction`, 3 entries (List submissionset / DocumentReference
  / Binary), profile `HRMinimalProvideDocumentBundle`.
- New DocumentReference: `masterIdentifier = urn:oid:2.16.840.1.113883.2.7.50.2.1.749997`,
  `status = current`.
- `relatesTo[].code = replaces`, `relatesTo[].target.identifier = urn:oid:2.16.840.1.113883.2.7.50.2.1.749991`
  (the OID for original Ref 1503283 retrieved via ITI-67 base64 data param).
- `subject.identifier.system = .../identifikatori/MBO`, `value = 999990260`
  (Croatian MBO path - foreign uses `jedinstveni-identifikator-pacijenta`).
- `practiceSetting = 1010000 Opća/obiteljska medicina`.
- `subject.encounter[].identifier.value = cmojomx8m03y3hb85onz4a6l2` (visit chosen
  in send dialog), `related[].identifier.value = cmojqreau03ylhb85am3ab367`
  (case picked in dialog).

CEZIH accepted the bundle and flipped 1503302 to Storniran via the
replace-with-`status=current`+OID-relatesTo pattern (NOT `entered-in-error`,
which CEZIH rejects with ERR_DOM_10057 - confirmed previous finding still
holds on this run).

## Impact

- **Croatian-patient leg of the card sweep GREEN end-to-end** for all
  in-scope TCs (TC1/TC4 + TC12-21 minus the explicitly skipped ones).
  Mate to today's Certilia-mobile sweep - dual-method dual-patient parity
  intact going into the exam.
- All wire ops timed by request_logger:
  - Visit lifecycle ops: 12-25s each (card sign + VPN + CEZIH roundtrip).
  - Case lifecycle 5x PUT: 13-89s (first remission included signing UI dwell).
  - e-Nalaz POST/PUT/DELETE: 12-21s each.
- No transients, no ERR_DS_*, no agent disconnects observed.

## Action items

- [ ] Foreign-patient card leg (ROGER ROG, EHIC) - planned next, completes
      the smart-card half of the dual-method, dual-patient exam matrix.
- [ ] Keep wire-evidence pattern (request_logger 200 + SMARTCARD PRE-SIGN +
      UI persistence after reload) as the exam-day smoke-test contract.

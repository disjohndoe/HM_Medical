---
date: 2026-05-18
topic: e2e | sweep | smartcard | croatian | pre-exam
status: active
---

# 2026-05-18 Smart-card sweep (Croatian GORAN, OIB-keyed) - pre-exam dry-run

## Context

Pre-exam re-verification on prod `app.hmdigital.hr` against `pvsek.cezih.hr`,
**AKD smart-card signing only** (card #558299, JWS ES384 detached). Run
covers the Croatian leg of the dual-method exam matrix ahead of the
upcoming provjera spremnosti retry.

Patient: GORAN PACPRIVATNICI19, OIB `99999900187`, MBO `999990260`, internal
id `245ec690-a024-4c90-b6d3-62621eca4d47`. PINs entered locally by user at
each card signing prompt.

Skipped per user direction: TC6 (OID gen), TC7 (PDQm raw), TC8/TC10 (SVCM
ValueSet ITI-95), TC9 (mCSD), TC22 (ITI-68 retrieve - covered by Phase 21
work). TC11 PMIR not applicable for Croatian patient (MBO sufficient).
TC2/TC3/TC5 (Certilia paths) deferred to a later mobile pass.

## Wire-verified TCs

All operations hit prod backend logs with `request_logger` 200 responses
and `SMARTCARD PRE-SIGN` payload assembly visible for every signed step.

| TC | Action | Wire evidence (UTC) |
|---|---|---|
| TC1 Auth | smart-card mTLS | implicit on every clinical 8443 call |
| TC4 Signing | smart-card JWS | SMARTCARD PRE-SIGN visible on every signed op below |
| TC12 Create visit (1.1) | POST /api/cezih/visits 05:08:34 -> 200 (11.8s) | visit `cmpaquahg05jyhb85lz45bbbk` |
| TC15 Update visit (1.2) | PATCH /api/cezih/visits/{id} 05:09:33 -> 200 (15.5s) | razlog + Hitni prijem |
| TC13 Close visit (1.3) | POST .../action 05:10:06 -> 200 (19.3s) | status -> Zavrsena |
| TC14 Cancel visit (1.4) | POST .../action 05:11:39 -> 200 (12.7s) | status -> Stornirana |
| TC14 Reopen visit (1.5) | POST .../action 05:13:37 -> 200 (15.8s) | status -> U tijeku |
| TC16 Create case (2.1) | POST /api/cezih/cases 05:17:22 -> 200 (14.6s) | case `cmpar5mbb05jzhb85my4vzwjk` (J06.9) |
| TC17 Remission (2.3) | PUT /cases/{id}/status 05:17:51 -> 200 (11.4s) | clinicalStatus -> remission |
| TC17 Relapse (2.5) | PUT /cases/{id}/status 05:20:38 -> 200 (15.3s) | clinicalStatus -> relapse |
| TC17 Resolve (2.4) | PUT /cases/{id}/status 05:21:32 -> 200 (18.0s) | clinicalStatus -> resolved |
| TC17 Reopen (2.9) | PUT /cases/{id}/status 05:22:14 -> 200 (12.3s) | clinicalStatus -> relapse (prior active sub-state) |
| TC17 Data update (2.6) | PUT /cases/{id}/data 05:28:38 -> 200 (36.2s) | note -> "TC17 2.6 card OIB E2E exam 2026-05-18 - data update after reopen" (first attempt 05:23:27 200 not surfaced as toast; retry persisted) |
| TC18 Send e-Nalaz (ITI-65) | POST /api/cezih/e-nalaz 05:30:49 -> 200 (12.4s) | **Ref 1609281**, Status Poslan (also Ref 1609286 from earlier accidental first submit, 05:29:56 -> 200, 44.1s) |
| TC19 Replace (ITI-65 PUT) | PUT /e-nalaz/1609281/replace-with-edit 05:31:52 -> 200 (14.6s) | **Ref 1609291**, original 1609281 flipped to Izmijenjen |
| TC20 Storno | DELETE /e-nalaz/1609291 05:34:12 -> 200 (14.6s) | Ref 1609291 -> Storniran (replace-with-OID-relatesTo) |
| TC21 Search docs (ITI-67) | Dohvati e-Karton triggered ITI-67 search | 68 aktivne dijagnoze rendered from CEZIH for this patient |

Zero `ERR_DS_*`, `ERR_DOM_*`, `ERR_EHE_*`, `ERR_PMIR_*`, `ERR_HEALTH_*`,
`ERR_DOCTRANSVAL_*` in 90 minutes of backend logs across this run.

## UI persistence check

All TC results verified visually in the UI tabs after each action:

- CEZIH -> Posjete: visit `cmpaquahg05jyhb85lz45bbbk` walked through
  U tijeku -> Zavrsena -> Stornirana -> U tijeku across the TC12/13/14/15
  sequence.
- CEZIH -> Slucajevi: case `cmpar5mbb05jzhb85my4vzwjk` walked through
  Aktivan -> Remisija -> Relaps -> Zatvoren -> Relaps (reopen returns to
  prior active sub-state, not raw Aktivan - acceptable CEZIH behaviour),
  with napomena "TC17 2.6 card OIB E2E exam 2026-05-18 - data update after
  reopen" persisted via 2.6.
- CEZIH -> e-Nalazi: chain 1609281 -> 1609291 -> Storniran visible at top
  of the table after each step, plus the spare 1609286 row Poslan.
- CEZIH -> e-Karton: ITI-67/68 retrieval rendered 68 active dijagnoze
  pulled from CEZIH.

## TC17 2.6 dialog quirk

First Spremi izmjene click left the dialog open with the request body
posted at 05:23:27 (PUT /cases/.../data 200). No toast surfaced and the
dialog stayed mounted, then closed shortly after. Re-opening the dialog
showed the napomena value already populated. A second Spremi click (05:28:38
-> 200) produced the "Podaci slucaja azurirani" toast. Two PUTs reached
CEZIH with the same payload; both 200; second one is the one with toast
confirmation. UX worth tightening but not exam-blocking.

## Impact

- **Croatian-patient leg of the card sweep GREEN end-to-end** for all
  in-scope TCs going into the next provjera spremnosti attempt.
- Wire op timings consistent with prior sweeps (visit 12-19s, case status
  PUT 11-18s, e-Nalaz POST/PUT/DELETE 12-44s).
- Spinner UX ("Salje se na CEZIH... Ceka se potpis i potvrda. Postupak
  moze potrajati do 30 sekundi.") shown for every signed op as expected.
- No transients, no ERR_*, no agent disconnects observed.

## Action items

- [ ] Certilia mobile leg (Croatian GORAN) - rerun before exam to confirm
      both methods still GREEN under current is_exam_tenant + Phase 21 fix.
- [ ] Foreign patient leg (ROGER ROG EHIC / passport) - card and mobile.
- [ ] Keep wire-evidence pattern (request_logger 200 + SMARTCARD PRE-SIGN +
      UI persistence after reload) as the exam-day smoke-test contract.
- [ ] Investigate TC17 2.6 dialog: first click should surface toast and
      close dialog; current behaviour double-posts on retry. Low priority -
      not exam blocking.

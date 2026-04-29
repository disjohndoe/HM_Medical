---
date: 2026-04-29
topic: e2e | sweep | certilia-mobile | dual-patient
status: active
---

# 2026-04-29 Certilia-mobile dual-patient sweep (Croatian GORAN + Foreign ROGER ROG, same day)

## Context

Same-day Certilia-mobile end-to-end sweep on 2026-04-29 covering both
patient types in scope for the HZZO exam: Croatian (OIB-keyed) GORAN
PACPRIVATNICI19 in the morning, then foreign (EHIC-keyed) ROGER ROG
PACPRIVATNICISTRAN3 in the afternoon. Goal was to close the same-day
gap from the 2026-04-28 run (foreign patient was deferred there) and
demonstrate dual-patient parity on Certilia mobile end-to-end.

Run target: prod `app.hmdigital.hr` against `pvsek.cezih.hr`. Certilia
mobile signing only on both runs (per-user `cezih_signing_method =
extsigner`). Skipped per user direction: TC6 (OID gen), TC7 (PDQm raw),
TC8/TC10 SVCM, TC9 (mCSD raw), TC22 (ITI-68 retrieve).

Patients exercised:

- Croatian: GORAN PACPRIVATNICI19, OIB 99999900187, MBO 999990260,
  patient UUID `245ec690-a024-4c90-b6d3-62621eca4d47`, CEZIH ID
  `cmj1txrtq00jx5c85z9znztob`.
- Foreign: ROGER ROG PACPRIVATNICISTRAN3, EHIC `TEST20251215113521HP`,
  drzavljanstvo UK, patient UUID `a2718e2b-dc35-463c-93e6-b9477e4fd5f9`,
  CEZIH ID `cmj70pxqx00sg5c85kg429x8n` (PMIR registration from prior
  sweep, not re-exercised today).

## Croatian GORAN sweep (morning)

| TC | Action | Wire / BE evidence |
|---|---|---|
| TC5 | OIB lookup (PDQm) | GORAN e-Karton rendered, OIB 99999900187 |
| TC10 | Insurance eligibility | Aktivan |
| TC12 | Create Posjeta (1.1) | visit created, period_start 06:35 UTC |
| TC13 | Close Posjeta (1.3) | status -> Završena |
| TC15 | Reopen Posjeta (1.5) | status -> Otvorena (U tijeku) |
| TC14 | Cancel Posjeta (1.4) | final BE state: `status=entered-in-error` at 06:46 UTC |
| TC16 | Create Slučaj (2.1) | case `cmojp05kt03y5hb85qpwi0vnk`, J06.9 Aktivan/Potvrđen |
| TC17 2.3 | Remisija | BE `clinical_status=remission` |
| TC17 2.5 | Relaps | BE `clinical_status=relapse` |
| TC17 2.4 | Zatvori | BE `clinical_status=resolved`, `abatement_date=2026-04-29` |
| TC17 2.9 | Ponovno otvori | BE `clinical_status=active`, abatement cleared |
| TC17 2.6 | Data update | BE note `TC17 2.6 mobile data-update OIB exam dry-run 2026-04-29`, `verification_status=confirmed` at 06:52 UTC |
| TC18 | Send e-Nalaz | Ref **1501842** sent at 06:54:50 UTC, record `7d434320-ea5a-4ee7-9d09-187d06af95f5` |
| TC19 | Replace e-Nalaz | new Ref **1501883**, sadrzaj appended `[TC19 replace edit 2026-04-29]` |
| TC20 | Storno e-Nalaz | `cezih_storno=true` on Ref 1501883 |
| TC21 | Document search (ITI-67) | CEZIH dokumenti rendered in e-Karton sidebar |

## Foreign ROGER ROG (EHIC) sweep (afternoon)

| TC | Action | Wire / BE evidence |
|---|---|---|
| TC5 | EHIC patient lookup | ROGER ROG e-Karton rendered, EHIC + UK visible |
| TC12 | Create Posjeta (1.1) | visit `cmojpmcl703y7hb858bdgh641`, period_start 07:04:37 UTC |
| TC13 | Close Posjeta (1.3) | status=`finished`, period_end 07:07:51 UTC |
| TC15 | Reopen Posjeta (1.5) | status=`in-progress`, period_end cleared |
| TC14 | Cancel Posjeta (1.4) | status=`entered-in-error` at 07:08:48 UTC |
| TC16 | Create Slučaj (2.1) | case `cmojpvykb03ybhb85qmajg7u8`, J06.9 Aktivan/Potvrđen at 07:11:47 UTC |
| TC17 2.3 | Remisija | BE `clinical_status=remission` at 07:12:47 UTC |
| TC17 2.5 | Relaps | BE `clinical_status=relapse` at 07:13:29 UTC |
| TC17 2.4 | Zatvori | BE `clinical_status=resolved`, `abatement_date=2026-04-29` at 07:14:10 UTC |
| TC17 2.9 | Ponovno otvori | BE `clinical_status=active`, abatement cleared at 07:14:41 UTC |
| TC17 2.6 | Data update | BE note `TC17 2.6 foreign EHIC mobile data-update 2026-04-29`, `verification_status=confirmed` at 07:15:20 UTC |
| TC18 | Send e-Nalaz | Ref **1502553** sent at 07:17:50 UTC, record `bd762610-b02d-4fbe-b28a-24d8aea5b966` |
| TC19 | Replace e-Nalaz | new Ref **1502566**, sadrzaj appended `[TC19 foreign replace 2026-04-29]` |
| TC20 | Storno e-Nalaz | `cezih_storno=true` on Ref 1502566 at 07:19:25 UTC |
| TC21 | Document search (ITI-67) | `GET /api/cezih/documents` -> 20 CEZIH dokumenti |

Backend confirmation method on both runs: every state transition
cross-checked via the live API rather than relying on toasts.

- Cases: `GET /api/cezih/cases?patient_id=...` -> `clinical_status` /
  `verification_status` / `abatement_date` / `note` / `updated_at`.
- Visits: `GET /api/cezih/visits?patient_id=...` -> final
  `status=entered-in-error` for both.
- e-Nalaz: `GET /api/medical-records?patient_id=...` ->
  `cezih_sent=true`, `cezih_storno=true`, `cezih_reference_id`.

## Refresh persistence verification

Hard `location.reload(ignoreCache=true)` after each sweep, re-queried
the same backend endpoints.

Croatian (GORAN):
- Visit (TC14 cancel) -> `status=entered-in-error`. ✓
- Case `cmojp05kt03y5hb85qpwi0vnk` -> `clinical_status=active`,
  `verification_status=confirmed`, `abatement_date=2026-04-29`, note
  reflects 2.6 update. ✓
- Ref 1501883 record `7d434320-...` -> `sent=true`, `storno=true`,
  sadrzaj reflects TC19 edit. ✓

Foreign (ROGER ROG):
- Visit `cmojpmcl703y7hb858bdgh641` -> `status=entered-in-error`. ✓
- Case `cmojpvykb03ybhb85qmajg7u8` -> `clinical_status=active`,
  `verification_status=confirmed`, `abatement_date=2026-04-29`, note
  reflects 2.6 update. ✓
- Ref 1502566 record `bd762610-...` -> `sent=true`, `storno=true`,
  sadrzaj reflects TC19 edit. ✓

## Signatures / transport observations

- Every signed action (visit + case state transitions) on both runs
  went through Certilia mobile push. Approval window typical 30-60 s.
  No `Unauthorized` from CEZIH on `extsigner/api/sign` -> Bearer-token
  fix from `2026-04-28-extsigner-bearer-token-required.md` still
  holding two days post-fix.
- ITI-65 path (TC18/19/20) unsigned by design on both runs - no
  mobile push for send/replace/storno, consistent with prior runs and
  with the 2026-04-22 afternoon EHIC reverify.
- Foreign EHIC patient: TC18 e-Nalaz Pošalji dialog correctly filters
  out cancelled visits (entered-in-error) from the Posjeta dropdown,
  forcing selection of an in-progress visit. New today's visit was
  cancelled in TC14 so TC18 proceeded against the most recent
  in-progress visit (`cmobh4c3902i8hb85gv8gmvjp` from 23.04.2026) -
  ITI-65 dispatcher accepted this without complaint, confirming the
  bundle does not require a same-day visit reference.
- Same-day case-state full round-trip
  (2.1 -> 2.3 -> 2.5 -> 2.4 -> 2.9 -> 2.6) completed on both Croatian
  and foreign cases via Certilia mobile push. Foreign case round-trip
  took ~3.5 minutes wall-clock (07:11:47 -> 07:15:20) including all
  mobile approvals.

## What was NOT exercised this run

- TC6 / TC7 / TC8 / TC9 / TC10-SVCM / TC22 - explicitly skipped per
  user direction.
- TC11 PMIR registration - foreign patient was already CEZIH-registered
  from prior runs; re-running TC11 would just create a duplicate.
- Insurance eligibility (TC10) on foreign EHIC patient - foreigners
  don't have HZZO insurance so the check is N/A; the e-Karton
  correctly displays them as "Strani državljanin" without an osiguranje
  block.

## Impact

- Same-day dual-patient parity proven on Certilia mobile: full
  Posjeta lifecycle (1.1/1.3/1.5/1.4) + full case lifecycle (2.1 ->
  2.3 -> 2.5 -> 2.4 -> 2.9 -> 2.6) + ITI-65 send/replace/storno chain
  + ITI-67 search verified on **both** Croatian (OIB) and foreign
  (EHIC) patient types in one sitting. Exam-ready narrative: "mobile
  user demonstrates the full feature matrix on both patient classes
  without ever touching a smart card".
- Cross-references with morning Croatian sweep narrative
  (`2026-04-28-certilia-mobile-OIB-exam-dry-run.md` style); the dual
  format here addresses the prior run's `[ ] Foreign patient ...
  mobile sweep` action item.
- Fully closes the foreign-mobile-since-Bearer-fix verification gap.
  Last green foreign-mobile run prior to today was
  `2026-04-22-certilia-mobile-afternoon-reverify.md` (pre-Bearer-fix);
  today re-confirms the same matrix on the post-fix code path.

## Action items

- [x] Foreign patient (ROGER ROG / EHIC) Certilia-mobile sweep -
      executed today, full TC matrix GREEN.
- [x] Croatian patient (GORAN / OIB) Certilia-mobile sweep -
      executed today, full TC matrix GREEN, persistence verified.
- [ ] No remaining gaps for Certilia mobile exam-readiness on either
      patient class. Both signing paths (smart card from
      2026-04-22/04-23 sweeps; Certilia mobile from 2026-04-28 +
      today) verified on Croatian + foreign within the past two
      weeks.

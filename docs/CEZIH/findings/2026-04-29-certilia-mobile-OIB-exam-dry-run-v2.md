---
date: 2026-04-29
topic: e2e | sweep | certilia-mobile | OIB | exam-dry-run
status: active
---

# 2026-04-29 Certilia-mobile OIB-only exam dry-run v2 (Croatian GORAN, third sweep of the day)

## Context

Third Certilia-mobile sweep on 2026-04-29, mobile + Croatian (OIB-keyed)
GORAN PACPRIVATNICI19 only. Same-day predecessors:

1. Morning dual-patient mobile sweep (Croatian + Foreign EHIC) -
   `2026-04-29-certilia-mobile-dual-patient-sweep.md`.
2. Mid-day smart-card sweeps (Croatian + Foreign EHIC) -
   `2026-04-29-card-sweep-croatian-oib.md` +
   `2026-04-29-card-sweep-foreign-ehic.md`.

This run reinforces the mobile + OIB combo specifically, per user's
"for now lets JUST DO mobile, for OIB, for our exam" pivot. Goal was
yet another full mobile-only TC matrix on a fresh visit + case to
confirm the `extsigner` Bearer-token fix from `960cf3e` continues to
hold three sweeps deep into the same day.

Run target: prod `app.hmdigital.hr` against `pvsek.cezih.hr`. Per-user
`cezih_signing_method = extsigner`. Skipped per user direction: TC6,
TC7, TC8/TC10 SVCM, TC9, TC22.

Patient: GORAN PACPRIVATNICI19, OIB 99999900187, MBO 999990260,
patient UUID `245ec690-a024-4c90-b6d3-62621eca4d47`, CEZIH ID
`cmj1txrtq00jx5c85z9znztob`.

## Test matrix

| TC | Action | Wire / BE evidence |
|---|---|---|
| TC5 | OIB lookup (PDQm) | GORAN e-Karton rendered, OIB 99999900187 |
| TC10 | Insurance eligibility | Aktivan |
| TC12 | Create Posjeta (1.1) | visit `cmojugowz03z9hb85yyfgmops`, period_start 09:20:11 UTC, reason "TC12 mobile OIB exam dry-run 2026-04-29" |
| TC13 | Close Posjeta (1.3) | eventCoding 1.3, hr-close-encounter-message at 09:21:41 UTC |
| TC15 | Reopen Posjeta (1.5) | eventCoding 1.5, hr-reopen-encounter-message at 09:27:06 UTC |
| TC14 | Cancel Posjeta (1.4) | eventCoding 1.4, hr-cancel-encounter-message at 09:28:11 UTC, BE `status=entered-in-error` |
| TC16 | Create Slučaj (2.1) | case `cmojushdm03zchb85kf3u7acy`, J06.9 Aktivan/Potvrđen at 09:29:03 UTC |
| TC17 2.3 | Remisija | BE `clinical_status=remission` at 09:30:05 UTC |
| TC17 2.5 | Relaps | BE `clinical_status=relapse` at 09:30:36 UTC |
| TC17 2.4 | Zatvori | BE `clinical_status=resolved`, `abatement_date=2026-04-29` at 09:31:08 UTC |
| TC17 2.9 | Ponovno otvori | BE `clinical_status=active` at 09:31:43 UTC |
| TC17 2.6 | Data update | BE note `TC17 2.6 mobile OIB exam dry-run data update 2026-04-29`, `verification_status=confirmed` at 09:32:18 UTC |
| TC18 | Send e-Nalaz | Ref **1505712** sent at 09:36:04 UTC, record `dc3d4dc5-03bf-49d3-893d-aa7a93d8a556`, ITI-65 unsigned, doc OID `urn:oid:2.16.840.1.113883.2.7.50.2.1.750050` |
| TC19 | Replace e-Nalaz | new Ref **1505716** at 09:36:57 UTC, sadrzaj appended `[TC19 mobile replace edit 2026-04-29]`, relatesTo `replaces` -> `urn:oid:...750050`, new OID `...750051`, PUT /replace-with-edit -> 200 |
| TC20 | Storno e-Nalaz | DELETE /api/cezih/e-nalaz/1505716 -> 200 at 09:37:44 UTC, ITI-65 transaction relatesTo `replaces` -> `urn:oid:...750051`, new OID `...750052`, Binary `Storno dokumenta 1505716` |
| TC21 | Document search (ITI-67) | `GET /api/cezih/documents` -> 200, 20 CEZIH dokumenti |

Backend confirmation method: every state transition cross-checked
against the live API rather than relying on toasts.

- Cases: `GET /api/cezih/cases?patient_id=...` -> `clinical_status` /
  `verification_status` / `abatement_date` / `note` / `updated_at`.
- Visits: `GET /api/cezih/visits?patient_id=...` -> final
  `status=entered-in-error`.
- e-Nalaz: `GET /api/medical-records?patient_id=...` ->
  `cezih_sent=true`, `cezih_storno=true`, `cezih_reference_id`.
- ITI-67: `GET /api/cezih/documents?patient_id=...` returns plain
  array (not envelope object).

SSH log confirmation pattern (from prod backend container):

- ITI-65 send: `ITI-65 build` + `ITI-65 transaction bundle detected — skipping extsigner (unsigned send)` + `Successfully created resource "DocumentReference/1505712"` + `Extracted document reference ID: 1505712`.
- ITI-65 replace: same path, plus `relatesTo[code=replaces, target=urn:oid:...750050]` + `PUT /api/cezih/e-nalaz/1505712/replace-with-edit -> 200`.
- ITI-65 storno: same path, `relatesTo[code=replaces, target=urn:oid:...750051]` + Binary `Storno dokumenta 1505716` + `DELETE /api/cezih/e-nalaz/1505716 -> 200`.
- ITI-67: `GET /api/cezih/documents -> 200 (1081.4ms)`.

## Refresh persistence verification

Hard `location.reload(ignoreCache=true)` after the sweep, re-queried
the same backend endpoints:

- Visit `cmojugowz03z9hb85yyfgmops` -> `status=entered-in-error`. ✓
- Case `cmojushdm03zchb85kf3u7acy` -> `clinical_status=active`,
  `verification_status=confirmed`, `abatement_date=2026-04-29`,
  note `TC17 2.6 mobile OIB exam dry-run data update 2026-04-29`,
  `updated_at=2026-04-29T09:32:18.346509Z`. ✓
- Ref 1505716 record `dc3d4dc5-...` -> `cezih_sent=true`,
  `cezih_storno=true`. ✓

## Signatures / transport observations

- Every signed action (visit + case state transitions) went through
  Certilia mobile push. Approval window typical 30-60 s. No
  `Unauthorized` from CEZIH on `extsigner/api/sign` -> Bearer-token
  fix from `2026-04-28-extsigner-bearer-token-required.md` continues
  to hold one full day post-fix, three sweeps deep.
- ITI-65 path (TC18/19/20) unsigned by design - no mobile push for
  send/replace/storno, consistent with prior sweeps.
- TC18 e-Nalaz Pošalji dialog correctly filters out cancelled visits
  (entered-in-error). Today's TC12 visit was cancelled in TC14, so
  TC18 used a different in-progress visit `cmojomx8m03y3hb85onz4a6l2`
  (also from today) - ITI-65 dispatcher accepted without complaint,
  re-confirming bundle does not require visit reference to match the
  same-day visit lifecycle.
- Same-day case-state full round-trip (2.1 -> 2.3 -> 2.5 -> 2.4 ->
  2.9 -> 2.6) completed in 3:15 wall-clock (09:29:03 -> 09:32:18 UTC)
  including all six mobile push approvals.
- Document OID generation (TC6 path) ran transparently on every
  ITI-65 send/replace/storno - generated `...750050`, `...750051`,
  `...750052` respectively.

## What was NOT exercised this run

- TC6 / TC7 / TC8 / TC9 / TC10-SVCM / TC22 - explicitly skipped per
  user direction.
- TC11 PMIR registration - patient is OIB-keyed, not applicable.
- Foreign EHIC patient - explicitly out of scope, "JUST DO mobile,
  for OIB" per user direction. Foreign mobile already covered in
  morning dual-patient sweep.

## Impact

- Third Certilia-mobile mobile-only OIB sweep of the same day, all
  GREEN. Combined with the morning dual-patient sweep and the two
  smart-card sweeps, today's evidence covers all four
  method × patient-class quadrants (card+OIB, card+EHIC, mobile+OIB,
  mobile+EHIC) - and now mobile+OIB has been re-verified three times
  on three independent visit/case/Ref triples.
- Bearer-token fix from `960cf3e` continues to hold across all three
  mobile sweeps within the same day.
- Exam-ready narrative for Certilia mobile + Croatian/OIB workflow:
  fresh visit + case + e-Nalaz lifecycle in under 20 minutes
  end-to-end with no manual retries.

## Action items

- [x] Mobile + OIB Certilia-mobile sweep #3 - executed today, full
      TC matrix GREEN, persistence verified.
- [ ] No remaining gaps for Certilia mobile exam-readiness on
      Croatian/OIB patient class. Both signing paths verified working
      on both patient classes within the past 24 hours.

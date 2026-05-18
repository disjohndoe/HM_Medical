---
date: 2026-05-18
topic: certification | pre-exam | sweep | certilia-mobile | doc-type | visit-case-link | stranac-jid
status: active
---

# 2026-05-18 Pre-exam sweep - Certilia mobile leg of HZZO 2026-05-11 rejection items, GREEN

## Context

Companion to `2026-05-18-pre-exam-three-rejection-items-verified.md` (smart card baseline). Same prod (`app.hmdigital.hr`), same test env (`pvsek.cezih.hr`), same exam tenant Ordinacija Horvat (`is_exam_tenant=true`, `djelatnost_code=2030000`, `sifra_ustanove=999001464`), same user Marko Kovacevic (`djelatnost_code=2010000`). Signing path swapped to mobile Certilia (extsigner POST + push-to-mobile flow); agent + VPN + mTLS baseline unchanged per the signing-independence rule.

Test patients:
- Croatian: GORAN PACPRIVATNICI19 (MBO `999990260`, OIB `99999900187`)
- Foreigner: MOBILE STRANCERTI20260518, DEU, passport `TEST20260518M` (PMIR-created on this run)

Goal: re-verify the three HZZO 2026-05-11 rejection items on the mobile Certilia path without using the smart card at all, so the next provjera spremnosti termin can be claimed on either signing method.

## HZZO 2026-05-11 rejection items - mobile Certilia evidence

### Item 1 - Foreigner JID must be numeric

PMIR (TC11) accepted by CEZIH: `Patient/1611164` returned. CEZIH again wrote a CUID into the `jedinstveni-identifikator-pacijenta` slot of the response (`cmpb1vvqa05lbhb85bf01qujp`).

JID strict-shape guard refused it:

```
PMIR extracted: patient_id=1611164, mbo=, cezih_id=
```

DB state: foreign patient `e586318b-fb7a-4347-a2ec-018eb508dcb7` `cezih_patient_id` stayed `NULL`. Subject reference fallback chain in `backend/app/services/cezih/fhir_api/identifiers.py` -> `resolve_cezih_identifier()` landed on `putovnica|TEST20260518M` for all downstream FHIR ops (case, visit, e-Nalaz, ITI-67), and CEZIH accepted every one.

### Item 2 - Doc type x djelatnost = 012 for prefix-2

Both Croatian and foreigner e-Nalaz wires sent as `Specijalisticki nalaz` -> HRTipDokumenta **012** -> display "Nalazi iz specijalisticke ordinacije privatne zdravstvene ustanove". Practitioner djelatnost `2010000` Internisticka (prefix-2), valid pair with 012.

Croatian GORAN ITI-65 chain (earlier in same session, pre-compaction): Ref 1611107 -> 1611123 -> Storniran.

Foreigner MOBILE STRANCERTI20260518 ITI-65 chain (this leg):

| TC | Op | Wire result |
|---|---|---|
| TC18 | ITI-65 POST | List/1611270 + **DocumentReference/1611271** + Binary/1611272, 201 Created x3 |
| TC19 | PUT `/api/cezih/e-nalaz/1611271/replace-with-edit` | 200 OK in 19.8s, new ref **1611285** Izmijenjen |
| TC20 | DELETE `/api/cezih/e-nalaz/1611285` | 200 OK in 13.7s, ref 1611285 Storniran (replace-with-OID-relatesTo) |
| TC21 | ITI-67 GET e-Karton | 1 e-Nalaz, "Nalazi iz specijalisticke ordinacije privatne zdravstvene ustanove" (012 display string), Ordinacija Horvat, 18.05.2026 |

### Item 3 - Posjeta x Slucaj eKarton linkage

Foreigner case `cmpb1xdfo05lchb85dm1e5wbn` (J06.9, Aktivan). Two visits both linked to it via `Encounter.diagnosis.condition.identifier` system `.../identifikatori/identifikator-slucaja`:

- `cmpb1yzdl05lfhb855mx4hr9r` - full lifecycle 1.1 -> 1.2 -> 1.3 -> 1.5 reopen -> 1.4 storno
- Fresh visit @ 12:24 - 1.1 only, used as the encounter context for the e-Nalaz

In-app e-Karton render (ITI-67 search response from CEZIH):

- Dijagnoze 1/1: J06.9 Aktivan od 18.05.2026
- Posjete row "Foreign sweep 2026-05-18 mobile Certilia - fresh visit for e-Nalaz chain TC18-21" 18.05.2026 12:24 U tijeku
- e-Nalazi 1 row, doc type 012 display, Ordinacija Horvat 18.05.2026

DocumentReference for the e-Nalaz carries both backrefs in `context`: `encounter[]` -> the 12:24 visit, `related[]` -> the J06.9 case. Same builder code path as smart card; the only thing that changed is the signing step.

## Log audit

`docker compose logs backend --since 90m | grep -E 'ERR_DS_|ERR_DOM_|ERR_EHE_|ERR_PMIR_|ERR_HEALTH_|ERR_DOCTRANSVAL_|Traceback|500 Internal'` returned zero matches for the window covering the full mobile Certilia sweep. Every signed op returned 200/201 on the wire.

## Combined cert matrix (smart card + mobile Certilia)

| Patient | Signing | Subject id | Doc type | e-Nalaz chain | Visit-case link in eKarton |
|---|---|---|---|---|---|
| Croatian GORAN (MBO 999990260) | Smart card | MBO | 012 | 1609343 -> 1609357 -> Storniran | Yes |
| Foreigner HZZOTEST STRANAC20260518 (passport TEST20260518A) | Smart card | putovnica | 012 | 1609495 -> 1609504 -> Storniran | Yes |
| Croatian GORAN (MBO 999990260) | Mobile Certilia | MBO | 012 | 1611107 -> 1611123 -> Storniran | Yes |
| Foreigner MOBILE STRANCERTI20260518 (passport TEST20260518M) | Mobile Certilia | putovnica | 012 | 1611271 -> 1611285 -> Storniran | Yes |

Both signing methods cleared all three rejection items on both patient classes. Independent of each other per the signing-independence rule (`feedback_signing_independence`); neither path falls back to the other.

## Conclusion

All three HZZO 2026-05-11 rejection items are now verified GREEN on both signing methods. System is exam-ready against the specific rejection items regardless of which method HZZO asks us to demo.

## Action items

- [x] Smart card sweep done (companion doc `2026-05-18-pre-exam-three-rejection-items-verified.md`)
- [x] Mobile Certilia sweep done (this doc)
- [ ] Request next provjera spremnosti termin from HZZO (`Provjera.Spremnosti@hzzo.hr`)
- [ ] After exam pass, revert `is_exam_tenant=true` per `docs/todo/post-exam-hardening.md`

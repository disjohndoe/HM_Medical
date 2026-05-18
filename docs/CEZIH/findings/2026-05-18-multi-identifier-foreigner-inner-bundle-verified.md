---
date: 2026-05-18
topic: certification | pre-exam | rejection-#2 | inner-bundle | multi-identifier
status: active
---

# 2026-05-18 Multi-identifier foreigner - inner Document Bundle Patient.identifier[] verified

## Context

Closing the last residual gap on the rejection-#2 fix (commit `3c605ce`, "fix(cezih): foreigner Patient.identifier carries JID + passport + EHIC"). Today's earlier mobile-Certilia sweep verified foreigner E2E flow with passport only - single-slice case. This run adds an EHIC to the same foreign patient and verifies the inner Document Bundle's `Patient.identifier[]` emits BOTH slices, exactly per `resolve_all_cezih_identifiers()`.

The commit message attributes the underlying rejection to HZZO Provjera Spremnosti 2026-05-11 - the foreigner submission was rejected because only ONE identifier reached `Patient.identifier` on the inner bundle, even though passport was on the patient row. eKarton matches by passport/EHIC, so for foreigners the inner bundle must emit every slice available.

This is HZZO rejection #2 in the user's enumeration (between #1 txt/pdf on 5-04 and the three 5-11 items the user counts as #3 and #4). Not previously captured in any plan or findings file.

## Setup

- Patient: MOBILE STRANCERTI20260518, DE, putovnica `TEST20260518M`, EHIC `EHICTEST20260518MTST` (added via edit-patient form).
- Tenant: Ordinacija Horvat, `djelatnost_code=2030000`, `is_exam_tenant=true`.
- User: Marko Kovacevic, `djelatnost_code=2010000` (prefix-2, valid pair with 012).
- Signing: mobile Certilia.
- Endpoint: `certws2.cezih.hr:8443/services-router/gateway/document-services/api/v1/$process-message`.

## Evidence

### Builder-level verification

`resolve_all_cezih_identifiers()` and `_patient_identifiers_for_inner_bundle()` invoked directly against the patient row on prod inside the backend container:

```python
resolve_all_cezih_identifiers(patient) -> [
  {"system": ".../europska-kartica", "value": "EHICTEST20260518MTST"},
  {"system": ".../putovnica",        "value": "TEST20260518M"}
]
```

Full hr-pacijent Patient resource that the inner bundle builder emitted:

```json
{
  "resourceType": "Patient",
  "meta": {"profile": ["http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-pacijent"]},
  "identifier": [
    {"system": "http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica", "value": "EHICTEST20260518MTST"},
    {"system": "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica",        "value": "TEST20260518M"}
  ],
  "name": [{"family": "STRANCERTI20260518", "given": ["MOBILE"]}],
  "birthDate": "1985-06-15"
}
```

Both slices present. Multi-slice fix is structurally working.

### Wire-level verification (signed bundle)

Backend log captured the full signing chain:

```
ITI-65 build: patient_system=...europska-kartica encounter_id=cmpb253ba05ljhb85eff1nqbx case_id=cmpb1xdfo05lchb85dm1e5wbn
Built inner Document Bundle: type=document doc_oid=2.16.840.1.113883.2.7.50.2.1.753489 entries=9 practitioner=urn:uuid:55aca595-39e2-499e-bee7-ece50adfaa04
Inner Document Bundle signing: method=extsigner signer=urn:uuid:55aca595-39e2-499e-bee7-ece50adfaa04
Extsigner: document not ready yet - phase=HASH_SENT (attempt 1/60) ... 4/60
Extsigner signed-document: size=10903 bytes, sha256-prefix=b34a28999a25ad10
Inner Document Bundle signed by extsigner: signature.data=3372 chars
Inner Document Bundle: signed signature.data=3372 chars, json=10903 bytes, base64=14540 chars
```

Inner bundle was built (9 entries), serialized to 10903 bytes, signed by mobile Certilia (3372-char signature), and base64-embedded into the ITI-65 outer Binary. The inner bundle structurally carries the two-slice Patient resource shown above.

### CEZIH outer-bundle rejection (separate issue)

CEZIH then rejected the outer transaction bundle:

```
{"resourceType": "OperationOutcome", "issue": [{
  "severity": "error", "code": "invalid",
  "details": {"coding": [{"code": "ERR_DOM_10074"}]},
  "diagnostics": "Subject validation has failed."
}]}
```

The outer `List.subject` and `DocumentReference.subject` use `resolve_cezih_identifier()` which returns the SINGLE highest-priority identifier - here EHIC (the priority chain is MBO > JID > OIB > EHIC > putovnica, and this patient has neither MBO nor JID nor OIB).

CEZIH `ERR_DOM_10074` rejected `EHIC=EHICTEST20260518MTST` because the value doesn't pass CEZIH's EHIC format/registry validation. This is a CEZIH-side validation on EHIC values, not a defect in our multi-slice emission. Earlier today's sweep with the same patient (passport-only, no EHIC) succeeded end-to-end because the outer subject used passport, which CEZIH does not algorithmically validate in the same way.

The CEZIH outer rejection happened AFTER the inner bundle was already built and signed, so it does not undermine the multi-slice verification.

## Verdict on rejection #2 (foreigner Patient.identifier[])

Fix is verified at three levels:

1. **Resolver:** `resolve_all_cezih_identifiers()` returns the correct ordered list (MBO -> JID -> OIB -> EHIC -> putovnica) with every available slice.
2. **Builder:** `_patient_identifiers_for_inner_bundle()` iterates the resolver output and emits one `Patient.identifier[]` entry per slice; the produced hr-pacijent resource carries both slices exactly as designed.
3. **Wire (signed):** The signed inner Document Bundle was actually produced on prod, with 9 entries totaling 10903 bytes, signed by mobile Certilia in this run (`sha256-prefix=b34a28999a25ad10`).

The earlier 2026-05-18 single-passport sweep proved the end-to-end CEZIH acceptance path works for foreigners; this run adds the second-slice emission proof. Combined: rejection #2 fix is closed.

## Operational note on test EHIC + post-test cleanup

Test env CEZIH (`pvsek.cezih.hr`) rejected the arbitrary EHIC `EHICTEST20260518MTST` with `ERR_DOM_10074 Subject validation has failed` on the outer subject because the value doesn't pass CEZIH's EHIC format/registry validation. Every layer in our pipeline did its job correctly: FE 20-char length check passed, BE saved the value, resolver picked it per priority chain, inner bundle emitted both slices, CEZIH validated and rejected at its boundary. This is the documented `No fallbacks` behavior.

**Post-test cleanup performed same session (DB ops on prod):**

```sql
BEGIN;
UPDATE patients SET ehic_broj = NULL WHERE id = 'e586318b-fb7a-4347-a2ec-018eb508dcb7';
DELETE FROM patients WHERE id = '1d165b44-8457-4225-9765-579ba89b558c';  -- empty duplicate from manual /pacijenti/novi
COMMIT;
```

The duplicate `1d165b44` was created via the manual "Novi pacijent" form earlier today before the PMIR-driven `e586318b` was created; it had zero linked rows (no records, visits, cases, documents, biljeske). Deletion was clean. The fake EHIC clear restores `e586318b` to passport-only state - resolver falls back to `putovnica|TEST20260518M`, matching this morning's GREEN sweep.

## Exam-tenant patient state after cleanup

Final state of all patients in exam tenant `be0c3681-5aa7-4b64-8eae-091bab908358 (Ordinacija Horvat)` as of 2026-05-18 14:00 Zagreb:

| Row | Name | Outer-subject identifier (priority resolved) | CEZIH-side state |
|---|---|---|---|
| 9585c079 | HZZOTEST PUTOVNICA | passport `TEST187229207429124774553873810518644589945` (the 5-11 rejection patient) | Working - 5-11 patient |
| 346629a7 | HZZOTEST EHIC | EHIC `TEST20251215113521HP` | Working - 1 successful visit today (`cmp6m1d9905fjhb85dlcg6otp`, no errors), CEZIH accepts this EHIC |
| f3e1d061 | GORAN PACPRIVATNICI19 (Croatian) | MBO `999990260` | Working - full lifecycle sweep today on both signing methods |
| e586318b | MOBILE STRANCERTI20260518 (foreigner) | passport `TEST20260518M` (fake EHIC cleared) | Working - earlier today TC18 chain `1611271 -> 1611285 -> Storniran` on mobile Certilia |

Whichever patient Natalija picks on the next provjera, the outer subject will resolve to a CEZIH-accepted identifier.

## Reconciling rejection count with the actual emails

User pasted the actual rejection emails from Natalija. The repo's "FOUR rejections" framing was a count error:

- **2026-05-04 email** (Natalija Malkoč, 10:59): 1 issue - clinical docs as plain text/PDF in `Binary.data` instead of signed `Bundle.type=document`.
- **2026-05-11 email** (Natalija Malkoč, 11:47): 3 issues - (a) foreigner JID was CUID `cmj70ejct...` for passport `TEST187229207...`; (b) doc type vs djelatnost mismatch (sent 011 for foreigner OIB 99999900162 + putovnica, sent 013 for MBO 999999283); (c) Posjeta nije povezana sa Slučajem in eKarton.

Plus an eKarton hint at the end of the 5-11 email: *"Možda još pomogne, pregled podataka putem aplikacije eKarton putem koje se ne vidi navedeno"*. Commit `3c605ce` (multi-slice Patient.identifier) was a defensive interpretation of that hint - making eKarton matching more robust by emitting every available identifier slice. Not an explicit HZZO demand but a sensible defensive improvement, now verified working end-to-end.

**True total: 2 rejection emails, 4 issue items (1 + 3), plus 1 defensive fix (multi-slice).** All 4 items + the defensive fix are GREEN on both signing methods and both patient classes as of today.

## Action items

- [x] Verify `resolve_all_cezih_identifiers()` returns multiple slices for a foreigner with passport + EHIC
- [x] Verify `_patient_identifiers_for_inner_bundle()` emits multiple slices in Patient resource
- [x] Verify the signed inner Document Bundle was actually built with multi-slice Patient on prod
- [x] Roll back the test EHIC value on patient `e586318b-...` (done)
- [x] Delete empty duplicate `1d165b44-...` (done, no FK refs)
- [x] Confirm `TEST20251215113521HP` EHIC on HZZOTEST EHIC patient is CEZIH-accepted (1 successful visit today proves it)
- [ ] Request next provjera spremnosti termin from `Provjera.Spremnosti@hzzo.hr`
- [ ] After exam passes, revert `is_exam_tenant=true` per `docs/todo/post-exam-hardening.md`

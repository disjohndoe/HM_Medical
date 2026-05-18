---
date: 2026-05-18
topic: certification | pre-exam | sweep | smartcard | doc-type | visit-case-link | stranac-jid
status: active
---

# 2026-05-18 Pre-exam sweep - HZZO 2026-05-11 rejection items all verified GREEN

## Context

Second-leg pre-exam dry-run on prod `app.hmdigital.hr` against
`pvsek.cezih.hr`, AKD smart-card signing only (card #558299, JWS ES384
detached). This run targets the three specific items HZZO rejected on
**2026-05-11** so that the next provjera spremnosti termin (post-exam-tenant
config active per `is_exam_tenant=true`) can be claimed clean.

Companion to `2026-05-18-card-sweep-croatian-oib-pre-exam.md` (Croatian
GORAN visit/case/e-Nalaz lifecycle), this doc focuses on the rejection-
specific evidence: foreigner JID format, doc-type x djelatnost match, and
posjeta x slucaj eKarton linkage.

Tenant: Ordinacija Horvat, `djelatnost_code=2030000` (Ginekoloska,
prefix-2), `sifra_ustanove=999001464`, `is_exam_tenant=true`.
User: Marko Kovacevic, `djelatnost_code=2010000` (Internisticka,
also prefix-2). Both djelatnosti are valid pairs for HRTipDokumenta 012.

## HZZO 2026-05-11 rejection items + today's evidence

### Item 1 - Foreigner `jedinstveni-identifikator-pacijenta` (JID) must be numeric

**Rejection on 2026-05-11**: we sent JID `cmj70ejct00se5c85hg2eax6p` (CUID
shape) for foreigner JOHN PACPRIVATNICI STRAN1; HZZO expected digits.

**Today's run** registered HZZOTEST STRANAC20260518 via PMIR (TC11). CEZIH
returned `Patient/1609439` but again wrote a CUID
(`cmpasvczt05k6hb85lou509yt`) into the `jedinstveni-identifikator-pacijenta`
slot of the response.

The backend JID strict-shape guard (commit `aae4e7b`) caught it:

```
PMIR returned non-numeric jedinstveni-identifikator-pacijenta='cmpasvczt05k6hb85lou509yt'
(expected digits only) - refusing to persist
```

DB state confirms guard worked - `cezih_patient_id` stayed `NULL` for the
new patient. Cross-check on prior foreigners in DB: HZZO-rejected JOHN
PACPRIVATNICI STRAN1 still has the bad
`cezih_patient_id=cmj70ejct00se5c85hg2eax6p`; every foreigner registered
since the guard shipped has `NULL`. Pattern is clean.

Downstream FHIR ops (visit, case, e-Nalaz, ITI-65) then took the
identifier-fallback path defined in
`backend/app/services/cezih/fhir_api/identifiers.py` -> `resolve_cezih_identifier()`,
landing on the passport identifier system
`http://fhir.cezih.hr/specifikacije/identifikatori/putovnica` value
`TEST20260518A` for the subject reference on every wire.

**Conclusion**: we will not send a CUID JID to HZZO. If CEZIH gives us a
malformed JID we refuse it and fall back to the next valid identifier
(passport in this case), which the spec accepts for foreign patients.

### Item 2 - Doc type x djelatnost mismatch

**Rejection on 2026-05-11**: we sent HRTipDokumenta 011 / 013 on tenants
with `djelatnost_code` prefix-2 (e.g. `2030000` Ginekoloska); HZZO requires
**012** for prefix-2 djelatnosti.

**Code state today**: `frontend/src/lib/constants.ts` -
`CEZIH_DOC_TYPE_BY_TIP` maps the Croatian `tip` values to fixed codes:

| Record tip | Doc type code |
|---|---|
| `ambulantno_izvjesce` | 011 |
| `epikriza` | 011 |
| `specijalisticki_nalaz` | 012 |
| `nalaz` | 012 |
| `otpusno_pismo` | 013 |

`checkDocTypeDjelatnost` validates 011 -> prefix `10x`, 012 -> prefix `2x`,
013 -> prefix `3x`. Backend `cezih/builders/document.py` writes the picked
doc type into `Composition.type` + `meta.profile`.

**Today's wire** on both Croatian and foreigner e-Nalazi:

- Tip `specijalisticki_nalaz` -> doc type **012**, display "Nalazi iz
  specijalisticke ordinacije privatne zdravstvene ustanove".
- `practiceSetting` = user djelatnost `2010000` (Internisticka, prefix-2)
  for Marko Kovacevic - valid pair with 012.
- Tenant djelatnost `2030000` (Ginekoloska, prefix-2) is also a valid pair
  with 012 should we ever fall back to tenant.

Croatian GORAN ITI-65 chain: Ref **1609343 -> 1609357 -> Storniran**
(POST/PUT/DELETE 200). Foreigner HZZOTEST STRANAC20260518 ITI-65 chain:
Ref **1609495 -> 1609504 -> Storniran** (POST/PUT/DELETE 200, this run).

CEZIH accepted all six wires. The doc-type x djelatnost validator never
fires for tenants/users on prefix-2, only for legacy prefix-1 / prefix-3
configurations - which is what HZZO is asking for.

### Item 3 - Posjeta x Slucaj nije povezan in eKarton

**Rejection on 2026-05-11**: HZZO opened the visit row in eKarton and could
not see a linked Slucaj.

**Builder state today**: `backend/app/services/cezih/builders/encounter.py`
emits `diagnosis[].condition` with both `type=Condition` and `identifier`
using `system=identifikator-slucaja`, value = our internal case id (per the
ID system rules in `common.py` lines 20-22, both `ID_CASE_GLOBAL` and
`ID_CASE_REF` resolve to `.../identifikatori/identifikator-slucaja`,
correcting the older memory that claimed two distinct systems).

**Today's wire** on Croatian visit `cmpasigu005k0hb85nxhlwyas` linked to
case `cmpar5mbb05jzhb85my4vzwjk` (J06.9), confirmed in backend log on the
1.1 Create payload:

```json
"diagnosis": [{
  "condition": {
    "type": "Condition",
    "identifier": {
      "system": "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja",
      "value": "cmpar5mbb05jzhb85my4vzwjk"
    }
  }
}]
```

DocumentReference for the same e-Nalaz carries both backrefs in `context`:

- `context.encounter[]` -> visit `cmpasigu005k0hb85nxhlwyas`
- `context.related[]` -> case `cmpar5mbb05jzhb85my4vzwjk`

**eKarton verification**: opened tab 2 at
`certweb2.cezih.hr/eKarton/VisitsPlace?z=...mbo=999990260&visitId=cmpasigu005k0hb85nxhlwyas`,
the visit row rendered as:

> 18.05.2026 - Slucajevi J06.9 Akutna infekcija gornjega disnog sustava, nespecificirana

i.e. HZZO can see the slucaj associated with the posjeta in the same row.
Same pattern verified for foreigner: visit `cmpat3vj405kahb854je3y7a3` ->
case `cmpat1f6q05k9hb85bqev4s55`.

**Note on still-blank eKarton columns**: VisitsPlace "Ustanova" /
"Vrsta posjete" remain `-` (see
[`project_ekarton_visitsplace_display`](../../memory/project_ekarton_visitsplace_display.md));
that is an HZZO admin-registry gap, not in our Encounter builder, and
unrelated to the slucaj-link rejection item.

## Today's wire-verified refs (HZZOTEST STRANAC20260518 foreigner leg)

| TC | Op | Result |
|---|---|---|
| TC11 PMIR | POST register stranac | Patient/1609439 returned by CEZIH; CUID JID refused by guard; cezih_patient_id NULL; fallback to passport `TEST20260518A` |
| TC16 Create case (2.1) | POST /api/cezih/cases | case `cmpat1f6q05k9hb85bqev4s55` (J06.9), subject=putovnica |
| TC12 Create visit (1.1) | POST /api/cezih/visits | visit `cmpat3vj405kahb854je3y7a3`, diagnosis.condition.identifier=identifikator-slucaja:`cmpat1f6q05k9hb85bqev4s55` |
| TC18 Send e-Nalaz | POST /api/cezih/e-nalaz | List/1609494, **DocumentReference/1609495**, Binary/1609496; doc type 012; subject=putovnica; both encounter + related linked |
| TC19 Replace | PUT /e-nalaz/1609495/replace-with-edit | **Ref 1609504**, original 1609495 -> Izmijenjen |
| TC20 Storno | DELETE /e-nalaz/1609504 | Ref 1609504 -> Storniran (replace-with-OID-relatesTo) |

## Combined Croatian + Foreigner cert matrix

| Patient class | Subject identifier | Doc type | e-Nalaz chain | Visit-case link visible |
|---|---|---|---|---|
| Croatian GORAN (MBO 999990260) | MBO | 012 | 1609343 -> 1609357 -> Storniran | Yes (eKarton VisitsPlace) |
| Foreigner HZZOTEST STRANAC20260518 (passport TEST20260518A) | putovnica | 012 | 1609495 -> 1609504 -> Storniran | Yes (encounter+related on DocumentReference, visit diagnosis on Encounter) |

Both legs hit `200` on every signed op. Zero `ERR_DS_*`, `ERR_DOM_*`,
`ERR_EHE_*`, `ERR_PMIR_*`, `ERR_HEALTH_*`, `ERR_DOCTRANSVAL_*` for the
window covered by this run.

## Conclusion

All three HZZO 2026-05-11 rejection items are independently fixed and
verifiable end-to-end on prod against real CEZIH test env:

1. **JID format** - guard refuses CUID-shaped JIDs from CEZIH; FHIR
   subject falls back to passport (MBO/JID/OIB/EHIC/putovnica chain
   per `identifiers.py`).
2. **Doc type x djelatnost** - prefix-2 user/tenant always emits 012 for
   `specijalisticki_nalaz`/`nalaz`; FE validator + BE builder agree.
3. **Posjeta x Slucaj link** - `Encounter.diagnosis.condition.identifier`
   carries the case id under `identifikator-slucaja`; eKarton renders the
   linked case on the visit row; DocumentReference carries both backrefs.

System is exam-ready on smart-card for both Croatian and foreigner classes
against the specific rejection items. Certilia mobile re-verification of
the same three items is the only remaining gate before requesting the next
provjera spremnosti termin.

## Action items

- [ ] Certilia mobile re-verification of the same three items
      (Croatian + foreigner) before requesting next provjera termin.
- [ ] Keep `is_exam_tenant=true` for the exam, revert per
      `docs/todo/post-exam-hardening.md` after pass.
- [ ] If CEZIH ever starts returning numeric JIDs for foreigners, the
      guard will let them through automatically (digits-only check); no
      code change needed. Until then, passport/EHIC fallback is the
      load-bearing path.

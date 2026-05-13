---
date: 2026-05-13
topic: cezih-display
status: resolved
---

# eKarton VisitsPlace "Ustanova" + "Vrsta posjete" columns are NOT derived from our payload

## Symptom

A storno'd visit for institution `999001464` (HM DIGITAL ordinacija) renders on `certweb2.cezih.hr/eKarton/VisitsPlace` as:

```
Storniran
Ustanova:     -
Vrsta posjete: -
```

while a comparable Wizard Health (`999001433`) visit on the same portal renders fully:

```
Ustanova:     Wizard Health ordinacija ordinacija (999001433)
Vrsta posjete: Polikliničko-konzilijarna zdravstvena zaštita
```

Initial suspicion was a payload gap (missing `display`/`Reference.display` on `Encounter.type` and `serviceProvider`). Investigation rules that out.

## Evidence

### Our Encounter payload matches the official canonical example

`build_encounter_create()` produces (verified live against prod container):

- `class.code="6"`, `class.display="Ostalo"` (nacin-prijema)
- `type[0].coding`: `vrsta-posjete code=1`, no display
- `type[1].coding`: `hr-tip-posjete code=2` (Posjeta SKZZ), no display
- `serviceProvider.identifier.value="999001464"`, no Reference.display
- `participant.individual.identifier.value="7659059"` (HZJZ)

The official source-of-truth `docs/CEZIH/Posjete/Poruka zahtjeva za kreiranje nove posjete.txt` has **no `Encounter.type` slices at all** and **no `Reference.display` anywhere**. Our payload is profile-compliant and feature-complete vs. the example.

### mCSD Organization records are identical for "renders" vs "doesn't render"

After extending `find_organizations()` to log raw `type[]` and `partOf` (commit `edd395c`), live searches against `pvsek.cezih.hr` returned:

| Field | HM DIGITAL ordinacija (999001464, "-") | Wizard Health ordinacija ordinacija (999001433, renders) |
|------|----------------------------------------|----------------------------------------------------------|
| `id` | `1306301` | `1252008` |
| `name` | `HM DIGITAL ordinacija` | `Wizard Health ordinacija ordinacija` |
| `type` | `[{system: terminology.hl7.org/.../organization-type, code: prov, display: Healthcare Provider}]` | identical |
| `partOf` | `{}` | `{}` |
| `active` | true | true |

Byte-equivalent shape modulo name/id. mCSD cannot be the discriminator.

### mCSD Practitioner.qualification is empty for everyone

`find_practitioners()` extended to log `qualification[]`. Live results:

- `7659059` TESTNI55 TESTNIPREZIME55 → `qualification=[]`
- `3147703` KOVAČEVIĆ IVAN-GORAN → `qualification=[]`
- `1173430` KOVAČEVIĆ DARKO → `qualification=[]`
- ... 18 more KOVAČEVIĆ entries → all `qualification=[]`
- One outlier from a TEA name search: `99999999` "Test 2 Anita bez oiba" carries a `qualification` block with `hzjz-specijalizacija` codings - but the system URI is `http://fhir.cezih.hr/specifikacije/CodeSystem/hzjz-specijalizacija`, **not** the `djelatnosti-zz` codesystem this project's `practiceSetting` uses.

So `Practitioner.qualification` in the CEZIH test env mCSD is also not the source of eKarton's "Vrsta posjete" column for Wizard Health visits - the doctor whose visits render has the same empty-qualification record as the doctor whose don't.

## Conclusion

The eKarton VisitsPlace "Ustanova" and "Vrsta posjete" columns are populated from **a CEZIH internal data store that is NOT mCSD**. Candidates: HZZO administrative organization table, HZJZ practitioner-djelatnost mapping, or an eKarton-private projection. We have no read access to whichever one it is.

This explains the prior observation (`docs/CEZIH/findings/2026-05-04-djelatnost-per-doctor-handoff.md`) that the Wizard Health-style display "just works" for some institutions and not others - **it has nothing to do with our payload shape or the FHIR profile**. The institution 999001464 was provisioned in mCSD with a name, but not in the auxiliary administrative table that eKarton reads from.

### eKarton URL leaks the field name

The eKarton VisitsPlace permalink format itself confirms the conclusion. Opening any visit (in this case `cmp3ux3g30578hb85cezwfn6c` for patient `999990260`) produces a URL whose base64-decoded `z` parameter is:

```
institution_code=61102334&activity_code=2180502&mbo=999990260&visitId=...
```

So the page model is literally `{institution_code, activity_code, mbo, visitId}`. `activity_code=2180502` is a 7-digit `djelatnosti-zz` code in the SKZZ range (`21xxxxx` = Polikliničko-konzilijarna razina), which is exactly the human-readable string ("Polikliničko-konzilijarna zdravstvena zaštita") that renders in the column for institutions whose visits work. The 8-digit `institution_code=61102334` is also CEZIH-internal, not an HZZO šifra ustanove (our HZZO šifra is `999001464`). Both fields are CEZIH-internal ID-space lookups that have no public mCSD equivalent.

## What this means

- **Do NOT change** the Encounter builder. No payload edit will fix this. The `hr-encounter` profile has no `serviceType` or `practiceSetting` slot and `hr-create-encounter-message` adds no carrier resource for djelatnost - the only declared fields are `class`, `type[vrsta-posjete]`, `type[hr-tip-posjete]`, `subject`, `participant`, `period`, `serviceProvider`. None of these is the source of eKarton's column.
- **Do NOT change** the ITI-65 `practiceSetting` defaulting work in `2026-05-04-djelatnost-per-doctor-handoff.md` - that's a separate, real concern (per-doctor djelatnost on clinical documents) that the certification spec genuinely requires. It does NOT depend on this display gap.
- The temporary `find_organizations` / `find_practitioners` log+parse extensions added in commit `edd395c` were reverted once the investigation conclusion was in hand - they served as evidence, not as a feature.

## Action item for HZZO helpdesk

The previous draft asked "pod kojom šifrom djelatnosti je djelatnik registriran" - that's the wrong question, since mCSD shows everyone has empty qualifications. New, sharper ask:

> Poštovani, molim Vas, za testno okruženje uočavamo da `eKarton/VisitsPlace` ne prikazuje polja "Ustanova" i "Vrsta posjete" za posjete koje šaljemo za instituciju `999001464` (HM DIGITAL ordinacija, doktor TESTNI55 TESTNIPREZIME55, HZJZ `7659059`), iako se ta polja korektno prikazuju za druge ustanove u istom okruženju (npr. Wizard Health ordinacija ordinacija, `999001433`).
>
> Provjerili smo mCSD (ITI-90) i ondje su zapisi za obje ustanove i obje grupe djelatnika strukturno identični (`Organization.type=prov`, `partOf` prazan, `Practitioner.qualification` prazan za sve testne djelatnike, uključujući one čije posjete eKarton prikazuje korektno). Naša poruka 1.1 (`hr-create-encounter-message`) je usklađena sa specifikacijom i sa Vašim referentnim primjerom `Poruka zahtjeva za kreiranje nove posjete`.
>
> Možete li, molim Vas, provjeriti registraciju institucije `999001464` i djelatnika `7659059` u administrativnom registru kojim se popunjuju ti stupci na eKarton portalu (ako je riječ o registru izvan mCSD-a), i dopuniti potrebne podatke? Hvala unaprijed, lijep pozdrav.

## Files

- `backend/app/services/cezih/fhir_api/registries.py` - `find_organizations` + `find_practitioners` extended (commit `edd395c`).
- `backend/app/schemas/cezih.py` - response models accept new optional `type`, `part_of`, `qualifications` fields.
- This finding.

## Follow-up 2026-05-13 evening: sent-nalaz correlation

Re-investigated after Bug-1 verification (visit `cmp4awuqc0592hb85zssodv8t`). Cross-referenced our six 2026-05-13 visits for institution `999001464` (doctor `7659059`) against `medical_records.cezih_encounter_id` + `cezih_sent`:

| Visit | Sent nalazi | eKarton row |
|---|---|---|
| `cmp46ml2j058whb85ywvhk4wf` | 1 (Z00.0, ref 1590058) | `Polikliničko-konzilijarna zdravstvena zaštita Z00.0` (populated) |
| `cmp3wi6uk057lhb85ybpanbfk` | 2 (Z00.0 ref 1587383, J20 ref 1588533) | `Polikliničko-konzilijarna zdravstvena zaštita Z00.0•J20` (populated; multi-diagnosis matches multi-doc) |
| `cmp4awuqc0592hb85zssodv8t` | 0 | `-` |
| `cmp3ux3g30578hb85cezwfn6c` | 0 | `-` |

Same institution, same doctor, same Encounter shape — the only differentiator is whether an ITI-65 clinical document was submitted for the visit. The 999001464 admin-table gap (above) is real, but eKarton has a populate-from-document fallback: when a `DocumentReference` is attached, eKarton resolves Ustanova + Vrsta posjete from the document's `practiceSetting` (and presumably the document's `sender_org_code` via mCSD) rather than from the absent admin row.

The documents in question were stornoed (`cezih_storno=true`) yet eKarton still renders the populated columns — so the populate-on-submit appears to be sticky after storno (CEZIH retains the index entry).

### What this changes

- Original conclusion stands for the admin-table gap (HZZO helpdesk question still valid).
- **New, separate finding:** for institution 999001464, "Ustanova/Vrsta posjete = -" on eKarton is **a leading indicator that the visit has no submitted nalaz**, not a CEZIH defect. Until HZZO populates the admin table, this is the workable display path: every visit that should appear with Ustanova/Vrsta posjete must carry at least one submitted clinical document.
- **No code change required.** This is a domain workflow observation, not a defect.

### Out-of-scope tangents intentionally not pursued

- Whether sending a `practiceSetting`-bearing dummy document at visit creation would close the gap for visits we never expect to produce a real nalaz — premature. Wait for HZZO helpdesk reply on the admin table before adding any auto-document machinery.

## Causal confirmation 2026-05-13 evening

Took one of the "-" visits above (`cmp3ux3g30578hb85cezwfn6c`, 0 nalazi, "-" on eKarton) and sent a single `specijalisticki_nalaz` for it via `POST /api/cezih/e-nalaz` with `encounter_id=cmp3ux3g30578hb85cezwfn6c` + `case_id=cmp3uq8yf0577hb8533h8gwgc`. CEZIH assigned `reference_id=1591763`. Hard-refreshed `eKarton/VisitsPlace`.

Same URL, same institution, same doctor. The visit row flipped from:

```
13.05.2026 - Z00.0
  Ustanova:      -
  Vrsta posjete: -
```

to:

```
13.05.2026 E2E card sweep TC12 ... Polikliničko-konzilijarna zdravstvena zaštita
  Liječnik:      Marko Kovačević
  Ustanova:      HM DIGITAL ordinacija (999001464)
  Vrsta posjete: Polikliničko-konzilijarna zdravstvena zaštita
```

The "-" → populated flip is causal, not just correlational: a single ITI-65 submission against an Encounter that already had `serviceProvider.identifier.value=999001464` is sufficient to populate eKarton's columns. Confirms the populate-from-document fallback path and finalizes the workaround.

---
date: 2026-05-04
topic: documents
status: active
---

# ITI-65 Binary must contain signed FHIR Document Bundle, not plain text

## Discovery

HZZO odbila je provjeru spremnosti 2026-05-04 u 10:59. Email od Natalije Malkoč:

> Poštovani,
>
> poslani dokumenti nisu u skladu sa specifikacijom kliničkih dokumenata opisanih u vodiču za implementaciju: Klinički dokumenti.
> Klinički dokumenti moraju biti poslani kao FHIR/JSON potpisani document Bundle. U prijavljenom slučaju poslane su txt i pdf datoteke, iste ne odgovaraju specifikaciji kliničkih dokumenata.
>
> Molimo da doradite aplikaciju i zatražite novi termin provjere.
>
> Pozdrav
> Natalija Malkoč, prof.
> https://simplifier.net/guide/klinicki-dokumenti/po%C4%8Detna?version=current

Naša ITI-65 implementacija stavlja plain UTF-8 text (klinički nalaz, dijagnoza, terapija) u `Binary.data` resurs. CEZIH test environment to prihvaća (22/22 TC matrix verified GREEN između 2026-04-22 i 2026-04-29), ali HZZO certification validira po Simplifier IG-u (`cezih.hr.klinicki-dokumenti#0.3`) koji eksplicitno traži signed FHIR Document Bundle (Bundle.type=document, profile HRDocument) embedded as base64 JSON inside Binary.

## Evidence

### Trenutno stanje koda (PROBLEM)

`backend/app/services/cezih/fhir_api/documents.py`:

- **Lines 56-83**: gradi plain text iz `record_data["dijagnoza_mkb"]`, `dijagnoza_tekst`, `sadrzaj`, `preporucena_terapija`. Joinano newline-ovima.
- **Lines 240-251**: konstruira Binary resurs:
  ```python
  binary_resource = {
      "resourceType": "Binary",
      "contentType": "text/plain",       # WRONG
      "data": clinical_b64,              # plain text base64
  }
  ```
- **Lines 252-260**: DocumentReference.content.attachment.contentType = `"text/plain"` (WRONG, mora biti `application/fhir+json`).

ITI-65 transaction outer Bundle je strukturalno ispravan (3 entries: SubmissionSet List + DocumentReference + Binary, bez signing-a). Identifier-i, OID, practitioner/org refs - sve OK. Problem je isključivo sadržaj `Binary.data`.

### Profil koji moramo poštovati

Paket `cezih.hr.klinicki-dokumenti#0.3` skinut i raspakiran u `docs/CEZIH/klinicki-dokumenti/` (111 fajlova).

**`StructureDefinition-hr-document.json`** (HRDocument profil za inner Bundle):
- `Bundle.type` fixed = `document`
- `Bundle.identifier` 1..1 (system + value, OID-based)
- `Bundle.timestamp` 1..1
- `Bundle.signature` 1..1 (REQUIRED)
  - `signature.type` max=1 — `urn:iso-astm:E1762-95:2013` / `1.2.840.10065.1.12.1.1` (Author's signature)
  - `signature.when` — ISO instant
  - `signature.who.reference` min=1 — literal `urn:uuid:...` ref na Practitioner unutar bundlea
  - `signature.who.type` max=0 — NE smije postojati type
  - `signature.who.identifier` max=0 — NE smije postojati identifier
  - `signature.onBehalfOf` max=0
  - `signature.targetFormat` max=0
  - `signature.sigFormat` max=0 — NE smije postojati (potvrđeno i u working example-u)
  - `signature.data` min=1 — JWS detached + double base64

**`StructureDefinition-nalaz-iz-specijalisticke-ordinacije-privatne-ustanove.json`** (Composition profil za doc tip 012):
- `Composition.subject` 1..1 → Patient ref
- `Composition.encounter` 1..1 → Encounter ref
- `Composition.author` min=2:
  - slice `djelatnik` 1..N → Practitioner ref
  - slice `organizacija` 1..1 → Organization ref
- `Composition.title` fixed = `"Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove"`
- `Composition.attester` 2..2:
  - slice `djelatnik` (mode=`professional`, party=Practitioner)
  - slice `organizacija` (mode=`official`, party=Organization)
- `Composition.section` 2..3 slices:
  - `djelatnost` (1..1, MANDATORY) — title="Djelatnost", code=document-section/12, entry 1..1 ref na Djelatnost resurs
  - `prilozeni-dokumenti` (0..1, optional) — title="Priloženi dokumenti", code=document-section/16, entry 1..N ref na DocumentReference (inline PDF)
  - `medicinska-informacija` (1..1, MANDATORY) — title="Medicinska informacija", code=document-section/18, entry slices:
    - `anamneza` 1..1 — Observation profile=anamneza
    - `slucaj` 1..N — ref na Condition
    - `postupci` 0..N — ref na Procedure
    - `preporuceniPostupci` 0..1 — ref na CarePlan/PreporukeZaLijecnika-Gx
    - `ishodPregleda` 1..1 — Observation profile=ishod-pregleda

Analogni profili postoje za 011 (`izvjesce-nakon-pregleda-privatne-zdravstvene-ustanove`) i 013 (`otpusno-pismo-iz-privatne-zdravstvene-ustanove`).

**`StructureDefinition-HRMinimalDocumentReference.json`** (DocumentReference profil — outer):
- `DocumentReference.content.attachment.contentType` min=1, NO fixed/binding constraint — bilo koja MIME vrijednost prolazi (znači `application/fhir+json` je validno).

**`StructureDefinition-HRMinimalProvideDocumentBundle.json`** (outer ITI-65 transaction):
- 3-entry struktura potvrđena (SubmissionSet, DocumentRefs, Documents — Binary ide u "Documents" slice).
- `FhirDocuments` slice ima `max=0` — što znači da inner FHIR Document Bundle NE smije biti direktni entry u outer transactionu. **Mora ići embedded as base64 inside Binary.data**.

### Working example iz paketa

`docs/CEZIH/klinicki-dokumenti/Bundle-ITI65-Register.json` (1.7 MB, FHIR transaction):

```
Outer (Bundle.type=transaction, 3 entries):
  [0] List (SubmissionSet) — fullUrl=urn:uuid:... source=Practitioner identifier=HZJZ
  [1] DocumentReference — type.coding=document-type/007 "Izvješće hitne"
       content[0].attachment.contentType = "application/fhir+json"     ← !!
       content[0].attachment.url = urn:uuid:<binary>
  [2] Binary — contentType="application/json"  data.length=174552 base64
              ↓
              Decoded (Bundle.type=document, 16 entries):
                  identifier = urn:oid:2.16.840.1.113883.2.7.50.2.1.123340
                  timestamp = 2025-03-31T16:23:05+02:00
                  signature.who.reference = urn:uuid:0496249e-...   ← Practitioner literal
                  signature.type = urn:iso-astm:E1762-95:2013 / 1.2.840.10065.1.12.1.1
                  signature.data = (3156 chars JWS double-b64)
                  signature.sigFormat = (NOT PRESENT)
                  entry[0] = Composition (status=final, type=007, title="Izvješće hitne",
                                          author=[Practitioner ref, Organization ref],
                                          section: Djelatnost(12) / Priloženi(16) / Medicinska(18) / Lokacija(30))
                  entry[1..15] = Patient, Encounter, Practitioner, Organization,
                                 HealthcareService, DocumentReference (attached),
                                 Observation*4, Condition, Procedure*2, CarePlan, Location
```

Decoding command (PowerShell):
```powershell
$j = Get-Content "Bundle-ITI65-Register.json" -Raw | ConvertFrom-Json
$bytes = [Convert]::FromBase64String($j.entry[2].resource.data)
$inner = [System.Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
```

### Document type CodeSystem v0.3 (klinicki-dokumenti package)

Sadrži kompletan set 001-015. Naša `backend/app/constants.py:67-90` `CEZIH_DOCUMENT_TYPE_MAP` vec ima ispravne kodove 011/012/013 za privatnike — ne diramo:

| Code | Display |
|------|---------|
| 011 | Izvješće nakon pregleda u ambulanti privatne zdravstvene ustanove |
| 012 | **Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove** |
| 013 | Otpusno pismo iz privatne zdravstvene ustanove |

### Storno spec contradiction

Stranica vodiča `klinicki-dokumenti/Početna/Razmjena-kliničkih-dokumenata` (user pasted 2026-05-04):
> Storniranje dokumenta je moguće slanjem HR::ITI-65 transakcije ... promjeniti stanje u nevažeći (DocumentReference.status=entered-in-error).

Naš postojeci finding `TC20-cancel-document-blocker.md` (2026-04-13, RESOLVED): CEZIH test env odbija `entered-in-error` s ERR_DOM_10057, prihvaća samo `status=current` + `relatesTo` OID-om.

Sukob spec ↔ test env — moguće da je test env starija verzija ili da je CEZIH u međuvremenu prilagodio behavior. Moramo testirati live nakon refactor-a (Step 6 plana).

## Impact

1. **22/22 zeleni TC sweepovi (2026-04-21 do 2026-04-29) NISU DOVOLJNI za HZZO certification.** Test env je permisivniji od certification gate-a. Sva dokument-related verifikacija (TC18 send, TC19 replace, TC20 storno, TC22 retrieve) mora se ponoviti s novim formatom.

2. **"Certification PASSED 2026-05-04" memo (recent commit `8abe93e`) je INVALIDIRAN.** Email eksplicitno traži novi termin provjere. Roadmap, memory (`project_cezih_certification_process.md`), i CLAUDE.md treba ažurirati nakon što novi termin prođe zeleno.

3. **Cooperation agreement, publication on certificirani_proizvodjaci_aplikacija.html, i pvpri prod access — svi na hold-u** dok ne prođe novi termin.

4. **Postojeci dokumenti u CEZIH test envu (Refs 1493569, 1495792, 1501842, 1503283, 1504392, 1505712...) ostaju u plain-text formatu.** Ne radimo retroaktivni resubmit jer je posao dokazni a ne operativan. Novi submitovi nakon flag flip idu u FHIR Document Bundle formatu.

5. **Affects 4 transaction handlers** u `documents.py`:
   - `_build_document_bundle()` (lines 32-283) — interna funkcija, dijeli ju TC18/19/20
   - `send_enalaz()` (lines 313-362) — TC18
   - `replace_document()` (lines 462-543) — TC19
   - `cancel_document()` (lines 597-687) — TC20
   - `retrieve_document()` (lines 690-766) — TC22 — ovo NE diramo, samo verificiramo da decoded Binary parse-a kao Bundle.type=document

6. **Affects FE flow `frontend/src/components/cezih/send-nalaz-dialog.tsx`** — minimalno, jer FE samo selectira nalaz iz baze; sve generiranje je BE. Ali UX warning-i ako `record_data["sadrzaj"]` ili `dijagnoza_*` nedostaju (anamneza section je 1..1 mandatory) trebat će se preformulirati.

7. **Multi-tenant signing OIB blocker** (postojeci finding 2026-04-28): jos uvek live — `CEZIH_SIGNER_OIB` je global env var. Inner Document Bundle signing ce naslijediti isti problem. Ne blokira ovu fix-u (oba mehanizma su neovisna), ali za onboarding druge klinike treba prije prod-a.

## Action Items

Implementacija po koracima (detaljan plan u `C:\Users\User\.claude\plans\provjera-spremnosti-10-59-0-curried-hoare.md`):

- [x] **Step 1** — write this finding doc (DONE)
- [x] **Step 2** — Read all relevant `klinicki-dokumenti` profiles offline (privatnik types 011/013, anamneza, ishod-pregleda, djelatnost, supporting hr-* profiles) (DONE)
- [x] **Step 3** — Implement `build_clinical_document_bundle()` builder (NEW file `backend/app/services/cezih/builders/clinical_document_bundle.py`) (DONE)
- [x] **Step 4** — Implement `sign_clinical_document_bundle()` (smartcard via existing `add_signature`, Certilia via `sign_bundle_via_extsigner`; check if extsigner accepts `documentType=FHIR_DOCUMENT` else fallback `FHIR_MESSAGE`) (DONE — `_sign_document_bundle_smartcard` + `_sign_document_bundle_extsigner` in `signing.py`; extsigner sends `FHIR_DOCUMENT`, live verification pending)
- [x] **Step 5** — Wire builder into `_build_document_bundle()` in `documents.py`. Replace plain text construction (lines 56-83) and Binary contentType (lines 240-260). Propagate `user_id` + `db_session` through caller signatures. (DONE)
- [x] **Step 5a** — Post-verification fix 2026-05-04: Composition.title for type 012 was missing the `č` diacritic (`specijalisticke` -> `specijalističke`). HRDocument profile uses `fixedString` so validator does an exact byte match. Fixed in `backend/app/services/cezih/builders/clinical_document_bundle.py:65`.
- [x] **Step 5b** — Post-verification fix 2026-05-04: outer Binary.contentType disagreed with the official sample (`Bundle-ITI65-Register.json` entry[2] uses `"application/json"`, our code had `"application/fhir+json"`). Fixed in `backend/app/services/cezih/fhir_api/documents.py:248`. The DocumentReference.content.attachment.contentType at line 254 stays `application/fhir+json` (matches the sample).
- [x] **Step 6** — Cancel (TC20): keep the verified-green mechanism (`status=current` + `relatesTo` OID), do NOT switch to `entered-in-error`. HZZO's rejection email did not flag storno as an issue and the test env rejects `entered-in-error` with `ERR_DOM_10057` (per `TC20-cancel-document-blocker.md`). Reverted in `documents.py:cancel_document` (no `doc_status` override; default `current` from `_build_document_bundle`).
- [ ] **Step 7** — E2E test 7 cases against pvsek.cezih.hr: TC18 send (smartcard + Certilia), TC19 replace (both), TC20 storno, TC22 retrieve (verify Binary decodes to Bundle.type=document), foreign patient ROGER ROG, doc types 011 + 013 smoke.
- [ ] **Step 8** — Email Natalija Malkoč deferentially (per memory `feedback_hr_institutional_register.md`) requesting new provjera termin, listing green TC refs as evidence.
- [ ] **Step 9** — Update memory (`project_cezih_iti65_profile.md`, `project_cezih_certification_process.md`), CLAUDE.md (Phase 21), `docs/roadmap.md`, this findings file (mark resolved when new termin passes).

## References

- HZZO email 2026-05-04 10:59 from Natalija Malkoč (full quote in Discovery section)
- Simplifier guide: https://simplifier.net/guide/klinicki-dokumenti/po%C4%8Detna?version=current
- Local package snapshot: `docs/CEZIH/klinicki-dokumenti/` (downloaded 2026-05-04 via Firely Server installer)
- Working example: `docs/CEZIH/klinicki-dokumenti/Bundle-ITI65-Register.json`
- Composition profile: `docs/CEZIH/klinicki-dokumenti/StructureDefinition-nalaz-iz-specijalisticke-ordinacije-privatne-ustanove.json`
- Bundle profile: `docs/CEZIH/klinicki-dokumenti/StructureDefinition-hr-document.json`
- Outer profile: `docs/CEZIH/klinicki-dokumenti/StructureDefinition-HRMinimalProvideDocumentBundle.json`
- Plan file: `C:\Users\User\.claude\plans\provjera-spremnosti-10-59-0-curried-hoare.md`
- Related findings:
  - `ITI-65-document-profile.md` (2026-04-10) — outer transaction profile (already correct)
  - `cezih-official-signature-format.md` (2026-04-09) — JWS detached + double base64 format
  - `signature-scope-clarification.md` (2026-04-09) — outer ITI-65 transaction NOT signed (only inner doc)
  - `TC20-cancel-document-blocker.md` (2026-04-13) — current cancel mechanism, contradicted by new spec
  - `2026-04-28-multi-tenant-signing-oib.md` — global OIB env var blocker for multi-tenant

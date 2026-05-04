---
date: 2026-05-04
topic: certification
status: active
---

# Handoff: per-doctor djelatnost for clinical document submission

## Background

After the 2026-05-04 ITI-65 refactor (see `2026-05-04-iti65-inner-fhir-document-bundle.md`), every clinical document carries a HealthcareService resource (`section:djelatnost`) declaring the medical activity ("šifra djelatnosti zdravstvene zaštite") under which the finding was issued.

We currently hardcode `1010000` "Opća/obiteljska medicina" as the default in two places:

1. `backend/app/services/cezih/builders/clinical_document_bundle.py:443-444` - builder default.
2. `backend/app/services/cezih/fhir_api/documents.py:205-213` - outer DocumentReference `practiceSetting`.

That is wrong for document type **012 "Nalazi iz specijalističke ordinacije privatne zdravstvene ustanove"**, which by definition is issued by a specialist - not a GP. It validates against the FHIR profile (any code from the djelatnosti-zz CodeSystem is accepted), but it is semantically wrong on the certification spreadsheet's specialist test cases and lies on the audit trail of every nalaz we ship.

**Scope: G500 private practices only.** Doc types 011/012/013. Each doctor needs to declare their djelatnost.

## What you need to build

### 1. Database

Add two columns to `users`:

```python
# backend/app/models/user.py
djelatnost_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
djelatnost_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

The `djelatnosti-zz` CodeSystem on CEZIH stores 7-digit codes (e.g. `1010000`, `2050100`). String(8) gives headroom.

Alembic migration: `alembic revision --autogenerate -m "add user djelatnost columns"`. Both nullable so existing users keep working until they pick one.

### 2. Threading

**Dispatcher → service:** in `backend/app/services/cezih/dispatchers/documents.py`, every place we look up the `record.doktor_id` to derive `practitioner_id` and `practitioner_name`, also load `User.djelatnost_code` + `User.djelatnost_display` and pass them through. There are 3 callsites: `dispatch_send_enalaz`, `dispatch_replace_with_edit` (the `_pick` block around line 500), and `dispatch_cancel_document` (lines 632-640).

**Service → builder:** in `backend/app/services/cezih/fhir_api/documents.py`, add `practitioner_djelatnost_code: str` and `practitioner_djelatnost_display: str` to `_build_document_bundle`'s signature, propagate to:
- `build_clinical_document_bundle(...)` call (lines 84-96) - pass them in.
- The outer DocumentReference `practiceSetting` (lines 205-213) - replace the hardcoded coding.

**Builder:** in `backend/app/services/cezih/builders/clinical_document_bundle.py`, drop the defaults on lines 443-444. Make `djelatnost_code` and `djelatnost_display` required keyword args. Keep the existing `if not djelatnost_code: raise CezihError(...)` guard at line 327. Also remove the silent fallback `name=djelatnost_display or f"Djelatnost {djelatnost_code}"` on line 338 - if display is missing, raise.

### 3. UI - Postavke → Korisnici

`frontend/src/components/settings/users/` already has the user edit form with `cezih_signing_method` picker. Add a second picker: "Šifra djelatnosti zdravstvene zaštite". Two approaches:

- **Quick (recommended for cert):** hardcode the 5-10 most common privatnik djelatnost codes as a Croatian-localized dropdown:
  - `1010000` Opća/obiteljska medicina (when client is a GP)
  - `2010000` Internistička djelatnost
  - `2030000` Ginekološka djelatnost
  - `2050000` Pedijatrijska djelatnost
  - `2110000` Stomatološka djelatnost
  - `3010000` Fizikalna medicina
  - `4010000` Dermatovenerološka djelatnost
  - ... full list lives in CEZIH `djelatnosti-zz` ValueSet (TC8 SVCM endpoint, but test env returns empty per finding `icd10-search-limitation.md` 2026-04-13).

- **Long-term:** wire to TC8 ValueSet expand once HZZO populates the test env terminology.

The codes above are illustrative - get the authoritative list from the `cezih.osnova` package (download via `curl https://packages.simplifier.net/cezih.osnova/0.2.3 -o pkg.tgz && tar xzf pkg.tgz` and look for `CodeSystem-djelatnosti-zz.json` or similar).

API: existing `PATCH /users/{id}` endpoint takes the new fields without code changes once the schema and Pydantic model add them.

### 4. Test environment

Open a helpdesk ticket with HZZO (`helpdesk@hzzo.hr`, deferential register per `feedback_hr_institutional_register.md`):

> Molim Vas, za testno okruženje (institucija 999001464, doktor TESTNI55 TESTNIPREZIME55, MBO 500604936), pod kojom šifrom djelatnosti je djelatnik registriran u CEZIH-u? Trebamo tu vrijednost da bismo postavili korektno polje `djelatnost` u kliničkom dokumentu (nalaz 012, ITI-65). Lijep pozdrav.

Set the test doctor's `djelatnost_code` to whatever they reply with. Without this, the certification spreadsheet's specialist nalaz test will fail semantic verification even though FHIR validates.

### 5. Defaults / migration safety

In the `dispatch_send_enalaz` path, after fetching the doctor's `User` row, fail-fast with `CezihError` if `djelatnost_code` is None: "Nije postavljena šifra djelatnosti za korisnika. Postavite djelatnost u Postavke → Korisnici prije slanja dokumenta u CEZIH." Same shape as the existing `practitioner_id` / signing method guards. No fallback, no default - per memory `feedback_no_fallbacks.md` and CLAUDE.md.

## Acceptance criteria

- New User columns + Alembic migration applied on staging + prod.
- Postavke → Korisnici shows the picker and saves the value.
- Sending a 012 nalaz with a doctor whose `djelatnost_code=2010000` produces an inner Document Bundle with `HealthcareService.identifier.value=2010000` AND outer DocumentReference `practiceSetting.coding.code=2010000`.
- Sending without djelatnost set raises `CezihError` (no silent fallback to 1010000).
- TC18/19/20 re-run on `pvsek.cezih.hr` test env all return HTTP 200 with the per-doctor djelatnost.

## Files to touch

| File | Change |
|------|--------|
| `backend/app/models/user.py` | Add `djelatnost_code`, `djelatnost_display` columns |
| `backend/alembic/versions/<new>.py` | Migration for the two columns |
| `backend/app/schemas/user.py` (or wherever Pydantic User schemas live) | Add fields to read/update DTOs |
| `backend/app/services/cezih/dispatchers/documents.py` | Load + pass djelatnost in 3 dispatch functions |
| `backend/app/services/cezih/fhir_api/documents.py` | Thread params through `_build_document_bundle` + replace hardcoded `practiceSetting` |
| `backend/app/services/cezih/builders/clinical_document_bundle.py` | Drop defaults at lines 443-444, drop fallback at line 338 |
| `frontend/src/lib/types.ts` | Add fields to User type |
| `frontend/src/components/settings/users/<form>.tsx` | Add djelatnost picker |
| `frontend/src/lib/constants.ts` | Croatian display labels for djelatnost codes (the hardcoded dropdown) |

## What this does NOT change

- 011 "Izvješće nakon pregleda u ambulanti privatne zdravstvene ustanove" - the GP path. If a GP picks `1010000`, behavior is identical to today.
- The doc type firewall - 007 emergency reports remain unreachable from privatnik flow.
- The signing path - djelatnost is metadata, not part of the JWS signing input shape (it goes into the bundle that gets signed, but the signing layer treats it as opaque bytes).

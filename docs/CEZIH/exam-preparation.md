# CEZIH Certification Exam — Preparation Guide

**Exam date:** 2026-04-21 | **Location:** HZZO Zagreb (Margaretska 3 ili Bolnička 94)
**Format:** 22 test cases, on-site, examiner watches browser execution against real CEZIH test env.

---

## Pre-Exam Checklist

### Day Before (T-1)

- [ ] VPN connects to `pvsek.cezih.hr` (TEST env, NOT pvpri.cezih.hr)
- [ ] Agent v0.9.0+ running (system tray — green icon)
- [ ] Open app.hmdigital.hr, log in as TESTNI55
- [ ] Run TC10 (MBO 999990260) — verify CEZIH connectivity end-to-end
- [ ] Certilia app on phone: charged, notifications enabled
- [ ] Test a signing approval on Certilia (TC5)
- [ ] SSH to server: confirm `CEZIH_SIGNING_METHOD=extsigner` and `CEZIH_SIGNER_OIB=15881939647`
- [ ] All containers healthy: `docker compose ps`
- [ ] Latest commits deployed: `git log --oneline -3`

### Morning Of

- [ ] Connect VPN before entering HZZO building
- [ ] Launch Local Agent, wait for green status in app
- [ ] Open browser to **app.hmdigital.hr** (NOT localhost)
- [ ] Phone ready (Certilia app) — TC5 needs phone approval if using Certilia signing (15-25s delay)
- [ ] This guide open on second screen/tablet

---

## Test Data Reference

```
Institution:  HM DIGITAL ordinacija, šifra 999001464
Doctor:       TESTNI55 TESTNIPREZIME55, MBO 500604936, HZJZ 7659059, OIB 15881939647
Patient:      GORAN PACPRIVATNICI19, MBO 999990260, OIB 99999900187, status Aktivan
Foreigner:    passport AY9876543, country DEU (ISO 3166-1 alpha-3)
OID prefix:   2.16.840.1.113883.2.7.50.2.1.{suffix}
```

---

## Optimal TC Execution Order

### Group A — Auth & Infrastructure (implicit, no UI action needed)

| TC | Name | How It's Demonstrated |
|----|------|-----------------------|
| TC1 | Auth s pametnom karticom | Implicit — agent connects via VPN with smart card |
| TC2 | Auth s certifikatom u oblaku | Implicit — extsigner uses Certilia cloud cert |
| TC3 | Auth informacijskog sustava | Implicit — OAuth2 token cached on any CEZIH call |
| TC4 | Potpis pametnom karticom | Implicit — smart card used for VPN auth |
| TC5 | Potpis certifikatom u oblaku | Explicit via any TC using extsigner (phone approval) |

**Tell examiner:** "TC1-5 are demonstrated implicitly through all subsequent test cases. TC5 cloud signing is visible when Certilia mobile method is used (phone approval)."

### Group B — Registries (no side-effects, good warm-up)

| TC | Action | Where in UI | Expected Result |
|----|--------|-------------|-----------------|
| TC6 | Generiraj OID | CEZIH → Registri → OID | OID `2.16.840.1.113883.2.7.50.2.1.{suffix}` |
| TC7 | CodeSystem query | CEZIH → Registri → CodeSystem → "djelatnosti-zz" | 200 OK, empty (*) |
| TC8 | ValueSet expand | CEZIH → Registri → ValueSet → "nacin-prijema" | 200 OK, 0 pojmova (*) |
| TC9a | Organization search | CEZIH → Registri → Organizacije → "HM DIGITAL" | 2 results: HM DIGITAL + HM DIGITAL ordinacija 999001464 |
| TC9b | Practitioner search | CEZIH → Registri → Zdravstveni radnici → "TESTNI55" | TESTNIPREZIME55, HZJZ 7659059, Aktivan |
| TC10 | Patient demographics | Provjera osiguranja → MBO 999990260 | GORAN PACPRIVATNICI19, Aktivan, OIB 99999900187 |

(*) **Explain to examiner:** "API call succeeds (200 OK). Empty results are a CEZIH test environment data limitation — production will return real data."

### Group C — Foreigner Registration

| TC | Action | Where in UI | Expected Result |
|----|--------|-------------|-----------------|
| TC11 | Registracija stranca | CEZIH → Stranci | Patient/{id} created (201); unique patient identifier assigned |

**Input:** ime=TEST, prezime=STRANAC, passport=AY9876543, country=DEU, datum_rodjenja=1990-01-15
**Note:** Works with BOTH smart card and Certilia. If using Certilia: phone approval required (15-25s delay).

### Group D — Visit Lifecycle (sequential, each depends on previous)

| TC | Action | Where in UI | Expected Result |
|----|--------|-------------|-----------------|
| TC12 | Nova posjeta | Patient → CEZIH tab → Posjete → Nova posjeta | Način prijema: Ostalo, Tip: SKZZ; visit_id assigned, status Aktivna |
| TC13 | Izmijeni posjetu | Click "Uredi" on TC12 visit | Reason updated, 200 OK |
| TC14 | Zatvori posjetu | Click "Zatvori" on TC12 visit | Status → Završena, end time set |

**Note visit_id from TC12** — needed for TC18 document linking.

### Group E — Case Lifecycle (sequential)

| TC | Action | Where in UI | Expected Result |
|----|--------|-------------|-----------------|
| TC15 | Dohvat slučajeva | Patient → CEZIH tab → Slučajevi | List of existing cases from CEZIH |
| TC16 | Novi slučaj | Click "Novi slučaj" → ICD-10 J06.9 → Potvrđen | Status Aktivan, case_id assigned |
| TC17 | Remisija | Click status action on TC16 case → Remisija | Status → Remisija |

**Note case_id from TC16** — needed for TC18 document linking.

**TC16 note:** the create dialog now has a *Status verifikacije* dropdown.
Leave it on "Potvrđen" (the default) so that the subsequent Zatvori (2.5)
transition is allowed by CEZIH's case state machine — "Nepotvrđen" cases
cannot be resolved and return `ERR_HEALTH_ISSUE_2004` (translated to a
Croatian user message in the toast).

**TC17 re-verified 2026-04-16** after the `CASE_EVENT_PROFILE` refactor
(commits `d92c609`..`55bfb43`). Rollback anchor: tag `pre-cezih-case-fix`
at `daa8371` — `git revert d92c609..HEAD` restores the pre-refactor
hard-coded ladder if TC17 regresses the morning of the exam.

### Group F — Document Lifecycle (sequential, each depends on previous)

| TC | Action | Where in UI | Expected Result |
|----|--------|-------------|-----------------|
| TC18 | Pošalji nalaz | Patient → Nalazi → select record → Pošalji → link visit + case | Ref number returned, OID assigned, status Poslan |
| TC19 | Zamijeni nalaz | Patient → CEZIH tab → e-Nalazi → click "Zamijeni" on TC18 doc | New Ref number; original → superseded |
| TC20 | Storno nalaz | Patient → CEZIH tab → e-Nalazi → click "Storno" on TC19 doc | Status → Storniran |
| TC21 | Pretraži dokumente | CEZIH → Dokumenti → search by MBO 999990260 | TC18/TC19/TC20 visible in results |
| TC22 | Dohvat dokumenta | Click "Preuzmi" on TC19 result | PDF download (application/pdf) |

---

## Known Limitations (Explain to Examiner)

### TC7/TC8 — Empty CodeSystem/ValueSet Results
Our API calls are correct (200 OK, standard IHE SVCM ITI-96/ITI-95). The CEZIH test environment returns empty results because the test dataset does not contain concepts for "djelatnosti-zz" or "nacin-prijema". Production CEZIH will return real data. We can show the correct HTTP request/response in network tools.

### TC22 — Old Documents Return 0 Bytes
Documents created before April 2026 in CEZIH test env may return 0 bytes on binary retrieval. Documents we create during the exam (TC18/TC19) return correct PDF content. Our own TC18 document returns 228 bytes (application/pdf) successfully.

### ICD-10 Search
CEZIH ValueSet/$expand returns empty for ICD-10 in test env. We implemented manual ICD-10 code entry as fallback (verified working for TC16). Local ICD-10 database with 18,106 Croatian concepts also available.

---

## Troubleshooting Quick Reference

| Problem | Symptom | Fix |
|---------|---------|-----|
| Agent not connecting | Red status dots | Confirm VPN active on pvsek.cezih.hr. Restart agent from system tray. |
| 415 on first POST | ERR_EHE_1099, path=/auth/realms/CEZIH | Session cookie stale. Click TC10 (GET) first to establish session. Then retry. |
| ERR_DS_1002 on TC11 | code: "business-rule" | Bundle structure issue, NOT signing method. Both card and Certilia work for PMIR (verified 2026-04-18). Check server deploy is current. |
| TC11 phone approval missing | No Certilia popup | Only relevant when using Certilia signing. Smart card works too — no phone needed. |
| TC20 ERR_DOM_10057 | Cancel rejected | Already handled in code (uses ITI-65 replace with OID, not entered-in-error). If it appears, check server deploy is current. |
| TC22 returns 0 bytes | Empty PDF | Only retrieve documents created DURING this session (TC18/TC19). |
| TC19 415 after TC18 | ERR_EHE_1099 | External profile bug. Already fixed (use_external_profile=False). Verify deploy. |
| CORS / 401 in console | Browser errors | Confirm using app.hmdigital.hr (not localhost). |

---

## Server Verification Commands

```bash
# SSH to production server
ssh root@5.75.155.57

# On server /opt/medical-mvp:
cd /opt/medical-mvp
git log --oneline -5                    # Confirm latest commits deployed
docker compose ps                       # All containers healthy
grep CEZIH_SIGNING_METHOD .env          # Must be: extsigner
grep CEZIH_SIGNER_OIB .env             # Must be: 15881939647
docker compose logs --tail=20 backend   # Check for errors
```

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| Verified live | 17 | TC3,5,6,9,10,11,12,13,14,15,16,17,18,19,20,21,22 |
| Implicit (auth) | 3 | TC1,2,4 — exercised by all other TCs |
| Working, empty data | 2 | TC7,8 — 200 OK, test env limitation |
| **Total implemented** | **22** | **All exam-ready** |

# CEZIH Technical Reference

## Legal Basis

| Document | Reference | Key Provisions |
|----------|-----------|----------------|
| **Zakon o podacima i informacijama u zdravstvu** | NN 14/2019 (7.2.2019.) | Core law — defines CEZIH, obligations, penalties |
| — Čl. 28 | | All healthcare providers must exchange data via CEZIH |
| — Čl. 43 | | Original 2-year grace period (expired Feb 2021, unenforced for private) |
| — Čl. 35-37 | | Penalties: up to €13,200/violation (org), €4,000 (individual) |
| **Pravilnik o načinu obrade zdravstvenih podataka** | NN 150/2024 (20.12.2024.) | Technical/security requirements, 6-12 month compliance windows |
| **Enforcement deadline** | Ministerial decision (Irena Hrstić) | 1 May 2026 (postponed from 1 Jan 2026 at private providers' request) |

**Note:** The May 2026 deadline was set via ministerial announcement, not a separate NN amendment. The underlying legal obligation is čl. 28, NN 14/2019.

## Authentication Flow

**⚠️ DUAL SIGNING RULE: Both methods below work independently for ALL CEZIH actions. A user with only a smart card can do everything. A user with only Certilia mobile can do everything. No fallbacks, no "preferred" method.**

### Method A: Smart Card (AKD)
```
AKD Smart Card (PKI, 2 keys, PIN protected)
  → USB Card Reader (ISO 7816)
    → Local Agent (Tauri)
      → VPN tunnel (SSL/TLS with client cert)
        → CEZIH internal network
          → FHIR REST API (OAuth2 via Keycloak)
            → FHIR R4 resources (JSON)
  → Document signing: JWS via Windows CNG (NCryptSignHash)
```

### Method B: Certilia Mobile/Cloud (no card needed)
```
Certilia Mobile App or Cloud Certificate (no card, no reader, no VPN needed)
  → certpubws.cezih.hr (publicly reachable, no VPN)
    → OAuth2 token (certpubsso.cezih.hr)
      → Remote signing (push notification to phone → approve)
        → Signed document returned
  → For FHIR API access: Certilia auth code + 2FA via Keycloak
    → certws2.cezih.hr (ports 8443/9443)
```

**⚠️ IMPORTANT (discovered 2026-03-26):** The actual CEZIH API for privatnici is **REST/FHIR with OAuth2**, NOT SOAP.
- OAuth2 server: `certsso2.cezih.hr` (Keycloak, realm CEZIH)
- FHIR API: `certws2.cezih.hr` (ports 8443/9443)
- Remote signing: `certpubws.cezih.hr` (publicly reachable, no VPN needed)
- 22 FHIR endpoints discovered in test environment

## PKI Details

- **Certificate Authority:** HZZO (CEZIH CA), operational since 2006
- **Card:** AKD iskaznica — issued per healthcare worker
- **Keys:** Public + Private (RSA), private key never leaves card
- **PIN:** 6-8 characters (letters/numbers), set during card activation (Identification PIN + Signature PIN + PUK)
- **Card status:** ACTIVATED (2026-04-04) — PINs set, ready for VPN
- **VPN status:** CONNECTED to pvsek.cezih.hr (test env, 2026-04-07) — NOT pvpri.cezih.hr (production!)
- **Soft cert alternative:** Can be installed on PC (file-based), less secure
- **Request cert:** digitalni.certifikat@hzzo.hr or Klovićeva 1, Zagreb

### Certilia Certificate Types (AKD)

| Type | Description | Card Required | CEZIH Actions | Purchase |
|------|-------------|---------------|---------------|----------|
| **Certilia Smart Card** | Physical chip card, private key on card, USB reader needed | Yes | ALL — VPN + mTLS + signing | AKD |
| **Certilia mobileID** | Certificate on mobile device (Android/iOS), no card reader | No | ALL — remote signing + auth code flow | Certilia app |
| **Certilia Cloud (udaljeni)** | Remote-hosted certificate, fully software-only, eIDAS QES | **No** | ALL — remote signing via certpubws.cezih.hr | https://portal.certilia.com/ |

**BOTH smart card and Certilia mobile/cloud must work for ALL 22 test cases.** Per-user preference set in Postavke → Korisnici. No method is a "fallback" — each is a first-class, fully independent path.

### Test Environment Certificates

Local test CA chain available at `docs/CEZIH/CertificateChain-TEST/`:
- `TESTAKDCARoot.crt` — AKD root CA
- `TESTCERTILIACA.crt` — Certilia CA
- `TESTHRIDCA.crt` — HR ID CA
- `TESTKIDCA.crt` — KID CA

## VPN Connection

- Must be established before any CEZIH API calls
- Uses client certificate from smart card or soft cert
- VPN client info: http://www.cezih.hr/VPN_klijent.html
- Creates encrypted tunnel to CEZIH internal network
- Session cookie maintained for subsequent calls

## ~~SOAP Web Services~~ → FHIR REST API (za privatnike)

> **DEPRECATED for private providers.** The old SOAP/HL7 CDA architecture applies to HZZO-contracted providers (G2-G9).
> Private providers use the new FHIR R4 + IHE profile system (CUS).

### Old System (SOAP — only for HZZO-contracted providers)
- WSDL-defined SOAP services
- WSDLs: http://www.cezih.hr/dokumentacija.html
- Python libraries: zeep or suds-jurko
- HL7 CDA R2 XML documents

### New System (FHIR — for private providers, our target)

**Protocol:** FHIR R4 + IHE profiles (MHD, PDQm, SVCM, mCSD, PMIR, QEDm)

**Auth — Two-Tier Model (discovered 2026-04-07):**
- **Service account** (client_credentials grant): Reference data only (terminology, mCSD, OID registry)
- **User identity** (Certilia authorization code flow + SMS 2FA): Clinical data (patients, visits, cases, documents)
- Clinical roles are assigned to the USER (test doctor TESTNI55), not the service account
- Service account token roles: offline_access, uma_authorization, default-roles-cezih (no clinical access)

**VPN:** `pvsek.cezih.hr` (test) — NOT `pvpri.cezih.hr` (production!)

**Test Environment Endpoints:**
| Service | URL | Port | Auth | VPN |
|---------|-----|------|------|-----|
| OAuth2 (Keycloak) | `certsso2.cezih.hr/auth/realms/CEZIH/...` | 443 | client_credentials | Yes |
| Reference services | `certws2.cezih.hr` | **9443** | Bearer token (service account) | Yes |
| Clinical services | `certws2.cezih.hr` | **8443** | Certilia session (auth code + 2FA) | Yes |
| Remote Signing | `certpubws.cezih.hr` | 443 | TBD (403 with service account) | **No** |

**⚠️ Keycloak uses older URL format with /auth/ prefix:** `certsso2.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token`

**Port 9443 Services (Bearer token OK):**
| Service | Path | Method | Status |
|---------|------|--------|--------|
| CodeSystem sync | `terminology-services/api/v1/CodeSystem` | GET | ✅ 200 |
| ValueSet expand | `terminology-services/api/v1/ValueSet` | GET | ✅ 200 |
| Organization search | `mcsd/api/Organization` | GET | ✅ 200 (no /v1/!) |
| Practitioner search | `mcsd/api/Practitioner` | GET | ✅ 200 (no /v1/!) |
| OID generate | `identifier-registry-services/api/v1/oid/generateOIDBatch` | POST | ✅ TC6 VERIFIED (used in TC18 document submit) |
| StructureDefinition | `fhir/StructureDefinition` | GET | Untested |
| Notifications pull | `notification-pull-service/api/v1/notifications` | GET | Untested |
| Notifications push | `notification-push-websocket/api/v1/notifications` | WSS | Untested |
| Signing | `extsigner/api/sign` | POST | ⚠️ Wrong table — extsigner is on port 8443 (see below) |

**Port 8443 Services (need Certilia auth code flow):**
| Service | Path | Method | Status |
|---------|------|--------|--------|
| Patient lookup | `patient-registry-services/api/v1/Patient` | GET | ✅ 200 (via mTLS cookie) |
| Foreigner reg | `patient-registry-services/api/iti93` | POST | ✅ TC11 VERIFIED (2026-04-13) — Patient/1348216 created; extsigner only; 4 stacked fixes |
| Visit management | `encounter-services/api/v1/$process-message` | POST | ✅ TC12 VERIFIED (2026-04-16) — **BOTH signing methods** (smartcard AKD ES384 + extsigner RS256) |
| Case management | `health-issue-services/api/v1/$process-message` | POST | ✅ TC16/17/case-actions VERIFIED (2026-04-16) — create, remission, resolve, relapse, reopen all working (extsigner) |
| Doc submit (ITI-65) | `doc-mhd-svc/api/v1/iti-65-service` | POST | ✅ TC18 VERIFIED (2026-04-10) — transaction bundle, no signing, OID from registry |
| Extsigner (sign) | `services-router/gateway/extsigner/api/sign` | POST | ✅ WORKING — Certilia remote signing (201 → poll → 200) |
| Extsigner (retrieve) | `services-router/gateway/extsigner/api/getSignedDocuments` | GET | ✅ WORKING |
| Doc search | `doc-mhd-svc/api/v1/DocumentReference` | GET | ✅ TC21 VERIFIED (2026-04-11) — real documents returned |
| Doc retrieve | `doc-mhd-svc/api/v1/iti-68-service` | GET | ✅ TC22 VERIFIED (2026-04-13) — application/pdf binary retrieved |
| QEDm encounters | `ihe-qedm-services/api/v1/Encounter` | GET | ✅ TC15 VERIFIED (2026-04-11) — real encounters returned |
| QEDm conditions | `ihe-qedm-services/api/v1/Condition` | GET | ✅ TC15 VERIFIED (2026-04-11) — 12 cases returned |
| SGP referral | `sgp-referral-services/api/v1/$process-message` | POST | Untested |

**Port 8443 Auth Flow (Apache mod_auth_openidc):**

**With smart card (mTLS) — NO interactive login needed:**
1. certws2:8443 → SSL renegotiation (requests client cert) → 302 to Keycloak
2. Keycloak sees client cert → auto-authenticates → 302 back with `code=`
3. certws2:8443/protected?code=... → session cookie set → FHIR access granted

**With Certilia mobile/cloud (auth code + SMS 2FA) — no card needed:**
1. certws2:8443 → 302 redirect to certsso2 Keycloak
2. Keycloak → 303 redirect to Certilia identity broker
3. idp.test.certilia.com → Login page (username/password + SMS 2FA)
4. After auth → redirect back with session cookie → FHIR access granted

**Both methods are first-class.** Smart card mTLS bypasses Certilia 2FA because the card IS the identity proof. Certilia flow uses interactive 2FA as its identity proof. Both achieve the same result — authenticated FHIR session.

**⚠️ POST session issue (FIX APPLIED 2026-04-08):** mTLS cookie session works for GET requests. POST was failing because libcurl converts POST→GET during 302 Keycloak redirects (RFC 7231 default behavior), losing the request body. **Fix:** Added `CURLOPT_POSTREDIR` (`PostRedirections::redirect_all`) to agent libcurl session + expanded retry logic for HTML/empty POST responses + improved warmup URL to target encounter service. Needs retest against real CEZIH.

**Encounter CodeSystems (discovered 2026-04-07):**
CEZIH does NOT use standard HL7 v3-ActCode for Encounter.class. Must use Croatian CodeSystems:

| Field | CodeSystem | Codes |
|-------|-----------|-------|
| `Encounter.class` (nacin-prijema) | `http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema` | 1=Hitni prijem, 2=Uputnica PZZ, 3=Premještaj iz druge ustanove, 4=Nastavno liječenje, 5=Premještaj unutar ustanove, 6=Ostalo, 7=Poziv na raniji termin, 8=Telemedicina, 9=Interna uputnica, 10=Program+ |
| `Encounter.type[VrstaPosjete]` | `http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete` | 1=Pacijent prisutan, 2=Pacijent udaljeno prisutan, 3=Pacijent nije prisutan |
| `Encounter.type[TipPosjete]` | `http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete` | 1=Posjeta LOM, 2=Posjeta SKZZ, 3=Hospitalizacija |

**Encounter FHIR Profiles (from CEZIH StructureDefinition server):**
| Profile | URL |
|---------|-----|
| HRCreateEncounterMessage | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-create-encounter-message` |
| HRUpdateEncounterMessage | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-update-encounter-message` |
| HRCloseEncounterMessage | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-close-encounter-message` |
| HRCancelEncounterMessage | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-cancel-encounter-message` |
| HRReopenEncounterMessage | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-reopen-encounter-message` |
| HREncounterResponseMessage | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-encounter-response-message` |
| HREncounter | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-encounter` |
| HREncounterManagementMessageHeader | `http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-encounter-management-message-header` |

**Test Credentials:**
- Client ID: `d9fe4a5d-4ca2-4e21-8ad3-0016d78ce02f`
- Client Secret: `jqx3xvCgLmiHknraNseDfJ885nexsYJ9`
- Test Patient: OIB `99999900187`, MBO `999990260`, GORAN PACPRIVATNICI19
- Test Doctor: MBO `500604936`, HZJZ `7659059`, TESTNI55 TESTNIPREZIME55
- Test Institution: `999001464` — "HM DIGITAL ordinacija"
- Certilia test login: `hrvoje@hmdigital.hr` (requires SMS 2FA)

**IHE Transactions:**
| Transaction | Profile | Purpose |
|-------------|---------|---------|
| ITI-65 | MHD | Provide Document Bundle (submit clinical documents) |
| ITI-67 | MHD | Find Document References (search documents) |
| ITI-68 | MHD | Retrieve Document (download) |
| ITI-78 | PDQm | Patient Demographics Query (lookup by MBO) |
| ITI-90 | mCSD | Find Matching Care Services (organizations, practitioners) |
| ITI-95 | SVCM | Query Value Set Expansion (concept sets sync) |
| ITI-96 | SVCM | Query Code System (code list sync) |
| PMIR | PMIR | Patient Master Identity Registry (foreigner registration) |
| QEDm | QEDm | Query for Existing Data (retrieve cases) |

### FHIR Implementation Guides (Official — Simplifier.net)

| Guide | URL | Description |
|-------|-----|-------------|
| **CEZIH osnova** | https://simplifier.net/guide/cezih-osnova | Core: resources, security, identifiers, extensions, terminology |
| **Klinički dokumenti** | https://simplifier.net/guide/klinicki-dokumenti | Clinical document exchange (**key for privatnici**) |
| **Upravljanje posjetima** | https://simplifier.net/guide/upravljanje-posjetama | Visit management (create/update/close) |
| **Upravljanje slučajevima** | https://simplifier.net/guide/upravljanje-slucajevima | Case/episode management |
| **COD** | https://simplifier.net/guide/cezih.hr.cod | Croatian Oncology Database |

**FHIR Package:** `cezih.hr.cezih-osnova` v1.0.0 — https://packages2.fhir.org/packages/cezih.hr.cezih-osnova

### CUS Technical Documentation (cezih.hr)

| Document | URL |
|----------|-----|
| Connection Specification | http://www.cezih.hr/cus/CEZIH-CUS_SpecifikacijaPovezivanja_B.docx |
| Code List Web Services | http://www.cezih.hr/cus/CUS-Implementacija_web_servisa_sifrarnika_F.docx |
| IHE Integration | http://www.cezih.hr/cus/CUS-Implementacija_web_servisa_za_IHE_A_19072019.docx |
| Transition Guide | http://www.cezih.hr/cus/CUS-Integracija-Upute_za_prelazak_na_certifikacijsku_i_produkcijsku_okolinu_B.docx |

### Known Production URLs (CUS)
- Runtime: `https://cus.zdravlje.hr:9449/`
- Runtime alt: `https://cus.zdravlje.hr:9446/`
- Browser: `https://cus.zdravlje.hr:9447/`
- FHIR identifier namespace: `http://fhir.cezih.hr/specifikacije/identifikatori`

## ~~G9 Certification (SKZZ)~~ → Unified Private Provider Certification

> **For private providers:** Single unified certification (22 test cases) replaces old G2-G9 groups.
> Old G2-G9 groups apply only to HZZO-contracted providers.

### 22 Test Cases for Private Providers (published 16.12.2025.)

| # | Test Case | IHE/FHIR Profile |
|---|-----------|-----------------|
| 1 | Auth with smart card | PKI |
| 2 | **Auth with cloud certificate** | PKI (cloud) |
| 3 | Auth of information system | OAuth2 |
| 4 | Signing with smart card | PKI |
| 5 | **Signing with cloud certificate** | PKI (cloud) |
| 6 | OID registry lookup | HTTP POST |
| 7 | Code list sync | IHE SVCM ITI-96 |
| 8 | Concept set sync | IHE SVCM ITI-95 |
| 9 | Subject registry lookup (orgs, practitioners) | IHE mCSD ITI-90 |
| 10 | Patient demographics lookup | IHE PDQm ITI-78 |
| 11 | Foreigner registration | PMIR |
| 12 | Create visit | FHIR messaging |
| 13 | Update visit | FHIR messaging |
| 14 | Close visit | FHIR messaging |
| 15 | Retrieve existing cases | IHE QEDm |
| 16 | Create case | FHIR messaging |
| 17 | Update case | FHIR messaging |
| 18 | Send clinical document (report after exam) | HR::ITI-65 / IHE MHD |
| 19 | Replace clinical document | HR::ITI-65 |
| 20 | Cancel clinical document | HR::ITI-65 |
| 21 | Search clinical documents | ITI-67 |
| 22 | Retrieve clinical document | ITI-68 |

**Test cases spreadsheet:** http://www.cezih.hr/aplikacije/Testni%20slucajevi_certifikacija%20privatnika.xlsx

### Testing procedure
1. Developer brings laptop to HZZO Zagreb (Margaretska 3 or Bolnička 94)
2. Connect to test environment via VPN (smart card OR cloud cert)
3. Execute all 22 test cases from "Testni slučajevi – privatnici"
4. Results recorded in inspection report
5. If passed → Business cooperation agreement + system operation protocol
6. Published on cezih.hr certified list

### Protocol document
- New: http://www.cezih.hr/dokumenti/Protokol_27102017.pdf
- Old (reference): http://www.cezih.hr/dokumenti/Protokol_za_provodenje_certifikacije_2016_s_pojasnjenjima.pdf

### Workshop recordings
- 19.03.2026.: http://www.cezih.hr/dokumenti/2026/Dodatna%20radionica%20-%20G500-20260318_104122-Snimka%20sastanka%201.mp4
- 05.12.2025.: http://www.cezih.hr/dokumenti/Gx%20radionica-%20privatnici_20251205.mp4

## Patient Identification

- **MBO** (matični broj osiguranika) — primary patient ID in CEZIH
- **KNOWN ISSUE:** Private clinics historically couldn't access MBO numbers
- **GIP** — internal ID code, linked to Electronic Population Register
- Health insurance card contains MBO — can be read with card reader

## Code Lists & Registries

- Institution codes (šifra ustanove): assigned by HZZO
- Diagnosis codes: ICD (MKB klasifikacija)
- Procedure codes: medical/dental procedure lists
- Full code lists: http://www.cezih.hr/sifrarnici.html
- Code list document: http://www.cezih.hr/pzz/kodneliste/Kodne_liste.doc

## Cloud Architecture — Updated 2026-04-16

**BOTH signing methods work independently for ALL CEZIH actions.** Per-user preference. No method is "optional" or "fallback" — each is fully supported.

### Method A: Local Agent + Smart Card
```
Browser → Cloud Backend → Local Agent (Tauri) → Card Reader → VPN → CEZIH
```
- AKD smart card handles: VPN tunnel, mTLS session auth, document signing (JWS)
- Per-user preference: `cezih_signing_method = "smartcard"`
- Requires: AKD kartica + USB čitač (ISO 7816) + VPN klijent + Local Agent

**Smart Card JWS format (VERIFIED 2026-04-16, agent v0.13.0):**
- Algorithm: ES384 (ECDSA P-384), `NCryptSignHash` with `flags=0` — AKD card returns raw P1363 natively
- Canonicalization: **JCS (RFC 8785)** via `jcs.canonicalize()` in `message_builder.py` — NOT `json.dumps`
- JWS form: **detached** (`header..sig`, empty middle) — signing input uses attached form for hash
- JOSE header: `{"alg":"ES384","jwk":{...},"kid":"<sha1-hex>"}` — jwk contains **nested** x5c, never top-level
- jwk fields (exact order): `kty, x5t#S256, nbf, use, crv, kid, x5c, x, y, exp`
- Output: double-base64 (`base64(JWS_compact)`) to avoid dots in FHIR `base64Binary` (HAPI-1821)
- See `docs/CEZIH/findings/smartcard-jws-format-fix.md` and `.claude/skills/cezih/signing.md` for full details

### Method B: Certilia Mobile/Cloud (no card, no VPN, no local agent)
```
Browser → Cloud Backend → certpubws.cezih.hr (remote signing) → CEZIH
```
- Certilia handles: document signing via remote push approval on phone
- For FHIR API: Certilia auth code flow + SMS 2FA (no VPN needed)
- Per-user preference: `cezih_signing_method = "extsigner"`
- Requires: Certilia račun + mobitel (Android/iOS)
- No physical card, no card reader, no VPN, no local agent needed

### Method C: Hybrid (user chooses per-account)
```
Browser → Cloud Backend
              ↕
      ┌───────┴────────┐
      │                │
  Local Agent      Certilia Remote
  Smart Card       Mobile/Cloud
```
- Each user picks their preferred method in Postavke → Korisnici
- System default via `CEZIH_SIGNING_METHOD` env var
- **No fallbacks** — each method must work independently for ALL actions

**RESOLVED:** HZZO accepts both smart card (TC1+TC4) and cloud/mobile certificate (TC2+TC5) for privatnici certification. Both are first-class paths.

### Mobile / Remote Access Architecture

With smart card method, the doctor does NOT need to be physically at the card reader:

```
Doctor's phone/laptop (bilo gdje)
    → Browser → Cloud Backend (REST)
        → Local Agent u ordinaciji (desktop, kartica umetnuta)
            → AKD kartica potpisuje zahtjev
                → VPN → CEZIH → odgovor natrag → Cloud → Mob
```

With Certilia mobile method, no base station needed — signing happens on the phone directly.

**Two separate data flows:**

| Tip operacije | Kartica metoda | Certilia metoda |
|---------------|---------------|-----------------|
| Kartoni pacijenata, raspored, bilješke, medicinski nalazi | Cloud — uvijek dostupno | Cloud — uvijek dostupno |
| CEZIH operacije (e-Nalaz, e-Recept, e-Uputnica, MBO provjera) | Agent + kartica (bazna stanica) | Mobitel — uvijek dostupno |

---

## PIN, VPN & Smart Card — Istraživanje (2026-03-24)

Bazirano na javno dostupnoj CEZIH/HZZO dokumentaciji i PKCS#11 standardu.

### 1. PIN politika AKD kartice

**Nalaz: Najvjerojatnije jednom po sessiji (ne za svaku operaciju).**

- AKD kartica koristi jedan 5-znamenkasti PIN za zaštitu osobnog certifikata
  (izvor: cezih.hr/Osobni_certifikati.html, hzzo.hr/pitanja-i-odgovori/23)
- PIN se unosi na dva mjesta u workflow-u:
  1. Kod uspostave VPN konekcije (Cisco AnyConnect → `pvpri.cezih.hr`)
  2. Kod prijave u aplikaciju
- Po PKCS#11 standardu, `C_Login` stanje se dijeli kroz sve sessije na istom tokenu
  — PIN se unese jednom i vrijedi do `C_Logout` ili vađenja kartice
- Eskulap vodič ima Cisco postavku "Disable: do not remember PIN" — što znači
  da je PIN caching očekivano ponašanje u CEZIH ekosustavu
- AKD middleware: `libEidPkcs11.so` (AKD eID Middleware PKCS11 v1.7)

**Izuzetak:** Ako ključ za potpis na kartici ima `CKA_ALWAYS_AUTHENTICATE = CK_TRUE`,
PIN se traži za **svaku** kriptografsku operaciju (potpis/dekript).

**AKCIJA:** Kad testna kartica stigne → `pkcs11-tool --list-objects --login` → provjeriti atribute ključa.

### 2. VPN Session Timeout

**Nalaz: Najvjerojatnije 30 minuta idle timeout (Cisco ASA default).**

- CEZIH VPN koristi **Cisco AnyConnect** (IPsec, certifikat s kartice) prema `pvpri.cezih.hr`
- Cisco ASA defaulti:
  | Parametar | Default | Opis |
  |-----------|---------|------|
  | `vpn-idle-timeout` | 30 min | Prekid nakon 30 min neaktivnosti |
  | `vpn-session-timeout` | Neograničen | Nema hard cap na trajanje |
  | Client DPD | 30 sec | Keepalive interval |
  | Server DPD | 300 sec | Server-side keepalive |
- Eskulap vodič potvrđuje da sustav javlja grešku kad VPN padne ili se kartica
  izvadi tijekom rada, ali ne spominje proaktivni timeout

**Za local agent:** Implementirati keepalive mehanizam (ping svakih ~5 min) da sesija ne istekne.

**NAPOMENA:** CEZIH VPN dokumentacija (PDF-ovi na cezih.hr) nije bila dostupna
zbog self-signed certifikata. Točan timeout potvrditi testiranjem na `pvpri.cezih.hr`.

### 3. Kartica stalno u čitaču — dopuštenost

**Nalaz: Nema pravila koje to zabranjuje. Sustav očekuje da kartica ostane umetnuta.**

- **Pravilnik NN 150/2024** (čl. 8, 10) — zahtijeva "odgovarajuće fizičke sigurnosne
  mjere" i da pristup "ne smije biti dijeljen" — ali **ne spominje vađenje kartice**
- **Eskulap pravila za rad s karticom** — PIN lockout (3 pokušaja), periodična
  promjena PIN-a, povjerljivost — ali **nema removal policy**
- **Eskulap vodič** — sustav javlja grešku ako se kartica izvadi tijekom rada,
  što implicira da kartica **treba ostati umetnuta** za normalan rad
- **HZZO soft certifikati** postoje kao alternativa (bez kartice) — sustav
  arhitekturalno ne zahtijeva stalnu fizičku prisutnost kartice za svaku operaciju

**Za local agent:** Kartica ostaje u čitaču tijekom radnog dana. Sigurnost osigurati:
- Zaključavanje workstationa kad je neaktivan (Windows lock)
- Fizička sigurnost ordinacije (zaključan ured)
- Audit log svih CEZIH operacija u cloudu

### Izvori

| Izvor | URL | Što sadrži |
|-------|-----|------------|
| CEZIH osobni certifikati | cezih.hr/Osobni_certifikati.html | PIN info, 5-znamenkasti |
| HZZO FAQ | hzzo.hr/pitanja-i-odgovori/23 | PIN promjena, kartica |
| Eskulap VPN vodič | edborel.hr/htm/VpnKonekcija.htm | Cisco AnyConnect setup |
| Eskulap eRecept | edborel.hr/htm/eRecept_spajanje_na_cezih.htm | Login flow, card removal alert |
| Eskulap pravila kartice | edborel.hr/htm/Pravila%20za%20rad%20s%20pametnom%20karticom.htm | PIN lockout, povjerljivost |
| AKD eID Applet spec | akd.hr/en/products-and-solutions/solutions/akd-eid-applet | Dual PIN, PKCS#11 |
| PKCS#11 spec | cryptsoft.com/pkcs11doc/v220/ | C_Login session sharing |
| Cisco AnyConnect Admin | cisco.com (AnyConnect 5.0 admin guide) | DPD, timeout defaults |

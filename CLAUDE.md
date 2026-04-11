# HM Digital — Medical MVP (Polyclinic Patient Management + CEZIH)

## What This Is

Cloud-based patient management system for Croatian private polyclinics and medical practices, with native CEZIH integration. Competes with Toscana (UX) and AdriaSoft (compliance).

**Hard deadline:** 1 May 2026 (Zakon o podacima i informacijama u zdravstvu, NN 14/2019, čl. 28 — mandatory CEZIH for all providers)
**Market:** 2,488 private healthcare institutions in Croatia
**Model:** Cloud SaaS — 14-day free trial → Solo €49/mo promo until 1.5. then €79/mo | Poliklinika €199/mo | Poliklinika+ po dogovoru

**User limits:**
| Plan | Website (live marketing) | Code (plan_limits.py) | Status |
|------|--------------------------|----------------------|--------|
| Solo | 1-2 korisnika | max_users=2 | ✅ aligned |
| Poliklinika | 3-5 korisnika | max_users=5 | ✅ aligned |
| Poliklinika+ | 6-15+ korisnika | max_users=15 | ✅ aligned |

**Onboarding:** Solo €490 (€290 promo), Poliklinika €1,490 | On-site: Slavonija €190, Zagreb €350, Dalmacija/Istra €490
**Lead list:** docs/medical_leads.csv (4,986 clinics, 2,884 with phone numbers)

## Project Structure

```
MEDICAL_MVP/
├── backend/          # FastAPI — REST API + WebSocket + CEZIH mock
├── frontend/         # Next.js — Patient management UI
├── local-agent/      # Tauri 2.x desktop app — smart card + VPN + WebSocket bridge
├── .github/workflows/deploy.yml        # CI/CD — server auto-deploy on push to main
├── .github/workflows/release-agent.yml # CI/CD — agent auto-release when version bumped
├── docker-compose.yml        # Production stack (Caddy + DB + Backend + Frontend + Backup)
├── docker-compose.dev.yml    # Dev override (direct ports, hot reload, no Caddy)
├── Caddyfile                 # Reverse proxy config (auto-SSL via Let's Encrypt)
├── deploy.sh                 # One-command deploy script (pull → build → up → migrate)
├── .env.example              # Production env var template
└── docs/
    ├── roadmap.md             # Master status tracker + timeline + all contacts
    ├── competitors.md         # Deep-dive competitive analysis (19 vendors verified)
    ├── cezih-technical.md     # VPN, PKI, FHIR REST API, OAuth2, cloud cert, 22 test cases
    ├── go-to-market.md        # Sales strategy, professional association partnerships, conferences, outreach
    └── implementation-plan.md # Full build spec — DB schema, API, UI, phases (junior-friendly)
```

## Tech Stack

- **Frontend:** Next.js 16, TypeScript, Tailwind CSS, shadcn/ui
- **Backend:** FastAPI, SQLAlchemy async, PostgreSQL
- **Local Agent:** Tauri 2.x (Rust), tokio-tungstenite, system tray — **REQUIRED**, reads AKD smart card, manages VPN
- **Infrastructure:** Docker Compose, Caddy (reverse proxy + auto-SSL), GitHub Actions CI/CD
- **CEZIH Integration (novi format za privatnike):** FHIR R4 + IHE profili (MHD, PDQm, SVCM, mCSD, PMIR, QEDm), OAuth2 via Keycloak, AKD smart card (mandatory for VPN)

## CEZIH Integration Architecture

### Smart Card + Local Agent (MANDATORY)
```
Browser ←→ Cloud Backend (FastAPI) ←→ Local Agent (Tauri) ←→ CEZIH
                REST API                  AKD smart card + VPN    FHIR/JSON
```

**⚠️ VPN does NOT support Certilia Cloud certificates.** Physical AKD smart card is required for VPN authentication. Cloud cert is signing-only (certpubws.cezih.hr, no VPN needed) — useful for remote document signing but not for CEZIH API access.

**Each client needs:** AKD kartica + USB čitač (ISO 7816) + VPN klijent + Local Agent installed

## Key CEZIH Modules (Unified Private Provider Certification)

| Module | Description | Format/Profile |
|--------|-------------|---------------|
| Auth & Signing | Smart card + cloud cert auth, document signing | PKI, OAuth2 |
| Patient Lookup | Demographics by MBO | IHE PDQm (ITI-78) |
| Clinical Documents | Send/replace/cancel/search/retrieve findings | IHE MHD (ITI-65/67/68) |
| Visits | Create/update/close patient visits | FHIR messaging |
| Cases | Create/update, retrieve existing cases | FHIR messaging, QEDm |
| Code Lists | Sync terminology, concept sets | IHE SVCM (ITI-95/96) |
| Subject Registry | Organizations, practitioners lookup | IHE mCSD (ITI-90) |
| OID Registry | Institution identifier lookup | HTTP POST |
| Foreigner Registration | Register non-insured patients | PMIR |

## Croatian Localization

- All UI in Croatian (Hrvatski)
- UTF-8 for šđčćž
- Timezone: Europe/Zagreb
- Currency: EUR
- GDPR compliant

## Development Progress

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 0 | DONE | Environment & scaffolding |
| Phase 1 | DONE | Auth & multi-tenancy |
| Phase 2 | DONE | Patient management |
| Phase 3 | DONE | Appointment scheduling |
| Phase 4 | DONE | Medical records & procedures |
| Phase 5 | DONE | Dashboard & settings |
| Phase 6A | DONE | Plan enforcement (tier limits, session kick, usage API) |
| Phase 6B | REMOVED | ~~CEZIH mock backend~~ — mock services deleted, production uses real CEZIH only |
| Phase 6C | DONE | CEZIH frontend (CEZIH page, insurance check, e-Nalaz send from records) |
| Phase 7 | DONE | Local agent skeleton (Tauri, WebSocket, agent auth, live status, system tray) |
| Phase 8 | DONE | Polish, testing, demo environment (bug fix, middleware, seed data, tests, Docker, mobile) |
| Phase 9 | DONE | CEZIH real infrastructure (config, OAuth2, HTTP client, FHIR models, dispatcher, exceptions) |
| Phase 9.5 | DONE | Remote signing service (certpubws.cezih.hr, separate OAuth, hash+sign, health check) |
| Phase 10 | DONE | Production deployment (Caddy reverse proxy, Docker hardening, CI/CD, git workflow) |
| Phase 11 | DONE | CEZIH full implementation — all 22 test cases (visits, cases, documents, registries, foreigner, storno) |
| Phase 12 | DONE | Nalazi/Biljeske separation + CEZIH compliance audit (2026-04-07) |
| Phase 13 | DONE | Production hardening — mock services removed, CEZIH credentials mandatory (2026-04-08) |
| Phase 14 | DONE | CEZIH live verification — 12/22 TCs verified against real CEZIH, FHIR compliance fixes (2026-04-11) |

### Phase 12 Details (completed 2026-04-07)

**Nalazi → CEZIH-only + new Biljeske tab:**
- Nalazi tab now shows only CEZIH-eligible types (specijalisticki_nalaz, nalaz)
- New Biljeske tab for internal clinical notes (6 categories), full CRUD, separate DB table
- Non-CEZIH record types deactivated (dijagnoza, misljenje, preporuka, anamneza, ambulantno_izvjesce, otpusno_pismo, epikriza)
- Fixed CEZIH CodeSystem URI to official `http://fhir.cezih.hr/specifikacije/CodeSystem/document-type`

**CEZIH compliance audit — missing UIs built:**
- TC12-14: Visit management (backend API + dispatcher + mock + frontend hooks + visit-management.tsx)
- TC6: OID lookup UI (registry-tools.tsx)
- TC8: ValueSet expand UI (registry-tools.tsx)
- TC9a/9b: Organization + Practitioner search UI (registry-tools.tsx)
- TC17b: Case data update UI ("Uredi" button in case-management.tsx)
- New "Registri" tab on CEZIH settings page
- MBO validation in send flows
- Audit log key mismatch fixed

**New files:** `biljeska.py` (model/schema/service/API), `biljeska-*.tsx` (3 components), `use-biljeske.ts`, `visit-management.tsx`, `registry-tools.tsx`, migration 023
**33+ API endpoints**, **32+ React hooks**, **14 CEZIH components**

### Phase 13 Details (completed 2026-04-08)

**Mock service removal — production hardening:**
- Deleted `cezih_service.py` (763 lines of mock implementations)
- Removed `CEZIH_MODE` env var and all `_is_mock()` branches from dispatcher (26 functions cleaned)
- Removed `mock: bool` from 24 Pydantic schemas and 23 frontend TypeScript interfaces
- Fixed e-Recept/cancel stubs to raise proper errors instead of fake success
- Renamed PDF signer `_sign_mock` → `_sign_local` (legitimate local certificate, not a mock)
- Made CEZIH credential validation FATAL in production (was only a warning)
- Deleted `test_cezih_mock.py`, cleaned `test_dispatcher.py` and `test_cezih_new_modules.py`
- Updated docker-compose.dev.yml, .env.example, all documentation

**Net result:** ~1,200 lines removed, 0 new functionality. Production app cannot start without real CEZIH credentials.

### Phase 11 Details (completed 2026-03-30)

All 22 CEZIH certification test cases implemented across backend (service + dispatcher + API) and frontend (types + hooks + components):

- **TC 1-5:** Auth & signing (cloud cert path — ready, needs VPN test)
- **TC 6:** OID registry lookup
- **TC 7:** Code list sync ITI-96 (generalized: ICD-10, procedures, drugs, admission types)
- **TC 8:** Concept set sync ITI-95 (ValueSet expand)
- **TC 9:** Subject registry ITI-90 mCSD (organizations + practitioners)
- **TC 10:** Patient demographics ITI-78 PDQm
- **TC 11:** Foreigner registration PMIR
- **TC 12-14:** Visit management — create (1.1), update (1.2), close (1.3), reopen (1.5), storno (1.4)
- **TC 15-17:** Case management — retrieve QEDm, create (2.1), recurring (2.2), remission (2.3), relapse (2.4), resolve (2.5), data update (2.6), reopen (2.7), delete (2.8)
- **TC 18:** Send clinical document ITI-65
- **TC 19:** Replace clinical document
- **TC 20:** Cancel/storno clinical document
- **TC 21:** Search documents ITI-67 (flexible: patient, type, date range, status)
- **TC 22:** Retrieve document ITI-68

**Note:** Phase 11 originally claimed visit management as complete, but TC12-14 backend/frontend was actually missing and was built in Phase 12.

### Phase 14 Details (completed 2026-04-11)

**CEZIH live verification — 12/22 TCs verified against real CEZIH test environment:**

Verified TCs:
- **TC3:** OAuth2 system auth — token caching working (Keycloak service account)
- **TC5:** Cloud cert signing — extsigner 2-step async flow (Certilia remote signing)
- **TC9:** Organization + Practitioner search (mCSD ITI-90) — real data from CEZIH
- **TC10:** Patient demographics (PDQm ITI-78) — GORAN PACPRIVATNICI19, Aktivan, MBO 999990260
- **TC12:** Create visit (1.1) — 200, visit_id assigned
- **TC13:** Update visit (1.2) — 200, reason/fields updated via PATCH
- **TC14:** Close visit (1.3) — 200, status=finished with end timestamp
- **TC15:** Retrieve cases (QEDm) — 12 cases returned from CEZIH
- **TC16:** Create case (2.1) — 200, M79.3 Panikulitis created in CEZIH
- **TC17:** Case remission (2.3) — I10 Esencijalna hipertenzija → remission status confirmed
- **TC18:** Send document (ITI-65) — 200, transaction bundle accepted
- **TC21:** Search documents (ITI-67) — real documents from multiple providers returned

**FHIR compliance fixes (12 commits):**
1. Case identifier system URL: changed `ID_CASE_GLOBAL` from `.../identifikatori/slucaj` to `.../identifikatori/identifikator-slucaja`
2. New `ID_CASE_REF` constant (`.../identifikatori/slucaj`) for Encounter.diagnosis case references
3. Removed `clinicalStatus` from case status transition messages (2.3-2.5, 2.7) — CEZIH profiles set max=0
4. Lenient `$process-message` error handling — CEZIH may return non-2xx for successful operations
5. OperationOutcome severity-aware parsing with `has_fatal_error` property
6. Document search: extract `content_url` from DocumentReference.content.attachment.url
7. Document search: fix field extraction (author instead of context.source)
8. Document retrieve: parse CEZIH gateway URL, extract relative path for agent proxy
9. Document retrieve: `Accept: */*` header for binary content (was 406 with `application/fhir+json`)
10. Binary response handling in FHIR client for non-JSON agent proxy responses
11. ICD-10 code search: try ValueSet/$expand + CodeSystem/$lookup, fallback to inline concepts
12. Manual ICD-10 code entry UI in case-management when CEZIH search returns no results

**Remaining TCs (need on-site investigation):**
- TC19/20 (replace/cancel doc) — 403 from CEZIH, transaction bundle format needs investigation
- TC22 (retrieve binary) — binary content transport through WebSocket agent proxy needs work
- TC6 (OID lookup) — ERR_OID_1000, generateOIDBatch endpoint format mismatch
- TC7/8 (CodeSystem/ValueSet) — CEZIH terminology server doesn't expose ICD-10 concepts inline

## Certification Status

- **HZZO test environment: PROVISIONED** (2026-04-07, helpdesk@hzzo.hr)
- **Test doctor assigned:** MBO `500604936`, HZJZ `7659059`, TESTNI55 TESTNIPREZIME55 (OIB: 15881939647)
- **Test institution created:** `999001464` — "HM DIGITAL ordinacija"
- **Certification request: SENT** (2026-04-07, `provjera.spremnosti@hzzo.hr`)
- Test certificate request: SENT (2026-03-24, `digitalni.certifikat@hzzo.hr`)
- AKD smart card: RECEIVED & ACTIVATED (2026-04-04, PINs set, card #558299)
- VPN connection: **CONNECTED** via `pvsek.cezih.hr` (test env). NOT pvpri.cezih.hr (production!)
- **Certilia Cloud cert: ACTIVE** (udaljeni potpisni certifikat, valid until 26.03.2028.) — signing only, NOT usable for VPN
- Certilia card certs also active (identifikacijski + potpisni na kartici, valid until 26.03.2029.) — waiting for physical card delivery
- **OAuth2 token: WORKING** (client_credentials grant via certsso2, needs `/auth/` prefix in URL)
- **12/22 TCs VERIFIED against real CEZIH** (2026-04-10/11):
  - TC3 (OAuth2), TC5 (cloud signing), TC9 (mCSD org+practitioner), TC10 (PDQm patient)
  - TC12 (visit create), TC13 (visit update), TC14 (visit close)
  - TC15 (retrieve cases), TC16 (create case), TC17 (case remission)
  - TC18 (send document ITI-65), TC21 (search documents ITI-67)
- **Remaining TCs:** TC19/20 (replace/cancel doc — 403), TC22 (retrieve binary — transport issue), TC6-8 (reference format), TC11 (foreigner — untested)
- **All 22 test cases: IMPLEMENTED** (backend + frontend, production-ready — mock mode removed)
- **Mock services removed:** CEZIH_MODE eliminated, cezih_service.py deleted, all mock branches removed from dispatcher, schemas cleaned (2026-04-08)
- **Document type codes:** HRTipDokumenta 011-013 for privatnici (from Simplifier cezih.hr.cezih-osnova v0.2.9)
- **ITI-65 architecture:** Transaction bundle (3 entries: SubmissionSet + DocumentReference + Binary), no signing, OID from registry, visit+case linking required
- **FHIR identifier systems (FIXED 2026-04-11):**
  - `ID_CASE_GLOBAL` = `.../identifikatori/identifikator-slucaja` (Condition.identifier in messages)
  - `ID_CASE_REF` = `.../identifikatori/slucaj` (Encounter.diagnosis case reference)
  - Case status transitions: NO clinicalStatus in message body (event code is sufficient)
- **Next step:** Fix TC19/20/22, prepare for on-site exam at HZZO Zagreb
- Unified private provider certification: PENDING on-site test at HZZO Zagreb

## Deployment

### Git Workflow
- **`main`** = production (auto-deploys via GitHub Actions)
- **`dev`** = development/testing
- Merge `dev → main` triggers:
  - **Server deploy:** backend + frontend auto-deploy (every push)
  - **Agent release:** auto-builds new installer only when agent version is bumped in `tauri.conf.json` + `Cargo.toml`
  - All clients auto-update within 30 minutes via Tauri updater

### Local Agent Distribution & Auto-Update
- **Repo:** `local-agent/` lives in this monorepo; releases published to a **public** GitHub repo (`hmdigital/agent`) for client downloads
- **Download:** Clients download installer from GitHub Releases (public, no auth needed)
- **Auto-update:** App checks on startup + every 30 min → downloads → passive install → relaunch
- **Signing:** Tauri updater requires `.sig` verification (private key in GitHub Secrets, pubkey embedded in app)
- **Release trigger:** Push to `main` with bumped agent version → `release-agent.yml` builds Windows NSIS + `.sig` + `latest.json` → publishes GitHub Release
- **Workflow:** `.github/workflows/release-agent.yml` — only runs when `local-agent/` files changed AND version bumped
- **Required GitHub Secrets:** `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

### Local Development
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
Exposes: backend :8000, frontend :3000, PostgreSQL :5433. No Caddy, hot reload enabled.

### Mandatory Testing Workflow (After Any Code Change)

**Every backend/frontend change requires:**

1. **Rebuild frontend** (Next.js hot reload misses some changes):
   ```bash
   docker compose restart frontend
   # Or full rebuild if dependencies changed:
   docker compose up --build frontend
   ```

2. **Run database migrations** (if schema changed):
   ```bash
   docker compose exec backend alembic upgrade head
   ```

3. **E2E test in browser** via MCP Chrome DevTools:
   - Take snapshot: `take_snapshot`
   - Navigate to affected pages
   - Test the modified feature end-to-end
   - Check console for errors: `list_console_messages`
   - Verify network requests: `list_network_requests`

**Why:** Hot reload is unreliable for schema/type changes. Skipping E2E tests leads to "works on my machine" bugs that only appear in production.

### Production
```bash
# On server (/opt/medical-mvp): copy .env.example → .env, fill in real values:
#   DOMAIN=app.hmdigital.hr
#   DB_PASSWORD=<strong random password>
#   JWT_SECRET_KEY=<openssl rand -hex 32>
docker compose up -d --build
```
Caddy handles SSL automatically via Let's Encrypt. Only ports 80/443 exposed.
Deploy path on server: `/opt/medical-mvp`

### Domain & DNS
- **App domain:** `app.hmdigital.hr` (Medical MVP app)
- **Company website:** `hmdigital.hr` (separate, NOT on Hetzner)
- **DNS:** Only one A record needed: `app.hmdigital.hr` → Hetzner server IP
- **SSL:** Caddy auto-provisions via Let's Encrypt for `app.hmdigital.hr`
- **Application ID (Tauri):** `hr.hmdigital.medical`

### Hosting
Hetzner Cloud CPX11 (2 vCPU / 2 GB / 40 GB, €4.49/mo) + 2 GB swap. Tuned for tight RAM: PostgreSQL 128 MB shared_buffers, 30 max_connections. Handles first 10-20 clinics. Scale to CPX21 (4 GB, ~€8.50/mo) when revenue allows.

### CI/CD
Push to `main` triggers two workflows:
1. **`.github/workflows/deploy.yml`** — SSH into server → runs `deploy.sh` (pull, build, up, migrate, prune). Runs on every push to main.
2. **`.github/workflows/release-agent.yml`** — Builds Windows NSIS installer + publishes GitHub Release. Only runs when agent version is bumped.

Required GitHub secrets: `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`, `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

## Competitive Position

Nobody combines modern cloud UX + CEZIH G9 + specialty-agnostic design.

- 12 CEZIH-certified vendors (all legacy desktop UI)
- 5 modern cloud vendors (zero CEZIH)
- Closest competitor: Aplikacija d.o.o. (cloud + CEZIH but older UX)
- See docs/competitors.md for full analysis

## Go-To-Market

Primary channel: HKDM, HLN, and professional associations — many haven't informed members about CEZIH yet. We position as CEZIH education experts.

Key events: Medical conferences (ongoing, leading up to May deadline).

See docs/go-to-market.md for full strategy.

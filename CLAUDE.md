# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HM Digital — Medical MVP (Polyclinic Patient Management + CEZIH)

## Build & Dev Commands

### Backend (FastAPI — `backend/`)
```bash
cd backend
# Dev server (via Docker):
docker compose -f ../docker-compose.yml -f ../docker-compose.dev.yml up --build backend
# Run tests:
pytest                                          # all tests
pytest tests/test_auth.py -k "test_login"       # single test by name
pytest tests/test_patients.py::test_create      # single test by path
# Lint:
ruff check .                                    # check
ruff check --fix .                              # auto-fix
# Database migrations:
alembic revision --autogenerate -m "description"  # create migration
alembic upgrade head                              # apply all
alembic downgrade -1                              # rollback one
```

### Frontend (Next.js 16 — `frontend/`)
```bash
cd frontend
pnpm install                  # install deps
pnpm dev                      # dev server (localhost:3000)
pnpm build                    # production build
pnpm start                    # serve production build
pnpm lint                     # eslint
```

### Local Agent (Tauri 2.x — `local-agent/`)
```bash
cd local-agent
pnpm install                  # install JS deps
pnpm tauri dev                # dev mode (connects to prod backend)
pnpm tauri build              # production build (Windows NSIS)
```

### Docker (full stack)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build   # dev
docker compose up --build -d                                                 # prod-like
```

## Architecture

### Backend (`backend/app/`)
- **`api/`** — 18 FastAPI routers. `router.py` aggregates all into `api_router` mounted at `/api`. `agent_ws.py` is the WebSocket endpoint for the local agent.
- **`models/`** — SQLAlchemy async ORM. `base.py` defines `BaseTenantModel` (tenant_id FK + timestamps). Most models inherit it for multi-tenant isolation.
- **`services/`** — Business logic. `cezih/` subdirectory has FHIR builders, dispatchers, and API client for CEZIH integration.
- **`schemas/`** — Pydantic v2 request/response models.
- **`core/`** — `plan_enforcement.py` (subscription tier checks), `plan_limits.py` (tier definitions).
- **`middleware/`** — `error_handler.py` (CezihError → HTTP), `request_logger.py`.
- **`dependencies.py`** — `get_current_user()` (cookie + bearer token auth), `require_roles()` (role-based access).
- **`database.py`** — async SQLAlchemy engine, session with auto-commit/rollback.
- **`config.py`** — Pydantic Settings from env vars.

**Auth flow:** JWT access_token in httpOnly cookie + refresh_token. Roles: `admin`, `doctor`, `nurse`, `receptionist`. Session revocation via refresh token invalidation.

**Multi-tenancy:** Every tenant-scoped model has `tenant_id`. `get_current_user()` verifies token tenant matches user tenant. Queries filter by tenant.

### Frontend (`frontend/src/`)
- **`app/`** — Next.js 16 App Router. `(auth)/` for login/register, `(dashboard)/` for all authenticated routes.
- **`components/`** — Organized by domain (appointments, cezih, patients, etc.). `ui/` is shadcn/ui primitives.
- **`lib/hooks/`** — One hook file per domain (`use-{domain}.ts`), all use @tanstack/react-query v5.
- **`lib/api-client.ts`** — Fetch wrapper with auto-refresh, cookie auth, `CezihApiError` handling. **Always use this, never raw fetch.**
- **`lib/constants.ts`** — Croatian label maps, status maps, nav items. **Use these, never hardcode Croatian strings.**
- **`lib/types.ts`** — TypeScript interfaces for all API entities.
- **`lib/auth.tsx`** — AuthProvider context, `useAuth` hook.

**State management:** React Query for server state. Local component state for UI. No global state store.

**⚠️ Next.js 16 breaking changes:** APIs differ from training data. Check `node_modules/next/dist/docs/` before writing code.

### Local Agent (`local-agent/src-tauri/`)
- Rust source: `main.rs`, `lib.rs`, `smartcard.rs` (AKD card reader via PC/SC), `signing.rs`, `vpn.rs`, `websocket.rs`.
- Connects to backend via WebSocket. Handles smart card signing + VPN for CEZIH.
- Dev mode (`pnpm tauri dev`) connects to `wss://app.hmdigital.hr` — no release cycle needed.

### Database (PostgreSQL 16)
- Alembic migrations in `backend/alembic/versions/` (43 migrations).
- Multi-tenant: tenant_id on most tables.
- Key models: User, Tenant, Patient, Appointment, MedicalRecord, Biljeska, Prescription, Procedure, Document, Predracun, ICD10, DrugList, RecordType, CezihCase, CezihVisit, RefreshToken, AuditLog.

## What This Is

Cloud-based patient management system for Croatian private polyclinics and medical practices, with native CEZIH integration.

**Hard deadline:** 1 May 2026 (Zakon o podacima i informacijama u zdravstvu, NN 14/2019, čl. 28 — mandatory CEZIH for all providers)
**Market:** 2,488 private healthcare institutions in Croatia.

**User limits (must stay aligned with `plan_limits.py`):**
| Plan | Website (live marketing) | Code (plan_limits.py) | Status |
|------|--------------------------|----------------------|--------|
| Solo | 1-2 korisnika | max_users=2 | ✅ aligned |
| Poliklinika | 3-5 korisnika | max_users=5 | ✅ aligned |
| Poliklinika+ | 6-15+ korisnika | max_users=15 | ✅ aligned |

For pricing, onboarding fees, lead lists, sales channels and competitive positioning see `klijenti/CLAUDE.md` - those are out of scope for programming work.

## Project Structure

```
MEDICAL_MVP/
├── backend/          # FastAPI — REST API + WebSocket + CEZIH integration
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
- **CEZIH Integration (novi format za privatnike):** FHIR R4 + IHE profili (MHD, PDQm, SVCM, mCSD, PMIR, QEDm), OAuth2 via Keycloak

## CEZIH Integration Architecture

### Dual Signing — Both Methods Work Independently

**Every CEZIH action MUST work with EITHER signing method. No fallbacks. No "preferred" method.**

**Both methods share the same infrastructure baseline:** AKD card + reader + CEZIH VPN + local agent. Clinical FHIR endpoints (`certws2.cezih.hr:8443`) live on the CEZIH internal network and require VPN + mTLS regardless of signing method. Only the signing step differs.

| Method | Signing step |
|--------|--------------|
| **AKD Smart Card** | Local agent reads card → JWS signed locally |
| **Certilia Mobile/Cloud** | Document hash sent to certpubws.cezih.hr → push to mobile → user approves → signed bundle returned |

```
Browser ←→ Cloud Backend (FastAPI)
                ↕
        Local Agent (Tauri)              ← always on path (VPN + mTLS)
                ↕
   ┌────────────┴────────────┐
   │   signing step only     │
   ↓                         ↓
AKD card (local JWS)   Certilia (push to mobile)
   │                         │
   └────────────┬────────────┘
                ↓
   CEZIH FHIR API (certws2.cezih.hr:8443, via VPN)
```

**Per-user preference:** Each user chooses their signing method in Postavke → Korisnici (`cezih_signing_method`: `smartcard` or `extsigner`). System default configurable via `CEZIH_SIGNING_METHOD` env var.

**⚠️ HARD RULE:** Never treat one method as a fallback for the other. Both must be independently tested and verified for ALL 22 test cases. If one method breaks, it's a P0 bug — not a "use the other method" situation. Both methods share the same VPN + agent + card baseline; choosing Certilia replaces the local signing step, not the network stack.

## Key CEZIH Modules (Unified Private Provider Certification)

| Module | Description | Format/Profile |
|--------|-------------|---------------|
| Auth & Signing | Dual signing: smart card OR Certilia mobile — both work for ALL actions | PKI, OAuth2 |
| Patient Lookup | Demographics by MBO | IHE PDQm (ITI-78) |
| Clinical Documents | Send/replace/cancel/search/retrieve findings | IHE MHD (ITI-65/67/68) |
| Visits | Create/update/close patient visits | FHIR messaging |
| Cases | Create/update, retrieve existing cases | FHIR messaging, QEDm |
| Code Lists | Sync terminology, concept sets | IHE SVCM (ITI-95/96) |
| Subject Registry | Organizations, practitioners lookup | IHE mCSD (ITI-90) |
| OID Registry | FHIR system OID generation (auto-generated by our software via TC6, NOT issued by HZZO) | HTTP POST |
| Foreigner Registration | Register non-insured patients | PMIR |

## Onboarding Identifiers — What Client Provides vs What We Auto-Generate

**⚠️ OID ≠ šifra ustanove. HZZO does NOT issue OIDs. Our software generates them via TC6 API.**

| Identifier | Source | Client Action |
|---|---|---|
| **Šifra ustanove** | HZZO (administrative registration) | Client provides (already has it or requests from HZZO) |
| **HZJZ šifra djelatnika** | HZJZ health worker registry (7 digits) | Client provides (every licensed doctor has one) |
| **MBO liječnika** | HZZO insurance (9 digits) | Client provides |
| **AKD kartica / Certilia** | AKD / Certilia | Client obtains (authentication mechanism) |
| **OID info sustava** | CEZIH TC6 API `generateOIDBatch` | **AUTO-GENERATED by our software** — client does nothing |
| **OIB, ime, cert serial** | Smart card certificate | **AUTO-EXTRACTED from card** — client does nothing |
| **Document OIDs** | CEZIH TC6 API (per ITI-65 submission) | **AUTO-GENERATED per document** — client does nothing |

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
| Phase 15 | DONE | CEZIH exam prep — TC19/20/22 fixes (agent binary transport, PUT method, relatesTo format) (2026-04-13) |
| Phase 16 | DONE | CEZIH live verification — TC19 + TC22 verified; TC20 + TC11 investigated (2026-04-13) |
| Phase 17 | DONE | TC20 cancel document — VERIFIED via ITI-65 replace with OID lookup (2026-04-13) |
| Phase 18 | DONE | E2E production test — all 16 TCs verified on app.hmdigital.hr against real CEZIH (2026-04-13) |
| Phase 19 | DONE | TC11 PMIR foreigner registration — VERIFIED (Patient/1348216, 4 stacked fixes) (2026-04-13) |
| Phase 20 | BLOCKED | Structured logging — branch `feat/structured-logging`, merge after HZZO exam (2026-04-23) |

### Key CEZIH Technical Findings (from live testing)

**Signing:**
- Both smart card AND Certilia work for ALL actions including PMIR
  - 22/22 TC matrix verified GREEN on smart card 2026-04-22 + 2026-04-23
  - 22/22 TC matrix verified GREEN on Certilia mobile 2026-04-22 (afternoon reverify)
  - Certilia (extsigner) regressed 2026-04-23–04-28 (CEZIH unilaterally tightened auth on `extsigner/api/sign` to require Bearer token); fixed in commit `960cf3e`. See `docs/CEZIH/findings/2026-04-28-extsigner-bearer-token-required.md`.
  - Certilia mobile path re-verified end-to-end 2026-04-28 on Croatian GORAN: full Posjeta lifecycle, full case lifecycle (2.1 -> 2.3 -> 2.5 -> 2.4 -> 2.9 -> 2.6), and e-Nalaz TC18 -> 19 -> 20 chain (Refs 1493569 -> 1493573 -> Storniran). See `docs/CEZIH/findings/2026-04-28-certilia-mobile-post-bearer-fix-sweep.md`.
- Earlier ERR_DS_1002 on PMIR was caused by bundle structure issues, not signing method

**ITI-65 document bundles:**
- Standard profiles only — `HRExternalMinimalProvideDocumentBundle` (v1.0.1) rejected with 415 ERR_EHE_1099
- Transaction bundle: 3 entries (SubmissionSet + DocumentReference + Binary), no signing, OID from registry
- Document types: HRTipDokumenta 011-013 for privatnici

**Document cancel (TC20):**
- Cancel = ITI-65 replace with `status=current` + relatesTo OID
- CEZIH rejects `entered-in-error` status (ERR_DOM_10057)
- CEZIH resolves relatesTo by OID only — literal `DocumentReference/{id}` fails
- OID extracted from ITI-67 content_url base64 data param

**PMIR foreigner registration (TC11):**
- Pre-flight GET required before POST (Keycloak mTLS session establishment)
- `urn:uuid:` prefix required on all fullUrls and references
- Foreigners get `jedinstveni-identifikator-pacijenta`, not MBO
- HRRegisterPatient profile: Bundle(message) → MessageHeader + Bundle(history) → Patient. Bundle.signature required.

**FHIR identifier systems:**
- `ID_CASE_GLOBAL` = `.../identifikatori/identifikator-slucaja` (Condition.identifier)
- `ID_CASE_REF` = `.../identifikatori/slucaj` (Encounter.diagnosis reference)
- Case status transitions: NO clinicalStatus in message body (event code is sufficient)

**Case delete — HARD RULE: never ship a CEZIH delete action.**
- User policy, not a spec interpretation. Even if Simplifier ships an `hr-delete-health-issue-message` profile, we do NOT expose it to doctors. In live HZZO test env CEZIH has never accepted delete from privatnici providers, and the audit-trail implications are not worth the risk.
- `CASE_ACTION_MAP` must not contain a `delete` entry. Frontend `CASE_ACTIONS` must not contain an "Obriši" option that hits CEZIH.
- Local-only delete (remove from our DB with audit log, never touch CEZIH) is fine as a separate feature.
- For "mistaken entry" UX on CEZIH side: 2.6 Data update with `verificationStatus=entered-in-error`. That's the only CEZIH-compatible neutralization.

**Binary retrieval (ITI-68):**
- Agent returns `body_bytes` (base64) for binary, `body` (text) for JSON
- `Accept: */*` required (406 with `application/fhir+json`)

**Agent (v0.13.0):**
- Binary detection + base64 encoding for PDF content
- PUT method: `custom_request("PUT")` — do NOT chain `.post(true)` (overrides method)

**Simplifier packages (authoritative FHIR specs):**
- `cezih.osnova` v0.2.3 — basic profiles
- `cezih.hr.cezih-osnova` v1.0.1 — COMPLETE (PMIR, hr-delete-patient, hr-update-patient)
- Download: `curl -sL https://packages.simplifier.net/{package}/{version} -o pkg.tgz && tar xzf pkg.tgz`
- Simplifier UI pages do NOT serve raw JSON — must download tar.gz

## Certification Status

- **HZZO test environment: PROVISIONED** (helpdesk@hzzo.hr)
- **Test doctor:** MBO `500604936`, HZJZ `7659059`, TESTNI55 TESTNIPREZIME55 (OIB: 15881939647)
- **Test institution:** `999001464` — "HM DIGITAL ordinacija"
- **AKD smart card:** RECEIVED & ACTIVATED (card #558299, PINs set)
- **VPN:** CONNECTED via `pvsek.cezih.hr` (test env). NOT pvpri.cezih.hr (production!)
- **Certilia Cloud cert:** ACTIVE (signing only, valid until 26.03.2028, NOT for VPN)
- **Certilia card certs:** Active (valid until 26.03.2029, waiting for physical card delivery)
- **OAuth2:** WORKING (client_credentials via certsso2, needs `/auth/` prefix)
- **22/22 TCs VERIFIED** against real CEZIH (smart card sweep 2026-04-22 + 2026-04-23; Certilia mobile sweep 2026-04-22 afternoon reverify). Certilia path subsequently outaged 2026-04-23–04-28 due to CEZIH Bearer requirement, re-verified after fix on 2026-04-28.
- **Certification:** in flight — exam date pending. Both signing paths verified working as of 2026-04-28; ready when scheduling resumes.

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

### Local Agent — Dev Mode (pointed at prod)

**The local Tauri agent at `C:\Dev\HM DIGITAL\MEDICAL_MVP\local-agent` runs in dev mode against `app.hmdigital.hr` (production backend).** This means agent code changes can be tested immediately without a full release cycle.

```bash
cd "C:\Dev\HM DIGITAL\MEDICAL_MVP\local-agent"
pnpm tauri dev
```

- Dev agent connects to `wss://app.hmdigital.hr` (same prod WebSocket endpoint)
- AKD smart card + VPN work exactly as in production
- Use this for all smartcard signing development — no need to bump version or wait for CI
- The installed released agent and the dev agent cannot run simultaneously (single-instance lock)

### Local Development (available but NOT used for testing)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
Exposes: backend :8000, frontend :3000, PostgreSQL :5433. No Caddy, hot reload enabled.

### Mandatory Testing Workflow — PROD ONLY

**All testing is done on prod (app.hmdigital.hr) via Chrome MCP + SSH. Do NOT test on localhost.**

Workflow for every code change:

1. **Commit and push** to `main` — triggers auto-deploy via GitHub Actions (~45s)
2. **Wait for deploy**: `gh run watch <run_id> --exit-status`
3. **E2E test on prod** via Chrome DevTools MCP:
   - Navigate to `https://app.hmdigital.hr`
   - Take snapshot: `take_snapshot`
   - Test the modified feature end-to-end
   - Check console for errors: `list_console_messages`
   - Verify network requests: `list_network_requests`
4. **Check server logs** via SSH if needed:
   ```bash
   ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose logs backend --tail 100"
   ```

### Production

**Live app:** https://app.hmdigital.hr/
**SSH access:** `ssh root@178.104.169.150` (key: `~/.ssh/id_ed25519`)
**Deploy path:** `/opt/medical-mvp`

```bash
# Check logs:
ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose logs backend --tail 100"
# Restart a service (does NOT re-read .env — use up -d for env changes):
ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose restart backend"
# To pick up .env changes, use up -d instead:
ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose up -d backend"
# Full deploy (also triggered automatically on push to main):
ssh root@178.104.169.150 "cd /opt/medical-mvp && bash deploy.sh"
```

Caddy handles SSL automatically via Let's Encrypt. Only ports 80/443 exposed.

### Domain & DNS
- **App domain:** `app.hmdigital.hr` (Medical MVP app — live in production)
- **Company website:** `hmdigital.hr` (separate, NOT on Hetzner)
- **DNS:** `app.hmdigital.hr` → `178.104.169.150` (Hetzner Nuremberg)
- **SSL:** Caddy auto-provisions via Let's Encrypt for `app.hmdigital.hr`
- **Application ID (Tauri):** `hr.hmdigital.medical`

### Hosting
Hetzner Cloud CPX22 (2 vCPU / 4 GB / 80 GB, Nuremberg). Handles first 20-30 clinics. PostgreSQL tuned: 128 MB shared_buffers, 30 max_connections.

### CI/CD
Push to `main` triggers two workflows:
1. **`.github/workflows/deploy.yml`** — SSH into server → runs `deploy.sh` (pull, build, up, migrate, prune). Runs on every push to main.
2. **`.github/workflows/release-agent.yml`** — Builds Windows NSIS installer + publishes GitHub Release. Only runs when agent version is bumped.

Required GitHub secrets: `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`, `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

## Sales / market context

Out of scope for programming work. Pricing, onboarding fees, lead list, go-to-market, competitive analysis: see `klijenti/CLAUDE.md` and `docs/competitors.md` / `docs/go-to-market.md`.

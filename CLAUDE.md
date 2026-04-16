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

**Every CEZIH action MUST work with EITHER signing method. No fallbacks. No "preferred" method. A user with only a smart card can do everything. A user with only Certilia mobile can do everything.**

| Method | How | What's Needed |
|--------|-----|---------------|
| **AKD Smart Card** | Local Agent reads card → JWS signature → VPN + mTLS + signing | AKD kartica + USB čitač + VPN klijent + Local Agent |
| **Certilia Mobile/Cloud** | Remote signing via certpubws.cezih.hr → push notification to phone | Certilia račun + mobitel (no card, no VPN, no local agent) |

```
Browser ←→ Cloud Backend (FastAPI) ←→ CEZIH
                REST API
                    ↕
            ┌───────┴────────┐
            │                │
    Local Agent (Tauri)   Certilia Remote Signing
    AKD smart card        certpubws.cezih.hr
    VPN + mTLS + JWS      OAuth2 + push approval
```

**Per-user preference:** Each user chooses their signing method in Postavke → Korisnici (`cezih_signing_method`: `smartcard` or `extsigner`). System default configurable via `CEZIH_SIGNING_METHOD` env var.

**⚠️ HARD RULE:** Never treat one method as a fallback for the other. Both must be independently tested and verified for ALL 22 test cases. If one method breaks, it's a P0 bug — not a "use the other method" situation.

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
| Phase 15 | DONE | CEZIH exam prep — TC19/20/22 fixes (agent binary transport, PUT method, relatesTo format) (2026-04-13) |
| Phase 16 | DONE | CEZIH live verification — TC19 + TC22 verified; TC20 + TC11 investigated (2026-04-13) |
| Phase 17 | DONE | TC20 cancel document — VERIFIED via ITI-65 replace with OID lookup (2026-04-13) |
| Phase 18 | DONE | E2E production test — all 16 TCs verified on app.hmdigital.hr against real CEZIH (2026-04-13) |
| Phase 19 | DONE | TC11 PMIR foreigner registration — VERIFIED (Patient/1348216, 4 stacked fixes) (2026-04-13) |

### Key CEZIH Technical Findings (from live testing)

**Signing (two-tier):**
- Encounters only check signature presence — ES384 smart card OK
- PMIR cryptographically verifies — must use extsigner (Certilia RS256), mTLS only (no Bearer token)

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

**Agent (v0.9.0):**
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
- **17/22 TCs VERIFIED** against real CEZIH (TC3-6, TC9-22). TC1/2/4 exercised implicitly. TC7/8 return empty (test data limitation).
- **Next step:** On-site exam at HZZO Zagreb (2026-04-16) — exam-ready

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
# Restart a service:
ssh root@178.104.169.150 "cd /opt/medical-mvp && docker compose restart backend"
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

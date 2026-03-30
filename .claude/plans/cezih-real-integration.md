# CEZIH Real Integration Plan

**Created:** 2026-03-27
**Updated:** 2026-03-27
**Status:** Phase 1 + 1.5 DONE — Phase 2+ blocked on VPN

## Current State
- Phase 1 (infrastructure) and Phase 1.5 (remote signing) are COMPLETE (56 tests pass)
- Mock/real dispatcher in place — `CEZIH_MODE=mock` default, transparent switching
- Real service stubs ready for ITI-78, ITI-65, ITI-67 — need VPN to test
- Remote signing service ready (`cezih_signing.py`) — need VPN for certws2 endpoint
- Certilia account activated — cloud signing cert active (valid until 26.03.2028)
- VPN blocked — waiting for physical AKD test card
- Remote signing endpoint (`certpubws.cezih.hr`) reachable WITHOUT VPN

## Credentials
- Client ID: `d9fe4a5d-4ca2-4e21-8ad3-0016d78ce02f`
- Client Secret: `jqx3xvCgLmiHknraNseDfJ885nexsYJ9`
- Test Patient: OIB `99999900187`, MBO `999990260`, GORAN PACPRIVATNICI19
- VPN: `pvsek.cezih.hr` (needs card)
- OAuth2: `certsso2.cezih.hr` (needs VPN)
- FHIR API: `certws2.cezih.hr:8443/9443` (needs VPN)
- Remote signing: `certpubws.cezih.hr` (public, NO VPN)

## FHIR Documentation
- Core guide: https://simplifier.net/guide/cezih-osnova
- Clinical documents: https://simplifier.net/guide/klinicki-dokumenti
- Visits: https://simplifier.net/guide/upravljanje-posjetama
- Cases: https://simplifier.net/guide/upravljanje-slucajevima
- CUS connection spec: http://www.cezih.hr/cus/CEZIH-CUS_SpecifikacijaPovezivanja_B.docx

---

## Phase 0: VPN + Card Setup [BLOCKED — waiting for AKD card]
- [ ] Receive AKD test smart card
- [ ] Buy USB card reader (ordered Renkforce RF-SCR-100)
- [ ] Connect to VPN (`pvsek.cezih.hr`) with card cert
- [ ] Tell HZZO OIB + card number to add permissions
- [ ] Test OAuth2 token acquisition from `certsso2.cezih.hr`

## Phase 1: Backend Infrastructure [DONE — 2026-03-27]

### 1.1 Configuration
- [x] CEZIH settings in `backend/app/config.py`: CEZIH_MODE, CEZIH_OAUTH2_URL, CEZIH_CLIENT_ID, CEZIH_CLIENT_SECRET, CEZIH_FHIR_BASE_URL, CEZIH_SIGNING_URL, CEZIH_SIGNING_OAUTH2_URL, CEZIH_TIMEOUT, CEZIH_RETRY_ATTEMPTS
- [x] Env vars in `backend/.env` (commented out, CEZIH_MODE=mock active)

### 1.2 OAuth2 Token Manager
- [x] `backend/app/services/cezih/oauth.py`: client_credentials grant, token caching with 30s TTL buffer, asyncio.Lock thread safety, Pydantic OAuth2TokenResponse model

### 1.3 HTTP Client
- [x] `backend/app/services/cezih/client.py`: CezihFhirClient class, Bearer token injection, retry on 401 (token refresh) + 5xx (exponential backoff), request/response logging with duration, FHIR content types, gateway prefix

### 1.4 Error Handling
- [x] `backend/app/services/cezih/exceptions.py`: CezihAuthError, CezihConnectionError, CezihFhirError (with status_code + operation_outcome), CezihSigningError, CezihTimeoutError

### 1.5 FHIR Resource Models
- [x] `backend/app/services/cezih/models.py`: FHIRPatient, FHIREncounter, FHIRDocumentReference, FHIRBundle, OperationOutcome (with smart error extraction), OAuth2TokenResponse, Croatian identifiers (MBO/OIB system URLs in service.py)

### 1.6 Dispatcher (Mock/Real Router)
- [x] `backend/app/services/cezih/dispatcher.py`: Routes by CEZIH_MODE, same interface, audit logging to AuditLog table, CezihError → HTTP 502 translation

### 1.7 Real CEZIH Service
- [x] `backend/app/services/cezih/service.py`: Patient lookup (ITI-78), clinical document submit (ITI-65), document search (ITI-67), e-Recept stub (no FHIR endpoint known yet)

### 1.8 Wire It Up
- [x] `backend/app/api/cezih.py` uses dispatcher (`from app.services.cezih import dispatcher as cezih`)
- [x] `backend/app/main.py` lifespan creates/closes httpx.AsyncClient
- [x] `httpx>=0.27.0` in `backend/pyproject.toml`
- [x] 56 tests pass with dispatcher in mock mode

### Files created
| File | Purpose |
|------|---------|
| `backend/app/services/cezih/__init__.py` | Package init |
| `backend/app/services/cezih/exceptions.py` | Custom exception hierarchy |
| `backend/app/services/cezih/models.py` | FHIR + OAuth2 Pydantic models |
| `backend/app/services/cezih/oauth.py` | OAuth2 token manager with caching |
| `backend/app/services/cezih/client.py` | CezihFhirClient HTTP wrapper |
| `backend/app/services/cezih/service.py` | Real CEZIH service (ITI-78, ITI-65, ITI-67) |
| `backend/app/services/cezih/dispatcher.py` | Mock/real router + audit logging |
| `backend/tests/cezih/` | 56 unit tests (models, oauth, client, service, dispatcher) |

## Phase 1.5: Remote Signing [DONE — 2026-03-27]

- [x] `backend/app/services/cezih_signing.py`: Client for certpubws.cezih.hr extsigner API
- [x] Separate OAuth2 token cache (certpubsso.cezih.hr, no VPN needed for auth)
- [x] SHA-256 hash computation + base64 encoding
- [x] Redirect detection (public endpoint → login page, with helpful error)
- [x] Health check endpoint for signing service
- [x] Dispatcher integration (sign_document, signing_health_check)
- [x] Architecture documented in code: public endpoint needs browser auth, VPN endpoint (certws2) accepts Bearer tokens
- Note: Signature response format TBD — needs tuning after first real API test

## Phase 2: Patient Lookup [NEEDS VPN]
- [ ] Implement PDQm ITI-78 query
- [ ] Query by MBO: `?identifier=<mbo_system>|999990260`
- [ ] Parse FHIR Patient response with Croatian extensions
- [ ] Map to existing `InsuranceCheckResponse` schema
- [ ] Test with test patient GORAN PACPRIVATNICI19

## Phase 3: Clinical Documents [NEEDS VPN]
- [ ] Implement ITI-65 (submit document bundle)
- [ ] Implement ITI-67 (search documents)
- [ ] Implement ITI-68 (retrieve document)
- [ ] Document replace + cancel (HR::ITI-65 variants)
- [ ] Sign documents via Phase 1.5 signing service before submit

## Phase 4: Visits & Cases [NEEDS VPN]
- [ ] FHIR messaging for visit CRUD (create/update/close Encounter)
- [ ] FHIR messaging for case CRUD (create/update EpisodeOfCare)
- [ ] QEDm for retrieving existing cases

## Phase 5: Terminology & Registry [NEEDS VPN]
- [ ] ITI-96 code list sync (SVCM)
- [ ] ITI-95 concept set sync (SVCM)
- [ ] ITI-90 subject registry (mCSD) — orgs, practitioners
- [ ] OID registry lookup (HTTP POST)
- [ ] PMIR foreigner registration

## Phase 6: Notifications [NEEDS VPN]
- [ ] Pull-based notification polling
- [ ] WebSocket push to frontend for real-time CEZIH events

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/config.py` | App settings (CEZIH config added) |
| `backend/app/api/cezih.py` | CEZIH API routes (uses dispatcher) |
| `backend/app/services/cezih/dispatcher.py` | Mock/real router + audit logging |
| `backend/app/services/cezih/oauth.py` | OAuth2 token manager with caching |
| `backend/app/services/cezih/client.py` | CezihFhirClient HTTP wrapper |
| `backend/app/services/cezih/service.py` | Real CEZIH service (ITI-78, ITI-65, ITI-67) |
| `backend/app/services/cezih/models.py` | FHIR + OAuth2 Pydantic models |
| `backend/app/services/cezih/exceptions.py` | Custom exception hierarchy |
| `backend/app/services/cezih_signing.py` | Remote signing service |
| `backend/app/services/cezih_mock_service.py` | Mock service (still used in mock mode) |
| `backend/app/schemas/cezih.py` | API response schemas |
| `backend/app/models/cezih_euputnica.py` | e-Uputnica DB model |
| `backend/app/main.py` | App lifespan (httpx client init/cleanup) |
| `backend/tests/cezih/` | 56 unit tests |
| `docs/cezih-technical.md` | Full technical reference (updated 2026-03-27) |
| `docs/roadmap.md` | Master status tracker |

## Open Questions
- FHIR query format for Patient lookup by MBO — exact identifier system URL?
- Remote signing API payload format — what JSON/XML does extsigner expect?
- Can dispatcher support hybrid mode (real signing + mock FHIR)?
- e-Recept: No dedicated FHIR endpoint found — uses $process-message?
- Which test environment operations are functional vs stubbed?

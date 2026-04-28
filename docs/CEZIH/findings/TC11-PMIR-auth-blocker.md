---
date: 2026-04-13
topic: session | signing | references | response-parsing
status: resolved
---

# TC11 PMIR ITI-93 — RESOLVED (2026-04-13)

**Result:** Patient/1348216 created in CEZIH (201 Created). 17/22 TCs now verified.

## Four Root Causes Found and Fixed

TC11 had **four stacked issues** that masked each other — each fix revealed the next.

---

### Issue 1: Session Establishment (415 ERR_EHE_1099 from Keycloak)

**Symptom:** All requests returned 415 with `"path":"/auth/realms/CEZIH/..."`. The request never reached the FHIR service.

**Root cause:** POST requests as the first gateway request couldn't establish the mTLS session cookie.

The agent has `CURLOPT_POSTREDIR=redirect_all` which maintains POST through 302 redirects. When the gateway redirects to Keycloak for auth, the POST body (`Content-Type: application/fhir+json`) is sent to Keycloak. Keycloak doesn't accept this and returns 415. The auth flow never completes, the session cookie is never set, and retries fail identically.

**Why other TCs worked:** They always ran after a GET request (e.g., TC10 patient lookup) which establishes the session cookie. GETs go through Keycloak cleanly (no body).

**Why warmup didn't help:** Warmup URL was `certws2:8443/metadata` — NOT behind the gateway auth. It only triggered the TLS handshake for smart card PIN caching.

**Fix (3 changes):**

| File | Change |
|------|--------|
| `backend/app/api/agent_ws.py` | Warmup URL changed from `/metadata` to `gateway/patient-registry-services/api/v1/Patient?_count=0` — triggers full Keycloak auth flow on agent connect |
| `backend/app/services/cezih/service.py` | Pre-flight GET before PMIR POST — safety net if warmup missed or session expired |
| `local-agent/src-tauri/src/websocket.rs` | When POST fails with Keycloak redirect, agent does GET warmup first, then retries POST (was: retry POST immediately → same failure) |

**How to diagnose in future:** Check the error response `"path"` field. If it points to `/auth/realms/CEZIH/...`, the request hit Keycloak, not the FHIR service. Add a pre-flight GET before any POST to establish the session.

---

### Issue 2: Digital Signature Format (400 ERR_DS_1002)

**Symptom:** After session fix, CEZIH returned `ERR_DS_1002` (Document Structure error) with `code: "business-rule"`.

**Root cause:** Smart card signing produces ES384 (ECDSA P-384) signatures. CEZIH's PMIR service **cryptographically verifies** signatures and expects RS256 (RSA) format produced by the extsigner (Certilia).

**Key discovery:** Encounters DON'T verify signatures — they only check for presence. Quote from `docs/CEZIH/Posjete/IMPLEMENTACIJA.md`:

> ERR_ENCOUNTER_2011 | signature is NOT verified on $process-message

So smart card ES384 works for encounters (just needs to exist) but fails for PMIR (actually verified).

**What ERR_DS_1002 means:**
- `DS` = Document Structure (NOT Digital Signature — those use `ERR_SEC_*` prefix)
- `code: "business-rule"` = structurally valid FHIR but fails a business logic check
- In this context: the signature is present but verification fails
- For encounters, this error was about missing Encounter.type slices, NOT signing

**How we confirmed this:**
1. Single base64 (JWS compact directly in `signature.data`) → HAPI-1821 "Invalid attribute value" — proves double-base64 IS correct for `base64Binary`
2. All bundle structure variations (with/without profiles, with/without birthDate, alpha-2/alpha-3 country) → same ERR_DS_1002 — proves it's NOT about the bundle content
3. Switching to extsigner → ERR_DS_1002 disappeared, got a different error — proves it WAS about the signing method

**Fix:**

| File | Change |
|------|--------|
| `backend/app/services/cezih_signing.py` | Restored extsigner to working state: removed Bearer token (causes 401), use `CEZIH_FHIR_BASE_URL` (certws2:8443 via agent mTLS) |
| Server `.env` | `CEZIH_SIGNING_METHOD=extsigner` (was: `smartcard`) |

**Extsigner auth lesson:** Extsigner authenticates via mTLS session cookie (same as all 8443 services). Adding a Bearer token broke it — the token from certsso2 realm was rejected. The working state (April 10) used NO Authorization header.

**How to diagnose in future:** If `ERR_DS_1002` persists after confirming bundle structure matches the official example, the issue is the **signing method**, not the bundle. Switch to extsigner. If extsigner returns 401, check that NO Bearer/Authorization header is being sent — it uses mTLS only.

> **Update 2026-04-28** — CEZIH reversed the extsigner auth requirement on/around 2026-04-23. `Authorization: Bearer <token>` from `certpubsso.cezih.hr` is now **required** on both `extsigner/api/sign` (POST) and `getSignedDocuments` (GET). The "no Bearer / mTLS only" guidance above was correct on 2026-04-13 and went stale on 2026-04-23. See `2026-04-28-extsigner-bearer-token-required.md`.

---

### Issue 3: Reference Resolution (Reference_REF_CantResolve)

**Symptom:** After signing fix, CEZIH returned `"Unable to resolve resource with reference 'Bundle/{uuid}'"` at `MessageHeader.focus[0]`.

**Root cause:** Outer entry `fullUrl` values were plain UUIDs (e.g., `6b11eccf-95b3-...`). The official Simplifier example uses plain UUIDs, but CEZIH's HAPI server resolves them as literal references (`Bundle/{uuid}`) instead of matching by `fullUrl`.

Working encounters use `urn:uuid:` prefix for ALL fullUrls and references.

**Fix:**

| File | Change |
|------|--------|
| `backend/app/services/cezih/service.py` | Changed outer entry fullUrls and focus reference from plain UUID to `urn:uuid:{uuid}` format |

**Rule:** Always use `urn:uuid:` prefix for all fullUrls and references in CEZIH message bundles, even though the official Simplifier example uses plain UUIDs. Match the pattern used by working encounters.

---

### Issue 4: Missing Response Data (empty MBO)

**Symptom:** PMIR returned 200 OK but the frontend showed empty MBO.

**Root cause:** Foreigners don't get MBO (Matični Broj Osiguranika — insured person number). CEZIH assigns them a `jedinstveni-identifikator-pacijenta` (unique patient identifier) instead.

**Fix:**

| File | Change |
|------|--------|
| `backend/app/services/cezih/service.py` | Added `_extract_cezih_patient_identifier()` — extracts `jedinstveni-identifikator-pacijenta` from response. Falls back to this when MBO is empty. |

---

## Final Working Configuration

**Endpoint:** `POST patient-registry-services/api/iti93`

**Signing:** Extsigner (Certilia remote signing, RS256) — NOT smart card (ES384)
- Server `.env`: `CEZIH_SIGNING_METHOD=extsigner`, `CEZIH_SIGNER_OIB=<doctor-oib>`
- User must approve on Certilia phone app (15-25 second delay)

**Bundle structure (what CEZIH accepts):**
```json
{
  "resourceType": "Bundle",
  "id": "<uuid>",
  "meta": {"profile": ["...HRRegisterPatient"]},
  "type": "message",
  "timestamp": "<iso-datetime>",
  "entry": [
    {
      "fullUrl": "urn:uuid:<uuid-1>",
      "resource": {
        "resourceType": "MessageHeader",
        "eventUri": "urn:ihe:iti:pmir:2019:patient-feed",
        "destination": [{"endpoint": "http://cezih.hr/pmir"}],
        "sender": {"type": "Organization", "identifier": {...}},
        "author": {"type": "Practitioner", "identifier": {...}},
        "source": {"endpoint": "urn:oid:<source-oid>"},
        "focus": [{"reference": "urn:uuid:<uuid-2>"}]
      }
    },
    {
      "fullUrl": "urn:uuid:<uuid-2>",
      "resource": {
        "resourceType": "Bundle",
        "type": "history",
        "entry": [{
          "fullUrl": "urn:uuid:<uuid-3>",
          "resource": {
            "resourceType": "Patient",
            "identifier": [{"system": "...putovnica", "value": "<passport>"}],
            "active": true,
            "name": [{"use": "official", "family": "<name>", "given": ["<name>"]}],
            "address": [{"country": "<ISO-3166-1-alpha-3>"}]
          },
          "request": {"method": "POST", "url": "Patient"},
          "response": {"status": "201"}
        }]
      }
    }
  ],
  "signature": {
    "type": [{"system": "urn:iso-astm:E1762-95:2013", "code": "1.2.840.10065.1.12.1.1"}],
    "when": "<iso-datetime>",
    "who": {"type": "Practitioner", "identifier": {...}},
    "data": "<double-base64-jws>"
  }
}
```

**Key differences from official Simplifier example:**
- `urn:uuid:` prefix on ALL fullUrls (example uses plain UUIDs — doesn't work)
- NO `meta.profile` on MessageHeader or inner Bundle (example has them — they're optional)
- Signature from extsigner (RS256), NOT smart card (ES384)
- Country code must be ISO 3166-1 alpha-3 (DEU, not DE)

**CEZIH response (200 OK):**
```json
{
  "resourceType": "Bundle",
  "type": "message",
  "entry": [
    {"resource": {"resourceType": "MessageHeader", "response": {"identifier": "1348217", "code": "ok"}, "focus": [{"reference": "Patient/1348216"}]}},
    {"resource": {"resourceType": "Patient", "id": "1348216", "identifier": [
      {"system": "...putovnica", "value": "AY9876543"},
      {"system": "...jedinstveni-identifikator-pacijenta", "value": "cmnx8onhd017chb85rkpgyban"}
    ]}}
  ]
}
```

---

## Lessons for Future CEZIH Integration

1. **415 from Keycloak ≠ FHIR error.** Check the `"path"` field — if it's `/auth/realms/...`, the request never reached the FHIR service. Fix: pre-flight GET to establish session.

2. **ERR_DS_1002 = Document Structure** (not Digital Signature). But in practice, it fires for BOTH bundle structure issues (encounters: missing type slices) AND signature verification failures (PMIR: wrong algorithm). The `code` field distinguishes: `"invalid"` = format wrong, `"business-rule"` = format OK but content/signature rejected.

3. **Encounters don't verify signatures; PMIR does.** Smart card ES384 works for encounters (presence check only) but fails for PMIR (cryptographic verification). Use extsigner for anything that requires real signature verification.

4. **Extsigner needs NO Bearer token.** Auth is mTLS via agent session cookie. Adding any Authorization header causes 401.

   > **Update 2026-04-28** — Lesson #4 inverted: extsigner now requires Bearer. Inline code comments asserting current vendor behavior should carry a verified-against date.

5. **Always use `urn:uuid:` in CEZIH bundles.** Even if official examples use plain UUIDs. HAPI resolves plain UUIDs as literal references.

6. **Official Simplifier examples are starting points, not gospel.** The PMIR example had plain UUIDs (doesn't work), IHE profile URLs (unnecessary), and was missing the signature format context. Always verify against actual CEZIH behavior.

7. **Stacked errors mask each other.** TC11 had 4 issues. Each fix only revealed the next. Don't conclude "it's an HZZO issue" until you've gotten past the gateway (session), past signing (extsigner), and gotten a proper FHIR OperationOutcome with diagnostics text.

---

## Files Changed (this session)

| File | Changes |
|------|---------|
| `backend/app/api/agent_ws.py` | Warmup URL → gateway path |
| `backend/app/services/cezih/service.py` | Pre-flight GET, `urn:uuid:` refs, alpha-3 country, response parser |
| `backend/app/services/cezih/message_builder.py` | Signing payload experiments (reverted to original) |
| `backend/app/services/cezih_signing.py` | Extsigner auth restored (no Bearer token) |
| `local-agent/src-tauri/src/websocket.rs` | GET warmup before POST retry |
| Server `.env` | `CEZIH_SIGNING_METHOD=extsigner` |

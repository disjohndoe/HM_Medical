# CEZIH Errors & Debugging

## ERR_DS_1002 — Digital Signature Verification Failed

**Meaning:** CEZIH's FHIR validator rejected the Bundle's digital signature.

**Error response:**
```json
{
  "resourceType": "Bundle",
  "type": "message",
  "entry": [{
    "resource": {
      "resourceType": "OperationOutcome",
      "issue": [{
        "severity": "error",
        "code": "business-rule",
        "details": {"coding": [{"system": "http://ent.hr/fhir/CodeSystem/message-error-type", "code": "ERR_DS_1002"}]}
      }]
    }
  }]
}
```

### Root Causes — ALL RESOLVED (2026-04-16)

1. **POST session issue (FIXED 2026-04-08):** libcurl converts POST→GET on 302 redirect. Fix: `CURLOPT_POSTREDIR` in websocket.rs. Empty body arrived at `$process-message`, CEZIH saw no signature.

2. **Wrong canonicalization (FIXED 2026-04-16):** Backend used `json.dumps(separators=(",",":"))` (compact JSON, insertion-order keys). CEZIH verifier reconstructs Bundle via RFC 8785 JCS (sorted keys) → hash mismatch. Fix: `jcs.canonicalize(bundle)` in `message_builder.py:521`.

3. **Wrong JWS format (FIXED 2026-04-16):** Sent attached JWS (`header.payload.sig`) with top-level `x5c`, no `jwk`. CEZIH expects **detached JWS** (`header..sig`) with full EC `jwk` in header (nested `x5c`, coords `x`/`y`, `x5t#S256`, `nbf`, `exp`). Fix: agent v0.13.0 — `signing.rs` CNG branch.

4. **Missing Encounter.type slices (FIXED 2026-04-09):** `VrstaPosjete` + `TipPosjete` slices were missing from Encounter; ERR_DS_1002 appeared before CEZIH reached signature verification.

### Debugging Checklist

1. [ ] VPN connected? (`pvsek.cezih.hr`)
2. [ ] mTLS session established? (GET clinical endpoint first if fresh session)
3. [ ] `jcs.canonicalize()` used (not `json.dumps`)? Check for "JCS canonical payload" in logs
4. [ ] `SMARTCARD JWS DECODED` log shows `payload_b64url=0 chars` (detached)?
5. [ ] `jwk_keys` includes `x5c`, `x`, `y`, `x5t#S256`, `nbf`, `exp`?
6. [ ] `x5c_count=0` at top level (x5c must be inside jwk)?
7. [ ] `sig_b64url=128 chars` (= 96 bytes ES384 P1363)?
8. [ ] `JWS: CNG SELF-VERIFICATION PASSED` in agent logs?
9. [ ] `signature.data=""` set before canonicalizing?
10. [ ] Encounter has both `VrstaPosjete` + `TipPosjete` type slices?

## HAPI-1821 — FHIR Validation Error

**Meaning:** HAPI FHIR server rejected the resource as invalid.

**Common causes:**
- Missing required fields
- Wrong CodeSystem URI (using standard HL7 instead of CEZIH-specific)
- Wrong identifier system
- Dots in base64Binary value

**Debugging:** Check `OperationOutcome.details.coding[0].code` from response.

## POST Session Issue (FIXED 2026-04-08)

**Symptom:** GET requests work fine, POST returns unexpected error or empty response.

**Cause:** certws2:8443 → 302 redirect to Keycloak → libcurl converts POST→GET (RFC 7231 default).

**Fix:** `websocket.rs`:
```rust
easy.post_redirections(PostRedirections::new().redirect_all(true))
```

**Additional fixes:**
- Retry logic for HTML/empty POST responses
- Warmup URL targeting encounter service
- Skip Authorization header for port 8443 (mTLS handles auth)

## 401 Unauthorized

- Token expired or invalid
- Client.py invalidates token and retries
- Check if correct auth tier used (service account vs mTLS)

## 403 Forbidden

- Service account token used for clinical endpoint (port 8443) — needs mTLS session
- Signing endpoint (`certpubws.cezih.hr/extsigner/api/sign`) — needs user-level auth

## Common HTTP Status Codes

| Status | Meaning | Action |
|--------|---------|--------|
| 200 | Success | — |
| 302 | Redirect to Keycloak | Auth flow in progress (handled by agent) |
| 400 | Invalid request | Check FHIR validation (OperationOutcome) |
| 401 | Token expired | Auto-retry with fresh token |
| 403 | Wrong auth tier | Use mTLS for port 8443 |
| 500 | Server error | CEZIH side — rare, retry |

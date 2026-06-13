# CEZIH Pitfalls — What NOT to Do

These are hard-won lessons from debugging sessions. Breaking these rules wastes time.

## Dual Signing

- **DO NOT treat one signing method as fallback for the other.** Both smart card AND Certilia mobile must work independently for ALL CEZIH actions. If one breaks, it's P0.
- **DO NOT assume a user has both methods configured.** Per-user preference means a user may only have smart card OR only have Certilia. Both paths must work standalone.
- **DO NOT skip testing with both methods.** Every CEZIH action must be verified with both `smartcard` and `extsigner`.

## VPN & URLs

- **DO NOT use `pvpri.cezih.hr` for testing** — that is PRODUCTION. Use `pvsek.cezih.hr`.
- **DO NOT forget the `/auth/` prefix** in Keycloak URL: `certsso2.cezih.hr/auth/realms/CEZIH/...`
- **DO NOT forget the gateway prefix** `/services-router/gateway/` in client.py URLs

## CodeSystems & FHIR

- **DO NOT use standard HL7 ActCode** for Encounter.class. CEZIH uses `nacin-prijema` CodeSystem.
- **DO NOT use literal URLs** in FHIR references. Use identifier-based logical references.
- **DO NOT use LOINC codes** for document types. CEZIH uses `HRTipDokumenta` numeric codes (privatnici: 011-013, HZZO-contracted: 001-010).
- **DO NOT use `/v1/`** for mCSD endpoints (Organization, Practitioner search).

## Authentication

- **DO NOT use service account token** for clinical endpoints (port 8443). It only works for port 9443.
- **DO NOT send Authorization header** to port 8443 when using mTLS. SChannel handles auth via client cert.

## Digital Signature

- **DO NOT sign pretty-printed JSON.** Use `jcs.canonicalize(bundle)` (RFC 8785, sorted keys). `json.dumps` is compact but NOT JCS — key order differs and CEZIH verifier rejects it.
- **DO NOT use dots in signature.data.** HAPI rejects them (HAPI-1821). Always double base64: `base64(JWS_compact)`.
- **DO NOT include signature.data in the signing input.** Set `signature.data = ""` before canonicalizing.
- **DO NOT send attached JWS** (header.payload.sig). CEZIH expects **detached JWS**: `header..sig` (empty middle). Signing input still uses attached form for the hash — only the on-wire format is detached.
- **DO NOT put x5c at JOSE header top level.** x5c must be **nested inside jwk**. Top-level x5c = signature format rejected.
- **DO NOT omit jwk from JOSE header for EC keys.** CEZIH requires full jwk: `{kty, crv, x, y, kid, use, nbf, exp, x5t#S256, x5c}`.
- **DO NOT use NCrypt P1363 flag with AKD card.** `NCRYPT_ECDSA_P1363_FORMAT_FLAG` returns `0x80090009`. Pass `flags=0` — AKD card returns P1363 natively.
- **DO NOT use IdentificationTest cert for signing** if SignatureTest is available. IdentificationTest has ECDH key usage (wrong purpose). Use SignatureTest (Non-Repudiation).
- **DO NOT assume the signing endpoint** (`certpubws.cezih.hr`) works with service account tokens. It returns 403. Use Bearer from `certpubsso.cezih.hr`.
- **DO NOT forget `CURLOPT_POSTREDIR`** in libcurl. Without it, POST→GET on 302 redirect, losing request body.

## Agent & Deployment

- **DO NOT forget to restart agent after building.** No hot reload — kill and restart the .exe.
- **DO NOT assume server deploys automatically** — it does (push to main triggers CI/CD), but verify.
- **DO NOT commit CEZIH credentials** to git. Client ID/secret stay in `.env` only.
- **DO NOT ignore VPN idle timeout** (~30 min). Implement keepalive or session drops silently.

## Testing

- **DO NOT skip E2E testing.** Hot reload misses schema/type changes. Always rebuild frontend + test in browser.
- **DO NOT test against production VPN** (`pvpri.cezih.hr`). Always use test (`pvsek.cezih.hr`).

## Certificate Management

- **DO NOT pull the smart card** during active operations. It terminates the VPN session.
- **DO NOT forget PIN lockout** — 3 failed attempts locks the card. Need PUK to reset.
- **DO NOT assume Certilia can't do something.** Both smart card AND Certilia mobile/cloud work for ALL CEZIH actions independently.

## Document Operations

- **DO NOT use `relatesTo` (appends/replaces) for doctor-facing document edits.** Using `appends` leaves the NEW doc `superseded` on CEZIH. Using `replaces` sets the OLD doc `superseded` which then PERMANENTLY deadlocks visit storno (visit-cancel demands all docs `entered-in-error` but `superseded` docs refuse cancellation with ERR_DOM_10035). Doctor edit = submit-new (NO relatesTo, status=current) + cancel-old (entered-in-error).
- **DO NOT cancel a doc using a stored OID.** Always resolve live document state from CEZIH (ITI-67) first. Stored OIDs may point to superseded docs, and canceling a superseded doc returns ERR_DOM_10035. Live resolution: already-EIE = idempotent no-op, current = cancel, superseded = resolve current head first.
- **DO NOT check local mirror for visit storno blockers.** CEZIH may have documents not in our DB (orphan docs from failed syncs or replaced docs). Visit storno cascade must ask CEZIH directly which `status=current` docs exist on the encounter via `list_active_documents_on_encounter()`.
- **DO NOT use HRTipDokumenta codes 001-010 for privatnici.** Those are for HZZO-contracted providers. Privatnici use 011-013 only. Using wrong codes causes doc-type vs djelatnost mismatch rejection.
- **DO NOT put plain text/PDF in ITI-65 Binary.** Binary must hold a signed `Bundle.type=document` (HRDocument profile, 9 entries) since Phase 21. Plain text was the reason for provjera spremnosti rejection #1 (2026-05-04).

## Common Debugging Traps

- **ERR_DS_1002 does NOT mean the crypto is wrong.** Self-verification passes. Usually it's a format or session issue.
- **HAPI-1821 does NOT mean the signature is invalid.** It means dots in base64Binary. Double-base64 fixes it.
- **Empty POST response does NOT mean the endpoint is down.** It usually means the auth redirect lost the POST body.
- **403 on clinical endpoint does NOT mean permissions are misconfigured.** It usually means wrong auth tier (service account vs mTLS).

---
date: 2026-04-16
topic: signing
status: resolved
supersedes: cezih-official-signature-format.md
---

# Smart-card JWS Format — Root Cause and Fix

## Discovery

Smart-card (AKD) signing path returned ERR_DS_1002 (business-rule) despite correct
cryptographic signing. Root cause was two combined format mismatches vs what CEZIH
verifier expects (as observed from working extsigner/Certilia JWS).

## Root Causes

### 1. Canonicalization — JCS required, not compact JSON

Backend was using `json.dumps(ensure_ascii=False, separators=(",",":"))` (compact
JSON, keys in insertion order). CEZIH verifier reconstructs the Bundle on its side
using RFC 8785 JCS (recursively sorted keys) before verifying the signature.
Hash mismatch → ERR_DS_1002.

**Fix:** `backend/app/services/cezih/message_builder.py:521`
— switched to `jcs.canonicalize(bundle)` (RFC 8785).

### 2. JWS format — detached + jwk with nested x5c, not attached + top-level x5c

Our header was `{"alg":"ES384","kid":"...","x5c":[...]}` — no jwk, x5c at top level,
attached JWS (full Bundle in payload segment).

CEZIH extsigner (Certilia) format that CEZIH accepts:
- `alg=ES384`
- Full `jwk` in JOSE header: `{kty, x5t#S256, nbf, use, crv, kid, x5c, x, y, exp}`
  — EC P-384 coords (x/y), SHA-256 fingerprint, cert validity timestamps
  — x5c chain INSIDE jwk, NOT at JOSE header top level
- **Detached JWS**: empty middle segment — `header..sig`
- Signing input (RFC 7515): `base64url(header) + "." + base64url(JCS_bundle)` (unchanged)
- Signature: ES384 P1363 raw r||s (96 bytes), double base64 wrapped

**Fix:** `local-agent/src-tauri/src/signing.rs` CNG branch (sign_for_jws_inner)
— builds EC jwk from SubjectPublicKeyInfo.PublicKey (CRYPT_BIT_BLOB, 0x04||X||Y)
— emits `header..sig` instead of `header.payload.sig`

## Evidence

From `_cezih_logs.txt:223` (extsigner JWS accepted by CEZIH):
```
alg=ES384, jwk_keys=['kty','x5t#S256','nbf','use','crv','kid','x5c','x','y','exp']
x5c_count=0 (top level), payload_b64url=0 chars, sig_b64url=128 chars
```

After fix (2026-04-16 20:54:22):
```
SMARTCARD JWS DECODED: alg=ES384 jwk_keys=['kty','x5t#S256','nbf','use','crv','kid','x5c','x','y','exp']
x5c_count=0, payload_b64url=0 chars, sig_b64url=128 chars
POST /api/cezih/visits → 200
```

## Impact

Both signing paths now work independently for all CEZIH actions:
- Smart card (AKD) via local agent NCrypt — VERIFIED 2026-04-16
- Certilia remote (extsigner) — already verified

## Action Items

- ✅ Deployed in commits ecc88ed (backend) + 43393f7 (agent v0.13.0)
- Agent v0.13.0 release build triggered via CI (for clients not running dev mode)

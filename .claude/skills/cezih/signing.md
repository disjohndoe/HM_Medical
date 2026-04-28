# CEZIH Digital Signature

## DUAL SIGNING RULE

**Both signing methods work independently for ALL CEZIH actions.** Per-user preference
(`smartcard` or `extsigner`). No fallbacks. No "preferred" method. If one breaks, it's P0.

| Method | Flow | Requirements |
|--------|------|-------------|
| **Smart Card (AKD)** | JCS → agent → Windows CNG (NCryptSignHash, ES384) → detached JWS | AKD kartica + USB čitač + Local Agent running |
| **Certilia Mobile** | Bundle → extsigner API → push to phone → approve → CEZIH signs → returns signed Bundle | Certilia račun + mobitel |

**Both VERIFIED on production 2026-04-16.** See `docs/CEZIH/findings/smartcard-jws-format-fix.md`.

---

## Verified JWS Format (both methods produce this — CEZIH accepts it)

```
signature.data = base64( base64url(JOSE_header) + ".." + base64url(ES384_sig_96bytes) )
                         ─────────────────────────────────────────────────────────────
                         JWS compact, DETACHED (empty middle segment = no payload bytes)
```

**Key facts:**
- **Detached JWS** — middle segment is empty: `header..sig` (two dots)
- **Signing input** = `base64url(header) + "." + base64url(JCS_canonicalized_bundle)` — standard RFC 7515, uses attached form for the hash, but emits detached on the wire
- **Double base64** — outer `base64()` to remove dots for FHIR `base64Binary` (HAPI-1821)
- **`signature.data = ""`** must be set on the Bundle BEFORE canonicalizing; CEZIH strips it when verifying
- **ES384 / P-384** (96 bytes raw P1363 r||s) for AKD card; **RS256** fallback for CAPI-only cards

### JOSE Header — exact verified structure

Both smartcard and extsigner produce this structure (from `EXTSIGNER JWS DECODED` + `SMARTCARD JWS DECODED` logs 2026-04-16):

```json
{
  "alg": "ES384",
  "jwk": {
    "kty": "EC",
    "x5t#S256": "<base64url(SHA-256(leaf_DER))>",
    "nbf": 1234567890,
    "use": "sig",
    "crv": "P-384",
    "kid": "<SHA-1(leaf_DER) lowercase hex>",
    "x5c": ["<base64std(leaf_DER)>", "<base64std(intermediate_DER)>", "<base64std(root_DER)>"],
    "x": "<base64url(X_coord_48bytes)>",
    "y": "<base64url(Y_coord_48bytes)>",
    "exp": 1234567890
  },
  "kid": "<same SHA-1 thumbprint as jwk.kid>"
}
```

**Critical:** `x5c` is **INSIDE** `jwk`, not at JOSE header top level. No top-level `x5c`.

---

## Smart Card Path (AKD)

### Backend — `message_builder.py::_add_signature_smartcard`

1. Set `bundle["signature"]["data"] = ""`
2. `bundle_json_bytes = jcs.canonicalize(bundle)` — RFC 8785, sorted keys recursively
3. `data_b64 = base64.b64encode(bundle_json_bytes)` — send to agent
4. `result = await agent_manager.sign_jws(tenant_id, data_base64=data_b64)`
5. `bundle["signature"]["data"] = result["jws_base64"]` — inject returned double-base64 JWS

### Agent — `signing.rs::sign_for_jws_inner` (CNG path)

1. Open Windows `My` cert store, find signing cert (`OU=Signing` / `OU=SignatureTest` / `OU=Digital Signature`)
2. `CryptAcquireCertificatePrivateKey` → CNG (key_spec=0xFFFFFFFF) or CAPI fallback
3. Probe signature size: `NCryptSignHash(flags=0, null_hash)` → 96 = ES384
4. Extract EC public key coords from `SubjectPublicKeyInfo.PublicKey` CRYPT_BIT_BLOB:
   - blob = `0x04 || X(48 bytes) || Y(48 bytes)` = 97 bytes (or 98 with leading 0x00 from DER — both handled)
   - `x = b64url(blob[1:49])`, `y = b64url(blob[49:97])`
5. Build jwk with `kty, x5t#S256, nbf, use, crv, kid, x5c, x, y, exp`
   - `x5t#S256 = b64url(SHA-256(cert_der))`
   - `nbf/exp` from `CERT_INFO.NotBefore/NotAfter` (FILETIME → Unix epoch: `(hi<<32|lo - 116_444_736_000_000_000) / 10_000_000`)
   - `x5c` chain: `build_x5c_chain()` walks My→CA→Root stores, leaf-first, stops at self-signed root (max 4 hops)
6. JOSE header = `{"alg":"ES384","jwk":{...},"kid":"<thumb>"}`
7. `signing_input = b64url(header) + "." + b64url(bundle_json)` (attached form for hash)
8. `hash = SHA-384(signing_input.as_bytes())`
9. `NCryptSignHash(key, hash, flags=0)` → 96-byte P1363 (AKD card returns P1363 natively with flags=0)
   - If first byte is `0x30`: DER → P1363 conversion via `der_ecdsa_to_p1363()`
10. Self-verify: `CryptImportPublicKeyInfoEx2` + `BCryptVerifySignature` — logs PASSED/FAILED
11. **Detached JWS**: `jws_compact = format!("{}..{}", header_b64url, sig_b64url)` (empty middle)
12. Return `base64std(jws_compact)` — double base64

### CAPI fallback (RS256 — rare, for older non-CNG cards)

Same flow but `CryptCreateHash + CryptHashData + CryptSignHashA`, RS256, byte-reversed output (CAPI = little-endian, JWS needs big-endian). Emits bare `{"alg":"RS256","kid":"...","x5c":[...]}` header (no jwk, still detached).

---

## Certilia Mobile Path (extsigner)

### Flow

1. Backend `_add_signature_extsigner` sends **full Bundle** (compact JSON with `signature.data=""`) to CEZIH's extsigner API:

```
POST https://certws2.cezih.hr:8443/services-router/gateway/extsigner/api/sign
Auth: mTLS session (via agent) AND Authorization: Bearer <token> from certpubsso (since 2026-04-23 — both required)
Content-Type: application/json

{
  "oib": "15881939647",
  "sourceSystem": "HM_DIGITAL",
  "requestId": "<uuid>",
  "documents": [{
    "documentType": "FHIR_MESSAGE",
    "mimeType": "JSON",
    "base64Document": "<base64(bundle_json)>",
    "messageId": "<uuid>"
  }]
}
```

2. CEZIH pushes notification to Certilia mobile app
3. User approves on phone
4. Poll `getSignedDocuments` until ready (max ~30s, 5s interval)
5. Response contains `signedDocuments[0].base64Document` = signed Bundle with `signature.data` populated by CEZIH
6. Backend uses the returned signed Bundle directly (CEZIH signed it — no local signing)

### Extsigner Auth (current as of 2026-04-28)

- `certws2.cezih.hr:8443` endpoint requires **BOTH** mTLS session (via agent) **AND** `Authorization: Bearer <token>` from `certpubsso.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token` (OAuth2 client_credentials, `CEZIH_CLIENT_ID` + `CEZIH_CLIENT_SECRET`, env var `CEZIH_SIGNING_OAUTH2_URL`).
- Token TTL: 300s. Reuse across step 1 POST + step 2 GET poll within the same signing operation.
- Implementation: `_get_signing_token(client)` in `backend/app/services/cezih_signing.py`, called from `sign_bundle_via_extsigner` (commit `960cf3e`).
- **Historical note:** before 2026-04-23, mTLS-only worked and adding Bearer caused 401. CEZIH flipped this without notice. See `docs/CEZIH/findings/2026-04-28-extsigner-bearer-token-required.md`.
- `certpubws.cezih.hr:8443` was historically referenced as a "public, no VPN" alternative — confirmed unreachable from our test-env agent's network in 2026-04-28 EXP-1. Do not target without verifying TCP connectivity from the agent first.
- `ERROR_CODE_0025 code 31` = user cannot sign on mobile → Certilia mobile app not configured for that OIB.

### Extsigner Wire Format (confirmed from logs)

```
alg=ES384, kid="" (empty), header has jwk with nested x5c
payload=empty (detached), sig=128 chars b64url (96 bytes P1363)
header_b64url ~2399 chars (large due to x5c chain in jwk)
```

---

## Signature Element on Bundle

```json
"signature": {
  "type": [{"system": "urn:iso-astm:E1762-95:2013", "code": "1.2.840.10065.1.12.1.1"}],
  "when": "2026-04-16T17:42:32+02:00",
  "who": {"type": "Practitioner", "identifier": {"system": "...HZJZ-...", "value": "7659059"}},
  "data": "<double_base64_detached_JWS>"
}
```

StructureDefinition constraints (`hr-request-message`):
- `signature` 1..1 — REQUIRED
- `signature.data` 1..1 — REQUIRED
- `signature.onBehalfOf` max 0 — PROHIBITED
- `signature.targetFormat` max 0 — PROHIBITED
- `signature.sigFormat` max 0 — PROHIBITED
- DIGSIG-1: `MessageHeader.author == signature.who`

---

## Debug Logging

Set `CEZIH_SIGNING_DEBUG=true` on server. Emits:

```
SMARTCARD JWS DECODED: alg=ES384 kid=... jwk_keys=[...] x5c_count=0 payload_b64url=0 chars sig_b64url=128 chars
EXTSIGNER JWS DECODED: alg=ES384 kid=? jwk_keys=[...] x5c_count=0 payload_b64url=0 chars sig_b64url=128 chars
SMARTCARD JWS DUMP header_json_sorted={...}
SMARTCARD JWS DUMP payload_b64url_len=0
SMARTCARD JWS DUMP payload=<detached/empty>
SMARTCARD JWS DUMP sig_b64url=...
JWS: CNG SELF-VERIFICATION PASSED   ← or FAILED
JWS: EC coords extracted x=... y=...
```

**Validation checklist:**
- `payload_b64url=0 chars` → detached ✓
- `jwk_keys` includes `x5c`, `x`, `y`, `x5t#S256`, `nbf`, `exp` ✓
- `x5c_count=0` at top level ✓
- `sig_b64url=128 chars` → 96 bytes ES384 P1363 ✓
- `SELF-VERIFICATION PASSED` ✓

---

## Key Code Locations

| Component | File | Function | Line |
|-----------|------|----------|------|
| Signing method dispatch | `backend/app/services/cezih/message_builder.py` | `add_signature()` | ~348 |
| Smart card signing | `backend/app/services/cezih/message_builder.py` | `_add_signature_smartcard()` | ~477 |
| Extsigner signing | `backend/app/services/cezih/message_builder.py` | `_add_signature_extsigner()` | ~377 |
| Debug JWS dump | `backend/app/services/cezih/message_builder.py` | `_debug_dump_jws()` | ~269 |
| Extsigner API client | `backend/app/services/cezih_signing.py` | `sign_bundle_via_extsigner()` | — |
| Windows CNG signing | `local-agent/src-tauri/src/signing.rs` | `sign_for_jws_inner()` | ~129 |
| EC coord extraction | `local-agent/src-tauri/src/signing.rs` | inside `sign_for_jws_inner` CNG branch | ~250 |
| x5c chain builder | `local-agent/src-tauri/src/signing.rs` | `build_x5c_chain()` | ~77 |
| Cert selector | `local-agent/src-tauri/src/signing.rs` | `find_all_certs()` | ~817 |
| DER→P1363 converter | `local-agent/src-tauri/src/signing.rs` | `der_ecdsa_to_p1363()` | ~885 |
| WebSocket handler | `local-agent/src-tauri/src/websocket.rs` | `sign_jws` command | ~614 |

---

## Python Verification Script (debugging only)

```python
import base64, json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.x509 import load_der_x509_certificate

sig_data = '<paste signature.data from logs>'
jws_compact = base64.b64decode(sig_data).decode('ascii')
parts = jws_compact.split('.')
# parts[0]=header, parts[1]="" (detached), parts[2]=sig

header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))
x5c = header['jwk']['x5c']  # x5c is inside jwk, not at top level
cert = load_der_x509_certificate(base64.b64decode(x5c[0]))
pub_key = cert.public_key()

# Reconstructed signing input = header + "." + b64url(JCS_bundle)
# For detached JWS, you need the original bundle bytes to verify
bundle_b64u = '<paste SMARTCARD PRE-SIGN payload_b64url from logs>'
signing_input = f'{parts[0]}.{bundle_b64u}'.encode('ascii')

sig_bytes = base64.urlsafe_b64decode(parts[2] + '==')  # 96 bytes P1363
r = int.from_bytes(sig_bytes[:48], 'big')
s = int.from_bytes(sig_bytes[48:], 'big')
der_sig = utils.encode_dss_signature(r, s)
pub_key.verify(der_sig, signing_input, ec.ECDSA(hashes.SHA384()))
print('SIGNATURE VALID!')
```

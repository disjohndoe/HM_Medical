//! Smart card digital signing for CEZIH FHIR Bundle signatures.
//!
//! Two signing modes:
//! 1. **JWS mode** (`sign_for_jws`): Uses NCryptSignHash per RFC 7515 + RFC 8785 (JCS).
//!    Signing input: `base64url(header) + "." + base64url(JCS_canonicalized_bundle)`
//!    Output: `base64(JWS_compact_string)` — double base64 encoding for HAPI compatibility.
//!    The Bundle must be JCS-canonicalized (sorted keys) BEFORE being sent to the agent.
//!
//! 2. **CMS mode** (`sign_with_smartcard`): Legacy CryptSignMessage that produces
//!    detached PKCS#7/CMS signatures. Used as fallback if NCrypt is unavailable.

use base64::Engine as _;
use log::{info, warn};
use sha2::{Sha256, Sha384, Digest};
use std::ptr;
use windows_sys::Win32::Security::Cryptography::*;
use windows_sys::Win32::Foundation::GetLastError;

/// NCrypt flag to produce IEEE P1363 format (raw r||s) instead of DER-encoded ECDSA signatures.
/// JWS (RFC 7515) requires P1363 format. Without this flag, Windows NCryptSignHash defaults to DER.
const NCRYPT_ECDSA_P1363_FORMAT_FLAG: u32 = 0x00000001;

/// Result of a successful CMS signing operation.
pub struct SignResult {
    /// Detached CMS/PKCS#7 signature (DER-encoded).
    pub signature: Vec<u8>,
    /// Certificate thumbprint (SHA-1 hex) — used as JWS `kid`.
    pub kid: String,
}

/// Certificate info result (lightweight, no signing).
pub struct CertInfo {
    /// Certificate thumbprint (SHA-1 hex) — used as JOSE `kid`.
    pub kid: String,
    /// JOSE algorithm name: "RS256", "ES256", "ES384", etc.
    pub algorithm: String,
    /// DER-encoded X.509 certificate bytes (for PAdES embedding).
    pub cert_der: Vec<u8>,
}

/// Result of raw signing — just the raw signature bytes + cert metadata.
pub struct RawSignResult {
    /// Raw cryptographic signature bytes (NOT base64-encoded).
    pub signature: Vec<u8>,
    /// Certificate thumbprint (SHA-1 hex).
    pub kid: String,
    /// JOSE algorithm used.
    pub algorithm: String,
}

/// Result of JWS signing — contains the signature data ready for Bundle.signature.data.
pub struct JwsSignResult {
    /// Double-encoded: base64(JWS_compact_with_dots).
    /// The JWS compact is standard RFC 7515: base64url(h).base64url(p).base64url(s).
    /// The outer base64 encoding makes it HAPI base64Binary-compatible (no dots).
    pub jws_base64: String,
    /// Certificate thumbprint (SHA-1 hex).
    pub kid: String,
    /// JOSE algorithm name: "ES256", "ES384", "RS256", etc.
    pub algorithm: String,
}

/// Sign a FHIR Bundle for CEZIH per RFC 7515 (JWS) + RFC 8785 (JCS).
///
/// Takes JCS-canonicalized Bundle JSON bytes (with signature.data = "").
/// JOSE header includes alg + kid + jwk (EC coords) + x5c (full chain) per spec.
/// The x5c chain is built automatically by walking the Windows cert store (My → CA → Root).
///
/// Signing input (RFC 7515): base64url(header) + "." + base64url(payload)
/// Output: base64(JWS_compact) — double base64 for HAPI base64Binary compatibility.
pub fn sign_for_jws(bundle_json: &[u8]) -> Result<JwsSignResult, String> {
    unsafe { sign_for_jws_inner(bundle_json) }
}

/// Walk the Windows cert store chain for `leaf_ctx` and return x5c array (base64-std DER).
/// Searches "My", "CA", and "Root" system stores for each issuer up the chain.
unsafe fn build_x5c_chain(
    my_store: *mut core::ffi::c_void,
    leaf_ctx: *const CERT_CONTEXT,
    b64std: &base64::engine::GeneralPurpose,
) -> Vec<String> {
    let leaf_der = std::slice::from_raw_parts((*leaf_ctx).pbCertEncoded, (*leaf_ctx).cbCertEncoded as usize);
    let mut chain = vec![b64std.encode(leaf_der)];

    let ca_name: Vec<u16> = "CA\0".encode_utf16().collect();
    let root_name: Vec<u16> = "Root\0".encode_utf16().collect();
    let ca_store = CertOpenSystemStoreW(0, ca_name.as_ptr());
    let root_store = CertOpenSystemStoreW(0, root_name.as_ptr());

    let mut subject_ctx: *const CERT_CONTEXT = leaf_ctx;
    let mut acquired: Vec<*const CERT_CONTEXT> = Vec::new();

    for _ in 0..4 {
        let mut found: *const CERT_CONTEXT = ptr::null();
        for &search in &[my_store, ca_store, root_store] {
            if search.is_null() { continue; }
            let mut flags: u32 = 0;
            let issuer = CertGetIssuerCertificateFromStore(search, subject_ctx, ptr::null(), &mut flags);
            if !issuer.is_null() {
                found = issuer;
                break;
            }
        }
        if found.is_null() { break; }

        let der = std::slice::from_raw_parts((*found).pbCertEncoded, (*found).cbCertEncoded as usize);
        chain.push(b64std.encode(der));
        acquired.push(found);
        subject_ctx = found;

        // Stop at self-signed root (Subject DN == Issuer DN)
        let ci = &*(*found).pCertInfo;
        let is_root = ci.Subject.cbData == ci.Issuer.cbData && {
            let s = std::slice::from_raw_parts(ci.Subject.pbData, ci.Subject.cbData as usize);
            let i = std::slice::from_raw_parts(ci.Issuer.pbData, ci.Issuer.cbData as usize);
            s == i
        };
        if is_root { break; }
    }

    for ctx in acquired { CertFreeCertificateContext(ctx); }
    if !ca_store.is_null() { CertCloseStore(ca_store, 0); }
    if !root_store.is_null() { CertCloseStore(root_store, 0); }

    info!("JWS: x5c chain = {} cert(s)", chain.len());
    chain
}

unsafe fn sign_for_jws_inner(bundle_json: &[u8]) -> Result<JwsSignResult, String> {
    const ENCODING: u32 = X509_ASN_ENCODING | PKCS_7_ASN_ENCODING;
    let b64url = base64::engine::general_purpose::URL_SAFE_NO_PAD;
    let b64std = base64::engine::general_purpose::STANDARD;

    let store_name: Vec<u16> = "My\0".encode_utf16().collect();
    let store = CertOpenSystemStoreW(0, store_name.as_ptr());
    if store.is_null() {
        return Err("Failed to open certificate store".into());
    }

    let certs = find_all_certs(store, ENCODING);
    if certs.is_empty() {
        CertCloseStore(store, 0);
        return Err("No certificates found. Is the AKD smart card inserted?".into());
    }

    // Per-cert diagnostics — appended to final error so backend sees exact HRESULTs.
    let mut cert_diagnostics: Vec<String> = Vec::new();

    // CERT_NCRYPT_KEY_SPEC: returned by CryptAcquireCertificatePrivateKey when CNG key acquired.
    // Other values (AT_KEYEXCHANGE=1, AT_SIGNATURE=2) indicate CAPI key (HCRYPTPROV).
    const CERT_NCRYPT_KEY_SPEC: u32 = 0xFFFFFFFF;
    // CALG_SHA_256 = 0x0000800c — SHA-256 algorithm ID for CryptCreateHash (CAPI path).
    const CALG_SHA_256_ID: u32 = 0x0000800c;

    for (cert_ctx, cert_label) in &certs {
        let kid = match get_cert_thumbprint(*cert_ctx) {
            Ok(k) => k,
            Err(_) => {
                cert_diagnostics.push(format!("cert={}: thumbprint failed", cert_label));
                continue;
            }
        };

        info!("JWS: [diag] Trying {} (kid={:.16})...", cert_label, kid);

        // Step 1 — acquire private key.
        // CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG (0x00020000): tries CNG first, falls back to
        // CAPI if the CSP is CAPI-only (AKD HZZO minidriver returns 0x80090016 with CNG-only).
        let mut key_handle: usize = 0;
        let mut key_spec: u32 = 0;
        let mut must_free: i32 = 0;

        let ok = CryptAcquireCertificatePrivateKey(
            *cert_ctx,
            0x00020000, // CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG
            ptr::null(),
            &mut key_handle as *mut usize as *mut _,
            &mut key_spec,
            &mut must_free,
        );

        if ok == 0 {
            let err = GetLastError();
            warn!("JWS: [diag] acquire failed {} hresult=0x{:08x}", cert_label, err);
            cert_diagnostics.push(format!(
                "cert={} kid={:.16}: step1_acquire failed hresult=0x{:08x}",
                cert_label, kid, err
            ));
            continue;
        }
        info!(
            "JWS: [diag] acquired {} key_spec=0x{:08x} must_free={} path={}",
            cert_label, key_spec, must_free,
            if key_spec == CERT_NCRYPT_KEY_SPEC { "CNG" } else { "CAPI" }
        );

        // Extract X.509 certificate DER bytes (shared between CNG and CAPI paths).
        let cert_der = std::slice::from_raw_parts(
            (**cert_ctx).pbCertEncoded,
            (**cert_ctx).cbCertEncoded as usize,
        );
        let cert_info_ptr = (**cert_ctx).pCertInfo;

        if key_spec == CERT_NCRYPT_KEY_SPEC {
            // ── CNG path (modern CSP or smart card with CNG minidriver) ──────────
            let probe_hash = [0u8; 48];
            let mut sig_len: u32 = 0;
            let status = NCryptSignHash(
                key_handle,
                ptr::null(),
                probe_hash.as_ptr(),
                48,
                ptr::null_mut(),
                0,
                &mut sig_len,
                0,
            );

            if status != 0 {
                warn!("JWS: [diag] CNG probe failed {} ntstatus=0x{:08x}", cert_label, status as u32);
                cert_diagnostics.push(format!(
                    "cert={} kid={:.16}: cng_probe failed ntstatus=0x{:08x}",
                    cert_label, kid, status as u32
                ));
                if must_free != 0 { NCryptFreeObject(key_handle); }
                continue;
            }
            info!("JWS: CNG probe OK {} sig_len={}", cert_label, sig_len);

            let algorithm = match sig_len as usize {
                64 => "ES256",
                96 => "ES384",
                132 => "ES512",
                256 => "RS256",
                _ => "RS256",
            };

            let pub_key_blob = &(*cert_info_ptr).SubjectPublicKeyInfo.PublicKey;
            let pub_key_data = std::slice::from_raw_parts(pub_key_blob.pbData, pub_key_blob.cbData as usize);
            info!("JWS: CNG cert DER={} bytes, pub_key={} bytes, alg={}", cert_der.len(), pub_key_data.len(), algorithm);

            // Build x5c chain by walking Windows cert store (My → CA → Root).
            let x5c_chain = build_x5c_chain(store, *cert_ctx, &b64std);
            let x5c_json = x5c_chain.iter().map(|c| format!("\"{}\"", c)).collect::<Vec<_>>().join(",");

            // Build JOSE header matching extsigner format (Certilia remote — accepted by CEZIH):
            //   alg=ES384, jwk with nested x5c, EC coords x/y, kid, x5t#S256, nbf/exp
            //   No top-level x5c — it lives inside jwk only.
            let jose_header = if algorithm.starts_with("ES") {
                let coord_size: usize = match algorithm { "ES256" => 32, "ES384" => 48, _ => 66 };
                let expected_len = 1 + coord_size * 2;

                // SubjectPublicKeyInfo.PublicKey (CRYPT_BIT_BLOB) contains the EC uncompressed
                // point: 0x04 || X || Y. Some CSPs add a leading 0x00 (unused-bits from DER
                // BIT STRING) so handle both 97- and 98-byte blobs.
                let ec_point: &[u8] = if pub_key_data.len() == expected_len && pub_key_data[0] == 0x04 {
                    pub_key_data
                } else if pub_key_data.len() == expected_len + 1 && pub_key_data[0] == 0x00 && pub_key_data[1] == 0x04 {
                    &pub_key_data[1..]
                } else {
                    &[]
                };

                if !ec_point.is_empty() {
                    let x_b64u = b64url.encode(&ec_point[1..1 + coord_size]);
                    let y_b64u = b64url.encode(&ec_point[1 + coord_size..]);
                    info!("JWS: EC coords extracted x={:.8}... y={:.8}...", x_b64u, y_b64u);

                    // x5t#S256 = base64url(SHA-256(leaf DER))
                    let mut sha256 = Sha256::new();
                    sha256.update(cert_der);
                    let x5t_hash = sha256.finalize();
                    let x5t_s256 = b64url.encode(x5t_hash.as_ref() as &[u8]);

                    // nbf / exp from cert NotBefore / NotAfter (FILETIME → Unix epoch seconds).
                    // FILETIME is 100ns intervals since 1601-01-01; subtract Windows epoch offset.
                    let filetime_to_unix = |lo: u32, hi: u32| -> i64 {
                        let ft: u64 = (hi as u64) << 32 | lo as u64;
                        (ft.saturating_sub(116_444_736_000_000_000_u64) / 10_000_000) as i64
                    };
                    let nb = &(*cert_info_ptr).NotBefore;
                    let na = &(*cert_info_ptr).NotAfter;
                    let nbf = filetime_to_unix(nb.dwLowDateTime, nb.dwHighDateTime);
                    let exp = filetime_to_unix(na.dwLowDateTime, na.dwHighDateTime);

                    let crv = match algorithm { "ES256" => "P-256", "ES384" => "P-384", _ => "P-521" };
                    let jwk = format!(
                        r#"{{"kty":"EC","x5t#S256":"{}","nbf":{},"use":"sig","crv":"{}","kid":"{}","x5c":[{}],"x":"{}","y":"{}","exp":{}}}"#,
                        x5t_s256, nbf, crv, kid, x5c_json, x_b64u, y_b64u, exp
                    );
                    format!(r#"{{"alg":"{}","jwk":{},"kid":"{}"}}"#, algorithm, jwk, kid)
                } else {
                    warn!("JWS: EC pub_key unexpected len={} prefix=0x{:02x} — bare header fallback",
                          pub_key_data.len(), pub_key_data.first().copied().unwrap_or(0));
                    format!(r#"{{"alg":"{}","kid":"{}","x5c":[{}]}}"#, algorithm, kid, x5c_json)
                }
            } else {
                // RSA path (rare for AKD CNG) — keep simple header
                format!(r#"{{"alg":"{}","kid":"{}","x5c":[{}]}}"#, algorithm, kid, x5c_json)
            };
            info!("JWS: CNG JOSE header {} bytes", jose_header.len());

            let header_b64url = b64url.encode(jose_header.as_bytes());
            let payload_b64url = b64url.encode(bundle_json);
            // RFC 7515 signing input is always header.payload (attached form),
            // even when emitting a detached JWS (empty middle segment).
            let signing_input = format!("{}.{}", header_b64url, payload_b64url);

            let hash_bytes: Vec<u8> = match algorithm {
                "ES384" => { let mut h = Sha384::new(); h.update(signing_input.as_bytes()); h.finalize().to_vec() }
                "ES512" => { let mut h = sha2::Sha512::new(); h.update(signing_input.as_bytes()); h.finalize().to_vec() }
                _ => { let mut h = Sha256::new(); h.update(signing_input.as_bytes()); h.finalize().to_vec() }
            };
            info!("JWS: CNG signing_input={} chars, hash={} bytes ({})", signing_input.len(), hash_bytes.len(), algorithm);

            // Pass flags=0: AKD card CSPs reject NCRYPT_ECDSA_P1363_FORMAT_FLAG (0x80090009)
            // and return P1363 natively. For CSPs that return DER, we detect and convert below.
            let mut sig_buf = vec![0u8; (sig_len as usize).max(128)];
            let mut actual_len = sig_buf.len() as u32;
            let status = NCryptSignHash(
                key_handle, ptr::null(),
                hash_bytes.as_ptr(), hash_bytes.len() as u32,
                sig_buf.as_mut_ptr(), sig_buf.len() as u32, &mut actual_len, 0,
            );

            if must_free != 0 { NCryptFreeObject(key_handle); }

            if status != 0 {
                warn!("JWS: CNG sign failed {} ntstatus=0x{:08x} alg={}", cert_label, status as u32, algorithm);
                cert_diagnostics.push(format!(
                    "cert={} kid={:.16}: cng_sign failed ntstatus=0x{:08x} alg={}",
                    cert_label, kid, status as u32, algorithm
                ));
                continue;
            }

            sig_buf.truncate(actual_len as usize);

            // Normalize EC signature to P1363. Most CSPs return P1363 by default with flags=0.
            // If the card returned DER-encoded ECDSA (starts with 0x30), convert it.
            if algorithm.starts_with("ES") && sig_buf.first() == Some(&0x30) {
                let coord_size: usize = match algorithm { "ES256" => 32, "ES384" => 48, _ => 66 };
                match der_ecdsa_to_p1363(&sig_buf, coord_size) {
                    Some(p1363) => {
                        info!("JWS: DER→P1363 conversion OK, sig={} bytes", p1363.len());
                        sig_buf = p1363;
                    }
                    None => {
                        warn!("JWS: DER→P1363 failed for {}", cert_label);
                        cert_diagnostics.push(format!("cert={} kid={:.16}: der_to_p1363 failed", cert_label, kid));
                        continue;
                    }
                }
            }
            info!("JWS: CNG sign OK {} sig={} bytes", cert_label, sig_buf.len());

            // Self-verify.
            {
                let mut pub_key_handle: *mut core::ffi::c_void = ptr::null_mut();
                let import_ok = CryptImportPublicKeyInfoEx2(
                    ENCODING, &(*cert_info_ptr).SubjectPublicKeyInfo as *const _ as *mut _,
                    0, ptr::null_mut(), &mut pub_key_handle,
                );
                if import_ok != 0 && !pub_key_handle.is_null() {
                    let vs = BCryptVerifySignature(
                        pub_key_handle, ptr::null(),
                        hash_bytes.as_ptr(), hash_bytes.len() as u32,
                        sig_buf.as_ptr(), actual_len, 0,
                    );
                    if vs == 0 { info!("JWS: CNG SELF-VERIFICATION PASSED"); }
                    else { warn!("JWS: CNG SELF-VERIFICATION FAILED: 0x{:08x}", vs as u32); }
                    BCryptDestroyKey(pub_key_handle);
                }
            }

            let sig_b64url = b64url.encode(&sig_buf);
            // Detached JWS (RFC 7515 §7.2): empty middle segment → "header..sig".
            // Matches extsigner output (payload_b64url=0 chars in CEZIH logs).
            // CEZIH reconstructs signing input from Bundle bytes on its side.
            let jws_compact = format!("{}..{}", header_b64url, sig_b64url);
            let jws_base64 = b64std.encode(jws_compact.as_bytes());
            info!("JWS: CNG complete! alg={}, detached jws_compact={} chars, double_b64={} chars",
                  algorithm, jws_compact.len(), jws_base64.len());

            for (ctx, _) in &certs { CertFreeCertificateContext(*ctx); }
            CertCloseStore(store, 0);
            return Ok(JwsSignResult { jws_base64, kid, algorithm: algorithm.to_string() });

        } else {
            // ── CAPI path (AKD HZZO smart card with CAPI-only CSP minidriver) ─
            // key_handle = HCRYPTPROV; key_spec = AT_SIGNATURE (2) or AT_KEYEXCHANGE (1).
            // Sign with CryptCreateHash + CryptHashData + CryptSignHash.
            // CAPI RSA output is little-endian; JWS RS256 requires big-endian — reverse after signing.
            let hprov = key_handle;
            let algorithm = "RS256";

            let x5c_chain = build_x5c_chain(store, *cert_ctx, &b64std);
            let x5c_json = x5c_chain.iter().map(|c| format!("\"{}\"", c)).collect::<Vec<_>>().join(",");
            let jose_header = format!(r#"{{"alg":"{}","kid":"{}","x5c":[{}]}}"#, algorithm, kid, x5c_json);
            info!("JWS: CAPI JOSE header {} bytes, alg={}", jose_header.len(), algorithm);

            let header_b64url = b64url.encode(jose_header.as_bytes());
            let payload_b64url = b64url.encode(bundle_json);
            let signing_input = format!("{}.{}", header_b64url, payload_b64url);

            let mut hhash: usize = 0;
            let ok_hash = CryptCreateHash(hprov, CALG_SHA_256_ID, 0, 0, &mut hhash);
            if ok_hash == 0 {
                let err = GetLastError();
                warn!("JWS: CAPI CryptCreateHash failed for {}: 0x{:08x}", cert_label, err);
                cert_diagnostics.push(format!("cert={} kid={:.16}: capi_hash_create failed 0x{:08x}", cert_label, kid, err));
                if must_free != 0 { CryptReleaseContext(hprov, 0); }
                continue;
            }

            let si_bytes = signing_input.as_bytes();
            let ok_data = CryptHashData(hhash, si_bytes.as_ptr(), si_bytes.len() as u32, 0);
            if ok_data == 0 {
                let err = GetLastError();
                warn!("JWS: CAPI CryptHashData failed for {}: 0x{:08x}", cert_label, err);
                cert_diagnostics.push(format!("cert={} kid={:.16}: capi_hash_data failed 0x{:08x}", cert_label, kid, err));
                CryptDestroyHash(hhash);
                if must_free != 0 { CryptReleaseContext(hprov, 0); }
                continue;
            }

            // Query signature size first (null output buffer).
            let mut sig_len: u32 = 0;
            let ok_size = CryptSignHashA(hhash, key_spec, ptr::null(), 0, ptr::null_mut(), &mut sig_len);
            if ok_size == 0 {
                let err = GetLastError();
                warn!("JWS: CAPI CryptSignHash size query failed for {}: 0x{:08x}", cert_label, err);
                cert_diagnostics.push(format!("cert={} kid={:.16}: capi_sign_size failed 0x{:08x}", cert_label, kid, err));
                CryptDestroyHash(hhash);
                if must_free != 0 { CryptReleaseContext(hprov, 0); }
                continue;
            }

            let mut sig_buf = vec![0u8; sig_len as usize];
            let ok_sign = CryptSignHashA(hhash, key_spec, ptr::null(), 0, sig_buf.as_mut_ptr(), &mut sig_len);
            CryptDestroyHash(hhash);
            if must_free != 0 { CryptReleaseContext(hprov, 0); }

            if ok_sign == 0 {
                let err = GetLastError();
                warn!("JWS: CAPI CryptSignHash sign failed for {}: 0x{:08x}", cert_label, err);
                cert_diagnostics.push(format!("cert={} kid={:.16}: capi_sign failed 0x{:08x}", cert_label, kid, err));
                continue;
            }

            sig_buf.truncate(sig_len as usize);
            // CAPI RSA output is little-endian (standard PKCS#1 is big-endian for JWS RS256).
            sig_buf.reverse();
            info!("JWS: CAPI sign OK {} raw_sig={} bytes", cert_label, sig_buf.len());

            let sig_b64url = b64url.encode(&sig_buf);
            let jws_compact = format!("{}.{}.{}", header_b64url, payload_b64url, sig_b64url);
            let jws_base64 = b64std.encode(jws_compact.as_bytes());
            info!("JWS: CAPI complete! alg={}, jws_compact={} chars, double_b64={} chars",
                  algorithm, jws_compact.len(), jws_base64.len());

            for (ctx, _) in &certs { CertFreeCertificateContext(*ctx); }
            CertCloseStore(store, 0);
            return Ok(JwsSignResult { jws_base64, kid, algorithm: algorithm.to_string() });
        }
    }

    for (ctx, _) in &certs {
        CertFreeCertificateContext(*ctx);
    }
    CertCloseStore(store, 0);

    // Build rich error: every cert's exact failure step + HRESULT.
    // Common HRESULTs (so the reader doesn't have to cross-reference):
    //   0x80090016 NTE_BAD_KEYSET       — key container not found (CSP/CNG mismatch)
    //   0x8009001D NTE_PROV_TYPE_NOT_DEF — provider can't hand out a CNG key
    //   0x80090015 NTE_BAD_PROV_TYPE    — wrong provider type
    //   0x80090008 NTE_BAD_ALGID        — algorithm not supported
    //   0x80090011 NTE_NO_KEY           — key does not exist
    //   0x80090005 NTE_BAD_DATA
    //   0x80090029 NTE_NOT_SUPPORTED    — operation not supported by CSP
    //   0xC000A000 STATUS_INVALID_SIGNATURE
    let diag_joined = if cert_diagnostics.is_empty() {
        "no diagnostic captured".to_string()
    } else {
        cert_diagnostics.join(" || ")
    };
    Err(format!(
        "JWS signing failed for all certificates (tried CNG + CAPI). Per-cert diagnostic: {}. \
        Common meanings — 0x80090016/0x8009001D = key container not found; \
        0x80090008/0x80090029 = card refuses requested algorithm; \
        0x80090011 = key missing; 0x80090005 = bad data.",
        diag_joined
    ))
}

/// Get certificate info (kid + algorithm) from the smart card.
/// Lightweight query — no signing performed.
pub fn get_cert_info() -> Result<CertInfo, String> {
    unsafe { get_cert_info_inner() }
}

unsafe fn get_cert_info_inner() -> Result<CertInfo, String> {
    const ENCODING: u32 = X509_ASN_ENCODING | PKCS_7_ASN_ENCODING;

    let store_name: Vec<u16> = "My\0".encode_utf16().collect();
    let store = CertOpenSystemStoreW(0, store_name.as_ptr());
    if store.is_null() {
        return Err("Failed to open certificate store".into());
    }

    let certs = find_all_certs(store, ENCODING);
    if certs.is_empty() {
        CertCloseStore(store, 0);
        return Err("No certificates found. Is the AKD smart card inserted?".into());
    }

    for (cert_ctx, cert_label) in &certs {
        let kid = match get_cert_thumbprint(*cert_ctx) {
            Ok(k) => k,
            Err(_) => continue,
        };

        info!("CertInfo: trying {} (kid={:.16})...", cert_label, kid);

        let mut key_handle: usize = 0;
        let mut key_spec: u32 = 0;
        let mut must_free: i32 = 0;

        let ok = CryptAcquireCertificatePrivateKey(
            *cert_ctx,
            0x00040000, // CRYPT_ACQUIRE_ONLY_NCRYPT_KEY_FLAG
            ptr::null(),
            &mut key_handle as *mut usize as *mut _,
            &mut key_spec,
            &mut must_free,
        );

        if ok == 0 {
            let err = GetLastError();
            warn!("CertInfo: CryptAcquireCertificatePrivateKey failed for {}: 0x{:08x}", cert_label, err);
            continue;
        }

        // Probe signature size to determine algorithm
        let probe_hash = [0u8; 48];
        let mut sig_len: u32 = 0;
        let status = NCryptSignHash(
            key_handle,
            ptr::null(),
            probe_hash.as_ptr(),
            48,
            ptr::null_mut(),
            0,
            &mut sig_len,
            0,
        );

        if must_free != 0 { NCryptFreeObject(key_handle); }

        if status != 0 {
            warn!("CertInfo: NCryptSignHash size query failed for {}: 0x{:08x}", cert_label, status as u32);
            continue;
        }

        let algorithm = match sig_len as usize {
            64 => "ES256",
            96 => "ES384",
            132 => "ES512",
            256 => "RS256",
            _ => "RS256",
        };

        info!("CertInfo: found cert kid={:.16}, alg={}", kid, algorithm);

        // Extract DER-encoded certificate (same technique as sign_for_jws_inner)
        let cert_der = std::slice::from_raw_parts(
            (*(*cert_ctx)).pbCertEncoded,
            (*(*cert_ctx)).cbCertEncoded as usize,
        ).to_vec();

        // Cleanup
        for (ctx, _) in &certs {
            CertFreeCertificateContext(*ctx);
        }
        CertCloseStore(store, 0);

        return Ok(CertInfo {
            kid,
            algorithm: algorithm.to_string(),
            cert_der,
        });
    }

    for (ctx, _) in &certs {
        CertFreeCertificateContext(*ctx);
    }
    CertCloseStore(store, 0);

    Err("No usable signing certificate found. Smart card may not support CNG.".into())
}

/// Sign raw bytes using the smart card.
/// Hashes the data with the specified algorithm, then signs via NCryptSignHash.
/// Returns raw signature bytes — NO JWS construction, NO base64 encoding.
pub fn sign_raw(data: &[u8], algorithm: &str) -> Result<RawSignResult, String> {
    unsafe { sign_raw_inner(data, algorithm) }
}

unsafe fn sign_raw_inner(data: &[u8], algorithm: &str) -> Result<RawSignResult, String> {
    const ENCODING: u32 = X509_ASN_ENCODING | PKCS_7_ASN_ENCODING;

    let store_name: Vec<u16> = "My\0".encode_utf16().collect();
    let store = CertOpenSystemStoreW(0, store_name.as_ptr());
    if store.is_null() {
        return Err("Failed to open certificate store".into());
    }

    let certs = find_all_certs(store, ENCODING);
    if certs.is_empty() {
        CertCloseStore(store, 0);
        return Err("No certificates found. Is the AKD smart card inserted?".into());
    }

    for (cert_ctx, cert_label) in &certs {
        let kid = match get_cert_thumbprint(*cert_ctx) {
            Ok(k) => k,
            Err(_) => continue,
        };

        info!("RawSign: trying {} (kid={:.16})...", cert_label, kid);

        let mut key_handle: usize = 0;
        let mut key_spec: u32 = 0;
        let mut must_free: i32 = 0;

        let ok = CryptAcquireCertificatePrivateKey(
            *cert_ctx,
            0x00040000,
            ptr::null(),
            &mut key_handle as *mut usize as *mut _,
            &mut key_spec,
            &mut must_free,
        );

        if ok == 0 {
            warn!("RawSign: CryptAcquireCertificatePrivateKey failed for {}", cert_label);
            continue;
        }

        // Get signature size
        let probe_hash = [0u8; 48];
        let mut sig_len: u32 = 0;
        let status = NCryptSignHash(
            key_handle,
            ptr::null(),
            probe_hash.as_ptr(),
            48,
            ptr::null_mut(),
            0,
            &mut sig_len,
            0,
        );

        if status != 0 {
            warn!("RawSign: NCryptSignHash size query failed for {}", cert_label);
            if must_free != 0 { NCryptFreeObject(key_handle); }
            continue;
        }

        // Hash the data
        let hash_bytes: Vec<u8> = match algorithm {
            "ES384" => {
                let mut h = Sha384::new();
                h.update(data);
                h.finalize().to_vec()
            }
            _ => {
                let mut h = Sha256::new();
                h.update(data);
                h.finalize().to_vec()
            }
        };

        info!("RawSign: signing {} bytes with {} (hash={} bytes)", data.len(), algorithm, hash_bytes.len());

        // Pass flags=0: AKD card CSPs reject NCRYPT_ECDSA_P1363_FORMAT_FLAG (0x80090009)
        // and return P1363 natively. For CSPs that return DER, we detect and convert below.
        let sign_flags: u32 = 0;
        let mut sig_buf = vec![0u8; sig_len as usize];
        let mut actual_len = sig_len;
        let status = NCryptSignHash(
            key_handle,
            ptr::null(),
            hash_bytes.as_ptr(),
            hash_bytes.len() as u32,
            sig_buf.as_mut_ptr(),
            sig_len,
            &mut actual_len,
            sign_flags,
        );

        if must_free != 0 { NCryptFreeObject(key_handle); }

        if status != 0 {
            warn!("RawSign: NCryptSignHash failed for {}: 0x{:08x}", cert_label, status as u32);
            continue;
        }

        sig_buf.truncate(actual_len as usize);

        // Normalize EC signature to P1363. Most CSPs return P1363 by default with flags=0.
        // If the card returned DER-encoded ECDSA (starts with 0x30), convert it.
        if algorithm.starts_with("ES") && sig_buf.first() == Some(&0x30) {
            let coord_size: usize = match algorithm { "ES256" => 32, "ES384" => 48, _ => 66 };
            match der_ecdsa_to_p1363(&sig_buf, coord_size) {
                Some(p1363) => {
                    info!("RawSign: DER→P1363 conversion OK, sig={} bytes", p1363.len());
                    sig_buf = p1363;
                }
                None => {
                    warn!("RawSign: DER→P1363 failed for {}", cert_label);
                    continue;
                }
            }
        }

        info!("RawSign: OK — {} bytes, kid={:.16}, alg={}", sig_buf.len(), kid, algorithm);

        // Cleanup
        for (ctx, _) in &certs {
            CertFreeCertificateContext(*ctx);
        }
        CertCloseStore(store, 0);

        return Ok(RawSignResult {
            signature: sig_buf,
            kid,
            algorithm: algorithm.to_string(),
        });
    }

    for (ctx, _) in &certs {
        CertFreeCertificateContext(*ctx);
    }
    CertCloseStore(store, 0);

    Err("NCryptSignHash failed with all certificates.".into())
}

/// Sign data using the AKD smart card signing certificate (CMS mode).
///
/// Uses CryptSignMessage which handles CSP, hashing, and signing internally.
/// Returns a detached PKCS#7/CMS signature.
pub fn sign_with_smartcard(data: &[u8]) -> Result<SignResult, String> {
    unsafe { sign_with_smartcard_inner(data) }
}

unsafe fn sign_with_smartcard_inner(data: &[u8]) -> Result<SignResult, String> {
    const ENCODING: u32 = X509_ASN_ENCODING | PKCS_7_ASN_ENCODING;

    // 1. Open "My" certificate store
    let store_name: Vec<u16> = "My\0".encode_utf16().collect();
    let store = CertOpenSystemStoreW(0, store_name.as_ptr());
    if store.is_null() {
        return Err("Failed to open certificate store".into());
    }

    // 2. Collect all candidate certs (signing first, then identification as fallback)
    let certs = find_all_certs(store, ENCODING);
    if certs.is_empty() {
        CertCloseStore(store, 0);
        return Err("No certificates found in store. Is the AKD smart card inserted?".into());
    }

    // 3. Try each cert with SHA-256, then SHA-1
    let hash_oids: &[(&[u8], &str)] = &[
        (b"2.16.840.1.101.3.4.2.1\0", "SHA-256"),
        (b"1.3.14.3.2.26\0", "SHA-1"),
    ];

    for (cert_ctx, cert_label) in &certs {
        let kid = match get_cert_thumbprint(*cert_ctx) {
            Ok(k) => k,
            Err(_) => continue,
        };
        for (hash_oid, hash_name) in hash_oids {
            info!("Trying {} with {} ...", cert_label, hash_name);
            match try_sign_message(*cert_ctx, ENCODING, hash_oid, data) {
                Ok(sig) => {
                    info!("Signing successful with {} + {}, CMS sig size: {} bytes", cert_label, hash_name, sig.len());
                    // Cleanup all certs
                    for (ctx, _) in &certs {
                        CertFreeCertificateContext(*ctx);
                    }
                    CertCloseStore(store, 0);
                    return Ok(SignResult { signature: sig, kid });
                }
                Err(e) => {
                    warn!("{} with {} failed: {}", cert_label, hash_name, e);
                }
            }
        }
    }

    for (ctx, _) in &certs {
        CertFreeCertificateContext(*ctx);
    }
    CertCloseStore(store, 0);
    Err("All signing attempts failed with all certificates and hash algorithms".into())
}

unsafe fn try_sign_message(
    cert_ctx: *const CERT_CONTEXT,
    encoding: u32,
    hash_oid: &[u8],
    data: &[u8],
) -> Result<Vec<u8>, String> {

    let sign_params = CRYPT_SIGN_MESSAGE_PARA {
        cbSize: std::mem::size_of::<CRYPT_SIGN_MESSAGE_PARA>() as u32,
        dwMsgEncodingType: encoding,
        pSigningCert: cert_ctx,
        HashAlgorithm: CRYPT_ALGORITHM_IDENTIFIER {
            pszObjId: hash_oid.as_ptr() as *mut u8,
            Parameters: CRYPT_INTEGER_BLOB {
                cbData: 0,
                pbData: ptr::null_mut(),
            },
        },
        pvHashAuxInfo: ptr::null_mut(),
        cMsgCert: 0,
        rgpMsgCert: ptr::null_mut(),
        cMsgCrl: 0,
        rgpMsgCrl: ptr::null_mut(),
        cAuthAttr: 0,
        rgAuthAttr: ptr::null_mut(),
        cUnauthAttr: 0,
        rgUnauthAttr: ptr::null_mut(),
        dwFlags: 0,
        dwInnerContentType: 0,
    };

    let data_ptr: *const u8 = data.as_ptr();
    let data_len: u32 = data.len() as u32;

    // Get signature size
    let mut sig_size: u32 = 0;
    let ok = CryptSignMessage(
        &sign_params,
        1, // detached
        1,
        &data_ptr,
        &data_len,
        ptr::null_mut(),
        &mut sig_size,
    );

    if ok == 0 {
        let err = GetLastError();
        return Err(format!("size query failed (err=0x{:08x})", err));
    }

    // Sign
    let mut sig_buf = vec![0u8; sig_size as usize];
    let ok = CryptSignMessage(
        &sign_params,
        1,
        1,
        &data_ptr,
        &data_len,
        sig_buf.as_mut_ptr(),
        &mut sig_size,
    );

    if ok == 0 {
        let err = GetLastError();
        return Err(format!("sign failed (err=0x{:08x})", err));
    }

    sig_buf.truncate(sig_size as usize);
    Ok(sig_buf)
}

/// Find all candidate certificates, signing certs first, then identification as fallback.
/// Returns duplicated cert contexts (caller must free each).
unsafe fn find_all_certs(store: *mut core::ffi::c_void, encoding: u32) -> Vec<(*const CERT_CONTEXT, String)> {
    let mut signing_certs = Vec::new();
    let mut other_certs = Vec::new();
    let mut prev_ctx: *const CERT_CONTEXT = ptr::null();

    loop {
        let ctx = CertEnumCertificatesInStore(store, prev_ctx);
        if ctx.is_null() {
            break;
        }

        let cert_info = &*(*ctx).pCertInfo;
        let name_blob = &cert_info.Subject;
        let len = CertNameToStrW(encoding, name_blob, CERT_X500_NAME_STR, ptr::null_mut(), 0);
        if len > 1 {
            let mut buf = vec![0u16; len as usize];
            CertNameToStrW(encoding, name_blob, CERT_X500_NAME_STR, buf.as_mut_ptr(), len);
            let subject = String::from_utf16_lossy(&buf);
            let subject = subject.trim_end_matches('\0').to_string();
            info!("Found cert: {}", subject);

            // Duplicate the context so enumeration can continue
            let dup = CertDuplicateCertificateContext(ctx) as *const CERT_CONTEXT;

            if subject.contains("OU=Signing") || subject.contains("OU=SignatureTest") || subject.contains("OU=Digital Signature") {
                signing_certs.push((dup, format!("signing({})", subject)));
            } else {
                other_certs.push((dup, format!("fallback({})", subject)));
            }
        }
        prev_ctx = ctx;
    }

    info!("Found {} signing + {} other certs", signing_certs.len(), other_certs.len());

    // Signing certs first, then others as fallback
    signing_certs.extend(other_certs);
    signing_certs
}

/// Get SHA-1 thumbprint of a certificate (hex string).
unsafe fn get_cert_thumbprint(ctx: *const CERT_CONTEXT) -> Result<String, String> {
    let mut hash_size: u32 = 20;
    let mut hash_buf = [0u8; 20];

    let ok = CryptHashCertificate(
        0,
        CALG_SHA1,
        0,
        (*ctx).pbCertEncoded,
        (*ctx).cbCertEncoded,
        hash_buf.as_mut_ptr(),
        &mut hash_size,
    );

    if ok == 0 {
        return Err("Failed to compute certificate thumbprint".into());
    }

    Ok(hash_buf[..hash_size as usize]
        .iter()
        .map(|b| format!("{:02x}", b))
        .collect())
}

/// Convert DER-encoded ECDSA signature (SEQUENCE { INTEGER r, INTEGER s }) to
/// IEEE P1363 format (raw r || s, each zero-padded to coord_size bytes).
/// Required when the smart card CSP rejects NCRYPT_ECDSA_P1363_FORMAT_FLAG.
fn der_ecdsa_to_p1363(der: &[u8], coord_size: usize) -> Option<Vec<u8>> {
    if der.len() < 6 || der[0] != 0x30 { return None; }
    let mut pos = 1usize;
    let _seq_len = parse_der_len(der, &mut pos)?;
    if pos >= der.len() || der[pos] != 0x02 { return None; }
    pos += 1;
    let r_len = parse_der_len(der, &mut pos)?;
    if pos + r_len > der.len() { return None; }
    let r_bytes = &der[pos..pos + r_len];
    pos += r_len;
    if pos >= der.len() || der[pos] != 0x02 { return None; }
    pos += 1;
    let s_len = parse_der_len(der, &mut pos)?;
    if pos + s_len > der.len() { return None; }
    let s_bytes = &der[pos..pos + s_len];

    let r = strip_leading_zeros(r_bytes);
    let s = strip_leading_zeros(s_bytes);
    if r.len() > coord_size || s.len() > coord_size { return None; }

    let mut out = vec![0u8; coord_size * 2];
    out[coord_size - r.len()..coord_size].copy_from_slice(r);
    out[coord_size * 2 - s.len()..].copy_from_slice(s);
    Some(out)
}

fn parse_der_len(data: &[u8], pos: &mut usize) -> Option<usize> {
    if *pos >= data.len() { return None; }
    let b = data[*pos];
    *pos += 1;
    if b & 0x80 == 0 {
        Some(b as usize)
    } else {
        let n = (b & 0x7f) as usize;
        if *pos + n > data.len() { return None; }
        let mut len = 0usize;
        for _ in 0..n { len = (len << 8) | (data[*pos] as usize); *pos += 1; }
        Some(len)
    }
}

fn strip_leading_zeros(b: &[u8]) -> &[u8] {
    let i = b.iter().position(|&x| x != 0).unwrap_or(b.len().saturating_sub(1));
    &b[i..]
}

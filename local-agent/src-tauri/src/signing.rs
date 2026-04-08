//! Smart card digital signing for CEZIH FHIR Bundle signatures.
//!
//! Two signing modes:
//! 1. **JWS mode** (`sign_for_jws`): Uses NCryptSignHash to produce raw ECDSA/RSA
//!    signature bytes for the CEZIH signature format:
//!    `base64(JOSE_header_JSON + Bundle_JSON + raw_signature_bytes)`
//!
//! 2. **CMS mode** (`sign_with_smartcard`): Legacy CryptSignMessage that produces
//!    detached PKCS#7/CMS signatures. Used as fallback if NCrypt is unavailable.

use base64::Engine as _;
use log::{info, warn};
use sha2::{Sha256, Sha384, Digest};
use std::ptr;
use windows_sys::Win32::Security::Cryptography::*;
use windows_sys::Win32::Foundation::GetLastError;

/// Result of a successful CMS signing operation.
pub struct SignResult {
    /// Detached CMS/PKCS#7 signature (DER-encoded).
    pub signature: Vec<u8>,
    /// Certificate thumbprint (SHA-1 hex) — used as JWS `kid`.
    pub kid: String,
}

/// Result of JWS signing — contains the complete base64-encoded JWS
/// ready to be placed directly in Bundle.signature.data.
pub struct JwsSignResult {
    /// Complete JWS, base64-encoded: base64(b64url_header.b64url_payload.b64url_sig)
    pub jws_base64: String,
    /// Certificate thumbprint (SHA-1 hex).
    pub kid: String,
    /// JOSE algorithm name: "ES256", "ES384", "RS256", etc.
    pub algorithm: String,
}

/// Sign a FHIR Bundle for CEZIH — produces standard JWS (RFC 7515).
///
/// Takes the serialized Bundle JSON bytes (with signature.data = "").
/// Builds a complete JWS with:
///   - JOSE header including `alg`, `kid`, `x5c` (full cert for verification)
///   - Payload = base64url(bundle_json)
///   - Signature = base64url(NCryptSignHash output)
/// Returns base64(JWS_compact) ready for FHIR signature.data.
pub fn sign_for_jws(bundle_json: &[u8]) -> Result<JwsSignResult, String> {
    unsafe { sign_for_jws_inner(bundle_json) }
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

    let mut certs = find_all_certs(store, ENCODING);
    if certs.is_empty() {
        CertCloseStore(store, 0);
        return Err("No certificates found. Is the AKD smart card inserted?".into());
    }

    // Reverse: try identification cert first (signing cert key link is broken).
    certs.reverse();

    for (cert_ctx, cert_label) in &certs {
        let kid = match get_cert_thumbprint(*cert_ctx) {
            Ok(k) => k,
            Err(_) => continue,
        };

        info!("JWS: Trying NCryptSignHash with {} ...", cert_label);

        // Get NCrypt key handle
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
            warn!("JWS: CryptAcquireCertificatePrivateKey failed for {}: 0x{:08x}", cert_label, err);
            continue;
        }

        // Probe signature size to determine algorithm
        let probe_hash = [0u8; 48]; // max hash size we use (SHA-384)
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
            warn!("JWS: NCryptSignHash size query failed for {}: 0x{:08x}", cert_label, status as u32);
            if must_free != 0 { NCryptFreeObject(key_handle); }
            continue;
        }

        // Determine algorithm from signature length
        let algorithm = match sig_len as usize {
            64 => "ES256",
            96 => "ES384",
            132 => "ES512",
            256 => "RS256",
            _ => "RS256",
        };

        // Get certificate DER for x5c
        let cert_der = std::slice::from_raw_parts(
            (**cert_ctx).pbCertEncoded,
            (**cert_ctx).cbCertEncoded as usize,
        ).to_vec();
        let cert_b64 = b64std.encode(&cert_der);

        // Build JOSE header with x5c (cert chain for signature verification)
        let jose_header = format!(
            r#"{{"alg":"{}","x5c":["{}"],"kid":"{}"}}"#,
            algorithm, cert_b64, kid,
        );
        info!("JWS: JOSE header alg={}, x5c cert={} bytes, kid={:.16}", algorithm, cert_der.len(), kid);

        // Build JWS signing input: base64url(header) + "." + base64url(payload)
        let header_b64url = b64url.encode(jose_header.as_bytes());
        let payload_b64url = b64url.encode(bundle_json);
        let signing_input = format!("{}.{}", header_b64url, payload_b64url);

        // Hash with correct algorithm for the key type
        let hash_bytes: Vec<u8> = match algorithm {
            "ES384" => {
                let mut h = Sha384::new();
                h.update(signing_input.as_bytes());
                h.finalize().to_vec()
            }
            _ => {
                // ES256, RS256, etc. use SHA-256
                let mut h = Sha256::new();
                h.update(signing_input.as_bytes());
                h.finalize().to_vec()
            }
        };

        info!("JWS: signing_input={} chars, hash={} bytes ({})",
              signing_input.len(), hash_bytes.len(), algorithm);

        // Sign the hash
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
            0,
        );

        if must_free != 0 { NCryptFreeObject(key_handle); }

        if status != 0 {
            warn!("JWS: NCryptSignHash failed for {}: 0x{:08x}", cert_label, status as u32);
            continue;
        }

        sig_buf.truncate(actual_len as usize);

        // Assemble JWS compact: header.payload.signature
        let sig_b64url = b64url.encode(&sig_buf);
        let jws_compact = format!("{}.{}", signing_input, sig_b64url);

        // Put JWS compact directly in signature.data (no extra base64 encoding).
        // FHIR base64Binary field value IS the JWS compact string, which is
        // already composed of base64url characters + dots.
        let jws_base64 = jws_compact;

        info!("JWS: complete! alg={}, sig={} bytes, JWS={} chars",
              algorithm, sig_buf.len(), jws_base64.len());

        // Cleanup
        for (ctx, _) in &certs {
            CertFreeCertificateContext(*ctx);
        }
        CertCloseStore(store, 0);

        return Ok(JwsSignResult {
            jws_base64,
            kid,
            algorithm: algorithm.to_string(),
        });
    }

    for (ctx, _) in &certs {
        CertFreeCertificateContext(*ctx);
    }
    CertCloseStore(store, 0);

    Err("NCryptSignHash failed with all certificates. Smart card may not support CNG signing.".into())
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

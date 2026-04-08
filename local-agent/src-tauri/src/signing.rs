//! Smart card digital signing via Windows CryptoAPI.
//!
//! Uses the AKD signing certificate (OU=Signing) from the Windows
//! certificate store. The private key lives on the smart card and
//! Windows CSP handles PIN caching (same process = single prompt).
//!
//! Flow:
//! 1. Open "My" cert store
//! 2. Find cert with OU=Signing (AKD signing certificate)
//! 3. Acquire private key handle via CryptAcquireCertificatePrivateKey
//! 4. Hash data with SHA-256
//! 5. Sign hash with RSA PKCS#1 v1.5
//! 6. Return raw signature bytes + certificate thumbprint as kid

use log::{debug, info, warn};
use sha2::{Digest, Sha256};
use std::ptr;
use windows_sys::Win32::Security::Cryptography::*;

/// Result of a successful signing operation.
pub struct SignResult {
    /// Raw RSA signature bytes (DER, big-endian).
    pub signature: Vec<u8>,
    /// Certificate thumbprint (SHA-1 hex) — used as JWS `kid`.
    pub kid: String,
}

/// Sign data using the AKD smart card signing certificate.
///
/// Returns the raw RSA signature and the certificate's thumbprint.
/// The caller is responsible for creating the JWS structure.
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

    // 2. Find the signing certificate (OU=Signing)
    let cert_ctx = find_signing_cert(store, ENCODING);
    if cert_ctx.is_null() {
        CertCloseStore(store, 0);
        return Err(
            "No signing certificate found (OU=Signing). Is the AKD smart card inserted?".into(),
        );
    }

    // 3. Get certificate thumbprint for JWS kid
    let kid = get_cert_thumbprint(cert_ctx)?;
    info!("Found signing cert, thumbprint (kid): {}", &kid[..16]);

    // 4. Acquire private key
    let mut key_prov: usize = 0; // HCRYPTPROV or NCRYPT_KEY_HANDLE
    let mut key_spec: u32 = 0;
    let mut caller_free: i32 = 0;

    let ok = CryptAcquireCertificatePrivateKey(
        cert_ctx,
        CRYPT_ACQUIRE_CACHE_FLAG | CRYPT_ACQUIRE_SILENT_FLAG,
        ptr::null_mut(),
        &mut key_prov,
        &mut key_spec,
        &mut caller_free,
    );

    if ok == 0 {
        // Retry without SILENT flag — may trigger PIN prompt
        let ok2 = CryptAcquireCertificatePrivateKey(
            cert_ctx,
            CRYPT_ACQUIRE_CACHE_FLAG,
            ptr::null_mut(),
            &mut key_prov,
            &mut key_spec,
            &mut caller_free,
        );
        if ok2 == 0 {
            CertFreeCertificateContext(cert_ctx);
            CertCloseStore(store, 0);
            return Err("Failed to acquire private key from smart card".into());
        }
    }

    info!(
        "Private key acquired (key_spec={}, caller_free={})",
        key_spec, caller_free
    );

    // 5. Compute SHA-256 hash
    let hash_bytes = Sha256::digest(data);
    debug!("SHA-256 hash: {:x}", hash_bytes);

    // 6. Sign the hash using CryptoAPI
    let signature = sign_hash_capi(key_prov, key_spec, &hash_bytes)?;

    // 7. Cleanup
    if caller_free != 0 {
        CryptReleaseContext(key_prov, 0);
    }
    CertFreeCertificateContext(cert_ctx);
    CertCloseStore(store, 0);

    info!("Signing successful, signature size: {} bytes", signature.len());

    Ok(SignResult { signature, kid })
}

/// Find a certificate with OU=Signing in the store.
unsafe fn find_signing_cert(store: *mut core::ffi::c_void, encoding: u32) -> *const CERT_CONTEXT {
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
            let subject = subject.trim_end_matches('\0');
            debug!("Checking cert: {}", subject);

            // AKD smart cards have two certs:
            // - OU=Identification (for mTLS auth)
            // - OU=Signing (for document signing)
            if subject.contains("OU=Signing") || subject.contains("OU=Digital Signature") {
                info!("Found signing certificate: {}", subject);
                return ctx;
            }
        }
        prev_ctx = ctx;
    }

    // Fallback: try any cert with a private key (non-Identification)
    warn!("No OU=Signing cert found, trying fallback...");
    prev_ctx = ptr::null();
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
            let subject = subject.trim_end_matches('\0');

            // Skip identification certs, take any other (likely signing)
            if !subject.contains("OU=Identification") {
                info!("Fallback signing certificate: {}", subject);
                return ctx;
            }
        }
        prev_ctx = ctx;
    }

    ptr::null()
}

/// Get SHA-1 thumbprint of a certificate (hex string).
unsafe fn get_cert_thumbprint(ctx: *const CERT_CONTEXT) -> Result<String, String> {
    let mut hash_size: u32 = 20; // SHA-1 = 20 bytes
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

/// Sign a SHA-256 hash using legacy CryptoAPI (CAPI).
unsafe fn sign_hash_capi(
    prov: usize,
    key_spec: u32,
    hash_bytes: &[u8],
) -> Result<Vec<u8>, String> {
    // Create a hash object
    let mut hash_handle: usize = 0;
    if CryptCreateHash(prov, CALG_SHA_256, 0, 0, &mut hash_handle) == 0 {
        return Err("CryptCreateHash failed".into());
    }

    // Set the hash value directly (we already computed SHA-256)
    if CryptSetHashParam(hash_handle, HP_HASHVAL, hash_bytes.as_ptr(), 0) == 0 {
        CryptDestroyHash(hash_handle);
        return Err("CryptSetHashParam failed".into());
    }

    // Get signature size first
    let mut sig_len: u32 = 0;
    if CryptSignHashW(hash_handle, key_spec, ptr::null(), 0, ptr::null_mut(), &mut sig_len) == 0 {
        CryptDestroyHash(hash_handle);
        return Err("CryptSignHash (size query) failed".into());
    }

    // Sign
    let mut sig_buf = vec![0u8; sig_len as usize];
    if CryptSignHashW(
        hash_handle,
        key_spec,
        ptr::null(),
        0,
        sig_buf.as_mut_ptr(),
        &mut sig_len,
    ) == 0
    {
        CryptDestroyHash(hash_handle);
        return Err("CryptSignHash failed — PIN cancelled or card error?".into());
    }

    CryptDestroyHash(hash_handle);

    // CryptoAPI returns signature in little-endian; PKCS#1 / JWS needs big-endian
    sig_buf.truncate(sig_len as usize);
    sig_buf.reverse();

    Ok(sig_buf)
}

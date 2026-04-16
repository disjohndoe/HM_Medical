use log::{debug, warn};
use once_cell::sync::Lazy;
use serde::Serialize;
use serde_json::json;
use std::sync::Mutex;

#[derive(Debug, Clone, Serialize)]
pub struct ReaderInfo {
    pub name: String,
    pub card_inserted: bool,
    pub card_holder: Option<String>,
    pub atr_hex: Option<String>,
}

/// Convert reader list to JSON values for WebSocket status messages and shared state.
pub fn readers_to_json(readers: &[ReaderInfo]) -> Vec<serde_json::Value> {
    readers.iter().map(|r| {
        json!({
            "name": r.name,
            "card_inserted": r.card_inserted,
            "card_holder": r.card_holder,
            "atr": r.atr_hex,
        })
    }).collect()
}

/// Identity extracted from the Windows cert store for the inserted card.
#[derive(Debug, Clone, Default)]
pub struct CardIdentity {
    pub holder: Option<String>,
    /// X.509 certificate serial number, lowercase hex, no separators.
    pub cert_serial: Option<String>,
    /// Subject-DN serialNumber RDN (OID 2.5.4.5) — Croatian AKD encodes the person's
    /// OIB here (optionally `HR`-prefixed). We strip any non-digit prefix.
    pub subject_oib: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SmartCardStatus {
    pub reader_available: bool,
    pub card_inserted: bool,
    pub card_holder: Option<String>,
    pub card_serial: Option<String>,
    pub card_subject_oib: Option<String>,
    pub readers: Vec<ReaderInfo>,
}

/// Cache for the last known card state to avoid PowerShell on every tick.
struct CachedCard {
    reader_name: String,
    atr_hex: Option<String>,
    identity: CardIdentity,
}

static CARD_CACHE: Lazy<Mutex<Option<CachedCard>>> = Lazy::new(|| Mutex::new(None));

/// Check smart card readers, card presence, and read holder names.
///
/// Uses `get_status_change()` to detect card presence and read ATR from reader
/// state flags — **never connects to the card**, so it never triggers Windows
/// Certificate Propagation Service PIN prompts.
///
/// Holder name is read from the Windows cert store via CryptoAPI (public data
/// only, no private key access, no PIN).
pub fn check_card_status() -> SmartCardStatus {
    let ctx = match pcsc::Context::establish(pcsc::Scope::User) {
        Ok(ctx) => ctx,
        Err(e) => {
            debug!("PC/SC context failed: {}", e);
            return SmartCardStatus {
                reader_available: false,
                card_inserted: false,
                card_holder: None,
                card_serial: None,
                card_subject_oib: None,
                readers: vec![],
            };
        }
    };

    // List readers
    let readers_list = match ctx.list_readers_len() {
        Ok(len) => {
            let mut buf = vec![0u8; len];
            match ctx.list_readers(&mut buf) {
                Ok(readers) => readers.map(|r| r.to_string_lossy().into_owned()).collect::<Vec<_>>(),
                Err(e) => {
                    debug!("Failed to list readers: {}", e);
                    return SmartCardStatus {
                        reader_available: false,
                        card_inserted: false,
                        card_holder: None,
                        card_serial: None,
                        card_subject_oib: None,
                        readers: vec![],
                    };
                }
            }
        }
        Err(e) => {
            debug!("Failed to get readers buffer length: {}", e);
            return SmartCardStatus {
                reader_available: false,
                card_inserted: false,
                card_holder: None,
                card_serial: None,
                card_subject_oib: None,
                readers: vec![],
            };
        }
    };

    if readers_list.is_empty() {
        return SmartCardStatus {
            reader_available: false,
            card_inserted: false,
            card_holder: None,
            card_serial: None,
            card_subject_oib: None,
            readers: vec![],
        };
    }

    debug!("Found {} reader(s): {:?}", readers_list.len(), readers_list);

    // Query reader states WITHOUT connecting to cards.
    // get_status_change returns card presence + ATR from the reader driver,
    // with zero card interaction → zero PIN prompts.
    let mut reader_states: Vec<pcsc::ReaderState> = readers_list
        .iter()
        .filter_map(|name| {
            std::ffi::CString::new(name.as_str()).ok()
                .map(|cname| pcsc::ReaderState::new(cname, pcsc::State::UNAWARE))
        })
        .collect();

    if let Err(e) = ctx.get_status_change(std::time::Duration::from_millis(0), &mut reader_states) {
        warn!("get_status_change failed: {}", e);
        return SmartCardStatus {
            reader_available: true,
            card_inserted: false,
            card_holder: None,
            card_serial: None,
            card_subject_oib: None,
            readers: readers_list.iter().map(|name| ReaderInfo {
                name: name.clone(), card_inserted: false, card_holder: None, atr_hex: None,
            }).collect(),
        };
    }

    let mut readers: Vec<ReaderInfo> = Vec::new();
    let mut first_identity: CardIdentity = CardIdentity::default();

    for rs in reader_states.iter() {
        let reader_name = rs.name().to_string_lossy().into_owned();
        let state = rs.event_state();
        let card_present = state.contains(pcsc::State::PRESENT);

        if card_present {
            // Read ATR directly from reader state (no card connection needed)
            let atr = rs.atr();
            let atr_hex = if !atr.is_empty() {
                let hex: String = atr.iter().map(|b| format!("{:02x}", b)).collect();
                debug!("Card ATR in '{}': {}", reader_name, hex);
                Some(hex)
            } else {
                None
            };

            // Check cache: only call CryptoAPI if card changed
            let identity = {
                let cache = CARD_CACHE.lock().unwrap_or_else(|e| e.into_inner());
                if let Some(ref cached) = *cache {
                    if cached.reader_name == reader_name && cached.atr_hex == atr_hex {
                        debug!("Card unchanged (same reader+ATR) — using cached identity");
                        cached.identity.clone()
                    } else {
                        drop(cache);
                        debug!("Card changed — reading identity from cert store");
                        read_card_identity_from_certstore()
                    }
                } else {
                    drop(cache);
                    debug!("No cached card — reading identity from cert store");
                    read_card_identity_from_certstore()
                }
            };

            if let Some(ref name) = identity.holder {
                debug!("Card holder: {}", name);
            }
            if let Some(ref serial) = identity.cert_serial {
                debug!("Card cert serial: {}", serial);
            }

            // Update cache
            {
                let mut cache = CARD_CACHE.lock().unwrap_or_else(|e| e.into_inner());
                *cache = Some(CachedCard {
                    reader_name: reader_name.clone(),
                    atr_hex: atr_hex.clone(),
                    identity: identity.clone(),
                });
            }

            if first_identity.holder.is_none() {
                first_identity = identity.clone();
            }

            readers.push(ReaderInfo {
                name: reader_name.clone(),
                card_inserted: true,
                card_holder: identity.holder,
                atr_hex,
            });
        } else {
            debug!("Reader '{}' — no card inserted", reader_name);
            readers.push(ReaderInfo {
                name: reader_name.clone(),
                card_inserted: false,
                card_holder: None,
                atr_hex: None,
            });
        }
    }

    // Derive top-level fields from readers array (backward compat)
    let any_card = readers.iter().any(|r| r.card_inserted);
    let first_holder = readers
        .iter()
        .find(|r| r.card_holder.is_some())
        .and_then(|r| r.card_holder.clone());

    // Clear cache when all cards removed
    if !any_card {
        let mut cache = CARD_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        *cache = None;
    }

    SmartCardStatus {
        reader_available: !readers.is_empty(),
        card_inserted: any_card,
        card_holder: first_holder,
        card_serial: if any_card { first_identity.cert_serial } else { None },
        card_subject_oib: if any_card { first_identity.subject_oib } else { None },
        readers,
    }
}

/// Read identity (holder name + cert serial + subject-DN OIB) from the Windows
/// certificate store using CryptoAPI.
///
/// Reads only public certificate data — does NOT access private keys, so this
/// never triggers Windows Security PIN prompts.
///
/// Windows Certificate Propagation Service automatically copies smart card certs
/// to CurrentUser\My when a card is inserted, so we just read from there.
fn read_card_identity_from_certstore() -> CardIdentity {
    use std::ptr;
    use std::slice;
    use windows_sys::Win32::Security::Cryptography::*;

    const ENCODING: u32 = X509_ASN_ENCODING | PKCS_7_ASN_ENCODING;

    let mut identity = CardIdentity::default();

    unsafe {
        let store_name: Vec<u16> = "My\0".encode_utf16().collect();
        let store = CertOpenSystemStoreW(0, store_name.as_ptr());
        if store.is_null() {
            warn!("Failed to open certificate store");
            return identity;
        }

        let mut prev_ctx: *const CERT_CONTEXT = ptr::null();

        loop {
            let ctx = CertEnumCertificatesInStore(store, prev_ctx);
            if ctx.is_null() {
                break;
            }

            let cert_info = &*(*ctx).pCertInfo;
            let name_blob = &cert_info.Subject;

            let len = CertNameToStrW(ENCODING, name_blob, CERT_X500_NAME_STR, ptr::null_mut(), 0);
            if len > 1 {
                let mut buf = vec![0u16; len as usize];
                CertNameToStrW(ENCODING, name_blob, CERT_X500_NAME_STR, buf.as_mut_ptr(), len);

                let subject = String::from_utf16_lossy(&buf);
                let subject = subject.trim_end_matches('\0');
                debug!("Cert subject: {}", subject);

                if subject.contains("OU=Identification") {
                    let (holder, subject_oib) = parse_subject_dn(subject);
                    if let Some(h) = holder {
                        // Read X.509 cert serial number (little-endian in pbData; reverse for standard hex).
                        let serial_blob = &cert_info.SerialNumber;
                        let cert_serial = if serial_blob.cbData > 0 && !serial_blob.pbData.is_null() {
                            let bytes = slice::from_raw_parts(
                                serial_blob.pbData,
                                serial_blob.cbData as usize,
                            );
                            let hex: String = bytes
                                .iter()
                                .rev()
                                .map(|b| format!("{:02x}", b))
                                .collect::<String>()
                                .trim_start_matches('0')
                                .to_string();
                            if hex.is_empty() { Some("0".to_string()) } else { Some(hex) }
                        } else {
                            None
                        };

                        identity = CardIdentity {
                            holder: Some(h),
                            cert_serial,
                            subject_oib,
                        };
                        CertFreeCertificateContext(ctx);
                        break;
                    }
                }
            }

            prev_ctx = ctx;
        }

        let _ = CertCloseStore(store, 0);
    }

    identity
}

/// Split a CertNameToStrW X.500 subject string into (CN, subject-DN serialNumber digits).
/// Accepts both `SERIALNUMBER=` and `OID.2.5.4.5=` forms, strips `HR` prefix if present.
fn parse_subject_dn(subject: &str) -> (Option<String>, Option<String>) {
    let mut cn: Option<String> = None;
    let mut serial: Option<String> = None;

    for raw in subject.split(',') {
        let part = raw.trim();
        if cn.is_none() {
            if let Some(v) = part.strip_prefix("CN=") {
                cn = Some(v.to_string());
                continue;
            }
        }
        if serial.is_none() {
            let val = part
                .strip_prefix("SERIALNUMBER=")
                .or_else(|| part.strip_prefix("serialNumber="))
                .or_else(|| part.strip_prefix("OID.2.5.4.5="))
                .or_else(|| part.strip_prefix("2.5.4.5="));
            if let Some(v) = val {
                let digits: String = v
                    .trim_start_matches("HR")
                    .trim_start_matches("hr")
                    .chars()
                    .filter(|c| c.is_ascii_digit())
                    .collect();
                if !digits.is_empty() {
                    serial = Some(digits);
                }
            }
        }
    }

    (cn, serial)
}

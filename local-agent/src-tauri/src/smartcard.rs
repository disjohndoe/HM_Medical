use log::{debug, warn};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct SmartCardStatus {
    pub reader_available: bool,
    pub card_inserted: bool,
    pub card_holder: Option<String>,
}

/// Check smart card reader and card status via PC/SC (Windows WinSCard).
pub fn check_card_status() -> SmartCardStatus {
    let ctx = match pcsc::Context::establish(pcsc::Scope::User) {
        Ok(ctx) => ctx,
        Err(e) => {
            debug!("PC/SC context failed: {}", e);
            return SmartCardStatus {
                reader_available: false,
                card_inserted: false,
                card_holder: None,
            };
        }
    };

    // List readers
    let readers_buf = match ctx.list_readers_len() {
        Ok(len) => {
            let mut buf = vec![0u8; len];
            match ctx.list_readers(&mut buf) {
                Ok(readers) => {
                    let names: Vec<String> = readers.map(|r| r.to_string_lossy().into_owned()).collect();
                    names
                }
                Err(e) => {
                    debug!("Failed to list readers: {}", e);
                    return SmartCardStatus {
                        reader_available: false,
                        card_inserted: false,
                        card_holder: None,
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
            };
        }
    };

    if readers_buf.is_empty() {
        return SmartCardStatus {
            reader_available: false,
            card_inserted: false,
            card_holder: None,
        };
    }

    debug!("Found {} reader(s): {:?}", readers_buf.len(), readers_buf);

    // Check if any reader has a card inserted
    for reader_name in &readers_buf {
        let reader_cstr = match std::ffi::CString::new(reader_name.as_str()) {
            Ok(c) => c,
            Err(_) => continue,
        };

        // Try to connect to the card
        match ctx.connect(
            &reader_cstr,
            pcsc::ShareMode::Shared,
            pcsc::Protocols::ANY,
        ) {
            Ok(_card) => {
                debug!("Card detected in reader: {}", reader_name);
                return SmartCardStatus {
                    reader_available: true,
                    card_inserted: true,
                    card_holder: None, // TODO: read cardholder name from AKD cert
                };
            }
            Err(pcsc::Error::NoSmartcard) | Err(pcsc::Error::RemovedCard) => {
                debug!("Reader '{}' — no card inserted", reader_name);
            }
            Err(e) => {
                warn!("Reader '{}' — connect error: {}", reader_name, e);
            }
        }
    }

    SmartCardStatus {
        reader_available: true,
        card_inserted: false,
        card_holder: None,
    }
}

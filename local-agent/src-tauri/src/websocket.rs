use std::sync::Arc;
use std::time::Duration;

use base64::Engine as _;
use futures_util::{SinkExt, StreamExt};
use log::{error, info, warn};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::sync::Mutex as StdMutex;
use curl::easy::{Easy2, Handler, WriteError, InfoType, List, PostRedirections, SslOpt};
use tokio::sync::{mpsc, watch, RwLock};
use tokio_tungstenite::tungstenite::Message;

use crate::smartcard::{check_card_status, readers_to_json};
use crate::vpn::check_vpn_status;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConnectionState {
    pub ws_connected: bool,
    pub card_inserted: bool,
    pub card_holder: Option<String>,
    pub vpn_connected: bool,
    pub vpn_name: Option<String>,
    pub reader_available: bool,
    pub last_error: Option<String>,
    pub agent_id: Option<String>,
    pub readers: Vec<serde_json::Value>,
    pub configured: bool,
    pub backend_url: Option<String>,
    pub pairing_status: Option<String>,
}

impl Default for ConnectionState {
    fn default() -> Self {
        Self {
            ws_connected: false,
            card_inserted: false,
            card_holder: None,
            vpn_connected: false,
            vpn_name: None,
            reader_available: false,
            last_error: None,
            agent_id: None,
            readers: vec![],
            configured: false,
            backend_url: None,
            pairing_status: None,
        }
    }
}

pub type SharedState = Arc<RwLock<ConnectionState>>;

/// Channel to signal the WebSocket reconnection loop to stop.
/// Send `true` to cancel; the loop checks each iteration.
pub type CancelTx = watch::Sender<bool>;

/// Snapshot of card + VPN status, collected on a blocking thread.
struct StatusSnapshot {
    reader_available: bool,
    card_inserted: bool,
    card_holder: Option<String>,
    vpn_connected: bool,
    vpn_name: Option<String>,
    readers_json: Vec<serde_json::Value>,
    ws_message: serde_json::Value,
}

/// Collect card + VPN status (blocking I/O — call via spawn_blocking).
fn collect_status() -> StatusSnapshot {
    let card = check_card_status();
    let vpn = check_vpn_status();
    let readers_json = readers_to_json(&card.readers);
    let ws_message = json!({
        "type": "status",
        "card_inserted": card.card_inserted,
        "card_holder": card.card_holder,
        "card_serial": card.card_serial,
        "card_subject_oib": card.card_subject_oib,
        "reader_available": card.reader_available,
        "vpn_connected": vpn.connected,
        "vpn_name": vpn.connection_name,
        "readers": &readers_json,
    });
    StatusSnapshot {
        reader_available: card.reader_available,
        card_inserted: card.card_inserted,
        card_holder: card.card_holder,
        vpn_connected: vpn.connected,
        vpn_name: vpn.connection_name,
        readers_json,
        ws_message,
    }
}

/// Apply a status snapshot to shared state.
async fn apply_status(state: &SharedState, snap: &StatusSnapshot) {
    let mut s = state.write().await;
    s.reader_available = snap.reader_available;
    s.card_inserted = snap.card_inserted;
    s.card_holder = snap.card_holder.clone();
    s.vpn_connected = snap.vpn_connected;
    s.vpn_name = snap.vpn_name.clone();
    s.readers = snap.readers_json.clone();
}

// ---------------------------------------------------------------------------
// In-process libcurl session for CEZIH mTLS (smart card via SChannel)
// ---------------------------------------------------------------------------
// Why libcurl instead of curl.exe subprocess:
//   1. certws2:8443 requires client cert at TLS level on EVERY request (no cert → 406)
//   2. Windows Smart Card CSP caches PIN per-process — each curl.exe = new PIN prompt
//   3. libcurl runs in the agent process → PIN cached for process lifetime → one prompt
// ---------------------------------------------------------------------------

/// Collects the HTTP response body from libcurl.
struct CezihCollector {
    response_body: Vec<u8>,
}

impl Handler for CezihCollector {
    fn write(&mut self, data: &[u8]) -> Result<usize, WriteError> {
        self.response_body.extend_from_slice(data);
        Ok(data.len())
    }

    fn debug(&mut self, kind: InfoType, data: &[u8]) {
        // Log curl verbose output for TLS/cert diagnostics
        let text = String::from_utf8_lossy(data);
        let prefix = match kind {
            InfoType::Text => "* ",
            InfoType::HeaderIn => "< ",
            InfoType::HeaderOut => "> ",
            _ => return, // Skip raw data (SSL/body bytes)
        };
        for line in text.lines() {
            if !line.is_empty() {
                info!("curl {}{}", prefix, line);
            }
        }
    }
}

/// Shared libcurl session — created once per WS connection.
/// PIN is prompted on first TLS handshake, cached for process lifetime.
/// StdMutex (not tokio) because libcurl is synchronous (used in spawn_blocking).
type CezihSession = Arc<StdMutex<Easy2<CezihCollector>>>;

/// Create a new libcurl session configured for CEZIH mTLS.
fn create_cezih_session() -> Easy2<CezihCollector> {
    let mut easy = Easy2::new(CezihCollector { response_body: vec![] });

    // SChannel auto client cert selection (= curl --ssl-auto-client-cert)
    let mut ssl_opts = SslOpt::new();
    ssl_opts.auto_client_cert(true);
    easy.ssl_options(&ssl_opts).expect("failed to set SSL options");

    // Follow redirects (Keycloak auth: certws2 → certsso2 → certws2)
    easy.follow_location(true).expect("failed to set follow_location");

    // Maintain POST method+body through 301/302/303 redirects.
    // Without this, libcurl converts POST→GET on 302 (RFC 7231 default),
    // which causes CEZIH $process-message to fail (empty body → ERR_DS_1002).
    easy.post_redirections(PostRedirections::new().redirect_all(true))
        .expect("failed to set post_redirections");

    // Enable in-memory cookie engine (no file needed)
    easy.cookie_list("").expect("failed to enable cookie engine");

    // Request timeout
    easy.timeout(Duration::from_secs(30)).expect("failed to set timeout");

    // Accept uncompressed responses only (prevent gzip decoding issues)
    easy.accept_encoding("identity").expect("failed to set accept_encoding");

    easy
}

/// Apply persistent session options after reset().
/// reset() preserves cookies/connections but clears all options.
fn apply_session_defaults(easy: &mut Easy2<CezihCollector>) -> Result<(), String> {
    let mut ssl_opts = SslOpt::new();
    ssl_opts.auto_client_cert(true);
    easy.ssl_options(&ssl_opts).map_err(|e| e.to_string())?;
    easy.follow_location(true).map_err(|e| e.to_string())?;
    easy.post_redirections(PostRedirections::new().redirect_all(true))
        .map_err(|e| e.to_string())?;
    easy.cookie_list("").map_err(|e| e.to_string())?;
    easy.timeout(Duration::from_secs(30)).map_err(|e| e.to_string())?;
    easy.accept_encoding("identity").map_err(|e| e.to_string())?;
    Ok(())
}

/// Execute a single CEZIH HTTP request via libcurl. Synchronous — call from spawn_blocking.
/// Returns raw response bytes to preserve binary content (e.g., PDF documents).
fn do_cezih_request(
    session: &mut Easy2<CezihCollector>,
    method: &str,
    url: &str,
    headers: &[(String, String)],
    body: Option<&[u8]>,
) -> Result<(u32, Vec<u8>), String> {
    // Reset per-request state, preserve cookies + connections
    session.reset();
    session.get_mut().response_body.clear();
    apply_session_defaults(session)?;

    // URL
    session.url(url).map_err(|e| e.to_string())?;

    // Pass ALL headers including Authorization — encounter-services may need Bearer token
    // even on port 8443 (mTLS provides cert identity, Bearer provides auth context).
    let mut list = List::new();
    for (k, v) in headers {
        list.append(&format!("{}: {}", k, v)).map_err(|e| e.to_string())?;
    }
    // Disable Expect: 100-continue (libcurl default on POST, CEZIH may not support)
    list.append("Expect:").map_err(|e| e.to_string())?;
    session.http_headers(list).map_err(|e| e.to_string())?;

    // Method + body
    match method.to_uppercase().as_str() {
        "GET" => {
            session.get(true).map_err(|e| e.to_string())?;
        }
        "POST" => {
            session.post(true).map_err(|e| e.to_string())?;
            session.post_fields_copy(body.unwrap_or(b"")).map_err(|e| e.to_string())?;
        }
        "DELETE" => {
            session.custom_request("DELETE").map_err(|e| e.to_string())?;
        }
        other => {
            // PUT, PATCH, etc. — use custom_request + post_fields_copy (WITHOUT post(true)
            // which would override the method back to POST)
            session.custom_request(other).map_err(|e| e.to_string())?;
            if let Some(b) = body {
                // post_fields_copy sets body without overriding custom method
                session.post_fields_copy(b).map_err(|e| e.to_string())?;
            }
        }
    }

    // Enable verbose mode for POST to encounter-services (debug ERR_DS_1002)
    if method.eq_ignore_ascii_case("POST") && url.contains("encounter-services") {
        session.verbose(true).map_err(|e| e.to_string())?;
        info!("Verbose curl enabled for POST to encounter-services");
    }

    // Execute (blocking — PIN prompted on first TLS handshake, cached after)
    session.perform().map_err(|e| format!("curl: {}", e))?;

    let status = session.response_code().map_err(|e| e.to_string())?;
    let resp_bytes = session.get_ref().response_body.clone();

    // Diagnostic logging for POST failures (helps debug CEZIH $process-message issues)
    if method.eq_ignore_ascii_case("POST") && status >= 400 {
        let resp_preview = String::from_utf8_lossy(&resp_bytes[..resp_bytes.len().min(2000)]);
        warn!("POST {} — status {} — body (first 2000): {}", url, status, resp_preview);
    }

    // Retry when the request hit Keycloak auth instead of the FHIR service.
    // This happens on first request before mTLS session cookie is established.
    //
    // For POST requests: Keycloak rejects POST with application/fhir+json body
    // (415 Unsupported Media Type) and the redirect chain never completes, so
    // the session cookie is NEVER set.  Fix: do a GET to the same URL first to
    // establish the session cookie (GET goes through Keycloak redirect cleanly),
    // then retry the POST.
    //
    // For GET requests: the first attempt goes through the redirect chain and
    // establishes the cookie.  Simple retry is sufficient.
    let resp_str = String::from_utf8_lossy(&resp_bytes);
    let resp_has_auth_path = resp_str.contains("/auth/realms/") || resp_str.contains("openid-connect");
    let should_retry = status == 406
        || status == 415
        || (resp_str.starts_with('<') && !resp_bytes.is_empty())
        || (method.eq_ignore_ascii_case("POST") && resp_bytes.is_empty() && status < 400)
        || resp_has_auth_path;
    if should_retry {
        // For POST/PUT/PATCH: first do a GET warmup to establish the session cookie.
        // Keycloak accepts GET (no body) but rejects POST with FHIR Content-Type.
        if !method.eq_ignore_ascii_case("GET") && !method.eq_ignore_ascii_case("DELETE") {
            info!("Got {} (redirect/session issue) — GET warmup to establish session before retrying {}", status, method);
            session.reset();
            session.get_mut().response_body.clear();
            apply_session_defaults(session)?;
            session.url(url).map_err(|e| e.to_string())?;

            // Pass Authorization header for the warmup GET
            let mut warmup_list = List::new();
            for (k, v) in headers {
                if k.eq_ignore_ascii_case("Authorization") || k.eq_ignore_ascii_case("Accept") {
                    warmup_list.append(&format!("{}: {}", k, v)).map_err(|e| e.to_string())?;
                }
            }
            warmup_list.append("Expect:").map_err(|e| e.to_string())?;
            session.http_headers(warmup_list).map_err(|e| e.to_string())?;

            session.get(true).map_err(|e| e.to_string())?;
            match session.perform() {
                Ok(()) => {
                    let warmup_status = session.response_code().unwrap_or(0);
                    info!("GET warmup completed — status {} (cookie should be set now)", warmup_status);
                }
                Err(e) => {
                    warn!("GET warmup failed: {} — retrying {} anyway", e, method);
                }
            }
        } else {
            info!("Got {} (redirect/session issue) — retrying with session cookie", status);
        }

        // Now retry the original request (session cookie should be set)
        session.reset();
        session.get_mut().response_body.clear();
        apply_session_defaults(session)?;
        session.url(url).map_err(|e| e.to_string())?;

        let mut list = List::new();
        for (k, v) in headers {
            list.append(&format!("{}: {}", k, v)).map_err(|e| e.to_string())?;
        }
        list.append("Expect:").map_err(|e| e.to_string())?;
        session.http_headers(list).map_err(|e| e.to_string())?;

        match method.to_uppercase().as_str() {
            "GET" => { session.get(true).map_err(|e| e.to_string())?; }
            "POST" => {
                session.post(true).map_err(|e| e.to_string())?;
                session.post_fields_copy(body.unwrap_or(b"")).map_err(|e| e.to_string())?;
            }
            "DELETE" => { session.custom_request("DELETE").map_err(|e| e.to_string())?; }
            other => {
                session.custom_request(other).map_err(|e| e.to_string())?;
                if let Some(b) = body {
                    session.post_fields_copy(b).map_err(|e| e.to_string())?;
                }
            }
        }

        session.perform().map_err(|e| format!("curl retry: {}", e))?;
        let status = session.response_code().map_err(|e| e.to_string())?;
        let resp_bytes = session.get_ref().response_body.clone();
        if !method.eq_ignore_ascii_case("GET") {
            let preview = String::from_utf8_lossy(&resp_bytes[..resp_bytes.len().min(500)]);
            info!("{} retry — status {} — body (first 500): {}", method, status, preview);
        }
        return Ok((status, resp_bytes));
    }

    Ok((status, resp_bytes))
}

/// Handle an HTTP proxy request using in-process libcurl with SChannel mTLS.
/// PIN is prompted once (first TLS handshake), then cached for process lifetime.
async fn handle_http_proxy(msg: serde_json::Value, session: CezihSession) -> String {
    let request_id = msg.get("request_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let method = msg.get("method").and_then(|v| v.as_str()).unwrap_or("GET").to_string();
    let url = msg.get("url").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let headers_val = msg.get("headers").cloned();
    let body_val = msg.get("body").cloned();

    let rid = request_id[..request_id.len().min(8)].to_string();

    // Parse headers
    let hdrs: Vec<(String, String)> = headers_val
        .as_ref()
        .and_then(|h| h.as_object())
        .map(|obj| obj.iter().filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string()))).collect())
        .unwrap_or_default();

    // Serialize body
    let body_bytes: Option<Vec<u8>> = body_val.as_ref().and_then(|b| {
        if b.is_null() { None }
        else if b.is_string() { Some(b.as_str().unwrap_or("").as_bytes().to_vec()) }
        else { Some(b.to_string().into_bytes()) }
    });

    // Execute on blocking thread (libcurl is synchronous, StdMutex serializes access)
    match tokio::task::spawn_blocking(move || {
        let mut s = session.lock().map_err(|e| format!("Session lock poisoned: {}", e))?;
        do_cezih_request(&mut s, &method, &url, &hdrs, body_bytes.as_deref())
    }).await {
        Ok(Ok((status, body_raw))) => {
            // Detect if response is valid UTF-8 JSON or binary content
            let (body_text, body_bytes_b64) = match String::from_utf8(body_raw.clone()) {
                Ok(s) if s.starts_with('{') || s.starts_with('[') || s.starts_with('<') => {
                    // Valid UTF-8 text (JSON or HTML/XML error) — return as body
                    (s, serde_json::Value::Null)
                }
                _ => {
                    // Binary content (PDF, etc.) — base64 encode for transport
                    let b64 = base64::engine::general_purpose::STANDARD.encode(&body_raw);
                    ("".to_string(), serde_json::Value::String(b64))
                }
            };
            let preview = String::from_utf8_lossy(&body_raw[..body_raw.len().min(500)]);
            info!("HTTP proxy {} — {} ({} bytes) preview: {}", rid, status, body_raw.len(), preview);
            json!({
                "type": "http_proxy_response",
                "request_id": request_id,
                "status_code": status,
                "headers": {},
                "body": body_text,
                "body_bytes": body_bytes_b64
            }).to_string()
        }
        Ok(Err(e)) => {
            error!("HTTP proxy {} failed: {}", rid, e);
            json!({
                "type": "http_proxy_response",
                "request_id": request_id,
                "error": e
            }).to_string()
        }
        Err(e) => {
            error!("HTTP proxy {} task panicked: {}", rid, e);
            json!({
                "type": "http_proxy_response",
                "request_id": request_id,
                "error": format!("Internal error: {}", e)
            }).to_string()
        }
    }
}

/// Spawn a WebSocket connection task that reconnects with exponential backoff.
/// Returns a `CancelTx` that, when sent `true`, stops the reconnection loop.
pub fn spawn_connection_task(
    backend_url: String,
    tenant_id: String,
    agent_secret: String,
    initial_agent_id: Option<String>,
    state: SharedState,
) -> CancelTx {
    let (cancel_tx, mut cancel_rx) = watch::channel(false);

    tauri::async_runtime::spawn(async move {
        let mut backoff = Duration::from_secs(1);
        let max_backoff = Duration::from_secs(60);

        // Agent ID persists across reconnections within this process
        let mut agent_id: Option<String> = initial_agent_id;

        loop {
            // Check cancellation before each connection attempt
            if *cancel_rx.borrow() {
                info!("WebSocket task cancelled — stopping reconnection loop");
                break;
            }

            // Connect WITHOUT credentials in URL — auth is sent as first message
            let ws_url = format!("{}ws/agent", backend_url);
            info!("Connecting to {}", ws_url);

            match tokio::time::timeout(
                Duration::from_secs(15),
                tokio_tungstenite::connect_async(&ws_url),
            ).await {
                Ok(Ok((ws_stream, _))) => {
                    info!("WebSocket TCP connected (awaiting auth confirmation)");

                    let (mut write, mut read) = ws_stream.split();

                    // Send auth message IMMEDIATELY as first message (credentials NOT in URL)
                    let auth_msg = json!({
                        "type": "auth",
                        "tenant_id": tenant_id,
                        "agent_secret": agent_secret,
                        "agent_id": agent_id,
                    });
                    if write.send(Message::Text(auth_msg.to_string().into())).await.is_err() {
                        error!("Failed to send auth message");
                        break;
                    }

                    // Channel for spawned tasks to send WS messages (e.g., HTTP proxy responses)
                    let (outbound_tx, mut outbound_rx) = mpsc::channel::<String>(32);

                    // Shared libcurl session — PIN cached for process lifetime.
                    let cezih_session: CezihSession = Arc::new(StdMutex::new(create_cezih_session()));

                    // Don't set ws_connected yet — wait for server "connected" confirmation
                    {
                        let mut s = state.write().await;
                        s.last_error = None;
                    }
                    let mut status_interval = tokio::time::interval(Duration::from_secs(10));

                    loop {
                        tokio::select! {
                            msg = read.next() => {
                                match msg {
                                    Some(Ok(Message::Text(text))) => {
                                        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                                            let msg_type = parsed.get("type").and_then(|t| t.as_str()).unwrap_or("");
                                            match msg_type {
                                                "connected" => {
                                                    info!("Server confirmed connection: {}", parsed.get("message").and_then(|m| m.as_str()).unwrap_or(""));
                                                    // Auth confirmed — NOW mark as connected and reset backoff
                                                    backoff = Duration::from_secs(1);
                                                    {
                                                        let mut s = state.write().await;
                                                        s.ws_connected = true;
                                                    }
                                                    // Persist agent_id from server
                                                    if let Some(id) = parsed.get("agent_id").and_then(|v| v.as_str()) {
                                                        agent_id = Some(id.to_string());
                                                        let mut s = state.write().await;
                                                        s.agent_id = Some(id.to_string());
                                                        info!("Agent ID: {}", id);
                                                    }
                                                    // Send initial status (blocking I/O on thread pool, 5s timeout)
                                                    match tokio::time::timeout(
                                                        Duration::from_secs(5),
                                                        tokio::task::spawn_blocking(collect_status),
                                                    ).await {
                                                        Ok(Ok(snap)) => {
                                                            let _ = write.send(Message::Text(snap.ws_message.to_string().into())).await;
                                                            apply_status(&state, &snap).await;

                                                            // Session warmup: if VPN+card active and backend sent a
                                                            // CEZIH URL, establish the mTLS session now (single PIN
                                                            // prompt on connect instead of on first user action).
                                                            let warmup_url = parsed.get("cezih_warmup_url")
                                                                .and_then(|v| v.as_str())
                                                                .unwrap_or("")
                                                                .to_string();
                                                            if snap.vpn_connected && snap.card_inserted && !warmup_url.is_empty() {
                                                                let sess = Arc::clone(&cezih_session);
                                                                let tx = outbound_tx.clone();
                                                                tokio::spawn(async move {
                                                                    info!("Warming up CEZIH session (PIN prompt expected)...");
                                                                    let warmup_msg = json!({
                                                                        "request_id": "warmup",
                                                                        "method": "GET",
                                                                        "url": warmup_url,
                                                                        "headers": {},
                                                                    });
                                                                    let resp = handle_http_proxy(warmup_msg, sess).await;
                                                                    // Parse status code for clearer logging
                                                                    let status = serde_json::from_str::<serde_json::Value>(&resp)
                                                                        .ok()
                                                                        .and_then(|v| v.get("status_code").and_then(|s| s.as_u64()));
                                                                    match status {
                                                                        Some(code) => info!("CEZIH session established (warmup {code}) — future requests won't prompt for PIN"),
                                                                        None => warn!("CEZIH session warmup failed — PIN will be prompted on first request"),
                                                                    }
                                                                    drop(tx);
                                                                });
                                                            }
                                                        }
                                                        _ => { warn!("Initial status collection timed out or failed"); }
                                                    }
                                                }
                                                "ping" => {
                                                    let _ = write.send(Message::Text(r#"{"type":"pong"}"#.into())).await;
                                                }
                                                "sign_request" => {
                                                    let rid = parsed.get("request_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                                                    let data_b64 = parsed.get("data").and_then(|v| v.as_str()).unwrap_or("");
                                                    info!("Received sign_request {} ({} chars)", &rid[..rid.len().min(8)], data_b64.len());

                                                    // Decode base64 data and sign with smart card
                                                    let sign_result = {
                                                        let data_bytes = match base64::engine::general_purpose::STANDARD.decode(data_b64) {
                                                            Ok(b) => b,
                                                            Err(e) => {
                                                                let response = json!({
                                                                    "type": "sign_response",
                                                                    "request_id": &rid,
                                                                    "error": format!("Invalid base64 data: {}", e),
                                                                });
                                                                let _ = write.send(Message::Text(response.to_string().into())).await;
                                                                continue;
                                                            }
                                                        };
                                                        // Run signing on blocking thread (CryptoAPI may prompt for PIN)
                                                        tokio::task::spawn_blocking(move || {
                                                            crate::signing::sign_with_smartcard(&data_bytes)
                                                        }).await
                                                    };

                                                    let response = match sign_result {
                                                        Ok(Ok(result)) => {
                                                            info!("Signing successful, sig={} bytes, kid={}", result.signature.len(), &result.kid[..16]);
                                                            json!({
                                                                "type": "sign_response",
                                                                "request_id": &rid,
                                                                "signature": base64::engine::general_purpose::STANDARD.encode(&result.signature),
                                                                "kid": result.kid,
                                                            })
                                                        }
                                                        Ok(Err(e)) => {
                                                            error!("Signing failed: {}", e);
                                                            json!({
                                                                "type": "sign_response",
                                                                "request_id": &rid,
                                                                "error": e,
                                                            })
                                                        }
                                                        Err(e) => {
                                                            error!("Signing task panicked: {}", e);
                                                            json!({
                                                                "type": "sign_response",
                                                                "request_id": &rid,
                                                                "error": format!("Internal error: {}", e),
                                                            })
                                                        }
                                                    };
                                                    let _ = write.send(Message::Text(response.to_string().into())).await;
                                                }
                                                "sign_jws" => {
                                                    // JWS signing: receive bundle JSON, build JOSE header + sign
                                                    let rid = parsed.get("request_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                                                    let data_b64 = parsed.get("data").and_then(|v| v.as_str()).unwrap_or("");
                                                    // Optional extra x5c chain certs (intermediate, root) in base64-std DER
                                                    let extra_certs: Vec<String> = parsed.get("extra_certs")
                                                        .and_then(|v| v.as_array())
                                                        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
                                                        .unwrap_or_default();
                                                    info!("Received sign_jws {} ({} chars, {} extra_certs)", &rid[..rid.len().min(8)], data_b64.len(), extra_certs.len());

                                                    let sign_result = {
                                                        let data_bytes = match base64::engine::general_purpose::STANDARD.decode(data_b64) {
                                                            Ok(b) => b,
                                                            Err(e) => {
                                                                let response = json!({
                                                                    "type": "sign_jws_response",
                                                                    "request_id": &rid,
                                                                    "error": format!("Invalid base64 data: {}", e),
                                                                });
                                                                let _ = write.send(Message::Text(response.to_string().into())).await;
                                                                continue;
                                                            }
                                                        };
                                                        tokio::task::spawn_blocking(move || {
                                                            crate::signing::sign_for_jws(&data_bytes, &extra_certs)
                                                        }).await
                                                    };

                                                    let response = match sign_result {
                                                        Ok(Ok(result)) => {
                                                            info!("JWS signing OK: alg={}, jws_b64={} chars, kid={:.16}", result.algorithm, result.jws_base64.len(), result.kid);
                                                            json!({
                                                                "type": "sign_jws_response",
                                                                "request_id": &rid,
                                                                "jws_base64": result.jws_base64,
                                                                "kid": result.kid,
                                                                "algorithm": result.algorithm,
                                                            })
                                                        }
                                                        Ok(Err(e)) => {
                                                            // NCrypt failed — try CMS fallback
                                                            warn!("JWS signing failed ({}), trying CMS fallback", e);
                                                            json!({
                                                                "type": "sign_jws_response",
                                                                "request_id": &rid,
                                                                "error": e,
                                                            })
                                                        }
                                                        Err(e) => {
                                                            error!("JWS signing task panicked: {}", e);
                                                            json!({
                                                                "type": "sign_jws_response",
                                                                "request_id": &rid,
                                                                "error": format!("Internal error: {}", e),
                                                            })
                                                        }
                                                    };
                                                    let _ = write.send(Message::Text(response.to_string().into())).await;
                                                }
                                                "get_cert_info" => {
                                                    let rid = parsed.get("request_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                                                    info!("Received get_cert_info {}", &rid[..rid.len().min(8)]);

                                                    let result = tokio::task::spawn_blocking(|| {
                                                        crate::signing::get_cert_info()
                                                    }).await;

                                                    let response = match result {
                                                        Ok(Ok(info)) => {
                                                            let cert_b64 = base64::engine::general_purpose::STANDARD.encode(&info.cert_der);
                                                            info!("Cert info OK: kid={:.16}, alg={}, cert_der={} bytes", info.kid, info.algorithm, info.cert_der.len());
                                                            json!({
                                                                "type": "get_cert_info_response",
                                                                "request_id": &rid,
                                                                "kid": info.kid,
                                                                "algorithm": info.algorithm,
                                                                "cert_der_base64": cert_b64,
                                                            })
                                                        }
                                                        Ok(Err(e)) => {
                                                            error!("get_cert_info failed: {}", e);
                                                            json!({
                                                                "type": "get_cert_info_response",
                                                                "request_id": &rid,
                                                                "error": e,
                                                            })
                                                        }
                                                        Err(e) => {
                                                            error!("get_cert_info task panicked: {}", e);
                                                            json!({
                                                                "type": "get_cert_info_response",
                                                                "request_id": &rid,
                                                                "error": format!("Internal error: {}", e),
                                                            })
                                                        }
                                                    };
                                                    let _ = write.send(Message::Text(response.to_string().into())).await;
                                                }
                                                "sign_raw" => {
                                                    let rid = parsed.get("request_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                                                    let data_b64 = parsed.get("data").and_then(|v| v.as_str()).unwrap_or("");
                                                    let algorithm = parsed.get("algorithm").and_then(|v| v.as_str()).unwrap_or("RS256");
                                                    info!("Received sign_raw {} ({} chars, alg={})", &rid[..rid.len().min(8)], data_b64.len(), algorithm);

                                                    let sign_result = {
                                                        let data_bytes = match base64::engine::general_purpose::STANDARD.decode(data_b64) {
                                                            Ok(b) => b,
                                                            Err(e) => {
                                                                let response = json!({
                                                                    "type": "sign_raw_response",
                                                                    "request_id": &rid,
                                                                    "error": format!("Invalid base64 data: {}", e),
                                                                });
                                                                let _ = write.send(Message::Text(response.to_string().into())).await;
                                                                continue;
                                                            }
                                                        };
                                                        let alg = algorithm.to_string();
                                                        tokio::task::spawn_blocking(move || {
                                                            crate::signing::sign_raw(&data_bytes, &alg)
                                                        }).await
                                                    };

                                                    let response = match sign_result {
                                                        Ok(Ok(result)) => {
                                                            info!("Raw signing OK: alg={}, sig={} bytes, kid={:.16}",
                                                                  result.algorithm, result.signature.len(), result.kid);
                                                            json!({
                                                                "type": "sign_raw_response",
                                                                "request_id": &rid,
                                                                "signature": base64::engine::general_purpose::STANDARD.encode(&result.signature),
                                                                "kid": result.kid,
                                                                "algorithm": result.algorithm,
                                                            })
                                                        }
                                                        Ok(Err(e)) => {
                                                            error!("Raw signing failed: {}", e);
                                                            json!({
                                                                "type": "sign_raw_response",
                                                                "request_id": &rid,
                                                                "error": e,
                                                            })
                                                        }
                                                        Err(e) => {
                                                            error!("Raw signing task panicked: {}", e);
                                                            json!({
                                                                "type": "sign_raw_response",
                                                                "request_id": &rid,
                                                                "error": format!("Internal error: {}", e),
                                                            })
                                                        }
                                                    };
                                                    let _ = write.send(Message::Text(response.to_string().into())).await;
                                                }
                                                "http_proxy_request" => {
                                                    let rid = parsed.get("request_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                                                    info!("HTTP proxy request {} — {} {}",
                                                        &rid[..rid.len().min(8)],
                                                        parsed.get("method").and_then(|v| v.as_str()).unwrap_or("?"),
                                                        parsed.get("url").and_then(|v| v.as_str()).unwrap_or("?"));
                                                    let tx = outbound_tx.clone();
                                                    let p = parsed.clone();
                                                    let sess = Arc::clone(&cezih_session);
                                                    tokio::spawn(async move {
                                                        let resp = handle_http_proxy(p, sess).await;
                                                        let _ = tx.send(resp).await;
                                                    });
                                                }
                                                other => {
                                                    warn!("Unknown message type: {}", other);
                                                }
                                            }
                                        }
                                    }
                                    Some(Ok(Message::Ping(data))) => {
                                        let _ = write.send(Message::Pong(data)).await;
                                    }
                                    Some(Ok(Message::Close(_))) | None => {
                                        info!("WebSocket closed by server");
                                        break;
                                    }
                                    Some(Err(e)) => {
                                        error!("WebSocket error: {}", e);
                                        break;
                                    }
                                    _ => {}
                                }
                            }
                            // Forward outbound messages from spawned tasks (HTTP proxy responses)
                            Some(outbound_msg) = outbound_rx.recv() => {
                                if write.send(Message::Text(outbound_msg.into())).await.is_err() {
                                    break;
                                }
                            }
                            _ = status_interval.tick() => {
                                match tokio::time::timeout(
                                    Duration::from_secs(5),
                                    tokio::task::spawn_blocking(collect_status),
                                ).await {
                                    Ok(Ok(snap)) => {
                                        if write.send(Message::Text(snap.ws_message.to_string().into())).await.is_err() {
                                            break;
                                        }
                                        apply_status(&state, &snap).await;
                                    }
                                    _ => { warn!("Status collection timed out or failed — skipping heartbeat"); }
                                }
                            }
                            _ = cancel_rx.changed() => {
                                if *cancel_rx.borrow() {
                                    info!("WebSocket task cancelled — closing active connection");
                                    let _ = write.send(Message::Close(None)).await;
                                    break;
                                }
                            }
                        }
                    }

                    // Disconnected
                    {
                        let mut s = state.write().await;
                        s.ws_connected = false;
                    }
                }
                Ok(Err(e)) => {
                    let mut s = state.write().await;
                    s.ws_connected = false;
                    s.last_error = Some(format!("{}", e));
                    warn!("Connection failed: {}", e);
                }
                Err(_) => {
                    warn!("WebSocket connection timed out after 15s for {}", ws_url);
                    let mut s = state.write().await;
                    s.ws_connected = false;
                    s.last_error = Some("Veza istekla (timeout)".to_string());
                }
            }

            // Wait before reconnecting — abort early if cancelled
            info!("Reconnecting in {:?}...", backoff);
            tokio::select! {
                _ = tokio::time::sleep(backoff) => {}
                _ = cancel_rx.changed() => {
                    if *cancel_rx.borrow() {
                        info!("WebSocket task cancelled during backoff — stopping");
                        break;
                    }
                }
            }
            backoff = (backoff * 2).min(max_backoff);
        }
    });

    cancel_tx
}

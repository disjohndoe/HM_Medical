mod signing;
mod smartcard;
mod vpn;
mod websocket;

use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

use log::{error, info, warn};
use url::Url;
use serde::{Deserialize, Serialize};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::Manager;
use tokio::sync::RwLock;
use tauri_plugin_deep_link::DeepLinkExt;

use websocket::{CancelTx, ConnectionState, SharedState};

/// Holds the cancellation sender for the active WebSocket task.
/// Wrapped in Arc<RwLock<..>> so it can be swapped on re-pair.
type WsCancelHandle = Arc<RwLock<Option<CancelTx>>>;

// --- Config persistence ---
//
// Security: tenant_id and backend_url are stored in a plain JSON file
// (not secrets). The agent_secret is stored in the OS credential store
// (Windows Credential Manager / macOS Keychain / Linux keyring) via the
// `keyring` crate — encrypted at rest with DPAPI on Windows.

const KEYRING_SERVICE: &str = "hm-digital-agent";
const KEYRING_USERNAME: &str = "agent-secret";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub tenant_id: String,
    pub agent_secret: String,
    pub backend_url: String,
}

/// Non-secret fields persisted in a JSON file.
#[derive(Debug, Serialize, Deserialize)]
struct ConfigFile {
    tenant_id: String,
    backend_url: String,
}

fn config_dir() -> Option<PathBuf> {
    dirs::config_dir().map(|p| p.join("hm-digital-agent"))
}

fn config_file_path() -> Option<PathBuf> {
    config_dir().map(|p| p.join("config.json"))
}

/// Read the agent_secret from the OS credential store.
fn read_secret_from_keyring() -> Option<String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_USERNAME).ok()?;
    match entry.get_password() {
        Ok(secret) => Some(secret),
        Err(keyring::Error::NoEntry) => None,
        Err(e) => {
            error!("Failed to read secret from credential store: {}", e);
            None
        }
    }
}

/// Write the agent_secret to the OS credential store.
fn write_secret_to_keyring(secret: &str) -> Result<(), String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_USERNAME)
        .map_err(|e| format!("Cannot create keyring entry: {}", e))?;
    entry.set_password(secret)
        .map_err(|e| format!("Cannot save secret to credential store: {}", e))?;
    info!("Agent secret saved to OS credential store");
    Ok(())
}

/// Delete the agent_secret from the OS credential store.
fn delete_secret_from_keyring() -> Result<(), String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_USERNAME)
        .map_err(|e| format!("Cannot create keyring entry: {}", e))?;
    match entry.delete_credential() {
        Ok(()) => {
            info!("Agent secret removed from OS credential store");
            Ok(())
        }
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(format!("Cannot delete secret from credential store: {}", e)),
    }
}

/// Load full config: non-secret fields from JSON file + secret from keyring.
fn load_config() -> Option<AppConfig> {
    let path = config_file_path()?;
    if !path.exists() {
        return None;
    }
    let content = fs::read_to_string(&path).ok()?;
    let file_config: ConfigFile = serde_json::from_str(&content).ok()?;

    let agent_secret = read_secret_from_keyring()?;

    info!("Loaded config from {} + credential store", path.display());
    Some(AppConfig {
        tenant_id: file_config.tenant_id,
        agent_secret,
        backend_url: file_config.backend_url,
    })
}

/// Save full config: non-secret fields to JSON file, secret to keyring.
fn save_config(config: &AppConfig) -> Result<(), String> {
    // Save non-secret fields to JSON
    let dir = config_dir().ok_or("Cannot determine config directory")?;
    fs::create_dir_all(&dir).map_err(|e| format!("Cannot create config dir: {}", e))?;
    let path = dir.join("config.json");
    let file_config = ConfigFile {
        tenant_id: config.tenant_id.clone(),
        backend_url: config.backend_url.clone(),
    };
    let content = serde_json::to_string_pretty(&file_config)
        .map_err(|e| format!("Cannot serialize config: {}", e))?;
    fs::write(&path, content).map_err(|e| format!("Cannot write config: {}", e))?;
    info!("Saved config to {}", path.display());

    // Save secret to OS credential store
    write_secret_to_keyring(&config.agent_secret)?;

    Ok(())
}

/// Clear all stored config: JSON file + keyring secret.
fn clear_config() -> Result<(), String> {
    if let Some(path) = config_file_path() {
        if path.exists() {
            fs::remove_file(&path).map_err(|e| format!("Cannot remove config: {}", e))?;
            info!("Removed config file");
        }
    }
    delete_secret_from_keyring()?;
    Ok(())
}

/// Attempt to load config from file first, then fall back to env vars.
fn resolve_config() -> Option<AppConfig> {
    // 1. Try persisted config (JSON + keyring)
    if let Some(config) = load_config() {
        return Some(config);
    }

    // 2. Try env vars (dev fallback)
    let tenant_id = std::env::var("HM_TENANT_ID").ok()?;
    let agent_secret = std::env::var("HM_AGENT_SECRET").ok()?;
    let backend_url = std::env::var("HM_BACKEND_URL")
        .unwrap_or_else(|_| "ws://localhost:8000/".to_string());

    Some(AppConfig {
        tenant_id,
        agent_secret,
        backend_url,
    })
}

/// Derive the base HTTP URL from the WebSocket URL for API calls.
fn ws_to_http_url(ws_url: &str) -> String {
    ws_url
        .replace("wss://", "https://")
        .replace("ws://", "http://")
        .trim_end_matches('/')
        .to_string()
}

// --- Tauri commands ---

#[tauri::command]
async fn get_connection_state(state: tauri::State<'_, SharedState>) -> Result<ConnectionState, String> {
    Ok(state.read().await.clone())
}

#[tauri::command]
async fn get_config(_state: tauri::State<'_, SharedState>) -> Result<Option<AppConfig>, String> {
    // Mask the secret in the response — frontend doesn't need the raw value
    Ok(load_config().map(|mut c| {
        let len = c.agent_secret.len();
        c.agent_secret = if len >= 8 {
            format!("{}…{}", &c.agent_secret[..4], &c.agent_secret[len-4..])
        } else {
            "***".to_string()
        };
        c
    }))
}

#[tauri::command]
async fn clear_config_cmd(
    state: tauri::State<'_, SharedState>,
    ws_cancel: tauri::State<'_, WsCancelHandle>,
) -> Result<(), String> {
    clear_config()?;

    // Cancel the active WebSocket reconnection loop
    if let Some(tx) = ws_cancel.write().await.take() {
        let _ = tx.send(true);
        info!("Cancelled active WebSocket connection task");
    }

    let mut s = state.write().await;
    *s = websocket::ConnectionState::default();
    s.last_error = Some("Agent isključen — konfiguracija obrisana".to_string());
    Ok(())
}

/// Allowed backend hostnames for deep link pairing.
/// Prevents a crafted deep link from pointing the agent to a malicious server.
const ALLOWED_BACKENDS: &[&str] = &["app.hmdigital.hr", "localhost", "127.0.0.1"];

fn is_allowed_backend(url: &str) -> bool {
    if let Ok(parsed) = Url::parse(url) {
        if let Some(host) = parsed.host_str() {
            // Exact match against built-in list
            if ALLOWED_BACKENDS.iter().any(|&allowed| host == allowed) {
                return true;
            }
            // Allow *.hmdigital.hr subdomains (staging, test)
            if host.ends_with(".hmdigital.hr") {
                return true;
            }
            // Allow env var override for custom test environments
            if let Ok(extra) = std::env::var("HM_ALLOWED_BACKENDS") {
                return extra.split(',').any(|h| h.trim() == host);
            }
        }
    }
    false
}

/// Core pairing logic — reusable from both Tauri command and deep link handler.
/// `backend_override` comes from the deep link URL; falls back to env var then production.
async fn do_claim_pairing_token(token: String, backend_override: Option<String>, state: SharedState) -> Result<AppConfig, String> {
    info!("Claiming pairing token...");

    {
        let mut s = state.write().await;
        s.pairing_status = Some("Spremanje...".to_string());
    }

    // Backend URL priority: deep link param → env var → production default
    let backend_ws = backend_override
        .filter(|url| is_allowed_backend(url))
        .or_else(|| std::env::var("HM_BACKEND_URL").ok())
        .unwrap_or_else(|| "wss://app.hmdigital.hr/".to_string());
    let http_base = ws_to_http_url(&backend_ws);

    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{}/api/settings/pair/claim", http_base))
        .json(&serde_json::json!({ "pairing_token": token }))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("Greška pri povezivanju: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = if status.as_u16() == 410 {
            "Pairing token je istekao. Generirajte novi u postavkama.".to_string()
        } else {
            format!("Greška servera ({}): {}", status, body)
        };
        {
            let mut s = state.write().await;
            s.pairing_status = None;
            s.last_error = Some(detail.clone());
        }
        return Err(detail);
    }

    let claim: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Greška pri čitanju odgovora: {}", e))?;

    // Validate backend_url from server against allowed hosts (prevent SSRF)
    let claimed_url = claim["backend_url"].as_str().unwrap_or(&backend_ws);
    let validated_url = if is_allowed_backend(claimed_url) {
        claimed_url.to_string()
    } else {
        warn!("Server returned non-allowed backend URL: {}, using original", claimed_url);
        backend_ws.clone()
    };

    let config = AppConfig {
        tenant_id: claim["tenant_id"].as_str().unwrap_or("").to_string(),
        agent_secret: claim["agent_secret"].as_str().unwrap_or("").to_string(),
        backend_url: validated_url,
    };

    if config.tenant_id.is_empty() || config.agent_secret.is_empty() {
        return Err("Server nije vratio valjane podatke".to_string());
    }

    // Save config (JSON + keyring)
    save_config(&config)?;

    // Update state
    {
        let mut s = state.write().await;
        s.configured = true;
        s.backend_url = Some(config.backend_url.clone());
        s.pairing_status = None;
        s.last_error = None;
    }

    info!("Pairing successful — tenant: {}", &config.tenant_id[..config.tenant_id.len().min(8)]);
    Ok(config)
}

/// Tauri command wrapper for pairing (called from frontend UI).
#[tauri::command]
async fn claim_pairing_token(
    token: String,
    backend_url: Option<String>,
    state: tauri::State<'_, SharedState>,
) -> Result<AppConfig, String> {
    do_claim_pairing_token(token, backend_url, state.inner().clone()).await
}

// --- App entry point ---

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let shared_state: SharedState = Arc::new(RwLock::new(ConnectionState::default()));
    let ws_cancel: WsCancelHandle = Arc::new(RwLock::new(None));

    let state_clone = shared_state.clone();
    let ws_cancel_clone = ws_cancel.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_deep_link::init())
        .manage(shared_state.clone())
        .manage(ws_cancel.clone())
        .setup(move |app| {
            // Initialize logger
            let _ = env_logger::Builder::from_env(
                env_logger::Env::default().default_filter_or("info"),
            ).try_init();

            // Single instance plugin — ensures deep links go to existing window
            #[cfg(desktop)]
            {
                let handle = app.handle().clone();
                app.handle().plugin(
                    tauri_plugin_single_instance::init(move |_app, argv, _cwd| {
                        info!("Single instance callback — argv: {:?}", argv);
                        // Deep link will be handled by the deep-link plugin
                        if let Some(window) = handle.get_webview_window("main") {
                            window.show().ok();
                            window.set_focus().ok();
                        }
                    })
                )?;
            }

            // Register deep link schemes at runtime for dev mode
            #[cfg(any(windows, target_os = "linux"))]
            {
                app.deep_link().register_all()?;
            }

            // Handle deep links
            let state_for_deep_link = state_clone.clone();
            let ws_cancel_for_deep_link = ws_cancel_clone.clone();
            let app_handle_for_deep_link = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                let urls = event.urls();
                info!("Deep link received: {:?}", urls);

                for url in urls {
                    if let Some(params) = extract_pairing_params(url.as_str()) {
                        info!("Extracted pairing token from deep link (backend: {:?})", params.backend_url);
                        let state = state_for_deep_link.clone();
                        let cancel_handle = ws_cancel_for_deep_link.clone();
                        let app_handle = app_handle_for_deep_link.clone();
                        tauri::async_runtime::spawn(async move {
                            // Cancel any existing WebSocket task before re-pairing
                            if let Some(old_tx) = cancel_handle.write().await.take() {
                                let _ = old_tx.send(true);
                                info!("Cancelled previous WebSocket task for re-pair");
                            }

                            match do_claim_pairing_token(params.token, params.backend_url, state.clone()).await {
                                Ok(config) => {
                                    info!("Pairing complete, starting connection...");
                                    let cancel_tx = websocket::spawn_connection_task(
                                        config.backend_url,
                                        config.tenant_id,
                                        config.agent_secret,
                                        None,
                                        state,
                                    );
                                    *cancel_handle.write().await = Some(cancel_tx);

                                    // Show and focus the window so the user sees the connected state
                                    if let Some(window) = app_handle.get_webview_window("main") {
                                        window.show().ok();
                                        window.set_focus().ok();
                                    }
                                }
                                Err(e) => error!("Pairing failed: {}", e),
                            }
                        });
                    }
                }
            });

            // Register updater plugin (desktop only)
            #[cfg(desktop)]
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;

            // Local hardware polling — runs every 5s regardless of WebSocket state.
            // Ensures card/VPN status stays fresh even when disconnected from cloud.
            {
                let local_state = state_clone.clone();
                tauri::async_runtime::spawn(async move {
                    let mut interval = tokio::time::interval(std::time::Duration::from_secs(5));
                    loop {
                        interval.tick().await;
                        let snap = tokio::task::spawn_blocking(|| {
                            let card = smartcard::check_card_status();
                            let vpn = vpn::check_vpn_status();
                            (card, vpn)
                        }).await.unwrap();
                        let (card, vpn) = snap;
                        let mut s = local_state.write().await;
                        s.reader_available = card.reader_available;
                        s.card_inserted = card.card_inserted;
                        s.card_holder = card.card_holder.clone();
                        s.vpn_connected = vpn.connected;
                        s.vpn_name = vpn.connection_name.clone();
                        s.readers = smartcard::readers_to_json(&card.readers);
                    }
                });
            }

            // Resolve config: file → env vars → unconfigured
            if let Some(config) = resolve_config() {
                info!("Starting agent — backend: {}, tenant: {}",
                    config.backend_url,
                    &config.tenant_id[..config.tenant_id.len().min(8)]
                );

                // Update state
                {
                    let mut s = tauri::async_runtime::block_on(state_clone.write());
                    s.configured = true;
                    s.backend_url = Some(config.backend_url.clone());
                }

                // Spawn WebSocket connection
                let cancel_tx = websocket::spawn_connection_task(
                    config.backend_url,
                    config.tenant_id,
                    config.agent_secret,
                    std::env::var("HM_AGENT_ID").ok(),
                    state_clone.clone(),
                );
                *tauri::async_runtime::block_on(ws_cancel_clone.write()) = Some(cancel_tx);
            } else {
                info!("No configuration found — waiting for pairing deep link");
            }

            // System tray
            let open_item = MenuItem::with_id(app, "open", "Otvori", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Izlaz", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

            let _tray = TrayIconBuilder::with_id("main-tray")
                .menu(&menu)
                .tooltip("HM Digital Agent")
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "open" => {
                        if let Some(window) = app.get_webview_window("main") {
                            window.show().ok();
                            window.set_focus().ok();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            window.show().ok();
                            window.set_focus().ok();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_connection_state,
            get_config,
            clear_config_cmd,
            claim_pairing_token,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Parsed deep link parameters.
struct DeepLinkParams {
    token: String,
    backend_url: Option<String>,
}

/// Percent-decode a URL query parameter value (e.g., `wss%3A%2F%2F` → `wss://`).
fn percent_decode(input: &str) -> String {
    let mut out = Vec::with_capacity(input.len());
    let bytes = input.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(byte) = u8::from_str_radix(
                &input[i + 1..i + 3], 16,
            ) {
                out.push(byte);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).to_string()
}

/// Extract pairing token and backend URL from a deep link like
/// hm-agent://connect?token=XXX&backend=wss%3A%2F%2Fapp.hmdigital.hr%2F
fn extract_pairing_params(url: &str) -> Option<DeepLinkParams> {
    if !url.starts_with("hm-agent://connect") {
        return None;
    }
    let query = url.split('?').nth(1)?;
    let mut token = None;
    let mut backend_url = None;
    for pair in query.split('&') {
        let mut kv = pair.splitn(2, '=');
        match kv.next() {
            Some("token") => token = kv.next().map(|s| percent_decode(s)),
            Some("backend") => backend_url = kv.next().map(|s| percent_decode(s)),
            _ => {}
        }
    }
    token.map(|t| DeepLinkParams { token: t, backend_url })
}

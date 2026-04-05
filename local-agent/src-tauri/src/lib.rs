mod smartcard;
mod vpn;
mod websocket;

use std::sync::Arc;

use log::info;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::Manager;
use tokio::sync::RwLock;

use websocket::{ConnectionState, SharedState};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let shared_state: SharedState = Arc::new(RwLock::new(ConnectionState::default()));

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .manage(shared_state.clone())
        .setup(move |app| {
            // Initialize logger
            let _ = env_logger::Builder::from_env(
                env_logger::Env::default().default_filter_or("info"),
            ).try_init();

            // Register updater plugin (desktop only)
            #[cfg(desktop)]
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;

            // Read config from env vars (MVP) or config.json (production)
            let backend_url = std::env::var("HM_BACKEND_URL")
                .unwrap_or_else(|_| "ws://localhost:8000/".to_string());
            let tenant_id = std::env::var("HM_TENANT_ID")
                .expect("HM_TENANT_ID environment variable required");
            let agent_secret = std::env::var("HM_AGENT_SECRET")
                .expect("HM_AGENT_SECRET environment variable required");
            let agent_id = std::env::var("HM_AGENT_ID").ok();

            info!("Starting agent — backend: {}, tenant: {}", backend_url, &tenant_id[..tenant_id.len().min(8)]);

            // Spawn WebSocket connection
            websocket::spawn_connection_task(backend_url, tenant_id, agent_secret, agent_id, shared_state.clone());

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
        .invoke_handler(tauri::generate_handler![get_connection_state])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[tauri::command]
async fn get_connection_state(state: tauri::State<'_, SharedState>) -> Result<ConnectionState, String> {
    Ok(state.read().await.clone())
}

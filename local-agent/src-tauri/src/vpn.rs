use log::debug;
use serde::Serialize;
use std::process::Command;

#[derive(Debug, Clone, Serialize)]
pub struct VpnStatus {
    pub connected: bool,
    pub connection_name: Option<String>,
}

/// Check VPN connection status by inspecting Windows network adapters.
/// Looks for active VPN/TAP/TUN adapters via `ipconfig`.
pub fn check_vpn_status() -> VpnStatus {
    // Check rasphone/rasdial (Windows built-in VPN)
    if let Some(name) = check_rasdial() {
        return VpnStatus {
            connected: true,
            connection_name: Some(name),
        };
    }

    // Check for VPN-like network adapters (OpenVPN TAP, WireGuard, etc.)
    if let Some(name) = check_vpn_adapters() {
        return VpnStatus {
            connected: true,
            connection_name: Some(name),
        };
    }

    VpnStatus {
        connected: false,
        connection_name: None,
    }
}

/// Check Windows RAS dial-up/VPN connections.
fn check_rasdial() -> Option<String> {
    let output = Command::new("rasdial").output().ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    debug!("rasdial output: {}", stdout);

    // rasdial with no args lists active connections
    // If no connections: "No connections" or Croatian equivalent
    // If connected: lists the connection name(s)
    if output.status.success() && !stdout.contains("No connections") && !stdout.contains("Nema veza") {
        // Parse connection name from output (first non-empty line after header)
        for line in stdout.lines().skip(1) {
            let trimmed = line.trim();
            if !trimmed.is_empty() && !trimmed.starts_with("Command completed") && !trimmed.starts_with("Naredba") {
                return Some(trimmed.to_string());
            }
        }
    }

    None
}

/// Check for VPN-like network adapters via ipconfig.
fn check_vpn_adapters() -> Option<String> {
    let output = Command::new("ipconfig")
        .args(["/all"])
        .output()
        .ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);

    let vpn_keywords = ["TAP-Windows", "OpenVPN", "WireGuard", "CEZIH", "VPN", "Fortinet", "FortiClient"];
    let mut current_adapter: Option<String> = None;
    let mut has_ip = false;

    for line in stdout.lines() {
        // Adapter header lines end with ":"
        if !line.starts_with(' ') && line.contains("adapter") && line.ends_with(':') {
            // Save previous adapter if it had an IP
            if current_adapter.is_some() && has_ip {
                return current_adapter;
            }
            // Check if this adapter name matches VPN keywords
            let is_vpn = vpn_keywords.iter().any(|kw| line.to_lowercase().contains(&kw.to_lowercase()));
            current_adapter = if is_vpn {
                // Extract adapter name between "adapter " and ":"
                line.split("adapter ").nth(1)
                    .map(|s| s.trim_end_matches(':').trim().to_string())
            } else {
                None
            };
            has_ip = false;
        }

        // Check if adapter has an IPv4 address (meaning it's connected)
        if current_adapter.is_some() && (line.contains("IPv4 Address") || line.contains("IPv4 adresa")) {
            has_ip = true;
        }
    }

    // Check last adapter
    if current_adapter.is_some() && has_ip {
        return current_adapter;
    }

    None
}

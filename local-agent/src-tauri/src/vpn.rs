use log::debug;
use serde::Serialize;
use std::net::{TcpStream, ToSocketAddrs};
use std::process::Command;
use std::time::Duration;

// Console commands (rasdial/ipconfig/route) must not flash a visible window:
// the agent is a GUI-subsystem app, so every spawned console process would
// open its own black console for the fraction of a second it runs — with the
// 2-second status poll that meant constant flashing whenever VPN was down.
#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Run a detection command without showing a console window.
#[cfg(windows)]
fn hidden_command(program: &str) -> Command {
    let mut cmd = Command::new(program);
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

#[cfg(not(windows))]
fn hidden_command(program: &str) -> Command {
    Command::new(program)
}

#[derive(Debug, Clone, Serialize)]
pub struct VpnStatus {
    pub connected: bool,
    pub connection_name: Option<String>,
}

/// Check VPN connection status by inspecting Windows network adapters.
/// Looks for active VPN/TAP/TUN adapters via `ipconfig`.
pub fn check_vpn_status() -> VpnStatus {
    // Tier 0: TCP connectivity to CEZIH server (most reliable)
    if let Some(name) = check_tcp_connectivity() {
        return VpnStatus {
            connected: true,
            connection_name: Some(name),
        };
    }

    // Tier 1: rasphone/rasdial (Windows built-in VPN)
    if let Some(name) = check_rasdial() {
        return VpnStatus {
            connected: true,
            connection_name: Some(name),
        };
    }

    // Tier 2: Check for VPN-like network adapters (OpenVPN TAP, WireGuard, Cisco AnyConnect, etc.)
    if let Some(name) = check_vpn_adapters() {
        return VpnStatus {
            connected: true,
            connection_name: Some(name),
        };
    }

    // Tier 3: Fallback — check if CEZIH VPN subnet (172.30.0.0/23) is routable
    if check_cezih_route() {
        return VpnStatus {
            connected: true,
            connection_name: Some("CEZIH VPN (route detected)".to_string()),
        };
    }

    VpnStatus {
        connected: false,
        connection_name: None,
    }
}

/// VPN hosts to check connectivity against (ordered by priority).
/// Configurable via HM_CEZIH_VPN_HOSTS env var (comma-separated).
/// Default: VPN gateway first, then FHIR server.
fn vpn_check_hosts() -> Vec<String> {
    std::env::var("HM_CEZIH_VPN_HOSTS")
        .unwrap_or_else(|_| "certws2.cezih.hr:8443,certws2.cezih.hr:9443".to_string())
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

/// Tier 0: Attempt TCP connection to CEZIH VPN hosts.
/// Tries each host in order — first success means VPN is up.
/// DNS resolution only works inside the VPN, so this doubles as a DNS check.
fn check_tcp_connectivity() -> Option<String> {
    for host in vpn_check_hosts() {
        let parts: Vec<&str> = host.rsplitn(2, ':').collect();
        let hostname = match parts.get(1) {
            Some(h) => *h,
            None => continue,
        };
        let port: u16 = match parts.first().and_then(|p| p.parse().ok()) {
            Some(p) => p,
            None => continue,
        };

        // Resolve DNS — succeeds only if VPN DNS is routing
        let addr = format!("{}:{}", hostname, port);
        let socket_addr = match addr.to_socket_addrs().ok().and_then(|mut addrs| addrs.find(|a| a.is_ipv4())) {
            Some(sa) => sa,
            None => {
                debug!("DNS resolution failed for {} — VPN DNS not active", host);
                continue;
            }
        };

        match TcpStream::connect_timeout(&socket_addr, Duration::from_secs(2)) {
            Ok(_) => {
                debug!("TCP connectivity to {} succeeded — VPN is up", host);
                return Some(format!("CEZIH VPN ({})", hostname));
            }
            Err(e) => {
                debug!("TCP connectivity to {} failed: {}", host, e);
            }
        }
    }
    None
}

/// Check Windows RAS dial-up/VPN connections.
fn check_rasdial() -> Option<String> {
    let output = hidden_command("rasdial").output().ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    debug!("rasdial output: {}", stdout);

    // rasdial with no args lists active connections
    // If no connections: "No connections" or Croatian equivalent
    // If connected: lists the connection name(s)
    if output.status.success() {
        // Structural approach: rasdial outputs header + connection names + footer.
        // With no connections: 1-2 non-empty lines. With connections: >2 lines.
        let lines: Vec<&str> = stdout.lines()
            .map(|l| l.trim())
            .filter(|l| !l.is_empty())
            .collect();
        if lines.len() > 2 {
            return Some(lines[1].to_string());
        }
    }

    None
}

/// Check for VPN-like network adapters via ipconfig.
fn check_vpn_adapters() -> Option<String> {
    let output = hidden_command("ipconfig")
        .args(["/all"])
        .output()
        .ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);

    let vpn_keywords = ["TAP-Windows", "OpenVPN", "WireGuard", "CEZIH", "VPN", "Fortinet", "FortiClient", "Cisco AnyConnect", "AnyConnect"];
    let mut current_adapter: Option<String> = None;
    let mut has_ip = false;

    for line in stdout.lines() {
        // Adapter header lines: non-indented, end with ":" (locale-independent structure)
        if !line.starts_with(' ') && line.ends_with(':') && !line.is_empty() {
            // Save previous adapter if it had an IP
            if current_adapter.is_some() && has_ip {
                return current_adapter;
            }
            // Use full header line (minus ":") as adapter name — avoids locale-dependent "adapter" keyword
            let adapter_name = line.trim_end_matches(':').trim().to_string();
            let is_vpn = vpn_keywords.iter().any(|kw| adapter_name.to_lowercase().contains(&kw.to_lowercase()));
            current_adapter = if is_vpn { Some(adapter_name) } else { None };
            has_ip = false;
        }

        // Check if adapter has an IPv4 address — "IPv4" is universal across all locales
        if current_adapter.is_some() && line.contains("IPv4") {
            has_ip = true;
        }
    }

    // Check last adapter
    if current_adapter.is_some() && has_ip {
        return current_adapter;
    }

    None
}

/// Check if CEZIH VPN subnet is routable via Windows routing table.
fn check_cezih_route() -> bool {
    // Use substring "172.30." — more reliable than "172.30.*" on Windows
    let output = match hidden_command("route").args(["print", "172.30."]).output() {
        Ok(o) => o,
        Err(_) => return false,
    };
    let stdout = String::from_utf8_lossy(&output.stdout);
    // If 172.30.0.0 appears in the routing table, the VPN tunnel is up
    stdout.contains("172.30.0")
}

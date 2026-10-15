const { invoke } = window.__TAURI__.core;
const check = window.__TAURI__.updater?.check;

function $(id) { return document.getElementById(id); }

// Error set by a failed user action; alert() is a no-op in WebView2, so
// errors must surface through the error boxes instead.
let manualError = null;

// --- View switching ---

function showSetupView() {
  $("setup-view").style.display = "block";
  $("status-view").style.display = "none";
}

function showStatusView() {
  $("setup-view").style.display = "none";
  $("status-view").style.display = "block";
}

function updateUI(state) {
  if (!state.configured) {
    showSetupView();

    // Show pairing status if active
    const pairingEl = $("pairing-status");
    if (state.pairing_status) {
      pairingEl.textContent = "";
      const spinner = document.createElement("span");
      spinner.className = "pairing-spinner";
      pairingEl.appendChild(spinner);
      pairingEl.appendChild(document.createTextNode(state.pairing_status));
    } else {
      pairingEl.textContent = "";
    }

    // Show error in setup view
    const errorBox = $("error-box");
    const setupError = manualError || state.last_error;
    if (setupError) {
      errorBox.style.display = "block";
      errorBox.textContent = setupError;
    } else {
      errorBox.style.display = "none";
    }
    return;
  }

  showStatusView();

  // Cloud connection — warn if card missing (CEZIH not usable)
  const cloudDot = $("cloud-dot");
  const cloudLabel = $("cloud-label");
  const cloudDetail = $("cloud-detail");
  if (state.ws_connected && state.card_inserted) {
    cloudDot.className = "dot green";
    cloudLabel.textContent = "CEZIH spreman";
    cloudDetail.textContent = "";
  } else if (state.ws_connected && !state.card_inserted) {
    cloudDot.className = "dot yellow";
    cloudLabel.textContent = "Umetnite karticu za CEZIH";
    cloudDetail.textContent = "";
  } else {
    cloudDot.className = "dot red";
    cloudLabel.textContent = "Cloud usluga nedostupna";
    cloudDetail.textContent = "";
  }

  // Smart card
  const cardDot = $("card-dot");
  const cardLabel = $("card-label");
  const cardDetail = $("card-detail");
  if (!state.reader_available) {
    cardDot.className = "dot gray";
    cardLabel.textContent = "Čitač nije pronađen";
    cardDetail.textContent = "";
  } else if (state.card_inserted) {
    cardDot.className = "dot green";
    cardLabel.textContent = "Kartica umetnuta";
    cardDetail.textContent = state.card_holder || "";
  } else {
    cardDot.className = "dot red";
    cardLabel.textContent = "Čitač pronađen — umetnite karticu";
    cardDetail.textContent = "";
  }

  // VPN
  const vpnDot = $("vpn-dot");
  const vpnLabel = $("vpn-label");
  const vpnDetail = $("vpn-detail");
  if (state.vpn_connected) {
    vpnDot.className = "dot green";
    vpnLabel.textContent = "VPN spojen";
    vpnDetail.textContent = state.vpn_name || "";
  } else {
    vpnDot.className = "dot red";
    vpnLabel.textContent = "VPN nije spojen";
    vpnDetail.textContent = "";
  }

  // Tenant info footer
  const tenantInfo = $("tenant-info");
  if (state.backend_url) {
    try {
      const url = new URL(state.backend_url);
      tenantInfo.textContent = url.hostname;
    } catch {
      tenantInfo.textContent = state.backend_url;
    }
  }

  // Error (status view)
  const errorBox2 = $("error-box-2");
  const statusError = manualError || (state.last_error && !state.ws_connected ? state.last_error : null);
  if (statusError) {
    errorBox2.style.display = "block";
    errorBox2.textContent = statusError;
  } else {
    errorBox2.style.display = "none";
  }
}

// --- Config management ---

async function resetConfig() {
  manualError = null;
  try {
    await invoke("clear_config_cmd");
    // Force immediate UI refresh
    poll();
  } catch (e) {
    console.error("Failed to clear config:", e);
    manualError = "Greška pri odspajanju: " + e;
    poll();
  }
}

// --- Update logic ---
// The agent never self-installs: it only checks for a newer release and
// shows a notice. Installing is manual (run the setup exe from the releases
// page).

let updateState = "idle";
let updateVersion = "";

function updateUpdateUI() {
  const updateRow = $("update-row");
  if (updateState === "idle") {
    updateRow.style.display = "none";
    return;
  }

  updateRow.style.display = "flex";

  if (updateState === "available") {
    $("update-dot").className = "dot blue";
    $("update-label").textContent = "Dostupno je novo ažuriranje programa";
    $("update-detail").textContent = updateVersion;
  }
}

async function checkForUpdates() {
  if (!check) return;

  try {
    const update = await check();
    updateVersion = update ? update.version : "";
    updateState = update ? "available" : "idle";
  } catch (e) {
    // A failed check (e.g. no internet) stays silent — the next interval
    // retry will surface the notice once reachable again.
    console.error("Update check failed:", e);
    updateState = "idle";
  }
  updateUpdateUI();
}

// --- Polling ---

async function poll() {
  try {
    const state = await invoke("get_connection_state");
    updateUI(state);
  } catch (e) {
    console.error("Failed to get state:", e);
  }
}

// --- Button bindings (CSP's script-src-attr blocks inline onclick attributes) ---
$("disconnect-btn")?.addEventListener("click", resetConfig);

// Initial + poll every 2 seconds
poll();
setInterval(poll, 2000);

// Check for new updates on startup, then every 30 minutes
checkForUpdates();
setInterval(checkForUpdates, 30 * 60 * 1000);

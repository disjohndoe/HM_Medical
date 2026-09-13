const { invoke } = window.__TAURI__.core;
const check = window.__TAURI__.updater?.check;
const relaunch = window.__TAURI__.process?.relaunch;

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

const REMINDER_DAYS = 3;
const STORAGE_KEY = "hm_update_pending";

let updateState = "idle";
let updateVersion = "";

function updateUpdateUI() {
  const updateRow = $("update-row");
  const updateDot = $("update-dot");
  const updateLabel = $("update-label");
  const updateDetail = $("update-detail");
  const restartBtn = $("restart-btn");

  if (updateState === "idle") {
    updateRow.style.display = "none";
    restartBtn.style.display = "none";
    return;
  }

  updateRow.style.display = "flex";
  restartBtn.style.display = "none";

  switch (updateState) {
    case "checking":
      updateDot.className = "dot gray";
      updateLabel.textContent = "Provjera za ažuriranje...";
      updateDetail.textContent = "";
      break;
    case "downloading":
      updateDot.className = "dot blue";
      updateLabel.textContent = "Preuzimanje ažuriranja...";
      updateDetail.textContent = updateVersion;
      break;
    case "ready":
      updateDot.className = "dot green";
      updateLabel.textContent = "Ažuriranje spremno";
      updateDetail.textContent = updateVersion + " — primijenit će se pri sljedećem pokretanju";
      break;
    case "overdue":
      updateDot.className = "dot red";
      updateLabel.textContent = "Ažuriranje potrebno";
      updateDetail.textContent = updateVersion;
      restartBtn.style.display = "inline-block";
      break;
    case "error":
      updateDot.className = "dot red";
      updateLabel.textContent = "Ažuriranje neuspjelo";
      updateDetail.textContent = "";
      break;
  }
}

function savePendingUpdate(version) {
  const data = { version, downloadedAt: Date.now() };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function getPendingUpdate() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

function clearPendingUpdate() {
  localStorage.removeItem(STORAGE_KEY);
}

function isOverdue(pending) {
  if (!pending) return false;
  const elapsed = Date.now() - pending.downloadedAt;
  return elapsed > REMINDER_DAYS * 24 * 60 * 60 * 1000;
}

function checkPendingUpdate() {
  const pending = getPendingUpdate();
  if (!pending) return;

  updateVersion = pending.version;
  if (isOverdue(pending)) {
    updateState = "overdue";
  } else {
    updateState = "ready";
  }
  updateUpdateUI();
}

async function checkForUpdates() {
  if (!check) return;
  if (updateState === "downloading") return;

  try {
    updateState = "checking";
    updateUpdateUI();

    const update = await check();

    if (!update) {
      const pending = getPendingUpdate();
      if (pending) {
        updateVersion = pending.version;
        updateState = isOverdue(pending) ? "overdue" : "ready";
      } else {
        updateState = "idle";
      }
      updateUpdateUI();
      return;
    }

    updateVersion = update.version;

    updateState = "downloading";
    updateUpdateUI();

    await update.download();

    savePendingUpdate(update.version);

    updateState = "ready";
    updateUpdateUI();
  } catch (e) {
    console.error("Update check failed:", e);
    updateState = "error";
    updateUpdateUI();
    setTimeout(() => {
      if (updateState === "error") {
        updateState = "idle";
        updateUpdateUI();
      }
    }, 30000);
  }
}

async function restartNow() {
  if (!relaunch) return;
  try {
    await relaunch();
  } catch (e) {
    console.error("Restart failed:", e);
  }
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
$("restart-btn")?.addEventListener("click", restartNow);
$("disconnect-btn")?.addEventListener("click", resetConfig);

// Initial + poll every 2 seconds
poll();
setInterval(poll, 2000);

// Check for pending update first (instant, no network)
checkPendingUpdate();

// Check for new updates on startup, then every 30 minutes
checkForUpdates();
setInterval(checkForUpdates, 30 * 60 * 1000);

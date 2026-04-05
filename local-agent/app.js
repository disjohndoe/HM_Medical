const { invoke } = window.__TAURI__.core;
const check = window.__TAURI__.updater?.check;
const relaunch = window.__TAURI__.process?.relaunch;

function $(id) { return document.getElementById(id); }

function updateUI(state) {
  // Cloud connection
  const cloudDot = $("cloud-dot");
  const cloudLabel = $("cloud-label");
  const cloudDetail = $("cloud-detail");
  if (state.ws_connected) {
    cloudDot.className = "dot green";
    cloudLabel.textContent = "Cloud usluga dostupna";
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

  // Error
  const errorBox = $("error-box");
  if (state.last_error) {
    errorBox.style.display = "block";
    errorBox.textContent = state.last_error;
  } else {
    errorBox.style.display = "none";
  }
}

// --- Update logic ---
// Strategy: download silently → install on next restart → remind after 3 days

const REMINDER_DAYS = 3;
const STORAGE_KEY = "hm_update_pending";

let updateState = "idle"; // idle | checking | downloading | ready | overdue | error
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

// Persist pending update info so it survives app restarts
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

// Check if a previously downloaded update is waiting to be applied
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
  if (!check) return; // updater plugin not available (dev mode)
  if (updateState === "downloading") return;

  try {
    updateState = "checking";
    updateUpdateUI();

    const update = await check();

    if (!update) {
      // No update available — check if a previous one is pending
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

    // Download silently — do NOT install yet
    updateState = "downloading";
    updateUpdateUI();

    await update.download();

    // Save to localStorage so it persists across restarts
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

async function poll() {
  try {
    const state = await invoke("get_connection_state");
    updateUI(state);
  } catch (e) {
    console.error("Failed to get state:", e);
  }
}

// Initial + poll every 2 seconds
poll();
setInterval(poll, 2000);

// Check for pending update first (instant, no network)
checkPendingUpdate();

// Check for new updates on startup, then every 30 minutes
checkForUpdates();
setInterval(checkForUpdates, 30 * 60 * 1000);

const state = {
  chairCount: 24,
  chairs: [],
  flaskUrl: "",
  wsUrl: "",
  pollMs: 2000,
  pollTimer: null,
  socket: null,
  reconnectTimer: null
};

const chairsGrid = document.getElementById("chairsGrid");
const totalCount = document.getElementById("totalCount");
const occupiedCount = document.getElementById("occupiedCount");
const vacantCount = document.getElementById("vacantCount");
const flaskStatus = document.getElementById("flaskStatus");
const wsStatus = document.getElementById("wsStatus");
const lastSource = document.getElementById("lastSource");
const lastUpdated = document.getElementById("lastUpdated");

const chairCountInput = document.getElementById("chairCount");
const flaskUrlInput = document.getElementById("flaskUrl");
const wsUrlInput = document.getElementById("wsUrl");
const pollMsInput = document.getElementById("pollMs");

function setPill(element, text, type) {
  element.textContent = text;
  element.className = "pill " + type;
}

function normaliseSeatValue(value) {
  if (value === true || value === "true") return 1;
  if (value === false || value === "false") return 0;
  if (typeof value === "string") {
    const trimmed = value.trim().toLowerCase();
    if (trimmed === "occupied") return 1;
    if (trimmed === "vacant" || trimmed === "empty") return 0;
  }
  return Number(value) === 1 ? 1 : 0;
}

function ensureChairArray() {
  while (state.chairs.length < state.chairCount) {
    state.chairs.push(0);
  }
  state.chairs = state.chairs.slice(0, state.chairCount);
}

function buildChairCards() {
  ensureChairArray();
  chairsGrid.innerHTML = "";

  for (let i = 0; i < state.chairCount; i += 1) {
    const value = state.chairs[i];
    const card = document.createElement("div");
    card.className = "chair " + (value === 1 ? "occupied" : "vacant");
    card.innerHTML = `
      <div class="chair-name">Chair ${i + 1}</div>
      <div class="chair-state">${value === 1 ? "Occupied" : "Vacant"}</div>
      <div class="chair-value">${value}</div>
    `;
    chairsGrid.appendChild(card);
  }

  updateSummary();
}

function updateSummary() {
  const occupied = state.chairs.filter((value) => value === 1).length;
  const vacant = state.chairCount - occupied;
  totalCount.textContent = String(state.chairCount);
  occupiedCount.textContent = String(occupied);
  vacantCount.textContent = String(vacant);
}

function markUpdate(sourceLabel) {
  lastSource.textContent = sourceLabel;
  lastUpdated.textContent = new Date().toLocaleString();
  buildChairCards();
}

function applySeatArray(values, sourceLabel) {
  const next = values.slice(0, state.chairCount).map(normaliseSeatValue);
  state.chairs = next;
  ensureChairArray();
  markUpdate(sourceLabel);
}

function applySeatMap(entries, sourceLabel) {
  ensureChairArray();
  entries.forEach((item) => {
    const rawId = item.id ?? item.seatId ?? item.chairId ?? item.index;
    const rawValue = item.occupied ?? item.value ?? item.state ?? item.status;
    const seatIndex = Number(rawId) - 1;
    if (seatIndex >= 0 && seatIndex < state.chairCount) {
      state.chairs[seatIndex] = normaliseSeatValue(rawValue);
    }
  });
  markUpdate(sourceLabel);
}

function applySingleSeatUpdate(payload, sourceLabel) {
  ensureChairArray();
  const rawId = payload.id ?? payload.seatId ?? payload.chairId ?? payload.index;
  const rawValue = payload.occupied ?? payload.value ?? payload.state ?? payload.status;
  const seatIndex = Number(rawId) - 1;
  if (seatIndex >= 0 && seatIndex < state.chairCount) {
    state.chairs[seatIndex] = normaliseSeatValue(rawValue);
    markUpdate(sourceLabel);
  }
}

function parseChairPayload(payload, sourceLabel) {
  if (Array.isArray(payload)) {
    applySeatArray(payload, sourceLabel);
    return true;
  }

  if (!payload || typeof payload !== "object") {
    return false;
  }

  if (Array.isArray(payload.chairs)) {
    applySeatArray(payload.chairs, sourceLabel);
    return true;
  }

  if (Array.isArray(payload.seats)) {
    applySeatMap(payload.seats, sourceLabel);
    return true;
  }

  if ("id" in payload || "seatId" in payload || "chairId" in payload || "index" in payload) {
    applySingleSeatUpdate(payload, sourceLabel);
    return true;
  }

  const numericKeys = Object.keys(payload).filter((key) => /^chair_\d+$/i.test(key));
  if (numericKeys.length > 0) {
    ensureChairArray();
    numericKeys.forEach((key) => {
      const chairId = Number(key.split("_")[1]);
      if (chairId >= 1 && chairId <= state.chairCount) {
        state.chairs[chairId - 1] = normaliseSeatValue(payload[key]);
      }
    });
    markUpdate(sourceLabel);
    return true;
  }

  return false;
}

async function fetchFlaskData() {
  if (!state.flaskUrl) {
    setPill(flaskStatus, "No URL", "waiting");
    return;
  }

  try {
    const response = await fetch(state.flaskUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (typeof data === "string") {
      setPill(flaskStatus, "Connected", "connected");
      lastSource.textContent = "Flask connected, but no chair JSON detected";
      return;
    }

    const applied = parseChairPayload(data, "Flask fetch");
    setPill(flaskStatus, applied ? "Connected" : "Unknown payload", applied ? "connected" : "waiting");
  } catch (error) {
    setPill(flaskStatus, "Disconnected", "disconnected");
    lastSource.textContent = "Flask error: " + error.message;
  }
}

function scheduleFetchLoop() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }

  if (!state.flaskUrl) return;

  state.pollTimer = setInterval(fetchFlaskData, state.pollMs);
}

function closeSocket() {
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
  if (state.socket) {
    state.socket.close();
    state.socket = null;
  }
}

function connectWebSocket() {
  closeSocket();

  if (!state.wsUrl) {
    setPill(wsStatus, "No URL", "waiting");
    return;
  }

  try {
    setPill(wsStatus, "Connecting", "waiting");
    state.socket = new WebSocket(state.wsUrl);

    state.socket.onopen = () => {
      setPill(wsStatus, "Connected", "connected");
    };

    state.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const applied = parseChairPayload(data, "WebSocket");
        if (!applied) {
          lastSource.textContent = "WebSocket connected, but payload format is not supported";
        }
      } catch (error) {
        lastSource.textContent = "WebSocket message is not valid JSON";
      }
    };

    state.socket.onerror = () => {
      setPill(wsStatus, "Error", "disconnected");
    };

    state.socket.onclose = () => {
      setPill(wsStatus, "Disconnected", "disconnected");
      state.reconnectTimer = setTimeout(connectWebSocket, 3000);
    };
  } catch (error) {
    setPill(wsStatus, "Invalid URL", "disconnected");
  }
}

function loadSettings() {
  const saved = JSON.parse(localStorage.getItem("smart-chair-monitor-config") || "{}");
  state.chairCount = Number(saved.chairCount) || 24;
  state.flaskUrl = saved.flaskUrl || "";
  state.wsUrl = saved.wsUrl || "";
  state.pollMs = Number(saved.pollMs) || 2000;

  chairCountInput.value = String(state.chairCount);
  flaskUrlInput.value = state.flaskUrl;
  wsUrlInput.value = state.wsUrl;
  pollMsInput.value = String(state.pollMs);
}

function saveSettings() {
  localStorage.setItem("smart-chair-monitor-config", JSON.stringify({
    chairCount: state.chairCount,
    flaskUrl: state.flaskUrl,
    wsUrl: state.wsUrl,
    pollMs: state.pollMs
  }));
}

function applySettings() {
  state.chairCount = Math.max(1, Number(chairCountInput.value) || 24);
  state.flaskUrl = flaskUrlInput.value.trim();
  state.wsUrl = wsUrlInput.value.trim();
  state.pollMs = Math.max(500, Number(pollMsInput.value) || 2000);

  ensureChairArray();
  buildChairCards();
  saveSettings();
  scheduleFetchLoop();
  connectWebSocket();
  fetchFlaskData();
}

function loadDemoData() {
  const demo = Array.from({ length: state.chairCount }, (_, index) => index % 3 === 1 ? 1 : 0);
  applySeatArray(demo, "Demo data");
  setPill(flaskStatus, "Demo mode", "waiting");
  setPill(wsStatus, "Demo mode", "waiting");
}

document.getElementById("applyBtn").addEventListener("click", applySettings);
document.getElementById("fetchBtn").addEventListener("click", fetchFlaskData);
document.getElementById("wsBtn").addEventListener("click", connectWebSocket);
document.getElementById("demoBtn").addEventListener("click", loadDemoData);

loadSettings();
ensureChairArray();
buildChairCards();
scheduleFetchLoop();
connectWebSocket();
fetchFlaskData();

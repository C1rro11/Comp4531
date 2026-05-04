const BADGE = document.getElementById("badge");
const CONF_FILL = document.getElementById("conf-fill");
const CONF_TEXT = document.getElementById("conf-text");
const TS = document.getElementById("ts");
const CO2_TOGGLE = document.getElementById("co2-toggle");
const WINDOW_INPUT = document.getElementById("window-input");

const CLASS_COLOR = { EMPTY: "#22c55e", OCCUPIED: "#ef4444", HOARDED: "#f59e0b", NO_MODEL: "#6b7280" };

function updateBadge(pred, conf) {
  BADGE.textContent = pred;
  BADGE.className = "badge " + pred.toLowerCase().replace("_", "");
  CONF_FILL.style.width = (conf * 100) + "%";
  CONF_FILL.style.background = CLASS_COLOR[pred] || "#6b7280";
  CONF_TEXT.textContent = (conf * 100).toFixed(1) + "% confidence";
}

function updateProbs(probs) {
  const names = ["EMPTY", "OCCUPIED", "HOARDED"];
  const colors = { EMPTY: "#22c55e", OCCUPIED: "#ef4444", HOARDED: "#f59e0b" };
  names.forEach(name => {
    const pct = probs[name] * 100;
    document.querySelector(`.prob-row:nth-child(${names.indexOf(name) + 1}) .prob-bar`).style.width = pct + "%";
    document.querySelector(`.prob-row:nth-child(${names.indexOf(name) + 1}) .prob-bar`).style.background = colors[name];
    document.querySelector(`.prob-row:nth-child(${names.indexOf(name) + 1}) .prob-val`).textContent = pct.toFixed(1) + "%";
  });
}

function updateRaw(raw) {
  setVal("r-dist",   raw.mmwave_distance != null ? raw.mmwave_distance + " cm" : "--");
  setVal("r-det",    raw.mmwave_detection != null ? (raw.mmwave_detection ? "Detected" : "None") : "--");
  setVal("r-mmcount",raw.mmwave_readings);
  setVal("r-co2",    raw.co2_latest != null ? raw.co2_latest + " ppm" : "--");
  setVal("r-temp",   raw.temperature != null ? raw.temperature + " °C" : "--");
  setVal("r-hum",    raw.humidity != null ? raw.humidity + " %" : "--");
  setVal("r-pres",   raw.pressure === 1 ? "OCCUPIED" : "EMPTY");
  if (raw.last_nfc) {
    setVal("r-nfc", raw.last_nfc.uid + " @ " + raw.last_nfc.time);
  } else {
    setVal("r-nfc", "--");
  }
}

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function updateFeatures(feats) {
  const el = document.getElementById("features");
  if (!feats || feats.length === 0) { el.textContent = "--"; return; }
  const raw = feats.slice(0, 8);
  const delta = feats.slice(8, 16);
  const labels = [
    "gate0_mean","gate0_std","gate1_mean","gate1_std",
    "gate2_mean","gate2_std","co2_mean","pressure"
  ];
  let html = "<b>Raw (0-7):</b><br>";
  raw.forEach((v, i) => {
    html += `  ${i} ${labels[i]}: ${v.toFixed(4)}<br>`;
  });
  html += "<br><b>Deltas (8-15):</b><br>";
  delta.forEach((v, i) => {
    const sign = v >= 0 ? "+" : "";
    html += `  ${i+8} Δ${labels[i]}: ${sign}${v.toFixed(4)}<br>`;
  });
  el.innerHTML = html;
}

function updateSettings(settings) {
  if (!settings) return;
  CO2_TOGGLE.textContent = "CO2: " + (settings.co2_enabled ? "ON" : "OFF");
  if (document.activeElement !== WINDOW_INPUT) {
    WINDOW_INPUT.value = settings.window_sec;
  }
}

function updateCollecting(info) {
  const msg = document.getElementById("collect-msg");
  if (info.active) {
    const cls = (info.class || "").toUpperCase();
    msg.innerHTML = `<span class="status-dot active"></span> Collecting ${cls}: <b>${info.collected}/${info.target}</b>`;
  } else if (info.collected > 0 && info.collected >= info.target) {
    msg.innerHTML = `Finished collecting ${(info.class||"").toUpperCase()} (${info.collected} samples).`;
    setTimeout(() => { msg.textContent = ""; }, 5000);
  } else {
    msg.textContent = "";
  }
}

// ── SSE ────────────────────────────────────────────────────────────────────
function connectSSE() {
  const es = new EventSource("/stream");
  es.onmessage = (e) => {
    const d = JSON.parse(e.data);
    TS.textContent = d.timestamp || "";
    updateBadge(d.prediction, d.confidence);
    updateProbs(d.probabilities);
    updateRaw(d.raw);
    updateFeatures(d.features);
    updateSettings(d.settings);
    updateCollecting(d.collecting || {});
  };
  es.onerror = () => {
    console.warn("SSE disconnected, retrying in 2s...");
    es.close();
    setTimeout(connectSSE, 2000);
  };
}

// ── Buttons ────────────────────────────────────────────────────────────────
async function startCollect(label) {
  const count = parseInt(document.getElementById("collect-count").value) || 30;
  await fetch("/api/collect/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ class: label, count }),
  });
}

async function stopCollect() {
  await fetch("/api/collect/stop", { method: "POST" });
}

async function doTrain() {
  const r = await fetch("/api/train", { method: "POST" });
  const d = await r.json();
  alert(d.message);
}

async function doClear() {
  if (!confirm("Delete all training data and model?")) return;
  await fetch("/api/clear", { method: "POST" });
  location.reload();
}

async function toggleCO2() {
  const r = await fetch("/api/co2/toggle", { method: "POST" });
  const d = await r.json();
  CO2_TOGGLE.textContent = "CO2: " + (d.co2_enabled ? "ON" : "OFF");
}

async function applyWindow() {
  const val = parseFloat(WINDOW_INPUT.value) || 10;
  const r = await fetch("/api/window", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ window_sec: val }),
  });
  const d = await r.json();
  if (d.status === "error") alert(d.message);
}

// ── Init ───────────────────────────────────────────────────────────────────
connectSSE();

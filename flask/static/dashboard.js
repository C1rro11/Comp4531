const BADGE = document.getElementById("badge");
const CONF_FILL = document.getElementById("conf-fill");
const CONF_TEXT = document.getElementById("conf-text");
const TS = document.getElementById("ts");

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
  const raw = feats.slice(0, 27);
  const delta = feats.slice(27, 54);
  const labels = [
    "dist_mean","dist_max","dist_min","dist_std","det_mean","det_sum","rd_count",
    "gate_0","gate_1","gate_2","gate_3","gate_4","gate_5","gate_6","gate_7",
    "gate_8","gate_9","gate_10","gate_11","gate_12","gate_13","gate_14","gate_15",
    "co2_mean","co2_std","co2_rate","pressure"
  ];
  let html = "<b>Raw (0-26):</b><br>";
  raw.forEach((v, i) => {
    html += `  ${String(i).padStart(2)} ${labels[i]}: ${v.toFixed(4)}<br>`;
  });
  html += "<br><b>Deltas (27-53):</b><br>";
  delta.forEach((v, i) => {
    const sign = v >= 0 ? "+" : "";
    html += `  ${String(i+27).padStart(2)} Δ${labels[i]}: ${sign}${v.toFixed(4)}<br>`;
  });
  el.innerHTML = html;
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

// ── Init ───────────────────────────────────────────────────────────────────
connectSSE();

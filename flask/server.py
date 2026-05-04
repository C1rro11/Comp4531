import csv
import json
import os
import threading
import time
from collections import deque
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from model import FEATURE_FULL, LABELS, FeatureExtractor, XGBoostModel

# =============================================================================
# Configuration
# =============================================================================
CO2_HORIZON_SEC = 30
BUFFER_RETENTION_SEC = 120
MODEL_PATH = "models/seat_model.pkl"
TRAINING_DATA_PATH = "training_data/training_data.csv"

# =============================================================================
# Shared state (protected by state_lock)
# =============================================================================
state_lock = threading.Lock()

co2_enabled = True
window_sec = 10.0

# data buffers
mmwave_buffer = deque()      # (timestamp, detection, distance, energy_array)
sdc40_buffer = deque()       # (timestamp, co2, temperature, humidity)
pressure_state = 0.0          # persistent last-known seat occupancy
pressure_ts = 0.0
nfc_log = deque(maxlen=50)    # last 50 NFC scans

# window output
latest_state = {
    "version": 0,
    "data": {
        "prediction": "NO_MODEL",
        "confidence": 0.0,
        "probabilities": {"EMPTY": 0, "OCCUPIED": 0, "HOARDED": 0},
        "raw": {},
        "features": [],
        "timestamp": "",
        "collecting": {},
    },
}

# training collection
collecting = {
    "active": False,
    "label": None,    # int  0 / 1 / 2
    "class": None,    # str  "empty" / "occupied" / "hoarded"
    "target": 0,
    "collected": 0,
}
training_samples = []   # list of (features_16, label_int)

# feature extractor / model
extractor = FeatureExtractor()
model_obj = XGBoostModel()

# SSE subscribers  (list of queues)
sse_queues = []

# =============================================================================
# Helpers
# =============================================================================

def _label_to_int(name):
    m = {"empty": 0, "occupied": 1, "hoarded": 2}
    return m.get(name.lower(), None)


def _int_to_label(i):
    return LABELS[i] if 0 <= i < len(LABELS) else "UNKNOWN"


def build_raw_snapshot(mm_items, co30s, sdc10s):
    """Build a JSON-friendly snapshot of the latest raw sensor values."""
    snap = {}
    if mm_items:
        latest_mm = mm_items[-1]
        snap["mmwave_detection"] = latest_mm[0]
        snap["mmwave_distance"] = round(latest_mm[1], 1)
        snap["mmwave_energy"] = [round(e, 2) for e in latest_mm[2]] if latest_mm[2] else []
        snap["mmwave_readings"] = len(mm_items)
    else:
        snap["mmwave_detection"] = None
        snap["mmwave_distance"] = None
        snap["mmwave_energy"] = []
        snap["mmwave_readings"] = 0

    if co30s:
        snap["co2_latest"] = round(co30s[-1], 1)
        snap["co2_readings"] = len(co30s)
    else:
        snap["co2_latest"] = None
        snap["co2_readings"] = 0

    if sdc10s:
        snap["temperature"] = round(sdc10s[-1][0], 2)
        snap["humidity"] = round(sdc10s[-1][1], 2)
    else:
        snap["temperature"] = None
        snap["humidity"] = None

    snap["pressure"] = int(pressure_state)

    nfc_entries = list(nfc_log)
    snap["last_nfc"] = nfc_entries[-1] if nfc_entries else None

    return snap


def save_training_data():
    if not training_samples:
        return
    os.makedirs(os.path.dirname(TRAINING_DATA_PATH), exist_ok=True)
    with open(TRAINING_DATA_PATH, "w", newline="") as f:
        w = csv.writer(f)
        header = [str(i) for i in range(FEATURE_FULL)] + ["label"]
        w.writerow(header)
        for feats, label in training_samples:
            w.writerow(feats + [label])


def load_training_data():
    if not os.path.exists(TRAINING_DATA_PATH):
        return []
    rows = []
    with open(TRAINING_DATA_PATH, "r") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) < FEATURE_FULL + 1:
                continue
            feats = [float(v) for v in row[:FEATURE_FULL]]
            label = int(row[FEATURE_FULL])
            rows.append((feats, label))
    return rows


def get_distribution():
    dist = {"EMPTY": 0, "OCCUPIED": 0, "HOARDED": 0}
    for _, lbl in training_samples:
        name = _int_to_label(lbl)
        if name in dist:
            dist[name] += 1
    return dist


# =============================================================================
# Background window aggregator
# =============================================================================

def window_aggregator():
    global latest_state, window_sec, co2_enabled

    while True:
        t0 = time.time()
        with state_lock:
            wnd = window_sec
        time.sleep(wnd - (t0 % wnd) + 0.1)
        now = time.time()
        cutoff_wnd = now - wnd
        cutoff_30s = now - CO2_HORIZON_SEC

        with state_lock:
            # snap mmWave (window)
            mm = [(d, dist, eng) for (ts, d, dist, eng) in mmwave_buffer if ts >= cutoff_wnd]

            # snap sdc40  →  window (temp, hum)  +  30 s (co2)
            sd10 = [(t, h) for (ts, _, t, h) in sdc40_buffer if ts >= cutoff_wnd]
            co30 = [co2 for (ts, co2, _, _) in sdc40_buffer if ts >= cutoff_30s]

            ps = pressure_state

            features = extractor.extract_full(mm, co30, ps)
            raw = build_raw_snapshot(mm, co30, sd10)

            # zero CO2 features when disabled (after delta calc, so deltas stay consistent)
            if not co2_enabled:
                features[6] = 0.0   # raw co2_mean
                features[14] = 0.0  # Δco2_mean

            pred, conf = "NO_MODEL", 0.0
            probs = {"EMPTY": 0, "OCCUPIED": 0, "HOARDED": 0}
            if model_obj.trained:
                probs = model_obj.predict_proba(features) or probs
                pred = max(probs, key=probs.get)
                conf = probs[pred]

            ver = latest_state["version"] + 1
            latest_state["data"] = {
                "prediction": pred,
                "confidence": round(conf, 4),
                "probabilities": probs,
                "raw": raw,
                "features": [round(f, 4) for f in features],
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "collecting": dict(collecting),
                "settings": {
                    "co2_enabled": co2_enabled,
                    "window_sec": window_sec,
                },
            }
            latest_state["version"] = ver

            if collecting["active"] and collecting["label"] is not None:
                training_samples.append((features, collecting["label"]))
                collecting["collected"] += 1

                if collecting["collected"] >= collecting["target"]:
                    save_training_data()
                    collecting["active"] = False
                    collecting["class"] = None
                    collecting["label"] = None
                    latest_state["data"]["collecting"] = dict(collecting)

            cutoff_all = now - BUFFER_RETENTION_SEC
            while mmwave_buffer and mmwave_buffer[0][0] < cutoff_all:
                mmwave_buffer.popleft()
            while sdc40_buffer and sdc40_buffer[0][0] < cutoff_all:
                sdc40_buffer.popleft()


# =============================================================================
# Flask app
# =============================================================================
app = Flask(__name__)


@app.route("/")
def dashboard():
    return render_template("index.html")


# ---- SSE stream ------------------------------------------------------------

@app.route("/stream")
def stream():
    def generate():
        last_ver = -1
        while True:
            with state_lock:
                ver = latest_state["version"]
                data = latest_state["data"]
            if ver > last_ver:
                last_ver = ver
                payload = json.dumps(data)
                yield f"data: {payload}\n\n"
            time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream")


# ---- Sensor endpoints ------------------------------------------------------

@app.route("/mmwave", methods=["POST"])
def recv_mmwave():
    try:
        data = request.get_json()
        detection = float(data.get("detection", 0))
        distance = float(data.get("distance", 0))
        energy = data.get("energyArray")
        if energy is not None:
            energy = [float(e) for e in energy]
        with state_lock:
            mmwave_buffer.append((time.time(), detection, distance, energy))
            while mmwave_buffer and mmwave_buffer[0][0] < time.time() - BUFFER_RETENTION_SEC:
                mmwave_buffer.popleft()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/sdc40", methods=["POST"])
def recv_sdc40():
    try:
        data = request.get_json()
        co2 = float(data.get("co2", 400))
        temp = float(data.get("temperature", 22))
        hum = float(data.get("humidity", 50))
        with state_lock:
            sdc40_buffer.append((time.time(), co2, temp, hum))
            while sdc40_buffer and sdc40_buffer[0][0] < time.time() - BUFFER_RETENTION_SEC:
                sdc40_buffer.popleft()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/seat_state", methods=["POST"])
def recv_seat_state():
    global pressure_state, pressure_ts
    try:
        data = request.get_json()
        seat_str = data.get("seatState", "empty")
        with state_lock:
            pressure_state = 1.0 if seat_str == "seatOccupied" else 0.0
            pressure_ts = time.time()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/nfc", methods=["POST"])
def recv_nfc():
    try:
        data = request.get_json()
        uid = data.get("uid", "unknown")
        entry = {"uid": uid, "time": datetime.now().strftime("%H:%M:%S")}
        with state_lock:
            nfc_log.append(entry)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---- API endpoints ---------------------------------------------------------

@app.route("/api/state")
def api_state():
    with state_lock:
        data = dict(latest_state["data"])
    return jsonify(data), 200


@app.route("/api/collect/start", methods=["POST"])
def api_collect_start():
    try:
        data = request.get_json()
        cls_name = data.get("class", "").lower()
        count = int(data.get("count", 30))
        label = _label_to_int(cls_name)
        if label is None:
            return jsonify({"status": "error", "message": "Class must be 'empty', 'occupied', or 'hoarded'"}), 400
        if count < 5:
            return jsonify({"status": "error", "message": "Count must be >= 5"}), 400

        with state_lock:
            if collecting["active"]:
                return jsonify({"status": "error", "message": "Collection already active"}), 409
            collecting["active"] = True
            collecting["label"] = label
            collecting["class"] = cls_name
            collecting["target"] = count
            collecting["collected"] = 0
            # reset deltas so first window of new collection is clean
            extractor.reset()

        label_name = _int_to_label(label)
        return jsonify({
            "status": "ok",
            "message": f"Started collecting {count} '{label_name}' samples",
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/collect/stop", methods=["POST"])
def api_collect_stop():
    with state_lock:
        was_active = collecting["active"]
        cls = collecting["class"]
        cnt = collecting["collected"]
        collecting["active"] = False
        collecting["class"] = None
        collecting["label"] = None
        if was_active and cnt > 0:
            save_training_data()
    if was_active:
        return jsonify({"status": "ok", "message": f"Stopped. Saved {cnt} samples for '{cls}'."}), 200
    return jsonify({"status": "ok", "message": "No active collection."}), 200


@app.route("/api/collect/status")
def api_collect_status():
    with state_lock:
        info = dict(collecting)
        info["distribution"] = get_distribution()
        info["total_samples"] = len(training_samples)
    return jsonify(info), 200


@app.route("/api/train", methods=["POST"])
def api_train():
    try:
        with state_lock:
            if len(training_samples) < 10:
                return jsonify({
                    "status": "error",
                    "message": f"Need at least 10 samples. Have {len(training_samples)}.",
                }), 400

            X = [s[0] for s in training_samples]
            y = [s[1] for s in training_samples]
            dist = get_distribution()

        model_obj.train(X, y, save_path=MODEL_PATH)
        ext = FeatureExtractor()  # fresh extractor after training

        with state_lock:
            global extractor
            extractor = ext

        return jsonify({
            "status": "ok",
            "message": f"Model trained on {len(y)} samples. Saved to {MODEL_PATH}",
            "distribution": dist,
            "feature_importance": model_obj.get_importance_ranked(),
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/clear", methods=["POST"])
def api_clear():
    global training_samples
    with state_lock:
        training_samples = []
        if os.path.exists(TRAINING_DATA_PATH):
            os.remove(TRAINING_DATA_PATH)
        extractor.reset()
    return jsonify({"status": "ok", "message": "Training data cleared."}), 200


@app.route("/api/model/status")
def api_model_status():
    with state_lock:
        info = {
            "trained": model_obj.trained,
            "total_samples": len(training_samples),
            "distribution": get_distribution(),
        }
    return jsonify(info), 200


# ---- Settings endpoints ----------------------------------------------------

@app.route("/api/co2/toggle", methods=["POST"])
def api_co2_toggle():
    global co2_enabled
    with state_lock:
        co2_enabled = not co2_enabled
        st = co2_enabled
    return jsonify({"status": "ok", "co2_enabled": st}), 200


@app.route("/api/window", methods=["POST"])
def api_window():
    global window_sec
    try:
        data = request.get_json()
        new_sec = float(data.get("window_sec", 10))
        if new_sec < 1 or new_sec > 120:
            return jsonify({"status": "error", "message": "Window must be 1-120 seconds"}), 400
        with state_lock:
            window_sec = new_sec
        return jsonify({"status": "ok", "window_sec": window_sec}), 200
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid window_sec value"}), 400


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    # load persisted training data
    loaded = load_training_data()
    training_samples = loaded
    print(f"Loaded {len(loaded)} training samples from {TRAINING_DATA_PATH}")

    # load model if exists
    if os.path.exists(MODEL_PATH):
        ok = model_obj.load(MODEL_PATH)
        print(f"Model loaded: {MODEL_PATH}" if ok else "Model failed to load")
    else:
        print("No model found. Collect training data first.")

    # start background aggregator
    agg_thread = threading.Thread(target=window_aggregator, daemon=True)
    agg_thread.start()

    print(f"\n  Seat Detection Server")
    print(f"  Dashboard : http://0.0.0.0:5000")
    print(f"  SSE stream: http://0.0.0.0:5000/stream")
    print(f"  Window    : {window_sec}s  |  CO2 horizon: {CO2_HORIZON_SEC}s  |  CO2: {'ON' if co2_enabled else 'OFF'}\n")

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

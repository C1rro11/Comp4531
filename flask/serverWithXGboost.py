import threading
import time
import numpy as np
from collections import deque
from datetime import datetime
from flask import Flask, request, jsonify
import xgboost as xgb
import pickle
import os

app = Flask(__name__)

# ========== Configuration ==========
WINDOW_SEC = 5
DEBUG = False
model_file = "xgboost_seat_model_3class.pkl"

# ========== Data Buffers ==========
mmwave_buffer = deque()  # (timestamp, detection, distance, energy_array)
sdc40_buffer = deque()  # (timestamp, co2, temperature, humidity)
pressure_buffer = (
    deque()
)  # (timestamp, pressure_binary)  # 1 = occupied seat, 0 = empty seat

# Training data: list of (feature_vector, label)  label: 0=empty, 1=occupied, 2=hoarded
training_samples = []
model = None

prev_features = None
current_window_features = None
current_window_time = None

# Auto-collection
collecting_active = False
collecting_class = None  # 0, 1, or 2
collecting_target = 0
collecting_count = 0


# ========== Feature Aggregation ==========
def aggregate_window(mmwave_items, sdc40_items, pressure_items, prev_feat=None):
    features = []

    # --- mmWave features ---
    if len(mmwave_items) > 0:
        distances = [d for (_, d, _) in mmwave_items]
        detections = [det for (det, _, _) in mmwave_items]
        features.append(np.mean(distances))
        features.append(np.max(distances))
        features.append(np.min(distances))
        features.append(np.std(distances) if len(distances) > 1 else 0)
        features.append(np.mean(detections))
        features.append(np.sum(detections))
        features.append(len(mmwave_items))
        # gate energies (first 3)
        energy_arrays = [e for (_, _, e) in mmwave_items if e is not None]
        if energy_arrays:
            energy_means = np.mean(energy_arrays, axis=0)
            for i in range(min(3, len(energy_means))):
                features.append(energy_means[i])
        else:
            features.extend([0, 0, 0])
    else:
        features.extend([0] * 10)  # 7 + 3

    # --- SDC40 features ---
    if len(sdc40_items) > 0:
        co2s = [c for (c, _, _) in sdc40_items]
        temps = [t for (_, t, _) in sdc40_items]
        hums = [h for (_, _, h) in sdc40_items]
        features.append(np.mean(co2s))
        features.append(np.std(co2s) if len(co2s) > 1 else 0)
        features.append(np.mean(temps))
        features.append(np.std(temps) if len(temps) > 1 else 0)
        features.append(np.mean(hums))
        features.append(np.std(hums) if len(hums) > 1 else 0)
        # CO₂ rate (ppm/s)
        if len(co2s) > 1:
            time_span = len(co2s) * 5  # assuming 5s between CO₂ reads
            features.append((co2s[-1] - co2s[0]) / max(0.1, time_span))
        else:
            features.append(0)
    else:
        features.extend([400, 0, 22, 0, 50, 0, 0])

    # --- Seat pressure feature (binary) ---
    if len(pressure_items) > 0:
        # average binary pressure over window (0..1)
        avg_pressure = np.mean(
            pressure_items
        )  # pressure_items already is list of floats
        features.append(avg_pressure)
    else:
        features.append(0)

    # --- Delta features (difference from previous window) ---
    if prev_feat is not None:
        # only compare the non‑delta part (first len(features) without previous deltas)
        for i in range(len(features)):
            if i < len(prev_feat):
                features.append(features[i] - prev_feat[i])
            else:
                features.append(0)
    else:
        features.extend([0] * len(features))

    return features


# ========== Background Aggregator ==========
def window_aggregator():
    global current_window_features, current_window_time
    global \
        collecting_active, \
        collecting_class, \
        collecting_target, \
        collecting_count, \
        training_samples
    global prev_features
    last_aggregation = time.time()

    while True:
        now = time.time()
        if now - last_aggregation >= WINDOW_SEC:
            cutoff = now - WINDOW_SEC
            mm_items = [
                (d, dist, eng) for (ts, d, dist, eng) in mmwave_buffer if ts >= cutoff
            ]
            sdc_items = [(c, t, h) for (ts, c, t, h) in sdc40_buffer if ts >= cutoff]
            pressure_items = [(p) for (ts, p) in pressure_buffer if ts >= cutoff]

            if mm_items or sdc_items or pressure_items:
                feat = aggregate_window(
                    mm_items, sdc_items, pressure_items, prev_features
                )
                prev_features = feat.copy()
                current_window_features = feat
                current_window_time = datetime.now().strftime("%H:%M:%S")
                if DEBUG:
                    print(
                        f"\n[Window {current_window_time}] Features: {np.round(feat, 2)}"
                    )

                # Auto-collection
                if collecting_active and collecting_class is not None:
                    training_samples.append((feat, collecting_class))
                    collecting_count += 1
                    label_names = ["EMPTY", "OCCUPIED", "HOARDED"]
                    print(
                        f"   → Auto-labeled as {label_names[collecting_class]} ({collecting_count}/{collecting_target})"
                    )
                    if collecting_count >= collecting_target:
                        print(
                            f"   ✅ Finished collecting {collecting_target} '{label_names[collecting_class]}' samples."
                        )
                        collecting_active = False
                        collecting_class = None
                else:
                    # Inference
                    if model is not None:
                        proba = model.predict_proba([feat])[0]
                        pred = np.argmax(proba)
                        conf = proba[pred]
                        label_names = ["EMPTY", "OCCUPIED", "HOARDED"]
                        if DEBUG:
                            print(
                                f"   → Inference: {label_names[pred]} (conf: {conf:.3f})"
                            )
            else:
                if DEBUG:
                    print(f"\n[Window] No data in last {WINDOW_SEC}s.")

            last_aggregation = now
        time.sleep(0.5)


# ========== Train 3‑Class Model ==========
def train_model():
    global model
    if len(training_samples) < 6:
        print("Need at least 6 samples (preferably from all 3 classes).")
        return
    X = np.array([s[0] for s in training_samples])
    y = np.array([s[1] for s in training_samples])
    unique = np.unique(y)
    if len(unique) < 2:
        print("Need at least two classes to train.")
        return
    # Use CalibratedClassifierCV for better probabilities (works with multi‑class)
    from sklearn.calibration import CalibratedClassifierCV

    base_model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
    )
    model = CalibratedClassifierCV(base_model, method="sigmoid", cv=3)
    model.fit(X, y)
    with open(model_file, "wb") as f:
        pickle.dump(model, f)
    # Print class distribution
    occ = np.sum(y == 1)
    emp = np.sum(y == 0)
    hoa = np.sum(y == 2)
    print(
        f"Model trained on {len(y)} samples: EMPTY={emp}, OCCUPIED={occ}, HOARDED={hoa}"
    )


# ========== Console Listener ==========
def console_listener():
    global \
        DEBUG, \
        WINDOW_SEC, \
        collecting_active, \
        collecting_class, \
        collecting_target, \
        collecting_count, \
        training_samples, \
        model
    print("\n=== 3‑Class XGBoost Training Console ===")
    print("Commands:")
    print("  debug                       - Toggle debug printing")
    print("  set_window <seconds>        - Change aggregation window (default 5)")
    print("  collect empty <N>           - Auto-label next N windows as EMPTY")
    print("  collect occupied <N>        - Auto-label next N windows as OCCUPIED")
    print("  collect hoarded <N>         - Auto-label next N windows as HOARDED")
    print("  stop                        - Stop current collection")
    print("  train                       - Train model with collected data")
    print("  status                      - Show collected samples per class")
    print("  predict                     - Run inference on latest window")
    print("  save                        - Save training data to CSV")
    print("  clear                       - Clear all training samples")
    while True:
        cmd = input().strip().lower()
        if cmd == "debug":
            DEBUG = not DEBUG
            print(f"Debug mode: {'ON' if DEBUG else 'OFF'}")
        elif cmd.startswith("set_window"):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                WINDOW_SEC = int(parts[1])
                print(f"Window set to {WINDOW_SEC} seconds.")
            else:
                print("Usage: set_window <seconds>")
        elif cmd.startswith("collect"):
            parts = cmd.split()
            if len(parts) < 3:
                print("Usage: collect <empty|occupied|hoarded> <N>")
                continue
            class_str = parts[1]
            if class_str == "empty":
                cls = 0
                name = "EMPTY"
            elif class_str == "occupied":
                cls = 1
                name = "OCCUPIED"
            elif class_str == "hoarded":
                cls = 2
                name = "HOARDED"
            else:
                print("Class must be 'empty', 'occupied', or 'hoarded'")
                continue
            count = 20
            if len(parts) >= 3 and parts[2].isdigit():
                count = int(parts[2])
            collecting_active = True
            collecting_class = cls
            collecting_target = count
            collecting_count = 0
            print(
                f"Started collecting {count} '{name}' samples. Each new window will be auto-labeled."
            )
        elif cmd == "stop":
            if collecting_active:
                collecting_active = False
                collecting_class = None
                print("Stopped current collection.")
            else:
                print("No active collection.")
        elif cmd == "train":
            train_model()
        elif cmd == "status":
            emp = sum(1 for _, l in training_samples if l == 0)
            occ = sum(1 for _, l in training_samples if l == 1)
            hoa = sum(1 for _, l in training_samples if l == 2)
            print(
                f"Collected: EMPTY={emp}, OCCUPIED={occ}, HOARDED={hoa}, Total={len(training_samples)}"
            )
        elif cmd == "predict":
            if current_window_features is not None and model is not None:
                proba = model.predict_proba([current_window_features])[0]
                pred = np.argmax(proba)
                conf = proba[pred]
                labels = ["EMPTY", "OCCUPIED", "HOARDED"]
                print(f"Latest window: {labels[pred]} (conf: {conf:.3f})")
                if DEBUG:
                    print(
                        f"  Probabilities: EMPTY={proba[0]:.3f}, OCCUPIED={proba[1]:.3f}, HOARDED={proba[2]:.3f}"
                    )
            else:
                print("No model or no window features.")
        elif cmd == "save":
            if training_samples:
                import pandas as pd

                X_df = pd.DataFrame([f for f, _ in training_samples])
                X_df["label"] = [l for _, l in training_samples]
                X_df.to_csv("training_data_3class.csv", index=False)
                print("Saved to training_data_3class.csv")
            else:
                print("No training data.")
        elif cmd == "clear":
            training_samples.clear()
            print("All training samples cleared.")
        else:
            print("Unknown command.")


# ========== Flask Routes (silent unless DEBUG) ==========
@app.route("/", methods=["GET"])
def index():
    return "ESP32 + XGBoost 3‑Class Sensor Fusion Server"


@app.route("/mmwave", methods=["POST"])
def receive_mmwave():
    try:
        data = request.get_json()
        detection = data.get("detection")
        distance = data.get("distance")
        energyArray = data.get("energyArray")
        mmwave_buffer.append((time.time(), detection, distance, energyArray))
        while mmwave_buffer and mmwave_buffer[0][0] < time.time() - 120:
            mmwave_buffer.popleft()
        if DEBUG:
            print(f"mmWave: det={detection}, dist={distance:.1f}cm")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        if DEBUG:
            print(f"mmWave error: {e}")
        return jsonify({"status": "error"}), 500


@app.route("/sdc40", methods=["POST"])
def receive_sdc40():
    try:
        data = request.get_json()
        co2 = data.get("co2")
        temp = data.get("temperature")
        hum = data.get("humidity")
        sdc40_buffer.append((time.time(), co2, temp, hum))
        while sdc40_buffer and sdc40_buffer[0][0] < time.time() - 120:
            sdc40_buffer.popleft()
        if DEBUG:
            print(f"SCD40: CO2={co2}ppm, {temp:.1f}C, {hum:.1f}%")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        if DEBUG:
            print(f"SCD40 error: {e}")
        return jsonify({"status": "error"}), 500


@app.route("/seat_state", methods=["POST"])
def receive_seat_state():
    try:
        data = request.get_json()
        # seatState string: "seatOccupied" or "empty"
        seat_str = data.get("seatState", "empty")
        pressure_binary = 1.0 if seat_str == "seatOccupied" else 0.0
        pressure_buffer.append((time.time(), pressure_binary))
        while pressure_buffer and pressure_buffer[0][0] < time.time() - 120:
            pressure_buffer.popleft()
        if DEBUG:
            print(f"Seat state: {seat_str} -> pressure={pressure_binary}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        if DEBUG:
            print(f"seat_state error: {e}")
        return jsonify({"status": "error"}), 500


@app.route("/nfc", methods=["POST"])
def receive_nfc():
    if DEBUG:
        data = request.get_json()
        print(f"NFC card: {data.get('uid')}")
    return jsonify({"status": "ok"}), 200


# ========== Main ==========
if __name__ == "__main__":
    agg_thread = threading.Thread(target=window_aggregator, daemon=True)
    agg_thread.start()
    console_thread = threading.Thread(target=console_listener, daemon=True)
    console_thread.start()
    print("Starting 3‑Class XGBoost server on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

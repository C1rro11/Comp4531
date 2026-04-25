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

# ========== Data Buffers ==========
mmwave_buffer = deque()
sdc40_buffer = deque()

WINDOW_SEC = 30
# Training data: list of (feature_vector, label)  label: 1=here, 0=away
training_samples = []
model = None
model_file = "xgboost_seat_model.pkl"

# ========== Auto-collection control ==========
collecting_active = False
collecting_class = None  # 1 for 'here', 0 for 'away'
collecting_target = 0
collecting_count = 0
current_window_features = None
current_window_time = None


# ========== Helper: Aggregate window ==========
def aggregate_window(mmwave_items, sdc40_items):
    features = []
    # mmWave features
    if len(mmwave_items) > 0:
        distances = [d for (_, d, _) in mmwave_items]
        detections = [det for (det, _, _) in mmwave_items]
        features.append(np.mean(distances))
        features.append(np.max(distances))
        features.append(np.min(distances))
        features.append(np.std(distances))
        features.append(np.mean(detections))
        features.append(np.sum(detections))
        features.append(len(mmwave_items))
    else:
        features.extend([0, 0, 0, 0, 0, 0, 0])

    # SDC40 features
    if len(sdc40_items) > 0:
        co2s = [c for (c, _, _) in sdc40_items]
        temps = [t for (_, t, _) in sdc40_items]
        hums = [h for (_, _, h) in sdc40_items]
        features.append(np.mean(co2s))
        features.append(np.std(co2s))
        features.append(np.mean(temps))
        features.append(np.std(temps))
        features.append(np.mean(hums))
        features.append(np.std(hums))
    else:
        features.extend([400, 0, 22, 0, 50, 0])

    # Energy means (first 3 gates)
    if len(mmwave_items) > 0 and mmwave_items[0][2] is not None:
        energy_means = np.mean(
            [e for (_, _, e) in mmwave_items if e is not None], axis=0
        )
        for i in range(min(3, len(energy_means))):
            features.append(energy_means[i])
    else:
        features.extend([0, 0, 0])
    return features


# ========== Background window aggregator ==========
def window_aggregator():
    global current_window_features, current_window_time
    global \
        collecting_active, \
        collecting_class, \
        collecting_target, \
        collecting_count, \
        training_samples
    last_aggregation = time.time()

    while True:
        now = time.time()
        if now - last_aggregation >= WINDOW_SEC:
            cutoff = now - WINDOW_SEC
            mm_items = [
                (d, dist, eng) for (ts, d, dist, eng) in mmwave_buffer if ts >= cutoff
            ]
            sdc_items = [(c, t, h) for (ts, c, t, h) in sdc40_buffer if ts >= cutoff]

            if mm_items or sdc_items:
                feat = aggregate_window(mm_items, sdc_items)
                window_time = datetime.now().strftime("%H:%M:%S")
                print(f"\n[Window {window_time}] Features: {np.round(feat, 2)}")

                # Auto-collect if active
                if collecting_active and collecting_class is not None:
                    training_samples.append((feat, collecting_class))
                    collecting_count += 1
                    label_str = "HERE" if collecting_class == 1 else "AWAY"
                    print(
                        f"   → Auto-labeled as {label_str} ({collecting_count}/{collecting_target})"
                    )
                    if collecting_count >= collecting_target:
                        print(
                            f"   ✅ Finished collecting {collecting_target} '{label_str}' samples."
                        )
                        collecting_active = False
                        collecting_class = None
                else:
                    # Inference mode
                    if model is not None:
                        pred = model.predict([feat])[0]
                        prob = model.predict_proba([feat])[0][1]
                        state = "HERE" if pred == 1 else "AWAY"
                        print(f"   → Inference: {state} (conf: {prob:.2f})")
                    else:
                        print(
                            "   → No model trained yet. Use 'train' after collecting data."
                        )
            else:
                print(f"\n[Window] No data in last {WINDOW_SEC}s.")

            last_aggregation = now

        time.sleep(1)


# ========== Train model ==========
def train_model():
    global model
    if len(training_samples) < 2:
        print("Need at least 2 samples (both classes) to train.")
        return
    # Check if both classes present
    labels = [l for _, l in training_samples]
    if len(set(labels)) < 2:
        print("Need samples from both classes (here and away).")
        return
    X = np.array([s[0] for s in training_samples])
    y = np.array([s[1] for s in training_samples])
    model = xgb.XGBClassifier(
        n_estimators=50, max_depth=3, use_label_encoder=False, eval_metric="logloss"
    )
    model.fit(X, y)
    with open(model_file, "wb") as f:
        pickle.dump(model, f)
    print(
        f"Model trained on {len(training_samples)} samples (HERE: {sum(y)}, AWAY: {len(y) - sum(y)}) and saved."
    )


# ========== Console listener ==========
def console_listener():
    global collecting_active, collecting_class, collecting_target, collecting_count
    print("\n=== XGBoost Training Console ===")
    print("Commands:")
    print(
        "  collect_data here [N]   - Automatically label next N windows as 'here' (N=20 default)"
    )
    print("  collect_data away [N]   - Automatically label next N windows as 'away'")
    print("  stop                    - Stop current collection")
    print("  train                   - Train model with collected data")
    print("  status                  - Show collected samples")
    print(
        "  predict                 - Run inference on latest window (if model exists)"
    )
    print("  save                    - Save current training data to CSV")
    while True:
        cmd = input().strip().lower()
        if cmd.startswith("collect_data"):
            parts = cmd.split()
            if len(parts) < 3:
                print("Usage: collect_data here [count] or collect_data away [count]")
                continue
            class_str = parts[1]
            if class_str == "here":
                cls = 1
                label_name = "HERE"
            elif class_str == "away":
                cls = 0
                label_name = "AWAY"
            else:
                print("Class must be 'here' or 'away'")
                continue
            count = 20
            if len(parts) >= 3 and parts[2].isdigit():
                count = int(parts[2])
            collecting_active = True
            collecting_class = cls
            collecting_target = count
            collecting_count = 0
            print(
                f"Started collecting {count} '{label_name}' samples. Each new window will be auto-labeled."
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
            here_count = sum(1 for _, l in training_samples if l == 1)
            away_count = sum(1 for _, l in training_samples if l == 0)
            print(
                f"Collected samples: HERE = {here_count}, AWAY = {away_count}, Total = {len(training_samples)}"
            )
        elif cmd == "predict":
            if current_window_features is not None and model is not None:
                pred = model.predict([current_window_features])[0]
                prob = model.predict_proba([current_window_features])[0][1]
                print(
                    f"Latest window prediction: {'HERE' if pred == 1 else 'AWAY'} (conf: {prob:.2f})"
                )
            else:
                print("No model or no window features yet.")
        elif cmd == "save":
            if training_samples:
                import pandas as pd

                df = pd.DataFrame([f for f, _ in training_samples])
                df["label"] = [l for _, l in training_samples]
                df.to_csv("training_data.csv", index=False)
                print("Saved to training_data.csv")
            else:
                print("No training data to save.")
        else:
            print("Unknown command.")


# ========== Flask Routes ==========
@app.route("/", methods=["GET"])
def index():
    return "ESP32 + XGBoost Auto-collection Server"


@app.route("/mmwave", methods=["POST"])
def receive_mmwave():
    data = request.get_json()
    mmwave_buffer.append(
        (time.time(), data["detection"], data["distance"], data.get("energyArray"))
    )
    while mmwave_buffer and mmwave_buffer[0][0] < time.time() - 120:
        mmwave_buffer.popleft()
    return jsonify({"status": "ok"}), 200


@app.route("/sdc40", methods=["POST"])
def receive_sdc():
    data = request.get_json()
    sdc40_buffer.append(
        (time.time(), data["co2"], data["temperature"], data["humidity"])
    )
    while sdc40_buffer and sdc40_buffer[0][0] < time.time() - 120:
        sdc40_buffer.popleft()
    return jsonify({"status": "ok"}), 200


@app.route("/nfc", methods=["POST"])
def receive_nfc():
    print(f"NFC card: {request.get_json().get('uid')}")
    return jsonify({"status": "ok"}), 200


@app.route("/seat_state", methods=["POST"])
def receive_seat_state():
    print(f"Seat state: {request.get_json().get('seatState')}")
    return jsonify({"status": "ok"}), 200


# ========== Main ==========
if __name__ == "__main__":
    agg_thread = threading.Thread(target=window_aggregator, daemon=True)
    agg_thread.start()
    console_thread = threading.Thread(target=console_listener, daemon=True)
    console_thread.start()
    print("Starting Flask server on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

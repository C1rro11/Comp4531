#!/usr/bin/env python3
"""
seat_xgboost.py  —  XGBoost seat-occupancy ML for ESP32 sensor streams
=======================================================================

Run alongside your main Flask server (port 5000). This server listens on
port 5001. Point your ESP32 at BOTH servers, or bridge them via the optional
forwarder at the bottom of server.py (see integration note).

Commands
--------
  python seat_xgboost.py train <label> <n>
      Wait 5 s (get into position!), then collect <n> feature-vectors
      labelled <label> from live sensor data.
      Labels:  occupied | seatEmpty
      Example: python seat_xgboost.py train occupied   150
               python seat_xgboost.py train seatEmpty  150

  python seat_xgboost.py fit
      Train an XGBoost classifier on all collected data, print a full
      classification report + feature-importance bar chart, and save the
      model to seat_model.pkl.

  python seat_xgboost.py predict
      Load seat_model.pkl and run live inference on every incoming sensor
      reading. Predictions print in-place with a confidence bar.

  python seat_xgboost.py status
      Show a summary of collected training data and model info.

  python seat_xgboost.py clear
      ⚠  Delete training_data.pkl and seat_model.pkl (fresh start).

Feature engineering (rolling window = 5 readings)
--------------------------------------------------
mmWave  →  dist_cur, dist_mean, dist_std, dist_delta, det_cur, det_mean
SCD40   →  co2_cur,  co2_mean,  co2_delta (window trend), co2_rate (step),
           temp_cur, hum_cur

The delta / rate features let the model detect occupancy *changes*, not just
static snapshots — crucial for transitions like "just walked past" vs "sat down".
"""

import os, sys, time, pickle, threading, numpy as np
from collections import deque, Counter
from flask import Flask, request, jsonify

# ─────────────────────────── configuration ──────────────────────────────────
PORT        = 5001
WINDOW      = 5          # rolling-window length  (3–5 works well)
COUNTDOWN   = 5          # seconds before collection actually starts
MODEL_FILE  = "seat_model.pkl"
DATA_FILE   = "training_data.pkl"

FEATURE_NAMES = [
    "dist_cur",    # latest mmWave distance (cm)
    "dist_mean",   # window mean distance
    "dist_std",    # window std  — high = moving, low = stationary
    "dist_delta",  # dist[last] – dist[first]  (drift across window)
    "det_cur",     # latest detection flag  (0 / 1)
    "det_mean",    # detection fraction over window  (reliability)
    "co2_cur",     # latest CO₂ (ppm)
    "co2_mean",    # window mean CO₂
    "co2_delta",   # co2[last] – co2[first]  (window trend: rising = occupied)
    "co2_rate",    # co2[last] – co2[last-1] (step velocity)
    "temp_cur",    # latest temperature (°C)
    "hum_cur",     # latest humidity (%)
]

# ──────────────────────────── shared buffers ────────────────────────────────
_lock       = threading.Lock()
_mmwave_buf = deque(maxlen=WINDOW)
_sdc_buf    = deque(maxlen=WINDOW)

# ──────────────────────────── collection state ──────────────────────────────
_col_active   = False
_col_label    = None
_col_target   = 0
_col_count    = 0
_col_start_ts = 0.0     # unix ts: do NOT collect before this
_session_X    = []      # in-memory buffer for current collection session
_session_y    = []

# ──────────────────────────── loaded model ──────────────────────────────────
_model_data   = None    # dict loaded from MODEL_FILE


# ─────────────────────────── feature extraction ─────────────────────────────
def _extract(mm_list, sd_list):
    """
    Build a 12-element feature vector from two snapshot lists.
    Returns None if either buffer has fewer than 2 readings.
    """
    if len(mm_list) < 2 or len(sd_list) < 2:
        return None

    dists = [r["distance"]          for r in mm_list]
    dets  = [float(r["detection"])  for r in mm_list]
    co2s  = [r["co2"]               for r in sd_list]
    temps = [r["temp"]              for r in sd_list]
    hums  = [r["hum"]               for r in sd_list]

    return [
        dists[-1],                           # dist_cur
        float(np.mean(dists)),               # dist_mean
        float(np.std(dists)),                # dist_std
        float(dists[-1] - dists[0]),         # dist_delta  (window)
        dets[-1],                            # det_cur
        float(np.mean(dets)),                # det_mean
        co2s[-1],                            # co2_cur
        float(np.mean(co2s)),                # co2_mean
        float(co2s[-1] - co2s[0]),           # co2_delta   (window trend)
        float(co2s[-1] - co2s[-2]),          # co2_rate    (step velocity)
        temps[-1],                           # temp_cur
        hums[-1],                            # hum_cur
    ]


# ──────────────────────────── data persistence ──────────────────────────────
def _load_data():
    if not os.path.exists(DATA_FILE):
        return [], []
    with open(DATA_FILE, "rb") as f:
        d = pickle.load(f)
    return d["X"], d["y"]


def _save_data(X, y):
    with open(DATA_FILE, "wb") as f:
        pickle.dump({"X": X, "y": y}, f)


# ────────────────────────── feature handler ─────────────────────────────────
def _handle(feats):
    """
    Called on every new sensor reading (after lock is released).
    Dispatches to collection mode or live prediction mode.
    """
    global _col_active, _col_count
    now = time.time()

    # ── Training / collection mode ───────────────────────────────────────────
    if _col_active:
        if now < _col_start_ts:
            remaining = int(_col_start_ts - now) + 1
            print(f"\r  ⏳  Starting in {remaining}s … get into position!     ",
                  end="", flush=True)
            return

        _session_X.append(feats)
        _session_y.append(_col_label)
        _col_count += 1

        pct    = _col_count / _col_target
        filled = int(pct * 24)
        bar    = "█" * filled + "░" * (24 - filled)
        print(f"\r  [{bar}] {_col_count:4d}/{_col_target}  label='{_col_label}'",
              end="", flush=True)

        if _col_count >= _col_target:
            _col_active = False
            X_old, y_old = _load_data()
            X_new = X_old + _session_X
            y_new = y_old + _session_y
            _save_data(X_new, y_new)
            counts = dict(Counter(y_new))
            print(f"\n\n  ✓  {_col_count} new samples saved → {DATA_FILE}")
            print(f"     Dataset totals: {counts}")
            print(f"     Next step: python seat_xgboost.py fit\n")
            threading.Thread(target=lambda: (time.sleep(0.4), os._exit(0)),
                             daemon=True).start()
        return

    # ── Live prediction mode ─────────────────────────────────────────────────
    if _model_data is None:
        return

    model = _model_data["model"]
    le    = _model_data["le"]
    X     = np.array(feats, dtype=np.float32).reshape(1, -1)

    pred_idx = model.predict(X)[0]
    proba    = model.predict_proba(X)[0]
    label    = le.inverse_transform([pred_idx])[0]
    conf     = proba.max() * 100
    filled   = int(conf / 5)
    bar      = "█" * filled + "░" * (20 - filled)
    icon     = "🟢 OCCUPIED " if "occupied" in label.lower() else "⬜ EMPTY    "

    print(
        f"\r  {icon} [{bar}] {conf:5.1f}%"
        f"  dist={feats[0]:5.0f}cm  Δdist={feats[3]:+5.0f}"
        f"  CO₂={feats[6]:5.0f}ppm  ΔCO₂={feats[8]:+5.0f}",
        end="", flush=True,
    )


# ──────────────────────────── Flask endpoints ────────────────────────────────
app = Flask(__name__)
app.logger.disabled = True


@app.route("/", methods=["GET"])
def index():
    return "seat_xgboost server running on port 5001"


@app.route("/mmwave", methods=["POST"])
def recv_mmwave():
    data = request.get_json(silent=True)
    if data:
        with _lock:
            _mmwave_buf.append({
                "detection": bool(data.get("detection", False)),
                "distance":  float(data.get("distance", 0)),
            })
            snap_mm = list(_mmwave_buf)
            snap_sd = list(_sdc_buf)
        feats = _extract(snap_mm, snap_sd)
        if feats:
            _handle(feats)
    return jsonify({"status": "ok"})


@app.route("/sdc40", methods=["POST"])
def recv_sdc():
    data = request.get_json(silent=True)
    if data:
        with _lock:
            _sdc_buf.append({
                "co2":  float(data.get("co2",         0)),
                "temp": float(data.get("temperature", 0)),
                "hum":  float(data.get("humidity",    0)),
            })
            snap_mm = list(_mmwave_buf)
            snap_sd = list(_sdc_buf)
        feats = _extract(snap_mm, snap_sd)
        if feats:
            _handle(feats)
    return jsonify({"status": "ok"})


# ──────────────────────────── CLI — train ────────────────────────────────────
def cmd_train(label, n):
    global _col_active, _col_label, _col_target, _col_count, _col_start_ts
    global _session_X, _session_y

    _session_X    = []
    _session_y    = []
    _col_label    = label
    _col_target   = n
    _col_count    = 0
    _col_start_ts = time.time() + COUNTDOWN
    _col_active   = True

    print(f"\n  📡  seat_xgboost — COLLECT  label='{label}'  n={n}")
    print(f"       Server  :  http://0.0.0.0:{PORT}/mmwave  +  /sdc40")
    print(f"       Window  :  {WINDOW} readings")
    print(f"       Delay   :  {COUNTDOWN}s countdown before capture starts\n")

    # Suppress Flask startup noise
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=PORT, debug=False)


# ──────────────────────────── CLI — fit ──────────────────────────────────────
def cmd_fit():
    try:
        import xgboost as xgb
    except ImportError:
        print("  ✗  xgboost not installed.  Run: pip install xgboost")
        sys.exit(1)

    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
    from sklearn.preprocessing   import LabelEncoder
    from sklearn.metrics         import classification_report, accuracy_score

    X_list, y_list = _load_data()
    if len(X_list) < 10:
        print(f"  ✗  Only {len(X_list)} samples — collect more first.")
        return

    counts = dict(Counter(y_list))
    print(f"\n  📦  Loaded {len(X_list)} samples: {counts}")

    le = LabelEncoder()
    y  = le.fit_transform(y_list)
    X  = np.array(X_list, dtype=np.float32)

    # ── Model ────────────────────────────────────────────────────────────────
    model = xgb.XGBClassifier(
        n_estimators      = 300,
        max_depth         = 4,
        learning_rate     = 0.08,
        subsample         = 0.8,
        colsample_bytree  = 0.8,
        min_child_weight  = 3,
        gamma             = 0.1,
        reg_alpha         = 0.05,
        reg_lambda        = 1.0,
        use_label_encoder = False,
        eval_metric       = "logloss",
        random_state      = 42,
        verbosity         = 0,
    )

    # ── Cross-validation ─────────────────────────────────────────────────────
    cv_scores = cross_val_score(model, X, y,
                                cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
                                scoring="accuracy")
    print(f"  CV accuracy:  {cv_scores.mean()*100:.1f}% ± {cv_scores.std()*100:.1f}%")

    # ── Final train / test split ─────────────────────────────────────────────
    test_size = max(0.15, min(0.25, 30 / len(X)))
    try:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y)
    except ValueError:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=42)

    model.fit(X_tr, y_tr,
              eval_set=[(X_te, y_te)],
              verbose=False)

    y_pred = model.predict(X_te)
    acc    = accuracy_score(y_te, y_pred)

    print(f"  Hold-out acc: {acc*100:.1f}%\n")
    print(classification_report(y_te, y_pred, target_names=le.classes_))

    # ── Feature importance ───────────────────────────────────────────────────
    importance = model.feature_importances_
    ranked     = sorted(zip(FEATURE_NAMES, importance), key=lambda x: -x[1])
    print("  Feature importance (gain):")
    for fname, imp in ranked:
        bar = "█" * int(imp * 40)
        print(f"    {fname:12s}  {bar:<40s}  {imp:.3f}")

    # ── Save ─────────────────────────────────────────────────────────────────
    save_data = {
        "model":    model,
        "le":       le,
        "classes":  le.classes_.tolist(),
        "features": FEATURE_NAMES,
        "window":   WINDOW,
        "n_train":  len(y_list),
        "accuracy": acc,
        "cv_mean":  float(cv_scores.mean()),
    }
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(save_data, f)

    print(f"\n  ✓  Model saved → {MODEL_FILE}")
    print(f"     CV {cv_scores.mean()*100:.1f}%  |  hold-out {acc*100:.1f}%\n")


# ──────────────────────────── CLI — predict ──────────────────────────────────
def cmd_predict():
    global _model_data

    if not os.path.exists(MODEL_FILE):
        print(f"  ✗  No model at '{MODEL_FILE}'.  Run: python seat_xgboost.py fit")
        sys.exit(1)

    with open(MODEL_FILE, "rb") as f:
        _model_data = pickle.load(f)

    classes = _model_data["classes"]
    acc     = _model_data.get("accuracy", 0) * 100

    print(f"\n  🤖  seat_xgboost — PREDICT")
    print(f"      Model   : {MODEL_FILE}")
    print(f"      Classes : {classes}")
    print(f"      Acc     : {acc:.1f}%  (hold-out)")
    print(f"      Server  : http://0.0.0.0:{PORT}/mmwave  +  /sdc40")
    print(f"      Waiting for sensor data …\n")

    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=PORT, debug=False)


# ──────────────────────────── CLI — status ───────────────────────────────────
def cmd_status():
    X, y = _load_data()
    counts = Counter(y)

    print(f"\n  📊  Training data  —  '{DATA_FILE}'")
    if not X:
        print("      (no data yet — run the train command first)")
    else:
        print(f"      Total samples : {len(X)}")
        for lbl, cnt in sorted(counts.items()):
            bar = "█" * (cnt // 5)
            print(f"      {lbl:15s}: {cnt:5d}  {bar}")

    print()
    if os.path.exists(MODEL_FILE):
        with open(MODEL_FILE, "rb") as f:
            d = pickle.load(f)
        acc = d.get("accuracy", 0) * 100
        cv  = d.get("cv_mean",  0) * 100
        print(f"  🤖  Model  —  '{MODEL_FILE}'")
        print(f"      Trained on : {d['n_train']} samples")
        print(f"      CV acc     : {cv:.1f}%")
        print(f"      Hold-out   : {acc:.1f}%")
        print(f"      Classes    : {d['classes']}")
        print(f"      Features   : {d['features']}")
    else:
        print(f"  ⚠   No model found.  Run: python seat_xgboost.py fit")
    print()


# ──────────────────────────── CLI — clear ────────────────────────────────────
def cmd_clear():
    ans = input("  ⚠  Delete training data and model? (yes/no): ").strip().lower()
    if ans == "yes":
        for f in [DATA_FILE, MODEL_FILE]:
            if os.path.exists(f):
                os.remove(f)
                print(f"     Deleted {f}")
        print("  ✓  Cleared.\n")
    else:
        print("  Aborted.\n")


# ──────────────────────────── entry point ────────────────────────────────────
USAGE = """
Usage:
  python seat_xgboost.py train <label> <n>    e.g.  train occupied 150
  python seat_xgboost.py fit
  python seat_xgboost.py predict
  python seat_xgboost.py status
  python seat_xgboost.py clear
"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "train":
        if len(sys.argv) != 4:
            print("  Usage: python seat_xgboost.py train <label> <n>")
            sys.exit(1)
        label = sys.argv[2]
        try:
            n = int(sys.argv[3])
        except ValueError:
            print("  <n> must be an integer")
            sys.exit(1)
        if n < 10:
            print("  Collect at least 10 samples.")
            sys.exit(1)
        cmd_train(label, n)

    elif cmd == "fit":
        cmd_fit()

    elif cmd == "predict":
        cmd_predict()

    elif cmd == "status":
        cmd_status()

    elif cmd == "clear":
        cmd_clear()

    else:
        print(f"  Unknown command: '{cmd}'")
        print(USAGE)
        sys.exit(1)

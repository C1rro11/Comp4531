import os
import pickle

import numpy as np

FEATURE_RAW = 27
FEATURE_FULL = 54
LABELS = ["EMPTY", "OCCUPIED", "HOARDED"]

FEATURE_NAMES_RAW = [
    "dist_mean",     # 0
    "dist_max",      # 1
    "dist_min",      # 2
    "dist_std",      # 3
    "det_mean",      # 4
    "det_sum",       # 5
    "reading_count", # 6
    "gate_0",        # 7
    "gate_1",        # 8
    "gate_2",        # 9
    "gate_3",        # 10
    "gate_4",        # 11
    "gate_5",        # 12
    "gate_6",        # 13
    "gate_7",        # 14
    "gate_8",        # 15
    "gate_9",        # 16
    "gate_10",       # 17
    "gate_11",       # 18
    "gate_12",       # 19
    "gate_13",       # 20
    "gate_14",       # 21
    "gate_15",       # 22
    "co2_mean",      # 23
    "co2_std",       # 24
    "co2_rate",      # 25  ppm/s over 30s horizon
    "pressure",      # 26
]

FEATURE_NAMES_FULL = FEATURE_NAMES_RAW + ["Δ" + n for n in FEATURE_NAMES_RAW]


class FeatureExtractor:
    """
    Dual-horizon feature extraction:
      - 10s window for mmWave and pressure
      - 30s horizon for CO2 trend

    Output: 27 raw features + 27 delta features = 54 total.
      - mmWave dist/det     (0-6)   7 features
      - mmWave energy gates (7-22)  16 features — all individual gate values
      - CO2 30 s horizon    (23-25) 3 features
      - Pressure            (26)    1 persistent state
    """

    def __init__(self):
        self.prev_raw = None

    def extract_raw(self, mmwave_items, co30s, pressure):
        """
        mmwave_items : list of (detection, distance, energy_array)
                       energy_array is list of 16 floats (gates 0-15)
        co30s        : list of CO2 floats from last 30 s
        pressure     : float  (persistent last-known seat state 0.0 | 1.0)
        """
        feats = []

        # ── mmWave dist / det  (0‑6) ──────────────────────────────────
        if mmwave_items:
            dists = [d for (_, d, _) in mmwave_items]
            dets  = [d for (d, _, _) in mmwave_items]
            feats += [
                float(np.mean(dists)),
                float(np.max(dists)),
                float(np.min(dists)),
                float(np.std(dists)) if len(dists) > 1 else 0.0,
                float(np.mean(dets)),
                float(np.sum(dets)),
                float(len(mmwave_items)),
            ]
        else:
            feats += [0.0] * 7

        # ── mmWave energy — all 16 individual gates  (7‑22) ──────────
        energies = [
            np.array(e, dtype=np.float32)
            for (_, _, e) in mmwave_items
            if e is not None and len(e) >= 16
        ]
        if energies:
            avg = np.mean(energies, axis=0)        # shape (16,)  — mean per gate
            feats += avg.tolist()
        else:
            feats += [0.0] * 16

        # ── CO2 from 30 s horizon  (23‑25) ────────────────────────────
        if co30s and len(co30s) >= 2:
            c = [float(v) for v in co30s]
            feats += [
                float(np.mean(c)),
                float(np.std(c)),
                float((c[-1] - c[0]) / max(0.1, len(c) * 5)),
            ]
        elif co30s:
            v = float(co30s[-1])
            feats += [v, 0.0, 0.0]
        else:
            feats += [400.0, 0.0, 0.0]

        # ── Persistent pressure state  (26) ───────────────────────────
        feats.append(float(pressure))

        return feats

    def compute_deltas(self, current, previous):
        if previous is None:
            return [0.0] * len(current)
        return [current[i] - previous[i] for i in range(len(current))]

    def extract_full(self, mmwave_items, co30s, pressure):
        raw = self.extract_raw(mmwave_items, co30s, pressure)
        deltas = self.compute_deltas(raw, self.prev_raw)
        self.prev_raw = raw
        return raw + deltas

    def reset(self):
        self.prev_raw = None


class XGBoostModel:
    def __init__(self):
        self.model = None
        self.trained = False
        self.feature_importance = None

    def train(self, X, y, save_path=None):
        import xgboost as xgb
        from sklearn.calibration import CalibratedClassifierCV

        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int32)

        unique = np.unique(y)
        if len(unique) < 2:
            raise ValueError("Need at least two classes to train")

        base = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=3,
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            reg_lambda=3.0,
            reg_alpha=0.5,
            min_child_weight=5,
            random_state=42,
            verbosity=0,
        )
        self.model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
        self.model.fit(X, y)

        # Average feature importance across CV folds
        importances = []
        for est in self.model.calibrated_classifiers_:
            importances.append(est.estimator.feature_importances_)
        self.feature_importance = np.mean(importances, axis=0).tolist()

        self.trained = True

        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                pickle.dump(
                    {
                        "model": self.model,
                        "feature_importance": self.feature_importance,
                    },
                    f,
                )

        return self.model

    def load(self, path):
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            self.model = data.get("model")
            self.feature_importance = data.get("feature_importance")
        else:
            self.model = data
            self.feature_importance = None
        self.trained = self.model is not None
        return self.trained

    def predict_proba(self, features):
        if self.model is None:
            return None
        X = np.array(features, dtype=np.float32).reshape(1, -1)
        proba = self.model.predict_proba(X)[0]
        return {
            "EMPTY": round(float(proba[0]), 4),
            "OCCUPIED": round(float(proba[1]), 4),
            "HOARDED": round(float(proba[2]), 4),
        }

    def predict(self, features):
        probs = self.predict_proba(features)
        if probs is None:
            return ("NO_MODEL", 0.0)
        best = max(probs, key=probs.get)
        return (best, probs[best])

    def get_importance_ranked(self):
        if self.feature_importance is None:
            return None
        ranked = sorted(
            zip(FEATURE_NAMES_FULL, self.feature_importance),
            key=lambda x: -x[1],
        )
        return [{"feature": n, "importance": round(v, 4)} for n, v in ranked]

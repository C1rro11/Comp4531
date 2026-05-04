import os
import pickle

import numpy as np

FEATURE_RAW = 8
FEATURE_FULL = 16
LABELS = ["EMPTY", "OCCUPIED", "HOARDED"]

FEATURE_NAMES_RAW = [
    "gate0_mean",   # 0
    "gate0_std",    # 1
    "gate1_mean",   # 2
    "gate1_std",    # 3
    "gate2_mean",   # 4
    "gate2_std",    # 5
    "co2_mean",     # 6
    "pressure",     # 7
]

FEATURE_NAMES_FULL = FEATURE_NAMES_RAW + ["Δ" + n for n in FEATURE_NAMES_RAW]


class FeatureExtractor:
    """
    Focused feature extraction:
      - Gate 0-2: mean + std across mmWave readings per window (6 features)
      - CO2 mean over 30s horizon (1 feature)
      - Pressure persistent state (1 feature)

    Output: 8 raw features + 8 delta features = 16 total.
    """

    def __init__(self):
        self.prev_raw = None

    @staticmethod
    def _gate_stats(mmwave_items, gate_idx):
        vals = [
            float(e[gate_idx])
            for (_, _, e) in mmwave_items
            if e is not None and len(e) > gate_idx
        ]
        if len(vals) >= 2:
            return float(np.mean(vals)), float(np.std(vals))
        elif vals:
            return float(vals[0]), 0.0
        else:
            return 0.0, 0.0

    def extract_raw(self, mmwave_items, co30s, pressure):
        feats = []

        # ── gate 0-2 mean + std  (0‑5) ──────────────────────────────
        for gi in range(3):
            m, s = self._gate_stats(mmwave_items, gi)
            feats += [m, s]

        # ── CO2 mean from 30 s horizon  (6) ─────────────────────────
        if co30s:
            feats.append(float(np.mean([float(v) for v in co30s])))
        else:
            feats.append(400.0)

        # ── Persistent pressure state  (7) ──────────────────────────
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
        classes = self.model.classes_
        result = {}
        for idx, cls in enumerate(classes):
            label = LABELS[cls] if cls < len(LABELS) else str(cls)
            result[label] = round(float(proba[idx]), 4)
        for label in LABELS:
            if label not in result:
                result[label] = 0.0
        return result

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

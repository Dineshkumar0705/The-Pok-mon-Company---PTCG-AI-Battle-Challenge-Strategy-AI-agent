"""v5 Phase 2 (docs/v5-architecture.md §3.2) — Learned leaf-value function.

Trained supervised on real self-play (state, eventual real outcome) pairs
from `memory.replay_store` / `scripts/generate_self_play_training_data.py`,
not simulated or hand-labeled data. Same "learn the evaluation, keep the
search" pattern the v5 doc cites (AlphaZero, arXiv:1712.01815): this swaps
in for `search/expectimax.py`'s `position_value()` leaf call, the search
tree shape around it is unchanged.

Model choice, per the v5 doc's own stated plan ("start with logistic
regression / small gradient-boosted trees on hand-engineered features"):
`LogisticRegression` over `memory.featurize`'s 19-feature vector, wrapped in
a `StandardScaler` (the features mix raw counts and 0-1 fractions, so
unscaled logistic regression would let large-magnitude features like scores
dominate the weights regardless of actual predictive value). This is
deliberately the cheap end of that plan -- a small MLP or GBT is the named
next step "once there's enough data," not before, matching Rule 4's
cheapest-first ordering.

Every number a `LearnedLeafValue` instance reports about itself (`metrics`)
comes from an actual held-out split of real training data -- never
hand-picked or asserted. See `scripts/train_leaf_value_model.py` for how
those numbers are produced and `docs/v5-architecture.md` for the last real
run's result.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class TrainMetrics:
    """Real numbers from one train() call's held-out split. Never invented --
    every field here is computed from actual predictions on actual held-out
    real-game records."""

    n_train: int
    n_test: int
    test_accuracy: float
    test_log_loss: float
    test_auc: Optional[float]


class LearnedLeafValue:
    """Wraps a scikit-learn classifier. `predict(features) -> float in [0,1]`
    is the win-probability estimate `search/expectimax.py` can use as a
    drop-in replacement for `position_value()`'s hand-coded score."""

    def __init__(self):
        self._pipeline = None  # sklearn Pipeline(StandardScaler, classifier), set by train()/load()
        self.metrics: Optional[TrainMetrics] = None
        self.feature_names: Optional[list[str]] = None
        self.model_type: str = "logistic"  # v7: "logistic" (v5 default) or "gbt" -- see train()

    @classmethod
    def train(cls, features: list[list[float]], labels: list[float],
              feature_names: list[str], test_size: float = 0.2,
              random_state: int = 0, model_type: str = "logistic") -> "LearnedLeafValue":
        """`model_type`: "logistic" (default, v5's original, unchanged) or
        "gbt" (v7, docs/v7-architecture.md item B) -- a small
        GradientBoostingClassifier, the v5 doc's own explicitly named
        next-cheapest step ("a small gradient-boosted tree... before
        jumping to an MLP"), tried after the Suphx-style oracle idea was
        found genuinely blocked by the real engine (see
        memory/featurize.py's FEATURE_NAMES_V7 docstring). Default behavior
        and v5's shipped model are completely unaffected by this parameter
        existing -- every existing caller that doesn't pass it gets exactly
        v5's original pipeline.
        """
        from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        X = np.array(features, dtype=float)
        y = np.array(labels, dtype=float)
        assert set(np.unique(y)) <= {0.0, 1.0}, (
            "LearnedLeafValue.train() expects binary win/loss labels; filter "
            "out draw (0.5) records before calling this, same as "
            "scripts/train_leaf_value_model.py does."
        )
        assert model_type in ("logistic", "gbt"), f"unknown model_type: {model_type!r}"

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y,
        )

        if model_type == "gbt":
            from sklearn.ensemble import GradientBoostingClassifier
            # Deliberately small/shallow -- "a small gradient-boosted tree"
            # per the v5 doc's own plan, not a large tuned ensemble; this is
            # a first real test of whether the MODEL CLASS was the limiter,
            # not a hyperparameter search.
            clf = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=random_state)
        else:
            from sklearn.linear_model import LogisticRegression
            clf = LogisticRegression(max_iter=1000)

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", clf),
        ])
        pipeline.fit(X_train, y_train)

        proba = pipeline.predict_proba(X_test)[:, 1]
        preds = (proba >= 0.5).astype(float)

        metrics = TrainMetrics(
            n_train=len(X_train),
            n_test=len(X_test),
            test_accuracy=float(accuracy_score(y_test, preds)),
            test_log_loss=float(log_loss(y_test, proba)),
            test_auc=float(roc_auc_score(y_test, proba)) if len(np.unique(y_test)) > 1 else None,
        )

        model = cls()
        model._pipeline = pipeline
        model.metrics = metrics
        model.feature_names = list(feature_names)
        model.model_type = model_type
        return model

    def predict(self, features: list[float]) -> float:
        if self._pipeline is None:
            raise RuntimeError("LearnedLeafValue has no trained model loaded -- call train() or load() first.")
        proba = self._pipeline.predict_proba(np.array([features], dtype=float))[0, 1]
        return float(proba)

    def save(self, path: str) -> None:
        import joblib

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        joblib.dump({
            "pipeline": self._pipeline,
            "metrics": self.metrics,
            "feature_names": self.feature_names,
            "model_type": self.model_type,
        }, path)

    @classmethod
    def load(cls, path: str) -> "LearnedLeafValue":
        import joblib

        payload = joblib.load(path)
        model = cls()
        model._pipeline = payload["pipeline"]
        model.metrics = payload["metrics"]
        model.feature_names = payload["feature_names"]
        model.model_type = payload.get("model_type", "logistic")  # v5 models predate this key
        return model


def load_training_records(path: str) -> tuple[list[list[float]], list[float]]:
    """Reads scripts/generate_self_play_training_data.py's output, drops any
    draw (label==0.5) records (LearnedLeafValue.train() is binary-only, per
    its own docstring), and returns (features, labels) ready for train()."""
    features: list[list[float]] = []
    labels: list[float] = []
    if not os.path.exists(path):
        return features, labels
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["label"] == 0.5:
                continue
            features.append(rec["features"])
            labels.append(rec["label"])
    return features, labels

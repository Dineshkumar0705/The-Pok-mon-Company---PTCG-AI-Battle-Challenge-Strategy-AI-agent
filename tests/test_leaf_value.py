"""Pure-Python/sklearn test of LearnedLeafValue -- no live engine needed.
Uses a small synthetic-but-honestly-labeled dataset (not real game data,
which is what makes this a unit test rather than the real validation:
scripts/train_leaf_value_model.py's printed metrics on real self-play data
are the actual validation, this just confirms the training/predict/save/load
mechanics work correctly).
"""
from __future__ import annotations

import random

from pokemon_agent.learning.leaf_value import LearnedLeafValue, load_training_records


def _linearly_separable_dataset(n=400, seed=0):
    """features=[x], label=1.0 if x>0 else 0.0 -- a trivially learnable
    relationship, just to exercise the real training pipeline end to end."""
    rng = random.Random(seed)
    features, labels = [], []
    for _ in range(n):
        x = rng.uniform(-5, 5)
        features.append([x, rng.uniform(-1, 1)])  # a second, irrelevant feature
        labels.append(1.0 if x > 0 else 0.0)
    return features, labels


def test_train_learns_a_trivially_separable_relationship():
    features, labels = _linearly_separable_dataset()
    model = LearnedLeafValue.train(features, labels, feature_names=["x", "noise"])
    assert model.metrics.test_accuracy > 0.9
    assert model.metrics.n_train + model.metrics.n_test == len(features)


def test_predict_returns_a_probability_in_bounds():
    features, labels = _linearly_separable_dataset()
    model = LearnedLeafValue.train(features, labels, feature_names=["x", "noise"])
    p_high = model.predict([4.0, 0.0])
    p_low = model.predict([-4.0, 0.0])
    assert 0.0 <= p_low <= p_high <= 1.0
    assert p_high > 0.5 > p_low


def test_predict_before_training_raises():
    model = LearnedLeafValue()
    try:
        model.predict([1.0])
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_save_and_load_round_trips_predictions():
    import tempfile
    import os

    features, labels = _linearly_separable_dataset()
    model = LearnedLeafValue.train(features, labels, feature_names=["x", "noise"])
    p_before = model.predict([3.0, 0.0])

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "model.joblib")
        model.save(path)
        loaded = LearnedLeafValue.load(path)

    p_after = loaded.predict([3.0, 0.0])
    assert abs(p_before - p_after) < 1e-9
    assert loaded.feature_names == ["x", "noise"]


def test_load_training_records_drops_draws(tmp_path):
    import json

    path = tmp_path / "data.jsonl"
    path.write_text(
        json.dumps({"features": [1.0], "label": 1.0, "meta": {}}) + "\n" +
        json.dumps({"features": [2.0], "label": 0.5, "meta": {}}) + "\n" +  # draw -- must be dropped
        json.dumps({"features": [3.0], "label": 0.0, "meta": {}}) + "\n"
    )
    features, labels = load_training_records(str(path))
    assert features == [[1.0], [3.0]]
    assert labels == [1.0, 0.0]


def test_load_training_records_on_missing_file_returns_empty():
    features, labels = load_training_records("/nonexistent/path.jsonl")
    assert features == [] and labels == []

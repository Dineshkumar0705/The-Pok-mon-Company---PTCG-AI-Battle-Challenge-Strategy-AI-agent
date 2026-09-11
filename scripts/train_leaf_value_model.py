#!/usr/bin/env python3
"""Trains LearnedLeafValue on real self-play data from
scripts/generate_self_play_training_data.py's output, reports the real
held-out metrics (never asserted), and saves the model.

v7: `--model-type gbt` trains `learning.leaf_value.LearnedLeafValue`'s new
GradientBoostingClassifier option instead of v5's default LogisticRegression.
`--feature-version v7` selects the richer `FEATURE_NAMES_V7` feature set
(memory/featurize.py) for reporting/labeling and defaults `--data`/`--out`
to the v7 data/model paths -- v5's own default invocation is unaffected.

Usage:
    python3 scripts/train_leaf_value_model.py
    python3 scripts/train_leaf_value_model.py --data replays/raw/leaf_value_training_data.jsonl \\
        --out models/leaf_value_v5.joblib
    python3 scripts/train_leaf_value_model.py --feature-version v7 --model-type gbt
"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_DATA = os.path.join(REPO_ROOT, "replays", "raw", "leaf_value_training_data.jsonl")
DEFAULT_MODEL_PATH = os.path.join(REPO_ROOT, "models", "leaf_value_v5.joblib")
DEFAULT_DATA_V7 = os.path.join(REPO_ROOT, "replays", "raw", "leaf_value_training_data_v7.jsonl")
DEFAULT_MODEL_PATH_V7 = os.path.join(REPO_ROOT, "models", "leaf_value_v7.joblib")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--feature-version", choices=("v5", "v7"), default="v5")
    parser.add_argument("--model-type", choices=("logistic", "gbt"), default="logistic")
    parser.add_argument("--test-size", type=float, default=0.2)
    args = parser.parse_args()
    is_v7 = args.feature_version == "v7"
    if args.data is None:
        args.data = DEFAULT_DATA_V7 if is_v7 else DEFAULT_DATA
    if args.out is None:
        args.out = DEFAULT_MODEL_PATH_V7 if is_v7 else DEFAULT_MODEL_PATH

    from pokemon_agent.learning.leaf_value import LearnedLeafValue, load_training_records
    from pokemon_agent.memory.featurize import FEATURE_NAMES, FEATURE_NAMES_V7

    feature_names = FEATURE_NAMES_V7 if is_v7 else FEATURE_NAMES

    features, labels = load_training_records(args.data)
    if len(features) < 100:
        print(f"Only {len(features)} usable (non-draw) records in {args.data} -- "
              f"run scripts/generate_self_play_training_data.py first.")
        return

    print(f"Training a {args.model_type!r} model on {len(features)} real (state, outcome) "
          f"records from {args.data} ({args.feature_version} features)...")
    model = LearnedLeafValue.train(features, labels, feature_names=feature_names,
                                    test_size=args.test_size, model_type=args.model_type)

    m = model.metrics
    print(f"\n=== Real held-out metrics (n_train={m.n_train}, n_test={m.n_test}) ===")
    print(f"Test accuracy: {m.test_accuracy:.1%}")
    print(f"Test log loss: {m.test_log_loss:.4f}")
    print(f"Test AUC: {m.test_auc:.4f}" if m.test_auc is not None else "Test AUC: n/a")

    # A naive baseline for comparison: always predict 0.5 (maximum uncertainty).
    from sklearn.metrics import log_loss
    naive_ll = log_loss(labels, [0.5] * len(labels))
    print(f"(For reference: a naive always-0.5 baseline's log loss on the full "
          f"dataset is {naive_ll:.4f} -- the trained model's test log loss above "
          f"should be well below this if it learned real signal.)")

    clf = model._pipeline.named_steps["clf"]
    if hasattr(clf, "coef_"):
        ranked = sorted(zip(feature_names, clf.coef_[0]), key=lambda x: -abs(x[1]))
        print("\n=== Top 8 features by |learned weight| (after standardization) ===")
        for name, coef in ranked[:8]:
            print(f"  {name}: {coef:+.3f}")
    elif hasattr(clf, "feature_importances_"):
        ranked = sorted(zip(feature_names, clf.feature_importances_), key=lambda x: -x[1])
        print("\n=== Top 8 features by GBT importance ===")
        for name, imp in ranked[:8]:
            print(f"  {name}: {imp:.3f}")

    model.save(args.out)
    print(f"\nSaved model to {args.out}")


if __name__ == "__main__":
    main()

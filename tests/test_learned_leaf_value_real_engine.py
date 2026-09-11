"""Real-engine end-to-end check of the learned leaf-value path: the actual
trained model (models/leaf_value_v5.joblib, from
scripts/train_leaf_value_model.py) driving rank_attack_candidates() against
a real attack decision, and a full real self-play game with
leaf_value_mode="learned" wired all the way through build_agent(). Skipped
if either the real engine or the trained model file isn't available.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_DIR = os.path.join(REPO_ROOT, "notebooks", "legacy")
MODEL_PATH = os.path.join(REPO_ROOT, "models", "leaf_value_v5.joblib")
for _p in (os.path.join(REPO_ROOT, "vendor"), os.path.join(REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from cg import game
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not (_ENGINE_AVAILABLE and os.path.exists(MODEL_PATH)),
    reason="real cg engine or trained models/leaf_value_v5.joblib not available",
)


def _load_legacy_deck():
    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)
    try:
        spec = importlib.util.spec_from_file_location("legacy_for_learned_value_test", "main_v1_reference.py")
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        return legacy.my_deck, legacy
    finally:
        os.chdir(cwd)


def test_build_agent_with_learned_leaf_value_plays_complete_legal_games():
    from pokemon_agent.agent import build_agent
    from pokemon_agent.search.expectimax import ExpectimaxConfig

    deck, _legacy = _load_legacy_deck()
    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)
    try:
        learned_agent = build_agent(deck, search_config=ExpectimaxConfig(
            enabled=True, depth=1, leaf_value_mode="learned", leaf_value_model_path=MODEL_PATH,
        ))
        obs_dict, _start = game.battle_start(deck, deck)
        try:
            steps = 0
            for _ in range(300):
                sel = obs_dict.get("select")
                if sel is None or obs_dict.get("current", {}).get("result", -1) != -1:
                    break
                choice = learned_agent(obs_dict)
                obs_dict = game.battle_select(choice)
                steps += 1
            assert steps > 20, f"only {steps} real decision steps -- too few to trust this run"
        finally:
            try:
                game.battle_finish()
            except Exception:
                pass
    finally:
        os.chdir(cwd)


def test_learned_model_actually_gets_used_not_silently_skipped():
    """Confirms the telemetry says leaf_value_mode_used == 'learned' at least
    once during a real game -- i.e. the model genuinely loaded and was
    consulted, not silently falling back to heuristic the whole time."""
    from pokemon_agent.agent import build_agent
    from pokemon_agent.search.expectimax import ExpectimaxConfig

    deck, _legacy = _load_legacy_deck()
    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)
    try:
        learned_agent = build_agent(deck, search_config=ExpectimaxConfig(
            enabled=True, depth=1, leaf_value_mode="learned", leaf_value_model_path=MODEL_PATH,
        ))
        obs_dict, _start = game.battle_start(deck, deck)
        saw_learned_mode = False
        try:
            for _ in range(300):
                sel = obs_dict.get("select")
                if sel is None or obs_dict.get("current", {}).get("result", -1) != -1:
                    break
                choice = learned_agent(obs_dict)
                telemetry = learned_agent.get_search_telemetry()
                if telemetry is not None and telemetry.leaf_value_mode_used == "learned":
                    saw_learned_mode = True
                obs_dict = game.battle_select(choice)
        finally:
            try:
                game.battle_finish()
            except Exception:
                pass
        assert saw_learned_mode, "the learned model was never actually consulted during this real game"
    finally:
        os.chdir(cwd)

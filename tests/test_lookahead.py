"""Real test of the search_begin/search_step/search_end wiring in
search/lookahead.py -- against the actual engine, not a mock. Advances a
real self-play game a few real turns (so hand/deck/prize counts are past
their trivial turn-1 values), then probes one hypothetical step from a real
MAIN-context decision point and checks the round trip behaves sanely.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_DIR = os.path.join(REPO_ROOT, "notebooks", "legacy")
for _p in (os.path.join(REPO_ROOT, "vendor"), os.path.join(REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from cg import game
    from cg.api import to_observation_class
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _ENGINE_AVAILABLE, reason="real cg engine not available")


def test_probe_one_step_round_trips_against_the_real_engine():
    from pokemon_agent.search.lookahead import probe_one_step

    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)
    try:
        spec = importlib.util.spec_from_file_location("legacy_probe_test", "main_v1_reference.py")
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        deck = legacy.my_deck

        obs_dict, _start = game.battle_start(deck, deck)
        try:
            # Advance a few real turns so we're past trivial turn-1 states.
            for _ in range(60):
                sel = obs_dict.get("select")
                if sel is None or obs_dict["current"].get("result", -1) != -1:
                    break
                if sel.get("context") == 0 and obs_dict["current"]["turn"] >= 2:
                    break
                obs_dict = game.battle_select(legacy.agent(obs_dict))

            sel = obs_dict.get("select")
            if sel is None or obs_dict["current"].get("result", -1) != -1:
                pytest.skip("game ended before reaching a real MAIN decision to probe")

            obs = to_observation_class(obs_dict)
            result = probe_one_step(obs, choice=[0], card_pool=deck)

            assert result.ok, f"probe failed: {result.error}"
            assert result.result_after_step in (-1, 0, 1, 2)
            # The live battle must be untouched -- confirm we can still make a
            # real move on it after the probe released its own search.
            real_choice = legacy.agent(obs_dict)
            obs_dict = game.battle_select(real_choice)
            assert obs_dict.get("select") is not None or obs_dict["current"]["result"] != -1
        finally:
            try:
                game.battle_finish()
            except Exception:
                pass
    finally:
        os.chdir(cwd)

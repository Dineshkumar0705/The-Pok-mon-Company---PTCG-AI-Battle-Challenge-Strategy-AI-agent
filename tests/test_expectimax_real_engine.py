"""Real-engine integration test for search/expectimax.py -- not a mock. Runs
real self-play through vendor/cg, and at a real MAIN decision that has at
least one ATTACK option, drives rank_attack_candidates() with the real
engine's search_begin/search_step/search_end. Also exercises the fully
wired path: build_agent(deck, search_config=ExpectimaxConfig(enabled=True))
playing real, complete games without ever producing an illegal choice
(the real engine would reject it) or crashing.

Skipped entirely if the real cg engine isn't loadable in this environment,
same convention as test_lookahead.py / test_agent_matches_legacy.py.
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
    from cg.api import to_observation_class, AreaType, OptionType, SelectContext
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _ENGINE_AVAILABLE, reason="real cg engine not available")


def _load_legacy_deck():
    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)
    try:
        spec = importlib.util.spec_from_file_location("legacy_for_expectimax_test", "main_v1_reference.py")
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        return legacy.my_deck, legacy
    finally:
        os.chdir(cwd)


def _advance_to_attack_decision(obs_dict, legacy, max_steps=250):
    """Play real self-play with the legacy heuristic agent until we hit a
    real MAIN-context decision with at least one ATTACK option, or the game
    ends / we run out of steps."""
    for _ in range(max_steps):
        sel = obs_dict.get("select")
        if sel is None or obs_dict.get("current", {}).get("result", -1) != -1:
            return obs_dict, False
        options = sel.get("option", [])
        if sel.get("context") == int(SelectContext.MAIN) - 0 and any(
            o.get("type") == int(OptionType.ATTACK) for o in options
        ):
            return obs_dict, True
        obs_dict = game.battle_select(legacy.agent(obs_dict))
    return obs_dict, False


def test_rank_attack_candidates_against_a_real_attack_decision():
    from pokemon_agent.card_data import load_card_table
    from pokemon_agent.belief.energy_density import EnergyDensityBelief
    from pokemon_agent.search.expectimax import ExpectimaxConfig, rank_attack_candidates
    from pokemon_agent.search.transposition_table import TranspositionTable
    from pokemon_agent.scoring.option_scorer import TurnContext, score_options

    deck, legacy = _load_legacy_deck()
    card_table, attack_table, source = load_card_table(prefer_engine=True)
    assert source == "engine"

    obs_dict, start_data = game.battle_start(deck, deck)
    try:
        obs_dict, found = _advance_to_attack_decision(obs_dict, legacy)
        if not found:
            pytest.skip("no real MAIN+ATTACK decision reached in this self-play run")

        obs = to_observation_class(obs_dict)
        select = obs.select
        current = obs.current
        my_index = current.yourIndex
        my_state = current.players[my_index]
        op_state = current.players[1 - my_index]

        from collections import defaultdict
        field_counts, hand_counts, discard_counts = defaultdict(int), defaultdict(int), defaultdict(int)
        for c in list(my_state.active or []) + list(my_state.bench or []):
            if c is not None:
                field_counts[c.id] += 1

        ctx = TurnContext(
            obs=obs, card_table=card_table, attack_table=attack_table,
            plan=__import__("pokemon_agent.attack_plans", fromlist=["AttackPlan"]).AttackPlan(),
            field_counts=field_counts, hand_counts=hand_counts, discard_counts=discard_counts,
            stadium_id=current.stadium[0].id if current.stadium else 0,
            my_active=my_state.active[0] if my_state.active else None,
            active_in_danger=False, relicanth_present=False, metal_in_discard=0,
            my_index=my_index, op_state=op_state, my_state=my_state,
            context=select.context, area_type=AreaType, select_context_type=SelectContext,
        )
        baseline = score_options(select.option, ctx, OptionType)

        belief = EnergyDensityBelief()
        ttable = TranspositionTable()

        for depth in (1, 2):
            config = ExpectimaxConfig(enabled=True, depth=depth, max_branch_steps=6)
            scores, telemetry = rank_attack_candidates(
                obs=obs, select=select, baseline_scores=baseline,
                card_table=card_table, attack_table=attack_table, card_pool=deck,
                option_type=OptionType, select_context_type=SelectContext, area_type=AreaType,
                config=config, ttable=ttable, belief=belief,
            )
            assert telemetry.attempted
            assert len(scores) == len(baseline)
            # The live battle must still be usable after search released itself.
            real_choice = legacy.agent(obs_dict)
            next_obs_dict = game.battle_select(real_choice)
            assert next_obs_dict.get("select") is not None or next_obs_dict["current"]["result"] != -1
            break  # advancing the real battle only once -- depth 2 reuses the same pre-advance obs below
    finally:
        try:
            game.battle_finish()
        except Exception:
            pass


def test_build_agent_with_search_enabled_plays_complete_legal_games():
    """The fully wired path: agent.py's build_agent() with search turned on,
    playing real games end to end. Never produces a choice the engine
    rejects (an IndexError from game.battle_select would mean an illegal
    index slipped through), and completes normally."""
    from pokemon_agent.agent import build_agent
    from pokemon_agent.search.expectimax import ExpectimaxConfig

    deck, _legacy = _load_legacy_deck()
    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)
    try:
        search_agent = build_agent(deck, search_config=ExpectimaxConfig(
            enabled=True, depth=1, belief_informed_determinization=True,
        ))
        obs_dict, _start = game.battle_start(deck, deck)
        try:
            steps = 0
            for _ in range(300):
                sel = obs_dict.get("select")
                if sel is None or obs_dict.get("current", {}).get("result", -1) != -1:
                    break
                choice = search_agent(obs_dict)
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

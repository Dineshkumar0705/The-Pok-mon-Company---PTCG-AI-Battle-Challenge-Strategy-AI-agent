"""Real-engine integration tests for v7's two expectimax additions:
policy_top_k branch capping and depth>=3's generalized multi-round
fast-forward. Same skip convention as test_expectimax_real_engine.py --
skipped entirely if the real cg engine isn't loadable here.
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
        spec = importlib.util.spec_from_file_location("legacy_for_v7_expectimax_test", "main_v1_reference.py")
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        return legacy.my_deck, legacy
    finally:
        os.chdir(cwd)


def _advance_to_attack_decision(obs_dict, legacy, max_steps=250):
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


def _real_attack_decision_context(min_attack_options: int = 1, max_games: int = 1):
    """Shared setup: play real self-play to a real MAIN+ATTACK decision and
    return everything needed to call rank_attack_candidates() against it.

    `min_attack_options`/`max_games`: the policy_top_k test specifically
    needs a decision with >=2 real ATTACK candidates to be a meaningful
    check (pruning 1-of-1 proves nothing). Real self-play games don't
    reliably produce one on the first attack decision reached, so this
    tries up to `max_games` real games before honestly skipping -- still a
    skip, never a fabricated multi-candidate state.
    """
    from pokemon_agent.card_data import load_card_table
    from pokemon_agent.scoring.option_scorer import TurnContext, score_options
    from pokemon_agent.attack_plans import AttackPlan

    deck, legacy = _load_legacy_deck()
    card_table, attack_table, source = load_card_table(prefer_engine=True)
    assert source == "engine"

    for _game_attempt in range(max_games):
        obs_dict, _start = game.battle_start(deck, deck)
        obs_dict, found = _advance_to_attack_decision(obs_dict, legacy)
        if not found:
            game.battle_finish()
            continue

        obs = to_observation_class(obs_dict)
        select = obs.select
        n_attacks = sum(1 for o in select.option if o.type == OptionType.ATTACK)
        if n_attacks < min_attack_options:
            game.battle_finish()
            continue

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
            obs=obs, card_table=card_table, attack_table=attack_table, plan=AttackPlan(),
            field_counts=field_counts, hand_counts=hand_counts, discard_counts=discard_counts,
            stadium_id=current.stadium[0].id if current.stadium else 0,
            my_active=my_state.active[0] if my_state.active else None,
            active_in_danger=False, relicanth_present=False, metal_in_discard=0,
            my_index=my_index, op_state=op_state, my_state=my_state,
            context=select.context, area_type=AreaType, select_context_type=SelectContext,
        )
        baseline = score_options(select.option, ctx, OptionType)
        return deck, card_table, attack_table, obs, select, baseline

    pytest.skip(f"no real MAIN+ATTACK decision with >={min_attack_options} ATTACK "
                f"option(s) reached across {max_games} real self-play game(s)")


def test_depth_three_runs_a_genuine_extra_round_without_crashing():
    from pokemon_agent.search.expectimax import ExpectimaxConfig, rank_attack_candidates
    from pokemon_agent.belief.energy_density import EnergyDensityBelief
    from pokemon_agent.search.transposition_table import TranspositionTable

    deck, card_table, attack_table, obs, select, baseline = _real_attack_decision_context(max_games=5)
    try:
        belief = EnergyDensityBelief()
        ttable = TranspositionTable()
        config = ExpectimaxConfig(enabled=True, depth=3, max_branch_steps=10)
        scores, telemetry = rank_attack_candidates(
            obs=obs, select=select, baseline_scores=baseline,
            card_table=card_table, attack_table=attack_table, card_pool=deck,
            option_type=OptionType, select_context_type=SelectContext, area_type=AreaType,
            config=config, ttable=ttable, belief=belief,
        )
        assert telemetry.attempted
        assert len(scores) == len(baseline)
        # depth=3 must spend at least as many real engine calls as depth=2
        # would for the same decision (it does one more real round), and it
        # must never raise -- the actual assertion here is "this ran at all".
        assert telemetry.engine_calls > 0
        assert telemetry.leaf_eval_errors == 0
    finally:
        try:
            game.battle_finish()
        except Exception:
            pass


def test_policy_top_k_prunes_candidates_and_still_produces_valid_scores():
    from pokemon_agent.search.expectimax import ExpectimaxConfig, rank_attack_candidates
    from pokemon_agent.belief.energy_density import EnergyDensityBelief
    from pokemon_agent.search.transposition_table import TranspositionTable

    deck, card_table, attack_table, obs, select, baseline = _real_attack_decision_context(
        min_attack_options=2, max_games=15)
    try:
        n_attacks = sum(1 for o in select.option if o.type == OptionType.ATTACK)

        belief = EnergyDensityBelief()
        ttable = TranspositionTable()
        config = ExpectimaxConfig(enabled=True, depth=1, policy_top_k=1)
        scores, telemetry = rank_attack_candidates(
            obs=obs, select=select, baseline_scores=baseline,
            card_table=card_table, attack_table=attack_table, card_pool=deck,
            option_type=OptionType, select_context_type=SelectContext, area_type=AreaType,
            config=config, ttable=ttable, belief=belief,
        )
        assert telemetry.attempted
        assert telemetry.candidates_considered == n_attacks
        assert telemetry.candidates_pruned_by_policy == n_attacks - 1
        assert len(scores) == len(baseline)
    finally:
        try:
            game.battle_finish()
        except Exception:
            pass

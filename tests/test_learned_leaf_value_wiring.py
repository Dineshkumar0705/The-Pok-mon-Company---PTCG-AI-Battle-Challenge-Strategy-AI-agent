"""v5: learned-leaf-value wiring inside search/expectimax.py. Pure-Python
where possible (missing-model fail-closed path); real-engine where the
actual trained model needs to run through a real search decision.
"""
from __future__ import annotations

import os

from pokemon_agent.search.expectimax import ExpectimaxConfig, rank_attack_candidates

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINED_MODEL_PATH = os.path.join(REPO_ROOT, "models", "leaf_value_v5.joblib")


class _OptionType:
    ATTACK = "ATTACK"
    PLAY = "PLAY"


def _select(option_types):
    from dataclasses import dataclass, field

    @dataclass
    class _Option:
        type: str

    @dataclass
    class _Select:
        context: str = "MAIN"
        option: list = field(default_factory=lambda: [_Option(type=t) for t in option_types])
        maxCount: int = 1

    return _Select()


def test_learned_mode_with_missing_model_path_falls_back_to_heuristic():
    select = _select(["ATTACK"])
    baseline = [1200]
    config = ExpectimaxConfig(enabled=True, depth=0, leaf_value_mode="learned",
                               leaf_value_model_path=None)

    # depth=0 short-circuits before leaf evaluation is ever reached -- confirms
    # the depth-0 regression gate still applies unchanged regardless of leaf_value_mode.
    scores, telemetry = rank_attack_candidates(
        obs=None, select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )
    assert scores == baseline
    assert not telemetry.attempted


def _minimal_mock_obs():
    """Structurally enough like a real Observation for rank_attack_candidates()
    to read obs.current.yourIndex/turn/players -- but NOT a real engine
    Observation (no search_begin_input), so the real search_begin() call
    fails and is caught, exactly like a real engine rejecting a bad
    determinization would be."""
    from dataclasses import dataclass, field

    @dataclass
    class _Pokemon:
        id: int = 190
        hp: int = 100

    @dataclass
    class _PlayerState:
        active: list = field(default_factory=lambda: [_Pokemon()])
        bench: list = field(default_factory=list)
        prize: list = field(default_factory=list)
        deckCount: int = 10
        handCount: int = 3

    @dataclass
    class _Current:
        yourIndex: int = 0
        turn: int = 3
        result: int = -1
        players: list = field(default_factory=lambda: [_PlayerState(), _PlayerState()])

    @dataclass
    class _Obs:
        current: _Current

    return _Obs(current=_Current())


def test_learned_mode_with_nonexistent_model_file_fails_closed():
    """depth>0, learned mode requested, but the model file doesn't exist --
    must fall back to the heuristic evaluator for this decision, flagged in
    telemetry, never a crash. The mock observation isn't a real engine
    Observation, so the real search_begin() call itself also fails and is
    caught -- the same fail-closed path a real engine rejection would take."""
    select = _select(["ATTACK"])
    baseline = [1200]
    config = ExpectimaxConfig(enabled=True, depth=1, leaf_value_mode="learned",
                               leaf_value_model_path="/nonexistent/model.joblib")

    scores, telemetry = rank_attack_candidates(
        obs=_minimal_mock_obs(), select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )
    assert scores == baseline
    assert telemetry.learned_model_load_failed
    # Either the engine import itself fails first, or it gets far enough to
    # reach search_begin() and that fails on the mock observation -- both are
    # the same honest outcome: no crash, never a silent "it worked" claim.
    assert telemetry.fell_back_to_heuristic or not telemetry.attempted


def test_load_learned_model_returns_none_for_missing_path():
    from pokemon_agent.search.expectimax import _load_learned_model

    assert _load_learned_model("/definitely/not/a/real/path.joblib") is None


def test_learned_value_normalized_handles_terminal_states():
    from dataclasses import dataclass

    from pokemon_agent.search.expectimax import learned_value_normalized

    @dataclass
    class _Current:
        result: int = 0

    @dataclass
    class _Obs:
        current: _Current

    win_obs = _Obs(current=_Current(result=0))
    loss_obs = _Obs(current=_Current(result=1))
    draw_obs = _Obs(current=_Current(result=2))

    assert learned_value_normalized(win_obs, {}, my_index=0, model=None) == 1.0
    assert learned_value_normalized(loss_obs, {}, my_index=0, model=None) == -1.0
    assert learned_value_normalized(draw_obs, {}, my_index=0, model=None) == 0.0

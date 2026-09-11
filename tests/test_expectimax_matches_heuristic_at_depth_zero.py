"""The regression gate named explicitly in the v3-upgrade doc's build-order
table: depth-0 (or search disabled outright) expectimax must be
byte-identical to the plain heuristic's own score_options() output. This is
what guarantees a missing/corrupt config file, or anyone calling
build_agent() without search_config, reproduces v1/v2 exactly -- the whole
point of shipping this gated.

Also covers: rank_attack_candidates() never mutates baseline_scores in
place (callers must be able to trust the list they passed in is untouched),
and it degrades to the heuristic unchanged when there's no ATTACK option to
search over, regardless of config.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pokemon_agent.search.expectimax import ExpectimaxConfig, rank_attack_candidates


@dataclass
class _Option:
    type: str


class _OptionType:
    ATTACK = "ATTACK"
    PLAY = "PLAY"
    RETREAT = "RETREAT"


def _select(option_types):
    @dataclass
    class _Select:
        context: str = "MAIN"
        option: list = field(default_factory=lambda: [_Option(type=t) for t in option_types])
        maxCount: int = 1

    return _Select()


def test_depth_zero_returns_baseline_scores_unchanged():
    select = _select(["PLAY", "ATTACK", "RETREAT"])
    baseline = [10000, 1200, 2000]
    config = ExpectimaxConfig(enabled=True, depth=0)  # depth 0 -- must be a no-op even if "enabled"

    scores, telemetry = rank_attack_candidates(
        obs=None, select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )

    assert scores == baseline
    assert not telemetry.attempted


def test_search_disabled_returns_baseline_scores_unchanged():
    select = _select(["PLAY", "ATTACK", "RETREAT"])
    baseline = [10000, 1200, 2000]
    config = ExpectimaxConfig(enabled=False, depth=2)  # depth>0 but disabled -- still a no-op

    scores, telemetry = rank_attack_candidates(
        obs=None, select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )

    assert scores == baseline
    assert not telemetry.attempted


def test_no_attack_option_returns_baseline_scores_unchanged_even_when_enabled():
    select = _select(["PLAY", "RETREAT"])  # no ATTACK option present
    baseline = [10000, 2000]
    config = ExpectimaxConfig(enabled=True, depth=2)

    scores, telemetry = rank_attack_candidates(
        obs=None, select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )

    assert scores == baseline
    assert not telemetry.attempted
    assert telemetry.candidates_considered == 0


def test_baseline_scores_list_is_never_mutated_in_place():
    select = _select(["ATTACK"])
    baseline = [1200]
    original = list(baseline)
    config = ExpectimaxConfig(enabled=True, depth=0)

    rank_attack_candidates(
        obs=None, select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )

    assert baseline == original


def test_engine_unavailable_falls_back_to_heuristic(monkeypatch):
    """Even with search genuinely enabled and an ATTACK option present, if
    `cg.api` can't be imported at all, rank_attack_candidates() must degrade
    to the untouched baseline rather than raising."""
    import builtins
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "cg.api" or name == "cg":
            raise ImportError("no engine here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    select = _select(["ATTACK"])
    baseline = [1200]
    config = ExpectimaxConfig(enabled=True, depth=1)

    scores, telemetry = rank_attack_candidates(
        obs=None, select=select, baseline_scores=baseline,
        card_table={}, attack_table={}, card_pool=[1, 2, 3],
        option_type=_OptionType, select_context_type=None, area_type=None,
        config=config,
    )

    assert scores == baseline
    assert telemetry.fell_back_to_heuristic

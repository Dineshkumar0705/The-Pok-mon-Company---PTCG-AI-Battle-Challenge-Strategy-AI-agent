from __future__ import annotations

from dataclasses import dataclass, field

from pokemon_agent.memory.featurize import featurize_observation, FEATURE_NAMES
from pokemon_agent.mock_engine import CardData


@dataclass
class _Pokemon:
    id: int
    hp: int = 100
    maxHp: int = 100
    energies: list = field(default_factory=list)
    tools: list = field(default_factory=list)


@dataclass
class _PlayerState:
    active: list = field(default_factory=list)
    bench: list = field(default_factory=list)
    hand: list = field(default_factory=list)
    discard: list = field(default_factory=list)
    prize: list = field(default_factory=list)
    handCount: int = 0


@dataclass
class _Current:
    turn: int = 5
    players: list = field(default_factory=list)


@dataclass
class _Obs:
    current: _Current


def _card_table():
    return {190: CardData(cardId=190, ex=True), 1: CardData(cardId=1)}


def test_feature_vector_has_expected_length():
    my = _PlayerState(active=[_Pokemon(id=190, hp=80, maxHp=120)], bench=[_Pokemon(id=1, hp=50)], handCount=3)
    op = _PlayerState(active=[_Pokemon(id=1, hp=100)], bench=[], handCount=4, prize=[None] * 5)
    obs = _Obs(current=_Current(turn=5, players=[my, op]))

    features = featurize_observation(obs, _card_table(), my_index=0)
    assert len(features) == len(FEATURE_NAMES)
    assert features[0] == 5.0  # turn


def test_missing_active_pokemon_contributes_zeros_not_a_crash():
    my = _PlayerState(active=[], bench=[])
    op = _PlayerState(active=[], bench=[])
    obs = _Obs(current=_Current(turn=1, players=[my, op]))

    features = featurize_observation(obs, _card_table(), my_index=0)
    assert len(features) == len(FEATURE_NAMES)
    assert all(isinstance(x, float) for x in features)


def test_hp_fraction_is_correctly_normalized():
    my = _PlayerState(active=[_Pokemon(id=190, hp=30, maxHp=120)], bench=[])
    op = _PlayerState(active=[_Pokemon(id=1, hp=100, maxHp=100)], bench=[])
    obs = _Obs(current=_Current(turn=2, players=[my, op]))

    features = featurize_observation(obs, _card_table(), my_index=0)
    my_active_hp_frac_idx = FEATURE_NAMES.index("my_active_hp_frac")
    op_active_hp_frac_idx = FEATURE_NAMES.index("op_active_hp_frac")
    assert abs(features[my_active_hp_frac_idx] - 0.25) < 1e-9
    assert abs(features[op_active_hp_frac_idx] - 1.0) < 1e-9


def test_perspective_swap_swaps_my_and_op_features():
    my = _PlayerState(active=[_Pokemon(id=190, hp=120, maxHp=120)], bench=[])
    op = _PlayerState(active=[_Pokemon(id=1, hp=10, maxHp=100)], bench=[])
    obs = _Obs(current=_Current(turn=3, players=[my, op]))

    from_p0 = featurize_observation(obs, _card_table(), my_index=0)
    from_p1 = featurize_observation(obs, _card_table(), my_index=1)

    hp_idx = FEATURE_NAMES.index("my_active_hp_frac")
    op_hp_idx = FEATURE_NAMES.index("op_active_hp_frac")
    assert from_p0[hp_idx] == from_p1[op_hp_idx]
    assert from_p0[op_hp_idx] == from_p1[hp_idx]

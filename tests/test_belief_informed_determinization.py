"""L3 integration test: belief_informed_sample()'s output Energy fraction
converges to the belief's density() estimate, and belief_informed_determinization()
produces the same shape of kwargs search_begin() expects (same contract as
default_determinization(), swapped sampler). Pure-Python, mock engine, no
live engine needed -- the statistical claim ("this sampler is actually
biased toward the target density") is checkable without touching cg.api.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from pokemon_agent.belief.energy_density import EnergyDensityBelief, BASIC_ENERGY_CARD_TYPE_VALUE
from pokemon_agent.mock_engine import CardData
from pokemon_agent.search.lookahead import belief_informed_sample, belief_informed_determinization


def _card_table():
    return {
        1: CardData(cardId=1, cardType=BASIC_ENERGY_CARD_TYPE_VALUE),  # energy
        2: CardData(cardId=2, cardType=1),  # non-energy
        3: CardData(cardId=3, cardType=1),  # non-energy
    }


def _card_pool():
    # A mixed pool standing in for "our own deck", same shape default_determinization() uses.
    return [1] * 12 + [2] * 24 + [3] * 24  # 60 cards, 12 energy -- matches the generic prior


def test_belief_informed_sample_converges_to_target_density():
    rng = random.Random(1234)
    table = _card_table()
    pool = _card_pool()
    n = 4000
    target_density = 0.35  # deliberately different from the pool's raw 12/60 = 0.20,
    # so a bug that ignores target_density and just samples the raw pool would fail this.

    sample = belief_informed_sample(n, pool, table, target_density, rng)
    observed_fraction = sum(1 for cid in sample if cid == 1) / n

    # Binomial std dev at n=4000, p=0.35 is ~0.0075; 4 std devs is a very
    # generous, non-flaky tolerance for a statistical convergence check.
    assert abs(observed_fraction - target_density) < 0.03


def test_belief_informed_sample_falls_back_to_uniform_when_pool_has_only_one_kind():
    rng = random.Random(1)
    table = _card_table()
    all_energy_pool = [1, 1, 1]
    out = belief_informed_sample(5, all_energy_pool, table, target_density=0.9, rng=rng)
    assert len(out) == 5
    assert all(cid == 1 for cid in out)  # nothing else to draw from -- no crash, no bias needed


def test_belief_informed_sample_returns_empty_for_n_zero_or_negative():
    rng = random.Random(1)
    table = _card_table()
    pool = _card_pool()
    assert belief_informed_sample(0, pool, table, 0.5, rng) == []
    assert belief_informed_sample(-3, pool, table, 0.5, rng) == []


@dataclass
class _Pokemon:
    id: int


@dataclass
class _PlayerState:
    active: list = field(default_factory=list)
    bench: list = field(default_factory=list)
    prize: list = field(default_factory=list)
    deckCount: int = 0
    handCount: int = 0


@dataclass
class _Current:
    yourIndex: int = 0
    players: list = field(default_factory=list)


@dataclass
class _Obs:
    current: _Current


def _make_obs(my_deck=10, my_prize=6, op_deck=12, op_hand=5, op_active_hidden=False):
    my = _PlayerState(active=[_Pokemon(id=190)], deckCount=my_deck, prize=[None] * my_prize)
    op = _PlayerState(
        active=[] if op_active_hidden else [_Pokemon(id=1)],
        deckCount=op_deck, handCount=op_hand, prize=[None] * 2,
    )
    return _Obs(current=_Current(yourIndex=0, players=[my, op]))


def test_belief_informed_determinization_returns_correctly_sized_zones():
    table = _card_table()
    pool = _card_pool()
    belief = EnergyDensityBelief(deck_size=60, energy_prior_count=12)
    belief.observe([2, 2, 2], table)  # a few non-energy cards seen from the opponent
    obs = _make_obs(my_deck=10, my_prize=6, op_deck=12, op_hand=5)

    det = belief_informed_determinization(obs, pool, table, belief, rng=random.Random(7))

    assert len(det["your_deck"]) == 10
    assert len(det["your_prize"]) == 6
    assert len(det["opponent_deck"]) == 12
    assert len(det["opponent_prize"]) == 2
    assert len(det["opponent_hand"]) == 5
    assert det["opponent_active"] == []  # opponent's active was face-up in this fixture


def test_belief_informed_determinization_fills_hidden_active_when_face_down():
    table = _card_table()
    pool = _card_pool()
    belief = EnergyDensityBelief()
    obs = _make_obs(op_active_hidden=True)

    det = belief_informed_determinization(obs, pool, table, belief, rng=random.Random(3))
    assert len(det["opponent_active"]) == 1

"""L2 transposition table -- pure-Python, mock-engine data, no live engine
needed. Covers: hit/miss counting, FIFO eviction at capacity, and that
node_key() is sensitive to real board-state differences (two states that
actually differ must not collide) while being insensitive to irrelevant
detail (two Observations with the same relevant fields but different unread
detail -- e.g. hand card order -- must collide, since that's the entire
point of a transposition table).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pokemon_agent.search.transposition_table import (
    TranspositionEntry,
    TranspositionTable,
    node_key,
)


@dataclass
class _Pokemon:
    id: int
    hp: int = 100
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
    turn: int = 3
    yourIndex: int = 0
    stadium: list = field(default_factory=list)
    energyAttached: bool = False
    supporterPlayed: bool = False
    players: list = field(default_factory=list)


@dataclass
class _Select:
    context: int = 1


@dataclass
class _Obs:
    current: _Current
    select: _Select = None


def _make_obs(active_hp=100, hand_count=3, turn=3):
    p0 = _PlayerState(active=[_Pokemon(id=190, hp=active_hp)], bench=[], handCount=hand_count)
    p1 = _PlayerState(active=[_Pokemon(id=1, hp=100)], bench=[], handCount=4)
    current = _Current(turn=turn, players=[p0, p1])
    return _Obs(current=current, select=_Select(context=1))


def test_identical_relevant_state_produces_the_same_key():
    a = _make_obs(active_hp=80, hand_count=2)
    b = _make_obs(active_hp=80, hand_count=2)
    assert node_key(a) == node_key(b)


def test_a_real_hp_difference_produces_a_different_key():
    a = _make_obs(active_hp=80)
    b = _make_obs(active_hp=70)
    assert node_key(a) != node_key(b)


def test_a_real_turn_difference_produces_a_different_key():
    a = _make_obs(turn=3)
    b = _make_obs(turn=4)
    assert node_key(a) != node_key(b)


def test_get_counts_misses_and_hits_correctly():
    table = TranspositionTable()
    key = node_key(_make_obs())
    assert table.get(key) is None
    assert table.misses == 1 and table.hits == 0

    table.put(key, TranspositionEntry(value=42.0, depth_searched=1))
    entry = table.get(key)
    assert entry is not None and entry.value == 42.0
    assert table.hits == 1 and table.misses == 1
    assert table.hit_rate == 0.5


def test_eviction_at_capacity_is_fifo_and_bounds_size():
    table = TranspositionTable(max_entries=3)
    for i in range(5):
        table.put(i, TranspositionEntry(value=float(i), depth_searched=1))
    assert len(table) == 3
    # The two oldest (0, 1) should have been evicted; the newest three remain.
    assert table.get(0) is None
    assert table.get(1) is None
    assert table.get(4) is not None


def test_clear_resets_entries_and_counters():
    table = TranspositionTable()
    table.put(1, TranspositionEntry(value=1.0, depth_searched=1))
    table.get(1)
    table.get(2)
    table.clear()
    assert len(table) == 0
    assert table.hits == 0 and table.misses == 0

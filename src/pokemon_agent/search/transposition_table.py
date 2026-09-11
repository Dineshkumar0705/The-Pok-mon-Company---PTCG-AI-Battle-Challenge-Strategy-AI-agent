"""L2 — transposition table: caches leaf/node evaluations within one
expectimax search call so board states reached via different move orders
inside the same turn aren't re-evaluated from scratch.

Scope, stated honestly: this is a plain per-call (or per-agent-lifetime, if
you keep one instance around) hash -> value cache. It is not a persistent
opening book and it is not shared across processes. `search/expectimax.py`
owns one instance per `build_agent()` closure and clears it at real turn
boundaries (state can't transpose across a turn boundary anyway, since hand/
energy-attached/supporter-played reset), which keeps memory bounded and
avoids stale hits from a materially different game state that happens to
hash-collide on stale data left over from many turns ago.

Design: the cache key is a canonical tuple built from exactly the fields
`node_key()` below reads off an Observation — not a cryptographic hash of the
whole JSON blob, so two `search_step()` results that reached the same board
position via a different move order collide on purpose (that's the whole
point of a transposition table) while a real difference in board state never
does. `zlib.crc32` gives a compact fixed-width int key without the overhead
of hashing full JSON strings on every lookup, at the (astronomically small
for this state space) cost of a possible collision.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any, Optional


def _pokemon_signature(p: Any) -> tuple:
    if p is None:
        return (None,)
    return (
        getattr(p, "id", None),
        getattr(p, "hp", None),
        len(getattr(p, "energies", None) or []),
        len(getattr(p, "tools", None) or []),
    )


def node_key(obs: Any) -> int:
    """Canonical, order-sensitive board-state key for the current observation.

    Includes: turn number, whose turn/select this is, select context, both
    players' active + bench (id/hp/energy-count/tool-count), hand counts,
    discard/prize counts, and stadium — everything `option_scorer`'s leaf
    evaluation actually reads. Deliberately excludes full hand/discard
    contents (not read by the leaf evaluator) so unrelated card-order
    differences don't defeat cache hits.
    """
    current = obs.current
    select = obs.select
    parts: list = [
        current.turn,
        current.yourIndex,
        select.context if select is not None else None,
        current.stadium[0].id if current.stadium else 0,
        getattr(current, "energyAttached", None),
        getattr(current, "supporterPlayed", None),
    ]
    for pi in range(2):
        ps = current.players[pi]
        active = ps.active[0] if ps.active else None
        parts.append(_pokemon_signature(active))
        parts.append(tuple(_pokemon_signature(b) for b in ps.bench))
        parts.append(getattr(ps, "handCount", len(getattr(ps, "hand", None) or [])))
        parts.append(len(ps.discard))
        parts.append(len(ps.prize))
    blob = repr(parts).encode("utf-8")
    return zlib.crc32(blob)


@dataclass
class TranspositionEntry:
    value: float
    depth_searched: int
    best_choice: Optional[list] = None


@dataclass
class TranspositionTable:
    """Bounded LRU-ish cache: `max_entries` caps memory; once full, the
    oldest-inserted entry is evicted (simple FIFO via dict insertion order —
    plenty for a single turn's search tree, which is at most a few hundred
    nodes for this game's branching factor)."""

    max_entries: int = 20_000
    _store: dict = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, key: int) -> Optional[TranspositionEntry]:
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
        else:
            self.hits += 1
        return entry

    def put(self, key: int, entry: TranspositionEntry) -> None:
        if key not in self._store and len(self._store) >= self.max_entries:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = entry

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> Optional[float]:
        total = self.hits + self.misses
        return self.hits / total if total else None

"""Turns a real Observation into a fixed-length numeric feature vector, from
one player's perspective (`my_index`). Shared by the Replay Vector Store
(Phase 1) and the learned leaf-value function (Phase 2) so both read the
board state the same way.

Deliberately hand-engineered and small (18 features), matching v5's own
research doc: "start with logistic regression / small gradient-boosted
trees on hand-engineered features... then graduate to a small MLP once
there's enough data." There isn't enough data yet for anything past this --
see docs/v5-architecture.md for the real sample size this was trained on.

Every feature here is read off fields `scoring/pokemon_score.py` and
`search/expectimax.py`'s `position_value()` already use -- this is the same
information the hand-coded evaluator sees, just in a form a model can weigh
instead of a human. That's a deliberate scoping choice: it isolates "does
learning the WEIGHTS beat hand-set ones" as its own testable question,
separate from "would more/different input features help" (a real, separate
next step, not conflated with this one).
"""
from __future__ import annotations

from typing import Any

from ..scoring.pokemon_score import pokemon_score

FEATURE_NAMES = [
    "turn",
    "my_active_hp_frac",
    "my_active_energy_count",
    "my_active_tool_count",
    "my_active_score",
    "my_bench_count",
    "my_bench_avg_hp_frac",
    "my_bench_total_score",
    "my_hand_count",
    "my_discard_count",
    "my_prize_count",
    "op_active_hp_frac",
    "op_active_energy_count",
    "op_active_tool_count",
    "op_active_score",
    "op_bench_count",
    "op_bench_avg_hp_frac",
    "op_bench_total_score",
    "op_hand_count",
    "op_discard_count",
    "op_prize_count",
]


def _hp_frac(p: Any) -> float:
    hp = getattr(p, "hp", 0)
    max_hp = getattr(p, "maxHp", hp) or 1
    return max(0.0, min(1.0, hp / max_hp))


def featurize_observation(obs: Any, card_table: dict, my_index: int) -> list[float]:
    """Real feature extraction from a real (or mock-shaped) Observation.
    Always returns a vector of len(FEATURE_NAMES); a missing/empty zone
    (no active Pokemon, e.g. between-turns edge states) contributes zeros
    rather than raising.
    """
    current = obs.current
    my_state = current.players[my_index]
    op_state = current.players[1 - my_index]

    def side_features(ps) -> list[float]:
        active = ps.active[0] if ps.active else None
        bench = list(ps.bench or [])
        if active is not None:
            active_hp_frac = _hp_frac(active)
            active_energy = len(getattr(active, "energies", None) or [])
            active_tools = len(getattr(active, "tools", None) or [])
            active_score = float(pokemon_score(active, card_table))
        else:
            active_hp_frac = active_energy = active_tools = active_score = 0.0
        bench_count = float(len(bench))
        if bench:
            bench_avg_hp = sum(_hp_frac(b) for b in bench if b is not None) / len(bench)
            bench_total_score = float(sum(pokemon_score(b, card_table) for b in bench if b is not None))
        else:
            bench_avg_hp = bench_total_score = 0.0
        hand_count = float(getattr(ps, "handCount", len(getattr(ps, "hand", None) or [])))
        discard_count = float(len(ps.discard or []))
        prize_count = float(len(ps.prize or []))
        return [active_hp_frac, active_energy, active_tools, active_score,
                bench_count, bench_avg_hp, bench_total_score,
                hand_count, discard_count, prize_count]

    features = [float(current.turn)] + side_features(my_state) + side_features(op_state)
    assert len(features) == len(FEATURE_NAMES), (len(features), len(FEATURE_NAMES))
    return features


# ---------------------------------------------------------------------- v7
# Suphx-style full-information "oracle" leaf value (docs/v7-architecture.md
# item B) was investigated and found genuinely blocked by the real vendored
# engine, not skipped for convenience: `cg.api.Observation.hand` is `None`
# for the opponent by the engine's own contract (`vendor/cg/api.py`'s own
# comment: "None for the opponent"), verified directly against the RAW
# obs_dict during this work, not just the dataclass wrapper -- there is no
# privileged, omniscient view of both hidden hands reachable from this
# Python API, even while this project's own self-play harness is driving
# both seats. Reconstructing it via turn-by-turn bookkeeping was considered
# and rejected: deck order/draws are hidden from BOTH sides by the same
# real constraint, so a hand-tracked "oracle" would eventually be feeding
# the model guessed state dressed up as privileged state, which is exactly
# the kind of overclaiming this project's rules exist to prevent.
#
# Pivoted instead to the v5 doc's own next-named, still-legal alternative:
# one new, fully board-visible feature (below) plus a stronger model class
# (learning/leaf_value.py's new "gbt" option) -- same target question ("why
# did v5's leaf value null out"), different, honest lever.
FEATURE_NAMES_V7 = FEATURE_NAMES + ["stadium_is_full_metal_lab"]

_FULL_METAL_LAB_ID = 1244


def featurize_observation_v7(obs: Any, card_table: dict, my_index: int) -> list[float]:
    """`featurize_observation()` plus one new, fully legal (board-visible to
    both players) feature: whether Full Metal Lab is the active stadium.
    This is a real, materially relevant fact (it changes incoming/outgoing
    damage for this deck's own Metal Pokemon, see scoring/damage.py) that
    v5's original feature set never encoded at all -- not padding, a named
    real gap. Wraps the original function rather than editing it in place,
    so v5's shipped model and its 21-length feature contract are completely
    untouched by this addition.
    """
    base = featurize_observation(obs, card_table, my_index)
    stadium = getattr(obs.current, "stadium", None)
    is_fml = 1.0 if (stadium and len(stadium) > 0 and getattr(stadium[0], "id", None) == _FULL_METAL_LAB_ID) else 0.0
    features = base + [is_fml]
    assert len(features) == len(FEATURE_NAMES_V7), (len(features), len(FEATURE_NAMES_V7))
    return features

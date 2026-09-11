"""Crustle (345) — Mysterious Rock Inn.

Finding: Mysterious Rock Inn blocks ALL damage from ex attackers. Archaludon ex
is itself ex-flagged, so every point of its damage into Crustle was previously
computed as nonzero by dyn_damage() and silently absorbed by the ability
(the engine enforces the block, but the agent's own planning didn't know that,
so it would plan lethal lines into Crustle that could never land). Fixed with
two coordinated pieces: dyn_damage() zeroes the (ex attacker -> Crustle)
pairing (see scoring/damage.py), and the planner should skip that pairing
entirely rather than "plan" a guaranteed no-op — see is_blocked_by_crustle().
"""

Crustle_Wall = 345


def is_blocked_by_crustle(target_pokemon_id: int, attacker_is_ex: bool) -> bool:
    """True if this (attacker, target) pairing is a guaranteed no-op via Mysterious Rock Inn."""
    return target_pokemon_id == Crustle_Wall and attacker_is_ex


def crustle_switch_target_penalty(card_id: int) -> int:
    """Score penalty for dragging up Crustle as a forced-switch target (e.g. via Boss's Orders) —
    it just walls the ex attacker for free, so avoid it when a softer target exists."""
    return -150 if card_id == Crustle_Wall else 0

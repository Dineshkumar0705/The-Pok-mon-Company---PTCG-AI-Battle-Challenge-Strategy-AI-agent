"""Target-priority scoring — ported from v1 main.py's pokemon_score(), with the
two threat bonuses (Fire-type-vs-Metal weakness pressure, Bellibolt ex line
snipe priority) kept as named calls into threats/ instead of inline magic
numbers, so each is independently visible and testable.
"""
from __future__ import annotations

from ..threats.bellibolt_ex import bellibolt_snipe_bonus


def prize_count(pokemon, card_table, energy_healer_id: int = 12) -> int:
    """Prize value of a Pokemon (2 for ex, 3 for Mega ex, 1 otherwise), minus any
    prize-reduction from an attached tool such as Poison Barb (id 12 in v1's
    convention) — ported as-is from v1."""
    data = card_table.get(pokemon.id)
    if data is None:
        return 1
    count = 3 if getattr(data, "megaEx", False) else 2 if getattr(data, "ex", False) else 1
    for c in getattr(pokemon, "energyCards", []):
        if c.id == energy_healer_id:
            count -= 1
    return max(0, count)


def pokemon_score(pokemon, card_table, fire_weakness_energy_type=None) -> int:
    """Priority score for targeting an opponent's Pokemon. Same weighting as v1:
    prize value dominates, then energy investment, then evolution stage, then
    the two named matchup bonuses, then raw HP as a tiebreak.
    """
    data = card_table.get(pokemon.id)
    if data is None:
        return 0
    score = prize_count(pokemon, card_table) * 1000
    score += len(getattr(pokemon, "energies", [])) * 150
    score += len(getattr(pokemon, "tools", [])) * 100
    if getattr(data, "stage2", False):
        score += 250
    elif getattr(data, "stage1", False):
        score += 130
    # Fire-type threats hit Metal for weakness — kill first.
    if fire_weakness_energy_type is not None and getattr(data, "energyType", None) == fire_weakness_energy_type \
            and len(getattr(pokemon, "energies", [])) >= 1:
        score += 450
    # FIX 3: snipe Bellibolt ex pre-evolutions before they come online.
    score += bellibolt_snipe_bonus(pokemon.id)
    score += getattr(pokemon, "hp", 0)
    return score

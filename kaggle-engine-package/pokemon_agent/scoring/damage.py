"""Damage math — ported verbatim in logic from v1 main.py's dyn_damage() and
opp_incoming_damage(), decomposed into pure functions with card_table/
attack_table passed as arguments instead of module globals.

Behavior-preserving change only: same branches, same order of operations, same
constants (Full Metal Lab's -30, Crustle's full-block). The only real
difference from v1 is dependency injection, which is what makes this testable
in isolation (see tests/test_damage.py) without a live engine.
"""
from __future__ import annotations

from ..threats.crustle import Crustle_Wall
from ..threats.alakazam_ex import Alakazam_PowerfulHand, powerful_hand_damage
from ..threats.cornerstone_ogerpon import is_blocked_by_cornerstone_stance

Full_Metal_Lab = 1244
METAL_POKEMON_IDS = {169, 190}  # Duraludon, Archaludon ex


def dyn_damage(attack_id, attacker_data, target_pokemon, attack_table, card_table,
                stadium_id=0, attacker_is_ex=False):
    """Compute attack damage with weakness/resistance/Full Metal Lab/Crustle immunity.

    Identical logic to v1's dyn_damage(); attack_table/card_table are now
    parameters instead of module-level globals populated from a live engine.
    """
    a = attack_table.get(attack_id)
    if a is None:
        return 0
    dmg = a.damage
    # Crustle's Mysterious Rock Inn blocks ALL damage from ex attackers.
    if target_pokemon.id == Crustle_Wall and attacker_is_ex:
        return 0
    # v6: Cornerstone Mask Ogerpon ex's Cornerstone Stance blocks ALL damage
    # from attackers that have an Ability (Archaludon ex, via Assemble
    # Alloy) -- see threats/cornerstone_ogerpon.py for the real card-text
    # source and why Duraludon is unaffected.
    if is_blocked_by_cornerstone_stance(target_pokemon.id, getattr(attacker_data, "cardId", None)):
        return 0
    tdata = card_table.get(target_pokemon.id)
    if tdata is None:
        return dmg
    if tdata.weakness is not None and tdata.weakness == attacker_data.energyType:
        dmg *= 2
    if tdata.resistance is not None and tdata.resistance == attacker_data.energyType:
        dmg = max(0, dmg - 30)
    if stadium_id == Full_Metal_Lab and target_pokemon.id in METAL_POKEMON_IDS:
        dmg = max(0, dmg - 30)
    return dmg


def opp_incoming_damage(op_active, my_active, attack_table, card_table,
                         stadium_id=0, op_hand_count=0):
    """Max damage the opponent's active can deal this turn.

    Identical logic to v1's opp_incoming_damage(), including FIX 1 (Alakazam
    ex's Powerful Hand scales with the opponent's hand size rather than a
    fixed attack_table value).
    """
    if op_active is None or my_active is None:
        return 0
    odata = card_table.get(op_active.id)
    if odata is None:
        return 0
    best = 0
    if op_active.id == Alakazam_PowerfulHand:
        hand_dmg = powerful_hand_damage(op_hand_count)
        if hand_dmg > best:
            best = hand_dmg
    for aid in (getattr(odata, "attacks", []) or []):
        a = attack_table.get(aid)
        if a is None:
            continue
        if len(op_active.energies) < len(a.energies):
            continue
        d = a.damage
        mdata = card_table.get(my_active.id)
        if mdata:
            if mdata.weakness is not None and mdata.weakness == odata.energyType:
                d *= 2
            if mdata.resistance is not None and mdata.resistance == odata.energyType:
                d = max(0, d - 30)
        if stadium_id == Full_Metal_Lab and my_active.id in METAL_POKEMON_IDS:
            d = max(0, d - 30)
        if d > best:
            best = d
    return best

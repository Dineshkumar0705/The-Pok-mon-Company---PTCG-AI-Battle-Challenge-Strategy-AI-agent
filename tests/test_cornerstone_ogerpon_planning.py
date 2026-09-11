"""v6: build_attack_plan must skip Archaludon ex attacking into Cornerstone
Mask Ogerpon ex (guaranteed 0 damage via Cornerstone Stance -- see
threats/cornerstone_ogerpon.py for the real card-text source) and fall
through to Duraludon instead when Duraludon is a viable attacker. Uses
mock_engine fixtures -- no live engine required.
"""
from __future__ import annotations

from pokemon_agent.mock_engine import CardData, AttackData, Pokemon
from pokemon_agent.attack_plans import AttackPlan, Archaludon_ex, Duraludon, build_attack_plan
from pokemon_agent.threats.cornerstone_ogerpon import Cornerstone_Ogerpon_ex


def _card_table():
    return {
        Archaludon_ex: CardData(cardId=Archaludon_ex, ex=True, attacks=[901]),
        Duraludon: CardData(cardId=Duraludon, attacks=[902]),
        Cornerstone_Ogerpon_ex: CardData(cardId=Cornerstone_Ogerpon_ex),
    }


def _attack_table():
    return {
        901: AttackData(attackId=901, damage=220, energies=[1, 1, 1]),  # Metal Defender
        902: AttackData(attackId=902, damage=30, energies=[1]),          # Hammer In
    }


def test_plan_skips_archaludon_into_cornerstone_ogerpon_and_uses_duraludon():
    card_table = _card_table()
    attack_table = _attack_table()

    my_cards = [
        Pokemon(id=Duraludon, hp=130, energies=[8]),            # active, ready
        None,
        Pokemon(id=Archaludon_ex, hp=340, energies=[8, 8, 8]),  # bench, ready
    ]
    op_cards = [Pokemon(id=Cornerstone_Ogerpon_ex, hp=270), None, None]

    plan = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=True, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=5,
        previous_plan=AttackPlan(),
    )
    # Archaludon ex's 220-damage Metal Defender is a guaranteed no-op here
    # (Cornerstone Stance), so the planner must not select it -- it should
    # fall through to Duraludon's Hammer In (real, unblocked damage) instead.
    assert plan.attacker == 0, "should fall through to Duraludon (index 0), not blocked Archaludon ex"


def test_plan_finds_nothing_when_only_archaludon_is_viable_against_cornerstone_ogerpon():
    card_table = _card_table()
    attack_table = _attack_table()

    my_cards = [
        Pokemon(id=Archaludon_ex, hp=340, energies=[8, 8, 8]),  # active, ready
        None,
        None,
    ]
    op_cards = [Pokemon(id=Cornerstone_Ogerpon_ex, hp=270), None, None]

    plan = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=False, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=5,
        previous_plan=AttackPlan(),
    )
    # No viable, non-blocked pairing exists -- the planner must not "plan"
    # the guaranteed no-op; a fresh previous_plan stays at attacker=-1.
    assert plan.attacker == -1

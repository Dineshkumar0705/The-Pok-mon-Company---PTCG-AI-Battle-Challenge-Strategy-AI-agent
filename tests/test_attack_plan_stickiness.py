"""Regression test for the second real bug found via head-to-head validation
against the actual cg engine: v1's `plan` is a single object mutated in place
across every MAIN-context call within one turn, so a call that finds no
viable attacker silently keeps whatever a PRIOR call this turn already found,
rather than resetting to "no plan." build_attack_plan() must reproduce that
via `previous_plan=`, or a real turn can regress from a found attack to none
mid-turn purely because a later MAIN call (e.g. after playing a Trainer) saw
a different, momentarily-unusable active Pokemon.

Uses mock_engine fixtures -- no live engine required.
"""
from __future__ import annotations

from pokemon_agent.mock_engine import CardData, AttackData, Pokemon
from pokemon_agent.attack_plans import (
    AttackPlan, Archaludon_ex, Duraludon, build_attack_plan,
)


def _card_table():
    return {
        Archaludon_ex: CardData(cardId=Archaludon_ex, ex=True, attacks=[901]),
        Duraludon: CardData(cardId=Duraludon, attacks=[902]),
        1: CardData(cardId=1),  # generic opponent target
    }


def _attack_table():
    return {
        901: AttackData(attackId=901, damage=220, energies=[1, 1, 1]),
        902: AttackData(attackId=902, damage=30, energies=[1]),
    }


def test_previous_plan_is_kept_when_this_call_finds_nothing_viable():
    card_table = _card_table()
    attack_table = _attack_table()

    # Call 1: Archaludon ex on the bench (index 2) is fully energized and a
    # target is available -- a real plan should be found (attacker index 2).
    my_cards_turn_start = [
        Pokemon(id=Duraludon, hp=130, energies=[]),           # active, no energy yet
        None,
        Pokemon(id=Archaludon_ex, hp=340, energies=[8, 8, 8]),  # bench, ready to attack
    ]
    op_cards = [Pokemon(id=1, hp=200), None, None]

    plan_after_call1 = build_attack_plan(
        my_cards_turn_start, op_cards, card_table, attack_table,
        can_switch=True, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=5,
        previous_plan=AttackPlan(),
    )
    assert plan_after_call1.attacker == 2, "should have found the ready bench Archaludon ex"

    # Call 2, same turn: agent already played a Trainer, now can_switch is
    # False (no Switch Card / retreat option this select) so only the active
    # Duraludon (index 0, still with 0 energy) is considered -- no viable
    # attacker THIS call. The previously found plan must be preserved, not
    # blanked back to -1.
    plan_after_call2 = build_attack_plan(
        my_cards_turn_start, op_cards, card_table, attack_table,
        can_switch=False, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=True, turn=5,
        previous_plan=plan_after_call1,
    )
    assert plan_after_call2.attacker == 2, (
        "a call that finds nothing viable must keep the prior call's plan, "
        "matching v1's in-place-mutated persistent `plan` object"
    )
    assert plan_after_call2 is plan_after_call1, "same object, mutated in place -- not replaced"


def test_fresh_plan_with_no_previous_plan_defaults_to_unset():
    card_table = _card_table()
    attack_table = _attack_table()
    my_cards = [Pokemon(id=Duraludon, hp=130, energies=[])]  # no viable attacker
    op_cards = [Pokemon(id=1, hp=200)]

    plan = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=False, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=True, turn=5,
        previous_plan=None,
    )
    assert plan.attacker == -1
    assert plan.target == -1


def test_turn_before_two_never_builds_a_plan():
    card_table = _card_table()
    attack_table = _attack_table()
    my_cards = [Pokemon(id=Archaludon_ex, hp=340, energies=[8, 8, 8])]
    op_cards = [Pokemon(id=1, hp=200)]

    plan = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=True, can_op_switch=True, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=1,
        previous_plan=AttackPlan(),
    )
    assert plan.attacker == -1  # turn < 2 always returns the plan untouched

"""v7: cross-turn plan stability (PLAN_STABILITY_BONUS in attack_plans.py).
Real, cited design principle -- PokéLLMon's consistent-action-generation
(arXiv:2402.01118): don't flip-flop the committed attacker for a
near-tied alternative, but never let stability override a real
improvement, including a lethal line. Uses mock_engine fixtures -- no live
engine required.
"""
from __future__ import annotations

from pokemon_agent.mock_engine import CardData, AttackData, Pokemon
from pokemon_agent.attack_plans import AttackPlan, Archaludon_ex, Duraludon, build_attack_plan


def _card_table():
    return {
        Archaludon_ex: CardData(cardId=Archaludon_ex, ex=True, attacks=[901]),
        Duraludon: CardData(cardId=Duraludon, attacks=[902]),
        1: CardData(cardId=1),
    }


def _attack_table(dmg_archaludon=207, dmg_duraludon=200):
    return {
        901: AttackData(attackId=901, damage=dmg_archaludon, energies=[1, 1, 1]),
        902: AttackData(attackId=902, damage=dmg_duraludon, energies=[1]),
    }


def test_near_tied_candidates_prefer_the_previously_committed_attacker():
    card_table = _card_table()
    # Both candidates on the bench (index 1 and 2) -- deliberately avoids
    # the i==0 "active slot" scoring bonus so the comparison isolates the
    # stability bonus, not a confound with it. Archaludon ex's slightly
    # higher raw damage (207 vs 200) gives it a small, real edge (~17
    # points once scaled by pokemon_score/hp) over Duraludon by default --
    # well under PLAN_STABILITY_BONUS (40), so committing to Duraludon last
    # turn should be enough to keep it as the pick.
    attack_table = _attack_table(dmg_archaludon=207, dmg_duraludon=200)

    my_cards = [
        Pokemon(id=999, hp=100, energies=[]),                   # active, not a real candidate (unknown id)
        Pokemon(id=Duraludon, hp=130, energies=[8]),             # bench, index 1
        Pokemon(id=Archaludon_ex, hp=340, energies=[8, 8, 8]),   # bench, index 2
    ]
    op_cards = [Pokemon(id=1, hp=900), None, None]  # high HP -- neither line is lethal

    # No prior commitment (-1): the higher-damage line wins normally.
    plan_no_history = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=True, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=5,
        previous_plan=AttackPlan(), last_committed_attacker=-1,
    )
    assert plan_no_history.attacker == 2  # Archaludon ex, the higher-damage line

    # Same position, but Duraludon (index 1) was the committed attacker last
    # turn -- the near-tie should now resolve in its favor instead.
    plan_with_history = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=True, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=5,
        previous_plan=AttackPlan(), last_committed_attacker=1,
    )
    assert plan_with_history.attacker == 1  # stays with Duraludon


def test_stability_bonus_never_overrides_a_lethal_line():
    card_table = _card_table()
    attack_table = _attack_table(dmg_archaludon=220, dmg_duraludon=30)

    my_cards = [
        Pokemon(id=Duraludon, hp=130, energies=[8]),            # active, index 0 -- committed last turn
        None,
        Pokemon(id=Archaludon_ex, hp=340, energies=[8, 8, 8]),  # bench, index 2 -- the real lethal line
    ]
    # Low HP target: Archaludon ex's 220 damage is lethal, Duraludon's 30 is not.
    op_cards = [Pokemon(id=1, hp=50), None, None]

    plan = build_attack_plan(
        my_cards, op_cards, card_table, attack_table,
        can_switch=True, can_op_switch=False, relicanth_present=False,
        hand_metal_energy_count=0, energy_already_attached=False, turn=5,
        op_remaining_prizes=1,
        previous_plan=AttackPlan(), last_committed_attacker=0,
    )
    assert plan.attacker == 2, "a real lethal KO must never lose to the stability bonus"

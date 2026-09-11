"""Unit tests for the pure scoring/threat math, using mock_engine fixtures.
No live engine required -- these run everywhere, including on a machine
without the proprietary libcg.so (e.g. the user's own Windows checkout).
"""
from __future__ import annotations

from pokemon_agent.mock_engine import CardData, AttackData, Pokemon, EnergyType
from pokemon_agent.scoring.pokemon_score import pokemon_score, prize_count
from pokemon_agent.scoring.damage import dyn_damage, opp_incoming_damage
from pokemon_agent.threats.alakazam_ex import Alakazam_PowerfulHand, powerful_hand_damage
from pokemon_agent.threats.crustle import Crustle_Wall, is_blocked_by_crustle
from pokemon_agent.threats.bellibolt_ex import Iono_Tadbulb
from pokemon_agent.threats.cornerstone_ogerpon import (
    Cornerstone_Ogerpon_ex, is_blocked_by_cornerstone_stance,
    cornerstone_ogerpon_switch_target_penalty,
)


def _card_table(*entries):
    return {c.cardId: c for c in entries}


# ---------------------------------------------------------------- prize_count
def test_prize_count_basic_ex_megaex():
    table = _card_table(
        CardData(cardId=1, ex=False, megaEx=False),
        CardData(cardId=2, ex=True, megaEx=False),
        CardData(cardId=3, ex=True, megaEx=True),
    )
    assert prize_count(Pokemon(id=1), table) == 1
    assert prize_count(Pokemon(id=2), table) == 2
    assert prize_count(Pokemon(id=3), table) == 3


def test_prize_count_unknown_card_defaults_to_one():
    assert prize_count(Pokemon(id=999), {}) == 1


# ------------------------------------------------------------- pokemon_score
def test_pokemon_score_prize_dominates_ordering():
    table = _card_table(
        CardData(cardId=1, ex=False),  # 1 prize
        CardData(cardId=2, ex=True),  # 2 prizes
    )
    low = pokemon_score(Pokemon(id=1, hp=100), table)
    high = pokemon_score(Pokemon(id=2, hp=100), table)
    assert high > low


def test_pokemon_score_fire_weakness_bonus_only_fires_for_matching_energy_type():
    # energyType here is METAL, not FIRE -> the +450 weakness bonus never
    # applies, no matter the energy count (only the general +150/energy
    # investment term should move the score).
    table = _card_table(CardData(cardId=1, energyType=EnergyType.METAL))
    no_energy = pokemon_score(Pokemon(id=1, hp=100, energies=[]), table,
                               fire_weakness_energy_type=EnergyType.FIRE)
    with_energy = pokemon_score(Pokemon(id=1, hp=100, energies=[8]), table,
                                 fire_weakness_energy_type=EnergyType.FIRE)
    assert with_energy - no_energy == 150  # +150/energy only, no weakness bonus

    fire_table = _card_table(CardData(cardId=2, energyType=EnergyType.FIRE))
    base = pokemon_score(Pokemon(id=2, hp=100, energies=[]), fire_table,
                          fire_weakness_energy_type=EnergyType.FIRE)
    boosted = pokemon_score(Pokemon(id=2, hp=100, energies=[8]), fire_table,
                             fire_weakness_energy_type=EnergyType.FIRE)
    assert boosted - base == 150 + 450  # +150/energy AND the +450 weakness bonus


def test_pokemon_score_bellibolt_snipe_bonus_applies_to_preevolutions():
    table = _card_table(CardData(cardId=Iono_Tadbulb))
    boosted = pokemon_score(Pokemon(id=Iono_Tadbulb, hp=60), table)
    plain_table = _card_table(CardData(cardId=1))
    plain = pokemon_score(Pokemon(id=1, hp=60), plain_table)
    assert boosted > plain


# ------------------------------------------------------------------- dyn_damage
def test_dyn_damage_applies_weakness_doubling():
    attacks = {10: AttackData(attackId=10, damage=50, energies=[1])}
    cards = _card_table(CardData(cardId=1, weakness=EnergyType.FIRE))
    attacker = CardData(cardId=99, energyType=EnergyType.FIRE)
    dmg = dyn_damage(10, attacker, Pokemon(id=1), attacks, cards)
    assert dmg == 100


def test_dyn_damage_applies_resistance_reduction_floored_at_zero():
    attacks = {10: AttackData(attackId=10, damage=20, energies=[1])}
    cards = _card_table(CardData(cardId=1, resistance=EnergyType.FIRE))
    attacker = CardData(cardId=99, energyType=EnergyType.FIRE)
    dmg = dyn_damage(10, attacker, Pokemon(id=1), attacks, cards)
    assert dmg == 0  # 20 - 30 floored at 0


def test_dyn_damage_full_metal_lab_reduces_damage_to_metal_targets():
    attacks = {10: AttackData(attackId=10, damage=100, energies=[1])}
    cards = _card_table(CardData(cardId=169))  # Duraludon, a METAL_POKEMON_ID
    attacker = CardData(cardId=99, energyType=EnergyType.COLORLESS)
    dmg = dyn_damage(10, attacker, Pokemon(id=169), attacks, cards, stadium_id=1244)
    assert dmg == 70


def test_dyn_damage_crustle_blocks_all_damage_from_ex_attackers():
    attacks = {10: AttackData(attackId=10, damage=999, energies=[1])}
    cards = _card_table(CardData(cardId=Crustle_Wall))
    attacker = CardData(cardId=190, energyType=EnergyType.METAL)
    dmg = dyn_damage(10, attacker, Pokemon(id=Crustle_Wall), attacks, cards, attacker_is_ex=True)
    assert dmg == 0
    # Non-ex attacker is NOT blocked by Crustle's ability.
    dmg_nonex = dyn_damage(10, attacker, Pokemon(id=Crustle_Wall), attacks, cards, attacker_is_ex=False)
    assert dmg_nonex == 999


def test_is_blocked_by_crustle_matches_dyn_damage():
    assert is_blocked_by_crustle(Crustle_Wall, attacker_is_ex=True) is True
    assert is_blocked_by_crustle(Crustle_Wall, attacker_is_ex=False) is False
    assert is_blocked_by_crustle(1, attacker_is_ex=True) is False


# v6: Cornerstone Mask Ogerpon ex (117) -- Cornerstone Stance blocks all
# damage from attackers that HAVE an Ability (Archaludon ex/Assemble Alloy),
# but not from Duraludon, which has none. See threats/cornerstone_ogerpon.py.
def test_dyn_damage_cornerstone_stance_blocks_archaludon_ex_but_not_duraludon():
    attacks = {10: AttackData(attackId=10, damage=220, energies=[1, 1, 1])}
    cards = _card_table(CardData(cardId=Cornerstone_Ogerpon_ex))
    archaludon_attacker = CardData(cardId=190, energyType=EnergyType.METAL)
    duraludon_attacker = CardData(cardId=169, energyType=EnergyType.METAL)

    dmg_archaludon = dyn_damage(10, archaludon_attacker, Pokemon(id=Cornerstone_Ogerpon_ex),
                                 attacks, cards)
    assert dmg_archaludon == 0  # Assemble Alloy makes Archaludon ex an Ability attacker

    dmg_duraludon = dyn_damage(10, duraludon_attacker, Pokemon(id=Cornerstone_Ogerpon_ex),
                                attacks, cards)
    assert dmg_duraludon == 220  # Duraludon has no Ability -- not blocked


def test_is_blocked_by_cornerstone_stance_matches_dyn_damage():
    assert is_blocked_by_cornerstone_stance(Cornerstone_Ogerpon_ex, attacker_id=190) is True
    assert is_blocked_by_cornerstone_stance(Cornerstone_Ogerpon_ex, attacker_id=169) is False
    assert is_blocked_by_cornerstone_stance(1, attacker_id=190) is False


def test_cornerstone_ogerpon_switch_target_penalty_discourages_gusting_it_up():
    assert cornerstone_ogerpon_switch_target_penalty(Cornerstone_Ogerpon_ex) == -150
    assert cornerstone_ogerpon_switch_target_penalty(1) == 0


# -------------------------------------------------------------- opp_incoming
def test_opp_incoming_damage_alakazam_scales_with_hand_count():
    cards = _card_table(CardData(cardId=Alakazam_PowerfulHand, attacks=[]))
    op = Pokemon(id=Alakazam_PowerfulHand, energies=[])
    my = Pokemon(id=1, hp=200)
    dmg_small_hand = opp_incoming_damage(op, my, {}, cards, op_hand_count=2)
    dmg_big_hand = opp_incoming_damage(op, my, {}, cards, op_hand_count=8)
    assert dmg_small_hand == powerful_hand_damage(2)
    assert dmg_big_hand == powerful_hand_damage(8)
    assert dmg_big_hand > dmg_small_hand


def test_opp_incoming_damage_requires_enough_energy_for_normal_attacks():
    attacks = {10: AttackData(attackId=10, damage=90, energies=[1, 1])}
    cards = _card_table(CardData(cardId=1, attacks=[10]))
    op_not_enough = Pokemon(id=1, energies=[1])
    op_enough = Pokemon(id=1, energies=[1, 1])
    my = Pokemon(id=2, hp=200)
    assert opp_incoming_damage(op_not_enough, my, attacks, cards) == 0
    assert opp_incoming_damage(op_enough, my, attacks, cards) == 90

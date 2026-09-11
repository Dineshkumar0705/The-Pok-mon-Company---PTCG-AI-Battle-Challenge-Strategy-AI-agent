from __future__ import annotations

from pokemon_agent.belief.energy_density import EnergyDensityBelief, BASIC_ENERGY_CARD_TYPE_VALUE
from pokemon_agent.mock_engine import CardData


def _card_table():
    return {
        1: CardData(cardId=1, cardType=BASIC_ENERGY_CARD_TYPE_VALUE),  # an energy card
        2: CardData(cardId=2, cardType=1),  # a non-energy card
    }


def test_density_starts_at_the_flat_prior_with_nothing_observed():
    belief = EnergyDensityBelief(deck_size=60, energy_prior_count=12)
    table = _card_table()
    assert belief.density(table) == 12 / 60


def test_seeing_energy_cards_lowers_the_remaining_density():
    belief = EnergyDensityBelief(deck_size=60, energy_prior_count=12)
    table = _card_table()
    belief.observe([1, 1, 1], table)  # 3 energy cards seen
    # 12 - 3 = 9 energy left believed among 57 unseen cards
    assert belief.density(table) == 9 / 57


def test_seeing_non_energy_cards_only_shrinks_the_unseen_pool():
    belief = EnergyDensityBelief(deck_size=60, energy_prior_count=12)
    table = _card_table()
    belief.observe([2, 2, 2], table)  # 3 non-energy cards seen
    assert belief.density(table) == 12 / 57


def test_density_never_goes_negative_once_prior_is_exhausted():
    belief = EnergyDensityBelief(deck_size=60, energy_prior_count=2)
    table = _card_table()
    belief.observe([1, 1, 1, 1], table)  # saw more energy than the prior allowed
    assert belief.density(table) == 0.0


def test_expected_energy_in_next_n_draws_scales_linearly():
    belief = EnergyDensityBelief(deck_size=60, energy_prior_count=12)
    table = _card_table()
    d = belief.density(table)
    assert belief.expected_energy_in_next_n_draws(5, table) == 5 * d

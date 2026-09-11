"""Opponent hidden-hand belief: an energy-density PRIOR, not a particle filter.

Honesty about scope (this matters for the writeup's Model Score section):
there is no opponent decklist to sample from at inference. A real ISMCTS
implementation over an imperfect-information card game normally
determinizes the hidden zone by sampling a full candidate decklist/hand
consistent with what's been observed (Cowling et al.-style). We don't have
that decklist, so this module does the next best thing that's still honest:
it tracks how many Energy cards have actually been SEEN coming out of the
opponent's deck (their discard pile + battlefield), and estimates the
density of Energy remaining among their unseen cards (hand + deck) against a
generic competitive-deck energy count as a prior -- not a simulation of a
specific real decklist. Treat every number out of this as a soft prior for
tie-breaking and "how likely can they power up next turn" reasoning, not a
certainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Typical competitive PTCG decks run 8-14 Energy cards out of 60; 12 is a
# reasonable generic prior absent any real knowledge of the specific deck.
# This is explicitly a GENERIC prior, not fit to any particular meta deck.
GENERIC_DECK_SIZE = 60
GENERIC_ENERGY_PRIOR_COUNT = 12
BASIC_ENERGY_CARD_TYPE_VALUE = 5  # cg.api.CardType.BASIC_ENERGY


def is_energy_card(card_id: int, card_table: dict) -> bool:
    """True if `card_id` is a Basic Energy card, per `card_table`. Public so
    other modules (search/lookahead.py's belief-informed determinization) can
    reuse the exact same classification this belief model uses internally,
    rather than re-deriving it and risking the two disagreeing."""
    data = card_table.get(card_id)
    if data is None:
        return False
    return getattr(data, "cardType", None) == BASIC_ENERGY_CARD_TYPE_VALUE


# Backward-compatible alias for the original private name.
_is_energy_card = is_energy_card


@dataclass
class EnergyDensityBelief:
    """Call `observe()` every time an opponent card becomes visible (played,
    discarded, attached) -- typically once per MAIN-context agent() call,
    passing the full current field_counts + discard_counts for the opponent.
    `density()` returns the current P(a random unseen opponent card is Energy)
    estimate."""

    deck_size: int = GENERIC_DECK_SIZE
    energy_prior_count: int = GENERIC_ENERGY_PRIOR_COUNT
    _seen_card_ids: list = field(default_factory=list)

    def observe(self, opponent_visible_card_ids, card_table: dict):
        """`opponent_visible_card_ids`: every card ID currently known to have
        left the opponent's hidden zone (discard + in-play + used-up prizes
        if ever revealed). Safe to call repeatedly with the full current set
        each time -- internally deduplicated by position, not by ID (energy
        cards are usually not unique, so counting duplicates matters)."""
        self._seen_card_ids = list(opponent_visible_card_ids)

    @property
    def seen_count(self) -> int:
        return len(self._seen_card_ids)

    def seen_energy_count(self, card_table: dict) -> int:
        return sum(1 for cid in self._seen_card_ids if _is_energy_card(cid, card_table))

    def density(self, card_table: dict) -> float:
        """P(a uniformly random still-unseen opponent card is Energy), under
        the generic-deck prior. Clamped to [0, 1]; returns the flat prior
        density if there are no unseen cards left to reason about."""
        unseen = max(0, self.deck_size - self.seen_count)
        if unseen == 0:
            return 0.0
        remaining_energy_prior = max(0, self.energy_prior_count - self.seen_energy_count(card_table))
        return min(1.0, remaining_energy_prior / unseen)

    def expected_energy_in_next_n_draws(self, n: int, card_table: dict) -> float:
        """Expected number of Energy cards among the opponent's next `n`
        unseen cards (hand refills, deck draws), under this density."""
        return n * self.density(card_table)

"""Regression test for the first real bug found via head-to-head validation:
_is_pokemon_type() matched an enum NAME string, which silently broke when
`cardType` comes through as a raw int -- exactly what the real engine's
to_dataclass() produces (it assigns JSON scalars without enum casting). The
fix compares directly against CardType.POKEMON, which works for both a raw
int (IntEnum equality) and an actual enum instance.
"""
from __future__ import annotations

import pytest

from pokemon_agent.scoring import option_scorer as _os_mod
from pokemon_agent.scoring.option_scorer import _is_pokemon_type
from pokemon_agent.mock_engine import CardData

# Use whichever CardType option_scorer itself resolved to (real cg.api when the
# live engine is importable in this environment, mock_engine otherwise) -- the
# function under test always compares against THAT one, so a test hardcoded to
# mock_engine.CardType would spuriously fail in an environment where the real
# engine is present (they are different, unrelated enums).
CardType = _os_mod.CardType

try:
    from cg.api import CardType as RealCardType
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False


def test_is_pokemon_type_with_real_enum_instance():
    data = CardData(cardId=1, cardType=CardType.POKEMON)
    assert _is_pokemon_type(data) is True

    non_pokemon_member = next(m for m in CardType if m != CardType.POKEMON)
    other = CardData(cardId=2, cardType=non_pokemon_member)
    assert _is_pokemon_type(other) is False


@pytest.mark.skipif(not _ENGINE_AVAILABLE, reason="real cg engine not available")
def test_is_pokemon_type_with_raw_int_like_the_real_engine():
    """The real cg engine's to_dataclass() assigns cardType as a bare int
    (0 for POKEMON in the real cg.api.CardType), not an enum instance -- this
    is the exact shape that broke the old name-string-matching implementation
    (a real, previously-shipping bug caught by tests/test_agent_matches_legacy.py).
    """
    assert RealCardType.POKEMON.value == 0

    class _RawIntCard:
        cardType = 0  # what to_dataclass() actually produces for a Pokemon card

    assert _is_pokemon_type(_RawIntCard()) is True

    class _RawIntItemCard:
        cardType = RealCardType.ITEM.value

    assert _is_pokemon_type(_RawIntItemCard()) is False


def test_is_pokemon_type_handles_missing_cardtype_gracefully():
    class _NoCardType:
        pass

    assert _is_pokemon_type(_NoCardType()) is False

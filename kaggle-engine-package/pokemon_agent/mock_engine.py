"""Minimal, honestly-labeled stand-ins for the real `cg.api` types.

The real battle engine (`cg`) is proprietary to the competition runtime and is
not available outside a Kaggle episode — it is NOT bundled here, and this
module does not attempt to reimplement it. What's below is just enough of the
*shape* of `cg.api`'s data classes (Card, Pokemon, Observation, enums) to let
the pure decision-logic in scoring/, threats/, attack_plans.py, and
deck_loading.py be unit-tested with plain Python objects, independent of a
live engine.

Anything that needs the real engine's rules enforcement, legal-move
enumeration, or turn simulation is explicitly out of scope here — see
src/pokemon_agent/search/expectimax.py's StateSimulator docstring for where
that real dependency has to be wired in by whoever runs this against the
actual competition harness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class CardType(Enum):
    POKEMON = auto()
    TRAINER = auto()
    ENERGY = auto()


class EnergyType(Enum):
    COLORLESS = "C"
    FIRE = "R"
    WATER = "W"
    LIGHTNING = "L"
    GRASS = "G"
    PSYCHIC = "P"
    FIGHTING = "F"
    METAL = "M"
    DRAGON = "N"


class AreaType(Enum):
    DECK = auto()
    HAND = auto()
    DISCARD = auto()
    ACTIVE = auto()
    BENCH = auto()
    PRIZE = auto()
    STADIUM = auto()
    LOOKING = auto()


class OptionType(Enum):
    NUMBER = auto()
    YES = auto()
    CARD = auto()
    PLAY = auto()
    ATTACH = auto()
    EVOLVE = auto()
    ABILITY = auto()
    RETREAT = auto()
    ATTACK = auto()


class SelectContext(Enum):
    MAIN = auto()
    SWITCH = auto()
    TO_ACTIVE = auto()
    SETUP_ACTIVE_POKEMON = auto()
    TO_HAND = auto()
    ATTACH_FROM = auto()


@dataclass
class CardData:
    """A card-table entry — what `card_table[cardId]` looks like in main.py."""

    cardId: int
    cardType: CardType = CardType.POKEMON
    energyType: Optional[EnergyType] = None
    weakness: Optional[EnergyType] = None
    resistance: Optional[EnergyType] = None
    ex: bool = False
    megaEx: bool = False
    stage1: bool = False
    stage2: bool = False
    attacks: list = field(default_factory=list)


@dataclass
class AttackData:
    """An attack-table entry — what `attack_table[attackId]` looks like."""

    attackId: int
    damage: int = 0
    energies: list = field(default_factory=list)


@dataclass
class Card:
    id: int


@dataclass
class Pokemon(Card):
    hp: int = 0
    maxHp: int = 0
    energies: list = field(default_factory=list)
    energyCards: list = field(default_factory=list)
    tools: list = field(default_factory=list)


@dataclass
class PlayerState:
    active: list = field(default_factory=list)
    bench: list = field(default_factory=list)
    hand: list = field(default_factory=list)
    discard: list = field(default_factory=list)
    prize: list = field(default_factory=list)
    handCount: int = 0


@dataclass
class GameState:
    players: list = field(default_factory=list)
    yourIndex: int = 0
    turn: int = 1
    stadium: list = field(default_factory=list)
    energyAttached: bool = False


@dataclass
class Option:
    type: OptionType
    index: int = -1
    area: Optional[AreaType] = None
    playerIndex: int = 0
    inPlayArea: Optional[AreaType] = None
    inPlayIndex: int = -1
    number: int = 0
    attackId: Optional[int] = None


@dataclass
class Select:
    context: SelectContext
    option: list = field(default_factory=list)
    deck: list = field(default_factory=list)
    maxCount: int = 1


@dataclass
class Observation:
    current: GameState
    select: Optional[Select] = None

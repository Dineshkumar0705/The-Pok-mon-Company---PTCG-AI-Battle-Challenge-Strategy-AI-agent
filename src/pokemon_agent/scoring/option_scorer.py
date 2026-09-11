"""Per-option scoring dispatch — ported branch-for-branch from v1 main.py's
`agent()` scoring loop (the `for o in select.option:` block), decomposed into
a TurnContext + score_option()/score_options() pair so it's callable and
testable outside the full agent() control flow.

Every branch below corresponds 1:1 to a branch in v1's main.py. Where v1 used
a bare module-level constant (e.g. `Hero_Cape = 1159`), those constants are
imported from the same place v1 defined them conceptually (attack_plans.py
for the deck's core IDs, threats/ for the three fixes, and this module's own
CARD_IDS for the rest of the trainer/supporter suite) — nothing was renumbered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..attack_plans import AttackPlan, Duraludon, Archaludon_ex, Relicanth
from ..threats.crustle import crustle_switch_target_penalty
from ..threats.cornerstone_ogerpon import (
    cornerstone_ogerpon_switch_target_penalty,
)
from ..engine_interface import get_card

try:
    from cg.api import CardType
except ImportError:
    from ..mock_engine import CardType  # type: ignore

# ---- Trainer/supporter/energy card IDs, as defined in v1 main.py ----
Basic_Metal_Energy = 8
Ultra_Ball = 1121
Night_Stretcher = 1097
Poke_Pad = 1152
Pokegear = 1122
Switch_Card = 1123
Hero_Cape = 1159
Lillie_Determination = 1227
Carmine = 1192
Judge = 1213
Boss_Orders = 1182
Full_Metal_Lab = 1244
Jumbo_Ice_Cream = 1147
Explorers_Guidance = 1185
Cinderace = 666

METAL_POKEMON_IDS = {Duraludon, Archaludon_ex}


@dataclass
class TurnContext:
    obs: Any
    card_table: dict
    attack_table: dict
    plan: AttackPlan
    field_counts: dict
    hand_counts: dict
    discard_counts: dict
    stadium_id: int
    my_active: Any
    active_in_danger: bool
    relicanth_present: bool
    metal_in_discard: int
    my_index: int
    op_state: Any
    my_state: Any
    context: Any  # the actual SelectContext value for this select
    area_type: Any  # AreaType enum module (cg.api.AreaType or mock_engine.AreaType)
    select_context_type: Any  # SelectContext enum module


def energy_score_for_attach(pokemon, is_active: bool) -> int:
    """Score for attaching Metal energy (or evaluating a Pokemon as an energy
    target during ATTACH_FROM/Assemble-Alloy-style selection). Ported as-is."""
    ec = len(pokemon.energies)
    score = 8000
    if is_active:
        score += 10
    if pokemon.id == Archaludon_ex:
        score += 5
        if ec < 3:
            score += 100
        if ec >= 3:
            score -= 300
    elif pokemon.id == Duraludon:
        if ec < 1:
            score += 60
        else:
            score -= 100
    elif pokemon.id == Relicanth:
        score -= 200
    return score


def score_option(o, ctx: TurnContext, option_type) -> int:
    """Score one Option. `option_type` is the OptionType enum module."""
    obs = ctx.obs
    area_type = ctx.area_type
    sctx = ctx.select_context_type
    plan = ctx.plan
    card_table = ctx.card_table

    if o.type == option_type.NUMBER:
        return o.number

    if o.type == option_type.YES:
        return 1

    if o.type == option_type.CARD:
        card = get_card(obs, o.area, area_type, o.index, o.playerIndex)
        if card is None:
            return 0
        if ctx.context in (sctx.SWITCH, sctx.TO_ACTIVE):
            score = 0
            if o.playerIndex == ctx.my_index:
                score += len(card.energies) * 2
                if o.index == plan.attacker - 1:
                    score += 100
                if card.id == Archaludon_ex:
                    score += 30 if len(card.energies) >= 2 else 15
                elif card.id == Duraludon and len(card.energies) >= 1:
                    score += 10
                elif card.id == Relicanth:
                    score -= 20
            else:
                if o.index == plan.target - 1:
                    score += 100
                score += crustle_switch_target_penalty(card.id)
                score += cornerstone_ogerpon_switch_target_penalty(card.id)
            return score

        if ctx.context == sctx.SETUP_ACTIVE_POKEMON:
            if card.id == Duraludon:
                return 5
            if card.id == Relicanth:
                return 3
            return 1

        if ctx.context == sctx.TO_HAND:
            score = 200 - ctx.hand_counts[card.id] * 100
            if card.id in (Duraludon, Archaludon_ex):
                have = ctx.field_counts[Duraludon] + ctx.field_counts[Archaludon_ex]
                score += 30 if have < 2 else -20
            elif card.id == Relicanth:
                score += -100 if ctx.field_counts[Relicanth] >= 1 else 50
            elif card.id == Basic_Metal_Energy:
                score += 25
            elif card.id == Cinderace:
                score += 20 if ctx.field_counts[Cinderace] < 1 else -20
            elif card.id == Lillie_Determination:
                score += 15
            return score

        if ctx.context == sctx.ATTACH_FROM:
            if hasattr(card, "energies"):
                return energy_score_for_attach(card, o.area == area_type.ACTIVE)
            if card.id == Basic_Metal_Energy:
                return 5000
            return 100

        return 0

    if o.type == option_type.PLAY:
        card = get_card(obs, area_type.HAND, area_type, o.index, ctx.my_index)
        if card is None:
            return 1000
        data = card_table.get(card.id)
        if data is None:
            return 1000
        if _is_pokemon_type(data):
            score = 20000
            if card.id == Relicanth and ctx.field_counts[Relicanth] >= 1:
                score = -1
            elif card.id == Duraludon:
                have = ctx.field_counts[Duraludon] + ctx.field_counts[Archaludon_ex]
                if have >= 4:
                    score = -1
            elif card.id == Cinderace:
                if ctx.field_counts[Cinderace] >= 2:
                    score = -1
                else:
                    score += 500
            return score

        # Trainer/supporter/energy
        score = 10000
        if card.id == Switch_Card:
            if plan.attacker > 0:
                score = 6000
            elif ctx.active_in_danger and len(ctx.my_state.bench) > 0:
                score = 5500
            else:
                score = -1
        elif card.id == Boss_Orders:
            score = 3200 if plan.target >= 1 else -1
        elif card.id == Carmine:
            score = 3000
        elif card.id == Lillie_Determination:
            score = 3100
        elif card.id == Judge:
            arch_ready = (
                ctx.field_counts[Archaludon_ex] >= 1
                and any(
                    c is not None and c.id == Archaludon_ex and len(c.energies) >= 3
                    for c in ctx.my_state.active + ctx.my_state.bench
                )
            )
            if arch_ready:
                score = 2800
            elif ctx.obs.current.turn >= 5:
                score = 2400
            else:
                score = -1
        elif card.id == Full_Metal_Lab:
            if ctx.stadium_id != 0 and ctx.stadium_id != Full_Metal_Lab:
                score = 4500
            elif ctx.field_counts[Archaludon_ex] >= 1:
                score = 3800
            else:
                score = 2500
        elif card.id == Ultra_Ball:
            score = 10000
        elif card.id == Pokegear:
            score = 9000
        elif card.id == Night_Stretcher:
            score = 8500 if (ctx.metal_in_discard >= 1 or any(
                c.id in (Duraludon, Relicanth) for c in ctx.my_state.discard
            )) else 3000
        elif card.id == Poke_Pad:
            have_dura = ctx.field_counts[Duraludon] + ctx.field_counts[Archaludon_ex]
            have_relic = ctx.field_counts[Relicanth]
            score = 9500 if (have_dura < 2 or have_relic < 1) else 1500
        elif card.id == Hero_Cape:
            score = 10000
        elif card.id == Jumbo_Ice_Cream:
            my_active = ctx.my_active
            score = 7500 if (
                my_active is not None
                and len(my_active.energies) >= 3
                and my_active.hp < getattr(my_active, "maxHp", my_active.hp)
            ) else -1
        elif card.id == Explorers_Guidance:
            score = 8800
        return score

    if o.type == option_type.ATTACH:
        card = get_card(obs, area_type.HAND, area_type, o.index, ctx.my_index)
        pokemon = get_card(obs, o.inPlayArea, area_type, o.inPlayIndex, ctx.my_index)
        if card is None or pokemon is None:
            return 0
        if card.id == Hero_Cape:
            score = 7000
            if o.inPlayArea == area_type.ACTIVE and ctx.active_in_danger:
                score += 400
            if pokemon.id == Archaludon_ex:
                score += 400
            elif pokemon.id == Duraludon:
                score += 100
            return score
        score = energy_score_for_attach(pokemon, o.inPlayArea == area_type.ACTIVE)
        if o.inPlayArea == area_type.ACTIVE:
            if plan.attacker == 0 and plan.energy:
                score += 200
        else:
            if plan.attacker == 1 + o.inPlayIndex and plan.energy:
                score += 200
        return score

    if o.type == option_type.EVOLVE:
        pokemon = get_card(obs, o.inPlayArea, area_type, o.inPlayIndex, ctx.my_index)
        score = 9000 + len(pokemon.energies)
        if ctx.metal_in_discard >= 2:
            score += 600
        elif ctx.metal_in_discard >= 1:
            score += 200
        return score

    if o.type == option_type.ABILITY:
        card = get_card(obs, o.area, area_type, o.index, ctx.my_index)
        if card is None:
            return 30000
        if card.id == Relicanth:
            return 25000 if ctx.field_counts[Archaludon_ex] >= 1 else 5000
        return 30000

    if o.type == option_type.RETREAT:
        return 2000 if plan.attacker >= 1 else -1

    if o.type == option_type.ATTACK:
        score = 1000
        a = ctx.attack_table.get(getattr(o, "attackId", None)) if ctx.attack_table else None
        if a:
            score += a.damage
        return score

    return 0


def _is_pokemon_type(data) -> bool:
    """Handle both the real cg.api.CardType IntEnum and mock_engine.CardType.

    The real engine's to_dataclass() assigns JSON scalars raw, so
    `data.cardType` comes through as a plain int (e.g. 0), not an enum
    instance. IntEnum compares transparently against raw ints in both
    directions (CardType.POKEMON == 0 is True), so a direct equality check
    against CardType.POKEMON handles both the raw-int (real engine) and
    actual-enum (mock engine) cases correctly -- unlike the previous
    `.name`-string match, which silently failed on raw ints and
    misclassified every Pokemon card into the trainer/energy branch.
    """
    ct = getattr(data, "cardType", None)
    if ct is None:
        return False
    return ct == CardType.POKEMON


def score_options(options, ctx: TurnContext, option_type) -> list[int]:
    return [score_option(o, ctx, option_type) for o in options]

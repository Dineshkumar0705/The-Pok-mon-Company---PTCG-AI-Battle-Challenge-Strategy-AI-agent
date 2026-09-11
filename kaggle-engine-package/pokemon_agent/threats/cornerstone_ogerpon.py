"""Cornerstone Mask Ogerpon ex (117) — Cornerstone Stance.

v6 addition: expert-sourced, not discovered by self-play (this deck's
mirror-match self-play can never surface it -- see docs/v6-architecture.md
for why this had to come from research instead of a measured regression).

Real printed Ability text (Cornerstone Mask Ogerpon ex, card 117 in this
project's own card-data table): "Prevent all damage from attacks done to this
Pokémon by your opponent's Pokémon that have an Ability." That is a
physical-attacker-has-an-Ability trigger, not a blanket "Abilities don't
work" lock -- the attacking Pokémon just needs to HAVE an Ability printed on
it, whether or not that Ability was used this turn.

In THIS deck, Archaludon ex is the only physical attacker with an Ability of
its own (Assemble Alloy) -- Duraludon has none. That holds even when
Archaludon ex is throwing a Duraludon attack borrowed via Relicanth's Memory
Dive (src/pokemon_agent/attack_plans.py): Archaludon ex is still the
physical attacker, so Cornerstone Stance still applies and the borrowed
attack is blocked too. Duraludon itself, attacking directly (not evolved,
or after retreating Archaludon ex back to it), is NOT blocked -- its attacks
carry no Ability tag. The correct real-play line into this matchup is
therefore to lean on Duraludon as the active attacker rather than planning
(and losing tempo on) a guaranteed no-op Archaludon ex swing.

Secondary source corroborating this is a known, real structural weakness in
competitive play (not just a card-text technicality this project noticed
first): Deltia's Gaming's Archaludon ex deck guide
(https://deltiasgaming.com/pokemon-tcg-best-archaludon-ex-deck-guide/,
checked 2026-09-10) names Cornerstone Mask Ogerpon ex specifically as what
the deck is "weak to," describing it as shutting down most of the deck's
Abilities. Limitless TCG's own tournament-history page for the Archaludon
archetype (https://limitlesstcg.com/decks/315, checked 2026-09-10) confirms
this is a real, actively-played archetype (13 Regional Top 8s, 2
International Top 8 finishes at the time checked), which is what makes a
real, sourced counter-card worth coding for rather than a hypothetical.

Wired the same way as threats/crustle.py: a guaranteed-0-damage pairing gets
skipped by the planner (attack_plans.py) and zeroed by the damage calculator
(scoring/damage.py), unconditionally -- this is a rules-correctness fix
(the printed card text is not in dispute), not an experimental, A/B-gated
improvement, exactly like the Crustle and Alakazam ex fixes it sits beside.
"""

Cornerstone_Ogerpon_ex = 117
Archaludon_ex = 190

# Attacker IDs (from THIS deck) that carry an Ability, for Cornerstone
# Stance's "opponent's Pokemon that have an Ability" trigger. Archaludon ex
# has Assemble Alloy. Duraludon and Relicanth-as-a-non-attacker are not in
# this set -- see module docstring for why Duraludon stays unblocked even
# when using a Memory-Dive-eligible attack (the physical attacker matters,
# not which Pokemon's attack text is being borrowed).
ABILITY_ATTACKER_IDS = {Archaludon_ex}


def is_blocked_by_cornerstone_stance(target_pokemon_id: int, attacker_id: int) -> bool:
    """True if this (attacker, target) pairing is a guaranteed no-op via Cornerstone Stance."""
    return target_pokemon_id == Cornerstone_Ogerpon_ex and attacker_id in ABILITY_ATTACKER_IDS


def cornerstone_ogerpon_switch_target_penalty(card_id: int) -> int:
    """Score penalty for dragging up Cornerstone Mask Ogerpon ex as a forced-switch
    target (e.g. via Boss's Orders) -- with Archaludon ex as the only real attacker
    in this deck that can reliably threaten a KO, gusting up the one card that
    walls it for free wastes the Supporter for the turn. Mirrors
    threats/crustle.py's crustle_switch_target_penalty exactly."""
    return -150 if card_id == Cornerstone_Ogerpon_ex else 0

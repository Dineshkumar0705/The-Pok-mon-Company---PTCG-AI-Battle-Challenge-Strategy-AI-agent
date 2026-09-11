"""Attack-plan construction — ported from v1 main.py: AttackPlan, the
Archaludon ex / Duraludon attack candidate lists, and Relicanth's Memory Dive
(borrowing Duraludon's attacks through Archaludon ex, with Raging Hammer's
damage-counter scaling).

v7 addition: PLAN_STABILITY_BONUS (docs/v7-architecture.md). Real, cited
design principle -- PokéLLMon's published "consistent-action-generation"
technique (arXiv:2402.01118) names exactly this failure mode: an agent that
flip-flops its committed line of play between turns purely because two
candidates' scores are nearly tied performs worse against strong opponents
than one that stays the course unless a new option is MEANINGFULLY better.
`build_attack_plan()` already had turn-INTERNAL stickiness (see the
`previous_plan` docstring below, a real bug fix, not this feature); this is
new, separate, cross-TURN stability: a small bonus for re-selecting the
attacker actually committed to on the PREVIOUS turn, small enough to never
override a real improvement (a lethal line, a materially higher-scoring
target) but large enough to break near-ties in favor of not thrashing.
"""
from __future__ import annotations

from dataclasses import dataclass

Duraludon = 169
Archaludon_ex = 190
Relicanth = 57

# v7: small enough to only break near-ties between comparably-good attacker
# choices (the existing i==0/j==0 active-slot bonuses are 220/300, and a
# real damage swing moves `score` by far more than this) -- never large
# enough to keep a worse line over a genuinely better one, including a
# lethal KO (the 50000 game-winning-KO score dwarfs it by three orders of
# magnitude).
PLAN_STABILITY_BONUS = 40


@dataclass
class AttackPlan:
    attacker: int = -1
    target: int = -1
    attack_index: int = -1
    remain_hp: int = -1
    energy: bool = False


def get_archaludon_attacks(card_table, attack_table):
    """(attack_id, damage, energy_needed) for Archaludon ex's own attacks."""
    data = card_table.get(Archaludon_ex)
    if data is None:
        return []
    result = []
    for aid in (getattr(data, "attacks", []) or []):
        a = attack_table.get(aid)
        if a is None:
            continue
        result.append((aid, a.damage, len(a.energies)))
    return result


def get_duraludon_attacks(pokemon, card_table, attack_table):
    """(attack_id, effective_damage, energy_needed) for Duraludon's attacks, usable via
    Memory Dive. Raging Hammer's effective damage scales +10 per damage counter
    already on the user (base + 10 * damage_counters), ported as-is from v1."""
    data = card_table.get(Duraludon)
    if data is None:
        return []
    result = []
    max_hp = getattr(pokemon, "maxHp", pokemon.hp)
    damage_counters = max(0, (max_hp - pokemon.hp) // 10)
    for aid in (getattr(data, "attacks", []) or []):
        a = attack_table.get(aid)
        if a is None:
            continue
        effective_dmg = a.damage + damage_counters * 10
        result.append((aid, effective_dmg, len(a.energies)))
    return result


def relicanth_on_bench(bench) -> bool:
    return any(c is not None and c.id == Relicanth for c in bench)


def build_attack_plan(
    my_cards,
    op_cards,
    card_table,
    attack_table,
    can_switch: bool,
    can_op_switch: bool,
    relicanth_present: bool,
    hand_metal_energy_count: int,
    energy_already_attached: bool,
    turn: int,
    op_remaining_prizes: int = 6,
    stadium_id: int = 0,
    previous_plan: AttackPlan | None = None,
    last_committed_attacker: int = -1,
) -> AttackPlan:
    """Search every (my attacker, op target) pairing and return the best-scoring one.

    Ported from v1 main.py's MAIN-context planning block inside agent(), with
    dyn_damage/Crustle-skip/threat logic delegated to scoring.damage and
    threats.crustle instead of being inlined.

    IMPORTANT (found via real head-to-head validation against the actual cg
    engine): v1's `plan` is a single persistent object, mutated in place every
    time this block runs -- it is NOT reset to a fresh AttackPlan() at the top
    of each MAIN-context call, only at a genuine turn boundary. Within one
    turn, MAIN can be entered several times (e.g. play a Trainer, then get
    asked MAIN again before attacking); v1's `best_score` restarts at -1 each
    of those calls, but a call that finds no viable (attacker, target) pairing
    at all simply never assigns into `plan`, so the fields silently keep
    whatever a PRIOR MAIN call this turn last wrote. A version that instead
    returns a brand-new AttackPlan() whenever the current call finds nothing
    regresses real decisions mid-turn (confirmed by a real mismatch: v1 kept
    attacker=0 target=1 from an earlier call in the turn, entering this call
    with an active Pokemon that no longer has enough energy; recomputing from
    scratch here produced attacker=-1 and picked a different, worse option).
    `previous_plan` restores that stickiness: pass the turn's current plan in,
    and get back the same object, updated in place only when this call
    actually beats it.

    `last_committed_attacker` (v7): the attacker index actually chosen at
    the end of the PREVIOUS turn (agent.py persists this across the
    turn-boundary reset that clears `previous_plan`). Candidates for this
    same attacker get PLAN_STABILITY_BONUS added to their score -- see the
    module docstring for why. -1 (default) means "no prior commitment to
    reward" (e.g. turn 2, the first real attacking turn), a no-op.
    """
    from .scoring.damage import dyn_damage
    from .threats.crustle import is_blocked_by_crustle
    from .threats.cornerstone_ogerpon import is_blocked_by_cornerstone_stance
    from .scoring.pokemon_score import pokemon_score

    plan = previous_plan if previous_plan is not None else AttackPlan()
    if turn < 2:
        return plan

    best_score = -1
    for i, my_pokemon in enumerate(my_cards):
        if my_pokemon is None:
            continue
        if i != 0 and not can_switch:
            break

        mdata = card_table.get(my_pokemon.id)
        if mdata is None:
            continue

        candidate_attacks = []
        is_ex_attacker = bool(mdata and (getattr(mdata, "ex", False) or getattr(mdata, "megaEx", False)))
        if my_pokemon.id == Archaludon_ex:
            candidate_attacks.extend(get_archaludon_attacks(card_table, attack_table))
            if relicanth_present:
                candidate_attacks.extend(get_duraludon_attacks(my_pokemon, card_table, attack_table))
        elif my_pokemon.id == Duraludon:
            candidate_attacks.extend(get_duraludon_attacks(my_pokemon, card_table, attack_table))

        for aid, base_dmg, energy_needed in candidate_attacks:
            if base_dmg <= 0:
                continue
            cur_energy = len(my_pokemon.energies)
            more_energy = False
            if cur_energy < energy_needed:
                if hand_metal_energy_count >= 1 and not energy_already_attached:
                    cur_energy += 1
                    more_energy = True
                if cur_energy < energy_needed:
                    continue

            for j, op_pokemon in enumerate(op_cards):
                if op_pokemon is None:
                    continue
                if j != 0 and not can_op_switch:
                    break

                if is_blocked_by_crustle(op_pokemon.id, is_ex_attacker):
                    # Guaranteed no-op -- never plan this pairing.
                    continue
                if is_blocked_by_cornerstone_stance(op_pokemon.id, my_pokemon.id):
                    # v6: Cornerstone Stance guaranteed no-op for Ability
                    # attackers (Archaludon ex) -- never plan this pairing
                    # either; fall through to Duraludon if it's viable.
                    continue

                damage = dyn_damage(aid, mdata, op_pokemon, attack_table, card_table,
                                     stadium_id=stadium_id, attacker_is_ex=is_ex_attacker)
                if damage == 0:
                    damage = base_dmg

                score = pokemon_score(op_pokemon, card_table)
                if op_pokemon.hp <= damage:
                    from .scoring.pokemon_score import prize_count
                    prize = prize_count(op_pokemon, card_table)
                    if op_remaining_prizes <= prize:
                        score = 50000  # game-winning KO
                else:
                    score *= damage / max(1, op_pokemon.hp)

                if i == 0:
                    score += 220
                if j == 0:
                    score += 300
                score += cur_energy
                if i == last_committed_attacker:
                    score += PLAN_STABILITY_BONUS

                if score > best_score:
                    best_score = score
                    plan.attacker = i
                    plan.target = j
                    plan.attack_index = 0
                    plan.remain_hp = op_pokemon.hp - damage
                    plan.energy = more_energy

    return plan

import os
import sys
from collections import defaultdict

from cg.api import (AreaType, CardType, EnergyType, Observation, SelectContext,
                    OptionType, Card, Pokemon, all_card_data, all_attack,
                    to_observation_class)

"""
ARCHALUDON ex "Steel Fortress" Agent -- v3 (upgraded from v28 real-ladder audit
+ a critical deck-loading fix found in the v2 notebook's own real ladder run)

Base: the project's 791.ipynb "Steel Fortress" agent (shipped unmodified as
build/portfolio_archaludon/main.py). This version starts from that same core
engine and adds three narrow, card-ID-gated fixes found by auditing 47 real
Kaggle-ladder replays of a sibling notebook (apextcg-v28), which went 22W-22L
on the live ladder. The three losses/near-losses traced to distinct causes:

  FIX 1 -- Alakazam ex (743) "Powerful Hand": damage = handCount * 20, not a
  fixed number, so opp_incoming_damage()'s attack_table.damage lookup silently
  under-counts it (attack_table stores 0/placeholder damage for hand-scaling
  attacks). Added an explicit case so active_in_danger correctly accounts for
  a loaded Alakazam hand before we commit to attacking instead of retreating.

  FIX 2 -- Crustle (345) "Mysterious Rock Inn": prevents ALL damage from
  attacks by ex Pokemon. Archaludon ex is ex-flagged, so every point of
  Archaludon-ex damage into Crustle silently no-ops even though dyn_damage()
  reports a nonzero number (it doesn't know about ability-based immunity).
  Added a Crustle-immunity check that zeroes any Archaludon-ex-vs-Crustle
  attack candidate and instead routes through Duraludon's own attacks (not
  ex-flagged, so damage goes through normally), or prefers Boss's Orders to
  drag up a non-Crustle target when available.

  FIX 3 -- Iono's Bellibolt ex (269) line pressure-deny: Bellibolt ex itself
  is a 280 HP wall, but its pre-evolutions Iono's Tadbulb (268, 60 HP) and
  Iono's Wattrel (270, 60 HP) are cheap, low-HP setup pieces. Sniping either
  on the bench before it evolves denies the whole Electric Streamer + 230-dmg
  Thunderous Bolt engine from ever coming online. Added a kill-priority bonus
  for these IDs so the agent takes a "small" KO over passing when it's free.

Also extends card handling to the REAL v28 battle-tested 60-card deck (pulled
directly from a v28 replay's starting-hand ground truth, not the older
791-era decklist), which swaps in Cinderace (666, energy-ramp attacker),
Jumbo Ice Cream (1147, conditional heal), and Explorer's Guidance (1185,
dig-and-select draw) in place of Carmine. This card handling stays unused on
the currently-shipped deck (see the deck-configuration cell for why) but is
kept in for a future attempt.

v3 CHANGES (this notebook's own real ladder run surfaced two more issues):
  - The notebook's deck-loading cell had a bug (not in this file) that let a
    Kaggle-auto-mounted, totally unrelated deck.csv silently override the
    real deck below for every game played on the ladder — see the deck-
    configuration cell's comments for the fix.
  - `is_ex_attacker` (used by the Crustle fix) is now computed generically
    from `card_table[id].ex`/`.megaEx` instead of a hardcoded Archaludon_ex
    ID check, so the Crustle-avoidance logic keeps working correctly even if
    a deck/attacker mismatch like the one above were ever to happen again.
"""

# ------------------------------------------------------------------ deck
file_path = "deck.csv"
if not os.path.exists(file_path):
    file_path = "/kaggle_simulations/agent/" + file_path
with open(file_path, "r") as f:
    csv_data = f.read().split("\n")
my_deck = [int(csv_data[i]) for i in range(60)]

# ------------------------------------------------------------------ card data
all_card = all_card_data()
card_table = {c.cardId: c for c in all_card}
attack_table = {a.attackId: a for a in all_attack()}

# ------------------------------------------------------------------ constants
Duraludon       = 169
Archaludon_ex   = 190
Relicanth       = 57
Cinderace       = 666

Basic_Metal_Energy = 8

Ultra_Ball          = 1121
Night_Stretcher     = 1097
Poke_Pad            = 1152
Pokegear            = 1122
Switch_Card         = 1123
Hero_Cape           = 1159
Lillie_Determination = 1227
Carmine             = 1192
Judge               = 1213
Boss_Orders         = 1182
Full_Metal_Lab      = 1244
Jumbo_Ice_Cream     = 1147
Explorers_Guidance  = 1185

METAL_POKEMON_IDS = {Duraludon, Archaludon_ex}

# Threats found via real-ladder replay audit (v28, 22W-22L, 47 games)
Alakazam_PowerfulHand = 743      # 140 HP {P}; Powerful Hand = handCount * 20 dmg
Crustle_Wall           = 345     # 150 HP {G}; Mysterious Rock Inn: immune to ex-attacker damage
Bellibolt_ex           = 269     # 280 HP {L}; Thunderous Bolt 230 dmg, locks next turn
Iono_Tadbulb            = 268     # 60 HP -- Bellibolt pre-evo #1 (snipe target)
Iono_Wattrel            = 270     # 60 HP -- Bellibolt pre-evo #2 (snipe target)
BELLIBOLT_SNIPE_IDS = {Iono_Tadbulb, Iono_Wattrel}

# ------------------------------------------------------------------ state
class AttackPlan:
    attacker = -1; target = -1; attack_index = -1; remain_hp = -1
    energy = False
plan = AttackPlan()
pre_turn = 0

# ------------------------------------------------------------------ helpers
def get_card(obs, area, index, player_index):
    ps = obs.current.players[player_index]
    if area == AreaType.DECK:    return obs.select.deck[index]
    if area == AreaType.HAND:    return ps.hand[index]
    if area == AreaType.DISCARD: return ps.discard[index]
    if area == AreaType.ACTIVE:  return ps.active[index]
    if area == AreaType.BENCH:   return ps.bench[index]
    if area == AreaType.PRIZE:   return ps.prize[index]
    if area == AreaType.STADIUM: return obs.current.stadium[index]
    if area == AreaType.LOOKING: return obs.current.looking[index]
    return None

def prize_count(pokemon):
    data = card_table.get(pokemon.id)
    if data is None: return 1
    count = 3 if data.megaEx else 2 if data.ex else 1
    for c in pokemon.energyCards:
        if c.id == 12: count -= 1
    return max(0, count)

def dyn_damage(attack_id, attacker_data, target_pokemon, stadium_id=0, attacker_is_ex=False):
    """Compute attack damage with weakness/resistance/Full Metal Lab/Crustle immunity."""
    a = attack_table.get(attack_id)
    if a is None: return 0
    dmg = a.damage
    # FIX 2: Crustle's Mysterious Rock Inn blocks ALL damage from ex attackers.
    if target_pokemon.id == Crustle_Wall and attacker_is_ex:
        return 0
    tdata = card_table.get(target_pokemon.id)
    if tdata is None: return dmg
    if tdata.weakness is not None and tdata.weakness == attacker_data.energyType:
        dmg *= 2
    if tdata.resistance is not None and tdata.resistance == attacker_data.energyType:
        dmg = max(0, dmg - 30)
    # Full Metal Lab: if target is Metal, reduce damage by 30
    if stadium_id == Full_Metal_Lab and target_pokemon.id in METAL_POKEMON_IDS:
        dmg = max(0, dmg - 30)
    return dmg

def opp_incoming_damage(op_active, my_active, stadium_id=0, op_hand_count=0):
    """Max damage opponent's active can deal this turn."""
    if op_active is None or my_active is None: return 0
    odata = card_table.get(op_active.id)
    if odata is None: return 0
    best = 0
    # FIX 1: Alakazam ex Powerful Hand scales with the OPPONENT's hand size,
    # not a fixed attack_table value (hand-scaling attacks store 0/placeholder
    # damage there). Compute it directly so we don't walk into a lethal hit
    # thinking it's a small one.
    if op_active.id == Alakazam_PowerfulHand:
        hand_dmg = op_hand_count * 20
        if hand_dmg > best:
            best = hand_dmg
    for aid in (getattr(odata, 'attacks', []) or []):
        a = attack_table.get(aid)
        if a is None: continue
        if len(op_active.energies) < len(a.energies): continue
        d = a.damage
        mdata = card_table.get(my_active.id)
        if mdata:
            if mdata.weakness is not None and mdata.weakness == odata.energyType:
                d *= 2
            if mdata.resistance is not None and mdata.resistance == odata.energyType:
                d = max(0, d - 30)
        # Full Metal Lab reduces damage to our Metal Pokemon
        if stadium_id == Full_Metal_Lab and my_active.id in METAL_POKEMON_IDS:
            d = max(0, d - 30)
        if d > best: best = d
    return best

def pokemon_score(pokemon):
    """Priority score for targeting an opponent's Pokemon."""
    data = card_table.get(pokemon.id)
    if data is None: return 0
    score = prize_count(pokemon) * 1000
    score += len(pokemon.energies) * 150
    score += len(getattr(pokemon, 'tools', [])) * 100
    if getattr(data, 'stage2', False): score += 250
    elif getattr(data, 'stage1', False): score += 130
    # Fire-type threats hit Metal for weakness — kill first
    if getattr(data, 'energyType', None) == EnergyType.FIRE and len(pokemon.energies) >= 1:
        score += 450
    # FIX 3: snipe Bellibolt ex pre-evolutions before they come online —
    # cheap (60 HP) kills that deny the whole Electric Streamer engine.
    if pokemon.id in BELLIBOLT_SNIPE_IDS:
        score += 500
    score += pokemon.hp
    return score

def get_archaludon_attacks(pokemon):
    """Return list of (attack_id, damage) for Archaludon ex, including Memory Dive."""
    data = card_table.get(Archaludon_ex)
    if data is None: return []
    result = []
    for aid in (getattr(data, 'attacks', []) or []):
        a = attack_table.get(aid)
        if a is None: continue
        result.append((aid, a.damage, len(a.energies)))
    return result

def get_duraludon_attacks(pokemon):
    """Return Duraludon attacks usable via Memory Dive (Raging Hammer etc)."""
    data = card_table.get(Duraludon)
    if data is None: return []
    result = []
    damage_counters = max(0, (getattr(pokemon, 'maxHp', pokemon.hp) - pokemon.hp) // 10)
    for aid in (getattr(data, 'attacks', []) or []):
        a = attack_table.get(aid)
        if a is None: continue
        # Raging Hammer: base 80 + 10 per damage counter
        effective_dmg = a.damage + damage_counters * 10
        result.append((aid, effective_dmg, len(a.energies)))
    return result

def energy_score_for_attach(pokemon, is_active):
    """Score for attaching Metal energy to a given Pokemon."""
    ec = len(pokemon.energies)
    score = 8000
    if is_active: score += 10
    if pokemon.id == Archaludon_ex:
        score += 5
        if ec < 3: score += 100    # needs 3 for Metal Defender
        if ec >= 3: score -= 300   # already set — put elsewhere
    elif pokemon.id == Duraludon:
        if ec < 1: score += 60    # 1 energy on pre-evo: useful if it gets attacked early
        else: score -= 100
    elif pokemon.id == Relicanth:
        score -= 200               # Relicanth needs no energy
    return score

# ------------------------------------------------------------------ agent
def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    state    = obs.current
    select   = obs.select
    context  = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]
    my_prize = len(my_state.prize)

    global plan, pre_turn
    if pre_turn != state.turn:
        pre_turn = state.turn
        plan = AttackPlan()

    # ---- field census ----
    field_counts   = defaultdict(int)
    hand_counts    = defaultdict(int)
    discard_counts = defaultdict(int)
    for c in my_state.active + my_state.bench:
        if c is None: continue
        field_counts[c.id] += 1
    for c in my_state.hand:    hand_counts[c.id]    += 1
    for c in my_state.discard: discard_counts[c.id] += 1

    stadium_id = state.stadium[0].id if state.stadium else 0
    my_active  = my_state.active[0] if my_state.active else None
    op_active  = op_state.active[0] if op_state.active else None
    op_hand_count = getattr(op_state, 'handCount', len(getattr(op_state, 'hand', []) or []))

    relicanth_on_bench = any(
        c is not None and c.id == Relicanth for c in my_state.bench
    )
    metal_in_discard = discard_counts[Basic_Metal_Energy]

    incoming      = opp_incoming_damage(op_active, my_active, stadium_id, op_hand_count)
    active_in_danger = my_active is not None and incoming >= my_active.hp

    # ---- build attack plan (MAIN context only) ----
    can_attack  = False
    can_switch  = False
    can_op_switch = False

    if context == SelectContext.MAIN:
        for o in select.option:
            if o.type == OptionType.PLAY:
                c = get_card(obs, AreaType.HAND, o.index, my_index)
                if c.id == Switch_Card:  can_switch    = True
                elif c.id == Boss_Orders: can_op_switch = True
            elif o.type == OptionType.RETREAT:
                can_switch = True
            elif o.type == OptionType.ATTACK:
                can_attack = True

        my_cards = [my_state.active[0]] + list(my_state.bench)
        op_cards = [op_state.active[0]] + list(op_state.bench)

        if state.turn >= 2:
            best_score = -1
            for i, my_pokemon in enumerate(my_cards):
                if my_pokemon is None: continue
                if i != 0 and not can_switch: break

                mdata = card_table.get(my_pokemon.id)
                if mdata is None: continue

                # Collect attacks this Pokemon can use
                candidate_attacks = []
                # Generalized ex-attacker check (not hardcoded to Archaludon_ex):
                # Crustle's Mysterious Rock Inn blocks damage from ANY ex attacker,
                # so this needs to hold even if this code ever ends up piloting a
                # different deck (defense-in-depth after the deck-loading bug fix
                # below — see notebook overview for what caused that).
                is_ex_attacker = bool(mdata and (getattr(mdata, 'ex', False) or getattr(mdata, 'megaEx', False)))
                if my_pokemon.id == Archaludon_ex:
                    candidate_attacks.extend(get_archaludon_attacks(my_pokemon))
                    # Memory Dive adds Duraludon attacks if Relicanth is on bench.
                    # These go through Archaludon ex's own body, so Crustle's
                    # ex-immunity STILL applies (the attacker is Archaludon ex).
                    if relicanth_on_bench:
                        candidate_attacks.extend(get_duraludon_attacks(my_pokemon))
                elif my_pokemon.id == Duraludon:
                    candidate_attacks.extend(get_duraludon_attacks(my_pokemon))

                for aid, base_dmg, energy_needed in candidate_attacks:
                    if base_dmg <= 0: continue
                    cur_energy = len(my_pokemon.energies)
                    more_energy = False
                    if cur_energy < energy_needed:
                        if hand_counts[Basic_Metal_Energy] >= 1 and not state.energyAttached:
                            cur_energy += 1
                            more_energy = True
                        if cur_energy < energy_needed: continue

                    for j, op_pokemon in enumerate(op_cards):
                        if op_pokemon is None: continue
                        if j != 0 and not can_op_switch: break

                        damage = dyn_damage(aid, mdata, op_pokemon, stadium_id, is_ex_attacker)
                        if damage == 0 and not (op_pokemon.id == Crustle_Wall and is_ex_attacker):
                            damage = base_dmg
                        # FIX 2: never plan an ex-attacker hit into Crustle — it's a
                        # guaranteed no-op. Skip this (attacker, target) pairing
                        # entirely so the planner looks for another attacker/target.
                        if op_pokemon.id == Crustle_Wall and is_ex_attacker:
                            continue

                        score = pokemon_score(op_pokemon)
                        if op_pokemon.hp <= damage:
                            prize = prize_count(op_pokemon)
                            if len(op_state.prize) <= prize: score = 50000  # game-winning KO
                        else:
                            score *= damage / max(1, op_pokemon.hp)

                        if i == 0:  score += 220   # active attacker bonus
                        if j == 0:  score += 300   # active target bonus
                        score += cur_energy

                        if score > best_score:
                            best_score     = score
                            plan.attacker  = i
                            plan.target    = j
                            plan.attack_index = 0
                            plan.remain_hp = op_pokemon.hp - damage
                            plan.energy    = more_energy

    # ---- score every option ----
    scores = []
    for o in select.option:
        score = 0

        if o.type == OptionType.NUMBER:
            score = o.number

        elif o.type == OptionType.YES:
            score = 1

        elif o.type == OptionType.CARD:
            card = get_card(obs, o.area, o.index, o.playerIndex)
            if card is None:
                score = 0
            elif context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
                if o.playerIndex == my_index:
                    score += len(card.energies) * 2
                    if o.index == plan.attacker - 1: score += 100
                    if card.id == Archaludon_ex:
                        score += 30 if len(card.energies) >= 2 else 15
                    elif card.id == Duraludon and len(card.energies) >= 1:
                        score += 10
                    elif card.id == Relicanth:
                        # keep Relicanth on bench for Memory Dive
                        score -= 20
                else:
                    # Opponent switch target.
                    if o.index == plan.target - 1: score += 100
                    # FIX 2: when using Boss's Orders / forced-switch selection,
                    # avoid dragging up Crustle if a softer target exists —
                    # Crustle just walls our ex attacker for free.
                    if card.id == Crustle_Wall: score -= 150

            elif context == SelectContext.SETUP_ACTIVE_POKEMON:
                # T1 active choice: Duraludon is ideal (evolves into win con)
                if card.id == Duraludon:  score = 5
                elif card.id == Relicanth: score = 3   # bench role
                else: score = 1

            elif context == SelectContext.TO_HAND:
                # Picking from discard or searching
                score = 200 - hand_counts[card.id] * 100
                if card.id in (Duraludon, Archaludon_ex):
                    have = field_counts[Duraludon] + field_counts[Archaludon_ex]
                    score += 30 if have < 2 else -20
                elif card.id == Relicanth:
                    score += -100 if field_counts[Relicanth] >= 1 else 50
                elif card.id == Basic_Metal_Energy:
                    score += 25   # energy in hand = T1 attach
                elif card.id == Cinderace:
                    score += 20 if field_counts[Cinderace] < 1 else -20
                elif card.id == Lillie_Determination:
                    score += 15

            elif context == SelectContext.ATTACH_FROM:
                # Assemble Alloy fires here: pick best Metal targets from discard
                if isinstance(card, Pokemon):
                    score = energy_score_for_attach(card, o.area == AreaType.ACTIVE)
                else:
                    # Energy card — Metal energy is always good
                    if card.id == Basic_Metal_Energy:
                        score = 5000
                    else:
                        score = 100

        elif o.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, o.index, my_index)
            if card is None:
                score = 1000
                scores.append(score); continue
            data = card_table.get(card.id)
            if data is None:
                score = 1000
            elif data.cardType == CardType.POKEMON:
                score = 20000
                # Don't double-up on Relicanth
                if card.id == Relicanth and field_counts[Relicanth] >= 1:
                    score = -1
                # Don't over-bench Duraludon line
                elif card.id == Duraludon:
                    have = field_counts[Duraludon] + field_counts[Archaludon_ex]
                    if have >= 4: score = -1
                # Cinderace: ramp piece — get it down early, but don't flood
                elif card.id == Cinderace:
                    if field_counts[Cinderace] >= 2: score = -1
                    else: score += 500
            else:
                score = 10000
                if card.id == Switch_Card:
                    if plan.attacker > 0:        score = 6000
                    elif active_in_danger and len(my_state.bench) > 0: score = 5500
                    else: score = -1

                elif card.id == Boss_Orders:
                    score = 3200 if plan.target >= 1 else -1

                elif card.id == Carmine:
                    # Great T1 card — discard hand, draw 5
                    score = 3000

                elif card.id == Lillie_Determination:
                    # Draw 6 (8 if 6 prizes remain)
                    score = 3100

                elif card.id == Judge:
                    # Disrupt opponent: play when Archaludon ex is set up
                    # Avoid early (hurts our own setup)
                    arch_ready = (field_counts[Archaludon_ex] >= 1 and
                                  any(c is not None and c.id == Archaludon_ex
                                      and len(c.energies) >= 3
                                      for c in my_state.active + my_state.bench))
                    if arch_ready:
                        score = 2800   # disrupt after we're ready
                    elif state.turn >= 5:
                        score = 2400   # late game always valuable
                    else:
                        score = -1     # T1-T3 too early

                elif card.id == Full_Metal_Lab:
                    if stadium_id != 0 and stadium_id != Full_Metal_Lab:
                        score = 4500   # overwrite opponent's stadium ASAP
                    elif field_counts[Archaludon_ex] >= 1:
                        score = 3800   # -30 dmg when 300-400 HP tank is active
                    else:
                        score = 2500   # set up proactively

                elif card.id == Ultra_Ball:
                    score = 10000      # search any Pokemon (get Duraludon/Relicanth)

                elif card.id == Pokegear:
                    score = 9000       # top 7 for supporter

                elif card.id == Night_Stretcher:
                    # Recover Metal energy from discard (re-fuel Assemble Alloy)
                    # or recover a KO'd Duraludon/Relicanth
                    if metal_in_discard >= 1 or any(
                        c.id in (Duraludon, Relicanth) for c in my_state.discard
                    ):
                        score = 8500
                    else:
                        score = 3000

                elif card.id == Poke_Pad:
                    # Fetches non-Rule Box Pokemon (Duraludon, Relicanth)
                    have_dura  = field_counts[Duraludon] + field_counts[Archaludon_ex]
                    have_relic = field_counts[Relicanth]
                    if have_dura < 2 or have_relic < 1:
                        score = 9500   # high prio — fill bench
                    else:
                        score = 1500   # already set

                elif card.id == Hero_Cape:
                    score = 10000      # ACE SPEC — always play (Archaludon ex → 400 HP)

                elif card.id == Jumbo_Ice_Cream:
                    # Heal 80 if active has 3+ energy attached — play only when
                    # our active is actually damaged, otherwise it's wasted.
                    if (my_active is not None and len(my_active.energies) >= 3
                            and my_active.hp < getattr(my_active, 'maxHp', my_active.hp)):
                        score = 7500
                    else:
                        score = -1

                elif card.id == Explorers_Guidance:
                    # Look at top 6, take 2 — strong mid-game dig/consistency card.
                    score = 8800

        elif o.type == OptionType.ATTACH:
            card    = get_card(obs, AreaType.HAND, o.index, my_index)
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            if card is None or pokemon is None:
                score = 0
            elif card.id == Hero_Cape:
                score = 7000
                if o.inPlayArea == AreaType.ACTIVE and active_in_danger: score += 400
                if pokemon.id == Archaludon_ex: score += 400  # 300 → 400 HP is the goal
                elif pokemon.id == Duraludon:   score += 100
            else:
                # Energy attachment
                score = energy_score_for_attach(pokemon, o.inPlayArea == AreaType.ACTIVE)
                # Boost toward attacker if attack plan exists
                if o.inPlayArea == AreaType.ACTIVE:
                    if plan.attacker == 0 and plan.energy: score += 200
                else:
                    if plan.attacker == 1 + o.inPlayIndex and plan.energy: score += 200

        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score = 9000 + len(pokemon.energies)
            # Evolving with 2+ Metal in discard → Assemble Alloy instant 2 energy attach!
            if metal_in_discard >= 2: score += 600
            elif metal_in_discard >= 1: score += 200

        elif o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if card is None:
                score = 30000
            elif card.id == Relicanth:
                # Memory Dive: enable only when Archaludon ex is active attacker
                score = 25000 if field_counts[Archaludon_ex] >= 1 else 5000
            else:
                score = 30000

        elif o.type == OptionType.RETREAT:
            # NOTE: an earlier version of this fix also boosted RETREAT's score
            # whenever active_in_danger was true even without an attack plan.
            # Direct A/B testing (n=16, real engine) showed that broadened
            # retreat trigger caused a real regression (25% vs a 56% baseline
            # with it reverted) — it made the agent over-retreat and lose
            # tempo in ordinary trades, not just genuine lethal-Alakazam
            # avoid. Reverted to the original narrow rule. The Alakazam hand-
            # damage fix still helps: it feeds a more accurate active_in_danger
            # into the EXISTING Switch_Card PLAY scoring below, without adding
            # a new always-on retreat pathway.
            score = 2000 if plan.attacker >= 1 else -1

        elif o.type == OptionType.ATTACK:
            score = 1000
            # Pick the highest-damage available attack
            a = attack_table.get(getattr(o, 'attackId', None))
            if a:
                score += a.damage

        scores.append(score)

    desc = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
    if context == SelectContext.MAIN and desc:
        pass  # no extra state tracking needed
    return desc[:select.maxCount]

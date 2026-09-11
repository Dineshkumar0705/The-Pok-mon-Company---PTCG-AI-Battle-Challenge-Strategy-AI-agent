"""Real forward search over the actual cg engine via search_begin/search_step
/search_end -- belief-state determinization + real simulation, not a stub.

STATUS: this is genuinely validated plumbing (see
tests/test_lookahead.py, which runs it against the real engine, and the
module-level notes below on exactly what was confirmed). It is NOT wired
into agent.py's decision-making, and ships disabled/unused by default. That
is a deliberate scope boundary, not an oversight: turning this into an
actual move-ranking layer needs a real scoring function over the resulting
SearchState (how much did this line of play help us?) and real win-rate A/B
validation against the heuristic-only baseline (matching how the two
already-shipped bugs in attack_plans.py/option_scorer.py were only trusted
after head-to-head validation against v1). Neither exists yet. Shipping the
ranking function without that validation would repeat exactly the mistake
this project's whole v1->v2 audit process exists to catch: an unvalidated
change to real decision logic. See README.md's Discussion section for the
honest "shipped vs. explored" split.

What IS confirmed (via tests/test_lookahead.py, against the real engine):
  - search_begin() accepts a real observation + a determinization of every
    hidden zone (your remaining deck, both prize piles, opponent's hand),
    each supplied as REAL, valid card IDs matching the exact remaining count
    -- filler IDs of 0 or mismatched lengths are rejected by the engine
    ("Invalid Card ID" / count-mismatch errors), which is itself useful,
    previously-undocumented information about the real API's contract.
  - search_step() genuinely advances a hypothetical game from that
    determinized state using a chosen option index, and returns a real next
    Observation (or a real terminal result).
  - search_end() releases the search cleanly and self-play can continue
    normally afterward on the SAME live battle_ptr.

Belief-state honesty: `default_determinization()` below fills every hidden
zone by sampling from OUR OWN known deck's card pool as a generic prior --
not a real particle filter over a modeled opponent decklist (there is no
real opponent decklist to sample from at inference; see
belief/energy_density.py for the same honesty note applied to the simpler
Energy-counting heuristic). Pass a different `card_pool` to determinize
against a better guess (e.g. informed by belief.energy_density) once one
exists.

v4 update: that "once one exists" is now `belief_informed_determinization()`
below -- the same generic card_pool, but the opponent's hidden zones are
sampled with the Energy-fraction bias from an `EnergyDensityBelief` instead
of uniformly. It is still the same honest thing, just weighted: a density
prior over a generic pool, not a sampled real decklist.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


def default_determinization(obs, card_pool: list[int], rng: random.Random | None = None) -> dict:
    """Build valid (engine-accepted) filler contents for every hidden zone at
    the current observation, sampled from `card_pool` (defaults to the
    caller's own known deck elsewhere). Returns the exact kwargs
    search_begin() expects besides `agent_observation`."""
    rng = rng or random.Random()
    current = obs.current
    my_index = current.yourIndex
    my_state = current.players[my_index]
    op_state = current.players[1 - my_index]

    def sample(n: int) -> list[int]:
        if n <= 0:
            return []
        return [rng.choice(card_pool) for _ in range(n)]

    op_active = op_state.active[0] if op_state.active else None
    opponent_active_guess = [] if op_active is not None else sample(1)

    return dict(
        your_deck=sample(getattr(my_state, "deckCount", 0)),
        your_prize=sample(len(my_state.prize)),
        opponent_deck=sample(getattr(op_state, "deckCount", 0)),
        opponent_prize=sample(len(op_state.prize)),
        opponent_hand=sample(getattr(op_state, "handCount", 0)),
        opponent_active=opponent_active_guess,
    )


def _split_pool_by_energy(card_pool: list[int], card_table: dict) -> tuple[list[int], list[int]]:
    from ..belief.energy_density import is_energy_card

    energy_pool = [c for c in card_pool if is_energy_card(c, card_table)]
    nonenergy_pool = [c for c in card_pool if not is_energy_card(c, card_table)]
    return energy_pool, nonenergy_pool


def belief_informed_sample(n: int, card_pool: list[int], card_table: dict,
                            target_density: float, rng: random.Random) -> list[int]:
    """Sample `n` cards from `card_pool`, but instead of drawing uniformly
    across the whole pool, draw each card Energy-or-not by a coin weighted
    toward `target_density` (typically belief.EnergyDensityBelief.density()),
    then pick uniformly within whichever half was chosen. Falls back to plain
    uniform sampling if `card_pool` has no cards of one kind to draw from (the
    bias has nothing to bias with)."""
    if n <= 0:
        return []
    energy_pool, nonenergy_pool = _split_pool_by_energy(card_pool, card_table)
    if not energy_pool or not nonenergy_pool:
        return [rng.choice(card_pool) for _ in range(n)]
    out = []
    for _ in range(n):
        if rng.random() < target_density:
            out.append(rng.choice(energy_pool))
        else:
            out.append(rng.choice(nonenergy_pool))
    return out


def belief_informed_determinization(obs, card_pool: list[int], card_table: dict,
                                     belief, rng: random.Random | None = None) -> dict:
    """Same contract as `default_determinization()`, but the OPPONENT's hidden
    zones (hand/deck/prize) are sampled with `belief_informed_sample()` using
    `belief.density(card_table)` as the target Energy fraction, instead of
    uniformly across `card_pool`. This is the concrete integration point
    between belief/energy_density.py's density prior and the search layer's
    determinization -- previously the two v3 modules existed side by side
    with no code path connecting them.

    Our OWN hidden zones (your_deck/your_prize) are left at uniform sampling
    from `card_pool`: that's already the best obtainable prior for unseen
    cards in our own known deck (order is hidden, composition isn't), and the
    belief model exists specifically to reason about the OPPONENT's hidden
    zone, so biasing our own would misapply it.

    `belief`: an `EnergyDensityBelief` instance the caller has already
    `observe()`-d with the opponent's currently-visible cards this game.
    """
    rng = rng or random.Random()
    current = obs.current
    my_index = current.yourIndex
    my_state = current.players[my_index]
    op_state = current.players[1 - my_index]

    density = belief.density(card_table)

    def uniform(n: int) -> list[int]:
        if n <= 0:
            return []
        return [rng.choice(card_pool) for _ in range(n)]

    def biased(n: int) -> list[int]:
        return belief_informed_sample(n, card_pool, card_table, density, rng)

    op_active = op_state.active[0] if op_state.active else None
    opponent_active_guess = [] if op_active is not None else uniform(1)

    return dict(
        your_deck=uniform(getattr(my_state, "deckCount", 0)),
        your_prize=uniform(len(my_state.prize)),
        opponent_deck=biased(getattr(op_state, "deckCount", 0)),
        opponent_prize=biased(len(op_state.prize)),
        opponent_hand=biased(getattr(op_state, "handCount", 0)),
        opponent_active=opponent_active_guess,
    )


@dataclass
class ProbeResult:
    """What one search_begin -> search_step -> search_end round-trip produced."""
    ok: bool
    error: str | None = None
    result_after_step: int | None = None  # -1 if still ongoing, 0/1/2 if the probe ended the game
    next_context: int | None = None
    next_option_count: int | None = None


def probe_one_step(obs, choice: list[int], card_pool: list[int],
                    rng: random.Random | None = None) -> ProbeResult:
    """Determinize the hidden zones, start a real search, take exactly one
    real step with `choice` (the same [index,...] format agent() returns),
    and report what happened. Always releases the search (search_end) before
    returning, even on error, so it never leaks state into the live battle.

    Requires the real cg engine (imports cg.api lazily so this module can
    still be imported -- just not called -- without it).
    """
    from cg.api import search_begin, search_step, search_end

    try:
        det = default_determinization(obs, card_pool, rng)
        state = search_begin(obs, **det)
    except Exception as e:  # noqa: BLE001 -- surface any engine rejection as data, not a crash
        return ProbeResult(ok=False, error=f"{type(e).__name__}: {e}")

    try:
        next_state = search_step(state.searchId, choice)
    except Exception as e:  # noqa: BLE001
        return ProbeResult(ok=False, error=f"{type(e).__name__}: {e}")
    finally:
        try:
            search_end()
        except Exception:
            pass

    next_obs = next_state.observation
    result = next_obs.current.result if next_obs is not None else None
    next_sel = next_obs.select if next_obs is not None else None
    return ProbeResult(
        ok=True,
        result_after_step=result,
        next_context=(next_sel.context if next_sel is not None else None),
        next_option_count=(len(next_sel.option) if next_sel is not None else None),
    )

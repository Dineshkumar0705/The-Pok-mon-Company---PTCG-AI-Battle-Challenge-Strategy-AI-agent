"""Thin agent entrypoint — wires together card_data, deck_loading, attack_plans,
and scoring/option_scorer. Same decisions as v1 main.py's agent(); the only
difference is every piece is now an importable, independently testable
function instead of one 300-line closure over module globals.

Validated behavior-identical to v1 by tests/test_agent_matches_legacy.py,
which runs both through the real cg engine on identical seeded games.

v4: `build_agent()` gained an opt-in `search_config` parameter (search/
expectimax.py's L1 expectimax, gated by config/search_config.yaml). It
defaults to `None`, which loads the shipped config file -- and that file
ships with `enabled: false` -- so the decision path here is unchanged from
v1/v2 unless a caller explicitly turns search on. See
tests/test_expectimax_matches_heuristic_at_depth_zero.py and
tests/test_agent_matches_legacy.py, both of which assert this stays true.
"""
from __future__ import annotations

from collections import defaultdict

try:
    from cg.api import AreaType, OptionType, SelectContext, to_observation_class
    _ENGINE_AVAILABLE = True
except ImportError:
    from .mock_engine import AreaType, OptionType, SelectContext  # type: ignore
    _ENGINE_AVAILABLE = False

    def to_observation_class(obs):  # type: ignore
        return obs

from .card_data import load_card_table
from .deck_loading import load_deck
from .attack_plans import AttackPlan, build_attack_plan, relicanth_on_bench
from .scoring.damage import opp_incoming_damage
from .scoring.option_scorer import TurnContext, score_options, Basic_Metal_Energy as _BME
from .belief.energy_density import EnergyDensityBelief
from .search.expectimax import ExpectimaxConfig, rank_attack_candidates
from .search.transposition_table import TranspositionTable


def build_agent(deck: list[int], search_config: ExpectimaxConfig | None = None,
                 plan_stability_enabled: bool = True):
    """Return an `agent(obs_dict) -> list[int]` closure bound to `deck` and the
    engine's real card/attack tables (loaded once, not per-call).

    `search_config`: v4's opt-in L1 expectimax layer. `None` (the default)
    loads config/search_config.yaml, which ships with `enabled: false` --
    pass `ExpectimaxConfig(enabled=True, depth=...)` explicitly (as
    scripts/ab_test_search_vs_heuristic.py does) to turn it on. Whenever
    search is disabled or depth<=0, `rank_attack_candidates()` returns the
    heuristic scores byte-identical to before this parameter existed --
    see tests/test_expectimax_matches_heuristic_at_depth_zero.py.

    `plan_stability_enabled` (v7, docs/v7-architecture.md):
    ============================================================
    ALL-ON OVERRIDE (requested explicitly, 2026-09-11): default flipped
    True -- was False. Real A/B result (scripts/ab_test_plan_stability.py)
    was a NULL, not a win: this bonus makes no measured difference to win
    rate, it just changes which attacker gets picked on some ties. Flip
    this back to `False` to restore the shipped, validated default.
    ============================================================
    When False, `state["last_committed_attacker"]` is
    never updated past its initial -1, which is a guaranteed no-op in
    `attack_plans.py`'s PLAN_STABILITY_BONUS check -- so that call stays
    byte-identical to pre-v7 behavior. This was found the hard
    way: an EARLIER version of this feature updated that state
    unconditionally, and a real self-play parity run against v1
    (tests/test_agent_matches_legacy.py) caught a real divergence from it
    (1/976 real decisions) -- v1 has no such bonus, so it's not a
    "correctness fix" like v6's Cornerstone Ogerpon threat (grounded in
    printed card text); it's a genuinely new heuristic change, and this
    project's own rule is that nothing like that ships as the default
    until it wins a real head-to-head A/B, same as v4/v5's search layer.
    See `scripts/ab_test_plan_stability.py` for that result. Defaulting it
    True here means `tests/test_agent_matches_legacy.py` is EXPECTED to
    start failing -- that's the parity gate correctly noticing the change.
    """
    card_table, attack_table, source = load_card_table(prefer_engine=True)
    if source != "engine":
        raise RuntimeError(
            "build_agent() requires the live cg engine for card_table/attack_table "
            "(attackId semantics aren't reconstructible from the CSV fallback). "
            "Use card_data.load_card_table(prefer_engine=False) directly only for "
            "offline analysis that doesn't need engine-exact attack IDs."
        )

    if search_config is None:
        from .search.config_loader import load_search_config
        search_config = load_search_config()

    state = {
        "plan": AttackPlan(),
        "pre_turn": 0,
        "belief": EnergyDensityBelief(),
        "ttable": TranspositionTable(max_entries=search_config.transposition_table_size),
        "last_search_telemetry": None,
        "last_committed_attacker": -1,  # v7: plan-stability -- see attack_plans.py
    }

    def agent(obs_dict):
        obs = to_observation_class(obs_dict)
        if obs.select is None:
            return deck

        current = obs.current
        select = obs.select
        context = select.context
        my_index = current.yourIndex
        my_state = current.players[my_index]
        op_state = current.players[1 - my_index]

        if state["pre_turn"] != current.turn:
            # v7: capture the just-ended turn's committed attacker BEFORE
            # resetting -- this is what carries plan stability across the
            # turn boundary that already clears `plan` itself. Gated by
            # plan_stability_enabled (see build_agent()'s docstring for why
            # this must stay opt-in): when disabled, last_committed_attacker
            # stays -1 forever, a guaranteed no-op.
            if plan_stability_enabled and state["plan"].attacker >= 0:
                state["last_committed_attacker"] = state["plan"].attacker
            state["pre_turn"] = current.turn
            state["plan"] = AttackPlan()
            state["ttable"].clear()  # a new turn can't transpose with the last one
        plan = state["plan"]

        field_counts = defaultdict(int)
        hand_counts = defaultdict(int)
        discard_counts = defaultdict(int)
        for c in list(my_state.active) + list(my_state.bench):
            if c is None:
                continue
            field_counts[c.id] += 1
        for c in (my_state.hand or []):
            hand_counts[c.id] += 1
        for c in my_state.discard:
            discard_counts[c.id] += 1

        stadium_id = current.stadium[0].id if current.stadium else 0
        my_active = my_state.active[0] if my_state.active else None
        op_active = op_state.active[0] if op_state.active else None
        op_hand_count = getattr(op_state, "handCount", len(getattr(op_state, "hand", None) or []))

        relicanth_present = relicanth_on_bench(my_state.bench)
        metal_in_discard = discard_counts[_BME]

        incoming = opp_incoming_damage(op_active, my_active, attack_table, card_table,
                                        stadium_id, op_hand_count)
        active_in_danger = my_active is not None and incoming >= my_active.hp

        # v4: keep the opponent belief model current with everything of
        # theirs that's visible right now (discard + battlefield). Cheap,
        # and harmless even when search is disabled -- observe() only
        # updates internal state, it never changes any decision by itself.
        op_visible_ids = [c.id for c in op_state.discard] + [
            c.id for c in ([op_state.active[0]] if op_state.active else []) + list(op_state.bench) if c is not None
        ]
        state["belief"].observe(op_visible_ids, card_table)

        can_attack = can_switch = can_op_switch = False
        if context == SelectContext.MAIN:
            for o in select.option:
                if o.type == OptionType.PLAY:
                    c = my_state.hand[o.index] if my_state.hand else None
                    if c is not None:
                        if c.id == 1123:  # Switch_Card
                            can_switch = True
                        elif c.id == 1182:  # Boss_Orders
                            can_op_switch = True
                elif o.type == OptionType.RETREAT:
                    can_switch = True
                elif o.type == OptionType.ATTACK:
                    can_attack = True

            my_cards = [my_state.active[0] if my_state.active else None] + list(my_state.bench)
            op_cards = [op_state.active[0] if op_state.active else None] + list(op_state.bench)
            state["plan"] = build_attack_plan(
                my_cards, op_cards, card_table, attack_table,
                can_switch, can_op_switch, relicanth_present,
                hand_counts[_BME], current.energyAttached, current.turn,
                op_remaining_prizes=len(op_state.prize),
                stadium_id=stadium_id,
                previous_plan=state["plan"],
                last_committed_attacker=state["last_committed_attacker"],
            )
            plan = state["plan"]

        ctx = TurnContext(
            obs=obs, card_table=card_table, attack_table=attack_table, plan=plan,
            field_counts=field_counts, hand_counts=hand_counts, discard_counts=discard_counts,
            stadium_id=stadium_id, my_active=my_active, active_in_danger=active_in_danger,
            relicanth_present=relicanth_present, metal_in_discard=metal_in_discard,
            my_index=my_index, op_state=op_state, my_state=my_state,
            context=context, area_type=AreaType, select_context_type=SelectContext,
        )
        scores = score_options(select.option, ctx, OptionType)

        if search_config.enabled and context == SelectContext.MAIN and can_attack:
            scores, telemetry = rank_attack_candidates(
                obs=obs, select=select, baseline_scores=scores,
                card_table=card_table, attack_table=attack_table, card_pool=deck,
                option_type=OptionType, select_context_type=SelectContext, area_type=AreaType,
                config=search_config, ttable=state["ttable"], belief=state["belief"],
            )
            state["last_search_telemetry"] = telemetry

        desc = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
        return desc[: select.maxCount]

    # Introspection hooks for callers that want to observe (never change)
    # search behavior -- scripts/ab_test_search_vs_heuristic.py uses these to
    # report real telemetry instead of asserting search helped without proof.
    agent.get_search_telemetry = lambda: state["last_search_telemetry"]
    agent.get_transposition_table = lambda: state["ttable"]
    agent.search_config = search_config

    return agent


def load_agent_and_deck(deck_path: str = "deck.csv",
                         dataset_glob: str = "/kaggle/input/**/deck.csv"):
    """Convenience entrypoint mirroring v1's module-level setup: load the deck
    (with the validated override guard), build the agent, return both."""
    inline_deck = [int(x) for x in open(deck_path).read().split() if x.strip()]
    deck, source = load_deck(inline_deck, dataset_glob=dataset_glob)
    return build_agent(deck), deck, source

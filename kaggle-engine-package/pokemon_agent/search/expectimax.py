"""L1 -- shallow expectimax over the existing scorers, wired for real against
the real engine's search_begin/search_step/search_end (lookahead.py's
validated plumbing), not a stub.

Scope, deliberately narrow: this module only re-ranks ATTACK-type options
within a MAIN-context decision. That's the specific decision v1/v2's
one-ply-only scoring (`scoring/option_scorer.py`) can't reason about --
"if I attack now, does the opponent have lethal back?" -- and it's also, by
construction, the only place the existing score bands make a search bonus
able to change the outcome: PLAY/ATTACH/EVOLVE options score 8000-30000 in
option_scorer.py, dwarfing ATTACK's 1000-1300, so in any MAIN select that
still has a playable card, the agent plays it first regardless of what this
module says. Only once a turn reaches the MAIN call where ATTACK/RETREAT are
the strongest remaining category does this module's re-ranking matter --
which is exactly the turn-ending "attack or not, and with what" decision it
targets. Nothing here overrides that scope; it adds a bounded, ATTACK-only
adjustment term to `option_scorer.score_options()`'s own output.

Leaf evaluation: `position_value()` reuses `scoring.pokemon_score.pokemon_score`
(already validated, already used for real target-priority decisions) as the
board-value function -- summed over each side's Active + Bench, HP-weighted --
rather than inventing a new evaluator. This is the "wrap the existing scorers
as the leaf-value function" design from the v3 upgrade doc, now actually
built.

Depth-2 "opponent's best expected counter": there is no separate opponent
model. This module approximates the opponent's reply by applying the SAME
per-option heuristic (`option_scorer.score_options()`, with a throwaway
default AttackPlan -- no cross-call plan-stickiness inside a hypothetical
branch) to whichever side the engine says is choosing next, for a bounded
number of `search_step()` calls. This is a real limitation, stated plainly
here rather than sold as an opponent model: self-play-heuristic-as-proxy is
a documented, common shortcut (also how the depth-2 discount is framed in
the v3 upgrade doc's PokeChamp citation), not full adversarial search.

Safety: every real-engine call in this module is wrapped so a failure (bad
determinization, an engine rejection, an unexpected observation shape)
degrades to "return the baseline heuristic scores unchanged" rather than
raising -- an agent that can't search is still the validated v1/v2 agent,
never a crash. `search_end()` is always called in a `finally` block once a
root search is opened, matching lookahead.py's existing pattern, so the live
battle_ptr this decision came from is never left in a searched-into state.

Validated: `tests/test_expectimax_matches_heuristic_at_depth_zero.py` pins
depth=0 (or search_enabled=False) to byte-identical output to
`option_scorer.score_options()` -- the regression gate named in the v3
upgrade doc's build-order table. `tests/test_expectimax_real_engine.py`
exercises this against the real engine (skipped if unavailable).
`scripts/ab_test_search_vs_heuristic.py` is the actual decision gate for
whether this ships wired into `agent.py` by default -- see that script and
`docs/v4-architecture.md` for the real, measured result.

v5 addition: the leaf evaluator is now swappable. `config.leaf_value_mode`
picks between `"heuristic"` (default, `position_value()` -- unchanged from
v4) and `"learned"` (`learning.leaf_value.LearnedLeafValue`, a model trained
on real self-play outcomes -- see `docs/v5-architecture.md` and
`scripts/train_leaf_value_model.py`). Both evaluators are normalized to
[-1, 1] before the ATTACK-score bonus is computed, so the bonus's scale
(`SEARCH_SCORE_SCALE`) means the same thing regardless of which leaf
evaluator produced it. `"learned"` fails closed to `"heuristic"` for this
one decision if the model file is missing or fails to load -- never a crash,
same safety rule as every other engine-call failure in this module.

v7 additions (docs/v7-architecture.md):
- `config.policy_top_k`: an optional branch cap. When set, only the top-K
  ATTACK candidates BY THE EXISTING HEURISTIC'S OWN BASELINE SCORE are
  actually searched (real engine calls spent on the candidates the
  heuristic itself already thinks are best); the rest keep their baseline
  score untouched. This is a real, cheap "policy prior" using data this
  module already has (`baseline_scores`) rather than a new trained policy
  network -- the AlphaZero-family idea (search only where the policy says
  to look), scaled to what this project can build and validate for real.
  `None` (default) searches every candidate, byte-identical to v4/v5.
- `config.depth` now generalizes past 2: `_fast_forward()` takes a
  `my_turn_crossings_to_stop_at` count instead of stopping the first time
  it sees `my_index`'s turn. depth=2 stops at 1 crossing (identical to
  v4/v5's behavior -- the opponent's intervening turn, fast-forwarded, then
  evaluate). depth=3+ keeps going: it takes a real (proxy-heuristic) choice
  on OUR OWN follow-up turn too, then fast-forwards the opponent's NEXT
  turn as well, before evaluating -- a genuine extra real round, not a
  relabeled depth-2 search. Still the same stated limitation as before:
  both sides are approximated by the same per-option heuristic proxy, not a
  real adversarial opponent model.
- The leaf-evaluation block (`_evaluate()` and its cache lookup/store) is
  now wrapped in its own try/except, falling back to the baseline score for
  that one candidate and incrementing `telemetry.leaf_eval_errors` --
  closing a real gap found while building v7: previously, an exception
  raised by a leaf evaluator (a corrupted model file passing `_load_learned_model`'s
  load check but failing at `.predict()`, or a future evaluator hitting an
  unexpected observation shape) would propagate out of
  `rank_attack_candidates()` uncaught, contradicting this module's own
  stated fail-closed guarantee. Every other engine-call failure here was
  already wrapped; this one wasn't. Fixed as part of v7 rather than filed
  as a separate ticket, since v7's new GBT leaf evaluator (see
  `learning/leaf_value.py`) is exactly the kind of new code this gap could
  have bitten first.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Optional

from ..scoring.pokemon_score import pokemon_score
from .lookahead import belief_informed_determinization, default_determinization
from .transposition_table import TranspositionEntry, TranspositionTable, node_key

WIN_VALUE = 1_000_000.0
LOSS_VALUE = -1_000_000.0

# How strongly a search-derived value can move an ATTACK option's score,
# relative to option_scorer's own ATTACK band (1000 + up to a few hundred
# damage) and RETREAT's fixed 2000 -- large enough to flip "attack now" vs
# "retreat instead" or to reorder which attack, never large enough to beat a
# still-playable Trainer/Supporter (8000+). This is a scaling CHOICE, not a
# fit to data -- stated plainly rather than implied to be tuned.
SEARCH_SCORE_SCALE = 900.0
SEARCH_SCORE_NORMALIZER = 3000.0

DEFAULT_MAX_BRANCH_STEPS = 8


@dataclass
class ExpectimaxConfig:
    """Data, not hardcoded -- loaded from config/search_config.yaml by
    `config_loader.py`. Every field has a safe, inert default
    (depth=0 means "search never actually runs", matching v1/v2 behavior)."""

    enabled: bool = False
    depth: int = 0
    max_branch_steps: int = DEFAULT_MAX_BRANCH_STEPS
    transposition_table_size: int = 20_000
    belief_informed_determinization: bool = True
    leaf_value_mode: str = "heuristic"  # "heuristic" | "learned" -- v5
    leaf_value_model_path: Optional[str] = None  # required when leaf_value_mode == "learned"
    policy_top_k: Optional[int] = None  # v7: cap search to the top-K candidates by baseline score; None = search all (v4/v5 behavior)


@dataclass
class SearchTelemetry:
    """Real counters from one `rank_attack_candidates()` call, surfaced so
    callers (the A/B script, tests) can report what actually happened instead
    of assuming search ran. Never used to change scoring -- observation only."""

    attempted: bool = False
    candidates_considered: int = 0
    candidates_evaluated: int = 0
    engine_calls: int = 0
    engine_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    fell_back_to_heuristic: bool = False
    fallback_reason: Optional[str] = None
    leaf_value_mode_used: str = "heuristic"  # v5: "heuristic" or "learned", whichever actually evaluated leaves
    learned_model_load_failed: bool = False
    candidates_pruned_by_policy: int = 0  # v7: candidates skipped by policy_top_k, kept at baseline score
    leaf_eval_errors: int = 0  # v7: leaf-evaluation exceptions caught, candidate fell back to baseline for that one index


def position_value(obs: Any, card_table: dict, my_index: int) -> float:
    """HP-weighted board value from `my_index`'s perspective: sum of
    pokemon_score() over my Active+Bench minus the same over the opponent's,
    each individual Pokemon's score weighted by its remaining HP fraction
    (a nearly-dead threat is worth less to hold onto, and a nearly-dead
    opponent Pokemon is worth more to finish). Terminal states short-circuit
    to a fixed win/loss value so a lethal line always dominates any material
    swing that falls short of it.
    """
    current = obs.current
    result = getattr(current, "result", -1)
    if result is not None and result in (0, 1):
        return WIN_VALUE if result == my_index else LOSS_VALUE
    if result == 2:
        return 0.0

    def side_value(pi: int) -> float:
        ps = current.players[pi]
        total = 0.0
        for p in ([ps.active[0]] if ps.active else []) + list(ps.bench):
            if p is None:
                continue
            hp = getattr(p, "hp", 0)
            max_hp = getattr(p, "maxHp", hp) or 1
            frac = max(0.0, min(1.0, hp / max_hp))
            total += pokemon_score(p, card_table) * (0.4 + 0.6 * frac)
        return total

    return side_value(my_index) - side_value(1 - my_index)


def position_value_normalized(obs: Any, card_table: dict, my_index: int) -> float:
    """position_value() squashed to [-1, 1] via tanh, so it's directly
    comparable to learned_value_normalized() below regardless of which one a
    given ExpectimaxConfig picks."""
    raw = position_value(obs, card_table, my_index)
    return math.tanh(raw / SEARCH_SCORE_NORMALIZER)


_LEAF_MODEL_CACHE: dict = {}  # path -> LearnedLeafValue, process-lifetime cache (loading is not free)


def _load_learned_model(path: str):
    """Cached load of a LearnedLeafValue from disk. Returns None (never
    raises) if the path is missing or the file fails to load -- callers must
    treat None as "fall back to the heuristic evaluator for this decision,"
    matching every other engine-call failure's fail-open behavior in this
    module."""
    if path in _LEAF_MODEL_CACHE:
        return _LEAF_MODEL_CACHE[path]
    try:
        from ..learning.leaf_value import LearnedLeafValue
        model = LearnedLeafValue.load(path)
    except Exception:  # noqa: BLE001
        model = None
    _LEAF_MODEL_CACHE[path] = model
    return model


def learned_value_normalized(obs: Any, card_table: dict, my_index: int, model: Any) -> float:
    """model.predict() is already a probability in [0, 1] -- rescale to
    [-1, 1] (0.5 win probability -> 0.0, matching position_value_normalized()'s
    "even" reading of 0.0) so the two evaluators share one bonus scale.

    v7: a model can now be trained on either v5's original feature shape
    (`memory.featurize.FEATURE_NAMES`) or v7's richer one
    (`FEATURE_NAMES_V7`, see that module's docstring for why -- the
    Suphx-oracle idea was found genuinely blocked by the real engine, so
    this is the pivot: one new legal feature + a stronger model class, not
    privileged state). Every `LearnedLeafValue.train()`/`save()` call
    records which feature set it used as `model.feature_names`; this reads
    that off the loaded model itself rather than adding a new
    `ExpectimaxConfig` knob, so an existing v5 model (or any caller not
    passing a v7 model) is featurized exactly as before -- zero behavior
    change unless the model on disk actually asks for the v7 shape.
    """
    from ..memory.featurize import FEATURE_NAMES_V7, featurize_observation, featurize_observation_v7

    current = obs.current
    result = getattr(current, "result", -1)
    if result is not None and result in (0, 1):
        return 1.0 if result == my_index else -1.0
    if result == 2:
        return 0.0
    if getattr(model, "feature_names", None) == FEATURE_NAMES_V7:
        features = featurize_observation_v7(obs, card_table, my_index)
    else:
        features = featurize_observation(obs, card_table, my_index)
    proba = model.predict(features)
    return 2.0 * proba - 1.0


def _quick_choice(obs: Any, card_table: dict, attack_table: dict,
                   option_type: Any, select_context_type: Any, area_type: Any) -> list[int]:
    """Self-contained per-option heuristic chooser for a hypothetical branch
    node -- same dispatch as the real agent (`scoring.option_scorer.score_options`)
    but with a throwaway default AttackPlan (no previous_plan threading,
    since a hypothetical branch has no real "rest of this turn" to be
    consistent with). Used only inside search's own fast-forward simulation,
    never for the real top-level decision, which keeps using the full,
    plan-threaded `agent.py` logic exactly as before.
    """
    from collections import defaultdict

    from ..attack_plans import AttackPlan
    from ..scoring.damage import opp_incoming_damage
    from ..scoring.option_scorer import Basic_Metal_Energy, TurnContext, score_options

    current = obs.current
    select = obs.select
    my_index = current.yourIndex
    my_state = current.players[my_index]
    op_state = current.players[1 - my_index]

    field_counts: dict = defaultdict(int)
    hand_counts: dict = defaultdict(int)
    discard_counts: dict = defaultdict(int)
    for c in list(my_state.active or []) + list(my_state.bench or []):
        if c is not None:
            field_counts[c.id] += 1
    for c in (my_state.hand or []):
        hand_counts[c.id] += 1
    for c in (my_state.discard or []):
        discard_counts[c.id] += 1

    stadium_id = current.stadium[0].id if current.stadium else 0
    my_active = my_state.active[0] if my_state.active else None
    op_active = op_state.active[0] if op_state.active else None
    op_hand_count = getattr(op_state, "handCount", len(getattr(op_state, "hand", None) or []))

    incoming = opp_incoming_damage(op_active, my_active, attack_table, card_table,
                                    stadium_id, op_hand_count)
    active_in_danger = my_active is not None and incoming >= my_active.hp

    ctx = TurnContext(
        obs=obs, card_table=card_table, attack_table=attack_table, plan=AttackPlan(),
        field_counts=field_counts, hand_counts=hand_counts, discard_counts=discard_counts,
        stadium_id=stadium_id, my_active=my_active, active_in_danger=active_in_danger,
        relicanth_present=any(c is not None and c.id == 57 for c in (my_state.bench or [])),
        metal_in_discard=discard_counts[Basic_Metal_Energy],
        my_index=my_index, op_state=op_state, my_state=my_state,
        context=select.context, area_type=area_type, select_context_type=select_context_type,
    )
    scores = score_options(select.option, ctx, option_type)
    desc = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
    return desc[: select.maxCount] if select.maxCount > 0 else desc[:1]


def _fast_forward(search_state: Any, my_index: int, card_table: dict, attack_table: dict,
                   option_type: Any, select_context_type: Any, area_type: Any,
                   start_turn: int, max_steps: int, telemetry: SearchTelemetry,
                   my_turn_crossings_to_stop_at: int = 1) -> Any:
    """From `search_state` (already one real ply deep), keep taking real
    `search_step()`s -- whoever's turn it is, via `_quick_choice()` -- until
    either: the game ends, `max_steps` is exhausted, or control has returned
    to `my_index` on a new turn number `my_turn_crossings_to_stop_at` times.

    `my_turn_crossings_to_stop_at=1` (v4/v5's only behavior, still the
    default) stops the FIRST time it's `my_index`'s turn again, without
    acting there -- "fast-forward through the opponent's one intervening
    turn, then evaluate." v7's depth>=3 passes a larger count: each
    additional crossing means the fast-forward takes one more real
    (proxy-heuristic) choice on OUR OWN turn before continuing to fast-
    forward the opponent's NEXT turn too -- a genuine extra real round of
    lookahead, not a relabeled depth-2 search. Any engine error simply stops
    the fast-forward early and returns the last good state -- a truncated
    lookahead is still a valid (if shallower) evaluation point.
    """
    from cg.api import search_step

    state = search_state
    my_turn_crossings = 0
    for _ in range(max_steps):
        obs = state.observation
        if obs is None or obs.select is None:
            break
        current = obs.current
        if getattr(current, "result", -1) != -1:
            break
        if current.yourIndex == my_index and current.turn != start_turn:
            my_turn_crossings += 1
            if my_turn_crossings >= my_turn_crossings_to_stop_at:
                break
        try:
            choice = _quick_choice(obs, card_table, attack_table, option_type,
                                    select_context_type, area_type)
            telemetry.engine_calls += 1
            state = search_step(state.searchId, choice)
        except Exception:  # noqa: BLE001 -- truncate, don't propagate
            telemetry.engine_errors += 1
            break
    return state


def rank_attack_candidates(
    obs: Any,
    select: Any,
    baseline_scores: list[int],
    card_table: dict,
    attack_table: dict,
    card_pool: list[int],
    option_type: Any,
    select_context_type: Any,
    area_type: Any,
    config: ExpectimaxConfig,
    ttable: Optional[TranspositionTable] = None,
    belief: Optional[Any] = None,
    rng: Optional[random.Random] = None,
) -> tuple[list[int], SearchTelemetry]:
    """Return (scores, telemetry). `scores` is `baseline_scores` with ATTACK-
    option entries adjusted by a bounded expectimax term; every other index
    is returned byte-identical to `baseline_scores`. Falls back to
    `baseline_scores` unchanged (with telemetry explaining why) whenever
    search is disabled, there's nothing to search over, or the real engine
    rejects the determinization/step -- see module docstring.
    """
    telemetry = SearchTelemetry()
    scores = list(baseline_scores)

    if not config.enabled or config.depth <= 0:
        telemetry.fallback_reason = "search disabled or depth 0"
        return scores, telemetry

    attack_indices = [i for i, o in enumerate(select.option) if o.type == option_type.ATTACK]
    telemetry.candidates_considered = len(attack_indices)
    if not attack_indices:
        telemetry.fallback_reason = "no ATTACK option in this select"
        return scores, telemetry

    # v7: policy_top_k -- spend real engine calls only on the candidates the
    # existing heuristic already ranks highest (a cheap, real "policy prior"
    # built from data this module already has, not a new trained network).
    # Un-searched candidates simply keep their baseline score, exactly as if
    # search were never invoked for them.
    if config.policy_top_k is not None and config.policy_top_k > 0 and len(attack_indices) > config.policy_top_k:
        ranked = sorted(attack_indices, key=lambda i: baseline_scores[i], reverse=True)
        attack_indices = ranked[: config.policy_top_k]
        telemetry.candidates_pruned_by_policy = len(ranked) - len(attack_indices)

    try:
        from cg.api import search_begin, search_end, search_step
    except ImportError:
        telemetry.fell_back_to_heuristic = True
        telemetry.fallback_reason = "real cg engine not importable"
        return scores, telemetry

    telemetry.attempted = True
    rng = rng or random.Random()
    my_index = obs.current.yourIndex
    start_turn = obs.current.turn

    learned_model = None
    if config.leaf_value_mode == "learned":
        if config.leaf_value_model_path:
            learned_model = _load_learned_model(config.leaf_value_model_path)
        if learned_model is None:
            telemetry.learned_model_load_failed = True
            # Fails closed to the heuristic evaluator for THIS decision only --
            # never a crash, never a silent switch back to depth-0 behavior.
    telemetry.leaf_value_mode_used = "learned" if learned_model is not None else "heuristic"

    if config.belief_informed_determinization and belief is not None:
        det = belief_informed_determinization(obs, card_pool, card_table, belief, rng)
    else:
        det = default_determinization(obs, card_pool, rng)

    try:
        root_state = search_begin(obs, **det)
        telemetry.engine_calls += 1
    except Exception as e:  # noqa: BLE001
        telemetry.engine_errors += 1
        telemetry.fell_back_to_heuristic = True
        telemetry.fallback_reason = f"search_begin failed: {type(e).__name__}: {e}"
        return scores, telemetry

    try:
        for idx in attack_indices:
            try:
                child = search_step(root_state.searchId, [idx])
                telemetry.engine_calls += 1
            except Exception:  # noqa: BLE001
                telemetry.engine_errors += 1
                continue

            if config.depth >= 2:
                # v7: depth generalizes past 2 -- each extra depth level is
                # one more real "my turn, then opponent's next turn"
                # crossing, not a relabeled depth-2 search. depth=2 passes
                # crossings=1, identical to v4/v5.
                child = _fast_forward(child, my_index, card_table, attack_table,
                                       option_type, select_context_type, area_type,
                                       start_turn, config.max_branch_steps, telemetry,
                                       my_turn_crossings_to_stop_at=config.depth - 1)

            leaf_obs = child.observation
            if leaf_obs is None:
                continue

            def _evaluate(o):
                if learned_model is not None:
                    return learned_value_normalized(o, card_table, my_index, learned_model)
                return position_value_normalized(o, card_table, my_index)

            # v7: the leaf-evaluation block is now its own try/except -- a
            # real gap found while building v7 (see module docstring): this
            # block used to be unguarded, so any exception here (a corrupted
            # model that loads but fails at .predict(), an evaluator hitting
            # an unexpected observation shape) would propagate out of
            # rank_attack_candidates() uncaught, contradicting this module's
            # own fail-closed guarantee. Now it degrades to this ONE
            # candidate keeping its baseline score, same tier as a failed
            # search_step above.
            try:
                cache_key = None
                if ttable is not None:
                    try:
                        cache_key = node_key(leaf_obs)
                        cached = ttable.get(cache_key)
                    except Exception:  # noqa: BLE001 -- caching is an optimization, never fatal
                        cached = None
                        cache_key = None
                    if cached is not None:
                        telemetry.cache_hits += 1
                        normalized_value = cached.value
                    else:
                        telemetry.cache_misses += 1
                        normalized_value = _evaluate(leaf_obs)
                        if cache_key is not None:
                            ttable.put(cache_key, TranspositionEntry(value=normalized_value, depth_searched=config.depth))
                else:
                    normalized_value = _evaluate(leaf_obs)
            except Exception:  # noqa: BLE001 -- fail closed for this one candidate only
                telemetry.leaf_eval_errors += 1
                continue

            telemetry.candidates_evaluated += 1
            bonus = SEARCH_SCORE_SCALE * normalized_value
            scores[idx] = int(round(baseline_scores[idx] + bonus))
    finally:
        try:
            search_end()
        except Exception:  # noqa: BLE001 -- best-effort cleanup
            pass

    if telemetry.candidates_evaluated == 0:
        telemetry.fell_back_to_heuristic = True
        telemetry.fallback_reason = "every candidate step failed"

    return scores, telemetry

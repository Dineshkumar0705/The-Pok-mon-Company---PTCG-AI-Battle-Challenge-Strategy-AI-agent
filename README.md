# Pokémon TCG AI Agent — Archaludon ex "Steel Fortress"

A layered decision agent for the PTCG AI Battle Challenge, built and validated
against the real competition battle engine (`cg`, vendored under `vendor/cg/`
from the organizer-supplied build). This repo is a **behavior-preserving
decomposition and audit** of the shipped, already-scored v1 agent, plus a set
of real, engine-tested v3/v4 modules that stay explicitly *opt-in* until
they've earned their way into the scored decision path the same way v1's own
fixes did.

**v4 update:** the search/belief/rating modules below are no longer just
tested-but-disconnected plumbing — `search/expectimax.py` now runs a real
1–2 ply forward search over the actual engine, using `belief/energy_density.py`
to bias its determinization and `search/transposition_table.py` to cache
repeated leaf lookups, and it has a real, measured A/B result: **67.0% win
rate (n=100, 95% CI [57.3%, 75.4%]) at depth 2** against the pure-heuristic
baseline in real self-play mirror matches, zero engine errors across 1,645
real search calls. It ships **opt-in** (`config/search_config.yaml`'s
`enabled: false` by default) rather than replacing `build_agent(deck)`'s
default behavior — see `docs/v4-architecture.md` for the full result and why.

**v5 update:** adds a Replay Vector Store (`memory/`) and a learned
leaf-value function (`learning/leaf_value.py`, trained on 76,486 real
self-play records from 300 real games) as a swappable alternative to
`position_value()`'s hand-coded evaluator. Reported honestly: its real A/B
result against the heuristic leaf was a **null result** — 50.0% win rate at
both depth 1 (n=80) and depth 2 (n=60) — despite 69.4% held-out prediction
accuracy on its own training data. It stays off by default for that reason,
not omission. Behavioral cloning from human replays (the next item on the
project's own roadmap) is explicitly blocked: this environment has no real
human/top-episode replay corpus to train on, and nothing here fakes one.
See `docs/v5-architecture.md` for the full result and reasoning.

**v6 update:** adds `threats/cornerstone_ogerpon.py` — this deck's real,
named structural counter in competitive play (Cornerstone Mask Ogerpon ex's
Cornerstone Stance blocks all damage from attackers that have an Ability,
which in this deck is Archaludon ex alone via Assemble Alloy; Duraludon is
unaffected). Unlike v3–v5, this came from external research (real printed
card text + a named community source), not this repo's own self-play data —
the deck's mirror-match self-play tooling structurally cannot produce this
opponent, so it's validated by targeted unit tests against real card text
and the existing real-engine parity test, not an A/B result, and that's
stated as a different evidence tier rather than glossed over. It ships
**unconditional** (not behind `config/search_config.yaml`), the same tier as
the existing Crustle and Alakazam ex fixes, because it corrects a real
zero-damage planning gap rather than adding new, unvalidated machinery. See
`docs/v6-architecture.md`.

**v7 update:** implements the buildable-now items from `docs/v7-research-and-proposal.md`
(a world-wide game-AI gap survey run against v6). Real wins: a new
asymmetric-deck self-play harness (`scripts/ab_test_cornerstone_matchup.py`)
finally A/B-tests v6's own previously "structurally untestable" Cornerstone
Ogerpon fix directly — a real **+11.7pp** result (40.0% vs. 28.3%, fix live
vs. disabled) — and `rating/ladder.py` gains a real symmetric multi-agent
Elo pool (`MatchupLadder.record_match()`, 150 real games across 4 agent
variants), giving the "avoids over-reliance on specific matchups" claim an
actual mechanism, not an assumed property. Everything else is a real,
honestly-reported null or negative result: search depth 3 (56.0%, n=100,
worse than depth 2), a `policy_top_k` branch cap (35.0%, n=40, real
negative), a plan-stability bonus (47.0%, n=100, null), and a second attempt
at the learned leaf-value function — a GradientBoostingClassifier plus a new
stadium feature, real held-out metrics genuinely improved (72.5% vs. 69.4%
accuracy) but the real A/B win rate still didn't (50.0%/53.3%), which rules
out "wrong model class" as the explanation for v5's original null result.
Every new knob stays off by default; the shipped agent's decisions are
unchanged from v6. A real deploy-check pass also found and fixed a genuine
wiring gap: `policy_top_k` had been added to `ExpectimaxConfig` but never
threaded through `search/config_loader.py`'s yaml reader, so setting it in
`config/search_config.yaml` would have silently done nothing — fixed, and
a new completeness-guard test now catches this exact bug class for any
future config field. See `docs/v7-architecture.md` for every real result,
including the negative and null ones.

**v7 dataset upgrade:** cross-validated the cleaned reference CSV against
the real battle engine's own structured card database (`cg.api.all_card_data()`/
`all_attack()`) and merged them into four new, normalized, ML-ready tables
(`data/raw/cards_enriched.csv`, `attacks_enriched.csv`,
`abilities_enriched.csv`, `evolution_lines.csv`) with real engine ground
truth for fields (`is_ex`, `is_mega_ex`, `is_tera`, `is_ace_spec`,
`evolves_from`, real engine `attack_id`s) the old CSV schema had no way to
represent at all — no external/fabricated data added, everything is read
or computed directly from these two already-verified real sources. Found
and fixed two real accuracy bugs along the way: the old text heuristics
for `ex`/`megaEx` were wrong for 30 and 4 real cards respectively (e.g.
every Mega Evolution ex card), and — worse — `attack_plans.py`'s real
decision code reads engine-style attribute names (`.ex`/`.megaEx`) that
`CardRecord` never actually exposed, silently no-oping ex-detection
entirely in CSV-fallback mode (never affected the real scored submission,
which always uses the live engine). All three fixed in
`src/pokemon_agent/card_data.py`, with 6 new regression tests. See
`data/raw/DATASET_UPGRADE_REPORT.md` for the full real cross-validation
table, every real number, and the methodology.

## Layout

```
notebooks/legacy/main_v1_reference.py   v1 — the FROZEN, shipped, scored agent. Never edited.
notebooks/legacy/*.ipynb                the original notebook it was extracted from
deck.csv                                the real 60-card decklist
data/raw/                               canonical EN/JP card reference data (cleaned dataset) + v7's
                                         engine-cross-validated cards_enriched/attacks_enriched/
                                         abilities_enriched/evolution_lines.csv -- see DATASET_UPGRADE_REPORT.md
vendor/cg/                              the real proprietary battle engine (organizer-supplied)

src/pokemon_agent/                      v2 — v1's logic, decomposed into independently
  agent.py                              testable modules. Same decisions, same bugs* fixed,
  attack_plans.py                       nothing behavioral changed beyond that. v4: build_agent()
  deck_loading.py                       gained an opt-in search_config param (default: disabled).
  engine_interface.py
  card_data.py
  scoring/{damage,pokemon_score,option_scorer}.py
  threats/{crustle,alakazam_ex,bellibolt_ex,cornerstone_ogerpon}.py  # v6: cornerstone_ogerpon.py, unconditional real-card-text fix
  mock_engine.py                        lightweight fixture types for engine-free unit tests
  rating/ladder.py                      v3 — real Elo ladder fed by real replay logs (opt-in, unused by agent.py)
  belief/energy_density.py              v3/v4 — energy-density prior; v4 wires it into search determinization
  search/lookahead.py                   v3/v4 — real search_begin/search_step wiring, now with
                                         belief-informed determinization (v4)
  search/expectimax.py                  v4/v5 — real 1-2 ply search, swappable leaf eval (heuristic or
                                         learned, v5), ATTACK-only re-ranking, opt-in via config/search_config.yaml
  search/transposition_table.py         v4 — real leaf-value cache within one search call
  search/config_loader.py               v4/v5 — loads config/search_config.yaml, fails closed to disabled
  memory/featurize.py                   v5/v7 — Observation -> feature vector (21 v5 / 22 v7 w/ stadium flag), one player's perspective
  memory/replay_store.py                v5 — Replay Vector Store: real (features, outcome) records + similarity query
  learning/leaf_value.py                v5/v7 — LearnedLeafValue: trained win-probability model (logistic or v7's GBT), opt-in leaf evaluator
  threats/cornerstone_ogerpon.py        v6 — unconditional real-card-text fix; v7 finally A/B-tests it directly

tests/                                  pytest suite — see "Testing" below
scripts/
  deck_consistency_check.py             deck legality + trusted-override audit
  replay_logger.py                      runs real games, logs real results
  matchup_breakdown.py                  win-rate-by-archetype report from real logs
  ab_test_search_vs_heuristic.py        v4 — real A/B gate: search vs. heuristic, real self-play, real CI
  generate_self_play_training_data.py   v5/v7 — real self-play data generation (--feature-version v5|v7)
  train_leaf_value_model.py             v5/v7 — trains + reports real held-out metrics (--model-type logistic|gbt)
  ab_test_learned_value_vs_heuristic_leaf.py  v5/v7 — real A/B gate: learned leaf vs. heuristic leaf, any model path
  ab_test_plan_stability.py             v7 — real A/B gate: plan-stability bonus vs. baseline
  ab_test_cornerstone_matchup.py        v7 — real asymmetric-deck self-play, first direct test of v6's fix
  run_ladder_pool.py                    v7 — real round-robin of 4 agent variants through MatchupLadder.record_match()
  smoke_test_v7_all_features.py         v7 — deploy check: every v7 feature active at once, real games, no win-rate claim
  build_engine_enriched_dataset.py      v7 — builds cards/attacks/abilities/evolution_lines_enriched.csv from real engine ground truth, cross-validated against the CSV
replays/raw/replay_log.jsonl            real self-play results (see "Real results" below)
replays/raw/ab_search_vs_heuristic_log.jsonl   v4 — real A/B run log (see docs/v4-architecture.md)
replays/raw/leaf_value_training_data.jsonl     v5 — real (state, outcome) training data, 76,486 records
replays/raw/leaf_value_training_data_v7.jsonl  v7 — real (state, outcome) training data w/ v7 features, 77,062 records
replays/raw/ab_learned_vs_heuristic_leaf_log.jsonl  v5 — real A/B run log (see docs/v5-architecture.md)
replays/raw/ab_learned_v7_vs_heuristic_leaf_log.jsonl  v7 — real A/B run log (see docs/v7-architecture.md)
replays/raw/ladder_pool_log.jsonl / ladder_pool_summary.json  v7 — real 150-game ladder pool run

decks/cornerstone_ogerpon_v7.csv        v7 — real, legal 2nd decklist, used for the item D matchup A/B above

config/search_config.yaml               v4/v5 — search + leaf-value feature flags, data not hardcoded
docs/v4-architecture.md                 v4 — what was built, the real A/B result, and why it ships opt-in
docs/v5-architecture.md                 v5 — learned leaf-value function, its real (null) A/B result, and why Phase 3+ is blocked
docs/v6-architecture.md                 v6 — Cornerstone Ogerpon ex prior, why it's validated differently than v3-v5
docs/v7-architecture.md                 v7 — search generalization, cross-archetype validation, ladder pool, 2nd leaf-value null result — every real result, honestly
models/leaf_value_v5.joblib             v5 — the actual trained model (StandardScaler + LogisticRegression)
models/leaf_value_v7.joblib             v7 — GBT model on the richer v7 feature set (real A/B result: still a null result)

writeup/                                the Kaggle Strategy-category writeup draft + figure
kaggle-dataset-package/                 the packaged card-data Kaggle Dataset upload (v7: now includes
                                         the engine-cross-validated tables + DATASET_UPGRADE_REPORT.md)
```

*`*bugs`* — see "Bugs found and fixed" below; this is not a euphemism, two real,
previously-shipping-adjacent decision bugs were found here.

## Why v1/v2/v3, and why nothing here is claimed without proof

This project treats "the agent that's actually scored" as sacred: `v1` is
frozen and never edited. Everything else earns trust by being checked
*against* v1 on the real engine, not by looking plausible. Concretely:

- **v2 must make identical decisions to v1.** `tests/test_agent_matches_legacy.py`
  runs real self-play games through the real engine, feeds the identical
  observation to both `legacy.agent()` and the new `agent()` at every single
  decision point, and asserts zero divergence. It currently passes with real
  games completing end to end (see "Real results").
- **v3 modules are real and engine-tested, but not decision-affecting** until
  a change to agent.py is itself validated the same way. `rating/`, `belief/`,
  and `search/` all have real tests that exercise them against the real
  engine or on real data — they are not stubs — but none of them currently
  change what `agent.py` decides. Wiring one in without a head-to-head/A-B
  validation pass would be the exact mistake this whole audit process exists
  to catch.

## Bugs found and fixed (via real head-to-head testing, this build)

Both were caught the same way: running real self-play games through the real
engine and diffing v1's and v2's chosen option index at every decision.

1. **Pokemon-card misclassification.** `_is_pokemon_type()` compared an enum
   *name string* (`"POKEMON"`) against `cardData.cardType`. The real engine's
   `to_dataclass()` assigns JSON scalars raw — `cardType` comes through as a
   plain `int` (`0` for Pokemon), not an enum instance — so the string match
   silently never fired, and every Pokemon-card PLAY was scored as a generic
   Trainer (~10000 instead of ~20000). Caught via a real mismatch: legacy
   correctly prioritized playing Duraludon, v2 tied it with playing Ultra Ball.
   Fixed by comparing directly against `CardType.POKEMON` — `IntEnum`
   equality works transparently against both a raw int and an actual enum
   instance, so one fix covers the real engine and the mock fixtures.
2. **Attack-plan staleness.** v1's `plan` is a single object, mutated in
   place, across *every* MAIN-context call within one turn — not reset each
   call. A call that finds no viable attacker this turn simply never writes
   into `plan`, so it silently keeps whatever a *prior* call that same turn
   already found. The first cut of `build_attack_plan()` instead returned a
   brand-new blank plan any time that call alone found nothing, which
   regressed a real found attack back to "no plan" purely because a later
   MAIN call saw a momentarily-unusable active Pokemon. Fixed by threading
   `previous_plan=` through so the same "only overwrite if this call beats
   -1" semantics apply. Regression test:
   `tests/test_attack_plan_stickiness.py` (mock-engine, no live engine
   needed, so it runs everywhere).

A third, pre-existing finding from before this session (see v1's own module
docstring): the `deck_loading.py` guard against Kaggle auto-mounting its own
`sample_submission/deck.csv` over the real deck — generalized here into
`validate_trusted_override()`, audited on demand by
`scripts/deck_consistency_check.py`.

## Real results (not simulated, not estimated)

`replays/raw/replay_log.jsonl` holds real records from `scripts/replay_logger.py`
actually playing games through the live engine in this environment. Current
log (mirror match — both seats run this same agent/deck, since no other
archetype's decklist was available in this environment to play against):

```
opponent_archetype | decided | logged | win_rate | 95% CI         | avg_steps
mirror              | 30      | 30     | 60.0%    | [42.3%, 75.4%] | 134
```

Read honestly: 30 games is enough to see the agent completes real, coherent,
non-crashing games end to end and to get a rough sense of first-seat/
initiative advantage in the mirror — it is **not** enough to claim a precise
win rate, hence the wide Wilson interval. `scripts/matchup_breakdown.py`
recomputes this from the log at any time; `scripts/replay_logger.py --games N
--opponent-deck <path> --opponent-archetype <name>` appends real data for an
actual opposing decklist the moment one is available, rather than guessing.

## A real, previously-undocumented engine boundary found while building this

Early versions of the test harness checked `obs_dict.get("result")` (a
top-level key that doesn't exist) instead of the real field,
`obs["current"]["result"]` (`-1` while a game is ongoing, `0`/`1`/`2` once it
ends). Every game looked like it hit a mysterious, 100%-reproducible "empty
option pool" crash around step 100-170 — which was actually just games ending
normally and the harness not noticing, so it kept calling `battle_select()`
on an already-finished battle. Fixed by reading the correct field
everywhere. Documented here because it's exactly the kind of engine-contract
detail that's easy to get subtly wrong when driving `cg` directly instead of
through whatever wrapper the graded Kaggle harness uses, and worth knowing if
this code is ever extended.

## Testing

```
pip install pytest
pytest                      # conftest.py wires up src/ and vendor/ automatically
```

91 tests, all passing in this environment (up from v3's 34, v4's 56, v5's 76, v6's 81):
- `test_agent_matches_legacy.py` — real engine, real self-play, v1-vs-v2 parity (skips if `vendor/cg`'s `.so` isn't loadable on this platform, e.g. a non-Linux-x86_64 machine — see `vendor/cg/sim.py` for the platform table it looks for). Deliberately builds its v2 comparison agent with search disabled — this test's whole claim is decomposition parity, a different claim from search's own validation below.
- `test_lookahead.py` — real engine, confirms the `search_begin`/`search_step`/`search_end` wiring round-trips correctly
- `test_expectimax_real_engine.py` — v4, real engine: `rank_attack_candidates()` against a real attack decision at depth 1 and 2, plus a full real self-play game with search fully wired through `build_agent()`
- `test_expectimax_matches_heuristic_at_depth_zero.py` — v4, the regression gate: depth 0 / disabled must be byte-identical to plain heuristic scoring
- `test_transposition_table.py`, `test_belief_informed_determinization.py`, `test_search_config_loader.py` — v4/v5, pure-Python/mock-engine, run on any machine
- `test_featurize.py`, `test_replay_vector_store.py` — v5, Phase 1 (Replay Vector Store), pure-Python
- `test_leaf_value.py`, `test_learned_leaf_value_wiring.py` — v5, Phase 2 (learned leaf-value), pure-Python: training/predict/save-load mechanics and fail-closed behavior
- `test_learned_leaf_value_real_engine.py` — v5, real engine: confirms the trained model is genuinely consulted (not silently skipped) across a full real self-play game
- `test_scoring.py`, `test_attack_plan_stickiness.py`, `test_option_scorer.py`, `test_deck_loading.py`, `test_ladder.py`, `test_energy_density.py` — pure-Python, mock-engine or math-only, run on any machine regardless of engine availability
- `test_cornerstone_ogerpon_planning.py` — v6, pure-Python/mock-engine: confirms `build_attack_plan()` skips the blocked Archaludon ex pairing and falls through to Duraludon
- `test_expectimax_v7_real_engine.py` — v7, real engine: depth-3 runs a genuine extra real round without crashing; `policy_top_k` pruning mechanics
- `test_plan_stability.py` — v7, mock-engine: the stability bonus prefers the previously-committed attacker near ties, and never overrides a lethal line
- `test_ladder.py` — v3/v7, pure-Python: real Elo math, plus v7's `record_match()` symmetric two-sided update (including a guard against pre-game-rating double-counting)

## Scoped out (explored, not shipped) — and what moved out of this list

Consistent with the "shipped and measured" vs. "explored but not validated"
split this project holds itself to elsewhere (see `writeup/`): a PPO
self-play loop and genetic deck search were considered and are **not** in
this repo in any form, stub or otherwise — they'd need training
infrastructure this environment doesn't have, and claiming them without
that would be exactly the overclaiming the writeup's own honesty section
warns against.

**v4:** `search/lookahead.py`'s plumbing is no longer just tested —
`search/expectimax.py` wires it into a real, A/B-validated ATTACK-ranking
layer (67.0% win rate, n=100, 95% CI [57.3%, 75.4%] at depth 2 vs. the pure
heuristic in real self-play mirror matches — see `docs/v4-architecture.md`).
Ships opt-in, not as `build_agent(deck)`'s default — see that doc.

**v5:** a value net (`learning/leaf_value.py`) is no longer on the "not
built" list either — it's real, trained on 76,486 real self-play records,
and A/B-tested. Its result was a **null result** (50.0% vs. the heuristic
leaf at both depth 1 and depth 2 — see `docs/v5-architecture.md`), so it
stays off by default, but it's a real, measured finding now, not an
unstarted item. Behavioral cloning from real ladder replays is still
explicitly not started — but for a concrete reason now, not a training-
infrastructure gap: this environment has no real human/top-episode replay
export to train on (see `docs/v5-architecture.md`'s Phase 3 section).
Population/league training, CFR/fictitious play, bandit search-mode
selection, and Bayesian-tuned hyperparameters remain not started, for the
same reasons the v3 doc gave (`docs/agent-v3-upgrade-architecture.md`) — no
real gap in the now-measured layers has named a reason to start any of them
yet.

**v6:** `threats/cornerstone_ogerpon.py` adds one real, externally-sourced
competitive-play prior — Cornerstone Mask Ogerpon ex's Cornerstone Stance,
this deck's named structural counter in real competitive play, verified
against this project's own card-data table and wired into both the damage
calculator and the attack planner. Unlike v3–v5, it isn't A/B-tested,
honestly, because it can't be: this deck's mirror-match self-play tooling
never produces this opponent, so validation is unit tests against real card
text plus the existing v1-parity real-engine test, not a win-rate result —
see `docs/v6-architecture.md` for why that's the right evidence tier here,
not a shortcut.

**v7:** every buildable-now item from `docs/v7-research-and-proposal.md`
(A–E) is now real and measured, not proposed. Two moved to "real positive
result": the Cornerstone Ogerpon fix is now directly A/B-tested for the
first time (real +11.7pp, item D) and the multi-agent ladder pool is real,
not dormant (item A, 150 real games). Three are real negative/null results,
reported the same way v4/v5's were: search depth 3 underperforms the
shipped depth 2, `policy_top_k` branch pruning is a real loss, and the
plan-stability bonus is a real null. The Suphx-style oracle idea (the
original item B) was investigated and found genuinely blocked by the real
engine — `Observation.hand` is `None` for the opponent even at the raw dict
level, confirmed directly, not assumed — and honestly pivoted to a
GradientBoostingClassifier plus one new legal feature instead; that pivot's
real A/B result is a second null result, which is itself useful: it rules
out "wrong model class" as v5's original bottleneck. An LLM-in-the-loop
evaluator (item G) stays explicitly not attempted pending a rules check on
whether the competition's runtime even permits inference-time network
calls. League-scale training (item H) and Kaggle-credential-gated
behavioral cloning (item F) remain named-but-blocked for the same
compute/access reasons as before. See `docs/v7-architecture.md`.

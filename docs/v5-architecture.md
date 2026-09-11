# Pokémon TCG AI Agent — v5: Learned Evaluation, Measured Honestly

*Sep 10, 2026 · Extends `docs/v4-architecture.md` and answers the elaborated
Phase 1–10 module list the user's own research doc proposed. This doc covers
what was actually built and A/B-tested this cycle (Phases 1–2) and states
plainly why Phase 3 onward is not started — not a schedule slip, a real
missing input.*

## What v5 actually is, vs. the full research doc

The research doc's own Phase 1–5 table put the realistic-this-cycle work at
13–23 person-days. This session built and A/B-validated Phases 1–2 for
real, against the live engine, with real data — matching the project's own
"cheapest, most load-bearing module first" rule. Phase 3 (behavioral
cloning from human replays) is explicitly **not started**, for a concrete,
stated reason below, not a vague "future work" deferral.

## Phase 1 — Replay Vector Store (shipped)

`src/pokemon_agent/memory/featurize.py` + `memory/replay_store.py`. Turns a
real `Observation` into a 19-feature vector (HP fractions, energy/tool
counts, per-side `pokemon_score()` totals, hand/discard/prize counts, turn
number) from one player's perspective, and a brute-force numpy
cosine-similarity store over `(features, real_outcome, meta)` records — real
records, not FAISS/annoy, because at this project's actual data volume
(tens of thousands of records, see below) brute-force is exact and fast; an
ANN library is a scaling upgrade for data this project doesn't have yet, not
a correctness requirement today. 12 tests, all against real feature
extraction and real save/load round-trips.

## Phase 2 — Learned Leaf-Value Function (shipped, real A/B, real null result)

`src/pokemon_agent/learning/leaf_value.py`: `LearnedLeafValue`, a
`StandardScaler` + `LogisticRegression` pipeline (the cheap end of the
doc's own "start with logistic regression / small GBT" plan), trained to
predict P(win) from the Phase 1 feature vector.

**Real training data:** `scripts/generate_self_play_training_data.py` ran
**300 real self-play games** through the actual engine, mixing
heuristic-only, search-depth-1, and search-depth-2 agents across both seats
for state diversity, logging a record from BOTH players' perspectives at
every real decision (the same real board state, featurized once per side —
not fabricated duplication, a legitimate doubling of usable signal from the
same real games). **76,486 real (state, outcome) records**, exactly balanced
(38,243 win-labeled / 38,243 loss-labeled — no draws occurred in this deck's
self-play).

**Real training result** (`scripts/train_leaf_value_model.py`, 80/20 held-out
split, n_test=15,298):

| metric | value |
|---|---|
| Test accuracy | 69.4% |
| Test log loss | 0.5633 (vs. 0.6931 for an always-0.5 naive baseline) |
| Test AUC | 0.7782 |

The top-weighted feature by a wide margin, after standardization, is the
prize-count differential (`op_prize_count`: +0.916, `my_prize_count`:
−0.916) — the model correctly found that being closer to taking all 6 prizes
is the dominant signal in this exact game, which is the sanity check that
says it learned something real rather than noise.

**Wired, opt-in, gated:** `search/expectimax.py`'s leaf evaluator is now
swappable (`ExpectimaxConfig.leaf_value_mode`: `"heuristic"` or `"learned"`),
both normalized to `[-1, 1]` so the ATTACK-score bonus means the same thing
regardless of which evaluator produced it. Fails closed to heuristic if the
model path is missing or fails to load — never a crash. 10 new tests cover
the mechanics (fail-closed behavior, terminal-state handling, save/load) and
2 real-engine tests confirm the trained model is genuinely consulted (not
silently skipped) across a full real self-play game.

### The real A/B result: a null result, reported honestly

`scripts/ab_test_learned_value_vs_heuristic_leaf.py`: both sides run search
at the SAME depth (isolating the leaf evaluator as the only variable), real
self-play, seats alternated.

| depth | games (n) | learned-leaf wins | win rate | 95% Wilson CI |
|---|---|---|---|---|
| 1 | 80 | 40 | 50.0% | [39.3%, 60.7%] |
| 2 | 60 | 30 | 50.0% | [37.7%, 62.3%] |

**The learned leaf-value function does not currently beat the hand-coded
heuristic leaf.** Both intervals sit centered on a coin flip. This is a real
result from real games, not a bug to explain away, and per this project's
own rule ("nothing replaces a scored decision path until it wins a
head-to-head A/B"), it stays unshipped: `config/search_config.yaml`'s
`leaf_value_mode` stays `"heuristic"`.

**Read honestly, why this is still a useful result, not a dead end:** the
model's 69.4% held-out accuracy is real signal on its OWN training
distribution, but that didn't translate into winning games through the
narrow slice of decisions it actually influences here — `expectimax.py`'s
ATTACK-only re-ranking scope (unchanged from v4, see that doc for why) means
the leaf evaluator only ever moves the needle on the turn-ending
attack-or-not decision, and a marginally-better win-probability estimate at
just that one decision type, filtered through a fixed-magnitude score bonus
tuned for the OTHER evaluator's range, may simply not be enough signal to
show up in full-game win rate. That's a stated hypothesis, not a proven
explanation — distinguishing it from "the model is just wrong" is real,
scoped next work (see below), not something this session claims to have
resolved.

**Named, concrete next steps for Phase 2 specifically** (not vague
"improve the model" — each is a testable, falsifiable change):
1. Widen the leaf evaluator's reach past ATTACK-only re-ranking, so a better
   win-probability estimate has more decisions to actually influence.
2. Try the doc's own next-cheapest step (a small gradient-boosted tree)
   before jumping to an MLP — logistic regression's linear decision boundary
   may be the real bottleneck, not the feature set.
3. Re-run with a larger, even more diverse self-play corpus — 300 games is
   real data, not a large amount by RL standards.
Each of these is a new, separately A/B-gated experiment, not a batch of
assumed wins to bundle into a future default flip.

## Phase 3 — Behavioral Cloning from Human Replays: blocked, not skipped

The research doc's Phase 3 needs a real human/top-episode replay export to
train on. **This environment does not have one.** There is no ladder replay
corpus, no top-episode export, and no way to fabricate one honestly — a
model "trained" on synthetic data relabeled as human imitation would be
exactly the overclaiming this project's own rules exist to prevent. This is
named as a real, external blocker: the moment a real replay export is
available (the competition's daily top-episode export, per the research
doc's own citation), Phase 3 is buildable with the same discipline as
Phases 1–2 used here. Until then, it stays unstarted, honestly, rather than
approximated with something that isn't what it claims to be.

## Phases 4–10: unchanged from the research doc's own reasoning

Phase 4 (PUCT/guided search) explicitly depends on Phase 3 providing a real
policy prior — not attempted, since Phase 3 is blocked and Phase 2 alone
isn't (yet) a proven-better leaf to build a new search backend around.
Phases 5–10 (archetype modeling, bandit mode selection, Bayesian tuning,
LLM meta-controller, skill library, self-play league) all still name real
trigger conditions in the research doc that haven't been met — a single
mirror-matchup dataset doesn't justify an archetype classifier (Phase 5),
one search mode with no proven-better alternative doesn't justify a bandit
selector (Phase 6) or its downstream tuner (Phase 7), and so on down the
list. None of this changed this cycle; restated here rather than silently
dropped.

## Test suite

76 tests total (up from v4's 56), all passing: +8 for Phase 1
(`test_featurize.py`, `test_replay_vector_store.py`), +12 for Phase 2
(`test_leaf_value.py`'s training/predict/save-load mechanics,
`test_learned_leaf_value_wiring.py`'s fail-closed behavior,
`test_learned_leaf_value_real_engine.py`'s real-engine confirmation that the
trained model is genuinely consulted). Every real-engine test in this repo
(v3 through v5) still passes; nothing in v5 touched v1–v4's default decision
path.

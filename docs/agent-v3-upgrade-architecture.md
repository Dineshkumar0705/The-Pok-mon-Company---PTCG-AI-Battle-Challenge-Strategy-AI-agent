# Archaludon ex Agent — v3: High-Architecture Multi-Module Upgrade

*Sep 10, 2026 · Built from the project's own already-researched material (`next-gen-agent-architecture-research-report.md`, `agent-upgraded-rd-report.md`, `strategy-writeup-research-report.md`) — no new citations invented, only real precedent pulled from what's already been vetted this project. This is R&D on top of the real v1 agent, not part of the graded writeup.*

## Lineage

- **v1** — the shipped, scored agent (`main.py`): single-pass heuristic scorer, no search.
- **v2** — decomposition of v1 into testable modules + a formalized replay-audit tool (delivered last turn). Zero behavior change from v1.
- **v3 (this doc)** — the first version that adds genuine algorithmic depth beyond single-pass scoring. Every module below is explicitly unvalidated until it beats v1/v2 head-to-head; nothing here is claimed as shipped.

## Ground rules (unchanged from v2, restated because v3 raises the stakes)

1. Every module names the specific problem it solves and its precedent — no module gets added because it sounds sophisticated.
2. v1/v2 keeps running standalone. Every v3 module sits behind a feature flag.
3. Nothing replaces anything in the scored path until it wins a head-to-head A/B test with a stated binomial CI, the same discipline already used for the retreat-trigger revert.
4. Precise vocabulary, enforced: a density prior is not ISMCTS; a transposition table is not a world model; a replay index is not opponent prediction.

## Modules

### L1 — Search: shallow expectimax over the existing scorers

**Problem it solves:** v1/v2 score every option in isolation, one ply deep — no accounting for the opponent's best reply. **Design:** wrap the existing `pokemon_score()` / `dyn_damage()` as the leaf-value function at the bottom of a 1-to-2-ply expectimax tree, rather than replacing them — the heuristics you already validated become the evaluation function a shallow search calls, not something search discards. **Precedent:** PokéChamp (ICML 2025, [arXiv:2503.04094](https://arxiv.org/abs/2503.04094)) — an expert-level minimax language agent showing shallow adversarial lookahead beating pure-heuristic and pure-RL baselines in this exact game family. Cited as precedent for trying this, not as evidence it will work here — that's what the A/B test is for.

### L2 — Caching: transposition table

**Problem it solves:** L1 introduces a search tree for the first time in this project; without caching, it re-evaluates board states reached via different move orders within the same turn. Not useful before L1 exists — v1/v2 has nothing to cache. **Design:** hash the board state, cache `{value, depth_searched, best_move}`, cleared between games. **Precedent:** standard chess/checkers-engine technique — see the transposition-table sources already gathered (Wikipedia overview, the Stochastic Game Tree Search paper, the alpha-beta tutorial slides) in `next-gen-agent-architecture-research-report.md` §3.

### L3 — Belief-state opponent modeling, now grounded in the real card dataset

**Problem it solves:** the opponent's hand is hidden; v1/v2 only reacts to what's already on the visible board. **Design:** an energy-density proxy over the opponent's likely available energy/cards, built from observed board and discard state — and now genuinely groundable, because `data/raw/EN_Card_Data_canonical.csv` (from the dataset cleanup) gives a real, verified lookup of each card's actual energy costs and types, so the density estimate can condition on what's mechanically possible for the archetype in play, not a guess. This is the concrete "notebook + dataset + agent" integration point. **Honesty, stated plainly:** this is a density prior, not full ISMCTS — there's no opponent decklist to sample from at inference, so it's closer to determinization-with-a-heuristic-prior than textbook belief-state search. **Precedent:** Cowling, Powley & Whitehouse's original ISMCTS paper, cited as the standard family this approach borrows vocabulary from, with the PIMC-vs-ISMCTS distinction (`strategy-writeup-research-report.md` §5) used to state honestly what this is and isn't.

### L4 — Evaluation: a real rating ladder fed by v2's own tooling

**Problem it solves:** "avoids over-reliance on specific matchups" needs to be a measured mechanism, not an assertion. v2's `replays/audit/matchup_breakdown.py` already produces win/loss-by-archetype data — L4 is what turns that into a running skill estimate rather than a one-off report. **Design:** a TrueSkill-style Bayesian rating, updated after each logged game, tracked per-archetype. **Precedent:** TrueSkill (Herbrich, Minka & Graepel, Microsoft Research) — chosen over plain Elo specifically because it tracks uncertainty from partial, non-round-robin match data, which is exactly this project's situation (see `strategy-writeup-research-report.md` §5 for the Elo-vs-TrueSkill reasoning already worked out).

## Explicitly not building yet — named, not hand-waved

Real techniques, real citations already in this project's own research, deliberately not started because no gap in L1–L4 has shown they're needed:

- **A learned leaf-value function / AlphaZero-style self-play** ([arXiv:1712.01815](https://arxiv.org/abs/1712.01815)) — only justified once L1's hand-coded leaf evaluator is shown, by measurement, to be the bottleneck.
- **Algorithm-portfolio / multi-armed-bandit search-mode selection** (Kotthoff's survey; Slivkins' bandit introduction) — a cheaper, non-LLM way to pick "fast heuristic vs. deep search" per decision. Not before L1 exists to choose between.
- **Bayesian optimization for hyperparameter tuning** (Snoek et al.) — the correct tool for jointly tuning search depth/cache size once there are enough parameters worth tuning systematically. Premature with one search depth and one cache.
- **Population-based / league training** (AlphaStar, Nature 2019) — addresses staleness against a fixed opponent set more rigorously than matchup-conditioned regression, but requires a population of agent variants that doesn't exist yet.
- **Fictitious play / CFR-style equilibrium approximation** — the dominant alternative paradigm for imperfect-information games at equilibrium. Named explicitly as prior art considered and not pursued this cycle, which is itself a technical-soundness signal, not an omission to hide.

## File structure (extends the v2 tree — nothing in v2 is removed or renamed)

```
archaludon-ex-agent/
├── src/
│   └── archaludon_agent/
│       ├── ... (all v2 modules: scoring/, threats/, attack_plans.py, deck_loading.py, agent.py — unchanged)
│       │
│       ├── search/                      # NEW — v3
│       │   ├── __init__.py
│       │   ├── expectimax.py            # L1: wraps scoring/ as the leaf-value function
│       │   └── transposition_table.py   # L2: hash(board_state) -> {value, depth, best_move}
│       │
│       ├── belief/                      # NEW — v3
│       │   └── energy_density.py        # L3: density prior, reads data/raw/ for real card costs
│       │
│       └── rating/                      # NEW — v3
│           ├── trueskill_ladder.py      # L4: per-archetype Bayesian rating
│           └── matchup_report.py        # consumes v2's matchup_breakdown.py output
│
├── config/
│   └── search_config.yaml               # expectimax depth, transposition table size — data, not hardcoded
│
├── scripts/
│   ├── ... (v2 scripts unchanged)
│   └── ab_test_search_vs_heuristic.py   # the actual validation gate: v1/v2 heuristic-only vs. v3 L1 search,
│                                         #   binomial CI, real engine — nothing in search/ ships without this passing
│
└── tests/
    ├── ... (v2 tests unchanged)
    ├── test_transposition_table.py
    ├── test_expectimax_matches_heuristic_at_depth_zero.py   # depth-0 expectimax must equal v1/v2's plain scoring —
    │                                                          #   the regression guardrail for the search wrapper
    └── test_energy_density_against_known_card_costs.py       # L3's estimates checked against data/raw/ ground truth
```

## Build order

| Step | Deliverable | Depends on | Validation gate before it counts as "done" |
|---|---|---|---|
| 1 | L1 expectimax, depth 1 | v2 (scoring/ modules) | `test_expectimax_matches_heuristic_at_depth_zero.py` passes; then A/B vs. v1/v2, binomial CI |
| 2 | L2 transposition table | L1 (nothing to cache before search exists) | `bench_cache.py`-style nodes-evaluated metric, before/after |
| 3 | L3 belief-state density prior | `data/raw/` (dataset cleanup, already done) | Estimates checked against `data/raw/` ground truth on known archetypes |
| 4 | L4 TrueSkill ladder | v2's `matchup_breakdown.py` (needs real logged games first) | Ratings converge sensibly on the existing 93.8%-vs-random / 50.0%-non-regression data before trusting it on new data |
| 5+ (not scheduled) | Learned value function, bandit search-selector, Bayesian-tuned hyperparameters, league training, CFR/fictitious play | Only once a specific measured gap in steps 1–4 names it | — |

Step 1 is the only one worth starting before there's more post-fix ladder data — everything from step 3 onward benefits from having a larger, cleaner replay set first, which is still the single open item from the writeup's Discussion section.

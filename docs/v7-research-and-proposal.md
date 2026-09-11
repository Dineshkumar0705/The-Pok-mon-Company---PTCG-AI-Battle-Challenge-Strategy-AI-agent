# v7 Research: World-Wide Game-AI Survey, Gap Analysis, Upgrade Proposal

*Sep 10, 2026 · Research-and-proposal pass only — nothing in this doc is built
yet. Extends `docs/v6-architecture.md`. Scope: survey real game-playing AI
systems across categories (board games, imperfect-info card games, esports,
cooperative games, LLM agents), including direct competitive intelligence
from other real entrants in this exact Kaggle competition, then name
concrete, honestly-tagged upgrade candidates for v7.*

## Survey scope and honesty note on "100+"

This pass covered roughly a dozen categories via targeted web research (not
every individual source below was independently fetched in full — some are
search-result summaries, marked accordingly). Counting every individually
named bot/entry surfaced (Hearthstone AI Competition alone lists dozens of
competing bots across years; Kaggle's Lux AI and Halite leaderboards list
hundreds of submitted agents), the survey's total surface easily clears 100+
distinct systems. The citations below are the ones actually read in enough
depth to ground a claim — that's the honest count, not 100+ individually
vetted papers.

## Category survey

**Board games (perfect information):**
- AlphaZero / MuZero — self-play + PUCT search guided by a learned
  policy+value network; MuZero learns a model of the environment itself
  rather than being given the rules ([Science](https://www.science.org/doi/10.1126/science.aar6404), [MuZero explainer](https://www.reinforcement-learning.com/kb/alphazero-and-muzero)).
- KataGo — open-source Go engine, same self-play/MCTS family, heavy
  engineering on training efficiency.

**Imperfect-information card/table games:**
- Pluribus — superhuman multiplayer poker; blueprint strategy computed
  offline (abstraction + self-play), refined by real-time subgame search at
  play time ([Science](https://www.science.org/doi/10.1126/science.aay2400), [explainer](https://openpoker.ai/blog/pluribus-poker-bot-explained)).
- DeepStack / Libratus — earlier poker agents combining deep counterfactual
  value networks with real-time search ([DeepStack coverage](https://www.theregister.com/2017/01/14/deepstack/)).
- Deep CFR / ReBeL — regret-minimization learned via deep nets instead of
  tabular counterfactual regret, avoiding hand-crafted abstractions
  ([Deep CFR paper](https://proceedings.mlr.press/v97/brown19b/brown19b.pdf)).
- Suphx (Microsoft, Mahjong) — superhuman via deep RL *plus* an
  "oracle guiding" technique: a full-information teacher (sees all players'
  hidden tiles during training) shapes a partial-information student's
  value function, plus global-reward prediction for long-horizon credit
  assignment ([Microsoft Research](https://www.microsoft.com/en-us/research/publication/suphx-mastering-mahjong-with-deep-reinforcement-learning/)).
- ISMCTS (Cowling, Powley, Whitehouse) — information-set MCTS with
  determinization over hidden state; the foundational citation for exactly
  the belief-informed-sampling family this project's own `search/lookahead.py`
  already implements ([original paper](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf), [Dou Di Zhu application](https://www.semanticscholar.org/paper/Determinization-and-information-set-Monte-Carlo-for-Whitehouse-Powley/67e1f4795c461a5467d6009b1efdaa36aad03a40)).
- RLCard — a standardized RL toolkit/benchmark suite across many card games
  (Dou Dizhu, UNO, Leduc/Limit Hold'em, Mahjong) ([rlcard.org](https://rlcard.org/)).

**TCG-specific bots:**
- Hearthstone AI Competition — a recurring bot ladder; MCTS-based and
  rule-based entries are both common, several years of published results
  ([competition site](https://hearthstoneai.github.io/), [MCTS assistant paper](https://www.researchgate.net/publication/357898736_Hearthstone_Battleground_An_AI_Assistant_with_Monte_Carlo_Tree_Search)).
- ygo-agent (Yu-Gi-Oh!) — combines deep RL *and* LLMs in one bot
  ([GitHub](https://github.com/sbl1996/ygo-agent)).

**Esports / RTS (large-scale self-play):**
- AlphaStar (StarCraft II) — league-based, population self-play: many
  agents with different exploiter roles trained concurrently to avoid
  cyclical strategy collapse ([DeepMind](https://deepmind.google/blog/alphastar-grandmaster-level-in-starcraft-ii-using-multi-agent-reinforcement-learning/)).
- OpenAI Five (Dota 2) — large-scale PPO self-play at massive compute scale
  ([OpenAI paper](https://cdn.openai.com/dota-2.pdf)).

**Cooperative / negotiation:**
- Hanabi Challenge — theory-of-mind / belief modeling between cooperating
  agents under hidden information, a different problem shape but the same
  underlying belief-tracking machinery this project's `belief/energy_density.py`
  is a simple instance of ([Hanabi Challenge paper](https://arxiv.org/pdf/1902.00506)).
- Cicero (Meta, Diplomacy) — LLM for open-domain natural-language
  negotiation *combined with* a strategic-reasoning planner (not the LLM
  freelancing alone) ([Meta AI](https://ai.meta.com/research/cicero/)).

**LLM-driven game agents (most directly relevant to this deck's own
project-level research doc):**
- PokéChamp (ICML 2025) — an LLM used as an expert-level **minimax agent**:
  the LLM generates and evaluates candidate actions in-context, replacing a
  hand-coded evaluator, not just adding chat flavor
  ([arXiv](https://arxiv.org/pdf/2503.04094), [GitHub](https://github.com/sethkarten/PokeChamp)).
- PokéLLMon — reaches human-parity Pokémon-battle win rates (49% ladder /
  56% invited, >100 games) via three concrete techniques: in-context
  reinforcement (learning from this match's own text feedback),
  knowledge-augmented generation (reduces hallucinated rule violations), and
  **consistent-action generation** (avoids panic-switching against strong
  play) ([arXiv](https://arxiv.org/abs/2402.01118), [Georgia Tech summary](https://www.cc.gatech.edu/news/new-llm-based-ai-agent-achieves-human-performance-levels-pokemon)).
- Voyager (Minecraft) — LLM agent that builds and reuses a persistent
  **skill library** as it plays, the closest published analog to the user's
  own v5 research doc's "Skill Library" phase ([arXiv](https://arxiv.org/abs/2305.16291)).

**Direct competitive intelligence — other real entrants in *this* Kaggle
competition** (this is the most load-bearing part of the survey — not
theory, but what actual rivals in this exact event are doing):
- A public entrant repo ([TomBombadyl/kaggle_pokemon](https://github.com/TomBombadyl/kaggle_pokemon))
  frames the problem explicitly as an imperfect-information POMDP, runs
  **MCTS** (not fixed-depth expectimax), fields **multiple archetype-specific
  policies** (named variants for Lucario, Dragapult, and Snorlax decks, not
  one deck), and — critically — **pulls real episode data via the Kaggle
  API** for local evaluation, gated by a real TrueSkill-style ladder
  ("ladder μ sorts; local gates filter", one tracked rating example at
  880.9 μ). This directly contradicts nothing in this project's own v5
  finding (no *credentialed* access to that data in *this* environment) but
  does confirm the data access path is real and used by at least one other
  competitor — see the v7 proposal's item F below.
- Two public starter notebooks confirm the field's baseline spread: a PPO
  (policy-gradient RL) agent and a separate pure-heuristic-plus-data-pipeline
  agent are both submitted approaches for this competition (titles only
  confirmed — Kaggle's notebook viewer requires authentication this
  environment doesn't have, so their internals weren't read; noted
  honestly as a source-title-only citation, not a verified technical claim:
  [PPO notebook](https://www.kaggle.com/code/hmnshudhmn24/pok-mon-tcg-ai-battle-challenge-ppo-agent),
  [heuristic notebook](https://www.kaggle.com/code/avikdas567/ptcg-ai-battle-heuristic-agent-data-pipeline)).

## Gap analysis: this build (v6) vs. the survey

**Where this build already matches the literature's standard approach**
(worth stating, not just gaps): belief-informed determinization for hidden
opponent state (`belief/energy_density.py` + `search/lookahead.py`) is the
same family of technique ISMCTS/Cowling's work established as standard —
this isn't a novelty claim, and the project's own docs never claimed it was.
A real Elo/TrueSkill-style ladder module already exists
(`rating/ladder.py`), matching the competitor repo's own evaluation
methodology — it's just never been wired into an active iteration loop.

**Real, named gaps:**

| Gap | What the literature/competitor does | What v6 does |
|---|---|---|
| Search algorithm | MCTS with flexible simulation budget, guided by a learned policy (AlphaZero family; confirmed used by a real rival in this competition) | Fixed 1–2 ply expectimax, brute-force over all legal ATTACK candidates, no policy prior to guide/prune branching |
| Deck coverage | A real rival fields 3+ archetype-specific policies | Single deck (Archaludon ex only) |
| Self-play diversity | League/population-based training (AlphaStar, OpenAI Five) — many concurrent, differently-biased agents prevent strategy collapse | Only ever two mirrored copies of the same agent config in any A/B run |
| Ladder usage | The rival repo actively gates submissions through ladder μ | `rating/ladder.py` exists, tested, but never consumes a real diverse-opponent pool |
| Leaf-value training signal | Suphx's oracle-guiding: a full-information teacher (sees both hidden hands during training) shapes the partial-information student | v5's `LearnedLeafValue` trained directly on partial-information features only — no oracle signal, and its A/B result was a null result |
| Decision stability | PokéLLMon's consistent-action-generation avoids panic-switching under pressure | No general plan-stability prior beyond the specific `AttackPlan` stickiness bug fix (which was a mutation-semantics bug fix, not a designed anti-thrash heuristic) |
| Human/LLM reasoning layer | PokéChamp/PokéLLMon use an LLM as the action generator or evaluator itself | None — this agent is pure hand-coded heuristic + statistical search, no language-model component anywhere in the decision path |
| Real replay-derived training data | The rival repo pulls real competition episodes via the Kaggle API | Blocked in this environment specifically for lack of Kaggle credentials (see `docs/v5-architecture.md` Phase 3) — now confirmed by direct evidence that the path itself is real and used by at least one other competitor |

## v7 proposal: buildable now vs. genuinely blocked

Tagged honestly per this project's own discipline — nothing here is claimed
built, and infrastructure-blocked items are named as such rather than
quietly skipped.

**A — Wire up the dormant ladder against a real diverse pool (buildable
now).** `rating/ladder.py` has existed since v3 and has never consumed a
real multi-opponent pool. Round-robin the agent configs this repo already
has — heuristic-only, v4 search depth 1, v4 search depth 2, v5 learned-leaf
— through real self-play games and feed real results into the ladder. This
directly produces the matchup-conditioned evidence the "avoids
over-reliance on specific matchups" rubric line wants, using only what's
already built.

**B — Oracle-guided leaf value, Suphx-style (buildable now).** This
project's self-play already knows both hands' true hidden information
during training (it's simulating both sides). v5's `LearnedLeafValue` never
used that — it trained on partial-information features only. A second,
full-information "oracle" value function, trained on the SAME real self-play
games but with privileged features, could supervise/distill into the
partial-information student. This is a concrete, testable hypothesis for
*why* v5's real A/B result was a null result (not enough signal in 19
partial-information features), not a guaranteed win — would need its own
real A/B gate exactly like Phases 1–2 got.

**C — Policy-guided branch ordering (buildable now).** `expectimax.py`
currently brute-forces every legal ATTACK candidate. A cheap learned or
heuristic priority score to order/cap branch expansion (in the spirit of
AlphaZero's policy-guided PUCT, scaled down) could let real depth-3 search
fit in the same per-decision engine-call budget depth-2 uses today —
falsifiable via the same A/B harness `ab_test_search_vs_heuristic.py`
already provides.

**D — A second archetype policy (buildable now, larger scope).** Real
rivals in this exact competition field 3+ deck-specific policies. Building
even one additional archetype's heuristic layer (not full search/learning
stack) would let the ladder in item A produce genuinely cross-archetype
matchup data instead of only mirror-match numbers — directly addressing the
rubric's "avoids over-reliance on specific matchups" line with real
evidence instead of an assumed property.

**E — Plan-stability prior (buildable now, small).** Generalize the
existing `AttackPlan` stickiness fix's spirit (don't thrash a decision
without a real reason) into a small, explicit anti-flip-flop scoring term,
inspired by PokéLLMon's named consistent-action-generation technique —
cheap to build and A/B-test, real citation for the design rationale.

**F — Unblock Phase 3 behavioral cloning with real Kaggle credentials
(blocked on the user, not on technique).** The v5 doc named this blocked for
lack of a real replay corpus in this environment. A real rival's public repo
now confirms the Kaggle API path for pulling this exact competition's
episode data is real and actively used. Since the account profile shows an
active Kaggle account (`dineshkumar0705`), providing a Kaggle API token
(`~/.kaggle/kaggle.json` or `KAGGLE_USERNAME`/`KAGGLE_KEY`) would unblock
this directly — same scope as originally proposed, now with outside
confirmation the data is real and reachable.

**G — LLM-in-the-loop evaluator or policy, PokéChamp/PokéLLMon-style
(flagged, not recommended yet).** The literature's most different idea from
everything else in this build. Two real open questions before it's worth
attempting: (1) whether the competition's actual submission runtime permits
network calls to an LLM API at inference time — unconfirmed, and a wrong
guess here risks an agent that can't run at all under judging; (2) per-move
LLM inference latency/cost against whatever the real per-match time budget
is. Named here as a real technique other Pokémon-battle agents use
successfully, not as a v7 commitment — needs a rules check before any code.

**H — League/population-scale training (named, out of scope).**
AlphaStar/OpenAI-Five-scale training needs compute this environment doesn't
have. Item A (ladder against this repo's own existing agent variants) is
the honest, right-sized local analog — named here so the gap is
acknowledged rather than silently attempted at a scale that would fail.

## What this doc is not

This is a proposal, not a build. Nothing above has code, tests, or an A/B
result yet — consistent with how the v5 research doc was itself evaluated
before any phase was built. The next real step for any item above is the
same one this project has used for every prior version: build it,
A/B-gate it for real, and report the number honestly, whatever it is.

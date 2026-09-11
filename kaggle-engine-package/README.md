# PTCG Search Agent Engine Bundle (v7)

This dataset is the real, redistributable runtime this project's Strategy Category
writeup describes: the vendored battle-engine SDK (`cg/`) plus the real agent source
tree (`pokemon_agent/`) from the
[`pokemon-ai-agent`](https://github.com/) GitHub repo -- not a rebuild, not a
simplified stand-in. It exists so a Kaggle notebook can **actually run the real
search/ISMCTS agent live**, instead of only reporting numbers from a linked repo a
judge can't execute inside Kaggle.

## Why this is a separate dataset from the card dataset

The card dataset (`ptcg-card-data-cleaned-bilingual`) is *data about* the cards --
CSVs. This dataset is *code that plays the game* -- the compiled engine binary
(`cg/libcg.so`) and its Python wrappers, plus this project's real agent logic on top
of it. A notebook that attaches both can load real card data **and** run real games
with the real agent in the same place, which is the point: one working integration,
not two notebooks that never touch each other.

## How to use it in a notebook

1. Create the notebook on Kaggle, click **+ Add Input**, and attach both this dataset
   and `ptcg-card-data-cleaned-bilingual`.
2. In the first code cell, find the mounted engine folder and put it on `sys.path`:

   ```python
   import glob, sys
   eng = glob.glob("/kaggle/input/**/cg", recursive=True)
   assert eng, "attach the ptcg-search-agent-engine-v7 dataset first"
   sys.path.insert(0, eng[0].rsplit("/cg", 1)[0])   # the dir *containing* cg/ and pokemon_agent/

   from cg import game
   from pokemon_agent.agent import build_agent
   from pokemon_agent.search.config_loader import ExpectimaxConfig
   ```

3. Build the real, validated configuration explicitly in code -- do **not** rely on
   whatever `config/search_config.yaml` in this bundle currently says, since that file
   may carry a local debugging override. The real, A/B-validated winning configuration
   (depth=2 expectimax, heuristic leaf, belief-informed determinization, no
   candidate pruning, plan-stability off) is:

   ```python
   deck = [int(x) for x in open(f"{eng[0].rsplit('/cg',1)[0]}/deck.csv").read().split() if x.strip()]

   heuristic_agent = build_agent(deck, search_config=ExpectimaxConfig(enabled=False),
                                  plan_stability_enabled=False)
   search_agent = build_agent(deck, search_config=ExpectimaxConfig(
       enabled=True, depth=2, max_branch_steps=8,
       belief_informed_determinization=True, policy_top_k=None,
   ), plan_stability_enabled=False)
   ```

4. Play real games with `game.battle_start` / `game.battle_select` /
   `game.battle_finish`, exactly as `scripts/ab_test_search_vs_heuristic.py` does in
   the GitHub repo -- see the companion notebook
   (`ptcg_agent_engine_live_integration.ipynb`) for the full, already-executed version
   of this.

## What's NOT included

No training data, no replay logs, no test suite -- those live in the GitHub repo.
This bundle is deliberately scoped to exactly what a notebook needs to *run* the real
agent: the engine SDK, the agent source, the two (unused-by-default) learned-leaf
models for completeness, the search config file (for reference), and the real
decklist.

## Provenance

Every file here is copied unmodified from the `pokemon-ai-agent` GitHub repo's
`vendor/cg/`, `src/pokemon_agent/`, `config/`, `models/`, and `deck.csv` as of this
dataset's creation date. The engine binary (`cg/libcg.so`) is the same vendored SDK
already used by this project's other Simulation Category work -- it is not
reverse-engineered or reconstructed.

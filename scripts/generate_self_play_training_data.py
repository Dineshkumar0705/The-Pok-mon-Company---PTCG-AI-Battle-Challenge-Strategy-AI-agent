#!/usr/bin/env python3
"""v5 Phase 1/2 data generation: real self-play games through the actual cg
engine, logging a (features, label) record to the Replay Vector Store at
EVERY real decision point, from BOTH players' perspectives (two records per
decision -- the same real board state, featurized once per side; each side's
label is its own real eventual outcome, so this doubles usable data from the
same real games without fabricating anything).

Mixes three agent types across seats (heuristic-only, search depth=1, search
depth=2) so the logged states cover more of the real state space than a
single mirror-matchup would -- more varied board states to learn from, not
synthetic ones. Every game is real, played start to finish through
vendor/cg; nothing here is simulated data.

v7: `--feature-version v7` switches the logged vector from
`memory.featurize.featurize_observation()` (v5's original, still the
default) to `featurize_observation_v7()` (adds the Full Metal Lab stadium
flag -- see that module's docstring). Output records are otherwise
identical in shape/fields; only the feature vector length/content and the
output file default change, so v5's existing corpus and this script's own
default invocation are completely unaffected.

Usage:
    python3 scripts/generate_self_play_training_data.py --games 200
    python3 scripts/generate_self_play_training_data.py --games 200 --feature-version v7
"""
from __future__ import annotations

import argparse
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_OUT = os.path.join(REPO_ROOT, "replays", "raw", "leaf_value_training_data.jsonl")
DEFAULT_OUT_V7 = os.path.join(REPO_ROOT, "replays", "raw", "leaf_value_training_data_v7.jsonl")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--out", default=None)
    parser.add_argument("--feature-version", choices=("v5", "v7"), default="v5")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.out is None:
        args.out = DEFAULT_OUT_V7 if args.feature_version == "v7" else DEFAULT_OUT

    from cg import game  # noqa: E402
    from pokemon_agent.agent import build_agent  # noqa: E402
    from pokemon_agent.card_data import load_card_table  # noqa: E402
    from pokemon_agent.search.expectimax import ExpectimaxConfig  # noqa: E402
    from pokemon_agent.memory.featurize import featurize_observation, featurize_observation_v7  # noqa: E402
    from pokemon_agent.memory.replay_store import ReplayRecord  # noqa: E402

    featurize = featurize_observation_v7 if args.feature_version == "v7" else featurize_observation

    deck = _load_deck_file(args.deck)
    card_table, attack_table, source = load_card_table(prefer_engine=True)
    assert source == "engine"

    rng = random.Random(args.seed)
    agent_pool = {
        "heuristic": build_agent(deck, search_config=ExpectimaxConfig(enabled=False)),
        "search_d1": build_agent(deck, search_config=ExpectimaxConfig(enabled=True, depth=1)),
        "search_d2": build_agent(deck, search_config=ExpectimaxConfig(enabled=True, depth=2, max_branch_steps=6)),
    }
    agent_names = list(agent_pool.keys())

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    total_records = 0
    total_games_decided = 0

    with open(args.out, "a") as outf:
        for gi in range(args.games):
            seat_names = [rng.choice(agent_names), rng.choice(agent_names)]
            seat_agents = [agent_pool[n] for n in seat_names]

            obs_dict, _start = game.battle_start(deck, deck)
            pending = []  # (features_p0, features_p1) tuples, one per real decision
            result = -1
            steps = 0
            try:
                for steps in range(1, MAX_STEPS + 1):
                    sel = obs_dict.get("select")
                    if sel is None:
                        break
                    result = obs_dict.get("current", {}).get("result", -1)
                    if result != -1:
                        break

                    from cg.api import to_observation_class
                    obs = to_observation_class(obs_dict)
                    f0 = featurize(obs, card_table, my_index=0)
                    f1 = featurize(obs, card_table, my_index=1)
                    pending.append((f0, f1))

                    seat = obs_dict["current"]["yourIndex"]
                    choice = seat_agents[seat](obs_dict)
                    try:
                        obs_dict = game.battle_select(choice)
                    except IndexError:
                        break
                    result = obs_dict.get("current", {}).get("result", -1)
                    if result != -1:
                        break
            finally:
                try:
                    game.battle_finish()
                except Exception:
                    pass

            if result not in (0, 1, 2):
                continue  # game never reached a real result -- don't label unfinished data
            total_games_decided += 1

            label_p0 = 1.0 if result == 0 else (0.0 if result == 1 else 0.5)
            label_p1 = 1.0 if result == 1 else (0.0 if result == 0 else 0.5)

            for f0, f1 in pending:
                r0 = ReplayRecord(features=f0, label=label_p0,
                                   meta={"game_id": gi, "seat": 0, "agent": seat_names[0], "opponent_agent": seat_names[1]})
                r1 = ReplayRecord(features=f1, label=label_p1,
                                   meta={"game_id": gi, "seat": 1, "agent": seat_names[1], "opponent_agent": seat_names[0]})
                outf.write(__import__("json").dumps(
                    {"features": r0.features, "label": r0.label, "meta": r0.meta}) + "\n")
                outf.write(__import__("json").dumps(
                    {"features": r1.features, "label": r1.label, "meta": r1.meta}) + "\n")
                total_records += 2

            print(f"game {gi}: {seat_names[0]} vs {seat_names[1]}, result={result}, "
                  f"steps={steps}, records so far={total_records}")

    print(f"\n{total_games_decided}/{args.games} games decided. "
          f"Wrote {total_records} real (features, label) records to {args.out}")


if __name__ == "__main__":
    main()

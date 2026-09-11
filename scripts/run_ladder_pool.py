#!/usr/bin/env python3
"""v7: wire the dormant rating/ladder.py to a real pool of THIS project's
own agent variants (docs/v7-architecture.md item A) -- heuristic-only, v4
search at depth 1 and depth 2, and v5's learned-leaf evaluator. Real
self-play, round-robin, every pairing played real games through the actual
cg engine, fed into MatchupLadder.record_match() (v7's new symmetric
two-sided Elo method). This is the concrete mechanism behind the writeup's
"avoids over-reliance on specific matchups" claim -- a single strong
pairing can't hide a bad one here, each is visible on its own.

Usage:
    python3 scripts/run_ladder_pool.py --games-per-pairing 20
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "ladder_pool_log.jsonl")
DEFAULT_SUMMARY = os.path.join(REPO_ROOT, "replays", "raw", "ladder_pool_summary.json")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def _play_one(agent_a, agent_b, deck, a_plays_seat0: bool):
    from cg import game

    seat0_agent = agent_a if a_plays_seat0 else agent_b
    seat1_agent = agent_b if a_plays_seat0 else agent_a
    obs_dict, _start = game.battle_start(deck, deck)
    steps = 0
    stopped_reason = "max_steps"
    result = None
    for steps in range(1, MAX_STEPS + 1):
        sel = obs_dict.get("select")
        if sel is None:
            stopped_reason = "no_select"
            break
        result = obs_dict.get("current", {}).get("result", -1)
        if result != -1:
            stopped_reason = "finished"
            break
        seat = obs_dict["current"]["yourIndex"]
        choice = seat0_agent(obs_dict) if seat == 0 else seat1_agent(obs_dict)
        try:
            obs_dict = game.battle_select(choice)
        except IndexError:
            stopped_reason = "engine_select_rejected"
            break
        result = obs_dict.get("current", {}).get("result", -1)
        if result != -1:
            stopped_reason = "finished"
            break
    try:
        game.battle_finish()
    except Exception:
        pass

    decided = result in (0, 1, 2)
    a_won = None
    if decided and result in (0, 1):
        a_won = (result == 0) == a_plays_seat0
    return result, decided, a_won, steps, stopped_reason


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games-per-pairing", type=int, default=20)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    parser.add_argument("--summary-path", default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    from pokemon_agent.agent import build_agent
    from pokemon_agent.search.expectimax import ExpectimaxConfig
    from pokemon_agent.rating.ladder import MatchupLadder

    deck = _load_deck_file(args.deck)
    learned_model_path = os.path.join(REPO_ROOT, "models", "leaf_value_v5.joblib")

    agent_pool = {
        "heuristic": build_agent(deck, search_config=ExpectimaxConfig(enabled=False)),
        "search_d1": build_agent(deck, search_config=ExpectimaxConfig(enabled=True, depth=1)),
        "search_d2": build_agent(deck, search_config=ExpectimaxConfig(enabled=True, depth=2, max_branch_steps=8)),
        "learned_leaf_d2": build_agent(deck, search_config=ExpectimaxConfig(
            enabled=True, depth=2, max_branch_steps=8,
            leaf_value_mode="learned", leaf_value_model_path=learned_model_path,
        )),
    }
    names = list(agent_pool.keys())

    ladder = MatchupLadder()
    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)

    records = []
    with open(args.log_path, "a") as logf:
        for name_a, name_b in itertools.combinations(names, 2):
            agent_a, agent_b = agent_pool[name_a], agent_pool[name_b]
            for i in range(args.games_per_pairing):
                a_plays_seat0 = (i % 2 == 0)
                result, decided, a_won, steps, stopped_reason = _play_one(
                    agent_a, agent_b, deck, a_plays_seat0,
                )
                if decided and result in (0, 1, 2):
                    ladder.record_match(name_a, name_b, a_won)
                record = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "agent_a": name_a, "agent_b": name_b,
                    "a_plays_seat0": a_plays_seat0,
                    "result": result if decided else None,
                    "a_won": a_won, "steps": steps, "stopped_reason": stopped_reason,
                }
                records.append(record)
                logf.write(json.dumps(record) + "\n")
                print(f"{name_a} vs {name_b} [{i}]: a_seat={'0' if a_plays_seat0 else '1'} "
                      f"result={result} a_won={a_won} steps={steps} stopped=({stopped_reason})")

    summary = ladder.summary()
    print("\n=== Real ladder pool result (docs/v7-architecture.md item A) ===")
    for name in sorted(summary, key=lambda n: -summary[n]["rating"]):
        s = summary[name]
        wr = f"{s['win_rate']:.1%}" if s["win_rate"] is not None else "n/a"
        print(f"{name:20s} rating={s['rating']:7.1f}  games={s['games']:3d}  win_rate={wr}")

    with open(args.summary_path, "w") as sf:
        json.dump({
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "games_per_pairing": args.games_per_pairing,
            "pool": names,
            "ladder": summary,
        }, sf, indent=2)
    print(f"\nWrote {len(records)} real game records to {args.log_path}")
    print(f"Wrote ladder summary to {args.summary_path}")


if __name__ == "__main__":
    main()

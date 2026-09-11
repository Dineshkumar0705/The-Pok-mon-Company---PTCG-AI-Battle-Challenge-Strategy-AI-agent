#!/usr/bin/env python3
"""v7 real A/B gate for PLAN_STABILITY_BONUS (attack_plans.py):
plan-stability-enabled vs. plain heuristic, real self-play mirror-match
games through the actual cg engine, seats alternated. Same pattern as
scripts/ab_test_search_vs_heuristic.py -- nothing here ships as the default
(`build_agent(deck)`'s `plan_stability_enabled` stays False) without a real
head-to-head win reported here, per this project's own rule.

Usage:
    python3 scripts/ab_test_plan_stability.py --games 40
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "ab_plan_stability_log.jsonl")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    from scripts.matchup_breakdown import wilson_interval  # noqa: E402

    if args.summarize_only:
        records = []
        if os.path.exists(args.log_path):
            with open(args.log_path) as f:
                records = [json.loads(line) for line in f if line.strip()]
        decided = [r for r in records if r.get("stable_won") is not None]
        wins = sum(1 for r in decided if r["stable_won"])
        n = len(decided)
        print(f"=== All logged results in {args.log_path} ===")
        if n:
            lo, hi = wilson_interval(wins, n)
            print(f"Plan-stability win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
        else:
            print("No decided games logged yet.")
        return

    from cg import game  # noqa: E402
    from pokemon_agent.agent import build_agent  # noqa: E402
    from pokemon_agent.search.expectimax import ExpectimaxConfig  # noqa: E402

    deck = _load_deck_file(args.deck)

    plain_agent = build_agent(deck, search_config=ExpectimaxConfig(enabled=False),
                               plan_stability_enabled=False)
    stable_agent = build_agent(deck, search_config=ExpectimaxConfig(enabled=False),
                                plan_stability_enabled=True)

    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)
    start_id = 0
    if os.path.exists(args.log_path):
        with open(args.log_path) as f:
            for line in f:
                if line.strip():
                    start_id = max(start_id, json.loads(line)["game_id"] + 1)

    records = []
    with open(args.log_path, "a") as logf:
        for i in range(args.games):
            stable_plays_seat0 = (i % 2 == 0)
            seat0_agent = stable_agent if stable_plays_seat0 else plain_agent
            seat1_agent = plain_agent if stable_plays_seat0 else stable_agent

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
            stable_won = None
            if decided and result in (0, 1):
                winner_seat = result
                stable_won = (winner_seat == 0) == stable_plays_seat0

            record = {
                "game_id": start_id + i,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "opponent_archetype": "mirror",
                "stable_plays_seat0": stable_plays_seat0,
                "result": result if decided else None,
                "stable_won": stable_won,
                "turns": obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None,
                "steps": steps,
                "stopped_reason": stopped_reason,
            }
            records.append(record)
            logf.write(json.dumps(record) + "\n")
            print(f"game {record['game_id']}: stable_seat={'0' if stable_plays_seat0 else '1'} "
                  f"result={result} stable_won={stable_won} steps={steps} stopped=({stopped_reason})")

    decided = [r for r in records if r["stable_won"] is not None]
    wins = sum(1 for r in decided if r["stable_won"])
    n = len(decided)
    print(f"\n=== Plan-stability vs. plain heuristic, {n}/{len(records)} real games decided ===")
    if n:
        lo, hi = wilson_interval(wins, n)
        print(f"Plan-stability win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
    else:
        print("No decided games -- cannot report a win rate.")
    print(f"\nAppended {len(records)} record(s) to {args.log_path}")


if __name__ == "__main__":
    main()

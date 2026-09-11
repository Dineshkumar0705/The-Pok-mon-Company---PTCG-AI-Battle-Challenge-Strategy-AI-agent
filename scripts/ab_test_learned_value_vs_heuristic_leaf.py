#!/usr/bin/env python3
"""v5's real validation gate, same discipline as v4's
ab_test_search_vs_heuristic.py: real self-play mirror-match games through
the actual cg engine, both sides running search at the SAME depth (so this
isolates ONE variable -- the leaf evaluator -- rather than confounding it
with search depth), seats alternated to cancel first-move advantage.

    seat A: search, leaf_value_mode="heuristic"  (v4's validated position_value())
    seat B: search, leaf_value_mode="learned"    (v5's LearnedLeafValue)

Usage:
    python3 scripts/ab_test_learned_value_vs_heuristic_leaf.py --games 60 --depth 1
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

DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "ab_learned_vs_heuristic_leaf_log.jsonl")
DEFAULT_MODEL_PATH = os.path.join(REPO_ROOT, "models", "leaf_value_v5.joblib")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--depth", type=int, default=1, choices=(1, 2))
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    from scripts.matchup_breakdown import wilson_interval  # noqa: E402

    if args.summarize_only:
        records = []
        if os.path.exists(args.log_path):
            with open(args.log_path) as f:
                records = [json.loads(line) for line in f if line.strip()]
        decided = [r for r in records if r.get("depth") == args.depth and r.get("learned_won") is not None]
        wins = sum(1 for r in decided if r["learned_won"])
        n = len(decided)
        print(f"=== All logged depth={args.depth} results in {args.log_path} ===")
        if n:
            lo, hi = wilson_interval(wins, n)
            print(f"Learned-leaf win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
        else:
            print("No decided games logged at this depth yet.")
        return

    from cg import game  # noqa: E402
    from pokemon_agent.agent import build_agent  # noqa: E402
    from pokemon_agent.search.expectimax import ExpectimaxConfig  # noqa: E402

    if not os.path.exists(args.model_path):
        print(f"No trained model at {args.model_path} -- run scripts/train_leaf_value_model.py first.")
        return

    deck = _load_deck_file(args.deck)

    heuristic_leaf_agent = build_agent(deck, search_config=ExpectimaxConfig(
        enabled=True, depth=args.depth, leaf_value_mode="heuristic",
    ))
    learned_leaf_agent = build_agent(deck, search_config=ExpectimaxConfig(
        enabled=True, depth=args.depth, leaf_value_mode="learned", leaf_value_model_path=args.model_path,
    ))

    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)
    start_id = 0
    if os.path.exists(args.log_path):
        with open(args.log_path) as f:
            for line in f:
                if line.strip():
                    start_id = max(start_id, json.loads(line)["game_id"] + 1)

    records = []
    learned_used_count = 0
    with open(args.log_path, "a") as logf:
        for i in range(args.games):
            learned_plays_seat0 = (i % 2 == 0)
            seat0_agent = learned_leaf_agent if learned_plays_seat0 else heuristic_leaf_agent
            seat1_agent = heuristic_leaf_agent if learned_plays_seat0 else learned_leaf_agent

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

            telemetry = learned_leaf_agent.get_search_telemetry()
            if telemetry is not None and telemetry.leaf_value_mode_used == "learned":
                learned_used_count += 1

            decided = result in (0, 1, 2)
            learned_won = None
            if decided and result in (0, 1):
                learned_won = (result == 0) == learned_plays_seat0

            record = {
                "game_id": start_id + i,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "depth": args.depth,
                "learned_plays_seat0": learned_plays_seat0,
                "result": result if decided else None,
                "learned_won": learned_won,
                "turns": obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None,
                "steps": steps,
                "stopped_reason": stopped_reason,
            }
            records.append(record)
            logf.write(json.dumps(record) + "\n")
            print(f"game {record['game_id']}: learned_seat={'0' if learned_plays_seat0 else '1'} "
                  f"result={result} learned_won={learned_won} steps={steps} stopped=({stopped_reason})")

    decided = [r for r in records if r["learned_won"] is not None]
    wins = sum(1 for r in decided if r["learned_won"])
    n = len(decided)
    print(f"\n=== Learned leaf (depth={args.depth}) vs. heuristic leaf, {n}/{len(records)} real games decided ===")
    if n:
        lo, hi = wilson_interval(wins, n)
        print(f"Learned-leaf win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
    else:
        print("No decided games -- cannot report a win rate.")
    print(f"Learned model actually consulted in {learned_used_count}/{len(records)} games "
          f"(should equal games -- confirms the model loaded and was used, not silently skipped)")
    print(f"Appended {len(records)} record(s) to {args.log_path}")


if __name__ == "__main__":
    main()

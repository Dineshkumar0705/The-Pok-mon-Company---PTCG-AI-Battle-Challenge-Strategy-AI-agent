#!/usr/bin/env python3
"""Run real games through the actual cg engine and append genuine results to
a replay log (JSON Lines, one record per game).

This does NOT fabricate matchup data. Every record here comes from an actual
game played through the real engine in this process. By default both seats
play the same deck (deck.csv) with the same agent -- a real mirror-match
self-play run, tagged opponent_archetype="mirror". If you have an actual
opposing decklist (60 card IDs, one per line, same format as deck.csv), pass
it with --opponent-deck and --opponent-archetype to log real data for that
matchup instead. Nothing here invents results for matchups that weren't
actually played.

Schema (one JSON object per line, appended to replays/raw/replay_log.jsonl):
    {
        "game_id": int,             # monotonically increasing within a log file
        "opponent_archetype": str,  # "mirror" unless --opponent-deck given
        "result": int,              # 0 = our seat (player 0) won,
                                     # 1 = opponent (player 1) won, 2 = draw
        "our_win": bool,
        "turns": int,
        "steps": int,               # raw agent decisions made, not game turns
        "stopped_reason": str,      # "finished" (real win/loss/draw), or
                                     # "max_steps"/"no_select"/"engine_select_rejected"
                                     # if something else ended the loop early
    }

Usage:
    python3 scripts/replay_logger.py --games 20
    python3 scripts/replay_logger.py --games 20 --opponent-deck path/to/deck.csv \\
        --opponent-archetype "water_control"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "replay_log.jsonl")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--opponent-deck", default=None,
                         help="60-card-ID file for the opposing seat; defaults to --deck (mirror match)")
    parser.add_argument("--opponent-archetype", default="mirror")
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    args = parser.parse_args()

    from cg import game  # noqa: E402  (import here: requires the real engine)
    from pokemon_agent.agent import build_agent  # noqa: E402

    our_deck = _load_deck_file(args.deck)
    opp_deck = _load_deck_file(args.opponent_deck) if args.opponent_deck else our_deck
    our_agent = build_agent(our_deck)
    opp_agent = build_agent(opp_deck)

    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)

    # game_id continues from whatever is already logged, so repeated runs
    # append rather than collide.
    start_id = 0
    if os.path.exists(args.log_path):
        with open(args.log_path) as f:
            for line in f:
                if line.strip():
                    start_id = max(start_id, json.loads(line)["game_id"] + 1)

    records = []
    with open(args.log_path, "a") as logf:
        for i in range(args.games):
            obs_dict, _start = game.battle_start(our_deck, opp_deck)
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

                current = obs_dict["current"]
                seat = current["yourIndex"]
                choice = our_agent(obs_dict) if seat == 0 else opp_agent(obs_dict)

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
            record = {
                "game_id": start_id + i,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "opponent_archetype": args.opponent_archetype,
                "result": result if decided else None,
                "our_win": (result == 0) if decided else None,
                "turns": obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None,
                "steps": steps,
                "stopped_reason": stopped_reason,
            }
            records.append(record)
            logf.write(json.dumps(record) + "\n")
            print(f"game {record['game_id']}: result={result} steps={steps} "
                  f"stopped=({stopped_reason})")

    decided = [r for r in records if r["result"] in (0, 1)]
    if decided:
        win_rate = sum(1 for r in decided if r["our_win"]) / len(decided)
        print(f"\n{len(decided)}/{len(records)} games reached a real result. "
              f"Win rate vs '{args.opponent_archetype}': {win_rate:.1%}")
    else:
        print(f"\n0/{len(records)} games reached a real result before the known "
              f"engine edge case (see module docstring) -- no win rate to report.")
    print(f"Appended {len(records)} record(s) to {args.log_path}")


if __name__ == "__main__":
    main()

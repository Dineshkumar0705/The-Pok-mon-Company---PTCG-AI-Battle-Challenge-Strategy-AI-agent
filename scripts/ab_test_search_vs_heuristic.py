#!/usr/bin/env python3
"""The real validation gate named in the v3-upgrade doc's build-order table:
v1/v2 heuristic-only vs. v4's L1 expectimax search, played as real self-play
mirror-match games through the actual cg engine -- nothing simulated,
nothing estimated. Seats alternate each game (agent under test plays seat 0
on even games, seat 1 on odd games) so first-move advantage (documented in
README.md's existing mirror-match data) cancels out of the comparison
instead of confounding it.

This script is the ONLY thing that gets to flip config/search_config.yaml's
`enabled: false` to `true` in good conscience -- per this project's stated
rule, nothing moves from "explored" to "shipped" without a head-to-head
win against the already-validated baseline, with a reported confidence
interval, not a vibe.

Also reports real search telemetry (candidates evaluated, engine-call count,
transposition-table hit rate, fallback rate) pulled from the agent's own
introspection hooks -- not asserted, read off what actually happened during
the run.

Usage:
    python3 scripts/ab_test_search_vs_heuristic.py --games 30 --depth 1
    python3 scripts/ab_test_search_vs_heuristic.py --games 30 --depth 2 --max-branch-steps 8
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

DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "ab_search_vs_heuristic_log.jsonl")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--depth", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--max-branch-steps", type=int, default=8)
    parser.add_argument("--no-belief", action="store_true",
                         help="disable belief-informed determinization, use uniform sampling instead")
    parser.add_argument("--policy-top-k", type=int, default=None,
                         help="v7: only search the top-K ATTACK candidates by baseline heuristic "
                              "score; default (None) searches all, same as v4/v5")
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    parser.add_argument("--summarize-only", action="store_true",
                         help="skip playing games; just report aggregate stats "
                              "already in --log-path, filtered to --depth")
    args = parser.parse_args()

    from scripts.matchup_breakdown import wilson_interval  # noqa: E402

    if args.summarize_only:
        records = []
        if os.path.exists(args.log_path):
            with open(args.log_path) as f:
                records = [json.loads(line) for line in f if line.strip()]
        decided = [r for r in records if r.get("search_depth") == args.depth and r.get("search_won") is not None]
        wins = sum(1 for r in decided if r["search_won"])
        n = len(decided)
        print(f"=== All logged depth={args.depth} results in {args.log_path} ===")
        if n:
            lo, hi = wilson_interval(wins, n)
            print(f"Search win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
        else:
            print("No decided games logged at this depth yet.")
        return

    from cg import game  # noqa: E402
    from pokemon_agent.agent import build_agent  # noqa: E402
    from pokemon_agent.search.expectimax import ExpectimaxConfig  # noqa: E402

    deck = _load_deck_file(args.deck)

    heuristic_agent = build_agent(deck, search_config=ExpectimaxConfig(enabled=False))
    search_config = ExpectimaxConfig(
        enabled=True, depth=args.depth, max_branch_steps=args.max_branch_steps,
        belief_informed_determinization=not args.no_belief,
        policy_top_k=args.policy_top_k,
    )
    search_agent = build_agent(deck, search_config=search_config)

    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)
    start_id = 0
    if os.path.exists(args.log_path):
        with open(args.log_path) as f:
            for line in f:
                if line.strip():
                    start_id = max(start_id, json.loads(line)["game_id"] + 1)

    records = []
    telemetry_totals = dict(
        decisions_with_search=0, candidates_considered=0, candidates_evaluated=0,
        engine_calls=0, engine_errors=0, cache_hits=0, cache_misses=0, fallbacks=0,
    )

    with open(args.log_path, "a") as logf:
        for i in range(args.games):
            search_plays_seat0 = (i % 2 == 0)
            seat0_agent = search_agent if search_plays_seat0 else heuristic_agent
            seat1_agent = heuristic_agent if search_plays_seat0 else search_agent

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

            telemetry = search_agent.get_search_telemetry()
            if telemetry is not None and telemetry.attempted:
                telemetry_totals["decisions_with_search"] += 1
                telemetry_totals["candidates_considered"] += telemetry.candidates_considered
                telemetry_totals["candidates_evaluated"] += telemetry.candidates_evaluated
                telemetry_totals["engine_calls"] += telemetry.engine_calls
                telemetry_totals["engine_errors"] += telemetry.engine_errors
                telemetry_totals["cache_hits"] += telemetry.cache_hits
                telemetry_totals["cache_misses"] += telemetry.cache_misses
                if telemetry.fell_back_to_heuristic:
                    telemetry_totals["fallbacks"] += 1

            decided = result in (0, 1, 2)
            search_won = None
            if decided and result in (0, 1):
                winner_seat = result
                search_won = (winner_seat == 0) == search_plays_seat0

            record = {
                "game_id": start_id + i,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "opponent_archetype": "mirror",
                "search_depth": args.depth,
                "search_plays_seat0": search_plays_seat0,
                "result": result if decided else None,
                "search_won": search_won,
                "turns": obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None,
                "steps": steps,
                "stopped_reason": stopped_reason,
            }
            records.append(record)
            logf.write(json.dumps(record) + "\n")
            print(f"game {record['game_id']}: search_seat={'0' if search_plays_seat0 else '1'} "
                  f"result={result} search_won={search_won} steps={steps} stopped=({stopped_reason})")

    decided = [r for r in records if r["search_won"] is not None]
    wins = sum(1 for r in decided if r["search_won"])
    n = len(decided)
    print(f"\n=== Search (depth={args.depth}) vs. heuristic-only, {n}/{len(records)} real games decided ===")
    if n:
        lo, hi = wilson_interval(wins, n)
        print(f"Search win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
    else:
        print("No decided games -- cannot report a win rate.")

    tt = telemetry_totals
    print("\n=== Real search telemetry (from this run only) ===")
    print(f"Decisions where search actually ran: {tt['decisions_with_search']}")
    print(f"ATTACK candidates considered / evaluated: {tt['candidates_considered']} / {tt['candidates_evaluated']}")
    print(f"Real engine calls (search_begin+search_step): {tt['engine_calls']}")
    print(f"Engine call errors (caught, fell back): {tt['engine_errors']}")
    cache_total = tt["cache_hits"] + tt["cache_misses"]
    if cache_total:
        print(f"Transposition table: {tt['cache_hits']}/{cache_total} hits "
              f"({tt['cache_hits']/cache_total:.1%})")
    else:
        print("Transposition table: no lookups recorded this run.")
    print(f"Full fallback-to-heuristic decisions (search attempted but every candidate failed): {tt['fallbacks']}")
    print(f"\nAppended {len(records)} record(s) to {args.log_path}")


if __name__ == "__main__":
    main()

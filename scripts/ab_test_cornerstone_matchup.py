#!/usr/bin/env python3
"""v7 real cross-archetype validation, closing v6's own stated gap
(docs/v6-architecture.md: "this deck's mirror-match self-play tooling can
never surface this opponent"). Real asymmetric self-play -- this deck
(deck.csv) vs. a real, legal second decklist built around Cornerstone Mask
Ogerpon ex (decks/cornerstone_ogerpon_v7.csv, see docs/v7-architecture.md
for the real card-text sourcing) -- through the actual cg engine, which
already supports asymmetric decks (`game.battle_start(deck0, deck1)`).

Reports TWO real win rates: this deck AS SHIPPED (the v6 fix live) vs. the
Cornerstone deck, and the SAME matchup with the fix's trigger condition
monkeypatched off (ABILITY_ATTACKER_IDS emptied) for this script's own
comparison agent only -- never touching the shipped module. This is the
real, direct, honest test of whether v6's fix matters in a genuine
adversarial matchup, something mirror self-play structurally cannot do.

Usage:
    python3 scripts/ab_test_cornerstone_matchup.py --games 60
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

DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "ab_cornerstone_matchup_log.jsonl")
MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def _play_one(archaludon_agent, cornerstone_agent, archaludon_deck, cornerstone_deck,
              archaludon_plays_seat0: bool):
    from cg import game

    deck0 = archaludon_deck if archaludon_plays_seat0 else cornerstone_deck
    deck1 = cornerstone_deck if archaludon_plays_seat0 else archaludon_deck
    seat0_agent = archaludon_agent if archaludon_plays_seat0 else cornerstone_agent
    seat1_agent = cornerstone_agent if archaludon_plays_seat0 else archaludon_agent

    obs_dict, _start = game.battle_start(deck0, deck1)
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
    archaludon_won = None
    if decided and result in (0, 1):
        winner_seat = result
        archaludon_won = (winner_seat == 0) == archaludon_plays_seat0
    return result, decided, archaludon_won, steps, stopped_reason


def _run_condition(label, games, log_path, start_id, archaludon_agent, cornerstone_agent,
                    archaludon_deck, cornerstone_deck):
    from scripts.matchup_breakdown import wilson_interval

    records = []
    with open(log_path, "a") as logf:
        for i in range(games):
            archaludon_plays_seat0 = (i % 2 == 0)
            result, decided, archaludon_won, steps, stopped_reason = _play_one(
                archaludon_agent, cornerstone_agent, archaludon_deck, cornerstone_deck,
                archaludon_plays_seat0,
            )
            record = {
                "condition": label,
                "game_id": start_id + i,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "opponent_archetype": "cornerstone_ogerpon",
                "archaludon_plays_seat0": archaludon_plays_seat0,
                "result": result if decided else None,
                "archaludon_won": archaludon_won,
                "steps": steps,
                "stopped_reason": stopped_reason,
            }
            records.append(record)
            logf.write(json.dumps(record) + "\n")
            print(f"[{label}] game {record['game_id']}: archaludon_seat="
                  f"{'0' if archaludon_plays_seat0 else '1'} result={result} "
                  f"archaludon_won={archaludon_won} steps={steps} stopped=({stopped_reason})")

    decided = [r for r in records if r["archaludon_won"] is not None]
    wins = sum(1 for r in decided if r["archaludon_won"])
    n = len(decided)
    print(f"\n=== [{label}] Archaludon ex vs. Cornerstone Ogerpon deck, {n}/{len(records)} decided ===")
    if n:
        lo, hi = wilson_interval(wins, n)
        print(f"Archaludon win rate: {wins}/{n} = {wins/n:.1%}  (95% Wilson CI: [{lo:.1%}, {hi:.1%}])")
    else:
        print("No decided games -- cannot report a win rate.")
    return wins, n


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=60,
                         help="games PER condition (fix-live and fix-disabled each get this many)")
    parser.add_argument("--archaludon-deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--cornerstone-deck",
                         default=os.path.join(REPO_ROOT, "decks", "cornerstone_ogerpon_v7.csv"))
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    args = parser.parse_args()

    from pokemon_agent.agent import build_agent
    from pokemon_agent.search.expectimax import ExpectimaxConfig
    from pokemon_agent.threats import cornerstone_ogerpon as cs_module

    archaludon_deck = _load_deck_file(args.archaludon_deck)
    cornerstone_deck = _load_deck_file(args.cornerstone_deck)
    assert len(archaludon_deck) == 60 and len(cornerstone_deck) == 60

    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)
    start_id = 0
    if os.path.exists(args.log_path):
        with open(args.log_path) as f:
            for line in f:
                if line.strip():
                    start_id = max(start_id, json.loads(line)["game_id"] + 1)

    cornerstone_agent = build_agent(cornerstone_deck, search_config=ExpectimaxConfig(enabled=False))

    # Condition 1: fix live (as shipped).
    archaludon_agent_fixed = build_agent(archaludon_deck, search_config=ExpectimaxConfig(enabled=False))
    wins_fixed, n_fixed = _run_condition(
        "fix_live", args.games, args.log_path, start_id,
        archaludon_agent_fixed, cornerstone_agent, archaludon_deck, cornerstone_deck,
    )

    # Condition 2: fix's trigger condition disabled, THIS SCRIPT'S OWN
    # comparison agent only -- never touches the shipped module for anyone
    # else. Restored in a finally block regardless of outcome.
    original_ids = set(cs_module.ABILITY_ATTACKER_IDS)
    try:
        cs_module.ABILITY_ATTACKER_IDS.clear()  # empties the set in place -- is_blocked_by_cornerstone_stance() always False now
        archaludon_agent_unfixed = build_agent(archaludon_deck, search_config=ExpectimaxConfig(enabled=False))
        wins_unfixed, n_unfixed = _run_condition(
            "fix_disabled", args.games, args.log_path, start_id + args.games,
            archaludon_agent_unfixed, cornerstone_agent, archaludon_deck, cornerstone_deck,
        )
    finally:
        cs_module.ABILITY_ATTACKER_IDS.clear()
        cs_module.ABILITY_ATTACKER_IDS.update(original_ids)

    print("\n=== v6 Cornerstone Stance fix: real, direct, cross-archetype comparison ===")
    if n_fixed and n_unfixed:
        from scripts.matchup_breakdown import wilson_interval
        lo_f, hi_f = wilson_interval(wins_fixed, n_fixed)
        lo_u, hi_u = wilson_interval(wins_unfixed, n_unfixed)
        print(f"Fix live:     {wins_fixed}/{n_fixed} = {wins_fixed/n_fixed:.1%} "
              f"(95% CI [{lo_f:.1%}, {hi_f:.1%}])")
        print(f"Fix disabled: {wins_unfixed}/{n_unfixed} = {wins_unfixed/n_unfixed:.1%} "
              f"(95% CI [{lo_u:.1%}, {hi_u:.1%}])")
    print(f"\nAppended records to {args.log_path}")


if __name__ == "__main__":
    main()

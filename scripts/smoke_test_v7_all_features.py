#!/usr/bin/env python3
"""v7 deploy-check (task: "deploy agents to check engineering wiring
mismatch corrections... and code quality"): a real self-play smoke test
with EVERY v7 feature turned on AT ONCE in a single agent --

    ExpectimaxConfig(enabled=True, depth=3, policy_top_k=2,
                      leaf_value_mode="learned",
                      leaf_value_model_path="models/leaf_value_v7.joblib")
    build_agent(..., plan_stability_enabled=True)

Every other v7 test/A/B script in this repo exercises exactly ONE new
feature at a time (by design -- that's what makes each A/B result
attributable to a single variable). None of them prove the features don't
step on each other when combined: depth=3's extra real round now calls the
leaf evaluator more times per decision than depth=2 ever did; policy_top_k
prunes the SAME candidate list plan_stability's bonus is added to; the GBT
leaf evaluator's predict() is now on the hot path for both the depth-3
extra round AND the pruned candidate set. This script's only job is to
play real full games through that combined configuration and confirm nothing
crashes, nothing silently falls back to a fail-closed default in a way
that indicates a wiring bug, and every real telemetry field looks sane.
This is NOT a win-rate A/B (each feature already has its own, honestly
reported, mostly-null real result above) -- it's a wiring/integration
check.

Usage:
    python3 scripts/smoke_test_v7_all_features.py --games 15
"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=15)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--model-path", default=os.path.join(REPO_ROOT, "models", "leaf_value_v7.joblib"))
    args = parser.parse_args()

    from cg import game  # noqa: E402
    from pokemon_agent.agent import build_agent  # noqa: E402
    from pokemon_agent.search.expectimax import ExpectimaxConfig  # noqa: E402

    deck = _load_deck_file(args.deck)

    all_features_config = ExpectimaxConfig(
        enabled=True, depth=3, max_branch_steps=8, policy_top_k=2,
        leaf_value_mode="learned", leaf_value_model_path=args.model_path,
    )
    agent_a = build_agent(deck, search_config=all_features_config, plan_stability_enabled=True)
    agent_b = build_agent(deck, search_config=all_features_config, plan_stability_enabled=True)

    crashes = 0
    finished = 0
    total_leaf_eval_errors = 0
    total_pruned = 0
    total_learned_calls = 0
    total_heuristic_fallback_calls = 0

    for gi in range(args.games):
        obs_dict, _start = game.battle_start(deck, deck)
        result = -1
        steps = 0
        crashed_this_game = False
        try:
            for steps in range(1, MAX_STEPS + 1):
                sel = obs_dict.get("select")
                if sel is None:
                    break
                result = obs_dict.get("current", {}).get("result", -1)
                if result != -1:
                    break
                seat = obs_dict["current"]["yourIndex"]
                choice = agent_a(obs_dict) if seat == 0 else agent_b(obs_dict)
                try:
                    obs_dict = game.battle_select(choice)
                except IndexError:
                    break
                result = obs_dict.get("current", {}).get("result", -1)
                if result != -1:
                    break
        except Exception as e:  # noqa: BLE001 -- exactly what this script exists to catch
            crashed_this_game = True
            crashes += 1
            print(f"game {gi}: CRASH at step {steps}: {type(e).__name__}: {e}")
        finally:
            try:
                game.battle_finish()
            except Exception:
                pass

        if not crashed_this_game and result in (0, 1, 2):
            finished += 1

        for agent, label in ((agent_a, "a"), (agent_b, "b")):
            t = agent.get_search_telemetry()
            if t is not None:
                total_leaf_eval_errors += t.leaf_eval_errors
                total_pruned += t.candidates_pruned_by_policy
                if t.leaf_value_mode_used == "learned":
                    total_learned_calls += 1
                else:
                    total_heuristic_fallback_calls += 1

        print(f"game {gi}: result={result} steps={steps} crashed={crashed_this_game}")

    print(f"\n=== v7 all-features-combined smoke test: {finished}/{args.games} games "
          f"finished cleanly, {crashes} crashed ===")
    print(f"leaf_eval_errors across all decisions: {total_leaf_eval_errors} "
          f"(nonzero here would mean the try/except fallback fired -- expected occasionally, "
          f"just confirming it never propagates as a crash)")
    print(f"candidates_pruned_by_policy fired (nonzero games): "
          f"policy_top_k engaged at least once: {total_pruned > 0}")
    print(f"leaf_value_mode_used == 'learned' in {total_learned_calls} agent-games, "
          f"fell back to 'heuristic' in {total_heuristic_fallback_calls} "
          f"(fallback would mean the v7 model failed to load -- should be 0)")

    if crashes == 0 and finished == args.games and total_heuristic_fallback_calls == 0:
        print("\nPASS -- no crashes, all games finished, learned model never silently fell back.")
    else:
        print("\nFAIL -- see counts above.")


if __name__ == "__main__":
    main()

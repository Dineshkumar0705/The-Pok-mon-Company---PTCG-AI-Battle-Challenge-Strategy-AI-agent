"""Behavioral parity test: the v2 decomposed agent (src/pokemon_agent/agent.py)
must make IDENTICAL decisions to the frozen v1 reference (notebooks/legacy/
main_v1_reference.py) on every real turn of real self-play games through the
actual cg engine.

This is not a mock/fixture test -- it runs the real proprietary battle engine
(vendor/cg, loaded from the user-supplied libcg.so) start to finish across
several full self-play games and diffs both agents' chosen option index at
every single decision point. It is the test that actually caught both real
bugs fixed during development (see git history / README "Bugs found via this
test" section):

  1. `_is_pokemon_type()` compared an enum NAME string against the real
     engine's raw-int `cardType` field, which never matched, so every Pokemon
     card play was silently scored as a generic Trainer.
  2. `build_attack_plan()` returned a brand-new, blank AttackPlan() any time a
     MAIN-context call found no viable attacker this turn, discarding a real
     plan a PRIOR MAIN call in the same turn had already found. v1's `plan`
     is a single object mutated in place across a turn; this call needs
     `previous_plan=` threaded through to reproduce that stickiness.

Game-over detection: the real "did the game end" signal is
`obs["current"]["result"]` (-1 while ongoing, 0/1/2 once a side wins or it's
a draw) -- there is no top-level "result" key on the observation dict. An
earlier version of this harness checked `obs_dict.get("result")` (always
None, since that key doesn't exist at the top level) and so kept calling
battle_select() past the real end of the game every time, which is what
produced an apparently "random" IndexError ~100-170 steps into every single
game. Checking the real field, games complete cleanly and consistently.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_DIR = os.path.join(REPO_ROOT, "notebooks", "legacy")
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
SRC_DIR = os.path.join(REPO_ROOT, "src")

for p in (VENDOR_DIR, SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from cg import game  # noqa: E402
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ENGINE_AVAILABLE,
    reason="Real cg engine (vendor/cg/libcg.so) not available in this environment.",
)

N_GAMES = 8
MAX_STEPS_PER_GAME = 400


def _load_legacy():
    """Fresh import of the frozen v1 reference each call, since it keeps a
    module-level `plan`/`pre_turn` that must not leak state between games."""
    spec = importlib.util.spec_from_file_location(
        "legacy_main_under_test", os.path.join(LEGACY_DIR, "main_v1_reference.py")
    )
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    return legacy


def test_v2_agent_matches_v1_across_real_self_play_games():
    from pokemon_agent.agent import build_agent

    cwd = os.getcwd()
    os.chdir(LEGACY_DIR)  # v1 reads deck.csv relative to cwd
    try:
        legacy = _load_legacy()
        deck = legacy.my_deck
        new_agent = build_agent(deck)

        total_steps = 0
        total_mismatches = 0
        mismatch_details = []

        for gnum in range(1, N_GAMES + 1):
            obs_dict, _start_data = game.battle_start(deck, deck)
            try:
                for _ in range(MAX_STEPS_PER_GAME):
                    sel = obs_dict.get("select")
                    if sel is None:
                        break
                    if obs_dict.get("current", {}).get("result", -1) != -1:
                        break  # game over -- see module docstring on the result field

                    legacy_choice = legacy.agent(obs_dict)
                    new_choice = new_agent(obs_dict)
                    total_steps += 1

                    if legacy_choice != new_choice:
                        total_mismatches += 1
                        mismatch_details.append(
                            f"game {gnum}: context={sel.get('context')} "
                            f"legacy={legacy_choice} new={new_choice}"
                        )

                    try:
                        obs_dict = game.battle_select(legacy_choice)
                    except IndexError:
                        break

                    if obs_dict.get("current", {}).get("result", -1) != -1:
                        break
            finally:
                try:
                    game.battle_finish()
                except Exception:
                    pass

        assert total_steps > 100, (
            f"Only {total_steps} real decision steps were exercised across "
            f"{N_GAMES} games -- too few to trust this as real coverage."
        )
        assert total_mismatches == 0, (
            f"{total_mismatches}/{total_steps} decisions diverged from v1:\n"
            + "\n".join(mismatch_details)
        )
    finally:
        os.chdir(cwd)

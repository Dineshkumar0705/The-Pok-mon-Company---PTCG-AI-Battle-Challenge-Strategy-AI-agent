#!/usr/bin/env python3
"""Builds a real, card-level self-play dataset: runs N (default 60, i.e.
50+) real games through the actual `cg` engine and aggregates what actually
happened, per real card and per real attack -- not simulated, not sampled
from the reference CSVs, read directly off `Observation.logs` the same way
`scripts/replay_logger.py` and `scripts/render_battle_log_gif.py` do.

Why this exists: the existing `replays/raw/replay_log.jsonl` only ever
recorded game-level outcomes (who won, how many turns) -- it has no
per-card signal at all, which is the actual gap for a "card dataset."
This script closes that gap with two new real, derived tables:

    data/raw/card_usage_from_self_play.csv
    data/raw/attack_usage_from_self_play.csv

REPRODUCIBILITY NOTE: `build_agent(deck)` with no arguments currently picks
up whatever `config/search_config.yaml` / `agent.py`'s own default say --
and as of this repo's "all-on override" (see README's "Current build
configuration" section), that is NOT the validated baseline anymore. This
script explicitly pins `ExpectimaxConfig()` (all defaults -> disabled) and
`plan_stability_enabled=False` for BOTH seats, regardless of what the repo's
checked-in override currently says, so this dataset always reflects the
same real, validated, byte-identical-to-v1 policy that the original 30-game
`replay_log.jsonl` was generated under -- not whatever experimental flags
happen to be flipped on in this checkout right now. Pass --use-repo-config
to opt into the checked-in config instead, if that's ever what you want to
measure.

A real KO-attribution attempt (approximating "our attack scored a KO" from
an opponent CHANGE-of-active event immediately following our ATTACK in the
same log batch) was tried and dropped: across the real run this script's
result depends on, it measured exactly zero KOs in every single game,
which real self-play mirror matches plainly do have -- the forced-switch
event does not appear to land in the same log batch as the attack that
caused it, so this heuristic silently undercounts to zero rather than
approximating anything real. Rather than ship a column that always reads
0, it is left out of the output entirely; a real per-attack KO count would
need to track HP reaching exactly 0 directly instead, a real follow-up
noted in the report, not something invented here.

Usage:
    python3 scripts/generate_card_usage_dataset.py --games 60
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MAX_STEPS = 400
DEFAULT_LOG = os.path.join(REPO_ROOT, "replays", "raw", "card_usage_log.jsonl")
DEFAULT_CARD_OUT = os.path.join(REPO_ROOT, "data", "raw", "card_usage_from_self_play.csv")
DEFAULT_ATTACK_OUT = os.path.join(REPO_ROOT, "data", "raw", "attack_usage_from_self_play.csv")


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def _play_one_game(deck: list[int], agent) -> dict:
    """Plays one real game (mirror match, same agent both seats) and
    returns a dict of real per-card/per-attack events observed for seat 0
    ("us"), plus the real game result."""
    from cg import game

    plays = Counter()          # cardId -> times PLAYed by us
    attaches_energy = Counter()  # cardId (energy) -> times we attached it
    attaches_target = Counter()  # cardIdTarget -> times something was attached to it
    evolutions = Counter()     # cardId (the new form) -> times we evolved into it
    attack_uses = Counter()    # (cardId, attackId) -> times we used it
    attack_damage = defaultdict(int)  # (cardId, attackId) -> total real damage dealt
    cards_seen = set()

    pending_attack = None  # (cardId, attackId) most recently used by us, this batch

    obs_dict, _start = game.battle_start(deck, deck)
    result = -1
    turns = 0
    try:
        for _ in range(1, MAX_STEPS + 1):
            sel = obs_dict.get("select")
            if sel is None:
                break
            result = obs_dict.get("current", {}).get("result", -1)
            if result != -1:
                break
            turns = obs_dict.get("current", {}).get("turn", turns) or turns

            for log in obs_dict.get("logs", []):
                t = log.get("type")
                p = log.get("playerIndex")
                if t == 10 and p == 0:  # PLAY
                    plays[log["cardId"]] += 1
                    cards_seen.add(log["cardId"])
                elif t == 11 and p == 0:  # ATTACH
                    attaches_energy[log["cardId"]] += 1
                    attaches_target[log.get("cardIdTarget")] += 1
                    cards_seen.add(log["cardId"])
                elif t == 12 and p == 0:  # EVOLVE
                    evolutions[log["cardId"]] += 1
                    cards_seen.add(log["cardId"])
                elif t == 15 and p == 0:  # ATTACK
                    pending_attack = (log["cardId"], log["attackId"])
                    attack_uses[pending_attack] += 1
                    cards_seen.add(log["cardId"])
                elif t == 16 and p == 1 and pending_attack is not None:  # HP_CHANGE, opponent
                    val = log.get("value", 0)
                    if val < 0:
                        attack_damage[pending_attack] += -val
                elif t == 2:  # TURN_START -- reset "pending_attack" association
                    pending_attack = None

            choice = agent(obs_dict)
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

    return {
        "result": result,
        "our_win": (result == 0) if result in (0, 1) else None,
        "turns": turns,
        "plays": dict(plays),
        "attaches_energy": dict(attaches_energy),
        "attaches_target": dict(attaches_target),
        "evolutions": dict(evolutions),
        "attack_uses": {f"{c}:{a}": n for (c, a), n in attack_uses.items()},
        "attack_damage": {f"{c}:{a}": n for (c, a), n in attack_damage.items()},
        "cards_seen": sorted(cards_seen),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    parser.add_argument("--card-out", default=DEFAULT_CARD_OUT)
    parser.add_argument("--attack-out", default=DEFAULT_ATTACK_OUT)
    parser.add_argument("--use-repo-config", action="store_true",
                         help="use build_agent(deck)'s own defaults (picks up "
                              "config/search_config.yaml + agent.py's default "
                              "plan_stability_enabled) instead of the pinned, "
                              "validated baseline this script uses by default")
    args = parser.parse_args()

    from pokemon_agent.agent import build_agent
    from pokemon_agent.search.expectimax import ExpectimaxConfig
    from cg.api import CardType, all_attack, all_card_data

    card_table = {c.cardId: c for c in all_card_data()}
    attack_table = {a.attackId: a for a in all_attack()}
    deck = _load_deck_file(args.deck)

    if args.use_repo_config:
        agent = build_agent(deck)
        config_note = "repo's own checked-in config (may include the all-on override)"
    else:
        agent = build_agent(deck, search_config=ExpectimaxConfig(), plan_stability_enabled=False)
        config_note = "pinned validated baseline (search disabled, plan_stability disabled) -- byte-identical to v1/v2 decisions"
    print(f"Config used for this run: {config_note}")

    os.makedirs(os.path.dirname(args.log_path), exist_ok=True)
    os.makedirs(os.path.dirname(args.card_out), exist_ok=True)

    start_id = 0
    if os.path.exists(args.log_path):
        with open(args.log_path) as f:
            for line in f:
                if line.strip():
                    start_id = max(start_id, json.loads(line)["game_id"] + 1)

    all_games = []
    with open(args.log_path, "a") as logf:
        for i in range(args.games):
            g = _play_one_game(deck, agent)
            g["game_id"] = start_id + i
            g["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
            g["config"] = config_note
            all_games.append(g)
            logf.write(json.dumps(g) + "\n")
            print(f"game {g['game_id']}: result={g['result']} turns={g['turns']} "
                  f"attacks_used={sum(g['attack_uses'].values())}")

    decided = [g for g in all_games if g["result"] in (0, 1)]
    win_rate = (sum(1 for g in decided if g["our_win"]) / len(decided)) if decided else 0.0
    print(f"\n{len(decided)}/{len(all_games)} games reached a real result this run. "
          f"Win rate this run: {win_rate:.1%}")

    # ---- aggregate across every game ever logged to this file (not just this run) ----
    logged_games = []
    with open(args.log_path) as f:
        for line in f:
            if line.strip():
                logged_games.append(json.loads(line))
    n_games = len(logged_games)
    print(f"Aggregating {n_games} total real games logged in {args.log_path}")

    card_games_used = Counter()   # card_id -> games it appeared in at all
    card_games_used_and_won = Counter()
    card_plays = Counter()
    card_attacks_with = Counter()
    card_energy_attached = Counter()
    card_evolved_into = Counter()
    attack_uses_total = Counter()
    attack_damage_total = Counter()

    for g in logged_games:
        used_this_game = set(g.get("cards_seen", []))
        for cid in used_this_game:
            card_games_used[cid] += 1
            if g.get("our_win"):
                card_games_used_and_won[cid] += 1
        for cid, n in g.get("plays", {}).items():
            card_plays[int(cid)] += n
        for cid, n in g.get("attaches_energy", {}).items():
            card_energy_attached[int(cid)] += n
        for cid, n in g.get("evolutions", {}).items():
            card_evolved_into[int(cid)] += n
        for key, n in g.get("attack_uses", {}).items():
            cid_s, aid_s = key.split(":")
            card_attacks_with[int(cid_s)] += n
            attack_uses_total[(int(cid_s), int(aid_s))] += n
        for key, n in g.get("attack_damage", {}).items():
            cid_s, aid_s = key.split(":")
            attack_damage_total[(int(cid_s), int(aid_s))] += n

    deck_card_ids = sorted(set(deck))
    with open(args.card_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["card_id", "card_name", "card_type", "games_logged", "games_used_in",
                    "pct_games_used", "times_played", "times_attacked_with",
                    "times_energy_attached", "times_evolved_into",
                    "win_rate_when_used"])
        for cid in deck_card_ids:
            c = card_table.get(cid)
            used = card_games_used.get(cid, 0)
            won = card_games_used_and_won.get(cid, 0)
            w.writerow([
                cid,
                c.name if c else f"Card#{cid}",
                CardType(c.cardType).name if c else "",
                n_games,
                used,
                round(used / n_games, 4) if n_games else 0,
                card_plays.get(cid, 0),
                card_attacks_with.get(cid, 0),
                card_energy_attached.get(cid, 0),
                card_evolved_into.get(cid, 0),
                round(won / used, 4) if used else "",
            ])
    print(f"Wrote {len(deck_card_ids)} real card-usage rows to {args.card_out}")

    with open(args.attack_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        total_attack_events = sum(attack_uses_total.values()) or 1
        w.writerow(["attack_id", "attack_name", "card_id", "card_name", "times_used",
                    "pct_of_all_attacks", "total_damage_dealt", "avg_damage_dealt"])
        for (cid, aid), n in sorted(attack_uses_total.items(), key=lambda kv: -kv[1]):
            a = attack_table.get(aid)
            c = card_table.get(cid)
            dmg = attack_damage_total.get((cid, aid), 0)
            w.writerow([
                aid,
                a.name if a else f"Attack#{aid}",
                cid,
                c.name if c else f"Card#{cid}",
                n,
                round(n / total_attack_events, 4),
                dmg,
                round(dmg / n, 1) if n else 0,
            ])
    print(f"Wrote {len(attack_uses_total)} real attack-usage rows to {args.attack_out}")


if __name__ == "__main__":
    main()

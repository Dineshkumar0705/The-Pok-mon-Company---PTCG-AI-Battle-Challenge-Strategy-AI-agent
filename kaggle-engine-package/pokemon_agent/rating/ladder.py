"""Local matchup-conditioned rating ladder.

This is the mechanism behind the writeup's "avoids over-reliance on specific
matchups" claim: instead of one aggregate win rate, it tracks a separate Elo
rating PER (agent, opponent_archetype) pair, fed directly by
replays/raw/replay_log.jsonl (the real records scripts/replay_logger.py
writes). A single strong archetype can't hide a bad matchup here -- each one
is visible on its own.

Real TrueSkill (a full Bayesian skill-rating model with per-player variance,
draw margins, and multi-team support) is a meaningfully bigger dependency and
algorithm than this project needs for a two-agent, single-deck ladder; a
standard Elo update captures the same "who is beating whom, and by how
reliably" signal for this scope with no extra machinery. If a future version
tracks many distinct agent variants (v1 vs v2 vs v3 experiments) rather than
one agent across opponent archetypes, upgrading this to real TrueSkill would
be a reasonable, scoped next step -- noted honestly rather than claimed now.

v7 (docs/v7-architecture.md): that "future version" arrived, and turned out
not to need TrueSkill after all -- `record_match()` below is the same named
next step, but implemented as standard symmetric two-sided Elo (both sides
of a direct game are just two more named entries in the same dict this
class already keyed by opponent archetype), not a new algorithm or
dependency. `scripts/run_ladder_pool.py` is the first real caller: this
project's own agent variants (heuristic, v4 search at two depths, v5's
learned leaf), round-robinned through real self-play and fed in here.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


DEFAULT_RATING = 1500.0
DEFAULT_K = 24.0


@dataclass
class RatingEntry:
    rating: float = DEFAULT_RATING
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return self.wins / decided if decided else None


def expected_score(rating_a: float, rating_b: float) -> float:
    """Standard Elo expected-score formula."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


class MatchupLadder:
    """One Elo rating per opponent_archetype, all keyed under a single agent
    identity (this project ships one agent, so `agent_id` defaults to that;
    pass a different id to track multiple agent variants side by side)."""

    def __init__(self, k: float = DEFAULT_K):
        self.k = k
        self._entries: dict[str, RatingEntry] = {}

    def entry(self, archetype: str) -> RatingEntry:
        return self._entries.setdefault(archetype, RatingEntry())

    def record_result(self, archetype: str, our_win: bool | None, opponent_rating: float = DEFAULT_RATING):
        """our_win: True/False for a decided game, None for a draw."""
        e = self.entry(archetype)
        e.games += 1
        if our_win is None:
            e.draws += 1
            actual = 0.5
        elif our_win:
            e.wins += 1
            actual = 1.0
        else:
            e.losses += 1
            actual = 0.0
        expected = expected_score(e.rating, opponent_rating)
        e.rating += self.k * (actual - expected)

    def record_match(self, agent_a: str, agent_b: str, a_won: bool | None):
        """v7: symmetric two-sided Elo update for a direct agent-vs-agent
        game. `agent_a`/`agent_b` are tracked as their own entries in the
        SAME dict this class already uses for opponent archetypes -- to
        this class, an agent identity and an opponent archetype are both
        just "a named thing with a rating." Each side is updated once,
        using the OTHER side's rating from just BEFORE this game (not
        after, which would double-count the game's own effect on one side
        into the other's expected-score calculation). `a_won`:
        True/False/None (draw), from `agent_a`'s perspective.
        """
        rating_a = self.entry(agent_a).rating
        rating_b = self.entry(agent_b).rating
        self.record_result(agent_a, our_win=a_won, opponent_rating=rating_b)
        b_won = None if a_won is None else (not a_won)
        self.record_result(agent_b, our_win=b_won, opponent_rating=rating_a)

    def load_replay_log(self, log_path: str):
        """Replay every record in a replay_logger.py JSONL log through
        record_result, in file order, so the ladder reflects the real,
        already-played games -- not synthetic data."""
        if not os.path.exists(log_path):
            return
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                result = rec.get("result")
                our_win = None if result == 2 else (True if result == 0 else (False if result == 1 else None))
                if result is None:
                    continue  # game never finished -- not a real data point
                self.record_result(rec["opponent_archetype"], our_win)

    def summary(self) -> dict[str, dict]:
        return {
            archetype: {
                "rating": round(e.rating, 1),
                "games": e.games,
                "win_rate": e.win_rate,
            }
            for archetype, e in sorted(self._entries.items())
        }

from __future__ import annotations

from pokemon_agent.rating.ladder import MatchupLadder, expected_score, DEFAULT_RATING


def test_expected_score_symmetric_at_equal_rating():
    assert expected_score(1500, 1500) == 0.5


def test_expected_score_favors_higher_rating():
    assert expected_score(1600, 1400) > 0.5
    assert expected_score(1400, 1600) < 0.5


def test_record_result_moves_rating_up_on_win_down_on_loss():
    ladder = MatchupLadder()
    ladder.record_result("mirror", our_win=True)
    assert ladder.entry("mirror").rating > DEFAULT_RATING

    ladder2 = MatchupLadder()
    ladder2.record_result("mirror", our_win=False)
    assert ladder2.entry("mirror").rating < DEFAULT_RATING


def test_matchups_tracked_independently():
    ladder = MatchupLadder()
    for _ in range(5):
        ladder.record_result("mirror", our_win=True)
    for _ in range(5):
        ladder.record_result("water_control", our_win=False)
    summary = ladder.summary()
    assert summary["mirror"]["win_rate"] == 1.0
    assert summary["water_control"]["win_rate"] == 0.0
    assert summary["mirror"]["rating"] > summary["water_control"]["rating"]


def test_record_match_updates_both_sides_symmetrically():
    ladder = MatchupLadder()
    ladder.record_match("agent_a", "agent_b", a_won=True)
    assert ladder.entry("agent_a").rating > DEFAULT_RATING
    assert ladder.entry("agent_b").rating < DEFAULT_RATING
    # Equal ratings pre-game -> the standard Elo update is symmetric in
    # magnitude (winner gains exactly what the loser loses).
    gain = ladder.entry("agent_a").rating - DEFAULT_RATING
    loss = DEFAULT_RATING - ladder.entry("agent_b").rating
    assert abs(gain - loss) < 1e-9
    assert ladder.entry("agent_a").wins == 1
    assert ladder.entry("agent_b").losses == 1


def test_record_match_draw_leaves_ratings_at_start_when_equal():
    ladder = MatchupLadder()
    ladder.record_match("agent_a", "agent_b", a_won=None)
    assert ladder.entry("agent_a").rating == DEFAULT_RATING  # expected 0.5, actual 0.5 at equal ratings
    assert ladder.entry("agent_b").rating == DEFAULT_RATING
    assert ladder.entry("agent_a").draws == 1
    assert ladder.entry("agent_b").draws == 1


def test_record_match_uses_pregame_ratings_for_both_updates():
    """A real bug this design has to avoid: updating agent_a's rating
    before reading it as agent_b's opponent_rating would let one game
    double-count itself into the other side's expected score."""
    ladder = MatchupLadder()
    ladder.record_result("agent_a", our_win=True)  # agent_a already has a real history: rating != DEFAULT_RATING
    rating_a_before = ladder.entry("agent_a").rating
    assert rating_a_before != DEFAULT_RATING

    ladder.record_match("agent_a", "agent_b", a_won=False)
    # agent_b's update must have used agent_a's PRE-this-game rating
    # (rating_a_before), not a value already bumped by this same call.
    expected_b_gain = ladder.k * (1.0 - expected_score(DEFAULT_RATING, rating_a_before))
    assert abs((ladder.entry("agent_b").rating - DEFAULT_RATING) - expected_b_gain) < 1e-9


def test_load_replay_log_matches_manual_replay(tmp_path):
    import json
    log = tmp_path / "log.jsonl"
    records = [
        {"opponent_archetype": "mirror", "result": 0},  # win
        {"opponent_archetype": "mirror", "result": 1},  # loss
        {"opponent_archetype": "mirror", "result": None},  # unfinished -- must be skipped
        {"opponent_archetype": "stall", "result": 2},  # draw
    ]
    with open(log, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    ladder = MatchupLadder()
    ladder.load_replay_log(str(log))
    summary = ladder.summary()
    assert summary["mirror"]["games"] == 2  # the unfinished record was skipped
    assert summary["stall"]["games"] == 1
    assert summary["stall"]["win_rate"] is None  # only a draw recorded, no decided games

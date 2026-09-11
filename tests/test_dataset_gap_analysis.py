"""Pure-file tests for the v3 dataset-gap-analysis deliverables: the new
effect-tag enrichment tables and the real 60-game card/attack-usage
dataset. No live engine needed -- these just check the CSVs that
scripts/build_effect_tag_datasets.py and
scripts/generate_card_usage_dataset.py already produced are well-formed
and internally consistent with the rest of data/raw/.
"""
import csv
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data", "raw")


def _read_csv(name):
    path = os.path.join(DATA_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_attack_effect_tags_cover_every_real_attack():
    attacks = _read_csv("attacks_enriched.csv")
    tags = _read_csv("attack_effect_tags.csv")
    assert len(tags) == len(attacks), (
        "attack_effect_tags.csv must have exactly one row per real attack "
        "in attacks_enriched.csv"
    )
    attack_ids = {a["attack_id"] for a in attacks}
    tag_ids = {t["attack_id"] for t in tags}
    assert attack_ids == tag_ids, "attack_id sets must match exactly"


def test_ability_trigger_tags_cover_every_real_ability():
    abilities = _read_csv("abilities_enriched.csv")
    tags = _read_csv("ability_trigger_tags.csv")
    assert len(tags) == len(abilities)


def test_attack_effect_tag_columns_are_real_booleans():
    tags = _read_csv("attack_effect_tags.csv")
    flag_cols = [c for c in tags[0].keys() if c not in ("attack_id", "attack_name", "card_id", "card_name")]
    assert len(flag_cols) >= 10, "expected the full real keyword-tag set to be present"
    for row in tags[:50]:
        for c in flag_cols:
            assert row[c] in ("0", "1"), f"{c} must be a real 0/1 flag, got {row[c]!r}"


def test_a_known_real_card_gets_the_right_tag():
    # Metal Defender (Archaludon ex, attack_id 253) is a plain damage attack
    # with no printed effect text -- every effect flag should be 0.
    tags = _read_csv("attack_effect_tags.csv")
    row = next(t for t in tags if t["attack_id"] == "253")
    flag_cols = [c for c in row.keys() if c not in ("attack_id", "attack_name", "card_id", "card_name")]
    assert all(row[c] == "0" for c in flag_cols), (
        "Metal Defender has no printed effect text in this dataset; "
        "every keyword tag should read 0, not a false positive"
    )


def test_card_usage_dataset_real_games_at_least_fifty():
    log_path = os.path.join(REPO_ROOT, "replays", "raw", "card_usage_log.jsonl")
    with open(log_path) as f:
        n_games = sum(1 for line in f if line.strip())
    assert n_games >= 50, (
        f"card_usage_log.jsonl has {n_games} real logged games, expected >= 50"
    )


def test_card_usage_csv_win_rates_are_plausible_fractions():
    rows = _read_csv("card_usage_from_self_play.csv")
    assert len(rows) > 0
    for r in rows:
        if r["win_rate_when_used"] != "":
            wr = float(r["win_rate_when_used"])
            assert 0.0 <= wr <= 1.0, f"{r['card_name']}: win_rate_when_used out of range: {wr}"
        pct = float(r["pct_games_used"])
        assert 0.0 <= pct <= 1.0


def test_attack_usage_csv_damage_is_nonnegative_and_consistent():
    rows = _read_csv("attack_usage_from_self_play.csv")
    assert len(rows) > 0
    for r in rows:
        times_used = int(r["times_used"])
        total_damage = int(r["total_damage_dealt"])
        assert times_used > 0
        assert total_damage >= 0
        if times_used:
            expected_avg = round(total_damage / times_used, 1)
            assert abs(expected_avg - float(r["avg_damage_dealt"])) < 0.05

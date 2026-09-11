from __future__ import annotations

from pokemon_agent.card_data import (
    DEFAULT_ENRICHED_CSV,
    CardRecord,
    load_card_records,
)

# Real card IDs, verified against both data/raw/EN_Card_Data_canonical.csv
# and the live engine (see data/raw/DATASET_UPGRADE_REPORT.md):
ARCHALUDON_EX = 190       # this deck's own key attacker -- a real `ex` Pokemon, not Mega
MEGA_LUCARIO_EX = 678     # real Mega Evolution ex: ex=False, megaEx=True (engine ground truth)
MEGANIUM = 710            # real non-Mega card whose name merely starts with "Mega"


def test_attribute_names_match_what_attack_plans_py_actually_reads():
    """Regression test for the real bug this module's docstring documents:
    attack_plans.py reads getattr(mdata, "ex", False) / "megaEx" -- these
    must exist as real attributes on CardRecord, not just as differently-
    named `is_ex`/`is_mega_ex` properties, or the CSV-fallback path's
    ex-detection silently no-ops for every card."""
    records = load_card_records()
    archaludon = records[ARCHALUDON_EX]
    assert hasattr(archaludon, "ex")
    assert hasattr(archaludon, "megaEx")
    assert getattr(archaludon, "ex", False) is True or getattr(archaludon, "megaEx", False) is True


def test_enriched_file_gives_real_engine_ground_truth_for_mega_ex():
    """The real case the old heuristic got wrong: engine ground truth says
    ex=False, megaEx=True for a true Mega Evolution ex card -- this is
    real, cross-validated data (data/raw/DATASET_UPGRADE_REPORT.md), not
    invented for this test."""
    assert DEFAULT_ENRICHED_CSV.exists(), (
        "data/raw/cards_enriched.csv is missing -- run "
        "scripts/build_engine_enriched_dataset.py first."
    )
    records = load_card_records()
    mega_lucario = records[MEGA_LUCARIO_EX]
    assert mega_lucario.ex is False
    assert mega_lucario.megaEx is True


def test_enriched_file_fixes_the_meganium_false_positive():
    """The old `"mega" in name.lower()` heuristic wrongly flagged Meganium
    (a real, ordinary non-Mega Pokemon whose name happens to start with
    "Mega") as megaEx. Real engine ground truth says otherwise."""
    records = load_card_records()
    assert records[MEGANIUM].megaEx is False


def test_disabling_enrichment_reproduces_the_exact_old_heuristic():
    """Passing enriched_csv_path=None must reproduce the pre-v7 heuristic
    behavior exactly -- including its known-wrong cases -- so this change
    is additive, not a silent behavior change for any caller that opts out."""
    records = load_card_records(enriched_csv_path=None)
    mega_lucario = records[MEGA_LUCARIO_EX]
    # The OLD heuristic's real, documented mistake: "ex" in Rule text
    # matches "Pokémon ex" even for Mega Evolution cards, so it says
    # ex=True here (wrong, per engine ground truth) -- this test pins that
    # exact old behavior for the disabled path, not the corrected one.
    assert mega_lucario.ex is True
    assert mega_lucario.is_ex is True  # the property still aliases the field


def test_missing_enriched_path_fails_closed_to_heuristic_not_a_crash():
    records = load_card_records(enriched_csv_path="/nonexistent/cards_enriched.csv")
    # Falls back silently, same as enriched_csv_path=None.
    assert records[MEGA_LUCARIO_EX].ex is True


def test_card_record_default_ex_fields_are_false():
    """A CardRecord constructed directly (no loader) defaults every v7
    ground-truth field to a safe, inert False/None -- never crashes a
    caller that only sets the required fields."""
    rec = CardRecord(card_id=1, name="x", expansion="", stage="", rule="",
                      category="", hp=None, type_="", weakness="", resistance="", retreat=None)
    assert rec.ex is False
    assert rec.megaEx is False
    assert rec.tera is False
    assert rec.aceSpec is False
    assert rec.evolvesFrom is None

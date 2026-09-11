"""Tests for the generalized guard that fixed v1's worst real bug: an
unconditional /kaggle/input/**/deck.csv glob silently loading the
competition's own sample_submission/deck.csv instead of the real deck for an
entire real ladder batch."""
from __future__ import annotations

from pokemon_agent.deck_loading import (
    validate_trusted_override, load_deck, DECK_CORE_IDS, Duraludon, Archaludon_ex, Relicanth,
)


def test_rejects_sample_submission_path_even_with_matching_core_ids():
    def parse(_path):
        return [Duraludon, Archaludon_ex, Relicanth] + [0] * 57

    result = validate_trusted_override(
        "/kaggle/input/comp/sample_submission/deck.csv", parse, DECK_CORE_IDS
    )
    assert result is None


def test_rejects_candidate_without_enough_core_id_matches():
    def parse(_path):
        return [1, 2, 3] * 20  # none of our deck's core IDs

    result = validate_trusted_override("/kaggle/input/other/deck.csv", parse, DECK_CORE_IDS)
    assert result is None


def test_accepts_a_real_looking_override():
    def parse(_path):
        return [Duraludon, Archaludon_ex, Relicanth] + [0] * 57

    result = validate_trusted_override("/kaggle/input/mydeck/deck.csv", parse, DECK_CORE_IDS)
    assert result is not None
    assert Duraludon in result and Archaludon_ex in result


def test_load_deck_falls_back_to_inline_when_no_dataset_glob_matches(tmp_path):
    inline = [Duraludon, Archaludon_ex, Relicanth] + [0] * 57
    deck, source = load_deck(inline, dataset_glob=str(tmp_path / "**" / "deck.csv"))
    assert deck == inline
    assert "inline" in source

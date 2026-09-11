"""Validated external-input loading — generalizes the guard pattern that fixed
v1's worst bug.

Finding (v1 -> v2): Kaggle auto-mounts the competition's own bundle, including
its demo `sample_submission/deck.csv`, under `/kaggle/input/...` for any
notebook attached to the competition — no explicit action required. An earlier
version's deck-loading cell searched `/kaggle/input/**/deck.csv` unconditionally
and silently matched that demo file instead of this deck's own list. An entire
real ladder batch was played on the wrong deck before this was caught by
cross-checking replay data against the deck the scoring logic was actually
written for.

The fix in the notebook was two guards specific to deck.csv: reject any path
containing "sample_submission", and require at least 2 of 3 core-defining
card IDs before trusting a candidate. `validate_trusted_override` below is
that same pattern, generalized so it can guard ANY future read from
`/kaggle/input` (or any other external/untrusted source), not just deck.csv —
this is the #1 scoped next-step from the writeup's Discussion section.
"""
from __future__ import annotations

import glob as _glob
from pathlib import Path
from typing import Callable, Iterable, Optional

SAMPLE_SUBMISSION_MARKER = "sample_submission"

Duraludon = 169
Archaludon_ex = 190
Relicanth = 57
DECK_CORE_IDS = {Duraludon, Archaludon_ex, Relicanth}


def validate_trusted_override(
    candidate_path: str,
    parse: Callable[[str], Iterable[int]],
    core_ids: set[int],
    min_core_matches: int = 2,
    reject_markers: tuple[str, ...] = (SAMPLE_SUBMISSION_MARKER,),
) -> Optional[list[int]]:
    """Return the parsed candidate if it passes both guards, else None.

    Guard 1: the path must not contain any of `reject_markers` (the confirmed
    sample_submission collision, generalized to any known-untrusted path
    fragment).
    Guard 2: the parsed content must contain at least `min_core_matches` of
    `core_ids` before it's trusted as a real override rather than unrelated
    data that happened to glob-match.
    """
    lower_path = candidate_path.lower()
    if any(marker in lower_path for marker in reject_markers):
        return None
    try:
        candidate = list(parse(candidate_path))
    except Exception:
        return None
    if len(core_ids & set(candidate)) >= min_core_matches:
        return candidate
    return None


def load_deck(
    inline_deck: list[int],
    dataset_glob: str = "/kaggle/input/**/deck.csv",
    expected_size: int = 60,
) -> tuple[list[int], str]:
    """Deck-specific wrapper over validate_trusted_override — same behavior as
    v1's fixed deck-loading cell. Returns (deck, source_description)."""

    def _parse(path: str) -> list[int]:
        return [int(x) for x in Path(path).read_text().split() if x.strip()]

    for src in sorted(_glob.glob(dataset_glob, recursive=True)):
        candidate = validate_trusted_override(src, _parse, DECK_CORE_IDS)
        if candidate is not None and len(candidate) == expected_size:
            return candidate, f"dataset override (validated core-ID match): {src}"
    assert len(inline_deck) == expected_size, (
        f"inline deck has {len(inline_deck)} cards, expected {expected_size}"
    )
    return inline_deck, "inline deck (no valid dataset override found)"

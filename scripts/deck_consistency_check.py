#!/usr/bin/env python3
"""Deck consistency / legality audit.

Two independent checks, both born from real problems found in this project's
history:

1. TRUSTED-OVERRIDE AUDIT (deck_loading.load_deck): the exact bug class that
   cost an entire real ladder batch in v1 -- a Kaggle-auto-mounted, unrelated
   deck.csv silently overriding the real deck. Reports which deck was
   actually loaded (inline vs. a validated dataset override) and refuses to
   proceed silently if the override guard's core-ID check barely passed
   (e.g. exactly at the min_core_matches threshold) without flagging it.

2. TCG LEGALITY AUDIT: standard deck-construction rules -- exactly 60 cards,
   max 4 copies of any card except Basic Energy (unlimited) and ACE SPEC
   cards (max 1 total across all ACE SPECs). Uses the real engine's
   card_table when available so "is this an ACE SPEC / Basic Energy card" is
   looked up from real data, not guessed.

Usage:
    python3 scripts/deck_consistency_check.py [deck.csv]
    (defaults to ./deck.csv)

Exit code is nonzero if any check fails, so this is CI/pre-submission-safe.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pokemon_agent.deck_loading import load_deck, DECK_CORE_IDS  # noqa: E402
from pokemon_agent.card_data import load_card_table  # noqa: E402

BASIC_ENERGY_CARD_TYPE_VALUE = 5  # cg.api.CardType.BASIC_ENERGY


def audit_trusted_override(deck_path: str) -> tuple[list[int], list[str]]:
    problems = []
    inline_deck = [int(x) for x in open(deck_path).read().split() if x.strip()]
    deck, source = load_deck(inline_deck)
    print(f"[override audit] source: {source}")
    matched_core = DECK_CORE_IDS & set(deck)
    print(f"[override audit] core-ID matches: {len(matched_core)}/{len(DECK_CORE_IDS)} "
          f"({sorted(matched_core)})")
    if "dataset override" in source and len(matched_core) == 2:
        problems.append(
            "Dataset override matched the MINIMUM required core IDs (2/3) -- "
            "borderline trust. Verify this is really the intended deck before "
            "shipping, not a coincidental glob match."
        )
    return deck, problems


def audit_legality(deck: list[int]) -> list[str]:
    problems = []
    counts = Counter(deck)

    if len(deck) != 60:
        problems.append(f"Deck has {len(deck)} cards, expected 60.")

    try:
        card_table, _attack_table, source = load_card_table(prefer_engine=True)
    except Exception as e:
        print(f"[legality audit] WARNING: could not load engine card table ({e}); "
              f"falling back to the generic max-4 rule for every card.")
        card_table, source = {}, "unavailable"
    print(f"[legality audit] card table source: {source}")

    ace_spec_count = 0
    for card_id, count in sorted(counts.items()):
        data = card_table.get(card_id)
        is_basic_energy = bool(data) and getattr(data, "cardType", None) == BASIC_ENERGY_CARD_TYPE_VALUE
        is_ace_spec = bool(data) and getattr(data, "aceSpec", False)
        name = getattr(data, "name", f"id={card_id}") if data else f"id={card_id} (not in card table)"

        if is_ace_spec:
            ace_spec_count += count
            if count > 1:
                problems.append(f"{name}: {count} copies, but ACE SPEC allows max 1.")
        elif not is_basic_energy and count > 4:
            problems.append(f"{name}: {count} copies, exceeds the max-4 rule.")

    if ace_spec_count > 1:
        problems.append(
            f"{ace_spec_count} total ACE SPEC cards across the deck -- only 1 is legal, "
            f"even split across different ACE SPEC cards."
        )
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck_path", nargs="?", default="deck.csv")
    args = parser.parse_args()

    all_problems = []
    deck, override_problems = audit_trusted_override(args.deck_path)
    all_problems.extend(override_problems)
    all_problems.extend(audit_legality(deck))

    print()
    if all_problems:
        print(f"FAILED -- {len(all_problems)} problem(s) found:")
        for p in all_problems:
            print(f"  - {p}")
        sys.exit(1)
    else:
        print(f"OK -- {len(deck)}-card deck passed the override-trust and legality audits.")
        sys.exit(0)


if __name__ == "__main__":
    main()

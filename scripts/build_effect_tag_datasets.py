#!/usr/bin/env python3
"""Derives two new, real, transparent enrichment tables from text already
present in `data/raw/attacks_enriched.csv` and `data/raw/abilities_enriched.csv`
(both built from real engine ground truth by
`scripts/build_engine_enriched_dataset.py`):

    data/raw/attack_effect_tags.csv    -- one row per attack, boolean columns
                                           for real, keyword-matched effect
                                           categories (status conditions,
                                           coin flips, energy discard, etc.)
    data/raw/ability_trigger_tags.csv  -- one row per named ability, boolean
                                           columns for real, keyword-matched
                                           trigger-timing categories

METHODOLOGY, stated plainly: this is regex/keyword matching over the real
printed effect text already in the dataset -- not an LLM classifier, not
hand-labeled, not fabricated. It is intentionally conservative (a handful
of clear, high-precision patterns) rather than exhaustive, and every tag's
real match count is printed when this script runs and recorded in
data/raw/DATASET_UPGRADE_REPORT.md so nobody downstream mistakes "matched
this keyword pattern" for "a verified rules engine parse." A card whose
real effect uses unusual phrasing this pattern set doesn't anticipate will
simply not get that tag -- false negatives are expected and considered
safer than false positives here, since every pattern was written to be
specific rather than broad.

Usage:
    python3 scripts/build_effect_tag_datasets.py
"""
from __future__ import annotations

import csv
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ATTACKS_IN = os.path.join(REPO_ROOT, "data", "raw", "attacks_enriched.csv")
ABILITIES_IN = os.path.join(REPO_ROOT, "data", "raw", "abilities_enriched.csv")
ATTACKS_OUT = os.path.join(REPO_ROOT, "data", "raw", "attack_effect_tags.csv")
ABILITIES_OUT = os.path.join(REPO_ROOT, "data", "raw", "ability_trigger_tags.csv")

# Ordered so the printed report lists them in a stable, meaningful order.
ATTACK_EFFECT_PATTERNS = [
    ("inflicts_poisoned", r"\bpoison(ed)?\b"),
    ("inflicts_burned", r"\bburn(ed)?\b"),
    ("inflicts_paralyzed", r"\bparalyz"),
    ("inflicts_confused", r"\bconfus"),
    ("inflicts_asleep", r"\basleep\b"),
    ("coin_flip", r"\bflip (a|\d+) coin"),
    ("discards_energy", r"discard.{0,20}energy"),
    ("discards_own_hand", r"discard your hand"),
    ("heals", r"\bheal(s)?\b"),
    ("draws_cards", r"\bdraw\b"),
    ("switches_pokemon", r"switch (in|out)|switch .*pok[eé]mon"),
    ("prevents_or_reduces_damage", r"prevent(s)? .*damage|reduce.*damage"),
    ("hits_the_bench", r"bench"),
    ("self_damage", r"this pok[eé]mon (also )?(takes|does)|does \d+ damage to itself"),
    ("references_knock_out", r"knocked out"),
    ("ignores_weakness_resistance", r"weakness and resistance"),
]

ABILITY_TRIGGER_PATTERNS = [
    ("once_per_turn", r"once during your turn"),
    ("passive_static", r"as long as this"),
    ("on_play_or_enter", r"when you play this|when this pok[eé]mon is (put|placed) into play"),
    ("on_damaged", r"is damaged by"),
    ("on_knock_out", r"when.*knocked out"),
    ("on_attack", r"when this pok[eé]mon attacks"),
]


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    attacks = _read_csv(ATTACKS_IN)
    abilities = _read_csv(ABILITIES_IN)

    print(f"Read {len(attacks)} real attacks from {ATTACKS_IN}")
    print(f"Read {len(abilities)} real abilities from {ABILITIES_IN}")

    attack_counts = {tag: 0 for tag, _ in ATTACK_EFFECT_PATTERNS}
    with open(ATTACKS_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["attack_id", "attack_name", "card_id", "card_name"] + [t for t, _ in ATTACK_EFFECT_PATTERNS])
        for a in attacks:
            text = (a.get("text") or "").lower()
            row_flags = []
            for tag, pat in ATTACK_EFFECT_PATTERNS:
                hit = bool(re.search(pat, text)) if text else False
                if hit:
                    attack_counts[tag] += 1
                row_flags.append(int(hit))
            w.writerow([a["attack_id"], a["move_name"], a["card_id"], a["card_name"]] + row_flags)
    print(f"Wrote {len(attacks)} rows to {ATTACKS_OUT}")
    print("Real match counts (of", sum(1 for a in attacks if a.get("text")), "attacks with real effect text):")
    for tag, n in attack_counts.items():
        print(f"  {tag}: {n}")

    ability_counts = {tag: 0 for tag, _ in ABILITY_TRIGGER_PATTERNS}
    with open(ABILITIES_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["card_id", "card_name", "ability_name"] + [t for t, _ in ABILITY_TRIGGER_PATTERNS])
        for a in abilities:
            text = (a.get("ability_text") or "").lower()
            row_flags = []
            for tag, pat in ABILITY_TRIGGER_PATTERNS:
                hit = bool(re.search(pat, text)) if text else False
                if hit:
                    ability_counts[tag] += 1
                row_flags.append(int(hit))
            w.writerow([a["card_id"], a["card_name"], a["ability_name"]] + row_flags)
    print(f"\nWrote {len(abilities)} rows to {ABILITIES_OUT}")
    print(f"Real match counts (of {len(abilities)} real named abilities):")
    for tag, n in ability_counts.items():
        print(f"  {tag}: {n}")


if __name__ == "__main__":
    main()

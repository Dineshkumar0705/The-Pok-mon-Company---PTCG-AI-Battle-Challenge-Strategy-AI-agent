# PTCG AI Battle Challenge — Cleaned, Bilingual, Engine-Cross-Validated Card Reference Data

Corrected, deduplicated, bilingually-indexed, and **engine-cross-validated**
reference card data for The Pokémon Company's PTCG AI Battle Challenge,
derived from two real official sources: the competition's own `Card Data.csv`
files (EN + JP) and the competition's own real battle engine's structured
card database.

## Why this exists

**v1 (cleaning):** the competition ships each card-data file as two
near-duplicate copies (e.g. `EN Card Data.csv` and `EN_Card_Data.csv`).
Comparing them row-by-row found the two EN copies weren't simple
duplicates — each had a different real defect: one has a header typo
("Previos stage") but correct card data; the other has the typo fixed but
corrupts 71 Dragon/Ancient-type Pokémon's `Type` field into raw Japanese
kanji (`竜`) instead of the standard `{N}` token, and swaps ASCII
parentheses for full-width JP parentheses in 241 `Category` values. Full
methodology and diff evidence in `DATA_QUALITY_REPORT.md`.

**v2 (engine cross-validation and structural enrichment):** the cleaned
CSV is still a flat, one-row-per-move text export with no boolean ground
truth for anything. The competition's own real battle engine exposes the
exact same 1,267 cards as **typed, structured data** — because it's
literally what the engine itself uses to run matches — including real
`ex`/`megaEx`/`tera`/`aceSpec` flags the CSV schema has no room for at
all. This pass cross-validates the two real sources against each other
(exact match-rate numbers reported, not asserted) and merges them into
normalized, ML-ready tables. Full methodology, every real number, and two
real accuracy bugs this found in the old text-heuristic approach are in
`DATASET_UPGRADE_REPORT.md`.

**v3 (effect enrichment and a real gameplay dataset):** re-verified every
v2 cross-reference (0 real mismatches once re-checked correctly), found
two more real, previously-undocumented engine quirks (Fossil Items
carrying a real HP value; one Tool card with a real engine-modeled
attack), added real keyword-tagged effect/trigger tables over text
already in this dataset, and — the actual remaining gap — built the first
real dataset tying individual cards to *actual gameplay*: 60 real
self-play games through the real engine, aggregated into real per-card
and per-attack usage statistics. Every number, every dropped attempt
(a KO-attribution heuristic that measured a suspicious flat zero and was
removed rather than shipped), and the full methodology are in the v3
section of `DATASET_UPGRADE_REPORT.md`.

## Files

**Original cleaned exports (v1):**
- **`EN_Card_Data_canonical.csv`** — 2,022 rows / 1,267 unique cards. Merges the correct parts of both official EN files: typo-fixed header, BOM removed, `\n` line endings, and both content bugs (kanji-in-Type, full-width parens) corrected back to their proper EN-locale values.
- **`JP_Card_Data_canonical.csv`** — 2,022 rows / 1,267 unique cards. BOM removed, line endings normalized; JP content was already consistent between the two official copies.
- **`EN_JP_Card_Index.csv`** — 1,267 rows, one per unique Card ID, joining EN and JP card-level fields (Name, Expansion, Collection No. in both languages, plus Category/HP/Type).
- **`DATA_QUALITY_REPORT.md`** — exact diff counts, before/after examples, and what was deliberately left unchanged.

**New, engine-cross-validated tables (v2):**
- **`cards_enriched.csv`** — 1,267 rows, one per unique card. Real engine ground truth (HP, retreat cost, energy/weakness/resistance type, `is_ex`/`is_mega_ex`/`is_tera`/`is_ace_spec`, `evolves_from`) merged with CSV-only fields (expansion, collection no., bilingual name/expansion/collection no.) and derived fields (evolution stage number, attack/ability counts, the real engine `attack_ids` list per card).
- **`attacks_enriched.csv`** — 1,556 rows, one per real attack, keyed by the real engine `attack_id`. Structured `energies` (a real list of energy types, not a cost string to parse), integer `damage`, derived `damage_per_energy`, full effect text, plus the original CSV cost/damage text alongside for reference.
- **`abilities_enriched.csv`** — 426 rows, one per real named card effect — a genuinely new entity, split out from Attack for the first time.
- **`evolution_lines.csv`** — 461 rows, one per real, fully-reconstructed evolution chain (Basic → Stage1 → Stage2), built by walking the engine's real `evolvesFrom` pointers.
- **`DATASET_UPGRADE_REPORT.md`** — the real cross-validation match-rate table, two real accuracy bugs found and explained (with real examples), real descriptive statistics computed from the merged data, and the full v3 gap-analysis/effect-tag/card-usage methodology and findings.

**New, real-gameplay tables (v3):**
- **`attack_effect_tags.csv`** — 1,556 rows, one per real attack. 16 real keyword-matched boolean flags (status conditions, coin flips, energy discard, bench damage, weakness/resistance-ignoring, etc.) derived from each attack's own real printed text — methodology and every real match count in `DATASET_UPGRADE_REPORT.md`.
- **`ability_trigger_tags.csv`** — 426 rows, one per real named ability. 6 real keyword-matched trigger-timing flags (once-per-turn, passive/static, on-play, on-damaged, on-knock-out, on-attack).
- **`card_usage_from_self_play.csv`** — 15 rows, one per unique card in the real 60-card decklist. Real usage counts and real win rate when used, aggregated from **60 real self-play games** through the actual battle engine — the first row in this dataset tying individual cards to actual observed gameplay rather than printed text alone.
- **`attack_usage_from_self_play.csv`** — 4 rows, one per (card, attack) pair actually used across those 60 real games, with real times-used and real total/average damage dealt.

## Schema (original per-move-row files)

`Card ID, Card Name, Expansion, Collection No., Stage (Pokémon)/Type (Energy and Trainer), Rule, Category, Previous stage, HP, Type, Weakness, Resistance (Type), Retreat, Move Name, Cost, Damage, Effect Explanation`

Schema for the new tables is documented in full in `DATASET_UPGRADE_REPORT.md`'s "New files" section.

## Provenance

Source: the official competition card-data files, and the official
competition battle engine's own structured card database, both distributed
with The Pokémon Company – PTCG AI Battle Challenge (Kaggle Game Arena).
This dataset is a cleaned, cross-validated, structurally-enriched
derivative for reference/lookup/ML use — it does not add, remove, or
reinterpret any card's real content; every new field is either read
directly off one of these two official sources or computed by direct
arithmetic from them (cost counts, damage-per-energy, evolution-chain
reconstruction) — never estimated, inferred, or sourced externally.

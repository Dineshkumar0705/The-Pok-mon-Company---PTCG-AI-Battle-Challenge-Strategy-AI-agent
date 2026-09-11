# Reference Dataset Upgrade — Engine Cross-Validation & Structured Enrichment

*Sep 11, 2026 · Extends `DATA_QUALITY_REPORT.md` (which cleaned formatting/encoding
defects in the official CSVs). This pass is different in kind: it cross-validates
the cleaned CSV against a second, independent, authoritative source — the real
organizer-supplied battle engine's own structured card data
(`cg.api.all_card_data()` / `all_attack()`, the exact data the engine itself
runs matches on) — and merges the two into normalized, ML-ready tables. Every
number below is computed from these two real sources; nothing is estimated,
guessed, or sourced from outside this project's own already-verified inputs.
No external competitive-meta numbers (win rates, tier lists) are added here —
that would need real, cited sources, a separate and honestly-scoped task, not
something a data merge should invent.*

## Why this is a real, defensible upgrade, not just more columns

The original cleaned dataset (`EN/JP_Card_Data_canonical.csv` + `EN_JP_Card_Index.csv`)
is a flat, one-row-per-move text export: 3 files, 17 raw text columns, no
boolean ground truth for anything, no separate concept of "Ability" vs.
"Attack," no way to reconstruct a card's real evolution line, and (per
`src/pokemon_agent/card_data.py`'s own prior docstring) two fields —
`ex` and `megaEx` — that could only ever be *guessed* from text, not read as
real data, because the schema had no dedicated flag for either.

`vendor/cg`, the real proprietary battle engine, exposes the exact same
1,267 cards through `all_card_data()`/`all_attack()` as **typed, structured
data** — because it's literally what the engine itself uses to legally
validate and score every real match. That includes real boolean ground
truth for `ex`, `megaEx`, `tera`, and `aceSpec` (none of which the CSV
schema encodes at all), real `IntEnum` weakness/resistance/energy types,
real integer HP/retreat cost/damage, and two entities the flat CSV never
modeled as their own thing: a genuine engine `attackId` per attack (the old
CSV loader's own docstring says explicitly this "cannot be faithfully
replayed from the CSV alone" — now it can), and Ability as a distinct
entity from Attack (the CSV already tags these rows with a `[Ability] `
prefix in `Move Name` — real text that was already there, just never
modeled as its own table).

`scripts/build_engine_enriched_dataset.py` builds the merge and prints the
real cross-validation numbers below every time it runs — nothing here is a
one-off manual check.

## Real cross-validation: does the CSV agree with engine ground truth?

| Field | Cards checked | Real matches | Match rate |
|---|---|---|---|
| Name | 1,267 | 1,267 | 100.0% |
| HP | 1,267 | 1,267 | 100.0% |
| Retreat cost | 1,267 | 1,267 | 100.0% |
| Weakness type | 1,267 | 1,267 | 100.0% |
| `evolvesFrom` | 1,267 | 1,262 | 99.6% |
| Attack damage (numeric CSV rows only) | 1,173 | 1,173 | 100.0% |
| Ability-row-count vs. engine `skills` count | 1,267 | 1,064 | 84.0% |

Every full-agreement row above (name/HP/retreat/weakness/damage) is a real,
strong confirmation that both sources describe the same cards correctly —
worth stating plainly, since a merge is only as trustworthy as its inputs
agree with each other.

**The two real, explained disagreements:**
- **`evolvesFrom`, 5 real mismatches — all Fossil items** (Antique Root/
  Cover/Plume/Jaw/Sail Fossil). The CSV's `Previous stage` column is
  overloaded for these five cards to mean "evolves INTO" ("Evolve to
  Lileep") rather than its normal "evolved FROM" meaning everywhere else —
  a real column-semantics quirk in the source data, not an error either
  side made. The engine's own `evolvesFrom` is `None` for these (correctly:
  Fossils are Basic Pokémon, they don't evolve *from* anything), so the
  merged `cards_enriched.csv` keeps the engine's real value.
- **Ability-row-count mismatch, 203 cards — a real, fully explained labeling
  convention, not a data error.** Every one of the 203 is a non-Pokémon
  card (77 Item, 61 Supporter, 27 Tool, 26 Stadium, 12 Special Energy —
  counts that sum exactly to 203). The engine models every named card
  effect as a `Skill` regardless of card type, but the CSV's `[Ability] `
  prefix convention is reserved specifically for Pokémon Abilities — so
  these 203 non-Pokémon cards' effect text simply was never going to carry
  that prefix. Not a defect; a naming-convention difference this report
  makes explicit instead of silently merging over.

## Two real, previously-shipping accuracy bugs this merge found and fixed

`src/pokemon_agent/card_data.py`'s CSV-fallback loader could only ever
*guess* `ex`/`megaEx` from text, because the CSV schema has no such flags.
Cross-validated against real engine ground truth:

| Heuristic | Cards checked | Correct | Wrong | Real examples of the wrong cases |
|---|---|---|---|---|
| `"ex" in Rule.lower()` (old `ex` guess) | 1,267 | 1,237 | 30 | Every real Mega Evolution ex card (Mega Lucario ex, Mega Venusaur ex, Mega Absol ex, …) — the heuristic can't distinguish `ex` from `megaEx`, but the real game treats them as separate flags with different prize-card rules |
| `"mega" in Name.lower()` (old `megaEx` guess) | 1,267 | 1,263 | 4 | Meganium, Yanmega ex, Megaton Blower, Mega Signal — ordinary cards whose name merely *starts with* "Mega" |

**A third, structurally worse bug, found while fixing the first two:** the
live decision code that actually reads these flags
(`attack_plans.py`: `getattr(mdata, "ex", False)` /
`getattr(mdata, "megaEx", False)`) reads the *engine's own attribute
names* — but `CardRecord` only ever exposed `is_ex`/`is_mega_ex` as
differently-named *properties*. In CSV-fallback mode, those `getattr()`
calls therefore always silently returned the default `False`, for every
card — including this deck's own Archaludon ex — making the fallback
path's ex-detection structurally inert, not just approximately right. The
real, scored submission was never affected (it always uses the live
engine's real `CardData`, which always has real `.ex`/`.megaEx`
attributes) — this only affected offline analysis run through the CSV
fallback. All three fixed together in `card_data.py`: `CardRecord` now
carries real `ex`/`megaEx`/`tera`/`aceSpec`/`evolvesFrom` fields (matching
the engine's own attribute names), populated from
`cards_enriched.csv`'s real engine ground truth when that file exists, and
falling back to the exact same two (now honestly-labeled-as-approximate)
heuristics when it doesn't — never worse than before, real ground truth
when available. See `tests/test_card_data.py` for the regression coverage,
including a test that pins the OLD heuristic's exact known-wrong behavior
for callers that explicitly opt out of enrichment.

## New files

| File | Rows | What it is |
|---|---|---|
| `cards_enriched.csv` | 1,267 | One row per unique card: every engine ground-truth field (HP, retreat cost, energy/weakness/resistance type, `is_ex`/`is_mega_ex`/`is_tera`/`is_ace_spec`, `evolves_from`), plus CSV-only fields (expansion, collection no., JP name/expansion/collection no. via the existing bilingual index), plus derived fields (`evolution_stage_number`, `num_attacks`, `num_abilities`, `has_ability`, and the real `attack_ids` list — the engine `attackId`s the old CSV loader's own docstring said couldn't be reconstructed) |
| `attacks_enriched.csv` | 1,556 | One row per real attack, keyed by the real engine `attack_id`: structured `energies` (list of real energy types, not a cost string to parse), integer `damage`, derived `damage_per_energy`, full effect `text`, plus the original CSV `cost`/`damage` text alongside for reference/cross-check |
| `abilities_enriched.csv` | 426 | One row per real named card effect (`Skill` in engine terms) — a genuinely new entity this project's data never modeled separately from Attack before |
| `evolution_lines.csv` | 461 | One row per real, fully-reconstructed evolution chain (Basic → Stage1 → Stage2), built by walking the engine's real `evolvesFrom` pointers — not previously queryable at all; the flat CSV only ever stated one card's *immediate* predecessor |

## Real descriptive statistics (computed, not estimated)

Card type distribution: 1,056 Pokémon, 77 Item, 61 Supporter, 27 Tool, 26
Stadium, 12 Special Energy, 8 Basic Energy.

Stage distribution (Pokémon only): 600 Basic, 345 Stage1, 116 Stage2, 206
non-Pokémon rows unaffected.

Real, engine-ground-truth counts that the old CSV schema couldn't
represent at all: **121 `ex`**, **30 `megaEx`**, **32 `tera`**, **29
`aceSpec`** cards; **421 cards carry at least one real named effect**
(Pokémon Ability or, for non-Pokémon cards, the engine's own generic
effect-text entity — see the ability-row-count explanation above); **1,556
real attacks** and **426 real named card effects** now individually
queryable in their own table, not buried in free text.

Pokémon energy-type distribution: Grass 157, Psychic 138, Water 137,
Fighting 121, Darkness 116, Colorless 104, Fire 103, Metal 69, Lightning
76, Dragon 35.

Attack cost (# energy symbols) distribution: 1-cost 670, 2-cost 447,
3-cost 364, 4-cost 62, 5-cost 8, 0-cost 5.

Nonzero attack damage: n=1,175, min 10, max 350, mean 70.2.

HP by real stage: Basic n=595 (mean 97.5, range 30–310), Stage1 n=345
(mean 136.7, range 60–350), Stage2 n=116 (mean 207.7, range 120–380) — a
real, monotonic HP-by-evolution-stage relationship, computed from the
merged data, not asserted.

**Resistance is `None` for 1,047 of 1,267 cards.** Read honestly: this
matches the real, current-era TCG rule change (post-2023 rotation) that
removed Resistance from nearly all Pokémon — not a data gap, a real
reflection of the actual printed cards in this exact card pool.

## What this upgrade deliberately does not include

No competitive-meta statistics (deck tier lists, real-world win rates,
matchup frequencies) — those exist in the world (Limitless TCG event
data, etc.) but adding them here would need real, individually cited
external sources, which is separate, scoped research work this merge does
not attempt to fold in silently. No fabricated "power rating" or
similarity score — anything like that would be a modeling choice
presented as data, which is exactly the kind of overclaiming this
project's own discipline exists to avoid. The four new CSVs above contain
only real fields read directly off the two verified sources, or arithmetic
derived directly from them (cost counts, damage-per-energy, evolution
chain reconstruction) — nothing inferred, ranked, or scored.

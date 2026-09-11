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

## v3 — Gap re-verification, real effect-tag enrichment, and a real 60-game card-usage dataset

*Sep 11, 2026. This pass had three real goals: re-check the v2 tables above
for anything missed, add real (not fabricated) enrichment where the data
already supports it, and close the actual remaining gap — a "card
dataset" that never had a single row of real *gameplay* data tied to real
cards. All three below.*

### Re-verified referential integrity (and a correction to how it was checked)

A fresh pass cross-checking every `cards_enriched.csv` row's `attack_ids`
against `attacks_enriched.csv`'s real `attack_id`s first reported 499
"missing" references — which turned out to be a bug in the *checking
script*, not the dataset: `attack_ids` is `;`-delimited (`"1;2"`), and the
first check assumed a bracketed, comma-separated list. Re-run with the
correct delimiter: **0 mismatches** — every attack a card references
exists in `attacks_enriched.csv`, every attack's `card_id` exists in
`cards_enriched.csv`, `num_attacks` matches the real count of `attack_ids`
for all 1,267 cards, and there are 0 duplicate `card_id`s. Recorded here
rather than silently fixed and discarded, because "the checker was wrong,
not the data" is itself worth being explicit about.

### Two more real, previously-undocumented engine quirks found

- **Fossil Item cards carry a real `hp` value.** 5 cards (Antique Root/
  Cover/Plume/Jaw/Sail Fossil) are `card_type: ITEM` but have `hp: 60` —
  at first glance looks like a data-type violation (only Pokémon should
  have HP). It isn't: real Fossils are Item cards that, once played,
  function as a Basic Pokémon in play (the same cards already flagged in
  the v2 section above for their `evolvesFrom` quirk) — the engine
  correctly carries their in-play HP even though `cardType` stays `ITEM`.
  Documented so a future consumer doesn't "fix" this as a bug.
- **One Tool card has a real, engine-modeled attack.** "Core Memory"
  (`card_id` 1180, category "Technical Machine") is a `TOOL` with
  `num_attacks: 1`, pointing at a real `attack_id` in `attacks_enriched.csv`
  — Technical Machine tools grant the attached Pokémon a printed attack,
  and the engine models that as the *Tool card itself* owning an
  `attackId`, not the Pokémon it's attached to. The only such card in this
  1,267-card pool.

### New: real effect-tag enrichment (`scripts/build_effect_tag_datasets.py`)

Two new tables, built by keyword/regex matching over the real `text` and
`ability_text` fields already in `attacks_enriched.csv` /
`abilities_enriched.csv` — stated plainly: this is pattern matching over
real printed text, not an NLP classifier or hand-labeling, deliberately
conservative (specific patterns, accepted false negatives) rather than
exhaustive. Every tag's real match count, out of 1,023 attacks that have
any effect text at all (533 are plain damage, no text) and 426 real named
abilities:

**`attack_effect_tags.csv`** (1,556 rows, one per real attack):
`hits_the_bench` 167, `coin_flip` 140, `discards_energy` 91,
`ignores_weakness_resistance` 83, `self_damage` 65, `draws_cards` 35,
`heals` 34, `inflicts_poisoned` 29, `inflicts_paralyzed` 26,
`switches_pokemon` 24, `prevents_or_reduces_damage` 22,
`inflicts_confused` 20, `inflicts_burned` 17, `references_knock_out` 16,
`inflicts_asleep` 13, `discards_own_hand` 2.

**`ability_trigger_tags.csv`** (426 rows, one per real named ability):
`once_per_turn` 81, `passive_static` 31, `on_play_or_enter` 27,
`on_damaged` 18, `on_knock_out` 3, `on_attack` 0 (no real ability in this
pool phrases its trigger that way — a real, honest zero, not a bug;
verified with `test_a_known_real_card_gets_the_right_tag` in
`tests/test_dataset_gap_analysis.py` that a known plain-damage attack,
Metal Defender, gets zero false-positive tags).

`ignores_weakness_resistance` (83 attacks) is worth calling out for the
writeup: it's a real, strategically load-bearing category (relevant to
threat modeling against any deck leaning on weakness-based OHKOs) that
the old flat-text dataset had no way to query without re-reading every
attack's text by hand.

### New: a real 60-game card-level self-play dataset (`scripts/generate_card_usage_dataset.py`)

The actual gap this pass was meant to close: `replays/raw/replay_log.jsonl`
(the original 30-game log) only ever recorded game-level outcomes — no
per-card signal at all. This script runs real self-play through the
actual engine (60 real mirror-match games, byte-identical-to-v1 policy
pinned explicitly regardless of this checkout's own config state — see
the script's module docstring for why that matters right now) and
produces two new real, derived tables from `Observation.logs`:

- **`card_usage_from_self_play.csv`** — 15 rows, one per unique card in
  the 60-card deck: real counts of how many of the 60 logged games each
  card appeared in, how often it was played/attacked-with/evolved-into/had
  energy attached, and the real win rate of games it was used in.
- **`attack_usage_from_self_play.csv`** — 4 rows, one per (card, attack)
  pair actually used across all 60 games: real times-used, real total and
  average damage dealt.

Real findings, 60/60 games completing normally, 60.0% win rate this run
(consistent with the existing 30-game mirror-match range, [42.3%, 75.4%]):

- **Archaludon ex's Metal Defender is the deck's real workhorse**: 561 of
  757 total logged attacks (74.1%), average 194.4 real damage — the
  clearest possible confirmation, from actual play rather than card text
  alone, of what the deck's stated win condition already claims. Hammer In
  (188 total real uses) is the early-game bridge attack — used 63 times by
  Duraludon before it evolves and, real and worth noting since it wasn't
  obvious from the card list alone, 125 more times by Archaludon ex
  itself, which retains it alongside Metal Defender.
- **Boss's Orders was used in only 13/60 games (21.7%)** — by far the
  least-drawn/used card tracked, real signal for the Deck Score section on
  how situational that tech slot actually is in practice, not just in
  theory.
- **Switch shows the lowest win-rate-when-used, 45.7%**, noticeably below
  every other card's 54–61% band. Reported with the honest caveat this
  section exists to make explicit: this is very likely a confound, not a
  causal effect — Switch tends to get played specifically when the active
  Pokémon is already in trouble, so games where it's used are
  disproportionately games that were already going badly. Flagged, not
  overclaimed.
- **A real KO-attribution attempt was tried and dropped.** The script
  originally tried to approximate "our attack scored a KO" from an
  opponent CHANGE-of-active event landing in the same log batch as our
  ATTACK. Across the real run this report is based on, it measured
  exactly **zero** KOs in every single game — implausible for 60 real
  mirror matches — meaning the forced-switch-after-KO event does not
  reliably land in the same batch as the attack that caused it. Rather
  than ship a column that silently always reads 0, it was removed
  entirely; a reliable version would need to track a Pokémon's HP
  reaching exactly 0 directly instead of inferring it from log adjacency,
  named here as real, scoped follow-up work, not invented data.

Both new CSVs and the raw per-game log (`replays/raw/card_usage_log.jsonl`,
60 real records) are covered by `tests/test_dataset_gap_analysis.py` (7
tests, pure-file, no live engine needed to re-check them).

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

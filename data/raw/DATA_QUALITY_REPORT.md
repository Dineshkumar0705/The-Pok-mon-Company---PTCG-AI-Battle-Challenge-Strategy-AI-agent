# Competition Reference Dataset — Cleanup Report

*Checked Sep 10, 2026. Scope: reference card-data CSVs only (EN/JP `Card Data.csv` pairs). This is background/reference material for your own lookup use — it does not change anything in the graded Strategy writeup, which describes the already-built and already-scored agent as-is.*

## What was in the folder

Four CSVs, in two duplicate-looking pairs (`EN Card Data.csv` / `EN_Card_Data.csv`, `JP Card Data.csv` / `JP_Card_Data.csv`), plus two duplicate-looking PDF pairs. All four CSVs share the same schema: `Card ID, Card Name, Expansion, Collection No., Stage/Type, Rule, Category, Previous stage, HP, Type, Weakness, Resistance, Retreat, Move Name, Cost, Damage, Effect Explanation` — one row per attack/ability, so a card with 2 attacks has 2 rows. 2,022 rows / 1,267 unique Card IDs in both EN files; 2,022 rows / 1,267 unique Card IDs in both JP files.

## What was actually wrong (not just cosmetic)

A row-by-row, column-by-column diff of each pair found:

**JP pair** — genuinely just a formatting difference. `JP Card Data.csv` has a UTF-8 BOM; `JP_Card_Data.csv` doesn't. No content differs. Not a data problem.

**EN pair** — this one has two real content bugs, not just formatting, and they're split across the two files (neither file is simply "the good one"):

| Issue | `EN Card Data.csv` (space name) | `EN_Card_Data.csv` (underscore name) |
|---|---|---|
| Header typo | "Previos stage" (typo) | "Previous stage" (fixed) |
| BOM | present | absent |
| **Type column, 71 rows** | correct: `{N}` (the standard type-icon token used everywhere else in the file) | **corrupted: raw kanji `竜` ("dragon")** — every Ancient/Dragon-type Pokémon (Koraidon, Miraidon, Raging Bolt, Dragapult ex, Applin/Dreepy/Drakloak lines, Altaria, Dialga, Turtonator, etc.) has its Type field silently replaced with a Japanese character in the *English* file |
| **Category column, 241 rows** | correct: ASCII parens, e.g. `Trainer's Pokémon(Team Rocket)` | **corrupted: full-width JP parens**, e.g. `Trainer's Pokémon（Team Rocket）`, leaking into English text |
| Line endings inside multi-line fields | `\r\n` | `\n` |

Best guess at cause: the underscore-named file looks like a later re-export where someone ran a find/replace pass (fixed the header typo) but the pass also mangled `{N}` → `竜` and half-width → full-width parens somewhere in the pipeline, most likely because that step touched JP-adjacent tooling. Whatever the cause, `EN_Card_Data.csv` is not simply the "corrected" version of `EN Card Data.csv` — each file is right about something the other gets wrong.

## What I built

Three files, written into `competition dataset/cleaned/` alongside your originals (nothing original was modified or deleted):

1. **`EN_Card_Data_canonical.csv`** — header typo fixed, BOM removed, line endings normalized to `\n`, and the two content bugs corrected: `Type` values restored to `{N}` (not `竜`) and `Category` parens restored to ASCII. Content values otherwise come from `EN Card Data.csv` (the file that had the bugs) — 2,022 rows, 1,267 unique Card IDs, verified zero remaining kanji leakage and zero remaining full-width parens.
2. **`JP_Card_Data_canonical.csv`** — same file, BOM removed, line endings normalized. Content was already consistent between the two JP originals, so nothing else changed. 2,022 rows.
3. **`EN_JP_Card_Index.csv`** — new: a 1,267-row bilingual lookup, one row per unique Card ID, joining EN and JP card-level fields (Name, Expansion, Collection No. in both languages, plus Category/HP/Type). Verified the Card ID sets match 1:1 between EN and JP and that card-level fields (name/expansion/category/HP/type) are internally consistent across a card's own move-rows before building this, so the join is safe. Useful if you ever want to cross-reference a card by JP name/set code against its EN identity, or vice versa.

One data quirk worth knowing about but **not changed**: Basic Energy cards (Card IDs 1–5) show `Expansion = n/a` and `Collection No. = GRA/FIR/WAT/LIG/PSY` (an energy-type code sitting in the set-number field) in both original JP files. That's how the competition's own source data encodes those five rows — it's consistent in both files, so it's not something the dedup introduced, and I didn't guess at "fixing" it without knowing whether it's intentional.

## What I didn't touch

The two duplicate PDF pairs (`Card_ID List_EN(_).pdf` at ~137MB, `Card_ID List_JP(_).pdf` at ~182MB). Each pair matches exactly in file size, which is consistent with them being byte-identical duplicates, but I haven't verified that byte-for-byte (they're too large to be worth transferring for a reference-only check), and I haven't deleted anything from your folder — deleting requires your explicit permission. If you want, say the word and I'll request delete access and remove the redundant copy of each pair after confirming they're identical.
